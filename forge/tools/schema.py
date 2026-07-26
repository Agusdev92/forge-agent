"""Definición de herramientas y generación de sus esquemas JSON.

Reemplaza al decorador `@beta_tool` del SDK de Anthropic, que quedó fuera al
pasar a modelos locales. Hace lo mismo que hacía aquel: leer la firma y el
docstring de una función y derivar el esquema que el modelo va a ver.

Mantener la descripción de los parámetros en el docstring no es cosmético —
para un modelo chico, esa descripción es toda la información que tiene sobre
cómo llamar la herramienta, y es la diferencia entre una llamada correcta y
tres intentos fallidos.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from typing import Callable, get_type_hints

#: Solo tipos que un esquema JSON representa sin ambigüedad. Si hace falta uno
#: nuevo se agrega acá; un tipo no soportado falla al construir la herramienta
#: y no en medio de una conversación con el modelo.
JSON_TYPES = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}

_ARGS_HEADER = re.compile(r"^\s*Args:\s*$", re.MULTILINE)
_ARG_LINE = re.compile(r"^\s+(\w+):\s*(.+)$")


class ToolDefinitionError(Exception):
    """La función no puede convertirse en herramienta."""


def split_docstring(doc: str) -> tuple:
    """Separa la descripción general de las descripciones por parámetro."""
    if not doc:
        return "", {}

    doc = inspect.cleandoc(doc)
    match = _ARGS_HEADER.search(doc)

    if not match:
        return doc.strip(), {}

    description = doc[: match.start()].strip()
    params = {}
    current = None

    for line in doc[match.end():].splitlines():
        if not line.strip():
            continue
        arg = _ARG_LINE.match(line)
        if arg:
            current = arg.group(1)
            params[current] = arg.group(2).strip()
        elif current:
            params[current] += " " + line.strip()

    return description, params


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict
    func: Callable

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def to_openai(self) -> dict:
        """Formato que esperan Ollama, llama.cpp, LM Studio y vLLM."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def call(self, arguments: dict) -> str:
        return self.func(**(arguments or {}))


def tool(func: Callable) -> Tool:
    """Convierte una función en herramienta, derivando el esquema de su firma."""
    description, param_docs = split_docstring(func.__doc__ or "")

    if not description:
        raise ToolDefinitionError(f"{func.__name__} no tiene docstring")

    properties = {}
    required = []

    # Los módulos que definen herramientas usan `from __future__ import
    # annotations`, con lo cual `parameter.annotation` es la *cadena* "str" y
    # no el tipo. `get_type_hints` las evalúa; leerlas de la firma directamente
    # hacía que ningún tipo fuera reconocido.
    try:
        hints = get_type_hints(func)
    except Exception as exc:  # anotación que no resuelve
        raise ToolDefinitionError(
            f"{func.__name__}: no se pudieron resolver las anotaciones ({exc})"
        ) from exc

    for name, parameter in inspect.signature(func).parameters.items():
        annotation = hints.get(name, inspect.Parameter.empty)

        if annotation is inspect.Parameter.empty:
            raise ToolDefinitionError(
                f"{func.__name__}: el parámetro '{name}' no tiene anotación de tipo"
            )
        if annotation not in JSON_TYPES:
            raise ToolDefinitionError(
                f"{func.__name__}: tipo no soportado para '{name}': {annotation}"
            )

        schema = {"type": JSON_TYPES[annotation]}

        if name in param_docs:
            schema["description"] = param_docs[name]
        if parameter.default is not inspect.Parameter.empty:
            schema["default"] = parameter.default
        else:
            required.append(name)

        properties[name] = schema

    input_schema = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        input_schema["required"] = required

    return Tool(
        name=func.__name__,
        description=description,
        input_schema=input_schema,
        func=func,
    )
