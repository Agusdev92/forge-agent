# Reporte técnico 003 — Ejecución de Fase 2 y Fase 3

**Fecha:** 2026-07-25
**Rama:** `claude/project-analysis-92tsia`
**Reportes previos:** [001 — Diagnóstico](2026-07-25-analisis-tecnico-y-roadmap.md) ·
[002 — Fase 0 y 1](2026-07-25-fase-0-1-ejecucion.md)
**Alcance aprobado:** Fase 2 (D5) + Fase 3 (D7)

---

## 1. Resumen

Forge pasa de 0% de cobertura y errores en forma de traceback a **67 tests**, CI en dos
versiones de Python y códigos de salida que un script puede interpretar.

La suite encontró dos defectos que la revisión de código no había visto, ambos del mismo
tipo: **el análisis devolvía un resultado plausible pero incorrecto en vez de fallar**.
Están en la §4.

| | Antes | Después |
|---|---|---|
| Tests | 0 | 67 |
| CI | ninguno | GitHub Actions, Python 3.9 y 3.12 |
| `--path` inexistente | traceback de `os.listdir` | `❌ La ruta no existe` + exit 2 |
| `--path` sin permisos | reportaba "0 archivos" | `❌ Sin permisos para leer` + exit 2 |
| Exit code ante fallo | siempre 0 | 2 (uso) / 1 (`--strict`) |
| `forge doctor` sobre este repo | 5/6 | **5/5** |
| Falsos positivos de `scan` | 5 | 0 |
| Líneas: `forge/` vs `tests/` | 750 / 0 | 750 / 620 |

---

## 2. Fase 2 — Manejo de errores (D5)

### Códigos de salida diferenciados

Dos códigos, con significados distintos a propósito:

- **`2` — error de uso.** La ruta no existe, no es un directorio, no se puede leer, o
  `--depth` es inválido. Forge no pudo hacer el análisis.
- **`1` — proyecto no sano**, solo con `--strict`. Forge hizo el análisis y el resultado
  fue negativo.

La distinción importa porque un pipeline necesita reaccionar distinto a "tu configuración
está mal" y a "tu proyecto no pasa los checks". Colapsarlos en un único código de error
obliga a parsear la salida de texto para saber cuál de los dos pasó.

### `forge doctor --strict`

Sin `--strict`, `doctor` informa y sale con 0: **diagnosticar un proyecto enfermo no es un
error de ejecución**, y hacer que fallara por defecto rompería cualquier uso interactivo.
Con `--strict` sale con 1 si algún check puntuable falla, que es lo que lo vuelve usable
como gate de CI.

Está en uso: el workflow corre `forge doctor --strict --path .` sobre el propio repo. Es
dogfooding real, no decorativo — si una decisión futura degrada la salud del proyecto, el
CI lo corta.

### Traducción de errores en la frontera

`core/` deja propagar las excepciones y `cli.py` las traduce. Esa división es deliberada
y mira hacia la etapa de agente: cuando estos análisis se expongan como herramientas del
modelo, ese consumidor va a querer manejar las excepciones a su manera, no heredar
mensajes con emojis pensados para una terminal.

---

## 3. Fase 3 — Tests y CI (D7)

### 67 tests, organizados por lo que pueden romper

| Archivo | Tests | Foco |
|---|---|---|
| `test_filesystem.py` | 9 | exclusión de directorios, contenido vacío, propagación de errores |
| `test_checks.py` | 11 | los tres estados, manifiestos, checks informativos |
| `test_doctor.py` | 5 | cálculo del score |
| `test_analyzers.py` | 26 | lenguaje, stats, scanner, árbol |
| `test_cli.py` | 16 | códigos de salida y errores de uso |

**La mayoría son tests de regresión de bugs reales**, no cobertura genérica. Cada bug
documentado en los reportes 001–003 tiene su test con la explicación del defecto en el
docstring, para que quien lo vea fallar dentro de un año entienda qué se estaba
protegiendo.

Los tests construyen proyectos reales en directorios temporales en vez de mockear `os`.
Es más lento —la suite tarda 0.3 s, así que "más lento" es teórico— y verifica lo que el
código realmente hace: **los cinco falsos positivos encontrados hasta ahora fueron todos
del recorrido de disco**, justo lo que un mock habría dado por bueno.

### CI

`.github/workflows/ci.yml`: instala el paquete, corre la suite y ejecuta
`forge doctor --strict` sobre sí mismo. Matriz de **Python 3.9 y 3.12**, los extremos del
rango declarado en `pyproject.toml` — probar solo la versión de desarrollo deja pasar
sintaxis que rompe al mínimo soportado, y probar todas las intermedias no agrega
información proporcional al tiempo.

Este CI habría detectado los dos fallos que originaron el reporte 001: el arranque roto
por `typer` no declarado (falla en `pip install`) y el import inexistente de
`forge/commands/analyze.py` (falla al importar).

---

## 4. Dos defectos encontrados al verificar

