"""Save / Restore flows and the close guard (brief S8, S9).

    python -m pytest -q tests/ui/test_ui_save.py
"""

CHANGED = {"changes": 1, "edited": True,
           "design": [{"type": "low_shelf", "frequency": 100, "gain": 3, "q": 0.7, "bypass": False},
                      {"type": "peaking", "frequency": 200, "gain": -6, "q": 0.6, "bypass": False},
                      {"type": "peaking", "frequency": 1400, "gain": -2.5, "q": 1.6, "bypass": False},
                      {"type": "peaking", "frequency": 3500, "gain": -4.8, "q": 1.0, "bypass": False},
                      {"type": "peaking", "frequency": 9000, "gain": -2, "q": 1.5, "bypass": False}],
           "device_bands": [{"type": "low_shelf", "frequency": 100, "gain": 3, "q": 0.7},
                            {"type": "peaking", "frequency": 200, "gain": -6, "q": 0.6},
                            {"type": "peaking", "frequency": 1400, "gain": -2.5, "q": 1.6},
                            {"type": "peaking", "frequency": 3500, "gain": -4.8, "q": 1.0},
                            {"type": "peaking", "frequency": 9000, "gain": -2, "q": 1.5}]}


def _push_save(page, **fields):
    page.evaluate("(f) => window.__mock.push({save: Object.assign(window.__mock.state().save, f)})", fields)


def _called(page, method):
    page.wait_for_function("(m) => window.__mock.calls.some((c) => c[0] === m)", arg=method)


def test_save_asks_first_then_shows_progress_then_done(open_app):
    page = open_app(CHANGED)
    page.click("[data-test=save]")
    panel = page.locator("[data-test=save-panel][data-phase=confirm]")
    assert "audio drops for about a second" in panel.inner_text()
    assert page.inner_text("[data-test=change-list]") == "Band 1 · Low shelf 100 Hz +3.0 dB"
    assert page.evaluate("window.__mock.calls.filter((c) => c[0] === 'save').length") == 0
    page.click("[data-test=save-confirm]")
    _called(page, "save")
    page.wait_for_selector("[data-test=save-panel][data-phase=running]")
    _push_save(page, step="committing")
    page.wait_for_selector("[data-step=committing][data-status=active]")
    assert page.get_attribute("[data-step=writing]", "data-status") == "done"
    _push_save(page, step="still_waiting")
    page.wait_for_selector("[data-test=still-waiting]")
    assert page.get_attribute("[data-step=restarting]", "data-status") == "active"
    assert page.get_attribute(".studio", "inert") is not None  # the rest waits during a save
    _push_save(page, state="done", step=None)
    page.wait_for_selector(".toast:has-text('Saved to CHU 2 ✓ Checked.')")
    _called(page, "dismiss_save")
    assert page.locator("[data-test=save-panel]").count() == 0


def test_cancel_does_not_save(open_app):
    page = open_app(CHANGED)
    page.click("[data-test=save]")
    page.click("[data-test=save-cancel]")
    assert page.locator("[data-test=save-panel]").count() == 0
    assert page.evaluate("window.__mock.calls.filter((c) => c[0] === 'save').length") == 0


def test_ctrl_s_opens_the_confirm_and_escape_closes_it(open_app):
    page = open_app(CHANGED)
    page.keyboard.press("Control+s")
    page.wait_for_selector("[data-test=save-panel][data-phase=confirm]")
    page.keyboard.press("Escape")
    assert page.locator("[data-test=save-panel]").count() == 0


def test_a_failed_save_says_what_happened_and_retries(open_app):
    page = open_app(dict(CHANGED, save={"state": "failed", "kind": "save", "step": None,
                                         "reason": "restart_timeout", "after_commit": True,
                                         "mismatched": [], "message": None}))
    assert page.inner_text("[data-test=save-failure]") == (
        "Your CHU 2 may still have its previous EQ. Reconnect it and we'll check.")
    page.click("[data-test=save-retry]")
    _called(page, "save")


def test_a_read_back_mismatch_names_the_bands(open_app):
    page = open_app(dict(CHANGED, save={"state": "failed", "kind": "save", "step": None,
                                         "reason": "write_mismatch", "after_commit": False,
                                         "mismatched": [1, 3], "message": None}))
    assert page.inner_text("[data-test=save-failure]") == (
        "Your CHU 2 didn't take band 2, 4 as sent. It still has its previous EQ.")


def test_saving_without_a_device_waits_and_can_be_stopped(open_app):
    page = open_app(dict(CHANGED, connected=False))
    page.click("[data-test=explore]")
    assert page.inner_text("[data-test=save]").strip() == "Save when connected"
    page.click("[data-test=save]")
    _called(page, "save")
    page.wait_for_selector("[data-test=save-panel][data-phase=waiting]")
    page.click("[data-test=save-stop-waiting]")
    _called(page, "cancel_save")


def test_restore_original_from_the_device_menu(open_app):
    page = open_app()
    page.click("[data-test=device-chip]")
    page.click("[data-test=restore-open]")
    assert page.inner_text("#restore-title") == "Put back the EQ your CHU 2 had on 19 Sep 2026, 14:02?"
    page.click("[data-test=restore-confirm]")
    _called(page, "restore_original")
    page.wait_for_selector("#save-title:has-text('Restoring the original EQ')")


def test_restore_needs_a_backup(open_app):
    page = open_app({"backup": None})
    page.click("[data-test=device-chip]")
    assert page.is_disabled("[data-test=restore-open]")


def test_closing_with_unsaved_changes_asks(open_app, calls):
    page = open_app(CHANGED)
    page.evaluate("window.__mock.emit('close_requested', {changes: 1, connected: true, saving: false})")
    dialog = page.locator("[data-test=close-dialog]")
    assert "Your CHU 2 still has the old EQ." in dialog.inner_text()
    page.click("[data-test=close-keep]")
    assert dialog.count() == 0 and calls(page, "close_app") == []
    page.evaluate("window.__mock.emit('close_requested', {changes: 1, connected: true, saving: false})")
    page.click("[data-test=close-discard]")
    _called(page, "close_app")
    assert calls(page, "close_app") == [["discard"]]


def test_save_and_close(open_app, calls):
    page = open_app(CHANGED)
    page.evaluate("window.__mock.emit('close_requested', {changes: 1, connected: true, saving: false})")
    page.click("[data-test=close-save]")
    _called(page, "close_app")
    assert calls(page, "close_app") == [["save"]]


def test_closing_during_a_save_says_wait(open_app):
    page = open_app(CHANGED)
    page.evaluate("window.__mock.emit('close_requested', {changes: 1, connected: true, saving: true})")
    assert page.inner_text("#close-title") == "Saving to your CHU 2…"
    assert page.locator("[data-test=close-discard]").count() == 0


def test_key_a_switches_the_eq(open_app, calls):
    page = open_app()
    page.keyboard.press("a")
    _called(page, "set_eq_enabled")
    assert calls(page, "set_eq_enabled") == [[False]]


def test_save_says_it_turns_the_eq_back_on(open_app):
    page = open_app(dict(CHANGED, eq_on=False))
    page.click("[data-test=save]")
    assert page.inner_text("[data-test=save-eq-note]") == (
        "The EQ is off for comparing; saving turns it back on.")
