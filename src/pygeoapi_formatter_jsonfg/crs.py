"""Coordinate reference system helpers, built on GDAL/OSR.

A single JSON-FG response can involve up to three CRSs:

* the *storage* CRS the provider keeps its data in (``storage_crs`` in the
  provider definition), which is the CRS the GML in ``_geometry_gml`` is
  encoded in;
* the *content* CRS the client asked for (the ``crs`` query parameter, passed
  on by pygeoapi as ``content_crs``), which is what the JSON-FG ``place``
  member is written in and what ``coordRefSys`` names;
* CRS84, which is the only CRS a GeoJSON ``geometry`` member may use.

Note on axis order: the transformations built here keep GDAL's default
``OAMS_AUTHORITY_COMPLIANT`` mapping, so coordinates come out in the axis
order the CRS authority defines. That is what both formats want -- JSON-FG
positions follow the axis order of ``coordRefSys``, and the CRS84 URI is
defined as longitude/latitude, which is the GeoJSON order.
"""

from osgeo import osr

# Keep the GDAL bindings in their historical, non-throwing mode: failures are
# reported through return codes and the GDAL error handler instead of Python
# exceptions. The setting is global to ``osgeo.osr``, hence applied at import.
osr.DontUseExceptions()

__all__ = ["get_coordinate_transformation"]


def get_coordinate_transformation(
    source_crs: str,
    target_crs: str | None
) -> osr.CoordinateTransformation | None:
    """Build a transformation from *source_crs* to *target_crs*.

    :param source_crs: CRS identifier to transform from.
    :param target_crs: CRS identifier to transform to, or ``None``.

    Both are anything ``OGRSpatialReference::SetFromUserInput()`` accepts;
    pygeoapi supplies OGC CRS URIs such as
    ``http://www.opengis.net/def/crs/EPSG/0/25833``.

    :returns: an `osr.CoordinateTransformation`, or ``None`` when no
              transformation is needed -- either because the target is
              unknown (pygeoapi leaves ``content_crs`` unset when the request
              carries no ``crs`` parameter) or because both sides name the
              same CRS.
    """
    if target_crs is None or source_crs == target_crs:
        return None

    source = osr.SpatialReference()
    source.SetFromUserInput(source_crs)

    target = osr.SpatialReference()
    target.SetFromUserInput(target_crs)

    return osr.CoordinateTransformation(source, target)
