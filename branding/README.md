# Branding

`logo-mark.svg` is the **single source of truth** for the gerber-diff mark.
Everything else — the PNGs, the favicon, the Windows `.ico`, the report header,
and the app window icon — is derived from it.

## Palette

| token | hex | meaning |
|---|---|---|
| A / added | `#2f6fe0` (blue) | revision A · added geometry |
| B / removed | `#e07b2d` (orange) | revision B · removed geometry |
| both / unchanged | `#5b6473` (slate) | present in both |

These match the colour-blind-safe diff overlay (`gerberdiff.diff`) and the
report/GUI accents, so the logo and the product read as one system.

## Generated files

`icon-512/256/128/64/32.png`, `favicon-32.png`, `app.ico` (multi-size, used for
the desktop app window and the packaged `.exe`).

## To change the logo

1. Edit `logo-mark.svg` (keep the `0 0 64 64` viewBox so the crops stay centred).
2. Regenerate the rasters:
   ```
   python scripts/build_branding.py
   ```
   (needs Microsoft Edge or Google Chrome to rasterize, plus Pillow.)
3. Commit `logo-mark.svg` together with the regenerated `icon-*.png`,
   `favicon-32.png`, and `app.ico`.

To rebrand entirely, replace `logo-mark.svg` and update the palette table above.
The HTML report inlines the mark in its header; the desktop app and the packaged
executable take their icon from `app.ico`.
