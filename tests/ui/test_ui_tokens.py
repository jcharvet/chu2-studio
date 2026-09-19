"""Design tokens, bundled fonts and icons, focus ring, reduced motion (brief §5, §6).

    python -m pytest -q tests/ui/test_ui_tokens.py
"""

ICONS = ("usb", "plugs-connected", "power", "floppy-disk", "arrow-counter-clockwise",
         "clock-counter-clockwise", "eye", "eye-slash", "warning", "info", "check", "x",
         "headphones", "question", "arrow-u-up-left", "arrow-u-up-right",
         "books", "share-network", "gear-six", "star", "star-fill", "magnifying-glass",
         "copy", "trash", "pencil-simple", "folder-open", "download-simple")


def _var(page, name):
    return page.evaluate("(n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim()",
                         name)


def test_palette_matches_the_brief(open_app):
    page = open_app()
    expected = {"--bg": "#0A0B0F", "--plate": "#0E1016", "--surface": "#13151C", "--raised": "#1B1E27",
                "--text": "#F0EEE9", "--jade": "#91E7C2", "--amber": "#FFB45B", "--warn": "#FF6F6F",
                "--amethyst": "#A99BFF", "--stone": "#8F8B84", "--slate": "#767987"}
    assert {name: _var(page, name) for name in expected} == expected


def test_bundled_fonts_load_without_network(open_app):
    page = open_app()
    loaded = page.evaluate("""async () => {
        const out = {};
        for (const f of ['16px Inter', '16px Newsreader', '12px "JetBrains Mono"']) {
            out[f] = (await document.fonts.load(f)).length;
        }
        return out;
    }""")
    assert all(count >= 1 for count in loaded.values()), loaded
    assert "Inter" in page.evaluate("getComputedStyle(document.body).fontFamily")


def test_icons_and_licences_are_bundled(open_app, ui_url):
    page = open_app()
    for name in ICONS:
        response = page.request.get(f"{ui_url}/icons/{name}.svg")
        assert response.ok and "currentColor" in response.text(), name
    for path in ("icons/LICENSE-phosphor.txt", "fonts/OFL-Inter.txt", "fonts/OFL-Newsreader.txt",
                 "fonts/OFL-JetBrainsMono.txt", "vendor/LICENSE-vue.txt"):
        assert page.request.get(f"{ui_url}/{path}").ok, path
    page.evaluate("document.body.insertAdjacentHTML('beforeend', '<span id=probe class=\"icon i-usb\"></span>')")
    assert "usb.svg" in page.evaluate("getComputedStyle(document.getElementById('probe')).maskImage")


def test_keyboard_focus_shows_the_porcelain_ring(open_app):
    page = open_app()
    page.evaluate("document.body.insertAdjacentHTML('afterbegin', '<button id=probe class=btn>Probe</button>')")
    page.keyboard.press("Tab")
    style = page.evaluate("""() => { const s = getComputedStyle(document.activeElement);
        return [document.activeElement.id, s.outlineStyle, s.outlineWidth, s.outlineColor]; }""")
    assert style == ["probe", "solid", "2px", "rgb(240, 238, 233)"]


def test_reduced_motion_turns_durations_off(open_app):
    assert _var(open_app(), "--dur-base") == "180ms"
    assert _var(open_app(reduced_motion="reduce"), "--dur-base") == "0ms"
