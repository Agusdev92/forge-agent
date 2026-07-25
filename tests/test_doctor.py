"""Tests del health score."""

from __future__ import annotations

from forge.core.doctor import Doctor


def test_empty_project_scores_zero(make_project):
    report = Doctor(make_project()).check()

    assert report.score == 0
    assert not report.healthy


def test_project_with_only_empty_files_scores_zero(make_project):
    """Regresión del bug principal de D6.

    Con el código anterior este proyecto sacaba 2/6, porque `README.md` y
    `requirements.txt` existían aunque estuvieran vacíos. Un health score que
    premia `touch` no mide salud.
    """
    project = make_project(files={"README.md": "", "requirements.txt": ""})

    report = Doctor(project).check()

    assert report.score == 0
    assert len(report.warnings) == 2


def test_healthy_project_scores_full(healthy_project):
    report = Doctor(healthy_project).check()

    assert report.score == report.total
    assert report.healthy
    assert report.warnings == []


def test_venv_does_not_affect_score(make_project):
    """El mismo proyecto debe puntuar igual con y sin entorno virtual."""
    files = {"README.md": "# x", "pyproject.toml": "[project]\n"}

    sin_venv = Doctor(make_project(files=files)).check()
    con_venv = Doctor(make_project(files=files, dirs=[".venv"])).check()

    assert sin_venv.score == con_venv.score
    assert sin_venv.total == con_venv.total


def test_total_excludes_informational_checks(healthy_project):
    report = Doctor(healthy_project).check()

    assert report.total == len([c for c in report.checks if c.scored])
    assert report.total < len(report.checks)
