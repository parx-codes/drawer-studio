"""HTML locale per le note: formato limitato, senza risorse o contenuti attivi.

Questo modulo non importa Qt, così il modello dei progetti rimane utilizzabile
anche da script e test che non avviano l'interfaccia grafica.
"""
from html import escape
from html.parser import HTMLParser
import re

MAX_NOTE_TEXT = 16_384
MAX_NOTE_HTML = 131_072

_TAGS = {'p', 'br', 'span', 'b', 'strong', 'i', 'em', 'u', 's', 'strike',
         'div', 'ul', 'ol', 'li', 'sub', 'sup'}
_BLOCKED = {'head', 'script', 'style', 'iframe', 'object', 'embed', 'svg', 'math'}
_COLORS = re.compile(r'(?:#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?(?:[0-9a-fA-F]{2})?|[A-Za-z]{1,24})\Z')


def _style(raw: str) -> str:
    """Conserva solo proprietà tipografiche; URL ed espressioni non transitano."""
    result = {}
    for part in raw.split(';'):
        if ':' not in part:
            continue
        key, value = (piece.strip() for piece in part.split(':', 1))
        key = key.lower()
        lower = value.lower()
        if not value or any(char in value for char in '<>\\@') or 'url' in lower or 'expression' in lower:
            continue
        valid = False
        if key == 'font-family':
            valid = bool(re.fullmatch(r"[\w .,'\"-]{1,160}", value))
        elif key == 'font-size':
            match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(pt|px)', lower)
            valid = bool(match and 6 <= float(match[1]) <= 128)
        elif key == 'font-weight':
            valid = bool(re.fullmatch(r'(?:normal|bold|bolder|lighter|[1-9]00)', lower))
        elif key == 'font-style':
            valid = lower in {'normal', 'italic', 'oblique'}
        elif key == 'color':
            valid = bool(_COLORS.fullmatch(value))
        elif key == 'text-decoration':
            valid = all(piece in {'none', 'underline', 'line-through', 'overline'} for piece in lower.split())
        elif key == 'text-align':
            valid = lower in {'left', 'right', 'center', 'justify'}
        elif key == 'vertical-align':
            valid = lower in {'sub', 'super', 'baseline'}
        elif key == 'white-space':
            valid = lower in {'normal', 'pre', 'pre-wrap'}
        elif key == '-qt-paragraph-type':
            # Qt distingue il paragrafo vuoto da un'interruzione <br> interna.
            # Conservare il marcatore evita di duplicare le righe a ogni apertura.
            valid = lower == 'empty'
        elif key == 'list-style-type':
            valid = lower in {'disc', 'circle', 'square', 'decimal', 'lower-alpha', 'upper-alpha', 'lower-roman', 'upper-roman'}
        elif key in {'margin-top', 'margin-bottom', 'margin-left', 'margin-right', 'text-indent'}:
            match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*px', lower)
            valid = bool(match and float(match[1]) <= 128)
        if valid:
            result[key] = value
    return ';'.join(f'{key}:{result[key]}' for key in sorted(result))


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.stack = []
        self.blocked = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _BLOCKED:
            self.blocked.append(tag)
            return
        if self.blocked:
            return
        output_tag = 'div' if tag == 'body' else 'span' if tag == 'font' else tag
        if output_tag not in _TAGS:
            return
        attributes = dict(attrs)
        style = attributes.get('style') or ''
        if output_tag in {'p', 'li'}:
            # Qt esporta questa regola nel blocco <style> globale: la portiamo
            # nel frammento locale per non perdere spazi ripetuti e tabulazioni.
            style += ';white-space:pre-wrap'
        if tag == 'font':
            if attributes.get('face'):
                style += ';font-family:' + attributes['face']
            if attributes.get('color'):
                style += ';color:' + attributes['color']
        if attributes.get('align'):
            style += ';text-align:' + attributes['align']
        safe_style = _style(style)
        rendered = (' style="' + escape(safe_style, quote=True) + '"') if safe_style else ''
        if output_tag == 'ol' and re.fullmatch(r'[1-9]\d{0,2}', attributes.get('start') or ''):
            rendered += ' start="' + attributes['start'] + '"'
        self.output.append('<' + output_tag + rendered + '>')
        if output_tag != 'br':
            self.stack.append((tag, output_tag))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() != 'br':
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.blocked:
            if tag in self.blocked:
                self.blocked = self.blocked[:self.blocked.index(tag)]
            return
        matching = next((index for index in range(len(self.stack)-1, -1, -1) if self.stack[index][0] == tag), None)
        if matching is not None:
            while len(self.stack) > matching:
                self.output.append('</' + self.stack.pop()[1] + '>')

    def handle_data(self, data):
        if not self.blocked:
            self.output.append(escape(data, quote=False))

    def finish(self):
        while self.stack:
            self.output.append('</' + self.stack.pop()[1] + '>')
        return ''.join(self.output).strip()


def sanitize_note_html(value: str) -> str:
    """Normalizza un frammento HTML mantenendo solo testo e stili tipografici."""
    if not isinstance(value, str) or '\x00' in value or len(value) > MAX_NOTE_HTML:
        raise ValueError('La nota formattata non è valida o supera 128 KiB di testo HTML.')
    parser = _Sanitizer()
    parser.feed(value)
    parser.close()
    result = parser.finish()
    if len(result) > MAX_NOTE_HTML:
        raise ValueError('La nota formattata supera il limite di 128 KiB.')
    return result
