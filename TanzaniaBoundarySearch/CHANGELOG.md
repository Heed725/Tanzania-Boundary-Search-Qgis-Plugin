# Changelog

## 1.1.1 — 2026-09-02

- Fixed `RuntimeError: wrapped C/C++ object of type QCompleter has been deleted` during unload.
- Made Coordinate-field cleanup safe and idempotent for QGIS plugin reloads.
- Gave the plugin explicit ownership of its completer and autocomplete model.

## 1.1.0 — 2026-09-02

- Moved autocomplete into QGIS's existing Coordinate input field.
- Removed the separate Tanzania Place status-bar widget.
- Preserved normal coordinate entry and QGIS's built-in Coordinate-field commands.
- Restores any previous Coordinate-field completer when the plugin is unloaded.

## 1.0.1 — 2026-09-02

- Fixed QGIS `QgsMessageBar.pushSuccess()` compatibility after loading a boundary.
- Fixed the equivalent `pushInfo()` call used when a boundary is already loaded.

## 1.0.0 — 2026-09-02

- Initial release.
- Added status-bar autocomplete for Tanzania administrative levels 0–3.
- Added filtered layer loading, automatic styling, zooming, and duplicate detection.
- Bundled the supplied GADM 4.1 Tanzania shapefiles for offline use.
