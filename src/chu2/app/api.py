"""The object pywebview exposes to the page as ``window.pywebview.api`` (spec §4).

It owns the app state: the user's five-band *design*, the *device bands* made
from it by the auto preamp (``chu2.preamp``), what the CHU 2 has *stored*, and
the save flow. It owns no device handle: it calls ``DeviceService`` and hears
back through :meth:`Api._on_device_event` on the device worker thread.

Public methods are called from JavaScript on pywebview's bridge threads; each
takes and returns JSON-friendly values. Methods that change the EQ return the
new state snapshot; library methods (``get_library``, ``save_preset``, ...)
return the library; import and export return a preview or a result.
Changes the device causes are pushed to the page as ``push("state", snapshot)``.
Other pushed events: ``backup_saved {"saved_at"}`` and ``close_requested
{"changes", "connected", "saving"}``. Snapshots carry a growing ``rev`` so the
page can ignore an older one that arrives late.

Rules worth knowing:
- Opening the app never changes the sound: the CHU 2 keeps playing its stored
  EQ until the first edit. From then on it plays what Save would store.
- Methods starting with ``_`` are for ``main.py`` and tests; pywebview does not
  expose them to JavaScript.
"""

from __future__ import annotations

import itertools
import logging
import math
import os
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import (__version__, dsp, eq, keepawake, library, preamp, quicktune, sharecode,
                transfer)
from ..store import THEMES, Store, band_to_dict
from . import autostart

logger = logging.getLogger(__name__)

BAND_TYPES = ("peaking", "low_shelf", "high_shelf")
#: Brief §3.5 idle slots: Bass, Body, Voice, Detail, Air (all 0 dB)
DEFAULT_DESIGN: List[Dict[str, Any]] = quicktune.IDLE_DESIGN
MAX_IMPORT_CHARS = 1_000_000
STORED_NAME = "Your CHU 2's EQ"
_IDLE_SAVE = {"state": "idle", "kind": "save", "step": None, "reason": None,
              "after_commit": False, "mismatched": [], "message": None}
_RECHECK_ON_CONNECT = ("restart_timeout", "verify_unavailable")
_RECHECK_AFTER_UNPLUG = ("no_restart", "commit_unknown")


