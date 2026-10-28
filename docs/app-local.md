# La app local de BMS

Paso 15 · 19 de octubre de 2026 · Paso 16 (la base de Aurora, los temas y el castellano; la rueda con seis entradas, el inicio y las pantallas en su sitio; Documentos con datos reales; Cuentas por cobrar y por pagar con datos reales; el cierre de la puerta) · 28 de octubre de 2026 · Paso 17, B1 (el marco, el inicio y el menú de Aurora tal cual; o el menú o una pantalla) · 28 de octubre de 2026

La ventana con la que trabaja administración: facturas, avisos, relaciones, dinero y
datos, en **neerlandés, inglés o castellano**, sin salir del ordenador. La pidió el dueño así:
«Podríamos construir como app local para que tenga una interfaz razonable con el
cliente y que pueda acceder a la información que necesite?», con la opción B del
diseño («Me gusta la opción B con el menú de navegación así. Importante que sea
claro») y «Quiero que sea minimalista el panel y que sea fácil de entender».

> **Lo de siempre sigue valiendo.** La app enseña y deja dar las órdenes que ya
> existían (con su permiso, su motivo y su firma). No paga, no aprueba un pago, no
> presenta el BTW ni crea una factura: esas pantallas no existen. «Sin objeciones del
> sistema» nunca es «aprobado». Un IBAN se verifica como siempre, por teléfono al
> número que ya se tenía, y lo firma una persona ([arquitectura.md](arquitectura.md)).

Este documento cubre la **base** (el marco, la entrada, la navegación, los idiomas y el
servicio), **las pantallas del trabajo diario** (el inicio, la Werklijst, las
Inkoopfacturen y Verkoopfacturen, la ficha de una factura, las Uitzonderingen y los
IBAN-controles, §4.1) y **las demás**: Leveranciers, Klanten, Objecten e Inkooporders con
sus fichas (§4.2), Kasstroom y Btw (§4.3), Importeren y Facturen lezen (§4.4),
Instellingen (§4.5) y Documenten (§4.7), todas con datos y órdenes de verdad.

El **paso 16** trae dentro la base de **Aurora**, el prototipo del dueño: su aspecto
oscuro, su orbe, su logo y sus piezas, sin nada simulado (§7, «Aurora dentro de la app»);
los **dos temas**, el oscuro de Aurora por defecto, el claro y «Volg Windows» (§1); y el
**castellano** como tercer idioma, con su catálogo del dominio (§5). Y una primera
**navegación de Aurora** (seis entradas, la rueda en el inicio, las seis en pequeño en las
demás pantallas, Ctrl+K y el menú del nombre), que el paso 17 cambió por la de Aurora tal
cual (abajo). **La barra lateral con pestañas como las de Chrome ya no es la navegación**
(§4, «Lo que se quitó»). Y **Documentos es el archivo de
Aurora** con los datos de verdad: las carpetas de cristal, el árbol «Explorar», la ficha de
cada relación y la vista previa dibujada desde el registro, con la descarga del original
(§4.7). Y **Cuentas por cobrar y por pagar** con la cartera del motor: un resumen con
cuatro cifras («Saldos pendientes · No es efectivo disponible»), la antigüedad, cada
empresa con lo que debe o se le debe, y lo que hay que pagar esta semana con lo retenido y
por qué; el banco de cada lado (los pagos que propone y las líneas sin casar); y en la
ficha de cada factura sus **pagos** con las tres órdenes: confirmar un pago propuesto,
retirarlo y apuntar uno ya hecho, con motivo (§4.1, «Cobrar y pagar»). Nada de eso paga.

El **paso 17** (B1) cambia el marco por **el de Aurora, tal cual**, porque el dueño lo pidió
así: «Necesito que te apegues a las animaciones y diseño de esta aplicación, no quiero que
hagas algo diferente. No pueden vivir las pantallas y el menú al mismo tiempo». La app es
ahora la de su prototipo: el saludo, el orbe (la onda `SiriWave` de 440 px), «Druk om te
navigeren» y la caja; la rueda de Aurora con ocho entradas; los paneles de Aurora a la
derecha; la conversación con el resumen general (el Finance Bento); la búsqueda de Aurora; y
las pantallas de trabajo con el vuelo del orbe a la esquina. **O el menú o una pantalla,
nunca los dos** (§4, «La regla del dueño»). Se fueron la cabecera de arriba, las seis en
pequeño, las pastillas de las vistas, Ctrl+K, el menú del nombre, las cuatro tarjetas en el
inicio y las fuentes IBM Plex (§4, «Lo que se quitó»). Las pantallas del paso 15 y 16 siguen,
todas, como pantallas de trabajo dentro del marco de Aurora mientras sus paneles se rehacen
(el paso siguiente, B2).

---

## 1. Qué es

Una página que sirve el mismo programa de siempre (`bms-agent serve`) en
`http://127.0.0.1:8765/app`. Se escribe en `frontend/` (React y TypeScript) y se
construye en `src/bms_agent/web/`, que va en git: el ordenador del dueño (Docker o la
instalación nativa) no necesita Node para nada.

- **Solo se abre desde el propio ordenador**, como la consola: el servidor escucha en
  `127.0.0.1` y no deja entrar a otra web (Host y Origin, igual que en `/api/v2`).
- **No tiene internet ni lo necesita**: la letra es la del sistema, como en Aurora (Inter
  si está; si no, Segoe UI), y no hay imágenes, fuentes, scripts ni estilos de fuera.
- **La consola de antes sigue** en `http://127.0.0.1:8765/consola`, de reserva, con
  el mismo token. Si algo de la app no se viera bien, todo se puede hacer allí.

El aspecto es el de Aurora: **tema oscuro por defecto** (desde el paso 17, el de sus hojas
tal cual: fondo `#08090b`, texto `#e8e5ee`, la rueda en `#544e60` y `#eee5fa`, el panel en
`#101015`), la letra del sistema, títulos finos, líneas finas y sin sombras salvo en lo que
flota (menús, avisos). Hay también un **tema claro** con la misma paleta (fondo `#f5f4f8`,
tarjetas `#fcfbfe`, acento `#5b4890`) y **«Volg Windows»**, que sigue al modo de Windows y
cambia en vivo si Windows cambia. Lo elige cada persona en el menú de su cuenta o en
Ajustes (paso 17: el panel de la entrada «Instellingen» de la rueda), y se guarda como el
idioma: por persona y entorno, y la entrada sale con el último de ese ordenador. En las
hojas de Aurora, el claro es su inversión (`src/aurora/claro.css`, que escribe
`scripts/aurora-claro.mjs`: cada color con su luminosidad invertida en OKLab y el mismo
matiz; las hojas del dueño no se tocan). Los dos temas son variables CSS que usa toda la app
(`src/index.css`: las claras en `:root`, las oscuras en `:root.dark`) y los dos pasan WCAG
AA (axe y la medida de cada pastilla en cada pantalla, §7). El tema lo decide **solo la
clase `.dark` de `<html>`** (`frontend/src/lib/theme.tsx`, que la pone antes de pintar
nada): el CSS construido no lleva `prefers-color-scheme`, así que un Windows en oscuro no
cambia el tema que la persona eligió. Pensado para una ventana de 1440 px, con los cortes de
Aurora (1150 y 700 px): se usa también a 1024 × 768 y en el móvil (de 360 a 430 px), donde
todo va como en Aurora (el orbe arriba y la caja al pie, la rueda se gira con el dedo). Las
tablas anchas se desplazan dentro de su caja y nada se sale de la ventana por el lado, salvo
el orbe de Aurora, que a 400 px empieza fuera, como en su prototipo.

## 2. Cómo se abre

| Dónde | Cómo |
| --- | --- |
| Docker | `docker\iniciar.bat` (o con `-Demo`, los datos de prueba) |
| Instalación nativa | **BMS Finanzas - Abrir la consola** (`windows\iniciar.bat`; con `-Demo`, los datos de prueba) |
| A mano, para desarrollar | `bms-agent serve` (con `--db datos/demo.sqlite3` para los de prueba) y abrir `http://127.0.0.1:8765/app` |

Los dos `iniciar` esperan a que conteste la consola (`/consola`, que no depende de lo
construido) y abren la app **en su propia ventana de Edge**
(`msedge --app=http://127.0.0.1:8765/app`): sin pestañas del navegador ni barra de
direcciones, como un programa. Si `/app` no contesta 200 (el servidor da 503 cuando falta
lo construido o está incompleto), lo dicen y abren **la consola de antes** en su lugar: es
la reserva, y así se abre justo cuando hace falta. Si Edge no está, se abre en el navegador
de siempre; si tampoco se puede, dicen la dirección. Al terminar dicen también dónde está
la consola de antes.

Con la base de prueba, arriba de todo va la banda **TESTGEGEVENS · TEST DATA** (desde el
paso 17, sin la marca de la cabecera: ya no hay cabecera, y todo, la marca de BMS también,
baja lo que ocupan las bandas). En la instalación nativa, si la comprobación del
aislamiento falla, falta o es vieja, una **banda roja** dice qué papel falla y que se
ejecute `comprobar.bat`. Las dos bandas las pone el servidor dentro de la página, así
que se ven aunque el script no llegue a cargar. **Se desplaza la página entera** (con la
rueda del ratón, las teclas o el dedo; revisión del paso 16: antes el cuerpo no se
desplazaba y lo de debajo de la ventana no se alcanzaba), y las bandas se quedan arriba,
una debajo de otra, con la app debajo de ellas (`src/lib/server-bands.ts`).

## 3. Cómo se entra

Con el **token personal** de siempre (el de la consola), que da quien mantiene el
programa (`bms-agent usuario token NOMBRE`, o `persona.bat` en Docker). Desde el paso 17 la
entrada es el inicio de Aurora (L0): «Welkom.», el orbe (que no se pulsa hasta entrar), la
caja pide el código y el idioma va donde irá «Druk om te navigeren»; al entrar cambia solo el
saludo («Welkom, Ana»).

- **El token vive solo en la memoria de la ventana.** No va a `localStorage`, ni a
  `sessionStorage`, ni a una cookie, ni a la dirección. Recargar o cerrar la ventana es
  volver a escribirlo.
- **Tampoco al gestor de contraseñas de Edge.** Edge y Chromium no hacen caso de
  `autocomplete="off"` para guardar contraseñas, y un campo de contraseña que desaparece
  después de un `fetch` es para ellos una entrada que salió bien: ofrecerían guardar el
  token (y sincronizarlo con la cuenta de Microsoft). Por eso la entrada no tiene `<form>`
  ni `<input type="password">`: es un campo de texto con los caracteres tapados
  (`-webkit-text-security`), `autocomplete="one-time-code"`, Intro para entrar, y el
  campo se vacía antes de comprobar el token. Si aun así Edge ofreciera guardar algo, hay
  que decir **que no**.
- `GET /api/v2/yo` dice quién es (el inicio la saluda por su nombre) y qué permisos
  tiene: las entradas y sus filas solo enseñan lo que la persona puede usar (Importeren y
  Facturen lezen piden `importar_datos`: sin él, la entrada Verwerken no sale de la rueda,
  que tiene siete, ni Importeren del panel de Te ontvangen) y los botones de cada orden
  siguen su permiso.
- **Uitloggen / Log out** (al pie del panel de Instellingen) olvida el token. Si el servidor contesta `401` en cualquier momento
  (un token retirado), la app vuelve sola a la entrada y lo dice.

## 4. Las pantallas

**El marco es el de Aurora** (paso 17, B1; `src/aurora/`, con las hojas del dueño tal cual:
`styles.css`, `workspace-layout.css` y las de cada pieza). Hay dos pantallas, como en su
prototipo: **el inicio de Aurora** (todo lo que pasa en su espacio central) y **una pantalla
de trabajo** (Documentos o una pantalla del motor), y se pasa de una a otra con el vuelo del
orbe. Cada cosa que se pulsa es una acción de una máquina de estados pura
(`src/aurora/estado.ts`), así que nunca se ve un estado a medias.

| Estado | Qué se ve | Cómo se llega |
| --- | --- | --- |
| **L0** · la entrada | «Welkom.», el orbe quieto de pulsar, la caja del código y el idioma | Al abrir la app, al salir o si la sesión caduca |
| **E0** · el inicio | «Welkom, Ana», «Waarmee kan ik je vandaag helpen?», el orbe, «Druk om te navigeren» y la caja | Al entrar; el orbe con un panel, una conversación o una búsqueda; «Terug naar Aurora» y la miga «Start» desde una pantalla de trabajo |
| **E1** · la rueda | El orbe a la izquierda y la rueda de Aurora con las ocho entradas | «Druk om te navigeren» o el orbe desde E0; la ✕ de un panel |
| **E2** · un panel | El panel de Aurora (340 px) con su título, su frase y sus filas; el orbe a ×0,75 | Una entrada con panel (Instellingen, Start, Te ontvangen, Te betalen, Btw) |
| **E3** · escribiendo | La caja con lo escrito | La primera tecla (cierra la rueda, como en Aurora) |
| **E4** · la conversación | Las preguntas y respuestas; con «Geef me een overzicht», el resumen general (Finance Bento) | Intro en la caja |
| **E5** · la búsqueda | «Wat zocht je?», la caja de buscar, Filters y los resultados | La entrada «Zoeken»; «Zoeken met filters» en una respuesta |
| **Pantalla de trabajo** | El marco de Documentos de Aurora: la marca, «Terug naar Aurora», las migas y el orbe pequeño de la esquina, con la pantalla debajo | Documenten y Verwerken en la rueda; una fila de un panel; una fila de una respuesta |

