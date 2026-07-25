"""Escaneo del código fuente en busca de deuda visible."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from forge.core.filesystem import iter_files

#: Solo cuentan los marcadores en comentarios. Buscar la subcadena "TODO" suelta
#: daba falsos positivos con cualquier código que mencionara la palabra —
#: incluido este propio módulo.
TODO_PATTERN = re.compile(r"#\s*(TODO|FIXME)\b")

#: Un `__init__.py` vacío es un marcador de paquete válido, no deuda técnica.
ALLOWED_EMPTY = frozenset({"__init__.py"})


@dataclass(frozen=True)
class ScanReport:
    python_files: int
    todos: int
    empty_files: int
    files_with_todos: list = field(default_factory=list)
    empty_paths: list = field(default_factory=list)


class Scanner:
    def __init__(self, path="."):
        self.path = Path(path)

    def scan(self) -> ScanReport:
        """Recorre los `.py` del proyecto contando TODOs y archivos vacíos.

        Usa `filesystem.iter_files` en vez de `rglob` para no entrar en `.venv`:
        antes, sobre un proyecto con dependencias instaladas, este comando
        reportaba los TODO de las librerías de terceros como deuda propia.
        """
        todos = 0
        empty_paths = []
        files_with_todos = []
        total = 0

        for file in iter_files(self.path, ".py"):
            total += 1
            try:
                text = file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            if not text.strip() and file.name not in ALLOWED_EMPTY:
                empty_paths.append(str(file))

            found = len(TODO_PATTERN.findall(text))
            if found:
                todos += found
                files_with_todos.append(str(file))

        return ScanReport(
            python_files=total,
            todos=todos,
            empty_files=len(empty_paths),
            files_with_todos=sorted(files_with_todos),
            empty_paths=sorted(empty_paths),
        )
