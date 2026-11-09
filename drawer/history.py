"""Cronologia indipendente dalla GUI: una transazione per gesto dell'utente."""
import json

from .model import Document


class History:
    def __init__(self, document: Document, limit: int = 150):
        self.limit = limit
        self.states = [self.signature(document)]
        self.index = 0

    @staticmethod
    def signature(document: Document) -> str:
        return json.dumps(document.to_dict(), sort_keys=True, ensure_ascii=False)

    def push(self, document: Document) -> bool:
        state = self.signature(document)
        if state == self.states[self.index]:
            return False
        self.states = self.states[:self.index + 1] + [state]
        self.states = self.states[-self.limit:]
        self.index = len(self.states) - 1
        return True

    def update_filename_title(self, previous: str, title: str):
        """Aggiorna il titolo automatico senza aggiungere un passo di modifica."""
        for index, state in enumerate(self.states):
            snapshot = json.loads(state)
            if snapshot["title"] == previous:
                snapshot["title"] = title
                self.states[index] = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)

    @property
    def can_undo(self):
        return self.index > 0

    @property
    def can_redo(self):
        return self.index < len(self.states) - 1

    def undo(self):
        if self.can_undo:
            self.index -= 1
        return Document.from_dict(json.loads(self.states[self.index]))

    def redo(self):
        if self.can_redo:
            self.index += 1
        return Document.from_dict(json.loads(self.states[self.index]))