**La regla del dueño: o el menú o una pantalla.** La rueda solo se ve en E1. Con un panel
abierto la rueda se oculta **en todos los anchos** (en Aurora solo a 1150 px o menos; la regla
`.has-panel .navigation{display:none}` va al final de `src/aurora/styles.css`) y la entrada
activa no se mueve: la rueda escondida no manda (ni la rueda del ratón ni las flechas). La
conversación, la búsqueda y las pantallas de trabajo tampoco conviven con la rueda. La pantalla que se va se
funde en 0,18 s y mientras tanto no recibe clics. Lo comprueba `e2e/exclusividad.spec.ts` en
cada estado, en cada cuadro de cada transición y a 1440, 1151, 1150, 1024 y 400 px.

**La rueda de Aurora** (`src/aurora/text-marquee.tsx`, su `TextMarquee`): una ventana de
240 px con filas de 48 px; se ven cinco entradas y la del centro es la activa (23 px, peso
650, `#eee5fa`; las demás, `#544e60`). Las ocho, en este orden: **Instellingen, Zoeken,
Documenten, Start, Te ontvangen, Te betalen, Btw y Verwerken**. Al abrirla por primera vez
en una sesión, Start está en el centro; después, la última que se usó. **Un clic en
cualquier entrada a la vista la abre a la primera** (en Aurora la centraba y el clic se
perdía); las que quedan fuera de la ventana no se pueden pulsar, como en Aurora, y se
alcanzan con un paso de la rueda del ratón (un paso por gesto, sin dar la vuelta), las
flechas, Tab (centra la entrada que recibe el foco) o el dedo (un paso por gesto): Instellingen
y Btw están a un paso, Verwerken a dos. Con Verwerken en el centro, el morado de Aurora y el
orbe de partículas; el orbe entra en Verwerken. Sin el permiso `importar_datos` la rueda
tiene siete (sin Verwerken). La decisión de dejar la ventana de cinco de Aurora (y no las
ocho a la vista) es del dueño, que pidió no cambiar su diseño (especificación §7, punto 10).

**Los paneles** (E2, `src/aurora/panels.tsx`), con el marco de Aurora: «WERKRUIMTE» y la ✕
(vuelve a la rueda con su entrada en el centro), el título, su frase, la línea de los datos
(«Testgegevens · EUR») y sus filas `.doc`. Escape cierra lo de dentro y después el panel; el
orbe vuelve al inicio.

- **Instellingen** (E2-A): Taal, Thema, Jouw account y Systeem, y «Uitloggen» al pie. Taal y
  Thema abren su lista (la elegida dice «In gebruik»); Jouw account, su tarjeta (el rol y
  «Wat je mag doen: N» con cada permiso); Systeem, sus filas: Bedrijf, Afscherming, Personen
  (solo para quien administra) y Back-ups, cada una con su tarjeta (§4.5).
- **Start, Te ontvangen, Te betalen y Btw**: mientras sus paneles se rehacen (paso
  siguiente, B2: la cifra y los grupos de especificación §2.2), cada uno lista sus pantallas
  de hoy, cada fila con su nombre, su frase y, si pide algo, su número («Werklijst 4
  geblokkeerd», «Uitzonderingen 13», «IBAN-controles 3», «Bankontvangsten» con los pagos
  propuestos). La primera es «Overzicht», su resumen. Una fila abre su pantalla de trabajo
  con el vuelo:

| Entrada | Sus filas, en este orden |
| --- | --- |
| **Start** | Overzicht (el resumen de antes: las cuatro tarjetas, «Als eerste» y «Ook in Start»), Werklijst, Uitzonderingen, IBAN-controles y Kasstroom |
| **Te ontvangen** | Overzicht, Verkoopfacturen, Bankontvangsten, Klanten, Objecten, Inkooporders van klanten e Importeren (pide `importar_datos`) |
| **Te betalen** | Overzicht, Inkoopfacturen, Bankbetalingen, Leveranciers e Inkooporders aan leveranciers |
| **Btw** | Overzicht (los trimestres) |

**Start › Overzicht** es el inicio de los pasos 15 y 16, entero: **cuatro tarjetas**
(**Aandacht nodig**, de `GET /api/v2/panel`; **Te ontvangen** y **Te betalen**, de
`GET /api/v2/cartera`, la misma lectura que sus resúmenes, con «Te bevestigen» cuando el banco
propuso pagos; y **Btw dit kwartaal**, con un plazo pasado sin la aangifte anotada y el
próximo), que **cuadran al céntimo** con su resumen, con la lista que abren y con el panel (lo
comprueba `e2e/payments.spec.ts`); **«Als eerste»**, solo lo bloqueado o urgente (como mucho
cinco cosas distintas, dos facturas con el mismo número en una fila); y **«Ook in Start»**,
con la Werklijst, las Uitzonderingen, los IBAN-controles y la Kasstroom. Cada tarjeta abre la
pantalla que la explica y sus filas la lista ya filtrada («Vervallen» abre las
Verkoopfacturen vencidas). Se vuelve a leer cada minuto mientras se ve y después de cada
orden.

Documenten (§4.7) y Verwerken (Facturen lezen, §4.4) se abren desde la rueda, sin panel, con
el vuelo. Las fichas (una factura, un proveedor, un cliente, un Object, una PO, un trimestre
del BTW, una excepción y la carpeta de documentos de una empresa) se abren dentro de su
pantalla de trabajo. Ninguna función se perdió por el camino: cada pantalla del paso 15 y 16
se alcanza desde una entrada (lo comprueba `src/aurora/estado.test.ts`).

**Las pantallas de trabajo** (`src/aurora/work-screen.tsx`), con el marco del archivo de
Aurora (`document-workspace.css`): la marca arriba a la izquierda, **«Terug naar Aurora»**
arriba a la derecha, **las migas** («Start › Te betalen › Leveranciers › J. Voorbeeld
Beveiliging (zzp)»; cada una vuelve a ese paso, «Start» al inicio) y el orbe pequeño de la
esquina (la `SiriWave` de 180 px en su caja de 96 × 52), que vuelve al inicio. Al entrar,
una copia de la onda vuela del centro del orbe grande al pequeño (1,05 s con
`cubic-bezier(.4,0,.15,1)`); al volver, el camino inverso. Alt+← y el botón de atrás del
ratón vuelven un paso (en la primera, al inicio). La lista vuelve como se dejó. Con «menos
movimiento», sin vuelo.

**La conversación** (E4, `src/aurora/chat/` y `src/aurora/assistant.ts`) contesta en el
ordenador, sin ningún modelo: con «Geef me een overzicht» («Dame un resumen general», «Give
me an overview»), el **resumen general**, el Finance Bento de Aurora con los datos de verdad
(la cartera de cobrar y de pagar, los clientes y los proveedores con lo que queda de cada
uno, los documentos de sus carpetas y la última lectura de facturas): **son saldos
pendientes, no efectivo disponible**, y lo dice; con «Wat is een Object?», la frase del
glosario; con el nombre de una pantalla, una fila que la abre (si es la de un panel, el
panel); con un número de factura, un nombre, un Object o una PO, «Ik vond N voor «…».» y sus
filas, que abren su sitio, y «Zoeken met filters», que lleva lo escrito a la búsqueda; con lo
demás, lo que sí sabe hacer. «Terug naar de ruimte» vuelve a la rueda.

**La búsqueda** (E5, §4.8) es la de Aurora: se abre desde la entrada «Zoeken» o desde una
respuesta y busca en `GET /api/v2/buscar`.

**Lo que se quitó** (paso 16): la barra lateral con pestañas como las de Chrome (el componente
del dueño del paso 15, `src/components/ui/sidebar-with-chrome-like-tabs.tsx`, se queda sin
montar). **Y en el paso 17**: la cabecera de arriba, las seis entradas en pequeño, las
pastillas de las vistas de cada entrada, Ctrl+K («Snel openen»), el menú del nombre (su
idioma, tema y salir están en Instellingen), la marca de prueba de la cabecera (la banda del
servidor sigue), las cuatro tarjetas y «Als eerste» del inicio (están en Start › Overzicht),
la caja que buscaba sin contestar (ahora es la conversación), la pantalla de la búsqueda con
filtros del paso 16 (ahora E5), el orbe del paso 16 (ahora la `SiriWave` de Aurora) y las
fuentes IBM Plex. La dirección sigue sin cambiar y al entrar se empieza en el inicio.

Lo que se ve, en las reglas de diseño que valen para todas las pantallas de trabajo:

- Una lista lleva como mucho seis columnas, las cifras a la derecha y alineadas, y una
  columna «Waarom» en palabras normales.
- Una ficha empieza por qué es, qué está mal y qué hacer (una lista corta con los
  botones), y deja los detalles (campos, líneas, planning, relaciones, historia)
  plegados debajo.
- Un estado es siempre la pastilla del dueño (§4.6): texto **y** color, nunca solo
  color, y su punto late solo en lo que pide hacer algo ya.
- Los códigos de regla (X1, B2…) salen pequeños y en gris, como referencia.
- Las palabras del oficio (Object, PO, BTW, uitzondering) llevan un (?) que las explica.
- Una pantalla vacía dice algo útil («Niets heeft je aandacht nodig»); una que carga o
  falla lo dice también, con un botón para reintentar.

**Los clics** (revisión §5). `e2e/clicks.spec.ts` cuenta, desde el inicio, los clics de cada
tarea de la tabla de la revisión y, aparte, los pasos de la rueda (escribir no cuenta; un
diálogo de confirmación va aparte), con la rueda como sale la primera vez en una sesión, Start
en el centro. Mientras los paneles llevan las pantallas de hoy, cada
camino por la rueda pasa por «Druk om te navigeren», la entrada y la fila: lo de un panel
cuesta 2 (qué necesita atención hoy: Start), lo de una pantalla 3 (Kasstroom, IBAN-controles,
Bankbetalingen, Objecten, Importeren, los resúmenes de cobrar y pagar) y una ficha 4. Lo que
se busca por su número o su nombre va por la conversación: escribirlo no cuesta y abrirlo es
1 (el PDF original de una factura, 2; marcarla revisada o apuntar un pago, 2 más su
diálogo). Btw está a un paso de rueda (su hoja, 5 clics) y Verwerken a dos (2 clics); cambiar
el idioma son 4 clics y un paso. La prueba falla si un camino crece; los paneles de B2 los
acortan a lo de la tabla de la especificación (§2.6).

### 4.1 El trabajo diario

Todo sale de `/api/v2` y cada orden es una de `servicios.ACCIONES` por
`POST /api/v2/acciones`. Un botón solo sale si la persona tiene el permiso de esa
orden (`frontend/src/lib/actions.ts`, que un test compara con `servicios.ACCIONES`);
quien solo puede mirar (rol `consulta`) no ve ninguno. Cada orden abre un diálogo que
dice en palabras normales qué va a pasar (la frase de confirmación del catálogo en lo
que mueve dinero, BTW o el banco), **una sola vez** y sin «Doorgaan?» (el botón ya dice
la orden; aparte, en una caja, solo lo que no se deshace, como anotar una aangifte), y
pide lo que hace falta (un motivo, una fecha). Después de una orden se vuelven a leer la
ficha, las listas, las insignias de las vistas y el inicio, sin que la pantalla salte a «Laden…».

