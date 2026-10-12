"""The formatter must not change, or depend on, the global GDAL exception mode."""

import importlib

from conftest import CRS84, GML_POINT, make_feature, make_feature_collection, make_options
from osgeo import ogr, osr

import pygeoapi_formatter_jsonfg.crs as crs_module


def test_importing_the_package_leaves_the_mode_alone(gdal_exception_mode):
    importlib.reload(crs_module)

    assert bool(ogr.GetUseExceptions()) is gdal_exception_mode
    assert bool(osr.GetUseExceptions()) is gdal_exception_mode


def test_writing_leaves_the_mode_alone(formatter, gdal_exception_mode):
    data = make_feature_collection([
        make_feature(GML_POINT, feature_id="1"),
        make_feature("<not-gml/>", feature_id="2")])

    formatter.write(make_options(content_crs=CRS84), data)

    assert bool(ogr.GetUseExceptions()) is gdal_exception_mode
    assert bool(osr.GetUseExceptions()) is gdal_exception_mode
