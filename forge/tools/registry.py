"""Las herramientas que el modelo puede invocar.

`build_tools()` es una fábrica que cierra sobre la raíz del proyecto y la
política de aprobación. Eso es deliberado: si la raíz fuera un parámetro de las
herramientas, el modelo podría elegirla y el confinamiento de `sandbox.py` no
serviría de nada. El modelo decide *qué* mirar dentro del proyecto; nunca
*cuál* es el proyecto ni si una escritura se ejecuta.

Los esquemas JSON los genera `@tool` a partir de la firma y el docstring
de cada función, así que la documentación de los parámetros no es decorativa:
es literalmente lo que el modelo lee para decidir cómo llamarlas.
"""

from __future__ import annotations

import json
from pathlib import Path


from forge.core.doctor import Doctor
from forge.core.project import Project
from forge.core.scanner import Scanner
from forge.core.stats import Stats
from forge.core.tree import DEFAULT_MAX_DEPTH, Tree
from forge.tools.schema import tool
from forge.tools.approval import CREATE, OVERWRITE, WriteRequest, deny_all
from forge.tools.sandbox import (
    MAX_READ_BYTES,
    PathOutsideProject,
    relative_to_root,
    resolve_within,
)


#: Superficie reducida para modelos chicos.
#:
#: Un modelo de 1B–3B elige mal entre siete herramientas: se confunde entre las
#: que se parecen (`analyze`, `doctor`, `stats`) y gasta pasos. Estas tres
#: cubren el ciclo completo —descubrir, leer, escribir— sin opciones ambiguas:
#: `forge_analyze` ya devuelve estructura y salud en una sola llamada, con lo
#: cual no hace falta ninguna de las otras de análisis.
MINIMAL_TOOLS = ("forge_analyze", "read_file", "write_file")

#: Las herramientas que no modifican nada.
#:
#: Existe porque un modelo chico no distingue "evaluá esto" de "producí esto":
#: ante "leé el README y decime si está bien", un 3B eligió `write_file` y
#: propuso reescribirlo entero, borrando secciones. La compuerta de aprobación
#: lo frenó, pero la consulta se perdió igual. Si la pregunta es una pregunta,
#: lo más barato es que la herramienta de escritura ni esté sobre la mesa.
READ_ONLY_TOOLS = (
    "forge_analyze",
    "forge_doctor",
    "forge_stats",
    "forge_scan",
    "forge_tree",
    "read_file",
)


def _ok(payload) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _scoped(payload: dict, base, target) -> dict:
    """Reemplaza la ruta del reporte por una relativa al proyecto.

    Los reportes de `core/` llevan la ruta con la que se los construyó, que en
    el camino de las herramientas es absoluta. Devolvérsela al modelo expondría
    la estructura del disco de quien ejecuta Forge sin aportar nada al
    análisis, así que la traducción ocurre acá — en la capa que decide qué ve
    el modelo, no en los analizadores.
    """
    return {**payload, "path": relative_to_root(base, target)}


def _error(message: str) -> str:
    """Los errores vuelven como resultado, no como excepción.

    Una excepción cortaría el ciclo del agente; un error descrito deja que el
    modelo corrija el rumbo — pida otra ruta, o le avise al usuario.
    """
    return json.dumps({"error": message}, ensure_ascii=False)


class UnknownTool(Exception):
    """Se pidió una herramienta que no existe."""


