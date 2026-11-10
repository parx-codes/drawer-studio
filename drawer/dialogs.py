"""Finestre di modifica e guida dell'editor.

I dialoghi lavorano su copie: un annullamento non altera mai il documento.
La validazione di dominio e la generazione SQL restano nei rispettivi moduli.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTextBrowser,
    QVBoxLayout, QWidget,
)

from .model import Document, Link, Node
from .sql import SQL_TYPES, normalize_type
from .richtext import RichTextEditor
from .note_html import MAX_NOTE_TEXT


CARDINALITIES = ("0,1", "1,1", "0,N", "1,N")
KIND_LABELS = {
    "entity": "entità", "relation": "relazione", "attribute": "attributo",
    "multivalue": "attributo multivalore", "isa": "generalizzazione ISA", "text": "testo",
}


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _buttons(dialog: QDialog, accept_label: str = "Applica") -> QDialogButtonBox:
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText(accept_label)
    buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annulla")
    buttons.rejected.connect(dialog.reject)
    return buttons


def _card_combo(value: str = "0,N") -> QComboBox:
    combo = QComboBox()
    combo.addItems(CARDINALITIES)
    combo.setCurrentText(value if value in CARDINALITIES else "0,N")
    combo.setToolTip(
        "Numero minimo e massimo di occorrenze della relazione per una singola "
        "occorrenza dell'entità. N significa molte."
    )
    return combo


def _run_dialog(dialog: QDialog) -> bool:
    """Schedule deletion after modal use, releasing signal closures and widgets."""
    try:
        return dialog.exec() == QDialog.DialogCode.Accepted
    finally:
        dialog.deleteLater()


def edit_node(parent: QWidget | None, node: Node, doc: Document | None = None) -> Node | None:
    """Restituisce il nodo modificato o None, preservando sempre l'originale."""
    result = deepcopy(node)
    dialog = QDialog(parent)
    dialog.setWindowTitle(f"Modifica {KIND_LABELS.get(node.kind, 'elemento')}")
    dialog.setMinimumWidth(460)
    layout = QVBoxLayout(dialog)
    form = QFormLayout()
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    rich_editor = None
    if node.kind == "text":
        dialog.setMinimumWidth(660)
        rich_editor = RichTextEditor(node.name, node.text_html)
        name = rich_editor.text_edit
    else:
        name = QLineEdit(node.name)
        # Match persistence limits so opening a legacy item never truncates its name.
        name.setMaxLength(1024)
    name.setObjectName("nodeName")
    name.setPlaceholderText("Un nome descrittivo")
    form.addRow("Testo" if node.kind == "text" else "Nome", rich_editor or name)
    if rich_editor:
        transparent = QCheckBox("Sfondo trasparente")
        transparent.setObjectName("noteTransparent")
        transparent.setChecked(node.note_transparent)
        background = node.note_background
        color_button = QPushButton(background or "Colore predefinito")
        color_button.setObjectName("noteBackground")
        reset_color = QPushButton("Ripristina colore predefinito")
        color_controls = QHBoxLayout()
        color_controls.addWidget(color_button)
        color_controls.addWidget(reset_color)

        def set_background(value):
            nonlocal background
            background = value
            color_button.setText(value or "Colore predefinito")

        def choose_background():
            chosen = QColorDialog.getColor(QColor(background or "#fff9e7"), dialog, "Sfondo della nota")
            if chosen.isValid():
                set_background(chosen.name())

        color_button.clicked.connect(choose_background)
        reset_color.clicked.connect(lambda: set_background(None))
        for button in (color_button, reset_color):
            button.setEnabled(not transparent.isChecked())
            transparent.toggled.connect(button.setDisabled)
        form.addRow("Sfondo", transparent)
        form.addRow("Colore", color_controls)
    owner = None
    if doc is not None and node.kind in ("attribute", "multivalue", "isa"):
        owner = QComboBox()
        owner.setObjectName("owner")
        owner.addItem("Seleziona un proprietario…", None)
        allowed = {"entity", "relation", "multivalue"} if node.kind == "attribute" else {"entity"}
        for candidate in doc.nodes:
            if candidate.id != node.id and candidate.kind in allowed:
                owner.addItem(
                    f"{candidate.name} · {KIND_LABELS[candidate.kind]}",
                    candidate.id,
                )
        current = owner.findData(node.parent_id)
        owner.setCurrentIndex(max(0, current))
        if current < 0 or node.parent_id is None:
            owner.setItemText(0, "Proprietario mancante: seleziona…")
        form.addRow("Entità padre" if node.kind == "isa" else "Proprietario", owner)
    dimensions = QHBoxLayout()
    width = QSpinBox()
    width.setRange(20, 4000)
    width.setValue(round(node.width))
    width.setSuffix(" px")
    height = QSpinBox()
    height.setRange(20, 4000)
    height.setValue(round(node.height))
    height.setSuffix(" px")
    dimensions.addWidget(width)
    dimensions.addWidget(QLabel("×"))
    dimensions.addWidget(height)
    if node.kind != 'isa':
        form.addRow("Dimensioni", dimensions)

    cardinality = use_cardinality = None
    data_type = None
    primary = nullable = unique = derived = None
    if node.kind in ("attribute", "multivalue"):
        data_type = QComboBox()
        data_type.setEditable(True)
        data_type.addItems(SQL_TYPES)
        data_type.setCurrentText(node.data_type)
        if node.kind=='multivalue' and doc is not None and doc.attributes(node.id):
            data_type.setEnabled(False)
            data_type.setToolTip('Il tipo è definito dagli attributi componenti dell’aggregato.')
        form.addRow("Tipo SQL", data_type)
        primary = QCheckBox("Parte della chiave primaria")
        primary.setObjectName("primaryKey")
        primary.setChecked(node.is_pk and node.kind != "multivalue")
        primary.setEnabled(node.kind != "multivalue")
        primary.setToolTip("Seleziona più attributi per definire una chiave composta.")
        nullable = QCheckBox("Ammette valori NULL")
        nullable.setObjectName("nullable")
        nullable.setChecked(node.nullable)
        unique = QCheckBox("Valore univoco (UNIQUE)")
        unique.setChecked(node.unique)
        derived = QCheckBox("Derivato: escluso dalla generazione SQL")
        derived.setObjectName("derived")
        derived.setChecked(node.derived)
        form.addRow("Vincoli", primary)
        form.addRow("", nullable)
        form.addRow("", unique)
        form.addRow("", derived)

        def sync_constraints() -> None:
            if primary.isChecked():
                nullable.setChecked(False)
                derived.setChecked(False)
            nullable.setEnabled(not primary.isChecked())
            derived.setEnabled(not primary.isChecked())

        primary.toggled.connect(sync_constraints)
        sync_constraints()
        if node.kind == "attribute":
            use_cardinality = QCheckBox("Specifica cardinalità")
            use_cardinality.setObjectName("attributeCardEnabled")
            use_cardinality.setChecked(node.attribute_card is not None)
            cardinality = _card_combo(node.attribute_card or "1,1")
            cardinality.setObjectName("attributeCard")
            form.addRow("Cardinalità", use_cardinality)
            form.addRow("", cardinality)

            def sync_cardinality():
                enabled = use_cardinality.isChecked()
                cardinality.setEnabled(enabled)
                allows_key = not enabled or cardinality.currentText() == "1,1"
                if not allows_key:
                    primary.setChecked(False)
                primary.setEnabled(allows_key)

            use_cardinality.toggled.connect(sync_cardinality)
            cardinality.currentTextChanged.connect(sync_cardinality)
            sync_cardinality()


    hierarchy = None
    if node.kind == "isa":
        hierarchy = QComboBox()
        hierarchy.setObjectName('isaType')
        for label, flags in [('Totale sovrapposta (t,s)',(True,False)),
                             ('Totale disgiunta (t,d)',(True,True)),
                             ('Parziale sovrapposta (p,s)',(False,False)),
                             ('Parziale disgiunta (p,d)',(False,True))]:
            hierarchy.addItem(label,flags)
        hierarchy.setCurrentIndex(next(i for i in range(4)
            if tuple(hierarchy.itemData(i)) == (node.isa_total,node.isa_disjoint)))
        form.addRow('Tipo di gerarchia', hierarchy)

    notes = QPlainTextEdit(node.notes)
    notes.setPlaceholderText("Descrizione, regole di dominio, osservazioni…")
    notes.setMaximumHeight(100)
    form.addRow("Note", notes)
    layout.addLayout(form)
    if node.kind == "isa":
        layout.addWidget(_hint(
            "Collega le entità figlie al punto di diramazione ISA. Il triangolino "
            "punta sempre al padre. L'etichetta usa t/p e d/s. I vincoli sono documentati nello SQL, "
            "ma richiedono verifiche applicative o trigger."
        ))
    elif node.kind == "multivalue":
        layout.addWidget(_hint(
            "Puoi aggiungere attributi componenti all'ovale multivalore. L'aggregato "
            "diventa una tabella separata con FK all'entità proprietaria."
        ))
    buttons = _buttons(dialog)
    layout.addWidget(buttons)

    def accept() -> None:
        name_text = rich_editor.toPlainText() if rich_editor else name.text()
        if not name_text.strip():
            QMessageBox.warning(dialog, "Nome richiesto", "Inserisci un nome o un testo.")
            name.setFocus()
            return
        maximum = MAX_NOTE_TEXT if rich_editor else 1024
        if (len(name_text) > maximum or len(notes.toPlainText()) > 16384
                or "\x00" in notes.toPlainText() or "\x00" in name_text):
            QMessageBox.warning(
                dialog, "Testo non valido",
                f"Il nome o testo può contenere al massimo {maximum:,} caratteri; "
                "le note al massimo 16.384. "
                "Nome e note non possono contenere caratteri nulli.",
            )
            return
        if owner is not None and owner.currentData() is None:
            QMessageBox.warning(
                dialog, "Proprietario richiesto",
                "Seleziona un'entità o relazione proprietaria valida prima di confermare.",
            )
            owner.setFocus()
            return
        result.name = name_text.strip()
        if rich_editor:
            try:
                result.text_html = rich_editor.get_html()
                result.note_transparent = transparent.isChecked()
                result.note_background = background
            except ValueError as error:
                QMessageBox.warning(dialog, "Nota troppo complessa", str(error))
                return
        if owner is not None:
            result.parent_id = owner.currentData()
        if cardinality is not None:
            result.attribute_card = cardinality.currentText() if use_cardinality.isChecked() else None
        result.width = width.value()
        result.height = height.value()
        result.notes = notes.toPlainText().strip()
        if data_type is not None:
            try:
                normalized = normalize_type(data_type.currentText(), "postgresql")
            except ValueError as exc:
                QMessageBox.warning(dialog, "Tipo SQL non valido", str(exc))
                data_type.setFocus()
                return
            result.data_type = normalized
            result.is_pk = primary.isChecked()
            result.nullable = nullable.isChecked() and not result.is_pk
            result.unique = unique.isChecked()
            result.derived = derived.isChecked() and not result.is_pk
        if hierarchy is not None:
            result.isa_total, result.isa_disjoint = hierarchy.currentData()
        dialog.accept()

    buttons.accepted.connect(accept)
    name.selectAll()
    name.setFocus()
    return result if _run_dialog(dialog) else None


