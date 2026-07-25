"""Checks de salud de un proyecto, expresados como datos.

Antes existían dos implementaciones de los mismos checks —una en `Project`,
otra en `Doctor`— con código distinto. En el primer cambio que tocara una sola
de las dos, `forge analyze` y `forge doctor` habrían empezado a contradecirse
sobre el mismo proyecto. Acá hay una sola definición y ambos comandos la
consumen.

Los checks tienen tres estados en vez de dos: un `README.md` de 0 bytes existe
pero no documenta nada, y darle ✅ hacía que el health score midiera presencia
de archivos en lugar de salud.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from forge.core.filesystem import has_content, is_dir, join

#: Archivos que declaran las dependencias de un proyecto Python.
DEPENDENCY_MANIFESTS = ("pyproject.toml", "requirements.txt")


class Status(str, Enum):
    OK = "ok"
    WARNING = "warning"
    MISSING = "missing"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.status is Status.OK


def _directory_check(root, name: str, label: str) -> CheckResult:
    if is_dir(join(root, name)):
        return CheckResult(label, Status.OK)
    return CheckResult(label, Status.MISSING, f"falta {name}/")


def _file_check(root, name: str) -> CheckResult:
    path = Path(join(root, name))
    if has_content(path):
        return CheckResult(name, Status.OK)
    if path.is_file():
        return CheckResult(name, Status.WARNING, "existe pero está vacío")
    return CheckResult(name, Status.MISSING, "no existe")


def _dependency_check(root) -> CheckResult:
    label = "Dependencias declaradas"

    present = [m for m in DEPENDENCY_MANIFESTS if Path(join(root, m)).is_file()]
    if not present:
        return CheckResult(
            label, Status.MISSING, "ni pyproject.toml ni requirements.txt"
        )

    with_content = [m for m in present if has_content(join(root, m))]
    if not with_content:
        return CheckResult(
            label, Status.WARNING, f"{present[0]} existe pero está vacío"
        )

    return CheckResult(label, Status.OK, with_content[0])


def run_checks(root=".") -> list:
    """Ejecuta todos los checks sobre `root`, en orden de importancia."""
    return [
        _directory_check(root, ".git", "Git"),
        _dependency_check(root),
        _directory_check(root, "tests", "tests"),
        _file_check(root, "README.md"),
        _file_check(root, ".gitignore"),
        _directory_check(root, ".venv", "Entorno virtual"),
    ]
