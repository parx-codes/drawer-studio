"""Formattazione delle note attraverso scena, progetto, cronologia ed export."""
import os

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from drawer.exports import export_diagram
from drawer.history import History
from drawer.model import Document, Node
from drawer.scene import DiagramScene
from drawer.storage import load_document, save_document
from drawer.window import MainWindow


@pytest.fixture(scope='module')
def app():
    instance=QApplication.instance() or QApplication([])
    yield instance
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


def note(html=None, **kwargs):
    return Node(kind='text',name='DrawER — nota',width=320,height=120,
                text_html=html or '<p><span style="color:#d01863;font-size:24pt;font-weight:700;font-style:italic;text-decoration:underline">DrawER — nota</span></p>',
                **kwargs)


def image_from_export(path, kind):
    if kind=='png':
        return QImage(str(path))
    if kind=='svg':
        renderer=QSvgRenderer(str(path))
        assert renderer.isValid()
        image=QImage(renderer.defaultSize(),QImage.Format_ARGB32)
        image.fill(Qt.white)
        painter=QPainter(image)
        renderer.render(painter)
        painter.end()
        return image
    pdf=QPdfDocument()
    assert pdf.load(str(path))==QPdfDocument.Error.None_
    assert pdf.pageCount()==1
    size=pdf.pagePointSize(0)
    image=pdf.render(0,QSize(1000,round(1000*size.height()/size.width())))
    pdf.close()
    return image


def is_note_color(color):
    return color.red()>140 and color.red()>color.green()*1.5 and color.blue()>color.green()*1.5


@pytest.mark.parametrize('kind',['png','svg','pdf'])
def test_formatted_note_exports_have_real_colored_text(app,tmp_path,kind):
    scene=DiagramScene(Document(nodes=[note()]))
    path=tmp_path/('nota.'+kind)
    export_diagram(scene,path,kind)
    image=image_from_export(path,kind)
    assert not image.isNull()
    colored=sum(is_note_color(image.pixelColor(x,y))
                for y in range(0,image.height(),2)
                for x in range(0,image.width(),2))
    assert colored>40
    if kind=='svg':
        source=path.read_text(encoding='utf-8')
        assert 'font-weight="700"' in source
        assert 'font-style="italic"' in source
        assert '#d01863' in source.lower()


@pytest.mark.parametrize('style',['font-weight:700','font-style:italic','text-decoration:underline'])
def test_each_primary_text_style_changes_scene_rendering(app,tmp_path,style):
    images=[]
    for index,extra in enumerate(('',style)):
        html=f'<p><span style="font-size:24pt;color:#d01863;{extra}">DrawER</span></p>'
        scene=DiagramScene(Document(nodes=[note(html)]))
        path=tmp_path/f'{index}.png'
        export_diagram(scene,path,'png')
        images.append(QImage(str(path)))
    assert images[0].size()==images[1].size()
    # An accepted style must alter the rendered glyphs/decoration, not merely
    # survive as unused HTML in the saved JSON.
    assert images[0]!=images[1]


def test_note_formatting_survives_save_copy_and_history(app,tmp_path):
    original=note()
    path=tmp_path/'note.erdraw'
    save_document(Document(nodes=[original]),path)
    document=load_document(path)
    html=document.nodes[0].text_html
    assert 'font-weight:700' in html and 'text-decoration:underline' in html
    window=MainWindow(document,recovery=False)
    try:
        window.scene.node_items[original.id].setSelected(True)
        window.copy_selection()
        window.paste_selection()
        assert len(window.document.nodes)==2
        assert all(n.text_html==html for n in window.document.nodes)
        assert window.document.nodes[0].id!=window.document.nodes[1].id
        window.undo()
        assert len(window.document.nodes)==1
        assert window.document.nodes[0].text_html==html
        window.redo()
        assert len(window.document.nodes)==2
        assert all(n.text_html==html for n in window.document.nodes)
    finally:
        window.saved_signature=History.signature(window.document)
        window.close()
        window.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


def test_old_plain_note_uses_readable_ink_in_dark_theme(app,tmp_path):
    original=Node(kind='text',name='Nota precedente',width=320,height=100)
    scene=DiagramScene(Document(nodes=[original]))
    scene.dark=True
    path=tmp_path/'legacy-dark.png'
    export_diagram(scene,path,'png')
    image=QImage(str(path))
    bright=sum(image.pixelColor(x,y).red()>180
               and image.pixelColor(x,y).green()>190
               and image.pixelColor(x,y).blue()>200
               for y in range(0,image.height(),2)
               for x in range(0,image.width(),2))
    assert bright>20


def test_oversized_note_text_stays_inside_its_text_area(app,tmp_path):
    original=note('<p><span style="font-size:28pt;color:#d01863">'+('WRAPPING '*30)+'</span></p>')
    original.width,original.height=120,60
    scene=DiagramScene(Document(nodes=[original]))
    path=tmp_path/'clipped.png'
    export_diagram(scene,path,'png')
    image=QImage(str(path))
    area=QRectF(original.x+12,original.y+8,original.width-24,original.height-16).adjusted(-1,-1,1,1)
    origin_x = original.x + original.width/2 - image.width()/4
    origin_y = original.y + original.height/2 - image.height()/4
    colored=0
    for y in range(image.height()):
        for x in range(image.width()):
            if is_note_color(image.pixelColor(x,y)):
                colored+=1
                assert area.contains(origin_x+x/2,origin_y+y/2)
    assert colored>30