def edit_link(parent: QWidget | None, link: Link, doc: Document) -> Link | None:
    """Modifica cardinalità di partecipazione e ruolo di un collegamento."""
    result = deepcopy(link)
    source, target = doc.node(link.source), doc.node(link.target)
    dialog = QDialog(parent)
    dialog.setWindowTitle("Proprietà del collegamento")
    dialog.setMinimumWidth(480)
    layout = QVBoxLayout(dialog)
    form = QFormLayout()
    cards = {}
    if not any(node and node.kind == "isa" for node in (source, target)):
        two_entities = all(node and node.kind == "entity" for node in (source, target))
        for end, node in (("source", source), ("target", target)):
            if node and node.kind == "entity":
                field = end + "_card"
                cards[field] = _card_combo(getattr(link, field))
                form.addRow(f"Cardinalità · {node.name}" if two_entities
                            else "Cardinalità", cards[field])
    ports = {}
    if any(existing.id == link.id for existing in doc.links):
        for end, node in (("source", source), ("target", target)):
            if node and node.kind in ("entity", "relation", "multivalue"):
                field = end + "_port"
                combo = QComboBox()
                combo.addItem("Automatico", None)
                for label, side in zip(("Alto", "Destra", "Basso", "Sinistra"),
                                       ("top", "right", "bottom", "left")):
                    combo.addItem(label, side)
                combo.setCurrentIndex(combo.findData(getattr(link, field)))
                ports[field] = combo
                form.addRow(f"Attacco · {node.name}", combo)
    reset_route = QCheckBox("Ricalcola il percorso automaticamente")
    if ports and link.route_points:
        form.addRow("", reset_route)
    role = QLineEdit(link.role)
    role.setObjectName("linkRole")
    role.setMaxLength(1024)
    role.setPlaceholderText("Ad esempio: responsabile, subordinato")
    form.addRow("Ruolo / etichetta", role)
    layout.addLayout(form)
    if cards:
        layout.addWidget(_hint("Minimo e massimo di partecipazione. 0 = facoltativa, "
                               "1 = una sola, N = molte."))
    buttons = _buttons(dialog)
    layout.addWidget(buttons)

    def accept() -> None:
        for field, combo in cards.items():
            setattr(result, field, combo.currentText())
        changed_ports = any(combo.currentData() != getattr(link, field) for field, combo in ports.items())
        for field, combo in ports.items():
            setattr(result, field, combo.currentData())
        if changed_ports or reset_route.isChecked():
            result.route_points = []
        result.role = role.text().strip()
        dialog.accept()

    buttons.accepted.connect(accept)
    return result if _run_dialog(dialog) else None