def clean_band(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a band from the page, clamp it to the CHU 2's limits and round
    it to the steps the device stores (1 Hz, 0.1 dB, Q 0.001)."""
    kind = data.get("type")
    if kind not in BAND_TYPES:
        raise ValueError(f"band type {kind!r} is not one of {BAND_TYPES}")
    values = []
    for key in ("frequency", "gain", "q"):
        value = float(data[key])
        if not math.isfinite(value):
            raise ValueError(f"{key} must be a finite number")
        values.append(value)
    frequency, gain, q = values
    return {
        "type": kind,
        "frequency": float(round(min(max(frequency, dsp.KT_FREQ_MIN_HZ), dsp.KT_FREQ_MAX_HZ))),
        "gain": round(min(max(gain, -dsp.KT_GAIN_LIMIT_DB), dsp.KT_GAIN_LIMIT_DB), 1) + 0.0,
        "q": round(min(max(q, dsp.KT_Q_MIN), dsp.KT_Q_MAX), 3),
        "bypass": bool(data.get("bypass", False)),
    }


def design_band(band: eq.FilterBand) -> Dict[str, Any]:
    return dict(band_to_dict(band), bypass=False)


def effective_band(design: Dict[str, Any]) -> eq.FilterBand:
    """What a design band plays: a bypassed band is written as 0 dB (spec §4.3)."""
    gain = 0.0 if design["bypass"] else design["gain"]
    return eq.FilterBand(design["type"], design["frequency"], gain, design["q"])


def same_band(a: Optional[eq.FilterBand], b: Optional[eq.FilterBand]) -> bool:
    """Equal as the CHU 2 stores them."""
    return a is not None and b is not None and dsp.kt_encode_band(a) == dsp.kt_encode_band(b)


def _open_folder(path: str) -> None:
    starter = getattr(os, "startfile", None)  # Windows Explorer
    if starter is not None:
        starter(path)


class Api:
    def __init__(self, store: Store, push: Callable[[str, Dict[str, Any]], None],
                 close_window: Callable[[], None] = lambda: None, dialogs: Any = None) -> None:
        self._store = store
        self._push = push
        self._close_window = close_window
        self._dialogs = dialogs  # open_file() -> path | None, save_file(name, kind) -> path | None
        self._open_folder: Callable[[str], None] = _open_folder
        self._library = library.Library(store)
        self._name = "My EQ"
        self._quick: Optional[Dict[str, Any]] = None  # the Quick Tune choice behind the design
        self._svc: Any = None
        self._lock = threading.RLock()
        self._rev = 0
        self._settings = store.load_settings()
        if self._settings.get("keep_awake"):
            # The CHU 2 clicks when its amplifier wakes (test #36). Say so either way:
            # a switch that claims to be on while nothing plays is worse than no switch.
            if not keepawake.start() and keepawake.available():
                logger.warning("the clicking switch is on but no silence is playing")
        self._connected = False
        self._device_error: Optional[Dict[str, str]] = None
        self._eq_on = True
        self._design = [dict(b) for b in DEFAULT_DESIGN]
        self._edited = False               # the user changed the design since it was loaded or saved
        self._stored: Optional[List[eq.FilterBand]] = None  # what the CHU 2 has saved
        self._recheck: Optional[str] = None  # None | "on_connect" | "after_unplug"
        self._live: Dict[int, eq.FilterBand] = {}  # what the CHU 2 plays now, per band
        self._save = dict(_IDLE_SAVE)
        self._save_pending = False
        self._restore_bands: Optional[List[eq.FilterBand]] = None
        self._close_after_save = False
        self._allow_close = False
        backup = store.read_backup()
        self._backup = {"saved_at": backup["saved_at"]} if backup else None
        self._result = self._compute()

    # ---- wiring for main.py -------------------------------------------------- #
    def _attach(self, service: Any) -> None:
        self._svc = service

    # ---- called from JavaScript ---------------------------------------------- #
    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return self._snapshot()

    def set_band(self, index: int, band: Dict[str, Any]) -> Dict[str, Any]:
        index = int(index)
        if not 0 <= index < dsp.KT_BANDS:
            raise ValueError(f"band index {index} is outside 0-{dsp.KT_BANDS - 1}")
        clean = clean_band(band)
        with self._lock:
            self._design[index] = clean
            self._quick = None  # a hand edit leaves Quick Tune
            self._edited = True
            self._result = self._compute()
            self._send_live()
            return self._changed()

    def reset_bands(self) -> Dict[str, Any]:
        """All five bands back to the idle slots at 0 dB: the CHU 2's own tuning.
        Played now, not saved (Save stores it)."""
        return self._replace_design(DEFAULT_DESIGN, "Flat")

    def set_design(self, bands: List[Dict[str, Any]], name: Optional[str] = None,
                   quick: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Replace all five bands at once (undo / redo, "Import to editor").

        ``quick`` ({"scene", "tweaks", "intensity"}) is the Quick Tune choice
        behind the bands, which an undo puts back.
        """
        state = None
        if quick is not None:
            if not isinstance(quick, dict):
                raise ValueError("quick must be a Quick Tune choice")
            state = self._quick_choice(quick.get("scene"), quick.get("tweaks") or [],
                                       quick.get("intensity", "standard"))[2]
        return self._replace_design(bands, name, state)

    def apply_preset(self, preset_id: str) -> Dict[str, Any]:
        """Play a preset from the library (not saved until Save)."""
        found = self._library.find(str(preset_id))
        return self._replace_design(found["bands"], found["name"], self._quick_for(found["bands"]))

    def quick_tune(self, scene: Optional[str], tweaks: List[str], intensity: str) -> Dict[str, Any]:
        """Play a Quick Tune choice: a scene, tweaks and an intensity (brief §4)."""
        design, name, quick = self._quick_choice(scene, tweaks, intensity)
        return self._replace_design(design, name, quick)

    @staticmethod
    def _quick_choice(scene: Optional[str], tweaks: List[str],
                      intensity: str) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
        """(design, name, quick state) for a choice; ValueError for an unknown one."""
        tweaks = [str(t) for t in tweaks]
        design, notes = quicktune.compose(scene or None, tweaks, str(intensity))
        names = [s["name"] for s in quicktune.SCENES if s["id"] == scene]
        quick = {"scene": scene or None, "tweaks": tweaks, "intensity": str(intensity), "notes": notes,
                 "text": quicktune.explain(scene or None, tweaks)}
        return design, names[0] if names else "Quick Tune", quick

    # ---- the preset library (brief S6) ---------------------------------------------- #
    def get_library(self) -> Dict[str, Any]:
        """Presets (each with "on_chu2") and the Quick Tune recipes."""
        items = self._library.presets()
        with self._lock:
            stored = self._stored
            auto = bool(self._settings.get("auto_preamp", True))
        for item in items:
            device = preamp.compute([effective_band(b) for b in item["bands"]], auto=auto).bands
            item["on_chu2"] = stored is not None and all(same_band(a, b) for a, b in zip(device, stored))
        return {"presets": items, "recipes": quicktune.recipes()}

    def save_preset(self, name: str, tags: List[str]) -> Dict[str, Any]:
        """Save the current EQ as one of "Mine"; the EQ takes that name."""
        with self._lock:
            design = [dict(b) for b in self._design]
        saved = self._library.save(str(name), [str(t) for t in tags], design)
        with self._lock:
            self._name = saved["name"]
            snapshot = self._changed()
        self._push("state", snapshot)
        return self.get_library()

    def rename_preset(self, preset_id: str, name: str) -> Dict[str, Any]:
        self._library.rename(str(preset_id), str(name))
        return self.get_library()

    def delete_preset(self, preset_id: str) -> Dict[str, Any]:
        self._library.delete(str(preset_id))
        return self.get_library()

    def set_favourite(self, preset_id: str, on: bool) -> Dict[str, Any]:
        self._library.set_favourite(str(preset_id), bool(on))
        return self.get_library()

    # ---- import, export, share (brief S7) --------------------------------------------- #
    def import_file(self) -> Dict[str, Any]:
        """Open dialog -> a preview (nothing changes until "Import to editor")."""
        if self._dialogs is None:
            return {"error": "Opening files isn't available here."}
        path = self._dialogs.open_file()
        if not path:
            return {"cancelled": True}
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                return transfer.read_text(handle.read(MAX_IMPORT_CHARS), path)
        except (OSError, transfer.TransferError) as exc:
            return {"error": str(exc)}

    def import_text(self, text: str, name: str = "") -> Dict[str, Any]:
        """A preview of pasted text, or of a file dropped on the window (``name``)."""
        try:
            return transfer.read_text(str(text)[:MAX_IMPORT_CHARS], str(name))
        except transfer.TransferError as exc:
            return {"error": str(exc)}

    def share_code(self) -> Dict[str, Any]:
        """The current EQ as a share code and as plain text (bypassed bands as 0 dB)."""
        with self._lock:
            name = self._name
            bands = [effective_band(b) for b in self._design]
        return {"code": sharecode.encode(name, bands), "text": sharecode.describe(bands)}

    def export_file(self, fmt: str) -> Dict[str, Any]:
        """Save dialog -> an Equalizer APO / AutoEq .txt ("apo") or a .chu2.json ("json")."""
        if fmt not in ("apo", "json"):
            raise ValueError(f"unknown export format {fmt!r}")
        if self._dialogs is None:
            return {"error": "Saving files isn't available here."}
        with self._lock:
            name, design, preamp_db = self._name, [dict(b) for b in self._design], self._result.preamp_db
        if fmt == "apo":
            filename, text = sharecode.safe_name(name) + ".txt", transfer.export_apo(name, design, preamp_db)
        else:
            filename, text = sharecode.safe_name(name) + ".chu2.json", transfer.export_json(name, design)
        path = self._dialogs.save_file(filename, fmt)
        if not path:
            return {"cancelled": True}
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        except OSError as exc:
            return {"error": f"Couldn't save the file: {exc}"}
        return {"saved": path}

    # ---- settings (brief S10) ---------------------------------------------------------- #
    def set_setting(self, key: str, value: Any) -> Dict[str, Any]:
        """``theme`` (one of THEMES), or ``confirm_save``, ``keep_awake`` and
        ``start_with_windows`` (bool)."""
        if key == "theme":
            if value not in THEMES:
                raise ValueError(f"unknown theme {value!r}")
        elif key == "confirm_save":
            value = bool(value)
        elif key == "keep_awake":
            value = bool(value)
            # Stores what the user asked for even if the silence refuses to play, so the
            # switch stays where they put it; `keep_awake_running` reports the truth.
            keepawake.start() if value else keepawake.stop()
        elif key == "start_with_windows":
            # Not stored: Windows' own Run key *is* the state, so removing the entry by
            # hand cannot leave the switch lying.
            autostart.enable() if value else autostart.disable()
            with self._lock:
                return self._changed()
        else:
            raise ValueError(f"unknown setting {key!r}")
        with self._lock:
            self._settings[key] = value
            self._store.save_settings(self._settings)
            return self._changed()

    def open_data_folder(self) -> Dict[str, Any]:
        """Show %APPDATA%\\CHU2Studio (backup, presets, settings, log) in Explorer."""
        os.makedirs(self._store.root, exist_ok=True)
        self._open_folder(self._store.root)
        return {"folder": self._store.root}

    def set_eq_enabled(self, on: bool) -> Dict[str, Any]:
        with self._lock:
            if self._connected and self._svc is not None:
                self._svc.set_eq_enabled(bool(on))  # the state follows the device's answer
            return self._snapshot()

    def set_auto_preamp(self, on: bool) -> Dict[str, Any]:
        with self._lock:
            self._settings["auto_preamp"] = bool(on)
            self._store.save_settings(self._settings)
            self._edited = True
            self._result = self._compute()
            self._send_live()
            return self._changed()

    def free_smallest_band(self) -> Dict[str, Any]:
        """Reset the band with the smallest non-zero gain, so the preamp can use it."""
        with self._lock:
            used = [i for i, b in enumerate(self._design) if b["gain"] != 0]
            if not used:
                return self._snapshot()
            smallest = min(used, key=lambda i: abs(self._design[i]["gain"]))
            band = dict(self._design[smallest], gain=0.0)
        return self.set_band(smallest, band)

    def save(self) -> Dict[str, Any]:
        with self._lock:
            if self._save["state"] != "running":
                self._start_save("save")
            return self._changed()

    def cancel_save(self) -> Dict[str, Any]:
        """Cancel a save that waits for the CHU 2 to be plugged in."""
        with self._lock:
            if self._save["state"] == "waiting_device":
                self._save_pending = False
                self._close_after_save = False  # "Save & close" was cancelled too
                self._save = dict(_IDLE_SAVE)
            return self._changed()

    def dismiss_save(self) -> Dict[str, Any]:
        """Close the save result (done or failed)."""
        with self._lock:
            if self._save["state"] in ("done", "failed"):
                self._save = dict(_IDLE_SAVE)
            return self._changed()

    def restore_original(self) -> Dict[str, Any]:
        """Save the first-seen backup back to the CHU 2, exactly as it was."""
        backup = self._store.read_backup()
        if backup is None:
            raise ValueError("There is no backup on this PC yet.")
        with self._lock:
            if self._save["state"] != "running":
                self._design = [design_band(b) for b in backup["bands"]]
                self._name = "Your CHU 2 when first seen"
                self._quick = None
                self._edited = True
                self._restore_bands = list(backup["bands"])
                self._result = self._compute()
                self._start_save("restore")
            return self._changed()

    def close_app(self, action: str) -> Dict[str, Any]:
        """Answer to ``close_requested``: "discard" or "save" (then close)."""
        with self._lock:
            if action == "save":
                self._close_after_save = True
                if self._save["state"] != "running":
                    self._start_save("save")
                return self._changed()
            if action != "discard":
                raise ValueError(f"unknown close action {action!r}")
            self._save_pending = False  # a save waiting for the CHU 2 must never run now
            self._close_after_save = False
            if self._save["state"] == "waiting_device":
                self._save = dict(_IDLE_SAVE)
            if self._connected and self._svc is not None and self._stored is not None:
                for i, band in enumerate(self._stored):  # the CHU 2 keeps its old EQ
                    if not same_band(self._live.get(i), band):
                        self._svc.set_band_live(i, band)
                        self._live[i] = band
            self._allow_close = True
            snapshot = self._snapshot()
        self._close_window()
        return snapshot

    # ---- window events (main.py) --------------------------------------------- #
    def _on_window_closing(self) -> bool:
        """pywebview ``closing`` handler (GUI thread): False keeps the window open."""
        with self._lock:
            if self._allow_close:
                return True
            saving = self._save["state"] == "running"
            changes = self._changes()
            if not saving and not (self._edited and changes):
                return True
            info = {"changes": changes, "connected": self._connected, "saving": saving}
        self._push("close_requested", info)
        return False

    def _shutdown(self) -> None:
        """After the window closed: switch the EQ back on and stop the worker."""
        with self._lock:
            svc = self._svc
            self._save_pending = False  # nothing may be saved once the window is gone
            if svc is not None and self._connected and not self._eq_on:
                svc.set_eq_enabled(True)
        if svc is not None:
            svc.stop()

    # ---- device events (worker thread) ----------------------------------------- #
    def _on_device_event(self, name: str, data: Dict[str, Any]) -> None:
        after: List[Callable[[], None]] = []
        with self._lock:
            handler = getattr(self, "_ev_" + name, None)
            if handler is None or handler(data, after) is False:
                return
            snapshot = self._changed()
        self._push("state", snapshot)
        for action in after:
            action()

    def _ev_connected(self, data: Dict[str, Any], after: List[Callable[[], None]]) -> None:
        slot, bands = data["slot"], list(data["bands"])
        logger.info("CHU 2 connected (EQ slot 0x%02X)", slot)
        self._connected = True
        self._device_error = None
        self._eq_on = slot != dsp.KT_SLOT_OFF
        self._live = dict(enumerate(bands))
        if self._stored is None or self._recheck == "on_connect":
            self._stored = list(bands)
            self._recheck = None
        if self._backup is None:
            try:
                backup = self._store.read_backup() if self._store.write_backup_once(slot, bands) else None
            except OSError:
                logger.exception("could not write the first-seen backup")
                backup = None
            if backup is not None:
                self._backup = {"saved_at": backup["saved_at"]}
                info = dict(self._backup)
                after.append(lambda: self._push("backup_saved", info))
        if self._edited:
            self._result = self._compute()
            self._send_live()  # edits made without the CHU 2 are heard now
        else:
            self._design, self._name = self._design_for(bands)
            self._quick = self._quick_for(self._design)
            self._result = self._compute()
        if self._save_pending:
            self._save_pending = False
            self._start_save(self._save["kind"])

    def _ev_disconnected(self, data: Dict[str, Any], after: List[Callable[[], None]]) -> None:
        logger.info("CHU 2 disconnected (%s)", data.get("reason", "unknown"))
        self._connected = False
        self._live = {}
        if data.get("reason") == "unplugged" and self._recheck == "after_unplug":
            self._recheck = "on_connect"

    def _ev_error(self, data: Dict[str, Any], after: List[Callable[[], None]]) -> Optional[bool]:
        error = {"code": str(data.get("code", "open_failed")), "message": str(data.get("message", ""))}
        if error == self._device_error:
            return False  # the same error every second: nothing new to show
        self._device_error = error
        return None

    def _ev_eq_enabled(self, data: Dict[str, Any], after: List[Callable[[], None]]) -> None:
        self._eq_on = bool(data["on"])

    def _ev_save_progress(self, data: Dict[str, Any], after: List[Callable[[], None]]) -> None:
        self._save = dict(self._save, state="running", step=data["step"])

    def _ev_saved(self, data: Dict[str, Any], after: List[Callable[[], None]]) -> None:
        bands = list(data["bands"])
        self._stored = bands
        self._recheck = None
        self._live = dict(enumerate(bands))
        self._eq_on = data.get("slot", dsp.KT_SLOT_ON) != dsp.KT_SLOT_OFF
        kind = self._save["kind"]
        logger.info("%s done and checked", kind)
        self._save = dict(_IDLE_SAVE, state="done", kind=kind, after_commit=True)
        self._edited = False
        if kind == "restore":
            self._restore_bands = None
            self._design = [design_band(b) for b in bands]
            self._result = self._compute()
        else:
            try:
                self._store.write_last_saved(self._design, bands, self._name)
            except OSError:
                logger.exception("could not remember the saved design")
        if self._close_after_save:
            self._close_after_save = False
            self._allow_close = True
            after.append(self._close_window)

    def _ev_save_failed(self, data: Dict[str, Any], after: List[Callable[[], None]]) -> None:
        reason = data["reason"]
        logger.warning("%s failed: %s", self._save["kind"], reason)
        self._save = dict(_IDLE_SAVE, state="failed", kind=self._save["kind"], reason=reason,
                          after_commit=bool(data.get("after_commit")),
                          mismatched=list(data.get("mismatched", [])),
                          message=data.get("message"))
        self._close_after_save = False
        if reason == "verify_mismatch":
            self._stored = list(data["bands"])
            self._live = dict(enumerate(self._stored))
        elif reason in _RECHECK_ON_CONNECT:
            self._connected = False
            self._recheck = "on_connect"
        elif reason in _RECHECK_AFTER_UNPLUG:
            self._connected = False
            self._recheck = "after_unplug"

    # ---- helpers (call with the lock held) ------------------------------------ #
    def _compute(self) -> preamp.PreampResult:
        bands = [effective_band(b) for b in self._design]
        result = preamp.compute(bands, auto=bool(self._settings.get("auto_preamp", True)))
        if not self._edited and self._stored is not None \
                and not all(same_band(a, b) for a, b in zip(result.bands, self._stored)):
            # The CHU 2's EQ was stored without this preamp (another app, Restore original):
            # show it as it is, so Save has nothing to store until the first edit.
            result = preamp.compute(bands, auto=False)
            result.warning = "stored_without_preamp"
        return result

    def _send_live(self) -> None:
        """Play the device bands that differ from what the CHU 2 plays now."""
        if not self._connected or self._svc is None or self._save["state"] == "running":
            return
        for i, band in enumerate(self._result.bands):
            if not same_band(self._live.get(i), band):
                self._svc.set_band_live(i, band)
                self._live[i] = band

    def _start_save(self, kind: str) -> None:
        if not self._connected or self._svc is None:
            self._save = dict(_IDLE_SAVE, state="waiting_device", kind=kind)
            self._save_pending = True
            return
        self._save = dict(_IDLE_SAVE, state="running", kind=kind)
        if kind == "restore" and self._restore_bands is not None:
            self._svc.save(self._restore_bands)
        else:
            self._svc.save(self._result.bands)

    def _design_for(self, bands: List[eq.FilterBand]) -> Tuple[List[Dict[str, Any]], str]:
        """(design, name) behind ``bands``: the last saved design if it produced them."""
        last = self._store.read_last_saved()
        if last is not None and len(last["device"]) == len(bands) == len(last["design"]) \
                and all(same_band(a, b) for a, b in zip(last["device"], bands)):
            try:
                return [clean_band(b) for b in last["design"]], last["name"] or STORED_NAME
            except (KeyError, TypeError, ValueError):
                logger.warning("ignoring an unreadable last saved design")
        return [design_band(b) for b in bands], STORED_NAME

    def _quick_for(self, design: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """The Quick Tune choice that composes ``design`` (fewest tweaks, then Standard
        first), so Quick Tune shows it again after a restart or a library Apply."""
        if any(b.get("bypass") for b in design):
            return None
        target = [effective_band(b) for b in design]
        tweak_ids = [t["id"] for t in quicktune.TWEAKS]
        scenes = [s["id"] for s in quicktune.SCENES] + [None]
        # ponytail: brute force over the recipes (about 5 ms); index them if recipes grow a lot
        for count in range(len(tweak_ids) + 1):
            for tweaks in itertools.combinations(tweak_ids, count):
                for scene in scenes:
                    if scene is None and not tweaks:
                        continue  # nothing chosen is not a Quick Tune choice
                    for intensity in ("standard", "subtle", "strong"):
                        try:
                            composed, _name, quick = self._quick_choice(scene, list(tweaks), intensity)
                        except ValueError:
                            break  # two tweaks that share a band
                        if all(same_band(effective_band(a), b) for a, b in zip(composed, target)):
                            return quick
        return None

    def _replace_design(self, bands: List[Dict[str, Any]], name: Optional[str],
                        quick: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """All five bands at once, played now (not saved)."""
        if len(bands) != dsp.KT_BANDS:
            raise ValueError(f"expected {dsp.KT_BANDS} bands, got {len(bands)}")
        clean = [clean_band(b) for b in bands]
        with self._lock:
            self._design = clean
            if name:
                self._name = str(name)[:60]
            self._quick = quick
            self._edited = True
            self._result = self._compute()
            self._send_live()
            return self._changed()

    def _changes(self) -> int:
        """Bands where what Save would store differs from what the CHU 2 has."""
        if self._stored is not None:
            base = self._stored
        else:
            base = [effective_band(b) for b in DEFAULT_DESIGN]
        return sum(1 for a, b in zip(self._result.bands, base) if not same_band(a, b))

    def _changed(self) -> Dict[str, Any]:
        self._rev += 1
        return self._snapshot()

    def _snapshot(self) -> Dict[str, Any]:
        return {
            "rev": self._rev,
            "connected": self._connected,
            "device_error": dict(self._device_error) if self._device_error else None,
            "eq_on": self._eq_on,
            "design": [dict(b) for b in self._design],
            "device_bands": [band_to_dict(b) for b in self._result.bands],
            "stored": [band_to_dict(b) for b in self._stored] if self._stored is not None else None,
            "changes": self._changes(),
            "edited": self._edited,
            "auto_preamp": bool(self._settings.get("auto_preamp", True)),
            "settings": {"theme": self._settings.get("theme", "atelier"),
                         "confirm_save": bool(self._settings.get("confirm_save", True)),
                         "keep_awake": bool(self._settings.get("keep_awake", False)),
                         "keep_awake_ok": keepawake.available(),
                         "keep_awake_running": keepawake.running(),
                         "start_with_windows": autostart.enabled(),
                         "start_with_windows_ok": autostart.available()},
            "name": self._name,
            "quick": dict(self._quick) if self._quick else None,
            "version": __version__,
            "preamp": self._result.to_dict(),
            "save": dict(self._save, mismatched=list(self._save["mismatched"])),
            "backup": dict(self._backup) if self._backup else None,
        }