def build_tools(root=".", approver=deny_all, only=None) -> list:
    """Construye las herramientas ancladas a `root`.

    Args:
        root: Raíz del proyecto. La fija quien ejecuta Forge.
        approver: Se consulta antes de cada escritura. El default deniega.
        only: Nombres a exponer. `None` expone todas. Ver `MINIMAL_TOOLS`.
    """
    base = Path(root).resolve()

    def _target(path: str) -> Path:
        return resolve_within(base, path)

    # ------------------------------------------------------------------
    # Análisis (solo lectura)
    # ------------------------------------------------------------------

    @tool
    def forge_analyze(path: str = ".") -> str:
        """Analiza un proyecto: lenguaje detectado, checks de salud y contenido del primer nivel.

        Args:
            path: Ruta relativa dentro del proyecto. Por defecto, la raíz.
        """
        try:
            target = _target(path)
            return _ok(_scoped(Project(target).analyze().to_dict(), base, target))
        except (PathOutsideProject, OSError) as exc:
            return _error(str(exc))

    @tool
    def forge_doctor(path: str = ".") -> str:
        """Diagnostica la salud del proyecto y devuelve un puntaje sobre los checks puntuables.

        Args:
            path: Ruta relativa dentro del proyecto. Por defecto, la raíz.
        """
        try:
            target = _target(path)
            return _ok(_scoped(Doctor(target).check().to_dict(), base, target))
        except (PathOutsideProject, OSError) as exc:
            return _error(str(exc))

    @tool
    def forge_stats(path: str = ".") -> str:
        """Cuenta carpetas y archivos del proyecto, excluyendo .git, .venv y artefactos de build.

        Args:
            path: Ruta relativa dentro del proyecto. Por defecto, la raíz.
        """
        try:
            return _ok(Stats(_target(path)).show().to_dict())
        except (PathOutsideProject, OSError) as exc:
            return _error(str(exc))

    @tool
    def forge_scan(path: str = ".") -> str:
        """Busca deuda visible: archivos Python, marcadores TODO/FIXME en comentarios y archivos vacíos.

        Args:
            path: Ruta relativa dentro del proyecto. Por defecto, la raíz.
        """
        try:
            payload = Scanner(_target(path)).scan().to_dict()
            # Las listas de archivos vienen absolutas desde el recorrido; se
            # relativizan por la misma razón que la ruta del reporte.
            for key in ("files_with_todos", "empty_paths"):
                payload[key] = [relative_to_root(base, p) for p in payload[key]]
            return _ok(payload)
        except (PathOutsideProject, OSError) as exc:
            return _error(str(exc))

    @tool
    def forge_tree(path: str = ".", depth: int = DEFAULT_MAX_DEPTH) -> str:
        """Devuelve el árbol de directorios del proyecto hasta cierta profundidad.

        Args:
            path: Ruta relativa dentro del proyecto. Por defecto, la raíz.
            depth: Profundidad máxima a recorrer. Debe ser al menos 1.
        """
        if depth < 1:
            return _error("depth debe ser al menos 1")
        try:
            entries = Tree(_target(path), max_depth=depth).build()
            return _ok([e.to_dict() for e in entries])
        except (PathOutsideProject, OSError) as exc:
            return _error(str(exc))

    @tool
    def read_file(path: str) -> str:
        """Lee el contenido de un archivo de texto del proyecto.

        Args:
            path: Ruta del archivo, relativa a la raíz del proyecto.
        """
        try:
            target = _target(path)
        except PathOutsideProject as exc:
            return _error(str(exc))

        if not target.is_file():
            return _error(f"No es un archivo: {path}")

        try:
            data = target.read_bytes()
        except OSError as exc:
            return _error(f"No se pudo leer {path}: {exc.strerror or exc}")

        truncated = len(data) > MAX_READ_BYTES
        text = data[:MAX_READ_BYTES].decode("utf-8", errors="replace")

        return _ok({"path": relative_to_root(base, target), "content": text,
                    "truncated": truncated})

    # ------------------------------------------------------------------
    # Escritura (requiere aprobación)
    # ------------------------------------------------------------------

    @tool
    def write_file(path: str, content: str) -> str:
        """Crea o reemplaza un archivo de texto del proyecto.

        Requiere aprobación humana: la escritura solo ocurre si la persona que
        ejecuta Forge acepta el cambio después de ver el diff. Si la rechaza,
        el archivo queda intacto y hay que proponer otra cosa, no reintentar.

        Args:
            path: Ruta del archivo, relativa a la raíz del proyecto.
            content: Contenido completo del archivo. Reemplaza el anterior.
        """
        try:
            target = _target(path)
        except PathOutsideProject as exc:
            return _error(str(exc))

        if target.is_dir():
            return _error(f"Es un directorio, no un archivo: {path}")

        display = relative_to_root(base, target)
        exists = target.is_file()
        previous = None

        if exists:
            try:
                previous = target.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                return _error(f"No se pudo leer el archivo actual: {exc.strerror or exc}")

        request = WriteRequest(
            path=display,
            action=OVERWRITE if exists else CREATE,
            content=content,
            previous_content=previous,
        )

        if not approver(request):
            return _error(
                f"El usuario rechazó la escritura de {display}. "
                "No reintentes la misma escritura."
            )

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            return _error(f"No se pudo escribir {display}: {exc.strerror or exc}")

        return _ok({"path": display, "action": request.action,
                    "bytes": len(content.encode("utf-8"))})

    tools = [
        forge_analyze,
        forge_doctor,
        forge_stats,
        forge_scan,
        forge_tree,
        read_file,
        write_file,
    ]

    if only is None:
        return tools

    wanted = list(only)
    available = {t.name for t in tools}
    unknown = [name for name in wanted if name not in available]

    if unknown:
        raise UnknownTool(
            f"No existe: {', '.join(unknown)}. "
            f"Disponibles: {', '.join(sorted(available))}"
        )

    # Se respeta el orden pedido: el orden en que el modelo ve las herramientas
    # influye en cuál elige, así que quien recorta decide la prioridad.
    by_name = {t.name: t for t in tools}
    return [by_name[name] for name in wanted]
