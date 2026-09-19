"""No device screen (brief S0), explore mode, unplug banner, backup toast.

    python -m pytest -q tests/ui/test_ui_nodevice.py
"""

OFF = {"connected": False, "stored": None, "backup": None}


def test_no_device_screen_explains_and_disclaims(open_app):
    page = open_app(OFF)
    screen = page.locator("[data-test=no-device]")
    assert page.inner_text("#nd-title") == "Plug in your CHU 2 DSP"
    assert "Unofficial EQ studio for the Moondrop CHU 2 DSP" in screen.text_content()
    assert "Close browser tabs using the CHU 2" in screen.inner_text()
    assert page.inner_text("[data-test=disclaimer]") == (
        "Unofficial community app · not affiliated with or endorsed by Moondrop · open source")
    assert page.locator("[data-test=save]").count() == 0


def test_explore_opens_the_studio_with_a_banner(open_app):
    page = open_app(OFF)
    page.click("[data-test=explore]")
    assert page.inner_text("[data-test=banner]") == (
        "No CHU 2 connected. Edit freely and save when it's plugged in.")
    assert page.inner_text("[data-test=device-chip]").strip() == "No CHU 2 · exploring"
    assert page.locator(".graph").count() == 1


def test_plugging_in_opens_the_studio(open_app):
    page = open_app(OFF)
    page.evaluate("window.__mock.push({connected: true})")
    page.wait_for_selector("[data-test=device-chip]:has-text('CHU 2 DSP')")
    assert page.locator("[data-test=no-device]").count() == 0


def test_unplugging_keeps_the_studio_and_the_edits(open_app):
    page = open_app()
    page.evaluate("window.__mock.push({connected: false, changes: 1})")
    page.wait_for_selector("[data-test=banner]")
    assert page.inner_text("[data-test=banner]") == (
        "CHU 2 unplugged. Your edits are kept; they're not on CHU 2.")
    assert page.locator("[data-test=no-device]").count() == 0


def test_a_device_error_is_explained(open_app):
    page = open_app(dict(OFF, device_error={"code": "unknown_filter_type", "message": "code 9"}))
    assert "filter type this app doesn't know" in page.inner_text("[data-test=device-error]")


def test_first_seen_backup_toast(open_app):
    page = open_app(OFF)
    page.evaluate("window.__mock.emit('backup_saved', {saved_at: '2026-09-19T14:02:00'})")
    page.wait_for_selector(".toast:has-text('Backup saved on this PC: the EQ your CHU 2 had on "
                           "19 Sep 2026, 14:02.')")


def test_the_looking_pulse_respects_reduced_motion(open_app):
    moving = open_app(OFF)
    assert moving.evaluate("getComputedStyle(document.querySelector('.pulse-dot')).animationName") == "pulse"
    still = open_app(OFF, reduced_motion="reduce")
    assert still.evaluate("getComputedStyle(document.querySelector('.pulse-dot')).animationName") == "none"
