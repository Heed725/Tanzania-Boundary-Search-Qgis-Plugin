"""Build a self-contained QGIS boundary autocomplete plugin from zipped shapefiles.

The builder uses only the Python standard library, so it works with ordinary
Python 3 on Windows. Run it through build_boundary_plugin.bat for interactive
prompts, or pass command-line arguments for repeatable builds.
"""

from __future__ import annotations

import argparse
import codecs
import json
import re
import shutil
import struct
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath


BUILDER_VERSION = "1.0.0"
SIDECAR_EXTENSIONS = {
    ".shp",
    ".shx",
    ".dbf",
    ".prj",
    ".cpg",
    ".qpj",
    ".sbn",
    ".sbx",
    ".xml",
}
DEFAULT_AUTHOR = "Hemed Lungo"
DEFAULT_EMAIL = "Hemedlungo@gmail.com"
DEFAULT_HOMEPAGE = "https://github.com/Heed725"


PLUGIN_TEMPLATE = r'''"""@@PLUGIN_NAME@@ QGIS plugin."""

from __future__ import annotations

import json
import os
import unicodedata

from qgis.PyQt.QtCore import QObject, Qt, QStringListModel
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QCompleter, QLabel, QLineEdit
from qgis.core import Qgis, QgsExpression, QgsFillSymbol, QgsProject, QgsVectorLayer


PLUGIN_NAME = @@PLUGIN_NAME_JSON@@
AREA_NAME = @@AREA_NAME_JSON@@
ICON_FILE = @@ICON_FILE_JSON@@
LAYER_KEY_PROPERTY = @@LAYER_KEY_JSON@@


def normalize(text):
    """Return a case- and accent-insensitive value for matching."""
    value = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(char for char in value if not unicodedata.combining(char)).casefold().strip()


class IconStringListModel(QStringListModel):
    """String-list model which decorates completions with the plugin icon."""

    def __init__(self, strings, icon, parent=None):
        super().__init__(strings, parent)
        self._icon = icon

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DecorationRole:
            return self._icon
        return super().data(index, role)


class BoundarySearchPlugin(QObject):
    """Autocomplete administrative boundaries from QGIS's Coordinate field."""

    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.plugin_icon = QIcon(os.path.join(self.plugin_dir, ICON_FILE))
        self.action = None
        self.search_edit = None
        self.completer = None
        self.previous_completer = None
        self.entries = []
        self.by_display = {}
        self.by_name = {}

    def initGui(self):  # noqa: N802 - QGIS API name
        self.action = QAction(self.plugin_icon, PLUGIN_NAME, self.iface.mainWindow())
        self.action.setToolTip("Search {} administrative boundaries".format(AREA_NAME))
        self.action.triggered.connect(self.focus_search)
        self.iface.addPluginToVectorMenu(PLUGIN_NAME, self.action)
        self.iface.addToolBarIcon(self.action)
        self._load_index()
        self._attach_to_coordinate_field()

    def unload(self):
        """Remove plugin actions and safely restore the Coordinate field."""
        if self.action is not None:
            self.iface.removePluginVectorMenu(PLUGIN_NAME, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None

        search_edit = self.search_edit
        completer = self.completer
        previous_completer = self.previous_completer
        self.search_edit = None
        self.completer = None
        self.previous_completer = None

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
                pass

    def _notify(self, text, level=Qgis.Info, duration=5):
        """Use the stable QgsMessageBar API across supported QGIS versions."""
        self.iface.messageBar().pushMessage(
            PLUGIN_NAME, text, level=level, duration=duration
        )

    def _load_index(self):
        index_path = os.path.join(self.plugin_dir, "search_index.json")
        try:
            with open(index_path, "r", encoding="utf-8") as handle:
                self.entries = json.load(handle)
        except (OSError, ValueError) as error:
            self.entries = []
            self._notify(
                "Could not read the bundled place index: {}".format(error), Qgis.Critical
            )
            return

        self.entries.sort(key=lambda item: (item["level"], normalize(item["display"])))
        self.by_display = {normalize(item["display"]): item for item in self.entries}
        self.by_name = {}
        for item in self.entries:
            for name in [item["name"]] + item.get("aliases", []):
                key = normalize(name)
                if key:
                    self.by_name.setdefault(key, []).append(item)

    def _attach_to_coordinate_field(self):
        coordinate_label = self.iface.mainWindow().findChild(QLabel, "mCoordsLabel")
        coordinate_widget = coordinate_label.parentWidget() if coordinate_label else None
        line_edits = coordinate_widget.findChildren(QLineEdit) if coordinate_widget else []
        self.search_edit = line_edits[0] if line_edits else None

        if self.search_edit is None:
            self._notify("Could not locate the QGIS Coordinate field.", Qgis.Critical)
            return

        self.previous_completer = self.search_edit.completer()
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
        if self.search_edit is None:
            return
        if self.search_edit.isReadOnly():
            self._notify("Switch the status display from Extents to Coordinate first.", Qgis.Warning)
            return
        self.search_edit.setFocus(Qt.ShortcutFocusReason)
        self.search_edit.selectAll()

    def _load_from_typed_text(self):
        if self.search_edit is None:
            return
        query = self.search_edit.text().strip()
        if not query:
            return
        entry = self._resolve_query(query)
        if entry is not None:
            self._add_entry(entry)

    def _resolve_query(self, query):
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
        entry = self.by_display.get(normalize(display_text))
        if entry is None:
            entry = self._resolve_query(display_text)
        if entry is not None:
            self._add_entry(entry)

    def _add_entry(self, entry):
        project = QgsProject.instance()
        entry_key = entry["key"]
        for existing in project.mapLayers().values():
            if existing.customProperty(LAYER_KEY_PROPERTY, "") == entry_key and existing.isValid():
                self.iface.setActiveLayer(existing)
                self._zoom_to_layer(existing)
                if self.search_edit is not None:
                    self.search_edit.setText(entry["display"])
                return

        source_parts = entry["source"].replace("\\", "/").split("/")
        source = os.path.join(self.plugin_dir, "data", *source_parts)
        if not os.path.isfile(source):
            self._notify(
                "Boundary file is missing: {}".format(entry["source"]), Qgis.Critical
            )
            return

        layer = QgsVectorLayer(source, entry["layer_name"], "ogr")
        if not layer.isValid():
            self._notify("QGIS could not open {}.".format(entry["source"]), Qgis.Critical)
            return

        filter_parts = []
        for item in entry.get("filters", []):
            filter_parts.append(
                "({})".format(
                    "{} = {}".format(
                        QgsExpression.quotedColumnRef(item["field"]),
                        QgsExpression.quotedValue(item["value"]),
                    )
                )
            )
        if not filter_parts or not layer.setSubsetString(" AND ".join(filter_parts)):
            self._notify("Could not filter the selected boundary.", Qgis.Critical)
            return

        layer.setCustomProperty(LAYER_KEY_PROPERTY, entry_key)
        layer.setCustomProperty(LAYER_KEY_PROPERTY + "/display", entry["display"])
        self._style_layer(layer, entry["level"])
        project.addMapLayer(layer)
        self.iface.setActiveLayer(layer)
        self._zoom_to_layer(layer)
        if self.search_edit is not None:
            self.search_edit.setText(entry["display"])
        self._notify("Loaded {}.".format(entry["display"]), Qgis.Success, 4)

    def _style_layer(self, layer, level):
        colors = {
            0: (0, 163, 221, 55, 0, 92, 169, 255, "1.0"),
            1: (26, 177, 136, 50, 0, 121, 107, 255, "0.9"),
            2: (252, 209, 22, 58, 207, 157, 0, 255, "0.8"),
            3: (30, 136, 229, 45, 13, 71, 161, 255, "0.7"),
        }
        red, green, blue, alpha, out_r, out_g, out_b, out_a, width = colors.get(
            level, colors[level % 4]
        )
        symbol = QgsFillSymbol.createSimple(
            {
                "color": "{},{},{},{}".format(red, green, blue, alpha),
                "outline_color": "{},{},{},{}".format(out_r, out_g, out_b, out_a),
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
'''


