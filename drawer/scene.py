"""Scena Qt: forme ER, collegamenti, selezione e transazioni di trascinamento."""
import math

from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QTimer, QRect, QEvent
from PySide6.QtGui import QColor, QPen, QBrush, QPainter, QPainterPath, QFont, QPolygonF, QFontMetricsF, QTransform
from PySide6.QtWidgets import QGraphicsScene, QGraphicsObject, QGraphicsPathItem, QGraphicsItem, QGraphicsSimpleTextItem, QGraphicsView, QMenu, QApplication, QRubberBand

from .routing import route
from .richtext import create_note_document
from .geometry import port_point, nearest_port, NORMALS, adapt_manual, serialized
from .model import PORTS
from .controls import PortArrow, ResizeHandle
from .connections import EdgeItem

GRID = 20
NAMES = {'entity': 'Entità', 'relation': 'Relazione', 'attribute': 'Attributo',
         'multivalue': 'Multivalore', 'isa': 'Generalizzazione ISA', 'text': 'Nota'}


class NodeItem(QGraphicsObject):
    def __init__(self, node):
        super().__init__()
        self.node = node
        self.object_id = node.id
        self._note_document = None
        self._note_document_key = None
        self._resizing = False
        self.resize_handles = []
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemSendsGeometryChanges)
        self.setPos(node.x, node.y)
        self.setZValue(2)
        self.setToolTip(f'{NAMES[node.kind]} · {node.name}\nDoppio clic per modificare' + ('\n' + node.notes if node.notes else ''))
        self.port_arrows = []
        if node.kind in ('entity','relation','multivalue','isa'):
            for side in PORTS:
                arrow = PortArrow(self,side)
                self.port_arrows.append(arrow)
        if node.kind in ('entity', 'relation', 'multivalue', 'text'):
            self.resize_handles = [ResizeHandle(self, left, top)
                                   for top in (True, False) for left in (True, False)]
        self.position_controls()

    @property
    def editor(self):
        return self.scene()

    def port_anchor(self, side):
        rect = self.body_rect()
        return rect.center() if self.node.kind == 'isa' else port_point(rect, side)

    def position_controls(self):
        for arrow in self.port_arrows:
            arrow.setPos(self.port_anchor(arrow.side) + NORMALS[arrow.side] * 15)
        rect = self.body_rect()
        for handle in self.resize_handles:
            handle.setPos(rect.left() if handle.left else rect.right(),
                          rect.top() if handle.top else rect.bottom())

    def port_hover_contains(self, position):
        local = self.mapFromScene(position)
        return any(QRectF(self.port_anchor(arrow.side), arrow.pos()).normalized()
                   .adjusted(-8, -8, 8, 8).contains(local) for arrow in self.port_arrows)

    def resize_to(self, rect):
        self.prepareGeometryChange()
        self.node.width, self.node.height = rect.width(), rect.height()
        self._resizing = True
        try:
            self.setPos(rect.topLeft())
        finally:
            self._resizing = False
        self.position_controls()
        self.update()

    def body_rect(self):
        n = self.node
        if n.kind == 'attribute':
            return QRectF(-7, -7, 14, 14)
        return QRectF(0, 0, n.width, n.height)

    def boundingRect(self):
        n = self.node
        if n.kind == 'attribute':
            font = QFont('Sans Serif', 10)
            font.setBold(n.is_pk)
            font.setUnderline(n.is_pk)
            width = QFontMetricsF(font).horizontalAdvance(n.name) + 38
            return QRectF(-11, -15, max(60, width), 32)
        if n.kind == 'isa':
            center = self.body_rect().center()
            return QRectF(center.x()-12,center.y()-12,24,24)
        return self.body_rect().adjusted(-5,-5,5,5)

    def shape(self):
        p = QPainterPath()
        r, kind = self.body_rect(), self.node.kind
        if kind == 'relation':
            p.addPolygon(QPolygonF([QPointF(r.center().x(), 0), QPointF(r.right(), r.center().y()), QPointF(r.center().x(), r.bottom()), QPointF(0, r.center().y())]))
            p.closeSubpath()
        elif kind in ('attribute', 'text'):
            p.addRect(self.boundingRect())
        elif kind == 'multivalue':
            p.addEllipse(r)
        elif kind == 'isa':
            p.addEllipse(r.center(),10,10)
        else:
            p.addRect(r)
        return p

    def paint(self, painter, option, widget=None):
        n, r = self.node, self.body_rect()
        dark = self.editor.dark
        ink = QColor('#dce8ee' if dark else '#243b49')
        accent = QColor('#59d9c0' if dark else '#087f73')
        fill = QColor('#20313e' if dark else '#ffffff')
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(accent if self.isSelected() else ink, 2.3 if self.isSelected() else 1.6)
        if n.derived:
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(fill)
        font = QFont('Sans Serif', 10)
        font.setBold(n.kind == 'entity' or n.is_pk)
        font.setUnderline(n.is_pk)
        painter.setFont(font)
        if n.kind == 'entity':
            painter.drawRect(r)
            painter.fillRect(QRectF(0, 0, 4, r.height()), accent)
        elif n.kind == 'relation':
            painter.drawPath(self.shape())
        elif n.kind == 'multivalue':
            painter.drawEllipse(r)
            painter.drawEllipse(r.adjusted(5, 5, -5, -5))
        elif n.kind == 'attribute':
            painter.setBrush(ink if n.is_pk else fill)
            painter.drawEllipse(r)
            painter.setPen(ink)
            painter.drawText(QRectF(14, -12, self.boundingRect().width()-24, 26), Qt.AlignLeft | Qt.AlignVCenter, n.name)
            return
        elif n.kind == 'isa':
            painter.setBrush(accent if self.isSelected() else ink)
            painter.drawEllipse(r.center(),3.5,3.5)
            if self.isSelected() and not self.editor.exporting:
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(accent,1,Qt.DashLine))
                painter.drawEllipse(r.center(),10,10)
            return
        elif n.kind == 'text':
            painter.setBrush(QColor('#2b3433' if dark else '#fff9e7'))
            painter.setPen(QPen(QColor('#b6a163'), 1, Qt.DashLine))
            painter.drawRoundedRect(r, 5, 5)
            area = r.adjusted(12,8,-12,-8)
            if area.isEmpty():
                return
            key = (n.name,n.text_html,area.width(),ink.name())
            if key != self._note_document_key:
                self._note_document = create_note_document(n,area.width(),ink)
                self._note_document_key = key
            document = self._note_document
            y = area.top() if n.text_html else max(area.top(),(r.height()-document.size().height())/2)
            painter.save()
            painter.setClipRect(area)
            painter.translate(area.left(),y)
            document.drawContents(painter)
            painter.restore()
            return
        painter.setPen(ink)
        painter.save()
        painter.setClipRect(r.adjusted(8,4,-8,-4))
        painter.drawText(r.adjusted(12, 6, -12, -6), Qt.AlignCenter | Qt.TextWrapAnywhere, n.name)
        painter.restore()

    def itemChange(self, change, value):
        if change not in (QGraphicsItem.ItemPositionChange, QGraphicsItem.ItemPositionHasChanged,
                          QGraphicsItem.ItemSelectedHasChanged):
            return value
        editor = self.scene()
        if editor is None or editor.loading:
            return value
        if change == QGraphicsItem.ItemPositionChange:
            if editor.snap and not editor.following_parent and not self._resizing:
                value = QPointF(round(value.x()/GRID)*GRID, round(value.y()/GRID)*GRID)
                if self.node.kind in ('entity','relation','multivalue','isa'):
                    center = value+self.body_rect().center()
                    others = [item for item in editor.node_items.values()
                              if item is not self and item.node.kind in ('entity','relation','multivalue')
                              and not item.isSelected()]
                    for axis in ('x','y'):
                        candidates = [getattr(item.mapToScene(item.body_rect().center()),axis)() for item in others]
                        if candidates:
                            nearest = min(candidates,key=lambda coordinate:abs(coordinate-getattr(center,axis)()))
                            if abs(nearest-getattr(center,axis)()) <= 10:
                                if axis=='x': value.setX(nearest-self.body_rect().center().x())
                                else: value.setY(nearest-self.body_rect().center().y())
            return value
        if change == QGraphicsItem.ItemPositionHasChanged:
            old = QPointF(self.node.x, self.node.y)
            self.node.x, self.node.y = self.pos().x(), self.pos().y()
            if self._resizing:
                return value
            delta = self.pos() - old
            # Un attributo resta solidale al proprietario, salvo selezione esplicita.
            for child in editor.node_items.values():
                if child.node.parent_id == self.node.id and not child.isSelected():
                    editor.following_parent += 1
                    try:
                        child.setPos(child.pos() + delta)
                    finally:
                        editor.following_parent -= 1
            editor.request_edges_refresh()
        if change == QGraphicsItem.ItemSelectedHasChanged:
            for handle in self.resize_handles:
                handle.setVisible(bool(value))
        return value

    def mouseDoubleClickEvent(self, event):
        self.editor.edit_requested.emit(self.object_id)
        event.accept()


