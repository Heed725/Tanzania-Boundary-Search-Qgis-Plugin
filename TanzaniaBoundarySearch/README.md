# Tanzania Boundary Search

Search and load Tanzania administrative boundaries directly from QGIS's existing **Coordinate** field.

## Features

- Autocomplete inside the normal QGIS Coordinate field
- Consistent Tanzania icon in Plugin Manager, menus, toolbar, and autocomplete suggestions
- Search across Tanzania, 31 regions, districts, and wards
- Contains-text matching, case-insensitive matching, and selected alternative names
- Loads only the chosen feature from the bundled GADM shapefile
- Automatically zooms to the boundary
- Avoids duplicate layers when the same boundary is searched again
- Uses different Tanzania-inspired styles for each administrative level
- Keeps normal coordinate entry working
- Works offline after installation

## Install

1. Download `TanzaniaBoundarySearch.zip`.
2. In QGIS, open **Plugins → Manage and Install Plugins**.
3. Choose **Install from ZIP**.
4. Select the downloaded ZIP and approve the security prompt.
5. Enable **Tanzania Boundary Search** if QGIS does not enable it automatically.

## Use

1. Click the value beside **Coordinate** in the bottom QGIS status bar.
2. Select the current coordinate text and type a name such as `Tanzania`, `Dodoma`, `Ilala`, or `Kati`.
3. Pick the correct autocomplete suggestion. Parent regions/districts are shown where needed.
4. The selected boundary is added and QGIS zooms to it.

You can continue entering normal coordinates such as `39.967, -7.460` in the same field. The plugin only acts when the text matches a Tanzania boundary.

Typing an exact shared name and pressing Enter prefers the higher administrative level. For example, `Dodoma` loads **Dodoma — Region**. To load a lower-level result, choose its full autocomplete label.

## Boundary levels

| Level | Meaning | Example |
| --- | --- | --- |
| 0 | Country | Tanzania |
| 1 | Region | Dodoma |
| 2 | District | Ilala |
| 3 | Ward/lower administrative area | Kati |

## Data

The bundled Tanzania boundary files are GADM 4.1 data supplied for this plugin. They remain subject to GADM's own license and are not covered by the plugin code license. Check <https://gadm.org/license.html> before redistribution or commercial use.

## License

Plugin source code: MIT License. See `LICENSE`.
