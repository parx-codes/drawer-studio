"""Collegamenti ER editabili: porte, pieghe, cardinalità e freccia ISA."""
import copy
import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QColor,QPen,QPainterPath,QPainterPathStroker,QFont,
                          QFontMetricsF,QPolygonF)
from PySide6.QtWidgets import QGraphicsPathItem,QGraphicsItem

from .model import PORTS
from .geometry import nearest_port,adapt_manual,serialized
from .routing import route
from .controls import ConnectionHandle, EdgeLabel


class EdgeItem(QGraphicsPathItem):
    def __init__(self,link=None,child=None):
        super().__init__()
        self.link,self.child=link,child
        self.object_id=link.id if link else child.id
        self.labels,self.handles,self.points=[],[],[]
        self._labels_by_key = {}
        self._triangle=[]
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setToolTip('Clic per selezionare · cerchi: attacchi · quadrati: pieghe · doppio clic: proprietà')
        self.setZValue(0)

    @property
    def editor(self):
        return self.scene()

    @property
    def source_item(self):
        return self.editor.node_items.get(self.link.source if self.link else self.child.parent_id)

    @property
    def target_item(self):
        return self.editor.node_items.get(self.link.target if self.link else self.child.id)

    @property
    def source_port(self):
        return self.link.source_port if self.link else self.child.parent_port

    @property
    def target_port(self):
        return self.link.target_port if self.link else self.child.child_port

    @property
    def manual_points(self):
        return self.link.route_points if self.link else self.child.connection_points

    def set_port(self,end,side):
        owner=self.link if self.link else self.child
        field=('source_port' if end=='source' else 'target_port') if self.link else (
            'parent_port' if end=='source' else 'child_port')
        setattr(owner,field,side)

    def set_manual_points(self,points):
        if self.link:self.link.route_points=points
        else:self.child.connection_points=points

    def geometry_snapshot(self):
        return self.source_port,self.target_port,copy.deepcopy(self.manual_points)

    def restore_geometry(self,state):
        self.set_port('source',state[0]);self.set_port('target',state[1]);self.set_manual_points(state[2])

    def pin_current_ports(self):
        if self.points:
            for end,item,point,following in (('source',self.source_item,self.points[0],self.points[1]),
                                            ('target',self.target_item,self.points[-1],self.points[-2])):
                if item.node.kind in ('attribute','isa'):
                    # Una giunzione/circonferenza ha un solo punto geometrico:
                    # la normale va dedotta dal tratto, non da porte coincidenti.
                    delta=following-point
                    side=('right' if delta.x()>0 else 'left') if abs(delta.x())>abs(delta.y()) else (
                        'bottom' if delta.y()>0 else 'top')
                else:side=nearest_port(self._rect(item),point)
                self.set_port(end,side)

    def reset_geometry(self):
        self.set_port('source',None);self.set_port('target',None);self.set_manual_points([])
        self.update_path();self.editor.changed_by_user.emit()

    @staticmethod
    def _rect(item):
        rect=item.mapRectToScene(item.body_rect())
        if item.node.kind in ('isa','attribute'):
            return QRectF(rect.center(),rect.center())
        return rect

    def boundingRect(self):
        return super().boundingRect().adjusted(-9,-9,9,9)

    def shape(self):
        stroker=QPainterPathStroker();stroker.setWidth(12)
        shape=stroker.createStroke(self.path())
        if self._triangle:shape.addPolygon(QPolygonF(self._triangle))
        return shape

    def update_path(self):
        self.labels=[]
        src,tgt=self.source_item,self.target_item
        if src is None or tgt is None:return
        sr,tr=self._rect(src),self._rect(tgt)
        obstacles=[self._rect(item).adjusted(-8,-8,8,8) for item in self.editor.node_items.values()
                   if item not in (src,tgt) and item.node.kind in ('entity','relation','multivalue')]
        parallels=[link for link in self.editor.document.links if self.link and
                   {link.source,link.target}=={self.link.source,self.link.target}]
        lane=parallels.index(self.link) if self.link in parallels else 0
        automatic=route(sr,tr,obstacles,lane,
                        PORTS.index(self.source_port) if self.source_port else None,
                        PORTS.index(self.target_port) if self.target_port else None)
        if self.manual_points:
            start,end=automatic[0],automatic[-1]
            self.points=adapt_manual(self.manual_points,start,end,
                self.source_port or nearest_port(sr,start),self.target_port or nearest_port(tr,end))
            normalized=serialized(self.points)
            if normalized!=self.manual_points:self.set_manual_points(normalized)
        else:self.points=automatic
        self.prepareGeometryChange()
        path=QPainterPath(self.points[0])
        for point in self.points[1:]:path.lineTo(point)
        self.setPath(path)
        self.setPen(QPen(QColor('#8babb9' if self.editor.dark else '#7c919d'),1.5))
        self._triangle=[]
        if self.child and self.child.kind=='isa':
            tip,following=self.points[:2]
            delta=following-tip
            length=math.hypot(delta.x(),delta.y()) or 1
            normal=delta/length;perpendicular=QPointF(-normal.y(),normal.x())
            self._triangle=[tip,tip+normal*15+perpendicular*7,tip+normal*15-perpendicular*7]
            code=('t' if self.child.isa_total else 'p')+','+('d' if self.child.isa_disjoint else 's')
            self.add_label('isa','('+code+')',path.pointAtPercent(.55)+QPointF(8,-18))
        if self.link:
            inheritance=src.node.kind=='isa' or tgt.node.kind=='isa'
            for key,item,card,p,q in (('source',src,self.link.source_card,self.points[0],self.points[1]),
                                      ('target',tgt,self.link.target_card,self.points[-1],self.points[-2])):
                if item.node.kind=='entity' and not inheritance:
                    delta=q-p;length=math.hypot(delta.x(),delta.y()) or 1
                    point=p+delta*(32/length);text='('+card+')'
                    width=QFontMetricsF(QFont('Sans Serif',9)).horizontalAdvance(text)
                    offset=QPointF(-width/2,-22) if abs(delta.x())>abs(delta.y()) else QPointF(8,-8)
                    self.add_label(key,text,point+offset)
            if self.link.role:self.add_label('role',self.link.role,path.pointAtPercent(.5)+QPointF(7,7))
        for key in self._labels_by_key.keys() - {label.key for label in self.labels}:
            self.editor.removeItem(self._labels_by_key.pop(key))
        self._update_handles()

    def add_label(self,key,text,position):
        item = self._labels_by_key.get(key)
        if item is None:
            item = EdgeLabel(self, key)
            item.setFont(QFont('Sans Serif',9))
            self._labels_by_key[key] = item
            self.editor.addItem(item)
        item.setText(text)
        item.setBrush(QColor('#b8cecc' if self.editor.dark else '#45686b'))
        item.anchor = position
        item.update_position()
        self.labels.append(item)

    def _update_handles(self):
        specifications=[]
        if self.points:
            for end,item,point in (('source',self.source_item,self.points[0]),('target',self.target_item,self.points[-1])):
                if item.node.kind in ('entity','relation','multivalue'):
                    specifications.append((end,0,point))
            specifications += [('corner',i,point) for i,point in enumerate(self.points[1:-1],1)]
            if len(self.points)==2:
                specifications.append(('corner',1,(self.points[0]+self.points[1])/2))
        if self.isSelected() and self.scene():
            while len(self.handles)<len(specifications):
                handle=ConnectionHandle(self);self.editor.addItem(handle);self.handles.append(handle)
        for i,handle in enumerate(self.handles):
            if handle._dragging:continue
            visible=self.isSelected() and i<len(specifications) and not self.editor.exporting
            handle.setVisible(visible)
            if visible:
                handle.kind,handle.index,position=specifications[i]
                handle.setPos(position)
                handle.setToolTip('Trascina su uno dei quattro punti di attacco' if handle.kind!='corner'
                                  else 'Trascina la piega per spostare il tratto in orizzontale o verticale')

    def itemChange(self,change,value):
        result=super().itemChange(change,value)
        if change==QGraphicsItem.ItemSelectedHasChanged and self.scene() and not self.editor.loading:
            self._update_handles()
        return result

    def paint(self,painter,option,widget=None):
        ink=QColor('#0ca68e') if self.isSelected() else self.pen().color()
        painter.setPen(QPen(ink,2.5 if self.isSelected() else 1.5))
        painter.drawPath(self.path())
        if self._triangle:
            painter.setBrush(ink);painter.drawPolygon(QPolygonF(self._triangle))

    def mouseDoubleClickEvent(self,event):
        self.editor.edit_requested.emit(self.object_id)
        event.accept()