INIT_TEMPLATE = '''"""QGIS entry point for @@PLUGIN_NAME@@."""


def classFactory(iface):  # pylint: disable=invalid-name
    """Return the plugin instance expected by QGIS."""
    from .boundary_search_plugin import BoundarySearchPlugin

    return BoundarySearchPlugin(iface)
'''


def clean_text(value: object) -> str:
    return " ".join(str(value or "").replace("\x00", "").split()).strip()


def ascii_identifier(value: str, suffix: str = "") -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    words = re.findall(r"[A-Za-z0-9]+", ascii_value)
    identifier = "".join(word[:1].upper() + word[1:] for word in words)
    if not identifier:
        identifier = "Boundary"
    if identifier[0].isdigit():
        identifier = "Area" + identifier
    if suffix and not identifier.casefold().endswith(suffix.casefold()):
        identifier += suffix
    return identifier


def property_identifier(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    compact = re.sub(r"[^a-z0-9]+", "_", ascii_value).strip("_")
    return compact or "boundary_search"


def choose_file(title: str, filetypes: list[tuple[str, str]]) -> Path:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(title=title, filetypes=filetypes)
        root.destroy()
        if selected:
            return Path(selected).expanduser().resolve()
    except Exception:
        pass

    while True:
        selected = input("{}: ".format(title)).strip().strip('"')
        path = Path(selected).expanduser()
        if path.is_file():
            return path.resolve()
        print("File not found. Try again.")


def prompt_required(label: str) -> str:
    while True:
        value = input("{}: ".format(label)).strip()
        if value:
            return value
        print("A value is required.")


def safe_extract(archive: Path, destination: Path) -> None:
    destination_root = destination.resolve()
    with zipfile.ZipFile(archive) as handle:
        bad_member = handle.testzip()
        if bad_member:
            raise ValueError("The data ZIP is damaged at: {}".format(bad_member))
        for info in handle.infolist():
            member = PurePosixPath(info.filename.replace("\\", "/"))
            if member.is_absolute() or ".." in member.parts:
                raise ValueError("Unsafe path inside data ZIP: {}".format(info.filename))
            target = (destination / Path(*member.parts)).resolve()
            if destination_root != target and destination_root not in target.parents:
                raise ValueError("Unsafe path inside data ZIP: {}".format(info.filename))
        handle.extractall(destination)


def sidecar_path(source_path: Path, suffix: str) -> Path:
    wanted_stem = source_path.stem.casefold()
    wanted_suffix = suffix.casefold()
    for candidate in source_path.parent.iterdir():
        if candidate.is_file() and candidate.stem.casefold() == wanted_stem:
            if candidate.suffix.casefold() == wanted_suffix:
                return candidate
    return source_path.with_suffix(suffix)


def dbf_encoding(dbf_path: Path) -> str:
    cpg_path = sidecar_path(dbf_path, ".cpg")
    if cpg_path.is_file():
        raw = cpg_path.read_text(encoding="ascii", errors="ignore").strip()
        aliases = {"65001": "utf-8", "UTF8": "utf-8", "ANSI 1252": "cp1252"}
        candidate = aliases.get(raw.upper(), raw)
        try:
            codecs.lookup(candidate)
            return candidate
        except LookupError:
            pass
    return "cp1252"


def parse_dbf_value(raw: bytes, field_type: str, decimals: int, encoding: str) -> object:
    text = raw.decode(encoding, errors="replace").replace("\x00", "").strip()
    if not text:
        return None
    if field_type in {"N", "F", "I", "B", "Y"}:
        try:
            if decimals == 0 and not any(char in text for char in ".eE"):
                return int(text)
            return float(text)
        except ValueError:
            return text
    if field_type == "L":
        return text.upper() in {"Y", "T", "1"}
    return text


def read_dbf(dbf_path: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    encoding = dbf_encoding(dbf_path)
    with dbf_path.open("rb") as handle:
        header = handle.read(32)
        if len(header) != 32:
            raise ValueError("Invalid DBF header: {}".format(dbf_path.name))
        record_count = struct.unpack("<I", header[4:8])[0]
        header_length = struct.unpack("<H", header[8:10])[0]
        record_length = struct.unpack("<H", header[10:12])[0]
        fields: list[dict[str, object]] = []
        while handle.tell() < header_length:
            descriptor = handle.read(32)
            if not descriptor or descriptor[0] == 0x0D:
                break
            name = descriptor[:11].split(b"\x00", 1)[0].decode("ascii", errors="ignore")
            fields.append(
                {
                    "name": name,
                    "type": chr(descriptor[11]),
                    "length": descriptor[16],
                    "decimals": descriptor[17],
                }
            )
        handle.seek(header_length)
        records: list[dict[str, object]] = []
        for _ in range(record_count):
            raw_record = handle.read(record_length)
            if len(raw_record) < record_length:
                break
            if raw_record[:1] == b"*":
                continue
            offset = 1
            record: dict[str, object] = {}
            for field in fields:
                length = int(field["length"])
                raw_value = raw_record[offset : offset + length]
                offset += length
                record[str(field["name"])] = parse_dbf_value(
                    raw_value, str(field["type"]), int(field["decimals"]), encoding
                )
            records.append(record)
    return fields, records


def field_lookup(fields: list[dict[str, object]]) -> dict[str, str]:
    return {str(field["name"]).upper(): str(field["name"]) for field in fields}


def first_field(lookup: dict[str, str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate.upper() in lookup:
            return lookup[candidate.upper()]
    return None


def detect_level(shapefile: Path, lookup: dict[str, str]) -> int:
    filename_match = re.search(r"(?:_|-)(\d+)$", shapefile.stem)
    if filename_match:
        return int(filename_match.group(1))
    levels = []
    for field_name in lookup:
        match = re.match(r"(?:GID|NAME|TYPE|ENGTYPE|VARNAME|NL_NAME)_(\d+)$", field_name)
        if match:
            levels.append(int(match.group(1)))
    return max(levels) if levels else 0


def name_field_for(level: int, lookup: dict[str, str]) -> str | None:
    candidates = [
        "NAME_{}".format(level),
        "NAME{}".format(level),
        "ADM{}_NAME".format(level),
        "ADMIN{}_NAME".format(level),
    ]
    if level == 0:
        candidates.extend(["COUNTRY", "SOVEREIGNT", "ADMIN", "NAME_EN", "NAME"])
    else:
        candidates.extend(["NAME_EN", "NAME", "ADMIN", "REGION", "PROVINCE", "DISTRICT"])
    return first_field(lookup, candidates)


def id_field_for(level: int, lookup: dict[str, str]) -> str | None:
    return first_field(
        lookup,
        [
            "GID_{}".format(level),
            "ID_{}".format(level),
            "ID{}".format(level),
            "ADM{}_CODE".format(level),
            "ADMIN{}_CODE".format(level),
            "HASC_{}".format(level),
            "ISO_{}".format(level),
            "ISO_A3",
            "ADM0_A3",
            "OBJECTID",
            "FID",
        ],
    )


def parent_name_fields(level: int, lookup: dict[str, str]) -> list[str]:
    result = []
    for parent_level in range(level):
        field = name_field_for(parent_level, lookup)
        if field and field not in result:
            result.append(field)
    return result


def admin_type_for(level: int, record: dict[str, object], lookup: dict[str, str]) -> str:
    field = first_field(
        lookup,
        ["ENGTYPE_{}".format(level), "TYPE_{}".format(level), "TYPE{}".format(level)],
    )
    if field:
        value = clean_text(record.get(field))
        if value and value.casefold() not in {"unknown", "n/a", "na"}:
            return value
    defaults = {0: "Country", 1: "Region", 2: "District", 3: "Ward"}
    return defaults.get(level, "Administrative level {}".format(level))


def aliases_for(
    level: int, name: str, record: dict[str, object], lookup: dict[str, str]
) -> list[str]:
    aliases: list[str] = []
    candidates = [
        "VARNAME_{}".format(level),
        "NL_NAME_{}".format(level),
        "ALT_NAME",
        "NAME_ALT",
        "NAME_EN",
    ]
    for candidate in candidates:
        field = lookup.get(candidate.upper())
        if not field:
            continue
        raw = clean_text(record.get(field))
        for value in re.split(r"[|;]", raw):
            alias = clean_text(value)
            if (
                alias
                and alias.casefold() not in {"na", "n/a", "none", "null", "<null>", "unknown"}
                and alias.casefold() != name.casefold()
                and alias.casefold() not in {
                item.casefold() for item in aliases
                }
            ):
                aliases.append(alias)
    return aliases


def build_entries(
    extraction_root: Path, copied_sources: dict[Path, str], area_name: str
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    country_names: set[str] = set()
    for shapefile in sorted(copied_sources, key=lambda item: item.as_posix().casefold()):
        dbf_path = sidecar_path(shapefile, ".dbf")
        if not dbf_path.is_file():
            raise ValueError("Missing DBF for {}".format(shapefile.name))
        fields, records = read_dbf(dbf_path)
        lookup = field_lookup(fields)
        level = detect_level(shapefile, lookup)
        name_field = name_field_for(level, lookup)
        if not name_field:
            raise ValueError(
                "Could not find a name field in {}. Expected NAME_{}, COUNTRY, NAME, "
                "ADMIN, REGION, PROVINCE, or DISTRICT.".format(dbf_path.name, level)
            )
        id_field = id_field_for(level, lookup)
        parent_fields = parent_name_fields(level, lookup)
        source = copied_sources[shapefile]
        country_field = name_field_for(0, lookup)

        for record_number, record in enumerate(records):
            name = clean_text(record.get(name_field))
            if not name:
                continue
            parents = [clean_text(record.get(field)) for field in parent_fields]
            parents = [parent for parent in parents if parent and parent.casefold() != name.casefold()]
            country_name = clean_text(record.get(country_field)) if country_field else ""
            if country_name:
                country_names.add(country_name.casefold())
            admin_type = admin_type_for(level, record, lookup)
            filters: list[dict[str, object]] = []
            if id_field and record.get(id_field) not in {None, ""}:
                filters.append({"field": id_field, "value": record[id_field]})
            else:
                for field in parent_fields + [name_field]:
                    value = record.get(field)
                    if value not in {None, ""}:
                        filters.append({"field": field, "value": value})
            if not filters:
                continue

            identity = json.dumps(filters, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            key = "{}|{}".format(source, identity)
            aliases = aliases_for(level, name, record, lookup)
            if level == 0 and len(records) == 1 and area_name.casefold() != name.casefold():
                aliases.append(area_name)
            entries.append(
                {
                    "level": level,
                    "name": name,
                    "aliases": aliases,
                    "display": "",
                    "layer_name": "",
                    "source": source,
                    "filters": filters,
                    "key": key,
                    "record": record_number,
                    "_parents": parents,
                    "_country": country_name,
                    "_admin_type": admin_type,
                }
            )

    show_country_parent = len(country_names) > 1
    for entry in entries:
        parents = list(entry.pop("_parents", []))
        country_name = clean_text(entry.pop("_country", ""))
        admin_type = clean_text(entry.pop("_admin_type", "Boundary"))
        if not show_country_parent and country_name and parents:
            if parents[0].casefold() == country_name.casefold():
                parents.pop(0)
        parent_label = ", ".join(reversed(parents))
        display = "{} — {}".format(entry["name"], admin_type)
        if parent_label:
            display += " ({})".format(parent_label)
        entry["display"] = display
        entry["layer_name"] = (
            str(entry["name"])
            if not parent_label
            else "{} — {}".format(entry["name"], parent_label)
        )

    seen: dict[str, int] = {}
    for entry in entries:
        base = str(entry["display"])
        count = seen.get(base.casefold(), 0) + 1
        seen[base.casefold()] = count
        if count > 1:
            entry["display"] = "{} [{}]".format(base, count)
    for entry in entries:
        entry.pop("record", None)
    entries.sort(key=lambda item: (int(item["level"]), str(item["display"]).casefold()))
    if not entries:
        raise ValueError("No searchable records were found in the supplied shapefiles.")
    return entries


def discover_and_copy_data(extraction_root: Path, data_destination: Path) -> dict[Path, str]:
    shapefiles = sorted(
        (path for path in extraction_root.rglob("*") if path.is_file() and path.suffix.lower() == ".shp"),
        key=lambda path: path.as_posix().casefold(),
    )
    if not shapefiles:
        raise ValueError("The selected ZIP contains no .shp files.")

    copied_sources: dict[Path, str] = {}
    for shapefile in shapefiles:
        siblings = {
            path.name.casefold(): path for path in shapefile.parent.iterdir() if path.is_file()
        }
        dbf_name = (shapefile.stem + ".dbf").casefold()
        shx_name = (shapefile.stem + ".shx").casefold()
        if dbf_name not in siblings:
            raise ValueError("{} has no matching .dbf file.".format(shapefile.name))
        if shx_name not in siblings:
            raise ValueError("{} has no matching .shx file.".format(shapefile.name))

        relative_parent = shapefile.parent.relative_to(extraction_root)
        for candidate in shapefile.parent.iterdir():
            if not candidate.is_file():
                continue
            if candidate.stem.casefold() != shapefile.stem.casefold():
                continue
            if candidate.suffix.lower() not in SIDECAR_EXTENSIONS:
                continue
            target = data_destination / relative_parent / candidate.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, target)
        copied_source = (relative_parent / shapefile.name).as_posix()
        copied_sources[shapefile] = copied_source
    return copied_sources


def render_plugin_source(plugin_name: str, area_name: str, icon_file: str, property_key: str) -> str:
    replacements = {
        "@@PLUGIN_NAME@@": plugin_name,
        "@@PLUGIN_NAME_JSON@@": json.dumps(plugin_name, ensure_ascii=False),
        "@@AREA_NAME_JSON@@": json.dumps(area_name, ensure_ascii=False),
        "@@ICON_FILE_JSON@@": json.dumps(icon_file, ensure_ascii=False),
        "@@LAYER_KEY_JSON@@": json.dumps("boundary_search/{}/key".format(property_key)),
    }
    content = PLUGIN_TEMPLATE
    for marker, value in replacements.items():
        content = content.replace(marker, value)
    return content


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8", newline="\n")


def plugin_readme(plugin_name: str, area_name: str, zip_name: str, entry_count: int) -> str:
    return """# {plugin_name}

Type {area_name} place names directly in QGIS's native **Coordinate** field and load the matching boundary.

## Install

1. Open **Plugins → Manage and Install Plugins** in QGIS.
2. Choose **Install from ZIP**.
3. Select `{zip_name}`.
4. Approve the prompt and enable **{plugin_name}**.

## Use

Click the value beside **Coordinate**, type a place name, and choose an autocomplete suggestion. Normal coordinate input continues to work.

The generated plugin contains **{entry_count:,} searchable boundaries** and works offline.

## Data license

The boundary files keep the license and redistribution terms of their original data provider. Verify those terms before sharing the generated plugin.
""".format(
        plugin_name=plugin_name,
        area_name=area_name,
        zip_name=zip_name,
        entry_count=entry_count,
    )


def build_plugin(
    area_name: str,
    icon_path: Path,
    data_zip: Path,
    output_directory: Path,
    plugin_name: str | None = None,
    author: str = DEFAULT_AUTHOR,
    email: str = DEFAULT_EMAIL,
    homepage: str = DEFAULT_HOMEPAGE,
) -> Path:
    area_name = clean_text(area_name)
    plugin_name = clean_text(plugin_name) if plugin_name else "{} Boundary Search".format(area_name)
    author = clean_text(author)
    email = clean_text(email)
    homepage = clean_text(homepage)
    if not area_name or not plugin_name:
        raise ValueError("Area name and plugin name cannot be empty.")
    if icon_path.suffix.lower() not in {".svg", ".png"}:
        raise ValueError("The icon must be an SVG or PNG file.")
    if not zipfile.is_zipfile(data_zip):
        raise ValueError("The selected data file is not a valid ZIP archive.")

    plugin_folder_name = ascii_identifier(area_name, "BoundarySearch")
    property_key = property_identifier(area_name)
    icon_file = "icon" + icon_path.suffix.lower()
    output_directory.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="boundary_plugin_builder_") as temporary:
        temporary_root = Path(temporary)
        extracted = temporary_root / "extracted"
        plugin_parent = temporary_root / "plugin"
        plugin_directory = plugin_parent / plugin_folder_name
        data_directory = plugin_directory / "data"
        extracted.mkdir()
        data_directory.mkdir(parents=True)

        safe_extract(data_zip, extracted)
        copied_sources = discover_and_copy_data(extracted, data_directory)
        entries = build_entries(extracted, copied_sources, area_name)
        shutil.copy2(icon_path, plugin_directory / icon_file)

        source = render_plugin_source(plugin_name, area_name, icon_file, property_key)
        init_source = INIT_TEMPLATE.replace("@@PLUGIN_NAME@@", plugin_name)
        metadata = """[general]
name={plugin_name}
description=Type {area_name} place names in the QGIS Coordinate field to load boundaries.
about=Autocomplete {area_name} administrative boundaries from QGIS's existing Coordinate field. Normal coordinate entry continues to work.
version=1.0.0
qgisMinimumVersion=3.22
author={author}
email={email}
category=Vector
icon={icon_file}
tags=boundary,autocomplete,place search,{area_tag},administrative boundaries
homepage={homepage}
experimental=False
deprecated=False
hasProcessingProvider=no
server=False
""".format(
            plugin_name=plugin_name,
            area_name=area_name,
            author=author,
            email=email,
            icon_file=icon_file,
            area_tag=property_key,
            homepage=homepage,
        )

        write_text(plugin_directory / "boundary_search_plugin.py", source)
        write_text(plugin_directory / "__init__.py", init_source)
        write_text(plugin_directory / "metadata.txt", metadata)
        write_text(
            plugin_directory / "search_index.json",
            json.dumps(entries, ensure_ascii=False, separators=(",", ":")),
        )

        output_path = output_directory / (plugin_folder_name + ".zip")
        if output_path.exists():
            number = 2
            while (output_directory / "{}-{}.zip".format(plugin_folder_name, number)).exists():
                number += 1
            output_path = output_directory / "{}-{}.zip".format(plugin_folder_name, number)

        write_text(
            plugin_directory / "README.md",
            plugin_readme(plugin_name, area_name, output_path.name, len(entries)),
        )

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as handle:
            for path in sorted(plugin_directory.rglob("*")):
                if path.is_file():
                    archive_name = Path(plugin_folder_name) / path.relative_to(plugin_directory)
                    handle.write(path, archive_name.as_posix())
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a QGIS boundary-search plugin from zipped shapefiles."
    )
    parser.add_argument("--name", help="Area name, for example Nigeria or Philippines")
    parser.add_argument("--plugin-name", help="Optional full plugin display name")
    parser.add_argument("--icon", type=Path, help="SVG or PNG icon")
    parser.add_argument("--data", type=Path, help="ZIP containing complete shapefile components")
    parser.add_argument("--output", type=Path, help="Output directory")
    parser.add_argument("--author", default=DEFAULT_AUTHOR)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--homepage", default=DEFAULT_HOMEPAGE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    interactive = not (args.name and args.icon and args.data)
    if interactive:
        print("=" * 62)
        print(" QGIS Boundary Search Plugin Builder v{}".format(BUILDER_VERSION))
        print("=" * 62)
        print("Examples: Africa, Nigeria, Philippines")
        print()
        area_name = args.name or prompt_required("Area or country name")
        icon_path = args.icon or choose_file(
            "Choose the plugin icon",
            [("Icon files", "*.svg *.png"), ("SVG", "*.svg"), ("PNG", "*.png")],
        )
        data_zip = args.data or choose_file(
            "Choose the ZIP containing shapefiles", [("ZIP archives", "*.zip")]
        )
    else:
        area_name = args.name
        icon_path = args.icon
        data_zip = args.data

    script_directory = Path(__file__).resolve().parent
    output_directory = (args.output or script_directory / "output").expanduser().resolve()
    assert area_name is not None and icon_path is not None and data_zip is not None
    icon_path = icon_path.expanduser().resolve()
    data_zip = data_zip.expanduser().resolve()

    print()
    print("Building plugin...")
    print("  Name : {}".format(area_name))
    print("  Icon : {}".format(icon_path))
    print("  Data : {}".format(data_zip))
    try:
        output_path = build_plugin(
            area_name=area_name,
            icon_path=icon_path,
            data_zip=data_zip,
            output_directory=output_directory,
            plugin_name=args.plugin_name,
            author=args.author,
            email=args.email,
            homepage=args.homepage,
        )
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print("\nERROR: {}".format(error), file=sys.stderr)
        return 1

    print("\nSUCCESS: {}".format(output_path))
    print("Install it from QGIS: Plugins > Manage and Install Plugins > Install from ZIP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
