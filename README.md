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

## El agente

`forge ask` le pregunta a un **modelo que corre en tu máquina**. No usa servicios
pagos ni manda el código a ningún lado.

```bash
ollama serve                        # en otra terminal
ollama pull qwen2.5-coder:7b

forge ask "¿qué le falta a este proyecto?"
forge ask "escribí un README" --path ../otro-proyecto
```

Opciones: `--model`, `--base-url`, `--max-iterations`, y `--yes` para aprobar las
escrituras sin preguntar.

### Runtime

Funciona con cualquier runtime que exponga el endpoint compatible con OpenAI —
Ollama, llama.cpp server, LM Studio o vLLM. El default apunta a Ollama:

```bash
forge ask "..." --base-url http://localhost:8080/v1   # llama.cpp
forge ask "..." --base-url http://localhost:1234/v1   # LM Studio
```

**El tamaño de contexto se configura del lado del runtime**: el endpoint
compatible no lo acepta como parámetro. Si el modelo parece "olvidarse" de lo
que hizo dos pasos atrás, es contexto corto y el runtime lo truncó en silencio.

### Escrituras

El agente puede crear y reemplazar archivos, con dos límites que no puede saltear:

- **Confinamiento**: solo rutas dentro del proyecto. Rutas absolutas, `..` y
  symlinks que apunten afuera se rechazan.
- **Aprobación**: cada escritura muestra el diff y espera confirmación. El
  default es no escribir.

### Modelos

Se probó apuntando a `qwen2.5-coder:7b`. En general, cuanto más chico el modelo,
menos confiable el uso de herramientas — si ves llamadas inventadas o en loop,
probá uno más grande antes de tocar los prompts. Forge acepta llamadas emitidas
como texto además de las nativas, justamente para tolerar modelos sin soporte
nativo de herramientas.

## Estructura

```
forge/
  cli.py          # parseo de argumentos y salida
  render.py       # formateo de los reportes para la terminal
  agent.py        # el ciclo del agente
  approval_cli.py # compuerta de aprobación interactiva
  core/           # analizadores: devuelven datos, no imprimen
    checks.py       # definición única de los checks de salud
    filesystem.py   # acceso a disco y exclusión de .git/.venv/__pycache__
    project.py  doctor.py  stats.py  scanner.py  tree.py
  tools/          # lo que el modelo puede invocar
    schema.py       # genera los esquemas JSON desde firma y docstring
    sandbox.py      # confinamiento de rutas
    approval.py     # compuerta de escritura
    registry.py     # las siete herramientas
  providers/      # cliente del modelo local
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
