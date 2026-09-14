"""Tests for the OGR geometry -> JSON-FG ``place`` encoder."""

import pytest
from conftest import geom

from pygeoapi_formatter_jsonfg.geometry import (MAX_CIRCULARSTRING_POSITIONS,
                                                JsonFgError, geometry_to_place,
                                                has_arcs)


# --------------------------------------------------------------------------- #
# The six simple GeoJSON types, which JSON-FG encodes exactly as GeoJSON does
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("wkt, expected", [
    (
        "POINT (1 2)",
        {"type": "Point", "coordinates": [1.0, 2.0]}
    ),
    (
        "LINESTRING (0 0,1 1,2 0)",
        {"type": "LineString",
         "coordinates": [[0.0, 0.0], [1.0, 1.0], [2.0, 0.0]]}
    ),
    (
        "POLYGON ((0 0,10 0,10 10,0 0),(2 2,4 2,4 4,2 2))",
        {"type": "Polygon",
         "coordinates": [
             [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 0.0]],
             [[2.0, 2.0], [4.0, 2.0], [4.0, 4.0], [2.0, 2.0]]]}
    ),
    (
        "MULTIPOINT (1 2,3 4)",
        {"type": "MultiPoint", "coordinates": [[1.0, 2.0], [3.0, 4.0]]}
    ),
    (
        "MULTILINESTRING ((0 0,1 1),(5 5,6 6))",
        {"type": "MultiLineString",
         "coordinates": [[[0.0, 0.0], [1.0, 1.0]], [[5.0, 5.0], [6.0, 6.0]]]}
    ),
    (
        "MULTIPOLYGON (((0 0,1 0,1 1,0 0)))",
        {"type": "MultiPolygon",
         "coordinates": [[[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]]]}
    ),
])
def test_simple_types(wkt, expected):
    assert geometry_to_place(geom(wkt)) == expected


def test_triangle_becomes_polygon():
    """OGR has a Triangle type; JSON-FG does not, so it is written as one."""
    assert geometry_to_place(geom("TRIANGLE ((0 0,1 0,1 1,0 0))")) == {
        "type": "Polygon",
        "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]]
    }


def test_geometry_collection():
    place = geometry_to_place(
        geom("GEOMETRYCOLLECTION (POINT (1 2),LINESTRING (0 0,1 1))"))

    assert place == {
        "type": "GeometryCollection",
        "geometries": [
            {"type": "Point", "coordinates": [1.0, 2.0]},
            {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 1.0]]}
        ]
    }


def test_geometry_collection_rejects_curves():
    """A JSON-FG GeometryCollection admits only the six simple types."""
    with pytest.raises(JsonFgError, match="GeometryCollection"):
        geometry_to_place(
            geom("GEOMETRYCOLLECTION (CIRCULARSTRING (0 0,1 1,2 0))"))


def test_unsupported_type_raises():
    with pytest.raises(JsonFgError, match="Unsupported geometry type"):
        geometry_to_place(geom("POLYHEDRALSURFACE (((0 0 0,0 1 0,1 1 0,0 0 0)))"))  # noqa: E501


def test_none_geometry():
    assert geometry_to_place(None) is None


# --------------------------------------------------------------------------- #
# Curve types: the reason for using JSON-FG in the first place
# --------------------------------------------------------------------------- #


def test_circular_string_carries_coordinates():
    """Unlike the other curve types, CircularString has ``coordinates``."""
    assert geometry_to_place(geom("CIRCULARSTRING (0 0,1 1,2 0)")) == {
        "type": "CircularString",
        "coordinates": [[0.0, 0.0], [1.0, 1.0], [2.0, 0.0]]
    }


def test_compound_curve_carries_geometries():
    place = geometry_to_place(
        geom("COMPOUNDCURVE (CIRCULARSTRING (0 0,1 1,2 0),(2 0,3 0))"))

    assert place == {
        "type": "CompoundCurve",
        "geometries": [
            {"type": "CircularString",
             "coordinates": [[0.0, 0.0], [1.0, 1.0], [2.0, 0.0]]},
            {"type": "LineString", "coordinates": [[2.0, 0.0], [3.0, 0.0]]}
        ]
    }


