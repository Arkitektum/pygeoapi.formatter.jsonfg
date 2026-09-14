"""JSON-FG output formatter for pygeoapi.

JSON-FG (OGC Features and Geometries JSON) extends GeoJSON with the things
GeoJSON leaves out: a named coordinate reference system, a feature type, and
geometry types that GeoJSON cannot express -- notably circular arcs.

This package plugs into pygeoapi as a formatter. Reference it from a
collection's ``formatters:`` block by its dotted path:

.. code-block:: yaml

    formatters:
      - name: pygeoapi_formatter_jsonfg.JsonFgFormatter
        f: jsonfg

Modules:

``formatter``
    `JsonFgFormatter`, the pygeoapi plugin.
``geometry``
    `geometry_to_place`, turning an ``ogr.Geometry`` into a JSON-FG ``place``.
``crs``
    Coordinate transformations between storage, content and CRS84.
``constants``
    Media type, conformance class URIs and other fixed values.
"""

from .formatter import JsonFgFormatter
from .geometry import JsonFgError, geometry_to_place, has_arcs

__version__ = "0.1.0"

__all__ = [
    "JsonFgError",
    "JsonFgFormatter",
    "geometry_to_place",
    "has_arcs"
]
