# La app local de BMS

Paso 15 · 19 de octubre de 2026 · Paso 16 (la base de Aurora, los temas y el castellano; Documentos y Cuentas por cobrar y por pagar con datos reales; el cierre de la puerta) · Paso 17 (la app de Aurora tal cual: B1, el marco, el inicio y el menú; B2, los paneles y Documentos; B3, Procesar con la suricata, sobre la lectura de verdad) · 28 de octubre de 2026

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

**Desde el paso 17 la app es Aurora**, el prototipo del dueño, tal cual, porque lo pidió así:
«Necesito que te apegues a las animaciones y diseño de esta aplicación, no quiero que hagas algo
diferente. No pueden vivir las pantallas y el menú al mismo tiempo». Eso son dos reglas, y las dos
se comprueban en el navegador (§7):

1. **Se ve y se mueve como Aurora**: los mismos sitios, la misma letra, los mismos colores y
   espacios, las mismas transiciones con sus duraciones y sus curvas, las partículas, el orbe,
   la rueda y la suricata. Las piezas son las de su entrega del 28-10-2026, en `src/aurora/`, con
   sus hojas, sus clases y sus nombres; lo poco que se les cambia va dicho arriba de cada fichero
   (§7, «Aurora dentro de la app»).
2. **O el menú o una pantalla, nunca los dos** (§4, «La regla del dueño»). El orbe es la puerta:
   lleva del menú a una pantalla y de vuelta, con las transiciones de Aurora.

Lo que pone BMS, y casi no se ve: los **datos de verdad** de `/api/v2` en lugar de los de
demostración de Aurora (nada de negocio se guarda en el navegador); la **entrada con el código
personal**, con el aspecto de Aurora (§3); las **bandas del servidor**, la de los datos de
prueba y la del aislamiento (§2); la **política de contenido estricta**: nada de `innerHTML`,
scripts en línea ni funciones globales en `window` (§6); el **neerlandés y el inglés** además
del castellano, que es el del dueño (§5); los **euros desde céntimos enteros**; que la app **no
paga, no aprueba, no presenta el BTW ni crea facturas**; que **no tiene red ni lanza
programas**; y que el lector de los PDF sigue su orden de seguridad: salida encendida,
aislamiento comprobado, contar, el sí de una persona, leer y salida apagada (§4.5).

**Cómo se llegó aquí.** El paso 15 hizo la app con las pantallas del trabajo diario y las demás
(y la barra de pestañas del dueño). El paso 16 trajo la base de Aurora (su aspecto oscuro, el
tema claro y «Volg Windows»), el castellano, una primera rueda, y Documentos y Cuentas por
cobrar y por pagar con los datos de verdad. El paso 17 cambió todo eso por **Aurora tal cual**:
el marco, el inicio y la rueda (B1); los paneles en dos niveles y Documentos, que se llevaron
las pantallas de los pasos 15 y 16 (B2); y Procesar, con la suricata del dueño moviéndose al
ritmo de la lectura de verdad que hace el lector del escritorio (B3). Lo de cada paso, con sus
desviaciones, está en el registro ([v1/registro.md](v1/registro.md)).

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
  Procesar piden `importar_datos`: sin él, la entrada Verwerken no sale de la rueda, que
  tiene siete, ni Importeren del panel de Te ontvangen) y los botones de cada orden siguen
  su permiso.
- **Uitloggen / Log out** (al pie del panel de Instellingen) olvida el token. Si el servidor contesta `401` en cualquier momento
  (un token retirado), la app vuelve sola a la entrada y lo dice.

## 4. La app: o el menú o una pantalla

**Es la app de Aurora** (`src/aurora/`). Como en su prototipo, hay dos pantallas de raíz
(`root.tsx`): **el inicio de Aurora**, donde pasa casi todo, dentro de su espacio central (la
rueda, los paneles, la conversación, la búsqueda y Procesar), y **Documentos**, la única pantalla
de trabajo, a la que se va con el vuelo del orbe. Cada cosa que se pulsa es una acción de una
máquina de estados pura (`src/aurora/estado.ts`) que pone todo a la vez, así que nunca se ve un
estado a medias.

| Estado | Qué se ve | Cómo se llega |
| --- | --- | --- |
| **L0** · la entrada | «Welkom.», el orbe quieto de pulsar, la caja del código y el idioma | Al abrir la app, al salir o si la sesión caduca |
| **E0** · el inicio | «Welkom, Ana», «Waarmee kan ik je vandaag helpen?», el orbe, «Druk om te navigeren» y la caja | Al entrar; el orbe con un panel, una conversación o una búsqueda; «Terug naar Aurora» y la miga «Start» desde Documentos; «Terug naar start» desde Procesar |
| **E1** · la rueda | El orbe a la izquierda y la rueda de Aurora con las ocho entradas | «Druk om te navigeren» o el orbe desde E0; la ✕ de un panel |
| **E2** · un panel | El panel de Aurora (340 px) con su cifra principal y una fila por grupo; un grupo abre su vista y una fila, su tarjeta con sus órdenes; el orbe a ×0,75 (§4.1) | Una entrada con panel (Instellingen, Start, Te ontvangen, Te betalen, Btw); en la conversación, una fila que es un grupo |
| **E3** · escribiendo | La caja con lo escrito | La primera tecla (cierra la rueda, como en Aurora) |
| **E4** · la conversación | Las preguntas y respuestas; con «Geef me een overzicht», el resumen general (Finance Bento) (§4.7) | Intro en la caja |
| **E5** · la búsqueda | «Wat zocht je?», la caja de buscar, Filters y los resultados (§4.7) | La entrada «Zoeken»; «Zoeken met filters» en una respuesta; un grupo de un panel que lleva a sus facturas (E5-p) |
| **E6** · Documentos | El archivo de Aurora: el árbol, las carpetas, la ficha de la carpeta abierta y la hoja de un documento (E6-h, con sus órdenes) (§4.6) | Documenten en la rueda; «Factuur openen» de una tarjeta; una fila de una respuesta o un resultado de la búsqueda |
| **E7** · Procesar | El espacio central sin orbe, rueda ni caja: el saludo dice lo que pasa y, debajo, la tarjeta con la suricata, el plan, el botón y su nota; después las cinco etapas, el resultado o el error (§4.5) | Verwerken en la rueda; «Facturen lezen» en una respuesta de la conversación |

**La regla del dueño: o el menú o una pantalla.** La rueda solo se ve en E1. Con un panel
abierto la rueda se oculta **en todos los anchos** (en Aurora solo a 1150 px o menos; la regla
`.has-panel .navigation{display:none}` va al final de `src/aurora/styles.css`) y la entrada
activa no se mueve: la rueda escondida no manda (ni la rueda del ratón ni las flechas). La
conversación, la búsqueda, Documentos y Procesar tampoco conviven con la rueda; Procesar,
como en Aurora, tampoco con el orbe ni con la caja. La pantalla que se va se funde en 0,18 s y
mientras tanto no recibe clics. Lo comprueba `e2e/exclusividad.spec.ts` en cada estado, en cada
cuadro de cada transición y a 1440, 1151, 1150, 1024 y 400 px, y `e2e/procesar.spec.ts` en cada
estado de Procesar.

**El orbe es la puerta**, con los movimientos de Aurora. En el inicio abre la rueda y la cierra;
con un panel, la conversación o la búsqueda, vuelve al inicio. A **Documentos** se va con el
vuelo: una copia de la onda va del centro del orbe grande al pequeño de la esquina (1,05 s con
`cubic-bezier(.4,0,.15,1)`), y el pequeño, «Terug naar Aurora» o la miga «Start» vuelven con el
vuelo inverso (con «menos movimiento», sin vuelo). En **Procesar** el orbe no viaja: sus
partículas caen desde donde estaban y forman el montículo del que asoma la suricata (§4.5), y
«Terug naar start» vuelve al inicio, donde el orbe aparece otra vez. Alt+← y el botón de atrás
del ratón son la salida que se ve en cada estado: en la rueda, la cierran; en un panel, lo mismo
que Escape o su ✕ (primero lo de dentro); en la conversación, «Terug naar de werkruimte»; en la
búsqueda o con algo escrito en la caja, el orbe (al inicio); en Documentos, un paso atrás; en
Procesar, al inicio. El nombre del orbe para el lector de pantalla dice lo que hace su clic
(«Navigatie openen», «Navigatie sluiten», «Terug naar start» o «Verwerken openen»).

**El teclado.** Lo que se ve no cambia; lo que se oye y adónde va el foco, sí. Cuando un cambio
deja el foco en el aire (la entrada que abrió un panel se esconde, el panel se cierra, el orbe
entra en Procesar, se vuela a Documentos o se vuelve), el foco va a lo que se tiene delante: el
título del panel (que nombra el panel), la entrada activa de la rueda, «Terug naar start» en
Procesar, el título de Documentos o el orbe. Los anillos de foco solo se ven con el teclado: el
orbe con un aro lila en su zona de clic, «Terug naar start» en claro sobre el negro de Procesar y
la caja con su borde lila al llegar con Tab. La respuesta terminada de la conversación y cada
estado y etapa de Procesar se anuncian (un `role="status"` oculto).

