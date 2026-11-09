"""Palette coerente per finestre, pannelli e strumenti."""
from PySide6.QtGui import QColor, QPalette


def apply_theme(app, dark=False):
    bg, panel, text, muted, border = ('#15222d','#20313e','#e6eef2','#9db0bd','#354b58') if dark else ('#f4f7f8','#ffffff','#203847','#657c89','#dce5e9')
    palette = QPalette()
    for role,color in ((QPalette.Window,bg),(QPalette.WindowText,text),(QPalette.Base,panel),(QPalette.AlternateBase,bg),
                       (QPalette.Text,text),(QPalette.Button,panel),(QPalette.ButtonText,text),(QPalette.ToolTipBase,panel),
                       (QPalette.ToolTipText,text),(QPalette.Highlight,'#087f73'),(QPalette.HighlightedText,'#ffffff')):
        palette.setColor(role,QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(f'''
        QWidget {{ font-family: 'Inter', 'Segoe UI', 'Noto Sans', sans-serif; font-size: 13px; }}
        QMainWindow, QDialog {{ background: {bg}; }}
        QMenuBar, QToolBar, QStatusBar {{ background: {panel}; color: {text}; }}
        QMenuBar {{ padding: 3px 8px; }}
        QToolBar {{ border: 0; border-bottom: 1px solid {border}; spacing: 7px; padding: 8px 12px; }}
        QToolButton {{ padding: 7px 10px; border-radius: 5px; }}
        QToolButton:hover, QMenu::item:selected {{ background: #087f73; color: white; }}
        QPushButton {{ background: {panel}; color: {text}; border: 1px solid {border}; border-radius: 6px; padding: 8px 10px; }}
        QPushButton:hover {{ border-color: #0b9788; }}
        QPushButton:checked, QPushButton#primary {{ background: #087f73; border-color: #087f73; color: white; }}
        QPushButton:disabled {{ color: {muted}; }}
        QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: {panel}; color: {text}; border: 1px solid {border}; border-radius: 5px; padding: 6px; selection-background-color: #087f73; }}
        QTreeWidget, QListWidget {{ background: {panel}; border: none; outline: 0; }}
        QTreeWidget::item, QListWidget::item {{ padding: 5px 2px; }}
        QTreeWidget::item:selected, QListWidget::item:selected {{ background: #087f73; color: white; }}
        QDockWidget {{ font-weight: 600; }}
        QDockWidget::title {{ background: {bg}; padding: 10px; color: {muted}; }}
        QLabel#brand {{ font-size: 22px; font-weight: 700; color: #087f73; }}
        QLabel#eyebrow {{ color: {muted}; font-size: 11px; font-weight: 600; }}
        QLabel#title {{ font-size: 19px; font-weight: 600; color: {text}; }}
        QLabel#muted {{ color: {muted}; }}
        QFrame#canvasbar {{ background: {panel}; border-bottom: 1px solid {border}; }}
        QStatusBar {{ border-top: 1px solid {border}; padding: 3px; }}
        QGroupBox {{ border: 1px solid {border}; border-radius: 5px; margin-top: 12px; padding-top: 14px; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 10px; }}
        QSplitter::handle {{ background: {border}; width: 1px; }}
    ''')
