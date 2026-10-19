# La app local de BMS

Paso 15 · 19 de octubre de 2026

La ventana con la que trabaja administración: facturas, avisos, relaciones, dinero y
datos, en **neerlandés o inglés**, sin salir del ordenador. La pidió el dueño así:
«Podríamos construir como app local para que tenga una interfaz razonable con el
cliente y que pueda acceder a la información que necesite?», con la opción B del
diseño («Me gusta la opción B con el menú de navegación así. Importante que sea
claro») y «Quiero que sea minimalista el panel y que sea fácil de entender».

> **Lo de siempre sigue valiendo.** La app enseña y deja dar las órdenes que ya
> existían (con su permiso, su motivo y su firma). No paga, no aprueba un pago, no
> presenta el BTW ni crea una factura: esas pantallas no existen. «Sin objeciones del
> sistema» nunca es «aprobado». Un IBAN se verifica como siempre, por teléfono al
> número que ya se tenía, y lo firma una persona ([arquitectura.md](arquitectura.md)).

Este documento es la primera versión, la de la **base** del paso 15: el marco, la
entrada, la navegación, los idiomas y el servicio. Las pantallas se van llenando en las
partes siguientes del paso (al final, «Lo que falta»).

---

## 1. Qué es

Una página que sirve el mismo programa de siempre (`bms-agent serve`) en
`http://127.0.0.1:8765/app`. Se escribe en `frontend/` (React y TypeScript) y se
construye en `src/bms_agent/web/`, que va en git: el ordenador del dueño (Docker o la
instalación nativa) no necesita Node para nada.

- **Solo se abre desde el propio ordenador**, como la consola: el servidor escucha en
  `127.0.0.1` y no deja entrar a otra web (Host y Origin, igual que en `/api/v2`).
- **No tiene internet ni lo necesita**: las fuentes (IBM Plex Sans y Mono) van dentro;
  no hay imágenes, scripts ni estilos de fuera.
- **La consola de antes sigue** en `http://127.0.0.1:8765/consola`, de reserva, con
  el mismo token. Si algo de la app no se viera bien, todo se puede hacer allí.

El aspecto es el de la opción B («Workbench»), más sencillo: fondo blanco roto
(`#f7f5f0`), texto casi negro, un solo color de acento (verde azulado `#0e5f5c`),
líneas finas, sin gráficos y sin sombras salvo en lo que flota (menús, avisos). Solo
tema claro. Pensado para una ventana de 1440 px, y se usa también a 1024 px (las
tablas anchas se desplazan dentro de su caja); por debajo de 768 px el menú va en una
hoja que se abre con el botón de menú.

## 2. Cómo se abre

| Dónde | Cómo |
| --- | --- |
| Docker | `docker\iniciar.bat` (o con `-Demo`, los datos de prueba) |
| Instalación nativa | **BMS Finanzas - Abrir la consola** (`windows\iniciar.bat`; con `-Demo`, los datos de prueba) |
| A mano, para desarrollar | `bms-agent serve` (con `--db datos/demo.sqlite3` para los de prueba) y abrir `http://127.0.0.1:8765/app` |

Los dos `iniciar` esperan a que `/app` conteste y la abren **en su propia ventana de
Edge** (`msedge --app=http://127.0.0.1:8765/app`): sin pestañas del navegador ni barra
de direcciones, como un programa. Si Edge no está, se abre en el navegador de siempre;
si tampoco se puede, dicen la dirección. Al terminar dicen también dónde está la
consola de antes.

Con la base de prueba, arriba de todo va la banda **TESTGEGEVENS · TEST DATA**, y en
la cabecera la marca «Testgegevens». En la instalación nativa, si la comprobación del
aislamiento falla, falta o es vieja, una **banda roja** dice qué papel falla y que se
ejecute `comprobar.bat`. Las dos bandas las pone el servidor dentro de la página, así
que se ven aunque el script no llegue a cargar.

## 3. Cómo se entra

Con el **token personal** de siempre (el de la consola), que da quien mantiene el
programa (`bms-agent usuario token NOMBRE`, o `persona.bat` en Docker). La entrada
dice en una frase qué es y quién lo da.

- **El token vive solo en la memoria de la ventana.** No va a `localStorage`, ni a
  `sessionStorage`, ni a una cookie, ni a la dirección. Recargar o cerrar la ventana es
  volver a escribirlo.
- `GET /api/v2/yo` dice quién es y qué permisos tiene: el menú solo enseña lo que la
  persona puede usar (Importeren y Facturen lezen piden `importar_datos`) y los botones
  de cada orden siguen su permiso.
- **Uitloggen / Log out** (en el menú de la persona, arriba a la derecha, y en
  Instellingen) olvida el token. Si el servidor contesta `401` en cualquier momento
  (un token retirado), la app vuelve sola a la entrada y lo dice.

## 4. Las pantallas

A la izquierda, la navegación del componente del dueño (barra lateral con pestañas
como las de Chrome), en seis grupos. Cada pantalla contesta **una** pregunta, dicha en
una frase debajo de su título.

| Grupo | Pantalla | Qué contesta |
| --- | --- | --- |
| Dagelijks · Daily | Overzicht · Overview | Qué necesita atención hoy y cómo está el dinero |
| | Werklijst · Work queue | Todas las facturas, lo más urgente arriba |
| | Uitzonderingen · Exceptions | Lo que alguien tiene que resolver, y quién está en ello |
| | IBAN-controles · IBAN checks | Las cuentas que faltan por verificar por teléfono |
| Facturen · Invoices | Inkomend · In (inkoop) | Las facturas de proveedores y zzp'ers |
| | Uitgaand · Out (verkoop) | Las facturas de BMS a sus clientes |
| Relaties · Parties | Leveranciers · Providers | Proveedores: lo pendiente y lo que destaca |
| | Klanten · Clients | Clientes: lo que deben y lo que falta facturar |
| | Objecten · Objects | Por cada sitio de un cliente: ingresos, costes y margen |
| | Inkooporders · Purchase orders | Cuánto queda de cada PO y cuáles se acaban |
| Geld · Money | Kasstroom · Cash flow | Lo que entra y sale las próximas semanas |
| | Btw · VAT | El BTW por trimestre, listo para revisar (lo presenta una persona) |
| Gegevens · Data | Importeren · Import | Leer ficheros de Exact, del banco y de TRNSPRNT |
| | Facturen lezen · Read invoices | Leer PDF; antes se ve lo que cuesta |
| (abajo) | Instellingen · Settings | El idioma y la cuenta |

Junto a Werklijst, Uitzonderingen e IBAN-controles va una insignia solo con lo que pide
hacer algo (las facturas bloqueadas, las excepciones abiertas, las cuentas por
verificar); sale del panel (`/api/v2/panel`) y, si no se puede leer, no se pinta.

**Las pestañas.** Cada pestaña es una pantalla o una ficha. Elegir algo en el menú lo
abre en la pestaña actual; el `+` abre otra (y, con el ratón encima, «Snel openen»,
para abrirla ya en una pantalla); el menú `···` abre una nueva o cierra todas; con el
botón derecho sobre una pestaña se cierra, se cierran las demás o las de un lado; con
el botón central del ratón o con Supr se cierra; se reordenan arrastrándolas. Una fila
de una lista **abre su ficha en una pestaña nueva**, con su número de título; si esa
ficha ya estaba abierta, se va a su pestaña. Las pestañas abiertas y si la barra
lateral va plegada se guardan **por persona y por entorno**: al volver a entrar están
como se dejaron, y las de la base de prueba nunca abren una ficha de la de verdad.

En esta primera versión, Werklijst es una lista mínima (prioridad, número, relación,
importe, vencimiento y pago) y la ficha de factura dice qué es y de quién; las demás
pantallas enseñan su título y su frase. Instellingen ya está entera.

Lo que se ve, en las reglas de diseño que valen para todas las pantallas:

- El Overzicht lleva como mucho cuatro tarjetas (Aandacht nodig, Geld in, Geld uit,
  Btw dit kwartaal) y una lista «Volgende» de cinco, y nada más.
- Una lista lleva como mucho seis columnas, las cifras a la derecha y alineadas, y una
  columna «Waarom» en palabras normales.
- Una ficha empieza por qué es, qué está mal y qué hacer (una lista corta con los
  botones), y deja los detalles (campos, líneas, planning, relaciones, historia)
  plegados debajo.
- Un estado es siempre texto **y** color, nunca solo color. Las prioridades son
  etiquetas con forma: Geblokkeerd (cuadrado, naranja quemado oscuro), Urgent
  (triángulo, melocotón), Aandacht (círculo, azul claro), Normaal (gris).
- Los códigos de regla (X1, B2…) salen pequeños y en gris, como referencia.
- Las palabras del oficio (Object, PO, BTW, uitzondering) llevan un (?) que las explica.
- Una pantalla vacía dice algo útil («Niets heeft je aandacht nodig»); una que carga o
  falla lo dice también, con un botón para reintentar.

## 5. Neerlandés e inglés

Por defecto, **neerlandés**; el interruptor **NL | EN** está en la cabecera, en la
entrada y en Instellingen. Cada persona tiene el suyo (se guarda con su id y el
entorno); la entrada sale en el último usado en ese ordenador. No hay castellano en la
interfaz.

- **Importes, horas y fechas siempre en notación neerlandesa**, también en inglés:
  `€ 36.270,36`, `€ −24,76`, `78,5 u` / `78,5 h`; en tablas `16-10-2026`, en una frase
  `16 okt 2026` / `16 Oct 2026`. Los importes se escriben desde los céntimos enteros de
  la API (`*_cent`) y las horas desde las milésimas (`*_mil`) con aritmética de
  enteros: ni un céntimo se pierde por redondeo.
- **Los textos de la app** (menús, títulos, botones, avisos) están en
  `frontend/src/i18n/nl.ts` y `en.ts`; el tipo obliga a que los dos tengan las mismas
  claves.
- **Los textos del dominio** (cada regla, qué quiere decir y qué hacer; estados,
  prioridades, campos, fuentes, órdenes) salen de los catálogos de Python
  `src/bms_agent/textos/nl.json` y `en.json`, que la app importa al construirse, para
  que la CLI, la auditoría y la app digan lo mismo. Lo que la API manda en castellano
  (`titulo`, `detalle`, `etiqueta`, `fuente_texto`, `nota`, `motivos`) no se enseña:
  queda para la CLI y la auditoría. *Provisional:* mientras esos catálogos no están en
  esta rama, `frontend/src/i18n/domain.ts` usa un sustituto mínimo
  (`frontend/src/i18n/domain/`), marcado como tal.
- Lo que escribe una persona (notas, motivos) y lo que viene de un documento
  (descripciones de línea, referencias, nombres) se enseña tal cual, como texto.

## 6. La seguridad

Lo mismo que la consola, y algo más:

- **Lista blanca.** El servidor lee al arrancar lo que hay en `src/bms_agent/web/`
  (`index.html` y cada fichero de `assets/` con un tipo conocido: `.js`, `.css`,
  `.woff2`, `.svg`) y solo sirve eso, por nombre exacto. Ninguna ruta de una petición
  se junta con una carpeta: `/app/assets/../x` es un 404. Sin construir, `/app` dice
  que se use `/consola`.
- **Política de contenido** de la página:
  `default-src 'none'; script-src 'self'; style-src 'self' 'nonce-…'; font-src 'self';
  img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none';
  form-action 'none'; require-trusted-types-for 'script'; trusted-types 'none'`.
  Solo corre el script propio (nunca `unsafe-inline` ni `unsafe-eval`); el *nonce*,
  nuevo en cada respuesta, es para los `<style>` que meten dos bibliotecas (el bloqueo
  del desplazamiento de los menús y de la hoja del móvil); Trusted Types hace que una
  asignación a `innerHTML`, aunque la hubiera, falle. Además `X-Frame-Options: DENY`,
  `nosniff`, `Referrer-Policy: no-referrer`; la página no se guarda en caché y sus
  ficheros (con el hash en el nombre) se guardan para siempre.
- **El texto es texto.** En `frontend/src` no hay `dangerouslySetInnerHTML`,
  `innerHTML`, `insertAdjacentHTML`, `document.write`, `eval` ni `new Function`, ningún
  enlace ni imagen hecho con un dato de la API y ninguna dirección de fuera (lo mira
  `tests/test_app_local.py`).
- **Lo único que se guarda en el navegador** son comodidades de cada persona, en
  `localStorage` y solo desde `frontend/src/lib/storage.ts`: el idioma, si la barra va
  plegada y qué pestañas había (ids de pantalla e ids numéricos), con la clave
  `bms-app:v1:<entorno>:<persona>:…`. Lo que se lee se comprueba campo a campo; si el
  navegador no deja guardar, la app sigue igual.
- **Las órdenes** van solo por `POST /api/v2/acciones`, con la `rev` de la fila
  cuando la orden la pide y un `peticion_id` nuevo (repetirla no la aplica dos veces).
  Un `409` de concurrencia dice «Iemand anders heeft dit net gewijzigd. Laad opnieuw…».
  Las descargas (el PDF original, la hoja del BTW) se piden con `fetch` y el token, y se
  guardan con un `Blob`: el token nunca va en una dirección.

## 7. Para quien la cambia

```bash
cd frontend
npm ci            # las dependencias exactas de package-lock.json
npm run dev       # servidor de desarrollo en http://127.0.0.1:5173/app/, que pasa /api
                  # a un bms-agent serve en marcha (BMS_SERVE_URL, por defecto :8765)
npm run typecheck
npm test          # vitest: formatos, idiomas, rutas, lo que se guarda, el cliente de la API
npm run build     # construye en src/bms_agent/web y escribe web/fuente.json
npm run e2e       # Playwright con una base de prueba nueva (abajo)
```

Hace falta Node 22. Después de cambiar algo de `frontend/` hay que **construir y meter
lo construido en el mismo commit**: `tests/test_app_local.py` vuelve a calcular la
huella de las fuentes (lo que lista `frontend/build-inputs.json`, con los CRLF como
LF) y falla si no es la de `src/bms_agent/web/fuente.json`; también comprueba que lo
que hay en `web/` es lo que apunta. `web/` va en git byte a byte (`.gitattributes`).

**Dónde está cada cosa**

| Carpeta | Qué |
| --- | --- |
| `src/components/ui/` | Los componentes de shadcn (button, sheet, input, label, tooltip, context-menu, dropdown-menu, hover-card, avatar) y el componente de navegación del dueño (`sidebar-with-chrome-like-tabs.tsx`; arriba del fichero, lo que se le cambió y por qué) |
| `src/components/` | Las piezas de las pantallas: `PageHeader` y `Screen`, `SummaryCard`, `DataTable` (seis columnas como mucho, lo exige el tipo), `PriorityPill`, `StatusText`, `Money`, `Hours`, `DateText`, `EmptyState`, `ErrorState`, `Loading`, `HelpTip`, `Section` |
| `src/screens/` | Las pantallas, `registry.ts` (cuáles hay, su grupo, su icono y su permiso) y `render.tsx` (qué pinta cada ruta) |
| `src/shell/` | El marco: la navegación con sus insignias, el idioma, la persona, la marca de datos de prueba |
| `src/lib/` | El cliente de la API (`api.ts`), la sesión (`session.tsx`), los formatos (`format.ts`) y lo que se guarda (`storage.ts`) |
| `src/i18n/` | Los textos de la app (`nl.ts`, `en.ts`) y el acceso a los del dominio (`domain.ts`) |
| `e2e/` | Las pruebas en el navegador |

**Por qué los componentes de shadcn están en `src/components/ui`.** Es la ruta que usan
shadcn y su CLI (`components.json`: `ui` es `@/components/ui`), y todos sus imports
la dan por hecha (`@/components/ui/button`). Tenerlos ahí separa lo reutilizable de las
pantallas y deja que un `npx shadcn add` futuro funcione sin tocar nada. Aquí se
copiaron a mano (desde aquí no se llega a ui.shadcn.com); con el registro a mano, un
componente nuevo es `npx shadcn add NOMBRE`.

**Una pantalla nueva** es una línea en `screens/render.tsx`, sus textos en `nl.ts` y
`en.ts` (título, frase, y lo suyo) y, si es una ficha, su entrada en `RECORDS` de
`registry.ts`. Una fila abre una ficha con `useTabs().openRoute(recordRoute('invoice',
id, 'work-queue'))`, y la ficha pone su título con `setTabTitle`. Una lectura usa
`session.api.get(paths.algo)`; una orden, `session.api.action(nombre, datos)` (con
`rev` en `datos` cuando la pide; `GET /api/v2/acciones` las lista); una descarga,
`session.api.download(ruta, nombreDeReserva)`. Un error se dice con `ErrorState`, que
lo traduce: el texto del servidor no se enseña.

**Las dependencias** van con su versión exacta (sin `^` ni `~`), cada una publicada al
menos 14 días antes de fijarla, con `package-lock.json` en git. Para añadir o subir una:
`npm install --save-exact --before=AAAA-MM-DD paquete@versión` (con la fecha de hace
14 días), `node scripts/check-lock-age.mjs` (lo comprueba con el registro de npm) y
volver a construir. `@playwright/test` y `playwright-core` van fijados en 1.56.1, la
versión del Chromium que hay instalado para las pruebas.

**Las pruebas en el navegador** (`npm run e2e`) crean una base de prueba nueva en una
carpeta temporal (`scripts/crear_demo_e2e.py`, que da los tokens en JSON), arrancan
`bms-agent serve` sobre ella en un puerto libre y entran con un token de prueba. En
cada prueba: toda petición tiene que ir a `127.0.0.1` (otra se corta y la prueba falla),
ninguna violación de la CSP, ningún error en la consola, y axe sin problemas serios ni
críticos (WCAG 2.1 AA). Dejan una captura de cada pantalla en neerlandés y en inglés,
a 1440×900, en `CAPTURAS_DIR` (por defecto `frontend/test-results/capturas`, que no va
en git). El Python es el de `.venv` (o `BMS_PYTHON`); el navegador, el de
`PLAYWRIGHT_BROWSERS_PATH` (no se baja nada: nunca `playwright install`).

## 8. Lo que falta

Las partes siguientes del paso 15 llenan las pantallas sobre esta base: el Overzicht,
la Werklijst completa (con «Waarom»), la ficha de factura (qué está mal, qué hacer, los
detalles plegados, el original), las excepciones, las verificaciones de IBAN (con el
flujo de siempre), las relaciones, el dinero, el BTW, importar y leer, con los
catálogos de textos de Python en vez del sustituto.
