"""Undo / Redo (brief §3.4, §3.7): top-bar buttons, Ctrl+Z / Ctrl+Y; a whole drag is one step.

    python -m pytest -q tests/ui/test_ui_undo.py
"""


def _settle(page):
    page.evaluate("async () => (await import('./store.js')).flushEdits()")


def _design(page):
    return page.evaluate("async () => (await import('./store.js')).state.design")


def _node(page, n):
    box = page.locator(f"[data-node='{n}']").bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _set_design_calls(page, count):
    page.wait_for_function(
        "(n) => window.__mock.calls.filter((c) => c[0] === 'set_design').length === n", arg=count)


def test_a_whole_drag_is_one_undo_step(open_app, calls):
    page = open_app()
    before = _design(page)
    assert page.is_disabled("[data-test=undo]") and page.is_disabled("[data-test=redo]")
    x, y = _node(page, 3)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x, y - 60, steps=6)
    page.mouse.up()
    _settle(page)
    dragged = _design(page)
    assert dragged[2]["gain"] > before[2]["gain"]
    page.click("[data-test=undo]")
    _set_design_calls(page, 1)
    assert calls(page, "set_design")[-1] == [before, "My EQ", None] and _design(page) == before
    assert page.is_disabled("[data-test=undo]")
    page.click("[data-test=redo]")
    _set_design_calls(page, 2)
    assert calls(page, "set_design")[-1] == [dragged, "My EQ", None] and _design(page) == dragged


def test_ctrl_z_and_ctrl_y(open_app, calls):
    page = open_app()
    before = _design(page)
    page.focus(".graph")
    page.keyboard.press("2")
    page.keyboard.press("Shift+ArrowUp")
    _settle(page)
    page.keyboard.press("Control+z")
    _set_design_calls(page, 1)
    assert calls(page, "set_design")[-1] == [before, "My EQ", None]
    page.keyboard.press("Control+y")
    _set_design_calls(page, 2)
    assert calls(page, "set_design")[-1][0][1]["gain"] == -5.0


def test_edits_to_different_bands_are_separate_steps(open_app):
    page = open_app()
    page.fill("[data-band='1'] [data-test=gain]", "-3")
    page.press("[data-band='1'] [data-test=gain]", "Enter")
    page.fill("[data-band='4'] [data-test=gain]", "1")
    page.press("[data-band='4'] [data-test=gain]", "Enter")
    _settle(page)
    page.click("[data-test=undo]")
    _set_design_calls(page, 1)
    design = _design(page)
    assert design[0]["gain"] == -3 and design[3]["gain"] == -4.8


def test_reset_all_is_undone_through_the_same_history(open_app, calls):
    page = open_app()
    before = _design(page)
    page.click("[data-test=reset-all]")
    page.wait_for_selector(".toast [data-test=toast-action]")
    assert not page.is_disabled("[data-test=undo]")
    page.click(".toast [data-test=toast-action]")
    _set_design_calls(page, 1)
    assert calls(page, "set_design")[-1] == [before, "My EQ", None]
    assert not page.is_disabled("[data-test=redo]")


def test_ctrl_z_in_a_text_field_is_left_to_the_field(open_app, calls):
    page = open_app()
    page.fill("[data-band='2'] [data-test=frequency]", "250")
    page.press("[data-band='2'] [data-test=frequency]", "Control+z")
    page.wait_for_timeout(200)
    assert calls(page, "set_design") == []
