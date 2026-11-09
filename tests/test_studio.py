"""Flussi reali del foglio Studio: porte, pieghe, aggregati, ISA e clipboard."""
import copy
import os
import sqlite3

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('XDG_CONFIG_HOME','/tmp/drawer-test-config')
os.environ.setdefault('XDG_DATA_HOME','/tmp/drawer-test-data')

import pytest
from PySide6.QtCore import Qt,QPointF,QCoreApplication,QEvent,QSettings
from PySide6.QtGui import QColor,QImage
from PySide6.QtWidgets import QApplication,QDialog,QDialogButtonBox,QComboBox,QMessageBox,QFileDialog
from PySide6.QtTest import QTest

from drawer import __version__
from drawer.model import Document,Node,Link,PORTS
from drawer.window import MainWindow
from drawer.scene import DiagramScene
from drawer.geometry import port_point,adapt_manual,serialized
from drawer.history import History
from drawer.storage import save_document,load_document
from drawer.sql import generate_sql
from drawer.dialogs import edit_node
from drawer.exports import export_diagram


@pytest.fixture(scope='module')
def app():
    instance=QApplication.instance() or QApplication([])
    yield instance
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


@pytest.fixture
def editor(app,monkeypatch):
    entity=Node(name='Persona',x=0,y=0)
    relation=Node(kind='relation',name='Possiede',x=360,y=0,width=140,height=80)
    link=Link(entity.id,relation.id)
    window=MainWindow(Document(nodes=[entity,relation],links=[link]),recovery=False)
    monkeypatch.setattr('drawer.window.edit_link',lambda parent,edge,doc:edge)
    window.show();app.processEvents();window.view.fit_diagram();app.processEvents()
    yield window
    window.saved_signature=History.signature(window.document)
    window.close();window.deleteLater();app.processEvents()
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


def drag(editor,start,end):
    view=editor.view
    a,b=view.mapFromScene(start),view.mapFromScene(end)
    QTest.mousePress(view.viewport(),Qt.LeftButton,Qt.NoModifier,a)
    QTest.mouseMove(view.viewport(),b,delay=20)
    QTest.mouseRelease(view.viewport(),Qt.LeftButton,Qt.NoModifier,b)
    QApplication.processEvents()


def test_left_click_selects_node_and_link(editor):
    node=editor.document.nodes[0]
    QTest.mouseClick(editor.view.viewport(),Qt.LeftButton,Qt.NoModifier,
        editor.view.mapFromScene(editor.scene.node_items[node.id].sceneBoundingRect().center()))
    assert editor.scene.selected_ids()==[node.id] and not editor.dirty
    edge=editor.scene.edge_items[0]
    QTest.mouseClick(editor.view.viewport(),Qt.LeftButton,Qt.NoModifier,
        editor.view.mapFromScene(edge.path().pointAtPercent(.5)))
    assert editor.scene.selected_ids()==[editor.document.links[0].id]
    assert any(handle.isVisible() for handle in edge.handles)
    assert not editor.dirty


@pytest.mark.parametrize('end',['source','target'])
@pytest.mark.parametrize('side',PORTS)
def test_drag_endpoint_uses_exact_midpoint_or_diamond_vertex(editor,tmp_path,end,side):
    edge=editor.scene.edge_items[0];edge.setSelected(True)
    item=edge.source_item if end=='source' else edge.target_item
    destination=port_point(item.mapRectToScene(item.body_rect()),side)
    handle=next(handle for handle in edge.handles if handle.kind==end)
    previous = None
    if handle.scenePos() == destination:
        previous = PORTS[(PORTS.index(side) + 2) % 4]
        edge.set_port(end, previous)
        editor.commit()
    drag(editor,handle.scenePos(),destination)
    assert getattr(editor.document.links[0],end+'_port')==side
    assert (edge.points[0] if end=='source' else edge.points[-1])==destination
    for a,b in zip(edge.points,edge.points[1:]):
        assert abs(a.x()-b.x())<.01 or abs(a.y()-b.y())<.01
    save_document(editor.document,tmp_path/'ports.erdraw')
    assert getattr(load_document(tmp_path/'ports.erdraw').links[0],end+'_port')==side
    editor.undo()
    assert getattr(editor.document.links[0],end+'_port') == previous