**La rueda de Aurora** (`src/aurora/text-marquee.tsx`, su `TextMarquee`): una ventana de
240 px con filas de 48 px; se ven cinco entradas y la del centro es la activa (23 px, peso
650, `#eee5fa`; las demás, `#544e60`). Las ocho, en este orden: **Instellingen, Zoeken,
Documenten, Start, Te ontvangen, Te betalen, Btw y Verwerken**. Al abrirla por primera vez
en una sesión, Start está en el centro; después, la última que se usó. **Un clic en
cualquier entrada a la vista la abre a la primera.** Al apoyar el ratón pasa lo de Aurora (su
`onFocus`): la entrada pasa a ser la activa, la pista se desliza y, con Verwerken, sale el orbe
de partículas, del que Procesar toma las partículas y los sitios del título y de la escena. El
clic abre la entrada donde se apoyó aunque se suelte encima de otra (en Aurora ese clic se
perdía). Las que quedan fuera de la ventana no se pueden pulsar, como en Aurora, y se
alcanzan con un paso de la rueda del ratón (un paso por gesto, sin dar la vuelta), las
flechas, Inicio y Fin (el foco va con la entrada activa; con el foco en la rueda, Intro la abre),
Tab (centra la entrada que recibe el foco) o el dedo (un paso por gesto): Instellingen
y Btw están a un paso, Verwerken a dos. Con Verwerken en el centro, el morado de Aurora y el
orbe de partículas. Sin el permiso `importar_datos` la rueda tiene siete (sin Verwerken). La
decisión de dejar la ventana de cinco de Aurora (y no las ocho a la vista) es del dueño, que
pidió no cambiar su diseño (especificación §7, punto 10).

**Ninguna función se perdió por el camino**: cada pantalla de los pasos 15 y 16 tiene su
portador en Aurora (la tabla de la especificación §2.6; lo comprueban `src/aurora/estado.test.ts`
y las pruebas en el navegador). Las empresas, sus Objects y sus PO viven en Documentos (§4.6);
el trabajo de cada día, en los paneles y en la hoja de cada factura (§4.1 y §4.2); leer los PDF,
en Procesar (§4.5).

**Lo que se quitó** (paso 16): la barra lateral con pestañas como las de Chrome (el componente
del dueño del paso 15, `src/components/ui/sidebar-with-chrome-like-tabs.tsx`, se queda sin
montar). **En el paso 17**: la cabecera de arriba, las seis entradas en pequeño, las pastillas
de las vistas de cada entrada, Ctrl+K («Snel openen»), el menú del nombre (su idioma, tema y
salir están en Instellingen), la marca de prueba de la cabecera (la banda del servidor sigue),
la caja que buscaba sin contestar (ahora es la conversación), la búsqueda con filtros del paso
16 (ahora E5), el orbe del paso 16 (ahora la `SiriWave` de Aurora) y las fuentes IBM Plex; con
B2, **las pantallas de los pasos 15 y 16**: el inicio con sus cuatro tarjetas, las listas de
facturas, de relaciones, de Objects y de PO con sus columnas, la ficha de factura de página
entera, Kasstroom, Btw y Kwartaal, Importeren, Instellingen, los resúmenes de cobrar y pagar y
la vista del banco (lo que hacían está en los paneles, en sus tarjetas y en Documentos); y con
B3, **Facturen lezen** (la pantalla que decía cuánto costaba leer y cómo se empezaba fuera de la
app) con su marco de pantalla de trabajo (`work-screen.tsx`), que son ahora Procesar. La
dirección sigue sin cambiar y al entrar se empieza en el inicio.

**Los clics** (especificación §2.6). `e2e/clicks.spec.ts` cuenta, desde el inicio, los clics de
cada tarea de la tabla y, aparte, los pasos de la rueda (los dos suman; escribir no cuenta; el
«sí» de una orden va aparte), con la rueda como sale la primera vez en una sesión, Start en el
centro, y falla si un camino crece. Un grupo de un panel cuesta 3 (la rueda, la entrada y el
grupo); una tarjeta, 4; una orden, 5 como mucho; Procesar, dos pasos de la rueda y un clic; lo
que se busca por su número o su nombre va por la conversación (escribirlo no cuesta; abrir su
hoja, 1). Y en un grupo de más de cinco filas, la sexta y la última se alcanzan escribiendo en
su campo, sin ningún clic más. En la hoja de una factura con más de cuatro filas, lo plegado
cuesta un clic más (desplegarla): anotar un pago de VD26-306 por la caja, 4 en lugar de 3.

### 4.1 Los paneles (E2)

**Los paneles** (`src/aurora/panels.tsx` y `src/aurora/panels/`, paso 17 B2) tienen el
marco de Aurora: «WERKRUIMTE» y la ✕ (vuelve a la rueda con su entrada en el centro), el
título, su frase y la línea de los datos («Testgegevens · EUR»). **Cada panel tiene dos
niveles**, como el de Aurora:

- **En reposo**, la cifra principal de Aurora (`.balance`: lo que más importa de esa entrada,
  con su barra y su nota) y **una fila por grupo** (`.doc`: el nombre, una nota corta y, a la
  derecha, su cifra y su estado). Escape cierra lo de dentro y después el panel; el orbe vuelve
  al inicio.
- **La vista de un grupo**: el título del grupo con su cuenta (`.list-title`), **cinco filas
  como mucho** y, si hay más, el campo `.search` del panel de Aurora arriba («Zoek bedrijf of
  document…», sin mayúsculas ni acentos, sobre la lista entera) y «En nog N: typ hierboven om
  te verfijnen.»; abajo, «Terug naar …» (o Escape) vuelve al nivel de antes, al mismo sitio.
- **La tarjeta** (`.detail` de Aurora, con su ✕): una fila de una vista la abre debajo de la
  lista, con líneas cortas (qué es, cuánto, desde cuándo, por qué pide atención) y **sus
  órdenes**: la principal en `.primary`, las demás en `.outline`. Una orden con datos abre su
  formulario dentro de la tarjeta (`.order-form`, con los campos de la búsqueda de Aurora: el
  desplegable con buscador y el calendario) y pide su «sí» en `.chat-export`, una sola vez; lo
  que no se deshace lo dice ahí. Hecha, la tarjeta lo dice (`.success`) y lo de alrededor se
  vuelve a leer. Sin el permiso de una orden, la tarjeta sale igual y sin ese botón; quien solo
  mira (rol `consulta`) no ve ninguno.
- **El panel casi no se desplaza**: en reposo, en cada vista de grupo y en importar sin
  fichero, como mucho 53 px a 1440 × 900 y 213 px a 400 × 860 (lo mide
  `e2e/aurora-paridad.spec.ts`).

| Panel | En reposo | Sus grupos (cada fila, su tarjeta) |
| --- | --- | --- |
| **Instellingen** (E2-A) | Jouw account | Taal, Thema, Jouw account y Systeem (§4.8) |
| **Start** (E2-I) | Cuántas facturas piden a una persona; la barra, la parte bloqueada o urgente | **Eerst** (lo bloqueado o urgente, cinco cosas distintas como mucho; dos facturas con el mismo número en una fila); **Werklijst** (las facturas que piden a una persona, en el orden de la API; cada fila, la tarjeta de su factura); **Uitzonderingen** (las abiertas, la más urgente primero; su tarjeta: qué pasa, de qué va, su estado y quién la lleva, con Zelf oppakken, Toewijzen, Wachten op anderen y Oplossen); **IBAN te controleren** (cada cuenta nueva o cambiada; su tarjeta: el teléfono **de los datos maestros**, «Telefonisch bevestigen» en tres pasos —llamar a ese número, teclear el IBAN que dice el proveedor, quién contestó— y Afwijzen; las heredadas, Bevestigen); **Kasstroom** (las cuatro semanas: lo que entra, lo que sale y lo que queda; aparte y marcado, la estimación del planning; cada semana abre sus facturas en la búsqueda) |
| **Te ontvangen** (E2-C) | **Totaal openstaand**; la barra, la parte vencida de verdad; la nota, lo vencido y en cuántas facturas | **Te bevestigen** (cada cobro que el banco casó a medias: Bevestigen, Niet deze con motivo, Factuur openen); **Niet gekoppeld** (las líneas del banco sin factura: «Aan een factuur koppelen», sin ninguna factura elegida de antemano); **Vervallen** (abre la búsqueda con sus filtros, E5-p); **Hoe lang het al openstaat** (cada tramo de antigüedad con su importe; cada uno, sus facturas en la búsqueda); y el botón **«Een afschrift of export importeren»** (importar, §4.4) |
| **Te betalen** (E2-P) | Lo mismo, de lo que hay que pagar | Te bevestigen, Niet gekoppeld, **Deze week** (lo vencido y lo que vence hasta el domingo, sin objeciones del sistema), **Met bezwaren of geblokkeerd** (lo retenido, con su razón: no se paga hasta que se resuelve) y Hoe lang het al openstaat |
| **Btw** (E2-V) | El trimestre en curso: lo que sale a pagar o a devolver; la barra, la parte del trimestre que ya pasó; la nota, el plazo y el estado | Los tres últimos trimestres y **Eerdere**; cada trimestre, su tarjeta (§4.3). Al pie, «Werkblad van het kwartaal downloaden» |

**La tarjeta de una factura** (en cualquier vista; `src/aurora/panels/invoice-card.tsx`): el
número, la empresa, el importe y lo que queda, el vencimiento o el retraso, los pagos (tres
como mucho, con su fuente) y por qué pide atención; **«Factuur openen»** (`.primary`: su hoja en
Documentos, con el vuelo, §4.6), **«Origineel downloaden»** (`.outline`, la descarga auditada)
y, con el permiso `marcar_pagada` y algo pendiente, **«Betaling vastleggen»** (su formulario en
la tarjeta). Las demás órdenes de una factura están en su hoja.

### 4.2 El trabajo diario

Todo sale de `/api/v2` y cada orden es una de `servicios.ACCIONES` por
`POST /api/v2/acciones` (`src/aurora/orders.tsx`). Un botón solo sale si la persona tiene el
permiso de esa orden (`frontend/src/lib/actions.ts`, que un test compara con
`servicios.ACCIONES`). La orden dice en palabras normales qué va a pasar (la frase de
confirmación del catálogo en lo que mueve dinero, BTW o el banco), **una sola vez**, y pide lo
que hace falta (un motivo, una fecha). Después se vuelven a leer la tarjeta, la hoja, las
listas y el panel, sin que nada salte a «Laden…».

