# Forge Agent

CLI para analizar proyectos de software: detecta el stack, diagnostica el estado
del repositorio y reporta deuda visible en el código.

## Instalación

```bash
pip install -e .
```

## Uso

```bash
forge analyze          # detecta lenguaje, corre los checks y lista el contenido
forge doctor           # health score del proyecto
forge stats            # cantidad de carpetas y archivos
forge scan             # archivos Python, TODO/FIXME y archivos vacíos
forge tree --depth 2   # árbol de directorios
forge version
```

Todos los comandos aceptan `--path` / `-p` para apuntar a otro proyecto:

```bash
forge doctor --path ../otro-proyecto
```

## Estructura

```
forge/
  cli.py        # parseo de argumentos y salida
  render.py     # formateo de los reportes para la terminal
  core/         # analizadores: devuelven datos, no imprimen
    checks.py       # definición única de los checks de salud
    filesystem.py   # acceso a disco y exclusión de .git/.venv/__pycache__
    project.py  doctor.py  stats.py  scanner.py  tree.py
```

Los módulos de `core/` devuelven objetos (`DoctorReport`, `ScanReport`, ...) y no
escriben en pantalla. El formateo está aislado en `render.py` para que la
terminal no sea el único consumidor posible de estos análisis.

## Desarrollo

```bash
pip install -e ".[dev]"
pytest
forge doctor --strict --path .   # el mismo gate que corre en CI
```

## Estado

En desarrollo. Cada cambio técnico está documentado con su justificación en
[`docs/reports/`](docs/reports/).
