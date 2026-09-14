"""Tests for the pygeoapi formatter plugin."""

import copy
import json
import logging

import pytest
from conftest import (CRS84, EPSG_25833, GEOJSON_POINT, GML_ARC, GML_POINT,
                      GML_POLYGON, make_feature, make_feature_collection,
                      make_options)

from pygeoapi_formatter_jsonfg import JsonFgFormatter
from pygeoapi_formatter_jsonfg.constants import (CONF_CIRCULAR_ARCS, CONF_CORE,
                                                 CONF_TYPES_SCHEMAS)


def write(formatter, data, **options_kwargs):
    """Run the formatter and parse its output back into a dict."""
    return json.loads(formatter.write(make_options(**options_kwargs), data))


# --------------------------------------------------------------------------- #
# Plugin configuration
# --------------------------------------------------------------------------- #


def test_defaults():
    formatter = JsonFgFormatter({"name": "irrelevant"})

    assert formatter.f == "jsonfg"
    assert formatter.name == "jsonfg"
    assert formatter.mimetype == "application/vnd.ogc.fg+json"
    assert formatter.extension == "jsonfg"
    assert formatter.attachment is False
    assert formatter.feature_type is None


def test_formatter_def_overrides():
    formatter = JsonFgFormatter({
        "name": "irrelevant",
        "f": "fg",
        "mimetype": "application/json",
        "attachment": True,
        "feature_type": "Building"
    })

    assert formatter.f == "fg"
    assert formatter.name == "fg"
    assert formatter.mimetype == "application/json"
    assert formatter.attachment is True
    assert formatter.feature_type == "Building"


# --------------------------------------------------------------------------- #
# Feature collection documents
# --------------------------------------------------------------------------- #


def test_feature_collection_members(formatter):
    data = make_feature_collection([make_feature(GML_POINT)])

    out = write(formatter, data)

    assert list(out) == [
        "type", "conformsTo", "featureType", "featureSchema", "coordRefSys",
        "geometryDimension", "features", "numberReturned", "numberMatched",
        "links", "timeStamp"
    ]
    assert out["type"] == "FeatureCollection"
    assert out["featureType"] == "Building"
    assert out["geometryDimension"] == 2
    assert out["numberReturned"] == 1
    assert out["numberMatched"] == 1
    assert out["timeStamp"] == data["timeStamp"]


def test_feature_members(formatter):
    out = write(formatter, make_feature_collection([make_feature(GML_POINT)]))
    feature = out["features"][0]

    assert list(feature) == ["type", "place", "geometry", "id", "properties"]
    assert feature["type"] == "Feature"
    assert feature["id"] == "1"


def test_every_feature_is_converted(formatter):
    data = make_feature_collection([
        make_feature(GML_POINT, feature_id="1"),
        make_feature(GML_POLYGON, feature_id="2")
    ])

    out = write(formatter, data)

    assert [feature["id"] for feature in out["features"]] == ["1", "2"]
    assert [feature["place"]["type"] for feature in out["features"]] == [
        "Point", "Polygon"]


def test_empty_feature_collection(formatter):
    out = write(formatter, make_feature_collection([]))

    assert out["features"] == []
    assert out["numberReturned"] == 0


# --------------------------------------------------------------------------- #
# place and geometry
# --------------------------------------------------------------------------- #


def test_place_holds_the_gml_geometry(formatter):
    out = write(formatter, make_feature_collection([make_feature(GML_POINT)]))

    assert out["features"][0]["place"] == {
        "type": "Point",
        "coordinates": [262000.0, 6650000.0]
    }


def test_place_keeps_arcs_that_geojson_cannot_express(formatter):
    """The GeoJSON geometry member has already lost the arc; place has not."""
    data = make_feature_collection([make_feature(
        GML_ARC,
        geometry={"type": "LineString",
                  "coordinates": [[0.0, 0.0], [0.5, 0.87], [1.0, 1.0]]})])

    out = write(formatter, data)

    assert out["features"][0]["place"] == {
        "type": "CircularString",
        "coordinates": [[0.0, 0.0], [1.0, 1.0], [2.0, 0.0]]
    }


def test_geometry_is_null_when_place_carries_the_geometry(formatter):
    """JSON-FG allows this, and it avoids shipping the geometry twice."""
    out = write(formatter, make_feature_collection([make_feature(GML_POINT)]))

    assert out["features"][0]["geometry"] is None


def test_gml_property_is_removed(formatter):
    feature = make_feature(GML_POINT)

    out = write(formatter, make_feature_collection([feature]))

    assert "_geometry_gml" not in out["features"][0]["properties"]
    assert out["features"][0]["properties"] == {
        "name": "Feature 1", "height": 12.5}


def test_place_is_written_in_the_requested_crs(formatter):
    data = make_feature_collection([make_feature(GML_POINT)])

    out = write(formatter, data, storage_crs=EPSG_25833, content_crs=CRS84)

    assert out["features"][0]["place"]["coordinates"] == pytest.approx(
        [10.7415658933079, 59.918559537905])