| Dónde | Qué hay | Órdenes |
| --- | --- | --- |
| **Start › Eerst y Werklijst** | Las facturas que piden a una persona (una prioridad que no es normal, un hallazgo pendiente, una excepción abierta o campos por verificar): la empresa, el número («1 van 2» si otra lo comparte), el importe y la prioridad en el texto de la fila | La tarjeta de la factura (arriba); su hoja, con todo lo demás |
| **La hoja de una factura** (E6-h, en Documentos) | El papel de Aurora dibujado desde el registro (número, empresa, fecha, vencimiento, base, IVA, total, lo que queda y el pago **siempre con su fuente**: «volgens de bank», «volgens Exact» o «met de hand … door Ana», con K3 si el banco no lo trae), «Origineel downloaden» y **una sola tabla, «Wat je kunt doen»**: una fila por cosa pendiente, la más urgente primero (cada hallazgo con su nombre, cada pago propuesto, cada relación propuesta, la excepción abierta y la revisión si falta) y siempre «Gelezen gegevens» y «Betalingen, notities en geschiedenis». Con más de cuatro filas, la tabla se abre **plegada**: las tres más urgentes y, en la cuarta línea, «En nog N regels» (con «· K vragen aandacht» si detrás hay hallazgos o la excepción); «Minder tonen» la vuelve a plegar. Cada fila, dos líneas (qué es y su estado); al pulsarla, su tarjeta se abre debajo de la tabla y el diálogo se desplaza lo justo para enseñarla | En la tarjeta de un hallazgo: aceptarlo con un motivo de 10 caracteres o más (`anular_hallazgo`, con la segunda firma de otra persona cuando la pide), dar la segunda firma (`firmar_anulacion`), cerrar uno que ya no se ve (`cerrar_hallazgo`) y verificar o cambiar los campos a los que apunta (antes de guardar se ve «Nu → Nieuw»); en la de la revisión, `marcar_revisada` (con la huella de lo que se vio) o `devolver_factura`; en la de la excepción, las suyas; en la de un pago propuesto, Bevestigen y Niet deze; en la de una relación, Bevestigen y Afwijzen, con motivo; en «Gelezen gegevens», cada campo con su fuente y su calidad, y verificar, cambiar o deshacer; en «Betalingen, notities en geschiedenis», cada pago (Intrekken con motivo en lo que no es de Exact), **Betaling vastleggen**, «Notitie toevoegen», «Uitzondering openen» y la historia en palabras normales |
| **Start › Uitzonderingen** | Las abiertas, la más urgente primero: qué pasa (el hallazgo más urgente, en palabras normales), de qué va y quién la lleva | Zelf oppakken, Toewijzen, Wachten op anderen (a quién y hasta cuándo), Oplossen (cómo acabó y qué se hizo); «Factuur openen» |
| **Start › IBAN te controleren** | Cada cuenta nueva o cambiada (los avisos F de las facturas y las del registro sin verificar): de qué proveedor es, el IBAN encontrado, **lo que falta en una frase** cuando ya se verificó por teléfono, en qué factura y el teléfono **de los datos maestros**; las heredadas sin confirmar, aparte | Verificar por teléfono (`verificar_iban`): llamar a ese número, nunca a uno de la factura; el IBAN que lee el proveedor **se teclea** (el campo va vacío) y la tarjeta dice si es el mismo que el encontrado; quién contestó y una nota. Rechazar (`rechazar_iban`). Confirmar las heredadas (`atestar_iban`) |

La **regla de las dos personas** la hace cumplir el servidor (código `segunda_persona`), y la
tarjeta dice cuál de los casos es. Cuando un aviso pide la segunda firma y aún no la hay, la
tarjeta **no deja mandar** la aceptación: lo dice y pide a un colega «Tweede handtekening
geven»; con la firma ya dada, dice de quién es y hasta cuándo vale. En la base de prueba se ve
dos veces: Ana puso los teléfonos de los proveedores, así que no puede verificar con ellos una
cuenta (lo hace Bram), y aceptar el número de factura repetido (B2, que bloquea) pide que otra
persona dé antes la segunda firma.

**Cobrar y pagar** (paso 16; paso 17 B2: en los paneles E2-C y E2-P). Las cifras salen de
`GET /api/v2/cartera`, la misma lectura en el panel, en el resumen general de la conversación
y en cada carpeta de Documentos: **cuadran al céntimo** (lo comprueba
`e2e/cartera-partes.spec.ts`). **Una empresa dice el mismo «Openstaand» en todas partes**: el de
la cartera, `deuda_cent`; sus notas de crédito sin enlazar van aparte, debajo, en su ficha. Las
tres órdenes de los pagos salen de un solo sitio (`src/aurora/panels/payment-orders.tsx`):
confirmar o retirar lo que el banco propuso (en «Te bevestigen» y en la hoja), enlazar una
línea del banco sin factura (en «Niet gekoppeld»: se elige una factura pendiente de ese lado,
**ninguna viene elegida**, y las que parecen de la línea van primero y marcadas) y apuntar un
pago **ya hecho** (en la tarjeta de una factura y en su hoja: el importe, por defecto lo que
queda y no más; la fecha, no futura; la línea del banco sin casar si la hay; **el motivo,
obligatorio**). Todas piden el permiso `marcar_pagada` y dicen «Er wordt niets betaald». El
servidor decide lo demás: un pago que el banco o Exact ya traen, una factura sin nada
pendiente o una línea ya usada contestan `409 estado_no_valido`, y la tarjeta lo dice en
palabras normales.

**Concurrencia.** Cada orden lleva la `rev` de la fila (o la huella de la factura o del
hallazgo) que la persona vio. Si otra persona la cambió antes, el servidor contesta `409` con el
código `conflicto`; la tarjeta dice «Iemand heeft het intussen gewijzigd. Het is opnieuw
gelezen: kijk en probeer het nog eens.» y no pisa nada.

**Lo que no hay, a propósito.** Ningún botón crea una factura, paga, aprueba un pago o
presenta el BTW: esas órdenes no existen (un test comprueba que la app solo manda órdenes de
`servicios.ACCIONES` y ninguna de esas, y que las de los pagos solo salen de
`payment-orders.tsx`). Confirmar un pago o apuntar uno ya hecho dice qué dinero **ya se
movió**; no mueve ninguno ni prepara una transferencia. El IBAN del documento se enseña en los
datos leídos («er wordt niet naar betaald») pero no se cambia ni se verifica desde ahí: los
datos bancarios van por IBAN te controleren.

### 4.3 El dinero: Kasstroom y Btw

**Kasstroom** es el grupo de Start (E2-I): una fila por semana de las cuatro próximas, con lo
que entra, lo que sale y lo que queda, de las facturas abiertas por su vencimiento
(`/api/v2/flujo` de cada semana); cada semana abre sus facturas en la búsqueda. Debajo,
**aparte y marcado como estimación**, el trabajo del planning aún sin facturar: no son facturas
y no se suma.

**Btw** es su panel (E2-V). Cada trimestre lleva su estado en el texto de la fila (Open, Klaar
voor controle, Aangegeven; con el plazo cerca o pasado, «Nog N dagen» o «Aangifte te laat», en
rojo), el saldo (te betalen / terug) y qué hacer ahora. Su **tarjeta**: las líneas de la hoja
(rubriek e importe), lo que hay que mirar antes de que las cifras valgan y los pasos, en orden:

1. **Werkblad downloaden**: la hoja del trimestre en CSV (`/api/v2/btw/AAAA-TN/hoja`, con
   `fetch` y un `Blob`), la misma que da la CLI;
2. **Klaarzetten** (`btw_lista_para_revision`, cuando el trimestre ya acabó), con la huella de
   la hoja que se vio, o **Kwartaal heropenen** con un motivo (`btw_reabrir`) si ya estaba
   listo;
3. cuando **una persona ya presentó la aangifte en el portal de la Belastingdienst**,
   **Ingediende aangifte vastleggen** (`btw_anotar_presentacion`): la fecha, la referencia y el
   importe que presentó. Lo hace otra persona que quien lo dejó listo (`segunda_persona`).

El programa **no presenta nada**: cada paso lo dice («Er wordt niets ingediend en niets
betaald») y el último solo deja constancia de lo que hizo una persona.

### 4.4 Importeren

**Importeren** está dentro de Te ontvangen (el botón «Een afschrift of export importeren»): el
panel 4 de Aurora en el mismo panel. Lee un fichero suelto, igual que `bms-agent importar` (o
`importar.bat`), sin pasar por el buzón:

1. se **elige el fichero** en la zona de soltar de Aurora (como mucho 8 MB) y **su clase**: se
   reconoce sola por su contenido (las columnas de cada CSV de `config/importacion/`, un
   CAMT.053 o un MT940, una hoja de PO en YAML); si encaja en más de una, pide elegir entre
   esas; se puede elegir a mano;
2. se dice **el día en que se sacó** del sistema de origen (el calendario de Aurora; por
   defecto, el del fichero);
3. **Eerst proberen** (`.primary` mientras no se ha probado) lo importa de prueba (`simular`):
   **no guarda nada** y dice en una tarjeta lo que pasaría: cuántas filas se leyeron, cuántas
   entrarían, cuántas son nuevas y cuántas cambian, las rechazadas con su fila y su motivo, las
   cuentas bancarias nuevas, los avisos que saldrían y, en un extracto, los pagos que casarían;
4. solo después, **Nu echt importeren** (ahora el `.primary`: **una sola acción principal**
   cada vez, y ninguna si con la prueba no entraría nada o ya se importó) con su «sí» (que dice
   que queda con el nombre de quien importa y no se deshace) entra de verdad, **con exactamente
   lo que se probó**. Cambiar el día o la clase después de la prueba la borra.

Si el fichero ya entró (el mismo contenido) lo dice y no lo repite. La base de prueba solo
acepta ficheros de prueba (con la marca `BMS-DEMO`). Un planning que borra turnos pide
confirmarlo, como en la CLI. Sin fichero elegido, dos filas: **Hoe vers elke bron is**
(`/api/v2/fuentes`: la fecha de lo último importado de cada fuente, su edad y si está al día) y
**las últimas importaciones** (el fichero, la clase, quién y cuándo). Necesita el permiso
`importar_datos`; sin él no sale, y tampoco la entrada Verwerken (Procesar, §4.5).

