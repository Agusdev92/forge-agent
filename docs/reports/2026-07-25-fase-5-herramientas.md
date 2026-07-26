# Reporte técnico 004 — Capa de herramientas del agente (M1 y M2)

**Fecha:** 2026-07-25
**Rama:** `claude/project-analysis-92tsia`
**Reportes previos:** [001](2026-07-25-analisis-tecnico-y-roadmap.md) ·
[002](2026-07-25-fase-0-1-ejecucion.md) · [003](2026-07-25-fase-2-3-ejecucion.md)
**Decisiones del owner:** agente con LLM · alcance **lectura + escritura de archivos**

---

## 1. Resumen

Los seis análisis de Forge son ahora herramientas invocables por un modelo, más `read_file`
y `write_file`. Todo lo construido en esta tanda se ejercita **sin credenciales y sin
llamadas a la API**: las herramientas son funciones que devuelven JSON.

**35 tests nuevos** (102 en total), la mayoría sobre el confinamiento de rutas y la
compuerta de aprobación — que es donde un fallo silencioso tiene consecuencias reales.

| | Antes | Después |
|---|---|---|
| Salida de `core/` | dataclasses | dataclasses + `to_dict()` |
| Herramientas expuestas | 0 | 7 (5 análisis + lectura + escritura) |
| Tests | 67 | **102** |
| Dependencias | `typer` | `typer`, `anthropic>=0.120` |

---

## 2. Corrección al plan del reporte 003

En el reporte 003 listé "el loop de agente" como un hito a construir. **Es incorrecto y no
se construyó.** El SDK trae un *tool runner* (`client.beta.messages.tool_runner`) que
gestiona el ciclo pedir-herramienta → ejecutar → devolver → repetir, con hooks por turno
para aprobación, intercepción de errores y modificación de resultados.

Escribir ese loop a mano solo se justifica cuando se necesita control que esos hooks no
dan. No es nuestro caso — la compuerta de aprobación de §4 entra exactamente en el hook
previsto para eso. Se cae un hito entero del plan.

También verifiqué antes de diseñar, en vez de asumir, que `@beta_tool` funciona sobre
funciones anidadas y que genera el esquema JSON desde la firma y el docstring. Eso es lo
que hace viable la fábrica de §3.

---

## 3. La decisión estructural: la raíz no es un parámetro del modelo

`build_tools(root, approver)` es una fábrica que **cierra** sobre la raíz del proyecto y la
política de aprobación. Ninguna de las dos aparece en el esquema JSON que ve el modelo.

Esto no es estilo, es la base de todo lo demás. Si la raíz fuera un parámetro de las
herramientas, el modelo podría elegir qué proyecto mirar y el confinamiento de rutas no
serviría de nada: bastaría con pedir `root="/"`. El modelo decide *qué* mirar dentro del
proyecto; nunca *cuál* es el proyecto, ni si una escritura se ejecuta.

Hay un test que lo verifica sobre las siete herramientas — es una invariante que se rompe
silenciosamente si alguien agrega una herramienta nueva copiando mal el patrón.

Consecuencia práctica: `forge/providers/` y `forge/tools/` vuelven a existir, borradas en
la Fase 0. Vuelven con la forma que la integración real pidió, no con la que suponíamos en
el commit inicial — que era el argumento para borrarlas.

---

## 4. Seguridad

El alcance elegido —escritura de archivos— es lo que convierte esto en la parte más
delicada del proyecto. Dos controles **independientes**: uno acota *dónde*, el otro *si*.

### 4.1 Confinamiento de rutas (`sandbox.py`)

Toda ruta que llega del modelo se resuelve contra la raíz y se verifica que quede adentro.
Tres formas de escape, todas con test:

- **Rutas absolutas.** `Path("/proyecto") / "/etc/passwd"` devuelve `/etc/passwd` — el
  operador `/` de pathlib descarta el lado izquierdo cuando el derecho es absoluto. Sin un
  rechazo explícito de rutas absolutas **no hay confinamiento en absoluto**; es el caso
  que más fácil se pasa por alto porque el código *parece* estar componiendo rutas.
- **Travesía con `..`**, incluida la que aparece a mitad de camino (`src/../../fuera`).
- **Symlinks que apuntan afuera.** `resolve()` los sigue, así que se compara el destino
  real y no el nombre del enlace.

Queda **fuera de alcance y declarado**: el reemplazo de un componente por un symlink entre
la verificación y la escritura (TOCTOU). Cerrarlo exige operaciones relativas a
descriptores de directorio, desproporcionado para una CLI que corre con los permisos del
usuario que ya la invocó.

También se decidió **no expandir `~`**: dentro de un proyecto es un nombre de archivo común
y corriente, y expandirlo sería crear un cuarto camino de escape.

### 4.2 Compuerta de aprobación (`approval.py`)

Escribir es la única acción irreversible que hace Forge. Cada escritura construye un
`WriteRequest` con la ruta, la acción (crear o reemplazar), el contenido nuevo y el
anterior, y se consulta al aprobador antes de tocar el disco.

Tres decisiones, cada una con su motivo:

1. **El default es denegar.** Construir las herramientas sin pasar un aprobador hace que
   las escrituras fallen, no que se ejecuten. Una compuerta que se abre sola cuando se la
   olvida configurar no es una compuerta.
2. **El aprobador recibe el diff completo.** Aprobar a ciegas equivale a no tener
   compuerta, así que quien decide ve exactamente qué se va a escribir.
3. **Un rechazo se le informa al modelo como resultado, no como excepción.** El texto dice
   explícitamente que no reintente la misma escritura. Un rechazo que el modelo interpreta
   como fallo transitorio produce un bucle de reintentos contra un humano que ya dijo que
   no.

**Los dos controles son independientes**: aprobar una escritura no levanta el
confinamiento. Hay un test que aprueba todo y aun así verifica que `../fuera.txt` no se
escriba.

### 4.3 Sin copias de respaldo — decisión explícita

`write_file` no guarda backup antes de reemplazar. El resguardo es la compuerta con diff:
nada se sobrescribe sin que un humano vea el cambio. Un almacén paralelo de respaldos trae
sus propios problemas (archivos rancios, copias de contenido sensible, limpieza) a cambio
de poco.

**Es reversible y lo marco como tal**: si querés respaldo automático, el lugar es
`write_file`, antes de `write_text`. Vale saber que en un proyecto sin control de versiones
—algo que `forge doctor` justamente detecta— un reemplazo aprobado por error no se
recupera.

### 4.4 Verificación adversarial

Además de los tests, corrí los siete ataques a mano **con el aprobador permisivo**, para no
estar comprobando mi propia suposición: rutas absolutas de lectura y escritura, `..` simple
y a mitad de camino, y un análisis apuntado fuera del proyecto. Los siete bloqueados, el
archivo señuelo intacto, y la lectura legítima funcionando.

---

## 5. Dos fugas encontradas al verificar

Un test falló con `TypeError: Object of type PosixPath is not JSON serializable` —
`DoctorReport.path` guardaba un `Path`. Al mirarlo apareció algo más serio que el error de
tipo: **los reportes devolvían rutas absolutas al modelo**.

1. **`forge_analyze` y `forge_doctor`** exponían la ruta absoluta del proyecto.
2. **`forge_scan`** exponía rutas absolutas en `files_with_todos` y `empty_paths`.

No es una vulnerabilidad de acceso —el modelo no lee nada que no pudiera leer igual— pero
revela la estructura del disco de quien ejecuta Forge sin aportar nada al análisis, y ese
texto queda en el historial de la conversación.

La traducción a rutas relativas se hizo en **la capa de herramientas, no en los
analizadores**: `core/` no tiene por qué saber que existe un modelo del otro lado, y la
CLI sí quiere la ruta absoluta en su salida. La capa que decide qué ve el modelo es la que
traduce. Hay un test que recorre las tres herramientas y falla si la ruta absoluta aparece
en el JSON crudo.

Vale notar que el error de tipo fue lo que expuso la fuga: sin la serialización a JSON, las
rutas absolutas habrían pasado desapercibidas hasta producción.

---

## 6. Serialización (M1)

`to_dict()` en los cinco reports. Un detalle no obvio: `DoctorReport` expone `score`,
`total` y `healthy` **explícitos**, aunque sean propiedades derivadas que `asdict()`
omitiría. Dejarlas fuera obligaría a cada consumidor a reimplementar la regla de puntaje —
exactamente la duplicación que `core/checks.py` vino a eliminar en la Fase 1.

---

## 7. Estado y qué falta

| Hito | Estado |
|---|---|
| M1 — Serialización | ✅ |
| M2 — Herramientas (5 análisis + lectura + escritura) | ✅ |
| M3 — Capa de proveedor (cliente, timeouts, errores) | pendiente |
| M4 — `forge ask "..."` (tool runner, streaming, effort) | pendiente |
| M5 — Memoria | sin caso de uso todavía |

Lo que M3 y M4 tienen que respetar, del contrato del SDK:

- **`max_tokens` alto obliga a streaming.** Por encima de ~16K sin stream se choca contra
  el timeout HTTP. Un agente que recorre un proyecto genera salida larga, así que va con
  streaming desde el principio.
- **`stop_reason: "refusal"` llega con HTTP 200.** Código que lee `content[0]` sin chequear
  antes se rompe.
- **El pensamiento viene activado por defecto** y `max_tokens` limita pensamiento más
  respuesta *juntos* — hay que dimensionarlo contando ambos.
- **`temperature`, `top_p` y `top_k` devuelven 400.** El estilo se ajusta por prompt.

**Dependencia práctica:** M4 necesita credenciales para probarse punta a punta. Hasta
entonces quedará verificado solo contra respuestas fijas, y lo diré explícitamente en vez
de presentarlo como validado.

---

## 8. Qué cambió en este commit

`to_dict()` en `core/`; `forge/tools/` con `sandbox.py`, `approval.py` y `registry.py`;
`anthropic>=0.120` como dependencia; 35 tests nuevos. **La CLI no cambió** — sigue en 5/5
y con los mismos códigos de salida.
