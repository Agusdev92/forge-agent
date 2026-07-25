"""Tests de los analizadores: proyecto, stats, scanner y árbol.

Casi todos son regresiones de bugs concretos documentados en los reportes 001 y
002, no cobertura genérica.
"""

from __future__ import annotations

import pytest

from forge.core.project import UNKNOWN_LANGUAGE, Project
from forge.core.scanner import Scanner
from forge.core.stats import Stats
from forge.core.tree import Tree

# --------------------------------------------------------------------------
# Detección de lenguaje
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "manifest,expected",
    [
        ("pyproject.toml", "Python"),
        ("requirements.txt", "Python"),
        ("setup.py", "Python"),
        ("package.json", "Node.js"),
    ],
)
def test_detect_language_by_manifest(make_project, manifest, expected):
    project = make_project(files={manifest: "contenido"})

    assert Project(project).detect_language() == expected


def test_detect_language_falls_back_to_extension(make_project):
    """Regresión: un proyecto Python sin manifiesto daba "Desconocido"."""
    project = make_project(files={"src/app.py": "x = 1\n"})

    assert Project(project).detect_language() == "Python"


def test_detect_language_unknown(make_project):
    project = make_project(files={"notas.txt": "hola"})

    assert Project(project).detect_language() == UNKNOWN_LANGUAGE


def test_analyze_lists_only_visible_top_level(make_project):
    project = make_project(
        files={"app.py": "", "src/deep.py": ""}, dirs=[".git", ".venv"]
    )

    report = Project(project).analyze()

    assert report.directories == ["src"]
    assert report.files == ["app.py"]
    assert report.language == "Python"


# --------------------------------------------------------------------------
# Stats
# --------------------------------------------------------------------------


def test_stats_excludes_infrastructure_directories(make_project):
    """Regresión del bug del +226%.

    Antes `os.walk` contaba `.git` y `.venv`: sobre el repo de Forge reportaba
    101 archivos donde había 31.
    """
    project = make_project(
        files={
            "app.py": "x = 1\n",
            "README.md": "# demo",
            ".git/objects/abc": "binario",
            ".venv/lib/site.py": "x = 1\n",
            "__pycache__/app.pyc": "bytecode",
        },
        dirs=["src"],
    )

    report = Stats(project).show()

    assert report.files == 2
    assert report.directories == 1


def test_stats_reports_language(make_project):
    project = make_project(files={"pyproject.toml": "[project]\n"})

    assert Stats(project).show().language == "Python"


# --------------------------------------------------------------------------
# Scanner
# --------------------------------------------------------------------------


def test_scan_counts_only_comment_markers(make_project):
    """Regresión: `scan` se contaba a sí mismo.

    Buscar la subcadena "TODO" daba positivo en cualquier código que
    mencionara la palabra, incluida la propia definición de los marcadores.
    """
    project = make_project(
        files={
            "app.py": (
                "# TODO: refactorizar\n"
                "MARKERS = ('TODO', 'FIXME')\n"
                'mensaje = "TODO encontrados"\n'
                "# FIXME: revisar\n"
            )
        }
    )

    report = Scanner(project).scan()

    assert report.todos == 2
    assert report.files_with_todos == [str(project / "app.py")]


def test_scan_ignores_empty_init_files(make_project):
    """Un `__init__.py` vacío es un marcador de paquete, no deuda."""
    project = make_project(files={"pkg/__init__.py": "", "pkg/vacio.py": ""})

    report = Scanner(project).scan()

    assert report.python_files == 2
    assert report.empty_files == 1
    assert report.empty_paths == [str(project / "pkg" / "vacio.py")]


def test_scan_excludes_dependencies(make_project):
    """Regresión: `rglob` entraba en `.venv` y contaba TODOs de terceros."""
    project = make_project(
        files={"app.py": "# TODO: propio\n", ".venv/lib/dep.py": "# TODO: ajeno\n"}
    )

    report = Scanner(project).scan()

    assert report.python_files == 1
    assert report.todos == 1


def test_scan_ignores_markers_inside_string_literals(make_project):
    """Regresión de la segunda ronda de falsos positivos.

    Buscar `# TODO` por texto contaba los marcadores dentro de literales de
    string: los propios tests de Forge, que construyen archivos de prueba con
    TODOs adentro, inflaban la métrica del repo.
    """
    project = make_project(
        files={
            "app.py": (
                'fixture = "# TODO: esto es un dato de prueba"\n'
                'otro = """\n# FIXME: también dato\n"""\n'
                "# TODO: este sí es deuda\n"
            )
        }
    )

    report = Scanner(project).scan()

    assert report.todos == 1


def test_scan_falls_back_on_unparseable_file(make_project):
    """Un archivo con sintaxis inválida no debe romper el escaneo."""
    project = make_project(files={"roto.py": "def (: # TODO: arreglar\n"})

    report = Scanner(project).scan()

    assert report.python_files == 1
    assert report.todos == 1


def test_scan_on_clean_project_reports_nothing(healthy_project):
    report = Scanner(healthy_project).scan()

    assert report.todos == 0
    assert report.empty_files == 0


# --------------------------------------------------------------------------
# Tree
# --------------------------------------------------------------------------


def test_tree_is_recursive(make_project):
    """Regresión: se llamaba `tree` y listaba un solo nivel."""
    project = make_project(files={"src/core/app.py": "x = 1\n"})

    names = [e.name for e in Tree(project).build()]

    assert names == ["src", "core", "app.py"]


def test_tree_records_depth(make_project):
    project = make_project(files={"src/core/app.py": ""})

    depths = {e.name: e.depth for e in Tree(project).build()}

    assert depths == {"src": 0, "core": 1, "app.py": 2}


def test_tree_respects_max_depth(make_project):
    project = make_project(files={"a/b/c/d.py": ""})

    names = [e.name for e in Tree(project, max_depth=2).build()]

    assert names == ["a", "b"]


def test_tree_skips_hidden_and_ignored(make_project):
    project = make_project(
        files={"app.py": "", ".env": "SECRET=1"}, dirs=[".git", "__pycache__", "src"]
    )

    names = [e.name for e in Tree(project).build()]

    assert names == ["src", "app.py"]


def test_tree_on_empty_directory(make_project):
    assert Tree(make_project()).build() == []