### 4.5 Procesar: leer las facturas (E7)

**Procesar es el de Aurora** (`src/aurora/processing/`: su `processing-workspace.tsx`, la
tarjeta, el cargador, el motor de la suricata y sus PNG, tal cual) y **lo que cuenta es
verdad**: la suricata sigue la lectura que hace el lector del escritorio. Leer un PDF cuesta
dinero (la API de Anthropic, unos céntimos por factura) y la app **no puede leer**: no tiene
internet, a propósito, ni lanza programas. Lo que sí hace es **pedir** la lectura, **enseñar**
lo que costaría, **dar el sí** (o el no) con un tope de gasto y **seguir** la lectura documento
a documento. Lee `GET /api/v2/lectura` cada 2 s mientras Procesar está abierto y manda tres
órdenes, `pedir_lectura`, `aprobar_lectura` y `cancelar_lectura`, con el permiso
`importar_datos` ([integracion-web.md](integracion-web.md), «La lectura pedida desde la app»).
`aprobar_lectura` es el sí al coste de leer, con su tope: no aprueba ninguna factura ni ningún
pago.

**La entrada, como en Aurora.** Al pulsar Verwerken el orbe no viaja a ningún sitio: sus
partículas caen por gravedad desde donde estaban (1,4 s, sin remolino) y forman un montículo
(0,22 s), del que asoma **solo la cabeza** de la suricata (`guard-head.png`), que espera
mirando a un lado y a otro. El saludo dice lo que pasa, con su cambio de 0,3 s; debajo van la
tarjeta (la escena, el avance y su pie), el plan («Lezen — Vergelijken — Analyseren»), el botón
de Aurora (`FlowButton`) y su nota. **«Terug naar start»**, arriba, vuelve al inicio (también
Alt+← y el botón de atrás del ratón); si había una lectura en marcha, sigue: el lector no depende
de la app, y al volver Procesar la enseña donde va.

**Paso a paso** (los textos, en castellano; en neerlandés y en inglés, lo mismo):

| | Cuándo (la lectura) | Lo que se ve | Lo que se puede pulsar |
| --- | --- | --- | --- |
| **P0** · lista | Ninguna viva | «Déjame revisar tus facturas.»; la nota dice lo gastado hasta hoy y lo que suele costar cada factura («Gastado hasta hoy: $ 3,42 · Cada factura, entre $ 0,057 y $ 0,062») y cómo acabó la última («La última lectura: hoy a las 10:41 · 12 nuevas, 3 repetidas.») | **Pedir lectura** |
| **P1** · pedida | `pedida` | «Abre «BMS Finanzas - Leer facturas» en el escritorio.», con el porqué: la app no tiene internet; la nota dice quién la pidió y cuándo | «No leer», en la nota |
| **P2** · el lector empieza | `comprobando`, `contando` | «Comprobando la conexión…» (enciende la salida, solo hacia la API, y mira que nada más pueda salir) y «Contando lo que costaría…» (gratis) | «No leer» |
| **P3** · tu respuesta | `esperando_aprobacion` | «12 facturas nuevas, entre $ 0,68 y $ 0,75.» / «3 ya leídas no se vuelven a pagar. Tienes hasta las 10:27 para decidir.» | **Empezar** (el sí, con la huella de lo que se vio y su tope: el extremo alto) o «No leer» |
| **P4** · leyendo | `aprobada`, `leyendo` | Sale la suricata entera y hace las cinco etapas (abajo); el saludo dice la de ahora y la nota «Paso N de 5 · Lectura real» | «Parar la lectura» (para después de la factura en curso) |
| **P5** · hecha | `hecha`, o parada o en el tope con algo leído | «He finalizado con el análisis.»: **nuevas**, **repetidas** (las ya leídas y los posibles duplicados, B2–B5) y, si las hay, **con problemas**; una fila por documento, que abre su hoja en Documentos; con el tope o parada, cuánto se leyó | **Ver en Documentos** (sin vuelo); «Ir a la cola de trabajo» si entró alguna nueva (el panel Start con su Werklijst, en un solo cambio) |
| **P6** · fallida | `fallida` | La escena se funde (0,3 s) y sale el error de Aurora con el motivo en palabras normales («El aislamiento no está bien: no se ha leído ni pagado nada. Ejecuta comprobar.bat.») y, si algo se leyó, dónde está | **Volver a pedir** |
| **P7** · sin leer | `caducada`, o `cancelada` sin nada leído | «Nadie respondió en 15 minutos.» o «No se ha leído nada.» / «El lector apagó la salida. No se ha gastado nada.» | Pedir lectura |
| **P8** · nada nuevo | `nada_que_leer` | «No hay facturas nuevas.» / «Las 3 que hay ya están leídas: no se paga nada.» | Pedir lectura |

P5 y P6 se ven en la visita en que pasan; la siguiente vez Procesar empieza en P0, con la última
lectura en la nota. Sin el permiso `importar_datos`, Verwerken no sale en la rueda.

**El botón no se mueve.** De P0 a P3, en P7 y en P8, la intro tiene siempre lo mismo y en el
mismo sitio: cuando no hay nada que pulsar (P1, P2), el botón guarda su caja sin verse, y en P3
aparece en ella sin que nada salte. Mientras va el sí, el botón no acepta otro clic.

**El cuerpo sale solo con un sí de verdad.** Hasta que el servidor acepta el sí (el 200 de
`aprobar_lectura`, o la consulta que ve la lectura aprobada si el «si» se escribió en la ventana
del lector), la suricata es solo la cabeza: nunca «lee» antes de que exista un sí. Si la
estimación cambió mientras se miraba (el lector volvió a contar), el sí es un `409`: la cabeza
sigue y el saludo dice «Ha cambiado: 13 facturas nuevas, entre …» con el plazo nuevo; si el sí no
llega al servidor, «No he podido mandar tu sí. Prueba otra vez.».

**Las cinco etapas son las fases de la lectura**: cargar las facturas, leer los datos, comparar
los expedientes, analizar las coincidencias y organizar los resultados. Cada una empieza solo
cuando la lectura ha llegado a ella (`fase` de `pasada_lectura`), y la suricata la juega entera,
como en Aurora: busca a la izquierda, cava, recoge un papel, camina con él hasta la pila de la
derecha y lo deja caer (los papeles se quedan); después lo revisa, lo olfatea o vigila, de cuerpo
entero junto a la pila, nunca con solo la cabeza. Si la lectura va despacio, espera, y a los
6,5 s cava o entra en la cueva y vuelve a salir; si va deprisa, se pone al día etapa a etapa, sin
saltarse ninguna. Al final, la centinela junto a la pila de cinco papeles (1,2 s), el fundido de
0,3 s y el resultado. El título de cada etapa lo pone la suricata al empezarla, con los datos de
verdad en su línea («Leyendo 3 de 12. Identificando referencias, empresas e importes.»), así que
el título nunca va por delante del animal.

**El avance, debajo de la escena, nunca al azar.** La barra `[▓▓▓░░…]` y el % son lo menor de dos
cosas: lo que lleva la suricata (20 por cada papel de la pila, más lo que va de la etapa) y hasta
dónde ha llegado la lectura (cargando 20; leyendo, de 20 a 40 según los documentos hechos;
comparando 60; analizando 80; organizando 99; hecha 100). No va por delante de ninguna de las dos
y nunca baja. Las tres líneas son las de la lectura (`✓ nombre.pdf  listo`, `> nombre.pdf
leyendo…`, comparando o guardando) y el pie dice «LECTURA REAL · 12 FACTURAS · GASTADO $ 0,21».
Nada tapa al animal ni al botón.

**Cuando algo sale mal**, con lo que ya tiene Aurora: la suricata nunca pasa de golpe del cuerpo a
la cabeza. Lo que acaba mal con el cuerpo fuera se funde en 0,3 s, y después sale el error (P6)
o, si se paró sin haber leído nada, una suricata nueva, que entra con su nube pequeña de
partículas y saca la cabeza (P7). Si se para o se llega al tope con algo leído, la suricata
termina las etapas que faltan y sale el resultado, con la nota del tope («Paré en el tope de
$ 0,75 que aprobaste: leí 11 de 12.»).

**La suricata es la del dueño.** Los ocho PNG aprobados (`loader-sprites.ts`, byte a byte los de
`Suricata-Final-Revision/`), dibujados fotograma a fotograma con `drawImage`, sin suavizado
(`imageSmoothingEnabled = false`, `image-rendering: pixelated`), a escala entera (3 en el
ordenador, 2 a 700 px o menos) y a 8 fotogramas por segundo, en celdas de 76 × 47 con el ancla
en 35,41; la escena mide 640 px como mucho y la pila va a 550 px, o más cerca si no cabe. Blanco
sobre negro, sin ojo azul ni ningún color: Procesar es monocromo, y el verde de lo nuevo y el
naranja de lo repetido van en Documentos (§4.6). **Con «menos movimiento»**, lo de Aurora: sin
partículas ni paseos; la cabeza quieta, cada etapa deja su papel al momento y la centinela fija.
Al salir de Procesar se para todo: los cuadros, los observadores y la consulta de cada 2 s.

**Lo que pasa en el escritorio.** El acceso directo **BMS Finanzas - Leer facturas**
(`leer-facturas.bat` en Docker) toma la lectura pedida (o la pide él si nadie la pidió en la
app), enciende la salida con una credencial nueva, comprueba el aislamiento (si falla, no cuenta,
no lee, no paga y la deja fallida), cuenta lo que costaría (gratis; lo ya leído se reconoce por su
huella y no se cuenta ni se paga), espera el sí de la app o un «si» escrito en su ventana como
mucho 15 minutos, lee con el tope y apaga la salida pase lo que pase
([instalacion-nativa.md](instalacion-nativa.md), [entorno-local.md](entorno-local.md)). Sin
respuesta en 15 minutos la lectura caduca, y no se ha gastado nada.

