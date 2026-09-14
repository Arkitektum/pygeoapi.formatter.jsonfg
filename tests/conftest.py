"""Shared fixtures and helpers.

The data built here is synthetic; it mimics the shape of a pygeoapi
OGC API - Features response without being taken from any real dataset.
"""

from typing import Any, Dict, List

import pytest
from osgeo import ogr

#: A metric, projected CRS: ETRS89 / UTM zone 33N, the storage CRS in most of
#: the tests. Its authority axis order is easting/northing, i.e. x/y.
EPSG_25833 = "http://www.opengis.net/def/crs/EPSG/0/25833"

#: WGS 84 longitude/latitude.
CRS84 = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"

GML_NS = 'xmlns:gml="http://www.opengis.net/gml/3.2"'

#: A GML 3.2 point, in EPSG_25833 coordinates (somewhere in eastern Norway).
GML_POINT = (
    f'<gml:Point {GML_NS} srsName="urn:ogc:def:crs:EPSG::25833">'
    '<gml:pos>262000 6650000</gml:pos>'
    '</gml:Point>'
)

#: A GML 3.2 polygon with a hole.
GML_POLYGON = (
    f'<gml:Polygon {GML_NS}>'
    '<gml:exterior><gml:LinearRing>'
    '<gml:posList>0 0 10 0 10 10 0 10 0 0</gml:posList>'
    '</gml:LinearRing></gml:exterior>'
    '<gml:interior><gml:LinearRing>'
    '<gml:posList>2 2 4 2 4 4 2 4 2 2</gml:posList>'
    '</gml:LinearRing></gml:interior>'
    '</gml:Polygon>'
)

#: A GML 3.2 curve made of one circular arc. This is the case GeoJSON cannot
#: represent and JSON-FG can.
GML_ARC = (
    f'<gml:Curve {GML_NS}><gml:segments><gml:ArcString>'
    '<gml:posList>0 0 1 1 2 0</gml:posList>'
    '</gml:ArcString></gml:segments></gml:Curve>'
)


def geom(wkt: str) -> ogr.Geometry:
    """Parse *wkt* into an ``ogr.Geometry``, failing the test if it will not."""
    parsed = ogr.CreateGeometryFromWkt(wkt)
    assert parsed is not None, f"GDAL could not parse {wkt!r}"

    return parsed


#: The GeoJSON geometry pygeoapi produces for GML_POINT, once reprojected to
#: CRS84 -- which is what it does by default.
GEOJSON_POINT = {"type": "Point", "coordinates": [10.7415658933079,
                                                 59.918559537905]}


def make_feature(
    gml: str | None,
    feature_id: str = "1",
    geometry: Dict[str, Any] | None = GEOJSON_POINT,
    properties: Dict[str, Any] | None = None,
    **extra: Any
) -> Dict[str, Any]:
    """A GeoJSON feature as pygeoapi hands it to the formatter.

    :param gml: value of the synthetic ``_geometry_gml`` property. ``None``
                leaves the property out altogether.
    :param geometry: the GeoJSON ``geometry`` member. Its value only matters
                     when the formatter is configured to keep the member, or
                     when it has to stand in for missing GML.
    :param extra: further top-level members, e.g. ``links`` or ``prev``.
    """
    props = {"name": "Feature 1", "height": 12.5}
    props.update(properties or {})

    if gml is not None:
        props["_geometry_gml"] = gml

    return {
        "type": "Feature",
        "id": feature_id,
        "geometry": geometry,
        "properties": props,
        **extra
    }


def make_feature_collection(
    features: List[Dict[str, Any]],
    links: List[Dict[str, Any]] | None = None
) -> Dict[str, Any]:
    """A GeoJSON feature collection as pygeoapi hands it to the formatter."""
    return {
        "type": "FeatureCollection",
        "features": features,
        "numberReturned": len(features),
        "numberMatched": len(features),
        "links": links if links is not None else [
            {
                "rel": "self",
                "type": "application/geo+json",
                "href": "https://example.org/collections/buildings/items"
            },
            {
                "rel": "collection",
                "type": "application/json",
                "title": "Buildings",
                "href": "https://example.org/collections/buildings"
            }
        ],
        "timeStamp": "2026-01-01T12:00:00.000000Z"
    }


def make_options(
    storage_crs: str = EPSG_25833,
    content_crs: str | None = None
) -> Dict[str, Any]:
    """The ``options`` argument pygeoapi passes to ``write()``."""
    return {
        "content_crs": content_crs,
        "provider_def": {"storage_crs": storage_crs}
    }


@pytest.fixture
def formatter():
    """A formatter configured the way a collection normally would be."""
    from pygeoapi_formatter_jsonfg import JsonFgFormatter

    return JsonFgFormatter({
        "name": "pygeoapi_formatter_jsonfg.JsonFgFormatter",
        "feature_type": "Building"
    })
