"""Actionable checks for students and for the preliminary logical design."""
from __future__ import annotations

from dataclasses import dataclass
from collections import Counter, defaultdict

from .model import CARDINALITIES, Document, _check_node, _check_link, _check_references


@dataclass(frozen=True)
class Issue:
    severity: str
    message: str
    node_id: str | None = None


def validate(doc: Document) -> list[Issue]:
    issues: list[Issue] = []

    def add(severity, message, node=None):
        issues.append(Issue(severity, message, node.id if node else None))

    try:
        _check_references(doc)
    except (TypeError, ValueError) as error:
        add("error", str(error))
        return issues
    by_id = {node.id: node for node in doc.nodes}
    incident: dict[str, list] = defaultdict(list)
    for edge in doc.links:
        try:
            _check_link(edge)
        except (TypeError, ValueError) as error:
            add("error", str(error))
        incident[edge.source].append(edge)
        incident[edge.target].append(edge)
    names = Counter(node.name.strip().casefold() for node in doc.nodes if node.kind in {"entity", "relation"})
    inherited = set()
    for node in doc.nodes:
        if node.kind == "isa":
            for edge in incident[node.id]:
                other = by_id[edge.target if edge.source == node.id else edge.source]
                if other.kind == "entity" and other.id != node.parent_id:
                    inherited.add(other.id)
    from .sql import normalize_type  # Keep SQL normalization in a single place.

    for node in doc.nodes:
        try:
            _check_node(node)
        except (TypeError, ValueError) as error:
            add("error", str(error), node)
            continue
        if not node.name.strip():
            add("error" if node.kind != "text" else "warning", "Oggetto senza nome.", node)
        if node.kind in {"entity", "relation"} and names[node.name.strip().casefold()] > 1:
            add("error", f"Nome '{node.name}' duplicato tra entità o relazioni.", node)
        if node.kind in {"attribute", "multivalue"}:
            parent = by_id.get(node.parent_id)
            if not parent:
                add("error", f"'{node.name}': attribuire un proprietario prima dell'esportazione SQL.", node)
            elif parent.kind not in {"entity", "relation", "multivalue"}:
                add("error", f"'{node.name}': il proprietario deve essere un'entità o una relazione.", node)
            elif node.kind == "multivalue" and parent.kind != "entity":
                add("error", f"'{node.name}': il multivalore SQL richiede un'entità proprietaria.", node)
            if not node.derived and not (node.kind == 'multivalue' and doc.attributes(node.id)):
                try:
                    normalize_type(node.data_type)
                except ValueError as error:
                    add("error", f"'{node.name}': {error}", node)
            if node.is_pk and (node.kind != "attribute" or node.derived):
                add("error", f"'{node.name}': una chiave deve essere un attributo semplice non derivato.", node)
            if node.is_pk and parent and parent.kind == "relation":
                add("error", f"'{node.name}': chiavi proprie della relazione non supportate dalla traduzione SQL.", node)
        if node.kind in {"entity", "relation", "multivalue"}:
            attributes = doc.attributes(node.id)
            duplicated = Counter(attr.name.strip().casefold() for attr in attributes)
            for attr in attributes:
                if duplicated[attr.name.strip().casefold()] > 1:
                    add("error", f"'{node.name}': attributo '{attr.name}' duplicato.", attr)
            if node.kind == "entity" and node.id not in inherited and not any(attr.is_pk and not attr.derived for attr in attributes):
                add("error", f"'{node.name}': definire almeno un attributo chiave primaria.", node)
            if node.kind == "entity" and not incident[node.id] and not any(n.kind == "isa" and n.parent_id == node.id for n in doc.nodes):
                add("warning", f"'{node.name}': entità isolata.", node)
        if node.kind == "relation":
            edges = incident[node.id]
            participants = [by_id[edge.target if edge.source == node.id else edge.source] for edge in edges]
            if len(edges) != 2 or any(n.kind != "entity" for n in participants):
                add("error", f"'{node.name}': l'esportazione SQL richiede due partecipazioni di entità (anche riflessive).", node)
            if len(participants) == 2 and participants[0].id == participants[1].id:
                roles = [edge.role.strip().casefold() for edge in edges]
                if not all(roles) or roles[0] == roles[1]:
                    add("error", f"'{node.name}': specificare due ruoli distinti nella relazione riflessiva.", node)
        if node.kind == "isa":
            parent = by_id.get(node.parent_id)
            children = [by_id[edge.target if edge.source == node.id else edge.source] for edge in incident[node.id]]
            if not parent or parent.kind != "entity":
                add("error", f"'{node.name}': la generalizzazione richiede un'entità supertipo.", node)
            if not children or any(child.kind != "entity" or child.id == node.parent_id for child in children):
                add("error", f"'{node.name}': collegare almeno un sottotipo distinto dal supertipo.", node)
            add("warning", f"'{node.name}': SQL table-per-type; totalità e disgiunzione richiedono vincoli applicativi o trigger.", node)
        if node.notes.startswith("Importato dalla versione web"):
            add("warning", f"'{node.name}': importazione web, rivedere tipi SQL, cardinalità e vincoli.", node)
    seen = set()
    for edge in doc.links:
        source, target = by_id[edge.source], by_id[edge.target]
        kinds = {source.kind, target.kind}
        allowed = (kinds == {"entity", "relation"} or kinds == {"entity", "isa"}
                   or source.kind == target.kind == "entity")
        if not allowed:
            add("error", f"Collegamento '{source.name}'–'{target.name}' non traducibile in SQL: usare un proprietario per gli attributi.")
        signature = (frozenset((edge.source, edge.target)), edge.role.strip().casefold())
        if signature in seen:
            add("error", f"Collegamento duplicato tra '{source.name}' e '{target.name}' con lo stesso ruolo.")
        seen.add(signature)
        if edge.source == edge.target:
            add("error", "Una relazione riflessiva richiede un nodo relazione con due ruoli distinti.", source)
        if allowed and "isa" not in kinds:
            relevant = [edge.source_card] if source.kind == "entity" else []
            relevant += [edge.target_card] if target.kind == "entity" else []
            if any(card in CARDINALITIES and card.startswith("1,") for card in relevant):
                add("warning", "Le partecipazioni minime sul lato referenziato o N:M richiedono controlli applicativi/trigger; verificare le note SQL.")
    return issues
