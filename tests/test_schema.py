"""Tests de la generación de esquemas.

Reemplazan lo que antes garantizaba el SDK. Para un modelo chico el esquema es
toda la información que tiene sobre cómo llamar una herramienta, así que un
esquema mal generado se manifiesta como "el modelo es tonto" y en realidad es
un bug nuestro.
"""

from __future__ import annotations

import pytest

from forge.tools.schema import ToolDefinitionError, split_docstring, tool


def test_generates_schema_from_signature_and_docstring():
    @tool
    def buscar(patron: str, limite: int = 10) -> str:
        """Busca algo en el proyecto.

        Args:
            patron: Texto a buscar.
            limite: Cantidad máxima de resultados.
        """
        return f"{patron}:{limite}"

    schema = buscar.to_dict()

    assert schema["name"] == "buscar"
    assert schema["description"] == "Busca algo en el proyecto."

    properties = schema["input_schema"]["properties"]
    assert properties["patron"] == {"type": "string", "description": "Texto a buscar."}
    assert properties["limite"]["type"] == "integer"
    assert properties["limite"]["default"] == 10
    assert schema["input_schema"]["required"] == ["patron"]


def test_resolves_deferred_annotations():
    """`from __future__ import annotations` convierte las anotaciones en cadenas.

    Regresión: leerlas desde `inspect.signature` hacía que ningún tipo fuera
    reconocido y ninguna herramienta pudiera construirse.
    """

    @tool
    def contar(texto: str) -> str:
        """Cuenta caracteres.

        Args:
            texto: El texto a medir.
        """
        return str(len(texto))

    assert contar.input_schema["properties"]["texto"]["type"] == "string"


def test_multi_paragraph_description_is_kept():
    """La descripción larga es lo que le explica al modelo cuándo usarla."""

    @tool
    def escribir(ruta: str) -> str:
        """Escribe un archivo.

        Requiere aprobación humana. Si la rechazan, no reintentes.

        Args:
            ruta: Dónde escribir.
        """
        return ruta

    assert "Requiere aprobación humana" in escribir.description


def test_openai_format():
    @tool
    def simple(x: str) -> str:
        """Hace algo.

        Args:
            x: Un valor.
        """
        return x

    payload = simple.to_openai()

    assert payload["type"] == "function"
    assert payload["function"]["name"] == "simple"
    assert payload["function"]["parameters"]["properties"]["x"]["type"] == "string"


def test_call_invokes_the_function():
    @tool
    def doble(x: int) -> str:
        """Duplica.

        Args:
            x: Número.
        """
        return str(x * 2)

    assert doble.call({"x": 21}) == "42"


def test_rejects_a_function_without_docstring():
    with pytest.raises(ToolDefinitionError):

        @tool
        def sin_doc(x: str) -> str:
            return x


def test_rejects_an_unannotated_parameter():
    with pytest.raises(ToolDefinitionError):

        @tool
        def sin_tipo(x) -> str:
            """Falta la anotación.

            Args:
                x: Algo.
            """
            return x


def test_rejects_an_unsupported_type():
    """Falla al construir la herramienta, no en medio de una conversación."""
    with pytest.raises(ToolDefinitionError):

        @tool
        def compleja(x: dict) -> str:
            """Tipo no representable sin ambigüedad.

            Args:
                x: Un diccionario.
            """
            return str(x)


def test_split_docstring_without_args_section():
    description, params = split_docstring("Solo una descripción.")

    assert description == "Solo una descripción."
    assert params == {}


def test_split_docstring_joins_wrapped_argument_lines():
    description, params = split_docstring(
        "Resumen.\n\nArgs:\n    x: Primera linea\n        y su continuacion.\n"
    )

    assert params["x"] == "Primera linea y su continuacion."
