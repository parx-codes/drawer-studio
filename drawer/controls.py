"""Controlli del foglio: porte di collegamento e maniglie dei percorsi."""
import math
from weakref import ref

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPen, QPolygonF
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
        elif self.kind == 'segment':
            painter.drawRoundedRect(QRectF(-5,-3,10,6), 2, 2)
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
        edge = self.edge
        delta = event.scenePos() - self._origin
        if delta.manhattanLength() < .5:
            edge.restore_geometry(self._before)
        elif self._kind == 'source' and edge.attribute_connection:
            edge.set_attribute_anchor(event.scenePos())
        elif self._kind in ('source','target'):
            item = edge.source_item if self._kind == 'source' else edge.target_item
            side = nearest_port(item.mapRectToScene(item.body_rect()), event.scenePos())
            edge.restore_geometry(self._before)
            initial = self._before[0 if self._kind == 'source' else 1]
            start = self._points[0 if self._kind == 'source' else -1]
            if side != (initial or nearest_port(item.mapRectToScene(item.body_rect()), start)):
                edge.set_port(self._kind, side)
                edge.set_manual_points([])
        else:
            segment = self._index if self._kind == 'segment' else None
            points = shift_corner(self._points, self._index, self._points[self._index]+delta,
                                  segment=segment)
            if len(points) > 256:
                return
            edge.restore_geometry(self._before)
            if points != self._points:
                edge.points = self._points
                edge.pin_current_ports()
                edge.set_manual_points(serialized(points))
        edge.update_path()
        if self._kind in ('source','target'):
            self.setPos(edge.points[0 if self._kind == 'source' else -1])
        else:
            self.setPos(event.scenePos())
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


class AttributeName(QGraphicsSimpleTextItem):
    """Nome trascinabile, indipendente dalla posizione del pallino."""
    interactive_handle = True

    def __init__(self, node_item):
        super().__init__(node_item.node.name, node_item)
        font = QFont('Sans Serif', 10)
        font.setBold(node_item.node.is_pk)
        font.setUnderline(node_item.node.is_pk)
        self.setFont(font)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setCursor(Qt.SizeAllCursor)
        self.setToolTip("Trascina il nome attorno all’attributo")
        self._dragging = False
        self.update_position()

    def update_position(self):
        angle = self.parentItem().node.attribute_name_angle or 0
        direction = QPointF(math.cos(angle), math.sin(angle))
        bounds = self.boundingRect()
        # Proietta l'ingombro del nome sulla direzione radiale.
        extent = (abs(direction.x()) * bounds.width() + abs(direction.y()) * bounds.height()) / 2
        self.setPos(direction * (14 + extent) - bounds.center())

    def paint(self, painter, option, widget=None):
        painter.setPen(QColor('#dce8ee' if self.scene().dark else '#243b49'))
        painter.setFont(self.font())
        painter.drawText(QPointF(0, QFontMetricsF(self.font()).ascent()), self.text())

    def mousePressEvent(self, event):
        scene = self.scene()
        node_item = self.parentItem()
        if not node_item.isSelected():
            scene.clearSelection()
            node_item.setSelected(True)
        self._dragging = True
        self._previous_angle = node_item.node.attribute_name_angle
        self._origin = event.scenePos()
        scene.active_handle = self
        event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging:
            node_item = self.parentItem()
            if (event.scenePos() - self._origin).manhattanLength() < 1:
                node_item.node.attribute_name_angle = self._previous_angle
            else:
                direction = node_item.mapFromScene(event.scenePos())
                if not direction.isNull():
                    node_item.node.attribute_name_angle = math.atan2(direction.y(), direction.x())
            self.update_position()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self.scene().active_handle = None
            self.scene().changed_by_user.emit()
        event.accept()

    def cancel(self):
        self._dragging = False
        self.parentItem().node.attribute_name_angle = self._previous_angle
        self.update_position()


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
