
import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules



windows = Path(os.environ['SystemRoot'])
os.environ['PATH'] = os.pathsep.join(map(str, (
    Path(sys.base_prefix), Path(sys.base_prefix) / 'DLLs',
    windows / 'System32', windows,
)))

root = Path(SPECPATH)
hiddenimports = [
    'pynput.keyboard._win32', 'pynput.mouse._win32', 'pynput._util.win32',
    'comtypes.gen.UIAutomationClient',
] + collect_submodules('comtypes', filter=lambda name: '.test' not in name)

a = Analysis(
    [str(root / 'main.py')], pathex=[str(root)],
    binaries=[], datas=[(str(root / 'resources'), 'resources')],
    hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
              'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.Qt3DCore', 'PySide6.QtMultimedia',
              'tkinter', 'matplotlib', 'numpy', 'pandas', 'pytest', 'IPython'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name='Nexo',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon=str(root / 'resources' / 'nexo.ico'), uac_admin=False,
)
