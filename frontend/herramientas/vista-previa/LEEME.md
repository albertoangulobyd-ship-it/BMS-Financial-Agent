# La vista previa navegable de BMS Finance

UN fichero `.html` sin red (`salida/bms-finance-vista-previa.html`, unos 5,5 MB) que corre la app
DE VERDAD (el React y el CSS de este repo, por su entrada `frontend/src/main.tsx`) contra las
respuestas GRABADAS de `/api/v2` sobre la base de prueba de las e2e. Sirve para que el dueño (o
quien sea) recorra la app entera como una demo, sin instalar nada: abierta desde el disco, servida
en cualquier ruta o publicada como artefacto de claude.ai. Neerlandés y oscuro al abrir; el tema
(Instellingen › Thema: claro, oscuro, el del sistema) y los idiomas (ES, NL, EN) funcionan. Nada
se guarda: es una foto de la base de prueba.

La herramienta no tiene dependencias propias: usa las de `frontend/node_modules` (vite, los plugins
de React y de Tailwind, playwright-core) y el Python del repo. Del repo **solo se lee**; todo lo que
escribe va a esta carpeta (`grabacion/`, `salida/`, `.trabajo/`), que **no va en git**
(`.gitignore`): la grabación se rehace con `grabar.mjs` y el fichero con `construir.mjs`.

## Qué hace falta

- **Node 22 y las dependencias del frontend**: `npm ci` en `frontend/` (lo mismo que para
  construir la app).
- **Para grabar, el Python del repo** con sus dependencias, el mismo que usan las e2e
  (`e2e/global-setup.ts`): `BMS_PYTHON` si está puesta; si no, el `.venv` de la raíz del repo
  (`.venv/bin/python`, o `.venv\Scripts\python.exe` en Windows); si no, `python3` o `python` del
  `PATH`. Si no hay ninguno, la orden lo dice y para.
- **La base de prueba no hay que prepararla**: `grabar.mjs` la hace nueva cada vez, como las e2e,
  con `scripts/crear_demo_e2e.py` en `.trabajo/`, arranca `bms-agent serve` sobre ella en un puerto
  libre de 127.0.0.1 y la borra al terminar. `construir.mjs` no la necesita.
- **Para grabar y comprobar, el Chromium de Playwright** (abajo, «El navegador»).

## Las órdenes, desde una copia recién clonada

Desde `frontend/` (en Windows, las mismas en PowerShell o en cmd):

```sh
npm ci                                   # una vez: las dependencias exactas
npm run vista-previa:grabar              # 1. grabar: unos 10 min
npm run vista-previa:construir           # 2. construir: unos 10 s
npm run vista-previa:comprobar -- --solo iframe --anchos 1440 --rapida --sin-lectura
                                         # 3. comprobar, la corta: unos 6 min
npm run vista-previa:comprobar           #    la entera: unos 45 min
```

Son `node herramientas/vista-previa/grabar.mjs` (y `construir.mjs`, `comprobar.mjs`) con lo que
venga detrás de `--`; valen igual desde cualquier carpeta. `--repo <ruta>` hace la vista previa
de otra copia del repo (por defecto, la que lleva esta carpeta; tiene que tener
`frontend/node_modules`).

- **1. Grabar** solo hace falta la primera vez y cuando cambia la API, la base de prueba o lo que
  la app pide (`comprobar.mjs` falla entonces con «sin grabar»). Sin grabación, `construir.mjs` lo
  dice y para: «todavía no hay grabación… primero npm run vista-previa:grabar».
- **2. Construir** es lo normal cuando cambia la app y no la API: lee `frontend/src` y
  `src/bms_agent/textos` y usa la grabación que ya hay.
- **3. Comprobar** sale con 0 y dice `BIEN` solo si las pasadas pedidas terminan sin ningún fallo.
  Opciones: `--solo file,http,iframe` (y una cuarta que no entra si no se pide, `--solo srcdoc`:
  el mismo iframe sandbox con el fichero en su `srcdoc`, sin ruta ninguna), `--anchos 1440,400`,
  `--rapida` (sin la gira entera), `--sin-lectura` (sin la lectura grabada de Procesar), `--traza`
  (cada parada con su segundo), `--nombre x` (deja `comprobacion-x.json`), `--capturas <carpeta>`,
  `--fichero <html>` (otro fichero, también uno ya publicado, envuelto: así se comparan dos).

Con variables (en PowerShell, `$env:BMS_PYTHON = "C:\…\python.exe"`; en sh, delante de la orden):
`BMS_PYTHON`, `PLAYWRIGHT_BROWSERS_PATH` y `BMS_CHROMIUM` (abajo).

## Dónde queda cada cosa