def create_relationship(
    parent: QWidget | None, doc: Document
) -> tuple[Node, list[Link]] | None:
    """Crea una relazione binaria Chen, inclusi due ruoli per le auto-relazioni."""
    entities = [node for node in doc.nodes if node.kind == "entity"]
    if not entities:
        QMessageBox.information(
            parent, "Aggiungi un'entità", "Crea almeno un'entità prima della relazione."
        )
        return None
    dialog = QDialog(parent)
    dialog.setWindowTitle("Nuova relazione")
    dialog.setMinimumWidth(520)
    layout = QVBoxLayout(dialog)
    form = QFormLayout()
    name = QLineEdit("Relazione")
    name.setObjectName("relationName")
    name.setMaxLength(120)
    form.addRow("Nome", name)
    layout.addLayout(form)
    selectors: list[QComboBox] = []
    cards: list[QComboBox] = []
    roles: list[QLineEdit] = []
    for index in range(2):
        group = QGroupBox(f"Partecipazione {index + 1}")
        group_form = QFormLayout(group)
        selector = QComboBox()
        selector.setObjectName(f"entity{index}")
        for entity in entities:
            selector.addItem(entity.name, entity.id)
        selector.setCurrentIndex(min(index, len(entities) - 1))
        card = _card_combo("0,N")
        card.setObjectName(f"card{index}")
        role = QLineEdit()
        role.setObjectName(f"role{index}")
        role.setMaxLength(120)
        role.setPlaceholderText("Facoltativo; necessario per distinguere i ruoli ricorsivi")
        group_form.addRow("Entità", selector)
        group_form.addRow("Cardinalità (min, max)", card)
        group_form.addRow("Ruolo", role)
        selectors.append(selector)
        cards.append(card)
        roles.append(role)
        layout.addWidget(group)
    layout.addWidget(_hint(
        "Esempio: Studente (0,N) — Iscrizione — Corso (0,N) è una relazione N:M. "
        "Per una relazione 1:N, il lato «uno» partecipa a N occorrenze e il lato "
        "«molti» a una sola. Se scegli la stessa entità due volte, assegna due ruoli distinti."
    ))
    buttons = _buttons(dialog, "Crea relazione")
    layout.addWidget(buttons)
    created: tuple[Node, list[Link]] | None = None

    def accept() -> None:
        nonlocal created
        if not name.text().strip():
            QMessageBox.warning(dialog, "Nome richiesto", "Inserisci il nome della relazione.")
            name.setFocus()
            return
        first = doc.node(selectors[0].currentData())
        second = doc.node(selectors[1].currentData())
        if first is None or second is None:
            QMessageBox.warning(dialog, "Entità mancante", "Seleziona due entità valide.")
            return
        if first.id == second.id:
            role_names = [field.text().strip() for field in roles]
            if not all(role_names) or role_names[0].casefold() == role_names[1].casefold():
                QMessageBox.warning(
                    dialog, "Ruoli richiesti",
                    "Per una relazione ricorsiva assegna due ruoli diversi, "
                    "ad esempio responsabile e subordinato.",
                )
                return
        center_x = (first.x + first.width / 2 + second.x + second.width / 2) / 2
        center_y = (first.y + first.height / 2 + second.y + second.height / 2) / 2
        if first.id == second.id:
            center_y -= 180
        elif abs(first.y - second.y) < 100 and abs(first.x - second.x) < 280:
            center_y -= 150
        relation = Node(
            kind="relation", name=name.text().strip(),
            x=round((center_x - 80) / 20) * 20,
            y=center_y - 40,
            width=160, height=80,
        )
        links = [
            Link(
                source=entity.id, target=relation.id,
                source_card=cards[index].currentText(), target_card="0,N",
                role=roles[index].text().strip(),
            )
            for index, entity in enumerate((first, second))
        ]
        created = relation, links
        dialog.accept()

    buttons.accepted.connect(accept)
    name.selectAll()
    name.setFocus()
    return created if _run_dialog(dialog) else None


