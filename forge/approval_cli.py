"""Compuerta de aprobación interactiva para la terminal.

Es la implementación concreta del `approver` que `forge/tools/` consulta antes
de cada escritura. Vive fuera de `tools/` porque es presentación: muestra el
diff y pregunta. Otro consumidor —una interfaz gráfica, un pipeline— pondría
otra implementación sin tocar la lógica de las herramientas.
"""

from __future__ import annotations

import typer


def confirm_write(request) -> bool:
    """Muestra el cambio y pide confirmación explícita.

    El default de la pregunta es "no": ante un enter distraído, no se escribe.
    """
    verb = "Reemplazar" if request.is_overwrite else "Crear"
    typer.secho(f"\n✏️  {verb} {request.path}", fg=typer.colors.YELLOW, bold=True)

    diff = request.diff()
    if diff:
        typer.echo()
        for line in diff.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                typer.secho(line, fg=typer.colors.GREEN)
            elif line.startswith("-") and not line.startswith("---"):
                typer.secho(line, fg=typer.colors.RED)
            else:
                typer.echo(line)

    typer.echo()
    return typer.confirm("¿Aplicar este cambio?", default=False)


def approve_everything(request) -> bool:
    """Aprueba sin preguntar. Solo con `--yes` explícito."""
    typer.secho(
        f"✏️  {'Reemplazando' if request.is_overwrite else 'Creando'} {request.path} "
        "(--yes)",
        fg=typer.colors.YELLOW,
    )
    return True
