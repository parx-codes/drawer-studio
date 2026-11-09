"""Controlli del foglio: porte di collegamento e maniglie dei percorsi."""
from weakref import ref

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsObject, QGraphicsSimpleTextItem

from .geometry import NORMALS, nearest_port, shift_corner, serialized


class PortArrow(QGraphicsObject):
    interactive_handle = True

    def __init__(self, node_item, side):
        super().__init__(node_item)
        self.side = side
        self.setZValue(7)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CrossCursor)
        self.setToolTip('Trascina verso un altro oggetto per collegarlo')
        self.setOpacity(.25)
        self.hide()

    @property
    def node_item(self):
        return self.parentItem()

    def boundingRect(self):
        return QRectF(-8,-8,16,16)

    def paint(self,painter,option,widget=None):
        if self.node_item.editor.exporting:
            return
        normal = NORMALS[self.side]
        perpendicular = QPointF(-normal.y(),normal.x())
        painter.setPen(QPen(QColor('#0a9a88'),1.2))
        painter.setBrush(QColor('#0a9a88'))
        painter.drawPolygon(QPolygonF([normal*6,-normal*4+perpendicular*4,-normal*4-perpendicular*4]))

    def hoverEnterEvent(self,event):
        self.setOpacity(.9)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self,event):
        self.setOpacity(.25)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self,event):
        self.node_item.editor.begin_direct_connection(self.node_item.object_id,self.side)
        event.accept()

    def mouseMoveEvent(self,event):
        self.node_item.editor.preview_direct_connection(event.scenePos())
        event.accept()

    def mouseReleaseEvent(self,event):
        editor = self.node_item.editor
        position = event.scenePos()
        event.accept()
        editor.finish_direct_connection(position)


class ConnectionHandle(QGraphicsObject):
    """Maniglia indipendente dal livello dell'arco, sempre sopra le figure."""
    interactive_handle = True

    def __init__(self,edge):
        super().__init__()
        self._edge = ref(edge)
        self.kind, self.index = 'corner', 1
        self.setZValue(9)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setCursor(Qt.SizeAllCursor)
        self._dragging = False

    @property
    def edge(self):
        return self._edge()

    def boundingRect(self):
        return QRectF(-7,-7,14,14)

    def paint(self,painter,option,widget=None):
        if self.edge.editor.exporting:
            return
        painter.setPen(QPen(QColor('#087f73'),1.5))
        painter.setBrush(QColor('#ffffff'))
        if self.kind in ('source','target'):
            painter.drawEllipse(QRectF(-5,-5,10,10))
        else:
            painter.drawRect(QRectF(-4,-4,8,8))

    def mousePressEvent(self,event):
        self._dragging = True
        self._kind, self._index = self.kind,self.index
        self._origin = event.scenePos()
        self._points = [QPointF(p) for p in self.edge.points]
        self._before = self.edge.geometry_snapshot()
        self.edge.editor.active_handle = self
        event.accept()

    def mouseMoveEvent(self,event):
        if not self._dragging:
            return
        if self._kind in ('source','target'):
            item = self.edge.source_item if self._kind=='source' else self.edge.target_item
            side = nearest_port(item.mapRectToScene(item.body_rect()),event.scenePos())
            previous = self.edge.source_port if self._kind=='source' else self.edge.target_port
            if side != previous:
                self.edge.set_port(self._kind,side)
                self.edge.set_manual_points([])
        else:
            points = shift_corner(self._points,self._index,
                                  self._points[self._index]+event.scenePos()-self._origin)
            if len(points) > 256:
                return
            self.edge.pin_current_ports()
            self.edge.set_manual_points(serialized(points))
        self.edge.update_path()
        self.setPos(self.edge.points[0] if self._kind=='source' else self.edge.points[-1]
                    if self._kind=='target' else event.scenePos())
        event.accept()

    def mouseReleaseEvent(self,event):
        self._dragging = False
        self.edge.editor.active_handle = None
        self.edge.update_path()
        self.edge.editor.changed_by_user.emit()
        event.accept()

    def cancel(self):
        self._dragging = False
        self.edge.restore_geometry(self._before)
        self.edge.update_path()


class ResizeHandle(QGraphicsObject):
    interactive_handle = True

    def __init__(self, node_item, left, top):
        super().__init__(node_item)
        self.left, self.top = left, top
        self._dragging = False
        self.setZValue(8)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setCursor(Qt.SizeFDiagCursor if left == top else Qt.SizeBDiagCursor)
        self.setToolTip("Trascina per ridimensionare")
        self.hide()

    @property
    def node_item(self):
        return self.parentItem()

    def boundingRect(self):
        return QRectF(-6, -6, 12, 12)

    def paint(self, painter, option, widget=None):
        if self.node_item.editor.exporting:
            return
        painter.setPen(QPen(QColor('#087f73'), 1.5))
        painter.setBrush(QColor('#ffffff'))
        painter.drawRect(QRectF(-4, -4, 8, 8))

    def mousePressEvent(self, event):
        self._dragging = True
        self._origin = event.scenePos()
        item = self.node_item
        self._rect = item.mapRectToScene(item.body_rect())
        self._edges = [(edge, edge.geometry_snapshot()) for edge in item.editor.edge_items
                       if item in (edge.source_item, edge.target_item) and edge.manual_points]
        item.editor.active_handle = self
        event.accept()

    def _resize(self, rect):
        for edge, geometry in self._edges:
            edge.restore_geometry(geometry)
        self.node_item.resize_to(rect)
        self.node_item.editor.refresh_edges()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        delta = event.scenePos() - self._origin
        width = min(4000, max(20, self._rect.width() + (-delta.x() if self.left else delta.x())))
        height = min(4000, max(20, self._rect.height() + (-delta.y() if self.top else delta.y())))
        x = self._rect.right() - width if self.left else self._rect.left()
        y = self._rect.bottom() - height if self.top else self._rect.top()
        self._resize(QRectF(x, y, width, height))
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self._edges = ()
            self.node_item.editor.active_handle = None
            self.node_item.editor.changed_by_user.emit()
        event.accept()

    def cancel(self):
        self._dragging = False
        self._resize(self._rect)
        self._edges = ()


class EdgeLabel(QGraphicsSimpleTextItem):
    interactive_handle = True

    def __init__(self, edge, key):
        super().__init__()
        self._edge, self.key = ref(edge), key
        self.anchor = QPointF()
        self._dragging = False
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setCursor(Qt.SizeAllCursor)
        self.setToolTip("Trascina per spostare l’etichetta")
        self.setZValue(3)

    @property
    def edge(self):
        return self._edge()

    @property
    def offsets(self):
        owner = self.edge.link if self.edge.link else self.edge.child
        return owner.label_offsets

    def update_position(self):
        self.setPos(self.anchor + QPointF(*self.offsets.get(self.key, (0, 0))))

    def mousePressEvent(self, event):
        self._dragging = True
        self._origin = event.scenePos()
        self._before = self.offsets.get(self.key)
        self.edge.editor.active_handle = self
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        offset = QPointF(*(self._before or (0, 0))) + event.scenePos() - self._origin
        self.offsets[self.key] = [max(-1_000_000, min(1_000_000, coordinate))
                                  for coordinate in (offset.x(), offset.y())]
        self.update_position()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self.edge.editor.active_handle = None
            self.edge.editor.changed_by_user.emit()
        event.accept()

    def cancel(self):
        self._dragging = False
        if self._before is None:
            self.offsets.pop(self.key, None)
        else:
            self.offsets[self.key] = self._before
        self.update_position()
