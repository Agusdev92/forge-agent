"""Cliente para un modelo servido localmente.

Habla el shape `/v1/chat/completions` de OpenAI, que implementan Ollama,
llama.cpp server, LM Studio y vLLM. Eso es una sola implementación contra un
formato que los cuatro ya soportan hoy — no una capa de adaptadores por si
mañana aparece otro runtime.

Costo conocido de esa elección: el endpoint compatible **no acepta el tamaño de
contexto**. En Ollama se configura del lado del runtime (por modelo). Si el
contexto queda corto, el runtime trunca la conversación en silencio y el
síntoma es un modelo que "se olvida" de lo que hizo hace dos pasos.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

import httpx

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "qwen2.5-coder:7b"
DEFAULT_TIMEOUT = 300.0


class ProviderError(Exception):
    """Falla al hablar con el modelo local."""


class ModelUnavailable(ProviderError):
    """No hay nadie escuchando en la URL configurada."""


class ModelTimeout(ProviderError):
    """El modelo tardó más de lo permitido."""


@dataclass(frozen=True)
class ModelConfig:
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    #: Con streaming el timeout mide el silencio **entre fragmentos**, no la
    #: duración total. Pero hay un silencio inevitable antes del primer token:
    #: el runtime carga el modelo en memoria y procesa el prompt entero sin
    #: emitir nada. En hardware limitado ese tramo mudo domina, y es la razón
    #: del valor alto — no cubre generación lenta, cubre el arranque.
    timeout: float = DEFAULT_TIMEOUT
    max_tokens: int = 2048
    #: Cero por defecto. Un agente que elige herramientas necesita respuestas
    #: reproducibles, no variadas.
    temperature: float = 0.0


@dataclass(frozen=True)
class ToolCall:
    name: str
    raw_arguments: str
    id: str = ""

    def arguments(self) -> dict:
        """Parsea los argumentos. Puede fallar: los modelos chicos emiten JSON roto."""
        if not self.raw_arguments.strip():
            return {}
        return json.loads(self.raw_arguments)


@dataclass(frozen=True)
class ChatResponse:
    content: str = ""
    tool_calls: list = field(default_factory=list)
    finish_reason: str = ""


class LocalChatClient:
    """Envía conversaciones al modelo local y normaliza la respuesta."""

    def __init__(self, config: Optional[ModelConfig] = None, http_client=None):
        self.config = config or ModelConfig()
        self._client = http_client or httpx.Client(timeout=self.config.timeout)

    def chat(
        self, messages: list, tools: Optional[list] = None, on_token=None
    ) -> ChatResponse:
        """Pide una respuesta al modelo, consumiéndola por fragmentos.

        El streaming no es cosmético. Sin él, httpx espera la respuesta entera
        como un bloque y el timeout corre sobre el tiempo total de generación:
        en una GPU chica, una respuesta larga lo supera y la consulta se pierde
        aunque el modelo estuviera trabajando bien. Con streaming el reloj mide
        el silencio entre fragmentos, que es lo que de verdad indica que algo
        se colgó.

        `on_token` recibe cada fragmento de texto a medida que llega, para que
        quien llame pueda mostrar avance.
        """
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "stream": True,
        }
        if tools:
            payload["tools"] = [t.to_openai() for t in tools]

        url = f"{self.config.base_url.rstrip('/')}/chat/completions"

        try:
            with self._client.stream("POST", url, json=payload) as response:
                if response.status_code >= 400:
                    response.read()
                    raise ProviderError(
                        f"El modelo devolvió {response.status_code}: "
                        f"{response.text[:400]}"
                    )
                return self._consume(response, on_token)
        except httpx.ConnectError as exc:
            raise ModelUnavailable(
                f"No hay un modelo escuchando en {self.config.base_url}. "
                "¿Está corriendo el runtime (por ejemplo `ollama serve`)?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ModelTimeout(
                f"El modelo no emitió nada durante {self.config.timeout:.0f}s.\n"
                "   Suele ser el arranque: el runtime carga el modelo y procesa el "
                "prompt sin emitir nada.\n"
                "   Verificá con `ollama ps` si el modelo quedó en GPU o en CPU — "
                "en CPU esto es esperable.\n"
                "   Podés subir el límite con --timeout o acortar el prompt con "
                "--no-prompt-tools."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Error de red hablando con el modelo: {exc}") from exc

    def _consume(self, response, on_token=None) -> ChatResponse:
        """Acumula los fragmentos de un stream en una respuesta completa.

        Las llamadas a herramientas llegan partidas: el nombre suele venir en
        un fragmento y los argumentos repartidos en varios. Se acumulan por
        `index`, que es lo que permite además reconstruir varias llamadas en
        paralelo sin mezclarlas.
        """
        parts = []
        calls = {}
        finish_reason = ""
        raw_lines = []
        saw_stream = False

        for line in response.iter_lines():
            raw_lines.append(line)

            if not line or not line.startswith("data:"):
                continue

            saw_stream = True
            data = line[len("data:") :].strip()
            if data == "[DONE]":
                break

            try:
                chunk = json.loads(data)
            except ValueError:
                continue

            choices = chunk.get("choices") or []
            if not choices:
                continue

            choice = choices[0]
            delta = choice.get("delta") or choice.get("message") or {}

            text = delta.get("content")
            if text:
                parts.append(text)
                if on_token:
                    on_token(text)

            for raw in delta.get("tool_calls") or []:
                slot = calls.setdefault(
                    raw.get("index", len(calls)), {"id": "", "name": "", "arguments": ""}
                )
                if raw.get("id"):
                    slot["id"] = raw["id"]
                function = raw.get("function") or {}
                if function.get("name"):
                    slot["name"] = function["name"]
                arguments = function.get("arguments")
                if arguments:
                    # Algunos runtimes mandan el objeto entero de una sola vez.
                    slot["arguments"] += (
                        arguments if isinstance(arguments, str) else json.dumps(arguments)
                    )

            if choice.get("finish_reason"):
                finish_reason = choice["finish_reason"]

        if not saw_stream:
            # El runtime ignoró `stream: true` y mandó la respuesta completa.
            # Pasa con implementaciones parciales del endpoint compatible.
            return self._parse_body("\n".join(raw_lines))

        return ChatResponse(
            content="".join(parts),
            tool_calls=[
                ToolCall(name=c["name"], raw_arguments=c["arguments"], id=c["id"])
                for _, c in sorted(calls.items())
                if c["name"]
            ],
            finish_reason=finish_reason,
        )

    def _parse_body(self, text: str) -> ChatResponse:
        """Normaliza una respuesta completa (no fragmentada)."""
        try:
            body = json.loads(text)
        except ValueError as exc:
            raise ProviderError(
                f"El modelo devolvió algo que no es JSON: {text[:200]}"
            ) from exc

        choices = body.get("choices") or []
        if not choices:
            raise ProviderError(f"Respuesta sin 'choices': {json.dumps(body)[:300]}")

        message = choices[0].get("message") or {}

        calls = []
        for raw in message.get("tool_calls") or []:
            function = raw.get("function") or {}
            name = function.get("name")
            if not name:
                continue
            arguments = function.get("arguments", "")
            # Algunos runtimes ya lo entregan como objeto en vez de cadena.
            if isinstance(arguments, dict):
                arguments = json.dumps(arguments)
            calls.append(
                ToolCall(name=name, raw_arguments=arguments or "", id=raw.get("id", ""))
            )

        return ChatResponse(
            content=message.get("content") or "",
            tool_calls=calls,
            finish_reason=choices[0].get("finish_reason") or "",
        )

    def close(self) -> None:
        self._client.close()
