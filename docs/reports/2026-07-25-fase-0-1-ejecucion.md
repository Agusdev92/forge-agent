# Reporte técnico 002 — Ejecución de Fase 0 y Fase 1

**Fecha:** 2026-07-25
**Rama:** `claude/project-analysis-92tsia`
**Reporte previo:** [001 — Diagnóstico y roadmap](2026-07-25-analisis-tecnico-y-roadmap.md)
**Dirección de producto definida por el owner:** agente con LLM
**Alcance aprobado:** Fase 0 + Fase 1

---

## 1. Resumen

El proyecto pasa de "no arranca en una máquina limpia" a instalable, con los dos
comandos que devolvían números incorrectos ya corregidos y verificados contra un conteo
de control independiente.

Se eliminaron 17 archivos vacíos y un import roto. Se agregaron dos módulos nuevos
(`core/checks.py`, `render.py`) y una capa de datos que reemplaza a los `print()`
dispersos.

**Estado antes → después**

| | Antes | Después |
|---|---|---|
| `pip install -e . && forge doctor` | falla (`ModuleNotFoundError: typer`) | funciona |
| `forge stats` sobre este repo | 68 carpetas / 101 archivos | 4 / 16 (= conteo de control) |
| `forge scan` sobre este repo | 10 TODO, 2 archivos vacíos | 0 y 0 (eran falsos positivos) |
| `forge doctor` sobre proyecto vacío | 2/6 | 0/6 con 2 advertencias |
| `forge tree` | 1 nivel | recursivo, `--depth` configurable |
| Archivos `.py` vacíos en el repo | 17 de 27 (62%) | 2 de 12 (`__init__.py` legítimos) |
| Imports rotos | 1 | 0 |
| Salida de `core/` | `print()` a stdout | dataclasses |

---

## 2. Cómo cambió el plan la decisión de producto

El owner definió Forge como **agente con LLM**. Eso modificó tres cosas respecto del
reporte 001, y las explicito porque son desvíos del plan aprobado.

### 2.1 Se adelantó el refactor a salida estructurada (no estaba en Fase 1)

En el reporte 001 lo señalé como "lo único que urge decidir ya". Con la dirección
confirmada, dejó de ser opcional: **un LLM no puede consumir `print()`**. Si los seis
comandos van a ser herramientas invocables por el modelo, tienen que devolver objetos.

Lo incluí en esta tanda en lugar de dejarlo para después porque D4 y D6 me obligaban a
reescribir `stats.py`, `scanner.py`, `doctor.py` y `project.py` de todos modos. Hacerlo
en dos pasadas habría significado tocar los mismos cuatro archivos dos veces, la segunda
para deshacer lo que la primera acababa de escribir. El costo marginal de hacerlo ahora
fue cercano a cero; el de postergarlo crecía con cada comando nuevo.

Concretamente: `core/` devuelve `ProjectReport`, `DoctorReport`, `StatsReport`,
`ScanReport` y `list[TreeEntry]`. El formateo se movió a `forge/render.py`. La CLI quedó
reducida a parsear argumentos, llamar a `core/` y renderizar.

**Esto es la precondición de `forge/tools/`**: cuando llegue el momento de exponer estos
análisis como herramientas del agente, ya devuelven datos serializables y no hay nada que
reescribir.

### 2.2 D3 quedó absorbida por D6 (D3 era Fase 2)

D6 pedía que los checks distinguieran "existe" de "existe y tiene contenido". Esa lógica
vivía duplicada en `Project.analyze()` y `Doctor.check()`. Implementar D6 sin unificar
primero habría significado escribir la misma lógica de tres estados dos veces, en dos
archivos, sabiendo que iban a divergir.

Unificar era más barato que duplicar, así que se hizo: `core/checks.py` es ahora la
definición única, consumida por ambos comandos.

### 2.3 Los cuatro paquetes vacíos del agente se borraron igual

`forge/providers/`, `forge/tools/`, `forge/prompts/` y `forge/memory/` se eliminaron pese
a que la dirección elegida los va a necesitar.

**No estoy revirtiendo la decisión de producto — estoy borrando archivos vacíos.** Un
paquete que solo contiene un `__init__.py` de 0 bytes no aporta estructura, no compila
nada y no orienta a nadie; lo único que hace es afirmar que existe algo que no existe.
Van a volver en el commit que agregue el primer proveedor real, con la forma que esa
integración demande en vez de la que hoy suponemos. La decisión de agente no cambia si
conviene tenerlos vacíos, solo adelanta la fecha en que vuelven llenos.

Lo mismo con `prompts/` y `memory/`, que además codifican decisiones de diseño todavía
no tomadas (si el agente necesita memoria persistente, y de qué tipo, es una discusión
pendiente).

---

## 3. Cambios ejecutados

### Fase 0 — Instalable y sin código muerto

- **`pyproject.toml`** con `typer>=0.12`, extra `dev` con `pytest`, y entry point
  `forge = "forge.cli:app"`. Ahora `pip install -e .` deja el ejecutable `forge` en el
  PATH; antes solo existía `python -m forge` desde la raíz, y fallaba.
- **`requirements.txt` eliminado.** Con `pyproject.toml` declarando las dependencias,
  mantener los dos era tener dos fuentes de verdad que se desincronizan. Los checks
  ahora aceptan cualquiera de los dos (§3.2), así que ningún proyecto queda mal
  diagnosticado por esta elección.
- **`forge/commands/` eliminado** (5 archivos: 4 vacíos + `analyze.py` con un import a
  `analyze_project`, función inexistente). Cero referencias desde el resto del código.
  Criterio para reintroducirlo, del reporte 001: cuando `cli.py` supere las 200 líneas
  (hoy tiene 66).