def test_bend_drag_keeps_endpoints_and_is_persistent_undoable(editor,tmp_path):
    edge=editor.scene.edge_items[0];edge.setSelected(True)
    first,last=QPointF(edge.points[0]),QPointF(edge.points[-1])
    handle=next(handle for handle in edge.handles if handle.kind=='segment')
    drag(editor,handle.scenePos(),handle.scenePos()+QPointF(0,-100))
    assert edge.points[0]==first and edge.points[-1]==last
    assert min(point.y() for point in edge.points)<-20
    for a,b in zip(edge.points,edge.points[1:]):
        assert abs(a.x()-b.x())<.01 or abs(a.y()-b.y())<.01
    geometry=copy.deepcopy(editor.document.links[0].route_points)
    save_document(editor.document,tmp_path/'bends.erdraw')
    assert load_document(tmp_path/'bends.erdraw').links[0].route_points==geometry
    editor.undo();assert not editor.document.links[0].route_points
    editor.redo();assert editor.document.links[0].route_points==geometry


def test_center_alignment_removes_step_even_with_old_different_heights(editor):
    a,b=editor.document.nodes
    a.height,b.height=76,84
    editor.scene.rebuild()
    for item in editor.scene.node_items.values():item.setSelected(True)
    editor.align('centery')
    edge=editor.scene.edge_items[0]
    assert len(edge.points)==2
    assert edge.points[0].y()==edge.points[-1].y()
    assert edge.points[0].y()==a.y+a.height/2==b.y+b.height/2


def test_visual_arrow_creates_pinned_connection_without_connect_tool(editor):
    editor.document.links.clear();editor.commit(True)
    src,tgt=editor.document.nodes
    source=editor.scene.node_items[src.id]
    arrow=next(arrow for arrow in source.port_arrows if arrow.side=='right')
    QTest.mouseMove(editor.view.viewport(), editor.view.mapFromScene(source.sceneBoundingRect().center()))
    assert arrow.isVisible()
    target=editor.scene.node_items[tgt.id]
    drag(editor,arrow.scenePos(),port_point(target.mapRectToScene(target.body_rect()),'left'))
    assert editor.scene.mode=='select'
    assert len(editor.document.links)==1
    assert editor.document.links[0].source_port=='right'
    assert editor.document.links[0].target_port=='left'


@pytest.mark.parametrize('total,disjoint,code',[(True,False,'(t,s)'),(True,True,'(t,d)'),
    (False,False,'(p,s)'),(False,True,'(p,d)')])
def test_isa_points_at_parent_and_uses_initials(app,total,disjoint,code):
    parent=Node(name='Persona')
    isa=Node(kind='isa',name='ISA',parent_id=parent.id,x=70,y=180,width=20,height=20,
             isa_total=total,isa_disjoint=disjoint)
    child=Node(name='Studente',x=0,y=320)
    scene=DiagramScene(Document(nodes=[parent,isa,child],links=[Link(isa.id,child.id)]))
    stem=next(edge for edge in scene.edge_items if edge.child is isa)
    tip=stem._triangle[0]
    assert tip==QPointF(parent.x+parent.width/2,parent.y+parent.height)
    assert all(point.y()>tip.y() for point in stem._triangle[1:])
    assert [label.text() for label in stem.labels]==[code]
    branch=next(edge for edge in scene.edge_items if edge.link)
    assert not branch.labels and not branch._triangle


@pytest.mark.parametrize('index,flags',[(0,(True,False)),(1,(True,True)),(2,(False,False)),(3,(False,True))])
def test_hierarchy_dialog_offers_four_types(app,monkeypatch,index,flags):
    node=Node(kind='isa',name='ISA')
    def accept(dialog):
        combo=dialog.findChild(QComboBox,'isaType')
        assert combo.count()==4
        combo.setCurrentIndex(index)
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
        return dialog.result()
    monkeypatch.setattr(QDialog,'exec',accept)
    result=edit_node(None,node)
    assert (result.isa_total,result.isa_disjoint)==flags


