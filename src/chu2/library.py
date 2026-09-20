"""The preset library (brief S6): what the page's Presets sheet lists.

    official  "Flat (your CHU 2's own tuning)" and "Your CHU 2 when first seen"
              (the first-seen backup, chu2.store)
    builtin   the Quick Tune scenes (chu2.quicktune), at standard intensity
    measured  the published AutoEq tunings for the Chu 2 (chu2.measured)
    mine      the user's presets: ``%APPDATA%\\CHU2Studio\\presets\\<name>.chu2.json``

User files use the ``chu2.preset`` JSON format plus ``tags`` and a per-band
``bypass``, so ``chu2 preset`` and ``chu2 dsp write`` read them too. A file the
CHU 2 cannot play (a low-pass, more than five bands, a value out of range) is
skipped, not shown. Favourites (any group) are kept in ``favourites.json``.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import threading
from typing import Any, Dict, List, Sequence

from . import dsp, eq, measured, quicktune, transfer
from .store import Store, band_to_dict

logger = logging.getLogger(__name__)

SUFFIX = ".chu2.json"
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class LibraryError(ValueError):
    """A preset that doesn't exist, can't be changed, or has no name."""


def _design(bands: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Five design bands from a file's bands (checked against the CHU 2's limits)."""
    fitted = dsp.kt_fit_bands([eq.FilterBand(str(b["type"]), float(b["frequency"]),
                                             float(b["gain"]), float(b["q"])) for b in bands])
    design = [dict(band_to_dict(band), bypass=False) for band in fitted]
    for i, band in enumerate(bands):
        design[i]["bypass"] = bool(band.get("bypass", False))
    for i in range(len(bands), dsp.KT_BANDS):  # padding: the idle slot, not a 1 kHz band
        design[i] = dict(quicktune.IDLE_DESIGN[i])
    return design


def _slug(name: str) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", name.lower()))[:40] or "preset"


def _when(iso: str) -> str:
    try:
        d = datetime.datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"


class Library:
    def __init__(self, store: Store) -> None:
        self._store = store
        # Page calls arrive on several threads: a save's free-name check and the
        # favourites' read-modify-write must not interleave.
        self._lock = threading.RLock()

    # ---- reading ----------------------------------------------------------------- #
    def presets(self) -> List[Dict[str, Any]]:
        items = [{"id": "official:flat", "name": "Flat (your CHU 2's own tuning)", "group": "official",
                  "tags": ["Official"], "bands": [dict(b) for b in quicktune.IDLE_DESIGN],
                  "about": "All bands at 0 dB: the sound Moondrop tuned, with no EQ on top."}]
        backup = self._store.read_backup()
        if backup is not None:
            items.append({"id": "official:backup", "name": "Your CHU 2 when first seen",
                          "group": "official", "tags": ["Official"],
                          "bands": _design([band_to_dict(b) for b in backup["bands"]]),
                          "about": f"The EQ your CHU 2 had on {_when(backup['saved_at'])}, "
                                   "kept on this PC."})
        for scene in quicktune.SCENES:
            design, _notes = quicktune.compose(scene["id"], [], "standard")
            items.append({"id": f"scene:{scene['id']}", "name": scene["name"], "group": "builtin",
                          "tags": list(scene["tags"]), "bands": design, "about": scene["about"],
                          "gaming": scene["gaming"]})
        items.extend(measured.catalog())
        items.extend(self._mine())
        favourites = set(self._store.load_favourites())
        for item in items:
            item["favourite"] = item["id"] in favourites
            item.setdefault("gaming", False)
        return items

    def find(self, preset_id: str) -> Dict[str, Any]:
        for item in self.presets():
            if item["id"] == preset_id:
                return item
        raise LibraryError(f"There is no preset {preset_id!r}.")

    def _mine(self) -> List[Dict[str, Any]]:
        folder = self._store.presets_dir
        if not os.path.isdir(folder):
            return []
        items = []
        for filename in sorted(os.listdir(folder)):
            if not filename.endswith(SUFFIX):
                continue
            path = os.path.join(folder, filename)
            try:
                with open(path, encoding="utf-8") as handle:
                    data = json.load(handle)
                items.append({"id": "mine:" + filename[: -len(SUFFIX)], "name": str(data["name"]),
                              "group": "mine", "tags": [str(t) for t in data.get("tags", [])],
                              "bands": _design(data["bands"]),
                              "about": str(data.get("description", ""))})
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                logger.warning("skipping preset %s: %s", path, exc)
        return items

    # ---- changing ---------------------------------------------------------------- #
    def save(self, name: str, tags: Sequence[str], design: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        """Save ``design`` as the user's own preset; returns it as listed."""
        name = name.strip()
        if not name:
            raise LibraryError("A preset needs a name.")
        with self._lock:
            os.makedirs(self._store.presets_dir, exist_ok=True)
            slug, n = _slug(name), 1
            while os.path.exists(self._path(slug if n == 1 else f"{slug}-{n}")):
                n += 1
            preset_id = "mine:" + (slug if n == 1 else f"{slug}-{n}")
            self._write(preset_id, transfer.preset_document(name[:60], design, tags))
        return self.find(preset_id)

    def rename(self, preset_id: str, name: str) -> None:
        name = name.strip()
        if not name:
            raise LibraryError("A preset needs a name.")
        with self._lock:
            data = self._read_mine(preset_id)
            data["name"] = name[:60]
            self._write(preset_id, data)

    def delete(self, preset_id: str) -> None:
        with self._lock:
            self._read_mine(preset_id)
            os.remove(self._path(preset_id[len("mine:"):]))
            self.set_favourite(preset_id, False)

    def set_favourite(self, preset_id: str, on: bool) -> None:
        with self._lock:
            favourites = set(self._store.load_favourites())
            if on:
                favourites.add(preset_id)
            else:
                favourites.discard(preset_id)
            self._store.save_favourites(sorted(favourites))

    # ---- files ------------------------------------------------------------------- #
    def _path(self, slug: str) -> str:
        if not slug or slug in (".", "..") or os.path.basename(slug) != slug or "/" in slug:
            raise LibraryError(f"There is no preset {slug!r}.")  # ids come from the page: no paths
        return os.path.join(self._store.presets_dir, slug + SUFFIX)

    def _read_mine(self, preset_id: str) -> Dict[str, Any]:
        if not preset_id.startswith("mine:"):
            raise LibraryError("Only your own presets can be renamed or deleted.")
        try:
            with open(self._path(preset_id[len("mine:"):]), encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError) as exc:
            raise LibraryError(f"There is no preset {preset_id!r}.") from exc

    def _write(self, preset_id: str, data: Dict[str, Any]) -> None:
        path = self._path(preset_id[len("mine:"):])
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
