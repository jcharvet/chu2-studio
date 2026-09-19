"""The page talks to Python through window.pywebview.api and window.chu2.onEvent.

    python -m pytest -q tests/ui/test_ui_shell.py
"""


def test_page_loads_the_state_from_python(open_app, calls):
    page = open_app()
    assert calls(page, "get_state") == [[]]
    assert page.inner_text("[data-test=device-chip]").strip() == "CHU 2 DSP"
    assert page.locator("fieldset[data-band]").count() == 5
    assert page.input_value("[data-band='2'] [data-test=frequency]") == "200"


def test_pushed_state_updates_the_page(open_app):
    page = open_app({"connected": False})
    page.wait_for_selector("[data-test=no-device]")
    page.evaluate("window.__mock.push({connected: true})")
    page.wait_for_selector("[data-test=device-chip]:has-text('CHU 2 DSP')")


def test_an_older_snapshot_is_ignored(open_app):
    page = open_app()
    page.evaluate("""() => {
        const newer = window.__mock.push({connected: false});
        window.chu2.onEvent('state', Object.assign({}, newer, {rev: newer.rev - 1, connected: true}));
    }""")
    assert page.inner_text("[data-test=device-chip]").strip() == "CHU 2 not connected"


def test_band_edits_are_throttled_and_the_last_value_is_sent(open_app, calls):
    page = open_app()
    page.evaluate("""async () => {
        const store = await import('./store.js');
        for (let g = 1; g <= 20; g++) {
            store.setBand(0, {type: 'peaking', frequency: 40, gain: -g / 10, q: 0.5, bypass: false});
        }
        await store.flushEdits();
    }""")
    sent = calls(page, "set_band")
    assert 1 <= len(sent) <= 2 and sent[-1] == [0, {"type": "peaking", "frequency": 40,
                                                     "gain": -2, "q": 0.5, "bypass": False}]


def test_save_sends_waiting_edits_first(open_app):
    page = open_app()
    page.evaluate("""async () => {
        const store = await import('./store.js');
        store.setBand(2, {type: 'peaking', frequency: 1000, gain: 3, q: 1, bypass: false});
        await store.save();
    }""")
    methods = page.evaluate("window.__mock.calls.map((c) => c[0])")
    assert methods[-2:] == ["set_band", "save"]


def test_one_band_is_never_sent_twice_at_once(open_app, calls):
    page = open_app()
    page.evaluate("window.__mock.delayMs = 120")  # Python answers slower than the throttle
    page.evaluate("""async () => {
        const store = await import('./store.js');
        for (let g = 1; g <= 10; g++) {
            store.setBand(0, {type: 'peaking', frequency: 40, gain: -g / 10, q: 0.5, bypass: false});
            await new Promise((r) => setTimeout(r, 30));
        }
        await store.flushEdits();
    }""")
    assert page.evaluate("window.__mock.overlap") is False
    assert calls(page, "set_band")[-1][1]["gain"] == -1
    assert page.evaluate("window.__mock.state().design[0].gain") == -1
    assert page.evaluate("async () => (await import('./store.js')).state.design[0].gain") == -1


def test_a_module_that_fails_to_load_is_retried(open_app):
    refused = []

    def refuse_once(route):
        if refused:
            route.continue_()
        else:
            refused.append(route.request.url)
            route.abort("connectionrefused")

    page = open_app(before_goto=lambda p: p.route("**/format.js", refuse_once))
    assert refused  # the first load failed; open_app waited until the reloaded page was ready
    assert page.evaluate("sessionStorage.getItem('chu2-reloads')") == "1"
