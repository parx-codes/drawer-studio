"""Finestra principale: coordina comandi applicativi, modello e scena."""
import copy
import json
import math
import os
import sys
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QStandardPaths, QSettings
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QFont
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QToolBar, QToolButton, QDockWidget, QTreeWidget,
    QTreeWidgetItem, QLineEdit, QFrame, QFileDialog, QMessageBox, QMenu, QListWidget,
    QListWidgetItem, QInputDialog)

from .model import DEFAULT_TITLE, Document, Node, Link, new_id
from .storage import load_document, save_document
from .validation import validate
from .sql import generate_sql, SqlExportError
from .history import History
from .scene import DiagramScene, DiagramView, NAMES
from .dialogs import edit_node, edit_link, create_relationship, SqlPreviewDialog, HelpDialog
from .learning import LearningDock, EXERCISES
from .exports import export_diagram
from .theme import apply_theme
from . import __version__, APP_NAME


def resource_root():
    root=Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    return root if (root/'examples').exists() else Path(__file__).resolve().parent


def project_title(title, path, previous_path=None):
    if not title.strip() or title.strip().casefold() == DEFAULT_TITLE.casefold():
        return path.stem
    if previous_path and title == previous_path.stem:
        return path.stem
    return title


class MainWindow(QMainWindow):
    def __init__(self, document=None, path=None, recovery=True):
        super().__init__()
        self.path = Path(path) if path else None
        self.document = document or Document()
        if self.path:
            self.document.title = project_title(self.document.title, self.path)
        self.history = History(self.document)
        self.saved_signature = History.signature(self.document)
        self.clipboard = None
        self.clipboard_is_cut = False
        self.settings = QSettings('DrawER', 'DrawER Desktop')
        self.dark = self.settings.value('dark', False, type=bool)
        self._recovery_enabled = recovery
        self.recovery_path = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)) / 'recovery.erdraw'
        legacy_recovery=self.recovery_path.parent.parent/'DrawER Desktop'/'recovery.erdraw'
        if recovery and not self.recovery_path.exists() and legacy_recovery.exists():
            # La nuova identità pubblica non deve nascondere il recupero di una
            # sessione precedente. Il file viene gestito fino al salvataggio.
            self.recovery_path=legacy_recovery
        self.setMinimumSize(1000,680)
        self.resize(1440,900)
        self.scene = DiagramScene(self.document, self)
        self.view = DiagramView(self.scene, self)
        self.actions, self.mode_buttons = {}, {}
        self._build_actions()
        self._build_central()
        self._build_left_panel()
        self._build_inspector()
        self._build_issues()
        self.learning = LearningDock(self)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.learning)
        self.learning.starter_requested.connect(self.open_exercise_starter)
        self._build_menu_toolbar()
        self.hint_label = QLabel()
        self.count_label = QLabel()
        self.zoom_label = QLabel('100%')
        self.statusBar().addWidget(self.hint_label,1)
        self.statusBar().addPermanentWidget(self.count_label)
        self.statusBar().addPermanentWidget(self.zoom_label)
        self.scene.hint.connect(self.hint_label.setText)
        self.scene.changed_by_user.connect(self.commit)
        self.scene.edit_requested.connect(self.edit_object)
        self.scene.create_requested.connect(self.create_object)
        self.scene.connect_requested.connect(self.connect_objects)
        self.scene.direct_connect_requested.connect(self.connect_objects)
        self.scene.delete_requested.connect(self.delete_selection)
        self.scene.selectionChanged.connect(self.update_inspector)
        self.scene.selectionChanged.connect(self.update_learning_context)
        self.scene.hint.connect(self.update_learning_context)
        self.view.zoom_changed.connect(lambda value:self.zoom_label.setText(f'{value}%'))
        self.view.escape_pressed.connect(lambda:self.set_mode('select'))
        self.apply_theme()
        self.set_mode('select')
        self.refresh_panels()
        if recovery:
            self.recovery_timer = QTimer(self)
            self.recovery_timer.timeout.connect(self.autosave)
            self.recovery_timer.start(45000)
            if self.recovery_path.exists():
                QTimer.singleShot(150,self.offer_recovery)

    @property
    def dirty(self):
        return History.signature(self.document) != self.saved_signature

    def action(self,key,text,callback,shortcut=None,checkable=False):
        action = QAction(text,self)
        action.setCheckable(checkable)
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        self.actions[key]=action
        self.addAction(action)
        return action

    def _build_actions(self):
        self.action('new','Nuovo',self.new_document,'Ctrl+N')
        self.action('open','Apri…',self.open_document,'Ctrl+O')
        self.action('save','Salva',self.save_document,'Ctrl+S')
        self.action('saveas','Salva con nome…',lambda:self.save_document(True),'Ctrl+Shift+S')
        self.action('undo','Annulla',self.undo,'Ctrl+Z')
        self.action('redo','Ripeti',self.redo,'Ctrl+Shift+Z')
        self.actions['redo'].setShortcuts([QKeySequence('Ctrl+Shift+Z'),QKeySequence('Ctrl+Y')])
        self.action('delete','Elimina selezione',self.delete_selection,'Delete')
        self.action('copy','Copia',self.copy_selection,'Ctrl+C')
        self.action('cut','Taglia',self.cut_selection,'Ctrl+X')
        self.action('paste','Incolla',self.paste_selection,'Ctrl+V')
        self.action('all','Seleziona tutto',self.select_all,'Ctrl+A')
        self.action('edit','Modifica selezione…',self.edit_selected,'F2')
        self.action('fit','Adatta al diagramma',self.view.fit_diagram,'Ctrl+0')
        self.action('zoomin','Ingrandisci',lambda:self.view.zoom(1.2),'Ctrl++')
        self.action('zoomout','Riduci',lambda:self.view.zoom(1/1.2),'Ctrl+-')
        self.action('wizard','Relazione guidata…',self.relationship_wizard,'Ctrl+R')
        self.action('validate','Verifica schema',self.show_validation,'F7')
        self.action('demo','Apri esempio universitario',self.open_example)
        self.action('title','Rinomina progetto…',self.rename_document)
        self.action('help','Guida rapida',lambda:HelpDialog(self).exec(),'F1')
        self.action('tutorial','Guida didattica…',self.show_tutorial)
        self.action('about','Informazioni su DrawER Studio…',self.show_about)
        self.action('theme','Tema scuro',self.toggle_theme,checkable=True)
        self.action('snap','Aggancia alla griglia',self.toggle_snap,checkable=True).setChecked(True)
        self.action('layout','Disponi automaticamente',self.auto_layout)
        self.action('alignleft','Allinea a sinistra',lambda:self.align('left'))
        self.action('aligntop','Allinea in alto',lambda:self.align('top'))
        self.action('aligncentery','Allinea i centri orizzontalmente',lambda:self.align('centery'))
        self.action('aligncenterx','Allinea i centri verticalmente',lambda:self.align('centerx'))
        for kind in ('png','svg','pdf'):
            self.action(kind,'Esporta '+kind.upper()+'…',lambda checked=False,k=kind:self.export_image(k))
        for dialect,label in (('sqlite','SQLite'),('postgresql','PostgreSQL')):
            self.action(dialect,'SQL per '+label+'…',lambda checked=False,d=dialect:self.preview_sql(d))
        self.mode_group=QActionGroup(self)
        for mode,label,key in [('select','↖  Seleziona','V'),('entity','▭  Entità','1'),('relation','◇  Relazione','2'),
                ('multivalue','◎  Multivalore','3'),('isa','△  ISA','4'),('connect','⌁  Collega','5'),('attribute','○  Attributo','6'),('text','T  Nota','7')]:
            action=self.action('mode_'+mode,label,lambda checked=False,m=mode:self.set_mode(m),key,True)
            self.mode_group.addAction(action)

    def _build_central(self):
        central=QWidget()
        layout=QVBoxLayout(central)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        bar=QFrame()
        bar.setObjectName('canvasbar')
        row=QHBoxLayout(bar)
        row.setContentsMargins(22,12,18,12)
        titles=QVBoxLayout()
        eyebrow=QLabel('PROGETTAZIONE CONCETTUALE  /  NOTAZIONE ER')
        eyebrow.setObjectName('eyebrow')
        self.canvas_title=QLabel(self.document.title)
        self.canvas_title.setTextFormat(Qt.PlainText)
        self.canvas_title.setObjectName('title')
        titles.addWidget(eyebrow)
        titles.addWidget(self.canvas_title)
        row.addLayout(titles,1)
        fit=QPushButton('Adatta  ⤢')
        fit.clicked.connect(self.view.fit_diagram)
        row.addWidget(fit)
        layout.addWidget(bar)
        layout.addWidget(self.view,1)
        self.setCentralWidget(central)

    def _build_left_panel(self):
        dock=QDockWidget('SPAZIO DI LAVORO',self)
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        dock.setMinimumWidth(245)
        dock.setMaximumWidth(340)
        body=QWidget()
        layout=QVBoxLayout(body)
        layout.setContentsMargins(14,12,14,12)
        brand=QLabel('DrawER <span style="color:#87939d">Studio</span>')
        brand.setObjectName('brand')
        layout.addWidget(brand)
        subtitle=QLabel('Dall’idea allo schema.')
        subtitle.setObjectName('muted')
        layout.addWidget(subtitle)
        layout.addSpacing(16)
        title=QLabel('STRUMENTI')
        title.setObjectName('eyebrow')
        layout.addWidget(title)
        grid=QGridLayout()
        for index,mode in enumerate(('select','entity','relation','attribute','multivalue','isa','connect','text')):
            action=self.actions['mode_'+mode]
            button=QPushButton(action.text())
            button.setCheckable(True)
            button.setToolTip(action.text()+' · '+action.shortcut().toString())
            button.clicked.connect(lambda checked=False,m=mode:self.set_mode(m))
            grid.addWidget(button,index//2,index%2)
            self.mode_buttons[mode]=button
        layout.addLayout(grid)
        wizard=QPushButton('＋  Relazione guidata')
        wizard.setObjectName('primary')
        wizard.clicked.connect(self.relationship_wizard)
        layout.addWidget(wizard)
        layout.addSpacing(18)
        label=QLabel('ELEMENTI DEL DIAGRAMMA')
        label.setObjectName('eyebrow')
        layout.addWidget(label)
        self.search=QLineEdit()
        self.search.setPlaceholderText('Cerca per nome…')
        self.search.textChanged.connect(self.refresh_tree)
        layout.addWidget(self.search)
        self.tree=QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self.select_tree_item)
        self.tree.itemDoubleClicked.connect(lambda item,col:self.edit_object(item.data(0,Qt.UserRole)) if item.data(0,Qt.UserRole) else None)
        layout.addWidget(self.tree,1)
        dock.setWidget(body)
        self.addDockWidget(Qt.LeftDockWidgetArea,dock)

    def _build_inspector(self):
        dock=QDockWidget('PROPRIETÀ',self)
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        dock.setMinimumWidth(245)
        dock.setMaximumWidth(330)
        body=QWidget()
        layout=QVBoxLayout(body)
        layout.setContentsMargins(18,18,18,18)
        self.inspector_type=QLabel('NESSUNA SELEZIONE')
        self.inspector_type.setObjectName('eyebrow')
        self.inspector_name=QLabel('Inizia con un’entità')
        self.inspector_name.setTextFormat(Qt.PlainText)
        self.inspector_name.setObjectName('title')
        self.inspector_name.setWordWrap(True)
        self.inspector_info=QLabel()
        self.inspector_info.setWordWrap(True)
        self.inspector_info.setTextFormat(Qt.PlainText)
        self.inspector_info.setObjectName('muted')
        self.edit_button=QPushButton('Modifica proprietà…')
        self.edit_button.clicked.connect(self.edit_selected)
        self.add_attr_button=QPushButton('＋  Attributo')
        self.add_attr_button.clicked.connect(self.add_attribute_selected)
        for item in (self.inspector_type,self.inspector_name,self.inspector_info,self.edit_button,self.add_attr_button):
            layout.addWidget(item)
        layout.addStretch()
        legend=QLabel('LEGGERE IL DIAGRAMMA')
        legend.setObjectName('eyebrow')
        layout.addWidget(legend)
        explainer=QLabel('▭  Entità     ◇  Relazione\n●  Chiave primaria\n○  Attributo     ◎  Aggregato multivalore\n▲  ISA: triangolo verso il padre\n(t,s) totale sovrapposta · (t,d) totale disgiunta\n(p,s) parziale sovrapposta · (p,d) parziale disgiunta\n\n(0,1) facoltativa, al massimo una\n(1,1) obbligatoria, esattamente una\n(0,N) facoltativa, molte\n(1,N) obbligatoria, almeno una')
        explainer.setWordWrap(True)
        explainer.setObjectName('muted')
        layout.addWidget(explainer)
        check=QPushButton('✓  Verifica schema  ·  F7')
        check.clicked.connect(self.show_validation)
        layout.addWidget(check)
        dock.setWidget(body)
        self.addDockWidget(Qt.RightDockWidgetArea,dock)

    def _build_issues(self):
        self.issues_dock=QDockWidget('Verifica dello schema',self)
        self.issues_list=QListWidget()
        self.issues_list.itemClicked.connect(self.select_issue)
        self.issues_dock.setWidget(self.issues_list)
        self.addDockWidget(Qt.BottomDockWidgetArea,self.issues_dock)
        self.issues_dock.hide()

    def _build_menu_toolbar(self):
        for label,keys in [('File',['new','open','save','saveas','title','png','svg','pdf','sqlite','postgresql']),
                           ('Modifica',['undo','redo','cut','copy','paste','all','edit','delete']),
                           ('Diagramma',['wizard','validate','layout','alignleft','aligntop','aligncentery','aligncenterx','snap']),
                           ('Visualizza',['fit','zoomin','zoomout','theme']),('Aiuto',['help','tutorial','about'])]:
            menu=self.menuBar().addMenu(label)
            for key in keys:
                menu.addAction(self.actions[key])
            if label=='Aiuto':
                examples=menu.addMenu('Esempi')
                examples.addAction(self.actions['demo'])
                exercises = menu.addMenu('Esercizi formativi')
                for exercise in EXERCISES:
                    action = exercises.addAction(exercise.title)
                    action.triggered.connect(lambda checked=False, entry=exercise:
                                             self.learning.open_exercise(entry))
        toolbar=QToolBar('Comandi')
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for key in ('new','open','save'):
            toolbar.addAction(self.actions[key])
        toolbar.addSeparator()
        for key in ('undo','redo'):
            toolbar.addAction(self.actions[key])
        toolbar.addSeparator()
        toolbar.addAction(self.actions['validate'])
        spacer=QWidget()
        from PySide6.QtWidgets import QSizePolicy
        spacer.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
        toolbar.addWidget(spacer)
        for label,keys in [('Esporta ▾',('png','svg','pdf')),('SQL ▾',('sqlite','postgresql'))]:
            button=QToolButton()
            button.setText(label)
            button.setPopupMode(QToolButton.InstantPopup)
            menu=QMenu(button)
            for key in keys:
                menu.addAction(self.actions[key])
            button.setMenu(menu)
            toolbar.addWidget(button)
        toolbar.addAction(self.actions['help'])

    def set_mode(self,mode):
        self.scene.set_mode(mode)
        for key,button in self.mode_buttons.items():
            button.setChecked(key==mode)
        self.actions['mode_'+mode].setChecked(True)
        self.view.setDragMode(DiagramView.NoDrag)
        self.view.setCursor(Qt.ArrowCursor if mode=='select' else Qt.CrossCursor)
        self.view.setFocus()

    def apply_theme(self):
        apply_theme(QApplication.instance(),self.dark)
        self.scene.dark=self.dark
        self.actions['theme'].setChecked(self.dark)
        self.scene.refresh_edges()
        self.scene.update()

    def toggle_theme(self):
        self.dark=not self.dark
        self.apply_theme()

    def toggle_snap(self):
        self.scene.snap=self.actions['snap'].isChecked()

    def refresh_panels(self):
        self.canvas_title.setText(self.document.title+(' • modificato' if self.dirty else ''))
        self.setWindowTitle(APP_NAME)
        self.actions['undo'].setEnabled(self.history.can_undo)
        self.actions['redo'].setEnabled(self.history.can_redo)
        self.count_label.setText(f'{sum(n.kind=="entity" for n in self.document.nodes)} entità  ·  {sum(n.kind=="relation" for n in self.document.nodes)} relazioni')
        self.refresh_tree()
        self.update_inspector()
        if self.issues_dock.isVisible():
            self.populate_issues()

    def refresh_tree(self):
        if not hasattr(self,'tree'):
            return
        self.tree.clear()
        query=self.search.text().casefold().strip()
        for kind in ('entity','relation','multivalue','isa','text'):
            group=QTreeWidgetItem([NAMES[kind]])
            count=0
            for node in self.document.nodes:
                children=self.document.attributes(node.id)
                if node.kind!=kind or (query and query not in node.name.casefold() and not any(query in a.name.casefold() for a in children)):
                    continue
                item=QTreeWidgetItem([node.name])
                item.setData(0,Qt.UserRole,node.id)
                group.addChild(item)
                count+=1
                for attr in children:
                    child=QTreeWidgetItem([('● ' if attr.is_pk else '○ ')+attr.name])
                    child.setData(0,Qt.UserRole,attr.id)
                    item.addChild(child)
                if query:
                    item.setExpanded(True)
            if count:
                group.setText(0,f'{NAMES[kind]}  ({count})')
                self.tree.addTopLevelItem(group)
                group.setExpanded(True)

    def update_inspector(self):
        ids=self.scene.selected_ids()
        self.edit_button.setText('Modifica proprietà…')
        self.edit_button.setEnabled(len(ids)==1)
        node=self.document.node(ids[0]) if len(ids)==1 else None
        self.add_attr_button.setEnabled(bool(node and node.kind in ('entity','relation','multivalue')))
        if node:
            self.inspector_type.setText(NAMES[node.kind].upper())
            self.inspector_name.setText(node.name)
            info=[]
            if node.kind in ('attribute','multivalue'):
                if node.kind=='multivalue' and self.document.attributes(node.id):
                    info += [f'Aggregato di {len(self.document.attributes(node.id))} attributi','Tabella separata nello schema relazionale']
                else:info += [node.data_type,'Chiave primaria' if node.is_pk else ('Facoltativo (NULL)' if node.nullable else 'Obbligatorio (NOT NULL)')]
                if node.unique: info.append('Valori univoci')
                if node.derived: info.append('Derivato · escluso dal DDL')
            elif node.kind in ('entity','relation'):
                info.append(f'{len(self.document.attributes(node.id))} attributi')
            elif node.kind=='isa':
                info.append(('Totale' if node.isa_total else 'Parziale')+' · '+('disgiunta' if node.isa_disjoint else 'sovrapposta'))
            info += [f'Posizione  {node.x:g}, {node.y:g}']
            if node.kind in ('entity','relation','multivalue','text'):
                info += ['', 'Trascina un angolo per ridimensionare.']
            if node.notes: info+=['',node.notes]
            self.inspector_info.setText('\n'.join(info))
        elif len(ids)==1:
            link=next((l for l in self.document.links if l.id==ids[0]),None)
            if link:
                src,tgt=self.document.node(link.source),self.document.node(link.target)
                self.inspector_type.setText('COLLEGAMENTO')
                self.inspector_name.setText(link.role or 'Partecipazione')
                isa=src if src.kind=='isa' else tgt if tgt.kind=='isa' else None
                if isa:
                    parent=self.document.node(isa.parent_id)
                    child=tgt if src is isa else src
                    code=('t' if isa.isa_total else 'p')+','+('d' if isa.isa_disjoint else 's')
                    self.inspector_type.setText('GERARCHIA ISA')
                    self.inspector_name.setText('('+code+')')
                    self.inspector_info.setText(f'{child.name} → {parent.name if parent else "Padre mancante"}\n\nIl triangolino punta al padre. Trascina la sigla o le maniglie. Fai doppio clic per modificare il tipo di gerarchia.')
                    self.edit_button.setText('Modifica gerarchia…')
                else:
                    cards = [f'{node.name} ({card})' for node, card in
                             ((src, link.source_card), (tgt, link.target_card)) if node.kind == 'entity']
                    cards.append('Trascina le etichette, i cerchi di attacco o i quadrati delle pieghe.')
                    self.inspector_info.setText('\n\n'.join(cards))
        else:
            self.inspector_type.setText('SELEZIONE MULTIPLA' if ids else 'NESSUNA SELEZIONE')
            self.inspector_name.setText(f'{len(ids)} elementi' if ids else 'Inizia con un’entità')
            self.inspector_info.setText('Trascina con il sinistro per spostare gli elementi selezionati.' if ids else 'Clicca sugli oggetti per selezionarli; trascina sullo sfondo per navigare. Le freccette permettono di collegare gli oggetti direttamente sul foglio.')

    def commit(self,rebuild=False,selected=None):
        if rebuild:
            self.scene.document=self.document
            self.scene.rebuild(selected)
        else:
            self.scene.refresh_edges()
        changed=self.history.push(self.document)
        if changed or rebuild:
            self.refresh_panels()

    def replace_document(self,document,path=None):
        self.clear_recovery()
        self.document=document
        self.path=Path(path) if path else None
        if self.path:
            document.title = project_title(document.title, self.path)
        self.history=History(document)
        self.saved_signature=History.signature(document)
        self.scene.document=document
        self.scene.rebuild()
        self.set_mode('select')
        self.refresh_panels()
        self.view.fit_diagram()

    def create_object(self,kind,point,parent_id):
        parent=self.document.node(parent_id) if parent_id else None
        if kind in ('attribute','multivalue','isa'):
            allowed=('entity','relation','multivalue') if kind=='attribute' else ('entity',)
            if not parent or parent.kind not in allowed:
                self.hint_label.setText('Scegli prima un proprietario valido: '+('entità, relazione o aggregato multivalore.' if kind=='attribute' else 'entità.'))
                return
        count=sum(n.kind==kind for n in self.document.nodes)+1
        node=Node(kind=kind,name=NAMES.get(kind,'Elemento')+'_'+str(count),x=round(point.x()/20)*20,y=round(point.y()/20)*20)
        if kind in ('attribute','multivalue','isa'):
            node.parent_id=parent.id
            index=len([n for n in self.document.nodes if n.parent_id==parent.id])
            if kind=='isa':
                node.width,node.height=20,20
                node.name='ISA'
                node.x,node.y=parent.x+parent.width/2-10,parent.y+parent.height+80
            else:
                angle=-math.pi/2+index*.65
                node.x=round((parent.x+parent.width/2+math.cos(angle)*160)/20)*20
                node.y=round((parent.y+parent.height/2+math.sin(angle)*150)/20)*20
                if kind=='attribute' and not self.document.attributes(parent.id) and parent.kind=='entity':
                    node.name='id'
                    node.data_type='INTEGER'
                    node.is_pk,node.nullable=True,False
                if kind=='multivalue':
                    node.width,node.height=150,60
        elif kind=='relation':
            node.width,node.height=140,80
        elif kind=='text':
            node.width,node.height=220,100
        edited=edit_node(self,node,self.document)
        if edited:
            self.document.nodes.append(edited)
            self.commit(True,[edited.id])
            self.set_mode('select')

    def connect_objects(self,source,target,source_port=None,target_port=None):
        s,t=self.document.node(source),self.document.node(target)
        if not s or not t or s.id==t.id:return
        for child,parent,child_side,parent_side in ((s,t,source_port,target_port),(t,s,target_port,source_port)):
            ownership=(child.kind=='attribute' and parent.kind in ('entity','relation','multivalue')) or (
                child.kind=='multivalue' and parent.kind=='entity') or (
                child.kind=='isa' and child.parent_id==parent.id)
            if ownership:
                old_parent=child.parent_id
                child.parent_id=parent.id;child.parent_port=parent_side;child.child_port=child_side
                child.connection_points=[]
                if child.kind in ('attribute','multivalue'):
                    self.document.links=[edge for edge in self.document.links if
                        {edge.source,edge.target} not in ({child.id,parent.id},{child.id,old_parent})]
                self.commit(True,[child.id]);self.set_mode('select');return
        allowed=(s.kind=='entity' and t.kind in ('entity','relation','isa')) or (t.kind=='entity' and s.kind in ('relation','isa'))
        if not allowed or (s.kind=='isa' and s.parent_id==t.id) or (t.kind=='isa' and t.parent_id==s.id):
            self.hint_label.setText('Collega un’entità a una relazione, a un’altra entità o a un ISA di cui è sottotipo.')
            return
        link=Link(source=source,target=target,source_port=source_port,target_port=target_port)
        edited=link if 'isa' in (s.kind,t.kind) else edit_link(self,link,self.document)
        if edited:
            self.document.links.append(edited)
            self.commit(True,[edited.id])
        self.set_mode('select')

    def edit_object(self,id_):
        node=self.document.node(id_)
        if node:
            result=edit_node(self,node,self.document)
            if result:
                self.document.nodes[self.document.nodes.index(node)]=result
                if result.kind in ('attribute','multivalue') and result.parent_id:
                    # Il proprietario appena confermato sostituisce l'eventuale
                    # arco grafico dei file web; la scena lo genera dal parent_id.
                    self.document.links=[link for link in self.document.links
                        if {link.source,link.target}!={result.id,result.parent_id}]
                self.commit(True,[id_])
        else:
            link=next((l for l in self.document.links if l.id==id_),None)
            if link:
                isa=next((node for node in (self.document.node(link.source),self.document.node(link.target))
                          if node and node.kind=='isa'),None)
                if isa:
                    result=edit_node(self,isa,self.document)
                    if result:
                        self.document.nodes[self.document.nodes.index(isa)]=result
                        self.commit(True,[id_])
                    return
                result=edit_link(self,link,self.document)
                if result:
                    self.document.links[self.document.links.index(link)]=result
                    self.commit(True,[id_])

    def edit_selected(self):
        ids=self.scene.selected_ids()
        if len(ids)==1:
            self.edit_object(ids[0])

    def add_attribute_selected(self):
        ids=self.scene.selected_ids()
        if len(ids)==1:
            self.create_object('attribute',self.view.mapToScene(self.view.viewport().rect().center()),ids[0])

    def relationship_wizard(self):
        result=create_relationship(self,self.document)
        if result:
            node,links=result
            self.document.nodes.append(node)
            self.document.links.extend(links)
            self.commit(True,[node.id])
            self.set_mode('select')

    def delete_selection(self):
        ids=set(self.scene.selected_ids())
        if not ids:return
        # Chiusura transitiva dei figli: nessun attributo o ISA orfano.
        while True:
            children={n.id for n in self.document.nodes if n.parent_id in ids}
            if children.issubset(ids):break
            ids|=children
        self.document.nodes=[n for n in self.document.nodes if n.id not in ids]
        self.document.links=[l for l in self.document.links if l.id not in ids and l.source not in ids and l.target not in ids]
        self.commit(True)

    def select_all(self):
        for item in self.scene.node_items.values():item.setSelected(True)

    def copy_selection(self):
        ids=set(self.scene.selected_ids())
        if not ids:return
        while True:
            children={n.id for n in self.document.nodes if n.parent_id in ids}
            if children.issubset(ids):break
            ids|=children
        self.clipboard=copy.deepcopy(([n for n in self.document.nodes if n.id in ids],
            [l for l in self.document.links if l.id in ids or (l.source in ids and l.target in ids)]))
        self.clipboard_is_cut=False
        self.hint_label.setText('Selezione copiata. Ctrl+V per duplicarla.')

    def cut_selection(self):
        if not self.scene.selected_ids():return
        self.copy_selection()
        node_ids={node.id for node in self.clipboard[0]}
        present={link.id for link in self.clipboard[1]}
        self.clipboard[1].extend(copy.deepcopy([link for link in self.document.links if link.id not in present
            and (link.source in node_ids or link.target in node_ids)]))
        self.clipboard_is_cut=True
        self.delete_selection()
        self.hint_label.setText('Selezione tagliata. Ctrl+V per incollarla; Ctrl+Z per ripristinarla.')

    def paste_selection(self):
        if not self.clipboard:return
        nodes,links=copy.deepcopy(self.clipboard)
        mapping={n.id:new_id() for n in nodes}
        current_ids={node.id for node in self.document.nodes}
        orphaned=False
        for node in nodes:
            old_parent=node.parent_id
            node.id=mapping[node.id]
            node.parent_id=mapping.get(node.parent_id,node.parent_id)
            if node.parent_id and node.parent_id not in current_ids|set(mapping.values()):
                node.parent_id=None;orphaned=True
            node.x+=60;node.y+=60
            if node.connection_points:
                if old_parent in mapping:node.connection_points=[[x+60,y+60] for x,y in node.connection_points]
                elif node.parent_id is None:node.connection_points=[]
        available={node.id for node in self.document.nodes}|set(mapping.values())
        copied_links=[]
        for link in links:
            both_moved=link.source in mapping and link.target in mapping
            link.id=new_id();link.source=mapping.get(link.source,link.source);link.target=mapping.get(link.target,link.target)
            if both_moved:link.route_points=[[x+60,y+60] for x,y in link.route_points]
            if link.source in available and link.target in available:copied_links.append(link)
        self.document.nodes.extend(nodes)
        self.document.links.extend(copied_links)
        if not nodes and not copied_links:
            self.hint_label.setText('Gli estremi del collegamento non sono presenti in questo progetto.')
            return
        self.commit(True,list(mapping.values()) or [link.id for link in copied_links])
        if self.clipboard_is_cut:self.clipboard=None;self.clipboard_is_cut=False
        if orphaned:self.hint_label.setText('Elementi incollati: assegna un proprietario nelle proprietà degli attributi o della gerarchia.')

    def align(self,direction):
        items=[i for i in self.scene.selectedItems() if hasattr(i,'node')]
        if len(items)<2:return
        anchor=min(i.pos().x() if direction=='left' else i.pos().y() for i in items)
        centers=[item.mapToScene(item.body_rect().center()) for item in items]
        snap=self.scene.snap;self.scene.snap=False
        try:
            for item in items:
                if direction=='centery':item.setY(centers[0].y()-item.body_rect().center().y())
                elif direction=='centerx':item.setX(centers[0].x()-item.body_rect().center().x())
                else:item.setPos(anchor if direction=='left' else item.pos().x(),anchor if direction=='top' else item.pos().y())
        finally:self.scene.snap=snap
        self.commit()

    def auto_layout(self):
        roots=[n for n in self.document.nodes if not n.parent_id]
        for index,node in enumerate(roots):
            item=self.scene.node_items[node.id]
            item.setPos((index%3)*420,(index//3)*340)
        self.commit()
        self.view.fit_diagram()

    def select_tree_item(self,item,column=0):
        id_=item.data(0,Qt.UserRole)
        graphic=self.scene.find_item(id_) if id_ else None
        if graphic:
            self.scene.clearSelection();graphic.setSelected(True)
            self.view.ensureVisible(graphic,70,70)

    def populate_issues(self):
        self.issues_list.clear()
        issues=validate(self.document)
        if not issues:self.issues_list.addItem('✓ Nessun problema strutturale rilevato. Revisiona comunque il modello rispetto ai requisiti del dominio.')
        for issue in issues:
            item=QListWidgetItem(('ERRORE  ·  ' if issue.severity=='error' else 'AVVISO  ·  ')+issue.message)
            item.setData(Qt.UserRole,issue.node_id)
            self.issues_list.addItem(item)

    def show_validation(self):
        self.populate_issues();self.issues_dock.show()

    def select_issue(self,item):
        id_=item.data(Qt.UserRole)
        graphic=self.scene.find_item(id_) if id_ else None
        if graphic:
            self.scene.clearSelection();graphic.setSelected(True);self.view.ensureVisible(graphic,60,60)

    def rename_document(self):
        title,ok=QInputDialog.getText(self,'Nome del progetto','Titolo:',text=self.document.title)
        if ok and title.strip():
            self.document.title=title.strip();self.commit()

    def undo(self):
        if self.history.can_undo:self._restore(self.history.undo())

    def redo(self):
        if self.history.can_redo:self._restore(self.history.redo())

    def _restore(self,document):
        self.document=document;self.scene.document=document;self.scene.rebuild();self.refresh_panels()

    def confirm_discard(self):
        if not self.dirty:return True
        answer=QMessageBox.question(self,'Modifiche non salvate','Salvare le modifiche al progetto corrente?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Save)
        if answer==QMessageBox.Cancel:return False
        return self.save_document() if answer==QMessageBox.Save else True

    def new_document(self):
        if self.confirm_discard():self.replace_document(Document())

    def open_document(self):
        path,_=QFileDialog.getOpenFileName(self,'Apri diagramma','','Diagrammi DrawER (*.erdraw *.json);;Tutti i file (*)')
        if path:self.load_path(path)

    def load_path(self,path):
        try:document=load_document(path)
        except (OSError,ValueError) as error:
            self.show_error('Apertura non riuscita',error);return
        if self.confirm_discard():
            self.replace_document(document,path)
            if any('legacy' in n.notes.lower() or 'importat' in n.notes.lower() for n in document.nodes):
                self.show_validation()

    def open_example(self):
        self.load_path(resource_root()/'examples'/'universita.erdraw')
        if self.path and self.path.name=='universita.erdraw':
            self.path=None

    def maybe_show_tutorial(self):
        if not self.settings.value('didacticGuideSeen', False, type=bool):
            self.show_tutorial()

    def show_tutorial(self):
        self.settings.setValue('didacticGuideSeen', True)
        self.settings.sync()
        self.learning.start_tutorial()
        self.update_learning_context()

    def update_learning_context(self):
        if self.learning.isVisible():
            self.learning.update_context(self.scene)

    def open_exercise_starter(self, exercise):
        if self.confirm_discard():
            self.replace_document(exercise.starter())

    def save_document(self,save_as=False):
        # QAction passa un booleano: soltanto il comando dedicato forza Salva con nome.
        path=self.path
        if save_as or not path:
            title = self.document.title
            suggested = 'diagramma' if title == DEFAULT_TITLE else title.replace('/', '_').replace('\\', '_')
            chosen,_=QFileDialog.getSaveFileName(self,'Salva progetto',str(path or (suggested + '.erdraw')),'Diagramma DrawER (*.erdraw)')
            if not chosen:return False
            path=Path(chosen)
            if path.suffix.lower()!='.erdraw':path=path.with_suffix('.erdraw')
        title = project_title(self.document.title, path, self.path)
        try:save_document(replace(self.document, title=title),path)
        except (OSError,ValueError) as error:
            self.show_error('Salvataggio non riuscito',error);return False
        if title != self.document.title:
            self.history.update_filename_title(self.document.title, title)
            self.document.title = title
        self.path=path;self.saved_signature=History.signature(self.document)
        self.clear_recovery();self.refresh_panels()
        self.hint_label.setText('Progetto salvato: '+str(path))
        return True

    def export_image(self,kind):
        chosen,_=QFileDialog.getSaveFileName(self,'Esporta '+kind.upper(),'diagramma.'+kind,kind.upper()+' (*.'+kind+')')
        if not chosen:return
        path=Path(chosen)
        if path.suffix.lower()!='.'+kind:path=path.with_suffix('.'+kind)
        try:export_diagram(self.scene,path,kind)
        except (OSError,ValueError) as error:self.show_error('Esportazione non riuscita',error);return
        self.hint_label.setText('Esportato: '+str(path))

    def preview_sql(self,dialect):
        try:sql=generate_sql(self.document,dialect)
        except (ValueError,SqlExportError) as error:
            self.show_validation();self.show_error('Schema da completare',error);return
        SqlPreviewDialog(self,sql,dialect).exec()

    def show_error(self,title,error):
        QMessageBox.warning(self,title,str(error))

    def show_about(self):
        QMessageBox.about(self,'Informazioni su '+APP_NAME,
            f'<h3>DrawER <span style="color:#87939d">Studio</span></h3>'
            f'<p>Versione {__version__}</p><p>Editor di diagrammi Entità–Relazione.</p>'
            '<p>Salvataggio locale, esportazione grafica e SQL preliminare.</p>'
            '<p>I progetti delle versioni precedenti restano importabili.</p>')

    def autosave(self):
        if not self.dirty:return
        try:
            self.recovery_path.parent.mkdir(parents=True,exist_ok=True)
            save_document(self.document,self.recovery_path)
        except (OSError,ValueError):
            self.hint_label.setText('Recupero automatico non disponibile. Salva il progetto manualmente.')

    def offer_recovery(self):
        answer=QMessageBox.question(self,'Recupero automatico','Esiste un diagramma recuperabile da una sessione precedente. Aprirlo?',QMessageBox.Yes|QMessageBox.No)
        if answer==QMessageBox.Yes:
            try:document=load_document(self.recovery_path)
            except (OSError,ValueError) as error:self.show_error('Recupero non riuscito',error);return
            if self.confirm_discard():
                self.replace_document(document)
                self.saved_signature=''
                self.refresh_panels()
        else:self.clear_recovery()

    def clear_recovery(self):
        if not self._recovery_enabled:return
        try:self.recovery_path.unlink(missing_ok=True)
        except OSError:pass

    def closeEvent(self,event):
        if not self.confirm_discard():event.ignore();return
        self.clear_recovery()
        if self._recovery_enabled:
            self.settings.setValue('dark',self.dark)
        event.accept()
