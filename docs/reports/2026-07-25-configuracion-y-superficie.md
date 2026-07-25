# Reporte técnico 006 — Configuración persistente y superficie de herramientas

**Fecha:** 2026-07-25
**Rama:** `claude/project-analysis-92tsia`
**Reporte previo:** [005 — El agente, con modelo local](2026-07-25-agente-local.md)
**Contexto nuevo:** el owner corre Forge en **Termux (Android)**, con una PC disponible
solo a veces

---

## 1. Qué pasó

Forge quedó instalado y funcionando en un teléfono: `doctor` da 5/5, y `scan`, `tree` y
`stats` corren sin problemas. Todas las dependencias resolvieron como wheels puros —
`typer`, `rich`, `httpx`, `pygments`— así que no hizo falta compilar nada en Termux.

Ese entorno no estaba previsto cuando elegimos Ollama con GPU, y expone dos fricciones
reales que este commit corrige.

---

## 2. Una decisión anterior que se validó sola

`forge doctor` en el teléfono devolvió **5/5** con el check de entorno virtual en ❌ y
marcado `(informativo)`.

Es exactamente el cambio de criterio del reporte 003: `.venv/` está gitignoreado y su
presencia depende de cómo instaló cada uno, no de la salud del proyecto. En Termux la
instalación es global, sin virtualenv. Con el criterio original ese mismo repo habría
sacado **5/6 en el teléfono y 6/6 en una computadora** — el mismo proyecto, distinto
puntaje según el aparato. Que era justamente el argumento para sacarlo del denominador.

---

## 3. Configuración por variables de entorno

`--base-url http://192.168.1.47:11434/v1` es tolerable una vez y absurdo en cada consulta,
sobre todo tipeado en un teclado de teléfono.

Tres variables: `FORGE_BASE_URL`, `FORGE_MODEL` y `FORGE_TOOLS`. Se ponen una vez en el
`~/.bashrc` de cada dispositivo y `forge ask` las toma solo. **Las opciones de línea de
comandos siguen ganando**, que es la precedencia esperable: lo permanente en el entorno, lo
puntual en el comando.

Resuelve el caso "PC a veces sí, a veces no" sin agregar ningún concepto: en el teléfono la
variable apunta a la PC de la red, y cuando la PC no está se sobreescribe con la opción, o
se cambia la variable. No hace falta un sistema de perfiles ni un archivo de configuración
— sería inventar maquinaria para un problema que dos variables ya resuelven.

---

## 4. Recorte de la superficie de herramientas

En el reporte 005 anoté "siete herramientas pueden ser demasiadas para un modelo chico"
como algo a medir. Con un modelo corriendo en un teléfono deja de ser hipotético.

`--tools` acepta tres formas: `all` (default), `minimal`, o una lista separada por comas.

**`minimal` son `forge_analyze`, `read_file` y `write_file`.** El criterio fue cubrir el
ciclo completo —descubrir, leer, escribir— sin dejar opciones ambiguas. `forge_analyze`
devuelve estructura y salud en una sola llamada, con lo cual las otras tres de análisis
(`doctor`, `stats`, `scan`) se vuelven redundantes para un modelo que ya tiene poco margen
para elegir bien. Sacar una de las tres restantes rompería el ciclo: sin descubrir no sabe
qué leer, sin leer no sabe qué escribir.

Dos detalles del diseño:

- **El orden pedido se respeta.** El orden en que el modelo ve las herramientas influye en
  cuál elige, así que quien recorta decide también la prioridad.
- **Un nombre inexistente falla antes de contactar al modelo**, con la lista de nombres
  válidos. Hay un test que verifica que el error sea sobre la herramienta y no sobre la
  conexión — si fallara después, un error de tipeo se confundiría con un runtime caído.

**El recorte no toca los controles de seguridad.** Hay un test que construye solo
`write_file` y verifica que el confinamiento de rutas siga rechazando `../fuera.txt`.

---

## 5. Verificación

145 tests (nueve nuevos). A mano: las variables de entorno tomadas correctamente, la
opción ganándole a la variable, `minimal` dando tres herramientas contra siete de `all`, y
el nombre inexistente fallando con la lista de disponibles y código 2.

**Sigue sin verificarse lo mismo que en el reporte 005:** que un modelo real elija bien las
herramientas. `minimal` es una hipótesis razonada sobre por qué un modelo chico se
confunde, no una medición. Si con `all` la traza muestra llamadas erróneas y con `minimal`
no, ahí tendremos el dato — y puede que el corte correcto sea otro.

---

## 6. Recomendación de uso

**Con la PC disponible:** `FORGE_BASE_URL` apuntando a ella y `--tools all`. Entra un 7B y
la superficie completa.

**Solo con el teléfono:** llama.cpp compilado en Termux, un modelo de 1B–3B y
`--tools minimal`. Va a ser lento y va a equivocarse más; el tope de iteraciones y los
mensajes de error del ciclo están para que se equivoque de forma recuperable.

En los dos casos el instrumento de medición es la traza que imprime `forge ask`. Si ves una
herramienta con ✗, esa llamada falló y el modelo tuvo que corregir; si la respuesta llega
sin ninguna herramienta usada, el modelo la inventó.
