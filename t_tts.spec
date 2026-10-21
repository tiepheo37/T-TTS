# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

block_cipher = None

# Thu thập dữ liệu và binary cho webview, pythonnet, clr_loader, cryptography
wv_datas, wv_binaries, wv_hidden = collect_all('webview')
pn_datas, pn_binaries, pn_hidden = collect_all('pythonnet')
cl_datas, cl_binaries, cl_hidden = collect_all('clr_loader')
crypto_datas, crypto_binaries, crypto_hidden = collect_all('cryptography')

datas = [
    ('web', 'web'),
    ('backend', 'backend'),
    ('app_icon.ico', '.'),
] + collect_data_files('vieneu') + collect_data_files('sea_g2p') + wv_datas + pn_datas + cl_datas + crypto_datas

binaries = wv_binaries + pn_binaries + cl_binaries + crypto_binaries

hiddenimports = [
    'desktop_main',
    'backend',
    'backend.app',
    'backend.license',
    'backend.tts_engine',
    'backend.audio_utils',
    'backend.history',
    'backend.pron_dict',
    'backend.models_bootstrap',
    'backend.storage',
    'backend.vieneu_adapter',
    'vieneu',
    'vieneu._v3_turbo_engine',
    'vieneu._v3_turbo_engine.onnx_runtime_lite',
    'onnxruntime',
    'torch',
    'flask',
    'scipy',
    'soundfile',
    'kaldi_native_fbank',
    'pypdf',
    'docx',
    'webview',
    'webview.platforms.winforms',
    'webview.platforms.edgechromium',
    'pythonnet',
    'clr_loader',
    'bottle',
    'proxy_tools',
] + wv_hidden + pn_hidden + cl_hidden + crypto_hidden

a = Analysis(
    ['desktop_main.py'],
    pathex=['.', 'backend'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch.distributions'],
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