def test_curve_polygon_rings_are_geometries():
    """The first ring is the exterior one, as in Polygon."""
    place = geometry_to_place(
        geom("CURVEPOLYGON (CIRCULARSTRING (0 0,1 1,2 0,1 -1,0 0),"
             "(0.5 0,1.5 0,1 0.5,0.5 0))"))

    assert place["type"] == "CurvePolygon"
    assert [ring["type"] for ring in place["geometries"]] == [
        "CircularString", "LineString"]


def test_multi_curve():
    place = geometry_to_place(
        geom("MULTICURVE (CIRCULARSTRING (0 0,1 1,2 0),(5 5,6 6))"))

    assert place["type"] == "MultiCurve"
    assert [member["type"] for member in place["geometries"]] == [
        "CircularString", "LineString"]


def test_multi_surface():
    place = geometry_to_place(
        geom("MULTISURFACE (CURVEPOLYGON (CIRCULARSTRING "
             "(0 0,1 1,2 0,1 -1,0 0)),((10 10,11 10,11 11,10 10)))"))

    assert place["type"] == "MultiSurface"
    assert [member["type"] for member in place["geometries"]] == [
        "CurvePolygon", "Polygon"]


def test_nested_compound_curve_is_flattened():
    """CompoundCurve sections may only be LineString or CircularString."""
    place = geometry_to_place(
        geom("CURVEPOLYGON (COMPOUNDCURVE (CIRCULARSTRING (0 0,1 1,2 0),"
             "(2 0,0 0)))"))

    section_types = [
        section["type"] for section in place["geometries"][0]["geometries"]]

    assert section_types == ["CircularString", "LineString"]


# --------------------------------------------------------------------------- #
# normalize: drop curve containers that turned out to hold no arcs
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("wkt, expected_type", [
    ("CURVEPOLYGON ((0 0,1 0,1 1,0 0))", "Polygon"),
    ("MULTICURVE ((0 0,1 1))", "MultiLineString"),
    ("MULTISURFACE (((0 0,1 0,1 1,0 0)))", "MultiPolygon"),
    ("COMPOUNDCURVE ((0 0,1 1))", "LineString"),
])
def test_normalize_collapses_arcless_containers(wkt, expected_type):
    assert geometry_to_place(geom(wkt), normalize=True)["type"] == expected_type


@pytest.mark.parametrize("wkt, expected_type", [
    ("CURVEPOLYGON ((0 0,1 0,1 1,0 0))", "CurvePolygon"),
    ("MULTICURVE ((0 0,1 1))", "MultiCurve"),
    ("MULTISURFACE (((0 0,1 0,1 1,0 0)))", "MultiSurface"),
])
def test_containers_are_kept_without_normalize(wkt, expected_type):
    assert geometry_to_place(geom(wkt))["type"] == expected_type


def test_normalize_keeps_container_holding_an_arc():
    place = geometry_to_place(
        geom("CURVEPOLYGON (CIRCULARSTRING (0 0,1 1,2 0,1 -1,0 0))"),
        normalize=True)

    assert place["type"] == "CurvePolygon"


# --------------------------------------------------------------------------- #
# The 11-position cap on CircularString
# --------------------------------------------------------------------------- #


def _arc_wkt(positions: int) -> str:
    """A CircularString of *positions* points along a parabola."""
    points = ",".join(f"{i} {i % 2}" for i in range(positions))

    return f"CIRCULARSTRING ({points})"


def test_long_arc_is_split_into_a_compound_curve():
    place = geometry_to_place(geom(_arc_wkt(13)))

    assert place["type"] == "CompoundCurve"
    assert [len(section["coordinates"]) for section in place["geometries"]] == [
        MAX_CIRCULARSTRING_POSITIONS, 3]
    # Consecutive sections share the vertex they meet at.
    assert (place["geometries"][0]["coordinates"][-1]
            == place["geometries"][1]["coordinates"][0])


def test_arc_at_the_cap_is_not_split():
    place = geometry_to_place(geom(_arc_wkt(MAX_CIRCULARSTRING_POSITIONS)))

    assert place["type"] == "CircularString"


def test_long_arc_raises_when_splitting_is_disabled():
    with pytest.raises(JsonFgError, match="caps CircularString"):
        geometry_to_place(geom(_arc_wkt(13)), split_long_arcs=False)


def test_even_position_count_raises():
    even = geom("CIRCULARSTRING (0 0,1 1,2 0)")
    even.AddPoint_2D(3.0, 1.0)

    with pytest.raises(JsonFgError, match="odd number of positions"):
        geometry_to_place(even)


