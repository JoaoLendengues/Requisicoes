# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec — update_helper (executável standalone)
#
# Uso manual:
#   pyinstaller update_helper.spec --noconfirm
#
# Saída: dist/update_helper/update_helper.exe   (onefile)
#
# IMPORTANTE:
#   Este executável deve estar presente no pacote portátil (ZIP) junto com
#   requisicoes.exe e _internal/, para que a atualização possa se auto-atualizar.
#   O GitHub Actions o inclui automaticamente (ver build_release.yml).

block_cipher = None

a = Analysis(
    ['client/update_helper.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=['psutil'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6', 'PyQt5', 'PyQt6', 'tkinter',
        'fastapi', 'uvicorn', 'sqlalchemy', 'psycopg2',
        'pandas', 'reportlab', 'PIL', 'qrcode', 'openpyxl',
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
    name='update_helper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=True,          # precisa de console para logging via stdout (roda em background)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
