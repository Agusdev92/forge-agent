"""Escaneo del código fuente en busca de deuda visible."""

from __future__ import annotations

import io
import re
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

from forge.core.filesystem import iter_files

#: Marcador dentro de un comentario ya aislado.
TODO_PATTERN = re.compile(r"\b(TODO|FIXME)\b")

#: Fallback para archivos que no tokenizan (sintaxis inválida, Python 2...).
#: Menos preciso, pero es preferible a no reportar nada sobre ese archivo.
COMMENT_PATTERN = re.compile(r"#\s*(TODO|FIXME)\b")

#: Un `__init__.py` vacío es un marcador de paquete válido, no deuda técnica.
ALLOWED_EMPTY = frozenset({"__init__.py"})


def count_markers(text: str) -> int:
    """Cuenta TODO/FIXME que estén realmente en comentarios.

    Tokeniza en vez de buscar texto. Las dos versiones anteriores basadas en
    búsqueda de subcadena dieron falsos positivos: primero contaban la palabra
    "TODO" en cualquier posición (incluida la definición de los marcadores de
    este módulo), después contaban `# TODO` dentro de literales de string —
    los propios tests de Forge inflaban la métrica con sus datos de prueba.

    Dos rondas de falsos positivos sobre la misma métrica indican que buscar
    texto es la herramienta equivocada: solo el tokenizador sabe qué es un
    comentario y qué es un string que se le parece.
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError, IndentationError, ValueError):
        return len(COMMENT_PATTERN.findall(text))

    return sum(
        len(TODO_PATTERN.findall(token.string))
        for token in tokens
        if token.type == tokenize.COMMENT
    )


@dataclass(frozen=True)
class ScanReport:
    python_files: int
    todos: int
    empty_files: int
    files_with_todos: list = field(default_factory=list)
    empty_paths: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "python_files": self.python_files,
            "todos": self.todos,
            "empty_files": self.empty_files,
            "files_with_todos": list(self.files_with_todos),
            "empty_paths": list(self.empty_paths),
        }


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

            found = count_markers(text)
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
