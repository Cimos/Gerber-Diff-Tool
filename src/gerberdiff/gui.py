"""Modern desktop GUI for gerber-diff, built on stdlib Tkinter (no extra deps).

Pick two folders/zips of Gerbers — or two schematic PDFs — hit Compare, and a
native, layer-by-layer viewer opens (overlay / A / B / split / swipe / onion,
with pan-zoom). The self-contained HTML report is written alongside as the
shareable export. The launcher is keyboard-operable (Tab + Enter), with focus
rings, live progress, remembered folders, and tooltips.

Launch with ``gdiff-gui`` (or ``python -m gerberdiff.gui``).
"""

from __future__ import annotations

import datetime
import json
import sys
import tempfile
import threading
import webbrowser
from pathlib import Path

try:
    import tkinter as tk
    import tkinter.font as tkfont
    from tkinter import filedialog

    _TK_AVAILABLE = True
except ModuleNotFoundError:  # tkinter isn't bundled with every Python build
    tk = None  # type: ignore[assignment]
    _TK_AVAILABLE = False

from .runner import run_diff, write_report
from .theme import (  # noqa: F401 - shared dark-theme palette tokens
    _ACCENT,
    _ACCENT_DIM,
    _ACCENT_HI,
    _BG,
    _BORDER,
    _DANGER,
    _FIELD,
    _MUTED,
    _ON_ACCENT,
    _SUCCESS,
    _SURFACE,
    _TEXT,
    app_icon_path,
)

_CONFIG_PATH = Path.home() / ".gerber-diff.json"


