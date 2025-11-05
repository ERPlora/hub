# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for CPOS Hub
Builds cross-platform executable for Windows, macOS, and Linux
"""

import sys
from pathlib import Path

block_cipher = None

# Get base directory
BASE_DIR = Path('.').absolute()

# Collect Django and plugin files
datas = [
    ('apps/core/templates', 'apps/core/templates'),
    ('apps/core/static', 'apps/core/static'),
    ('apps/pos/templates', 'apps/pos/templates'),
    ('apps/pos/static', 'apps/pos/static'),
    ('apps/products/templates', 'apps/products/templates'),
    ('apps/products/static', 'apps/products/static'),
    ('apps/sales/templates', 'apps/sales/templates'),
    ('apps/sales/static', 'apps/sales/static'),
    ('apps/plugins/templates', 'apps/plugins/templates'),
    ('apps/hardware/templates', 'apps/hardware/templates'),
    ('apps/sync/templates', 'apps/sync/templates'),
    ('config/settings.py', 'config'),
    ('config/urls.py', 'config'),
    ('plugins', 'plugins'),  # Include plugins directory
]

# Hidden imports (Django apps and dependencies)
hiddenimports = [
    'django',
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.core',
    'apps.pos',
    'apps.products',
    'apps.sales',
    'apps.plugins',
    'apps.hardware',
    'apps.sync',
    'sqlite3',
    'PIL',
    'PIL._imaging',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='CPOS-Hub',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='static/icon.ico' if sys.platform == 'win32' else 'static/icon.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CPOS-Hub',
)

# macOS App Bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='CPOS Hub.app',
        icon='static/icon.icns',
        bundle_identifier='com.cpos.hub',
        info_plist={
            'CFBundleName': 'CPOS Hub',
            'CFBundleDisplayName': 'CPOS Hub',
            'CFBundleShortVersionString': '1.0.0',
            'CFBundleVersion': '1.0.0',
            'NSHighResolutionCapable': 'True',
            'LSMinimumSystemVersion': '10.13',
        },
    )
