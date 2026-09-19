"""Band cards, top bar and the preamp card.

    python -m pytest -q tests/ui/test_ui_bands.py
"""

PREAMP = {"preamp_db": -6.0, "peak_db": 4.8, "peak_hz": 20, "device_peak_db": -1.2, "method": "flip",
          "flipped": [1], "trim_index": None, "warning": None}


def _settle(page):
    page.evaluate("async () => (await import('./store.js')).flushEdits()")


def _card(n, what):
    return f"[data-band='{n}'] [data-test={what}]"


def test_five_cards_show_the_bands(open_app):
    page = open_app()
    assert page.locator("fieldset[data-band]").count() == 5
    assert [page.input_value(_card(2, k)) for k in ("frequency", "gain", "q")] == ["200", "-6.0", "0.60"]
    assert page.input_value(_card(2, "type")) == "peaking"


def test_typed_values_are_clamped_and_sent(open_app, calls):
    page = open_app()
    page.fill(_card(3, "gain"), "15")
    page.press(_card(3, "gain"), "Enter")
    _settle(page)
    assert calls(page, "set_band")[-1] == [2, {"type": "peaking", "frequency": 1400, "gain": 12,
                                               "q": 1.6, "bypass": False}]
    assert page.input_value(_card(3, "gain")) == "12.0"
    assert page.get_attribute("[data-band='3']", "aria-selected") == "true"


def test_type_bypass_and_reset(open_app, calls):
    page = open_app()
    page.select_option(_card(4, "type"), "high_shelf")
    _settle(page)
    assert calls(page, "set_band")[-1][1]["type"] == "high_shelf"
    page.click(_card(4, "bypass"))
    _settle(page)
    assert calls(page, "set_band")[-1][1]["bypass"] is True
    assert page.get_attribute(_card(4, "bypass"), "aria-pressed") == "true"
    page.click(_card(4, "reset"))
    _settle(page)
    assert calls(page, "set_band")[-1][1]["gain"] == 0


def test_top_bar_names_the_eq(open_app):
    page = open_app({"name": "Music (warm and clear)"})
    assert page.inner_text("[data-test=eq-name]") == "Music (warm and clear)"
    assert page.get_attribute("[data-test=eq-name]", "title") == "Music (warm and clear)"  # when cut short


def test_a_long_name_never_pushes_save_off_the_window(open_app):
    page = open_app({"name": "Gaming (League, RPG, MMO)", "changes": 1})
    page.set_viewport_size({"width": 1024, "height": 700})  # the window's minimum size
    assert page.evaluate("document.documentElement.scrollWidth") == 1024
    assert page.evaluate("document.querySelector('[data-test=save]').getBoundingClientRect().right") <= 1024


def test_top_bar_counts_changes_and_saves(open_app):
    page = open_app()
    assert page.inner_text("[data-test=changes]").strip() == "On CHU 2"
    assert page.is_disabled("[data-test=save]")
    page.evaluate("window.__mock.push({changes: 2})")
    page.wait_for_selector("[data-test=changes]:has-text('2 changes not on CHU 2')")
    page.click("[data-test=save]")
    page.click("[data-test=save-confirm]")
    page.wait_for_function("window.__mock.calls.some((c) => c[0] === 'save')")


def test_eq_switch_turns_the_device_eq_off(open_app, calls):
    page = open_app()
    assert page.get_attribute("[data-test=eq-switch]", "aria-checked") == "true"
    page.click("[data-test=eq-switch]")
    page.wait_for_selector("[data-test=eq-switch][aria-checked='false']")
    assert calls(page, "set_eq_enabled") == [[False]]


def test_preamp_readout_uses_the_spec_wording(open_app):
    page = open_app({"preamp": PREAMP})
    assert page.inner_text("[data-test=boost]") == "Max boost +4.8 dB at 20 Hz"
    assert page.inner_text("[data-test=preamp-line]") == (
        "Preamp −6.0 dB — turn your volume up about 6 dB to compare fairly.")
    assert page.inner_text(_card(2, "note")) == "Stored as the opposite shelf: same sound, quieter."


