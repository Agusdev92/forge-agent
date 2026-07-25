import typer

from forge.core.project import analyze_project


def analyze(
    path: str = typer.Argument(".", help="Ruta del proyecto")
):
    analyze_project(path)
