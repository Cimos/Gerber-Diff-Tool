# PyInstaller spec for the standalone desktop app.
#   one-folder:  uv run pyinstaller GerberDiff.spec --noconfirm   -> dist/GerberDiff/
# Bundles the non-obvious data the renderers load at runtime, which a naive
# build misses: pypdfium2_raw/pdfium.dll + its two version.json files, and
# gerbonara/newstroke_font.cpp (the stroke font used to render silkscreen text).
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in ("pypdfium2", "pypdfium2_raw", "pygerber"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden
datas += collect_data_files("gerbonara")  # newstroke_font.cpp, cad/*.kicad_mod
datas += [("branding/app.ico", "branding")]  # window icon at runtime (sys._MEIPASS)
hiddenimports += collect_submodules("pyparsing")  # pygerber grammar safety net
hiddenimports += collect_submodules("gerberdiff")  # lazily-imported renderers/discovery

a = Analysis(
    ["app_entry.py"],  # absolute-import launcher; gui.py can't be a direct entry
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "pytest_cov", "ruff", "PyInstaller"],  # keep the bundle lean
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GerberDiff",
    console=False,  # windowed GUI app
    icon="branding/app.ico",
)
coll = COLLECT(exe, a.binaries, a.datas, name="GerberDiff")
