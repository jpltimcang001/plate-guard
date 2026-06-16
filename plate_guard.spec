# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Plate Guard — License Plate Recognition Desktop App
#
# Build commands:
#   pyinstaller plate_guard.spec
#   pyinstaller plate_guard.spec -- --version 1.0.1    (override version)
#

import sys
import os
from pathlib import Path

# ---- Read version from CLI argument or default ---------------------------
# Usage: pyinstaller plate_guard.spec
#        pyinstaller plate_guard.spec -- --version 1.2.3
BLOCK_CALL = None
version = "1.0.0"
if "--version" in sys.argv:
    idx = sys.argv.index("--version")
    try:
        version = sys.argv[idx + 1]
    except IndexError:
        pass

# ---- Paths ---------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.resolve()
SRC_DIR = PROJECT_ROOT / "src"
MODELS_DIR = PROJECT_ROOT / "models"
ASSETS_DIR = PROJECT_ROOT / "assets"
INSTALLER_DIR = PROJECT_ROOT / "installer"

# ---- Collect all packages with hidden imports ----------------------------
# PyInstaller's hook mechanism handles most packages, but some need
# explicit listing because of dynamic imports.

hidden_imports = [
    # SQLAlchemy & database
    "sqlalchemy",
    "sqlalchemy.sql.default_comparator",
    "sqlalchemy.ext.declarative",
    "sqlalchemy.orm",
    # OpenCV
    "cv2",
    "numpy",
    # YOLO / Ultralytics
    "ultralytics",
    "ultralytics.nn.tasks",
    "ultralytics.models.yolo.detect.predict",
    "torch",
    "torchvision",
    # PaddleOCR (lazy-loaded, must be included explicitly)
    "paddleocr",
    "paddle",
    "paddle.nn",
    "paddle.tensor",
    "paddle.fluid",
    "shapely",
    # httpx & http core
    "httpx",
    "httpcore",
    "h11",
    "h2",
    # GUI
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtSvg",
    # Logging
    "loguru",
    # Other
    "yaml",
    "tqdm",
    "requests",
    "certifi",
    "charset_normalizer",
    "idna",
    "urllib3",
]

# Binaries that must be collected (DLLs, .so files)
binaries = []

# ---------------------------------------------------------------------------
# Data files
# ---------------------------------------------------------------------------

datas = []

# 1. YOLO model — bundle if it exists, otherwise include a placeholder notice
model_src = MODELS_DIR / "plate.pt"
if model_src.is_file():
    datas.append((str(model_src), "models"))
else:
    print(
        "WARNING: models/plate.pt not found. "
        "The packaged app will fail to start YOLO detection "
        "until a model file is placed at models/plate.pt.",
        file=sys.stderr,
    )

# 2. Assets (icons, resources)
if ASSETS_DIR.is_dir():
    for item in ASSETS_DIR.rglob("*"):
        if item.is_file():
            datas.append((str(item), str(item.relative_to(PROJECT_ROOT).parent)))

# 3. Installer scripts bundled for reference (optional)
if INSTALLER_DIR.is_dir():
    for item in INSTALLER_DIR.rglob("*"):
        if item.is_file() and item.suffix in {".iss", ".ps1", ".bat", ".cmd"}:
            datas.append((str(item), "installer"))

# ---------------------------------------------------------------------------
# Hook overrides for packages that PyInstaller struggles with
# ---------------------------------------------------------------------------

# PaddleOCR needs its pretrained models at runtime.
# We tell PyInstaller to collect paddle's data files.
# In practice, PaddleOCR downloads models to ~/.paddleocr/ on first use.
# We bundle the download dir hint here:
for hook_dir in ("paddleocr", "paddle"):
    for pattern in ("*.pdmodel", "*.pdiparams", "*.pdopt", "*.txt", "*.yml"):
        pass  # handled via --collect-data in build script, not here

# ---------------------------------------------------------------------------
# Exclusions
# ---------------------------------------------------------------------------

excludes = [
    "tkinter",
    "test",
    "unittest",
    "pytest",
    "distutils",
    "setuptools",
    "numpy._distributor_init",  # often causes issues
]

# ---------------------------------------------------------------------------
# Block cipher for obfuscation (optional — uncomment to enable)
# ---------------------------------------------------------------------------
# from pyinstaller import cryptography
# key = cryptography.fernet.Fernet.generate_key()
# block_cipher = key.decode("utf-8")

block_cipher = None

# ---------------------------------------------------------------------------
# Main EXE and bundle
# ---------------------------------------------------------------------------

a = Analysis(
    [str(SRC_DIR / "__main__.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    block_cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="PlateGuard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # Windowed app (no console) — system tray app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ASSETS_DIR / "icon.ico") if (ASSETS_DIR / "icon.ico").is_file() else None,
)

# ---------------------------------------------------------------------------
# Bundle into a single directory (not one-file) for:
#   - Faster startup (no extraction)
#   - Easier debugging
#   - OpenCV / FFmpeg codec access
# ---------------------------------------------------------------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PlateGuard",
)

# ---------------------------------------------------------------------------
# Create a version file for the EXE metadata
# ---------------------------------------------------------------------------
if hasattr(a, "make_versinfo"):
    try:
        # noinspection PyUnresolvedReferences
        a.make_versinfo(
            version=version,
            company_name="Plate Guard",
            product_name="Plate Guard LPR",
            file_description="License Plate Recognition Desktop Application",
            legal_copyright=f"© {__import__('datetime').datetime.now().year} Plate Guard",
            internal_name="PlateGuard",
            original_filename="PlateGuard.exe",
        )
    except Exception:
        pass  # versinfo is best-effort
