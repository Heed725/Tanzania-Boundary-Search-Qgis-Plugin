"""Tanzania Boundary Search QGIS plugin."""

from __future__ import annotations

import json
import os
import unicodedata

from qgis.PyQt.QtCore import QObject, Qt, QStringListModel
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QCompleter, QLabel, QLineEdit
from qgis.core import QgsFillSymbol, QgsProject, QgsVectorLayer


PLUGIN_NAME = "Tanzania Boundary Search"
LAYER_KEY_PROPERTY = "tanzania_boundary_search/gid"


def normalize(text):
    """Return a case- and accent-insensitive value for matching."""
    value = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(char for char in value if not unicodedata.combining(char)).casefold().strip()


class IconStringListModel(QStringListModel):
    """String-list model which decorates every completion with the plugin icon."""

    def __init__(self, strings, icon, parent=None):
        super().__init__(strings, parent)
        self._icon = icon

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DecorationRole:
            return self._icon
        return super().data(index, role)


class TanzaniaBoundarySearch(QObject):
    """Autocomplete Tanzania boundaries from QGIS's native Coordinate field."""

    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.plugin_icon = QIcon(os.path.join(self.plugin_dir, "icon.svg"))
        self.action = None
        self.search_edit = None
        self.completer = None
        self.previous_completer = None
        self.entries = []
        self.by_display = {}
        self.by_name = {}

    def initGui(self):  # noqa: N802 - QGIS API name
        """Create the plugin action and enhance QGIS's Coordinate field."""
        self.action = QAction(self.plugin_icon, PLUGIN_NAME, self.iface.mainWindow())
        self.action.setToolTip("Search Tanzania administrative boundaries")
        self.action.triggered.connect(self.focus_search)
        self.iface.addPluginToVectorMenu(PLUGIN_NAME, self.action)
        self.iface.addToolBarIcon(self.action)

        self._load_index()
        self._attach_to_coordinate_field()

    def unload(self):
        """Remove plugin actions and restore the Coordinate field."""
        if self.action is not None:
            self.iface.removePluginVectorMenu(PLUGIN_NAME, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None

        # Keep local references and clear instance state first so cleanup is
        # idempotent even if QGIS calls unload during a partial plugin reload.
        search_edit = self.search_edit
        completer = self.completer
        previous_completer = self.previous_completer
        self.search_edit = None
        self.completer = None
        self.previous_completer = None

        # Disconnect the completer before replacing it. QLineEdit may destroy
        # its current C++ completer as part of setCompleter(), so it must never
        # be accessed after the restore call unless guarded.
        if completer is not None:
            try:
                completer.activated[str].disconnect(self.load_boundary)
            except (TypeError, RuntimeError):
                pass

        if search_edit is not None:
            try:
                search_edit.returnPressed.disconnect(self._load_from_typed_text)
            except (TypeError, RuntimeError):
                pass
            try:
                if search_edit.completer() is completer:
                    search_edit.setCompleter(previous_completer)
            except RuntimeError:
                pass

        if completer is not None:
            try:
                completer.deleteLater()
            except RuntimeError:
                # The QLineEdit replacement may already have deleted the C++
                # object. Its Python wrapper must not be touched again.
                pass

    def _load_index(self):
        index_path = os.path.join(self.plugin_dir, "search_index.json")
        try:
            with open(index_path, "r", encoding="utf-8") as handle:
                self.entries = json.load(handle)
        except (OSError, ValueError) as error:
            self.entries = []
            self.iface.messageBar().pushCritical(
                PLUGIN_NAME, "Could not read the bundled place index: {}".format(error)
            )
            return

        self.entries.sort(key=lambda item: (item["level"], normalize(item["display"])))
        self.by_display = {normalize(item["display"]): item for item in self.entries}
        self.by_name = {}
        for item in self.entries:
            names = [item["name"]] + item.get("aliases", [])
            for name in names:
                key = normalize(name)
                if key:
                    self.by_name.setdefault(key, []).append(item)

    def _attach_to_coordinate_field(self):
        """Attach autocomplete to the QLineEdit inside QGIS's Coordinate widget."""
        coordinate_label = self.iface.mainWindow().findChild(QLabel, "mCoordsLabel")
        coordinate_widget = coordinate_label.parentWidget() if coordinate_label else None
        line_edits = coordinate_widget.findChildren(QLineEdit) if coordinate_widget else []
        self.search_edit = line_edits[0] if len(line_edits) == 1 else None

        if self.search_edit is None:
            self.iface.messageBar().pushCritical(
                PLUGIN_NAME, "Could not locate the QGIS Coordinate field."
            )
            return

        self.previous_completer = self.search_edit.completer()
        # Parent these helper objects to the plugin, not QGIS's line edit. This
        # gives the plugin explicit ownership across QGIS plugin reloads.
        self.completer = QCompleter(self)
        model = IconStringListModel(
            [entry["display"] for entry in self.entries], self.plugin_icon, self.completer
        )
        self.completer.setModel(model)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setMaxVisibleItems(12)
        self.completer.popup().setMinimumWidth(460)
        self.search_edit.setCompleter(self.completer)
        self.completer.activated[str].connect(self.load_boundary)
        self.search_edit.returnPressed.connect(self._load_from_typed_text)

    def focus_search(self):
        """Focus and select the search text when the toolbar/menu action is used."""
        if self.search_edit is not None:
            if self.search_edit.isReadOnly():
                self.iface.messageBar().pushWarning(
                    PLUGIN_NAME, "Switch the status display from Extents to Coordinate first."
                )
                return
            self.search_edit.setFocus(Qt.ShortcutFocusReason)
            self.search_edit.selectAll()

    def _load_from_typed_text(self):
        query = self.search_edit.text().strip()
        if not query:
            return

        entry = self._resolve_query(query)
        if entry is None:
            # Let QGIS keep handling ordinary coordinate values and its built-in
            # Coordinate-field commands. Unknown text is ignored by QGIS itself.
            return
        self._add_entry(entry)

    def _resolve_query(self, query):
        """Resolve a label/name, preferring country then region then lower levels."""
        key = normalize(query)
        if key in self.by_display:
            return self.by_display[key]

        exact = self.by_name.get(key, [])
        if exact:
            return sorted(exact, key=lambda item: item["level"])[0]

        prefix = [item for item in self.entries if normalize(item["name"]).startswith(key)]
        if len(prefix) == 1:
            return prefix[0]
        return None

    def load_boundary(self, display_text):
        """Load the autocomplete selection."""
        entry = self.by_display.get(normalize(display_text))
        if entry is None:
            entry = self._resolve_query(display_text)
        if entry is not None:
            self._add_entry(entry)

    def _add_entry(self, entry):
        project = QgsProject.instance()
        gid = entry["gid"]

        for existing in project.mapLayers().values():
            if existing.customProperty(LAYER_KEY_PROPERTY, "") == gid and existing.isValid():
                self.iface.setActiveLayer(existing)
                self._zoom_to_layer(existing)
                self.search_edit.setText(entry["display"])
                return

        source = os.path.join(self.plugin_dir, "data", entry["source"])
        if not os.path.isfile(source):
            self.iface.messageBar().pushCritical(
                PLUGIN_NAME, "Boundary file is missing: {}".format(entry["source"])
            )
            return

        layer = QgsVectorLayer(source, entry["layer_name"], "ogr")
        if not layer.isValid():
            self.iface.messageBar().pushCritical(
                PLUGIN_NAME, "QGIS could not open {}.".format(entry["source"])
            )
            return

        gid_field = "GID_{}".format(entry["level"])
        safe_gid = gid.replace("'", "''")
        if not layer.setSubsetString('"{}" = \'{}\''.format(gid_field, safe_gid)):
            self.iface.messageBar().pushCritical(
                PLUGIN_NAME, "Could not filter the selected boundary."
            )
            return

        layer.setCustomProperty(LAYER_KEY_PROPERTY, gid)
        layer.setCustomProperty("tanzania_boundary_search/display", entry["display"])
        self._style_layer(layer, entry["level"])
        project.addMapLayer(layer)
        self.iface.setActiveLayer(layer)
        self._zoom_to_layer(layer)
        self.search_edit.setText(entry["display"])
        self.iface.messageBar().pushSuccess(
            PLUGIN_NAME, "Loaded {}.".format(entry["display"])
        )

    def _style_layer(self, layer, level):
        colors = {
            0: (0, 163, 221, 55, 0, 92, 169, 255, "1.0"),
            1: (26, 177, 136, 50, 0, 121, 107, 255, "0.9"),
            2: (252, 209, 22, 58, 207, 157, 0, 255, "0.8"),
            3: (30, 136, 229, 45, 13, 71, 161, 255, "0.7"),
        }
        red, green, blue, alpha, or_, og, ob, oa, width = colors.get(level, colors[1])
        symbol = QgsFillSymbol.createSimple(
            {
                "color": "{},{},{},{}".format(red, green, blue, alpha),
                "outline_color": "{},{},{},{}".format(or_, og, ob, oa),
                "outline_width": width,
            }
        )
        layer.renderer().setSymbol(symbol)
        layer.triggerRepaint()

    def _zoom_to_layer(self, layer):
        layer.updateExtents()
        extent = layer.extent()
        if extent.isEmpty():
            return
        extent.scale(1.08)
        self.iface.mapCanvas().setExtent(extent)
        self.iface.mapCanvas().refresh()