class SqlPreviewDialog(QDialog):
    """Anteprima SQL con copia ed esportazione esplicite."""

    def __init__(self, parent: QWidget | None, sql: str, dialect: str):
        super().__init__(parent)
        self.setWindowTitle(f"SQL preliminare · {dialect}")
        self.resize(900, 670)
        self.sql = sql
        layout = QVBoxLayout(self)
        layout.addWidget(_hint(
            "DDL generato dal modello ER. Controlla nomi, tipi e regole di dominio "
            "prima dell'uso in un database reale. Le partecipazioni minime globali "
            "e i vincoli ISA che richiedono trigger sono descritti nei commenti."
        ))
        self.editor = QPlainTextEdit(sql)
        self.editor.setReadOnly(True)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        layout.addWidget(self.editor, 1)
        actions = QHBoxLayout()
        copy = QPushButton("Copia SQL")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.sql))
        save = QPushButton("Salva .sql…")
        save.clicked.connect(self.save_sql)
        close = QPushButton("Chiudi")
        close.clicked.connect(self.accept)
        actions.addWidget(copy)
        actions.addWidget(save)
        actions.addStretch()
        actions.addWidget(close)
        layout.addLayout(actions)

    def save_sql(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Esporta SQL", "schema.sql", "Script SQL (*.sql)"
        )
        if not filename:
            return
        path = Path(filename)
        if not path.suffix:
            path = path.with_suffix(".sql")
        try:
            path.write_text(self.sql, encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Salvataggio non riuscito", str(exc))
            return
        QMessageBox.information(self, "SQL esportato", f"Script salvato in:\n{path}")


class HelpDialog(QDialog):
    """Guida locale: nessuna dipendenza dalla rete per studenti o esercitazioni."""

    def __init__(self, parent: QWidget | None):
        super().__init__(parent)
        self.setWindowTitle("Guida a DrawER Studio")
        self.resize(780, 690)
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setHtml("""
        <h1>DrawER <span style="color:gray">Studio</span></h1>
        <p>Disegna uno schema concettuale Entità–Relazione, verifica il modello ed
        esporta immagini o uno schema SQL preliminare. I progetti rimangono locali.</p>
        <h2>Costruire il diagramma</h2>
        <ol>
          <li><b>Entità [1]</b>: aggiungi un rettangolo e assegna un nome al concetto.</li>
          <li><b>Relazione [2]</b>: fai clic sul foglio per creare un rombo, poi collegalo
          alle entità. <b>Relazione guidata / Ctrl+R</b> crea direttamente rombo,
          partecipazioni, cardinalità e ruoli, anche per la stessa entità.</li>
          <li><b>Multivalore [3]</b>: fai clic sull'entità proprietaria per aggiungere un attributo che
          può assumere più valori, per esempio i numeri di telefono.</li>
          <li><b>ISA [4]</b>: fai clic sull'entità padre, aggiungi la generalizzazione
          e collega il nodo ISA alle entità figlie.</li>
          <li><b>Collega [5]</b>: fai clic sull'origine e poi sulla destinazione.
          Usa entità–relazione per una partecipazione oppure ISA–entità per un figlio.</li>
          <li><b>Attributo [6]</b>: fai clic sull'entità o relazione proprietaria per aggiungere un
          attributo. Puoi cliccare anche su un multivalore per aggiungerne i componenti.
          Contrassegna gli identificatori con <b>chiave primaria</b>.</li>
        </ol>
        <p>Il doppio clic su un elemento ne apre le proprietà. Puoi impostare nome,
        note, dimensioni e, per gli attributi, tipo SQL e vincoli. Un attributo derivato
        rimane nel diagramma ma non viene materializzato nello SQL.</p>
        <h2>Muoversi e modificare</h2>
        <ul>
          <li>Fai clic con il <b>sinistro</b> per selezionare un elemento o
          trascina per selezionare un'area. Trascina un attributo o una nota per spostarli. Tieni premuto <b>Ctrl</b> per estendere la selezione.</li>
          <li>Trascina con il <b>destro</b> per spostare la vista. Trascina un’entità
          col sinistro per spostarla insieme ai suoi attributi. Puoi usare
          <b>Maiusc+sinistro</b> per spostare qualsiasi figura selezionata.</li>
          <li>Le guide di allineamento agganciano bordi e centri durante lo spostamento.
          Puoi disattivarle da <b>Diagramma → Allineamento intelligente</b>.
          Trascina un angolo di una figura selezionata per ridimensionarla.</li>
          <li><b>Doppio clic sinistro</b> apre le proprietà; <b>Maiusc+destro</b>
          apre il menu contestuale.</li>
          <li>Ruota la rotella per lo zoom. Trascina con il tasto centrale o con
          Spazio premuto per spostare la vista.</li>
          <li><b>Canc</b> elimina gli elementi selezionati e i relativi collegamenti.
          Gli attributi di un'entità eliminata vengono eliminati insieme al padre.</li>
          <li><b>Ctrl+Z</b> annulla, <b>Ctrl+Maiusc+Z</b> ripristina,
          <b>Ctrl+S</b> salva e <b>Ctrl+O</b> apre un progetto.</li>
          <li><b>Ctrl+X</b> taglia, <b>Ctrl+C</b> copia e <b>Ctrl+V</b> incolla.
          <b>Ctrl+Y</b> ripristina una modifica annullata.</li>
          <li><b>Esc</b> interrompe lo strumento in uso e torna alla selezione.</li>
        </ul>
        <p>Usa <b>Griglia</b> nella barra in alto per mostrare o nascondere le linee
        di riferimento. Le linee non compaiono nelle esportazioni.</p>
        <h2>Collegamenti sul foglio</h2>
        <p>Trascina il nome di un attributo attorno al pallino per riposizionarlo.</p>
        <p>Passa il cursore su un oggetto e trascina una delle freccette che
        compaiono per collegarlo a un altro oggetto. Trascina direttamente una
        cardinalità, un ruolo o una sigla ISA per spostarla.
        Clicca su un arco per mostrare i cerchi agli attacchi e i quadrati
        sulle pieghe. I cerchi agganciano il centro di un lato dell'entità
        o una punta del rombo. I quadrati spostano le pieghe.
        Allinea i centri dal menu Diagramma per ottenere collegamenti diritti.
        Maiusc+destro sull'arco permette di ripristinare il percorso automatico.</p>
        <h2>Gerarchie ISA</h2>
        <p>Il triangolino punta al padre; i figli si collegano al punto di diramazione.
        Scegli <b>(t,s)</b> totale sovrapposta, <b>(t,d)</b> totale disgiunta,
        <b>(p,s)</b> parziale sovrapposta o <b>(p,d)</b> parziale disgiunta.</p>
        <h2>Note formattate</h2>
        <p>Con <b>Nota [7]</b> aggiungi testo al diagramma. Nelle proprietà della
        nota puoi selezionare parole o frasi e applicare <b>grassetto</b>,
        <i>corsivo</i>, <u>sottolineato</u> e barrato, scegliere carattere,
        dimensione, colore, allineamento ed elenchi. Le scorciatoie
        <b>Ctrl+B</b>, <b>Ctrl+I</b> e <b>Ctrl+U</b> funzionano nell'editor.
        La formattazione viene conservata nel progetto e nelle esportazioni.</p>
        <h2>Leggere le cardinalità</h2>
        <p>DrawER usa la notazione Chen con coppie <b>(minimo, massimo)</b> accanto
        all'entità. La coppia indica a quante occorrenze della relazione partecipa
        una singola istanza dell'entità: <b>(0,1)</b> zero o una,
        <b>(1,1)</b> esattamente una, <b>(0,N)</b> zero o molte,
        <b>(1,N)</b> almeno una.</p>
        <p>Esempio: <i>Docente (0,N) — Insegna — Corso (1,1)</i> significa che ogni
        docente può insegnare più corsi e ogni corso ha esattamente un docente.</p>
        <h2>Dal modello concettuale a SQL</h2>
        <p>Le entità diventano tabelle. Gli attributi chiave definiscono una PK,
        anche composta. Le relazioni 1:N diventano chiavi esterne sul lato N,
        le 1:1 aggiungono un vincolo UNIQUE e le N:M diventano tabelle associative.
        Gli attributi delle relazioni seguono la stessa trasformazione.
        Gli attributi multivalore delle entità diventano tabelle separate.</p>
        <p>L'esportazione ISA usa una tabella per tipo: la PK del figlio è anche FK
        verso il padre. Totalità e disgiunzione richiedono controlli ulteriori,
        come trigger o regole applicative. Anche l'obbligo che un'entità partecipi
        ad almeno una relazione può richiedere vincoli oltre alle sole FK.</p>
        <p>La validazione segnala schemi incompleti o ambigui. Le relazioni con più
        di due partecipazioni e gli aggregati multivalore annidati richiedono
        una trasformazione esplicita prima dell'esportazione SQL.</p>
        <h2>Salvare ed esportare</h2>
        <p>Il formato <b>.erdraw</b> conserva il progetto modificabile. Puoi aprire
        anche i progetti JSON della versione web. Il PNG ha sfondo bianco e segue
        i bordi del contenuto. SVG preserva la qualità vettoriale.
        SQL è disponibile per SQLite e PostgreSQL.</p>
        <h2>Guida didattica ed esercizi</h2>
        <p>Da <b>Aiuto → Guida didattica</b> puoi riprendere il percorso
        introduttivo e provarne i passaggi sul foglio. In <b>Aiuto → Esercizi
        formativi</b> trovi tracce con suggerimenti e schemi di partenza facoltativi.</p>
        """)
        layout.addWidget(browser, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Chiudi")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
