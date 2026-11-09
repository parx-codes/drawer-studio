"""Executable domain checks: generated SQL is exercised by a real SQLite DB."""
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3

import pytest

from drawer.model import Document, Link, Node
from drawer.storage import load_document, save_document
from drawer.sql import generate_sql, normalize_type, SqlExportError
from drawer.validation import validate


def entity(doc, name, keys=("id",)):
    node = Node(kind="entity", name=name)
    doc.nodes.append(node)
    for key in keys:
        doc.nodes.append(Node(kind="attribute", name=key, parent_id=node.id,
                              data_type="INTEGER", is_pk=True))
    return node


def relation(doc, name, left, right, left_card="0,N", right_card="0,N", roles=("", "")):
    node = Node(kind="relation", name=name)
    doc.nodes.append(node)
    doc.links += [Link(left.id, node.id, source_card=left_card, role=roles[0]),
                  Link(node.id, right.id, target_card=right_card, role=roles[1])]
    return node


def database(doc):
    connection = sqlite3.connect(":memory:", isolation_level=None)
    connection.executescript(generate_sql(doc))
    assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
    return connection


def test_roundtrip_atomic_storage(tmp_path):
    doc = Document(title="Università — esame")
    entity(doc, "Studente")
    target = tmp_path / "schema.erdraw"
    save_document(doc, target)
    assert load_document(target).to_dict() == doc.to_dict()
    previous = target.read_bytes()
    doc.links.append(Link("missing", doc.nodes[0].id))
    with pytest.raises(ValueError, match="inesistente"):
        save_document(doc, target)
    assert target.read_bytes() == previous
    assert list(tmp_path.iterdir()) == [target]


def test_many_to_many_composite_keys_and_relationship_attributes():
    doc = Document()
    left = entity(doc, "Studente", ("facolta", "matricola"))
    right = entity(doc, "Corso")
    rel = relation(doc, "Iscrizione", left, right)
    doc.nodes.append(Node(kind="attribute", name="voto", data_type="INTEGER", parent_id=rel.id))
    db = database(doc)
    db.execute('INSERT INTO "Studente" VALUES (1, 42)')
    db.execute('INSERT INTO "Corso" VALUES (9)')
    db.execute('INSERT INTO "Iscrizione" VALUES (1,42,9,30)')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO "Iscrizione" VALUES (1,42,9,28)')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO "Iscrizione" VALUES (2,42,9,28)')
    assert db.execute('SELECT "voto" FROM "Iscrizione"').fetchone() == (30,)


def test_one_to_many_foreign_key_is_in_at_most_one_participant():
    doc = Document()
    teacher, course = entity(doc, "Docente"), entity(doc, "Corso")
    relation(doc, "Insegna", teacher, course, "0,N", "1,1")
    db = database(doc)
    assert [row[1] for row in db.execute('PRAGMA table_info("Corso")')] == ["id", "Insegna_Docente_id"]
    db.execute('INSERT INTO "Docente" VALUES (1)')
    db.execute('INSERT INTO "Corso" VALUES (4,1)')
    db.execute('INSERT INTO "Corso" VALUES (5,1)')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO "Corso" VALUES (6,NULL)')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO "Corso" VALUES (6,99)')


def test_optional_relationship_attributes_are_conditional():
    doc = Document()
    teacher, course = entity(doc, "Docente"), entity(doc, "Corso")
    rel = relation(doc, "Insegna", teacher, course, "0,N", "0,1")
    doc.nodes.append(Node(kind="attribute", name="inizio", parent_id=rel.id, data_type="DATE", nullable=False))
    db = database(doc)
    db.execute('INSERT INTO "Docente" VALUES (1)')
    db.execute('INSERT INTO "Corso" VALUES (1,NULL,NULL)')
    db.execute('INSERT INTO "Corso" VALUES (2,1,\'2026-11-06\')')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO "Corso" VALUES (3,1,NULL)')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO "Corso" VALUES (4,NULL,\'2026-11-06\')')


def test_optional_composite_foreign_key_cannot_be_half_null():
    doc = Document()
    teacher, course = entity(doc, "Docente", ("sede", "codice")), entity(doc, "Corso")
    relation(doc, "Insegna", teacher, course, "0,N", "0,1")
    db = database(doc)
    db.execute('INSERT INTO "Docente" VALUES (1,2)')
    db.execute('INSERT INTO "Corso" VALUES (1,NULL,NULL)')
    db.execute('INSERT INTO "Corso" VALUES (2,1,2)')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO "Corso" VALUES (3,1,NULL)')


