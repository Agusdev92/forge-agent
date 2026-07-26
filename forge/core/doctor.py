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

    @property
    def scored_checks(self) -> list:
        return [c for c in self.checks if c.scored]

    @property
    def informational_checks(self) -> list:
        return [c for c in self.checks if not c.scored]

    def to_dict(self) -> dict:
        """Los datos derivados van explícitos, y las dos clases de check separadas.

        `score`, `total` y `healthy` son propiedades, así que `asdict()` las
        omitiría — y son justo lo que un consumidor necesita. Dejarlas fuera
        obligaría a cada consumidor a reimplementar la regla de puntaje, que
        es exactamente la duplicación que `core/checks.py` vino a eliminar.

        Los checks informativos van en su propia lista en vez de marcados con
        un flag. Ver `CheckResult.to_dict` para el error que motivó el cambio.
        """
        return {
            "path": str(self.path),
            "score": self.score,
            "total": self.total,
            "healthy": self.healthy,
            "checks": [c.to_dict() for c in self.scored_checks],
            "informational": [c.to_dict() for c in self.informational_checks],
            "informational_note": (
                "Los checks de 'informational' se reportan pero no afectan el "
                "puntaje, porque describen el entorno de quien ejecuta y no el "
                "proyecto. Un 'passed': true ahí significa que está presente."
            ),
        }


class Doctor:
    def __init__(self, path="."):
        self.path = path

    def check(self) -> DoctorReport:
        return DoctorReport(path=self.path, checks=run_checks(self.path))
