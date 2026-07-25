import typer

from forge.core.project import Project

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


if __name__ == "__main__":
    app()