def test_one_to_one_prefers_mandatory_side_and_enforces_unique_fk():
    doc = Document()
    person, passport = entity(doc, "Persona"), entity(doc, "Passaporto")
    relation(doc, "Possiede", person, passport, "0,1", "1,1")
    db = database(doc)
    db.execute('INSERT INTO "Persona" VALUES (7)')
    db.execute('INSERT INTO "Passaporto" VALUES (1,7)')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO "Passaporto" VALUES (2,7)')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO "Passaporto" VALUES (3,NULL)')


def test_reflexive_relationship_uses_explicit_roles():
    doc = Document()
    employee = entity(doc, "Dipendente")
    relation(doc, "Dirige", employee, employee, "0,N", "0,1", ("capo", "subordinato"))
    db = database(doc)
    db.execute('INSERT INTO "Dipendente" VALUES (1,NULL)')
    db.execute('INSERT INTO "Dipendente" VALUES (2,1)')
    assert db.execute('PRAGMA foreign_key_list("Dipendente")').fetchone()[2] == "Dipendente"
    assert "Dirige_capo_id" in generate_sql(doc)


def test_reflexive_many_to_many_uses_two_role_keys():
    doc = Document()
    person = entity(doc, "Persona")
    relation(doc, "Conosce", person, person, roles=("mittente", "destinatario"))
    db = database(doc)
    db.execute('INSERT INTO "Persona" VALUES (1)')
    db.execute('INSERT INTO "Persona" VALUES (2)')
    db.execute('INSERT INTO "Conosce" VALUES (1,2)')
    assert [row[1] for row in db.execute('PRAGMA table_info("Conosce")')] == ["mittente_id", "destinatario_id"]


def test_multivalue_is_a_set_with_owner_fk():
    doc = Document()
    person = entity(doc, "Persona")
    doc.nodes.append(Node(kind="multivalue", name="telefono", parent_id=person.id, data_type="TEXT"))
    db = database(doc)
    db.execute('INSERT INTO "Persona" VALUES (1)')
    db.execute('INSERT INTO "Persona_telefono" VALUES (1,\'123\')')
    db.execute('INSERT INTO "Persona_telefono" VALUES (1,\'456\')')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO "Persona_telefono" VALUES (1,\'123\')')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO "Persona_telefono" VALUES (2,\'123\')')


def test_isa_inherits_composite_key_and_references_supertype():
    doc = Document()
    parent = entity(doc, "Persona", ("paese", "numero"))
    child = Node(kind="entity", name="Studente")
    isa = Node(kind="isa", name="ISA", parent_id=parent.id, isa_total=True)
    doc.nodes += [child, isa, Node(kind="attribute", name="anno", parent_id=child.id, data_type="INTEGER")]
    doc.links += [Link(isa.id, child.id)]
    sql = generate_sql(doc)
    assert "Totalità e disgiunzione non sono imposte" in sql
    db = database(doc)
    db.execute('INSERT INTO "Persona" VALUES (39,1)')
    db.execute('INSERT INTO "Studente" VALUES (39,1,2026)')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO "Studente" VALUES (39,2,2026)')


def test_isa_cycle_is_rejected():
    doc = Document()
    first, second = entity(doc, "A"), entity(doc, "B")
    one, two = Node(kind="isa", name="ISA1", parent_id=first.id), Node(kind="isa", name="ISA2", parent_id=second.id)
    doc.nodes += [one, two]
    doc.links += [Link(one.id, second.id), Link(two.id, first.id)]
    with pytest.raises(SqlExportError, match="ciclo"):
        generate_sql(doc)


def test_derived_attribute_is_not_persisted_as_column():
    doc = Document()
    person = entity(doc, "Persona")
    doc.nodes.append(Node(kind="attribute", name="eta", parent_id=person.id, derived=True))
    db = database(doc)
    assert [row[1] for row in db.execute('PRAGMA table_info("Persona")')] == ["id"]
    assert "derivato Persona.eta escluso" in generate_sql(doc)


def test_quoted_identifiers_cannot_inject_sql():
    doc = Document()
    name = 'user"; DROP TABLE victim; --'
    table = entity(doc, name, ('id"pk',))
    db = database(doc)
    assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone()[0] == name
    escaped = name.replace('"', '""')
    db.execute(f'INSERT INTO "{escaped}" VALUES (1)')
    assert len(doc.attributes(table.id)) == 1


@pytest.mark.parametrize("value", ["INTEGER; DROP TABLE x", "TEXT --", "VARCHAR(0)", "NUMERIC(2,3)", "VARCHAR(999999999)", "OBJECT"])
def test_type_whitelist_rejects_untrusted_sql(value):
    with pytest.raises(ValueError):
        normalize_type(value)


