"""The canvas graph: drag, wheel and keys edit a band within the CHU 2's limits.

    python -m pytest -q tests/ui/test_ui_graph.py
"""


def _node(page, n):
    box = page.locator(f"[data-node='{n}']").bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _settle(page):
    """Send what the 50 ms throttle still holds and wait for the answers."""
    page.evaluate("async () => (await import('./store.js')).flushEdits()")


def _last(page, calls, index):
    sent = [args[1] for args in calls(page, "set_band") if args[0] == index]
    return sent[-1] if sent else None


def test_nodes_sit_at_their_frequency_and_gain(open_app):
    page = open_app()
    xs = [_node(page, n)[0] for n in range(1, 6)]
    assert xs == sorted(xs)  # 40 Hz ... 9 kHz, left to right
    assert _node(page, 2)[1] > _node(page, 1)[1]  # -6 dB sits lower than -1.5 dB
    assert page.get_attribute("[data-node='2']", "aria-label") == \
        "Band 2, Peak, 200 hertz, minus 6.0 decibels, Q 0.60"


def test_dragging_a_node_up_raises_its_gain(open_app, calls):
    page = open_app()
    x, y = _node(page, 3)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x, y - 60, steps=6)
    page.mouse.up()
    _settle(page)
    band = _last(page, calls, 2)
    assert band["gain"] > -2.5 and band["frequency"] == 1400


def test_a_fast_drag_is_throttled_and_ends_on_the_last_value(open_app, calls):
    page = open_app()
    x, y = _node(page, 2)
    page.mouse.move(x, y)
    page.mouse.down()
    for k in range(1, 31):
        page.mouse.move(x + k, y - k)
    page.mouse.up()
    _settle(page)
    sent = [args[1] for args in calls(page, "set_band") if args[0] == 1]
    assert 1 <= len(sent) < 30
    assert sent[-1] == page.evaluate("async () => (await import('./store.js')).state.design[1]")


def test_arrow_keys_move_frequency_and_gain(open_app, calls):
    page = open_app()
    page.focus(".graph")
    page.keyboard.press("2")
    page.keyboard.press("ArrowRight")
    _settle(page)
    assert _last(page, calls, 1)["frequency"] == 206  # 200 Hz x 2^(1/24)
    page.keyboard.press("Shift+ArrowUp")
    _settle(page)
    assert _last(page, calls, 1)["gain"] == -5.0
    page.keyboard.press("ArrowDown")
    _settle(page)
    assert _last(page, calls, 1)["gain"] == -5.1


def test_wheel_over_a_node_changes_q_and_elsewhere_does_nothing(open_app, calls):
    page = open_app()
    x, y = _node(page, 4)
    page.mouse.move(x, y)
    page.mouse.wheel(0, -100)
    _settle(page)
    assert _last(page, calls, 3)["q"] == round(2 ** (1 / 6), 3)
    before = len(calls(page, "set_band"))
    box = page.locator(".graph").bounding_box()
    page.mouse.move(box["x"] + 70, box["y"] + 30)  # empty top-left of the plot
    page.mouse.wheel(0, -100)
    _settle(page)
    assert len(calls(page, "set_band")) == before


def test_values_stay_inside_the_limits(open_app, calls):
    page = open_app()
    x, y = _node(page, 5)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(1278, 2, steps=8)  # far past 20 kHz and +15 dB
    page.mouse.up()
    _settle(page)
    band = _last(page, calls, 4)
    assert band["frequency"] == 20000 and band["gain"] == 12
    page.focus(".graph")
    page.keyboard.press("1")
    for _ in range(40):
        page.keyboard.press("Shift+ArrowLeft")
    for _ in range(30):
        page.keyboard.press("Shift+ArrowDown")
    for _ in range(40):
        page.keyboard.press("PageUp")
    _settle(page)
    assert _last(page, calls, 0) == {"type": "peaking", "frequency": 20, "gain": -12, "q": 10,
                                     "bypass": False}
    for _ in range(80):
        page.keyboard.press("PageDown")
    _settle(page)
    assert _last(page, calls, 0)["q"] == 0.1


def test_keys_cycle_type_bypass_and_reset(open_app, calls):
    page = open_app()
    page.focus(".graph")
    page.keyboard.press("3")
    page.keyboard.press("t")
    _settle(page)
    assert _last(page, calls, 2)["type"] == "low_shelf"
    page.keyboard.press("b")
    _settle(page)
    assert _last(page, calls, 2)["bypass"] is True
    page.keyboard.press("0")
    _settle(page)
    assert _last(page, calls, 2)["gain"] == 0


def test_the_selected_band_is_announced(open_app):
    page = open_app()
    page.focus(".graph")
    page.keyboard.press("2")
    page.wait_for_function(
        "document.querySelector('[data-test=graph-live]').textContent.startsWith('Band 2, Peak, 200 hertz')")
