"""The preset library (brief S6).

    python -m pytest -q tests/ui/test_ui_presets.py
"""


def _open(page):
    page.click("[data-test=open-library]")
    page.wait_for_selector("[data-test=preset-sheet] [data-preset='scene:fps']")


def _count(page, cat):
    return page.inner_text(f"[data-test=cat-{cat}] .count")


def _shown(page):
    return page.locator("[data-preset]").evaluate_all("(els) => els.map((e) => e.dataset.preset)")


def _called(page, method, count=1):
    page.wait_for_function(
        "([m, n]) => window.__mock.calls.filter((c) => c[0] === m).length === n", arg=[method, count])


def test_groups_counts_and_the_on_chu2_badge(open_app):
    page = open_app()
    _open(page)
    assert [_count(page, c) for c in ("all", "official", "gaming", "music", "movies", "calls", "mine",
                                      "favourites")] == ["7", "1", "2", "2", "1", "1", "1", "0"]
    page.click("[data-test=cat-gaming]")
    assert _shown(page) == ["scene:gaming", "scene:fps"]
    page.click("[data-test=cat-mine]")
    assert page.inner_text("[data-preset='mine:night-drive'] [data-test=on-chu2]") == "On CHU 2"


def test_search_by_name_or_tag(open_app):
    page = open_app()
    _open(page)
    page.fill("[data-test=preset-search]", "cine")
    assert _shown(page) == ["scene:movies"]
    page.fill("[data-test=preset-search]", "calls")
    assert _shown(page) == ["scene:calls"]


def test_apply_plays_the_preset_and_closes(open_app, calls):
    page = open_app()
    _open(page)
    page.click("[data-preset='scene:calls']")
    assert "voices on calls are clearer" in page.inner_text("[data-test=preset-preview]")
    page.click("[data-test=preset-apply]")
    _called(page, "apply_preset")
    assert calls(page, "apply_preset") == [["scene:calls"]]
    assert page.locator("[data-test=preset-sheet]").count() == 0
    page.wait_for_selector(".toast:has-text('\"Calls\" is playing.')")


def test_apply_and_save_opens_the_save_confirm(open_app):
    page = open_app()
    _open(page)
    page.click("[data-preset='scene:fps']")
    page.click("[data-test=preset-apply-save]")
    page.wait_for_selector("[data-test=save-panel][data-phase=confirm]")


def test_keys_move_favourite_and_apply(open_app, calls):
    page = open_app()
    page.keyboard.press("Control+p")
    page.wait_for_selector("[data-preset='official:flat'][aria-selected=true]")
    page.keyboard.press("ArrowRight")
    page.wait_for_selector("[data-preset='scene:music'][aria-selected=true]")
    page.keyboard.press("f")
    _called(page, "set_favourite")
    assert calls(page, "set_favourite") == [["scene:music", True]]
    page.wait_for_function("document.querySelector('[data-test=cat-favourites] .count').textContent === '1'")
    page.keyboard.press("Enter")
    _called(page, "apply_preset")
    assert calls(page, "apply_preset") == [["scene:music"]]


def test_save_current_then_rename_and_delete(open_app, calls):
    page = open_app()
    _open(page)
    page.click("[data-test=save-current]")
    page.fill("[data-test=save-preset-name]", "Evening")
    page.check("[data-test=save-tag-music]")
    page.click("[data-test=save-preset-confirm]")
    _called(page, "save_preset")
    assert calls(page, "save_preset") == [["Evening", ["Music"]]]
    page.wait_for_selector("[data-preset='mine:evening'][aria-selected=true]")
    page.click("[data-test=preset-rename]")
    page.fill("[data-test=rename-name]", "Evening 2")
    page.press("[data-test=rename-name]", "Enter")
    _called(page, "rename_preset")
    page.click("[data-test=preset-delete]")
    assert page.inner_text("[data-test=preset-delete]").strip() == "Click again to delete"
    page.click("[data-test=preset-delete]")
    _called(page, "delete_preset")
    assert calls(page, "delete_preset") == [["mine:evening"]]


def test_escape_closes(open_app):
    page = open_app()
    _open(page)
    page.keyboard.press("Escape")
    page.wait_for_selector("[data-test=preset-sheet]", state="detached")
