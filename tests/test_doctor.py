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


def test_serialization_separates_informational_checks(make_project):
    """Regresión de un error observado con un modelo real.

    Emitir `"scored": false` dentro de cada check hacía que un modelo chico
    leyera el único `false` de la lista —al lado de `"passed": true`— como
    "esto falta". Concluyó que no había entorno virtual sobre un proyecto que
    sí lo tenía. La lista separada elimina el flag que se malinterpretaba.
    """
    project = make_project(
        files={"README.md": "# x", "pyproject.toml": "[project]\n"},
        dirs=[".git", ".venv", "tests"],
    )

    payload = Doctor(project).check().to_dict()

    assert [c["name"] for c in payload["informational"]] == ["Entorno virtual"]
    assert payload["informational"][0]["passed"] is True
    assert "Entorno virtual" not in [c["name"] for c in payload["checks"]]

    # Ningún check lleva ya un flag cuyo `false` se pueda leer como fracaso.
    for check in payload["checks"] + payload["informational"]:
        assert "scored" not in check


def test_scored_checks_match_the_score(healthy_project):
    payload = Doctor(healthy_project).check().to_dict()

    assert len(payload["checks"]) == payload["total"]
    assert sum(c["passed"] for c in payload["checks"]) == payload["score"]
