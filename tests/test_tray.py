"""The tray icon (chu2.app.tray), with a stand-in for pystray.

    python -m pytest -q tests/test_tray.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chu2.app import tray  # noqa: E402


class _FakePystray:
    """Enough of pystray to drive the menu without a desktop."""

    SEPARATOR = "----"

    class Menu:
        SEPARATOR = "----"

        def __init__(self, *items):
            self.items = list(items)

    class MenuItem:
        def __init__(self, text, action, checked=None, default=False):
            self.text, self.action, self.checked, self.default = text, action, checked, default

    class Icon:
        def __init__(self, name, image, title, menu):
            self.name, self.image, self.title, self.menu = name, image, title, menu
            self.running = False
            self.notified = []

        def run(self):
            self.running = True

        def stop(self):
            self.running = False

        def notify(self, message, title=None):
            self.notified.append(message)


def _tray(state):
    return tray.Tray(on_show=lambda: state.append("show"),
                     on_quit=lambda: state.append("quit"),
                     clicking_stopped=lambda: state[0],
                     set_clicking_stopped=lambda on: state.__setitem__(0, on),
                     backend=_FakePystray)


def _item(icon, text):
    return next(i for i in icon.menu.items if getattr(i, "text", None) == text)


def test_the_menu_shows_quits_and_carries_the_clicking_switch():
    state = [False]
    t = _tray(state)
    assert t.start() is True
    icon = t._icon

    _item(icon, "Show CHU 2 Studio").action()
    assert "show" in state

    toggle = _item(icon, "Stop the click before every sound")
    assert toggle.checked(toggle) is False
    toggle.action()
    assert state[0] is True and toggle.checked(toggle) is True
    toggle.action()
    assert state[0] is False

    _item(icon, "Quit").action()
    assert "quit" in state and t._icon is None, "Quit must take the icon down too"


def test_the_first_hide_explains_itself_once():
    state = [False]
    t = _tray(state)
    t.start()
    t.notify("still here")
    assert t._icon.notified == ["still here"]
    t.stop()
    t.notify("ignored once it is gone")  # must not raise after stop


def test_a_machine_without_a_tray_is_not_an_error():
    class Broken:
        def __getattr__(self, name):
            raise RuntimeError("no desktop")

    t = tray.Tray(lambda: None, lambda: None, lambda: False, lambda on: None, backend=Broken())
    assert t.start() is False


def test_the_icon_file_is_found_or_one_is_drawn():
    t = tray.Tray(lambda: None, lambda: None, lambda: False, lambda on: None,
                  backend=_FakePystray)
    image = t._image()
    assert image.size[0] > 0, "an icon must always come back, even with no .ico"