def test_place_is_not_transformed_when_no_crs_was_requested(formatter):
    data = make_feature_collection([make_feature(GML_POINT)])

    out = write(formatter, data, storage_crs=EPSG_25833, content_crs=None)

    assert out["features"][0]["place"]["coordinates"] == [262000.0, 6650000.0]


# --------------------------------------------------------------------------- #
# coordRefSys
# --------------------------------------------------------------------------- #


def test_coord_ref_sys_is_the_requested_crs(formatter):
    out = write(formatter, make_feature_collection([make_feature(GML_POINT)]),
                storage_crs=EPSG_25833, content_crs=CRS84)

    assert out["coordRefSys"] == CRS84


def test_coord_ref_sys_falls_back_to_the_storage_crs(formatter):
    out = write(formatter, make_feature_collection([make_feature(GML_POINT)]),
                storage_crs=EPSG_25833, content_crs=None)

    assert out["coordRefSys"] == EPSG_25833


# --------------------------------------------------------------------------- #
# conformsTo
# --------------------------------------------------------------------------- #


def test_conforms_to_without_arcs(formatter):
    out = write(formatter, make_feature_collection([make_feature(GML_POINT)]))

    assert out["conformsTo"] == [CONF_CORE, CONF_TYPES_SCHEMAS]


def test_conforms_to_declares_arcs_when_a_feature_has_one(formatter):
    data = make_feature_collection([
        make_feature(GML_POINT, feature_id="1"),
        make_feature(GML_ARC, feature_id="2")
    ])

    out = write(formatter, data)

    assert CONF_CIRCULAR_ARCS in out["conformsTo"]


def test_conforms_to_is_per_document_not_per_feature(formatter):
    """One arc anywhere sets the class for the whole document."""
    data = make_feature_collection([
        make_feature(GML_ARC, feature_id="1"),
        make_feature(GML_POINT, feature_id="2")
    ])

    out = write(formatter, data)

    assert out["conformsTo"].count(CONF_CIRCULAR_ARCS) == 1


# --------------------------------------------------------------------------- #
# featureSchema
# --------------------------------------------------------------------------- #


def test_feature_schema_is_derived_from_the_collection_link(formatter):
    out = write(formatter, make_feature_collection([make_feature(GML_POINT)]))

    assert out["featureSchema"] == (
        "https://example.org/collections/buildings/schema?f=json")


def test_feature_schema_is_none_without_a_collection_link(formatter):
    data = make_feature_collection(
        [make_feature(GML_POINT)],
        links=[{"rel": "self", "href": "https://example.org/items"}])

    out = write(formatter, data)

    assert out["featureSchema"] is None


# --------------------------------------------------------------------------- #
# Single feature (item) documents
# --------------------------------------------------------------------------- #


ITEM_LINKS = [
    {
        "rel": "self",
        "type": "application/geo+json",
        "href": "https://example.org/collections/buildings/items/1"
    },
    {
        "rel": "collection",
        "type": "application/json",
        "href": "https://example.org/collections/buildings"
    }
]


def test_single_feature_is_inlined(formatter):
    """An item response has its links on the feature, not the collection."""
    data = make_feature_collection(
        [make_feature(GML_POINT, links=ITEM_LINKS)])

    out = write(formatter, data)

    assert out["type"] == "Feature"
    assert "features" not in out
    assert list(out) == [
        "type", "conformsTo", "featureType", "featureSchema", "coordRefSys",
        "geometryDimension", "place", "geometry", "id", "properties", "links"
    ]
    assert out["id"] == "1"
    assert out["links"] == ITEM_LINKS


def test_single_feature_keeps_navigation_members(formatter):
    data = make_feature_collection([make_feature(
        GML_POINT, feature_id="2", links=ITEM_LINKS, prev="1", next="3")])

    out = write(formatter, data)

    assert out["prev"] == "1"
    assert out["next"] == "3"


def test_single_feature_without_links_stays_a_collection(formatter):
    """A one-hit search is a collection, and keeps the collection members."""
    data = make_feature_collection([make_feature(GML_POINT)])

    out = write(formatter, data)

    assert out["type"] == "FeatureCollection"
    assert len(out["features"]) == 1


def test_single_feature_omits_place_when_the_geometry_is_empty(formatter):
    """An empty point has no JSON-FG encoding, so the member is left out."""
    empty_point = ('<gml:Point xmlns:gml="http://www.opengis.net/gml/3.2">'
                   '<gml:pos></gml:pos></gml:Point>')
    data = make_feature_collection(
        [make_feature(empty_point, links=ITEM_LINKS)])

    out = write(formatter, data)

    assert "place" not in out


# --------------------------------------------------------------------------- #
# Missing or unusable input
# --------------------------------------------------------------------------- #


