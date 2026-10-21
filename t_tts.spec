# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

block_cipher = None

# Thu thập dữ liệu và binary cho PySide6, cryptography, vieneu, sea_g2p
pyside_datas, pyside_binaries, pyside_hidden = collect_all('PySide6')
crypto_datas, crypto_binaries, crypto_hidden = collect_all('cryptography')

datas = [
    ('gui', 'gui'),
    ('backend', 'backend'),
    ('web', 'web'),
    ('app_icon.ico', '.'),
] + collect_data_files('vieneu') + collect_data_files('sea_g2p') + pyside_datas + crypto_datas

binaries = pyside_binaries + crypto_binaries

hiddenimports = [
    'desktop_main',
    'gui',
    'gui.styles',
    'gui.main_window',
    'gui.dialogs.license_dialog',
    'gui.pages.page_synthesize',
    'gui.pages.page_clone',
    'gui.pages.page_batch',
    'gui.pages.page_voices',
    'gui.pages.page_history',
    'gui.pages.page_settings',
    'gui.pages.page_about',
    'gui.pages.page_guide',
    'backend',
    'backend.service',
    'backend.audio_player',
    'backend.license',
    'backend.tts_engine',
    'backend.audio_utils',
    'backend.history',
    'backend.pron_dict',
    'backend.models_bootstrap',
    'backend.storage',
    'backend.vieneu_adapter',
    'backend.app',
    'vieneu',
    'vieneu._v3_turbo_engine',
    'vieneu._v3_turbo_engine.onnx_runtime_lite',
    'onnxruntime',
    'scipy',
    'soundfile',
    'kaldi_native_fbank',
    'pypdf',
    'docx',
    'imageio_ffmpeg',
    'PySide6',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'shiboken6',
] + pyside_hidden + crypto_hidden

a = Analysis(
    ['desktop_main.py'],
    pathex=['.', 'backend', 'gui'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch.distributions', 'webview', 'pythonnet', 'clr_loader', 'bottle', 'proxy_tools', 'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets'],
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
    name='T-TTS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='app_icon.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='T-TTS_v1.0.1_Exe_Portable',
)
