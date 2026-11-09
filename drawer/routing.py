"""Instradamento ortogonale euristico, con lavoro lineare negli ostacoli.

Il corridoio locale limita gli ostacoli rilevanti; i candidati sono in numero
costante. Si provano prima L/Z, poi poche deviazioni attorno ai veri blocchi.
Non è un risolutore globale: in spazi congestionati restituisce il percorso
con il minor numero di intersezioni tra quelli esaminati.
"""
from PySide6.QtCore import QPointF, QRectF

_STEM = 22
_GAP = 14
_CORRIDOR = 80
_EPS = .01


def ports(rect):
    """Porte pubbliche in ordine alto, destra, basso, sinistra."""
    return [(QPointF(rect.center().x(), rect.top()), QPointF(0, -1)),
            (QPointF(rect.right(), rect.center().y()), QPointF(1, 0)),
            (QPointF(rect.center().x(), rect.bottom()), QPointF(0, 1)),
            (QPointF(rect.left(), rect.center().y()), QPointF(-1, 0))]


def intersects(a, b, rect):
    """Intersezione di un segmento ortogonale con l'interno del rettangolo."""
    return _crosses((a.x(), a.y()), (b.x(), b.y()),
                    (rect.left(), rect.top(), rect.right(), rect.bottom()))


def _crosses(a, b, rect):
    left, top, right, bottom = rect
    if abs(a[0] - b[0]) < _EPS:
        return left < a[0] < right and max(a[1], b[1]) > top and min(a[1], b[1]) < bottom
    return top < a[1] < bottom and max(a[0], b[0]) > left and min(a[0], b[0]) < right


def _rect(rect):
    return rect.left(), rect.top(), rect.right(), rect.bottom()


def _ports(rect):
    left, top, right, bottom = rect
    cx, cy = (left + right)/2, (top + bottom)/2
    return ((cx, top, 0, -1), (right, cy, 1, 0),
            (cx, bottom, 0, 1), (left, cy, -1, 0))


def _simplify(points):
    result = []
    for point in points:
        if result and abs(point[0]-result[-1][0]) + abs(point[1]-result[-1][1]) < _EPS:
            continue
        while len(result) > 1:
            a, b = result[-2:]
            vertical = abs(a[0]-b[0]) < _EPS and abs(b[0]-point[0]) < _EPS
            horizontal = abs(a[1]-b[1]) < _EPS and abs(b[1]-point[1]) < _EPS
            forward = (b[0]-a[0])*(point[0]-b[0]) + (b[1]-a[1])*(point[1]-b[1]) >= 0
            if not ((vertical or horizontal) and forward):
                break
            result.pop()
        result.append(point)
    return result


def _score(points, rects):
    length, hits, blockers = 0, 0, set()
    for a, b in zip(points, points[1:]):
        length += abs(a[0]-b[0]) + abs(a[1]-b[1])
        for index, rect in enumerate(rects):
            if _crosses(a, b, rect):
                hits += 1
                blockers.add(index)
    return hits*100000 + length + 16*max(0, len(points)-2), blockers


