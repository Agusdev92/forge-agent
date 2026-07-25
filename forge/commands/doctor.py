import typer

from forge.core.doctor import Doctor

app = typer.Typer()


@app.command()
def doctor(path: str = "."):
    """Revisa el estado de salud del proyecto."""
    Doctor(path).check()