def test_attribute_can_be_created_on_multivalue_and_sql_contains_components(editor,monkeypatch):
    entity=Node(name='Persona')
    key=Node(kind='attribute',name='id',is_pk=True,nullable=False,data_type='INTEGER',parent_id=entity.id)
    multi=Node(kind='multivalue',name='Recapiti',parent_id=entity.id,x=240)
    editor.replace_document(Document(nodes=[entity,key,multi]))
    monkeypatch.setattr('drawer.window.edit_node',lambda parent,node,doc:node)
    editor.create_object('attribute',QPointF(300,100),multi.id)
    component=editor.document.nodes[-1]
    component.name='numero';component.data_type='TEXT'
    assert component.parent_id==multi.id
    sql=generate_sql(editor.document)
    connection=sqlite3.connect(':memory:')
    try:
        connection.executescript(sql)
        names={row[1] for row in connection.execute('PRAGMA table_info("Persona_Recapiti")')}
        assert {'Persona_id','_indice','numero'}<=names
        assert 'Recapiti' not in names
        connection.execute('INSERT INTO Persona(id) VALUES (1)')
        connection.execute('INSERT INTO Persona_Recapiti(Persona_id,_indice,numero) VALUES (1,0,?)',('123',))
        connection.commit()
    finally:connection.close()


def test_cut_paste_keeps_names_children_and_external_links(editor):
    node=editor.document.nodes[0]
    key=Node(kind='attribute',name='id',parent_id=node.id,x=0,y=-100)
    editor.document.nodes.append(key);editor.commit(True)
    editor.scene.node_items[node.id].setSelected(True)
    editor.actions['cut'].trigger()
    assert editor.document.node(node.id) is None and not editor.document.links
    editor.actions['paste'].trigger()
    pasted=next(n for n in editor.document.nodes if n.kind=='entity')
    assert pasted.name=='Persona'
    assert editor.document.attributes(pasted.id)[0].name=='id'
    assert len(editor.document.links)==1 and editor.document.links[0].source==pasted.id
    editor.undo();assert not any(n.kind=='entity' for n in editor.document.nodes)
    editor.undo();assert editor.document.node(node.id) is not None and len(editor.document.links)==1


def test_selected_connection_can_be_cut_and_pasted(editor):
    edge=editor.scene.edge_items[0];edge.setSelected(True)
    editor.cut_selection();assert not editor.document.links
    editor.paste_selection();assert len(editor.document.links)==1
    assert len(editor.document.nodes)==2


def test_brand_only_in_title_and_version_in_about(editor,monkeypatch):
    assert editor.windowTitle()=='DrawER Studio'
    messages=[]
    monkeypatch.setattr(QMessageBox,'about',lambda *args:messages.append(args))
    editor.actions['about'].trigger()
    assert __version__ in messages[0][2]
    assert editor.actions['cut'].shortcut().toString()=='Ctrl+X'


def test_visual_controls_do_not_leak_into_exports(editor,tmp_path):
    export_diagram(editor.scene,tmp_path/'plain.png','png')
    editor.scene.edge_items[0].setSelected(True)
    export_diagram(editor.scene,tmp_path/'selected.png','png')
    assert QImage(str(tmp_path/'plain.png'))==QImage(str(tmp_path/'selected.png'))


def test_ctrl_x_keyboard_cuts_selected_node_and_undo_restores(editor):
    node=editor.document.nodes[0]
    item=editor.scene.node_items[node.id]
    QTest.mouseClick(editor.view.viewport(),Qt.LeftButton,Qt.NoModifier,
        editor.view.mapFromScene(item.sceneBoundingRect().center()))
    editor.view.setFocus()
    QTest.keyClick(editor.view,Qt.Key_X,Qt.ControlModifier)
    assert editor.document.node(node.id) is None
    QTest.keyClick(editor.view,Qt.Key_Z,Qt.ControlModifier)
    assert editor.document.node(node.id) is not None


def test_moving_node_adapts_manual_route_and_undo_keeps_exact_geometry(editor,tmp_path):
    edge=editor.scene.edge_items[0];edge.setSelected(True)
    handle=next(h for h in edge.handles if h.kind=='segment')
    drag(editor,handle.scenePos(),handle.scenePos()+QPointF(0,-80))
    original=editor.document.to_dict()
    source=edge.source_item
    source.setPos(source.pos()+QPointF(40,80))
    editor.commit()
    assert edge.points[0]==port_point(source.mapRectToScene(source.body_rect()),edge.source_port)
    save_document(editor.document,tmp_path/'moved.erdraw')
    moved=copy.deepcopy(editor.document.links[0].route_points)
    assert load_document(tmp_path/'moved.erdraw').links[0].route_points==moved
    editor.undo();assert editor.document.to_dict()==original
    editor.redo();assert editor.document.links[0].route_points==moved


