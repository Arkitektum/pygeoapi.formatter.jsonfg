"""
``ogr.Geometry`` -> the geometry object for a JSON-FG ``place`` member.

The formatter feeds this module geometries that GDAL/OGR parsed out of the
GML 3.2 carried by the ``_geometry_gml`` feature property, so the input may
contain the curve types GML has and GeoJSON does not: CircularString,
CompoundCurve, CurvePolygon, MultiCurve and MultiSurface.

Shapes follow the normative JSON-FG 1.0 schema:
https://schemas.opengis.net/json-fg/geometry-object.json

Reminder on the encoding, since it differs from GeoJSON habits:
``CircularString`` carries ``coordinates``; ``CompoundCurve``,
``CurvePolygon``, ``MultiCurve`` and ``MultiSurface`` carry ``geometries``.
For ``CurvePolygon`` the first entry is the exterior ring.

Only the top-level geometry gets ``coordRefSys`` / ``bbox``; the schema
forbids repeating ``coordRefSys``, ``measures`` or ``conformsTo`` on nested
geometries.
"""

from typing import Any, Dict, List, cast
from osgeo import ogr

__all__ = [
    "JsonFgError",
    "geometry_to_place",
    "has_arcs"
]

#: JSON-FG 1.0 constrains CircularString to 3, 5, 7, 9 or 11 positions.
MAX_CIRCULARSTRING_POSITIONS = 11
_MAX_ARCS_PER_STRING = MAX_CIRCULARSTRING_POSITIONS // 2  # 5

_SIMPLE_GEOJSON_TYPES = frozenset(
    {"Point", "MultiPoint", "LineString",
        "MultiLineString", "Polygon", "MultiPolygon"}
)

# Empty geometries: JSON-FG has no valid encoding for an empty Point or curve,
# so those become None. The homogeneous collections take an empty array.
_EMPTY_PLACE: Dict[int, Dict[str, Any]] = {
    ogr.wkbMultiPoint: {"type": "MultiPoint", "coordinates": []},
    ogr.wkbMultiLineString: {"type": "MultiLineString", "coordinates": []},
    ogr.wkbMultiPolygon: {"type": "MultiPolygon", "coordinates": []},
    ogr.wkbGeometryCollection: {"type": "GeometryCollection", "geometries": []},
}


class JsonFgError(ValueError):
    """The geometry has no valid JSON-FG encoding."""


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def geometry_to_place(
    geom: ogr.Geometry | None,
    *,
    bbox: bool = False,
    normalize: bool = False,
    split_long_arcs: bool = True,
    m_ordinate: str = "keep",
) -> Dict[str, Any] | None:
    """Convert an ``ogr.Geometry`` into a JSON-FG ``place`` object.

    bbox:
        Add a ``bbox``. Uses ``OGRGeometry::getEnvelope()``, which is
        arc-exact, so a half-circle reports its true extent rather than the
        control-point hull.
    normalize:
        Emit plain GeoJSON types where a curve container turned out to hold no
        arcs (CurvePolygon -> Polygon, MultiSurface -> MultiPolygon,
        MultiCurve -> MultiLineString, single-section CompoundCurve -> its
        section). Useful for advertising the circular-arcs conformance class
        only when a feature actually needs it.
    split_long_arcs:
        Chunk a CircularString longer than 11 positions into a CompoundCurve
        of <= 5-arc CircularStrings, per the schema cap.
    m_ordinate:
        ``"keep"`` writes M as the 4th ordinate (requires Z); ``"drop"``
        discards it.
    """
    if geom is None:
        return None

    ctx = {
        "normalize": normalize,
        "split_long_arcs": split_long_arcs,
        "m_ordinate": m_ordinate,
    }

    place = _place(geom, ctx)

    if place is None:
        return None

    if bbox:
        minx, maxx, miny, maxy = geom.GetEnvelope()
        if geom.Is3D():
            _, _, _, _, minz, maxz = geom.GetEnvelope3D()
            place["bbox"] = [minx, miny, minz, maxx, maxy, maxz]
        else:
            place["bbox"] = [minx, miny, maxx, maxy]

    return place


