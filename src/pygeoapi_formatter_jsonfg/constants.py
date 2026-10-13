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
    "DERIVED_POINT_PROPERTY",
    "EXTENSION",
    "GML_PROPERTY",
    "PROFILE_JSONFG",
    "PROFILE_JSONFG_PLUS",
]

#: Value of the ``f=`` query parameter this formatter answers to.
DEFAULT_F = "jsonfg"

#: Media type registered for JSON-FG (OGC 21-045).
DEFAULT_MIMETYPE = "application/geo+json"

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

#: Synthetic feature property postgresql_ext adds for the GML formatter on
#: påskrift collections. Never part of the output.
DERIVED_POINT_PROPERTY = "_derived_point_gml"

# Conformance class URIs advertised through the ``conformsTo`` member.
CONF_CORE = "http://www.opengis.net/spec/json-fg-1/1.0/conf/core"
CONF_TYPES_SCHEMAS = "http://www.opengis.net/spec/json-fg-1/1.0/conf/types-schemas"  # noqa: E501
CONF_CIRCULAR_ARCS = "http://www.opengis.net/spec/json-fg-1/1.0/conf/circular-arcs"  # noqa: E501

# GeoJSON profile ids (OGC 21-045 clause 14), the {id} in
# http://www.opengis.net/def/profile/OGC/0/{id} and the profile= query value.
PROFILE_JSONFG = "jsonfg"
PROFILE_JSONFG_PLUS = "jsonfg-plus"
