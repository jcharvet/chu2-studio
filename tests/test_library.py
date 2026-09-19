"""The preset library (brief S6): Official, the Quick Tune scenes, the user's own.

    python -m pytest -q tests/test_library.py
"""

import json
import os

from chu2 import eq, library, preset, quicktune
from chu2.store import Store

WARM = [{"type": "peaking", "frequency": 40.0, "gain": -1.5, "q": 0.5, "bypass": False},
        {"type": "low_shelf", "frequency": 100.0, "gain": 6.0, "q": 0.7, "bypass": True},
        {"type": "peaking", "frequency": 1400.0, "gain": -2.5, "q": 1.6, "bypass": False},
        {"type": "peaking", "frequency": 3500.0, "gain": -4.8, "q": 1.0, "bypass": False},
        {"type": "peaking", "frequency": 9000.0, "gain": -2.0, "q": 1.5, "bypass": False}]


def _lib(tmp_path):
    return library.Library(Store(str(tmp_path)))


def test_official_and_scene_presets_are_always_there(tmp_path):
    items = _lib(tmp_path).presets()
    ids = [p["id"] for p in items]
    assert ids[0] == "official:flat" and len(ids) == len(set(ids))
    assert [p["id"] for p in items if p["group"] == "builtin"] == [
        f"scene:{s['id']}" for s in quicktune.SCENES]
    assert all(len(p["bands"]) == 5 for p in items)
    assert items[0]["bands"] == quicktune.IDLE_DESIGN


def test_the_first_seen_backup_is_an_official_preset(tmp_path):
    store = Store(str(tmp_path))
    store.write_backup_once(3, [eq.FilterBand("peaking", 200.0, -6.0, 0.6)])
    backup = library.Library(store).find("official:backup")
    assert backup["name"] == "Your CHU 2 when first seen"
    assert backup["bands"][0]["gain"] == -6.0 and len(backup["bands"]) == 5


def test_save_rename_delete_my_preset(tmp_path):
    lib = _lib(tmp_path)
    saved = lib.save("Warm Bass", ["Music"], WARM)
    assert saved["id"] == "mine:warm-bass" and saved["group"] == "mine"
    assert lib.find(saved["id"])["bands"] == WARM  # bypass kept
    path = os.path.join(str(tmp_path), "presets", "warm-bass.chu2.json")
    assert preset.load(path).bands[1] == eq.FilterBand("low_shelf", 100.0, 6.0, 0.7)
    assert lib.save("Warm Bass", [], WARM)["id"] == "mine:warm-bass-2"
    lib.rename("mine:warm-bass", "Warm Bass (old)")
    assert lib.find("mine:warm-bass")["name"] == "Warm Bass (old)"
    lib.set_favourite("mine:warm-bass", True)
    lib.delete("mine:warm-bass")
    assert "mine:warm-bass" not in [p["id"] for p in lib.presets()]
    assert "mine:warm-bass" not in Store(str(tmp_path)).load_favourites()


def test_favourites_are_remembered(tmp_path):
    _lib(tmp_path).set_favourite("scene:fps", True)
    items = {p["id"]: p for p in _lib(tmp_path).presets()}
    assert items["scene:fps"]["favourite"] and not items["scene:calls"]["favourite"]


def test_files_the_chu2_cannot_play_are_skipped(tmp_path):
    folder = os.path.join(str(tmp_path), "presets")
    os.makedirs(folder)
    bad = {"version": 1, "name": "Low pass", "bands": [
        {"type": "lowpass", "frequency": 100.0, "gain": 0.0, "q": 0.7}]}
    with open(os.path.join(folder, "lowpass.chu2.json"), "w", encoding="utf-8") as handle:
        json.dump(bad, handle)
    with open(os.path.join(folder, "broken.chu2.json"), "w", encoding="utf-8") as handle:
        handle.write("{nope")
    assert [p for p in _lib(tmp_path).presets() if p["group"] == "mine"] == []


def test_names_are_needed_and_builtins_are_read_only(tmp_path):
    lib = _lib(tmp_path)
    for call in (lambda: lib.save("   ", [], WARM), lambda: lib.delete("scene:fps"),
                 lambda: lib.rename("official:flat", "x"), lambda: lib.find("mine:nope")):
        try:
            call()
        except library.LibraryError:
            continue
        raise AssertionError("no LibraryError")


def test_a_preset_id_cannot_reach_other_files(tmp_path):
    store = Store(str(tmp_path))
    store.save_favourites(["scene:fps"])
    lib = library.Library(store)
    for bad in ("mine:../favourites", "mine:..\favourites", "mine:", "mine:a/b"):
        try:
            lib.delete(bad)
        except library.LibraryError:
            continue
        raise AssertionError(f"accepted {bad}")
    assert store.load_favourites() == ["scene:fps"]


def test_changes_from_several_threads_are_all_kept(tmp_path):
    import threading

    lib = library.Library(Store(str(tmp_path)))
    ids = [f"scene:{s['id']}" for s in quicktune.SCENES] + [f"mine:x{i}" for i in range(15)]
    start = threading.Barrier(len(ids) + 3)

    def favourite(preset_id):
        start.wait()
        lib.set_favourite(preset_id, True)

    def save():
        start.wait()
        lib.save("Same name", [], quicktune.IDLE_DESIGN)

    threads = [threading.Thread(target=favourite, args=(i,)) for i in ids]
    threads += [threading.Thread(target=save) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(Store(str(tmp_path)).load_favourites()) == sorted(ids)  # no toggle lost
    mine = [p["id"] for p in lib.presets() if p["group"] == "mine"]
    assert sorted(mine) == ["mine:same-name", "mine:same-name-2", "mine:same-name-3"]  # none overwritten

