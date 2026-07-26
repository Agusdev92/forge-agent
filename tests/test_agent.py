"""Tests del ciclo del agente.

La mayoría son casos de modelo equivocándose, porque es lo que un modelo local
chico hace seguido: nombres de herramientas inventados, JSON roto, parámetros
que no existen. En todos, la expectativa es la misma — el ciclo sigue vivo y el
modelo recibe una descripción del problema con la que puede corregir.
"""

from __future__ import annotations

import json

import pytest

from forge.agent import Agent
from forge.providers.local import ChatResponse, ToolCall
from forge.tools import build_tools
from forge.tools.schema import Tool


class ScriptedClient:
    """Devuelve respuestas prefijadas y registra lo que se le mandó."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.conversations = []

    def chat(self, messages, tools=None, on_token=None):
        self.on_token = on_token
        self.conversations.append([dict(m) for m in messages])
        if not self.responses:
            raise AssertionError("El agente pidió más respuestas de las previstas")
        return self.responses.pop(0)


def native(name, arguments, call_id="c1"):
    return ChatResponse(
        tool_calls=[ToolCall(name=name, raw_arguments=json.dumps(arguments), id=call_id)]
    )


def agent_for(project, *responses, **kwargs):
    client = ScriptedClient(*responses)
    return Agent(client, build_tools(project), **kwargs), client


# --------------------------------------------------------------------------
# Camino feliz
# --------------------------------------------------------------------------


def test_answers_without_tools(make_project):
    agent, _ = agent_for(make_project(), ChatResponse(content="Hola."))

    result = agent.run("¿todo bien?")

    assert result.answer == "Hola."
    assert result.iterations == 1
    assert result.invocations == []


def test_calls_a_tool_and_then_answers(healthy_project):
    agent, client = agent_for(
        healthy_project,
        native("forge_doctor", {"path": "."}),
        ChatResponse(content="El proyecto está sano."),
    )

    result = agent.run("¿cómo está el proyecto?")

    assert result.answer == "El proyecto está sano."
    assert [i.name for i in result.invocations] == ["forge_doctor"]
    assert not result.invocations[0].failed

    # El resultado vuelve como mensaje `tool` referenciando el id.
    second = client.conversations[1]
    assert second[-1]["role"] == "tool"
    assert second[-1]["tool_call_id"] == "c1"


def test_tool_instructions_are_in_the_system_prompt(make_project):
    """Un modelo sin soporte nativo necesita que se las describan."""
    agent, _ = agent_for(make_project(), ChatResponse(content="ok"))

    prompt = agent.system_prompt()

    assert "forge_doctor" in prompt
    assert '{"tool"' in prompt


def test_tool_descriptions_can_be_omitted(make_project):
    agent, _ = agent_for(
        make_project(), ChatResponse(content="ok"), describe_tools_in_prompt=False
    )

    assert "forge_doctor" not in agent.system_prompt()


# --------------------------------------------------------------------------
# Llamadas escritas como texto (modelos sin soporte nativo)
# --------------------------------------------------------------------------


def test_extracts_a_tool_call_written_as_text(healthy_project):
    """El caso más común en hardware limitado: la llamada llega como prosa."""
    agent, client = agent_for(
        healthy_project,
        ChatResponse(content='{"tool": "forge_stats", "arguments": {"path": "."}}'),
        ChatResponse(content="Tiene 5 archivos."),
    )

    result = agent.run("¿cuántos archivos hay?")

    assert [i.name for i in result.invocations] == ["forge_stats"]
    # Sin id no se puede usar el mensaje `tool`: un tool_call_id inventado hace
    # que algunos runtimes rechacen la conversación entera.
    assert client.conversations[1][-1]["role"] == "user"


def test_ignores_json_that_is_not_a_tool_call(make_project):
    """La salida de nuestras propias herramientas es JSON y no debe reinterpretarse."""
    agent, _ = agent_for(
        make_project(),
        ChatResponse(content='El scan devolvió {"python_files": 3, "todos": 0}.'),
    )

    result = agent.run("¿?")

    assert result.invocations == []
    assert result.stop_reason == "answer"


# --------------------------------------------------------------------------
# El modelo se equivoca
# --------------------------------------------------------------------------


def test_unknown_tool_returns_the_valid_names(make_project):
    agent, _ = agent_for(
        make_project(),
        native("forge_inventada", {}),
        ChatResponse(content="Perdón, ya entendí."),
    )

    result = agent.run("¿?")

    assert result.invocations[0].failed
    payload = json.loads(result.invocations[0].result)
    assert "forge_doctor" in payload["error"]
    assert result.answer == "Perdón, ya entendí."


def test_malformed_json_arguments(make_project):
    agent, _ = agent_for(
        make_project(),
        ChatResponse(tool_calls=[ToolCall("forge_doctor", "{path: .}", id="c1")]),
        ChatResponse(content="Listo."),
    )

    result = agent.run("¿?")

    assert result.invocations[0].failed
    assert "JSON" in json.loads(result.invocations[0].result)["error"]


def test_unexpected_parameter_lists_the_accepted_ones(make_project):
    agent, _ = agent_for(
        make_project(),
        native("forge_doctor", {"ruta": "."}),
        ChatResponse(content="Listo."),
    )

    result = agent.run("¿?")

    error = json.loads(result.invocations[0].result)["error"]
    assert result.invocations[0].failed
    assert "path" in error


def test_a_broken_tool_does_not_kill_the_loop(make_project):
    """Una excepción inesperada en una herramienta no debe cortar el ciclo."""

    def explode():
        raise RuntimeError("boom")

    rota = Tool(
        name="rota",
        description="Falla siempre.",
        input_schema={"type": "object", "properties": {}},
        func=explode,
    )

    agent = Agent(
        ScriptedClient(native("rota", {}), ChatResponse(content="Sigo vivo.")),
        [rota],
    )

    result = agent.run("¿?")

    assert result.invocations[0].failed
    assert "boom" in result.invocations[0].result
    assert result.answer == "Sigo vivo."


# --------------------------------------------------------------------------
# Topes
# --------------------------------------------------------------------------


def test_stops_at_the_iteration_limit(healthy_project):
    """Un modelo que llama en loop tiene que encontrar un tope."""
    agent, _ = agent_for(
        healthy_project,
        *[native("forge_doctor", {"path": "."}) for _ in range(3)],
        max_iterations=3,
    )

    result = agent.run("¿?")

    assert result.stop_reason == "max_iterations"
    assert result.hit_limit
    assert result.iterations == 3


def test_empty_response_is_reported(make_project):
    agent, _ = agent_for(make_project(), ChatResponse(content="   "))

    result = agent.run("¿?")

    assert result.stop_reason == "empty_response"
    assert not result.answer


def test_a_rejected_write_is_marked_as_failed(make_project):
    """Regresión: una escritura rechazada aparecía en la traza como exitosa.

    El modelo suele afirmar que escribió el archivo. Si la traza le da el
    símbolo de éxito, quien lee no tiene cómo notar que no ocurrió.
    """
    project = make_project()
    agent = Agent(
        ScriptedClient(
            native("write_file", {"path": "x.md", "content": "hola"}),
            ChatResponse(content="Ya está."),
        ),
        build_tools(project),  # sin aprobador: deniega por defecto
    )

    result = agent.run("escribí x.md")

    assert result.invocations[0].failed
    assert not (project / "x.md").exists()


def test_a_successful_write_is_not_marked_as_failed(make_project):
    from forge.tools.approval import allow_all

    project = make_project()
    agent = Agent(
        ScriptedClient(
            native("write_file", {"path": "x.md", "content": "hola"}),
            ChatResponse(content="Listo."),
        ),
        build_tools(project, approver=allow_all),
    )

    result = agent.run("escribí x.md")

    assert not result.invocations[0].failed
    assert (project / "x.md").read_text(encoding="utf-8") == "hola"


def test_a_tool_returning_a_list_is_not_treated_as_an_error(healthy_project):
    """`forge_tree` devuelve una lista JSON, no un objeto."""
    agent = Agent(
        ScriptedClient(
            native("forge_tree", {"path": "."}), ChatResponse(content="Listo.")
        ),
        build_tools(healthy_project),
    )

    result = agent.run("¿?")

    assert not result.invocations[0].failed


def test_the_progress_callback_reaches_the_client(make_project):
    """Sin señal de avance, una terminal quieta no se distingue de un cuelgue."""
    client = ScriptedClient(ChatResponse(content="ok"))
    agent = Agent(client, build_tools(make_project()), on_token=print)

    agent.run("¿?")

    assert client.on_token is print
