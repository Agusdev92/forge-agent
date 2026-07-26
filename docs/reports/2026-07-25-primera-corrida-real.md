# Reporte técnico 007 — Primera corrida con un modelo real

**Fecha:** 2026-07-25
**Rama:** `claude/project-analysis-92tsia`
**Reporte previo:** [006 — Configuración y superficie](2026-07-25-configuracion-y-superficie.md)
**Entorno medido:** Windows · Ollama · `qwen2.5-coder:7b` · GPU de menos de 8 GB

---

## 1. La medición que faltaba

Desde el reporte 005 vengo marcando lo mismo como no verificado: **si un modelo real usa
bien las herramientas**. Ya está medido.

Primera corrida, sin ajustes previos:

```
forge ask "¿qué le falta a este proyecto?"

🔧 Herramientas usadas
  → forge_doctor(path='.')
```

Eligió la herramienta correcta para la pregunta, le pasó el argumento correcto, la llamada
salió bien y respondió sobre datos reales. **Tool calling nativo, al primer intento.**

Tres cosas que quedan confirmadas y dejan de ser hipótesis:

- `qwen2.5-coder:7b` soporta tool calling nativo y lo usa bien. El fallback por texto del
  reporte 005 no se activó — sigue siendo el respaldo para modelos más chicos, no el
  camino principal.
- El cliente OpenAI-compatible habla con Ollama sin ajustes. La decisión de formato del
  reporte 005 se sostiene contra un runtime real.
- Con siete herramientas disponibles eligió una sola y la correcta. **`--tools minimal` no
  hace falta en este hardware**, contra lo que anticipé en el reporte 006. Queda para
  modelos más chicos.

---

## 2. El bug que expuso, y es mío

La respuesta del modelo decía:

> *"El único check que no está puntuado es el 'Entorno virtual'. Esto significa que no hay
> un entorno virtual configurado."*

**Falso.** El entorno virtual existía. Esto es lo que le mandé:

```json
{ "name": "Entorno virtual", "status": "ok", "detail": "", "scored": false, "passed": true }
```

El check dice `status: "ok"` y `passed: true` — existe y pasa. Pero `scored: false` era el
**único `false` de toda la lista**, sentado al lado de un `passed: true`, en un campo cuyo
nombre no dice qué significa que sea falso. El modelo lo leyó como "esto está mal".

**No es un error del modelo, es un defecto de mi diseño de payload.** Le pedí a un
consumidor que interpretara un flag ambiguo, y un modelo chico es exactamente el consumidor
que no va a poder. Que un humano leyendo el JSON lo entienda no lo salva: el consumidor de
esta API es el modelo.

### La corrección

La tentación era explicárselo mejor en el prompt. Eso habría sido tapar el problema con
más texto y seguiría fallando con otro modelo. **La corrección es no hacerle interpretar
nada:** los checks informativos van en su propia lista.

```json
{
  "score": 5, "total": 5, "healthy": true,
  "checks": [ ...los 5 puntuables... ],
  "informational": [ {"name": "Entorno virtual", "status": "ok", "passed": true} ],
  "informational_note": "Los checks de 'informational' se reportan pero no afectan el
    puntaje... Un 'passed': true ahí significa que está presente."
}
```

El flag `scored` desapareció de los checks individuales: la pertenencia a una lista o a la
otra ya lo dice, y no queda ningún `false` que se pueda leer como fracaso. La nota
explicativa viaja en el propio payload, así que no depende del prompt del sistema.

Aplica igual a `ProjectReport`. **La salida de la CLI no cambió** — sigue mostrando
`✅ Entorno virtual (informativo)` y 5/5; el cambio es solo en lo que ve el modelo.

Hay test de regresión con el caso exacto: proyecto **con** `.venv`, verificando que aparezca
en `informational` con `passed: true`, que no esté entre los puntuables, y que ningún check
lleve ya el flag.

---

## 3. Qué me llevo de esto

El reporte 004 dejó una decisión que acá se cobra su primera factura: **`core/` no traduce
para el modelo, la capa de herramientas sí.** Eso estuvo bien, pero el payload que esa capa
emite es una interfaz de usuario, no un volcado de datos — y hasta ahora la venía tratando
como lo segundo. Los nombres de campos, qué se omite y cómo se agrupa son decisiones de
diseño con consecuencias medibles.

Regla operativa para lo que venga: **ningún campo booleano cuyo `false` no signifique
"algo salió mal"**. Si un flag necesita contexto para interpretarse, se convierte en
estructura.

---

## 4. Estado

147 tests. `doctor --strict` en verde. Todos los hitos del agente cerrados: serialización,
herramientas, seguridad, cliente local, ciclo y `forge ask` funcionando contra un modelo
real.

Lo que sigue sin medirse: cómo se comporta en preguntas que requieren **varias**
herramientas encadenadas. Esta corrida usó una sola. Ahí es donde un modelo de 7B
típicamente empieza a perder el hilo, y la traza de `forge ask` es el instrumento para
verlo.
