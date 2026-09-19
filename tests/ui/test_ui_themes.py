"""Themes (Settings): the page and the canvas graph follow the chosen theme.

    python -m pytest -q tests/ui/test_ui_themes.py
"""

PLATE_PIXEL = """() => {
    const canvas = document.querySelector('.graph-canvas');
    const dpr = window.devicePixelRatio || 1;
    const px = canvas.getContext('2d').getImageData(Math.round(52 * dpr), Math.round(22 * dpr), 1, 1).data;
    return '#' + [px[0], px[1], px[2]].map((v) => v.toString(16).padStart(2, '0')).join('').toUpperCase();
}"""


def _var(page, name):
    return page.evaluate("(n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim()", name)


def test_the_saved_theme_is_used_from_the_start(open_app):
    page = open_app({"settings": {"theme": "mocha", "confirm_save": True}})
    assert page.evaluate("document.documentElement.dataset.theme") == "mocha"
    assert _var(page, "--bg") == "#11111B"
    page.wait_for_function(f"({PLATE_PIXEL})() === '#181825'")  # mocha's graph plate


def test_changing_the_theme_recolours_the_graph(open_app):
    page = open_app()
    page.wait_for_function(f"({PLATE_PIXEL})() === '#0E1016'")  # atelier
    page.evaluate("window.__mock.push({settings: {theme: 'porcelain', confirm_save: true}})")
    page.wait_for_function(f"({PLATE_PIXEL})() === '#F8F6F2'")
    assert _var(page, "--text") == "#1E2027"
