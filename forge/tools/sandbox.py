"""Confinamiento de rutas.

Toda ruta que llega desde el modelo pasa por acá antes de tocar el disco.

El principio: la raíz del proyecto la fija quien ejecuta Forge, nunca el modelo.
Las herramientas reciben rutas *relativas* y este módulo las resuelve contra esa
raíz, rechazando todo lo que se escape. Un modelo puede equivocarse o ser
inducido a pedir `../../.ssh/id_rsa` por el contenido de un archivo que acaba de
leer; el confinamiento es lo que hace que ese pedido falle en vez de funcionar.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

#: Tope de lectura. Un archivo enorme no es un riesgo de seguridad, pero llena
#: la ventana de contexto y desplaza información útil.
MAX_READ_BYTES = 100_000


class PathOutsideProject(Exception):
    """La ruta pedida cae fuera de la raíz del proyecto."""


def resolve_within(root, candidate: str) -> Path:
    """Resuelve `candidate` contra `root` y verifica que quede adentro.

    Rechaza tres formas de escape:

    - **Rutas absolutas.** `Path("/proyecto") / "/etc/passwd"` devuelve
      `/etc/passwd`: el operador `/` de pathlib descarta la izquierda cuando la
      derecha es absoluta. Sin este chequeo el confinamiento no existe.
    - **Travesía con `..`.** La resuelve `resolve()` y la detecta la
      comparación de contención.
    - **Symlinks que apuntan afuera.** `resolve()` los sigue, así que el
      destino real es el que se compara.

    Queda fuera de alcance el reemplazo de un componente por un symlink entre
    la verificación y la escritura (TOCTOU): cerrarlo requiere operaciones
    relativas a descriptores de directorio, desproporcionado para una CLI que
    corre con los permisos del usuario que ya la invocó.
    """
    relative = PurePosixPath(candidate)

    if relative.is_absolute():
        raise PathOutsideProject(
            f"Se esperaba una ruta relativa al proyecto, no absoluta: {candidate}"
        )

    base = Path(root).resolve()
    target = (base / relative).resolve()

    if not target.is_relative_to(base):
        raise PathOutsideProject(
            f"La ruta queda fuera del proyecto: {candidate}"
        )

    return target


def relative_to_root(root, target: Path) -> str:
    """Ruta legible para mostrarle al usuario y al modelo.

    Nunca se devuelven rutas absolutas hacia afuera: revelan la estructura del
    disco de quien ejecuta Forge sin aportar nada al análisis.
    """
    base = Path(root).resolve()
    try:
        return str(Path(target).resolve().relative_to(base)) or "."
    except ValueError:
        return str(target)
