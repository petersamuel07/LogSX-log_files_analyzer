#!/usr/bin/env python
"""Derive every LogSX brand asset from a single background-removed master logo.

The repo keeps exactly two hand-made files in `assets/` — `logo.png` (the
background-removed master) and `logo-on-white.png` (the flattened original).
Everything else the project displays is generated from the master by this
script, so the artwork can never drift between the GUI, the exe icon, the
README, and the docs site: regenerate and every surface moves together.

What it produces (all committed, so contributors never need to run this):

    assets/mark.png             icon only, dark ink   — for light backgrounds
    assets/mark-on-dark.png     icon only, light ink  — for dark backgrounds
    assets/logo-on-dark.png     full lockup, light ink
    assets/icon.ico             multi-resolution Windows icon (exe + GUI window)
    docs/assets/*.png           web-sized copies of the above + a social card
    docs/favicon.ico            real favicon, replacing the emoji placeholder

The composite master stacks an icon over a "LogSX / LOG FILES ANALYZER"
wordmark. The GUI header and the site nav already render that text as live
type, so pairing them with the full lockup would say it twice — those surfaces
want the icon alone. Rather than hard-coding a crop ratio that a re-exported
logo would silently break, `split_lockup()` finds the blank horizontal band
between the two halves and cuts there.

Usage:
    python scripts/build_assets.py
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError as exc:  # pragma: no cover - developer tooling
    sys.exit(f"Missing dependency ({exc.name}). Run: pip install -r requirements.txt")

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSETS = REPO_ROOT / "assets"
DOCS_ASSETS = REPO_ROOT / "docs" / "assets"

MASTER = ASSETS / "logo.png"
MASTER_ON_WHITE = ASSETS / "logo-on-white.png"

# Ink colours mirror the palette in docs/index.html so the artwork sits on the
# page as if it were typeset with it, rather than as pasted-in pure black/white.
INK_DARK = (21, 24, 29)       # --ink        (draw on light backgrounds)
INK_LIGHT = (236, 232, 221)   # dark --ink   (draw on dark backgrounds)
PAPER = (251, 249, 244)       # --paper-raised

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
FAVICON_SIZES = (16, 32, 48)
ALPHA_FLOOR = 8               # treat near-transparent pixels as empty

# Social cards are a fixed 1200x630; the logo is inset so no platform's
# rounded-corner crop can clip it.
OG_SIZE = (1200, 630)
OG_LOGO_BOX = (760, 430)


def load_master() -> Image.Image:
    """Load the background-removed master, or explain what's missing."""
    if not MASTER.is_file():
        sys.exit(
            f"Missing {MASTER.relative_to(REPO_ROOT)}.\n"
            "Save the background-removed logo there (and the white-background\n"
            f"version as {MASTER_ON_WHITE.relative_to(REPO_ROOT)}), then re-run."
        )

    logo = Image.open(MASTER).convert("RGBA")
    if np.array(logo.getchannel("A")).min() > 250:
        sys.exit(
            f"{MASTER.relative_to(REPO_ROOT)} has no transparency — it looks like the\n"
            "white-background version. assets/logo.png must be the background-removed\n"
            "file, otherwise every derived asset gets a white box behind it."
        )
    return trim(logo)


def trim(img: Image.Image) -> Image.Image:
    """Crop away fully transparent margins."""
    bbox = img.getchannel("A").getbbox()
    return img.crop(bbox) if bbox else img


def split_lockup(logo: Image.Image) -> tuple[Image.Image, Image.Image]:
    """Split the stacked lockup into (icon, wordmark) at the gap between them.

    Finds every run of blank pixel rows, keeps the runs that sit in the middle
    of the image (so the gap inside the icon's own artwork or the one above
    the tagline rule can't win), and cuts at the middle of the tallest.
    """
    ink_rows = (np.array(logo.getchannel("A")) > ALPHA_FLOOR).any(axis=1)
    height = len(ink_rows)

    runs: list[tuple[int, int]] = []
    start: int | None = None
    for y, has_ink in enumerate(ink_rows):
        if not has_ink and start is None:
            start = y
        elif has_ink and start is not None:
            runs.append((start, y))
            start = None

    interior = [(a, b) for a, b in runs if 0.30 < ((a + b) / 2) / height < 0.80]
    if not interior:
        raise ValueError(
            "Could not find the blank band between the icon and the wordmark. "
            "If the master logo's layout changed, adjust split_lockup()."
        )

    top, bottom = max(interior, key=lambda run: run[1] - run[0])
    cut = (top + bottom) // 2
    width = logo.width
    return trim(logo.crop((0, 0, width, cut))), trim(logo.crop((0, cut, width, logo.height)))


