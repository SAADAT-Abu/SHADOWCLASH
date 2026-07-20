# PyInstaller spec — builds a standalone one-dir bundle of SHADOWCLASH.
# Used by .github/workflows/build-desktop.yml on Windows/macOS/Linux runners;
# also works locally: pyinstaller shadowclash.spec
#
# assets/ and config/ land at the bundle root, which is where the game's
# Path(__file__).parents[2] lookups resolve to when frozen (sys._MEIPASS).

from PyInstaller.utils.hooks import collect_all

datas = [("assets", "assets"), ("config", "config")]
binaries = []
hiddenimports = []

# mediapipe ships .tflite models and graph configs as package data
for pkg in ("mediapipe",):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["shadowclash/main.py"],
    pathex=["."],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="shadowclash",
    console=True,  # keep the log window; hits/tokens are also shown in-game
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="shadowclash",
)
