"""Tests de la CLI: códigos de salida y manejo de errores.

Verifican lo que agregó D5. Antes, un `--path` inexistente producía un
traceback de `os.listdir` y todos los comandos salían con código 0 pasara lo
que pasara, así que ningún script podía distinguir un análisis exitoso de uno
fallido.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from forge.cli import EXIT_UNHEALTHY, EXIT_USAGE, app

runner = CliRunner()

COMMANDS = ["analyze", "doctor", "stats", "scan", "tree"]


def output_of(result) -> str:
    """Junta stdout y stderr según lo que exponga la versión de click."""
    text = result.output or ""
    try:
        text += result.stderr or ""
    except (AttributeError, ValueError):
        pass
    return text


def test_version():
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert "Forge Agent v" in result.output


@pytest.mark.parametrize("command", COMMANDS)
def test_commands_succeed_on_valid_project(command, healthy_project):
    result = runner.invoke(app, [command, "--path", str(healthy_project)])

    assert result.exit_code == 0, output_of(result)


@pytest.mark.parametrize("command", COMMANDS)
def test_missing_path_fails_cleanly(command, tmp_path):
    """Sin traceback y con código de uso, no con 0."""
    result = runner.invoke(app, [command, "--path", str(tmp_path / "no-existe")])

    assert result.exit_code == EXIT_USAGE
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "no existe" in output_of(result).lower()


@pytest.mark.parametrize("command", COMMANDS)
def test_file_instead_of_directory_fails_cleanly(command, make_project):
    project = make_project(files={"archivo.txt": "hola"})

    result = runner.invoke(app, [command, "--path", str(project / "archivo.txt")])

    assert result.exit_code == EXIT_USAGE
    assert "directorio" in output_of(result).lower()


def test_doctor_strict_fails_on_unhealthy_project(make_project):
    result = runner.invoke(app, ["doctor", "--strict", "--path", str(make_project())])

    assert result.exit_code == EXIT_UNHEALTHY
    assert "Health Score: 0/" in result.output


def test_doctor_strict_passes_on_healthy_project(healthy_project):
    result = runner.invoke(
        app, ["doctor", "--strict", "--path", str(healthy_project)]
    )

    assert result.exit_code == 0


def test_doctor_without_strict_never_fails(make_project):
    """Sin `--strict` el comando informa, no falla: el diagnóstico de un
    proyecto enfermo no es un error de ejecución."""
    result = runner.invoke(app, ["doctor", "--path", str(make_project())])

    assert result.exit_code == 0


def test_doctor_marks_venv_as_informational(healthy_project):
    result = runner.invoke(app, ["doctor", "--path", str(healthy_project)])

    assert "(informativo)" in result.output


def test_tree_rejects_invalid_depth(healthy_project):
    result = runner.invoke(
        app, ["tree", "--depth", "0", "--path", str(healthy_project)]
    )

    assert result.exit_code == EXIT_USAGE
    assert "depth" in output_of(result).lower()


def test_scan_reports_todo_count(make_project):
    project = make_project(files={"app.py": "# TODO: algo\n"})

    result = runner.invoke(app, ["scan", "--path", str(project)])

    assert result.exit_code == 0
    assert "TODO/FIXME encontrados: 1" in result.output


# --------------------------------------------------------------------------
# `forge ask`: configuración por entorno y recorte de herramientas
# --------------------------------------------------------------------------

DEAD_URL = "http://127.0.0.1:9/v1"


def test_base_url_can_come_from_the_environment(healthy_project):
    """Escribir la URL a mano en cada consulta es inviable en un teléfono."""
    result = runner.invoke(
        app,
        ["ask", "hola", "--path", str(healthy_project)],
        env={"FORGE_BASE_URL": DEAD_URL},
    )

    assert result.exit_code == EXIT_USAGE
    assert "127.0.0.1:9" in output_of(result)


def test_the_flag_wins_over_the_environment(healthy_project):
    result = runner.invoke(
        app,
        ["ask", "hola", "--path", str(healthy_project), "--base-url", DEAD_URL],
        env={"FORGE_BASE_URL": "http://127.0.0.1:7/v1"},
    )

    assert "127.0.0.1:9" in output_of(result)


def test_unknown_tool_fails_before_contacting_the_model(healthy_project):
    """El error tiene que ser sobre la herramienta, no sobre la conexión."""
    result = runner.invoke(
        app,
        [
            "ask",
            "hola",
            "--path",
            str(healthy_project),
            "--tools",
            "forge_doctor,inventada",
            "--base-url",
            DEAD_URL,
        ],
    )

    output = output_of(result)
    assert result.exit_code == EXIT_USAGE
    assert "inventada" in output
    assert "escuchando" not in output


def test_minimal_selection_is_accepted(healthy_project):
    """Llega a intentar conectarse, o sea que la selección no falló."""
    result = runner.invoke(
        app,
        ["ask", "hola", "--path", str(healthy_project), "--tools", "minimal",
         "--base-url", DEAD_URL],
    )

    assert "escuchando" in output_of(result)
