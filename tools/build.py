"""Crea un eseguibile per il sistema operativo corrente con PyInstaller."""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--onefile',action='store_true',help='Un singolo file invece della cartella portabile')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent.parent
    sys.path.insert(0,str(root))
    from drawer import APP_NAME
    data=root/'examples'
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--name',APP_NAME,
             '--windowed','--onefile' if args.onefile else '--onedir',
             '--add-data',str(data)+os.pathsep+'examples',
             '--add-data',str(root/'README.md')+os.pathsep+'.',
             '--add-data',str(root/'THIRD_PARTY_NOTICES.md')+os.pathsep+'.',
             '--exclude-module','PySide6.QtWebEngineCore','--exclude-module','PySide6.QtWebEngineWidgets',
             '--exclude-module','PySide6.QtQml','--exclude-module','PySide6.QtQuick',str(root/'main.py')]
    environment=dict(os.environ,PYINSTALLER_CONFIG_DIR=str(root/'build'/'.pyinstaller'))
    subprocess.run(command,cwd=root,env=environment,check=True)
    print('Build completata. Distribuisci tutta la cartella dist/DrawER Studio.' if not args.onefile else 'Build completata: eseguibile in dist/.')


if __name__=='__main__':
    main()
