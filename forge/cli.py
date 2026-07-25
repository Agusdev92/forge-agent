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
    path: str = typer.Option(".", "--path", "-p", help="Ruta del proyecto"),
):
    """Analiza un proyecto."""
    Project(path).analyze()


@app.command()
def doctor(
    path: str = typer.Option(".", "--path", "-p", help="Ruta del proyecto"),
):
    """Revisa el estado del proyecto."""
    Doctor(path).check()


@app.command()
def tree(
    path: str = typer.Option(".", "--path", "-p", help="Ruta del proyecto"),
):
    """Muestra el árbol del proyecto."""
    from forge.core.tree import Tree
    Tree(path).show()


@app.command()
def stats(
    path: str = typer.Option(".", "--path", "-p", help="Ruta del proyecto"),
):
    """Muestra estadísticas del proyecto."""
    from forge.core.stats import Stats
    Stats(path).show()


@app.command()
def scan(
    path: str = typer.Option(".", "--path", "-p", help="Ruta del proyecto"),
):
    """Escanea el proyecto."""
    from forge.core.scanner import Scanner
    Scanner(path).scan()


if __name__ == "__main__":
    app()