Ninguno estaba en el plan. Los dos comparten la misma forma —**devolver un número
plausible pero incorrecto en lugar de fallar**— que es peor que un error visible: un
análisis silenciosamente incompleto se parece mucho a uno correcto.

### 4.1 `os.walk` se tragaba los errores de permisos

`os.walk` con `onerror=None` —el default— **descarta los errores en silencio**. Un
directorio sin permisos de lectura no producía un error: producía cero resultados. O sea
que `forge stats` sobre un proyecto que no podía leer informaba "0 carpetas, 0 archivos"
y salía con código 0.

Es exactamente el modo de fallo que D5 venía a eliminar, escondido un nivel más abajo de
donde D5 miraba. Corregido pasando un `onerror` que propaga; la CLI lo traduce a
`❌ Sin permisos para leer: <ruta>` con exit 2. Verificado con un usuario sin privilegios
sobre un directorio en modo 000.

### 4.2 `scan` contaba TODOs dentro de literales de string

Segunda ronda de falsos positivos sobre la misma métrica. En la Fase 1 el conteo pasó de
buscar la subcadena `"TODO"` a buscar `# TODO`, lo que eliminó unos falsos positivos pero
no otros: **los propios tests de Forge, que construyen archivos de prueba con TODOs
adentro, inflaban la métrica del repo en 5 unidades**.

Dos rondas de falsos positivos sobre la misma métrica dejaron de ser un bug para pasar a
ser una señal: **buscar texto es la herramienta equivocada para esto**. Solo un
tokenizador sabe distinguir un comentario de un string que se le parece. `count_markers()`
ahora usa `tokenize` y cuenta únicamente tokens `COMMENT`, con fallback a la expresión
regular para archivos que no parsean (sintaxis inválida, Python 2), porque no reportar
nada sobre un archivo roto también es una forma de mentir.

Resultado: `forge scan` sobre este repo pasó de 5 TODOs a 0, que es la respuesta correcta.

---

## 5. Cambio de criterio: el entorno virtual ya no puntúa

`.venv/` está en el `.gitignore` de cualquier proyecto sano, así que **nunca existe en un
clon recién hecho ni en un runner de CI**. Puntuarlo hacía que el mismo proyecto sacara
distinto health score según la máquina donde se ejecutara el comando, que es lo contrario
de lo que un score debería medir: es una propiedad del entorno de quien ejecuta, no del
proyecto analizado.

El check sigue apareciendo, marcado `(informativo)`, pero fuera del denominador. Por eso
este repo pasó de `5/6` a `5/5`: el puntaje no subió por mejoras, cambió porque se sacó
del cálculo algo que no correspondía medir.

**Es un cambio de criterio de producto y queda marcado como tal** — si preferís que el
entorno virtual vuelva a puntuar, es revertir el flag `scored` en `_venv_check`.

---

## 6. Estado del roadmap

| Fase | Estado |
|---|---|
| 0 — Instalable y sin código muerto | ✅ |
| 1 — Correctitud | ✅ |
| 2 — Robustez (D5) | ✅ |
| 3 — Red de seguridad (D7) | ✅ |
| 4 — README y decisión de producto | README ✅ · dirección definida: agente con LLM |

Las siete decisiones D1–D7 del reporte 001 están implementadas. El inspector está
terminado como base: instalable, correcto en sus métricas, con errores manejados, con
tests y con CI.

---

## 7. Recomendación para la etapa de agente

La base está lista y el orden que sugiero para lo que viene es:

**1. Serialización antes que integración.** `core/` ya devuelve dataclasses, pero un
proveedor de LLM necesita JSON. Agregar `to_dict()` (o pasar a `dataclasses.asdict`
verificado con tests) es barato ahora y define el contrato de las herramientas antes de
que haya un modelo dependiendo de él.

**2. La capa de proveedor, con una sola implementación.** Un solo proveedor real primero.
La abstracción sobre proveedores conviene extraerla cuando exista el segundo, no antes:
diseñar una interfaz genérica contra un único caso conocido casi siempre produce la
interfaz equivocada. Es el mismo criterio con el que se borraron los paquetes vacíos.

**3. Presupuesto y límites explícitos desde el primer commit.** Timeouts, límite de
tokens y manejo de fallos de API. La parte no determinista del sistema conviene que nazca
con límites, porque agregárselos después implica reescribir el manejo de errores de cada
llamada.

**4. Decidir `memory/` con un caso de uso concreto en la mano.** Es la única de las cuatro
carpetas originales cuyo diseño no se deduce de las otras: qué recuerda el agente, entre
qué invocaciones y dónde lo guarda son preguntas de producto, no de arquitectura.

Un riesgo a tener presente: los tests actuales son deterministas porque el sistema lo es.
En cuanto entre el LLM, la tentación va a ser testear contra respuestas reales del modelo.
Conviene mantener la frontera —los analizadores se testean sin modelo, la capa de
proveedor se testea con respuestas fijas— o la suite se vuelve lenta, cara e inestable, y
una suite en la que no se confía deja de correrse.
