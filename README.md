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

Opciones: `--model`, `--base-url`, `--tools`, `--timeout`, `--max-iterations`,
`--quiet` y `--yes` para aprobar las escrituras sin preguntar.

La respuesta se consume por fragmentos, así que mientras el modelo genera vas a
ver puntos de avance. **`--timeout` mide el silencio entre fragmentos, no la
duración total**: una respuesta de diez minutos no lo dispara mientras siga
llegando texto, pero un runtime colgado se detecta enseguida.

Hay un silencio inevitable **antes** del primer token: el runtime carga el modelo
y procesa el prompt entero sin emitir nada. En hardware limitado ese tramo puede
durar minutos, y es la razón del valor alto por defecto.

### Cuando tarda demasiado

```bash
ollama ps        # ¿el modelo quedó en GPU o en CPU?
```

La columna `PROCESSOR` es el diagnóstico: si dice CPU, el modelo no entró en la
VRAM y todo va a ser lento. Un modelo más chico o más cuantizado lo resuelve.

Si está en GPU y aun así tarda, achicá el prompt:

```bash
forge ask "..." --no-prompt-tools    # ~280 tokens menos
forge ask "..." --tools minimal      # menos schemas de herramientas
```

`--no-prompt-tools` saca la descripción de las herramientas del prompt. Solo hace
falta para modelos **sin** tool calling nativo — con uno que lo soporta (como
`qwen2.5-coder`) es información duplicada, porque los schemas ya viajan aparte.

### Configuración persistente

Para no repetir las opciones en cada consulta, hay tres variables de entorno:

```bash
export FORGE_BASE_URL=http://192.168.1.47:11434/v1
export FORGE_MODEL=qwen2.5-coder:7b
export FORGE_TOOLS=all
export FORGE_TIMEOUT=120

forge ask "¿qué le falta?"     # ya usa lo de arriba
```

Poniéndolas en `~/.bashrc` (o `~/.profile`) quedan fijas. Las opciones de línea
de comandos siguen teniendo prioridad sobre las variables.

### Runtime

Funciona con cualquier runtime que exponga el endpoint compatible con OpenAI —
Ollama, llama.cpp server, LM Studio o vLLM. El default apunta a Ollama:

```bash
forge ask "..." --base-url http://localhost:8080/v1   # llama.cpp
forge ask "..." --base-url http://localhost:1234/v1   # LM Studio
```

### Modelo en otra máquina de la red

Forge y el modelo no tienen por qué estar en el mismo equipo. Sirve para correr
Forge en una máquina modesta —un teléfono con Termux, por ejemplo— y dejar el
modelo en una con GPU.

En la máquina del modelo, Ollama tiene que escuchar en la red y no solo en
`localhost`:

```bash
OLLAMA_HOST=0.0.0.0 ollama serve
```

En la máquina que corre Forge, apuntá a su IP (`ip addr` o `ipconfig` te lo dice):

```bash
export FORGE_BASE_URL=http://192.168.1.47:11434/v1
forge ask "¿qué le falta?"
```

Sin firewall de por medio no hace falta nada más. **Los análisis se hacen del
lado de Forge**: al modelo solo le llegan los resultados, no el árbol de
archivos entero.

### Modelos chicos: recortar las herramientas

Un modelo de 1B–3B elige mal entre siete herramientas — se confunde entre las
que se parecen y gasta pasos. `--tools minimal` deja tres que cubren el ciclo
completo (`forge_analyze` para descubrir, `read_file`, `write_file`):

```bash
forge ask "..." --tools minimal
forge ask "..." --tools forge_doctor,read_file    # o elegilas a mano
```

Vale la pena probar `all` primero y recortar solo si ves llamadas erróneas en la
traza que imprime `forge ask` — para eso está.

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
