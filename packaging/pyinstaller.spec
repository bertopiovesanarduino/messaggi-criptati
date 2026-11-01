# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

import email
email_dir = os.path.dirname(email.__file__)

datas = [
    ('../assets', 'assets'),
    ('../config', 'config'),
    (email_dir, 'email'),
]
binaries = []
hiddenimports = [
    'sqlite3',
    'pystray',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'email',
    'email.message',
    'email.utils',
    'email.parser',
]

# Raccoglie in modo esaustivo tutti i file dati, binari e hiddenimports per Firebase e dipendenze
packages_to_collect = [
    'customtkinter',
    'cryptography',
    'firebase_admin',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google.auth',
    'google.api_core',
    'grpc',
]

for pkg in packages_to_collect:
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception as e:
        print(f"Warning collecting {pkg}: {e}")

a = Analysis(
    ['../main.py'],
    pathex=['..'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter.test', 'unittest'],
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
    name='SecureChatE2EE',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='../assets/app_icon.ico' if os.path.exists('../assets/app_icon.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SecureChatE2EE',
)