class DiagramScene(QGraphicsScene):
    changed_by_user = Signal()
    edit_requested = Signal(str)
    create_requested = Signal(str, object, object)
    connect_requested = Signal(str, str)
    direct_connect_requested = Signal(str, str, str, str)
    delete_requested = Signal()
    hint = Signal(str)

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.node_items, self.edge_items = {}, []
        self.dark, self.snap, self.loading, self.exporting = False, True, False, False
        self.transparent_background = False
        self.hovered_port_node = None
        self.following_parent = 0
        self.mode, self.connect_source = 'select', None
        self.active_handle = None
        self._direct_source = None
        self._connection_preview = None
        self.edge_timer = QTimer(self)
        self.edge_timer.setSingleShot(True)
        self.edge_timer.timeout.connect(self.refresh_edges)
        self.setSceneRect(-10000, -10000, 22000, 22000)
        self.rebuild()

    def rebuild(self, selected=None):
        self.loading = True
        self.cancel_direct_connection()
        self.set_port_hover(None)
        self.active_handle = None
        self.clear()
        self.node_items, self.edge_items = {}, []
        for node in self.document.nodes:
            item = NodeItem(node)
            self.addItem(item)
            self.node_items[node.id] = item
        for link in self.document.links:
            edge = EdgeItem(link=link)
            self.addItem(edge)
            self.edge_items.append(edge)
        for node in self.document.nodes:
            if node.parent_id and node.parent_id in self.node_items:
                edge = EdgeItem(child=node)
                self.addItem(edge)
                self.edge_items.append(edge)
        self.refresh_edges()
        self.loading = False
        for id_ in selected or []:
            item = self.find_item(id_)
            if item:
                item.setSelected(True)

    def set_port_hover(self, item):
        if item is self.hovered_port_node:
            return
        if self.hovered_port_node:
            for arrow in self.hovered_port_node.port_arrows:
                arrow.hide()
        self.hovered_port_node = item
        if item:
            for arrow in item.port_arrows:
                arrow.show()

    def find_item(self, id_):
        return self.node_items.get(id_) or next((e for e in self.edge_items if e.object_id == id_), None)

    def refresh_edges(self):
        self.edge_timer.stop()
        for edge in self.edge_items:
            edge.update_path()

    def request_edges_refresh(self):
        # Un solo ricalcolo per evento, anche trascinando molti nodi e figli.
        if not self.edge_timer.isActive():
            self.edge_timer.start(0)

    def selected_ids(self):
        return list(dict.fromkeys(i.object_id for i in self.selectedItems() if getattr(i, 'object_id', None)))

    def content_rect(self):
        return self.itemsBoundingRect().adjusted(-50,-50,50,50) if self.document.nodes else QRectF(0,0,900,600)

    def set_mode(self, mode):
        self.cancel_direct_connection()
        self.mode, self.connect_source = mode, None
        self.hint.emit({'select':'Sinistro: seleziona · destro: naviga · Maiusc+sinistro: sposta le figure',
                        'connect':'Scegli il primo oggetto, poi il secondo. Esc per annullare.',
                        'attribute':'Clicca l’entità, la relazione o il multivalore proprietario dell’attributo.',
                        'multivalue':'Clicca l’entità proprietaria dell’attributo multivalore.',
                        'isa':'Clicca l’entità supertipo; poi collega ISA ai sottotipi.'}.get(mode, 'Clicca sul foglio per creare: '+NAMES.get(mode,mode)))

    def drawBackground(self, painter, rect):
        if self.transparent_background:
            return
        painter.fillRect(rect, QColor('#15222d' if self.dark else '#f7f9fa'))
        if self.exporting:
            return
        painter.setPen(QPen(QColor('#30434e' if self.dark else '#d9e1e5'), 1))
        step = GRID
        if self.views() and self.views()[0].transform().m11() < .45:
            step *= 4
        left, top = math.floor(rect.left()/step)*step, math.floor(rect.top()/step)*step
        points = QPolygonF([QPointF(x,y) for x in range(left, int(rect.right())+step, step) for y in range(top, int(rect.bottom())+step, step)])
        painter.drawPoints(points)

    def mousePressEvent(self, event):
        if event.button()==Qt.LeftButton and any(getattr(item,'interactive_handle',False)
                for item in self.items(event.scenePos())):
            super().mousePressEvent(event)
            return
        if event.button() == Qt.LeftButton and self.mode != 'select':
            clicked = self.itemAt(event.scenePos(), QTransform())
            while clicked and not isinstance(clicked,NodeItem):
                clicked = clicked.parentItem()
            if self.mode == 'connect':
                if clicked:
                    if self.connect_source is None:
                        self.connect_source = clicked.object_id
                        self.clearSelection()
                        clicked.setSelected(True)
                        self.hint.emit('Ora scegli il secondo oggetto.')
                    elif self.connect_source != clicked.object_id:
                        source, self.connect_source = self.connect_source, None
                        self.connect_requested.emit(source,clicked.object_id)
                event.accept()
                return
            self.create_requested.emit(self.mode, event.scenePos(), clicked.object_id if clicked else None)
            event.accept()
            return
        super().mousePressEvent(event)

    def node_at(self,position,exclude=None):
        for candidate in self.items(position):
            while candidate and not isinstance(candidate,NodeItem):candidate=candidate.parentItem()
            if candidate and candidate.object_id!=exclude:return candidate
        nearby=[item for item in self.node_items.values() if item.object_id!=exclude
                and item.node.kind in ('entity','relation','multivalue','isa')
                and item.mapRectToScene(item.body_rect()).adjusted(-22,-22,22,22).contains(position)]
        return min(nearby,key=lambda item:(item.sceneBoundingRect().center()-position).manhattanLength()) if nearby else None

    def begin_direct_connection(self,source,side):
        self.cancel_direct_connection()
        self._direct_source=(source,side)
        self._connection_preview=QGraphicsPathItem()
        self._connection_preview.setPen(QPen(QColor('#0a9a88'),2,Qt.DashLine))
        self._connection_preview.setAcceptedMouseButtons(Qt.NoButton)
        self._connection_preview.setZValue(10)
        self.addItem(self._connection_preview)
        self.hint.emit('Rilascia su un altro oggetto per collegarlo. Esc per annullare.')

    def preview_direct_connection(self,position):
        if not self._direct_source:return
        source,side=self._direct_source
        item=self.node_items[source]
        rect=item.mapRectToScene(item.body_rect())
        start=rect.center() if item.node.kind=='isa' else port_point(rect,side)
        path=QPainterPath(start)
        path.lineTo(start+NORMALS[side]*22)
        path.lineTo(QPointF(position.x(),(start+NORMALS[side]*22).y()))
        path.lineTo(position)
        self._connection_preview.setPath(path)

    def finish_direct_connection(self,position):
        if not self._direct_source:return
        source,side=self._direct_source
        target=self.node_at(position,exclude=source)
        target_id=target.object_id if target else None
        target_side=nearest_port(target.mapRectToScene(target.body_rect()),position) if target else None
        self.cancel_direct_connection()
        if target_id:
            QTimer.singleShot(0,lambda:self.direct_connect_requested.emit(source,target_id,side,target_side))
        else:self.hint.emit('Collegamento annullato: rilascia su un oggetto.')

    def cancel_direct_connection(self):
        if self._connection_preview is not None:
            self.removeItem(self._connection_preview)
        self._connection_preview=None
        self._direct_source=None

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton and self.mode == 'select':
            self.changed_by_user.emit()

    def contextMenuEvent(self, event):
        self.show_context_menu(event.scenePos(), event.screenPos())
        event.accept()

    def show_context_menu(self, position, screen_position):
        """Menu esplicito (Maiusc+destro o tasto Menu), distinto dalla selezione."""
        item = next((candidate for candidate in self.items(position)
                     if getattr(candidate, 'object_id', None)), None)
        if not getattr(item,'object_id',None):
            return
        object_id = item.object_id
        self.clearSelection()
        item.setSelected(True)
        menu = QMenu()
        edit = menu.addAction('Modifica…')
        attr = menu.addAction('Aggiungi attributo…') if isinstance(item,NodeItem) and item.node.kind in ('entity','relation','multivalue') else None
        reset = menu.addAction('Ripristina percorso automatico') if isinstance(item,EdgeItem) else None
        menu.addSeparator()
        delete = menu.addAction('Elimina')
        chosen = menu.exec(screen_position)
        if chosen == edit:
            self.edit_requested.emit(object_id)
        elif attr and chosen == attr:
            self.create_requested.emit('attribute', position, object_id)
        elif reset and chosen==reset:
            item.reset_geometry()
        elif chosen == delete:
            self.delete_requested.emit()


