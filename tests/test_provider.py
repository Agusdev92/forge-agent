"""Tests del cliente contra un servidor local simulado.

Cubren el camino real —httpx, HTTP, SSE, parseo— sin necesitar un modelo. Lo
que no cubren, y conviene tenerlo presente al leerlos, es si un modelo concreto
usa bien las herramientas: eso solo se mide contra el runtime real.
"""

from __future__ import annotations

import pytest

from conftest import completion, sse, text_delta, tool_delta
from forge.providers import (
    LocalChatClient,
    ModelConfig,
    ModelUnavailable,
    ProviderError,
)


def client_for(server, **overrides):
    return LocalChatClient(ModelConfig(base_url=server.base_url, **overrides))


# --------------------------------------------------------------------------
# Texto
# --------------------------------------------------------------------------


def test_reassembles_streamed_text(model_server):
    model_server.responses.append(
        (200, sse(text_delta("El proyecto "), text_delta("usa Python."), ))
    )

    response = client_for(model_server).chat([{"role": "user", "content": "¿?"}])

    assert response.content == "El proyecto usa Python."
    assert response.tool_calls == []


def test_reports_each_fragment_as_it_arrives(model_server):
    """`on_token` es lo que permite mostrar avance en hardware lento."""
    model_server.responses.append(
        (200, sse(text_delta("uno "), text_delta("dos "), text_delta("tres")))
    )
    seen = []

    client_for(model_server).chat([], on_token=seen.append)

    assert seen == ["uno ", "dos ", "tres"]


def test_requests_streaming(model_server):
    model_server.responses.append((200, sse(text_delta("ok"))))

    client_for(model_server).chat([])

    assert model_server.requests[0]["stream"] is True


def test_sends_the_configured_model_and_tools(model_server, make_project):
    from forge.tools import build_tools

    model_server.responses.append((200, sse(text_delta("ok"))))
    tools = build_tools(make_project())

    client_for(model_server, model="qwen2.5-coder:7b").chat([], tools=tools)

    sent = model_server.requests[0]
    assert sent["model"] == "qwen2.5-coder:7b"
    assert {t["function"]["name"] for t in sent["tools"]} == {t.name for t in tools}


# --------------------------------------------------------------------------
# Llamadas a herramientas repartidas en fragmentos
# --------------------------------------------------------------------------


def test_reassembles_a_tool_call_split_across_fragments(model_server):
    """El caso normal: el nombre llega en un fragmento y los argumentos en varios."""
    model_server.responses.append(
        (
            200,
            sse(
                tool_delta(call_id="c1", name="forge_doctor", arguments=""),
                tool_delta(arguments='{"path"'),
                tool_delta(arguments=': "."}'),
            ),
        )
    )

    response = client_for(model_server).chat([])

    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "forge_doctor"
    assert response.tool_calls[0].id == "c1"
    assert response.tool_calls[0].arguments() == {"path": "."}


def test_keeps_parallel_calls_separate(model_server):
    """El `index` es lo que evita que dos llamadas se mezclen en una sola."""
    model_server.responses.append(
        (
            200,
            sse(
                tool_delta(index=0, call_id="c1", name="forge_doctor"),
                tool_delta(index=1, call_id="c2", name="forge_stats"),
                tool_delta(index=0, arguments='{"path": "a"}'),
                tool_delta(index=1, arguments='{"path": "b"}'),
            ),
        )
    )

    calls = client_for(model_server).chat([]).tool_calls

    assert [c.name for c in calls] == ["forge_doctor", "forge_stats"]
    assert calls[0].arguments() == {"path": "a"}
    assert calls[1].arguments() == {"path": "b"}


def test_accepts_arguments_sent_as_an_object(model_server):
    """Algunos runtimes mandan el objeto entero en vez de una cadena."""
    model_server.responses.append(
        (
            200,
            sse(tool_delta(call_id="c1", name="forge_stats", arguments={"path": "."})),
        )
    )

    assert client_for(model_server).chat([]).tool_calls[0].arguments() == {"path": "."}


def test_ignores_a_fragment_without_name(model_server):
    model_server.responses.append(
        (200, sse(tool_delta(index=0, arguments="{}"), text_delta("hola")))
    )

    response = client_for(model_server).chat([])

    assert response.tool_calls == []
    assert response.content == "hola"


# --------------------------------------------------------------------------
# Runtimes que se desvían del shape
# --------------------------------------------------------------------------


def test_falls_back_when_the_runtime_ignores_streaming(model_server):
    """Una implementación parcial puede devolver la respuesta entera igual."""
    model_server.responses.append((200, completion("Respuesta completa.")))

    response = client_for(model_server).chat([])

    assert response.content == "Respuesta completa."


def test_skips_malformed_fragments(model_server):
    body = b'data: {"roto\n\ndata: ' + b'{"choices":[{"delta":{"content":"ok"}}]}\n\n'
    model_server.responses.append((200, body + b"data: [DONE]\n\n"))

    assert client_for(model_server).chat([]).content == "ok"


# --------------------------------------------------------------------------
# Errores
# --------------------------------------------------------------------------


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
