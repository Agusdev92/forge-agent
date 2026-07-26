"""Aprobación humana para las escrituras.

Escribir archivos es la única acción irreversible que hace Forge, así que pasa
por una compuerta explícita. El modelo no la puede saltear: la política se fija
al construir las herramientas, no es un parámetro que el modelo elija.

**El default es denegar.** Si alguien construye las herramientas sin pasar un
aprobador, las escrituras fallan en vez de ejecutarse — una compuerta que se
abre sola cuando se la olvida configurar no es una compuerta.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Optional

CREATE = "create"
OVERWRITE = "overwrite"


@dataclass(frozen=True)
class WriteRequest:
    """Una escritura pendiente de aprobación."""

    path: str
    action: str
    content: str
    previous_content: Optional[str] = None

    @property
    def is_overwrite(self) -> bool:
        return self.action == OVERWRITE

    def diff(self) -> str:
        """Diff unificado para que la decisión se tome viendo el cambio.

        Aprobar a ciegas es igual a no tener compuerta, así que quien decide
        necesita ver exactamente qué se va a escribir.
        """
        before = (self.previous_content or "").splitlines(keepends=True)
        after = self.content.splitlines(keepends=True)

        return "".join(
            difflib.unified_diff(
                before,
                after,
                fromfile=f"a/{self.path}" if self.is_overwrite else "/dev/null",
                tofile=f"b/{self.path}",
            )
        )


def deny_all(request: WriteRequest) -> bool:
    """Política por defecto: ninguna escritura se ejecuta."""
    return False


def allow_all(request: WriteRequest) -> bool:
    """Aprueba todo. Solo para tests — nunca como default de la CLI."""
    return True
