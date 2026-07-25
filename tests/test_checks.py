"""Tests de los checks de salud.

El caso central es la distinción entre "el archivo existe" y "el archivo tiene
contenido": era el defecto que hacía que un proyecto recién creado con `touch`
sacara puntaje.
"""

from __future__ import annotations

import pytest

from forge.core.checks import Status, run_checks


def _by_name(checks):
    return {c.name: c for c in checks}


def test_readme_missing_empty_and_filled(make_project):
    missing = _by_name(run_checks(make_project()))["README.md"]
    empty = _by_name(run_checks(make_project(files={"README.md": ""})))["README.md"]
    filled = _by_name(run_checks(make_project(files={"README.md": "# Hola"})))["README.md"]

    assert missing.status is Status.MISSING
    assert empty.status is Status.WARNING
    assert filled.status is Status.OK


def test_empty_file_is_warning_not_ok(make_project):
    """Regresión: un README de 0 bytes daba ✅ y sumaba al score."""
    check = _by_name(run_checks(make_project(files={"README.md": ""})))["README.md"]

    assert not check.passed
    assert "vac" in check.detail


def test_dependency_check_accepts_pyproject(make_project):
    """`pyproject.toml` es el estándar actual y antes se ignoraba."""
    project = make_project(files={"pyproject.toml": "[project]\nname='x'\n"})

    check = _by_name(run_checks(project))["Dependencias declaradas"]

    assert check.status is Status.OK


def test_dependency_check_accepts_requirements(make_project):
    project = make_project(files={"requirements.txt": "typer\n"})

    assert _by_name(run_checks(project))["Dependencias declaradas"].status is Status.OK


def test_dependency_check_warns_on_empty_manifest(make_project):
    """El caso exacto de este repo antes de la Fase 0."""
    project = make_project(files={"requirements.txt": ""})

    check = _by_name(run_checks(project))["Dependencias declaradas"]

    assert check.status is Status.WARNING


def test_dependency_check_missing(make_project):
    check = _by_name(run_checks(make_project()))["Dependencias declaradas"]

    assert check.status is Status.MISSING


def test_git_and_tests_are_directory_checks(make_project):
    project = make_project(dirs=[".git", "tests"])

    checks = _by_name(run_checks(project))

    assert checks["Git"].status is Status.OK
    assert checks["tests"].status is Status.OK


def test_venv_check_is_informational(make_project):
    """`.venv/` está gitignoreado: no puede puntuar sin hacer el score
    dependiente de la máquina que ejecuta."""
    check = _by_name(run_checks(make_project(dirs=[".venv"])))["Entorno virtual"]

    assert check.status is Status.OK
    assert check.scored is False


@pytest.mark.parametrize("check_name", ["Git", "Dependencias declaradas", "tests"])
def test_scored_checks_are_scored(make_project, check_name):
    assert _by_name(run_checks(make_project()))[check_name].scored is True
