"""Constants shared by the formatter and the geometry encoder.

Everything here is either fixed by the JSON-FG 1.0 specification or is a
default that a pygeoapi ``formatters:`` block may override.
"""

__all__ = [
    "CONF_CIRCULAR_ARCS",
    "CONF_CORE",
    "CONF_TYPES_SCHEMAS",
    "CRS84_URI",
    "DEFAULT_F",
    "DEFAULT_MIMETYPE",
    "EXTENSION",
    "GEOMETRY_DIMENSION",
    "GML_PROPERTY",
]

#: Value of the ``f=`` query parameter this formatter answers to.
DEFAULT_F = "jsonfg"

#: Media type registered for JSON-FG (OGC 21-045).
DEFAULT_MIMETYPE = "application/vnd.ogc.fg+json"

#: Suffix used when pygeoapi serves the response as a file attachment.
EXTENSION = "jsonfg"

#: OGC URI for WGS 84 longitude/latitude. This is the CRS a GeoJSON
#: ``geometry`` member must be in, and therefore the target of the second,
#: optional coordinate transformation performed per feature.
CRS84_URI = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"

#: Synthetic feature property holding the GML 3.2 encoding of the geometry.
#: The provider adds it; the formatter consumes and removes it, so it never
#: reaches the response.
GML_PROPERTY = "_geometry_gml"

#: Value of the JSON-FG ``geometryDimension`` member. Fixed at 2 (surfaces):
#: the collections this formatter serves are planar, and JSON-FG allows the
#: member to be omitted rather than requiring it to be derived per document.
GEOMETRY_DIMENSION = 2

# Conformance class URIs advertised through the ``conformsTo`` member.
CONF_CORE = "http://www.opengis.net/spec/json-fg-1/1.0/conf/core"
CONF_TYPES_SCHEMAS = "http://www.opengis.net/spec/json-fg-1/1.0/conf/types-schemas"  # noqa: E501
CONF_CIRCULAR_ARCS = "http://www.opengis.net/spec/json-fg-1/1.0/conf/circular-arcs"  # noqa: E501