| Pantalla | Qué hay | Órdenes |
| --- | --- | --- |
| **Start › Overzicht** | Las cuatro tarjetas, «Als eerste» solo con lo bloqueado o urgente, y los accesos a la Werklijst, las Uitzonderingen, los IBAN-controles y la Kasstroom (§4, «Start › Overzicht») | —, salvo abrir: cada tarjeta, cada fila de una tarjeta y cada fila de «Als eerste» abre lo suyo |
| **Werklijst** | Las facturas que piden a una persona (una prioridad que no es normal, un hallazgo pendiente, una excepción abierta o campos por verificar), en el orden de la API. Fichas Alle / Geblokkeerd / Urgent / Aandacht con su cuenta, un buscador (número o relación, sin mayúsculas ni acentos) y cinco columnas: Prioriteit, Factuur (número y relación), Bedrag, Vervaldatum, Waarom | Una fila abre la factura (Start › Werklijst › su número) |
| **Inkoopfacturen / Verkoopfacturen** (en Te betalen y en Te ontvangen, después del resumen) | Todas las de un sentido, con fichas y su cuenta: Alle, Openstaand (toda la deuda abierta, también lo vencido), Vervallen, Deze week, 30 dagen, Te bevestigen (con un pago propuesto por el banco), Betaald y Controle nodig; un tramo de antigüedad sale como una ficha más cuando se llega desde la barra del resumen. Las fichas de pago son las de la cartera: van por vencimiento (lo más antiguo arriba) y debajo dicen lo que suman, lo mismo que la cifra que se pulsó. El buscador; seis columnas: Prioriteit (la única pastilla de la fila), Factuur (número y relación; «1 van 2» si otra tiene el mismo número), Openstaand (lo que queda; «van € 9.163,94» si no es el total), Vervaldatum («65 dagen te laat», «over 4 dagen»), Stand (pago, con el hoy del motor aunque la caché sea de otro día; «Betaald» siempre con su fuente: «volgens de bank», «volgens Exact» o «met de hand, nog niet in de bank», con K3; «Betaling te bevestigen» y revisión, en texto gris) y Waarom. «Vervallen», como los tramos, va por el hoy del motor (revisión del paso 16: con la caché de otro día se quedaba corta de la cifra que la abría) | Una fila abre la factura |
| **Ficha de factura** | Arriba, qué es (con el botón **Origineel**, que baja el PDF, y **Betaling vastleggen** mientras quede algo por cobrar o pagar): el número, la relación, el importe con IVA, la prioridad con su razón con nombre, el vencimiento («65 dagen te laat»), el pago («Betaald» siempre con su fuente: «volgens de bank», «volgens Exact» o «met de hand … door Ana», con K3 si el banco no lo trae) y la revisión. Después **Betalingen** (abajo, «Cobrar y pagar») y **Wat aandacht nodig heeft**, con lo que dice el sistema al lado, en su pastilla («Geen bezwaren van het systeem» cuando está limpia; nunca «goedgekeurd»): cada hallazgo pendiente con su nombre, su detalle escrito desde sus valores, «Wat te doen» y sus botones; y **Afronden**: controleren, la uitzondering y una notitie. Plegado debajo: Velden (valor, fuente y calidad: Ontbreekt, Onzeker, Afwijking, Afwijkend, Geverifieerd), Factuurregels, Referenties en inkooporders, Koppelingen, Planning (los turnos conciliados), Notities, Controles zonder gegevens, Geschiedenis (en palabras normales) y el Origineel document | Aceptar un hallazgo con un motivo de 10 caracteres o más (`anular_hallazgo`, si la regla lo admite; con la segunda firma de otra persona cuando la pide), dar la segunda firma a un colega (`firmar_anulacion`), cerrar uno que ya no se ve (`cerrar_hallazgo`), verificar o corregir el campo al que apunta un hallazgo de lectura; marcar como gecontroleerd (`marcar_revisada`, con la huella de lo que se vio) o devolver (`devolver_factura`); abrir, asignar, dejar esperando y resolver la excepción; añadir una nota; cambiar un campo (antes de guardar se ve «Nu → Nieuw»), verificarlo o deshacer un cambio; confirmar o rechazar una relación propuesta; confirmar o retirar un pago y apuntar uno ya hecho (`confirmar_pago`, `retirar_pago`, `marcar_pagada`); descargar el original |
| **Uitzonderingen** | Las abiertas, la más urgente primero: qué pasa (el hallazgo más urgente, en palabras normales), de qué va (la factura con su relación, el cliente, la PO o la importación), en qué estado está, quién la lleva y desde cuándo. Una fila abre **la ficha de la excepción** (Start › Uitzonderingen › su asunto; antes, un panel lateral): qué pasa, de qué va, su estado y qué hacer. Una que ya se cerró lo dice y vuelve a la lista | Zelf oppakken, toewijzen, wachten op anderen (a quién y hasta cuándo), oplossen (cómo acabó y qué se hizo); desde la ficha, «Factuur openen» |
| **IBAN-controles** | Cada cuenta nueva o cambiada (los avisos F de las facturas y las del registro sin verificar): de qué proveedor es, el IBAN encontrado («nog niet bevestigd» solo si aún no se llamó), **lo que falta en una frase** cuando ya se verificó por teléfono (con un F2 abierto: «nog niet in de stamgegevens van Exact: zet de rekening in Exact en importeer de leveranciers opnieuw»; ya no se ofrece volver a llamar), en qué factura, qué vio el sistema y el teléfono **de los datos maestros**. Abajo, las cuentas heredadas sin confirmar | Verificar por teléfono (`verificar_iban`): llamar a ese número, nunca a uno de la factura; el IBAN que lee el proveedor **se teclea** (el campo va vacío, nunca se rellena con el del documento) y la app dice si es el mismo que el encontrado; quién contestó y una nota. Rechazar (`rechazar_iban`), con qué pasa con la factura. Confirmar las heredadas (`atestar_iban`) |

La **regla de las dos personas** la hace cumplir el servidor (código `segunda_persona`),
y la app dice en el diálogo cuál de los casos es («Je hebt het telefoonnummer voor
controle van deze leverancier zelf ingesteld…»). Cuando un aviso pide la segunda firma y
aún no la hay, la app **no deja mandar** la aceptación: lo dice arriba del diálogo y
pide a un colega «Tweede handtekening geven»; con la firma ya dada, dice de quién es y
hasta cuándo vale, y pone el mismo plazo (la ficha trae las firmas vigentes, `firmas`,
contrato 2.1). En la base de prueba se ve dos veces: Ana puso los teléfonos de los
proveedores, así que no puede verificar con ellos una cuenta (lo hace Bram), y aceptar el
número de factura repetido (B2, que bloquea) pide que otra persona dé antes la segunda
firma.

**Cobrar y pagar** (paso 16; revisión de Aurora §8.3 paso 4 y §8.4). Te ontvangen y Te
betalen tienen la misma forma, de `GET /api/v2/cartera` (la misma lectura que el panel:
las cifras cuadran al céntimo con el inicio y con las listas):

| Vista | Qué hay | Órdenes |
| --- | --- | --- |
| **Overzicht** (el resumen, la primera vista) | **Cuatro cifras**: Openstaand (en N facturas), Vervallen, Deze week (hasta el domingo) y Komende 30 dagen (hasta su último día); cada una abre la lista con esa ficha. Debajo, siempre, «Openstaande saldi · Geen beschikbaar geld», la fecha de los datos y la del último extracto del banco (con la pastilla de la fuente caducada si los datos o el extracto son viejos) y lo cobrado o pagado este mes según el banco. **Wat op iemand wacht**: los pagos propuestos por confirmar y las líneas del banco sin casar (abren el banco), los abonos sin enlazar, X1 (facturas sin importe en euros) y los avisos de pago raros (K2–K5, K8, K9) con sus facturas. **Hoe lang het al openstaat**: la barra de antigüedad y sus seis tramos (al corriente, 1–30, 31–60, 61–90, más de 90 días, sin fecha), cada uno abre su lista; **visible en Te ontvangen, plegada en Te betalen**. En Te betalen, **«Tot en met zondag …»**: lo vencido y lo que vence esta semana, en dos columnas, sin objeciones del sistema y retenido o bloqueado (cada factura con su razón), y debajo lo retenido que vence después. **Por empresa** (Klanten o Leveranciers): lo vencido primero; prioridad, la empresa (facturas abiertas, cuánto tarda en pagar o en pagarle, la razón de lo retenido), Openstaand, Vervallen y la más antigua («65 dagen te laat»). **Una empresa dice el mismo «Openstaand» en todas partes** (este resumen, Leveranciers y Klanten, su carpeta en Documentos y su ficha): el de la cartera, `deuda_cent`; sus notas de crédito sin enlazar van aparte, debajo («Creditnota nog niet gekoppeld: −€ 362,03»). En «Tot en met zondag» y lo retenido, «1 van 2» en dos facturas con el mismo número | La fila abre la ficha de la empresa; «Map» abre su carpeta en Documentos |
| **Bankontvangsten / Bankbetalingen** | **Te bevestigen**: cada pago que el banco casó a medias (`GET /api/v2/pagos/propuestas`), la línea del banco al lado de la factura (día, importe, quién, concepto; número, relación, lo que queda) y las tres coincidencias (referencia, importe, cuenta) en verde o en rojo. **Zonder factuur**: las líneas del banco de ese signo que no casan con nada (`GET /api/v2/movimientos?signo=`), con su día, lo que queda, quién y el concepto, y desde cuándo | **Bevestigen** (`confirmar_pago`, con una nota si se quiere), **Niet deze** (`retirar_pago`, con motivo obligatorio) y «Factuur openen»; cada línea sin casar, **Aan een factuur koppelen** (`marcar_pagada` con su `movimiento_id`: se elige una factura pendiente de ese lado; **ninguna viene elegida**: «Kies een factuur», y las que parecen de la línea —lo que queda es lo de la línea, o su número sale en el concepto— van primero y marcadas, «past bij deze bankregel»). Dos facturas con el mismo número llevan su «1 van 2» |
| **Betalingen** (en la ficha de cada factura) | Cada pago con su estado (Voorgesteld, Bevestigd, Ingetrokken), la fecha, el importe, la fuente (Bank, Exact, Handmatig; «vanzelf gekoppeld» si lo casó el banco solo), quién lo confirmó o lo apuntó, su línea del banco («Bankregel van 27-10-2026: € −496,10 · quién · concepto»), el motivo, el justificante («Bewijs downloaden») y, de uno retirado, quién y por qué. Lo que espera arriba, lo retirado al final. Lo de Exact se corrige en Exact (lo dice) | Bevestigen y Niet deze en lo propuesto; **Intrekken** (con motivo) en lo que no es de Exact; **Betaling vastleggen** en la cabecera: el importe (por defecto lo que queda; no más), la fecha (no futura; con una línea del banco manda la del banco), la línea del banco sin casar si la hay, **el motivo, obligatorio**, y un justificante de su carpeta si se quiere. El diálogo dice «Er wordt niets betaald» |

Todas piden el permiso `marcar_pagada`: quien solo mira (rol `consulta`) ve los pagos y no
ve ningún botón. El servidor decide lo demás: un pago que el banco o Exact ya traen, una
factura sin nada pendiente o una línea ya usada contestan `409 estado_no_valido`, y el
diálogo lo dice en palabras normales; dos personas a la vez, `409 conflicto` (abajo). En la
base de prueba, un extracto del banco de hoy trae cuatro cobros y dos pagos por confirmar,
un ingreso de un desconocido y una comisión sin casar (`scripts/crear_demo_e2e.py`).

**Concurrencia.** Cada orden lleva la `rev` de la fila (o la huella de la factura o
del hallazgo) que la persona vio. Si otra persona la cambió antes, el servidor contesta
`409` con el código `conflicto`; el diálogo dice «Iemand anders heeft dit net
gewijzigd. Laad opnieuw…» y ofrece **Opnieuw laden**, que vuelve a leer y no pisa nada.

**Lo que no hay, a propósito.** Ningún botón crea una factura, paga, aprueba un pago o
presenta el BTW: esas órdenes no existen (un test comprueba que la app solo manda
órdenes de `servicios.ACCIONES` y ninguna de esas; y que las tres de los pagos solo salen
de `src/screens/payment-actions.tsx`). Confirmar un pago o apuntar uno ya hecho dice qué
dinero **ya se movió**; no mueve ninguno ni prepara una transferencia. El IBAN del documento se enseña en
los campos («er wordt niet naar betaald») pero no se cambia ni se verifica desde ahí:
los datos bancarios van por IBAN-controles.

### 4.2 Relaciones: proveedores, clientes, Objects y PO

Cuatro listas con la misma forma: lo más urgente arriba (el orden de la API), un buscador
(nombre, código o número, sin mayúsculas ni acentos) y como mucho seis columnas, la última
«Waarom»: el hallazgo pendiente más urgente de esa relación (de sus facturas, de sus
Objects o de ella misma), escrito desde sus valores, o «N dagen te laat» cuando lo único es
lo vencido. Una fila abre su ficha dentro de su entrada (Klanten, Objecten y las PO de los
clientes en Te ontvangen; Leveranciers y las de los proveedores en Te betalen), con migas y
«Terug». Por debajo de 1280 px, Objecten deja
la columna Kosten e Inkooporders la de Waarde (se deducen de las otras), para que «Waarom»
quepa a 1024 px sin desplazar la tabla. Aquí solo se mira: las órdenes de una factura están
en la factura, que se abre desde la ficha.

| Pantalla | La lista | La ficha |
| --- | --- | --- |
| **Leveranciers** | Prioriteit, Naam (con cuántas facturas), Openstaand, Vervallen, Waarom | Qué es (cuántas facturas, cuánto queda), cinco cifras (prioridad, openstaand, vervallen, lo facturado este año, el plazo de pago), **Wat aandacht nodig heeft** (los hallazgos agrupados por factura, con «Wat te doen» y un botón «Factuur X openen» por factura) y, plegado: las facturas abiertas y todas, los pagos del banco, el reparto por Object, las cuentas bancarias con su estado y el teléfono de los maestros (la verificación va por IBAN-controles) y las relaciones propuestas. Las facturas abiertas salen ya desplegadas cuando las hay |
| **Klanten** | Igual | Igual, con lo que queda por facturar en vez del plazo y, plegado, el trabajo del planning aún sin facturar por Object |
| **Objecten** | Prioriteit, Object (código, nombre y cliente), Opbrengst, Kosten y Marge de este año (sin btw), Waarom | El cliente y si pide PO; el periodo (Deze maand, Vorige maand, Dit jaar) con opbrengst, kosten, marge y las **horas planificadas frente a las facturadas** (a la clientela y de los proveedores); las facturas de la locatie que piden a una persona (cinco, y cuántas más); plegado: las horas por semana, las facturas a la clientela y de los proveedores y las PO |
| **Inkooporders** (la misma pantalla dos veces: en Te ontvangen, las de los clientes; en Te betalen, las de los proveedores) | Prioriteit, PO (número, de quién o para quién y hasta cuándo), Waarde, Verbruikt (con su parte), Over, Waarom | De qué cliente o para qué proveedor y de cuándo a cuándo; **waarde, verbruikt, over y la previsión** (cuándo se acaba al ritmo de las últimas semanas, y lo esperado contando lo planificado y lo aún sin facturar); lo que necesita atención (P5–P10) y, plegado, sus facturas (con lo que quedaba después de cada una) y sus Objects |

