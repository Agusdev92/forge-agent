"""Tests del cliente contra un servidor local simulado.

Cubren el camino real —httpx, HTTP, parseo— sin necesitar un modelo. Lo que no
cubren, y conviene tenerlo presente al leerlos, es si un modelo concreto usa
bien las herramientas: eso solo se mide contra el runtime real.
"""

from __future__ import annotations

import pytest

from forge.providers import (
    LocalChatClient,
    ModelConfig,
    ModelUnavailable,
    ProviderError,
)
from conftest import completion, tool_call


def client_for(server, **overrides):
    return LocalChatClient(ModelConfig(base_url=server.base_url, **overrides))


def test_plain_answer(model_server):
    model_server.responses.append((200, completion("El proyecto usa Python.")))

    response = client_for(model_server).chat([{"role": "user", "content": "¿?"}])

    assert response.content == "El proyecto usa Python."
    assert response.tool_calls == []


def test_sends_the_configured_model_and_tools(model_server, make_project):
    from forge.tools import build_tools

    model_server.responses.append((200, completion("ok")))
    tools = build_tools(make_project())

    client_for(model_server, model="qwen2.5-coder:7b").chat([], tools=tools)

    sent = model_server.requests[0]
    assert sent["model"] == "qwen2.5-coder:7b"
    assert sent["stream"] is False
    assert {t["function"]["name"] for t in sent["tools"]} == {t.name for t in tools}


def test_parses_native_tool_calls(model_server):
    model_server.responses.append(
        (200, completion("", [tool_call("forge_doctor", {"path": "."})]))
    )

    response = client_for(model_server).chat([])

    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "forge_doctor"
    assert response.tool_calls[0].arguments() == {"path": "."}


def test_accepts_arguments_already_decoded(model_server):
    """Algunos runtimes entregan `arguments` como objeto, no como cadena."""
    model_server.responses.append(
        (
            200,
            completion(
                "",
                [
                    {
                        "id": "c1",
                        "function": {"name": "forge_stats", "arguments": {"path": "."}},
                    }
                ],
            ),
        )
    )

    response = client_for(model_server).chat([])

    assert response.tool_calls[0].arguments() == {"path": "."}


def test_connection_refused_is_actionable():
    """El error tiene que decir qué hacer, no solo que falló."""
    client = LocalChatClient(ModelConfig(base_url="http://127.0.0.1:1/v1"))

    with pytest.raises(ModelUnavailable) as exc:
        client.chat([])

    assert "ollama serve" in str(exc.value)


def test_http_error_surfaces_the_body(model_server):
    model_server.responses.append((500, {"error": "model not found"}))

    with pytest.raises(ProviderError) as exc:
        client_for(model_server).chat([])

    assert "500" in str(exc.value)
    assert "model not found" in str(exc.value)


def test_non_json_response(model_server):
    model_server.responses.append((200, b"<html>proxy</html>"))

    with pytest.raises(ProviderError) as exc:
        client_for(model_server).chat([])

    assert "no es JSON" in str(exc.value)


def test_response_without_choices(model_server):
    model_server.responses.append((200, {"object": "chat.completion"}))

    with pytest.raises(ProviderError) as exc:
        client_for(model_server).chat([])

    assert "choices" in str(exc.value)


def test_tool_call_without_name_is_skipped(model_server):
    """Una entrada rota no debe romper el parseo de las demás."""
    model_server.responses.append(
        (
            200,
            completion(
                "",
                [
                    {"id": "c1", "function": {"arguments": "{}"}},
                    tool_call("forge_stats", {}, call_id="c2"),
                ],
            ),
        )
    )

    response = client_for(model_server).chat([])

    assert [c.name for c in response.tool_calls] == ["forge_stats"]
