"""El ciclo del agente.

Con el SDK de Anthropic esto lo resolvía el *tool runner*. Los runtimes locales
no traen equivalente, así que el ciclo se escribe acá.

El diseño está gobernado por una premisa: **el modelo se va a equivocar
seguido.** En hardware limitado va a inventar nombres de herramientas, emitir
JSON roto, pasar parámetros que no existen y llamar a la misma herramienta en
loop. Cada uno de esos casos vuelve al modelo como un resultado de herramienta
que describe el problema, nunca como una excepción que corta la ejecución: un
modelo que recibe "esa herramienta no existe, las válidas son X, Y, Z" suele
corregir en el intento siguiente.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from forge.providers.prompted import extract_from_text, tool_instructions

DEFAULT_MAX_ITERATIONS = 8

SYSTEM_PROMPT = """\
Sos Forge, un asistente que analiza proyectos de software.

Reglas:
- Usá las herramientas para averiguar cosas del proyecto. No inventes datos que
  no viste: si no llamaste a la herramienta, no sabés la respuesta.
- Las rutas son siempre relativas a la raíz del proyecto. Nunca uses rutas
  absolutas ni `..`.
- Escribir archivos requiere aprobación de la persona usuaria. Si rechaza una
  escritura, no la reintentes: proponé otra cosa o explicá por qué hacía falta.
- Cuando ya tengas lo que necesitás, respondé en prosa breve y concreta.
"""


@dataclass(frozen=True)
class ToolInvocation:
    name: str
    arguments: dict
    result: str
    failed: bool = False


@dataclass
class AgentResult:
    answer: str = ""
    iterations: int = 0
    invocations: list = field(default_factory=list)
    #: "answer" | "max_iterations" | "empty_response"
    stop_reason: str = "answer"

    @property
    def hit_limit(self) -> bool:
        return self.stop_reason == "max_iterations"


def _tool_error(message: str) -> str:
    return json.dumps({"error": message}, ensure_ascii=False)


def _reports_error(output: str) -> bool:
    """Una herramienta que devuelve `{"error": ...}` no tuvo éxito.

    Sin esto, una escritura **rechazada** por la persona usuaria aparecía en la
    traza con el mismo símbolo que una exitosa. Es justo lo que la traza tiene
    que evitar: el modelo suele afirmar que escribió el archivo, y quien lee no
    tendría cómo notar que no ocurrió.
    """
    try:
        payload = json.loads(output)
    except (ValueError, TypeError):
        return False
    return isinstance(payload, dict) and "error" in payload


class Agent:
    def __init__(
        self,
        client,
        tools,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        describe_tools_in_prompt: bool = True,
        on_token=None,
    ):
        self.client = client
        self.tools = list(tools)
        self.max_iterations = max_iterations
        self.describe_tools_in_prompt = describe_tools_in_prompt
        self.on_token = on_token
        self._by_name = {t.name: t for t in self.tools}

    # ------------------------------------------------------------------

    def system_prompt(self) -> str:
        """El prompt incluye la descripción de las herramientas por defecto.

        Cuesta unos cientos de tokens y es lo que mantiene utilizable a un
        modelo sin tool calling nativo. En un modelo que sí lo soporta, la
        redundancia no molesta.
        """
        if not self.describe_tools_in_prompt:
            return SYSTEM_PROMPT
        return f"{SYSTEM_PROMPT}\n{tool_instructions(self.tools)}"

    def run(self, question: str) -> AgentResult:
        messages = [
            {"role": "system", "content": self.system_prompt()},
            {"role": "user", "content": question},
        ]
        result = AgentResult()

        for iteration in range(1, self.max_iterations + 1):
            result.iterations = iteration
            response = self.client.chat(
                messages, tools=self.tools, on_token=self.on_token
            )

            calls = response.tool_calls or extract_from_text(
                response.content, self._by_name
            )

            if not calls:
                if not response.content.strip():
                    result.stop_reason = "empty_response"
                    return result
                result.answer = response.content.strip()
                result.stop_reason = "answer"
                return result

            self._append_assistant(messages, response, calls)

            for call in calls:
                invocation = self._dispatch(call)
                result.invocations.append(invocation)
                self._append_result(messages, call, invocation)

        result.stop_reason = "max_iterations"
        result.answer = (
            f"Me quedé sin pasos ({self.max_iterations}) antes de llegar a una "
            "respuesta. Probá con una pregunta más acotada."
        )
        return result

    # ------------------------------------------------------------------

    def _append_assistant(self, messages, response, calls) -> None:
        """El turno del asistente cambia según de dónde salieron las llamadas.

        Una llamada nativa trae `id` y el protocolo exige devolver el resultado
        en un mensaje `tool` que lo referencie. Una extraída del texto no tiene
        `id`, así que el intercambio se hace en prosa — mandar un `tool_call_id`
        inventado hace que algunos runtimes rechacen la conversación entera.
        """
        if calls and calls[0].id:
            messages.append(
                {
                    "role": "assistant",
                    "content": response.content or None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": c.raw_arguments},
                        }
                        for c in calls
                    ],
                }
            )
        else:
            messages.append({"role": "assistant", "content": response.content})

    def _append_result(self, messages, call, invocation) -> None:
        if call.id:
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": invocation.result}
            )
        else:
            messages.append(
                {
                    "role": "user",
                    "content": f"Resultado de {call.name}:\n{invocation.result}",
                }
            )

    def _dispatch(self, call) -> ToolInvocation:
        target = self._by_name.get(call.name)

        if target is None:
            available = ", ".join(sorted(self._by_name))
            return ToolInvocation(
                name=call.name,
                arguments={},
                result=_tool_error(
                    f"No existe la herramienta '{call.name}'. Disponibles: {available}"
                ),
                failed=True,
            )

        try:
            arguments = call.arguments()
        except ValueError:
            return ToolInvocation(
                name=call.name,
                arguments={},
                result=_tool_error(
                    "Los argumentos no son JSON válido. Reintentá con un objeto "
                    'JSON, por ejemplo {"path": "."}'
                ),
                failed=True,
            )

        if not isinstance(arguments, dict):
            return ToolInvocation(
                name=call.name,
                arguments={},
                result=_tool_error("Los argumentos tienen que ser un objeto JSON."),
                failed=True,
            )

        try:
            output = target.call(arguments)
            return ToolInvocation(
                name=call.name,
                arguments=arguments,
                result=output,
                failed=_reports_error(output),
            )
        except TypeError as exc:
            # Parámetro inventado o faltante: el modelo puede corregirlo si se
            # le dice cuáles acepta la herramienta.
            expected = ", ".join(target.input_schema.get("properties", {})) or "ninguno"
            return ToolInvocation(
                name=call.name,
                arguments=arguments,
                result=_tool_error(
                    f"Argumentos inválidos para {call.name} ({exc}). "
                    f"Parámetros aceptados: {expected}"
                ),
                failed=True,
            )
        except Exception as exc:  # una herramienta rota no debe matar el ciclo
            return ToolInvocation(
                name=call.name,
                arguments=arguments,
                result=_tool_error(f"La herramienta falló: {exc}"),
                failed=True,
            )
