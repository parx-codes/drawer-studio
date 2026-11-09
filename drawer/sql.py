"""Translate binary conceptual ER diagrams into reviewable SQLite/PostgreSQL DDL.

Cardinalities use Chen min/max participation: an entity labelled (0,1) can
participate in at most one relationship instance. In a 1:N relationship this is
the entity that receives the FK. Identifiers are always quoted and data types
come from a whitelist; no user text is treated as executable SQL.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re

from .model import Document, Link, Node

SQL_TYPES = ("INTEGER", "BIGINT", "REAL", "NUMERIC", "BOOLEAN", "TEXT", "DATE",
             "TIMESTAMP", "UUID", "VARCHAR(255)", "DECIMAL(10,2)")


class SqlExportError(ValueError):
    """The diagram needs an explicit design decision before it can become SQL."""


def normalize_type(value: str, dialect: str = "sqlite") -> str:
    if dialect not in {"sqlite", "postgresql"}:
        raise ValueError("Dialetto SQL non supportato: scegliere sqlite o postgresql.")
    if not isinstance(value, str):
        raise ValueError("Tipo SQL non valido.")
    kind = " ".join(value.strip().upper().split())
    aliases = {"INT": "INTEGER", "SMALLINT": "SMALLINT", "FLOAT": "REAL", "DOUBLE": "DOUBLE PRECISION",
               "DECIMAL": "NUMERIC", "BOOL": "BOOLEAN", "CHARACTER VARYING": "VARCHAR(255)"}
    kind = aliases.get(kind, kind)
    simple = {"INTEGER", "SMALLINT", "BIGINT", "REAL", "DOUBLE PRECISION", "NUMERIC", "BOOLEAN",
              "TEXT", "DATE", "TIME", "TIMESTAMP", "UUID", "BLOB", "BYTEA"}
    match = re.fullmatch(r"(VARCHAR|CHAR|NUMERIC|DECIMAL)\s*\(\s*(\d{1,5})\s*(?:,\s*(\d{1,4})\s*)?\)", kind)
    if match:
        base, first, second = match.groups()
        precision = int(first)
        if base in {"VARCHAR", "CHAR"}:
            if second is not None or not 1 <= precision <= 65535:
                raise ValueError("La lunghezza CHAR/VARCHAR deve essere compresa tra 1 e 65535.")
            return f"{base}({precision})"
        if not 1 <= precision <= 1000 or second is not None and int(second) > precision:
            raise ValueError("Precisione NUMERIC/DECIMAL non valida (1–1000, scala ≤ precisione).")
        return f"NUMERIC({precision}{',' + str(int(second)) if second is not None else ''})"
    if kind not in simple:
        raise ValueError(f"Tipo SQL '{value}' non supportato. Usare un tipo semplice o VARCHAR(n)/DECIMAL(p,s).")
    if dialect == "sqlite":
        return {"UUID": "TEXT", "DATE": "TEXT", "TIME": "TEXT", "TIMESTAMP": "TEXT",
                "BOOLEAN": "INTEGER", "BYTEA": "BLOB"}.get(kind, kind)
    return {"BLOB": "BYTEA"}.get(kind, kind)


def quote(name: str) -> str:
    """SQL-standard identifier quoting, including embedded quote characters."""
    return '"' + name.replace('"', '""') + '"'


def _comment(value: str) -> str:
    return " ".join(value.replace("\x00", "").split())


@dataclass
class _Column:
    name: str
    data_type: str
    nullable: bool = True
    unique: bool = False


@dataclass
class _ForeignKey:
    columns: list[str]
    target: str
    target_columns: list[str]

    def sql(self) -> str:
        return (f"FOREIGN KEY ({', '.join(map(quote, self.columns))}) REFERENCES {quote(self.target)} "
                f"({', '.join(map(quote, self.target_columns))}) DEFERRABLE INITIALLY DEFERRED")


@dataclass
class _Table:
    name: str
    columns: list[_Column] = field(default_factory=list)
    pk: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    foreign_keys: list[_ForeignKey] = field(default_factory=list)

    def add(self, column: _Column) -> None:
        if any(c.name.casefold() == column.name.casefold() for c in self.columns):
            raise SqlExportError(f"Tabella '{self.name}': collisione della colonna '{column.name}'. Rinominare attributi, relazioni o ruoli.")
        self.columns.append(column)

    def column(self, name: str) -> _Column:
        return next(column for column in self.columns if column.name == name)


@dataclass
class _Participation:
    entity: Node
    card: str
    role: str


@dataclass
class _Relationship:
    name: str
    ends: list[_Participation]
    attributes: list[Node]


def generate_sql(doc: Document, dialect: str = "sqlite") -> str:
    """Return complete transactional DDL; reject ambiguous/incomplete mappings.

    This exports a new schema, never a migration or a connection to a live DB.
    Minima on referenced entities and total/disjoint ISA cannot be represented
    by ordinary foreign keys; explicit comments retain those obligations.
    """
    dialect = dialect.casefold()
    if dialect not in {"sqlite", "postgresql"}:
        raise SqlExportError("Dialetto SQL non supportato: scegliere sqlite o postgresql.")
    from .validation import validate
    errors = [issue.message for issue in validate(doc) if issue.severity == "error"]
    if errors:
        raise SqlExportError("Correggere lo schema prima dell'esportazione:\n• " + "\n• ".join(dict.fromkeys(errors)))
    entities = [node for node in doc.nodes if node.kind == "entity"]
    if not entities:
        raise SqlExportError("Il diagramma non contiene entità da esportare.")
    by_id = {node.id: node for node in doc.nodes}
    tables: dict[str, _Table] = {}
    entity_tables: dict[str, _Table] = {}
    notes = ["DDL preliminare generato da DrawER Studio. Rivedere le scelte prima dell'uso in produzione.",
             "Cardinalità (min,max) = partecipazione dell'entità alla relazione.",
             "I nomi sono preservati e quotati; nessuna connessione al database viene aperta."]
    if any(node.notes.startswith("Importato dalla versione web") for node in doc.nodes):
        notes.insert(0, "IMPORTAZIONE WEB: tipi/cardinalità non presenti nel file originale, "
                        "valori iniziali da revisionare (VARCHAR(255) e partecipazione (0,N)).")

    for node in doc.nodes:
        if node.kind == "attribute" and node.attribute_card and not node.derived:
            if node.is_pk and node.attribute_card != "1,1":
                raise SqlExportError(f"'{node.name}': una chiave richiede cardinalità (1,1).")
            if node.attribute_card.endswith("N") and by_id[node.parent_id].kind != "entity":
                raise SqlExportError(f"'{node.name}': esportazione di attributi ripetibili supportata per le entità.")

    def check_name(name: str) -> str:
        clean = name.strip()
        if not clean or "\x00" in clean:
            raise SqlExportError("Identificatore SQL vuoto o non valido.")
        if dialect == "postgresql" and len(clean.encode("utf-8")) > 63:
            raise SqlExportError(f"Identificatore '{clean}' oltre 63 byte: rinominarlo per PostgreSQL.")
        return clean

    def table(name: str) -> _Table:
        name = check_name(name)
        if dialect == "sqlite" and name.casefold().startswith("sqlite_"):
            raise SqlExportError(f"Nome tabella '{name}' riservato da SQLite: scegliere un nome senza prefisso sqlite_.")
        if name.casefold() in tables:
            raise SqlExportError(f"Collisione del nome tabella '{name}'. Rinominare l'entità, la relazione o il multivalore.")
        result = _Table(name)
        tables[name.casefold()] = result
        return result

    def attribute_column(attr: Node, name: str | None = None, nullable: bool | None = None) -> _Column:
        optional = attr.attribute_card.startswith("0") if attr.attribute_card else attr.nullable
        return _Column(check_name(name if name is not None else attr.name), normalize_type(attr.data_type, dialect),
                       (optional and not attr.is_pk) if nullable is None else nullable,
                       attr.unique)

    # TPT: each subtype inherits exactly the supertype key. Multiple inheritance
    # needs a separate design decision and is intentionally not guessed.
    supertypes: dict[str, str] = {}
    for isa in [n for n in doc.nodes if n.kind == "isa"]:
        children = []
        for edge in doc.links:
            other = edge.target if edge.source == isa.id else edge.source if edge.target == isa.id else None
            if other:
                if other in supertypes:
                    raise SqlExportError(f"'{by_id[other].name}': ereditarietà multipla o ISA duplicata non supportata.")
                supertypes[other] = isa.parent_id
                children.append(by_id[other].name)
        notes.append(f"ISA {_comment(isa.name)}: supertipo {_comment(by_id[isa.parent_id].name)}, "
                     f"sottotipi {', '.join(map(_comment, children))}; "
                     f"{'totale' if isa.isa_total else 'parziale'}, {'disgiunta' if isa.isa_disjoint else 'sovrapposta'}. "
                     "Totalità e disgiunzione non sono imposte dal DDL: aggiungere logica applicativa o trigger.")

    visiting: set[str] = set()

    def build_entity(entity: Node) -> _Table:
        if entity.id in entity_tables:
            return entity_tables[entity.id]
        if entity.id in visiting:
            raise SqlExportError("La gerarchia ISA contiene un ciclo.")
        visiting.add(entity.id)
        supertable = build_entity(by_id[supertypes[entity.id]]) if entity.id in supertypes else None
        result = table(entity.name)
        entity_tables[entity.id] = result
        simple = [attr for attr in doc.attributes(entity.id) if attr.kind == "attribute" and not attr.derived
                  and attr.attribute_card not in ("0,N", "1,N")]
        own_keys = [attr for attr in simple if attr.is_pk]
        if supertable:
            inherited_names = {name.casefold() for name in supertable.pk}
            shadowed = [attr for attr in doc.attributes(entity.id)
                        if attr.name.strip().casefold() in inherited_names
                        and (attr.derived or attr.kind == "multivalue" or attr.attribute_card in ("0,N", "1,N"))]
            if shadowed:
                raise SqlExportError(f"'{entity.name}.{shadowed[0].name}': un attributo derivato o multivalore "
                                     "non può sostituire un membro della chiave primaria ereditata.")
            if own_keys and {attr.name.strip().casefold() for attr in own_keys} != inherited_names:
                raise SqlExportError(f"'{entity.name}': il sottotipo eredita la PK di '{supertable.name}'; "
                                     "rimuovere la PK autonoma o allinearla a quella ereditata.")
            for key in supertable.pk:
                source_column = supertable.column(key)
                same_name = next((attr for attr in simple if attr.name.strip().casefold() == key.casefold()), None)
                if same_name:
                    if normalize_type(same_name.data_type, dialect) != source_column.data_type:
                        raise SqlExportError(f"'{entity.name}.{same_name.name}': il tipo deve coincidere con la chiave ereditata.")
                    simple.remove(same_name)
                result.add(_Column(key, source_column.data_type, nullable=False,
                                   unique=same_name.unique if same_name else False))
            result.pk = list(supertable.pk)
            result.foreign_keys.append(_ForeignKey(list(result.pk), supertable.name, list(supertable.pk)))
        else:
            result.pk = [check_name(attr.name) for attr in own_keys]
            if not result.pk:
                raise SqlExportError(f"'{entity.name}': definire una chiave primaria.")
        for attr in simple:
            result.add(attribute_column(attr))
        for attr in doc.attributes(entity.id):
            if attr.derived:
                notes.append(f"Attributo derivato {_comment(entity.name)}.{_comment(attr.name)} escluso dal DDL.")
        visiting.remove(entity.id)
        return result

    for entity in entities:
        build_entity(entity)

    relationships: list[_Relationship] = []
    for relation in [node for node in doc.nodes if node.kind == "relation"]:
        ends = []
        for edge in doc.links:
            if edge.source == relation.id:
                ends.append(_Participation(by_id[edge.target], edge.target_card, edge.role.strip()))
            elif edge.target == relation.id:
                ends.append(_Participation(by_id[edge.source], edge.source_card, edge.role.strip()))
        relationships.append(_Relationship(relation.name.strip(), ends, doc.attributes(relation.id)))
    for edge in doc.links:
        source, target = by_id[edge.source], by_id[edge.target]
        if source.kind == target.kind == "entity":
            relation_name = edge.role.strip() or f"{source.name.strip()}_{target.name.strip()}"
            relationships.append(_Relationship(relation_name,
                                 [_Participation(source, edge.source_card, source.name.strip()),
                                  _Participation(target, edge.target_card, target.name.strip())], []))

    def add_fk(host: _Table, target: _Table, prefix: str, nullable: bool) -> list[str]:
        columns = []
        for key in target.pk:
            name = check_name(f"{prefix}_{key}")
            host.add(_Column(name, target.column(key).data_type, nullable))
            columns.append(name)
        host.foreign_keys.append(_ForeignKey(list(columns), target.name, list(target.pk)))
        if nullable and len(columns) > 1:
            # SQLite MATCH SIMPLE alone would accept half-NULL composite keys.
            nulls = " AND ".join(f"{quote(col)} IS NULL" for col in columns)
            values = " AND ".join(f"{quote(col)} IS NOT NULL" for col in columns)
            host.constraints.append(f"CHECK (({nulls}) OR ({values}))")
        return columns

    for relation in relationships:
        left, right = relation.ends
        host_end = None
        optional = False
        attrs = [attr for attr in relation.attributes if not attr.derived]
        for attr in relation.attributes:
            if attr.derived:
                notes.append(f"Attributo derivato {_comment(relation.name)}.{_comment(attr.name)} escluso dal DDL.")
        left_many, right_many = left.card.endswith("N"), right.card.endswith("N")
        if left_many and right_many:
            bridge = table(relation.name)
            for end in (left, right):
                target = entity_tables[end.entity.id]
                prefix = end.role or end.entity.name.strip()
                bridge.pk.extend(add_fk(bridge, target, prefix, nullable=False))
            for attr in attrs:
                bridge.add(attribute_column(attr))
            notes.append(f"Relazione {_comment(relation.name)} N:M → tabella ponte {_comment(bridge.name)} con PK composta delle due FK.")
        else:
            if left_many != right_many:
                host_end, target_end = (right, left) if left_many else (left, right)
            else:
                # Prefer a mandatory participant, then use stable visible names.
                host_end, target_end = sorted((left, right), key=lambda end: (not end.card.startswith("1,"),
                                                                            end.entity.name.casefold(), end.role.casefold(), end.entity.id))
            host, target = entity_tables[host_end.entity.id], entity_tables[target_end.entity.id]
            prefix = check_name(f"{relation.name}_{target_end.role or target.name}")
            optional = host_end.card.startswith("0,")
            fk_columns = add_fk(host, target, prefix, nullable=optional)
            if not left_many and not right_many:
                host.constraints.append(f"UNIQUE ({', '.join(map(quote, fk_columns))})")
            relation_columns = []
            for attr in attrs:
                name = check_name(f"{relation.name}_{attr.name.strip()}")
                host.add(attribute_column(attr, name, nullable=True if optional else None))
                relation_columns.append(name)
                if optional and not attribute_column(attr).nullable:
                    host.constraints.append(f"CHECK ({quote(fk_columns[0])} IS NULL OR {quote(name)} IS NOT NULL)")
            if optional and relation_columns:
                absent = " AND ".join(f"{quote(name)} IS NULL" for name in relation_columns)
                host.constraints.append(f"CHECK ({quote(fk_columns[0])} IS NOT NULL OR ({absent}))")
            shape = "1:1" if not left_many and not right_many else "1:N"
            notes.append(f"Relazione {_comment(relation.name)} {shape} → FK {'opzionale' if optional else 'obbligatoria'} "
                         f"in {_comment(host.name)} verso {_comment(target.name)}"
                         + ("; UNIQUE sulla FK." if shape == "1:1" else "."))
        for end in relation.ends:
            if end.card.startswith("1,"):
                # NOT NULL enforces a host-side minimum of one. Other minima
                # are cross-row/cross-table assertions, not ordinary FK checks.
                imposed = not (left_many and right_many) and end is host_end and not optional
                if not imposed:
                    notes.append(f"MINIMO NON IMPOSTO: {_comment(end.entity.name)} ({end.card}) nella relazione "
                                 f"{_comment(relation.name)} richiede controllo applicativo o trigger.")

    # Each simple multivalued attribute gets its own table. The value and owner
    # key form a composite PK: a set (duplicates are deliberately disallowed).
    for attr in [n for n in doc.nodes if (n.kind == "multivalue" or n.attribute_card in ("0,N", "1,N"))
                 and not n.derived]:
        if attr.parent_id not in entity_tables:
            raise SqlExportError(f"'{attr.name}': definire un'entità proprietaria per il multivalore.")
        owner = entity_tables[attr.parent_id]
        result = table(f"{owner.name}_{attr.name.strip()}")
        result.pk = add_fk(result, owner, owner.name, nullable=False)
        children = doc.attributes(attr.id)
        if children:
            if any(child.kind != 'attribute' for child in children):
                raise SqlExportError(f"'{attr.name}': annidamenti di aggregati multivalore non supportati.")
            columns = [child for child in children if not child.derived]
            if not columns:
                raise SqlExportError(f"'{attr.name}': aggiungere almeno un attributo semplice non derivato.")
            keys = [child for child in columns if child.is_pk]
            if not keys:
                index_name = '_indice'
                while any(child.name.casefold() == index_name.casefold() for child in columns):
                    index_name = '_' + index_name
                result.add(_Column(index_name, 'INTEGER', nullable=False))
                result.pk.append(index_name)
                notes.append(f"Aggregato multivalore {_comment(owner.name)}.{_comment(attr.name)}: "
                    f"{index_name} identifica l'occorrenza per proprietario; valorizzarlo in inserimento. "
                    "L'unicità dell'intera tupla di valori richiede una regola di dominio aggiuntiva.")
            for child in columns:
                result.add(attribute_column(child))
                if child.is_pk:
                    result.pk.append(check_name(child.name))
            notes.append(f"Aggregato multivalore {_comment(attr.name)} → tabella {_comment(result.name)} "
                         "con attributi componenti e FK al proprietario.")
            continue
        value_column = attribute_column(attr, attr.name.strip(), nullable=False)
        result.add(value_column)
        result.pk.append(value_column.name)
        if attr.attribute_card == "1,N":
            notes.append(f"MINIMO NON IMPOSTO: {_comment(owner.name)}.{_comment(attr.name)} (1,N) "
                         "richiede almeno un valore per proprietario, da verificare con trigger o applicazione.")
        notes.append(f"Multivalore {_comment(owner.name)}.{_comment(attr.name)} → tabella {_comment(result.name)}; "
                     "insieme di valori distinti, nessuna riga rappresenta l'insieme vuoto.")

    lines = ["-- " + _comment(note) for note in notes]
    if dialect == "sqlite":
        lines += ["-- SQLite usa affinità dinamiche: lunghezze VARCHAR, precisioni NUMERIC e domini BOOLEAN/data non sono imposti automaticamente."]
        lines += ["", "PRAGMA foreign_keys = ON;"]
    lines += ["", "BEGIN;", ""]
    for result in tables.values():
        definitions = []
        for column in result.columns:
            check_name(column.name)
            definitions.append(f"{quote(column.name)} {column.data_type}"
                               + (" NOT NULL" if not column.nullable else "")
                               + (" UNIQUE" if column.unique else ""))
        definitions.append(f"PRIMARY KEY ({', '.join(map(quote, result.pk))})")
        definitions.extend(result.constraints)
        if dialect == "sqlite":
            definitions.extend(fk.sql() for fk in result.foreign_keys)
        lines += [f"CREATE TABLE {quote(result.name)} (", "    " + ",\n    ".join(definitions), ");", ""]
    if dialect == "postgresql":
        # Separate ALTER statements support mutual references and any creation order.
        for result in tables.values():
            for fk in result.foreign_keys:
                lines.append(f"ALTER TABLE {quote(result.name)} ADD {fk.sql()};")
        lines.append("")
    lines += ["COMMIT;", ""]
    return "\n".join(lines)