### 4.6 Documentos (E6)

El archivo de Aurora tal como lo diseñó el dueño (`document-workspace.tsx` de su entrega, en
`src/aurora/documents/`, con sus clases, sus nombres y su movimiento), con los datos de verdad
del motor: nada inventado, nada guardado en el navegador y ningún botón que cree, cambie o
borre un documento. El sitio (la categoría, la carpeta y la hoja) es estado de la app
(`estado.ts`, la acción `docs`), sin direcciones. `documents-model.ts` (el orden, los tipos, el
árbol y de dónde sale «pagada», sin React, con sus pruebas) y `sheet-model.ts` (las filas de la
hoja de una factura) son puros.

- **El marco de Aurora**, el de su única pantalla de trabajo (`workspace-layout.css`): la marca
  arriba a la izquierda, «Terug naar Aurora» arriba a la derecha, **el árbol «Verkennen»** a la
  izquierda con su pista, **las migas** («Start › Documenten › Leveranciers › J. Voorbeeld
  Beveiliging (zzp) › JV-2026-006»; cada una vuelve a ese sitio), la cabecera con el orbe
  pequeño (la `SiriWave` de 180 px en su caja de 96 × 52; «Je financiële archief», «Alles heeft
  zijn plek.» y su frase; a los 12 s, la pista de Aurora), la rejilla de carpetas de cristal
  (con su aparición escalonada), la ficha de la carpeta abierta **debajo de la rejilla**, como
  en Aurora, y la nota del pie. Se llega con el vuelo del orbe (§4); «Terug naar Aurora», la
  miga «Start» y el orbe pequeño vuelven al inicio con el vuelo inverso; el nodo «Start» del
  árbol, sin vuelo. Alt+← y el botón de atrás del ratón vuelven un paso (en el primero, al
  inicio); «Naar de inhoud» lleva al título de Documentos.
- **Una carpeta de cristal por cliente y por proveedor** (`GET /api/v2/clientes` y
  `/proveedores`): la rejilla enseña **las doce que piden atención** (lo vencido, más y antes;
  luego lo pendiente; a igualdad, el orden de la API) y la nota del pie dice que las demás están
  en el árbol. Cada una dice de quién es (Klant, Leverancier), su puesto, el nombre y cuántos
  documentos tiene; encima, la pastilla de la prioridad **solo si pide algo** (`.ui-status`,
  quieta) junto a las nuevas y las repetidas de la última lectura de facturas (D-41: las de la
  última lectura de Procesar, §4.5); debajo, lo pendiente de la cartera («Bij» si no queda nada)
  y «Kaart bekijken».
- **El árbol**: Start; Documenten con Klanten y Leveranciers (las categorías) y cada carpeta con
  su cuenta; se maneja entero con el teclado (el patrón *tree* de WAI-ARIA: flechas, Home, End,
  la primera letra, Intro o espacio). Una categoría deja en la rejilla solo las suyas; una
  carpeta la abre.
- **La carpeta abierta**: la de cristal se abre con el abanico de sus documentos y, debajo de la
  rejilla, **la ficha** (`GET /api/v2/clientes/N` o `/proveedores/N`): lo del maestro (código de
  Exact, BTW, KvK, plazo de pago, contacto y correo de facturación), lo pendiente de la cartera
  con cuántas facturas abiertas, lo vencido, cómo paga o cómo le pagamos, la prioridad con su
  porqué; de un proveedor, sus cuentas con su estado y el teléfono de verificación de los
  maestros (solo para mirar); la nota de crédito sin enlazar, aparte. Y **su tabla**
  (`.ws-file-table`): sus documentos (`GET …/documentos`: los originales de sus facturas y
  abonos, los justificantes de sus pagos apuntados y las hojas de sus PO), el más reciente
  primero, y, de un cliente, sus Objects y sus PO. Una carpeta cuyos documentos no se pudieron
  leer lo dice con su «Opnieuw proberen».
- **La hoja** (el `<dialog>` de Aurora, `.ws-dialog`): arriba, el tipo y el estado con su ✕; el
  papel de Aurora (`.ws-paper`) **dibujado desde el registro**, no desde el PDF (la CSP no deja
  marcos, y un PDF de terceros no se abre dentro de la app), claro en los dos temas, con la marca
  de agua solo en la base de prueba; **«Origineel downloaden»** (`GET
  /api/v2/documentos/N/original` con `fetch` y el token; cada descarga queda en la auditoría
  como `documento_abierto`). De una factura o un abono, además, **la tabla «Wat je kunt doen»**
  con sus tarjetas y sus órdenes (§4.2). De un Object, lo facturado, lo que costó, el margen y
  las horas; de una PO, lo pedido, lo facturado, lo que queda y la previsión; en su tabla, sus
  facturas (cada una abre su hoja). Se cierra con la ✕, Escape o un clic fuera.
- **La tabla de una factura, plegada** (decisión del dueño del 29-10-2026: «que se vea lo más
  minimalista y limpio posible»). Con cuatro filas o menos, la tabla entera, sin nada más. Con
  más, la hoja se abre siempre plegada: se ven las tres filas más urgentes y, en la cuarta línea,
  **un solo control** con el botón discreto de la cabecera de la tabla de Aurora
  (`.ws-table-head button`): «En nog 5 regels» («Y 5 líneas más», «And 5 more lines») y, si
  entre lo plegado hay hallazgos o la excepción abierta, cuántos («· 1 vraagt aandacht», «· 1 pide
  atención», «· 1 needs attention»). Es un botón de verdad (`aria-expanded`, `aria-controls` a la
  tabla, Intro o espacio); al desplegar, el foco pasa a la primera fila que estaba plegada y el
  control dice «Minder tonen» («Ver menos», «Show fewer»), que vuelve a plegar (la tarjeta de una
  fila plegada se cierra con ella). Desplegar es de esa vez: cada hoja se abre plegada. El papel
  con sus totales (base, IVA, total, lo que queda) no se pliega nunca, y la cabecera sigue
  contando todas las filas. Lo puro (qué filas se ven, el texto y los avisos) está en
  `foldRows` y `foldLabel` (`src/aurora/documents/sheet-model.ts`).
- **La zona táctil del control** (petición del dueño del 30-10-2026: «Sí, amplía la zona
  táctil»). El botón se ve como antes (9 px de letra, 13,5 px de alto), pero se pulsa en más
  sitio: una capa transparente (`.sheet-fold button::before`, en `src/aurora/bms.css`; las hojas
  de Aurora no se tocan) lo agranda hacia abajo, nunca hacia arriba, donde está pegada la fila de
  antes. Con ratón, toda su línea: **27,5 px de alto** (WCAG 2.5.8 pide 24) por el ancho del
  texto; con el dedo (`pointer: coarse`), **44 px**, que bajan 16,5 px por el aire de debajo (el
  margen del diálogo, 24 px a 1440 y 18 a 400, o los 20 de la tarjeta de una fila abierta). No
  pisa nada ni desplaza más el diálogo, y nada cambia a la vista, ni el anillo del foco; lo
  comprueban `e2e/documents.spec.ts` y `e2e/aurora-paridad.spec.ts` (con `e2e/zona-tactil.ts`).
- **El desplazamiento de la hoja** se mide en cada factura de la base de prueba, plegada como
  se abre (`e2e/aurora-paridad.spec.ts`): no pasa de 300 px a 1440 × 900 ni a 400 × 860, en
  oscuro y en claro. Las plegadas, 246 px como mucho a 1440 (DBO-2026-0417 y KT-202609) y
  273 a 400 (KT-202608 y KT-202609); antes de plegar, DBO-2026-0417 (ocho filas) se desplazaba
  586 y 594 px. La que más, JV-2026-006, con cuatro filas y sin plegar como antes: 292 y 300.
- **Vacíos y errores.** Sin clientes ni proveedores, lo vacío de Aurora (`.ws-empty`), sin
  suricata (D-44). Una carpeta o una ficha que no se pudo leer lo dice, con su reintento.
- **Lo que no hay**: «Agregar muestra», «Descargar muestra TXT», los datos de demostración en
  pesos, las carpetas guardadas en el navegador y la suricata de las carpetas vacías.
- Los nombres de empresas, números, IBAN, teléfonos, correos y ficheros vienen de los datos: se
  pintan como texto (`data-proper-name`).

**Las relaciones: proveedores, clientes, Objects y PO.** Desde el paso 17 B2 viven aquí, como
en Aurora: cada cliente y cada proveedor es una carpeta, y su **ficha** (debajo de la rejilla,
con la de Aurora) dice lo del maestro y lleva, en su tabla, sus documentos, sus Objects y sus
órdenes de compra. Aquí solo se mira: las órdenes de una factura están en su hoja.

| Qué | Dónde | Qué dice |
| --- | --- | --- |
| **Proveedor** | Su carpeta | Código de Exact, BTW, KvK, plazo de pago, lo pendiente (el de la cartera) con cuántas facturas abiertas, lo vencido, **cómo le pagamos**, la prioridad con su porqué, el contacto, **cada cuenta del registro con su estado** y **el teléfono de verificación de los maestros** (solo para mirar: una cuenta se verifica en IBAN te controleren, por teléfono a ese número) y la nota de crédito sin enlazar, aparte |
| **Cliente** | Su carpeta | Lo mismo, con **cómo paga** («Gemiddeld na 25 dagen, nooit te laat») y lo que falta por facturar; en su tabla, sus Objects y sus PO |
| **Object** | Una fila de la ficha de su cliente: su hoja | El cliente y si pide PO; lo facturado, lo que costó y el margen de este año; **las horas planificadas frente a las facturadas**; en su tabla, sus facturas (cada una abre su hoja) |
| **PO** | Una fila de la ficha de su cliente o proveedor: su hoja | De quién o para quién y de cuándo a cuándo; **waarde, verbruikt, over y la previsión** (cuándo se acaba al ritmo de las últimas semanas); en su tabla, sus facturas |

