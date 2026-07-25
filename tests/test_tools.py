"""Tests de la capa de herramientas.

Se ejercita sin modelo: las herramientas son funciones que devuelven JSON, así
que se verifican como cualquier otra función. La frontera del reporte 003 se
mantiene — acá no hay llamadas a la API.
"""

from __future__ import annotations

import json

import pytest

from forge.tools import build_tools
from forge.tools.approval import CREATE, OVERWRITE, WriteRequest, allow_all, deny_all


def tools_by_name(root, approver=deny_all) -> dict:
    return {t.name: t for t in build_tools(root, approver=approver)}


def call(tool, **kwargs):
    """Invoca la herramienta como lo haría el tool runner y parsea el JSON."""
    return json.loads(tool.call(kwargs))


# --------------------------------------------------------------------------
# Esquemas
# --------------------------------------------------------------------------


def test_every_tool_exposes_a_schema(make_project):
    for tool in build_tools(make_project()):
        schema = tool.to_dict()
        assert schema["name"]
        assert schema["description"], f"{schema['name']} sin descripción"
        assert schema["input_schema"]["type"] == "object"


def test_root_is_not_a_model_parameter(make_project):
    """La raíz la fija quien ejecuta Forge, nunca el modelo.

    Si apareciera como parámetro, el modelo podría elegir qué proyecto mirar y
    el confinamiento de rutas no serviría de nada.
    """
    for tool in build_tools(make_project()):
        properties = tool.to_dict()["input_schema"].get("properties", {})
        assert "root" not in properties
        assert "approver" not in properties


# --------------------------------------------------------------------------
# Herramientas de análisis
# --------------------------------------------------------------------------


def test_doctor_returns_structured_data(healthy_project):
    tools = tools_by_name(healthy_project)

    result = call(tools["forge_doctor"], path=".")

    assert result["healthy"] is True
    assert result["score"] == result["total"]
    assert all("status" in c for c in result["checks"])


def test_scan_returns_structured_data(make_project):
    project = make_project(files={"app.py": "# TODO: algo\n"})

    result = call(tools_by_name(project)["forge_scan"], path=".")

    assert result["python_files"] == 1
    assert result["todos"] == 1


def test_tree_returns_entries(make_project):
    project = make_project(files={"src/app.py": ""})

    result = call(tools_by_name(project)["forge_tree"], path=".", depth=2)

    assert [e["name"] for e in result] == ["src", "app.py"]


def test_tree_rejects_invalid_depth(make_project):
    result = call(tools_by_name(make_project())["forge_tree"], depth=0)

    assert "error" in result


@pytest.mark.parametrize(
    "name", ["forge_analyze", "forge_doctor", "forge_stats", "forge_scan", "forge_tree"]
)
def test_analysis_tools_refuse_to_escape_the_project(make_project, name):
    result = call(tools_by_name(make_project())[name], path="../../etc")

    assert "error" in result
    assert "fuera del proyecto" in result["error"]


# --------------------------------------------------------------------------
# Lectura
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["forge_analyze", "forge_doctor", "forge_scan"])
def test_analysis_tools_never_leak_absolute_paths(make_project, name):
    """El modelo no tiene por qué ver la estructura del disco del usuario.

    Los reportes de `core/` llevan la ruta con la que se los construyó, que en
    el camino de las herramientas es absoluta.
    """
    project = make_project(files={"pkg/__init__.py": "", "pkg/app.py": "# TODO: x\n"})

    raw = tools_by_name(project)[name].call({"path": "."})

    assert str(project) not in raw, f"{name} filtró la ruta absoluta"


def test_read_file(make_project):
    project = make_project(files={"notas.md": "# Hola\n"})

    result = call(tools_by_name(project)["read_file"], path="notas.md")

    assert result["content"] == "# Hola\n"
    assert result["truncated"] is False


def test_read_file_truncates_large_files(make_project):
    """Un archivo enorme no es un riesgo, pero desplaza contexto útil."""
    from forge.tools.sandbox import MAX_READ_BYTES

    project = make_project(files={"grande.txt": "x" * (MAX_READ_BYTES + 500)})

    result = call(tools_by_name(project)["read_file"], path="grande.txt")

    assert result["truncated"] is True
    assert len(result["content"]) == MAX_READ_BYTES


def test_read_file_refuses_paths_outside(make_project):
    result = call(tools_by_name(make_project())["read_file"], path="/etc/passwd")

    assert "error" in result


def test_read_file_on_a_directory(make_project):
    project = make_project(dirs=["src"])

    result = call(tools_by_name(project)["read_file"], path="src")

    assert "error" in result


# --------------------------------------------------------------------------
# Escritura — la compuerta de aprobación
# --------------------------------------------------------------------------


def test_write_is_denied_by_default(make_project):
    """Sin aprobador configurado, nada se escribe.

    Una compuerta que se abre sola cuando se la olvida configurar no es una
    compuerta.
    """
    project = make_project()

    result = call(tools_by_name(project)["write_file"], path="README.md", content="# X")

    assert "error" in result
    assert not (project / "README.md").exists()


def test_write_creates_when_approved(make_project):
    project = make_project()
    tools = tools_by_name(project, approver=allow_all)

    result = call(tools["write_file"], path="docs/README.md", content="# Hola\n")

    assert result["action"] == CREATE
    assert (project / "docs" / "README.md").read_text(encoding="utf-8") == "# Hola\n"


def test_write_overwrites_when_approved(make_project):
    project = make_project(files={"README.md": "viejo\n"})
    tools = tools_by_name(project, approver=allow_all)

    result = call(tools["write_file"], path="README.md", content="nuevo\n")

    assert result["action"] == OVERWRITE
    assert (project / "README.md").read_text(encoding="utf-8") == "nuevo\n"


def test_rejected_write_leaves_the_file_intact(make_project):
    project = make_project(files={"README.md": "original\n"})
    tools = tools_by_name(project, approver=deny_all)

    call(tools["write_file"], path="README.md", content="pisado\n")

    assert (project / "README.md").read_text(encoding="utf-8") == "original\n"


def test_write_refuses_paths_outside_even_when_approved(make_project):
    """La aprobación no levanta el confinamiento: son controles independientes."""
    project = make_project()
    tools = tools_by_name(project, approver=allow_all)

    result = call(tools["write_file"], path="../fuera.txt", content="x")

    assert "error" in result
    assert not (project.parent / "fuera.txt").exists()


def test_approver_sees_the_previous_content(make_project):
    """Aprobar a ciegas es igual a no tener compuerta."""
    seen = []

    def recording_approver(request: WriteRequest) -> bool:
        seen.append(request)
        return True

    project = make_project(files={"README.md": "linea vieja\n"})
    tools = tools_by_name(project, approver=recording_approver)

    call(tools["write_file"], path="README.md", content="linea nueva\n")

    assert len(seen) == 1
    assert seen[0].previous_content == "linea vieja\n"
    assert seen[0].is_overwrite

    diff = seen[0].diff()
    assert "-linea vieja" in diff
    assert "+linea nueva" in diff


def test_diff_for_a_new_file(make_project):
    seen = []
    project = make_project()
    tools = tools_by_name(project, approver=lambda r: seen.append(r) or True)

    call(tools["write_file"], path="nuevo.md", content="contenido\n")

    assert "/dev/null" in seen[0].diff()
    assert "+contenido" in seen[0].diff()
