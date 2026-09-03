# QGIS Boundary Search Plugin Builder

Create a new QGIS autocomplete boundary plugin for **Africa, Nigeria, the Philippines, or another area** without editing Python code manually. GADM data is classified automatically; other shapefiles use a guided Level 0–5 assignment.

## What the pipeline asks for

1. The area or country name, such as `Nigeria`.
2. An SVG or PNG plugin icon.
3. A ZIP containing one or more complete shapefiles.

If the ZIP is GADM, the builder detects its administrative levels automatically. If it is not GADM, the builder lists the shapefiles and asks which file belongs to Level 0, Level 1, and so on through Level 5.

The finished QGIS plugin ZIP is created inside the `output` folder.

## Windows instructions

1. Extract `BoundaryPluginBuilder.zip`.
2. Double-click `build_boundary_plugin.bat`.
3. Enter the area name.
4. Choose the icon when the file window opens.
5. Choose the shapefile ZIP.
6. For non-GADM data, assign at least a Level 0 shapefile.
7. At Level 1–5, press Enter whenever the hierarchy is complete.
8. Confirm or select the boundary name and unique ID fields shown by the builder.
9. Wait for the `SUCCESS` message and open the builder's `output` folder.
10. In QGIS, select **Plugins → Manage and Install Plugins → Install from ZIP**.

Python 3 must be installed. The builder does not require GDAL, GeoPandas, Fiona, or any pip packages.

## Data ZIP requirements

Every shapefile must include at least:

- `.shp`
- `.shx`
- `.dbf`

Include `.prj` and `.cpg` whenever available. The builder preserves nested folders and all normal shapefile sidecar files.

The best results come from GADM-style data containing fields such as `GID_0`, `NAME_0`, `GID_1`, and `NAME_1`. The builder also recognizes common fields such as `COUNTRY`, `NAME`, `ADMIN`, `REGION`, `PROVINCE`, `DISTRICT`, `OBJECTID`, and `FID`.

## Classification rules

### GADM ZIP

- GADM filenames and `GID_0`–`GID_5` fields are detected.
- Levels are assigned automatically.
- No manual shapefile classification is requested.

### Non-GADM ZIP

- Level 0 is required.
- Levels 1, 2, 3, 4, and 5 are optional.
- Press Enter at the next level to stop. A plugin containing only Level 0, or only Levels 0–1, is valid.
- One or several shapefiles can be assigned to the same level by entering comma-separated numbers.
- The builder suggests name and ID fields; press Enter to accept or choose another displayed field.
- Enter `0` for the ID field to filter boundaries using their name and available parent fields.

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

Add `--force-manual` when you want to test or override the automatic GADM detection.

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
