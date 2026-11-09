"""Esportazioni dallo stesso renderer dell'editor, senza ritagli delle etichette."""
from contextlib import contextmanager
from math import ceil
from pathlib import Path

from PySide6.QtCore import Qt, QRect, QRectF, QSize, QSizeF, QMarginsF
from PySide6.QtGui import QImage, QPainter, QPdfWriter, QPageSize, QPageLayout
from PySide6.QtSvg import QSvgGenerator


@contextmanager
def clean_scene(scene, *, png=False):
    scene.cancel_direct_connection()
    selected = scene.selectedItems()
    scene.clearSelection()
    original_dark = scene.dark
    scene.exporting = True
    scene.transparent_background = png
    if png:
        scene.dark = False
    try:
        scene.refresh_edges()
        yield scene.content_rect()
    finally:
        scene.transparent_background = False
        scene.exporting = False
        scene.dark = original_dark
        if png and original_dark:
            scene.refresh_edges()
        for item in selected:
            item.setSelected(True)


def _crop_on_white(image):
    """Conserva anche i pixel di antialiasing ai bordi delle figure."""
    alpha = image.convertToFormat(QImage.Format_Alpha8)
    if alpha.isNull():
        raise ValueError('Memoria insufficiente per ritagliare il PNG.')
    pixels = alpha.constBits()
    stride, width, height = alpha.bytesPerLine(), alpha.width(), alpha.height()
    left, top, right, bottom = width, height, 0, 0
    for y in range(height):
        row = bytes(pixels[y*stride:y*stride+width])
        last = len(row.rstrip(b'\0'))
        if last:
            left = min(left, last - len(row[:last].lstrip(b'\0')))
            right = max(right, last)
            top = min(top, y)
            bottom = y + 1
    if right <= left or bottom <= top:
        raise ValueError('Nessun contenuto visibile nel diagramma.')
    source = QRect(left, top, right-left, bottom-top)
    result = QImage(source.size(), QImage.Format_RGB32)
    if result.isNull():
        raise ValueError('Memoria insufficiente per ritagliare il PNG.')
    result.fill(Qt.white)
    painter = QPainter(result)
    try:
        painter.drawImage(result.rect(), image, source)
    finally:
        painter.end()
    return result


def export_diagram(scene, path, kind):
    """Renderizza PNG 2x, SVG vettoriale o PDF. Solleva OSError/ValueError."""
    path = str(Path(path))
    if not scene.document.nodes:
        raise ValueError('Il diagramma è vuoto.')
    with clean_scene(scene, png=kind == 'png') as bounds:
        if kind == 'png':
            width, height = ceil(bounds.width()*2), ceil(bounds.height()*2)
            if width * height > 64_000_000 or max(width,height)>24000:
                raise ValueError('Immagine troppo grande. Usa SVG o PDF per questo diagramma.')
            device = QImage(width,height,QImage.Format_ARGB32_Premultiplied)
            if device.isNull():
                raise ValueError('Memoria insufficiente per l’immagine. Usa SVG o PDF.')
            device.fill(Qt.transparent)
            target = QRectF(0,0,bounds.width()*2,bounds.height()*2)
        elif kind == 'svg':
            device = QSvgGenerator()
            device.setFileName(path)
            device.setSize(QSize(round(bounds.width()),round(bounds.height())))
            device.setViewBox(QRectF(0,0,bounds.width(),bounds.height()))
            device.setTitle(scene.document.title)
            device.setDescription('Diagramma Entità-Relazione generato con DrawER Studio')
            target = QRectF(0,0,bounds.width(),bounds.height())
        elif kind == 'pdf':
            device = QPdfWriter(path)
            device.setResolution(144)
            device.setTitle(scene.document.title)
            device.setCreator('DrawER Studio')
            # Un solo foglio della dimensione del diagramma, senza riduzioni arbitrarie.
            size = QSizeF(bounds.width()*25.4/96,bounds.height()*25.4/96)
            device.setPageSize(QPageSize(size,QPageSize.Millimeter))
            device.setPageMargins(QMarginsF(0,0,0,0),QPageLayout.Millimeter)
            target = QRectF(0,0,device.width(),device.height())
        else:
            raise ValueError('Formato di esportazione sconosciuto: '+kind)
        painter = QPainter()
        if not painter.begin(device):
            raise OSError('Impossibile scrivere il file di esportazione.')
        try:
            painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
            scene.render(painter,target,bounds)
        finally:
            painter.end()
        if kind == 'png' and not _crop_on_white(device).save(path,'PNG'):
            raise OSError('Impossibile salvare l’immagine PNG.')
    if not Path(path).is_file() or Path(path).stat().st_size == 0:
        raise OSError('Esportazione non riuscita: file vuoto.')
