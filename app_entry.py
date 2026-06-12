"""PyInstaller entry point for the standalone desktop app.

Two hard-won constraints meet here:

1. ``multiprocessing.freeze_support()`` MUST run first. In a frozen Windows
   app, every ProcessPoolExecutor worker re-executes this entry script with
   ``__name__ == "__main__"`` — the usual main-guard does NOT protect frozen
   builds. ``freeze_support()`` detects a worker re-run and takes over (never
   returning); without it each render worker opens another GUI window.

2. The package import stays INSIDE the guard, after ``freeze_support()``.
   PyInstaller runs the entry as ``__main__``, so a module using
   package-relative imports can't be the entry itself, and importing the GUI
   at top level would make every worker pay the full Tk import before
   ``freeze_support()`` could intercept it.
"""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from gerberdiff.gui import main

    sys.exit(main())