def parse_int_field(value: object, default: int) -> int:
    """Parse an int from a GUI field, falling back to *default* on bad input."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - config is best-effort
        return {}


def _save_config(data: dict) -> None:
    try:
        _CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


class _Tooltip:
    """Minimal hover tooltip for a widget (raw tk, no deps)."""

    def __init__(self, widget: tk.Widget, text: str, font: tkfont.Font) -> None:
        self.widget = widget
        self.text = text
        self.font = font
        self.tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event: object = None) -> None:
        if self.tip is not None:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self.tip,
            text=self.text,
            font=self.font,
            bg="#0c0d10",
            fg=_TEXT,
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=4,
            justify="left",
            wraplength=260,
        ).pack()

    def _hide(self, _event: object = None) -> None:
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("gerber-diff")
        root.configure(bg=_BG)
        root.minsize(600, 0)
        _ico = app_icon_path()
        if _ico is not None:
            try:
                root.iconbitmap(default=str(_ico))
            except tk.TclError:
                pass
        self._cfg = _load_config()

        families = set(tkfont.families(root))
        family = next((f for f in ("Segoe UI", "Helvetica Neue", "Arial") if f in families), "")
        self.f_h1 = tkfont.Font(root=root, family=family, size=20, weight="bold")
        self.f_body = tkfont.Font(root=root, family=family, size=11)
        self.f_small = tkfont.Font(root=root, family=family, size=9)
        self.f_btn = tkfont.Font(root=root, family=family, size=11, weight="bold")
        self.f_label = tkfont.Font(root=root, family=family, size=9, weight="bold")

        default_out = self._cfg.get("output") or str(
            Path(tempfile.gettempdir()) / "gerber-diff-report.html"
        )
        self._last_dir = self._cfg.get("last_dir") or str(Path.home())
        self.old_var = tk.StringVar()
        self.new_var = tk.StringVar()
        self.out_var = tk.StringVar(value=default_out)
        self.dpmm_var = tk.StringVar(value=str(self._cfg.get("dpmm", 20)))
        self.dpi_var = tk.StringVar(value=str(self._cfg.get("dpi", 150)))
        self.threshold_var = tk.StringVar(value=str(self._cfg.get("threshold", 10)))
        self.mode_var = tk.StringVar(
            value="Choose two folders/zips of Gerbers, or two schematic PDFs."
        )
        self.status_var = tk.StringVar(value="Ready — pick Revision A and B, then Compare.")
        self._last_report: Path | None = None
        self._first_field: tk.Entry | None = None

        self._build()
        for var in (self.old_var, self.new_var):
            var.trace_add("write", self._update_mode)

    # --- styled widget helpers --------------------------------------------
    def _entry(self, parent: tk.Widget, textvariable: tk.StringVar, width: int = 0) -> tk.Entry:
        return tk.Entry(
            parent,
            textvariable=textvariable,
            font=self.f_body,
            width=width,
            bg=_FIELD,
            fg=_TEXT,
            insertbackground=_TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_ACCENT,
        )

    def _button(self, parent: tk.Widget, text: str, command, kind: str = "ghost") -> tk.Button:
        bg, fg, hover = {
            "accent": (_ACCENT, _ON_ACCENT, _ACCENT_HI),
            "ghost": (_FIELD, _TEXT, _BORDER),
        }[kind]
        button = tk.Button(
            parent,
            text=text,
            command=command,
            font=self.f_btn if kind == "accent" else self.f_label,
            bg=bg,
            fg=fg,
            activebackground=hover,
            activeforeground=fg,
            disabledforeground=_MUTED,
            relief="flat",
            bd=0,
            cursor="hand2",
            highlightthickness=2,
            highlightbackground=bg,
            highlightcolor=_ACCENT_HI,
            padx=14,
            pady=10 if kind == "accent" else 6,
        )

        def enter(_e: object) -> None:
            if str(button["state"]) != "disabled":
                button.configure(bg=hover)

        def leave(_e: object) -> None:
            if str(button["state"]) != "disabled":
                button.configure(bg=bg)

        button.bind("<Enter>", enter)
        button.bind("<Leave>", leave)
        button.bind("<FocusIn>", enter)  # focus is visible by fill + ring
        button.bind("<FocusOut>", leave)
        return button

    def _card(self, parent: tk.Widget) -> tk.Frame:
        return tk.Frame(parent, bg=_SURFACE, highlightthickness=1, highlightbackground=_BORDER)

    # --- layout -----------------------------------------------------------
    def _build(self) -> None:
        outer = tk.Frame(self.root, bg=_BG)
        outer.pack(fill="both", expand=True, padx=22, pady=20)
        outer.columnconfigure(0, weight=1)

        tk.Label(outer, text="gerber-diff", font=self.f_h1, bg=_BG, fg=_TEXT).grid(
            row=0, column=0, sticky="w"
        )
        tk.Label(
            outer,
            text="Free, offline visual diff for PCB Gerbers & schematic PDFs",
            font=self.f_small,
            bg=_BG,
            fg=_MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(2, 16))

        card = self._card(outer)
        card.grid(row=2, column=0, sticky="ew")
        card.columnconfigure(1, weight=1)
        self._first_field = self._input_row(card, 0, "Revision A — old", self.old_var, None)
        self._input_row(card, 1, "Revision B — new", self.new_var, self.old_var)
        tk.Label(card, textvariable=self.mode_var, font=self.f_small, bg=_SURFACE, fg=_MUTED).grid(
            row=2, column=0, columnspan=4, sticky="w", padx=14, pady=(2, 10)
        )

        tk.Label(card, text="Report", font=self.f_label, bg=_SURFACE, fg=_MUTED).grid(
            row=3, column=0, sticky="w", padx=(14, 8), pady=8
        )
        self._entry(card, self.out_var).grid(row=3, column=1, sticky="ew", ipady=5, pady=8)
        self._button(card, "Save as…", self._browse_output).grid(
            row=3, column=2, columnspan=2, sticky="ew", padx=(8, 14), pady=8
        )

        opts = tk.Frame(card, bg=_SURFACE)
        opts.grid(row=4, column=0, columnspan=4, sticky="w", padx=14, pady=(4, 14))
        self._option(
            opts,
            0,
            "Gerber dpmm",
            self.dpmm_var,
            "Gerber render resolution in dots per mm. Higher = sharper diff but slower and larger report.",
        )
        self._option(
            opts, 2, "PDF dpi", self.dpi_var, "Schematic-PDF render resolution in dots per inch."
        )
        self._option(
            opts,
            4,
            "Threshold",
            self.threshold_var,
            "Luminance 0–255: how bright a pixel must be to count as ink. Raise to ignore faint anti-aliasing.",
        )

        self.compare_btn = self._button(outer, "Compare", self._on_compare, kind="accent")
        self.compare_btn.grid(row=3, column=0, sticky="ew", pady=(16, 10))

        results = tk.Frame(outer, bg=_BG)
        results.grid(row=4, column=0, sticky="ew")
        results.columnconfigure(0, weight=1)
        self.status_lbl = tk.Label(
            results,
            textvariable=self.status_var,
            font=self.f_small,
            bg=_BG,
            fg=_MUTED,
            anchor="w",
            justify="left",
            wraplength=520,
        )
        self.status_lbl.grid(row=0, column=0, sticky="w")
        self.open_btn = self._button(results, "Open report", self._open_report)
        # open_btn is gridded only after a successful compare.

    def _input_row(
        self,
        card: tk.Frame,
        index: int,
        label: str,
        var: tk.StringVar,
        sibling: tk.StringVar | None,
    ) -> tk.Entry:
        top = 14 if index == 0 else 6
        tk.Label(card, text=label, font=self.f_label, bg=_SURFACE, fg=_MUTED).grid(
            row=index, column=0, sticky="w", padx=(14, 8), pady=(top, 6)
        )
        entry = self._entry(card, var)
        entry.grid(row=index, column=1, sticky="ew", ipady=5, pady=(top, 6))
        self._button(card, "Folder…", lambda: self._browse_folder(var, sibling)).grid(
            row=index, column=2, sticky="ew", padx=8, pady=(top, 6)
        )
        self._button(card, "File…", lambda: self._browse_pdf(var)).grid(
            row=index, column=3, sticky="ew", padx=(0, 14), pady=(top, 6)
        )
        return entry

    def _option(self, parent: tk.Frame, col: int, label: str, var: tk.StringVar, tip: str) -> None:
        lbl = tk.Label(parent, text=label, font=self.f_small, bg=_SURFACE, fg=_MUTED)
        lbl.grid(row=0, column=col, padx=(0, 6))
        entry = self._entry(parent, var, width=6)
        entry.grid(row=0, column=col + 1, ipady=3, padx=(0, 18))
        _Tooltip(lbl, tip, self.f_small)
        _Tooltip(entry, tip, self.f_small)

    # --- behaviour --------------------------------------------------------
    def _set_status(self, text: str, kind: str = "info") -> None:
        self.status_var.set(text)
        self.status_lbl.configure(fg={"info": _MUTED, "success": _SUCCESS, "error": _DANGER}[kind])

    def _update_mode(self, *_args: object) -> None:
        a = self.old_var.get().strip().lower()
        b = self.new_var.get().strip().lower()
        if a.endswith(".pdf") and b.endswith(".pdf"):
            self.mode_var.set("Mode: schematic PDF — compared page by page")
        elif a and b and (a.endswith(".zip") or b.endswith(".zip")):
            self.mode_var.set("Mode: Gerber zip — extracted and compared layer by layer")
        elif a and b:
            self.mode_var.set("Mode: Gerber folders — compared layer by layer")
        else:
            self.mode_var.set("Choose two folders/zips of Gerbers, or two schematic PDFs.")

    def _browse_folder(self, var: tk.StringVar, sibling: tk.StringVar | None) -> None:
        initial = self._last_dir
        if sibling is not None and sibling.get().strip():
            initial = str(Path(sibling.get().strip()).parent)  # default B next to A
        path = filedialog.askdirectory(title="Choose a folder of Gerber files", initialdir=initial)
        if path:
            var.set(path)
            self._last_dir = str(Path(path).parent)

    def _browse_pdf(self, var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(
            title="Choose a schematic PDF or a zip of Gerbers",
            initialdir=self._last_dir,
            filetypes=[
                ("PDF or Gerber zip", "*.pdf;*.zip"),
                ("PDF files", "*.pdf"),
                ("Zip archives", "*.zip"),
                ("All files", "*.*"),
            ],
        )
        if path:
            var.set(path)
            self._last_dir = str(Path(path).parent)

    def _browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save report as",
            defaultextension=".html",
            filetypes=[("HTML report", "*.html")],
        )
        if path:
            self.out_var.set(path)

    def _persist(self, dpmm: int, dpi: int, threshold: int) -> None:
        _save_config(
            {
                "last_dir": self._last_dir,
                "output": self.out_var.get().strip(),
                "dpmm": dpmm,
                "dpi": dpi,
                "threshold": threshold,
            }
        )

    def _on_compare(self) -> None:
        old = self.old_var.get().strip()
        new = self.new_var.get().strip()
        out = self.out_var.get().strip()
        if not old or not new or not out:
            self._set_status("Please choose both inputs and an output path.", kind="error")
            return

        self.open_btn.grid_remove()
        self.compare_btn.config(state="disabled", text="Comparing…", bg=_ACCENT_DIM)
        self.root.configure(cursor="watch")
        self._set_status("Comparing…")
        dpmm = parse_int_field(self.dpmm_var.get(), 20)
        dpi = parse_int_field(self.dpi_var.get(), 150)
        threshold = parse_int_field(self.threshold_var.get(), 10)
        self._persist(dpmm, dpi, threshold)

        def on_progress(index: int, total: int, label: str) -> None:
            self.root.after(
                0, lambda: self._set_status(f"Rendering {label} ({index + 1}/{total})…")
            )

        def work() -> None:
            try:
                result = run_diff(
                    Path(old),
                    Path(new),
                    dpmm=dpmm,
                    dpi=dpi,
                    threshold=threshold,
                    progress=on_progress,
                )
                if not result.layers:
                    raise ValueError(
                        "nothing to compare (no Gerber/drill files or PDF pages found)"
                    )
                generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                report = write_report(result, Path(out), generated_at=generated)
                self.root.after(0, lambda: self._done(result, report))
            except ValueError as exc:  # expected, user-fixable
                message = str(exc)
                self.root.after(0, lambda: self._fail(message))
            except Exception as exc:  # noqa: BLE001 - unexpected: show type for bug reports
                message = f"{type(exc).__name__}: {exc}"
                self.root.after(0, lambda: self._fail(message))

        threading.Thread(target=work, daemon=True).start()

    def _reset_button(self) -> None:
        self.compare_btn.config(state="normal", text="Compare", bg=_ACCENT)
        self.root.configure(cursor="")

    def _done(self, result, report: Path) -> None:
        self._last_report = report
        changed = len(result.changed_layers)
        noun = result.subject + ("s" if len(result.layers) != 1 else "")
        kind = "error" if changed else "success"
        tail = "differ" if changed else "identical"
        self._set_status(
            f"✓ Compared {len(result.layers)} {noun}: {changed} changed — {tail}.", kind=kind
        )
        self._reset_button()
        self.open_btn.grid(row=0, column=1, sticky="e", padx=(10, 0))
        from .viewer import DiffViewer

        DiffViewer(self.root, result, report)  # native layer-by-layer viewer

    def _fail(self, message: str) -> None:
        self._set_status(f"✕ {message}", kind="error")
        self._reset_button()

    def _open_report(self) -> None:
        if self._last_report is not None:
            webbrowser.open(self._last_report.resolve().as_uri())


def _selftest(report_path: str | None = None) -> int:
    """Headless end-to-end check that the (possibly frozen) renderers work.

    Exercises pygerber + gerbonara (Gerber path) and pypdfium2 (PDF path), so a
    packaged build can be verified before relying on it:
    ``GerberDiff.exe --selftest``.
    """
    import tempfile
    from pathlib import Path as _Path

    from .runner import run_diff

    msg = "OK"
    try:
        gerber = "G04*\n%FSLAX46Y46*%\n%MOMM*%\n%ADD10C,1.0*%\nD10*\nX1000000Y1000000D03*\nM02*\n"
        with tempfile.TemporaryDirectory() as td:
            a, b = _Path(td) / "a", _Path(td) / "b"
            a.mkdir()
            b.mkdir()
            for d in (a, b):
                (d / "x-F_Cu.gbr").write_text(gerber)
                (d / "x-B_Cu.gbr").write_text(gerber)
            assert run_diff(a, b, dpmm=10).layers, "gerber path produced no layers"

            from PIL import Image, ImageDraw

            pa, pb = _Path(td) / "a.pdf", _Path(td) / "b.pdf"
            for p, extra in ((pa, False), (pb, True)):
                im = Image.new("1", (120, 80), 1)
                draw = ImageDraw.Draw(im)
                draw.rectangle([10, 10, 80, 60], outline=0, width=3)
                if extra:
                    draw.line([90, 10, 110, 60], fill=0, width=3)
                im.save(str(p))
            assert run_diff(pa, pb, dpi=72).layers, "pdf path produced no pages"
    except Exception as exc:  # noqa: BLE001 - any failure becomes the test result
        msg = f"FAIL: {type(exc).__name__}: {exc}"
    if report_path:
        try:
            _Path(report_path).write_text(msg, encoding="utf-8")
        except OSError:
            pass
    if sys.stdout is not None:  # windowed PyInstaller builds have no stdout
        print(msg)
    return 0 if msg == "OK" else 1


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--selftest":
        return _selftest(args[1] if len(args) > 1 else None)
    if not _TK_AVAILABLE:
        print(
            "gdiff-gui needs tkinter, which this Python build doesn't include.\n"
            "Install it (e.g. 'sudo apt install python3-tk', or use the python.org\n"
            "build) — or use the command line instead: gdiff --help",
            file=sys.stderr,
        )
        return 1
    root = tk.Tk()
    app = App(root)
    root.bind("<Return>", lambda _e: app._on_compare())
    if app._first_field is not None:
        app._first_field.focus_set()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
