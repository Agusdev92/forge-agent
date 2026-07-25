"""Árbol de directorios del proyecto."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from forge.core.filesystem import is_ignored

DEFAULT_MAX_DEPTH = 3


@dataclass(frozen=True)
class TreeEntry:
    name: str
    is_directory: bool
    depth: int


class Tree:
    def __init__(self, path=".", max_depth: int = DEFAULT_MAX_DEPTH):
        self.path = Path(path)
        self.max_depth = max_depth

    def build(self) -> list:
        """Construye el árbol hasta `max_depth` niveles.

        La versión anterior listaba un solo nivel pese a llamarse `tree`. El
        límite de profundidad existe para que la salida siga siendo legible en
        proyectos grandes.
        """
        entries: list = []
        self._walk(self.path, depth=0, entries=entries)
        return entries

    def _walk(self, directory: Path, depth: int, entries: list) -> None:
        if depth >= self.max_depth:
            return

        try:
            children = sorted(
                directory.iterdir(), key=lambda p: (p.is_file(), p.name)
            )
        except OSError:
            return

        for child in children:
            if child.name.startswith(".") or is_ignored(child.name):
                continue

            entries.append(
                TreeEntry(
                    name=child.name, is_directory=child.is_dir(), depth=depth
                )
            )

            if child.is_dir():
                self._walk(child, depth + 1, entries)
