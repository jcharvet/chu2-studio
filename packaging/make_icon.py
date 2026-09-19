"""Draw the app icon and write ``packaging/icon.ico``.

    pip install -e ".[dev]" && python -m playwright install chromium
    python -m pip install pillow
    python packaging/make_icon.py

The mark is "C2" from the project's wordmark: off-white C, purple 2, on the
navy plate, set in Inter (the font the page already bundles). Each size is
drawn on its own instead of shrinking one big image, and the small ones drop
the superscript, which is mud below 48 px. The ``.ico`` is committed, so a
normal build never runs this script.
"""

from __future__ import annotations

import base64
import io
import os

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, "src", "chu2", "app", "ui", "fonts", "InterVariable.woff2")
ICO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
PNG = os.path.join(ROOT, "docs", "images", "icon.png")

NAVY, INK, PURPLE = "#171F67", "#F7F4EF", "#AD21C4"
SIZES = (256, 128, 64, 48, 32, 16)
SMALL = 48  # at or below this, the "2" is dropped and the C grows


def markup(size: int, font: str) -> str:
    """The icon at ``size`` pixels as a whole page."""
    plain = size <= SMALL
    c_size = round(size * (0.74 if plain else 0.64))
    two = "" if plain else (
        f'<span style="color:{PURPLE};font-size:{round(size * 0.30)}px;'
        f'margin-top:{round(size * 0.08)}px">2</span>')
    return f"""<style>
      @font-face {{ font-family: Inter; src: url(data:font/woff2;base64,{font}) format('woff2');
                    font-weight: 100 900 }}
      html, body {{ margin: 0; width: {size}px; height: {size}px; background: transparent }}
      .plate {{ width: {size}px; height: {size}px; background: {NAVY};
                border-radius: {round(size * 0.22)}px; display: flex; align-items: center;
                justify-content: center; font-family: Inter, sans-serif }}
      .mark {{ display: flex; align-items: flex-start; line-height: 1; font-weight: 800 }}
      .c {{ color: {INK}; font-size: {c_size}px; letter-spacing: -0.03em }}
    </style>
    <div class="plate"><div class="mark"><span class="c">C</span>{two}</div></div>"""


def frames() -> list:
    with open(FONT, "rb") as handle:
        font = base64.b64encode(handle.read()).decode()
    images = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for size in SIZES:
            page = browser.new_page(viewport={"width": size, "height": size})
            page.set_content(markup(size, font))
            page.wait_for_timeout(200)
            shot = page.screenshot(omit_background=True)  # the plate's corners stay see-through
            images.append(Image.open(io.BytesIO(shot)).convert("RGBA"))
            page.close()
        browser.close()
    return images


def main() -> None:
    images = frames()
    images[0].save(ICO, format="ICO", sizes=[(i.width, i.height) for i in images],
                   append_images=images[1:])
    os.makedirs(os.path.dirname(PNG), exist_ok=True)
    images[0].save(PNG)  # 256 px, for the README and the About box
    print("wrote", ICO, "and", PNG)


if __name__ == "__main__":
    main()
