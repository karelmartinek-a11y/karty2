# PyInstaller executes this recipe on Windows; no cross-compiled binary is claimed.
from PyInstaller.utils.hooks import collect_data_files
from pathlib import Path
root=Path(SPECPATH)
datas=collect_data_files('kajovokarty')+collect_data_files('tzdata')
datas.append((str(root/'LICENSES'),'LICENSES'))
a=Analysis([str(root/'tools/launcher.py')],pathex=[str(root/'src')],binaries=[],datas=datas,hiddenimports=['sqlite3','PySide6.QtNetwork'],hookspath=[],runtime_hooks=[],excludes=['tkinter'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='KajovoKarty',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='KajovoKarty')