### 4.3 El dinero: Kasstroom y Btw

**Kasstroom** es **una sola tabla**, sin gráficos: por filas, Al vervallen, Deze week,
Rest van deze maand, Komende 30 dagen, Zonder vervaldatum y Alles wat openstaat; por
columnas, Komt binnen, Gaat uit y Netto. Sale de las facturas abiertas por su vencimiento
(`/api/v2/flujo`; los periodos se solapan, y la tabla lo dice). Debajo, lo que ya se movió
este mes según el banco y, **aparte y marcado como estimación** («Schatting · geen
facturen»), el trabajo del planning aún sin facturar: no son facturas y no se suma a la
tabla.

**Btw** lista los trimestres, el más reciente primero, con su estado en texto y color
(Open, Klaar voor controle, Aangegeven), el saldo (te betalen / terug), hasta cuándo hay
para la aangifte (con los días que quedan, o «te laat») y qué hacer ahora, en palabras.
Una fila abre el **trimestre** (Btw › Q3 2026): arriba el estado y las cifras (omzet, btw
sobre la omzet, voorbelasting, saldo y plazo); después lo que hay que mirar antes de que
las cifras valgan (facturas por revisar, las que no entran, lo que cambió después de
dejarlo listo, con su factura) y los pasos para terminar, en orden:

1. **Werkblad downloaden**: la hoja del trimestre en CSV
   (`/api/v2/btw/AAAA-TN/hoja`, con `fetch` y un `Blob`), la misma que da la CLI;
2. **Klaarzetten** (`btw_lista_para_revision`, cuando el trimestre ya acabó), con la huella
   del werkblad que se vio, o **Kwartaal heropenen** con un motivo (`btw_reabrir`) si ya
   estaba listo;
3. cuando **una persona ya presentó la aangifte en el portal de la Belastingdienst**,
   **Ingediende aangifte vastleggen** (`btw_anotar_presentacion`): la fecha, la referencia
   y el importe que presentó. Lo hace otra persona que quien lo dejó listo (la regla de las
   dos personas, `segunda_persona`).

El programa **no presenta nada**: cada paso lo dice («Er wordt niets ingediend en niets
betaald»), la pantalla también («dient nooit iets in»), y el último paso solo deja
constancia de lo que hizo una persona. Plegadas debajo, las cifras por rubriek.

### 4.4 Los datos: Importeren y Facturen lezen

**Importeren** lee un fichero suelto, igual que `bms-agent importar` (o `importar.bat`), sin
pasar por el buzón:

1. se **elige el fichero** (como mucho 8 MB) y **su clase**: se reconoce sola por su
   contenido (las columnas de cada CSV de `config/importacion/`, un CAMT.053 o un MT940,
   una hoja de PO en YAML); si encaja en más de una, la app pide elegir entre esas; se puede
   elegir a mano;
2. se dice **el día en que se sacó** del sistema de origen (por defecto, el del fichero);
3. **Eerst proberen** (el botón de color mientras no se ha probado) lo importa de prueba
   (`simular`): **no guarda nada** y dice en palabras lo que pasaría: cuántas filas se
   leyeron, cuántas entrarían, cuántas son nuevas y cuántas cambian, las rechazadas con su
   fila y su motivo, las cuentas bancarias nuevas, los avisos que saldrían y, en un
   extracto, los pagos que casarían;
4. solo después, con el botón **Nu echt importeren** (ahora el de color; «Eerst proberen»
   pasa a secundario: **una sola acción principal** cada vez, y ninguna si con la prueba no
   entraría nada o ya se importó) y una confirmación aparte (que dice que queda con el
   nombre de quien importa y no se deshace), entra de verdad, **con
   exactamente lo que se probó** (la clase, el día de exportación y la confirmación del
   planning). Cambiar el día o la confirmación después de la prueba la borra: hay que
   volver a probar.

Si el fichero ya entró (el mismo contenido) lo dice y no lo repite. La base de prueba solo
acepta ficheros de prueba (con la marca `BMS-DEMO`), como siempre. Un planning que borra
turnos pide confirmarlo, como en la CLI. Debajo, **de cuándo es cada fuente**
(`/api/v2/fuentes`: la fecha de lo último importado, su edad y si está al día) y, plegadas,
las últimas importaciones (cuándo, qué, el fichero, quién, cuántas filas). Necesita el permiso
`importar_datos`; sin él, no sale, y tampoco la entrada Verwerken.

**Facturen lezen** no lee nada. Dice primero, en palabras normales, que **leer un PDF cuesta
dinero** (unos céntimos por factura, la API de Anthropic), que la app **no lo puede
empezar** (no tiene internet, a propósito) y que se empieza fuera de la app, con el acceso
directo del escritorio para leer facturas (**BMS Finanzas - Leer facturas**;
`leer-facturas.bat` en Docker: la app no lo nombra, porque es castellano), que antes de
leer cuenta, gratis, lo que va a costar y solo sigue con un «si». Después, de
`GET /api/v2/lectura`: cuántos documentos van, cuánto se ha gastado (en dólares, que es
como cobra el servicio, de lo medido en cada lectura), cuánto costaría la siguiente factura
(de lo medido, o una estimación holgada si aún no hay medidas; [costes.md](costes.md)) y
las últimas pasadas. **No hay ningún botón que la lance.**

### 4.5 Instellingen

Desde el paso 17, el panel de la entrada «Instellingen» de la rueda (E2-A), con las filas y
la tarjeta `.detail` de Aurora:

- **Taal**: Nederlands, English o Español (la elegida dice «In gebruik»).
- **Thema**: Donker (el de Aurora), Licht o Volg Windows.
- **Jouw account**: el nombre y el rol en la fila; en su tarjeta, el rol o los roles en
  palabras (Beheerder, Administratie, Alleen lezen) y **«Wat je mag doen: N»** con cada
  permiso en una frase (`GET /api/v2/yo`).
- **Systeem**, con sus filas:
  - **Bedrijf**, solo para leer: el nombre, los otros nombres, el btw-id, el KvK y las
    cuentas propias (en grupos de cuatro), tal como los usan los controles
    (`GET /api/v2/empresa`); si falta algo, la fila dice «Onvolledig», y que lo cambia quien
    administra el programa (con `empresa.bat`).
  - **Afscherming**, solo para leer (`GET /api/v2/aislamiento`): que la app nunca tiene
    internet; en la instalación nativa, si la última comprobación está bien («In orde») o
    hay que mirarla («Nakijken»), y en su tarjeta cada papel (la app, el lector de PDF, la
    salida a internet, las órdenes) con su estado (en orden, mislukt, niet gecontroleerd o te
    lang geleden gecontroleerd: `papeles[].estado`); en Docker o a mano, una frase sobre cómo
    se aísla allí.
  - **Personen**, solo para quien administra: cada una con su rol (`GET /api/v2/personas`),
    y que se gestionan fuera de la app (`persona.bat`).
  - **Back-ups**, una frase: los hace quien administra el programa (`copia.bat`), en el
    disco externo cifrado, y se comprueba cada copia.
- **Uitloggen**, al pie.

### 4.6 Alertas y estados

El dueño eligió cómo se ven las alertas («Así quiero las alertas»): su componente
**Status**, una pastilla redondeada y tintada con un punto de color y, siempre, su texto.
Todo estado de la app (prioridades, pagos, controles, avisos, la calidad de un campo, las
cuentas del banco, el aislamiento, la frescura de los datos, el BTW, las PO, las
importaciones y la marca de prueba de la cabecera) sale con esa pastilla; las etiquetas,
los colores sueltos y los puntos de antes se quitaron.

- **Dónde vive.** El componente del dueño está en `frontend/src/components/ui/status.tsx`
  (la ruta de shadcn), con su código; arriba del fichero se dice lo poco que se cambió y
  por qué (el contraste y el movimiento, abajo). Lo usa **una sola pieza**,
  `frontend/src/components/status-pill.tsx`: ahí, y solo ahí, se decide qué variante lleva
  cada estado y si su punto late. Las pantallas dicen el grupo y el valor tal como los
  manda la API (`<StatusPill group='pago' state={r.estado_pago} />`) y nunca eligen un
  color. Un valor que no se conoce sale en gris, quieto y con su texto.
- **Late solo lo que pide hacer algo ya**: una factura **bloqueada** o **urgente**, una
  cuenta del banco **por verificar** (nueva o cambiada) y el **aislamiento** que falla,
  falta o es viejo. Todo lo demás lleva el punto quieto. **Y en un solo sitio por
  pantalla** (`PingScope`, revisión del paso 15): las listas (`DataTable`), el inicio
  entero (sus tarjetas y su «Als eerste»), y las fichas de proveedores, clientes, Objects y PO van
  **quietas**; late la cabecera de la ficha de una factura bloqueada o urgente, las filas
  **Geblokkeerd** de la Werklijst (la lista donde se trabaja; las urgentes, quietas), una
  cuenta por llamar en IBAN-controles y el aislamiento. Antes latían diez pastillas a la
  vez en la Werklijst y seis en el Overzicht (hoy, el inicio). Quien pide menos movimiento en el sistema
  (`prefers-reduced-motion`) no ve latir nada.
- **Una pastilla de color por fila** en Inkoopfacturen y Verkoopfacturen: la prioridad. El pago y el
  control van en texto gris debajo («Openstaand · Controle nodig»), y lo vencido lo dicen
  el vencimiento («65 dagen te laat», desde el paso 16) y «Waarom»; antes eran tres pastillas por fila (49 en una pantalla).
- **Cada pastilla dice una cosa, y la misma cosa tiene un solo color.** La prioridad dice
  cuánto corre una factura; el pago, si está pagada; la gravedad de un aviso, qué hace con
  la factura. Por eso KT-202608 puede ser «Urgent» (naranja) con el pago «Vervallen»
  (rojo): son dos preguntas distintas. Un mismo aviso, en cambio, sale siempre en el color
  de su gravedad: también las señales de una PO junto a sus cifras (P5 «Bijna op» y su
  aviso «PO bijna op», debajo, los dos en azul).
- **Los textos** salen de los catálogos de Python (`src/bms_agent/textos/nl.json` y
  `en.json`) para lo que es del dominio, y de `frontend/src/i18n/nl.ts` y `en.ts`
  (`status`) para lo demás. Los que llevan una cifra la dicen («Nog 5 dagen», «Te oud
  (meer dan 5 werkdagen)», «Bezwaren van het systeem: 2»), y el plazo cercano dice los
  días en todas partes (el inicio, Btw y la ficha del trimestre). La gravedad de un aviso
  dice además, al pasar el ratón, qué hace con la factura (`significa` del catálogo).
- **El tema lo decide la app, no Windows.** Las clases `dark:` del componente del dueño
  valen con la clase `.dark` que la app pone en `<html>` con el tema oscuro
  (`@custom-variant dark` en `src/index.css`), nunca con `prefers-color-scheme`: con eso,
  un Windows en oscuro las aplicaría aunque la persona hubiera elegido el claro, y el texto
  de las pastillas saldría ilegible (menos de 2:1). En oscuro, el texto de cada variante es
  el tono -400 del dueño sobre su tinte; `e2e/status.spec.ts` y `e2e/themes.spec.ts` miden
  cada pastilla en los dos temas a 4,5:1 o más, también con Windows en el modo contrario.
- **No son estados** y siguen como estaban: las insignias de las vistas (son
  números), las cifras que van mal en el color de «tarde» (un importe vencido, un margen
  negativo: la cifra es el texto), los avisos de error de un formulario y el icono de
  «Niets heeft je aandacht nodig».

