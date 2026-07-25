# Reporte técnico 001 — Diagnóstico y roadmap

**Fecha:** 2026-07-25
**Rama:** `claude/project-analysis-92tsia`
**Commit base:** `21826ff`
**Estado del proyecto:** prototipo temprano — núcleo funcional, andamiaje especulativo alrededor

---

## 1. Resumen ejecutivo

Forge tiene un núcleo que funciona: seis comandos que inspeccionan un proyecto y devuelven
información útil. Ese núcleo son ~100 líneas y están bien escritas.

El problema no es el código que existe, es el que **no** existe y el que **sobra**:

1. El proyecto **no arranca en una máquina limpia** — `typer` es dependencia obligatoria y
   `requirements.txt` está vacío.
2. El **62% de los archivos `.py` del repo están vacíos** — son andamiaje de una arquitectura
   que todavía no se necesita.
3. Dos comandos (`stats`, `scan`) **devuelven números incorrectos** porque no filtran `.git`
   ni `.venv`.
4. **Cero tests**, cero CI, README vacío.

La decisión más importante de este reporte no es técnica sino de producto, y está en la §6.

---

## 2. Diagnóstico cuantitativo

Medido sobre el repo en `21826ff`:

| Métrica | Valor |
|---|---|
| LOC de Python reales | 264 |
| Archivos `.py` | 27 |
| Archivos `.py` **vacíos** | 17 (62%) |
| Carpetas reales | 10 |
| Archivos reales | 31 |
| Lo que `forge stats` **reporta** | 68 carpetas, 101 archivos |
| Error de `forge stats` | **+226%** |
| Cobertura de tests | 0% |
| Dependencias declaradas | 0 (requiere 1) |

**Por qué importa la última fila del error:** una herramienta de diagnóstico que miente en sus
propias métricas no es una herramienta con un bug, es una herramienta sin valor. `stats` y
`scan` cuentan el contenido de `.git` y `.venv` como si fuera código del proyecto. En un repo
con dependencias instaladas, `scan` reportaría los `TODO` de las librerías de terceros como
deuda propia. Esto es P0 y lo trato como corrección de correctitud, no como mejora.

---

## 3. El riesgo principal: arquitectura especulativa

El repo contiene cuatro paquetes vacíos — `forge/providers/`, `forge/tools/`,
`forge/prompts/`, `forge/memory/` — más un `forge/commands/` con cinco archivos, cuatro de
ellos vacíos y uno roto.

Esos nombres describen la arquitectura de un **agente LLM**: proveedores de modelo,
herramientas invocables, plantillas de prompt y memoria conversacional. Es un diseño
coherente. El problema es que se commiteó **antes** de que existiera una sola línea de esa
funcionalidad, mientras el código que sí funciona no tiene tests ni empaquetado.

**Por qué esto es un riesgo y no un detalle cosmético:**

- **Sesga decisiones futuras.** Una carpeta `providers/` vacía ya decidió, sin discusión, que
  habrá una capa de abstracción sobre proveedores de LLM. Cuando llegue el momento de
  integrar uno, la estructura empujará hacia esa forma aunque no sea la correcta.
- **Miente sobre la madurez.** Quien abra el repo ve la silueta de un agente completo y
  encuentra un listador de directorios. Eso cuesta credibilidad ante un colaborador o un
  evaluador.
- **Esconde el código muerto real.** `forge/commands/analyze.py:3` importa
  `analyze_project` de `forge.core.project`, **función que no existe**. No rompe la CLI
  solamente porque nada importa ese paquete. Es un import roto que ningún test detectaría
  porque no hay tests, y que nadie nota porque está entre 16 archivos vacíos más.

**Decisión propuesta:** borrar todo paquete vacío. Se reintroducen cuando exista la primera
feature que los necesite, con el diseño que esa feature demande y no con el que hoy
imaginamos. El costo de recrear una carpeta es cero; el costo de arrastrar una arquitectura
equivocada durante seis meses no lo es.

---

## 4. Decisiones técnicas propuestas

Cada decisión con contexto, propuesta, justificación y costo.

### D1 — Empaquetar con `pyproject.toml` y declarar dependencias

- **Contexto:** `requirements.txt` vacío; `python3 -m forge --help` falla con
  `ModuleNotFoundError: No module named 'typer'`. No existe el ejecutable `forge`.
