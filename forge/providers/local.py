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
    #: Generoso a propósito: en una GPU chica, un 7B puede tardar bastante en
    #: la primera respuesta porque además carga el modelo en memoria.
    timeout: float = 180.0
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

    def chat(self, messages: list, tools: Optional[list] = None) -> ChatResponse:
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "stream": False,
        }
        if tools:
            payload["tools"] = [t.to_openai() for t in tools]

        url = f"{self.config.base_url.rstrip('/')}/chat/completions"

        try:
            response = self._client.post(url, json=payload)
        except httpx.ConnectError as exc:
            raise ModelUnavailable(
                f"No hay un modelo escuchando en {self.config.base_url}. "
                "¿Está corriendo el runtime (por ejemplo `ollama serve`)?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ModelTimeout(
                f"El modelo no respondió en {self.config.timeout:.0f}s. "
                "En hardware limitado puede ser normal en la primera llamada."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Error de red hablando con el modelo: {exc}") from exc

        if response.status_code >= 400:
            raise ProviderError(
                f"El modelo devolvió {response.status_code}: {response.text[:400]}"
            )

        return self._parse(response)

    def _parse(self, response) -> ChatResponse:
        """Normaliza la respuesta, tolerando runtimes que se desvían del shape."""
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError(
                f"El modelo devolvió algo que no es JSON: {response.text[:200]}"
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
