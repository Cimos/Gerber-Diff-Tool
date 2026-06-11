"""Native, in-app diff viewer — one layer at a time, on a Tk Canvas.

The HTML report is the shareable artifact; this is the *working* viewer a
reviewer drives: pick a layer (changed first), choose a comparison mode
(Overlay / A / B / Split / Swipe / Onion), and pan/zoom around. Compositing is
done in Pillow; the canvas only ever rasterizes the visible crop at the current
zoom, so it stays smooth on large boards.

The pure helpers (``order_layers``, ``compose_master``, ``visible_crop``) carry
the logic and are unit-tested without a display. ``DiffViewer`` is a Tk
``Toplevel`` opened by the GUI after a compare.
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from io import BytesIO
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

from . import theme as T

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


# --- pure helpers (no Tk; unit-tested) -----------------------------------
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


class DiffViewer(tk.Toplevel):
    def __init__(self, parent: tk.Misc, result, report: Path | None = None) -> None:
        super().__init__(parent)
        self.result = result
        self.report = report
        self.layers = [_Layer(ld) for ld in order_layers(result.layers)]
        self.idx = 0
        self.mode = "overlay"
        self.scale = 1.0
        self.ox = 0.0
        self.oy = 0.0
        self.swipe = 0.5
        self.alpha = 0.5
        self._fit_scale = 1.0
        self._photo: ImageTk.PhotoImage | None = None
        self._photo_b: ImageTk.PhotoImage | None = None
        self._resize_job: str | None = None

        self.title(f"gerber-diff — {result.dir_a}  ↔  {result.dir_b}")
        self.configure(bg=T._BG)
        self.geometry("1120x760")
        self.minsize(720, 460)
        self._set_icon()
        self._build()
        if self.layers:
            self._select(0)

    def _set_icon(self) -> None:
        ico = Path(__file__).resolve().parent.parent.parent / "branding" / "app.ico"
        try:
            if ico.exists():
                self.iconbitmap(default=str(ico))
        except tk.TclError:
            pass  # non-Windows or no Tk image support — cosmetic only

    # --- layout -----------------------------------------------------------
    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = tk.Frame(self, bg=T._SURFACE)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._mode_btns: dict[str, tk.Button] = {}
        for m in _MODES:
            b = self._tbtn(toolbar, _MODE_LABELS[m], lambda m=m: self._set_mode(m))
            b.pack(side="left", padx=(8 if m == "overlay" else 2, 2), pady=8)
            self._mode_btns[m] = b
        tk.Frame(toolbar, bg=T._BORDER, width=1).pack(side="left", fill="y", pady=8, padx=8)
        self._tbtn(toolbar, "Fit", self._fit_and_draw).pack(side="left", padx=2, pady=8)
        self._tbtn(toolbar, "1:1", self._one_to_one).pack(side="left", padx=2, pady=8)
        self._tbtn(toolbar, "‹ Prev", self._prev).pack(side="left", padx=(8, 2), pady=8)
        self._tbtn(toolbar, "Next ›", self._next).pack(side="left", padx=2, pady=8)
        self.slider = ttk.Scale(toolbar, from_=0, to=100, command=self._on_slider)
        self.slider.set(50)
        self.slider.pack(side="left", fill="x", expand=True, padx=10)
        if self.report is not None:
            self._tbtn(toolbar, "Open HTML report", self._open_report).pack(
                side="right", padx=(2, 8), pady=8
            )

        # Left: layer list.
        side = tk.Frame(self, bg=T._SURFACE, width=240)
        side.grid(row=1, column=0, sticky="ns")
        side.grid_propagate(False)
        self._style_tree()
        self.tree = ttk.Treeview(side, columns=("px",), show="tree headings", style="GD.Treeview")
        self.tree.heading("#0", text="Layer")
        self.tree.heading("px", text="Δ px")
        self.tree.column("#0", width=150, stretch=True)
        self.tree.column("px", width=70, anchor="e", stretch=False)
        self.tree.tag_configure("chg", foreground=T._REMOVED)
        self.tree.tag_configure("same", foreground=T._MUTED)
        for i, layer in enumerate(self.layers):
            tag = "chg" if layer.ld.changed else "same"
            self.tree.insert(
                "",
                "end",
                iid=str(i),
                text=layer.ld.pair.layer_type,
                values=(f"{layer.ld.changed_pixels:,}",),
                tags=(tag,),
            )
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.pack(fill="both", expand=True, padx=6, pady=6)

        # Center: canvas (+ second canvas for Split), and a status line.
        center = tk.Frame(self, bg=T._BG)
        center.grid(row=1, column=1, sticky="nsew")
        center.rowconfigure(0, weight=1)
        center.columnconfigure(0, weight=1)
        center.columnconfigure(1, weight=1)
        self.canvas = self._canvas(center)
        self.canvas.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=8, pady=8)
        self.canvas_b = self._canvas(center)  # gridded only in Split
        self.img_id = self.canvas.create_image(0, 0, anchor="nw")
        self.img_id_b = self.canvas_b.create_image(0, 0, anchor="nw")

        self.status = tk.Label(
            self,
            textvariable=tk.StringVar(),
            bg=T._SURFACE,
            fg=T._MUTED,
            anchor="w",
        )
        self.status_var = tk.StringVar()
        self.status.configure(textvariable=self.status_var)
        self.status.grid(row=2, column=0, columnspan=2, sticky="ew", ipady=3, ipadx=8)

        for c in (self.canvas, self.canvas_b):
            c.bind("<ButtonPress-1>", self._pan_start)
            c.bind("<B1-Motion>", self._pan_move)
            c.bind("<MouseWheel>", self._zoom)
            c.bind("<Button-4>", self._zoom)  # X11 scroll up
            c.bind("<Button-5>", self._zoom)  # X11 scroll down
            c.bind("<Double-Button-1>", lambda _e: self._fit_and_draw())
            c.bind("<Configure>", self._on_resize)

    def _tbtn(self, parent: tk.Widget, text: str, command) -> tk.Button:
        b = tk.Button(
            parent,
            text=text,
            command=command,
            bg=T._FIELD,
            fg=T._TEXT,
            activebackground=T._BORDER,
            activeforeground=T._TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=5,
            cursor="hand2",
        )
        b.bind("<Enter>", lambda _e: b["state"] != "disabled" and b.configure(bg=T._BORDER))
        b.bind("<Leave>", lambda _e: b["state"] != "disabled" and b.configure(bg=self._btn_bg(b)))
        return b

    def _btn_bg(self, btn: tk.Button) -> str:
        # Active mode button keeps the accent fill.
        for m, b in getattr(self, "_mode_btns", {}).items():
            if b is btn and m == self.mode:
                return T._ACCENT
        return T._FIELD

    def _canvas(self, parent: tk.Widget) -> tk.Canvas:
        return tk.Canvas(parent, bg="#0c0d10", highlightthickness=0, takefocus=True)

    def _style_tree(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "GD.Treeview",
            background=T._SURFACE,
            fieldbackground=T._SURFACE,
            foreground=T._TEXT,
            borderwidth=0,
            rowheight=24,
        )
        style.configure(
            "GD.Treeview.Heading", background=T._FIELD, foreground=T._MUTED, borderwidth=0
        )
        style.map(
            "GD.Treeview", background=[("selected", T._ACCENT)], foreground=[("selected", "#fff")]
        )

    # --- state changes ----------------------------------------------------
    def _on_tree_select(self, _event: object) -> None:
        sel = self.tree.selection()
        if sel:
            self._select(int(sel[0]))

    def _select(self, i: int) -> None:
        self.idx = max(0, min(len(self.layers) - 1, i))
        iid = str(self.idx)
        if self.tree.selection() != (iid,):
            self.tree.selection_set(iid)
            self.tree.see(iid)
        self._refresh_mode_availability()
        self._fit()
        self._redraw()
        self._update_status()

    def _refresh_mode_availability(self) -> None:
        both = self.layers[self.idx].has_both if self.layers else False
        for m, b in self._mode_btns.items():
            enabled = both or m not in _BOTH_ONLY
            b.configure(state="normal" if enabled else "disabled")
        if self.mode in _BOTH_ONLY and not both:
            self.mode = "overlay"
        self._paint_mode_buttons()

    def _paint_mode_buttons(self) -> None:
        for m, b in self._mode_btns.items():
            active = m == self.mode
            b.configure(
                bg=T._ACCENT if active else T._FIELD,
                fg="#fff" if active else T._TEXT,
            )

    def _set_mode(self, mode: str) -> None:
        if self._mode_btns[mode]["state"] == "disabled":
            return
        self.mode = mode
        self._paint_mode_buttons()
        self._sync_slider_visibility()
        self._redraw()

    def _sync_slider_visibility(self) -> None:
        self.slider.state(["!disabled"] if self.mode in ("swipe", "onion") else ["disabled"])

    def _on_slider(self, value: str) -> None:
        frac = float(value) / 100.0
        if self.mode == "swipe":
            self.swipe = frac
        elif self.mode == "onion":
            self.alpha = frac
        else:
            return
        self._redraw()

    def _prev(self) -> None:
        self._select((self.idx - 1) % len(self.layers))

    def _next(self) -> None:
        self._select((self.idx + 1) % len(self.layers))

    # --- pan / zoom -------------------------------------------------------
    def _master(self) -> Image.Image | None:
        layer = self.layers[self.idx]
        return compose_master(
            self.mode, layer.overlay, layer.a, layer.b, swipe=self.swipe, alpha=self.alpha
        )

    def _fit(self) -> None:
        master = self._master()
        vw = max(1, self.canvas.winfo_width())
        vh = max(1, self.canvas.winfo_height())
        if master is None:
            return
        self._fit_scale = min(vw / master.width, vh / master.height)
        self.scale = self._fit_scale
        self.ox = (vw - master.width * self.scale) / 2
        self.oy = (vh - master.height * self.scale) / 2

    def _fit_and_draw(self) -> None:
        self._fit()
        self._redraw()

    def _one_to_one(self) -> None:
        master = self._master()
        if master is None:
            return
        vw, vh = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.scale = 1.0
        self.ox = (vw - master.width) / 2
        self.oy = (vh - master.height) / 2
        self._redraw()

    def _zoom(self, event: tk.Event) -> None:
        up = getattr(event, "delta", 0) > 0 or getattr(event, "num", 0) == 4
        factor = 1.15 if up else 1 / 1.15
        new = min(40.0, max(self._fit_scale, self.scale * factor))
        if new == self.scale:
            return
        self.ox = event.x - (event.x - self.ox) * (new / self.scale)
        self.oy = event.y - (event.y - self.oy) * (new / self.scale)
        self.scale = new
        self._redraw()

    def _pan_start(self, event: tk.Event) -> None:
        self._lx, self._ly = event.x, event.y

    def _pan_move(self, event: tk.Event) -> None:
        self.ox += event.x - self._lx
        self.oy += event.y - self._ly
        self._lx, self._ly = event.x, event.y
        self._redraw()

    def _on_resize(self, _event: object) -> None:
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self._fit_and_draw)

    # --- rendering --------------------------------------------------------
    def _blit(self, canvas: tk.Canvas, item: int, master: Image.Image | None, attr: str) -> None:
        vw, vh = canvas.winfo_width(), canvas.winfo_height()
        if master is None or vw < 2 or vh < 2:
            canvas.itemconfigure(item, image="")
            return
        sx0, sy0, sx1, sy1 = visible_crop(
            master.width, master.height, self.scale, self.ox, self.oy, vw, vh
        )
        if sx1 <= sx0 or sy1 <= sy0:
            canvas.itemconfigure(item, image="")
            return
        crop = master.crop((sx0, sy0, sx1, sy1))
        resample = Image.NEAREST if self.scale >= 1 else Image.BILINEAR
        disp = crop.resize(
            (max(1, round(crop.width * self.scale)), max(1, round(crop.height * self.scale))),
            resample,
        )
        photo = ImageTk.PhotoImage(disp)
        canvas.itemconfigure(item, image=photo)
        canvas.coords(item, self.ox + sx0 * self.scale, self.oy + sy0 * self.scale)
        setattr(self, attr, photo)  # keep a reference or Tk drops the image

    def _redraw(self) -> None:
        split = self.mode == "split"
        if split:
            self.canvas.grid_configure(columnspan=1)
            self.canvas_b.grid(row=0, column=1, sticky="nsew", padx=(0, 8), pady=8)
        else:
            self.canvas_b.grid_remove()
            self.canvas.grid_configure(columnspan=2)
        self._blit(self.canvas, self.img_id, self._master(), "_photo")
        if split:
            layer = self.layers[self.idx]
            self._blit(self.canvas_b, self.img_id_b, layer.b or layer.overlay, "_photo_b")

    def _update_status(self) -> None:
        layer = self.layers[self.idx]
        ld = layer.ld
        bits = [f"{ld.pair.layer_type} · {ld.pair.key}"]
        if ld.error:
            bits.append(f"error: {ld.error}")
        elif ld.changed:
            bits.append(f"+{ld.added_pixels:,} added / -{ld.removed_pixels:,} removed px")
        else:
            bits.append("unchanged")
        if getattr(ld, "warning", None):
            bits.append(f"⚠ {ld.warning}")
        bits.append("scroll = zoom · drag = pan · double-click = fit")
        self.status_var.set("   ·   ".join(bits))

    def _open_report(self) -> None:
        if self.report is not None:
            webbrowser.open(Path(self.report).resolve().as_uri())
