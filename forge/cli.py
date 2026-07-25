"""Interfaz de línea de comandos.

Esta capa hace tres cosas y ninguna más: parsear argumentos, llamar a `core/` y
renderizar el resultado. La lógica de análisis no vive acá.

También es la única frontera donde se traducen los errores de disco a mensajes
legibles: `core/` deja propagar las excepciones y la CLI decide cómo mostrarlas
y con qué código de salida. Cuando estos análisis se expongan como herramientas
del agente, ese otro consumidor va a querer manejar las excepciones a su manera
en vez de heredar mensajes pensados para una terminal.
"""

from __future__ import annotations

from pathlib import Path

import typer

from forge import render
from forge.core.doctor import Doctor
from forge.core.project import Project
from forge.core.scanner import Scanner
from forge.core.stats import Stats
from forge.core.tree import DEFAULT_MAX_DEPTH, Tree

__version__ = "0.1.0"

#: Uso incorrecto: la ruta no existe, no es un directorio o no se puede leer.
EXIT_USAGE = 2
#: El análisis corrió bien pero el proyecto no pasó los checks (`--strict`).
EXIT_UNHEALTHY = 1

app = typer.Typer(help="Forge Agent — análisis de proyectos de software")

PathOption = typer.Option(".", "--path", "-p", help="Ruta del proyecto")


def _fail(message: str, code: int = EXIT_USAGE) -> "typer.Exit":
    typer.secho(f"❌ {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=code)


def _validate(path: str) -> str:
    target = Path(path)

    if not target.exists():
        _fail(f"La ruta no existe: {path}")
    if not target.is_dir():
        _fail(f"La ruta no es un directorio: {path}")

    return path


def _guard(path: str, action):
    """Ejecuta `action` traduciendo errores de disco a mensajes legibles.

    Sin esto, un `--path` sin permisos de lectura terminaba en un traceback de
    `os.listdir`, que es una respuesta de bug ante un error de uso.
    """
    try:
        return action()
    except PermissionError as exc:
        _fail(f"Sin permisos para leer: {exc.filename or path}")
    except OSError as exc:
        _fail(f"No se pudo leer {path}: {exc.strerror or exc}")


@app.command()
def version():
    """Muestra la versión de Forge."""
    typer.echo(f"Forge Agent v{__version__}")


@app.command()
def analyze(path: str = PathOption):
    """Analiza un proyecto."""
    target = _validate(path)
    report = _guard(target, lambda: Project(target).analyze())
    typer.echo(render.render_project(report))


@app.command()
def doctor(
    path: str = PathOption,
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Termina con código 1 si algún check no pasa (útil en CI).",
    ),
):
    """Revisa el estado de salud del proyecto."""
    target = _validate(path)
    report = _guard(target, lambda: Doctor(target).check())
    typer.echo(render.render_doctor(report))

    if strict and not report.healthy:
        raise typer.Exit(code=EXIT_UNHEALTHY)


@app.command()
def tree(
    path: str = PathOption,
    depth: int = typer.Option(
        DEFAULT_MAX_DEPTH, "--depth", "-d", help="Profundidad máxima"
    ),
):
    """Muestra el árbol del proyecto."""
    target = _validate(path)

    if depth < 1:
        _fail("--depth debe ser al menos 1")

    entries = _guard(target, lambda: Tree(target, max_depth=depth).build())
    typer.echo(render.render_tree(entries))


@app.command()
def stats(path: str = PathOption):
    """Muestra estadísticas del proyecto."""
    target = _validate(path)
    report = _guard(target, lambda: Stats(target).show())
    typer.echo(render.render_stats(report))


@app.command()
def scan(path: str = PathOption):
    """Escanea el código en busca de deuda visible."""
    target = _validate(path)
    report = _guard(target, lambda: Scanner(target).scan())
    typer.echo(render.render_scan(report))


if __name__ == "__main__":
    app()
