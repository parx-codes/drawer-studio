"""Domain objects for a conceptual ER diagram, independent from the GUI.

Coordinates are scene coordinates; IDs (rather than list offsets) identify every
reference.  Incomplete conceptual diagrams can be saved: semantic correctness is
checked separately by :mod:`drawer.validation` and the SQL exporter.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import math
import re
from typing import Any
from uuid import uuid4

from .note_html import MAX_NOTE_HTML, MAX_NOTE_TEXT, sanitize_note_html

SCHEMA_VERSION = 2
KINDS = frozenset({"entity", "relation", "attribute", "multivalue", "isa", "text"})
CARDINALITIES = ("0,1", "1,1", "0,N", "1,N")
PORTS = ("top", "right", "bottom", "left")
DEFAULT_TITLE = "Nuovo diagramma"
MAX_NODES = 10_000
MAX_LINKS = 30_000


def new_id() -> str:
    return uuid4().hex


@dataclass
class Node:
    kind: str = "entity"
    name: str = "Entità"
    x: float = 0
    y: float = 0
    width: float = 160
    height: float = 80
    id: str = field(default_factory=new_id)
    parent_id: str | None = None
    data_type: str = "VARCHAR(255)"
    is_pk: bool = False
    nullable: bool = True
    unique: bool = False
    derived: bool = False
    notes: str = ""
    isa_total: bool = False
    isa_disjoint: bool = True
    text_html: str = ""
    parent_port: str | None = None
    child_port: str | None = None
    connection_points: list[list[float]] = field(default_factory=list)
    label_offsets: dict[str, list[float]] = field(default_factory=dict)
    attribute_card: str | None = None
    parent_anchor_angle: float | None = None


@dataclass
class Link:
    source: str
    target: str
    id: str = field(default_factory=new_id)
    source_card: str = "0,N"
    target_card: str = "0,N"
    role: str = ""
    source_port: str | None = None
    target_port: str | None = None
    route_points: list[list[float]] = field(default_factory=list)
    label_offsets: dict[str, list[float]] = field(default_factory=dict)


@dataclass
class Document:
    title: str = DEFAULT_TITLE
    nodes: list[Node] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)

    def node(self, identifier: str) -> Node | None:
        return next((n for n in self.nodes if n.id == identifier), None)

    def attributes(self, parent_id: str) -> list[Node]:
        return [n for n in self.nodes if n.parent_id == parent_id
                and n.kind in {"attribute", "multivalue"}]

    def to_dict(self) -> dict[str, Any]:
        def serialize(item):
            data = asdict(item)
            if data["label_offsets"] == {}:
                del data["label_offsets"]
            for key in ("attribute_card", "parent_anchor_angle"):
                if data.get(key) is None:
                    data.pop(key, None)
            return data

        return {"format": "drawer-desktop", "schema_version": SCHEMA_VERSION,
                "title": self.title, "nodes": [serialize(n) for n in self.nodes],
                "links": [serialize(edge) for edge in self.links]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Document:
        if not isinstance(data, dict):
            raise ValueError("Il progetto deve essere un oggetto JSON.")
        if "objects" in data:
            return cls._from_legacy(data)
        version = data.get("schema_version", SCHEMA_VERSION)
        if type(version) is not int or version != SCHEMA_VERSION:
            raise ValueError(f"Versione progetto {version!r} non supportata (attesa {SCHEMA_VERSION}).")
        if data.get("format", "drawer-desktop") != "drawer-desktop":
            raise ValueError("Il file non è un progetto DrawER Desktop.")
        raw_nodes, raw_links = data.get("nodes"), data.get("links")
        _check_arrays(raw_nodes, raw_links)
        title = _string(data.get("title", DEFAULT_TITLE), "Titolo", 1024)
        node_fields = {f.name for f in fields(Node)}
        link_fields = {f.name for f in fields(Link)}
        nodes: list[Node] = []
        links: list[Link] = []
        for index, raw in enumerate(raw_nodes):
            if not isinstance(raw, dict):
                raise ValueError(f"Oggetto {index + 1}: dati non validi.")
            if set(raw) - node_fields:
                raise ValueError(f"Oggetto {index + 1}: campi sconosciuti.")
            if "id" not in raw or "kind" not in raw:
                raise ValueError(f"Oggetto {index + 1}: mancano ID o tipo.")
            node = Node(**raw)
            _check_node(node)
            if node.text_html:
                node.text_html = sanitize_note_html(node.text_html)
            nodes.append(node)
        for index, raw in enumerate(raw_links):
            if not isinstance(raw, dict) or set(raw) - link_fields:
                raise ValueError(f"Collegamento {index + 1}: campi non validi.")
            if not {"source", "target", "id"}.issubset(raw):
                raise ValueError(f"Collegamento {index + 1}: mancano ID o estremi.")
            edge = Link(**raw)
            _check_link(edge)
            links.append(edge)
        result = cls(title, nodes, links)
        _check_references(result)
        return result

    @classmethod
    def _from_legacy(cls, data: dict[str, Any]) -> Document:
        """Convert the original browser .erdraw index-based representation.

        The browser never stored cardinalities or SQL types.  They start as
        optional-many / VARCHAR(255) and must be reviewed before SQL export.
        """
        raw_nodes, raw_links = data.get("objects"), data.get("links")
        _check_arrays(raw_nodes, raw_links)
        nodes: list[Node] = []
        for index, raw in enumerate(raw_nodes):
            if not isinstance(raw, dict) or not isinstance(raw.get("type"), str) or raw.get("type") not in KINDS:
                raise ValueError(f"Oggetto legacy {index + 1}: tipo sconosciuto.")
            kind = raw["type"]
            name = raw.get("text", "Nota") if kind == "text" else raw.get("name", raw.get("label", "ISA"))
            width = raw.get("w", 140 if kind in {"attribute", "multivalue"} else 160)
            height = raw.get("h", 44 if kind in {"attribute", "multivalue"} else 76)
            node = Node(kind=kind, name=name, x=raw.get("x", 0), y=raw.get("y", 0),
                        width=width, height=height, is_pk=raw.get("isPK", False),
                        notes="Importato dalla versione web: tipi SQL e cardinalità non erano definiti; verificare.")
            _check_node(node)
            # Both renderers anchor simple attributes at their small circle;
            # preserve their saved x/y exactly, without a box-coordinate offset.
            if kind == "isa":
                point = raw.get("endPoint")
                if point is not None:
                    if not isinstance(point, dict):
                        raise ValueError("Punto terminale ISA legacy non valido.")
                    point_x, point_y = point.get("x", node.x), point.get("y", node.y)
                    if type(point_x) not in (int, float) or type(point_y) not in (int, float):
                        raise ValueError("Coordinate terminali ISA legacy non valide.")
                    node.x = point_x - 32
                    node.y = point_y - 28
                else:
                    stem = raw.get("stemHeight", 60)
                    angle = raw.get("angle", math.pi / 2)
                    if (type(stem) not in (int, float) or not math.isfinite(stem)
                            or not 0 <= stem <= 1_000_000):
                        raise ValueError("Altezza ISA legacy non valida.")
                    if type(angle) not in (int, float) or not math.isfinite(angle):
                        raise ValueError("Angolo ISA legacy non valido.")
                    # script.js saved the anchor and angle; the modular version
                    # saved an explicit endpoint. Place the new triangle with
                    # its center at the same branching point in both cases.
                    node.x += math.cos(angle) * stem - 32
                    node.y += math.sin(angle) * stem - 28
                node.width, node.height = 64, 56
                label = str(raw.get("label", "")).casefold()
                code = re.fullmatch(r"\(?\s*([pt])\s*,\s*([dse])\s*\)?", label)
                node.isa_total = code[1] == "t" if code else "totale" in label
                node.isa_disjoint = code[2] in {"d", "e"} if code else any(
                    word in label for word in ("disgiunt", "esclusiv", "disjoint"))
            try:
                _check_node(node)
            except (TypeError, ValueError) as error:
                raise ValueError(f"Oggetto legacy {index + 1}: {error}") from error
            nodes.append(node)
        for index, raw in enumerate(raw_nodes):
            if raw["type"] in {"attribute", "isa"}:
                parent_index = raw.get("parentIdx")
                if type(parent_index) is not int or not 0 <= parent_index < len(nodes):
                    raise ValueError(f"Oggetto legacy {index + 1}: riferimento al genitore non valido.")
                nodes[index].parent_id = nodes[parent_index].id
        links: list[Link] = []
        for index, raw in enumerate(raw_links):
            if not isinstance(raw, dict):
                raise ValueError(f"Collegamento legacy {index + 1} non valido.")
            src, tgt = raw.get("srcIdx"), raw.get("tgtIdx")
            if any(type(value) is not int or not 0 <= value < len(nodes) for value in (src, tgt)):
                raise ValueError(f"Collegamento legacy {index + 1}: indice fuori intervallo.")
            links.append(Link(nodes[src].id, nodes[tgt].id))
        # Old 'multivalue' was an independent aggregate ellipse, rather than an
        # owned scalar attribute. Preserve that distinction for explicit review.
        for node in nodes:
            if node.kind != "multivalue":
                continue
            node.notes += " Ovale multivalore indipendente: assegnare esplicitamente un proprietario."
            if any(child.parent_id == node.id for child in nodes):
                node.notes += " Aggregato multivalore: la conversione SQL richiede una ristrutturazione esplicita."
        result = cls(_string(data.get("title", "Progetto web importato"), "Titolo", 1024), nodes, links)
        _check_references(result)
        return result


def _string(value: Any, label: str, maximum: int = 1024) -> str:
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise ValueError(f"{label}: testo non valido o troppo lungo.")
    return value


def _identifier(value: Any, label: str) -> None:
    if not _string(value, label, 128).strip():
        raise ValueError(f"{label}: identificatore vuoto.")


def _check_arrays(nodes: Any, links: Any) -> None:
    if not isinstance(nodes, list) or not isinstance(links, list):
        raise ValueError("Il progetto deve contenere liste di oggetti e collegamenti.")
    if len(nodes) > MAX_NODES or len(links) > MAX_LINKS:
        raise ValueError("Il progetto supera il limite di 10.000 oggetti o 30.000 collegamenti.")


def _check_node(node: Node) -> None:
    if not isinstance(node.kind, str) or node.kind not in KINDS:
        raise ValueError(f"Tipo di oggetto sconosciuto: {node.kind!r}.")
    _identifier(node.id, "ID oggetto")
    _string(node.name, "Testo nota" if node.kind == "text" else "Nome",
            MAX_NOTE_TEXT if node.kind == "text" else 1024)
    _string(node.text_html, "Formattazione della nota", MAX_NOTE_HTML)
    if node.text_html and node.kind != "text":
        raise ValueError("La formattazione del testo è disponibile solo per le note del diagramma.")
    _string(node.notes, "Note", 16384)
    _string(node.data_type, "Tipo SQL", 128)
    if node.parent_id is not None:
        _identifier(node.parent_id, "ID genitore")
    for name in ("x", "y", "width", "height"):
        value = getattr(node, name)
        if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1_000_000:
            raise ValueError(f"Coordinata o dimensione {name} non valida.")
    if not (20 <= node.width <= 4000 and 20 <= node.height <= 4000):
        raise ValueError("Dimensioni oggetto fuori intervallo (20–4000).")
    for name in ("is_pk", "nullable", "unique", "derived", "isa_total", "isa_disjoint"):
        if type(getattr(node, name)) is not bool:
            raise ValueError(f"Proprietà {name} non booleana.")
    if node.attribute_card is not None and (
        node.kind != "attribute" or node.attribute_card not in CARDINALITIES
    ):
        raise ValueError("Cardinalità dell’attributo non valida.")
    angle = node.parent_anchor_angle
    if angle is not None and (node.kind not in ("attribute", "multivalue")
                              or type(angle) not in (int, float) or not -math.pi <= angle <= math.pi):
        raise ValueError("Punto di attacco dell’attributo non valido.")
    _check_geometry(node.parent_port, node.child_port, node.connection_points)
    _check_label_offsets(node.label_offsets, {"isa"} if node.kind == "isa" else
                         {"attribute"} if node.kind == "attribute" else set())


def _check_link(edge: Link) -> None:
    for value, label in ((edge.id, "ID collegamento"), (edge.source, "Sorgente"), (edge.target, "Destinazione")):
        _identifier(value, label)
    _string(edge.role, "Ruolo")
    if edge.source_card not in CARDINALITIES or edge.target_card not in CARDINALITIES:
        raise ValueError("Cardinalità non valida: usare 0,1 / 1,1 / 0,N / 1,N.")
    _check_geometry(edge.source_port, edge.target_port, edge.route_points)
    _check_label_offsets(edge.label_offsets, {"source", "target", "role"})


def _check_label_offsets(offsets, keys):
    if not isinstance(offsets, dict) or not offsets.keys() <= keys:
        raise ValueError("Posizione delle etichette non valida.")
    for offset in offsets.values():
        if not isinstance(offset, list) or len(offset) != 2 or any(
            type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1_000_000
            for value in offset
        ):
            raise ValueError("Coordinate dell’etichetta non valide.")


def _check_geometry(source_port, target_port, points):
    if any(port is not None and port not in PORTS for port in (source_port, target_port)):
        raise ValueError("Punto di attacco non valido: usare uno dei quattro lati.")
    if not isinstance(points, list) or len(points) > 256 or (points and len(points) < 2):
        raise ValueError("Il percorso deve contenere da 2 a 256 punti.")
    for point in points:
        if not isinstance(point, list) or len(point) != 2 or any(
            type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1_000_000
            for value in point
        ):
            raise ValueError("Coordinate del collegamento non valide.")
    for a, b in zip(points, points[1:]):
        if abs(a[0]-b[0]) > .01 and abs(a[1]-b[1]) > .01:
            raise ValueError("Le pieghe del collegamento devono essere ortogonali.")


def _check_references(doc: Document) -> None:
    ids = [node.id for node in doc.nodes] + [edge.id for edge in doc.links]
    if len(ids) != len(set(ids)):
        raise ValueError("Il progetto contiene identificatori duplicati.")
    node_ids = {node.id for node in doc.nodes}
    parents = {node.id: node.parent_id for node in doc.nodes}
    for node in doc.nodes:
        if node.parent_id is not None and node.parent_id not in node_ids:
            raise ValueError(f"'{node.name}': genitore inesistente.")
        seen = {node.id}
        parent = node.parent_id
        while parent is not None:
            if parent in seen:
                raise ValueError("Il progetto contiene un ciclo tra genitori e attributi.")
            seen.add(parent)
            parent = parents.get(parent)
    for edge in doc.links:
        if edge.source not in node_ids or edge.target not in node_ids:
            raise ValueError("Collegamento con estremo inesistente.")
