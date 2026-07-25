"""Fixtures compartidas.

Los analizadores de Forge son funciones sobre el sistema de archivos, así que
los tests construyen proyectos reales en directorios temporales en vez de
mockear `os`. Es más lento pero verifica lo que el código realmente hace: los
tres falsos positivos que aparecieron en la Fase 1 eran del recorrido de disco,
justo lo que un mock habría dado por bueno.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def make_project(tmp_path):
    """Construye un proyecto temporal y devuelve su ruta.

    `files` es un dict de ruta relativa a contenido; `dirs` una lista de
    directorios a crear vacíos.
    """

    def build(files=None, dirs=()):
        for directory in dirs:
            (tmp_path / directory).mkdir(parents=True, exist_ok=True)

        for name, content in (files or {}).items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        return tmp_path

    return build


@pytest.fixture
def healthy_project(make_project):
    """Un proyecto que pasa todos los checks puntuables."""
    return make_project(
        files={
            "pyproject.toml": "[project]\nname = 'demo'\n",
            "README.md": "# Demo\n",
            ".gitignore": ".venv/\n",
            "tests/test_demo.py": "def test_ok():\n    assert True\n",
            "demo/__init__.py": "",
        },
        dirs=[".git"],
    )
