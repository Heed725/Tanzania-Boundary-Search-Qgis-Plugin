# QGIS Boundary Search Plugin Builder

Create a new QGIS autocomplete boundary plugin for **Africa, Nigeria, the Philippines, or another area** without editing Python code manually.

## What the pipeline asks for

1. The area or country name, such as `Nigeria`.
2. An SVG or PNG plugin icon.
3. A ZIP containing one or more complete shapefiles.

The finished QGIS plugin ZIP is created inside the `output` folder.

## Windows instructions

1. Extract `BoundaryPluginBuilder.zip`.
2. Double-click `build_boundary_plugin.bat`.
3. Enter the area name.
4. Choose the icon when the file window opens.
5. Choose the shapefile ZIP.
6. Wait for the `SUCCESS` message.
7. Open the builder's `output` folder.
8. In QGIS, select **Plugins → Manage and Install Plugins → Install from ZIP**.

Python 3 must be installed. The builder does not require GDAL, GeoPandas, Fiona, or any pip packages.

## Data ZIP requirements

Every shapefile must include at least:

- `.shp`
- `.shx`
- `.dbf`

Include `.prj` and `.cpg` whenever available. The builder preserves nested folders and all normal shapefile sidecar files.

The best results come from GADM-style data containing fields such as `GID_0`, `NAME_0`, `GID_1`, and `NAME_1`. The builder also recognizes common fields such as `COUNTRY`, `NAME`, `ADMIN`, `REGION`, `PROVINCE`, `DISTRICT`, `OBJECTID`, and `FID`.

## Examples

| Desired plugin | Name entered | Data ZIP |
| --- | --- | --- |
| Nigeria | `Nigeria` | GADM Nigeria levels 0–3 |
| Philippines | `Philippines` | GADM Philippines levels 0–3 |
| Africa | `Africa` | One or more African country/admin shapefiles |

## Optional command-line use

```bat
py -3 build_boundary_plugin.py --name "Nigeria" --icon "C:\GIS\nigeria.svg" --data "C:\GIS\gadm41_NGA_shp.zip" --output "C:\GIS\output"
```

## Safety and behavior

- Rejects damaged ZIP files and unsafe `..` extraction paths.
- Never overwrites an existing output ZIP; a numbered filename is created instead.
- Creates a valid QGIS plugin folder at the ZIP root.
- Keeps ordinary QGIS Coordinate entry working.
- Uses deletion-safe autocomplete cleanup when the plugin is disabled or uninstalled.
- Uses a QGIS message API compatible with supported QGIS 3 releases.
- Works offline after the generated plugin is installed.

## Data licensing

The generated plugin bundles the shapefiles you select. You are responsible for checking the original data provider's license and redistribution terms before publishing or sharing it.

The builder source is released under the MIT License. See `LICENSE`.
