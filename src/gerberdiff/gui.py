"""A minimal cross-platform GUI for gerber-diff, built on Tkinter (stdlib).

Pick two folders of Gerber files — or two schematic PDFs — run the diff, and
open the HTML report in your browser. A rich in-app pan/zoom viewer is future
work; for now the browser report is the viewer.

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
    from tkinter import filedialog, ttk

    _TK_AVAILABLE = True
except ModuleNotFoundError:  # tkinter isn't bundled with every Python build
    tk = None  # type: ignore[assignment]
    _TK_AVAILABLE = False

from .runner import run_diff, write_report

_PAD = {"padx": 8, "pady": 4}


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("gerber-diff")
        root.minsize(620, 0)

        default_out = str(Path(tempfile.gettempdir()) / "gerber-diff-report.html")
        self.old_var = tk.StringVar()
        self.new_var = tk.StringVar()
        self.out_var = tk.StringVar(value=default_out)
        self.dpmm_var = tk.StringVar(value="20")
        self.dpi_var = tk.StringVar(value="150")
        self.threshold_var = tk.StringVar(value="10")
        self.status_var = tk.StringVar(value="Ready. Choose two revisions to compare.")

        frame = ttk.Frame(root, padding=12)
        frame.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="gerber-diff", font=("", 14, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w"
        )
        ttk.Label(
            frame,
            text="Compare two PCB revisions — Gerber folders or schematic PDFs.",
            foreground="#888",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 8))

        self._path_row(frame, 2, "Old (A):", self.old_var)
        self._path_row(frame, 3, "New (B):", self.new_var)

        ttk.Label(frame, text="Output:").grid(row=4, column=0, sticky="w", **_PAD)
        ttk.Entry(frame, textvariable=self.out_var).grid(row=4, column=1, sticky="ew", **_PAD)
        ttk.Button(frame, text="Save as…", command=self._browse_output).grid(
            row=4, column=2, columnspan=2, sticky="ew", **_PAD
        )

        opts = ttk.Frame(frame)
        opts.grid(row=5, column=0, columnspan=4, sticky="w", pady=(8, 4))
        ttk.Label(opts, text="Gerber dpmm:").grid(row=0, column=0, padx=(8, 2))
        ttk.Entry(opts, textvariable=self.dpmm_var, width=6).grid(row=0, column=1, padx=(0, 12))
        ttk.Label(opts, text="PDF dpi:").grid(row=0, column=2, padx=(0, 2))
        ttk.Entry(opts, textvariable=self.dpi_var, width=6).grid(row=0, column=3, padx=(0, 12))
        ttk.Label(opts, text="Threshold:").grid(row=0, column=4, padx=(0, 2))
        ttk.Entry(opts, textvariable=self.threshold_var, width=6).grid(row=0, column=5)

        self.compare_btn = ttk.Button(frame, text="Compare", command=self._on_compare)
        self.compare_btn.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(10, 6))

        ttk.Label(frame, textvariable=self.status_var, foreground="#666", wraplength=560).grid(
            row=7, column=0, columnspan=4, sticky="w", **_PAD
        )

    def _path_row(self, frame: ttk.Frame, row: int, label: str, var: tk.StringVar) -> None:
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", **_PAD)
        ttk.Entry(frame, textvariable=var).grid(row=row, column=1, sticky="ew", **_PAD)
        ttk.Button(frame, text="Folder…", command=lambda: self._browse_folder(var)).grid(
            row=row, column=2, sticky="ew", **_PAD
        )
        ttk.Button(frame, text="PDF…", command=lambda: self._browse_pdf(var)).grid(
            row=row, column=3, sticky="ew", **_PAD
        )

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
            title="Save report as", defaultextension=".html",
            filetypes=[("HTML report", "*.html")],
        )
        if path:
            self.out_var.set(path)

    def _int(self, var: tk.StringVar, default: int) -> int:
        try:
            return int(var.get())
        except (TypeError, ValueError):
            return default

    def _set_status(self, text: str, *, error: bool = False) -> None:
        self.status_var.set(text)

    def _on_compare(self) -> None:
        old = self.old_var.get().strip()
        new = self.new_var.get().strip()
        out = self.out_var.get().strip()
        if not old or not new or not out:
            self._set_status("Please choose both inputs and an output path.", error=True)
            return

        self.compare_btn.config(state="disabled")
        self._set_status("Comparing…")
        dpmm = self._int(self.dpmm_var, 20)
        dpi = self._int(self.dpi_var, 150)
        threshold = self._int(self.threshold_var, 10)

        def work() -> None:
            try:
                result = run_diff(Path(old), Path(new), dpmm=dpmm, dpi=dpi, threshold=threshold)
                if not result.layers:
                    raise ValueError("nothing to compare (no Gerber/drill files or PDF pages found)")
                generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                report = write_report(result, Path(out), generated_at=generated)
                self.root.after(0, lambda: self._done(result, report))
            except Exception as exc:  # noqa: BLE001 - surface any failure in the UI
                message = f"{type(exc).__name__}: {exc}"
                self.root.after(0, lambda: self._fail(message))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, result, report: Path) -> None:
        changed = len(result.changed_layers)
        self._set_status(
            f"Compared {len(result.layers)} {result.subject}s, {changed} changed — opened {report.name}."
        )
        self.compare_btn.config(state="normal")
        webbrowser.open(report.resolve().as_uri())

    def _fail(self, message: str) -> None:
        self._set_status(f"Error: {message}", error=True)
        self.compare_btn.config(state="normal")


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
