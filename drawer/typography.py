"""Computer Modern per il diagramma, indipendente dai font installati."""
from functools import cache
from pathlib import Path
import sys

from PySide6.QtGui import QFont, QFontDatabase


@cache
def _diagram_family():
    root = Path(sys._MEIPASS) / 'fonts' if hasattr(sys, '_MEIPASS') else Path(__file__).parent / 'fonts'
    family = 'Sans Serif'
    for name in ('cmunrm', 'cmunbx', 'cmunti', 'cmunbi'):
        identifier = QFontDatabase.addApplicationFont(str(root / (name + '.otf')))
        if name == 'cmunrm' and identifier >= 0:
            family = QFontDatabase.applicationFontFamilies(identifier)[0]
    return family


def diagram_font(size=10):
    return QFont(_diagram_family(), size)
