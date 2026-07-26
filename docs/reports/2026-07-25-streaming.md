# Reporte técnico 008 — Streaming

**Fecha:** 2026-07-25
**Rama:** `claude/project-analysis-92tsia`
**Reporte previo:** [007 — Primera corrida real](2026-07-25-primera-corrida-real.md)
**Disparador:** una consulta que encadenaba dos herramientas se perdió por timeout

---

## 1. El síntoma y el diagnóstico

```
forge ask "leé el README y decime si describe bien lo que hace el código"
❌ El modelo no respondió en 180s.
```

La consulta anterior, que usaba una sola herramienta, funcionó. Esta encadena dos, y ahí
está la diferencia: la segunda llamada le manda al modelo el README completo (~1.300
tokens) y le pide un análisis largo. Con `max_tokens: 2048` en una GPU de menos de 8 GB,
generar esa respuesta puede llevar más de tres minutos.

El modelo estaba trabajando bien. La consulta se perdió igual.

---

## 2. Una corrección de mi diagnóstico anterior

En el reporte 005 anoté el streaming en la lista de "mejoras de experiencia, no
correcciones", junto con la observación de que "en una GPU chica hay una espera sin señal
en cada paso".

**Eso estuvo mal, y la corrida lo demostró.** Sin streaming, httpx espera la respuesta
entera como un bloque y el timeout corre sobre el **tiempo total de generación**. En
hardware modesto eso no es incomodidad: es que respuestas legítimas se descartan. Es un
defecto de correctitud disfrazado de detalle de presentación.

Vale anotar por qué me confundí: el streaming se justifica solo con el argumento de UX, y
me quedé ahí. El argumento fuerte —que cambia qué mide el reloj— solo se ve cuando el
hardware es lento, y hasta la corrida de Agustín no tenía hardware lento contra el cual
mirarlo.

---

## 3. Qué cambió

El cliente ahora pide `stream: true` y consume la respuesta por fragmentos.

**Lo importante es qué mide el timeout.** Antes medía la duración total de la respuesta;
ahora mide el **silencio entre fragmentos**. Son dos cosas distintas:

| Escenario | Antes (180s) | Ahora (120s) |
|---|---|---|
| Genera 20 s sin pausas | ✅ | ✅ |
| Genera 200 s sin pausas | ❌ se pierde | ✅ pasa |
| Manda algo y se cuelga | ❌ espera 180 s | ✅ corta a los 120 s |

El default bajó de 180 a 120 segundos justamente porque ahora significa otra cosa: 120
segundos *sin recibir un solo byte* ya es un runtime trabado, no un modelo pensando.
Configurable con `--timeout` o `FORGE_TIMEOUT`.

Verificado con dos servidores simulados: uno que genera durante 20 s con un timeout de 5 s
—que bajo el código anterior habría fallado— y otro que manda un fragmento y se calla,
detectado a los 3,2 s.

### Reensamblado de llamadas a herramientas

Es la parte fiddly. Una llamada llega repartida: el nombre en un fragmento, los argumentos
en varios (`{"path"` … `: "."}`). Se acumulan por `index`, que además es lo que permite
reconstruir varias llamadas en paralelo sin mezclarlas. Con tests para las dos cosas.

### Dos tolerancias a runtimes que se desvían

- **Un runtime que ignore `stream: true`** y mande la respuesta completa sigue
  funcionando: si no llegó ni una línea `data:`, se parsea el cuerpo entero. El parseo
  no-fragmentado no se borró, se recicló como respaldo.
- **Argumentos enviados como objeto** en vez de cadena, que algunos runtimes hacen.

### Indicador de avance

Puntos a **stderr** mientras el modelo genera. Van a stderr para no ensuciar la salida si
alguien la redirige, y se apagan con `--quiet`.

No es decoración: en una GPU chica cada paso tarda decenas de segundos, y una terminal
quieta es indistinguible de un cuelgue. Esa duda es lo que hace que uno corte una consulta
que estaba funcionando bien — que es exactamente lo que casi pasa acá.

---

## 4. Estado

153 tests (16 nuevos, casi todos del reensamblado de fragmentos). `doctor --strict` en
verde.

Lo que sigue sin medirse es lo mismo que disparó todo esto: **si el modelo mantiene el hilo
encadenando varias herramientas**. El timeout impidió llegar a esa medición. Ahora la
consulta debería completarse, y ahí recién se va a poder ver si un 7B sostiene una
secuencia de tres pasos o se pierde en el camino.
