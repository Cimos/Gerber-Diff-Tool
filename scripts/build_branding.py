"""Regenerate raster brand assets from ``branding/logo-mark.svg``.

The SVG is the single source of truth. This renders it (headless Edge/Chrome) to
PNGs and a multi-size Windows ``.ico``. Run after editing the logo::

    python scripts/build_branding.py

Needs Microsoft Edge or Google Chrome (to rasterize the SVG) and Pillow. The
generated files are committed, so contributors only need this when changing the
logo.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BRANDING = ROOT / "branding"
SVG = BRANDING / "logo-mark.svg"

_BROWSERS = [
    shutil.which("msedge"),
    shutil.which("chrome"),
    shutil.which("chromium"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
]


def _find_browser() -> str:
    for cand in _BROWSERS:
        if cand and Path(cand).exists():
            return cand
    raise SystemExit(
        "need Microsoft Edge or Google Chrome to rasterize the SVG; "
        "install one, or convert branding/logo-mark.svg to PNG by hand."
    )


def _render(browser: str, size: int, out: Path) -> None:
    svg = SVG.read_text(encoding="utf-8")
    html = (
        '<!doctype html><meta charset="utf-8">'
        f"<style>html,body{{margin:0;padding:0}}svg{{display:block;width:{size}px;height:{size}px}}</style>{svg}"
    )
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "logo.html"
        page.write_text(html, encoding="utf-8")
        subprocess.run(
            [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--default-background-color=00000000",
                f"--screenshot={out}",
                f"--window-size={size},{size}",
                str(page),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )


def main() -> int:
    browser = _find_browser()
    master = BRANDING / "icon-512.png"
    _render(browser, 512, master)
    base = Image.open(master).convert("RGBA")
    for size in (256, 128, 64, 32):
        base.resize((size, size), Image.LANCZOS).save(BRANDING / f"icon-{size}.png")
    base.resize((32, 32), Image.LANCZOS).save(BRANDING / "favicon-32.png")
    base.save(
        BRANDING / "app.ico",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    written = sorted(p.name for p in BRANDING.glob("*.png")) + ["app.ico"]
    print("wrote:", ", ".join(written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