def test_escape_restores_link_before_endpoint_drag(editor):
    edge=editor.scene.edge_items[0];edge.setSelected(True)
    original=editor.document.to_dict()
    handle=next(h for h in edge.handles if h.kind=='source')
    viewport=editor.view.viewport()
    start=editor.view.mapFromScene(handle.scenePos())
    end=editor.view.mapFromScene(QPointF(80,0))
    QTest.mousePress(viewport,Qt.LeftButton,Qt.NoModifier,start)
    QTest.mouseMove(viewport,end,delay=20)
    QTest.keyClick(editor.view,Qt.Key_Escape)
    QTest.mouseRelease(viewport,Qt.LeftButton,Qt.NoModifier,end)
    assert editor.document.to_dict()==original
    assert not editor.dirty


def test_compound_multivalue_local_key_is_scoped_to_owner():
    owner=Node(name='Persona')
    key=Node(kind='attribute',name='id',is_pk=True,nullable=False,data_type='INTEGER',parent_id=owner.id)
    multi=Node(kind='multivalue',name='Contatti',parent_id=owner.id)
    local=Node(kind='attribute',name='tipo',is_pk=True,parent_id=multi.id)
    value=Node(kind='attribute',name='valore',parent_id=multi.id)
    sql=generate_sql(Document(nodes=[owner,key,multi,local,value]))
    db=sqlite3.connect(':memory:')
    try:
        db.executescript(sql)
        db.executemany('INSERT INTO Persona(id) VALUES (?)',[(1,),(2,)])
        db.executemany('INSERT INTO Persona_Contatti(Persona_id,tipo,valore) VALUES (?,?,?)',
            [(1,'email','uno'),(2,'email','due')])
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('INSERT INTO Persona_Contatti(Persona_id,tipo) VALUES (1,?)',('email',))
    finally:db.close()


def test_selected_isa_branch_edits_hierarchy_without_cardinalities(editor,monkeypatch):
    parent=Node(name='Persona')
    isa=Node(kind='isa',name='ISA',parent_id=parent.id,x=70,y=180,width=20,height=20)
    child=Node(name='Studente',y=360)
    link=Link(isa.id,child.id)
    editor.replace_document(Document(nodes=[parent,isa,child],links=[link]))
    editor.scene.find_item(link.id).setSelected(True)
    assert editor.inspector_type.text()=='GERARCHIA ISA'
    assert '0,N' not in editor.inspector_info.text()
    def choose(parent,node,doc):
        assert node.kind=='isa'
        edited=copy.deepcopy(node)
        edited.isa_total,edited.isa_disjoint=True,False
        return edited
    monkeypatch.setattr('drawer.window.edit_node',choose)
    editor.edit_selected()
    stem=next(edge for edge in editor.scene.edge_items if edge.child)
    assert [label.text() for label in stem.labels]==['(t,s)']
    editor.undo();assert not editor.document.node(isa.id).isa_total


def test_direct_isa_branch_never_opens_cardinality_dialog(editor,monkeypatch):
    parent=Node(name='Persona')
    isa=Node(kind='isa',name='ISA',parent_id=parent.id,x=70,y=180,width=20,height=20)
    child=Node(name='Studente',x=0,y=360)
    editor.replace_document(Document(nodes=[parent,isa,child]))
    QApplication.processEvents()
    monkeypatch.setattr('drawer.window.edit_link',lambda *args:pytest.fail('Una ISA non ha cardinalità.'))
    source=editor.scene.node_items[isa.id]
    arrow=next(arrow for arrow in source.port_arrows if arrow.side=='bottom')
    QTest.mouseMove(editor.view.viewport(), editor.view.mapFromScene(source.sceneBoundingRect().center()))
    assert arrow.isVisible()
    target=editor.scene.node_items[child.id]
    drag(editor,arrow.scenePos(),port_point(target.mapRectToScene(target.body_rect()),'top'))
    assert len(editor.document.links)==1
    assert not next(edge for edge in editor.scene.edge_items if edge.link).labels


@pytest.mark.parametrize('property,value',[('source_port','middle'),
    ('route_points',[[0,0],[1,2]]),('route_points',[[0,0]]),
    ('route_points',[[0,0]]*257)])
def test_malformed_connection_geometry_is_rejected(property,value):
    a,b=Node(name='A'),Node(name='B')
    doc=Document(nodes=[a,b],links=[Link(a.id,b.id)])
    data=doc.to_dict();data['links'][0][property]=value
    with pytest.raises(ValueError):Document.from_dict(data)


