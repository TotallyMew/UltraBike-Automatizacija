# -*- mode: python ; coding: utf-8 -*-

# PyInstaller spec for UltraBike_Automatizacija (Windows)
#
# Produces a windowed Qt app (no console) and bundles only non-sensitive assets.
# Runtime data (DB/session/settings) is stored per-user in %APPDATA%\UltraBike_Automatizacija
# via Utilities/AppPaths.py so it should NOT be shipped alongside the executable.

from pathlib import Path

block_cipher = None

# PyInstaller provides SPECPATH; __file__ may be undefined depending on how the spec is executed.
ROOT = Path(SPECPATH).resolve() if 'SPECPATH' in globals() else Path.cwd().resolve()

# Non-sensitive runtime resources that must be available in frozen builds
_datas = [
    (str(ROOT / "Assets" / "Translations" / "*.txt"), "Assets/Translations"),
]

# Optional icon (won't fail if missing)
_icon = ROOT / "might work.ico"
_icon_path = str(_icon) if _icon.exists() else None


a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=_datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # We no longer ship the legacy Flet UI.
        "flet",
        "flet_desktop",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="UltraBike_Automatizacija",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=_icon_path,
)
