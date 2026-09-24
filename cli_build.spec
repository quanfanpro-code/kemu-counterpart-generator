# -*- mode: python ; coding: utf-8 -*-
# 序时账分析器命令行版打包配置（排除 GUI 和不相关大库，减小体积）

a = Analysis(
    ['cli/序时账分析器命令行版.py'],
    pathex=['.'],
    binaries=[],
    datas=[('src/中国节假日.json', 'src')],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=['customtkinter', 'tkinter', 'torch', 'scipy', 'matplotlib',
              'pytest', 'pyarrow', 'numba'],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ledger-cli',
    console=True,
)