class DiagramView(QGraphicsView):
    zoom_changed = Signal(int)
    escape_pressed = Signal()

    def __init__(self, scene, parent=None):
        super().__init__(scene,parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        # Il sinistro seleziona, il destro sposta la vista.
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setFrameShape(QGraphicsView.NoFrame)
        self._panning, self._space = False, False
        self._pan_button = None
        self._selection_origin = None
        self._selection_dragging = False
        self._selection_additive = False
        self._selection_baseline = []
        self._left_item_drag = False
        self._rubber_band = QRubberBand(QRubberBand.Rectangle, self.viewport())
        self._rubber_band.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._rubber_band.setFocusPolicy(Qt.NoFocus)
        self.centerOn(350,250)

    def wheelEvent(self, event):
        self.zoom(1.15 if event.angleDelta().y() > 0 else 1/1.15)
        event.accept()

    def zoom(self, factor):
        target = self.transform().m11()*factor
        if .15 <= target <= 3.5:
            self.scale(factor,factor)
            self.zoom_changed.emit(round(target*100))

    def fit_diagram(self):
        self.fitInView(self.scene().content_rect(),Qt.KeepAspectRatio)
        if self.transform().m11()>1.3:
            self.resetTransform()
            self.centerOn(self.scene().content_rect().center())
        self.zoom_changed.emit(round(self.transform().m11()*100))

    def _selectable_at(self, position):
        # Le etichette degli archi non sono selezionabili: cercare anche sotto
        # di esse permette di raggiungere il nodo o il collegamento sottostante.
        return next((item for item in self.items(position)
                     if item.flags() & QGraphicsItem.ItemIsSelectable), None)

    def _normal_cursor(self):
        self.setCursor(Qt.OpenHandCursor if self._space else
                       Qt.ArrowCursor if self.scene().mode == 'select' else Qt.CrossCursor)

    def _cancel_editor_interaction(self):
        scene=self.scene()
        if scene is None:return
        if scene.active_handle:
            scene.active_handle.cancel()
            scene.active_handle=None
        scene.cancel_direct_connection()
        scene.set_port_hover(None)

    def _update_port_hover(self, position):
        scene = self.scene()
        item = next((candidate for candidate in self.items(position)
                     if isinstance(candidate, (NodeItem, PortArrow))), None)
        if isinstance(item, PortArrow):
            item = item.node_item
        if item is None and scene.hovered_port_node:
            previous = scene.hovered_port_node
            if previous.port_hover_contains(self.mapToScene(position)):
                item = previous
        scene.set_port_hover(item if item and item.port_arrows else None)

    def leaveEvent(self, event):
        scene = self.scene()
        if scene is not None and not scene._direct_source:
            scene.set_port_hover(None)
        super().leaveEvent(event)

    def _begin_pan(self, event):
        self._panning = True
        self._pan_button = event.button()
        self._pan_pos = event.position()
        self.setCursor(Qt.ClosedHandCursor)
        event.accept()

    def _apply_selection_rectangle(self, position):
        rectangle = QRect(self._selection_origin, position).normalized()
        self._rubber_band.setGeometry(rectangle)
        self._rubber_band.show()
        path = QPainterPath()
        path.addPolygon(self.mapToScene(rectangle))
        path.closeSubpath()
        selected = {item for item in self.scene().items(path, Qt.IntersectsItemShape)
                    if item.flags() & QGraphicsItem.ItemIsSelectable}
        if self._selection_additive:
            selected.update(item for identifier in self._selection_baseline
                            if (item := self.scene().find_item(identifier)) is not None)
        for item in self.scene().selectedItems():
            if item not in selected:
                item.setSelected(False)
        for item in selected:
            item.setSelected(True)

    def _reset_gesture(self, restore_selection=False):
        if restore_selection and self._selection_origin is not None:
            self.scene().clearSelection()
            for identifier in self._selection_baseline:
                item = self.scene().find_item(identifier)
                if item:
                    item.setSelected(True)
        self._selection_origin = None
        self._selection_dragging = False
        self._selection_baseline = []
        self._rubber_band.hide()
        self._panning = False
        self._pan_button = None
        self._normal_cursor()

    def mousePressEvent(self,event):
        button, modifiers = event.button(), event.modifiers()
        if button == Qt.RightButton and modifiers & Qt.ShiftModifier:
            point = event.position().toPoint()
            self.scene().show_context_menu(self.mapToScene(point), event.globalPosition().toPoint())
            event.accept()
            return
        if button in (Qt.RightButton, Qt.MiddleButton) or (self._space and button == Qt.LeftButton):
            if not self._panning and self._selection_origin is None and not self.scene().mouseGrabberItem():
                self._begin_pan(event)
            event.accept()
            return
        if self._panning:
            event.accept()
            return
        if button == Qt.LeftButton and self.scene().mode == 'select':
            point = event.position().toPoint()
            if any(getattr(item,'interactive_handle',False) for item in self.items(point)):
                super().mousePressEvent(event)
                return
            item = self._selectable_at(point)
            if modifiers & Qt.ShiftModifier and isinstance(item, NodeItem):
                self._left_item_drag = True
                super().mousePressEvent(event)
                return
            self._selection_origin = point
            self._selection_additive = bool(modifiers & Qt.ControlModifier)
            self._selection_baseline = self.scene().selected_ids()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if event.buttons() == Qt.NoButton:
            self._update_port_hover(event.position().toPoint())
        if self._panning:
            delta=event.position()-self._pan_pos
            self._pan_pos=event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-round(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value()-round(delta.y()))
            event.accept()
        elif self._selection_origin is not None:
            position = event.position().toPoint()
            if (position-self._selection_origin).manhattanLength() >= QApplication.startDragDistance():
                self._selection_dragging = True
            if self._selection_dragging:
                self._apply_selection_rectangle(position)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if self._panning and event.button() == self._pan_button:
            self._reset_gesture()
            self._update_port_hover(event.position().toPoint())
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._selection_origin is not None:
            if self._selection_dragging:
                self._apply_selection_rectangle(event.position().toPoint())
            else:
                item = self._selectable_at(event.position().toPoint())
                if self._selection_additive:
                    if item:
                        item.setSelected(not item.isSelected())
                else:
                    self.scene().clearSelection()
                    if item:
                        item.setSelected(True)
            self._reset_gesture()
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton:
            self._left_item_drag = False
            self._update_port_hover(event.position().toPoint())

    def mouseDoubleClickEvent(self,event):
        if event.button() == Qt.LeftButton and self.scene().mode == 'select':
            self._reset_gesture()
            item = self._selectable_at(event.position().toPoint())
            if item and getattr(item, 'object_id', None):
                self.scene().edit_requested.emit(item.object_id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self,event):
        # Il menu nativo sul destro renderebbe difficile la selezione. Il menu
        # resta disponibile con Maiusc+destro, Menu oppure Maiusc+F10.
        event.accept()

    def _keyboard_context_menu(self):
        selected = self.scene().selectedItems()
        position = (self.mapFromScene(selected[0].sceneBoundingRect().center())
                    if selected else self.viewport().rect().center())
        self.scene().show_context_menu(self.mapToScene(position), self.viewport().mapToGlobal(position))

    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Space and not event.isAutoRepeat():
            self._space=True
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
        elif event.key()==Qt.Key_Escape:
            self._cancel_editor_interaction()
            self._reset_gesture(restore_selection=True)
            self.escape_pressed.emit()
            event.accept()
        elif event.key() == Qt.Key_Menu or (event.key() == Qt.Key_F10 and event.modifiers() & Qt.ShiftModifier):
            self._keyboard_context_menu()
            event.accept()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self,event):
        if event.key()==Qt.Key_Space:
            self._space=False
            self._normal_cursor()
            event.accept()
        else:
            super().keyReleaseEvent(event)

    def focusOutEvent(self,event):
        self._cancel_editor_interaction()
        if self._left_item_drag:
            self.scene().changed_by_user.emit()
            self._left_item_drag = False
        self._space = False
        self._reset_gesture(restore_selection=True)
        super().focusOutEvent(event)

    def event(self,event):
        if event.type() == QEvent.WindowDeactivate and hasattr(self, '_rubber_band'):
            self._cancel_editor_interaction()
            if self._left_item_drag:
                self.scene().changed_by_user.emit()
                self._left_item_drag = False
            self._space = False
            self._reset_gesture(restore_selection=True)
        return super().event(event)