def has_arcs(geom: ogr.Geometry) -> bool:
    """Whether *geom* really contains circular arcs.

    Use this to decide whether a document must declare the circular-arcs
    conformance class:
    ``http://www.opengis.net/spec/json-fg-1/1.0/conf/circular-arcs``
    """
    return bool(geom.HasCurveGeometry(True))

# --------------------------------------------------------------------------- #
# Positions
# --------------------------------------------------------------------------- #


def _position(geom: ogr.Geometry, i: int, has_z: bool, has_m: bool, m_ordinate: str) -> List[float]:
    """One JSON-FG position: [x, y], [x, y, z] or [x, y, z, m]."""
    if has_m and m_ordinate == "drop":
        has_m = False
    if has_m and not has_z:
        raise JsonFgError(
            "XYM has no unambiguous JSON-FG position ([x, y, z, m]); "
            "pass m_ordinate='drop' or promote the geometry to XYZM"
        )
    # GetPoint() reports z as 0.0 for XYM geometries, so read ordinates explicitly.
    pos = [geom.GetX(i), geom.GetY(i)]
    if has_z:
        pos.append(geom.GetZ(i))
    if has_m:
        pos.append(geom.GetM(i))

    return pos


def _positions(curve: ogr.Geometry, ctx: Dict[str, Any]) -> List[List[float]]:
    t = curve.GetGeometryType()
    has_z, has_m = bool(ogr.GT_HasZ(t)), bool(ogr.GT_HasM(t))
    return [
        _position(curve, i, has_z, has_m, ctx["m_ordinate"])
        for i in range(curve.GetPointCount())
    ]


# --------------------------------------------------------------------------- #
# CircularString, with splitting to satisfy the 11-position cap
# --------------------------------------------------------------------------- #


