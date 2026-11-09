"""Offscreen integration checks for editor transactions and real rendered output."""
import os
from xml.etree import ElementTree

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CONFIG_HOME", "/tmp/drawer-test-config")
os.environ.setdefault("XDG_DATA_HOME", "/tmp/drawer-test-data")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QFont, QFontMetricsF, QImage, QPalette
from PySide6.QtPdf import QPdfDocument
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from drawer.exports import export_diagram
from drawer.history import History
from drawer.model import Document, Link, Node
from drawer.scene import DiagramScene
from drawer.window import MainWindow


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def diagram():
    parent = Node(name="Studente", x=100, y=180)
    key = Node(kind="attribute", name="matricola", parent_id=parent.id,
               x=120, y=80, is_pk=True, nullable=False, data_type="INTEGER")
    multi = Node(kind="multivalue", name="telefono", parent_id=parent.id,
                 x=340, y=100, width=150, height=60)
    nested = Node(kind="attribute", name="prefisso", parent_id=multi.id,
                  x=400, y=20)
    isa = Node(kind="isa", name="ISA", parent_id=parent.id,
               x=140, y=340, width=70, height=48)
    other = Node(name="Corso", x=620, y=180)
    relation = Node(kind="relation", name="Iscrizione", x=380, y=260,
                    width=140, height=84)
    link = Link(parent.id, relation.id, source_card="1,N", role="studente")
    second = Link(other.id, relation.id, source_card="0,N", role="corso")
    return Document("Test universitario", [parent, key, multi, nested, isa, other, relation], [link, second])


@pytest.fixture
def window(app):
    editor = MainWindow(diagram(), recovery=False)
    yield editor
    # Never invoke a save dialog in test cleanup, including after assertion failure.
    editor.saved_signature = History.signature(editor.document)
    editor.close()
    editor.deleteLater()
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_mainwindow_starts_with_coherent_inspector_modes_and_palette(window, app):
    window.show()
    app.processEvents()
    assert window.windowTitle() == 'DrawER Studio'
    assert "Test universitario" in window.canvas_title.text()
    assert "2 entità" in window.count_label.text()
    assert not window.dirty
    assert not window.actions["undo"].isEnabled()
    assert not window.actions["redo"].isEnabled()
    parent = window.document.nodes[0]
    window.scene.node_items[parent.id].setSelected(True)
    assert window.inspector_name.text() == "Studente"
    assert window.add_attr_button.isEnabled()
    window.set_mode("connect")
    assert window.scene.mode == "connect"
    assert window.mode_buttons["connect"].isChecked()
    window.set_mode("select")
    window.dark = False
    window.apply_theme()
    light = app.palette().color(QPalette.ColorRole.Window).lightness()
    window.toggle_theme()
    dark = app.palette().color(QPalette.ColorRole.Window).lightness()
    assert dark < light
    assert window.scene.dark and window.actions["theme"].isChecked()
    assert app.palette().color(QPalette.ColorRole.Text).lightness() > dark


def test_drag_moves_descendants_in_one_undoable_transaction(window, app):
    parent = window.document.nodes[0]
    descendants = [n for n in window.document.nodes if n.parent_id in
                   {parent.id, window.document.nodes[2].id}]
    original = {n.id: (n.x, n.y) for n in [parent] + descendants}
    item = window.scene.node_items[parent.id]
    item.setSelected(True)
    item.setPos(item.pos() + QPointF(80, 40))
    window.scene.changed_by_user.emit()
    for identifier, (x, y) in original.items():
        node = window.document.node(identifier)
        assert (node.x, node.y) == (x + 80, y + 40)
    assert window.history.can_undo and len(window.history.states) == 2
    window.undo()
    for identifier, position in original.items():
        node = window.document.node(identifier)
        assert (node.x, node.y) == position
    window.redo()
    assert window.document.node(parent.id).x == original[parent.id][0] + 80


def test_actual_mouse_drag_updates_document_and_history(window, app):
    window.show()
    app.processEvents()
    window.view.fit_diagram()
    app.processEvents()
    parent = window.document.nodes[0]
    item = window.scene.node_items[parent.id]
    initial = QPointF(parent.x, parent.y)
    start = window.view.mapFromScene(item.sceneBoundingRect().center())
    end = start + window.view.mapFromScene(QPointF(80, 40)) - window.view.mapFromScene(QPointF(0, 0))
    viewport = window.view.viewport()
    QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, start)
    QTest.mouseMove(viewport, end, delay=15)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, end)
    app.processEvents()
    assert QPointF(parent.x, parent.y) != initial
    assert window.history.can_undo
    window.undo()
    restored = window.document.node(parent.id)
    assert (restored.x, restored.y) == (initial.x(), initial.y())


def test_delete_cascades_transitively_and_undo_restores_links(window):
    original = window.document.to_dict()
    parent = window.document.nodes[0]
    window.scene.node_items[parent.id].setSelected(True)
    window.delete_selection()
    remaining = {n.id for n in window.document.nodes}
    assert remaining == {original["nodes"][5]["id"], original["nodes"][6]["id"]}
    assert len(window.document.links) == 1
    assert all(n.parent_id is None or n.parent_id in remaining for n in window.document.nodes)
    window.undo()
    assert window.document.to_dict() == original
    assert len(window.scene.edge_items) == len(original["links"]) + 4


