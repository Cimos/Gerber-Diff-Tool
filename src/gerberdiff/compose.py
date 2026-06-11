"""Pure, Tk-free helpers behind the native viewer.

Kept separate from ``viewer.py`` so the compositing and layout logic — the part
that actually carries bugs — is unit-tested without a display, while the Tk
``DiffViewer`` shell stays thin. ``viewer.py`` imports these and wires them onto
the canvas.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image

_MODES = ("overlay", "a", "b", "split", "swipe", "onion")
_MODE_LABELS = {
    "overlay": "Overlay",
    "a": "A (old)",
    "b": "B (new)",
    "split": "Split",
    "swipe": "Swipe",
    "onion": "Onion",
}
_BOTH_ONLY = {"split", "swipe", "onion"}  # need both A and B rasters


def order_layers(layers: list) -> list:
    """Changed first, biggest change first, then unchanged."""
    return sorted(layers, key=lambda lyr: (not lyr.changed, -lyr.changed_pixels))


def decode_png(data: bytes | None) -> Image.Image | None:
    if not data:
        return None
    img = Image.open(BytesIO(data))
    img.load()
    return img.convert("RGB")


def compose_master(
    mode: str,
    overlay: Image.Image | None,
    image_a: Image.Image | None,
    image_b: Image.Image | None,
    *,
    swipe: float = 0.5,
    alpha: float = 0.5,
) -> Image.Image | None:
    """Composite the single image shown on the primary canvas for *mode*.

    Split shows A here and B on the secondary canvas. Modes needing both sides
    fall back to the overlay when a side is missing.
    """
    if mode == "a":
        return image_a or overlay
    if mode in ("b",):
        return image_b or overlay
    if mode == "split":
        return image_a or overlay
    if mode == "onion" and image_a and image_b:
        return Image.blend(image_a, image_b, max(0.0, min(1.0, alpha)))
    if mode == "swipe" and image_a and image_b:
        width, height = image_b.size
        cut = max(0, min(width, round(swipe * width)))
        out = image_b.copy()
        if cut:
            out.paste(image_a.crop((0, 0, cut, height)), (0, 0))
        return out
    return overlay


def visible_crop(
    mw: int, mh: int, scale: float, ox: float, oy: float, vw: int, vh: int
) -> tuple[int, int, int, int]:
    """Source rect (in master px) of the master currently visible in the canvas."""
    sx0 = max(0, int(-ox / scale))
    sy0 = max(0, int(-oy / scale))
    sx1 = min(mw, int((vw - ox) / scale) + 1)
    sy1 = min(mh, int((vh - oy) / scale) + 1)
    return sx0, sy0, sx1, sy1


# digit keys "1".."6" select a mode, in _MODES order
MODE_KEYS = {str(i + 1): mode for i, mode in enumerate(_MODES)}


def action_for_key(keysym: str) -> str | None:
    """Map a Tk keysym to a viewer action token, or None for no shortcut.

    Pure so the keyboard scheme is unit-tested without a display; the Tk
    DiffViewer just dispatches the token to its existing methods.
    """
    k = keysym.lower()
    if k in ("left", "up", "prior"):
        return "prev"
    if k in ("right", "down", "next", "space"):
        return "next"
    if k in ("plus", "equal", "kp_add"):
        return "zoom_in"
    if k in ("minus", "underscore", "kp_subtract"):
        return "zoom_out"
    if k in ("0", "f", "home"):
        return "fit"
    if k in MODE_KEYS:
        return "mode:" + MODE_KEYS[k]
    return None


class _Layer:
    """Decoded masters for one LayerDiff."""

    def __init__(self, ld) -> None:
        self.ld = ld
        self.overlay = decode_png(ld.overlay_png)
        self.a = decode_png(getattr(ld, "image_a_png", None))
        self.b = decode_png(getattr(ld, "image_b_png", None))

    @property
    def has_both(self) -> bool:
        return self.a is not None and self.b is not None
