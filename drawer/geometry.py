"""Geometria condivisa dalle maniglie e dal renderer dei collegamenti.

Le porte coincidono sempre con i punti cardinali reali delle forme. I percorsi
manuali sono polilinee ortogonali persistenti, comprese le coordinate degli
estremi usate per adattarli quando gli oggetti vengono spostati.
"""
from PySide6.QtCore import QPointF

from .model import PORTS
from .routing import ports, _simplify

NORMALS = {'top': QPointF(0,-1), 'right': QPointF(1,0),
           'bottom': QPointF(0,1), 'left': QPointF(-1,0)}


def port_point(rect, side):
    return ports(rect)[PORTS.index(side)][0]


def nearest_port(rect, point):
    return min(PORTS, key=lambda side: (port_point(rect,side)-point).manhattanLength())


def simplify(points):
    return [QPointF(x,y) for x,y in _simplify([(p.x(),p.y()) for p in points])]


def serialized(points):
    return [[point.x(),point.y()] for point in simplify(points)]


def orthogonalize(points):
    result = [points[0]]
    for point in points[1:]:
        previous = result[-1]
        if abs(previous.x()-point.x()) > .01 and abs(previous.y()-point.y()) > .01:
            result.append(QPointF(point.x(),previous.y()))
        result.append(point)
    return simplify(result)


def adapt_manual(points, start, end, start_side, end_side):
    old = [QPointF(*point) for point in points]
    da, db = start-old[0], end-old[-1]
    if da.manhattanLength() < .01 and db.manhattanLength() < .01:
        return old
    if (da-db).manhattanLength() < .01:
        return [point+da for point in old]
    # Aggiornare le pieghe terminali esistenti: aggiungere uno stelo ad ogni
    # fotogramma farebbe crescere il file durante un normale trascinamento.
    if len(old)<4:
        return orthogonalize([start,start+NORMALS[start_side]*22,
                              end+NORMALS[end_side]*22,end])
    old[0],old[-1]=start,end
    for source,index,neighbor,point,side in ((True,1,2,start,start_side),
                                            (False,-2,-3,end,end_side)):
        normal=NORMALS[side]
        if normal.x():
            old[index].setY(point.y())
            distance=(old[index].x()-point.x())*normal.x()
            if distance<22:
                old[index].setX(point.x()+normal.x()*22)
                old[neighbor].setX(old[index].x())
        else:
            old[index].setX(point.x())
            distance=(old[index].y()-point.y())*normal.y()
            if distance<22:
                old[index].setY(point.y()+normal.y()*22)
                old[neighbor].setY(old[index].y())
    return simplify(old)


def shift_corner(points, index, position, *, segment=None):
    """Sposta il tratto adiacente alla piega lungo l'asse del trascinamento.

    Gli estremi restano sul bordo: quando si muove un tratto terminale si
    introduce una coppia di pieghe, senza spostare la porta sulla figura.
    """
    initial = [QPointF(point) for point in points]
    delta = position-initial[index]
    horizontal_drag = abs(delta.x()) > abs(delta.y())
    def horizontal(a,b):
        return abs(a.y()-b.y()) < .01
    adjacent = [j for j in (index-1,index) if 0 <= j < len(initial)-1]
    if segment is None:
        segment = next((j for j in adjacent if horizontal(initial[j],initial[j+1]) != horizontal_drag), adjacent[0])
    is_horizontal = horizontal(initial[segment],initial[segment+1])
    amount = delta.y() if is_horizontal else delta.x()
    move = QPointF(0,amount) if is_horizontal else QPointF(amount,0)
    a,b = initial[segment],initial[segment+1]
    moved_a,moved_b = a+move,b+move
    result = initial[:segment]
    if segment == 0:
        direction = b-a
        length = direction.manhattanLength() or 1
        stub = a+direction*(min(22,length/3)/length)
        result += [a,stub,stub+move,moved_b]
    else:
        result += [moved_a,moved_b]
    if segment == len(initial)-2:
        direction = a-b
        length = direction.manhattanLength() or 1
        stub = b+direction*(min(22,length/3)/length)
        result = result[:-1]+[stub+move,stub,b]
    else:
        result += initial[segment+2:]
    return simplify(result)