### 4.7 La conversación y la búsqueda (E4 y E5)

**La conversación** (E4, `src/aurora/chat/` y `src/aurora/assistant.ts`) contesta en el
ordenador, sin ningún modelo: con «Geef me een overzicht» («Dame un resumen general», «Give
me an overview»), el **resumen general**, el Finance Bento de Aurora con los datos de verdad
(la cartera de cobrar y de pagar, los clientes y los proveedores con lo que queda de cada
uno, los documentos de sus carpetas y la última lectura de facturas): **son saldos
pendientes, no efectivo disponible**, y lo dice; con «Wat is een Object?», la frase del
glosario; con el nombre de un grupo o de una entrada, una fila que abre su panel (F9); con un
número de factura, un nombre, un Object o una PO, «Ik vond N voor «…».» y sus filas, que
abren su hoja en Documentos con el vuelo, y «Zoeken met filters», que lleva lo escrito a la
búsqueda; con lo demás, lo que sí sabe hacer. «Terug naar de werkruimte» vuelve a la rueda.

**La búsqueda** es, desde el paso 17, la de Aurora (E5, `src/aurora/search/`, su
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
  escrito se queda). Lo que llega de un panel (E5-p: «Vervallen», un tramo de la antigüedad,
  una semana de la Kasstroom) sale en sus pastillas.
- **Los resultados**, los 50 primeros por fecha: número, empresa, de cliente o de proveedor,
  fecha e importe. Un resultado abre la hoja de su factura en Documentos, en la carpeta de su
  empresa, con el vuelo. Sin nada que encaje, «Niets gevonden» y **«Opnieuw beginnen»**, que
  lo quita todo.

### 4.8 Instellingen

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

### 4.9 Alertas y estados

El dueño eligió cómo se ven las alertas («Así quiero las alertas»): su componente
**Status**, una pastilla redondeada y tintada con un punto de color y, siempre, su texto.
Todo estado de la app (prioridades, pagos, controles, avisos, la calidad de un campo, las
cuentas del banco, el aislamiento, la frescura de los datos, el BTW, las PO, las
importaciones y la marca de prueba de la cabecera) sale con esa pastilla; las etiquetas,
los colores sueltos y los puntos de antes se quitaron.

- **Paso 17 B2: los colores de Aurora** (especificación D-31). **En una fila de un panel no
  hay pastilla**: el estado va en el texto de la derecha (`doc-end small`) con el color de
  Aurora: `#b59a76` lo pendiente, `#93b4a4` lo pagado o en orden y, para lo bloqueado (y el
  plazo del BTW pasado), el rojo de `.ui-status.offline`, `#f87171` (en claro, `#4f3815`,
  `#1c3a2d` y `#7b0009`). **En una pastilla** (las carpetas de Documentos, las cuentas de una
  ficha, la tarjeta de la afscherming), la `.ui-status` de Aurora (`workspace-layout.css`):
  verde, naranja, rojo o azul, con su punto y su texto; lo neutro va solo en texto (Aurora no
  tiene pastilla gris). Lo comprueba `e2e/status.spec.ts` en los dos temas.
- **Dónde vive.** La pastilla de Aurora está en `frontend/src/aurora/documents/status.tsx`
  (su `components/ui/status.tsx`, con lo poco que se cambió arriba del fichero). La usa **una
  sola pieza**, `frontend/src/components/status-pill.tsx`: ahí, y solo ahí, se decide qué
  tono lleva cada estado y si su punto late; y `rowTone` da la clase de una fila (`paid`,
  `blocked` o ninguna). Las pantallas dicen el grupo y el valor tal como los manda la API y
  nunca eligen un color.
- **Late solo lo que pide hacer algo ya**: el **aislamiento** que falla, falta o es viejo (en
  su tarjeta de Instellingen) y, donde haya pastilla, lo bloqueado, lo urgente y una cuenta
  por verificar. En Documentos, la prioridad de una carpeta va **quieta** (`PingScope`); las
  marcas de nueva y repetida de la última lectura laten, como en Aurora. Quien pide menos
  movimiento en el sistema (`prefers-reduced-motion`) no ve latir nada.
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
| `lectura` | `en_curso` | Bezig | Running | info | no | Ninguna: Procesar es monocromo (§4.5) y dice el estado de la lectura con palabras * |
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
  pruebas en el navegador en cada pantalla, en los tres idiomas, sin tolerar ninguno. Los
  `.bat` y los accesos directos de la instalación se llaman en castellano en el disco, y los
  tres idiomas los nombran así, como nombres propios (`src/components/script-names.tsx`:
  «Open «BMS Finanzas - Leer facturas» op het bureaublad.», `empresa.bat`). Los
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
  lo que recuerda un panel o Documentos (la vista, el grupo, la carpeta abierta) es estado de
  la app (`aurora/estado.ts`), en la memoria de la ventana, como el token.
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
- **Lo que no hay, a propósito, en estas pantallas.** Procesar no lee ni lanza nada: pide la
  lectura (`pedir_lectura`), da el sí de una persona a lo que costaría, con su tope y la huella
  de lo que vio (`aprobar_lectura`), o el no (`cancelar_lectura`), y lee el progreso; leer lo
  hace el lector del escritorio, que una persona abre con su acceso directo, con la salida
  encendida solo mientras dura (§4.5). Btw no presenta: deja el trimestre listo y anota lo que
  una persona ya presentó (un test comprueba que `btw_anotar_presentacion` solo sale en la
  tarjeta del trimestre). Instellingen solo cambia el idioma y el tema: la empresa, las personas y las
  copias se hacen con sus órdenes. La conversación contesta en el ordenador, sin ningún
  modelo detrás (§4.7).

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
| `src/components/ui/` | Los componentes de shadcn que quedan (button, sheet, tooltip, context-menu, dropdown-menu, hover-card) y la navegación del dueño del paso 15 (`sidebar-with-chrome-like-tabs.tsx`, **sin montar desde el paso 16**: §4, «Lo que se quitó»); arriba de cada uno, lo que se le cambió y por qué |
| `src/components/` | `StatusPill` (todo estado, con la pastilla de Aurora, y `rowTone`, el color de una fila: §4.9) y `script-names.tsx` (los nombres de los `.bat` y del acceso directo, como nombres propios). Las pantallas de los pasos 15 y 16 (`src/screens/`) y sus piezas se fueron con B2 y B3: su trabajo está en los paneles, en Documentos y en Procesar |
| `src/aurora/` | La app de Aurora (paso 17): `root.tsx` (las dos pantallas y el vuelo del orbe), `app.tsx` (el inicio: L0 a E5 y E7), `estado.ts` (la máquina de estados, pura: también el sitio de cada panel y de Documentos), `navigation.ts` (abrir una factura o Documentos con el vuelo), `panels.tsx` (E2) y `panels/` (cada panel: `home-panel`, `money-panel`, `vat-panel`, `import-panel`, `settings-panel`; sus piezas de Aurora en `pieces.tsx`; la tarjeta de una factura, `invoice-card`; las órdenes de las excepciones y de los pagos, `exception-orders` y `payment-orders`; y lo puro, con sus pruebas: `panel-model`, `money-model`, `iban-model` y `weeks`), `orders.tsx` (una orden en una tarjeta: su botón, su formulario, su «sí» y su error), `documents/` (Documentos: `document-workspace.tsx` del dueño, `glass-folder-cards`, `tree-view`, la hoja de una factura `invoice-sheet.tsx` y las demás `sheets.tsx`, la pastilla `status.tsx`, y lo puro: `documents-model`, `sheet-model`, `analysis`), `processing/` (Procesar: `processing-workspace.tsx` del dueño, la tarjeta `processing-card.tsx`, el cargador `document-loader.tsx`, el motor de la suricata `loader-engine.ts` con sus PNG `loader-sprites.ts`, la entrada de las partículas `processing-entry.ts`, el `flow-button.tsx`, y lo puro, con sus pruebas: `reading-model.ts`, lo que se ve y lo que se le pide al motor según la lectura, y `process-texts.ts`, sus textos), `assistant.ts` (lo que contesta la conversación), `chat/`, `finance/` (el resumen general), `search/` (E5), `orb/` y `thinking-orb/`, `text-marquee.tsx` (la rueda), `composer.tsx`, `logo.tsx`, `due.ts` y `use-load.ts`; las hojas del dueño tal cual (`styles.css`, `workspace-layout.css` y las de cada pieza), `bms.css` (lo que añade BMS) y `claro.css` (el tema claro, generado por `scripts/aurora-claro.mjs`) |
| `src/lib/` | El cliente de la API (`api.ts`, con lo que contestan las lecturas en `api-types.ts`), la sesión (`session.tsx`), las órdenes y su permiso (`actions.ts`), los formatos (`format.ts`, `field-format.ts`), el tema (`theme-choice.ts`, los valores sin React; `theme.tsx`, `ThemeProvider` y `useTheme`), el «por qué» de una fila y si pide a una persona (`why.ts`), el «1 van 2» de dos facturas con el mismo número (`twins.ts`), volver a leer tras una orden (`refresh.tsx`), lo que encuentra la conversación (`quick-search.ts`: entradas, grupos, relaciones y facturas) y lo que se guarda (`storage.ts`) |
| `src/i18n/` | Los textos de la app (`nl.ts`, `en.ts`, `es.ts`; su tipo, `Messages`, en `messages.ts`, sin JSX, para que lo usen también las pruebas), los idiomas y `DOMAIN_FALLBACK` (`langs.ts`, sin React: lo usan también las pruebas en el navegador), el acceso a los del dominio (`domain.ts`), el lenguaje de sus plantillas (`templates.ts`), `fmt` y `countText` (una cifra con su palabra, §5) en `index.tsx`, y, para las pruebas, las listas de restos de otro idioma (`leftovers.ts`) y el glosario del castellano (`glossary.ts`) |
| `e2e/` | Las pruebas en el navegador; `nav.ts`, moverse como una persona (la rueda, los paneles, las migas, Instellingen, Procesar) con los nombres de los diccionarios; `aurora/referencia.json` (las medidas del prototipo, también con «menos movimiento») y `aurora/cajas.ts` (medirlas igual en BMS y compararlas, con la captura de cada estado), `aurora/tiempos.json` (los tiempos de Aurora, medidos con la misma herramienta) y `aurora/cruces.ts` (esa herramienta: cada animación del navegador, parada y llevada a cada instante, y los cruces del 5, 50 y 95 %), `aurora/visible.ts` (qué se ve en un cuadro: caja en la ventana, `visibility` y opacidad efectiva; con su propia prueba), `aurora/hojas.mjs` (las hojas de contactos Aurora | BMS de cada estado: `node e2e/aurora/hojas.mjs --aurora <grabaciones de Aurora>`), `aurora/suricata.json` y `aurora/suricata/` (lo grabado de la suricata de Aurora con el reloj virtual: las transiciones de la entrada, las acciones de cada etapa y dos recortes de la escena) y `aurora/contraste.json` (los grises de Aurora que no llegan a 4,5:1, apuntados); `png.ts`, leer un PNG sin dependencias para comparar esos recortes; `payments.spec.ts`, Cobrar y pagar de verdad (las cifras al céntimo, confirmar, retirar, enlazar, apuntar con motivo y justificante, el 409 y quien solo mira) |

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

