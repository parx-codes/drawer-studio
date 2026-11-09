"""Percorso da un progetto web incompleto a un modello esportabile."""
import copy
import os
import sqlite3

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from drawer.history import History
from drawer.model import Document
from drawer.sql import generate_sql
from drawer.validation import validate
from drawer.window import MainWindow


def test_user_can_repair_legacy_multivalue_without_editing_json(monkeypatch):
    app=QApplication.instance() or QApplication([])
    doc=Document.from_dict({'objects':[
        {'type':'entity','name':'Persona','x':100,'y':100,'w':160,'h':76},
        {'type':'attribute','name':'id','x':80,'y':40,'parentIdx':0,'isPK':True},
        {'type':'multivalue','name':'telefono','x':400,'y':100,'w':150,'h':60}],
        'links':[{'srcIdx':0,'tgtIdx':2}]})
    assert any(issue.severity=='error' for issue in validate(doc))
    window=MainWindow(doc,recovery=False)
    try:
        def choose_owner(parent,node,document):
            edited=copy.deepcopy(node)
            edited.parent_id=document.nodes[0].id
            return edited
        monkeypatch.setattr('drawer.window.edit_node',choose_owner)
        window.edit_object(doc.nodes[2].id)
        assert not [issue for issue in validate(window.document) if issue.severity=='error']
        connection=sqlite3.connect(':memory:')
        try:
            connection.executescript(generate_sql(window.document))
            tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert tables=={'Persona','Persona_telefono'}
        finally:
            connection.close()
        window.undo()
        assert window.document.nodes[2].parent_id is None
        assert len(window.document.links)==1
    finally:
        window.saved_signature=History.signature(window.document)
        window.close()
        window.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