def test_selected_link_delete_preserves_nodes_and_undo_restores_it(window):
    link = window.document.links[0]
    nodes = [n.id for n in window.document.nodes]
    window.scene.find_item(link.id).setSelected(True)
    assert window.scene.selected_ids() == [link.id]
    window.delete_selection()
    assert [n.id for n in window.document.nodes] == nodes
    assert link.id not in {l.id for l in window.document.links}
    window.undo()
    assert link.id in {l.id for l in window.document.links}


def test_copy_paste_remaps_internal_links_and_descendant_references(window):
    original_ids = {n.id for n in window.document.nodes}
    original_link_ids = {l.id for l in window.document.links}
    window.select_all()
    window.copy_selection()
    window.paste_selection()
    copies = [n for n in window.document.nodes if n.id not in original_ids]
    copy_ids = {n.id for n in copies}
    links = [l for l in window.document.links if l.id not in original_link_ids]
    assert len(copies) == len(original_ids)
    assert len(links) == len(original_link_ids)
    assert all(n.parent_id is None or n.parent_id in copy_ids for n in copies)
    assert all(l.source in copy_ids and l.target in copy_ids for l in links)
    assert set(window.scene.selected_ids()) == copy_ids
    # A second paste must receive a third, disjoint set of stable IDs.
    window.paste_selection()
    assert len({n.id for n in window.document.nodes}) == 3 * len(original_ids)
    assert len({l.id for l in window.document.links}) == 3 * len(original_link_ids)
    window.undo()
    assert len(window.document.nodes) == 2 * len(original_ids)


def test_history_branch_discards_redo_and_ignores_unchanged_states():
    doc = Document(nodes=[Node(name="A")])
    history = History(doc, limit=3)
    assert not history.push(doc)
    doc.nodes[0].name = "B"
    assert history.push(doc)
    doc.nodes[0].name = "C"
    history.push(doc)
    restored = history.undo()
    assert restored.nodes[0].name == "B" and history.can_redo
    restored.nodes[0].name = "D"
    history.push(restored)
    assert not history.can_redo
    assert history.undo().nodes[0].name == "B"
    assert history.undo().nodes[0].name == "A"


def _has_diagram_pixels(image):
    assert not image.isNull()
    # Export backgrounds are uniform. Sampling across the whole diagram must
    # find substantial different ink, so a file containing only a page fails.
    background = image.pixelColor(0, 0).rgb()
    changed = sum(image.pixelColor(x, y).rgb() != background
                  for y in range(0, image.height(), 3)
                  for x in range(0, image.width(), 3))
    return changed > 100


@pytest.mark.parametrize("kind", ["png", "svg", "pdf"])
def test_export_contains_diagram_and_preserves_selection(window, tmp_path, kind):
    parent = window.document.nodes[0]
    window.scene.node_items[parent.id].setSelected(True)
    selected = window.scene.selected_ids()
    path = tmp_path / ("diagramma." + kind)
    export_diagram(window.scene, path, kind)
    assert path.stat().st_size > 1000
    assert window.scene.selected_ids() == selected
    assert not window.scene.exporting
    if kind == "png":
        image = QImage(str(path))
        bounds = window.scene.content_rect()
        assert image.width() < bounds.width()*2
        assert image.height() < bounds.height()*2
    elif kind == "svg":
        root = ElementTree.parse(path).getroot()
        assert root.tag.endswith("svg")
        assert "Studente" in path.read_text(encoding="utf-8")
        renderer = QSvgRenderer(str(path))
        assert renderer.isValid()
        image = QImage(renderer.defaultSize(), QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
    else:
        pdf = QPdfDocument()
        assert pdf.load(str(path)) == QPdfDocument.Error.None_
        assert pdf.pageCount() == 1
        image = pdf.render(0, QSize(1200, 800))
        pdf.close()
    assert _has_diagram_pixels(image)


def test_export_failure_restores_selection_and_normal_rendering(window, tmp_path):
    parent = window.document.nodes[0]
    window.scene.node_items[parent.id].setSelected(True)
    with pytest.raises(ValueError, match="sconosciuto"):
        export_diagram(window.scene, tmp_path / "bad.xyz", "xyz")
    assert not window.scene.exporting
    assert window.scene.selected_ids() == [parent.id]


def test_isa_label_is_inside_reported_graphics_bounds(app):
    parent=Node(name='Persona',x=0,y=0)
    isa = Node(kind="isa", name="ISA", width=70, height=48,
               x=45,y=180,parent_id=parent.id,isa_total=True, isa_disjoint=False)
    scene = DiagramScene(Document(nodes=[parent,isa]))
    stem=next(edge for edge in scene.edge_items if edge.child is isa)
    assert [label.text() for label in stem.labels]==['(t,s)']
    assert scene.content_rect().contains(stem.labels[0].sceneBoundingRect())
    assert stem._triangle[0] == stem.points[0]


def test_long_primary_key_name_has_room_for_full_bold_text(app):
    key = Node(kind="attribute", name="identificatore_internazionale_dello_studente",
               is_pk=True)
    scene = DiagramScene(Document(nodes=[key]))
    item = scene.node_items[key.id]
    font = QFont("Sans Serif", 10)
    font.setBold(True)
    font.setUnderline(True)
    width = QFontMetricsF(font).horizontalAdvance(key.name)
    # The attribute label begins 14 scene units to the right of its circle.
    assert item.boundingRect().right() >= width + 14