def test_a_trim_band_is_labelled_as_the_preamp(open_app):
    trim = dict(PREAMP, method="trim", flipped=[], trim_index=4, preamp_db=-3.0)
    bands = [{"type": "peaking", "frequency": 1000, "gain": 0, "q": 1}] * 4 + \
        [{"type": "high_shelf", "frequency": 20, "gain": -3.0, "q": 0.707}]
    page = open_app({"preamp": trim, "device_bands": bands})
    assert page.inner_text(_card(5, "note")) == "Holds the preamp (−3.0 dB)."


def test_an_eq_stored_without_a_preamp_says_so(open_app):
    page = open_app({"preamp": dict(PREAMP, warning="stored_without_preamp", method="none", flipped=[],
                                    preamp_db=0.0, device_peak_db=4.8)})
    assert page.inner_text("[data-test=preamp-line]") == (
        "Stored without a preamp: boosts above 0 dB may distort. Your next edit adds one.")


def test_no_free_band_offers_to_free_the_smallest(open_app):
    page = open_app({"preamp": dict(PREAMP, warning="no_free_band", method="none", flipped=[],
                                    preamp_db=0.0, device_peak_db=4.8)})
    assert page.inner_text("[data-test=preamp-warning]").startswith(
        "All 5 bands are in use, so there is no room for a preamp: loud passages may distort.")
    assert page.locator("[data-test=preamp-line]").count() == 0  # never "No preamp needed." here
    assert page.inner_text("[data-test=free-band]") == "Free band 1 for the preamp"
    page.click("[data-test=free-band]")
    page.wait_for_function("window.__mock.calls.some((c) => c[0] === 'free_smallest_band')")


def test_auto_preamp_can_be_switched_off(open_app, calls):
    page = open_app()
    page.uncheck("[data-test=auto-preamp]")
    page.wait_for_function("window.__mock.calls.some((c) => c[0] === 'set_auto_preamp')")
    assert calls(page, "set_auto_preamp") == [[False]]


def test_layout_fits_the_smallest_windows(open_app):
    for width, height in ((1280, 688), (1024, 700)):
        page = open_app()
        page.set_viewport_size({"width": width, "height": height})
        assert page.evaluate("document.documentElement.scrollWidth") <= width
        save = page.locator("[data-test=save]").bounding_box()
        assert save["x"] + save["width"] <= width and save["y"] >= 0
        graph = page.locator(".graph").bounding_box()
        assert graph["width"] >= 560 and graph["height"] >= 400


def test_reset_all_goes_flat_and_can_be_undone(open_app, calls):
    page = open_app()
    before = page.evaluate("async () => (await import('./store.js')).state.design")
    page.click("[data-test=reset-all]")
    page.wait_for_selector(".toast:has-text('All bands reset to 0 dB')")
    assert calls(page, "reset_bands") == [[]]
    assert page.input_value(_card(2, "gain")) == "0.0"
    page.click(".toast [data-test=toast-action]")
    page.wait_for_function("window.__mock.calls.some((c) => c[0] === 'set_design')")
    assert calls(page, "set_design") == [[before, "My EQ", None]]
    page.wait_for_function("document.querySelector(\"[data-band='2'] [data-test=gain]\").value === '-6.0'")


def test_reset_all_is_off_when_already_flat(open_app):
    flat = [{"type": "peaking", "frequency": f, "gain": 0, "q": 1, "bypass": False}
            for f in (100, 300, 1000, 3000, 8000)]
    page = open_app({"design": flat})
    assert page.is_disabled("[data-test=reset-all]")


def test_typing_is_kept_when_an_update_arrives(open_app, calls):
    page = open_app()
    page.fill(_card(4, "gain"), "1")  # typed, not committed yet
    page.evaluate("window.__mock.push({changes: 1})")  # e.g. the answer to an earlier edit
    page.wait_for_selector("[data-test=changes]:has-text('1 change')")
    assert page.input_value(_card(4, "gain")) == "1"
    page.press(_card(4, "gain"), "Enter")
    _settle(page)
    assert calls(page, "set_band")[-1][1]["gain"] == 1

