# Build on Windows: .venv\Scripts\python -m PyInstaller --clean --noconfirm Biscuit.spec
from pathlib import Path
from importlib.util import find_spec
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH)
assets = root / 'desktop_pet' / 'assets'
data_files = [(str(path), 'desktop_pet/assets/' + str(path.parent.relative_to(assets)))
              for path in assets.rglob('*') if path.is_file()
              and '__pycache__' not in path.parts and path.suffix in ('.png', '.json', '.ttf', '.txt', '.py')]
data_files += collect_data_files('tzdata', include_py_files=True)
optional_imports = []
for module, distribution in (('psutil', 'psutil'), ('google.auth.transport.requests', 'google-auth'),
                             ('google.oauth2.credentials', 'google-auth'),
                             ('google_auth_oauthlib.flow', 'google-auth-oauthlib')):
    try:
        available = find_spec(module) is not None
    except (ModuleNotFoundError, ImportError):
        available = False
    if available:
        optional_imports.append(module)
        data_files += copy_metadata(distribution)

a = Analysis(
    [str(root / "run_pet.py")],
    pathex=[str(root)],
    binaries=[],
    datas=data_files,
    hiddenimports=["keyring.backends.Windows"] + collect_submodules('tzdata') + optional_imports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.QtSql", "PySide6.QtOpenGLWidgets", "pytest",
              "piper", "faster_whisper", "torch", "onnxruntime", "numpy"],
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
