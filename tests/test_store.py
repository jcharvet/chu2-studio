"""App data folder: first-seen backup, settings, last saved design.

    python -m pytest -q tests/test_store.py
"""

import datetime
import json
import os

from chu2 import eq, store

WARM = [eq.FilterBand("peaking", 40.0, -1.5, 0.5), eq.FilterBand("low_shelf", 100.0, 6.0, 0.7)]
OTHER = [eq.FilterBand("peaking", 1000.0, 3.0, 1.0)]
NOON = datetime.datetime(2026, 9, 19, 14, 2, 0)


def test_default_root_is_appdata_unless_overridden(monkeypatch, tmp_path):
    monkeypatch.delenv(store.APP_DIR_ENV, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert store.default_root() == os.path.join(str(tmp_path), "CHU2Studio")
    monkeypatch.setenv(store.APP_DIR_ENV, str(tmp_path / "elsewhere"))
    assert store.default_root() == str(tmp_path / "elsewhere")
    assert store.Store().root == str(tmp_path / "elsewhere")


def test_backup_is_written_once_and_never_overwritten(tmp_path):
    s = store.Store(str(tmp_path / "app"))
    assert s.read_backup() is None
    assert s.write_backup_once(3, WARM, now=NOON) is True
    before = open(s.backup_path, encoding="utf-8").read()
    assert s.write_backup_once(2, OTHER) is False
    assert open(s.backup_path, encoding="utf-8").read() == before
    backup = s.read_backup()
    assert backup == {"saved_at": "2026-09-19T14:02:00", "slot": 3, "bands": WARM}


def test_unreadable_backup_reads_as_none_and_is_still_not_overwritten(tmp_path):
    s = store.Store(str(tmp_path))
    with open(s.backup_path, "w", encoding="utf-8") as handle:
        handle.write("{not json")
    assert s.read_backup() is None
    assert s.write_backup_once(3, WARM) is False


def test_settings_defaults_round_trip_and_bad_file(tmp_path):
    s = store.Store(str(tmp_path))
    assert s.load_settings() == store.DEFAULT_SETTINGS
    s.save_settings({"auto_preamp": False, "future_key": 1})
    assert s.load_settings() == dict(store.DEFAULT_SETTINGS, auto_preamp=False, future_key=1)
    assert not os.path.exists(s.settings_path + ".tmp")
    with open(s.settings_path, "w", encoding="utf-8") as handle:
        handle.write("[1, 2")
    assert s.load_settings() == store.DEFAULT_SETTINGS


def test_last_saved_round_trip(tmp_path):
    s = store.Store(str(tmp_path))
    assert s.read_last_saved() is None
    design = [dict(store.band_to_dict(b), bypass=False) for b in WARM]
    s.write_last_saved(design, WARM, "Warm Bass")
    assert s.read_last_saved() == {"design": design, "device": WARM, "name": "Warm Bass"}
    with open(s.last_saved_path, encoding="utf-8") as handle:
        assert json.load(handle)["device"][1]["type"] == "low_shelf"
