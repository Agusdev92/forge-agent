"""Análisis general de un proyecto."""

from __future__ import annotations

from dataclasses import dataclass

from forge.core.checks import run_checks
from forge.core.filesystem import FileSystem, absolute, exists, iter_files, join

UNKNOWN_LANGUAGE = "Desconocido"


@dataclass(frozen=True)
class ProjectReport:
    path: str
    language: str
    checks: list
    directories: list
    files: list

    def to_dict(self) -> dict:
        """Misma separación que `DoctorReport`: informativos aparte."""
        return {
            "path": self.path,
            "language": self.language,
            "checks": [c.to_dict() for c in self.checks if c.scored],
            "informational": [c.to_dict() for c in self.checks if not c.scored],
            "directories": list(self.directories),
            "files": list(self.files),
        }


class Project:
    def __init__(self, path="."):
        self.path = path

    def detect_language(self) -> str:
        """Detecta el lenguaje por manifiesto y, si no hay, por extensiones.

        El fallback por extensión existe porque antes un proyecto Python sin
        `requirements.txt` se reportaba como "Desconocido" aunque estuviera
        lleno de archivos `.py`. También se agregó `pyproject.toml`, que es el
        estándar actual de empaquetado y que la versión anterior ignoraba.
        """
        for manifest, language in (
            ("pyproject.toml", "Python"),
            ("requirements.txt", "Python"),
            ("setup.py", "Python"),
            ("package.json", "Node.js"),
        ):
            if exists(join(self.path, manifest)):
                return language

        for suffix, language in ((".py", "Python"), (".js", "Node.js")):
            if next(iter_files(self.path, suffix), None) is not None:
                return language

        return UNKNOWN_LANGUAGE

    def analyze(self) -> ProjectReport:
        fs = FileSystem(self.path)
        return ProjectReport(
            path=absolute(self.path),
            language=self.detect_language(),
            checks=run_checks(self.path),
            directories=fs.list_directories(),
            files=fs.list_files(),
        )
