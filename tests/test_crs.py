"""Tests for the coordinate transformation helper."""

import pytest
from conftest import CRS84, EPSG_25833, geom

from pygeoapi_formatter_jsonfg.crs import get_coordinate_transformation

EPSG_4326 = "http://www.opengis.net/def/crs/EPSG/0/4326"

#: A point in EPSG_25833, and the same point in longitude/latitude.
POINT_25833 = "POINT (262000 6650000)"
POINT_LON_LAT = (10.7415658933079, 59.918559537905)


def test_no_transformation_without_a_target():
    """pygeoapi leaves content_crs unset when the request carries no crs."""
    assert get_coordinate_transformation(EPSG_25833, None) is None


def test_no_transformation_between_identical_crs():
    assert get_coordinate_transformation(EPSG_25833, EPSG_25833) is None


def test_transformation_to_crs84_yields_longitude_latitude():
    """The CRS84 URI is defined as longitude/latitude, the GeoJSON order."""
    point = geom(POINT_25833)
    point.Transform(get_coordinate_transformation(EPSG_25833, CRS84))

    assert (point.GetX(), point.GetY()) == pytest.approx(POINT_LON_LAT)


def test_transformation_follows_the_authority_axis_order():
    """EPSG:4326 is latitude/longitude, and is written that way.

    JSON-FG positions follow the axis order of the CRS named by
    ``coordRefSys``, so this is what the ``place`` member needs.
    """
    point = geom(POINT_25833)
    point.Transform(get_coordinate_transformation(EPSG_25833, EPSG_4326))

    assert (point.GetX(), point.GetY()) == pytest.approx(POINT_LON_LAT[::-1])
