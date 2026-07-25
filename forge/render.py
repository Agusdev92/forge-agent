"""Presentación de los reportes en texto para la terminal.

El formateo vive acá y no en `core/` a propósito: los analizadores devuelven
datos, y la terminal es solo uno de sus consumidores. Cuando Forge exponga
estos comandos como herramientas invocables por un LLM, ese consumidor va a
querer los objetos de `core/`, no estas cadenas con emojis.
"""

from __future__ import annotations

from forge.core.checks import Status

SYMBOLS = {
    Status.OK: "✅",
    Status.WARNING: "⚠️",
    Status.MISSING: "❌",
}


def _check_line(check) -> str:
    symbol = SYMBOLS[check.status]
    line = f"{symbol} {check.name}"

    if check.detail and check.status is not Status.OK:
        line += f" — {check.detail}"
    if not check.scored:
        line += " (informativo)"

    return line


def render_project(report) -> str:
    lines = [f"📁 Proyecto: {report.path}", f"🐍 Lenguaje: {report.language}", ""]
    lines += [_check_line(c) for c in report.checks]

    lines += ["", "📂 Carpetas"]
    lines += [f" - {d}" for d in report.directories] or [" (ninguna)"]

    lines += ["", "📄 Archivos"]
    lines += [f" - {f}" for f in report.files] or [" (ninguno)"]

    return "\n".join(lines)


def render_doctor(report) -> str:
    lines = ["🏥 Forge Doctor", ""]
    lines += [_check_line(c) for c in report.checks]
    lines += ["", f"Health Score: {report.score}/{report.total}"]

    if report.warnings:
        plural = "s" if len(report.warnings) > 1 else ""
        lines.append(
            f"⚠️ {len(report.warnings)} advertencia{plural}: "
            "el archivo existe pero está vacío."
        )

    return "\n".join(lines)


def render_stats(report) -> str:
    return "\n".join(
        [
            "📊 Forge Stats",
            "",
            f"🐍 Lenguaje: {report.language}",
            f"📂 Carpetas: {report.directories}",
            f"📄 Archivos: {report.files}",
        ]
    )


def render_scan(report) -> str:
    lines = [
        "🔎 Forge Scan",
        "",
        f"🐍 Archivos Python: {report.python_files}",
        f"⚠️ TODO/FIXME encontrados: {report.todos}",
        f"📄 Archivos vacíos: {report.empty_files}",
    ]

    if report.files_with_todos:
        lines += ["", "Con TODO/FIXME:"]
        lines += [f" - {f}" for f in report.files_with_todos]

    return "\n".join(lines)


def render_tree(entries) -> str:
    lines = ["📦 Proyecto", ""]

    if not entries:
        lines.append(" (vacío)")
        return "\n".join(lines)

    for entry in entries:
        indent = "  " * entry.depth
        icon = "📁" if entry.is_directory else "📄"
        lines.append(f"{indent}{icon} {entry.name}")

    return "\n".join(lines)