Desde el paso 17 las piezas son las de la entrega del dueño del 28-10-2026, tal cual (sus
hojas, sus clases y sus nombres), y lo que se les cambió va dicho arriba de cada fichero:
`document-workspace.tsx`, `glass-folder-cards.tsx` y `tree-view.tsx` (Documentos, §4.6), la
pastilla `status.tsx`, la rueda `text-marquee.tsx`, la onda `orb/` y el orbe de partículas
`thinking-orb/`, la conversación `chat/`, el resumen general `finance/`, la búsqueda
`search/` y Procesar `processing/` (§4.5: el motor de la suricata con sus PNG byte a byte, la
tarjeta, el cargador y la pantalla). El suricato del paso 16 (`meerkat/`) se fue con los vacíos
de Documentos (D-44): la suricata es la de Procesar. Del motor solo cambia lo que pide la
política de contenido: la escena se monta nodo a nodo (sin `innerHTML`), y en vez de
`window.setLoaderStage`, `finishLoader` y `hideLoader` el módulo devuelve sus funciones
(`setStage`, `finish`, `hide`, `dispose`); la app no llama nunca a `start()` (avanzaría solo):
pide cada etapa cuando la lectura llega a ella.

**Todo lo que hay en `src/aurora/` está montado**, también Procesar desde el paso 17 B3.
`scripts/codigo-muerto.test.mjs` (vitest) no deja que vuelva nada sin montar (§7, «Sin código
muerto»). De la entrega del dueño no se trae lo que solo era demostración: `invoice-analysis.ts`
y su `DEMO_BATCH`, y la escena vieja de la suricata (`meerkat-scene.tsx`), que ya no montaba.

- **Los estilos** son las hojas del dueño tal cual (`styles.css`, `workspace-layout.css`, las de
  cada pieza); lo que añade BMS va aparte, en `bms.css`, y el tema claro en `claro.css`, que
  escribe `scripts/aurora-claro.mjs` (cada color con su luminosidad invertida en OKLab; las
  superficies claras de Aurora con su texto oscuro —el botón `.primary`, el papel de la hoja,
  la descarga— se quedan como en el oscuro; `scripts/aurora-claro.test.mjs` comprueba que el
  fichero es el que sale). `palette.css` del paso 16 se fue.
- **El orbe** del inicio es la `SiriWave` de Aurora (`orb/siri-wave.tsx`), tal cual: sus dos
  sombreadores, sus constantes y su bucle. Lo único que se le cambia: se para con la ventana
  oculta o con el lienzo fuera de la vista y sigue al volver, y sin WebGL es un degradado fijo.
  Con «menos movimiento» sigue moviéndose, como en Aurora (la imagen fija es un punto para el
  dueño, especificación §7, punto 2); lo que mueve motion alrededor (el orbe de partículas que
  gira y crece al llegar a Verwerken, la onda que crece y el saludo que sube) cambia sin
  moverse. El orbe de partículas (`thinking-orb/`) es el de Verwerken
  en el centro de la rueda y el de «Even denken…»; sus partículas son las que caen al entrar
  en Procesar (§4.5).
- **Los textos** de las piezas están en la sección `aurora` de los tres diccionarios; cada
  uno lo lee alguna pieza (`scripts/codigo-muerto.test.mjs`).

**Por qué los componentes de shadcn están en `src/components/ui`.** Es la ruta que usan
shadcn y su CLI (`components.json`: `ui` es `@/components/ui`), y todos sus imports
la dan por hecha (`@/components/ui/button`). Tenerlos ahí separa lo reutilizable de las
pantallas y deja que un `npx shadcn add` futuro funcione sin tocar nada. Aquí se
copiaron a mano (desde aquí no se llega a ui.shadcn.com); con el registro a mano, un
componente nuevo es `npx shadcn add NOMBRE`.

**Algo nuevo en un panel** es un grupo en su `*-panel.tsx` (una fila `Row` en reposo, su vista
con `GroupView` y la tarjeta `Detail` de cada fila, de `panels/pieces.tsx`) y sus textos en
`nl.ts`, `en.ts` y `es.ts`; una orden nueva, una `OrderSpec` en su tarjeta (`orders.tsx`: el
nombre de `servicios.ACCIONES`, sus campos y sus datos). Algo de una empresa va en su ficha o en
una hoja de Documentos (`documents/`). Una lectura usa `session.api.get(paths.algo)`; una
orden, la de `orders.tsx` (con `rev` cuando la pide; `GET /api/v2/acciones` las lista); una
descarga, `session.api.download(ruta, nombreDeReserva)`. Un error se dice con
`apiErrorMessage`, que lo traduce: el texto del servidor no se enseña. Nada nuevo se dibuja
fuera de las piezas de Aurora.

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
construir, tres cosas, y `scripts/codigo-muerto.test.mjs` (vitest) exige que no haya
ninguna: los ficheros de `src` que `src/main.tsx` no alcanza siguiendo sus `import` (y los
`@import` de las hojas), salvo los que se guardan a propósito y la prueba nombra (la
biblioteca de `components/ui`: la tira de pestañas del dueño con las dos piezas que solo ella
usa, y `sheet`; y lo que solo usan las pruebas, `i18n/glossary.ts` e `i18n/leftovers.ts`);
las declaraciones exportadas que nadie nombra, ni la app ni una prueba ni e2e (con el
analizador de TypeScript); y las clases de las hojas que ninguna pantalla pone (salvo las bandas, que las pone el servidor). Además,
cada texto de la sección `aurora` de los diccionarios lo lee alguna pieza. A mano: `node
scripts/codigo-muerto.mjs`. Lo que espera a un paso posterior no se deja en `src` sin
montar: vuelve cuando su paso lo monte (§7, «Aurora dentro de la app»).