def _circular_sections(curve: ogr.Geometry, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One or more CircularStrings. Long arc strings are chunked at 5 arcs."""
    coords = _positions(curve, ctx)
    n = len(coords)
    if n < 3 or n % 2 == 0:
        raise JsonFgError(
            f"CircularString needs an odd number of positions >= 3, got {n}")
    if n <= MAX_CIRCULARSTRING_POSITIONS:
        return [{"type": "CircularString", "coordinates": coords}]
    if not ctx["split_long_arcs"]:
        raise JsonFgError(
            f"the JSON-FG 1.0 schema caps CircularString at "
            f"{MAX_CIRCULARSTRING_POSITIONS} positions, got {n}; "
            "pass split_long_arcs=True to chunk it into a CompoundCurve"
        )
    step = 2 * _MAX_ARCS_PER_STRING  # advance 10 positions, chunks share a vertex
    return [
        {"type": "CircularString", "coordinates": coords[i: i + step + 1]}
        for i in range(0, n - 1, step)
    ]


def _as_single_curve(sections: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Collapse split sections back into one curve object."""
    return sections[0] if len(sections) == 1 else {"type": "CompoundCurve", "geometries": sections}


def _curve(geom: ogr.Geometry, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """A curve usable as a CurvePolygon ring or MultiCurve member."""
    return _as_single_curve(_curve_sections(geom, ctx))


def _curve_sections(geom: ogr.Geometry, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flat List of LineString / CircularString sections for a curve."""
    flat = ogr.GT_Flatten(geom.GetGeometryType())
    if flat == ogr.wkbCircularString:
        return _circular_sections(geom, ctx)
    if flat == ogr.wkbLineString:  # LinearRing also reports wkbLineString
        return [{"type": "LineString", "coordinates": _positions(geom, ctx)}]
    if flat == ogr.wkbCompoundCurve:
        # CompoundCurve sections must be LineString or CircularString, never
        # another CompoundCurve, so splice split arcs in rather than nesting.
        out: List[Dict[str, Any]] = []
        for i in range(geom.GetGeometryCount()):
            out.extend(_curve_sections(_get_geometry(geom, i), ctx))
        return out
    raise JsonFgError(f"{geom.GetGeometryName()} is not a curve")


def _get_geometry(geom: ogr.Geometry, index: int) -> ogr.Geometry:
    child_geom = geom.GetGeometryRef(index)

    return cast(ogr.Geometry, child_geom)


# --------------------------------------------------------------------------- #
# Main dispatch
# --------------------------------------------------------------------------- #


def _place(geom: ogr.Geometry, ctx: Dict[str, Any]) -> Dict[str, Any] | None:
    flat = ogr.GT_Flatten(geom.GetGeometryType())

    if geom.IsEmpty():
        empty = _EMPTY_PLACE.get(flat)
        return dict(empty) if empty else None

    if flat == ogr.wkbPoint:
        return {"type": "Point", "coordinates": _positions(geom, ctx)[0]}

    if flat in (ogr.wkbLineString, ogr.wkbCircularString, ogr.wkbCompoundCurve):
        sections = _curve_sections(geom, ctx)
        if flat == ogr.wkbCompoundCurve and not ctx["normalize"]:
            return {"type": "CompoundCurve", "geometries": sections}
        return _as_single_curve(sections)

    if flat in (ogr.wkbPolygon, ogr.wkbTriangle):
        return {
            "type": "Polygon",
            "coordinates": [_positions(_get_geometry(geom, i), ctx)
                            for i in range(geom.GetGeometryCount())],
        }

    if flat == ogr.wkbCurvePolygon:
        rings = [_curve(_get_geometry(geom, i), ctx)
                 for i in range(geom.GetGeometryCount())]
        if ctx["normalize"] and all(r["type"] == "LineString" for r in rings):
            return {"type": "Polygon", "coordinates": [r["coordinates"] for r in rings]}
        return {"type": "CurvePolygon", "geometries": rings}

    if flat == ogr.wkbMultiPoint:
        return {
            "type": "MultiPoint",
            "coordinates": [_positions(_get_geometry(geom, i), ctx)[0]
                            for i in range(geom.GetGeometryCount())],
        }

    if flat == ogr.wkbMultiLineString:
        return {
            "type": "MultiLineString",
            "coordinates": [_positions(_get_geometry(geom, i), ctx)
                            for i in range(geom.GetGeometryCount())],
        }

    if flat == ogr.wkbMultiPolygon:
        return {
            "type": "MultiPolygon",
            "coordinates": [_place(_get_geometry(geom, i), ctx)["coordinates"] # type: ignore
                            for i in range(geom.GetGeometryCount())],
        }

    if flat == ogr.wkbMultiCurve:
        members = [_curve(_get_geometry(geom, i), ctx)
                   for i in range(geom.GetGeometryCount())]
        if ctx["normalize"] and all(m["type"] == "LineString" for m in members):
            return {"type": "MultiLineString", "coordinates": [m["coordinates"] for m in members]}
        return {"type": "MultiCurve", "geometries": members}

    if flat == ogr.wkbMultiSurface:
        members = [_place(_get_geometry(geom, i), ctx)
                   for i in range(geom.GetGeometryCount())]
        if ctx["normalize"] and all(m["type"] == "Polygon" for m in members): # type: ignore
            return {"type": "MultiPolygon", "coordinates": [m["coordinates"] for m in members]} # type: ignore
        return {"type": "MultiSurface", "geometries": members}

    if flat == ogr.wkbGeometryCollection:
        members = [_place(_get_geometry(geom, i), ctx)
                   for i in range(geom.GetGeometryCount())]
        members = [m for m in members if m is not None]
        bad = sorted({m["type"] for m in members} - _SIMPLE_GEOJSON_TYPES)
        if bad:
            raise JsonFgError(
                "a JSON-FG GeometryCollection admits only the six simple GeoJSON "
                f"types; got {', '.join(bad)}. Use MultiCurve / MultiSurface instead."
            )
        return {"type": "GeometryCollection", "geometries": members}

    raise JsonFgError(f"Unsupported geometry type {geom.GetGeometryName()}")