# --------------------------------------------------------------------------- #
# Z and M ordinates
# --------------------------------------------------------------------------- #


def test_z_is_kept():
    assert geometry_to_place(geom("POINT Z (1 2 3)"))["coordinates"] == [
        1.0, 2.0, 3.0]


def test_m_is_kept_as_the_fourth_ordinate():
    assert geometry_to_place(geom("POINT ZM (1 2 3 4)"))["coordinates"] == [
        1.0, 2.0, 3.0, 4.0]


def test_xym_has_no_unambiguous_encoding():
    with pytest.raises(JsonFgError, match="XYM"):
        geometry_to_place(geom("LINESTRING M (0 0 1,1 1 2)"))


def test_xym_can_drop_the_measure():
    place = geometry_to_place(
        geom("LINESTRING M (0 0 1,1 1 2)"), m_ordinate="drop")

    assert place["coordinates"] == [[0.0, 0.0], [1.0, 1.0]]


# --------------------------------------------------------------------------- #
# Empty geometries
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("wkt, expected", [
    ("MULTIPOINT EMPTY", {"type": "MultiPoint", "coordinates": []}),
    ("MULTILINESTRING EMPTY", {"type": "MultiLineString", "coordinates": []}),
    ("MULTIPOLYGON EMPTY", {"type": "MultiPolygon", "coordinates": []}),
    ("GEOMETRYCOLLECTION EMPTY",
     {"type": "GeometryCollection", "geometries": []}),
])
def test_empty_collections_are_encodable(wkt, expected):
    assert geometry_to_place(geom(wkt)) == expected


@pytest.mark.parametrize("wkt", [
    "POINT EMPTY", "LINESTRING EMPTY", "POLYGON EMPTY", "CIRCULARSTRING EMPTY"])
def test_empty_geometries_without_an_encoding_become_none(wkt):
    assert geometry_to_place(geom(wkt)) is None


# --------------------------------------------------------------------------- #
# bbox
# --------------------------------------------------------------------------- #


def test_bbox_is_omitted_by_default():
    assert "bbox" not in geometry_to_place(geom("POINT (1 2)"))


def test_bbox_2d():
    place = geometry_to_place(geom("LINESTRING (0 5,3 1)"), bbox=True)

    assert place["bbox"] == [0.0, 1.0, 3.0, 5.0]


def test_bbox_3d():
    place = geometry_to_place(geom("LINESTRING Z (0 0 1,3 4 5)"), bbox=True)

    assert place["bbox"] == [0.0, 0.0, 1.0, 3.0, 4.0, 5.0]


def test_bbox_of_an_arc_covers_the_curve_not_the_control_points():
    """A half circle bulges past its three control points."""
    place = geometry_to_place(
        geom("CIRCULARSTRING (0 0,1 1,2 0)"), bbox=True)

    assert place["bbox"] == pytest.approx([0.0, 0.0, 2.0, 1.0])


def test_bbox_is_only_set_on_the_top_level_geometry():
    place = geometry_to_place(
        geom("MULTICURVE (CIRCULARSTRING (0 0,1 1,2 0))"), bbox=True)

    assert "bbox" in place
    assert "bbox" not in place["geometries"][0]


# --------------------------------------------------------------------------- #
# has_arcs
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("wkt", [
    "CIRCULARSTRING (0 0,1 1,2 0)",
    "COMPOUNDCURVE (CIRCULARSTRING (0 0,1 1,2 0),(2 0,3 0))",
    "CURVEPOLYGON (CIRCULARSTRING (0 0,1 1,2 0,1 -1,0 0))",
    "MULTICURVE (CIRCULARSTRING (0 0,1 1,2 0))",
])
def test_has_arcs_true(wkt):
    assert has_arcs(geom(wkt)) is True


@pytest.mark.parametrize("wkt", [
    "POINT (1 2)",
    "LINESTRING (0 0,1 1)",
    "POLYGON ((0 0,1 0,1 1,0 0))",
    # A curve container holding no actual arc.
    "CURVEPOLYGON ((0 0,1 0,1 1,0 0))",
    "MULTICURVE ((0 0,1 1))",
])
def test_has_arcs_false(wkt):
    assert has_arcs(geom(wkt)) is False
