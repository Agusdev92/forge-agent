# Reporte técnico 005 — El agente, con modelo local

**Fecha:** 2026-07-25
**Rama:** `claude/project-analysis-92tsia`
**Reportes previos:** [001](2026-07-25-analisis-tecnico-y-roadmap.md) ·
[002](2026-07-25-fase-0-1-ejecucion.md) · [003](2026-07-25-fase-2-3-ejecucion.md) ·
[004](2026-07-25-fase-5-herramientas.md)
**Decisiones del owner:** sin modelos de pago · **Ollama** · GPU de menos de 8 GB

---

## 1. Resumen

`forge ask` funciona: el agente consulta un modelo que corre en la máquina del usuario,
usa las siete herramientas y puede escribir archivos con aprobación. Sin servicios pagos y
sin que el código salga de la máquina.

| | Antes | Después |
|---|---|---|
| Proveedor | SDK de Anthropic (de pago) | runtime local vía HTTP |
| Dependencias | `typer`, `anthropic` | `typer`, `httpx` |
| Ciclo del agente | lo resolvía el SDK | escrito acá |
| Comandos | 6 | **7** (`ask`) |
| Tests | 102 | **136** |

---

## 2. Qué costó el cambio, y qué no

Se fue el SDK de Anthropic y con él `@beta_tool`, que generaba los esquemas JSON desde los
docstrings. Hubo que reimplementarlo (`forge/tools/schema.py`, ~130 líneas).

**Lo que no se tocó: `sandbox.py`, `approval.py` y el cuerpo de las siete herramientas.**
El confinamiento de rutas, la compuerta de aprobación y sus 35 tests pasaron el cambio de
proveedor sin una sola modificación. No fue suerte — fue haber puesto la seguridad en la
capa de herramientas y no en la del modelo, decisión del reporte 004. Es la validación más
concreta que va a tener esa decisión.

### Reversión que me toca asumir

En el reporte 004 escribí que el *tool runner* del SDK eliminaba el hito "loop del agente".
Los runtimes locales no tienen equivalente, así que el loop volvió y está en
`forge/agent.py`. Es la segunda vez que ese hito cambia de estado en tres reportes.

---

## 3. La decisión de formato

El cliente habla el shape **`/v1/chat/completions` de OpenAI**, que implementan Ollama,
llama.cpp server, LM Studio y vLLM.

Quiero distinguirlo de lo que vengo rechazando desde el reporte 001. **No es diseñar una
interfaz por si aparece un segundo runtime** — eso sería especulativo y lo seguiría
descartando. Es elegir el formato que los cuatro ya implementan hoy: una sola
implementación, sin adaptadores, sin registro de plugins. Cambiar de runtime es cambiar la
URL base.

**Costo conocido y aceptado:** el endpoint compatible **no acepta el tamaño de contexto**.
En Ollama eso se configura del lado del runtime. Era la única ventaja real de la API
nativa y la estoy pagando. El síntoma cuando muerde es traicionero —el runtime trunca la
conversación en silencio y el modelo parece "olvidarse" de lo que hizo dos pasos atrás—
así que quedó documentado en el README, donde alguien lo va a buscar.

---

## 4. El diseño está gobernado por el modelo equivocándose

Con una GPU de menos de 8 GB entra un modelo chico, y un modelo chico usa herramientas
mal. Eso no es un detalle de implementación: es la premisa que define el ciclo.

Cinco fallas previstas, cada una con su manejo y su test:

| El modelo hace | Forge responde |
|---|---|
| Inventa un nombre de herramienta | Resultado con la lista de nombres válidos |
| Emite JSON roto como argumentos | Resultado con un ejemplo del formato correcto |
| Pasa un parámetro que no existe | Resultado con los parámetros que la herramienta acepta |
| Llama en loop sin converger | Tope de iteraciones, salida con código distinto de 0 |
| Escribe la llamada como texto en vez de emitirla | Se extrae del texto igual (§5) |

**Todas vuelven como resultado de herramienta, ninguna como excepción.** Una excepción
corta el ciclo; un resultado que describe el problema deja que el modelo corrija en el
intento siguiente, que es lo que suele pasar. Hay un test por cada caso.

También hay un tope duro de iteraciones y un `finally` que cierra el cliente, porque del
lado local no existe nada equivalente a los presupuestos de tarea del servidor.

---

## 5. Extracción de llamadas desde el texto

Muchos modelos chicos escriben la llamada en prosa aunque las herramientas estén
declaradas, y algunos no soportan el mecanismo nativo en absoluto. Forge busca llamadas en
el texto **siempre**, no solo cuando el nativo falla: si la respuesta trae `tool_calls` se
usan esas, y si no, se busca en el texto antes de darla por respuesta final. Es barato y
rescata el caso más común en hardware limitado.

