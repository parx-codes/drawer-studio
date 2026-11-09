"""La nuova area di lavoro dà priorità al progetto corrente."""
import os

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QPushButton

from drawer import __version__
from drawer.model import Document
from drawer.window import MainWindow


def test_example_is_only_in_help_submenu_and_new_project_stays_empty():
    app=QApplication.instance() or QApplication([])
    window=MainWindow(Document(),recovery=False)
    try:
        menus={action.text():action.menu() for action in window.menuBar().actions()}
        assert window.actions['demo'] not in menus['File'].actions()
        submenu=next(action.menu() for action in menus['Aiuto'].actions() if action.text()=='Esempi')
        assert window.actions['demo'] in submenu.actions()
        assert not [button for button in window.findChildren(QPushButton) if 'esempio' in button.text().casefold()]
        assert 'esempio' not in window.inspector_info.text().casefold()
        window.new_document()
        assert window.document.nodes==[] and window.document.links==[]
        assert not window.dirty
        assert window.windowTitle()=='DrawER Studio'
        assert __version__ not in window.windowTitle()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
