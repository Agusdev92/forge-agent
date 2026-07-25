"""Acceso al sistema de archivos.

Toda lectura de disco pasa por este módulo, incluido el filtrado de los
directorios que no forman parte del proyecto (`.git`, `.venv`, `__pycache__`...).

Centralizar el filtrado es deliberado: antes cada analizador recorría el árbol
por su cuenta y ninguno excluía nada, así que `stats` y `scan` contaban el
contenido de `.git` como código del proyecto. Con el recorrido acá, un
analizador nuevo hereda las exclusiones en vez de tener que recordarlas.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator, Optional

#: Directorios que nunca forman parte del código de un proyecto.
IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "node_modules",
        "build",
        "dist",
        ".eggs",
    }
)


def exists(path) -> bool:
    return Path(path).exists()


def is_dir(path) -> bool:
    return Path(path).is_dir()


def join(*paths) -> str:
    return os.path.join(*paths)


def absolute(path) -> str:
    return str(Path(path).resolve())


def is_ignored(name: str) -> bool:
    # `*.egg-info` se genera al instalar en modo editable: es artefacto de
    # build, no código del proyecto, y su nombre depende del paquete.
    return name in IGNORED_DIRS or name.endswith(".egg-info")


def has_content(path) -> bool:
    """True si el archivo existe y tiene algo más que espacios en blanco.

    Un `README.md` de 0 bytes cumple `exists()` pero no documenta nada; los
    checks necesitan distinguir "está" de "sirve".
    """
    file = Path(path)
    if not file.is_file():
        return False
    try:
        return bool(file.read_text(encoding="utf-8", errors="ignore").strip())
    except OSError:
        return False


def walk(root) -> Iterator[tuple]:
    """Como `os.walk`, pero podando los directorios ignorados.

    Devuelve `(Path, dirnames, filenames)` con ambas listas ordenadas.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not is_ignored(d))
        yield Path(dirpath), dirnames, sorted(filenames)


def iter_files(root, suffix: Optional[str] = None) -> Iterator[Path]:
    """Itera los archivos del proyecto, opcionalmente filtrando por extensión."""
    for dirpath, _, filenames in walk(root):
        for name in filenames:
            if suffix is None or name.endswith(suffix):
                yield dirpath / name


class FileSystem:
    """Listado de un único nivel, ya filtrado."""

    def __init__(self, path="."):
        self.path = Path(path)

    def list_files(self) -> list:
        return sorted(p.name for p in self.path.iterdir() if p.is_file())

    def list_directories(self) -> list:
        return sorted(
            p.name
            for p in self.path.iterdir()
            if p.is_dir() and not is_ignored(p.name)
        )