def _solve(source, target, nearby, forced_pair=None, source_port=None, target_port=None):
    starts, ends = _ports(source), _ports(target)
    # Includere gli interni dei due estremi impedisce percorsi che tornino
    # attraverso un'entità dopo essere usciti dalla sua porta.
    rects = [(source[0]+1, source[1]+1, source[2]-1, source[3]-1),
             (target[0]+1, target[1]+1, target[2]-1, target[3]-1)] + nearby
    pairs = [forced_pair] if forced_pair else [(i, j) for i in range(4) for j in range(4)
        if (source_port is None or source_port == i) and (target_port is None or target_port == j)]
    pairs.sort(key=lambda pair: abs(starts[pair[0]][0]-ends[pair[1]][0]) +
                                abs(starts[pair[0]][1]-ends[pair[1]][1]))
    best, best_score, best_pair = None, float('inf'), pairs[0]
    pair_results = []
    for si, ti in pairs:
        a, b = starts[si][:2], ends[ti][:2]
        # Percorso diretto: nessuna costruzione dei candidati se è già ottimo.
        dx, dy = b[0]-a[0], b[1]-a[1]
        source_normal, target_normal = starts[si][2:], ends[ti][2:]
        # Essere allineati non basta: una porta superiore deve uscire in
        # verticale, mai scorrere tangente lungo il bordo della figura.
        outward = (dx*source_normal[0] + dy*source_normal[1] > _EPS and
                   -dx*target_normal[0] - dy*target_normal[1] > _EPS)
        collinear = (abs(dx*source_normal[1] - dy*source_normal[0]) < _EPS and
                     abs(dx*target_normal[1] - dy*target_normal[0]) < _EPS)
        if outward and collinear:
            _, direct_blocks = _score([a, b], rects)
            if not direct_blocks:
                return [a, b], (si, ti)
        aa = (a[0]+starts[si][2]*_STEM, a[1]+starts[si][3]*_STEM)
        bb = (b[0]+ends[ti][2]*_STEM, b[1]+ends[ti][3]*_STEM)
        mx, my = (aa[0]+bb[0])/2, (aa[1]+bb[1])/2
        candidates = ([a, aa, (bb[0], aa[1]), bb, b],
                      [a, aa, (aa[0], bb[1]), bb, b],
                      [a, aa, (mx, aa[1]), (mx, bb[1]), bb, b],
                      [a, aa, (aa[0], my), (bb[0], my), bb, b])
        pair_best = (float('inf'), set())
        for raw in candidates:
            path = _simplify(raw)
            score, blocks = _score(path, rects)
            if score < pair_best[0]:
                pair_best = score, blocks
            if score < best_score:
                best, best_score, best_pair = path, score, (si, ti)
        pair_results.append((pair_best[0], si, ti, pair_best[1], a, aa, bb, b))
    if best_score < 100000:
        return best, best_pair
    # Solo se tutti i candidati semplici sono bloccati, fino a sei coppie di
    # porte e quattro blocchi reali producono un massimo di 96 deviazioni.
    for _, si, ti, blocks, a, aa, bb, b in sorted(pair_results, key=lambda item: item[0])[:6]:
        for index in sorted(blocks)[:4]:
            left, top, right, bottom = rects[index]
            candidates = []
            for x in (left-_GAP, right+_GAP):
                candidates.append([a, aa, (x, aa[1]), (x, bb[1]), bb, b])
            for y in (top-_GAP, bottom+_GAP):
                candidates.append([a, aa, (aa[0], y), (bb[0], y), bb, b])
            for raw in candidates:
                path = _simplify(raw)
                score, _ = _score(path, rects)
                if score < best_score:
                    best, best_score, best_pair = path, score, (si, ti)
    return best, best_pair


def route(source: QRectF, target: QRectF, obstacles: list[QRectF], lane=0, source_port=None, target_port=None):
    """Restituisce punti ortogonali, mantenendo porte distinte per le corsie.

    Gli ostacoli lontani dal riquadro degli estremi (+80 unità) non entrano
    nella ricerca. Anche in casi congestionati il numero dei candidati resta
    limitato, quindi il costo è O(n), senza ricerche su una griglia illimitata.
    """
    src, tgt = _rect(source), _rect(target)
    corridor = (min(src[0], tgt[0])-_CORRIDOR, min(src[1], tgt[1])-_CORRIDOR,
                max(src[2], tgt[2])+_CORRIDOR, max(src[3], tgt[3])+_CORRIDOR)
    nearby = []
    for obstacle in obstacles:
        rect = _rect(obstacle)
        if rect[2] >= corridor[0] and rect[0] <= corridor[2] and rect[3] >= corridor[1] and rect[1] <= corridor[3]:
            nearby.append(rect)
    path, pair = _solve(src, tgt, nearby, source_port=source_port, target_port=target_port)
    if lane:
        # Derivare dalla soluzione base garantisce che lane=1 usi porte
        # diverse anche quando la base ha già scelto un percorso alternativo.
        forced = (source_port if source_port is not None else (pair[0]+lane)%4,
                  target_port if target_port is not None else (pair[1]+lane)%4)
        path, _ = _solve(src, tgt, nearby, forced)
    return [QPointF(x, y) for x, y in path]
