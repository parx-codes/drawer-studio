"""Bounded JSON loading and atomic, UTF-8 project persistence."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from .model import Document

MAX_FILE_BYTES = 20 * 1024 * 1024


def load_document(path: str | Path) -> Document:
    target = Path(path)
    if target.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Il progetto supera il limite di 20 MiB.")
    with target.open("rb") as stream:
        content = stream.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("Il progetto supera il limite di 20 MiB.")
    try:
        data = json.loads(content.decode("utf-8-sig"), parse_constant=_reject_constant,
                          object_pairs_hook=_unique_keys)
        return Document.from_dict(data)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, TypeError) as error:
        raise ValueError(f"File progetto non valido: {error}") from error


def _reject_constant(value: str):
    raise ValueError(f"Valore JSON non valido: {value}.")


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Chiave JSON duplicata: {key}.")
        result[key] = value
    return result


def save_document(doc: Document, path: str | Path) -> None:
    """Write beside the destination, fsync, and replace only after success.

    A failed save leaves the previous file intact. No directory is created
    implicitly, and any incomplete temporary file is removed.
    """
    data = doc.to_dict()
    Document.from_dict(data)  # Catch broken references before replacing a file.
    content = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("Il progetto supera il limite di 20 MiB.")
    target = Path(path)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=target.parent, prefix=f".{target.name}.",
                                         suffix=".tmp", delete=False) as stream:
            temporary = stream.name
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
