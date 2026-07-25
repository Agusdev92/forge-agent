"""Tests de la capa de acceso a disco.

Es la capa donde vive la exclusión de directorios, así que acá se prueba la
causa raíz del bug que inflaba los conteos de `stats` y `scan`.
"""

from __future__ import annotations

import pytest

from forge.core import filesystem as fs


def test_walk_excludes_ignored_directories(make_project):
    project = make_project(
        files={
            "app.py": "x = 1\n",
            ".git/objects/abc": "binario",
            ".venv/lib/site.py": "x = 1\n",
            "__pycache__/app.cpython-311.pyc": "bytecode",
            "node_modules/dep/index.js": "x",
        }
    )

    found = {path.name for path in fs.iter_files(project)}

    assert found == {"app.py"}


def test_walk_excludes_egg_info(make_project):
    """`pip install -e .` genera `*.egg-info/`: es artefacto de build."""
    project = make_project(
        files={"app.py": "x = 1\n", "demo.egg-info/PKG-INFO": "Name: demo\n"}
    )

    assert {p.name for p in fs.iter_files(project)} == {"app.py"}


def test_iter_files_filters_by_suffix(make_project):
    project = make_project(
        files={"app.py": "", "README.md": "hola", "script.js": ""}
    )

    assert {p.name for p in fs.iter_files(project, ".py")} == {"app.py"}


def test_walk_propagates_unreadable_root(tmp_path):
    """Regresión: `os.walk` descarta los errores por defecto.

    Un directorio ilegible producía cero resultados en vez de un error, y
    `stats` informaba "0 archivos" sobre un proyecto que nunca pudo leer.
    """
    with pytest.raises(OSError):
        list(fs.walk(tmp_path / "no-existe"))


def test_is_ignored():
    assert fs.is_ignored(".git")
    assert fs.is_ignored("__pycache__")
    assert fs.is_ignored("forge_agent.egg-info")
    assert not fs.is_ignored("forge")


def test_has_content_distinguishes_empty_from_missing(make_project):
    project = make_project(
        files={
            "vacio.md": "",
            "espacios.md": "   \n\n  ",
            "lleno.md": "# Título\n",
        }
    )

    assert not fs.has_content(project / "no-existe.md")
    assert not fs.has_content(project / "vacio.md")
    assert not fs.has_content(project / "espacios.md")
    assert fs.has_content(project / "lleno.md")


def test_has_content_on_directory_is_false(make_project):
    project = make_project(dirs=["src"])

    assert not fs.has_content(project / "src")


def test_list_directories_excludes_ignored(make_project):
    project = make_project(files={"app.py": ""}, dirs=["src", ".git", ".venv"])

    listed = fs.FileSystem(project).list_directories()

    assert listed == ["src"]


def test_list_files_is_single_level(make_project):
    project = make_project(files={"app.py": "", "src/deep.py": ""})

    assert fs.FileSystem(project).list_files() == ["app.py"]
