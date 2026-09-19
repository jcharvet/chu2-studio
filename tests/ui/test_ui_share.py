"""Import & share (brief S7).

    python -m pytest -q tests/ui/test_ui_share.py
"""


def _called(page, method, count=1):
    page.wait_for_function(
        "([m, n]) => window.__mock.calls.filter((c) => c[0] === m).length === n", arg=[method, count])


def _statuses(page):
    return page.locator("[data-test=preview-table] tbody tr td:last-child").all_inner_texts()


def test_import_file_shows_a_preview_then_imports(open_app, calls):
    page = open_app()
    page.keyboard.press("Control+i")
    page.click("[data-test=choose-file]")
    page.wait_for_selector("[data-test=import-preview]")
    assert page.inner_text("[data-test=preview-summary]") == (
        "HD 600 ParametricEQ · Equalizer APO / AutoEq text · 7 filters · Preamp −6.2 dB")
    assert _statuses(page) == ["fits", "fits", "not kept (5 bands)", "fits", "fits", "not kept (5 bands)", "fits"]
    assert page.locator("[data-test=preview-table] tr.row-off").count() == 2
    assert "keeping the 5 largest" in page.inner_text("[data-test=preview-notes]")
    assert calls(page, "set_design") == []  # nothing changes before "Import to editor"
    page.click("[data-test=import-apply]")
    _called(page, "set_design")
    [[bands, name, quick]] = calls(page, "set_design")
    assert name == "HD 600 ParametricEQ" and quick is None
    assert [b["frequency"] for b in bands] == [105, 180, 3200, 5800, 10000]
    assert page.locator("[data-test=share-dialog]").count() == 0
    page.wait_for_selector(".toast:has-text('Imported \"HD 600 ParametricEQ\"')")
    page.keyboard.press("Control+z")  # the import is one undo step
    page.wait_for_function("window.__mock.calls.filter((c) => c[0] === 'set_design').length === 2")


def test_cancelled_open_dialog_changes_nothing(open_app):
    page = open_app()
    page.evaluate("window.__mock.cancelDialog = true")
    page.click("[data-test=open-share]")
    page.click("[data-test=choose-file]")
    _called(page, "import_file")
    assert page.locator("[data-test=import-preview], [data-test=import-error]").count() == 0


def test_paste_reads_text_and_shows_errors(open_app, mock_library):
    page = open_app()
    page.keyboard.press("Control+i")
    page.click("[data-test=tab-paste]")
    page.fill("[data-test=paste-text]", "hello")
    page.click("[data-test=paste-read]")
    page.wait_for_selector("[data-test=import-error]:has-text('No EQ filters were found')")
    page.fill("[data-test=paste-text]", mock_library["apo_text"])
    page.click("[data-test=paste-read]")
    page.wait_for_selector("[data-test=import-preview]")
    assert page.locator("[data-test=import-error]").count() == 0


def test_dropped_file_opens_the_preview(open_app, calls, mock_library):
    page = open_app()
    text = mock_library["apo_text"]
    page.evaluate("""(text) => {
        const dt = new DataTransfer();
        dt.items.add(new File([text], "HD 600 ParametricEQ.txt", { type: "text/plain" }));
        window.dispatchEvent(new DragEvent("drop", { dataTransfer: dt, bubbles: true, cancelable: true }));
    }""", text)
    page.wait_for_selector("[data-test=share-dialog] [data-test=import-preview]")
    assert calls(page, "import_text") == [[text, "HD 600 ParametricEQ.txt"]]


def test_pasted_share_code_opens_the_paste_tab(open_app, mock_library):
    page = open_app()
    code = mock_library["share"]["code"]
    page.evaluate("""(code) => {
        const dt = new DataTransfer();
        dt.setData("text/plain", "try this: " + code);
        document.body.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    }""", code)
    page.wait_for_selector("[data-test=tab-paste][aria-selected=true]")
    page.wait_for_selector("[data-test=import-preview]")
    assert page.input_value("[data-test=paste-text]") == "try this: " + code
    assert page.inner_text("[data-test=preview-summary]").startswith("FPS · Share code · 5 filters")


def test_export_saves_through_the_dialog(open_app, calls):
    page = open_app()
    page.keyboard.press("Control+i")
    page.click("[data-test=tab-export]")
    page.click("[data-test=export-apo]")
    page.wait_for_selector(".toast:has-text('Saved Documents/My EQ.txt')")
    page.click("[data-test=export-json]")
    _called(page, "export_file", 2)
    assert calls(page, "export_file") == [["apo"], ["json"]]


def test_share_code_copies(open_app, mock_library):
    page = open_app()
    page.keyboard.press("Control+Shift+S")
    page.wait_for_selector("[data-test=tab-share][aria-selected=true]")
    page.wait_for_function("document.querySelector('[data-test=share-code]').value.startsWith('CHU2-1.')")
    assert page.input_value("[data-test=share-code]") == mock_library["share"]["code"]
    assert page.locator("[data-test=save-panel]").count() == 0  # Ctrl+Shift+S is not Save
    page.click("[data-test=copy-code]")
    page.wait_for_selector(".toast:has-text('Copied.')")
    assert page.evaluate("navigator.clipboard.readText()") == mock_library["share"]["code"]


def test_escape_closes_and_clears_the_preview(open_app):
    page = open_app()
    page.keyboard.press("Control+i")
    page.click("[data-test=choose-file]")
    page.wait_for_selector("[data-test=import-preview]")
    page.keyboard.press("Escape")
    page.wait_for_selector("[data-test=share-dialog]", state="detached")
    page.keyboard.press("Control+i")
    assert page.locator("[data-test=import-preview]").count() == 0
