"""Editor tipografico delle note e documento condiviso da scena/esportazioni."""
from PySide6.QtCore import Qt, QSignalBlocker, QSize
from PySide6.QtGui import (QAction, QActionGroup, QColor, QFont, QTextDocument,
    QTextCharFormat, QTextCursor, QTextListFormat, QTextOption, QPalette)
from PySide6.QtWidgets import (QWidget, QTextEdit, QVBoxLayout, QToolBar,
    QFontComboBox, QComboBox, QColorDialog)

from .typography import diagram_font
from .note_html import sanitize_note_html


class LocalTextDocument(QTextDocument):
    """Le note non caricano immagini, file, stili o altre risorse esterne."""
    def loadResource(self, resource_type, name):
        return None


class LocalTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDocument(LocalTextDocument(self))
        self.setAcceptRichText(True)

    def setHtml(self, value):
        super().setHtml(sanitize_note_html(value))

    def canInsertFromMimeData(self, source):
        return source.hasText() or source.hasHtml()

    def insertFromMimeData(self, source):
        if source.hasHtml():
            try:
                self.textCursor().insertHtml(sanitize_note_html(source.html()))
            except ValueError:
                # Un incolla enorme o non valido resta semplice testo locale.
                self.textCursor().insertText(source.text())
        elif source.hasText():
            self.textCursor().insertText(source.text())


def create_note_document(node, width: float, ink: QColor) -> QTextDocument:
    """Restituisce il layout della nota, identico in canvas, PNG, SVG e PDF.

    Il chiamante imposta traslazione e ritaglio del painter e chiama
    document.drawContents(painter). Il documento non possiede il painter.
    """
    document = LocalTextDocument()
    document.setDefaultFont(diagram_font())
    document.setDocumentMargin(0)
    document.setDefaultStyleSheet(f'p,li,div {{ color: {ink.name()}; }}')
    option = document.defaultTextOption()
    option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    document.setDefaultTextOption(option)
    if node.text_html:
        document.setHtml(sanitize_note_html(node.text_html))
    else:
        document.setPlainText(node.name)
        cursor = QTextCursor(document)
        cursor.select(QTextCursor.Document)
        block = cursor.blockFormat()
        block.setAlignment(Qt.AlignCenter)
        cursor.mergeBlockFormat(block)
        foreground = QTextCharFormat()
        foreground.setForeground(ink)
        cursor.mergeCharFormat(foreground)
    document.setTextWidth(max(1, width))
    return document


