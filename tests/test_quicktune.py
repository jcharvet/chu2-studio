"""Quick Tune recipes (brief §4, spec §5 Calls) and how they combine.

    python -m pytest -q tests/test_quicktune.py
"""

import itertools

from chu2 import dsp, eq, quicktune

IDLE = quicktune.IDLE_DESIGN


def _band(design, n):
    b = design[n - 1]
    return (b["type"], b["frequency"], b["gain"], b["q"])


def _fits(design):
    dsp.kt_fit_bands([eq.FilterBand(b["type"], b["frequency"], b["gain"], b["q"]) for b in design])


def test_nothing_chosen_is_flat():
    design, notes = quicktune.compose(None, [], "standard")
    assert design == IDLE and notes == []


OWNER_PROFILES = {  # the owner's five profiles (2026-09-19), brief §4
    "music": [("low_shelf", 90.0, 2.0, 0.7), ("peaking", 250.0, -0.8, 1.0), ("peaking", 2800.0, -1.5, 1.2),
              ("peaking", 7500.0, -2.0, 2.0), ("high_shelf", 12000.0, 1.0, 0.7)],
    "gaming": [("low_shelf", 80.0, 1.0, 0.7), ("peaking", 220.0, -1.5, 1.0), ("peaking", 1700.0, 1.0, 1.0),
               ("peaking", 3500.0, 1.0, 1.2), ("peaking", 7000.0, -1.0, 2.0)],
    "movies": [("low_shelf", 65.0, 3.0, 0.7), ("peaking", 250.0, -1.0, 1.0), ("peaking", 1800.0, 1.0, 1.0),
               ("peaking", 3200.0, 1.0, 1.2), ("peaking", 7500.0, -1.5, 2.0)],
    "fps": [("low_shelf", 100.0, -2.5, 0.7), ("peaking", 250.0, -2.0, 1.0), ("peaking", 1600.0, 1.5, 1.0),
            ("peaking", 3200.0, 2.0, 1.2), ("peaking", 7000.0, -1.0, 2.0)],
    "calls": [("low_shelf", 120.0, -2.0, 0.7), ("peaking", 300.0, -1.5, 1.0), ("peaking", 1600.0, 1.0, 1.0),
              ("peaking", 2700.0, 1.5, 1.2), ("peaking", 7000.0, -1.5, 2.0)],
}


def test_the_scenes_are_the_owners_five_profiles():
    assert [s["id"] for s in quicktune.SCENES] == list(OWNER_PROFILES)
    for scene, bands in OWNER_PROFILES.items():
        design, _notes = quicktune.compose(scene, [], "standard")
        assert [_band(design, n) for n in range(1, 6)] == bands, scene


def test_every_recipe_fits_the_chu2_at_every_intensity():
    scenes = [None] + [s["id"] for s in quicktune.SCENES]
    for scene, intensity in itertools.product(scenes, quicktune.INTENSITY):
        for tweak in quicktune.TWEAKS:
            design, _notes = quicktune.compose(scene, [tweak["id"]], intensity)
            _fits(design)
            assert all(-8.0 <= b["gain"] <= 6.0 for b in design)


def test_intensity_scales_and_caps():
    design, _notes = quicktune.compose("music", [], "strong")
    assert _band(design, 3)[2] == -2.3  # -1.5 x 1.5 = -2.25, rounded away from zero
    design, _notes = quicktune.compose(None, ["sub_bass"], "strong")
    assert _band(design, 1)[2] == 6.0
    design, _notes = quicktune.compose("fps", [], "subtle")
    assert _band(design, 1)[2] == -1.3  # -2.5 x 0.5 = -1.25
    assert quicktune.scale(9.0, "standard") == 6.0 and quicktune.scale(-6.0, "strong") == -8.0


def test_a_tweak_says_which_scene_band_it_replaces():
    design, notes = quicktune.compose("fps", ["clearer_voices"], "standard")
    assert _band(design, 3) == ("peaking", 1600.0, 2.0, 1.0)
    assert notes == ["Replaces band 3 of Competitive FPS."]
    design, notes = quicktune.compose("fps", ["less_sharp"], "standard")
    assert notes == ["Replaces band 4 of Competitive FPS.", "Replaces band 5 of Competitive FPS."]
    assert _band(design, 4) == ("peaking", 7000.0, -2.5, 2.0)


def test_tweaks_that_share_a_band_cannot_be_combined():
    for pair in (["softer_vocals", "clearer_voices"], ["less_sharp", "sparkle"]):
        try:
            quicktune.compose(None, pair, "standard")
        except ValueError:
            continue
        raise AssertionError(f"combined {pair}")
    assert quicktune.conflicts("sparkle") == ["less_sharp"]


def test_unknown_names_are_refused():
    for args in (("nope", [], "standard"), (None, ["nope"], "standard"), (None, [], "loud")):
        try:
            quicktune.compose(*args)
        except ValueError:
            continue
        raise AssertionError(f"accepted {args}")


def test_what_changed_text_and_the_gaming_note():
    text = quicktune.explain("fps", ["sub_bass"])
    assert text[0].startswith("Lowers the bass below 100 Hz")
    assert text[1].startswith("Adds up to 4 dB below ~55 Hz")
    assert quicktune.explain("fps", [])[-1] == quicktune.GAMING_NOTE
    assert quicktune.GAMING_NOTE not in quicktune.explain("calls", [])
