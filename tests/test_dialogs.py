"""Verify dialog transactions and the constraints students edit most often."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QLineEdit, QMessageBox, QPlainTextEdit, QTextEdit,
)

from drawer.dialogs import (
    HelpDialog, SqlPreviewDialog, create_relationship, edit_link, edit_node,
)
from drawer.model import Document, Link, Node


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance
    # Modal helpers queue deletion after exec; the simulated exec above does not
    # run an event loop, so finish ownership cleanup before QApplication exits.
    for widget in QApplication.topLevelWidgets():
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _accept(dialog):
    buttons = dialog.findChild(QDialogButtonBox)
    buttons.button(QDialogButtonBox.StandardButton.Ok).click()
    return dialog.result()


def test_cancel_node_leaves_original_unchanged(app, monkeypatch):
    node = Node(name="Prima")

    def cancel(dialog):
        dialog.findChild(QLineEdit, "nodeName").setText("Non applicato")
        dialog.reject()
        return dialog.result()

    monkeypatch.setattr(QDialog, "exec", cancel)
    assert edit_node(None, node) is None
    assert node.name == "Prima"


def test_accept_node_returns_copy_with_primary_key_constraints(app, monkeypatch):
    node = Node(kind="attribute", name="id", nullable=True, derived=True)

    def accept(dialog):
        dialog.findChild(QLineEdit, "nodeName").setText("matricola")
        primary = dialog.findChild(QCheckBox, "primaryKey")
        primary.setChecked(True)
        assert not dialog.findChild(QCheckBox, "nullable").isEnabled()
        assert not dialog.findChild(QCheckBox, "nullable").isChecked()
        assert not dialog.findChild(QCheckBox, "derived").isChecked()
        return _accept(dialog)

    monkeypatch.setattr(QDialog, "exec", accept)
    result = edit_node(None, node)
    assert result is not node
    assert result.name == "matricola"
    assert result.is_pk and not result.nullable and not result.derived
    assert node.name == "id"
    assert node.nullable and node.derived and not node.is_pk


def test_multivalue_cannot_be_primary_key(app, monkeypatch):
    node = Node(kind="multivalue", name="telefono", is_pk=True)

    def accept(dialog):
        primary = dialog.findChild(QCheckBox, "primaryKey")
        assert not primary.isEnabled()
        assert not primary.isChecked()
        return _accept(dialog)

    monkeypatch.setattr(QDialog, "exec", accept)
    result = edit_node(None, node)
    assert not result.is_pk
    assert node.is_pk


def test_link_edit_preserves_original(app, monkeypatch):
    entity = Node(name="Studente")
    relation = Node(kind="relation", name="Iscrizione")
    link = Link(entity.id, relation.id)
    doc = Document(nodes=[entity, relation], links=[link])

    def accept(dialog):
        cards = dialog.findChildren(QComboBox)
        assert len(cards) == 3
        cards[0].setCurrentText("1,1")
        cards[1].setCurrentText("Basso")
        assert cards[0].isEnabled()
        dialog.findChild(QLineEdit, "linkRole").setText("studente")
        return _accept(dialog)

    monkeypatch.setattr(QDialog, "exec", accept)
    result = edit_link(None, link, doc)
    assert result.source_card == "1,1"
    assert result.source_port == "bottom" and link.source_port is None
    assert result.role == "studente"
    assert link.source_card == "0,N" and link.role == ""


def test_recursive_relationship_requires_distinct_roles(app, monkeypatch):
    entity = Node(name="Dipendente", x=200, y=240)
    doc = Document(nodes=[entity])
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: errors.append(args[2]))

    def accept(dialog):
        dialog.findChild(QLineEdit, "relationName").setText("Coordina")
        # First attempt must stay open and explain the missing roles.
        _accept(dialog)
        assert dialog.result() == QDialog.DialogCode.Rejected
        assert errors
        dialog.findChild(QLineEdit, "role0").setText("responsabile")
        dialog.findChild(QLineEdit, "role1").setText("subordinato")
        dialog.findChild(QComboBox, "card0").setCurrentText("0,N")
        dialog.findChild(QComboBox, "card1").setCurrentText("0,1")
        return _accept(dialog)

    monkeypatch.setattr(QDialog, "exec", accept)
    relation, links = create_relationship(None, doc)
    assert relation.kind == "relation" and relation.name == "Coordina"
    assert relation.y < entity.y
    assert len(links) == 2 and all(link.source == entity.id for link in links)
    assert {link.role for link in links} == {"responsabile", "subordinato"}
    assert [link.source_card for link in links] == ["0,N", "0,1"]
    assert doc.nodes == [entity] and not doc.links


def test_sql_and_help_dialogs_construct_and_sql_saves(app, monkeypatch, tmp_path):
    path = tmp_path / "schema.sql"

    def export_file(extension, writer, parent):
        assert extension == "sql" and isinstance(parent, SqlPreviewDialog)
        writer(path)
        return path

    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    preview = SqlPreviewDialog(None, 'CREATE TABLE "E" ("id" INTEGER);', "sqlite", export_file)
    preview.save_sql()
    assert path.read_text(encoding="utf-8") == preview.sql
    help_dialog = HelpDialog(None)
    assert help_dialog.windowTitle() == "Guida a DrawER Studio"
    preview.close()
    help_dialog.close()


def test_orphan_multivalue_can_receive_owner(app, monkeypatch):
    entity = Node(name="Persona")
    orphan = Node(kind="multivalue", name="telefono")
    doc = Document(nodes=[entity, orphan])
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: errors.append(args[2]))

    def accept(dialog):
        owner = dialog.findChild(QComboBox, "owner")
        assert owner.currentData() is None
        _accept(dialog)
        assert errors and dialog.result() == QDialog.DialogCode.Rejected
        owner.setCurrentIndex(owner.findData(entity.id))
        return _accept(dialog)

    monkeypatch.setattr(QDialog, "exec", accept)
    result = edit_node(None, orphan, doc)
    assert result.parent_id == entity.id
    assert orphan.parent_id is None


def test_text_note_accepts_multiline_and_roundtrips(app, monkeypatch):
    note = Node(kind="text", name="Prima")

    def accept(dialog):
        editor = dialog.findChild(QTextEdit, "nodeName")
        assert editor is not None
        editor.setPlainText("Regole del dominio\nOgni corso ha un docente.\nVerificare le eccezioni.")
        return _accept(dialog)

    monkeypatch.setattr(QDialog, "exec", accept)
    result = edit_node(None, note)
    doc = Document(nodes=[result])
    restored = Document.from_dict(doc.to_dict())
    assert restored.nodes[0].name == result.name
    assert result.name.count("\n") == 2
    assert note.name == "Prima"


def test_attribute_cardinality_is_opt_in(app, monkeypatch):
    node = Node(kind="attribute", name="Telefono")

    def accept(dialog):
        enabled = dialog.findChild(QCheckBox, "attributeCardEnabled")
        choices = dialog.findChild(QComboBox, "attributeCard")
        assert not enabled.isChecked() and not choices.isEnabled()
        enabled.setChecked(True)
        choices.setCurrentText("1,N")
        assert choices.isEnabled() and not dialog.findChild(QCheckBox, "primaryKey").isEnabled()
        return _accept(dialog)

    monkeypatch.setattr(QDialog, "exec", accept)
    assert edit_node(None, node).attribute_card == "1,N"
    assert node.attribute_card is None


def test_note_background_picker_preserves_color_when_transparent(app, monkeypatch):
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog, QPushButton

    node = Node(kind="text", name="Nota")
    monkeypatch.setattr(QColorDialog, "getColor", lambda *args: QColor("#2d7ab0"))

    def accept(dialog):
        color = dialog.findChild(QPushButton, "noteBackground")
        color.click()
        assert color.text() == "#2d7ab0"
        dialog.findChild(QCheckBox, "noteTransparent").setChecked(True)
        assert not color.isEnabled()
        return _accept(dialog)

    monkeypatch.setattr(QDialog, "exec", accept)
    result = edit_node(None, node)
    assert result.note_transparent and result.note_background == "#2d7ab0"
    assert not node.note_transparent and node.note_background is None
