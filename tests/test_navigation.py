"""Gesti reali della v1.0.1: sinistro naviga, destro seleziona."""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('XDG_CONFIG_HOME', '/tmp/drawer-test-config')
os.environ.setdefault('XDG_DATA_HOME', '/tmp/drawer-test-data')

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from drawer.history import History
from drawer.model import Document, Node
from drawer.window import MainWindow


@pytest.fixture(scope='module')
def app():
    application = QApplication.instance() or QApplication([])
    yield application
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.fixture
def editor(app):
    entity = Node(name='Persona')
    # Un progetto importato può contenere coordinate non multiple della griglia.
    key = Node(kind='attribute', name='id', x=-30, y=-70,
               parent_id=entity.id, is_pk=True, nullable=False)
    other = Node(name='Azienda', x=400, y=200)
    window = MainWindow(Document(nodes=[entity, key, other]), recovery=False)
    window.show()
    app.processEvents()
    window.view.fit_diagram()
    app.processEvents()
    yield window
    window.saved_signature = History.signature(window.document)
    window.close()
    window.deleteLater()
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def point(editor, index):
    node = editor.document.nodes[index]
    return editor.view.mapFromScene(editor.scene.node_items[node.id].sceneBoundingRect().center())


def drag(editor, button, start, end, modifiers=Qt.NoModifier):
    viewport = editor.view.viewport()
    QTest.mousePress(viewport, button, modifiers, start)
    QTest.mouseMove(viewport, end, delay=15)
    QTest.mouseRelease(viewport, button, modifiers, end)
    QApplication.processEvents()


def test_left_drag_pans_without_selecting_or_changing_document(editor):
    original = editor.document.to_dict()
    start = QPoint(25, 25)
    before = (editor.view.horizontalScrollBar().value(), editor.view.verticalScrollBar().value())
    drag(editor, Qt.LeftButton, start, start + QPoint(75, 45))
    after = (editor.view.horizontalScrollBar().value(), editor.view.verticalScrollBar().value())
    assert after != before
    assert editor.document.to_dict() == original
    assert not editor.scene.selected_ids()
    assert not editor.dirty and not editor.history.can_undo
    assert not editor.view._panning


def test_right_click_selects_and_control_toggles_without_opening_menu(editor, monkeypatch):
    def unexpected_menu(*args):
        pytest.fail('Il semplice clic destro non deve aprire un menu.')
    monkeypatch.setattr(editor.scene, 'show_context_menu', unexpected_menu)
    viewport = editor.view.viewport()
    first, other = editor.document.nodes[0], editor.document.nodes[2]
    QTest.mouseClick(viewport, Qt.RightButton, Qt.NoModifier, point(editor, 0))
    assert editor.scene.selected_ids() == [first.id]
    QTest.mouseClick(viewport, Qt.RightButton, Qt.ControlModifier, point(editor, 2))
    assert set(editor.scene.selected_ids()) == {first.id, other.id}
    QTest.mouseClick(viewport, Qt.RightButton, Qt.ControlModifier, point(editor, 0))
    assert editor.scene.selected_ids() == [other.id]
    assert not editor.dirty


@pytest.mark.parametrize('additive', [False, True])
def test_right_drag_selects_area_without_moving_nodes(editor, additive):
    original = editor.document.to_dict()
    other = editor.document.nodes[2]
    if additive:
        editor.scene.node_items[other.id].setSelected(True)
    start = editor.view.mapFromScene(QPointF(-70, -110))
    end = editor.view.mapFromScene(QPointF(190, 110))
    drag(editor, Qt.RightButton, start, end, Qt.ControlModifier if additive else Qt.NoModifier)
    wanted = {editor.document.nodes[0].id, editor.document.nodes[1].id}
    if additive:
        wanted.add(other.id)
    assert set(editor.scene.selected_ids()) == wanted
    assert editor.document.to_dict() == original
    assert not editor.view._rubber_band.isVisible()
    assert not editor.dirty


def test_right_drag_starting_on_node_never_moves_it(editor):
    original = editor.document.to_dict()
    start = point(editor, 0)
    drag(editor, Qt.RightButton, start, start + QPoint(80, 70))
    assert editor.document.to_dict() == original
    assert editor.document.nodes[0].id in editor.scene.selected_ids()
    assert not editor.history.can_undo


def test_selected_node_moves_with_left_drag_children_and_undo(editor):
    viewport = editor.view.viewport()
    entity, key = editor.document.nodes[:2]
    original = {node.id: (node.x, node.y) for node in (entity, key)}
    start = point(editor, 0)
    QTest.mouseClick(viewport, Qt.RightButton, Qt.NoModifier, start)
    end = start + editor.view.mapFromScene(QPointF(80, 40)) - editor.view.mapFromScene(QPointF())
    drag(editor, Qt.LeftButton, start, end)
    assert entity.x != original[entity.id][0]
    delta = (entity.x-original[entity.id][0], entity.y-original[entity.id][1])
    assert (key.x, key.y) == (original[key.id][0]+delta[0], original[key.id][1]+delta[1])
    assert editor.history.can_undo
    editor.undo()
    for identifier, coords in original.items():
        node = editor.document.node(identifier)
        assert (node.x, node.y) == coords