def test_pasting_attribute_into_another_project_never_breaks_history(editor):
    owner=editor.document.nodes[0]
    attribute=Node(kind='attribute',name='email',parent_id=owner.id,x=200,y=-100)
    editor.document.nodes.append(attribute);editor.commit(True)
    editor.scene.node_items[attribute.id].setSelected(True)
    editor.copy_selection()
    editor.replace_document(Document())
    editor.paste_selection()
    assert editor.document.nodes[0].parent_id is None
    assert Document.from_dict(editor.document.to_dict()).nodes[0].name=='email'
    editor.undo();assert not editor.document.nodes
    editor.redo();assert editor.document.nodes[0].name=='email'


def test_long_drag_does_not_accumulate_unbounded_route_vertices():
    points=[[160,40],[182,40],[182,-60],[338,-60],[338,40],[360,40]]
    for frame in range(1000):
        start=QPointF(160+frame/20,40+frame/40)
        adapted=adapt_manual(points,start,QPointF(360,40),'right','left')
        points=serialized(adapted)
        assert len(points)<=6
        assert adapted[0]==start and adapted[-1]==QPointF(360,40)
        assert all(abs(a.x()-b.x())<.01 or abs(a.y()-b.y())<.01 for a,b in zip(adapted,adapted[1:]))


@pytest.mark.parametrize('gesture',['handle','arrow'])
def test_focus_loss_cancels_unfinished_connection_gestures(editor,gesture):
    original=editor.document.to_dict()
    edge=editor.scene.edge_items[0];edge.setSelected(True)
    if gesture=='handle':control=next(h for h in edge.handles if h.kind=='source')
    else:
        source = editor.scene.node_items[editor.document.nodes[0].id]
        QTest.mouseMove(editor.view.viewport(), editor.view.mapFromScene(source.sceneBoundingRect().center()))
        control = source.port_arrows[1]
        assert control.isVisible()
    start=editor.view.mapFromScene(control.scenePos())
    viewport=editor.view.viewport()
    QTest.mousePress(viewport,Qt.LeftButton,Qt.NoModifier,start)
    QTest.mouseMove(viewport,start+editor.view.mapFromScene(QPointF(0,-80))-editor.view.mapFromScene(QPointF()),delay=20)
    QApplication.sendEvent(editor.view,QEvent(QEvent.WindowDeactivate))
    QTest.mouseRelease(viewport,Qt.LeftButton,Qt.NoModifier,start)
    assert editor.scene.active_handle is None and editor.scene._direct_source is None
    assert editor.document.to_dict()==original and not editor.dirty


def test_rename_keeps_previous_recovery_discoverable(app,tmp_path,monkeypatch):
    from PySide6.QtCore import QStandardPaths
    studio=tmp_path/'DrawER'/'DrawER Studio'
    old=tmp_path/'DrawER'/'DrawER Desktop'/'recovery.erdraw'
    old.parent.mkdir(parents=True)
    save_document(Document(nodes=[Node(name='Recuperabile')]),old)
    monkeypatch.setattr(QStandardPaths,'writableLocation',lambda *args:str(studio))
    monkeypatch.setattr(MainWindow,'offer_recovery',lambda self:None)
    window=MainWindow(recovery=True)
    try:
        assert window.recovery_path==old
    finally:
        window.recovery_timer.stop();window._recovery_enabled=False
        window.close();window.deleteLater();app.processEvents()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


def test_attribute_anchor_and_cardinality_survive_save_and_paste(editor, tmp_path):
    owner = Node(name='Persona')
    attribute = Node(kind='attribute', name='telefono', parent_id=owner.id,
                     attribute_card='1,N', x=300, y=40)
    editor.replace_document(Document(nodes=[owner, attribute]))
    edge = editor.scene.edge_items[0]
    assert edge.labels[0].text() == '(1,N)'
    edge.setSelected(True)
    handle = next(h for h in edge.handles if h.kind == 'source')
    drag(editor, handle.scenePos(), QPointF(42, 0))
    assert abs(edge.points[0].x() - 42) < 2
    assert edge.points[0].y() == 0
    assert attribute.parent_anchor_angle is not None
    path = tmp_path / 'attributo.erdraw'
    save_document(editor.document, path)
    assert load_document(path).node(attribute.id).parent_anchor_angle == attribute.parent_anchor_angle
    editor.scene.clearSelection()
    editor.scene.node_items[attribute.id].setSelected(True)
    editor.copy_selection()
    editor.paste_selection()
    pasted = next(n for n in editor.document.nodes if n.id not in (owner.id, attribute.id))
    assert pasted.parent_anchor_angle == attribute.parent_anchor_angle
    assert pasted.attribute_card == '1,N'