class RichTextEditor(QWidget):
    """Formattazione su testo selezionato o sulle successive digitazioni."""
    def __init__(self, text='', html='', parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(4)
        self.text_edit = LocalTextEdit(self)
        self.text_edit.setObjectName('nodeName')
        self.text_edit.setMinimumHeight(190)
        self.text_edit.setFont(diagram_font())
        self.text_edit.document().setDefaultFont(diagram_font())
        self.toolbar = QToolBar(self)
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(16,16))
        self.actions = {}
        for key, label, tip, shortcut in (
            ('bold','G','Grassetto','Ctrl+B'), ('italic','C','Corsivo','Ctrl+I'),
            ('underline','S','Sottolineato','Ctrl+U'), ('strike','abc','Barrato',None)):
            action = QAction(label,self)
            action.setObjectName('format_'+key)
            action.setToolTip(tip + (f' ({shortcut})' if shortcut else ''))
            action.setCheckable(True)
            font = action.font()
            font.setBold(key=='bold');font.setItalic(key=='italic')
            font.setUnderline(key=='underline');font.setStrikeOut(key=='strike')
            action.setFont(font)
            if shortcut:
                action.setShortcut(shortcut)
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            action.triggered.connect(lambda checked,k=key:self._style(k,checked))
            self.addAction(action)
            self.toolbar.addAction(action)
            self.actions[key]=action
        self.toolbar.addSeparator()
        self.font_family = QFontComboBox(self)
        self.font_family.setObjectName('noteFontFamily')
        self.font_family.setMaximumWidth(155)
        self.font_family.setToolTip('Carattere')
        self.font_family.currentFontChanged.connect(self._font_family)
        self.toolbar.addWidget(self.font_family)
        self.font_size = QComboBox(self)
        self.font_size.setObjectName('noteFontSize')
        self.font_size.setEditable(True)
        self.font_size.addItems(['6','8','9','10','11','12','14','16','18','20','24','28','36','48','72','96'])
        self.font_size.setMaximumWidth(70)
        self.font_size.setToolTip('Dimensione del carattere in punti')
        self.font_size.activated.connect(lambda:self._font_size())
        self.font_size.lineEdit().editingFinished.connect(self._font_size)
        self.toolbar.addWidget(self.font_size)
        color = QAction('Colore…',self)
        color.setObjectName('format_color')
        color.triggered.connect(self._choose_color)
        self.toolbar.addAction(color)
        self.actions['color']=color
        layout.addWidget(self.toolbar)
        self.paragraph_toolbar = QToolBar(self)
        self.paragraph_toolbar.setMovable(False)
        group = QActionGroup(self)
        group.setExclusive(True)
        self.alignment_actions = {}
        for key,label,alignment in (('left','Sinistra',Qt.AlignLeft),('center','Centro',Qt.AlignHCenter),('right','Destra',Qt.AlignRight),('justify','Giustifica',Qt.AlignJustify)):
            action=QAction(label,self)
            action.setCheckable(True)
            action.setObjectName('align_'+key)
            action.triggered.connect(lambda checked,a=alignment:self.text_edit.setAlignment(a))
            group.addAction(action)
            self.paragraph_toolbar.addAction(action)
            self.alignment_actions[alignment]=action
        self.paragraph_toolbar.addSeparator()
        for key,label,style in (('bullets','• Elenco',QTextListFormat.ListDisc),('numbers','1. Elenco',QTextListFormat.ListDecimal)):
            action=QAction(label,self)
            action.setObjectName('format_'+key)
            action.triggered.connect(lambda checked=False,s=style:self._toggle_list(s))
            self.paragraph_toolbar.addAction(action)
            self.actions[key]=action
        layout.addWidget(self.paragraph_toolbar)
        layout.addWidget(self.text_edit,1)
        if html:
            self.text_edit.setHtml(html)
        else:
            self.text_edit.setPlainText(text)
            self.text_edit.selectAll()
            self.text_edit.setAlignment(Qt.AlignCenter)
            cursor=self.text_edit.textCursor();cursor.clearSelection();cursor.movePosition(QTextCursor.Start)
            self.text_edit.setTextCursor(cursor)
        self.text_edit.currentCharFormatChanged.connect(self._sync)
        self.text_edit.cursorPositionChanged.connect(self._sync)
        self._sync()

    def _merge(self, fmt):
        self.text_edit.mergeCurrentCharFormat(fmt)
        self.text_edit.setFocus()

    def _style(self,key,checked):
        fmt=QTextCharFormat()
        if key=='bold':fmt.setFontWeight(QFont.Bold if checked else QFont.Normal)
        elif key=='italic':fmt.setFontItalic(checked)
        elif key=='underline':fmt.setFontUnderline(checked)
        elif key=='strike':fmt.setFontStrikeOut(checked)
        self._merge(fmt)

    def _font_family(self,font):
        fmt=QTextCharFormat();fmt.setFontFamilies([font.family()]);self._merge(fmt)

    def _font_size(self):
        try:size=float(self.font_size.currentText().replace(',','.'))
        except ValueError:return
        if 6<=size<=96:
            fmt=QTextCharFormat();fmt.setFontPointSize(size);self._merge(fmt)

    def _choose_color(self):
        current=self.text_edit.textColor()
        if not current.isValid():current=self.palette().color(QPalette.Text)
        color=QColorDialog.getColor(current,self,'Colore del testo')
        if color.isValid():self.set_text_color(color)

    def set_text_color(self,color):
        fmt=QTextCharFormat();fmt.setForeground(QColor(color));self._merge(fmt)

    def _toggle_list(self,style):
        cursor=self.text_edit.textCursor()
        current=cursor.currentList()
        cursor.beginEditBlock()
        if current and current.format().style()==style:
            first,last=cursor.selectionStart(),cursor.selectionEnd()
            block=self.text_edit.document().findBlock(first)
            while block.isValid() and block.position()<=last:
                existing=block.textList()
                if existing:existing.remove(block)
                block_cursor=QTextCursor(block)
                fmt=block_cursor.blockFormat();fmt.setIndent(0);block_cursor.setBlockFormat(fmt)
                if not cursor.hasSelection():break
                block=block.next()
        else:
            fmt=QTextListFormat();fmt.setStyle(style);fmt.setIndent(1);cursor.createList(fmt)
        cursor.endEditBlock()
        self.text_edit.setFocus()

    def _sync(self,*args):
        fmt=self.text_edit.currentCharFormat()
        values={'bold':fmt.fontWeight()>=QFont.Bold,'italic':fmt.fontItalic(),'underline':fmt.fontUnderline(),'strike':fmt.fontStrikeOut()}
        for key,value in values.items():
            with QSignalBlocker(self.actions[key]):self.actions[key].setChecked(value)
        with QSignalBlocker(self.font_family):self.font_family.setCurrentFont(self.text_edit.currentFont())
        with QSignalBlocker(self.font_size):self.font_size.setCurrentText(f'{self.text_edit.fontPointSize() or 10:g}')
        alignment=self.text_edit.alignment()
        for value,action in self.alignment_actions.items():
            with QSignalBlocker(action):action.setChecked(bool(alignment & value))

    def get_html(self):
        return sanitize_note_html(self.text_edit.toHtml())

    def toPlainText(self):
        return self.text_edit.toPlainText()

    def selectAll(self):
        self.text_edit.selectAll()

    def setFocus(self,*args):
        self.text_edit.setFocus(*args)
