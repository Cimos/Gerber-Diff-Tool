"""Modern desktop GUI for gerber-diff, built on stdlib Tkinter (no extra deps).

Pick two folders of Gerber files — or two schematic PDFs — run the diff, and the
self-contained HTML report opens in your browser. A rich in-app pan/zoom viewer
is future work; for now the browser report is the viewer.

Launch with ``gdiff-gui`` (or ``python -m gerberdiff.gui``).
"""

from __future__ import annotations

import datetime
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

# Dark theme palette.
_BG = "#16181d"
_SURFACE = "#1e2128"
_FIELD = "#262a33"
_BORDER = "#30343d"
_TEXT = "#e7e9ee"
_MUTED = "#9aa0aa"
_ACCENT = "#4f8cff"
_ACCENT_HI = "#6ba0ff"
_SUCCESS = "#37c95a"
_DANGER = "#ff5b52"
_ON_ACCENT = "#ffffff"


def parse_int_field(value: object, default: int) -> int:
    """Parse an int from a GUI field, falling back to *default* on bad input."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("gerber-diff")
        root.configure(bg=_BG)
        root.minsize(600, 0)

        families = set(tkfont.families(root))
        family = next((f for f in ("Segoe UI", "Helvetica Neue", "Arial") if f in families), "")
        self.f_h1 = tkfont.Font(root=root, family=family, size=20, weight="bold")
        self.f_body = tkfont.Font(root=root, family=family, size=11)
        self.f_small = tkfont.Font(root=root, family=family, size=9)
        self.f_btn = tkfont.Font(root=root, family=family, size=11, weight="bold")
        self.f_label = tkfont.Font(root=root, family=family, size=9, weight="bold")

        self.old_var = tk.StringVar()
        self.new_var = tk.StringVar()
        self.out_var = tk.StringVar(
            value=str(Path(tempfile.gettempdir()) / "gerber-diff-report.html")
        )
        self.dpmm_var = tk.StringVar(value="20")
        self.dpi_var = tk.StringVar(value="150")
        self.threshold_var = tk.StringVar(value="10")
        self.mode_var = tk.StringVar(value="Choose two folders of Gerbers, or two schematic PDFs.")
        self.status_var = tk.StringVar(value="Ready.")
        self._last_report: Path | None = None

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
            highlightthickness=0,
            padx=14,
            pady=10 if kind == "accent" else 6,
        )
        button.bind(
            "<Enter>",
            lambda e, w=button, h=hover: w.cget("state") != "disabled" and w.configure(bg=h),
        )
        button.bind(
            "<Leave>", lambda e, w=button, b=bg: w.cget("state") != "disabled" and w.configure(bg=b)
        )
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
        self._input_row(card, 0, "Revision A — old", self.old_var)
        self._input_row(card, 1, "Revision B — new", self.new_var)
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
        self._option(opts, 0, "Gerber dpmm", self.dpmm_var)
        self._option(opts, 2, "PDF dpi", self.dpi_var)
        self._option(opts, 4, "Threshold", self.threshold_var)

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

    def _input_row(self, card: tk.Frame, index: int, label: str, var: tk.StringVar) -> None:
        top = 14 if index == 0 else 6
        tk.Label(card, text=label, font=self.f_label, bg=_SURFACE, fg=_MUTED).grid(
            row=index, column=0, sticky="w", padx=(14, 8), pady=(top, 6)
        )
        self._entry(card, var).grid(row=index, column=1, sticky="ew", ipady=5, pady=(top, 6))
        self._button(card, "Folder…", lambda: self._browse_folder(var)).grid(
            row=index, column=2, sticky="ew", padx=8, pady=(top, 6)
        )
        self._button(card, "PDF…", lambda: self._browse_pdf(var)).grid(
            row=index, column=3, sticky="ew", padx=(0, 14), pady=(top, 6)
        )

    def _option(self, parent: tk.Frame, col: int, label: str, var: tk.StringVar) -> None:
        tk.Label(parent, text=label, font=self.f_small, bg=_SURFACE, fg=_MUTED).grid(
            row=0, column=col, padx=(0, 6)
        )
        self._entry(parent, var, width=6).grid(row=0, column=col + 1, ipady=3, padx=(0, 18))

    # --- behaviour --------------------------------------------------------
    def _set_status(self, text: str, kind: str = "info") -> None:
        self.status_var.set(text)
        self.status_lbl.configure(fg={"info": _MUTED, "success": _SUCCESS, "error": _DANGER}[kind])

    def _update_mode(self, *_args: object) -> None:
        a = self.old_var.get().strip().lower()
        b = self.new_var.get().strip().lower()
        if a.endswith(".pdf") and b.endswith(".pdf"):
            self.mode_var.set("Mode: schematic PDF — compared page by page")
        elif a and b:
            self.mode_var.set("Mode: Gerber folders — compared layer by layer")
        else:
            self.mode_var.set("Choose two folders of Gerbers, or two schematic PDFs.")

    def _browse_folder(self, var: tk.StringVar) -> None:
        path = filedialog.askdirectory(title="Choose a folder of Gerber files")
        if path:
            var.set(path)

    def _browse_pdf(self, var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(
            title="Choose a schematic PDF", filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if path:
            var.set(path)

    def _browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save report as",
            defaultextension=".html",
            filetypes=[("HTML report", "*.html")],
        )
        if path:
            self.out_var.set(path)

    def _on_compare(self) -> None:
        old = self.old_var.get().strip()
        new = self.new_var.get().strip()
        out = self.out_var.get().strip()
        if not old or not new or not out:
            self._set_status("Please choose both inputs and an output path.", kind="error")
            return

        self.open_btn.grid_remove()
        self.compare_btn.config(state="disabled", bg=_FIELD)
        self._set_status("Comparing…")
        dpmm = parse_int_field(self.dpmm_var.get(), 20)
        dpi = parse_int_field(self.dpi_var.get(), 150)
        threshold = parse_int_field(self.threshold_var.get(), 10)

        def work() -> None:
            try:
                result = run_diff(Path(old), Path(new), dpmm=dpmm, dpi=dpi, threshold=threshold)
                if not result.layers:
                    raise ValueError(
                        "nothing to compare (no Gerber/drill files or PDF pages found)"
                    )
                generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                report = write_report(result, Path(out), generated_at=generated)
                self.root.after(0, lambda: self._done(result, report))
            except Exception as exc:  # noqa: BLE001 - surface any failure in the UI
                message = f"{type(exc).__name__}: {exc}"
                self.root.after(0, lambda: self._fail(message))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, result, report: Path) -> None:
        changed = len(result.changed_layers)
        self._last_report = report
        noun = result.subject + ("s" if len(result.layers) != 1 else "")
        kind = "error" if changed else "success"
        verb = "differ" if changed else "identical"
        self._set_status(
            f"Compared {len(result.layers)} {noun}: {changed} changed — {verb}.", kind=kind
        )
        self.compare_btn.config(state="normal", bg=_ACCENT)
        self.open_btn.grid(row=0, column=1, sticky="e", padx=(10, 0))
        webbrowser.open(report.resolve().as_uri())

    def _fail(self, message: str) -> None:
        self._set_status(f"Error: {message}", kind="error")
        self.compare_btn.config(state="normal", bg=_ACCENT)

    def _open_report(self) -> None:
        if self._last_report is not None:
            webbrowser.open(self._last_report.resolve().as_uri())


def main() -> int:
    if not _TK_AVAILABLE:
        print(
            "gdiff-gui needs tkinter, which this Python build doesn't include.\n"
            "Install it (e.g. 'sudo apt install python3-tk', or use the python.org\n"
            "build) — or use the command line instead: gdiff --help",
            file=sys.stderr,
        )
        return 1
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