def test_manual_isa_branch_preserves_junction_normal_when_child_moves(editor):
    parent=Node(name='Persona')
    isa=Node(kind='isa',name='ISA',parent_id=parent.id,x=70,y=160,width=20,height=20)
    child=Node(name='Studente',x=360,y=130)
    link=Link(isa.id,child.id,source_port='right',target_port='left')
    editor.replace_document(Document(nodes=[parent,isa,child],links=[link]))
    edge=next(e for e in editor.scene.edge_items if e.link);edge.setSelected(True)
    handle=next(h for h in edge.handles if h.kind=='segment')
    drag(editor,handle.scenePos(),handle.scenePos()+QPointF(0,80))
    assert link.source_port=='right'
    item=editor.scene.node_items[child.id];item.setPos(item.pos()+QPointF(40,80))
    editor.commit()
    assert Document.from_dict(editor.document.to_dict()).links[0].route_points


def test_save_names_untitled_project_and_reopen_uses_file_stem(editor, tmp_path, monkeypatch):
    target = tmp_path / 'Archivio clienti.erdraw'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(target), ''))
    node = editor.document.nodes[0]
    original_name = node.name
    node.name = 'Clienti'
    editor.commit(rebuild=True)
    assert editor.save_document()
    assert load_document(target).title == 'Archivio clienti'
    assert editor.canvas_title.text() == 'Archivio clienti'
    assert not editor.dirty
    editor.undo()
    assert editor.document.node(node.id).name == original_name
    assert editor.document.title == 'Archivio clienti'
    editor.redo()
    assert not editor.dirty
    legacy = tmp_path / 'Vecchio progetto.erdraw'
    save_document(Document(), legacy)
    editor.load_path(legacy)
    assert editor.canvas_title.text() == 'Vecchio progetto'


def test_save_as_updates_filename_title_and_preserves_explicit_title(editor, tmp_path, monkeypatch):
    editor.path = tmp_path / 'Prima.erdraw'
    editor.document.title = 'Prima'
    editor.commit()
    target = tmp_path / 'Seconda.erdraw'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(target), ''))
    assert editor.save_document(True)
    assert load_document(target).title == 'Seconda'
    editor.document.title = 'Titolo personalizzato'
    editor.commit()
    assert editor.save_document()
    assert load_document(target).title == 'Titolo personalizzato'


def test_port_arrows_only_show_on_hover_and_stay_reachable(editor):
    source = editor.scene.node_items[editor.document.nodes[0].id]
    target = editor.scene.node_items[editor.document.nodes[1].id]
    view = editor.view
    viewport = view.viewport()
    QTest.mouseMove(viewport, view.mapFromScene(QPointF(250, -90)))
    assert not any(arrow.isVisible() for arrow in source.port_arrows)
    QTest.mouseMove(viewport, view.mapFromScene(source.sceneBoundingRect().center()))
    assert all(arrow.isVisible() for arrow in source.port_arrows)
    assert not any(arrow.isVisible() for arrow in target.port_arrows)
    arrow = source.port_arrows[1]
    QTest.mouseMove(viewport, view.mapFromScene(arrow.scenePos() - QPointF(11, 0)))
    assert arrow.isVisible()
    QTest.mouseMove(viewport, view.mapFromScene(arrow.scenePos()))
    assert arrow.isVisible()
    QTest.mouseMove(viewport, view.mapFromScene(target.sceneBoundingRect().center()))
    assert not any(arrow.isVisible() for arrow in source.port_arrows)
    assert all(arrow.isVisible() for arrow in target.port_arrows)


