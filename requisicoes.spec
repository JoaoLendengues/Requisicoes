# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec — Requisições Pinheiro (cliente desktop)
#
# Uso manual:
#   pyinstaller requisicoes.spec --noconfirm
#
# Saída: dist/requisicoes/requisicoes.exe + dist/requisicoes/_internal/

from PyInstaller.utils.hooks import collect_all

# Coleta todos os binários, dados e imports ocultos do PySide6
pyside6_datas, pyside6_binaries, pyside6_hiddenimports = collect_all('PySide6')

block_cipher = None

a = Analysis(
    ['client/main.py'],
    pathex=['.'],                      # raiz do projeto no sys.path
    binaries=pyside6_binaries,
    datas=[
        # Assets visuais (ícones, logos, fontes)
        ('client/assets', 'client/assets'),
        # Configurações padrão do cliente
        ('client/settings.json', 'client'),
        # Todos os dados do PySide6 (plugins, traduções, etc.)
        *pyside6_datas,
    ],
    hiddenimports=[
        *pyside6_hiddenimports,
        'requests',
        'reportlab',
        'reportlab.pdfgen',
        'reportlab.pdfgen.canvas',
        'reportlab.lib',
        'reportlab.lib.pagesizes',
        'reportlab.lib.styles',
        'reportlab.platypus',
        'PIL',
        'PIL.Image',
        'qrcode',
        'qrcode.image.pil',
        'odf',
        'odf.opendocument',
        'openpyxl',
        'pandas',
        'dotenv',
        'psutil',
        'httpx',
        'httpcore',
        'h11',
        'certifi',
        'anyio',
        'anyio._backends._asyncio',
        'anyio._backends._trio',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Dependências do servidor — não são necessárias no cliente
        'fastapi',
        'uvicorn',
        'sqlalchemy',
        'psycopg2',
        'pydantic',
        'starlette',
        'jose',
        'passlib',
        'aiofiles',
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
    [],
    exclude_binaries=True,
    name='requisicoes',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # sem janela de terminal
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='client/assets/icons/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='requisicoes',     # gera dist/requisicoes/
)