def recolour(img: Image.Image, rgb: tuple[int, int, int]) -> Image.Image:
    """Repaint the artwork in `rgb`, keeping its original alpha (anti-aliasing included)."""
    solid = Image.new("RGBA", img.size, (*rgb, 255))
    solid.putalpha(img.getchannel("A"))
    return solid


def squared(img: Image.Image, margin: float = 0.07) -> Image.Image:
    """Centre the artwork on a transparent square so icon sizes don't distort it."""
    side = round(max(img.size) * (1 + margin * 2))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
    return canvas


def scaled_to(img: Image.Image, box: tuple[int, int]) -> Image.Image:
    """Scale the artwork to fit inside `box` without changing its aspect ratio."""
    copy = img.copy()
    copy.thumbnail(box, Image.LANCZOS)
    return copy


def save(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)
    print(f"  {path.relative_to(REPO_ROOT).as_posix():<34} {img.width}x{img.height}")


def save_ico(img: Image.Image, path: Path, sizes: tuple[int, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Pillow builds every requested size from the one image it is handed, so
    # start from the largest square: downscaling stays sharp, upscaling doesn't.
    largest = max(sizes)
    source = squared(img).resize((largest, largest), Image.LANCZOS)
    source.save(path, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"  {path.relative_to(REPO_ROOT).as_posix():<34} {', '.join(f'{s}px' for s in sizes)}")


def build_social_card(logo_on_light: Image.Image) -> Image.Image:
    """Centre the dark-ink lockup on a paper-coloured 1200x630 card."""
    card = Image.new("RGBA", OG_SIZE, (*PAPER, 255))
    art = scaled_to(logo_on_light, OG_LOGO_BOX)
    card.paste(art, ((OG_SIZE[0] - art.width) // 2, (OG_SIZE[1] - art.height) // 2), art)
    return card.convert("RGB")


def main() -> None:
    master = load_master()
    print(f"Master: {MASTER.relative_to(REPO_ROOT).as_posix()} ({master.width}x{master.height})")

    if not MASTER_ON_WHITE.is_file():
        print(f"Note: {MASTER_ON_WHITE.relative_to(REPO_ROOT).as_posix()} is missing (optional master).")

    logo_light_bg = recolour(master, INK_DARK)
    logo_dark_bg = recolour(master, INK_LIGHT)
    mark, _wordmark = split_lockup(master)
    mark_light_bg = recolour(mark, INK_DARK)
    mark_dark_bg = recolour(mark, INK_LIGHT)

    print("\nApp assets:")
    save(logo_dark_bg, ASSETS / "logo-on-dark.png")
    save(mark_light_bg, ASSETS / "mark.png")
    save(mark_dark_bg, ASSETS / "mark-on-dark.png")
    # The GUI header renders the mark at ~28 px; ship a pre-scaled copy so the
    # window doesn't pay to downsample a 1200 px master on every launch.
    save(scaled_to(mark_dark_bg, (128, 128)), ASSETS / "mark-on-dark-128.png")
    save_ico(mark_light_bg, ASSETS / "icon.ico", ICO_SIZES)

    print("\nDocs site assets:")
    save(scaled_to(logo_light_bg, (720, 720)), DOCS_ASSETS / "logo.png")
    save(scaled_to(logo_dark_bg, (720, 720)), DOCS_ASSETS / "logo-on-dark.png")
    save(scaled_to(mark_light_bg, (192, 192)), DOCS_ASSETS / "mark.png")
    save(scaled_to(mark_dark_bg, (192, 192)), DOCS_ASSETS / "mark-on-dark.png")
    save(build_social_card(logo_light_bg), DOCS_ASSETS / "og-image.png")
    save_ico(mark_light_bg, REPO_ROOT / "docs" / "favicon.ico", FAVICON_SIZES)
    # Tab strips are dark in dark mode; browsers that support a media-queried
    # icon link get the light-ink mark there instead of a black-on-black blob.
    save(scaled_to(mark_dark_bg, (64, 64)), DOCS_ASSETS / "favicon-on-dark.png")

    print("\nDone.")


if __name__ == "__main__":
    main()