- **`forge/__main__.pyy` eliminado** — duplicado exacto de `__main__.py` con la extensión
  mal escrita.
- **Andamiaje de la raíz eliminado**: `agent.py`, `config.py`, `main.py`, `core/`,
  `commands/`, `providers/` — todos vacíos desde el commit inicial, y los dos últimos
  colisionaban por nombre con `forge/core` y `forge/commands`.
- **`README.md`** escrito: instalación, uso y estructura. Estaba en 0 bytes.
- **`.gitignore`** ampliado con `*.egg-info/`, `build/`, `dist/`, `.pytest_cache/`.

### Fase 1 — Correctitud

- **`core/filesystem.py` reescrito.** Concentra el acceso a disco e incorpora
  `IGNORED_DIRS` más un `walk()` que poda. La corrección no se aplicó comando por
  comando a propósito: puesta en la capa de filesystem, el próximo analizador que
  recorra el árbol hereda las exclusiones en vez de tener que acordarse de ellas. Es la
  diferencia entre arreglar dos bugs y eliminar una clase de bug.
- **`core/checks.py` nuevo.** Tres estados (`OK` / `WARNING` / `MISSING`) en vez de dos.
  Reconoce `pyproject.toml` además de `requirements.txt`.
- **`core/tree.py`**: ahora es recursivo, con `--depth` (default 3). Se llamaba `tree` y
  listaba un solo nivel; lo trato como bug de correctitud por la misma razón que `stats`:
  la salida contradecía lo que el comando dice ser.
- **`detect_language()`**: agrega `pyproject.toml` y `setup.py`, y cae a detección por
  extensión. Antes un proyecto Python sin `requirements.txt` se reportaba "Desconocido"
  aunque estuviera lleno de `.py`.

### Criterio de puntaje del health score

Las advertencias **no** suman puntaje parcial. Un `README.md` vacío no documenta a
medias, no documenta. Si sumaran 0.5, un proyecto que solo hizo `touch` de los archivos
correctos sacaría la mitad del puntaje, que es exactamente el defecto que D6 venía a
corregir.

---

## 4. Tres falsos positivos detectados al verificar

No estaban en el plan: aparecieron al correr los comandos contra este mismo repo después
de la primera implementación. Los anoto porque son la evidencia más concreta de por qué
Fase 3 (tests) importa — los tres pasaron desapercibidos en revisión de código y solo
salieron al ejecutar.

1. **`*.egg-info` se contaba como código.** `pip install -e .` genera
   `forge_agent.egg-info/` con 6 archivos, que `stats` y `tree` incluían. Es artefacto de
   build. `is_ignored()` ahora lo excluye por sufijo, porque el nombre depende del
   paquete y no puede ir en una lista fija.
2. **`scan` se contaba a sí mismo.** Buscar la subcadena `"TODO"` daba 10 resultados en
   `scanner.py` y `render.py`: las apariciones eran la propia definición de los
   marcadores y el texto de la salida. Ahora la búsqueda es
   `re.compile(r"#\s*(TODO|FIXME)\b")` — solo cuentan los marcadores en comentarios, que
   es lo que la métrica pretendía medir.
3. **`__init__.py` vacíos contados como deuda.** Un `__init__.py` de 0 bytes es un
   marcador de paquete válido, no un archivo sin terminar. Excluidos del conteo.

---

## 5. Verificación

Ejecutado sobre este repo tras `pip install -e .`:

- `forge --help` lista los 6 comandos; `forge version`, `analyze`, `doctor`, `stats`,
  `scan`, `tree` corren sin error, igual que `python -m forge`.
- **`forge stats` → 4 carpetas / 16 archivos**, idéntico a un conteo de control
  independiente que excluye `.git`, `.venv`, `__pycache__` y `*.egg-info`. Antes: 68/101.
- **`forge scan` → 12 archivos Python, 0 TODO, 0 vacíos**, tras corregir los falsos
  positivos.
- **`forge doctor` sobre un directorio temporal con `README.md` y `requirements.txt` de 0
  bytes → `0/6` con 2 advertencias.** Con el código anterior ese mismo directorio sacaba
  `2/6`. Es la demostración directa del bug que D6 corrige.
- **`forge stats --path` sobre un proyecto sin manifiesto pero con un `.py` → "Python"**,
  confirmando el fallback de detección por extensión.

---

## 6. Fuera de alcance en esta tanda

Deliberadamente no incluido, para respetar el alcance aprobado:

- **D5 — manejo de errores en la CLI (Fase 2).** Un `--path` inexistente sigue produciendo
  un traceback en vez de un mensaje, y los comandos no devuelven exit code distinto de 0
  al fallar. Es el próximo item.
- **D7 — tests y CI (Fase 3).** Sigue en 0% de cobertura. Los tres falsos positivos de la
  §4 son el argumento a favor de acelerarlo: los encontró la ejecución manual, y la
  ejecución manual no escala.
- **`tests/`** es el único check que `forge doctor` reprueba sobre este repo (5/6). Queda
  así a propósito: el diagnóstico debe reflejar el estado real.

---

## 7. Recomendación de próximo paso

Mantener el orden del roadmap: **Fase 2 (D5) y luego Fase 3 (D7)** antes de empezar la
integración con LLM.

El motivo es concreto y no burocrático: la primera integración con un proveedor va a
introducir fallos de red, timeouts, respuestas malformadas y errores de API. Construir
eso sobre una base que hoy no sabe manejar un path inexistente ni tiene un solo test de
regresión significa que el primer bug del agente va a ser indistinguible de un bug del
inspector. La red de seguridad conviene tenerla puesta antes de agregar la parte no
determinista del sistema, no después.