def test_creation_mode_keeps_left_click_and_right_does_not_create(editor):
    created = []
    editor.scene.create_requested.disconnect()
    editor.scene.create_requested.connect(lambda *args: created.append(args))
    editor.set_mode('entity')
    viewport = editor.view.viewport()
    QTest.mouseClick(viewport, Qt.RightButton, Qt.NoModifier, QPoint(25, 25))
    assert not created
    QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier, QPoint(25, 25))
    assert len(created) == 1 and created[0][0] == 'entity'


def test_double_left_click_edits_unselected_node(editor):
    editor.scene.edit_requested.disconnect()
    requested = []
    editor.scene.edit_requested.connect(requested.append)
    QTest.mouseDClick(editor.view.viewport(), Qt.LeftButton, Qt.NoModifier, point(editor, 0))
    assert requested == [editor.document.nodes[0].id]
    assert not editor.view._panning


def test_shift_right_and_keyboard_menu_remain_available(editor, monkeypatch):
    calls = []
    monkeypatch.setattr(editor.scene, 'show_context_menu', lambda *args: calls.append(args))
    QTest.mouseClick(editor.view.viewport(), Qt.RightButton, Qt.ShiftModifier, point(editor, 0))
    assert len(calls) == 1
    editor.scene.node_items[editor.document.nodes[0].id].setSelected(True)
    QTest.keyClick(editor.view, Qt.Key_Menu)
    QTest.keyClick(editor.view, Qt.Key_F10, Qt.ShiftModifier)
    assert len(calls) == 3


def test_escape_cancels_marquee_restoring_previous_selection(editor):
    first = editor.document.nodes[0]
    editor.scene.node_items[first.id].setSelected(True)
    viewport = editor.view.viewport()
    start = editor.view.mapFromScene(QPointF(370, 170))
    end = editor.view.mapFromScene(QPointF(590, 300))
    QTest.mousePress(viewport, Qt.RightButton, Qt.NoModifier, start)
    QTest.mouseMove(viewport, end, delay=15)
    assert editor.view._right_dragging
    QTest.keyClick(editor.view, Qt.Key_Escape)
    QTest.mouseRelease(viewport, Qt.RightButton, Qt.NoModifier, end)
    assert editor.scene.selected_ids() == [first.id]
    assert editor.view._right_origin is None
    assert not editor.view._rubber_band.isVisible()


def test_focus_loss_clears_pan_and_space_state(editor):
    QTest.keyPress(editor.view, Qt.Key_Space)
    QTest.mousePress(editor.view.viewport(), Qt.LeftButton, Qt.NoModifier, QPoint(25, 25))
    assert editor.view._panning and editor.view._space
    QApplication.sendEvent(editor.view, QEvent(QEvent.WindowDeactivate))
    assert not editor.view._panning and not editor.view._space
    QTest.mouseRelease(editor.view.viewport(), Qt.LeftButton, Qt.NoModifier, QPoint(25, 25))


@pytest.mark.parametrize('gesture', ['middle', 'space'])
def test_secondary_pan_gestures_work_even_over_selected_nodes(editor, gesture):
    first = editor.document.nodes[0]
    editor.scene.node_items[first.id].setSelected(True)
    original = editor.document.to_dict()
    start = point(editor, 0)
    before = editor.view.horizontalScrollBar().value()
    if gesture == 'space':
        QTest.keyPress(editor.view, Qt.Key_Space)
    drag(editor, Qt.MiddleButton if gesture == 'middle' else Qt.LeftButton,
         start, start+QPoint(60, 30))
    if gesture == 'space':
        QTest.keyRelease(editor.view, Qt.Key_Space)
    assert editor.view.horizontalScrollBar().value() != before
    assert editor.document.to_dict() == original
    assert editor.scene.selected_ids() == [first.id]
    assert not editor.history.can_undo


def test_focus_loss_cancels_marquee_and_preserves_previous_selection(editor):
    first = editor.document.nodes[0]
    editor.scene.node_items[first.id].setSelected(True)
    viewport = editor.view.viewport()
    start = editor.view.mapFromScene(QPointF(370, 170))
    end = editor.view.mapFromScene(QPointF(590, 300))
    QTest.mousePress(viewport, Qt.RightButton, Qt.NoModifier, start)
    QTest.mouseMove(viewport, end, delay=15)
    QApplication.sendEvent(editor.view, QEvent(QEvent.WindowDeactivate))
    QTest.mouseRelease(viewport, Qt.RightButton, Qt.NoModifier, end)
    assert editor.scene.selected_ids() == [first.id]
    assert editor.view._right_origin is None
    assert not editor.view._rubber_band.isVisible()