**Las pruebas en el navegador** (`npm run e2e`) crean una base de prueba nueva en una
carpeta temporal (`scripts/crear_demo_e2e.py`, que da los tokens en JSON: Ana
Demo, administradora; Bram Demo, de administración; y Cas Consulta, de solo lectura,
que añade el script), arrancan `bms-agent serve` sobre ella en un puerto libre y entran
con un token de prueba. Si a la base de hoy le falta algo que piden las pruebas (a final de mes
la factura mensual de un cliente ya está cobrada), el script la hace con el reloj de un día
antes, hasta una semana (`dias_atras` en su JSON). Se mueven como una persona (`e2e/nav.ts`, paso 17): «Druk om te
navigeren», la entrada en la rueda (Tab la centra, como con el teclado), la fila de su panel
y las migas; el idioma, el tema y salir en Instellingen (después del idioma se vuelve a la
pantalla por el mismo camino). `e2e/shell.spec.ts` prueba el marco de Aurora: L0 en los tres
idiomas; E0 sin nada más; la rueda con sus ocho entradas, el clic a la primera, la rueda del
ratón, las flechas, Tab, el dedo y «menos movimiento»; los paneles con su ✕, Escape y el
orbe; el vuelo a una pantalla de trabajo y de vuelta; cada pantalla de la app en los tres
idiomas; las migas y Alt+←; Instellingen y salir; recargar y la sesión que caduca; el
teclado; 1024 px y el móvil (400 × 860 y 360 × 740). `e2e/exclusividad.spec.ts` prueba la
regla del dueño (o el menú o una pantalla) con la visibilidad de §1.1 (`e2e/aurora/visible.ts`:
caja en la ventana, `visibility` y opacidad efectiva) en cada estado, en cada cuadro de cada
transición y en cinco anchos, también por dentro de los paneles (una vista, una tarjeta con su
orden abierta, importar), Ctrl+K, las fichas de un cliente y de un proveedor, un Object y una
PO, E5-p, la hoja de una factura con una orden abierta (E6-h, E6-o), plegada y desplegada
(cada cuadro del control), y Procesar (E7, con la
entrada de la suricata): la pantalla que se va solo se funde (su opacidad no sube y acaba en
0,18 s), no recibe clics y no deja ver la rueda; con «menos movimiento», sin solaparse; la rueda
escondida no manda (diez pasos hacia abajo y diez hacia arriba sobre el orbe, el hueco y el
saludo); y F8 y F9 en un solo cambio. El ayudante se prueba a sí mismo con las animaciones a
una décima de su velocidad;
`e2e/aurora-paridad.spec.ts` compara las cajas, la letra, el color y la escala de L0, E0, E1 (y
con Procesar en el centro), E2-C y E2-P (en reposo, con la vista de un grupo y con una tarjeta),
E3, E4, E4-b, E5 (sola, con resultados y con filtros) y Documentos (todo, una carpeta y la hoja)
a 1440 y 400 px con las medidas del prototipo (`e2e/aurora/referencia.json`, ±4 px; en Documentos
la `y` desde la marca; lo que Aurora no tiene en la página tampoco debe verse), y con «menos
movimiento» los estados que Aurora grabó así; lo que se desplaza cada panel (53 y 213 px como
mucho) y cada hoja de factura, plegada (300 px como mucho a 1440 y a 400 px, en los dos temas); y que nada
salte al aterrizar el vuelo a Documentos y de vuelta. Cada comparación deja su captura
(`CAPTURAS_DIR/<tema>/aurora-<estado>-<ancho>.png`) para las hojas de contactos de
`e2e/aurora/hojas.mjs`; `e2e/aurora-tiempos.spec.ts` mide las transiciones de la tabla de
tiempos (T01 a T33, salvo T31, que va en `procesar.spec.ts`) en la línea de tiempo de cada
animación, por los cruces del 5, 50 y 95 %, contra la curva del código del dueño (±10 % o una
muestra); el texto que se escribe y la cifra de puntos, con el reloj virtual; los muelles, contra
lo medido en Aurora; `e2e/conversacion.spec.ts` el resumen general en los tres idiomas (lo
pendiente de la cartera al céntimo, «saldos pendientes», a 1440 y a 400 px);
`e2e/search.spec.ts` la búsqueda de Aurora; `e2e/clicks.spec.ts` cuenta los clics de cada tarea
de la tabla de la especificación (§4, «Los clics») y que la sexta fila y la última de un grupo
se alcanzan escribiendo; `e2e/status.spec.ts` cada estado en su color de Aurora en los dos
temas, el latido solo donde toca y el plazo del BTW pasado en rojo; `e2e/documents.spec.ts` el
archivo de Aurora sobre la base de prueba: las carpetas en su orden contra la API, el árbol con
el teclado, la carpeta abierta con su ficha y su tabla, la hoja y la descarga auditada, la hoja
plegada de DBO-2026-0417 (con el ratón y con el teclado, el foco, el texto contra la API, axe,
otra vez plegada al volver a abrirla, las de cuatro filas o menos sin control y, en castellano a
400 px y con «menos movimiento», sin animación), las doce
primeras y las demás en el árbol, una carpeta que no se pudo leer con su reintento y el archivo
vacío (respuestas cambiadas con `page.route`), y las capturas en los tres idiomas, en los dos
temas y en el móvil; `e2e/daily.spec.ts` el trabajo diario con órdenes de verdad en las tarjetas
de Start y en la hoja (los motivos de las bloqueadas en los dos idiomas, aceptar un hallazgo con
la segunda firma de otra persona y resolver una excepción, marcar como gecontroleerd, una `rev`
vieja que da el aviso de conflicto, la verificación de un IBAN con la regla de las dos personas,
y que quien solo mira no ve ningún botón); `e2e/payments.spec.ts` cobrar y pagar en E2-C, E2-P y
la hoja; `e2e/cartera-partes.spec.ts` que una empresa dice un solo «Openstaand» en el panel, en
el resumen general y en su carpeta; y `e2e/screens.spec.ts` lo demás: las fichas y las hojas en
los tres idiomas, la Kasstroom, el BTW entero en su tarjeta (reabrir, dejar listo, bajar la hoja
y mirar que es el CSV del trimestre, la regla de las dos personas al anotar la aangifte y
anotarla con otra persona), Importeren dentro de Te ontvangen (un fichero que no se reconoce, la
prueba de un maestro de clientes que dice «1 nieuw» sin que cambie nada, un solo `.primary` en
cada momento, la importación de verdad con su «sí», la historia y la repetición, y el cliente
nuevo en Documentos), lo que cuesta leer los PDF y pedir la lectura en neerlandés y en inglés
(«Lezen aanvragen» y «Niet lezen»), Instellingen, quien solo mira y la app a 1024 px sin
desplazamiento horizontal. `e2e/procesar.spec.ts` prueba Procesar con **el lector de las
pruebas** (`scripts/simular_lector.py`, que se niega con una base que no sea de prueba y da, cuando
la prueba se lo pide, los pasos del lector con las mismas funciones del motor: tomar, contar,
leer con su pausa, caducar, volver a contar, el no de la ventana, fallar): pedir, contar,
empezar, leer y el resultado, con el cuerpo de la suricata que no sale sin el 200 del sí, las
cinco etapas en orden y cada una solo cuando la pide la lectura, el % cuadro a cuadro (no baja,
no pasa del techo de la lectura ni de lo que lleva la pila) y la centinela; «Ver en Documentos»
sin vuelo e «Ir a la cola de trabajo»; no leer, caducar y nada que leer con la misma cabeza; el
aislamiento mal y la lectura que falla leyendo, con el fundido de 0,3 s; el 409 de una
estimación que cambió y el sí que no llega; parar sin nada leído; el tope; «menos movimiento» a 1440
y 400 px; en cada estado, solo Procesar a la vista; las cajas de P0, P4 y P5 contra las de
Aurora (también con «menos movimiento»); la centinela y el fundido del final (T31); la fila 21
(dos pasos de rueda y Procesar dos filas por debajo del centro, por el mismo camino que en
Aurora); y, **con el reloj virtual de Playwright, lo mismo que
Aurora** a 1440 y 400 px: las transiciones de la entrada (±40 ms), la cabeza esperando píxel a
píxel, las acciones de cada etapa y la suricata revisando la pila (`e2e/aurora/suricata.json`). Van en orden y cambian la base, así
que comprueban cambios, no cifras sueltas. En
cada prueba: toda petición tiene que ir a `127.0.0.1` (otra se corta y la prueba falla),
ninguna violación de la CSP, ningún error en la consola, ninguna respuesta de error que la
prueba no espere, y axe sin problemas serios ni críticos (WCAG 2.1 AA) ni ninguna falta de
contraste, salvo los grises de Aurora en oscuro apuntados en `e2e/aurora/contraste.json` con su
sitio y su par de colores (con `BMS_E2E_CONTRASTE=fichero` se apuntan los casos nuevos en vez de
fallar) y la marca de agua del papel de la hoja, que es decoración; en cada pantalla,
además, ningún resto de otro idioma (`expectNoLeftovers` en `e2e/fixtures.ts`, con las
listas de `src/i18n/leftovers.ts`; no cuenta lo marcado con `data-proper-name` ni las
bandas que pone el servidor, que van en dos idiomas a propósito). Antes de medir y de cada
captura esperan a que la pantalla esté quieta (`settled`: ninguna animación con fin en
marcha y el contenido de la vista entero, sin esperas fijas). Las demás pruebas van en el
tema por defecto (el oscuro); `e2e/themes.spec.ts` recorre cada pantalla en claro en los
tres idiomas y en oscuro en castellano, las fichas en claro, cómo se elige y se guarda el
tema por persona y «Volg Windows» cambiando en vivo, y el orbe: se mueve al ritmo de la
pantalla y se para con la ventana oculta o fuera de la vista, sigue con «menos movimiento» (como
en Aurora) y sin WebGL es el degradado fijo.
Dejan una captura de cada pantalla, ficha y diálogo, a 1440×900 (`<idioma>-<pantalla>.png`),
en `CAPTURAS_DIR/dark/` o `CAPTURAS_DIR/light/` según el tema que se ve (por defecto
`frontend/test-results/capturas`, que no va en git). El Python es el de `.venv` (o `BMS_PYTHON`); el navegador, el de
`PLAYWRIGHT_BROWSERS_PATH` (no se baja nada: nunca `playwright install`).

## 8. Lo que falta

En la hoja de una factura quedan para la consola las órdenes menos de cada día (imputar una
línea a otro Objeto o a una PO, dividir o añadir líneas, anular o fusionar una factura,
enlazar dos a mano, subir la prioridad; los pagos ya están en la app desde el paso 16:
confirmar, retirar y apuntar uno ya hecho, §4.2), y de las relaciones lo que no se hace cada
semana: registrar, modificar, corregir o cerrar una PO a mano y sus Objects (`registrar_po`,
`modificar_po`, `corregir_po`, `cerrar_po`, `objetos_po`), corregir un dato maestro, poner el
teléfono de verificación de un proveedor, añadir un alias o un beneficiario. Las fichas lo
enseñan todo y esas órdenes siguen en `/consola` y en la CLI.

En Cobrar y pagar quedan dos cosas: subir un justificante nuevo al apuntar un pago (hoy se
elige uno que ya está en la carpeta de la empresa) y enlazar un abono a su factura (se ve en
«Wat op iemand wacht» y abre el abono; enlazarlo sigue en la consola).

Leer los PDF lo sigue haciendo el lector del escritorio, que abre una persona: la app lo pide y
da el sí, pero no lo arranca (no lanza programas). Que se arranque solo, con una tarea de
Windows en horario de oficina cuando hay una lectura pedida y un tope al mes, es la decisión 8B
de la revisión, del dueño; el sí lo seguiría dando una persona en la app.

Punto para el dueño (registro del paso 17): el techo del avance de Procesar, lo único de
Procesar que no es de Aurora (el % no va por delante de la lectura de verdad). El del diálogo de
una factura con muchas filas lo decidió el 29-10-2026: plegar lo que pasa de cuatro filas.

Que alguien de la oficina lea los textos neerlandeses en la app y diga lo que no suena
natural, y mirar en el ordenador del dueño que Edge abre la ventana `--app`.

Más adelante: el asistente local detrás de la conversación, que hoy contesta en el ordenador con
lo que sabe hacer; en Documentos, cuando el dueño lo decida (decisión 7B de la revisión), subir
contratos y otros documentos que no son de ningún registro; y que el motor enlace a cada
relación sus autofacturas de TRNSPRNT, en cuanto se conozca el formato.
