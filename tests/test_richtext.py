"""Formattazione reale, persistenza e risorse delle note del diagramma."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from copy import deepcopy
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QMimeData, Qt, QUrl
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QTextCursor, QTextDocument, QTextListFormat
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QTextEdit

from drawer.dialogs import edit_node
from drawer.model import Document, Node
from drawer.note_html import MAX_NOTE_HTML, MAX_NOTE_TEXT, sanitize_note_html
from drawer.richtext import LocalTextDocument, RichTextEditor, create_note_document
from drawer.storage import load_document, save_document


@pytest.fixture(scope='module')
def app():
    application=QApplication.instance() or QApplication([])
    yield application
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


@pytest.fixture
def editor(app):
    widget=RichTextEditor('Chiave e descrizione')
    yield widget
    widget.deleteLater()
    app.processEvents()
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


def select(editor,start,end):
    cursor=editor.text_edit.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(end,QTextCursor.KeepAnchor)
    editor.text_edit.setTextCursor(cursor)


def char_format(document,position):
    cursor=QTextCursor(document)
    cursor.setPosition(position)
    cursor.movePosition(QTextCursor.NextCharacter,QTextCursor.KeepAnchor)
    return cursor.charFormat()


def render(document):
    image=QImage(700,250,QImage.Format_ARGB32)
    image.fill(Qt.white)
    painter=QPainter(image)
    document.drawContents(painter)
    painter.end()
    return image


def colored_pixels(image,color):
    color=QColor(color)
    return sum(abs(image.pixelColor(x,y).red()-color.red())<15 and
               abs(image.pixelColor(x,y).green()-color.green())<15 and
               abs(image.pixelColor(x,y).blue()-color.blue())<15
               for y in range(image.height()) for x in range(image.width()))


def test_html_subset_blocks_resources_and_active_content():
    unsafe='''<html><head><style>p{background:url(file:///secret)}</style></head><body>
    <p onclick="run()" style="color:#00aa44;font-size:18pt;background-image:url(https://bad)">
    <b>Perché</b> <i>è</i> <u>utile</u><img src="file:///secret"><a href="https://bad">link</a>
    <script>alert('bad')</script><iframe src="https://bad">hidden</iframe></p></body></html>'''
    safe=sanitize_note_html(unsafe)
    assert '<b>Perché</b>' in safe and '<i>è</i>' in safe and '<u>utile</u>' in safe
    assert 'color:#00aa44' in safe and 'font-size:18pt' in safe
    for forbidden in ('onclick','url(','file:','https:','script','iframe','img','hidden','alert('):
        assert forbidden not in safe
    assert sanitize_note_html(safe)==safe


def test_model_loads_old_plain_notes_and_bounds_rich_text():
    old=Document(nodes=[Node(kind='text',name='Nota della v1.0')]).to_dict()
    old['nodes'][0].pop('text_html')
    assert Document.from_dict(old).nodes[0].text_html==''
    rich=Document(nodes=[Node(kind='text',name='à'*5000,text_html='<p><b>à</b></p>')]).to_dict()
    assert len(Document.from_dict(rich).nodes[0].name)==5000
    too_long=deepcopy(rich);too_long['nodes'][0]['text_html']='x'*(MAX_NOTE_HTML+1)
    with pytest.raises(ValueError,match='Formattazione'):Document.from_dict(too_long)
    too_long=deepcopy(rich);too_long['nodes'][0]['name']='x'*(MAX_NOTE_TEXT+1)
    with pytest.raises(ValueError,match='Testo nota'):Document.from_dict(too_long)
    entity=Document(nodes=[Node(name='E',text_html='<b>non nota</b>')]).to_dict()
    with pytest.raises(ValueError,match='solo per le note'):Document.from_dict(entity)


def test_imported_html_is_sanitized_without_qt_model_dependencies():
    raw=Document(nodes=[Node(kind='text',name='Testo',text_html='<p><b>Testo</b><img src="https://bad/x"></p>')]).to_dict()
    restored=Document.from_dict(raw)
    assert restored.nodes[0].text_html=='<p style="white-space:pre-wrap"><b>Testo</b></p>'


def test_selected_bold_italic_underline_and_color_roundtrip(editor,tmp_path):
    select(editor,0,6)
    for key in ('bold','italic','underline'):editor.actions[key].trigger()
    editor.set_text_color(QColor('#bc1234'))
    editor.font_size.setCurrentText('18')
    editor._font_size()
    fmt=char_format(editor.text_edit.document(),1)
    assert fmt.fontWeight()>=QFont.Bold and fmt.fontItalic() and fmt.fontUnderline()
    untouched=char_format(editor.text_edit.document(),10)
    assert not untouched.fontItalic() and not untouched.fontUnderline()
    node=Node(kind='text',name=editor.toPlainText(),text_html=editor.get_html())
    path=tmp_path/'note.erdraw'
    save_document(Document(nodes=[node]),path)
    restored=load_document(path).nodes[0]
    document=create_note_document(restored,600,QColor('#233844'))
    fmt=char_format(document,1)
    assert fmt.fontWeight()>=QFont.Bold and fmt.fontItalic() and fmt.fontUnderline()
    assert fmt.fontPointSize()==18
    assert fmt.foreground().color().name()=='#bc1234'
    assert restored.name==editor.toPlainText()
    assert colored_pixels(render(document),'#bc1234')>30


def test_strike_alignment_and_lists_survive_html(editor):
    editor.text_edit.setPlainText('Prima regola\nSeconda regola')
    editor.selectAll()
    editor.actions['strike'].trigger()
    editor.alignment_actions[Qt.AlignRight].trigger()
    editor.actions['bullets'].trigger()
    restored=create_note_document(Node(kind='text',name=editor.toPlainText(),text_html=editor.get_html()),600,QColor('black'))
    assert char_format(restored,1).fontStrikeOut()
    assert restored.firstBlock().blockFormat().alignment() & Qt.AlignRight
    assert restored.firstBlock().textList().format().style()==QTextListFormat.ListDisc
    editor.actions['numbers'].trigger()
    restored=create_note_document(Node(kind='text',name=editor.toPlainText(),text_html=editor.get_html()),600,QColor('black'))
    assert restored.firstBlock().textList().format().style()==QTextListFormat.ListDecimal


def test_formatting_applies_to_next_typed_characters(editor):
    select(editor,len(editor.toPlainText()),len(editor.toPlainText()))
    editor.actions['bold'].trigger()
    editor.text_edit.insertPlainText(' nuovo')
    assert char_format(editor.text_edit.document(),len(editor.toPlainText())-1).fontWeight()>=QFont.Bold


def test_repeated_spaces_tabs_and_empty_paragraph_roundtrip(editor):
    text='A  B\n\nC   D\tE'
    editor.text_edit.setPlainText(text)
    restored=create_note_document(Node(kind='text',name=text,text_html=editor.get_html()),600,QColor('black'))
    assert restored.toPlainText()==text
    canonical=editor.get_html()
    assert sanitize_note_html(canonical)==canonical
    document=Document(nodes=[Node(kind='text',name=text,text_html=canonical)])
    assert Document.from_dict(document.to_dict()).to_dict()==document.to_dict()


def test_rich_paste_is_local_text_without_embedded_resources(editor):
    editor.text_edit.clear()
    mime=QMimeData()
    mime.setHtml('<p><b>Da Word</b><img src="file:///tmp/private.png"></p>')
    mime.setText('Da Word')
    editor.text_edit.insertFromMimeData(mime)
    assert editor.toPlainText()=='Da Word'
    assert char_format(editor.text_edit.document(),1).fontWeight()>=QFont.Bold
    assert 'img' not in editor.get_html() and 'file:' not in editor.get_html()
    assert isinstance(editor.text_edit.document(),LocalTextDocument)
    assert editor.text_edit.document().loadResource(QTextDocument.ImageResource,QUrl('file:///tmp/private.png')) is None


@pytest.mark.parametrize('html',['','<p>Testo predefinito</p>'])
def test_default_ink_is_used_for_plain_and_rich_notes(app,html):
    note=SimpleNamespace(name='Testo predefinito',text_html=html)
    document=create_note_document(note,600,QColor('#e60000'))
    assert colored_pixels(render(document),'#e60000')>30


def test_cancel_formatted_note_never_mutates_original(app,monkeypatch):
    node=Node(kind='text',name='Prima',text_html='<p><b>Prima</b></p>')
    def cancel(dialog):
        editor=dialog.findChild(RichTextEditor)
        editor.text_edit.setHtml('<p><i>Modificata</i></p>')
        dialog.reject()
        return dialog.result()
    monkeypatch.setattr(QDialog,'exec',cancel)
    assert edit_node(None,node) is None
    assert node.name=='Prima' and node.text_html=='<p><b>Prima</b></p>'


def test_dialog_accepts_formatted_note_and_plain_search_text(app,monkeypatch):
    node=Node(kind='text',name='Prima')
    def accept(dialog):
        editor=dialog.findChild(RichTextEditor)
        editor.text_edit.setHtml('<p><b>Regole</b> del dominio</p><p><u>Verifica</u> i minimi.</p>')
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
        return dialog.result()
    monkeypatch.setattr(QDialog,'exec',accept)
    result=edit_node(None,node)
    assert result.name=='Regole del dominio\nVerifica i minimi.'
    assert result.text_html and 'font-weight:700' in result.text_html
    assert node.text_html=='' and node.name=='Prima'
