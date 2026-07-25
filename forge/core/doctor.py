"""Diagnóstico de salud del proyecto."""

from __future__ import annotations

from dataclasses import dataclass

from forge.core.checks import Status, run_checks


@dataclass(frozen=True)
class DoctorReport:
    path: str
    checks: list

    @property
    def score(self) -> int:
        """Solo los checks puntuables en OK suman.

        Las advertencias no dan puntaje parcial a propósito: un `README.md`
        vacío no documenta a medias, no documenta.
        """
        return sum(1 for c in self.checks if c.scored and c.passed)

    @property
    def total(self) -> int:
        return sum(1 for c in self.checks if c.scored)

    @property
    def warnings(self) -> list:
        return [c for c in self.checks if c.status is Status.WARNING]

    @property
    def healthy(self) -> bool:
        """True si todos los checks puntuables pasan. Lo usa `--strict`."""
        return self.score == self.total


class Doctor:
    def __init__(self, path="."):
        self.path = path

    def check(self) -> DoctorReport:
        return DoctorReport(path=self.path, checks=run_checks(self.path))
