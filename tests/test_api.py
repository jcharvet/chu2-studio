"""The window's Api against DeviceService + a fake CHU 2 (no window, no thread).

    python -m pytest -q tests/test_api.py
"""

import json
import logging
import threading
import time

from chu2 import dsp, eq, quicktune
from chu2.app.api import DEFAULT_DESIGN, Api
from chu2.device_service import DeviceService
from chu2.fake_device import FakePlug
from chu2.store import Store

BASS_UP = {"type": "low_shelf", "frequency": 100, "gain": 6, "q": 0.7}
LOW_CUT = {"type": "peaking", "frequency": 40, "gain": -3, "q": 0.5}


class Rig:
    """Api + DeviceService + FakePlug + Store in a temp folder; tick() = one second."""

    def __init__(self, tmp_path, present=True, store=None, plug=None):
        self.plug = plug or FakePlug(present=present)
        self.fake = self.plug.device
        self.store = store or Store(str(tmp_path / "app"))
        self.pushed = []
        self.closed = 0
        self.api = Api(self.store, lambda name, data: self.pushed.append((name, data)),
                       close_window=self._close)
        self.svc = DeviceService(self.plug.open, self.plug.is_present, self.api._on_device_event,
                                 sleep=lambda s: None, restart_timeout_s=0.5)
        self.api._attach(self.svc)
        self.t = 0.0

    def _close(self):
        self.closed += 1

    def tick(self):
        self.t += 1.0
        self.svc.run_once(now=self.t)

    def state(self):
        return self.api.get_state()

    def pushed_named(self, name):
        return [data for n, data in self.pushed if n == name]


def _band_regs(fake, index):
    reg = dsp.KT_REG_BAND0 + 2 * index
    return fake.live[reg], fake.live[reg + 1]


def test_starts_with_the_default_design_and_nothing_to_save(tmp_path):
    s = Rig(tmp_path, present=False).state()
    assert s["connected"] is False and s["design"] == DEFAULT_DESIGN
    assert s["changes"] == 0 and s["save"]["state"] == "idle" and s["auto_preamp"] is True
    json.dumps(s)  # JSON-friendly