| Carpeta (de esta) | Qué | Lo hace |
| --- | --- | --- |
| `grabacion/` | `grabacion.json` (las respuestas, unos 4 MB), `pagina.json` (las bandas del servidor), `grabacion-resumen.json` | `grabar.mjs` |
| `salida/` | `bms-finance-vista-previa.html` (lo que se publica), `construccion.json` (su tamaño, sha256, commit, cuántas respuestas) | `construir.mjs` |
| `salida/` | `comprobacion.json` y `capturas/` (las pantallas de cada pasada) | `comprobar.mjs` |
| `.trabajo/` | lo temporal: el build de Vite, la base de prueba mientras se graba, lo que sirve `comprobar.mjs` | las tres |
| `publicada/` | si se quiere, un fichero publicado de antes para comparar (`--fichero publicada/index.html --nombre viejo`) | a mano |

Nada de eso va en git (`.gitignore` de la raíz). Si un fallo de grabar deja una captura,
es `grabacion/FALLO-<idioma>-<parada>.png`.

## Publicarla o compartirla

El fichero es uno solo, sin red y solo con ASCII: se puede mandar tal cual, abrir desde el disco
(doble clic), servir en cualquier ruta o publicar como artefacto de claude.ai. Para que el enlace
que ya tiene el dueño siga valiendo, se **actualiza el mismo artefacto** con el fichero nuevo (no
se publica otro). El servicio lo envuelve en su esqueleto (`src/envoltorio.html` es ese esqueleto)
y lo enseña en un `<iframe sandbox>` sin `allow-same-origin`: `comprobar.mjs` lo comprueba así
(la manera `iframe`), además de desde `file://` y por http.

## El navegador

- **Por defecto, el del Playwright del repo** (`playwright-core` 1.56.1, el mismo que usan las
  pruebas e2e), con la compilación de Chromium que pide esa versión, en la carpeta de
  `PLAYWRIGHT_BROWSERS_PATH` si está puesta (si no, la de siempre de Playwright: en Windows
  `%LOCALAPPDATA%\ms-playwright`, en Linux `~/.cache/ms-playwright`). Nunca se instala nada.
- Si esa compilación no está pero en la misma carpeta hay otra, se usa esa y se dice («aviso: no
  está el Chromium que pide Playwright…»). Si no hay ninguna, la orden lo dice y para.
- `BMS_CHROMIUM=<ejecutable>` usa ese Chromium y ningún otro.
- En una máquina que solo tiene otra compilación (como la de las pruebas de 11-2026, con la 1243
  donde Playwright 1.56.1 pide la 1194), basta con `PLAYWRIGHT_BROWSERS_PATH` apuntando a esa
  carpeta, o a una con enlaces que se llamen como la que se pide (`chromium-1194`,
  `chromium_headless_shell-1194`) hacia la que hay.

## Windows

Está escrita para valer también en Windows: las rutas con `path.join` y `fileURLToPath` (y
`pathToFileURL` para abrir el fichero desde `file://`), los procesos sin shell, el Python de
`.venv\Scripts\python.exe` y el borrado de la base temporal con reintentos (Windows tarda en
soltarla). **No se ha corrido en Windows**: solo en Linux.

## Qué hace cada cosa

| Fichero | Qué hace |
|---|---|
| `grabar.mjs` | Levanta el servidor de verdad (`bms-agent serve`) sobre una base de prueba recién hecha (`scripts/crear_demo_e2e.py`), como `e2e/global-setup.ts`, da la gira por la app como Ana Demo (entera en neerlandés, las pantallas principales en español y en inglés) y guarda cada respuesta GET de `/api/v2`. Después pide directamente lo que la gira pidió de una factura, empresa, Object, orden, trimestre o documento para TODOS, la búsqueda con cada empresa y clase de documento, y la búsqueda por texto con lo que se escribe (números, nombres y los nombres de la rueda y de los paneles en los tres idiomas). Al final graba una lectura de Procesar con `scripts/simular_lector.py`. `--hoy AAAA-MM-DD` hace la base como si hoy fuera ese día. |
| `construir.mjs` | Un build de Vite aparte (sin el `vite.config.ts` del repo, para no escribir en él): entrada `src/entrada.js` (el shim y después `frontend/src/main.tsx`), un solo chunk, una sola hoja, todo en línea y solo ASCII. Añade a los catálogos de textos (en memoria) los dos errores de la vista previa. Compone el fichero: `<title>`, un `<style>`, el cuerpo, un `<script type="module">`. Falla si pasa de 10 MB. |
| `comprobar.mjs` | Abre el fichero (a) desde `file://`, (b) por http en una ruta cualquiera y (c) envuelto como lo publica el servicio y dentro de un `<iframe sandbox>` sin `allow-same-origin` y de otro origen; a 1440 y a 400 px; da la gira en oscuro y en claro y en los tres idiomas, y falla con cualquier error de consola, petición a la red, petición sin grabación o desplazamiento horizontal. |
| `gira.mjs` | La gira, UNA para grabar y para comprobar: así lo que se comprueba es lo que se grabó. Se mueve por la estructura del DOM (no por los textos), así que vale en los tres idiomas y con cualquier base de prueba. |
| `comun.mjs` | Las rutas de esta carpeta y del repo; lo demás (los argumentos, las dependencias del repo, el Python y el navegador) es de `../entorno.mjs`, común con la herramienta del diseño. |
| `src/shim.js` | Lo que cambia de la página (nada de la app): `fetch` contesta con lo grabado, `Date` es el momento de la grabación, y la lectura grabada de Procesar. |
| `src/rutas.js` | Qué se contesta a cada petición (lo grabado por su clave, 401, 409, 404), sin tocar la página: lo usa el shim y lo prueba `frontend/scripts/herramientas.test.mjs` (vitest). Su `clave` es también la de `grabar.mjs`. |
| `src/textos-vp.js` | Los dos textos de la vista previa en NL, EN y ES (el aviso de la página y los dos errores del catálogo). |
| `src/cuerpo.html` | El cuerpo: la nota de arriba, la banda de DATOS DE PRUEBA, la banda de la lectura grabada, `#root` y el aviso. |
| `src/vista-previa.css` | El CSS de esos elementos (va después del de la app, sin tocarlo). |
| `src/envoltorio.html` | El esqueleto con el que el servicio publica el fichero: con él comprueba `comprobar.mjs` la manera (c). |

