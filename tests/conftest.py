"""Fixtures compartidas.

Los analizadores de Forge son funciones sobre el sistema de archivos, así que
los tests construyen proyectos reales en directorios temporales en vez de
mockear `os`. Es más lento pero verifica lo que el código realmente hace: los
tres falsos positivos que aparecieron en la Fase 1 eran del recorrido de disco,
justo lo que un mock habría dado por bueno.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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


# --------------------------------------------------------------------------
# Servidor de modelo local simulado
# --------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.server.requests.append(json.loads(self.rfile.read(length) or b"{}"))

        status, body = self.server.responses.pop(0)
        payload = body if isinstance(body, bytes) else json.dumps(body).encode()

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        """Silencio: los logs del stub ensucian la salida de pytest."""


@pytest.fixture
def model_server():
    """Servidor que habla el shape `/v1/chat/completions`.

    Da cobertura real del cliente sobre HTTP —serialización, códigos de estado,
    respuestas malformadas— sin necesitar un modelo. Lo que **no** cubre es si
    un modelo concreto usa bien las herramientas; eso solo se mide con el
    runtime real.
    """
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.requests = []
    server.responses = []

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    host, port = server.server_address[:2]
    server.base_url = f"http://{host}:{port}/v1"

    yield server

    server.shutdown()
    server.server_close()


def completion(content="", tool_calls=None):
    """Construye una respuesta con el shape que devuelven los runtimes."""
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message, "finish_reason": "stop"}]}


def tool_call(name, arguments, call_id="call_1"):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }
