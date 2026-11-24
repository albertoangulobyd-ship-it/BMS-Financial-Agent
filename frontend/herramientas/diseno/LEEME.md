# El fichero de diseño de BMS Finance y las fotos de la comparación del tema claro

Dos herramientas que salen de la app construida de este repo (`src/bms_agent/web`, que va en git),
de la que **solo se lee**: la base de prueba, lo que escribe el servidor y todo lo demás va a esta
carpeta (`captura/`, `salida/`, `.trabajo/`), que **no va en git** (`.gitignore`): se rehace con
los guiones.

| Qué | Para qué | Guion | Sale en |
| --- | --- | --- | --- |
| **A. El fichero de diseño** | Las pantallas de la app, paradas y en DOM de verdad (se pueden inspeccionar), en un solo HTML sin red: 25 estados × 1440 y 400 px × oscuro y claro, con una primera página de colores y letra. Para mirar o revisar el diseño sin arrancar la app. | `capturar.mjs` → `montar.mjs` → `comprobar.mjs` | `salida/bms-finance-diseno.html` |
| **B. Las fotos «ahora» y «oscuro»** | Las de la comparación del tema claro (antes y ahora), rehechas con la app de hoy, con los mismos nombres, tamaño y encuadre | `comparacion.mjs` | `salida/comparacion/` (o `--out`) |

## Qué hace falta

- **Node 22 y las dependencias del frontend**: `npm ci` en `frontend/` (de ahí se carga
  Playwright; esta carpeta no tiene dependencias propias).
- **La app construida** en `src/bms_agent/web` (va en git; tras cambiar el frontend, `npm run
  build`). Se fotografía esa, no `frontend/src`.
- **El Python del repo** con sus dependencias, el mismo que usan las e2e (`e2e/global-setup.ts`):
  `BMS_PYTHON` si está puesta; si no, el `.venv` de la raíz del repo (`.venv/bin/python`, o
  `.venv\Scripts\python.exe` en Windows); si no, `python3` o `python` del `PATH`. Solo vale uno
  que cargue la app del repo (`import bms_agent.cli`, con pydantic y pyyaml). En una copia recién
  clonada se prepara como dice la puesta en marcha del `README.md` de la raíz: `python -m venv
  .venv`, activarlo y `pip install -e ".[dev]"`. Si no hay ninguno que valga, la orden dice cuál
  miró y qué le falta, y para antes de hacer nada. `montar.mjs` no lo necesita.
- **La base de prueba no hay que prepararla**: `capturar.mjs` y `comparacion.mjs` hacen una nueva
  por pasada, como las e2e, con `scripts/crear_demo_e2e.py` en `.trabajo/`, arrancan `bms-agent
  serve` sobre ella en un puerto libre de 127.0.0.1 y la borran al terminar.
- **El Chromium de Playwright** (abajo, «El navegador»).

## Las órdenes, desde una copia recién clonada

Desde `frontend/` (en Windows, las mismas en PowerShell o en cmd):

```sh
npm ci                              # una vez: las dependencias exactas
npm run diseno:capturar             # A1. capturar: unos 9 min (4 pasadas: oscuro y claro × 1440 y 400)
npm run diseno:montar               # A2. montar: unos 2 s
npm run diseno:comprobar            # A3. comprobar: 1 min; sale con 0 si todo está bien (abajo, «Si la comprobación falla»)
npm run diseno:comparacion          # B. las 12 fotos: unos 2 min
```

Son `node herramientas/diseno/capturar.mjs` (y `montar.mjs`, `comprobar.mjs`,
`comparacion.mjs`) con lo que venga detrás de `--`; valen igual desde cualquier carpeta. `--repo
<ruta>` fotografía otra copia del repo (por defecto, la que lleva esta carpeta).

- `capturar.mjs` arranca el servidor de verdad sobre una base de prueba nueva, entra como Ana Demo
  y llega a cada estado como una persona (el orbe, la rueda, las filas). En cada uno para la
  pantalla (sin cuadros de animación y con las animaciones de CSS en pausa), copia el DOM tal como
  está y hace la foto de la pantalla viva. Cada pasada (un tema y un ancho) tiene su servidor y su
  base: las cuatro ven los mismos datos. Opciones: `--solo estado,estado`, `--anchos 1440,400`,
  `--temas dark,light`. Lo capturado **se suma** a lo que ya hubiera en `captura/`: para empezar
  de cero, borra `captura/`.
- `montar.mjs` hace el HTML con lo que haya en `captura/`: no necesita el repo, ni Python ni un
  navegador. Opciones: `--captura <carpeta>`, `--salida <fichero>`. Falla si pasa de 12 MB. Sin
  nada capturado, lo dice y para («primero npm run diseno:capturar»).
- `comprobar.mjs` abre el fichero como lo abre una persona (`file://`, sin red) y mira que: no pide
  nada a la red ni deja errores en la consola; la primera página trae los colores de los dos temas
  y la escala de letra; el índice filtra por tema y por ancho; y **cada** fotograma se monta, tiene
  los elementos y el texto que tenía la app, y **se ve como la foto de la pantalla viva** del mismo
  estado: como mucho un 1 % de píxeles que cambien más de 48 niveles y una diferencia media de 1,5
  niveles. Opciones: `--fichero`, `--captura`, `--solo id,id`.
- **Si la comprobación falla** (sale con 1 y dice `MAL: <fotograma>: …`): la foto del marco queda en
  `.trabajo/comprobar/<fotograma>.png`, para ponerla al lado de la pantalla viva,
  `captura/<fotograma>.png`. Si es un fallo de la herramienta (un estado que no se monta como se
  veía), se arregla en `estados.mjs` o en `congelar.mjs` y se captura todo otra vez. **Recapturar
  solo ese estado (`--solo`) no vale como arreglo**: con `--solo` se toma sin el estado que le
  precede en la gira, y un fallo que viene de ese estado desaparece sin estar arreglado (así pasó
  con `documenten-klantkaart`; ahora llega desde una Documenten recién abierta). Lo que se publica
  sale de una captura entera que pasa.
- `comparacion.mjs`: opciones `--out <carpeta>` y `--solo nombre,nombre`.

Con variables (en PowerShell, `$env:BMS_PYTHON = "C:\…\python.exe"`; en sh, delante de la orden):
`BMS_PYTHON`, `PLAYWRIGHT_BROWSERS_PATH` y `BMS_CHROMIUM` (abajo).

## Dónde queda cada cosa

| Carpeta (de esta) | Qué | Lo hace |
| --- | --- | --- |
| `captura/` | por fotograma, `<estado>-<ancho>-<tema>.json` (el DOM) y `.png` (la pantalla viva); `hoja-0.css` (la hoja tal como la sirve la app), `tokens-<tema>.json` y `captura.json` (el índice, con el commit del repo); `FALLO-*.png` si algo falla | `capturar.mjs` |
| `salida/` | `bms-finance-diseno.html` (lo que se publica, unos 4,0 MB con los 100 fotogramas) y `montaje.json` | `montar.mjs` |
| `salida/` | `comprobacion.json` | `comprobar.mjs` |
| `salida/comparacion/` | `ahora-*.jpg` (10) y `oscuro-*.jpg` (2) | `comparacion.mjs` |
| `.trabajo/` | lo temporal: la base y el servidor de cada pasada; en `comprobar/`, la foto de lo que no pasa | todas |

## Publicarlo o compartirlo

El fichero de diseño es uno solo y sin red: se puede mandar tal cual, abrir desde el disco o
publicar como artefacto de claude.ai. Para que el enlace que ya se tiene siga valiendo, se
**actualiza el mismo artefacto** con el fichero nuevo. Las fotos de B van junto a las `antes-*`
de la comparación ya publicada (este guion no escribe ningún fichero con ese nombre).

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
- `comprobar.mjs` compara con las fotos que hizo `capturar.mjs`: hay que capturar y comprobar con
  el mismo navegador y en el mismo ordenador (otro Chromium u otro sistema cambian el suavizado de
  la letra o el ancho de las barras de desplazamiento).

## Windows

Está escrita para valer también en Windows: las rutas con `path.join` y `fileURLToPath` (el
fichero se abre con `pathToFileURL`), los procesos sin shell, el Python de
`.venv\Scripts\python.exe` y el borrado de la base temporal con reintentos (Windows tarda en
soltarla). **No se ha corrido en Windows**: solo en Linux.

## A. Qué lleva el fichero de diseño

- **La primera página**: los colores con nombre de la hoja de estilo de verdad (las propiedades
  `--…` que valen un color: la paleta `--l-*` del tema claro y las de la app), con lo que valen en
  cada tema y su muestra; los colores que de verdad pintan los fotogramas (el diseño oscuro de
  Aurora lleva sus colores escritos en cada regla, sin nombre: ahí están); y la escala de letra
  (cada cuerpo con su familia, pesos, interlineados y una muestra).
- **El índice**: cada estado con sus cuatro fotogramas; arriba, los botones que dejan solo un
  tema o un ancho, y la escala (25, 50 o 100 %).
- **Los fotogramas**: 25 estados × 1440 y 400 px × oscuro y claro, en neerlandés. Cada uno con su
  nombre, su ventana y su tema, en su propio `<iframe srcdoc sandbox>`: ningún estilo se sale de
  su marco ni entra en él. «Solo, a tamaño real» lo deja solo en la página (`#solo=<id>`).

