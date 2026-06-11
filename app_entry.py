"""PyInstaller entry point for the standalone desktop app.

PyInstaller runs the entry script as ``__main__``, so the entry point cannot be a
module that uses package-relative imports (``from .theme import ...``) — those
fail with "attempted relative import with no known parent package". This thin
launcher imports the package by its absolute name, so every relative import
inside ``gerberdiff`` resolves normally.
"""

from gerberdiff.gui import main

if __name__ == "__main__":
    raise SystemExit(main())
