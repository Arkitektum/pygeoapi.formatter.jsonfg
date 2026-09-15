# pygeoapi-formatter-jsonfg

A [JSON-FG](https://docs.ogc.org/is/21-045r1/21-045r1.html) output formatter for
[pygeoapi](https://pygeoapi.io/).

JSON-FG (OGC Features and Geometries JSON) is a GeoJSON extension that adds the
things GeoJSON deliberately leaves out:

| Member | What it adds |
| --- | --- |
| `coordRefSys` | The coordinate reference system of the data, so it need not be WGS 84 longitude/latitude. |
| `place` | A geometry in that CRS, in geometry types GeoJSON cannot express — in particular **circular arcs**. |
| `featureType` | The name of the feature type, e.g. `Building`. |
| `featureSchema` | A link to the schema describing the feature properties. |

Everything else stays valid GeoJSON, so a client that does not understand
JSON-FG can still read the document.

## How it works

pygeoapi's providers hand the API a GeoJSON document, and GeoJSON has no
circular arcs — by the time a formatter sees the data, any arc has already been
approximated by a chain of straight segments. Recovering the exact geometry
therefore needs a second, lossless copy of it.

This formatter expects the provider to supply that copy as a **synthetic
`_geometry_gml` feature property** holding the GML 3.2 encoding of the geometry:

```json
{
  "type": "Feature",
  "id": "1",
  "geometry": { "type": "LineString", "coordinates": [[0, 0], [1, 1], [2, 0]] },
  "properties": {
    "name": "Synthetic feature",
    "_geometry_gml": "<gml:Curve xmlns:gml=\"http://www.opengis.net/gml/3.2\"><gml:segments><gml:ArcString><gml:posList>0 0 1 1 2 0</gml:posList></gml:ArcString></gml:segments></gml:Curve>"
  }
}
```

For every feature the formatter then:

1. parses `_geometry_gml` with GDAL/OGR into an `ogr.Geometry`, which preserves
   the curve types (`CircularString`, `CompoundCurve`, `CurvePolygon`,
   `MultiCurve`, `MultiSurface`);
2. reprojects it from the provider's `storage_crs` to the CRS the client asked
   for via `?crs=` (pygeoapi's `content_crs`), if the two differ;
3. encodes it as the JSON-FG `place` member;
4. sets the GeoJSON `geometry` member to `null`, since `place` already carries
   the geometry and repeating it would ship the same shape twice;
5. leaves `_geometry_gml` out of the properties it writes, so it never reaches
   the client.

The circular-arcs conformance class is only advertised when a document actually
contains an arc, so clients that cannot handle arcs are not turned away from
documents they could have read.

Steps 3 and 4 are what `geometry_null: true` (the default) does. With
`geometry_null: false` the GeoJSON `geometry` member is kept as well — useful
for clients that do not understand JSON-FG — and is reprojected to CRS84, since
that is the only CRS GeoJSON allows.

If a feature has no `_geometry_gml` property, or GDAL cannot parse it, that one
feature is served without a `place` and keeps its GeoJSON geometry, and a
warning naming the feature id is logged. One unusable feature does not fail the
whole response.

## Requirements

* Python 3.12 or newer
* pygeoapi 0.24 or newer
* GDAL 3.12 (the `gdal` Python bindings, which must match the GDAL library
  installed on the system)
* A feature provider that adds the `_geometry_gml` property. It should also
  declare a `storage_crs`; as in pygeoapi itself, a provider without one is
  taken to store its data in CRS84.

## Installation

```bash
uv sync
```

or, into an existing pygeoapi environment:

```bash
pip install .
```

## Configuration

Reference the formatter from a collection's `formatters:` block in
`pygeoapi-config.yml`, by its dotted path:

```yaml
resources:
  buildings:
    type: collection
    formatters:
      - name: pygeoapi_formatter_jsonfg.JsonFgFormatter
        f: jsonfg
        mimetype: application/geo+json
        feature_type: Building
        attachment: false
        geometry_null: true
    providers:
      - type: feature
        name: ...
        storage_crs: http://www.opengis.net/def/crs/EPSG/0/25833
```

| Option | Default | Meaning |
| --- | --- | --- |
| `name` | — | Required by pygeoapi: the dotted path to the plugin class. |
| `f` | `jsonfg` | The value of the `f=` query parameter that selects this formatter. |
| `mimetype` | `application/geo+json` | The response `Content-Type`. |
| `feature_type` | *unset* | Value of the JSON-FG `featureType` member. |
| `attachment` | `false` | Whether pygeoapi serves the response as a file download. |
| `geometry_null` | `true` | Write the GeoJSON `geometry` member as `null` for features that got a `place`. Set to `false` to keep the (arc-approximated, CRS84) geometry alongside `place`. |

Features are then available as JSON-FG:

```
GET /collections/buildings/items?f=jsonfg
GET /collections/buildings/items?f=jsonfg&crs=http://www.opengis.net/def/crs/OGC/1.3/CRS84
```

## Example output

```json
{
  "type": "FeatureCollection",
  "conformsTo": [
    "http://www.opengis.net/spec/json-fg-1/1.0/conf/core",
    "http://www.opengis.net/spec/json-fg-1/1.0/conf/types-schemas",
    "http://www.opengis.net/spec/json-fg-1/1.0/conf/circular-arcs"
  ],
  "featureType": "Building",
  "featureSchema": "https://example.org/collections/buildings/schema?f=json",
  "coordRefSys": "http://www.opengis.net/def/crs/EPSG/0/25833",
  "geometryDimension": 2,
  "features": [
    {
      "type": "Feature",
      "place": {
        "type": "CircularString",
        "coordinates": [[0.0, 0.0], [1.0, 1.0], [2.0, 0.0]]
      },
      "geometry": null,
      "id": "1",
      "properties": { "name": "Synthetic feature", "height": 12.5 }
    }
  ],
  "numberReturned": 1,
  "numberMatched": 1,
  "links": [ "..." ],
  "timeStamp": "2026-01-01T12:00:00.000000Z"
}
```

An item response (a single feature) is written as a top-level `Feature` with the
same JSON-FG members, plus whatever `prev`, `next` and `links` pygeoapi put on
it.

## Geometry mapping

| OGR geometry | JSON-FG `place` type | Child member |
| --- | --- | --- |
| Point, MultiPoint | `Point`, `MultiPoint` | `coordinates` |
| LineString, MultiLineString | `LineString`, `MultiLineString` | `coordinates` |
| Polygon, Triangle | `Polygon` | `coordinates` |
| MultiPolygon | `MultiPolygon` | `coordinates` |
| CircularString | `CircularString` | `coordinates` |
| CompoundCurve | `CompoundCurve` | `geometries` |
| CurvePolygon | `CurvePolygon` | `geometries` (first entry is the exterior ring) |
| MultiCurve | `MultiCurve` | `geometries` |
| MultiSurface | `MultiSurface` | `geometries` |
| GeometryCollection | `GeometryCollection` | `geometries` |

The `geometries`/`coordinates` split is the part that most often surprises:
`CircularString` carries `coordinates` like a plain GeoJSON geometry, while the
other curve types carry `geometries`.

Further details handled by
[`geometry.py`](src/pygeoapi_formatter_jsonfg/geometry.py):

* **The 11-position cap.** The JSON-FG schema allows a `CircularString` of at
  most 11 positions (5 arcs). Longer arc strings are split into a
  `CompoundCurve` of chunks that share their meeting vertices.
* **Empty geometries.** `MultiPoint`, `MultiLineString`, `MultiPolygon` and
  `GeometryCollection` get an empty array; an empty `Point` or curve has no
  JSON-FG encoding, so `place` is omitted for those features.
* **Z and M.** Z becomes the third ordinate and M the fourth. XYM without Z has
  no unambiguous encoding and is rejected.
* **Axis order.** Transformations keep GDAL's authority-compliant axis mapping,
  which is what JSON-FG wants: positions follow the axis order of the CRS named
  by `coordRefSys`. The CRS84 URI is itself defined as longitude/latitude, so
  GeoJSON output comes out in the right order too.
* **Nesting rules.** Only the top-level geometry may carry `coordRefSys` or
  `bbox`; a `CompoundCurve` may only hold `LineString` and `CircularString`
  sections, so nested compound curves are spliced flat; a `GeometryCollection`
  may only hold the six simple GeoJSON types.

`geometry_to_place()` also takes options the formatter does not currently use —
`bbox`, `normalize` (drop curve containers that turned out to hold no arcs) and
`m_ordinate` — documented on the function itself.

## Project layout

```
src/pygeoapi_formatter_jsonfg/
├── __init__.py     public API: JsonFgFormatter, geometry_to_place, has_arcs
├── formatter.py    the pygeoapi plugin: GeoJSON document -> JSON-FG document
├── geometry.py     ogr.Geometry -> JSON-FG place object
├── crs.py          coordinate transformations (storage / content / CRS84)
└── constants.py    media type, conformance class URIs, other fixed values
```

## Development

```bash
uv sync --group dev
uv run pytest
```

The tests use synthetic geometries only; `tests/conftest.py` builds the GeoJSON
documents in the shape pygeoapi hands them to a formatter.