Los estados (`estados.mjs`): `login`, `start`, `start-wiel` (la rueda), `paneel-start-kaart`,
`te-ontvangen`, `te-ontvangen-kaart`, `bank` (Te bevestigen, con la tarjeta de un cobro que propone
el banco), `te-betalen`, `te-betalen-kaart`, `btw-kaart`, `instellingen`, `instellingen-kaart`,
`instellingen-mailbox`, `instellingen-automatisch` (las tarjetas del buzón de facturas y de la
lectura automática en Systeem, paso 18: en la base de prueba, sin configurar y apagada),
`gesprek-bento`, `zoeken-filters`, `zoeken-filterlijst` (la lista de un filtro, abierta), `ctrl-k`,
`documenten-mappen`, `documenten-map-open`, `documenten-klantkaart`, `factuur-ingeklapt`,
`factuur-uitgeklapt`, `verwerken-start` y `verwerken-bezig` (la lectura en marcha, con el lector de
las pruebas `scripts/simular_lector.py`).

### Cómo está hecho un fotograma

- Es el DOM de la app tal como estaba (el `outerHTML` de una copia, leído en la página de la app
  mientras se captura), sin sus guiones, y la hoja de estilo que sirve la app, sin tocar. La hoja y
  las imágenes (el logotipo y lo que enseñaba cada canvas) van **una vez** en el fichero; cada
  fotograma va tal cual en un `<script type="text/plain" data-df-marco="…">` y se monta en su
  `<iframe srcdoc>` al acercarse a la ventana (y se suelta al alejarse).
- **Los canvas** (el orbe, las carpetas, la suricata) siguen siendo `<canvas>`, para que las
  reglas de la hoja que apuntan a `canvas` sigan valiendo, pero ya no dibujan: llevan
  `data-df-canvas` y, como fondo, la imagen de lo que enseñaban (PNG; WebP las grandes).
- **Las animaciones de CSS** están en pausa en el punto en que se tomó el fotograma
  (`<style data-df-fijo>`: un retraso negativo por elemento, `data-df-anim`).
- Lo que el HTML solo no puede decir lo pone un guion mínimo dentro de cada marco (`df-restaurar`,
  lo único que corre en él): abre las hojas modales como modales (`data-df-modal`), pone cada
  desplazamiento en su sitio (`data-df-scroll`, en píxeles enteros) y el foco donde estaba
  (`data-df-foco`), y no deja que un enlace se lleve el marco.

### Límites

- La app no trae ficheros de letra: pide `Inter, "Segoe UI", sans-serif`. El fichero se ve con la
  letra del ordenador en que se abre, igual que la app.
- Un fotograma es un estado parado: se puede desplazar e inspeccionar, pero sus botones no hacen
  nada (no está la app).
- `Ctrl+K`: la app no tiene paleta ni atajo desde el paso 17 (registro, §6.5). El fotograma
  `ctrl-k` es lo que se ve tras pulsarlo en el inicio: nada nuevo.
- Documenten no tiene filtros: «la lista de un filtro abierta» es la de Zoeken
  (`zoeken-filterlijst`); de Documenten van la rejilla, una carpeta abierta y la ficha de un cliente.
- En los temas claro y oscuro los datos son los mismos, pero el orbe no: es una animación y cada
  fotograma lo coge en un momento distinto.

## B. Las fotos de la comparación del tema claro

Saca de la app construida las diez `ahora-<estado>.jpg` (tema claro) y las dos
`oscuro-<estado>.jpg`, con los mismos nombres, el mismo tamaño (1440 × 900 y 400 × 860, un píxel
por píxel) y el mismo estado y encuadre que las publicadas: `start-1440`, `te-ontvangen-1440`,
`gesprek-bento-1440`, `documenten-1440`, `factuur-kaart-1440`, `bevestigen-400`,
`factuur-ingeklapt-400`, `documenten-klant-400`, `zoeken-filters-400`, `verwerken-400`; en oscuro,
`start-1440` y `documenten-1440`. Las `antes-<estado>.jpg` (el tema claro viejo) no se rehacen.

Los importes y las fechas salen de la base de prueba del día: pueden no ser los de las fotos
viejas; el estado y el encuadre, sí. En `bevestigen-400` se llega hasta la pregunta de confirmación
y no se dice que sí: no se apunta ningún pago.

## Los ficheros

- `comun.mjs`: las rutas de esta carpeta, el servidor sobre una base de prueba nueva y el contexto
  del navegador; los argumentos, el Python y el navegador son de `../entorno.mjs`, común con la
  vista previa.
- `app.mjs`: moverse por la app como una persona (como `frontend/e2e/nav.ts`, sin `expect`).
- `estados.mjs`: los 25 estados del fichero de diseño y cómo se llega a cada uno.
- `congelar.mjs`: lo que corre dentro de la página de la app al capturar: parar la pantalla,
  copiar el DOM, leer los colores con nombre; y lo que corre dentro de cada marco del fichero
  (`RESTAURAR`).
- `capturar.mjs`, `montar.mjs`, `comprobar.mjs`: la herramienta A. `comparacion.mjs`: la B.