Dos detalles que no son obvios:

- **El escaneo cuenta llaves, no usa una expresión regular.** Los argumentos pueden traer
  objetos anidados y una regex no cuenta llaves. Las cadenas se saltean para que una `{`
  dentro de un string no rompa el conteo.
- **Solo se acepta una llamada cuyo nombre coincida con una herramienta registrada.** Sin
  esa guarda, cualquier JSON que el modelo imprima como parte de su respuesta —incluida la
  salida de nuestras propias herramientas, que es JSON— se interpretaría como una llamada
  nueva. Hay un test con el caso exacto.

El turno del asistente también cambia según el origen: una llamada nativa trae `id` y el
protocolo exige devolver el resultado en un mensaje `tool` que lo referencie; una extraída
del texto no tiene `id`, así que el intercambio se hace en prosa. **Mandar un
`tool_call_id` inventado hace que algunos runtimes rechacen la conversación entera.**

---

## 6. Dos bugs encontrados al verificar

### 6.1 `from __future__ import annotations` rompía toda la generación de esquemas

Los módulos de herramientas usan anotaciones diferidas, con lo cual
`inspect.signature(...).parameters[x].annotation` devuelve la **cadena** `"str"` y no el
tipo `str`. La tabla de tipos estaba indexada por los objetos de tipo, así que **ningún
tipo era reconocido y ninguna herramienta podía construirse**. Se resuelve con
`get_type_hints`, que las evalúa. Con test de regresión.

Es exactamente la clase de cosa que el SDK resolvía sin que uno se enterara.

### 6.2 Una escritura rechazada se mostraba como exitosa

Apareció corriendo el flujo completo a mano, no en los tests. Al rechazar una escritura, la
traza mostraba `→ write_file(...)` con el símbolo de éxito, porque la herramienta devolvía
un error en el payload sin lanzar excepción.

Importa más de lo que parece: **en esa misma corrida el modelo afirmó "dejé las notas en
NOTAS.md"**, que era falso. Si la traza también dice que la escritura salió bien, quien lee
no tiene ninguna señal de que no ocurrió. El propósito de la traza es justamente poder ver
si la respuesta se apoya en algo real. Ahora una herramienta que devuelve `{"error": ...}`
se marca como fallida, con cuidado de no confundir a `forge_tree`, que devuelve una lista
JSON y no un objeto.

---

## 7. Qué está verificado y qué no

**Verificado, automatizado (136 tests):** generación de esquemas; el cliente contra un
servidor stub que habla el shape real —incluyendo 500, respuesta no-JSON, respuesta sin
`choices` y `tool_calls` malformadas—; el ciclo completo con las cinco fallas del §4; el
confinamiento y la aprobación, intactos del reporte 004.

**Verificado a mano, punta a punta:** `forge ask` contra un modelo simulado que llama a
`forge_doctor` de forma nativa y a `write_file` como texto. Camino de aprobación (archivo
escrito), camino de rechazo (archivo intacto), y runtime caído (mensaje accionable, código
de salida 2).

**No verificado, y no lo voy a presentar como si lo estuviera:** **que un modelo real use
bien las herramientas.** En este entorno no hay runtime local ni GPU, y montar uno para
inferencia en 4 CPUs no daría una medición representativa de tu máquina. Todo lo que
depende del modelo —si `qwen2.5-coder:7b` elige la herramienta correcta, con qué
frecuencia inventa nombres, si el contexto por defecto alcanza— **solo se mide en tu
hardware**. Es la parte que te toca probar.

---

## 8. Lo que espero que falle primero

Cuando lo corras, en orden de probabilidad:

1. **Contexto corto.** Ollama lo define del lado del runtime y el default suele quedar
   chico para una conversación con resultados de herramientas. Síntoma: el modelo repite
   llamadas que ya hizo.
2. **Herramientas de más.** Siete pueden ser demasiadas para un modelo chico. Si elige mal
   de forma consistente, el experimento barato es recortar la superficie antes de tocar
   los prompts.
3. **Llamadas en loop.** El tope las corta, pero si pasa seguido conviene un modelo más
   grande antes que más prompt.

Los tres se miden con la traza que imprime `forge ask` — para eso está.

---

## 9. Estado del roadmap

| Hito | Estado |
|---|---|
| M1 — Serialización | ✅ |
| M2 — Herramientas + seguridad | ✅ |
| M3 — Cliente local | ✅ |
| M4 — `forge ask` | ✅ |
| M5 — Memoria | sin caso de uso |

Pendientes que no bloquean el uso: la salida no es *streaming*, así que en una GPU chica
hay una espera sin señal en cada paso; y el tamaño de contexto no se puede fijar desde
Forge por la elección del §3. Los dos son mejoras de experiencia, no correcciones —
conviene decidirlos después de medir en hardware real, no antes.
