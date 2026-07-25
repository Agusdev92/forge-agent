import typer

from forge.core.project import Project
from forge.core.doctor import Doctor 
app = typer.Typer(help="Forge Agent")


@app.command()
def version():
    """Show Forge version."""
    typer.echo("Forge Agent v0.1.0")


@app.command()
def analyze(
    path: str = typer.Option(
        ".",
        "--path",
        "-p",
        help="Ruta del proyecto",
    )
):
    """Analyze a project."""
    project = Project(path)
    project.analyze()
@app.command()
def doctor(
    path: str = typer.Option(
        ".",
        "--path",
        "-p",
        help="Ruta del proyecto",
    )
):
    """Revisa el estado del proyecto."""
    Doctor(path).check()
@app.command()
def tree(
    path: str = typer.Option(
        ".",
        "--path",
        "-p",
        help="Ruta del proyecto",
    )
):
    """Muestra el árbol del proyecto."""
    from forge.core.tree import Tree
@app.command()
def stats(
    path: str = typer.Option(
        ".",
        "--path",
        "-p",
        help="Ruta del proyecto",
    )
):
    """Muestra estadísticas del proyecto."""
    from forge.core.stats import Stats

    Stats(path).show()


if __name__ == "__main__":
    app()
if __name__ == "__main__":
    app()