- **Propuesta:** `pyproject.toml` con build backend estándar, dependencia `typer`, y
  `[project.scripts] forge = "forge.cli:app"`.
- **Por qué:** es el único punto del que dependen todos los demás. Sin instalación
  reproducible no hay CI, no hay tests en limpio y no hay forma de que un tercero use el
  proyecto. Además elimina la ironía de que `forge doctor` premie con ✅ un
  `requirements.txt` vacío.
- **Costo:** ~20 líneas. Ninguna ruptura.

### D2 — Eliminar `forge/commands/`

- **Contexto:** cinco archivos, cuatro vacíos, uno con un import a una función inexistente.
  Cero referencias desde el resto del código (verificado con `grep`).
- **Propuesta:** borrar el paquete. Los comandos siguen declarándose en `forge/cli.py`.
- **Por qué:** separar `commands/` de `core/` es un patrón correcto **a partir de cierto
  tamaño**. Con 264 LOC y seis comandos, `cli.py` completo son 59 líneas y se lee de un
  vistazo. La separación prematura duplica archivos sin reducir complejidad. Criterio
  objetivo para revertir esta decisión: **cuando `cli.py` supere las 200 líneas**, se extrae
  a `commands/` con la forma que el código tenga entonces.
- **Costo:** borrado. Riesgo cero — nada lo importa.

### D3 — Unificar los checks de `Project` y `Doctor`

- **Contexto:** `core/project.py:20-33` y `core/doctor.py:14-21` implementan **los mismos
  tres checks** (git, `.venv`, `requirements.txt`) con código distinto.
- **Propuesta:** un módulo `core/checks.py` con los checks como datos (nombre + predicado),
  consumido por ambos comandos.
- **Por qué:** hoy son dos implementaciones equivalentes; en el primer cambio que toque una
  sola, divergen y `analyze` y `doctor` empiezan a contradecirse sobre el mismo proyecto. Un
  diagnóstico que se contradice a sí mismo es peor que no tenerlo. Además, con los checks
  como datos, agregar uno nuevo pasa a ser una línea en vez de dos bloques `if/else`.
- **Costo:** ~30 líneas, refactor de dos archivos.

### D4 — Lista de exclusión compartida

- **Contexto:** `core/stats.py:15` (`os.walk`) y `core/scanner.py:9` (`rglob`) recorren
  `.git`, `.venv`, `__pycache__`.
- **Propuesta:** constante `IGNORED` y un helper de recorrido en `core/filesystem.py`, usado
  por ambos.
- **Por qué:** corrige el error del +226% en un solo lugar. Ponerlo en `filesystem.py` — que
  ya es la capa de acceso a disco — evita que el tercer comando que recorra el árbol vuelva a
  cometer el mismo error. Es la diferencia entre arreglar dos bugs y eliminar una clase de
  bug.
- **Costo:** ~15 líneas. Cambia la salida de `stats` y `scan` (a la correcta).

### D5 — Manejo de errores en la frontera de la CLI

- **Contexto:** ningún comando valida su `--path`. Un path inexistente produce un traceback
  crudo de `os.listdir`. Aplica a los seis comandos.
- **Propuesta:** validación del path en `cli.py` y salida con `typer.Exit(1)` y mensaje
  legible.
- **Por qué:** un traceback como respuesta a un typo del usuario es un bug de producto. Y el
  exit code importa: hoy los fallos no son distinguibles por un script o un pipeline de CI
  que invoque `forge doctor`.
- **Costo:** ~15 líneas concentradas en la capa CLI, sin tocar `core/`.

### D6 — Checks que validen contenido, no existencia

- **Contexto:** `forge doctor` da ✅ a `README.md` y `requirements.txt` de **0 bytes**. Este
  mismo repo saca un score alto siendo un repo sin documentar ni instalable.
- **Propuesta:** tres estados — OK / advertencia (existe pero vacío) / falta.
- **Por qué:** el health score es la salida principal del producto. Si un proyecto vacío
  puntúa alto, el número no mide salud, mide presencia de archivos. Corregir esto es lo que
  convierte a `doctor` en algo accionable.
- **Costo:** ~20 líneas.

