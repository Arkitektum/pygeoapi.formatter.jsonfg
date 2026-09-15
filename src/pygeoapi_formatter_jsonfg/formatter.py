"""The pygeoapi formatter plugin: GeoJSON feature collection -> JSON-FG.

pygeoapi hands the formatter the GeoJSON document it was about to serve. Each
feature carries a synthetic ``_geometry_gml`` property with the GML 3.2
encoding of its geometry, which is the only lossless source available here:
the GeoJSON ``geometry`` member has already had any circular arcs
approximated away. The formatter therefore re-reads the geometry from GML,
writes it to the JSON-FG ``place`` member, and drops the property.
"""

import json
import logging
from typing import Any, Dict, List, Tuple

from osgeo import ogr, osr
from pygeoapi.formatter.base import BaseFormatter
from pygeoapi.util import to_json

from . import constants
from .constants import (CONF_CIRCULAR_ARCS, CONF_CORE, CONF_TYPES_SCHEMAS,
                        EXTENSION, GEOMETRY_DIMENSION, GML_PROPERTY)
from .crs import get_coordinate_transformation
from .geometry import geometry_to_place, has_arcs

LOGGER = logging.getLogger(__name__)

__all__ = ["JsonFgFormatter"]


class JsonFgFormatter(BaseFormatter):
    """Serialize an OGC API - Features response as JSON-FG 1.0.

    Configure it in ``pygeoapi-config.yml`` under the collection:

    .. code-block:: yaml

        formatters:
          - name: pygeoapi_formatter_jsonfg.JsonFgFormatter
            f: jsonfg
            mimetype: application/geo+json
            feature_type: Bygning
            attachment: false
            geometry_null: true
    """

    #: Kept as class attributes for backwards compatibility; see
    #: `pygeoapi_formatter_jsonfg.constants` for the canonical definitions.
    DEFAULT_F = constants.DEFAULT_F
    DEFAULT_MIMETYPE = constants.DEFAULT_MIMETYPE
    CRS84_URI = constants.CRS84_URI

    def __init__(self, formatter_def: Dict[str, Any]):
        """
        :param formatter_def: the collection's ``formatters:`` entry. Honours
                              ``f``, ``mimetype``, ``attachment``,
                              ``feature_type`` and ``geometry_null``.
        """
        f = formatter_def.get("f", self.DEFAULT_F)
        mimetype = formatter_def.get("mimetype", self.DEFAULT_MIMETYPE)
        attachment = bool(formatter_def.get("attachment", False))

        # ``name`` is what pygeoapi keys the formatter by, and ``f`` is what it
        # matches the request format against; both are the short format name,
        # not the dotted plugin path in ``formatter_def['name']``.
        super().__init__({"name": f, "attachment": attachment})

        self.f = f
        self.mimetype = mimetype
        self.extension = EXTENSION

        #: JSON-FG ``featureType``: the name of the feature type the
        #: collection publishes. ``None`` omits the member.
        self.feature_type = formatter_def.get("feature_type")

        #: When true -- the default -- the GeoJSON ``geometry`` member is
        #: written as ``null`` for every feature that got a ``place``. JSON-FG
        #: allows this and it keeps the document from carrying the same
        #: geometry twice, once exactly and once arc-approximated in CRS84.
        #: Set ``geometry_null: false`` to keep the GeoJSON geometry as well,
        #: for clients that do not understand JSON-FG.
        self.geometry_null = bool(formatter_def.get("geometry_null", True))

    def write(
        self,
        options: Dict[str, Any] = {},
        data: Dict[str, Any] | None = None
    ) -> str:
        """Render *data* as a JSON-FG document.

        :param options: pygeoapi formatting options. Requires
                        ``provider_def`` (for ``storage_crs``) and
                        ``content_crs`` (the CRS requested by the client,
                        ``None`` when the request carried no ``crs``).
        :param data: the GeoJSON feature collection to convert.

        :returns: the JSON-FG document as a JSON string.
        """
        feature_collection: Dict[str, Any] = data or {}
        features: List[Dict[str, Any]] = feature_collection.get("features", [])

        # ``storage_crs`` is optional in a provider definition; pygeoapi itself
        # falls back to CRS84 when a collection does not declare one.
        provider_def: Dict[str, Any] = options.get("provider_def") or {}
        storage_crs: str = provider_def.get("storage_crs", self.CRS84_URI)
        content_crs: str | None = options.get("content_crs")

        LOGGER.debug(
            f'Formatting {len(features)} feature(s) as JSON-FG; '
            f'storage CRS {storage_crs}, content CRS {content_crs}')

        # GML -> requested CRS, for the ``place`` member.
        coord_trans = get_coordinate_transformation(storage_crs, content_crs)

        # Requested CRS -> CRS84, for the GeoJSON ``geometry`` member. Only
        # needed when the geometry is actually written out.
        crs84_coord_trans = self._get_crs84_coordinate_transformation(
            content_crs)

        features_out, has_any_arcs = self._create_features(
            features, coord_trans, crs84_coord_trans)

        is_single_feature = self._is_single_feature(features)

        # The links an item response carries sit on the feature rather than on
        # the collection pygeoapi wrapped it in, and that is where the
        # ``collection`` link the schema URL is derived from lives.
        links_owner = features[0] if is_single_feature else feature_collection

        # Members every JSON-FG document carries, whether it is a collection
        # or a single feature. Built first so the key order stays stable.
        head = {
            "conformsTo": self._get_conforms_to(has_any_arcs),
            "featureType": self.feature_type,
            "featureSchema": self._get_schema_link(links_owner),
            "coordRefSys": content_crs or storage_crs,
            "geometryDimension": GEOMETRY_DIMENSION
        }

        if is_single_feature:
            data_out = self._create_feature_document(
                head, features[0], features_out[0])
        else:
            data_out = self._create_feature_collection_document(
                head, feature_collection, features_out)

        return to_json(data_out, True)

    # ----------------------------------------------------------------- #
    # Features
    # ----------------------------------------------------------------- #

    def _create_features(
        self,
        features: List[Dict[str, Any]],
        coord_trans: osr.CoordinateTransformation | None,
        crs84_coord_trans: osr.CoordinateTransformation | None
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """Convert every input feature to its JSON-FG counterpart.

        :returns: the converted features, and whether any of them contains a
                  circular arc -- which decides the circular-arcs conformance
                  class for the whole document.
        """
        features_out: List[Dict[str, Any]] = []
        has_any_arcs = False

        for feature in features:
            geom = self._get_ogr_geometry(feature)

            if geom is not None:
                if coord_trans:
                    geom.Transform(coord_trans)

                has_any_arcs = has_any_arcs or has_arcs(geom)

            features_out.append(
                self._create_feature(feature, geom, crs84_coord_trans))

        return features_out, has_any_arcs

    def _get_ogr_geometry(
        self,
        feature: Dict[str, Any]
    ) -> ogr.Geometry | None:
        """Parse the feature's synthetic GML property.

        Returns ``None`` -- after logging a warning -- when the property is
        missing or GDAL cannot make sense of it. The feature then gets no
        ``place`` and keeps the GeoJSON geometry pygeoapi produced, which is a
        better outcome than failing the whole response over one feature.
        """
        properties: Dict[str, Any] = feature.get("properties") or {}
        gml = properties.get(GML_PROPERTY)
        feature_id = feature.get("id")

        if not gml:
            LOGGER.warning(
                f'Feature {feature_id} has no {GML_PROPERTY} property; '
                'falling back to its GeoJSON geometry')

            return None

        geom = ogr.CreateGeometryFromGML(gml)

        if geom is None:
            LOGGER.warning(
                f'Could not parse the {GML_PROPERTY} property of feature '
                f'{feature_id} as GML; falling back to its GeoJSON geometry')

        return geom

    def _create_feature(
        self,
        feature: Dict[str, Any],
        geom: ogr.Geometry | None,
        crs84_coord_trans: osr.CoordinateTransformation | None,
    ) -> Dict[str, Any]:
        """Build one JSON-FG feature from a GeoJSON feature and its geometry."""
        feature_out: Dict[str, Any] = {
            "type": "Feature"
        }

        place = geometry_to_place(geom)

        if place:
            feature_out["place"] = place

        feature_out["geometry"] = self._get_feature_geometry(
            geom, feature.get("geometry"), place is not None,
            crs84_coord_trans)
        feature_out["id"] = feature.get("id")
        feature_out["properties"] = self._get_properties(feature)

        return feature_out

    def _get_properties(self, feature: Dict[str, Any]) -> Dict[str, Any]:
        """The feature properties, without the synthetic GML property.

        A copy: the document belongs to pygeoapi, so it is left untouched.
        """
        properties: Dict[str, Any] = feature.get("properties") or {}

        return {key: value for key, value in properties.items()
                if key != GML_PROPERTY}

    def _get_feature_geometry(
        self,
        ogr_geom: ogr.Geometry | None,
        geom: Dict[str, Any] | None,
        has_place: bool,
        crs84_coord_trans: osr.CoordinateTransformation | None
    ) -> Dict[str, Any] | None:
        """The GeoJSON ``geometry`` member for a feature.

        ``null`` when the geometry is already carried by ``place``, otherwise
        the geometry pygeoapi produced -- re-projected to CRS84 by way of OGR
        when the requested CRS is something else.
        """
        if self.geometry_null and has_place:
            return None

        if crs84_coord_trans is None or geom is None:
            return geom

        if ogr_geom is None:
            # No usable GML to project from, so re-read the geometry pygeoapi
            # produced. It is already in the requested CRS, like the GML would
            # have been by this point.
            ogr_geom = ogr.CreateGeometryFromJson(json.dumps(geom))

            if ogr_geom is None:
                LOGGER.warning(
                    'Could not re-read the GeoJSON geometry; leaving it in '
                    'the requested CRS rather than CRS84')

                return geom

        ogr_geom.Transform(crs84_coord_trans)
        json_str = ogr_geom.ExportToJson()

        return json.loads(json_str)

    # ----------------------------------------------------------------- #
    # Documents
    # ----------------------------------------------------------------- #

    def _create_feature_collection_document(
        self,
        head: Dict[str, Any],
        feature_collection: Dict[str, Any],
        features_out: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """A JSON-FG ``FeatureCollection``."""
        data_out: Dict[str, Any] = {
            "type": "FeatureCollection",
            **head,
            "features": features_out,
            "numberReturned": feature_collection.get(
                "numberReturned", len(features_out))
        }

        # Optional in OGC API - Features. pygeoapi always supplies them, but a
        # provider that does not should not cost us the whole document.
        for member in ("numberMatched", "links", "timeStamp"):
            if member in feature_collection:
                data_out[member] = feature_collection[member]

        return data_out

    def _create_feature_document(
        self,
        head: Dict[str, Any],
        feature: Dict[str, Any],
        feature_out: Dict[str, Any]
    ) -> Dict[str, Any]:
        """A JSON-FG ``Feature``.

        The single feature is inlined into the top-level object rather than
        nested in a ``features`` array, and the navigation members pygeoapi
        puts on an item response are carried over.
        """
        data_out: Dict[str, Any] = {
            "type": "Feature",
            **head
        }

        if "place" in feature_out:
            data_out["place"] = feature_out["place"]

        data_out["geometry"] = feature_out["geometry"]
        data_out["id"] = feature_out["id"]
        data_out["properties"] = feature_out["properties"]

        for member in ("prev", "next", "links"):
            if member in feature:
                data_out[member] = feature[member]

        return data_out

    def _is_single_feature(self, features: List[Dict[str, Any]]) -> bool:
        """Whether *features* is an item response rather than a collection.

        pygeoapi wraps a single item in a feature collection before handing it
        to a formatter, so the two cases are told apart by the ``links``
        member: it sits on the feature for an item response and on the
        collection otherwise.
        """
        if not features or len(features) > 1:
            return False

        feature = features[0]

        return 'links' in feature and isinstance(feature['links'], list)

    # ----------------------------------------------------------------- #
    # Document members
    # ----------------------------------------------------------------- #

    def _get_schema_link(self, links_owner: Dict[str, Any] | None) -> str | None:
        """JSON-FG ``featureSchema``, derived from the collection link.

        :param links_owner: the object carrying the response's ``links``: the
                            feature for an item response, the feature
                            collection otherwise.
        """
        links: List[Dict[str, Any]] = (links_owner or {}).get("links") or []
        link = next(
            (link for link in links if link.get("rel") == "collection"), None)
        href = link.get("href") if link else None

        return f"{href}/schema?f=json" if href else None

    def _get_conforms_to(self, has_any_arcs: bool) -> List[str]:
        """JSON-FG ``conformsTo``.

        The circular-arcs class is only advertised when the document really
        contains an arc, so clients that cannot handle arcs are not turned
        away from documents they could have read.
        """
        conforms_to = [
            CONF_CORE,
            CONF_TYPES_SCHEMAS
        ]

        if has_any_arcs:
            conforms_to.append(CONF_CIRCULAR_ARCS)

        return conforms_to

    # ----------------------------------------------------------------- #
    # CRS
    # ----------------------------------------------------------------- #

    def _get_crs84_coordinate_transformation(
        self,
        content_crs: str | None
    ) -> osr.CoordinateTransformation | None:
        """Transformation for the GeoJSON ``geometry`` member, if any.

        ``None`` when the geometry is suppressed anyway, when the client asked
        for no particular CRS, or when it asked for CRS84 -- in which case
        pygeoapi already produced the geometry in the right CRS.
        """
        if (self.geometry_null
                or content_crs is None
                or content_crs == self.CRS84_URI):
            return None

        return get_coordinate_transformation(content_crs, self.CRS84_URI)

    def __repr__(self):
        return f'<JsonFgFormatter> {self.name}'
