"""Tests del confinamiento de rutas.

Cada test es un intento de escape concreto. Son la parte del proyecto donde un
fallo silencioso tiene consecuencias reales: una ruta que se escapa deja al
modelo leer o sobrescribir archivos fuera del proyecto que se está analizando.
"""

from __future__ import annotations

import pytest

from forge.tools.sandbox import (
    PathOutsideProject,
    relative_to_root,
    resolve_within,
)


def test_allows_paths_inside_the_project(make_project):
    project = make_project(files={"src/app.py": "x = 1\n"})

    target = resolve_within(project, "src/app.py")

    assert target == (project / "src" / "app.py").resolve()


def test_allows_the_root_itself(make_project):
    project = make_project()

    assert resolve_within(project, ".") == project.resolve()


def test_rejects_absolute_paths(make_project):
    """`Path(root) / "/etc/passwd"` devuelve `/etc/passwd`.

    El operador `/` de pathlib descarta el lado izquierdo cuando el derecho es
    absoluto. Sin este rechazo explícito no hay confinamiento en absoluto.
    """
    project = make_project()

    with pytest.raises(PathOutsideProject):
        resolve_within(project, "/etc/passwd")


def test_rejects_parent_traversal(make_project):
    project = make_project()

    with pytest.raises(PathOutsideProject):
        resolve_within(project, "../../etc/passwd")


def test_rejects_traversal_hidden_mid_path(make_project):
    """El `..` no siempre va al principio."""
    project = make_project(dirs=["src"])

    with pytest.raises(PathOutsideProject):
        resolve_within(project, "src/../../fuera.txt")


def test_rejects_symlink_pointing_outside(tmp_path):
    """`resolve()` sigue los symlinks, así que se compara el destino real."""
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("credenciales", encoding="utf-8")

    project = tmp_path / "project"
    project.mkdir()
    (project / "link.txt").symlink_to(secret)

    with pytest.raises(PathOutsideProject):
        resolve_within(project, "link.txt")


def test_allows_symlink_pointing_inside(make_project):
    project = make_project(files={"real.txt": "contenido"})
    (project / "alias.txt").symlink_to(project / "real.txt")

    assert resolve_within(project, "alias.txt") == (project / "real.txt").resolve()


def test_does_not_expand_home(make_project):
    """`~` es un nombre de archivo común y corriente, no el home del usuario."""
    project = make_project()

    target = resolve_within(project, "~/notas.txt")

    assert target.is_relative_to(project.resolve())


def test_target_for_a_file_that_does_not_exist_yet(make_project):
    """Escribir un archivo nuevo tiene que poder resolverse."""
    project = make_project()

    target = resolve_within(project, "docs/nuevo.md")

    assert not target.exists()
    assert target.is_relative_to(project.resolve())


def test_relative_to_root_hides_the_absolute_path(make_project):
    project = make_project(files={"src/app.py": ""})

    shown = relative_to_root(project, project / "src" / "app.py")

    assert shown == "src/app.py"