def test_postgresql_preserves_types_and_defers_fk_creation():
    doc = Document()
    left, right = entity(doc, "A"), entity(doc, "B")
    doc.nodes.append(Node(kind="attribute", name="uuid", parent_id=left.id, data_type="UUID"))
    relation(doc, "AB", left, right, "0,N", "0,1")
    sql = generate_sql(doc, "postgresql")
    assert '"uuid" UUID' in sql
    assert "PRAGMA" not in sql
    assert sql.index('CREATE TABLE "B"') < sql.index('ALTER TABLE "B" ADD FOREIGN KEY')


def test_unsupported_ternary_is_explicit():
    doc = Document()
    first, second, third = [entity(doc, name) for name in ("A", "B", "C")]
    rel = relation(doc, "R", first, second)
    doc.links.append(Link(third.id, rel.id))
    with pytest.raises(SqlExportError, match="due partecipazioni"):
        generate_sql(doc)


def test_generated_column_collision_requires_renaming():
    doc = Document()
    first, second = entity(doc, "A"), entity(doc, "B")
    doc.nodes.append(Node(kind="attribute", name="R_A_id", parent_id=second.id))
    relation(doc, "R", first, second, "0,N", "0,1")
    with pytest.raises(SqlExportError, match="collisione"):
        generate_sql(doc)


def test_legacy_format_preserves_structure_and_requires_review():
    data = {"objects": [
        {"type": "entity", "name": "Persona", "x": 100, "y": 100, "w": 120, "h": 60},
        {"type": "attribute", "name": "id", "x": 80, "y": 50, "isPK": True, "parentIdx": 0},
        {"type": "multivalue", "name": "Recapiti", "x": 300, "y": 100, "w": 120, "h": 60},
        {"type": "attribute", "name": "telefono", "x": 400, "y": 40, "isPK": False, "parentIdx": 2},
        {"type": "isa", "label": "Totale, Esclusiva", "x": 160, "y": 160,
         "parentIdx": 0, "endPoint": {"x": 200, "y": 300}},
    ], "links": [{"srcIdx": 0, "tgtIdx": 2}]}
    doc = Document.from_dict(data)
    assert doc.nodes[1].parent_id == doc.nodes[0].id
    assert (doc.nodes[1].x, doc.nodes[1].y) == (80, 50)
    assert doc.nodes[2].parent_id is None
    assert doc.nodes[3].parent_id == doc.nodes[2].id
    assert doc.nodes[4].x == 168
    assert doc.nodes[4].isa_total and doc.nodes[4].isa_disjoint
    assert doc.links[0].source_card == "0,N"
    assert any("importazione web" in issue.message for issue in validate(doc))
    assert Document.from_dict(doc.to_dict()).to_dict() == doc.to_dict()
    with pytest.raises(SqlExportError):
        generate_sql(doc)


@pytest.mark.parametrize("label,total,disjoint", [("(p,d)", False, True), ("(t,d)", True, True),
                                                ("(p,s)", False, False), ("(t,s)", True, False)])
def test_actual_legacy_isa_codes(label, total, disjoint):
    doc = Document.from_dict({"objects": [
        {"type": "entity", "name": "Persona"},
        {"type": "isa", "label": label, "parentIdx": 0}
    ], "links": []})
    assert (doc.nodes[1].isa_total, doc.nodes[1].isa_disjoint) == (total, disjoint)


