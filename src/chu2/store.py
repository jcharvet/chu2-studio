"""The app's files in ``%APPDATA%\\CHU2Studio\\`` (spec §4.3).

    backup.json      the EQ the CHU 2 had when this PC first saw it. Written
                     once, never overwritten (lesson from the APO backup bug).
    settings.json    app settings, e.g. {"auto_preamp": true}
    last_saved.json  the design behind the last save, so the editor can show
                     "Low shelf +6" again instead of its stored form "High shelf -6"
    favourites.json  the ids of favourite presets
    presets\\         the user's own presets (``<name>.chu2.json``, see chu2.library)

Nothing is written next to the program. Set ``CHU2STUDIO_HOME`` to use another
folder (tests do).
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from typing import Any, Dict, List, Optional, Sequence

from . import eq

APP_DIR_ENV = "CHU2STUDIO_HOME"
THEMES = ("atelier", "mocha", "sage", "latte", "porcelain")
DEFAULT_SETTINGS: Dict[str, Any] = {"auto_preamp": True, "theme": "atelier", "confirm_save": True}

logger = logging.getLogger(__name__)


def default_root() -> str:
    override = os.environ.get(APP_DIR_ENV)
    if override:
        return override
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "CHU2Studio")


def band_to_dict(band: eq.FilterBand) -> Dict[str, Any]:
    return {"type": band.type, "frequency": band.frequency, "gain": band.gain, "q": band.q}


def band_from_dict(data: Dict[str, Any]) -> eq.FilterBand:
    return eq.FilterBand(str(data["type"]), float(data["frequency"]),
                         float(data["gain"]), float(data["q"]))


class Store:
    def __init__(self, root: Optional[str] = None) -> None:
        self.root = root or default_root()
        self.backup_path = os.path.join(self.root, "backup.json")
        self.settings_path = os.path.join(self.root, "settings.json")
        self.last_saved_path = os.path.join(self.root, "last_saved.json")
        self.favourites_path = os.path.join(self.root, "favourites.json")
        self.presets_dir = os.path.join(self.root, "presets")

    # ---- first-seen backup -------------------------------------------------- #
    def read_backup(self) -> Optional[Dict[str, Any]]:
        """``{"saved_at": str, "slot": int, "bands": [FilterBand x 5]}`` or None."""
        data = self._read_json(self.backup_path)
        if data is None:
            return None
        try:
            return {"saved_at": str(data["saved_at"]), "slot": int(data["slot"]),
                    "bands": [band_from_dict(b) for b in data["bands"]]}
        except (KeyError, TypeError, ValueError):
            logger.warning("ignoring unreadable backup %s", self.backup_path)
            return None

    def write_backup_once(self, slot: int, bands: Sequence[eq.FilterBand],
                          now: Optional[datetime.datetime] = None) -> bool:
        """Write the backup if there is none yet. True if written, False if one exists."""
        os.makedirs(self.root, exist_ok=True)
        stamp = (now or datetime.datetime.now()).isoformat(timespec="seconds")
        text = json.dumps({"version": 1, "saved_at": stamp, "slot": slot,
                           "bands": [band_to_dict(b) for b in bands]}, indent=2)
        try:
            with open(self.backup_path, "x", encoding="utf-8") as handle:  # never overwrite
                handle.write(text + "\n")
        except FileExistsError:
            return False
        return True

    # ---- settings ---------------------------------------------------------- #
    def load_settings(self) -> Dict[str, Any]:
        settings = dict(DEFAULT_SETTINGS)
        data = self._read_json(self.settings_path)
        if isinstance(data, dict):
            settings.update(data)
        return settings

    def save_settings(self, settings: Dict[str, Any]) -> None:
        self._write_json(self.settings_path, settings)

    # ---- the design behind the last save ------------------------------------ #
    def read_last_saved(self) -> Optional[Dict[str, Any]]:
        """``{"design": [band dict with "bypass"] x 5, "device": [FilterBand x 5], "name": str}``
        or None."""
        data = self._read_json(self.last_saved_path)
        if data is None:
            return None
        try:
            return {"design": [dict(b) for b in data["design"]],
                    "device": [band_from_dict(b) for b in data["device"]],
                    "name": str(data.get("name", ""))}
        except (KeyError, TypeError, ValueError):
            logger.warning("ignoring unreadable %s", self.last_saved_path)
            return None

    def write_last_saved(self, design: Sequence[Dict[str, Any]],
                         device: Sequence[eq.FilterBand], name: str = "") -> None:
        self._write_json(self.last_saved_path, {"design": [dict(b) for b in design],
                                                "device": [band_to_dict(b) for b in device],
                                                "name": name})

    # ---- favourite presets ------------------------------------------------------ #
    def load_favourites(self) -> List[str]:
        data = self._read_json(self.favourites_path)
        return [str(x) for x in data] if isinstance(data, list) else []

    def save_favourites(self, ids: Sequence[str]) -> None:
        self._write_json(self.favourites_path, sorted(set(ids)))

    # ---- files --------------------------------------------------------------- #
    def _read_json(self, path: str) -> Any:
        try:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            logger.warning("ignoring unreadable %s", path)
            return None

    def _write_json(self, path: str, data: Any) -> None:
        os.makedirs(self.root, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.replace(tmp, path)  # a crash never leaves half a file behind