def test_missing_gml_falls_back_to_the_geojson_geometry(formatter, caplog):
    """One bad feature must not cost the whole response."""
    data = make_feature_collection([make_feature(None)])

    with caplog.at_level(logging.WARNING):
        out = write(formatter, data)

    feature = out["features"][0]

    assert "place" not in feature
    assert feature["geometry"] == GEOJSON_POINT
    assert "_geometry_gml" in caplog.text


def test_unparseable_gml_falls_back_to_the_geojson_geometry(
        formatter, caplog):
    data = make_feature_collection([make_feature("<not-gml/>")])

    with caplog.at_level(logging.WARNING):
        out = write(formatter, data)

    feature = out["features"][0]

    assert "place" not in feature
    assert feature["geometry"] == GEOJSON_POINT
    assert "as GML" in caplog.text


def test_one_bad_feature_does_not_affect_the_others(formatter):
    data = make_feature_collection([
        make_feature(None, feature_id="1"),
        make_feature(GML_ARC, feature_id="2")
    ])

    out = write(formatter, data)

    assert "place" not in out["features"][0]
    assert out["features"][1]["place"]["type"] == "CircularString"
    assert CONF_CIRCULAR_ARCS in out["conformsTo"]


def test_feature_without_a_geometry(formatter):
    """A GeoJSON feature may legitimately have a null geometry."""
    data = make_feature_collection([make_feature(None, geometry=None)])

    out = write(formatter, data)

    assert out["features"][0]["geometry"] is None
    assert "place" not in out["features"][0]


def test_the_input_document_is_not_modified(formatter):
    """The document belongs to pygeoapi; the formatter only reads it."""
    feature = make_feature(GML_POINT)
    data = make_feature_collection([feature])
    before = copy.deepcopy(data)

    write(formatter, data)

    assert data == before
    assert feature["properties"]["_geometry_gml"] == GML_POINT


# --------------------------------------------------------------------------- #
# Optional members of the input document
# --------------------------------------------------------------------------- #


def test_optional_collection_members_are_omitted_when_absent(formatter):
    data = {
        "type": "FeatureCollection",
        "features": [make_feature(GML_POINT), make_feature(GML_POLYGON)]
    }

    out = write(formatter, data)

    assert out["numberReturned"] == 2
    assert "numberMatched" not in out
    assert "links" not in out
    assert "timeStamp" not in out
    assert out["featureSchema"] is None


def test_links_without_a_rel_are_skipped(formatter):
    data = make_feature_collection(
        [make_feature(GML_POINT)],
        links=[{"href": "https://example.org/items"}])

    out = write(formatter, data)

    assert out["featureSchema"] is None


def test_storage_crs_defaults_to_crs84(formatter):
    """pygeoapi treats a provider without a storage_crs as CRS84."""
    out = json.loads(formatter.write(
        {"content_crs": None, "provider_def": {}},
        make_feature_collection([make_feature(GML_POINT)])))

    assert out["coordRefSys"] == CRS84


# --------------------------------------------------------------------------- #
# geometry_null
# --------------------------------------------------------------------------- #


def test_geometry_null_is_on_by_default():
    assert JsonFgFormatter({"name": "irrelevant"}).geometry_null is True


def test_geometry_null_false_keeps_the_geojson_geometry():
    formatter = JsonFgFormatter({"name": "irrelevant", "geometry_null": False})
    data = make_feature_collection([make_feature(GML_POINT)])

    out = write(formatter, data)
    feature = out["features"][0]

    assert feature["place"] == {
        "type": "Point", "coordinates": [262000.0, 6650000.0]}
    assert feature["geometry"] == GEOJSON_POINT


def test_kept_geometry_is_reprojected_to_crs84():
    """A GeoJSON geometry member must be in CRS84, whatever place uses."""
    formatter = JsonFgFormatter({"name": "irrelevant", "geometry_null": False})
    data = make_feature_collection([make_feature(
        GML_POINT,
        geometry={"type": "Point", "coordinates": [262000.0, 6650000.0]})])

    out = write(formatter, data,
                storage_crs=EPSG_25833, content_crs=EPSG_25833)
    feature = out["features"][0]

    assert feature["place"]["coordinates"] == [262000.0, 6650000.0]
    assert feature["geometry"]["coordinates"] == pytest.approx(
        GEOJSON_POINT["coordinates"])


def test_kept_geometry_is_reprojected_without_gml_to_project_from():
    formatter = JsonFgFormatter({"name": "irrelevant", "geometry_null": False})
    data = make_feature_collection([make_feature(
        None,
        geometry={"type": "Point", "coordinates": [262000.0, 6650000.0]})])

    out = write(formatter, data,
                storage_crs=EPSG_25833, content_crs=EPSG_25833)

    assert out["features"][0]["geometry"]["coordinates"] == pytest.approx(
        GEOJSON_POINT["coordinates"])
