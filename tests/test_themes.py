"""Every theme in ui/tokens.css is readable (WCAG 2.x contrast, brief §5.1, §6).

    python -m pytest -q tests/test_themes.py
"""

import os
import re

from chu2.store import THEMES

TOKENS = os.path.join(os.path.dirname(__file__), "..", "src", "chu2", "app", "ui", "tokens.css")
BACKGROUNDS = ("bg", "surface", "raised", "plate")


def _themes():
    css = open(TOKENS, encoding="utf-8").read()
    blocks = {}
    for match in re.finditer(r'(?::root, )?\[data-theme="(\w+)"\]\s*\{([^}]*)\}', css):
        values = dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6}|\d+, \d+, \d+)\s*;", match.group(2)))
        blocks[match.group(1)] = values
    return blocks


def _luminance(value):
    if value.startswith("#"):
        rgb = [int(value[i:i + 2], 16) for i in (1, 3, 5)]
    else:
        rgb = [int(x) for x in value.split(",")]
    lin = [(c / 255) / 12.92 if c / 255 <= 0.04045 else ((c / 255 + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_there_is_one_colour_block_per_theme():
    assert sorted(_themes()) == sorted(THEMES)


def test_text_is_readable_everywhere():
    for name, t in _themes().items():
        for fg in ("text", "text-2", "text-3", "jade-ink", "amber-ink", "warn-ink"):
            for bg in BACKGROUNDS:
                assert contrast(t[fg], t[bg]) >= 4.5, (name, fg, bg, round(contrast(t[fg], t[bg]), 2))


def test_curves_and_marks_stand_out_on_the_graph():
    for name, t in _themes().items():
        for fg in ("jade", "amber", "warn", "amethyst", "stone", "slate"):
            assert contrast(t[fg], t["plate"]) >= 3.0, (name, fg, round(contrast(t[fg], t["plate"]), 2))


def test_text_on_the_green_button_and_the_amber_selection():
    for name, t in _themes().items():
        assert contrast(t["on-jade"], t["jade"]) >= 4.5, (name, "on-jade")
        assert contrast(t["on-amber"], t["amber"]) >= 4.5, (name, "on-amber")


def test_rgb_triplets_match_their_colours():
    for name, t in _themes().items():
        for rgb, hex_name in (("bg-rgb", "bg"), ("text-rgb", "text"), ("jade-rgb", "jade"),
                              ("amber-rgb", "amber"), ("warn-rgb", "warn"), ("amethyst-rgb", "amethyst")):
            expected = ", ".join(str(int(t[hex_name][i:i + 2], 16)) for i in (1, 3, 5))
            assert t[rgb] == expected, (name, rgb)