### D7 — Tests y CI mínimos

- **Contexto:** 0% de cobertura. El import roto de §3 sobrevivió cuatro commits.
- **Propuesta:** `pytest` sobre `Doctor`, `detect_language` y las exclusiones de D4, con
  fixtures de directorios temporales, más un workflow de GitHub Actions que instale el
  paquete y corra los tests.
- **Por qué:** empiezo por estos tres porque son **funciones puras sobre el sistema de
  archivos** — entrada controlada, salida determinista, sin mocks. Son el mejor retorno por
  línea de test. Y un CI que solo haga `pip install . && pytest` ya habría detectado tanto el
  import roto como el fallo de arranque por `typer`.
- **Costo:** ~80 líneas de test + ~25 de workflow.

---

## 5. Roadmap propuesto

**Fase 0 — Que el proyecto sea instalable y honesto** (D1, D2, exclusión de archivos basura)
Criterio de hecho: `pip install . && forge doctor` funciona en una máquina limpia, y no queda
ningún archivo vacío ni import roto en el repo.

**Fase 1 — Corrección de correctitud** (D4, D6)
Criterio de hecho: `forge stats` sobre este repo reporta 10 carpetas y 31 archivos, y
`forge doctor` no premia archivos vacíos.

**Fase 2 — Robustez** (D3, D5)
Criterio de hecho: ningún comando produce un traceback ante entradas inválidas; `analyze` y
`doctor` nunca se contradicen.

**Fase 3 — Red de seguridad** (D7)
Criterio de hecho: CI en verde sobre cada push; los bugs de las fases 1 y 2 tienen test de
regresión.

**Fase 4 — README y decisión de producto** (§6)
Criterio de hecho: existe una definición escrita de qué es Forge, y el README la refleja.

El orden no es negociable en un punto: **D7 va después de las correcciones, no antes**.
Escribir tests contra `stats` hoy sería congelar el comportamiento incorrecto.

---

## 6. Decisión de producto pendiente (requiere definición del owner)

Esta es la pregunta que condiciona todo lo demás, y no es mía para responder:

> **¿Forge es un agente con LLM, o es un inspector de proyectos sin IA?**

**Si es un inspector** (lo que hoy realmente es): el roadmap de arriba lo lleva a v1.0. El
valor está en más analizadores, mejores heurísticas de detección y buena salida. Es un
producto acotado, terminable y útil. `providers/`, `tools/`, `prompts/` y `memory/` se borran
y no vuelven.

**Si es un agente**: el trabajo real ni empezó, y las seis funciones actuales pasan a ser
*herramientas* que el agente invoca — lo cual cambia su interfaz, porque hoy todas
`print()`ean a stdout en vez de **devolver datos estructurados**, que es lo que un LLM
necesita consumir. Ese refactor (de `print` a objetos de retorno, con el formateo movido a la
capa CLI) es la precondición de todo lo demás y conviene hacerlo antes de acumular más
comandos.

**Mi recomendación: definirlo como inspector ahora y llevarlo a v1.0.** Justificación: hay un
producto entregable a semanas de distancia, con alcance claro y sin dependencias externas ni
costos de API. La opción "agente" no se cierra — al contrario, un inspector con salida
estructurada y bien testeada es exactamente el conjunto de herramientas que un agente
necesitaría después. El camino corto es también el prerrequisito del camino largo.

Lo único que sí pediría decidir ya, en cualquier escenario: **empezar a devolver datos
estructurados en vez de imprimir**, porque el costo de ese cambio crece con cada comando
nuevo que se agregue.

---

## 7. Riesgos abiertos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Se siguen agregando comandos sobre una base sin tests | Cada feature nueva aumenta la superficie de regresión | Fase 3 antes de la próxima feature |
| El patrón `print()` se consolida en más comandos | Refactor a salida estructurada se encarece linealmente | Decidir §6 antes del próximo comando |
| Los paquetes vacíos se mantienen "por si acaso" | La arquitectura no validada se vuelve permanente por inercia | D2, con criterio explícito de reintroducción |

---

## 8. Qué cambió en este commit

Solo este documento. **Ninguna modificación de código.** Las decisiones D1–D7 están propuestas
y a la espera de aprobación; cada una se implementará en un commit propio con su reporte
correspondiente.