def test_legacy_sql_preserves_initial_type_and_cardinality_assumptions():
    doc = Document.from_dict({"objects": [
        {"type": "entity", "name": "Studente"},
        {"type": "attribute", "name": "matricola", "isPK": True, "parentIdx": 0},
        {"type": "entity", "name": "Corso"},
        {"type": "attribute", "name": "codice", "isPK": True, "parentIdx": 2},
        {"type": "relation", "name": "Iscrizione"}
    ], "links": [{"srcIdx": 0, "tgtIdx": 4}, {"srcIdx": 4, "tgtIdx": 2}]})
    sql = generate_sql(doc)
    assert sql.startswith("-- IMPORTAZIONE WEB: tipi/cardinalità non presenti nel file originale")
    assert "valori iniziali da revisionare" in sql
    assert "VARCHAR(255)" in sql and "(0,N)" in sql
    db = database(doc)
    assert {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {
        "Studente", "Corso", "Iscrizione"}


def test_monolithic_legacy_isa_endpoint_uses_angle_and_stem_length():
    doc = Document.from_dict({"objects": [
        {"type": "entity", "name": "Persona"},
        {"type": "isa", "label": "(p,d)", "parentIdx": 0,
         "x": 100, "y": 200, "angle": 0, "stemHeight": 80}
    ], "links": []})
    assert (doc.nodes[1].x, doc.nodes[1].y) == pytest.approx((148, 172))


def test_explicit_unique_on_composite_key_member_is_preserved():
    doc = Document()
    node = entity(doc, "A", ("paese", "numero"))
    doc.attributes(node.id)[0].unique = True
    db = database(doc)
    db.execute('INSERT INTO "A" VALUES (1,1)')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO "A" VALUES (1,2)')


def test_subtype_explicit_unique_on_inherited_key_is_preserved():
    doc = Document()
    parent = entity(doc, "Persona", ("paese", "numero"))
    child = Node(kind="entity", name="Studente")
    isa = Node(kind="isa", name="ISA", parent_id=parent.id)
    doc.nodes += [child, isa, Node(kind="attribute", name="paese", parent_id=child.id,
                                   data_type="INTEGER", unique=True)]
    doc.links.append(Link(isa.id, child.id))
    db = database(doc)
    db.execute('INSERT INTO "Persona" VALUES (1,1)')
    db.execute('INSERT INTO "Persona" VALUES (1,2)')
    db.execute('INSERT INTO "Studente" VALUES (1,1)')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO "Studente" VALUES (1,2)')


def test_subtype_cannot_shadow_inherited_pk_with_derived_attribute():
    doc = Document()
    parent = entity(doc, "Persona")
    child = Node(kind="entity", name="Studente")
    isa = Node(kind="isa", name="ISA", parent_id=parent.id)
    doc.nodes += [child, isa, Node(kind="attribute", name="id", parent_id=child.id, derived=True)]
    doc.links.append(Link(isa.id, child.id))
    with pytest.raises(SqlExportError, match="non può sostituire"):
        generate_sql(doc)


def test_reserved_sqlite_table_name_is_rejected_before_export():
    doc = Document()
    entity(doc, "sqlite_private")
    with pytest.raises(SqlExportError, match="riservato"):
        generate_sql(doc)
    assert 'CREATE TABLE "sqlite_private"' in generate_sql(doc, "postgresql")


@pytest.mark.parametrize("bad", [
    {"objects": [{"type": "attribute", "name": "x", "parentIdx": -1}], "links": []},
    {"objects": [{"type": "entity", "name": "x"}], "links": [{"srcIdx": 0, "tgtIdx": 1}]},
    {"objects": [{"type": "entity", "name": "x", "x": "bad"}], "links": []},
    {"objects": [{"type": []}], "links": []},
    {"format": "drawer-desktop", "schema_version": 999, "nodes": [], "links": []},
])
def test_invalid_legacy_and_versions_are_rejected(bad):
    with pytest.raises(ValueError):
        Document.from_dict(bad)


def test_duplicate_ids_dangling_parents_and_cycles_rejected():
    one = Node(name="One")
    two = Node(name="Two", id=one.id)
    with pytest.raises(ValueError, match="duplicati"):
        Document.from_dict(Document(nodes=[one, two]).to_dict())
    two.id = "other"
    one.parent_id, two.parent_id = two.id, one.id
    with pytest.raises(ValueError, match="ciclo"):
        Document.from_dict(Document(nodes=[one, two]).to_dict())
    one.parent_id = "absent"
    with pytest.raises(ValueError, match="inesistente"):
        Document.from_dict(Document(nodes=[one, two]).to_dict())


def test_nonfinite_geometry_and_duplicate_json_keys_rejected(tmp_path):
    raw = Document(nodes=[Node()]).to_dict()
    raw["nodes"][0]["x"] = float("nan")
    with pytest.raises(ValueError):
        Document.from_dict(raw)
    path = tmp_path / "invalid.erdraw"
    path.write_text('{"nodes":[],"nodes":[],"links":[]}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicata"):
        load_document(path)


def test_example_is_valid_and_sql_executes():
    path = Path(__file__).parents[1] / "examples" / "universita.erdraw"
    doc = load_document(path)
    assert not [issue for issue in validate(doc) if issue.severity == "error"]
    db = database(doc)
    names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert names == {"Studente", "Corso", "Docente", "Iscrizione"}


def test_repeatable_entity_attribute_generates_separate_sqlite_table():
    doc = Document()
    owner = entity(doc, "Persona")
    doc.nodes.append(Node(kind="attribute", name="Telefono", parent_id=owner.id,
                          attribute_card="1,N"))
    ddl = generate_sql(doc, "sqlite")
    assert "MINIMO NON IMPOSTO: Persona.Telefono (1,N)" in ddl
    with sqlite3.connect(":memory:") as db:
        db.executescript(ddl)
        db.execute('INSERT INTO "Persona" VALUES (1)')
        db.executemany('INSERT INTO "Persona_Telefono" VALUES (?, ?)', [(1, "123"), (1, "456")])
        assert db.execute('SELECT COUNT(*) FROM "Persona_Telefono"').fetchone()[0] == 2
