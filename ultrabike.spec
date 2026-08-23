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
    (str(ROOT / "Assets" / "i18n" / "*.json"), "Assets/i18n"),
    (str(ROOT / "Assets" / "Sounds" / "*.wav"), "Assets/Sounds"),
    (str(ROOT / "VERSION.txt"), "."),
]

# Optional icon (won't fail if missing)
_icon = ROOT / "might work.ico"
_icon_path = str(_icon) if _icon.exists() else None

# The EXE icon is embedded via EXE(icon=...), but the running Qt app also loads
# the .ico at runtime to set the window/taskbar icon. Bundle it as data so
# Utilities.ResourcePaths.resource_path() can find it in sys._MEIPASS.
if _icon.exists():
    _datas.append((str(_icon), "."))


a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        # Authenticated screens are registered by module name and imported lazily.
        "GUI_Qt.screens.UploadScreen",
        "GUI_Qt.screens.UnifiedBatchScreen",
        "GUI_Qt.screens.DescriptionsScreen",
        "GUI_Qt.screens.FolderCreatorScreen",
        "GUI_Qt.screens.TranslationsScreen",
        "GUI_Qt.screens.AnalyticsScreen",
        "GUI_Qt.screens.EarningsScreen",
        "GUI_Qt.screens.SpotifyScreen",
        "GUI_Qt.screens.ActivityScreen",
        "GUI_Qt.screens.SpecCheckerScreen",
        "GUI_Qt.screens.NameGetterScreen",
        "GUI_Qt.screens.CodeGetterScreen",
        "GUI_Qt.screens.ProductNameGetterScreen",
        "GUI_Qt.screens.BassoImageScreen",
        "GUI_Qt.screens.PinarelloImageScreen",
        "GUI_Qt.screens.CastelliUrlGetterScreen",
        "GUI_Qt.screens.CastelliImageDownloaderScreen",
        "GUI_Qt.screens.AbusUrlGetterScreen",
        "GUI_Qt.screens.OakleyUrlGetterScreen",
        "GUI_Qt.screens.AccountScreen",
        "GUI_Qt.screens.SettingsScreen",
        "GUI_Qt.screens.InfoScreen",
        # The Orbea screen loads these services lazily after login. Keep them
        # explicit so frozen builds include the complete workflow.
        "GUI_Qt.screens.OrbeaScreen",
        "tools.orbea_automation",
        "tools.orbea_automation.catalogue",
        "tools.orbea_automation.checkpoint",
        "tools.orbea_automation.descriptions",
        "tools.orbea_automation.models",
        "tools.orbea_automation.photos",
        "tools.orbea_automation.pimbo",
        "tools.orbea_automation.report",
        "tools.orbea_automation.service",
        "tools.orbea_automation.utils",
        "tools.orbea_table_image_downloader",
    ],
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
