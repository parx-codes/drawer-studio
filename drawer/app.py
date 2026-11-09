"""Ingresso GUI e modalità di verifica non interattiva."""
import argparse
import os
import sys
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description='DrawER Studio — diagrammi Entità-Relazione')
    parser.add_argument('project',nargs='?',help='File .erdraw da aprire')
    parser.add_argument('--demo',action='store_true',help='Apri l’esempio universitario')
    parser.add_argument('--smoke-test',action='store_true',help='Verifica avvio ed esportazioni senza interazione')
    parser.add_argument('--output-dir',default='verification',help='Cartella degli artefatti della verifica')
    args=parser.parse_args()
    if args.smoke_test:os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from .window import MainWindow, resource_root
    from .storage import load_document
    from . import __version__, APP_NAME
    app=QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName('DrawER')
    app.setStyle('Fusion')
    path=Path(args.project) if args.project else resource_root()/'examples'/'universita.erdraw' if args.demo or args.smoke_test else None
    try:document=load_document(path) if path else None
    except (OSError,ValueError) as error:
        if args.smoke_test:raise
        QMessageBox.critical(None,'Impossibile aprire il progetto',str(error));return 1
    window=MainWindow(document,path if args.project else None,recovery=not args.smoke_test)
    window.show()
    if document:QTimer.singleShot(0,window.view.fit_diagram)
    if not args.smoke_test:
        QTimer.singleShot(0,window.maybe_show_tutorial)
    if args.smoke_test:
        from .exports import export_diagram
        from .sql import generate_sql
        from .storage import save_document
        app.processEvents()
        window.view.fit_diagram()
        app.processEvents()
        output=Path(args.output_dir);output.mkdir(parents=True,exist_ok=True)
        window.grab().save(str(output/'drawer-desktop.png'))
        for kind in ('png','svg','pdf'):export_diagram(window.scene,output/('universita.'+kind),kind)
        for dialect in ('sqlite','postgresql'):(output/('universita-'+dialect+'.sql')).write_text(generate_sql(window.document,dialect),encoding='utf-8')
        save_document(window.document,output/'universita.erdraw')
        print('Avvio, rendering, PNG, SVG, PDF, JSON e SQL completati:',output.resolve())
        window.close()
        return 0
    return app.exec()