## Cómo se porta la vista previa

- **Entrar**: vale cualquier código (la nota de arriba lo dice mientras se ve la entrada). Sin
  código, 401 como el servidor. Se entra como Ana Demo (administradora).
- **Leer**: cada GET se contesta con lo grabado, por ruta y consulta (los parámetros, en orden).
  Un GET que no se grabó contesta 404 `no_grabado` (la app dice que no pudo leer los datos) y
  queda apuntado en `window.__vpSinGrabar`.
- **Las órdenes y subir un fichero** (todo lo que no es GET): 409 con el código `vista_previa`;
  la app lo dice donde dice sus errores y la página enseña siete segundos el aviso de abajo.
  (En Importar se ve el texto entero bajo el fichero elegido; Procesar dice sus errores con su
  frase de siempre, «Er ging iets mis…», y el porqué lo dice el aviso.)
- **Las descargas** (el original de una factura o de un documento, la hoja del btw en CSV): 409
  con el código `vista_previa_descarga`. Una factura sin documento contesta lo que el servidor.
- **La lectura de Procesar**: con Procesar abierto, la nota de arriba ofrece «▶ Opname van een
  leesronde afspelen»: `/api/v2/lectura` contesta entonces la lectura grabada, paso a paso con
  sus tiempos, y la app (que la consulta cada dos segundos) la sigue. Al salir de Procesar se
  acaba.
- **El reloj**: «ahora» es el momento de la grabación.
- **Sin red**: lo que no es `/api/` falla como falla la red. El fichero no pide nada fuera.

## Lo que hay que saber

- La búsqueda por texto solo contesta lo que se grabó (números de factura, nombres de empresas,
  Objects y órdenes, los nombres de la rueda y de los paneles, las tres preguntas del resumen).
  Otro texto, o una fecha o un importe en los filtros, da «no pude leer los datos».
- El fichero sale sin `<html>`, `<head>` ni `<meta charset>` propios (los pone quien lo publica)
  y solo con ASCII: abierto tal cual desde el disco, el navegador no tiene que adivinar la
  codificación (sin eso, a veces se leía como windows-1252 y la app no arrancaba).
- En el `<script>` del fichero, «`</script`», «`<!--`» y «`<script`» van escapados (`<\/`, `<\!`,
  `\x3C`): el fichero tiene exactamente un `<style>` y un `<script`. `construir.mjs` pasa después
  el código por `node --check` (un escape fuera de un texto sería un error de sintaxis).
- El CSS de la app que lleva el fichero es, byte a byte, el del build del repo
  (`src/bms_agent/web/assets/style-*.css`): el build de aquí usa los mismos plugins y la misma
  entrada (Tailwind lee las mismas fuentes: las de `src/index.css`, no esta carpeta). Detrás va
  solo `src/vista-previa.css`, que repite fuera de capa el marco de la página (el envoltorio del
  servicio pone `body{background:#fff}` sin capa) con el fondo de la app, `var(--background)`:
  #08090b en oscuro. Hasta el 15-11-2026 ponía `var(--sidebar)` (#0e0e12) y el fondo oscuro de la
  vista previa no era el de la app.
- Lo que corre dentro de la página (el shim, `rutas.js`, `entrada.js`, los textos, el cuerpo)
  sigue la regla de la app: nada de `innerHTML`, `outerHTML`, `insertAdjacentHTML` ni
  `dangerouslySetInnerHTML` (el aviso se pone con `textContent`), y ninguna dirección de fuera.
  Lo mira `frontend/scripts/herramientas.test.mjs`.
- `comprobar.mjs` no usa `serviceWorkers: 'block'` de Playwright: en un iframe sin
  `allow-same-origin` esa opción lee `navigator.serviceWorker` y da un error que no es de la página.
