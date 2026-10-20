# Build on Windows: .venv\Scripts\python -m PyInstaller --clean --noconfirm Biscuit.spec
from pathlib import Path

root = Path(SPECPATH)
a = Analysis(
    [str(root / "run_pet.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "desktop_pet" / "assets"), "desktop_pet/assets")],
    hiddenimports=["keyring.backends.Windows"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.QtSql", "PySide6.QtOpenGLWidgets", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="Biscuit",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon=str(root / "desktop_pet" / "assets" / "biscuit.png"),
    version=str(root / "scripts" / "windows-version.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Biscuit")