**El contraste, medido.** Los tonos de texto del dueño (green-600, orange-600 y blue-600
sobre su tinte del 10 %, a 12 px) no llegaban a 4,5:1 en los fondos de la app. Se midió en
Chromium, componiendo el tinte sobre cada fondo (#f7f5f0, #fbfaf7, #f2efe8, #f4f1ea,
#efece5, #ebe7df, #ffffff y la tarjeta de un aviso aceptado), y se oscureció **solo el
texto**; el tinte, el borde y el punto son los suyos.

| Variante | Texto del dueño | Texto ahora | Contraste ahora (mín.–máx.) |
| --- | --- | --- | --- |
| `default` | `text-muted-foreground` sobre `bg-muted` | el mismo | 5,73:1 |
| `success` | green-600: 2,40–2,93 | green-800 (#016630) | 5,32–6,49:1 |
| `warning` | orange-600: 2,64–3,22 | orange-800 (#9f2d00) | 5,43–6,62:1 |
| `info` | blue-600: 3,84–4,66 | blue-700 (#1447e6) | 5,00–6,07:1 |
| `error` | `--destructive` (#9b2c1c) | el mismo | 5,21–6,39:1 |

green-700 y orange-700 tampoco llegaban (3,69:1 y 3,85:1 en el peor fondo). El punto no
lleva texto: el estado lo dice siempre la etiqueta. Las pruebas en el navegador vuelven a
medir **cada pastilla de cada pantalla** (`e2e/fixtures.ts`, `expectStatusContrast`) y
fallan con cualquier falta de contraste de axe, de cualquier grado.

**La dependencia.** El componente importa el `Slot` de `radix-ui` (para `asChild`). Se fijó
`radix-ui` **1.6.7** (publicada el 24 jul 2026; la 1.7.0 salió el 5 oct, a menos de catorce
días): es la versión cuyos `@radix-ui/*` son exactamente los que ya estaban en
`package-lock.json` (`react-slot` 1.3.3, `react-primitive` 2.1.10, `react-dialog`
1.1.23…), así que no duplica ninguno, y lo construido no crece (el `vendor`, en gzip,
152.610 bytes antes y 152.488 después).

**La tabla.** Variante y latido de cada estado, con su texto en neerlandés y en inglés
(las cifras, de ejemplo: `{n}` = 2). Con * los valores que la pantalla deriva de lo que
manda la API (el plazo del BTW a 14 días o menos, la prueba de una importación con filas
rechazadas o avisos, las señales de una PO de sus avisos abiertos, un IBAN visto solo en
una factura…) o que no son del dominio. Los grupos `btw_config` y `empresa` no estaban en
la lista del dueño: van con la misma lógica (lo que falta confirmar avisa en naranja, lo
completo en verde, nada late).

| Grupo | Valor | NL | EN | Variante | Late | Dónde |
| --- | --- | --- | --- | --- | --- | --- |
| `prioridad` | `bloqueada` | Geblokkeerd | Blocked | error | **sí** (cabecera de la ficha de una factura; filas de la Werklijst) | Start, Werklijst, Inkoopfacturen, Verkoopfacturen, Uitzonderingen, las listas de relaciones, Objecten e Inkooporders, y cada ficha |
|  | `urgente` | Urgent | Urgent | warning | **sí** (solo la cabecera de la ficha de una factura) |  |
|  | `atencion` | Aandacht | Attention | info | no |  |
|  | `normal` | Normaal | Normal | default | no |  |
| `veredicto` | `limpia` | Geen bezwaren van het systeem | No system objections | success | no | Ficha de factura, junto a «Wat aandacht nodig heeft» (nunca «aprobada») |
|  | `limpia_sin_datos` | Geen bezwaren in wat is gecontroleerd; controles zonder gegevens: 3 | No objections in what was checked; checks without data: 3 | success | no |  |
|  | `objeciones` | Bezwaren van het systeem: 2 | System objections: 2 | warning | no |  |
|  | `campos` | Velden te verifiëren: 2 | Fields to verify: 2 | warning | no |  |
|  | `aceptadas` | Door een medewerker geaccepteerd: 2 | Accepted by a person: 2 | default | no |  |
| `severidad` | `bloqueo` | Blokkeert de factuur | Blocks the invoice | error | no | Cada aviso de una ficha (factura, proveedor, cliente, PO); al pasar el ratón, qué hace |
|  | `retencion` | Wacht op controle | Waits for a check | warning | no |  |
|  | `aviso` | Alleen een waarschuwing | Warning only | info | no |  |
| `hallazgo` | `abierto` | Open | Open | warning | no | Un aviso que ya no está abierto (aceptado, ya no se ve, cerrado) |
|  | `desaparecido` | Niet meer gezien, nog niet gesloten | No longer seen, not closed | info | no |  |
|  | `aceptado` | Geaccepteerd | Accepted | default | no |  |
|  | `cerrado` | Gesloten | Closed | success | no |  |
|  | `resuelto` | Opgelost | Resolved | success | no |  |
| `pago` | `vencida` | Vervallen | Overdue | error | no | La ficha de una factura y las facturas de una ficha, Start (Vervallen); en Inkoopfacturen y Verkoopfacturen, en texto gris |
|  | `pendiente` | Openstaand | Outstanding | default | no |  |
|  | `pagada` | Betaald | Paid | success | no |  |
|  | `anulada` | Geannuleerd | Cancelled | default | no |  |
|  | `acreditada` | Gecrediteerd | Credited | default | no |  |
| `aplicacion` | `propuesta` | Voorgesteld | Suggested | warning | no | Betalingen, en la ficha de una factura (paso 16) |
|  | `confirmada` | Bevestigd | Confirmed | success | no |  |
|  | `retirada` | Ingetrokken | Withdrawn | default | no |  |
| `revision` | `necesita_revision` | Controle nodig | Needs review | warning | no | Ficha de factura; en Inkoopfacturen y Verkoopfacturen, en texto gris |
|  | `sin_revisar` | Niet gecontroleerd | Unreviewed | default | no |  |
|  | `revisada` | Gecontroleerd | Reviewed | success | no |  |
| `excepcion` | `abierta` | Open | Open | warning | no | Uitzonderingen, ficha de factura (Afronden) |
|  | `asignada` | Toegewezen | Assigned | info | no |  |
|  | `esperando_externo` | Wacht op derden | Waiting on others | info | no |  |
|  | `resuelta` | Opgelost | Resolved | success | no |  |
| `calidad` | `faltante` | Ontbreekt | Missing | error | no | Ficha de factura, Velden |
|  | `dudoso` | Onzeker | Uncertain | warning | no |  |
|  | `discrepancia` | Verschil | Discrepancy | warning | no |  |
|  | `anomalia` | Afwijking | Anomaly | info | no |  |
|  | `verificado` | Geverifieerd | Verified | success | no |  |
| `cuenta` | `registrada` | Geregistreerd, niet geverifieerd | Registered, not verified | warning | **sí** | IBAN-controles, ficha de proveedor (Bankrekeningen) |
|  | `heredada` | Overgenomen, niet bevestigd | Inherited, not confirmed | warning | no |  |
|  | `verificada` | Telefonisch geverifieerd | Verified by phone | success | no | (con un F2 abierto, «Wat nog moet»: ponerla en Exact) |
|  | `atestada` | Bevestigd | Confirmed | success | no |  |
|  | `rechazada` | Afgewezen | Rejected | error | no |  |
| `iban_control` | `por_verificar` | Te verifiëren | To verify | warning | **sí** | IBAN-controles * |
|  | `sin_telefono` | Geen telefoonnummer in de stamgegevens | No phone number in the master data | error | no |  |
| `iban_tecleado` | `coincide` | Hetzelfde als het gevonden IBAN | Same as the IBAN found | success | no | IBAN-controles, diálogo «Telefonisch bevestigen» * |
|  | `difiere` | Anders dan het gevonden IBAN | Different from the IBAN found | error | no |  |
| `relacion` | `propuesta` | Voorgesteld | Suggested | warning | no | Ficha de factura, Koppelingen |
|  | `confirmada` | Bevestigd | Confirmed | success | no |  |
|  | `rechazada` | Afgewezen | Rejected | default | no |  |
| `turno` | `planificado` | Gepland | Planned | default | no | Ficha de factura, Planning |
|  | `realizado` | Gewerkt | Worked | info | no |  |
|  | `validado` | Gevalideerd | Validated | success | no |  |
|  | `cancelado` | Geannuleerd | Cancelled | default | no |  |
| `aislamiento` | `correcto` | Afscherming in orde | Shielding OK | success | no | Instellingen, Afscherming (`papeles[].estado`, nuevo en 2.1) |
|  | `falla` | Afscherming mislukt | Shielding failed | error | **sí** |  |
|  | `sin_comprobar` | Afscherming niet gecontroleerd | Shielding not checked | error | **sí** |  |
|  | `caducada` | Controle te oud | Check too old | error | **sí** |  |
| `fuente` | `al_dia` | Vers genoeg | Fresh enough | success | no | Importeren (frescura) y Start (cuando la stand no es de hoy) * |
|  | `caducada` | Te oud (meer dan 2) | Too old (more than 2) | warning | no |  |
|  | `sin_limite` | Geen termijn | No time limit | default | no |  |
| `btw` | `abierto` | Open | Open | default | no | Btw, ficha del trimestre, Start (el plazo: *) |
|  | `listo_revision` | Klaar voor controle | Ready for review | info | no |  |
|  | `presentado` | Aangegeven (door een medewerker vastgelegd) | Filed (recorded by a person) | success | no |  |
|  | `plazo_cerca` | Nog 2 dagen | 2 days left | warning | no |  |
|  | `plazo_vencido` | Aangifte te laat | Return overdue | error | no | También en el inicio, con los trimestres, aunque el próximo plazo ya sea el del trimestre siguiente |
| `btw_config` | `confirmada` | Bevestigd met de adviseur | Confirmed with the adviser | success | no | Btw y ficha del trimestre * |
|  | `sin_confirmar` | Niet bevestigd | Not confirmed | warning | no |  |
| `empresa` | `completa` | Compleet | Complete | success | no | Instellingen, Het bedrijf * |
|  | `incompleta` | Niet compleet | Not complete | warning | no |  |
| `po` | `activa` | Actief | Active | default | no | Inkooporders (solo «cerrada») |
|  | `cerrada` | Gesloten | Closed | default | no |  |
|  | `caducada` | Verlopen | Expired | default | no |  |
| `po_senal` | `P5` | Bijna op | Nearly used up | info | no | Ficha de PO, junto a Over y Verwachting *; el color de la gravedad de su aviso (avisa: info; retiene: warning) |
|  | `P7` | Verloopt bijna | Expires soon | info | no |  |
|  | `P8` | Gepland werk te hoog | Planned work too high | info | no |  |
|  | `P9` | Eerder op | Runs out early | info | no |  |
|  | `P10` | Meer dan de PO-waarde | More than the PO value | warning | no |  |
|  | `P4` | Boven het restant | Above what is left | warning | no |  |
|  | `P6` | Op, nog gefactureerd | Used up, still invoiced | warning | no |  |
| `importacion` | `en_curso` | Bezig | In progress | info | no | Importeren (después de importar, y la historia) |
|  | `aceptada` | Ingelezen | Imported | success | no |  |
|  | `parcial` | Deels ingelezen | Partly imported | warning | no |  |
|  | `rechazada` | Geweigerd | Rejected | error | no |  |
| `importar_prueba` | `ok` | In orde | OK | success | no | Importeren (la prueba) * |
|  | `avisos` | Met waarschuwingen | With warnings | warning | no |  |
|  | `errores` | Met fouten | With errors | error | no |  |
| `lectura` | `en_curso` | Bezig | Running | info | no | Ninguna todavía (la API no dice el estado de una pasada) * |
|  | `terminada` | Klaar | Done | success | no |  |
|  | `con_errores` | Met fouten | With errors | error | no |  |
| `datos_prueba` | `demo` | Testgegevens | Test data | warning | no | Cabecera, con la base de prueba * |

Lo mismo que en el fichero de diseño del dueño (que se hizo sobre las pantallas del
trabajo diario): la variante y el latido de cada estado son los mismos, salvo tres cosas
de la revisión del paso 15: el latido va en un solo sitio por pantalla (arriba), en las
listas de facturas el pago y el control van en texto, y las señales de una PO toman el
color de la gravedad de su aviso (el dueño las había pedido naranja, y en rojo «por encima
de su valor»: el mismo aviso salía así en dos colores en la misma ficha). Las señales
llevan un texto corto (van entre las cifras de su ficha; el nombre entero de la regla está
en sus avisos, justo debajo), y se añadieron `btw_config` y `empresa`.

### 4.7 Documentos

El archivo de Aurora tal como lo diseñó el dueño (revisión §2 y §8.5), con los datos de
verdad del motor: nada inventado, nada guardado en el navegador y ningún botón que cree,
cambie o borre un documento. Lo construyen `screens/documents.tsx` (lo que se lee y adónde
lleva cada clic), `screens/documents-model.ts` (el orden, los tipos, el árbol y de dónde sale
«pagada», sin React, con sus pruebas) y las piezas de `src/aurora/documents/`.

- **La cabecera de Aurora**: el orbe (quieto en reposo; lleva al inicio), «Je financiële
  archief · Your financial archive · Tu archivo financiero», el título (Documenten, o
  «Documenten van …» dentro de una carpeta) y su frase. Las migas y «Terug» son las de la
  app (§4); las del prototipo no se montan.
- **Una carpeta de cristal por cliente y por proveedor** (`GET /api/v2/clientes` y
  `/proveedores`), primero lo que pide atención: **lo vencido** (más, antes), **luego lo
  pendiente** (más, antes) y, a igualdad, el orden de la API (el de la prioridad). Cada una
  dice de quién es (Klant, Leverancier), su puesto (01, 02…), el nombre y cuántos documentos
  tiene; encima, la pastilla de la prioridad **solo si pide algo** (Geblokkeerd, Urgent,
  Aandacht); debajo, lo pendiente («€ 4.412,28 openstaand» o «Niets openstaand») y «Kaart
  openen». Salen **las doce primeras** y «Alle N mappen tonen»; la carpeta abierta se ve
  siempre, aunque esté más abajo.
- **Pestañas Alle / Klanten / Leveranciers**, con cuántas hay en cada una, y **el buscador de
  carpetas** (nombre o código de Exact, sin mayúsculas ni acentos), que en el prototipo
  estaba en el código y no salía. La pista de los 12 s del prototipo («¿Estás buscando algo
  en especial?», que cambiaba el título) es ahora su texto, una vez y quieto: «Zoek je iets
  in het bijzonder? Naam of code». Sin coincidencias: «Die map vinden we niet» y «Zoekopdracht
  wissen».
- **El árbol «Verkennen»**, a la izquierda: Start; Documenten con Klanten y Leveranciers;
  cada carpeta con su cuenta y, al abrirla en el árbol, sus documentos, que **se leen
  entonces** (por partes: hasta ese momento dice «Laden…»). Se maneja entero con el teclado
  (el patrón *tree* de WAI-ARIA): flechas arriba y abajo; derecha abre o baja un nivel;
  izquierda cierra o sube; Home y End; la primera letra de un nombre; Intro o espacio. Un
  grupo vuelve a la rejilla con esa pestaña; una carpeta la abre; un documento abre su
  carpeta y su vista previa; Start, el inicio. El camino hasta lo que se ve queda abierto,
  como en Aurora. Los nombres largos se cortan y se leen enteros al pasar el ratón.
- **La carpeta abierta** (la ficha `client-documents` o `provider-documents`: «Documenten ›
  Nombre», con «Terug»): la carpeta de cristal se abre con el abanico de sus cuatro
  documentos más recientes (la hoja de delante, la más nueva) y, **arriba**, la ficha de solo
  lectura con sus documentos al lado. En el prototipo la ficha quedaba debajo de la rejilla y
  había que desplazar; en el móvil va justo debajo de la cabecera, antes del árbol. Otra
  carpeta de la rejilla la sustituye (las migas no crecen); cerrar la de cristal vuelve a la
  rejilla. Al pasar el ratón por una carpeta cerrada, o al llegar a ella con el teclado, se
  leen sus documentos y sus hojas asoman.
- **La ficha** (`GET /api/v2/clientes/N` o `/proveedores/N`, con lo del contrato 2.2):
  código de Exact, número de IVA (BTW), número de KvK, plazo de pago, lo pendiente con
  cuántas facturas abiertas, lo vencido, **cómo paga** («Gemiddeld na 25 dagen, nooit te
  laat», de `plazo_de_pago`; de un proveedor, «Hoe wij betalen»), **la prioridad con su
  porqué** (el hallazgo más urgente en palabras normales, o lo vencido), la persona de
  contacto y el correo de facturación si el maestro los tiene (el teléfono de un contacto no
  sale: no es el de verificar una cuenta). De un **proveedor**, además, **cada cuenta del
  registro con su estado** (la pastilla de §4.6) y **el teléfono de verificación de los
  maestros**, solo para mirar, con «Naar IBAN-controles»: una cuenta se verifica allí, por
  teléfono a ese número, nunca desde aquí ni con un IBAN de un documento. De un **cliente**,
  sus Objects y sus PO (cada uno abre su ficha dentro de Documenten) y lo que falta por
  facturar. «Hele kaart openen» lleva a la ficha de la relación en su sección (Te ontvangen
  › Klanten, Te betalen › Leveranciers).
- **Los documentos de la carpeta** (`GET /api/v2/clientes/N/documentos` o
  `/proveedores/N/documentos`): lo que el sistema ya enlaza a la relación (decisión 7 de la
  revisión: los originales de sus facturas y abonos, los justificantes de sus pagos
  apuntados y las hojas de sus PO y de sus cambios; los contratos, más adelante), el más
  reciente primero. Cada fila: el tipo y el número, la fecha, el importe, la pastilla del
  pago y «1 van 2» cuando dos facturas comparten número. **El filtro de tipo** sale con dos
  tipos o más, y solo con los que hay en la carpeta, cada uno con cuántos. Los tipos que
  conoce el archivo: Inkoopfactuur, Verkoopfactuur, Creditnota (de un proveedor o a un
  cliente), Selfbilling-factuur (TRNSPRNT), Betaalbewijs, Inkooporderblad, Wijziging van een
  inkooporder y Bankafschrift; la autofactura y el extracto aún no los enlaza el motor a
  ninguna relación (el extracto es de la empresa: está en Importeren), así que hoy no salen.
  La fila abre la vista previa; a su lado, **la descarga del original**. Una carpeta sin
  documentos lo dice, con la suricata (en la base de prueba, los clientes: sus ventas llegan
  de Exact sin el PDF).
- **La vista previa** (un `<dialog>` nativo): la hoja clara de Aurora, **dibujada desde el
  registro**, no desde el PDF (la CSP no deja marcos, y un PDF de terceros no se abre dentro
  de la app), clara en los dos temas. De una factura o un abono (`GET /api/v2/facturas/N`):
  número, relación, fecha, vencimiento, base, IVA, total, lo pendiente, **el estado del pago
  con su fuente** («Betaald volgens de bank op 22-08-2026», «volgens Exact», «met de hand als
  betaald genoteerd op …; de bank laat het nog niet zien», con el aviso K3 si está abierto:
  manda el banco, luego Exact, luego lo apuntado a mano), cada pago (fecha, importe, fuente y
  estado), los avisos abiertos por su nombre y el fichero (nombre, tamaño, cuándo llegó). De
  un justificante, el pago y su factura; de una hoja de PO, su número, fecha y valor. Abajo,
  siempre a la vista: **«Origineel downloaden»** (`GET /api/v2/documentos/N/original` con
  `fetch` y el token; cada descarga queda en la auditoría como `documento_abierto`; lo que
  nunca se guardó lo dice) y «Factuur openen» o «Inkooporder openen» (dentro de Documenten,
  con sus migas; «Terug» vuelve a la carpeta). Se cierra con la X, Escape o un clic fuera, y
  el foco vuelve a lo que la abrió (la fila, la hoja del abanico o el árbol).
- **Vacíos y errores.** Sin clientes ni proveedores, la suricata y «Er zijn nog geen klanten
  of leveranciers»; una carpeta cuyos documentos no se pudieron leer lo dice con su
  «Opnieuw proberen», y la ficha igual; en el árbol, «Niet gelukt».
- **Lo que no hay**: «Agregar muestra», «Descargar muestra TXT», la marca «MUESTRA», los
  datos de demostración en pesos, las carpetas guardadas en el navegador, el «+» y el menú
  «…» de cada carpeta.
- **Lo que se recuerda**: la pestaña, la búsqueda, «Ver todas» y lo abierto del árbol,
  mientras la app está abierta (`lib/view-memory.ts`, en memoria); los documentos ya leídos,
  en la memoria de la sesión (se olvidan al salir y se vuelven a leer después de una orden).
  Nada va a `localStorage`.
- Los nombres de empresas, números, IBAN, teléfonos, correos y ficheros vienen de los datos:
  se pintan como texto (`data-proper-name`).

### 4.8 Zoeken: la búsqueda de Aurora

Desde el paso 17, la búsqueda es la de Aurora (E5, `src/aurora/search/`, su
`SearchWorkspace` con su hoja tal cual) sobre la del motor (`GET /api/v2/buscar`). La de
filtros del paso 16 (una pantalla con campos de fecha e importe) se fue.

- **Se llega** por la entrada «Zoeken» de la rueda y por «Zoeken met filters» en una
  respuesta de la conversación, con lo escrito. El saludo pasa a «Wat zocht je?» y la rueda
  no está. El orbe vuelve al inicio.
- **La caja** busca por número o nombre (`texto`) al pulsar Intro; mientras, «Even denken…»
  con el orbe de partículas, como mucho lo que espera Aurora (1,5 s).
- **«Filters»**, con cuántos hay puestos: el cliente o el proveedor (`cliente_id`,
  `proveedor_id`, en el desplegable de Aurora con su buscador), el tipo (factura o nota de
  crédito, `tipo`), el día de la factura (el calendario de Aurora, `fecha_desde` y
  `fecha_hasta`) y el importe sin IVA en euros (el deslizador de Aurora, `importe_min` e
  `importe_max`). Cada filtro, una pastilla con su X; **«Filters wissen»** los quita (lo
  escrito se queda). Lo que llega de un panel (B2: «Vervallen», un tramo) sale en su pastilla.
- **Los resultados**, los 50 primeros por fecha: número, empresa, de cliente o de proveedor,
  fecha e importe. Un resultado abre su factura en su lista con el vuelo. Sin nada que
  encaje, «Niets gevonden» y **«Opnieuw beginnen»**, que lo quita todo.

## 5. Neerlandés, inglés y castellano

Por defecto, **neerlandés**; se cambia en la entrada (debajo del orbe) y en Instellingen ›
Taal (cada opción lleva el nombre del idioma en ese idioma: Nederlands, English,
Español). Cada persona tiene el suyo (se guarda con su id y el entorno); la
entrada sale en el último usado en ese ordenador. El castellano llegó en el paso 16.

- **Importes, horas y fechas siempre en notación neerlandesa**, también en inglés y en
  castellano: `€ 36.270,36`, `€ −24,76`, `78,5 u` / `78,5 h`; en tablas `16-10-2026`, en una
  frase `16 okt 2026` / `16 Oct 2026` / `16 oct 2026`. Solo euros. Entre el euro y la cifra, y antes de `%`, va un espacio
  que no se parte (U+00A0): el euro nunca se queda al final de una línea sin su importe
  (igual en las plantillas de Python y de TypeScript). Los importes se escriben desde los céntimos enteros de
  la API (`*_cent`) y las horas desde las milésimas (`*_mil`) con aritmética de
  enteros: ni un céntimo se pierde por redondeo.
- **Los textos de la app** (menús, títulos, botones, avisos) están en
  `frontend/src/i18n/nl.ts`, `en.ts` y `es.ts`; el tipo (`Messages`, la forma de `nl.ts`)
  obliga a que los tres tengan las mismas claves, e `i18n.test.ts` lo vuelve a comprobar
  (las mismas claves, los mismos huecos `{n}` y ningún texto vacío).
- **Una cifra con su palabra**: «1 factuur», «2 facturen». En los tres idiomas solo el 1 va
  en singular (el 0 va en plural). Cada texto con `{n}` tiene su singular en `<clave>One`
  (o, si nunca sale con un 1, `i18n.test.ts` dice por qué), y la pantalla que lee uno lee
  también el otro (`scripts/singular.test.mjs`). Las palabras que se repiten (días, días
  laborables, veces, facturas, clientes y proveedores) están en `counts` y se escriben con
  `countText(t, 'days', n)` (`i18n/index.tsx`); un texto con dos cifras junta dos: «openstaand in
  2 facturen bij 1 klant» (la puerta del paso 16 vio «bij 1 klanten» en el inicio).
- **Los textos del dominio** (cada regla, qué quiere decir y qué hacer; estados,
  prioridades, campos, fuentes, órdenes) salen de los catálogos de Python
  `src/bms_agent/textos/nl.json`, `en.json` y `es.json`, que la app importa al construirse, para
  que la CLI, la auditoría y la app digan lo mismo. Lo que la API manda en castellano
  (`titulo`, `detalle`, `etiqueta`, `fuente_texto`, `nota`, `motivos`) no se enseña:
  queda para la CLI y la auditoría. Solo `frontend/src/i18n/domain.ts` los importa, y
  los tres ficheros entran en la huella de `web/fuente.json`.
- **Cada idioma con su catálogo.** Desde el paso 16 llegó `es.json`, y la app en castellano
  dice lo del dominio (reglas, estados, prioridades, campos, errores, el tipo de factura)
  en castellano. `DOMAIN_FALLBACK` (`frontend/src/i18n/langs.ts`) queda vacío: es donde se
  diría, si un idioma nuevo llegara antes que su catálogo, cuál usar mientras tanto (y las
  pruebas tolerarían sus restos).
- **El detalle de cada hallazgo se escribe desde sus `valores`** con las plantillas
  del catálogo (el lenguaje está en `src/bms_agent/textos/LEEME.md`).
  `frontend/src/i18n/templates.ts` es ese lenguaje en TypeScript, y
  `templates.test.ts` comprueba que da exactamente lo mismo que la referencia en Python
  en cada caso de `src/bms_agent/textos/casos.json` (los bordes del lenguaje y un
  hallazgo de cada variante de cada regla), en cada idioma de la app: neerlandés, inglés y
  castellano (la prueba falla si a `casos.json` le falta alguno).
- **Los errores** se dicen por su `codigo` estable (`conflicto`, `falta_motivo`,
  `segunda_persona`…, [integracion-web.md](integracion-web.md)), con el texto del
  catálogo (`errores`); `segunda_persona` dice además, para cada orden, cuál de los
  casos es (tú pusiste el teléfono, tú dejaste listo el trimestre, falta la firma de un
  colega). El desplegable «Technische details» enseña solo el estado HTTP y el código
  (`400 fichero_no_reconocido`), nunca la frase del servidor en castellano; los avisos del
  importador (frases en castellano) se cuentan, sin enseñarlos.
- **Ningún resto de otro idioma.** En neerlandés, ninguna palabra que solo sea inglesa o
  castellana, y así con cada idioma: `frontend/src/i18n/leftovers.ts` tiene, por idioma,
  palabras que solo existen en él, y lo miran `i18n.test.ts` en los diccionarios y las
  pruebas en el navegador en cada pantalla, en los tres idiomas, sin tolerar ninguno. En neerlandés y en inglés la app no nombra
  los `.bat` ni los accesos directos de la instalación (están en castellano, para el dueño):
  dice «de beheerder van het programma» o «de snelkoppeling op het bureaublad voor het lezen
  van facturen»; en castellano sí los nombra (`empresa.bat`, «BMS Finanzas - Leer
  facturas»), porque se llaman así. Los
  ficheros de la base de prueba se llaman en neerlandés (`exact-verkoopfacturen.csv`…). Lo
  que no es de la app va marcado con `data-proper-name` y no cuenta: el nombre de un
  fichero que eligió o importó la persona y el texto libre de un campo tal como vino del
  documento («30 dagen»).
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
  `localStorage` y solo desde `frontend/src/lib/storage.ts`: el idioma y el tema, con la
  clave `bms-app:v1:<entorno>:<persona>:…` (y `bms-app:v1:lang` y `bms-app:v1:theme`, los
  del último uso en ese ordenador, para la entrada). Lo que se lee se comprueba campo a
  campo; si el navegador no deja guardar, la app sigue igual. Desde el paso 16 no se guardan
  pestañas ni la barra plegada (al entrar se borra la clave `…:tabs` que dejó el paso 15), y
  lo que recuerda una lista al volver de una ficha (el filtro, la búsqueda, el
  desplazamiento) vive solo en la memoria de la ventana (`lib/view-memory.ts`), como el token.
- **La dirección no se toca.** La navegación es estado de la app: ni `location.hash`, ni
  `history`, ni `window.open`; nada de lo que se ve pasa a la dirección ni al historial.
- **Las órdenes** van solo por `POST /api/v2/acciones`, con la `rev` de la fila
  cuando la orden la pide y un `peticion_id` nuevo (repetirla no la aplica dos veces).
  Un `409` de concurrencia dice «Iemand anders heeft dit net gewijzigd. Laad opnieuw…».
  La app solo manda órdenes que existen en `servicios.ACCIONES`, cada botón con su
  permiso, y quien decide es siempre el servidor.
  Las descargas (el PDF original, la hoja del BTW) se piden con `fetch` y el token, y se
  guardan con un `Blob`: el token nunca va en una dirección.
- **Importar desde la app** (`POST /api/v2/importar`) es una orden más, con las mismas
  puertas: Host y Origin de la propia app (otro origen es un `403 otro_origen`), el token de
  la persona, el permiso `importar_datos` (comprobado **antes** de leer el fichero; una
  negativa queda en la auditoría) y un cuerpo JSON con su propio límite: el fichero va en
  base64 y no pasa de 8 MB (más es un `413 fichero_demasiado_grande`, sin leer el resto).
  Dentro, la misma `importar_fichero` que la CLI, todo o nada y auditada con el nombre de
  quien importa; la prueba (`simular`) deshace todo al acabar y no deja ni la importación.
  El fichero no se guarda en disco ni se abre con otro programa: el proceso de la app sigue
  sin red y sin lanzar procesos. Lo que contesta va en
  [integracion-web.md](integracion-web.md) («Importar desde la app»).
- **Lo que no hay, a propósito, en estas pantallas.** Facturen lezen no tiene botón para
  leer (la app no tiene red, y el lector cuesta dinero: lo empieza una persona con su
  acceso directo). Btw no presenta: deja el trimestre listo y anota lo que una persona ya
  presentó (un test comprueba que `btw_anotar_presentacion` solo sale en la ficha del
  trimestre). Instellingen solo cambia el idioma y el tema: la empresa, las personas y las
  copias se hacen con sus órdenes. La caja del inicio busca y no contesta (no hay ningún
  modelo detrás: el asistente local es de otro paso).

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
| `src/components/ui/` | Los componentes de shadcn (button, sheet, dialog, input, label, tooltip, context-menu, dropdown-menu, hover-card, avatar) y los dos del dueño: la navegación del paso 15 (`sidebar-with-chrome-like-tabs.tsx`, **sin montar desde el paso 16**: §4, «Lo que se quitó») y las alertas (`status.tsx`); arriba de cada uno, lo que se le cambió y por qué |
| `src/components/` | Las piezas de las pantallas: `PageHeader` y `Screen`, `SummaryCard`, `DataTable` (seis columnas como mucho, lo exige el tipo), `StatusPill` (todo estado, con el componente del dueño: §4.6), `Money`, `Hours`, `DateText`, `EmptyState`, `ErrorState` y `TechnicalDetail`, `Loading`, `HelpTip`, `Section`, `FilterChips`, `SearchBox`, `WhyCell`, `FactStrip` (las cifras de arriba de una ficha), `AttentionList` / `InvoiceAttentionList` (lo que necesita atención, agrupado por factura); `ActionDialog` / `ActionButton` (toda orden pasa por ahí; las fechas se teclean como `dd-mm-jjjj`) y `ExceptionStatus` / `ExceptionActions` |
| `src/screens/` | Las pantallas (`home`, el inicio; `work-queue`, `invoice-list`, `invoice` con `invoice-findings`, `invoice-fields` e `invoice-sections`, `exceptions` y `exception`, `iban-checks`, `party-list` y `party` para proveedores y clientes, `objects` y `object`, `purchase-orders` (las de los clientes o las de los proveedores) y `purchase-order`, `cash-flow`, `vat` y `vat-quarter`, `documents` (el archivo de Aurora: las carpetas, la de cada relación y la vista previa) y `documents-model.ts` (su orden, sus tipos y su árbol, sin React), `money-overview` (el resumen de Te ontvangen y Te betalen), `bank` (Bankontvangsten y Bankbetalingen), `invoice-payments` (los Betalingen de una factura), `payment-actions` (las tres órdenes de los pagos: el único sitio que las manda) y `money-model.ts` (qué factura cae en cada ficha y tramo como en la cartera, cuánto falta o va tarde, el orden de las empresas y de los pagos, leer un importe tecleado; sin React), `import`, `read-invoices`, `settings`); `sections.ts` (las seis entradas, sus vistas en orden y el permiso de cada vista, sin React: lo usan también las pruebas en el navegador), `registry.ts` (los iconos, las fichas y su vista, qué se ve con cada permiso, las rutas) y `render.tsx` (qué pinta cada ruta) |
| `src/shell/` | Dónde se está dentro de una pantalla de trabajo y su camino (`navigation.tsx`: `nextTrail`, puro, y `useNav`), las insignias de las filas de los paneles (`use-badges.ts`) y el nombre de cada paso de las migas (`crumbs.tsx`). El marco de antes (la cabecera, las seis en pequeño, las pastillas, Ctrl+K y el menú del nombre) se quitó en el paso 17 |
| `src/aurora/` | La app de Aurora (paso 17): `root.tsx` (las dos pantallas y el vuelo del orbe), `app.tsx` (el inicio: L0 a E5), `estado.ts` (la máquina de estados, pura), `panels.tsx` (E2), `work-screen.tsx` (el marco de una pantalla de trabajo), `assistant.ts` (lo que contesta la conversación), `chat/`, `finance/` (el resumen general), `search/` (E5), `orb/` y `thinking-orb/` (la onda y el orbe de partículas), `text-marquee.tsx` (la rueda), `composer.tsx` y `logo.tsx`; las hojas del dueño tal cual (`styles.css`, `workspace-layout.css` y las de cada pieza), `bms.css` (lo que añade BMS) y `claro.css` (el tema claro, generado). Y las piezas del paso 16 que siguen (Documentos): abajo, «Aurora dentro de la app» |
| `src/lib/` | El cliente de la API (`api.ts`, con lo que contestan las lecturas en `api-types.ts`), la sesión (`session.tsx`), las órdenes y su permiso (`actions.ts`), los formatos (`format.ts`, `field-format.ts`), el tema (`theme-choice.ts`, los valores sin React; `theme.tsx`, `ThemeProvider` y `useTheme`), el «por qué» de una fila (`why.ts`), el «1 van 2» de dos facturas con el mismo número (`twins.ts`), volver a leer tras una orden (`refresh.tsx`), lo que recuerda una vista al volver de una ficha (`view-memory.ts`, solo en memoria), lo que encuentra la conversación (`quick-search.ts`: pantallas, relaciones y facturas) y lo que se guarda (`storage.ts`) |
| `src/i18n/` | Los textos de la app (`nl.ts`, `en.ts`, `es.ts`; su tipo, `Messages`, en `messages.ts`, sin JSX, para que lo usen también las pruebas), los idiomas y `DOMAIN_FALLBACK` (`langs.ts`, sin React: lo usan también las pruebas en el navegador), el acceso a los del dominio (`domain.ts`), el lenguaje de sus plantillas (`templates.ts`), `fmt` y `countText` (una cifra con su palabra, §5) en `index.tsx`, y, para las pruebas, las listas de restos de otro idioma (`leftovers.ts`) y el glosario del castellano (`glossary.ts`) |
| `e2e/` | Las pruebas en el navegador; `nav.ts`, moverse como una persona (la rueda, los paneles, las migas, Instellingen) con los nombres de los diccionarios; `aurora/referencia.json` (las medidas del prototipo) y `aurora/contraste.json` (los grises de Aurora que no llegan a 4,5:1, apuntados); `payments.spec.ts`, Cobrar y pagar de verdad (las cifras al céntimo, confirmar, retirar, enlazar, apuntar con motivo y justificante, el 409 y quien solo mira) |

**Aurora dentro de la app (paso 16).** Aurora era un prototipo del dueño, con datos y
respuestas inventados. Se trajo a `src/aurora/` lo que la revisión quiere conservar, con
TypeScript estricto y sin nada simulado: fuera `invoice-analysis.ts` (decidía «repetida»
por el nombre del fichero), los lotes de muestra, sus dos claves de `localStorage`
(`bms-demo-parties-v1` y el borrador), las respuestas fijas del chat, «Simular
liquidación», «Agregar muestra», «Compartir», los pulgares, «Regenerar», los botones de
depuración, los paneles a los que no se llegaba y las funciones globales del cargador. Sin
NumberFlow ni date-fns (no se traen bibliotecas nuevas): los importes los escribe
`format.ts` desde los céntimos, y las fechas, nuestro formato. Cada pieza recibe sus datos
ya traducidos y avisa con callbacks (nada de enlaces `#/`); todo texto que viene de un dato
se pinta como texto.

| Pieza | Qué es | Dónde se usa |
| --- | --- | --- |
| `logo.tsx` | `BmsMark` (la marca BMS en un SVG pequeño, trazada del PNG del dueño, en `currentColor`) y `BmsLogo` (la marca con «finance») | La entrada y la cabecera |
| `orb/` | `AuroraOrb`, el orbe de colores (WebGL), y `AuroraMark`, su degradado fijo en pequeño; `orb-loop.ts` decide cuándo se mueve y a qué ritmo, sin React (`orb-loop.test.ts`) | El inicio, junto a la rueda (se mueve mientras carga o busca); `AuroraMark`, delante del logo fuera del inicio |
| `meerkat/` | `MeerkatScene`, el suricato del cargador (sus sprites en el código) | Los vacíos de Documentos (un archivo o una carpeta sin nada); el cargador de Procesar, cuando llegue |
| `documents/` | `ArchiveLayout`, `ArchiveHeading`, `ArchiveTabs`, `ArchiveSearch`, `FolderGrid`, `FolderCell`, `GlassFolder`, `TreeView`, `FolderProfile`, `FileTable`, `ArchiveEmpty`, `DocumentPreview` (un `<dialog>` nativo dibujado desde el registro, nunca desde el PDF) | Documentos (§4.7). Las migas son las de la app |
| `composer.tsx` | `WorkspaceComposer`, la caja de escribir | La caja de buscar del inicio |
| `search/` | La barra de filtros con su contador y «Filters wissen», sus pastillas con su X, los resultados y el vacío con «Opnieuw beginnen» | La búsqueda con filtros (§4.8), sobre `/api/v2/buscar`; mientras busca, el cargador de la app |
| `wheel.tsx` | `Wheel`, la rueda de navegación: el orden fijo, la distancia de cada entrada (`wheelDistance`), el paso de las flechas (`wheelStep`, que da la vuelta) y el de la rueda del ratón (`wheelScrollStep`, que no la da: en Start hacia arriba o en Btw hacia abajo el gesto es de la página), con sus pruebas (`wheel.test.ts`) | El inicio (§4) |

**Todo lo que hay en `src/aurora/` está montado.** Lo que espera a otro paso no está en
`src`: la conversación (con «Copiar» y «Detener», revisión §1b filas 19 y 20), el orbe de
partículas de «Pensando…» y «Lo importante» (`FinanceBento`), que esperan al asistente local
(§6 de la revisión), y el cargador con su progreso, la tarjeta y el resultado de Procesar
(«nuevas, ya leídas, posibles duplicados, fallidas») y su botón, que esperan a la lectura de
verdad (§8.5, pasos 3 a 7). Ya estaban pasados a TypeScript estricto, a nuestras bibliotecas
y a la CSP: cuando su paso los monte, vuelven de la historia de git, donde están tal como
quedaron (el último commit que los tiene es `756b1ba`: `git show
756b1ba:frontend/src/aurora/processing/loader-engine.ts`; `conversation/`, `finance/`,
`processing/` y `thinking-orb/`, con sus textos en la sección `aurora` de los diccionarios).
`scripts/codigo-muerto.test.mjs` (vitest) no deja que vuelva nada sin montar (§7, «Sin
código muerto»).

- **Los estilos** van bajo `.aurora-root` (cada pieza envuelve su raíz; `display: contents`,
  así no cambia la maquetación), en `@layer components` (las utilidades de Tailwind mandan)
  y con los `@keyframes` como `aurora-…`. Se sacaron una vez de las hojas del prototipo, solo
  con las reglas que usan sus componentes, y desde ahora se cambian a mano. Los colores son
  variables de `palette.css`: `--au-RRGGBB` es el color de Aurora en oscuro y su pareja en
  claro (el mismo matiz con la luminosidad invertida en OKLab), y `--au-t-…` el mismo color
  como texto, con 4,6:1 sobre una tarjeta en cada tema. Nada por debajo de 12 px.
  `src/main.tsx` importa `index.css` antes que nada, para que el orden de las capas sea el
  de Tailwind.
- **El orbe**, con las reglas de la revisión: quieto en reposo (dibuja **una** imagen y no
  pide ningún cuadro más); se mueve solo con `active` (el asistente trabaja) y como mucho a
  30 imágenes por segundo; nunca con la ventana oculta, fuera de pantalla
  (IntersectionObserver) ni con «menos movimiento»; **uno por pantalla** (`orbRegistry`:
  otro que llegue a la vez sale como el degradado fijo); y sin WebGL, o si el contexto se
  pierde, el degradado fijo con CSS. `data-orb` (`webgl` o `fallback`) y `data-moving`
  dicen en la página lo que hace, para las pruebas. En el prototipo dibujaba 60 veces por
  segundo siempre.
- **Los textos** de las piezas están en la sección `aurora` de los tres diccionarios; cada
  uno lo lee alguna pieza (`scripts/codigo-muerto.test.mjs`).

**Por qué los componentes de shadcn están en `src/components/ui`.** Es la ruta que usan
shadcn y su CLI (`components.json`: `ui` es `@/components/ui`), y todos sus imports
la dan por hecha (`@/components/ui/button`). Tenerlos ahí separa lo reutilizable de las
pantallas y deja que un `npx shadcn add` futuro funcione sin tocar nada. Aquí se
copiaron a mano (desde aquí no se llega a ui.shadcn.com); con el registro a mano, un
componente nuevo es `npx shadcn add NOMBRE`.

**Una pantalla nueva** es su sitio en `screens/sections.ts` (la entrada y el orden; su
permiso en `VIEW_REQUIRES`), su icono en `registry.ts`, una línea en `screens/render.tsx` y
sus textos en `nl.ts`, `en.ts` y `es.ts` (título, frase y lo suyo); una ficha nueva, su
entrada en `RECORDS` de `registry.ts` con la vista donde vive. Una fila abre una ficha con
`useNav().open(recordRoute('invoice', id))` (dentro de la sección en la que se está; desde
fuera, `openFrom`), y la ficha pone su título, el de las migas, con `setTitle(navKey, …)`. Una lectura usa
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

**Lo que lee Tailwind.** `src/index.css` le quita la detección automática
(`@import "tailwindcss" source(none)`) y le da solo `src` (sin las pruebas) e `index.html`:
lo que cubre la huella de `fuente.json`. Sin eso leía todo `frontend/` (las pruebas, `e2e/`,
los scripts) y una clase escrita en una prueba cambiaba el CSS sin cambiar la huella.
`scripts/tailwind-fuentes.mjs` saca con el escáner de Tailwind los ficheros que lee;
`fuente.mjs` no construye ni da por buena la huella si alguno no está en
`build-inputs.json`, y `scripts/tailwind-fuentes.test.mjs` (vitest) lo comprueba.

**Sin código muerto** (la puerta del paso 16). `scripts/codigo-muerto.mjs` mira, sin
construir, cuatro cosas, y `scripts/codigo-muerto.test.mjs` (vitest) exige que no haya
ninguna: los ficheros de `src` que `src/main.tsx` no alcanza siguiendo sus `import` (y los
`@import` de las hojas), salvo los que se guardan a propósito y la prueba nombra (la
biblioteca de `components/ui`: la tira de pestañas del dueño con las dos piezas que solo ella
usa, y `sheet`; y lo que solo usan las pruebas, `i18n/glossary.ts` e `i18n/leftovers.ts`);
las declaraciones exportadas que nadie nombra, ni la app ni una prueba ni e2e (con el
analizador de TypeScript); las variables de `aurora/palette.css` que nadie usa; y las clases
de las hojas que ninguna pantalla pone (salvo las bandas, que las pone el servidor). Además,
cada texto de la sección `aurora` de los diccionarios lo lee alguna pieza. A mano: `node
scripts/codigo-muerto.mjs`. Lo que espera a un paso posterior no se deja en `src` sin
montar: vuelve cuando su paso lo monte (§7, «Aurora dentro de la app»).

**Las pruebas en el navegador** (`npm run e2e`) crean una base de prueba nueva en una
carpeta temporal (`scripts/crear_demo_e2e.py`, que da los tokens en JSON: Ana
Demo, administradora; Bram Demo, de administración; y Cas Consulta, de solo lectura,
que añade el script), arrancan `bms-agent serve` sobre ella en un puerto libre y entran
con un token de prueba. Se mueven como una persona (`e2e/nav.ts`, paso 17): «Druk om te
navigeren», la entrada en la rueda (Tab la centra, como con el teclado), la fila de su panel
y las migas; el idioma, el tema y salir en Instellingen (después del idioma se vuelve a la
pantalla por el mismo camino). `e2e/shell.spec.ts` prueba el marco de Aurora: L0 en los tres
idiomas; E0 sin nada más; la rueda con sus ocho entradas, el clic a la primera, la rueda del
ratón, las flechas, Tab, el dedo y «menos movimiento»; los paneles con su ✕, Escape y el
orbe; el vuelo a una pantalla de trabajo y de vuelta; cada pantalla de la app en los tres
idiomas; las migas y Alt+←; Instellingen y salir; recargar y la sesión que caduca; el
teclado; 1024 px y el móvil (400 × 860 y 360 × 740). `e2e/exclusividad.spec.ts` prueba la
regla del dueño (o el menú o una pantalla) en cada estado, en cada cuadro de cada transición
y en cinco anchos; `e2e/aurora-paridad.spec.ts` compara las cajas, la letra, el color y la
escala de L0, E0, E1 y E2 a 1440 y 400 px con las medidas del prototipo
(`e2e/aurora/referencia.json`, ±4 px) y los tiempos del orbe (abrir la rueda y el vuelo, por
los cruces del 5, 50 y 95 %); `e2e/conversacion.spec.ts` el resumen general en los tres
idiomas (lo pendiente de la cartera al céntimo, «saldos pendientes», a 1440 y a 400 px);
`e2e/search.spec.ts` la búsqueda de Aurora; `e2e/clicks.spec.ts` cuenta los clics de cada
tarea de la tabla de la revisión (§4, «Los clics»); `e2e/documents.spec.ts` el archivo
de Documentos sobre la base de prueba, cada interacción de sus filas de la revisión (§1b, 36
a 48): las carpetas en su orden contra la API, las pestañas, el buscador y su vacío, las hojas
que asoman al pasar el ratón, la carpeta de cristal, «Kaart openen» y «Kaart bekijken», la
ficha de verdad (IBAN y teléfono solo para mirar, «Naar IBAN-controles»), el filtro de tipo,
un cliente sin documentos con sus Objects y PO, la ficha completa en su sección, el orbe; la
vista previa (desde la hoja del abanico y desde la fila, cerrada con la X, Escape y un clic
fuera, el foco de vuelta, «pagada» con su fuente, el PDF de verdad al descargar desde la vista
previa y desde la fila, «Factuur openen» y «Terug»); el árbol con el teclado; las doce primeras
y «Ver todas», un archivo vacío y una carpeta que no se pudo leer (respuestas cambiadas con
`page.route`); y las capturas del archivo en los tres idiomas, en los dos temas y en el
móvil; `e2e/daily.spec.ts` las pantallas del trabajo diario con órdenes de verdad (los motivos de las bloqueadas en
los dos idiomas, aceptar un hallazgo con la segunda firma de otra persona y resolver
una excepción con las cuentas del menú cambiando, marcar como gecontroleerd, una `rev`
vieja que da el aviso de conflicto, la verificación de un IBAN con la regla de las dos
personas, y que quien solo mira no ve ningún botón) y `e2e/screens.spec.ts` las demás:
cada lista y su ficha (con sus detalles abiertos), Kasstroom, el BTW entero (reabrir,
dejar listo, bajar el werkblad y mirar que es el CSV del trimestre, la regla de las dos
personas al anotar la aangifte y anotarla con otra persona), Importeren (un fichero que no
se reconoce, la prueba de un maestro de clientes que dice «1 nieuw» sin que cambie nada en
la base, un solo botón de color en cada momento, la importación de verdad tras la
confirmación, la historia y la repetición, y el cliente nuevo en Klanten), Facturen lezen sin
botón para leer, Instellingen, quien solo mira y la app a 1024 px sin desplazamiento
horizontal. Van en orden y cambian la base, así
que comprueban cambios, no cifras sueltas. En
cada prueba: toda petición tiene que ir a `127.0.0.1` (otra se corta y la prueba falla),
ninguna violación de la CSP, ningún error en la consola, ninguna respuesta de error que la
prueba no espere, y axe sin problemas serios ni críticos (WCAG 2.1 AA); en cada pantalla,
además, ningún resto de otro idioma (`expectNoLeftovers` en `e2e/fixtures.ts`, con las
listas de `src/i18n/leftovers.ts`; no cuenta lo marcado con `data-proper-name` ni las
bandas que pone el servidor, que van en dos idiomas a propósito). Antes de medir y de cada
captura esperan a que la pantalla esté quieta (`settled`: ninguna animación con fin en
marcha y el contenido de la vista entero, sin esperas fijas). Las demás pruebas van en el
tema por defecto (el oscuro); `e2e/themes.spec.ts` recorre cada pantalla en claro en los
tres idiomas y en oscuro en castellano, las fichas en claro, cómo se elige y se guarda el
tema por persona y «Volg Windows» cambiando en vivo, y el orbe: en reposo, ningún cuadro
pedido en 3 s y menos de 0,25 s de trabajo del hilo principal en 5 s (`TaskDuration` del
protocolo de Chrome; se mide cerca de 0); se mueve solo mientras carga y se para con la
ventana oculta, fuera de pantalla o con «menos movimiento»; sin WebGL, el degradado fijo.
Dejan una captura de cada pantalla, ficha y diálogo, a 1440×900 (`<idioma>-<pantalla>.png`),
en `CAPTURAS_DIR/dark/` o `CAPTURAS_DIR/light/` según el tema que se ve (por defecto
`frontend/test-results/capturas`, que no va en git). El Python es el de `.venv` (o `BMS_PYTHON`); el navegador, el de
`PLAYWRIGHT_BROWSERS_PATH` (no se baja nada: nunca `playwright install`).

## 8. Lo que falta

En la ficha de factura quedan para la consola las órdenes menos de cada día (imputar una
línea a otro Objeto o a una PO, dividir o añadir líneas, anular o fusionar una factura,
enlazar dos a mano, subir la prioridad; los pagos ya están en la app desde el paso 16:
confirmar, retirar y apuntar uno ya hecho, §4.1), y de las fichas de relaciones lo
que no se hace cada semana: registrar, modificar, corregir o cerrar una PO a mano y sus
Objects (`registrar_po`, `modificar_po`, `corregir_po`, `cerrar_po`, `objetos_po`),
corregir un dato maestro, poner el teléfono de verificación de un proveedor, añadir un
alias o un beneficiario. Las fichas lo enseñan todo y esas órdenes siguen en `/consola` y
en la CLI. Leer los PDF se sigue empezando con su acceso directo, a propósito.

En Cobrar y pagar quedan dos cosas: subir un justificante nuevo al apuntar un pago (hoy se
elige uno que ya está en la carpeta de la empresa) y enlazar un abono a su factura (se ve en
«Wat op iemand wacht» y abre el abono; enlazarlo sigue en la consola).

Que alguien de la oficina lea los textos neerlandeses en la app y diga lo que no suena
natural, y mirar en el ordenador del dueño que Edge abre la ventana `--app`.

Del paso 16, lo que hacen los pasos siguientes sobre esta navegación: **Procesar** de
verdad (leer los PDF con la confirmación de su coste, fila 21) y, más adelante, el
asistente local detrás de la caja del inicio, que hoy busca y dice que aún no contesta. Las
demás piezas de `src/aurora/` esperan a la pantalla que las use. En Documentos, cuando el
dueño lo decida (decisión 7B de la revisión), subir contratos y otros documentos que no son
de ningún registro; y que el motor enlace a cada relación sus autofacturas de TRNSPRNT, en
cuanto se conozca el formato.
