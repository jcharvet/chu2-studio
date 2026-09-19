"""Quick Tune mode (brief S4) and the mode switch.

    python -m pytest -q tests/ui/test_ui_quick.py
"""


def _quick_calls(page, count):
    page.wait_for_function(
        "(n) => window.__mock.calls.filter((c) => c[0] === 'quick_tune').length === n", arg=count)


def _open_quick(page):
    page.click("[data-test=mode-quick]")
    page.wait_for_selector("[data-test=quick-panel] [data-test=scene-fps]")


def test_a_scene_is_played_and_explained(open_app, calls):
    page = open_app()
    _open_quick(page)
    assert page.locator("[data-test=quick-panel] input[name=scene]").count() == 6  # None + 5 scenes
    assert page.locator(".band-card").count() == 0  # the right panel explains instead
    page.check("[data-test=scene-fps]")
    _quick_calls(page, 1)
    assert calls(page, "quick_tune")[-1] == ["fps", [], "standard"]
    page.wait_for_selector("[data-test=what-changed] .title:has-text('Competitive FPS')")
    assert "Lowers the bass below 100 Hz" in page.inner_text("[data-test=what-changed]")
    assert page.is_checked("[data-test=scene-fps]")


def test_tweaks_on_the_same_band_work_as_a_pair_and_intensity_scales(open_app, calls):
    page = open_app()
    _open_quick(page)
    page.check("[data-test=tweak-softer_vocals]")
    _quick_calls(page, 1)
    page.check("[data-test=tweak-clearer_voices]")
    _quick_calls(page, 2)
    assert calls(page, "quick_tune")[-1] == [None, ["clearer_voices"], "standard"]
    page.click("[data-test=intensity-strong]")
    _quick_calls(page, 3)
    assert calls(page, "quick_tune")[-1] == [None, ["clearer_voices"], "strong"]
    assert page.inner_text("[data-test=what-changed] .changed-note") == "Tweak clearer_voices."


def test_the_graph_only_shows_in_quick_tune(open_app, calls):
    page = open_app()
    _open_quick(page)
    box = page.locator("[data-node='3']").bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x, y - 60, steps=5)
    page.mouse.up()
    page.mouse.wheel(0, -100)
    page.wait_for_timeout(150)
    assert calls(page, "set_band") == []


def test_fine_tune_and_the_ctrl_keys_switch_modes(open_app):
    page = open_app()
    page.keyboard.press("Control+1")
    page.wait_for_selector("[data-test=quick-panel]")
    assert page.get_attribute("[data-test=mode-quick]", "aria-selected") == "true"
    page.click("[data-test=fine-tune]")
    page.wait_for_selector("fieldset[data-band]")
    page.keyboard.press("Control+1")
    page.wait_for_selector("[data-test=quick-panel]")
    page.keyboard.press("Control+3")
    page.wait_for_selector("fieldset[data-band]")


def test_quick_tune_is_undoable(open_app, calls):
    page = open_app()
    before = page.evaluate("async () => (await import('./store.js')).state.design")
    _open_quick(page)
    page.check("[data-test=scene-calls]")
    _quick_calls(page, 1)
    page.keyboard.press("Control+z")
    page.wait_for_function("window.__mock.calls.some((c) => c[0] === 'set_design')")
    assert calls(page, "set_design")[-1] == [before, "My EQ", None]


def test_undo_puts_back_the_previous_scene(open_app, calls):
    page = open_app()
    _open_quick(page)
    page.check("[data-test=scene-fps]")
    _quick_calls(page, 1)
    page.check("[data-test=scene-calls]")
    _quick_calls(page, 2)
    page.keyboard.press("Control+z")
    page.wait_for_function("window.__mock.calls.some((c) => c[0] === 'set_design')")
    assert calls(page, "set_design")[-1][1:] == [
        "Competitive FPS", {"scene": "fps", "tweaks": [], "intensity": "standard"}]
    page.wait_for_selector("[data-test=scene-fps]:checked")


def test_the_top_bar_fits_at_1024(open_app):
    page = open_app({"changes": 3})
    page.set_viewport_size({"width": 1024, "height": 700})
    _open_quick(page)
    assert page.evaluate("document.documentElement.scrollWidth") <= 1024
    save = page.locator("[data-test=save]").bounding_box()
    assert save["x"] + save["width"] <= 1024
    assert page.inner_text("[data-test=changes]").strip() == "3"  # short form; full text in the title
    assert page.get_attribute("[data-test=changes]", "title") == "3 changes not on CHU 2"