def test_connect_loads_the_eq_and_writes_the_first_seen_backup(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()
    s = rig.state()
    assert s["connected"] and s["eq_on"] and s["changes"] == 0
    assert s["design"][1] == {"type": "peaking", "frequency": 200.0, "gain": -6.0, "q": 0.6,
                              "bypass": False}
    assert len(rig.pushed_named("backup_saved")) == 1 and s["backup"] is not None
    assert rig.store.read_backup()["bands"][1] == eq.FilterBand("peaking", 200.0, -6.0, 0.6)
    again = Rig(tmp_path, store=rig.store)  # a later session on the same PC
    again.tick()
    assert again.pushed_named("backup_saved") == []


def test_an_edit_plays_only_the_changed_band(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()
    s = rig.api.set_band(0, LOW_CUT)
    assert s["changes"] == 1 and s["edited"]
    rig.tick()
    assert [reg for reg, _ in rig.fake.writes] == [0x26, 0x27] and rig.fake.commits == 0


def test_set_band_clamps_and_rounds_to_device_steps(tmp_path):
    rig = Rig(tmp_path, present=False)
    s = rig.api.set_band(2, {"type": "peaking", "frequency": 25000.4, "gain": 13.26, "q": 0.01})
    assert s["design"][2] == {"type": "peaking", "frequency": 20000.0, "gain": 12.0, "q": 0.1,
                              "bypass": False}
    for bad in ({"type": "lowpass", "frequency": 100, "gain": 0, "q": 1},
                {"type": "peaking", "frequency": float("nan"), "gain": 0, "q": 1}):
        try:
            rig.api.set_band(0, bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")


def test_a_bypassed_band_plays_flat(tmp_path):
    rig = Rig(tmp_path, present=False)
    s = rig.api.set_band(1, dict(LOW_CUT, bypass=True))
    assert s["design"][1]["gain"] == -3.0 and s["device_bands"][1]["gain"] == 0.0


def test_auto_preamp_flips_a_bass_boost(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()
    s = rig.api.set_band(1, BASS_UP)
    assert s["design"][1]["type"] == "low_shelf"
    assert s["device_bands"][1] == {"type": "high_shelf", "frequency": 100.0, "gain": -6.0, "q": 0.7}
    assert s["preamp"]["method"] == "flip" and s["preamp"]["preamp_db"] == -6.0
    rig.tick()
    assert _band_regs(rig.fake, 1) == dsp.kt_encode_band(eq.FilterBand("high_shelf", 100.0, -6.0, 0.7))


def test_auto_preamp_off_is_remembered_and_plays_the_design(tmp_path):
    rig = Rig(tmp_path, present=False)
    rig.api.set_band(1, BASS_UP)
    s = rig.api.set_auto_preamp(False)
    assert s["auto_preamp"] is False and s["device_bands"][1]["type"] == "low_shelf"
    assert rig.store.load_settings()["auto_preamp"] is False


def _warm_bass_plug():
    plug = FakePlug()
    for dev_regs in (plug.device.live, plug.device.saved):  # the owner's Warm Bass
        dev_regs[0x28], dev_regs[0x29] = dsp.kt_encode_band(eq.FilterBand("low_shelf", 100.0, 6.0, 0.7))
    return plug


def test_opening_the_app_never_changes_the_sound(tmp_path):
    rig = Rig(tmp_path, plug=_warm_bass_plug())
    rig.tick()
    rig.tick()
    s = rig.state()
    assert rig.fake.writes == [] and s["edited"] is False
    # an EQ stored without a preamp is shown as it is: nothing to save until an edit
    assert s["changes"] == 0 and s["device_bands"][1]["type"] == "low_shelf"
    assert s["preamp"]["preamp_db"] == 0.0 and s["preamp"]["warning"] == "stored_without_preamp"
    s = rig.api.set_band(0, LOW_CUT)  # the first edit adds the preamp
    assert s["preamp"]["preamp_db"] == -6.0 and s["changes"] == 2


def test_restore_original_leaves_nothing_to_save(tmp_path):
    rig = Rig(tmp_path, plug=_warm_bass_plug())
    rig.tick()
    rig.api.set_band(4, LOW_CUT)
    rig.api.save()
    rig.tick()
    rig.api.restore_original()
    rig.tick()
    s = rig.state()
    assert s["save"]["state"] == "done" and s["changes"] == 0
    assert s["device_bands"][1]["type"] == "low_shelf"  # Save would store the original as it is


def test_save_runs_to_done_and_remembers_the_design(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()
    rig.api.set_band(1, BASS_UP)
    assert rig.api.save()["save"]["state"] == "running"
    rig.tick()
    steps = [d["save"]["step"] for d in rig.pushed_named("state") if d["save"]["state"] == "running"]
    assert steps == ["writing", "committing", "restarting", "verifying"]
    s = rig.state()
    assert s["save"]["state"] == "done" and s["changes"] == 0 and not s["edited"]
    assert rig.fake.commits == 1
    assert rig.store.read_last_saved()["design"][1]["type"] == "low_shelf"


def test_the_saved_design_comes_back_next_session(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()
    rig.api.set_band(1, BASS_UP)
    rig.api.save()
    rig.tick()
    later = Rig(tmp_path, store=rig.store, plug=rig.plug)
    later.tick()
    s = later.state()
    assert s["design"][1]["type"] == "low_shelf" and s["design"][1]["gain"] == 6.0
    assert s["changes"] == 0


def test_save_while_unplugged_waits_for_the_device(tmp_path):
    rig = Rig(tmp_path, present=False)
    rig.api.set_band(0, LOW_CUT)
    assert rig.api.save()["save"]["state"] == "waiting_device"
    rig.tick()
    assert rig.fake.commits == 0
    rig.plug.present = True
    rig.tick()
    s = rig.state()
    assert s["save"]["state"] == "done" and rig.fake.commits == 1
    assert s["design"][0]["gain"] == -3.0  # the edit made without the CHU 2 was kept


def test_a_waiting_save_can_be_cancelled(tmp_path):
    rig = Rig(tmp_path, present=False)
    rig.api.set_band(0, LOW_CUT)
    rig.api.save()
    assert rig.api.cancel_save()["save"]["state"] == "idle"
    rig.plug.present = True
    rig.tick()
    assert rig.fake.commits == 0


def test_eq_off_then_save_reports_eq_on_again(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()
    rig.api.set_eq_enabled(False)
    rig.tick()
    assert rig.state()["eq_on"] is False
    rig.api.set_band(0, LOW_CUT)
    rig.api.save()
    rig.tick()
    assert rig.state()["eq_on"] is True


def test_write_mismatch_lists_bands_and_keeps_the_connection(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()
    rig.fake.ignore_writes_to = {0x28}
    rig.api.set_band(1, LOW_CUT)
    rig.api.save()
    rig.tick()
    save = rig.state()["save"]
    assert save["state"] == "failed" and save["reason"] == "write_mismatch"
    assert save["mismatched"] == [1] and not save["after_commit"]
    assert rig.state()["connected"] and rig.fake.commits == 0


def test_restart_timeout_rechecks_the_device_on_reconnect(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()
    rig.api.set_band(0, LOW_CUT)
    rig.fake.on_commit = lambda: setattr(rig.plug, "present", False)
    rig.api.save()
    rig.tick()
    s = rig.state()
    assert s["save"]["reason"] == "restart_timeout" and s["save"]["after_commit"]
    assert s["connected"] is False and s["changes"] == 1
    rig.plug.present = True
    rig.tick()
    assert rig.state()["changes"] == 0  # the commit did happen: the recheck shows it


def test_no_restart_waits_for_a_replug_before_trusting_a_read(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()
    rig.api.set_band(0, LOW_CUT)
    rig.fake.restarts_on_commit = False
    rig.api.save()
    rig.tick()
    assert rig.state()["save"]["reason"] == "no_restart"
    rig.tick()  # reconnects at once; its live registers prove nothing
    assert rig.state()["connected"] and rig.state()["changes"] == 1
    rig.plug.present = False
    rig.tick()
    rig.plug.present = True
    rig.tick()
    assert rig.state()["changes"] == 0


def test_restore_original_saves_the_backup_exactly(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()
    first = dict(rig.fake.saved)
    rig.api.set_band(1, BASS_UP)
    rig.api.save()
    rig.tick()
    assert rig.fake.saved != first
    s = rig.api.restore_original()
    assert s["save"]["kind"] == "restore" and s["save"]["state"] == "running"
    rig.tick()
    assert rig.fake.saved == first and rig.state()["save"]["state"] == "done"
    assert rig.state()["design"][1]["gain"] == -6.0


def test_connect_save_and_unplug_are_logged(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="chu2.app.api")
    rig = Rig(tmp_path)
    rig.tick()
    rig.api.set_band(0, LOW_CUT)
    rig.api.save()
    rig.tick()
    rig.plug.present = False
    rig.tick()
    assert [r.getMessage() for r in caplog.records] == [
        "CHU 2 connected (EQ slot 0x03)", "save done and checked", "CHU 2 disconnected (unplugged)"]


def test_restore_without_a_backup_is_refused(tmp_path):
    rig = Rig(tmp_path, present=False)
    try:
        rig.api.restore_original()
    except ValueError:
        return
    raise AssertionError("restored without a backup")


def test_closing_without_edits_is_allowed(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()
    assert rig.api._on_window_closing() is True and rig.pushed_named("close_requested") == []


def test_closing_with_edits_asks_and_discard_puts_the_old_eq_back(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()
    before = _band_regs(rig.fake, 0)
    rig.api.set_band(0, LOW_CUT)
    rig.tick()
    assert rig.api._on_window_closing() is False
    assert rig.pushed_named("close_requested") == [{"changes": 1, "connected": True, "saving": False}]
    rig.api.close_app("discard")
    assert rig.closed == 1 and rig.api._on_window_closing() is True
    rig.tick()
    assert _band_regs(rig.fake, 0) == before


def test_save_and_close(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()
    rig.api.set_band(0, LOW_CUT)
    rig.api.close_app("save")
    assert rig.closed == 0
    rig.tick()
    assert rig.closed == 1 and rig.fake.commits == 1


def test_free_smallest_band_makes_room_for_the_preamp(tmp_path):
    rig = Rig(tmp_path, present=False)
    for i, (freq, gain) in enumerate(((100, 2), (300, 3), (1000, 1), (3000, 4), (8000, 5))):
        s = rig.api.set_band(i, {"type": "peaking", "frequency": freq, "gain": gain, "q": 1})
    assert s["preamp"]["warning"] == "no_free_band"
    s = rig.api.free_smallest_band()
    assert s["design"][2]["gain"] == 0.0 and s["preamp"]["trim_index"] == 2
    assert s["preamp"]["warning"] is None


def test_shutdown_switches_the_eq_back_on(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()
    rig.api.set_eq_enabled(False)
    rig.tick()
    rig.api._shutdown()
    assert rig.fake.live[0x24][0] == dsp.KT_SLOT_ON and rig.fake.closed


def test_an_unknown_filter_type_is_shown_once(tmp_path):
    rig = Rig(tmp_path)
    rig.fake.live[0x27] = bytes.fromhex("f4010900")
    rig.tick()
    rig.tick()
    assert rig.state()["device_error"]["code"] == "unknown_filter_type"
    assert len(rig.pushed_named("state")) == 1


def test_revisions_only_grow(tmp_path):
    rig = Rig(tmp_path)
    revs = [rig.state()["rev"]]
    rig.tick()
    revs.append(rig.state()["rev"])
    revs.append(rig.api.set_band(0, LOW_CUT)["rev"])
    assert revs == sorted(set(revs))


def test_bridge_threads_and_the_worker_can_run_at_once(tmp_path):
    plug = FakePlug()
    store = Store(str(tmp_path / "app"))
    api = Api(store, lambda name, data: None)
    svc = DeviceService(plug.open, plug.is_present, api._on_device_event, poll_s=0.05)
    api._attach(svc)
    svc.start()
    deadline = time.monotonic() + 2
    while not api.get_state()["connected"] and time.monotonic() < deadline:
        time.sleep(0.01)

    def drag(index):
        for step in range(40):
            api.set_band(index, {"type": "peaking", "frequency": 200 + step, "gain": -step / 10,
                                 "q": 1.0})

    threads = [threading.Thread(target=drag, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    svc.stop()  # sends the last live edits
    final = api.get_state()["device_bands"]
    for i in range(4):
        band = eq.FilterBand(**final[i])
        assert (plug.device.live[0x26 + 2 * i], plug.device.live[0x27 + 2 * i]) == dsp.kt_encode_band(band)


# ---- whole-branch review fixes ------------------------------------------- #
def test_cancelling_a_waiting_save_also_cancels_save_and_close(tmp_path):
    rig = Rig(tmp_path, present=False)
    rig.api.set_band(0, LOW_CUT)
    rig.api.close_app("save")  # waits for the CHU 2
    rig.api.cancel_save()
    rig.plug.present = True
    rig.tick()
    rig.api.save()  # a later, unrelated save
    rig.tick()
    assert rig.state()["save"]["state"] == "done" and rig.closed == 0


def test_close_without_saving_drops_a_waiting_save(tmp_path):
    rig = Rig(tmp_path, present=False)
    rig.api.set_band(0, LOW_CUT)
    rig.api.save()  # waits for the CHU 2
    rig.api.close_app("discard")
    rig.plug.present = True
    rig.tick()  # the CHU 2 comes back while the app shuts down
    assert rig.fake.commits == 0 and rig.state()["save"]["state"] == "idle"


def test_shutdown_drops_a_waiting_save(tmp_path):
    rig = Rig(tmp_path, present=False)
    rig.api.set_band(0, LOW_CUT)
    rig.api.save()
    rig.api._shutdown()
    rig.plug.present = True
    rig.tick()
    assert rig.fake.commits == 0


def test_a_backup_that_cannot_be_written_does_not_break_the_connection(tmp_path, monkeypatch):
    rig = Rig(tmp_path)

    def disk_full(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(rig.store, "write_backup_once", disk_full)
    rig.tick()
    s = rig.state()
    assert s["connected"] and s["backup"] is None
    assert s["design"][1]["gain"] == -6.0 and len(rig.pushed_named("state")) == 1


# ---- owner request: reset to default ------------------------------------- #
def test_reset_bands_goes_flat_live_without_saving(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()
    s = rig.api.reset_bands()
    assert s["design"] == DEFAULT_DESIGN and s["changes"] == 5 and s["edited"]
    assert s["preamp"]["method"] == "none"
    rig.tick()
    gains = [rig.fake.live[0x26 + 2 * i][:2] for i in range(5)]
    assert gains == [bytes(2)] * 5 and rig.fake.commits == 0  # heard now, not saved


def test_set_design_puts_all_bands_back_for_undo(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()
    before = rig.state()["design"]
    rig.api.reset_bands()
    s = rig.api.set_design(before)
    assert s["design"] == before and s["changes"] == 0


def test_set_design_needs_five_valid_bands(tmp_path):
    rig = Rig(tmp_path, present=False)
    for bad in (DEFAULT_DESIGN[:4], DEFAULT_DESIGN[:4] + [{"type": "lowpass", "frequency": 100,
                                                          "gain": 0, "q": 1}]):
        try:
            rig.api.set_design(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")


# ---- Plan 3: presets, Quick Tune, import / export, share code, settings ---- #
class FakeDialogs:
    """Stands in for the window's Open / Save dialogs."""

    def __init__(self, open_path=None, save_path=None):
        self.open_path, self.save_path, self.asked = open_path, save_path, []

    def open_file(self):
        self.asked.append("open")
        return self.open_path

    def save_file(self, filename, kind):
        self.asked.append((filename, kind))
        return self.save_path


def _with_dialogs(rig, dialogs):
    rig.api._dialogs = dialogs
    return rig


def test_library_lists_presets_recipes_and_what_is_on_the_chu2(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()  # writes the first-seen backup, which equals what is stored
    lib = rig.api.get_library()
    ids = {p["id"]: p for p in lib["presets"]}
    assert ids["official:backup"]["on_chu2"] and not ids["scene:fps"]["on_chu2"]
    assert [s["id"] for s in lib["recipes"]["scenes"]] == ["music", "gaming", "movies", "fps", "calls"]


def test_apply_a_preset_plays_it_and_names_the_eq(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()
    s = rig.api.apply_preset("scene:calls")
    assert s["name"] == "Calls" and s["design"][2]["frequency"] == 1600.0 and s["edited"]
    rig.tick()
    assert rig.fake.commits == 0 and rig.fake.writes  # heard, not saved


def test_quick_tune_composes_and_explains(tmp_path):
    rig = Rig(tmp_path, present=False)
    s = rig.api.quick_tune("fps", ["clearer_voices"], "standard")
    assert s["quick"]["notes"] == ["Replaces band 3 of Competitive FPS."]
    assert s["quick"]["text"][-1] == quicktune.GAMING_NOTE and s["name"] == "Competitive FPS"
    assert s["design"][2]["frequency"] == 1600.0
    assert rig.api.set_band(0, LOW_CUT)["quick"] is None  # a hand edit leaves Quick Tune


def _choice(state):
    return {k: state["quick"][k] for k in ("scene", "tweaks", "intensity")} if state["quick"] else None


def test_reopening_selects_the_quick_tune_choice_behind_the_eq(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()
    rig.api.quick_tune("music", ["sparkle"], "strong")
    rig.api.save()
    rig.tick()
    later = Rig(tmp_path, store=rig.store, plug=rig.plug)
    later.tick()
    s = later.state()
    assert s["name"] == "Music (warm and clear)" and s["changes"] == 0 and not s["edited"]
    assert _choice(s) == {"scene": "music", "tweaks": ["sparkle"], "intensity": "strong"}


def test_an_eq_that_is_no_quick_tune_choice_selects_nothing(tmp_path):
    rig = Rig(tmp_path)
    rig.tick()  # the fake CHU 2's own EQ
    assert rig.state()["quick"] is None


def test_applying_a_scene_preset_selects_it_in_quick_tune(tmp_path):
    rig = Rig(tmp_path, present=False)
    s = rig.api.apply_preset("scene:calls")
    assert _choice(s) == {"scene": "calls", "tweaks": [], "intensity": "standard"}


def test_undo_puts_back_the_quick_tune_choice(tmp_path):
    rig = Rig(tmp_path, present=False)
    before = rig.api.quick_tune("fps", ["sparkle"], "strong")
    rig.api.quick_tune("calls", [], "standard")
    choice = {"scene": "fps", "tweaks": ["sparkle"], "intensity": "strong"}
    s = rig.api.set_design(before["design"], before["name"], choice)
    assert s["quick"] == before["quick"] and s["name"] == "Competitive FPS"
    assert rig.api.set_design(before["design"], "My EQ")["quick"] is None
    for bad in ({"scene": "nope", "tweaks": [], "intensity": "standard"}, "fps"):
        try:
            rig.api.set_design(before["design"], None, bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad!r}")


def test_save_rename_delete_and_favourite_my_presets(tmp_path):
    rig = Rig(tmp_path, present=False)
    rig.api.set_band(0, LOW_CUT)
    lib = rig.api.save_preset("Night Drive", ["Music"])
    mine = [p for p in lib["presets"] if p["group"] == "mine"]
    assert [p["id"] for p in mine] == ["mine:night-drive"] and mine[0]["bands"][0]["gain"] == -3.0
    assert rig.state()["name"] == "Night Drive"
    lib = rig.api.set_favourite("mine:night-drive", True)
    assert [p["favourite"] for p in lib["presets"] if p["id"] == "mine:night-drive"] == [True]
    lib = rig.api.rename_preset("mine:night-drive", "Night Drive 2")
    assert [p["name"] for p in lib["presets"] if p["group"] == "mine"] == ["Night Drive 2"]
    lib = rig.api.delete_preset("mine:night-drive")
    assert [p for p in lib["presets"] if p["group"] == "mine"] == []


def test_share_code_round_trips_through_import(tmp_path):
    rig = Rig(tmp_path, present=False)
    rig.api.apply_preset("scene:fps")
    shared = rig.api.share_code()
    assert shared["code"].startswith("CHU2-1.CompetitiveFPS.")
    assert shared["text"].startswith("LS 100 Hz −2.5 Q0.70")
    preview = rig.api.import_text(f"my EQ: {shared['code']}")
    assert preview["format"] == "Share code"
    assert [b["gain"] for b in preview["bands"]] == [b["gain"] for b in rig.state()["design"]]
    assert "error" in rig.api.import_text("nothing here")
    dropped = rig.api.import_text("Filter: ON PK Fc 1000 Hz Gain -3 dB Q 1", "Dropped.txt")
    assert dropped["name"] == "Dropped"


def test_import_a_file_through_the_open_dialog(tmp_path):
    path = tmp_path / "ParametricEQ.txt"
    path.write_text("Preamp: -3 dB\nFilter 1: ON PK Fc 1000 Hz Gain 3 dB Q 1\n", encoding="utf-8")
    rig = _with_dialogs(Rig(tmp_path, present=False), FakeDialogs(open_path=str(path)))
    preview = rig.api.import_file()
    assert preview["name"] == "ParametricEQ" and preview["preamp"] == -3.0
    rig.api._dialogs.open_path = None
    assert rig.api.import_file() == {"cancelled": True}


def test_import_to_editor_keeps_the_file_name(tmp_path):
    rig = Rig(tmp_path, present=False)
    preview = rig.api.import_text("Filter: ON PK Fc 1000 Hz Gain -3 dB Q 1\n")
    s = rig.api.set_design(preview["bands"], "Imported EQ")
    assert s["name"] == "Imported EQ" and s["design"][0]["gain"] == -3.0


def test_export_through_the_save_dialog(tmp_path):
    out = tmp_path / "out.txt"
    rig = _with_dialogs(Rig(tmp_path, present=False), FakeDialogs(save_path=str(out)))
    rig.api.apply_preset("scene:movies")
    assert rig.api.export_file("apo") == {"saved": str(out)}
    assert rig.api._dialogs.asked == [("MoviesCinematic.txt", "apo")]
    text = out.read_text(encoding="utf-8")
    assert "Preamp: -3.0 dB" in text and "Filter 1: ON LSC Fc 65 Hz Gain 3.0 dB Q 0.700" in text
    rig.api._dialogs.save_path = None
    assert rig.api.export_file("json") == {"cancelled": True}


def test_settings_theme_and_confirm_save(tmp_path):
    rig = Rig(tmp_path, present=False)
    assert rig.state()["settings"] == {"theme": "atelier", "confirm_save": True}
    s = rig.api.set_setting("theme", "mocha")
    assert s["settings"]["theme"] == "mocha" and rig.store.load_settings()["theme"] == "mocha"
    for key, value in (("theme", "neon"), ("volume", 3)):
        try:
            rig.api.set_setting(key, value)
        except ValueError:
            continue
        raise AssertionError(f"accepted {key}={value}")


def test_open_the_data_folder(tmp_path):
    rig = Rig(tmp_path, present=False)
    opened = []
    rig.api._open_folder = opened.append
    assert rig.api.open_data_folder() == {"folder": rig.store.root} and opened == [rig.store.root]
