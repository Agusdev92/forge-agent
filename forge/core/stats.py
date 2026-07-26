"""Métricas de tamaño del proyecto."""

from __future__ import annotations

from dataclasses import dataclass

from forge.core.filesystem import walk
from forge.core.project import Project


@dataclass(frozen=True)
class StatsReport:
    language: str
    directories: int
    files: int

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "directories": self.directories,
            "files": self.files,
        }


class Stats:
    def __init__(self, path="."):
        self.path = path

    def show(self) -> StatsReport:
        """Cuenta carpetas y archivos del proyecto.

        Usa `filesystem.walk`, que poda los directorios ignorados. La versión
        anterior llamaba a `os.walk` directamente y contaba `.git` y `.venv`:
        sobre este mismo repo reportaba 101 archivos donde hay 31.
        """
        directories = 0
        files = 0

        for _, dirnames, filenames in walk(self.path):
            directories += len(dirnames)
            files += len(filenames)

        return StatsReport(
            language=Project(self.path).detect_language(),
            directories=directories,
            files=files,
        )
