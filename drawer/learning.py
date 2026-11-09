"""Percorso didattico e tracce di esercitazione utilizzabili sul foglio."""
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDockWidget, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .model import Document, Node


LESSONS = (
    ("Riconosci le entità", "Scegli Entità oppure premi 1. Fai clic sul foglio e assegna "
     "un nome all’oggetto che vuoi rappresentare, per esempio Cliente."),
    ("Aggiungi un identificatore", "Premi 6 e fai clic sull’entità. Aggiungi un attributo "
     "come id_cliente e contrassegnalo come chiave primaria."),
    ("Collega due concetti", "Crea una seconda entità e usa Relazione guidata. Decidi per "
     "ciascuna entità quante volte ogni sua istanza può partecipare."),
    ("Controlla il risultato", "Premi F7 per verificare lo schema. Se vuoi conservare il "
     "diagramma premi Ctrl+S, oppure scegli PNG dal menu Esporta."),
)


@dataclass(frozen=True)
class Exercise:
    title: str
    entities: tuple[str, ...]
    prompt: str
    hint: str

    def starter(self):
        nodes = [Node(name=name, x=160 + index * 300, y=240)
                 for index, name in enumerate(self.entities)]
        return Document(title=self.title, nodes=nodes)


EXERCISES = (
    Exercise("Clienti e ordini", ("Cliente", "Ordine"),
             "Ogni ordine appartiene a un solo cliente. Un cliente può effettuare più ordini. "
             "Aggiungi una chiave a ogni entità, disegna la relazione e indica le cardinalità.",
             "Cliente partecipa con (0,N) e Ordine con (1,1). La chiave esterna va in Ordine."),
    Exercise("Studenti e corsi", ("Studente", "Corso"),
             "Ogni studente può iscriversi a più corsi e ogni corso può accogliere più studenti. "
             "Registra la data di ogni iscrizione e verifica lo schema.",
             "Usa la relazione Iscrizione con (0,N) da entrambi i lati. La data è un attributo "
             "della relazione e finisce nella tabella associativa."),
    Exercise("Persone e recapiti", ("Persona", "Studente", "Lavoratore"),
             "Una persona può essere studente, lavoratore, entrambi o nessuno dei due. "
             "Ogni persona può avere più recapiti, ciascuno con tipo e valore. Disegna la "
             "gerarchia e l’aggregato multivalore.",
             "Scegli ISA parziale sovrapposta (p,s). Collega Studente e Lavoratore alla "
             "diramazione. Aggiungi tipo e valore al multivalore Recapiti di Persona."),
)


class LearningDock(QDockWidget):
    starter_requested = Signal(object)

    def __init__(self, parent):
        super().__init__("Guida didattica", parent)
        self.setAllowedAreas(Qt.TopDockWidgetArea | Qt.BottomDockWidgetArea)
        self._step = 0
        self._exercise = None
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.title = QLabel()
        self.title.setObjectName("title")
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setTextFormat(Qt.PlainText)
        self.context = QLabel()
        self.context.setWordWrap(True)
        self.context.setTextFormat(Qt.PlainText)
        self.context.setObjectName("muted")
        for label in (self.title, self.description, self.context):
            layout.addWidget(label)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.starter = QPushButton("Apri schema di partenza")
        self.tip = QPushButton("Mostra suggerimento")
        self.back = QPushButton("Indietro")
        self.next = QPushButton("Avanti")
        self.skip = QPushButton("Salta guida")
        for button in (self.starter, self.tip, self.back, self.next, self.skip):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.starter.clicked.connect(self._request_starter)
        self.tip.clicked.connect(self._toggle_tip)
        self.back.clicked.connect(self._previous_lesson)
        self.next.clicked.connect(self._next_lesson)
        self.skip.clicked.connect(self.hide)
        self.setWidget(panel)
        self.hide()

    def start_tutorial(self):
        self._step = 0
        self._exercise = None
        self.setWindowTitle("Guida didattica")
        self._show_lesson()
        self.show()
        self.raise_()

    def open_exercise(self, exercise):
        self._exercise = exercise
        self.setWindowTitle("Esercizio formativo")
        self.title.setText(exercise.title)
        self.description.setText(exercise.prompt)
        self.context.hide()
        self.tip.setText("Mostra suggerimento")
        self._set_buttons(exercise=True)
        self.show()
        self.raise_()

    def update_context(self, scene):
        if self._exercise is not None:
            return
        mode_help = {
            'entity': 'Clicca sul foglio per collocare la nuova entità.',
            'attribute': 'Clicca sull’oggetto a cui appartiene l’attributo.',
            'connect': 'Clicca sull’origine e poi sull’oggetto da collegare.',
            'isa': 'Scegli il padre della gerarchia e imposta il tipo di specializzazione.',
        }
        selected = scene.selectedItems()
        item = selected[0] if len(selected) == 1 else None
        if scene.mode in mode_help:
            message = mode_help[scene.mode]
        elif getattr(getattr(item, 'node', None), 'kind', None) == 'entity':
            message = 'Entità selezionata. Puoi aggiungere una chiave o usare una freccetta per collegarla.'
        elif getattr(item, 'link', None):
            message = 'Collegamento selezionato. Doppio clic per modificare le proprietà.'
        else:
            message = 'I passaggi della guida si possono provare direttamente sul foglio.'
        self.context.setText(message)

    def _set_buttons(self, *, exercise):
        self.starter.setVisible(exercise)
        self.tip.setVisible(exercise)
        self.back.setVisible(not exercise)
        self.next.setVisible(not exercise)
        self.skip.setText("Chiudi esercizio" if exercise else "Salta guida")

    def _show_lesson(self):
        title, description = LESSONS[self._step]
        self.title.setText(f"{self._step + 1}/{len(LESSONS)}  {title}")
        self.description.setText(description)
        self.context.show()
        self._set_buttons(exercise=False)
        self.back.setEnabled(self._step > 0)
        self.next.setText("Fine" if self._step == len(LESSONS) - 1 else "Avanti")

    def _previous_lesson(self):
        self._step -= 1
        self._show_lesson()

    def _next_lesson(self):
        if self._step == len(LESSONS) - 1:
            self.hide()
        else:
            self._step += 1
            self._show_lesson()

    def _request_starter(self):
        self.starter_requested.emit(self._exercise)

    def _toggle_tip(self):
        visible = self.context.isHidden()
        self.context.setText(self._exercise.hint)
        self.context.setVisible(visible)
        self.tip.setText("Nascondi suggerimento" if visible else "Mostra suggerimento")
