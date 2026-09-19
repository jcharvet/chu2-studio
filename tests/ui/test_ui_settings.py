"""Settings and About (brief S10).

    python -m pytest -q tests/ui/test_ui_settings.py
"""

CHANGED = {"changes": 1, "edited": True}


def _called(page, method, count=1):
    page.wait_for_function(
        "([m, n]) => window.__mock.calls.filter((c) => c[0] === m).length === n", arg=[method, count])


def _swatch(page, theme):
    return page.eval_on_selector(f"[data-theme-option={theme}] .theme-swatch span",
                                 "(el) => getComputedStyle(el).backgroundColor")


def test_theme_cards_show_their_own_colours_and_switch_the_theme(open_app, calls):
    page = open_app()
    page.click("[data-test=open-settings]")
    assert page.get_attribute("[data-theme-option=atelier]", "aria-checked") == "true"
    assert len({_swatch(page, t) for t in ("atelier", "mocha", "sage", "latte", "porcelain")}) == 5
    page.click("[data-theme-option=latte]")
    _called(page, "set_setting")
    assert calls(page, "set_setting") == [["theme", "latte"]]
    page.wait_for_function("document.documentElement.dataset.theme === 'latte'")
    page.keyboard.press("ArrowRight")  # radio group: arrows pick the next theme
    _called(page, "set_setting", 2)
    assert calls(page, "set_setting")[-1] == ["theme", "porcelain"]
    page.wait_for_selector("[data-theme-option=porcelain][aria-checked=true]:focus")


def test_ask_before_saving_can_be_turned_off(open_app, calls):
    page = open_app(CHANGED)
    page.keyboard.press("Control+,")
    page.uncheck("[data-test=confirm-save]")
    _called(page, "set_setting")
    assert calls(page, "set_setting") == [["confirm_save", False]]
    page.keyboard.press("Escape")
    page.wait_for_selector("[data-test=settings-dialog]", state="detached")
    page.click("[data-test=save]")
    _called(page, "save")  # no confirm step
    page.wait_for_selector("[data-test=save-panel][data-phase=running]")


def test_dont_ask_again_in_the_save_confirm(open_app, calls):
    page = open_app(CHANGED)
    page.click("[data-test=save]")
    page.check("[data-test=save-dont-ask]")
    page.click("[data-test=save-confirm]")
    _called(page, "save")
    assert calls(page, "set_setting") == [["confirm_save", False]]


def test_data_folder_restore_and_about(open_app, calls):
    page = open_app()
    page.click("[data-test=open-settings]")
    page.click("[data-test=open-data-folder]")
    _called(page, "open_data_folder")
    assert page.inner_text("[data-test=about-version]") == "CHU 2 Studio 0.1.0"
    assert "not affiliated with or endorsed by Moondrop" in page.inner_text("[data-test=disclaimer]")
    credits = page.inner_text("[data-test=credits]")
    for name in ("Vue", "Phosphor Icons", "Catppuccin", "Inter", "Newsreader", "JetBrains Mono"):
        assert name in credits
    page.click("[data-test=settings-restore]")  # brief S9: also in Settings
    page.wait_for_selector("[data-test=restore-dialog]")
    assert page.locator("[data-test=settings-dialog]").count() == 0


def test_every_credited_licence_file_is_bundled(open_app, ui_url):
    page = open_app()
    page.click("[data-test=open-settings]")
    paths = page.locator("[data-test=credits] .muted").all_inner_texts()
    for path in paths:
        response = page.request.get(f"{ui_url}/{path.strip('()')}")
        assert response.ok, path


def test_only_one_dialog_is_open_at_a_time(open_app):
    page = open_app()
    page.click("[data-test=open-library]")
    page.wait_for_selector("[data-test=preset-sheet]")
    page.keyboard.press("Control+,")
    page.wait_for_selector("[data-test=settings-dialog]")
    assert page.locator("[data-test=preset-sheet]").count() == 0
    page.keyboard.press("Control+i")
    page.wait_for_selector("[data-test=share-dialog]")
    assert page.locator("[data-test=settings-dialog]").count() == 0
    page.keyboard.press("Control+p")
    page.wait_for_selector("[data-test=preset-sheet]")
    assert page.locator("[data-test=share-dialog], [data-test=settings-dialog]").count() == 0

