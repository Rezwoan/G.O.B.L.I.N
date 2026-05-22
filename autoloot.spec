# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for G.O.B.L.I.N AutoLoot CoC v3

import sys
from pathlib import Path

block_cipher = None

# Collect all data files
datas = [
    ('models/*',       'models'),
    ('config.toml',    '.'),
    ('priorities.toml','.',),
    ('tasks.toml',     '.'),
    ('armies.toml',    '.'),
]

# Add Tesseract binaries if present alongside the project
tesseract_dir = Path('tesseract')
if tesseract_dir.exists():
    datas.append(('tesseract/*', 'tesseract'))

hidden_imports = [
    'ultralytics',
    'ultralytics.nn',
    'ultralytics.nn.tasks',
    'ultralytics.utils',
    'customtkinter',
    'pytesseract',
    'cv2',
    'PIL',
    'PIL.Image',
    'requests',
    'numpy',
    'toml',
    'sqlite3',
    'keyboard',
    'core.adb',
    'core.vision',
    'core.ocr',
    'core.state_machine',
    'core.navigator',
    'engines.attack_engine',
    'engines.upgrade_engine',
    'engines.collect_engine',
    'engines.task_engine',
    'strategies',
    'strategies.surround',
    'strategies.one_side',
    'strategies.one_corner',
    'notify',
    'notify.discord',
    'notify.telegram',
    'gui.app',
    'gui.dashboard',
    'gui.tasks_tab',
    'gui.upgrades_tab',
    'gui.army_tab',
    'gui.settings_tab',
    'gui.log_view',
    'data.db',
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='GOBLIN',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # windowed — no console
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
    onefile=True,
)
