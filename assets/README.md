# Brand assets

Two files here are hand-made masters. Everything else is generated from
`logo.png` by [scripts/build_assets.py](../scripts/build_assets.py) and
committed, so nobody needs to run the script just to build or read the project.

## Masters (edit these)

| File | What it is |
| --- | --- |
| `logo.png` | The background-removed lockup — icon over the "LogSX / LOG FILES ANALYZER" wordmark. **Source of truth for every generated asset.** |
| `logo-on-white.png` | The same lockup flattened onto white. Kept for places that can't handle transparency (slide decks, print, image hosts that composite onto black). |

## Generated (do not edit — run the script instead)

| File | Used by |
| --- | --- |
| `logo-on-dark.png` | README header in GitHub's dark theme |
| `mark.png` | Icon alone, dark ink — light backgrounds |
| `mark-on-dark.png` | Icon alone, light ink — dark backgrounds |
| `mark-on-dark-128.png` | Pre-scaled copy the Tkinter header loads at launch |
| `icon.ico` | `LogSX.exe` icon and the GUI window/taskbar icon |
| `../docs/assets/*` | Docs site nav, hero, and social card |
| `../docs/favicon.ico` | Docs site favicon |

## Naming

`-on-dark` means *drawn in light ink, for placing on a dark background* — not
"a dark-coloured logo". The plain name is the dark-ink version for light
backgrounds.

## Why the standalone mark drops the motion lines

The full icon has speed lines streaming off its left side, and the generated
`mark*.png` files crop them away. Every surface that uses the mark alone is
small — a 16px favicon, the ~30px GUI header, the 28px site nav — and at those
sizes the lines go sub-pixel: they blur into a grey smear while squeezing the
document and magnifier into two-thirds of the tile. Cropping leaves a
near-square mark that still reads at 16px. The lines survive everywhere the
artwork appears large, because the README header and social card use the whole
lockup rather than the mark.

## Regenerating

```bash
python scripts/build_assets.py
```

Run it after replacing either master, then commit the results. The script
recolours the artwork to the palette in `docs/index.html` rather than pure
black and white, so the logo reads as part of the page instead of pasted onto
it, and it locates the icon/wordmark boundary by scanning for the blank band
between them — a re-exported logo with different proportions still splits
correctly.