@pytest.mark.parametrize('left,top', [(True, True), (False, True), (True, False), (False, False)])
def test_resize_corner_moves_live_and_preserves_opposite_corner(editor, left, top):
    node = editor.document.nodes[0]
    item = editor.scene.node_items[node.id]
    item.setSelected(True)
    handle = next(h for h in item.resize_handles if (h.left, h.top) == (left, top))
    assert handle.isVisible()
    start = editor.view.mapFromScene(handle.scenePos())
    end = editor.view.mapFromScene(handle.scenePos() + QPointF(-40 if left else 40,
                                                              -30 if top else 30))
    viewport = editor.view.viewport()
    QTest.mousePress(viewport, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(viewport, end, delay=20)
    assert node.width == pytest.approx(200, abs=2)
    assert node.height == pytest.approx(110, abs=2)
    assert (node.x + node.width if left else node.x) == pytest.approx(160 if left else 0)
    assert (node.y + node.height if top else node.y) == pytest.approx(80 if top else 0)
    assert editor.scene.edge_items[0].points[0] == port_point(item.mapRectToScene(item.body_rect()), 'right')
    QTest.mouseRelease(viewport, Qt.LeftButton, Qt.NoModifier, end)
    editor.undo()
    assert editor.document.node(node.id).width == 160
    editor.redo()
    assert editor.document.node(node.id).width == pytest.approx(200, abs=2)


def test_copy_preserves_entity_and_relationship_names(editor):
    original = [node.name for node in editor.document.nodes]
    editor.select_all()
    editor.copy_selection()
    editor.paste_selection()
    assert [node.name for node in editor.document.nodes] == original + original


def test_png_is_white_and_crops_to_the_diagram_in_dark_mode(app, tmp_path):
    node = Node(kind='relation', name='R', width=160, height=80)
    scene = DiagramScene(Document(nodes=[node]))
    scene.dark = True
    output = tmp_path / 'ritaglio.png'
    export_diagram(scene, output, 'png')
    image = QImage(str(output))
    white = QColor(Qt.white)
    assert image.pixelColor(0, 0) == white
    assert 320 <= image.width() <= 326 and 160 <= image.height() <= 166
    assert all(any(image.pixelColor(x, y) != white for x in range(image.width()))
               for y in (0, image.height()-1))
    assert all(any(image.pixelColor(x, y) != white for y in range(image.height()))
               for x in (0, image.width()-1))
    assert scene.dark and not scene.transparent_background


@pytest.mark.parametrize('key', ['source', 'role', 'isa'])
def test_drag_label_saves_position_and_undoes(editor, tmp_path, key):
    if key == 'isa':
        parent = editor.document.nodes[0]
        junction = Node(kind='isa', name='ISA', parent_id=parent.id, x=70, y=190,
                        width=20, height=20)
        editor.replace_document(Document(nodes=[parent, junction]))
        owner = junction
    else:
        owner = editor.document.links[0]
        owner.role = 'proprietario'
        editor.commit()
    edge = editor.scene.edge_items[0]
    label = next(label for label in edge.labels if label.key == key)
    start = label.sceneBoundingRect().center()
    drag(editor, start, start + QPointF(70, 44))
    offsets = owner.label_offsets[key]
    assert offsets == pytest.approx([70, 44], abs=2)
    output = tmp_path / 'etichette.erdraw'
    save_document(editor.document, output)
    loaded = load_document(output)
    restored = loaded.node(owner.id) if key == 'isa' else loaded.links[0]
    assert restored.label_offsets[key] == offsets
    editor.undo()
    assert key not in next(label for label in editor.scene.edge_items[0].labels if label.key == key).offsets
    editor.redo()
    assert next(label for label in editor.scene.edge_items[0].labels if label.key == key).offsets[key] == offsets


def test_tutorial_first_run_skip_replay_and_exercise_menu(editor, tmp_path):
    editor.settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.IniFormat)
    editor.maybe_show_tutorial()
    assert editor.learning.isVisible()
    editor.set_mode('attribute')
    assert 'appartiene' in editor.learning.context.text()
    editor.learning.skip.click()
    editor.settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.IniFormat)
    editor.maybe_show_tutorial()
    assert not editor.learning.isVisible()
    editor.actions['tutorial'].trigger()
    assert editor.learning.isVisible() and editor.learning.title.text().startswith('1/4')
    help_menu = next(action.menu() for action in editor.menuBar().actions() if action.text() == 'Aiuto')
    exercise_menu = next(action.menu() for action in help_menu.actions() if action.text() == 'Esercizi formativi')
    assert len(exercise_menu.actions()) == 3
    current = editor.document
    exercise_menu.actions()[1].trigger()
    assert editor.document is current
    editor.learning.tip.click()
    assert '(0,N)' in editor.learning.context.text()
    editor.learning.starter.click()
    assert [node.name for node in editor.document.nodes] == ['Studente', 'Corso']
    assert editor.path is None
