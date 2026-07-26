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

from forge import approval_cli, render
from forge.agent import DEFAULT_MAX_ITERATIONS, Agent
from forge.core.doctor import Doctor
from forge.core.project import Project
from forge.core.scanner import Scanner
from forge.core.stats import Stats
from forge.core.tree import DEFAULT_MAX_DEPTH, Tree
from forge.providers import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    LocalChatClient,
    ModelConfig,
    ProviderError,
)
from forge.tools import MINIMAL_TOOLS, UnknownTool, build_tools

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


def _progress_reporter():
    """Emite puntos a stderr mientras el modelo genera.

    En una GPU chica cada paso tarda decenas de segundos. Sin ninguna señal, la
    terminal quieta es indistinguible de un cuelgue — y esa duda es lo que hace
    que uno corte una consulta que estaba funcionando bien. Va a stderr para no
    ensuciar la respuesta si alguien redirige la salida.
    """
    state = {"pending": 0, "emitted": False}

    def on_token(text: str) -> None:
        state["pending"] += len(text)
        if state["pending"] < 40:
            return
        typer.secho(".", nl=False, err=True, fg=typer.colors.BRIGHT_BLACK)
        state["pending"] = 0
        state["emitted"] = True

    return on_token, state


def _tool_selection(value: str):
    """Traduce `--tools` a la lista de nombres, o `None` para todas."""
    if value == "all":
        return None
    if value == "minimal":
        return list(MINIMAL_TOOLS)
    return [name.strip() for name in value.split(",") if name.strip()]


@app.command()
def ask(
    question: str = typer.Argument(..., help="Qué querés saber del proyecto"),
    path: str = PathOption,
    model: str = typer.Option(
        DEFAULT_MODEL, "--model", "-m", envvar="FORGE_MODEL", help="Modelo local"
    ),
    base_url: str = typer.Option(
        DEFAULT_BASE_URL,
        "--base-url",
        envvar="FORGE_BASE_URL",
        help="URL del runtime. Podés fijarla con la variable FORGE_BASE_URL.",
    ),
    tools: str = typer.Option(
        "all",
        "--tools",
        envvar="FORGE_TOOLS",
        help="'all', 'minimal' (para modelos chicos) o una lista separada por comas.",
    ),
    max_iterations: int = typer.Option(
        DEFAULT_MAX_ITERATIONS, "--max-iterations", help="Tope de pasos del agente"
    ),
    timeout: float = typer.Option(
        DEFAULT_TIMEOUT,
        "--timeout",
        envvar="FORGE_TIMEOUT",
        help="Segundos de silencio tolerados entre fragmentos de la respuesta.",
    ),
    prompt_tools: bool = typer.Option(
        True,
        "--prompt-tools/--no-prompt-tools",
        envvar="FORGE_PROMPT_TOOLS",
        help=(
            "Describir las herramientas también en el prompt. Necesario solo "
            "para modelos sin tool calling nativo; desactivalo para ahorrar "
            "contexto si tu modelo lo soporta."
        ),
    ),
    max_tokens: int = typer.Option(
        DEFAULT_MAX_TOKENS,
        "--max-tokens",
        envvar="FORGE_MAX_TOKENS",
        help=(
            "Tope de tokens por respuesta. El contexto del runtime debe cubrir "
            "el prompt MÁS esto, o trunca en silencio."
        ),
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Sin indicador de avance."
    ),
    yes: bool = typer.Option(
        False, "--yes", help="Aprueba las escrituras sin preguntar. Usalo con cuidado."
    ),
):
    """Le pregunta al modelo local sobre el proyecto."""
    target = _validate(path)

    approver = (
        approval_cli.approve_everything if yes else approval_cli.confirm_write
    )

    try:
        selected = build_tools(
            target, approver=approver, only=_tool_selection(tools)
        )
    except UnknownTool as exc:
        _fail(str(exc))

    on_token, progress = (None, None) if quiet else _progress_reporter()

    client = LocalChatClient(
        ModelConfig(
            base_url=base_url, model=model, timeout=timeout,
            max_tokens=max_tokens,
        )
    )
    agent = Agent(
        client,
        selected,
        max_iterations=max_iterations,
        describe_tools_in_prompt=prompt_tools,
        on_token=on_token,
    )

    try:
        result = agent.run(question)
    except ProviderError as exc:
        if progress and progress["emitted"]:
            typer.echo(err=True)
        _fail(str(exc))
    finally:
        client.close()

    if progress and progress["emitted"]:
        typer.echo(err=True)

    typer.echo(render.render_agent(result))

    # Un tope alcanzado no es una respuesta: quien lo invoque desde un script
    # tiene que poder distinguirlo sin parsear el texto.
    if result.hit_limit:
        raise typer.Exit(code=EXIT_UNHEALTHY)


if __name__ == "__main__":
    app()
