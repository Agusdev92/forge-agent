"""Extracción de llamadas a herramientas desde el texto de la respuesta.

Los modelos locales chicos fallan de dos maneras con las herramientas: algunos
no soportan el mecanismo nativo, y muchos de los que sí lo soportan igual
escriben la llamada como texto en vez de emitirla en el campo `tool_calls`.

Este módulo cubre las dos. Se aplica **siempre**, no solo cuando el nativo
falla: si la respuesta trae `tool_calls`, se usan esas; si no, se busca en el
texto antes de darla por respuesta final. Es barato y rescata justamente el
caso más común en hardware limitado.

Guarda de precisión: solo se acepta una llamada cuyo nombre coincida con una
herramienta registrada. Sin esa guarda, cualquier JSON que el modelo imprima
como parte de su respuesta —incluido el que devuelven nuestras propias
herramientas— se interpretaría como una llamada.
"""

from __future__ import annotations

import json
from typing import Iterator

from forge.providers.local import ToolCall

#: Claves con las que los modelos suelen nombrar la herramienta y sus argumentos.
NAME_KEYS = ("tool", "name", "tool_name", "function")
ARGUMENT_KEYS = ("arguments", "parameters", "args", "input")


def iter_json_objects(text: str) -> Iterator[str]:
    """Devuelve los objetos JSON balanceados que aparezcan en el texto.

    Se hace con un escáner de llaves y no con una expresión regular porque los
    argumentos pueden traer objetos anidados, y una regex no cuenta llaves.
    Las cadenas se saltean para que una `{` dentro de un string no confunda el
    conteo.
    """
    depth = 0
    start = None
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                yield text[start : index + 1]
                start = None


def extract_from_text(text: str, known_names) -> list:
    """Busca llamadas a herramientas en el texto libre del modelo."""
    if not text:
        return []

    known = set(known_names)
    calls = []

    for candidate in iter_json_objects(text):
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue

        name = next(
            (data[k] for k in NAME_KEYS if isinstance(data.get(k), str)), None
        )
        if name not in known:
            continue

        arguments = next(
            (data[k] for k in ARGUMENT_KEYS if isinstance(data.get(k), dict)), {}
        )
        calls.append(
            ToolCall(name=name, raw_arguments=json.dumps(arguments, ensure_ascii=False))
        )

    return calls


def tool_instructions(tools) -> str:
    """Describe las herramientas en el prompt, para modelos sin soporte nativo.

    Se incluye siempre. Cuesta unos cientos de tokens y es lo que permite que
    un modelo sin tool calling nativo siga siendo utilizable.
    """
    lines = [
        "Tenés estas herramientas disponibles:",
        "",
    ]

    for t in tools:
        params = t.input_schema.get("properties", {})
        signature = ", ".join(
            f"{name} ({spec.get('type', 'string')})" for name, spec in params.items()
        )
        lines.append(f"- {t.name}({signature}): {t.description.splitlines()[0]}")

    lines += [
        "",
        "Para usar una, respondé ÚNICAMENTE con un objeto JSON de esta forma:",
        '{"tool": "nombre_de_la_herramienta", "arguments": {"param": "valor"}}',
        "",
        "Una sola herramienta por respuesta. No expliques la llamada ni la",
        "envuelvas en texto: el JSON solo. Cuando ya tengas la información que",
        "necesitás, respondé en prosa sin ningún JSON.",
    ]

    return "\n".join(lines)
