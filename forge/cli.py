"""Interfaz de línea de comandos.

Esta capa hace tres cosas y ninguna más: parsear argumentos, llamar a `core/` y
renderizar el resultado. La lógica de análisis no vive acá.
"""

from __future__ import annotations

import typer

from forge import render
from forge.core.doctor import Doctor
from forge.core.project import Project
from forge.core.scanner import Scanner
from forge.core.stats import Stats
from forge.core.tree import DEFAULT_MAX_DEPTH, Tree

__version__ = "0.1.0"

app = typer.Typer(help="Forge Agent — análisis de proyectos de software")

PathOption = typer.Option(".", "--path", "-p", help="Ruta del proyecto")


@app.command()
def version():
    """Muestra la versión de Forge."""
    typer.echo(f"Forge Agent v{__version__}")


@app.command()
def analyze(path: str = PathOption):
    """Analiza un proyecto."""
    typer.echo(render.render_project(Project(path).analyze()))


@app.command()
def doctor(path: str = PathOption):
    """Revisa el estado de salud del proyecto."""
    typer.echo(render.render_doctor(Doctor(path).check()))


@app.command()
def tree(
    path: str = PathOption,
    depth: int = typer.Option(
        DEFAULT_MAX_DEPTH, "--depth", "-d", help="Profundidad máxima"
    ),
):
    """Muestra el árbol del proyecto."""
    typer.echo(render.render_tree(Tree(path, max_depth=depth).build()))


@app.command()
def stats(path: str = PathOption):
    """Muestra estadísticas del proyecto."""
    typer.echo(render.render_stats(Stats(path).show()))


@app.command()
def scan(path: str = PathOption):
    """Escanea el código en busca de deuda visible."""
    typer.echo(render.render_scan(Scanner(path).scan()))


if __name__ == "__main__":
    app()
