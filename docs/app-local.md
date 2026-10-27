# La app local de BMS

Paso 15 · 19 de octubre de 2026 · Paso 16 (la base de Aurora, los temas y el castellano) · 27 de octubre de 2026

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

Este documento cubre el paso 15 entero: la **base** (el marco, la entrada, la
navegación, los idiomas y el servicio), **las pantallas del trabajo diario** (Overzicht,
Werklijst, Inkomend, Uitgaand, la ficha de una factura, Uitzonderingen e IBAN-controles,
§4.1) y **las demás**: Leveranciers, Klanten, Objecten e Inkooporders con sus fichas
(§4.2), Kasstroom y Btw (§4.3), Importeren y Facturen lezen (§4.4) e Instellingen (§4.5),
todas con datos y órdenes de verdad.

El **paso 16** trae dentro la base de **Aurora**, el prototipo del dueño: su aspecto
oscuro, su orbe, su logo y sus piezas, sin nada simulado (§7, «Aurora dentro de la app»);
los **dos temas**, el oscuro de Aurora por defecto, el claro y «Volg Windows» (§1); y el
**castellano** como tercer idioma (§5). La navegación de pestañas sigue como estaba: la
sustituye la rueda de Aurora en el paso siguiente.

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

El aspecto es el de Aurora desde el paso 16: **tema oscuro por defecto** (fondo
`#0a0a0d`, tarjetas `#111116`, texto `#ebe8f0`, acento lila `#c2aed7`), IBM Plex Sans en
cinco pesos (300 a 700) y Mono, títulos finos, líneas finas y sin sombras salvo en lo que
flota (menús, avisos). Hay también un **tema claro** con la misma paleta (fondo `#f5f4f8`,
tarjetas `#fcfbfe`, acento `#5b4890`) y **«Volg Windows»**, que sigue al modo de Windows y
cambia en vivo si Windows cambia. Lo elige cada persona en el menú de su cuenta o en
Instellingen, y se guarda como el idioma: por persona y entorno, y la entrada sale con el
último de ese ordenador. Los dos temas son variables CSS que usa toda la app
(`src/index.css`: las claras en `:root`, las oscuras en `:root.dark`) y los dos pasan WCAG
AA (axe y la medida de cada pastilla en cada pantalla, §7). El tema lo decide **solo la
clase `.dark` de `<html>`** (`frontend/src/lib/theme.tsx`, que la pone antes de pintar
nada): el CSS construido no lleva `prefers-color-scheme`, así que un Windows en oscuro no
cambia el tema que la persona eligió. Pensado para una ventana de 1440 px,
y se usa también a 1024 × 768 (las tablas anchas se desplazan dentro de su caja; la barra
lateral va más junta en pantallas bajas y se ven todos sus apartados; el + y el … de las
pestañas van fuera de la tira, y un fundido en el borde dice que hay más pestañas a ese
lado); por debajo de 768 px de ancho el menú va en una hoja que se abre con el botón de
menú, y la cabecera va en **dos filas** (pensado para el móvil, de 360 a 430 px): arriba el
botón del menú, la marca de prueba, NL | EN | ES y la persona; debajo, las pestañas con el + y el …
fuera de la tira. Las pestañas van más estrechas, se desplazan con el dedo y solo la activa
lleva la ✕ (como Chrome cuando no caben: sin ratón no se ve antes de tocar, y tocar el borde
de otra la cerraba). En cualquier anchura, la pestaña activa se ve siempre entera: si la
tira o sus pestañas cambian de tamaño (una que se abre, un título que llega), la tira se
desplaza hasta ella.

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
- **Tampoco al gestor de contraseñas de Edge.** Edge y Chromium no hacen caso de
  `autocomplete="off"` para guardar contraseñas, y un campo de contraseña que desaparece
  después de un `fetch` es para ellos una entrada que salió bien: ofrecerían guardar el
  token (y sincronizarlo con la cuenta de Microsoft). Por eso la entrada no tiene `<form>`
  ni `<input type="password">`: es un campo de texto con los caracteres tapados
  (`-webkit-text-security`), `autocomplete="one-time-code"`, Intro para entrar, y el
  campo se vacía antes de comprobar el token. Si aun así Edge ofreciera guardar algo, hay
  que decir **que no**.
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
| | Werklijst · Work queue | Las facturas que necesitan a una persona, lo más urgente arriba |
| | Uitzonderingen · Exceptions | Lo que alguien tiene que resolver, y quién está en ello |
| | IBAN-controles · IBAN checks | Las cuentas que faltan por verificar por teléfono |
| Facturen · Invoices | Inkomend · In (inkoop) | Todas las facturas de proveedores y zzp'ers, y cómo están |
| | Uitgaand · Out (verkoop) | Todas las facturas de BMS a sus clientes, y cómo están |
| Relaties · Parties | Leveranciers · Providers | Proveedores: lo pendiente y lo que destaca |
| | Klanten · Clients | Clientes: lo que deben y lo que falta facturar |
| | Objecten · Objects | Por cada sitio de un cliente: ingresos, costes y margen |
| | Inkooporders · Purchase orders | Cuánto queda de cada PO y cuáles se acaban |
| Geld · Money | Kasstroom · Cash flow | Lo que entra y sale las próximas semanas |
| | Btw · VAT | El BTW por trimestre, listo para revisar (lo presenta una persona) |
| Gegevens · Data | Importeren · Import | Leer un fichero de Exact, del banco o de TRNSPRNT: primero de prueba, luego de verdad |
| | Facturen lezen · Read invoices | Lo que ha costado leer los PDF y cómo se empieza (no desde aquí) |
| (abajo) | Instellingen · Settings | El idioma, quién eres, la empresa y cómo está aislado el programa |

Y las fichas, cada una en su pestaña: una factura, un proveedor, un cliente, un Object,
una PO y un trimestre del BTW.

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

Lo que se ve, en las reglas de diseño que valen para todas las pantallas:

- El Overzicht lleva como mucho cuatro tarjetas (Aandacht nodig, Geld binnen, Geld
  uit, Btw dit kwartaal) y una lista «Als eerste» de cinco, y nada más.
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

### 4.1 El trabajo diario

Todo sale de `/api/v2` y cada orden es una de `servicios.ACCIONES` por
`POST /api/v2/acciones`. Un botón solo sale si la persona tiene el permiso de esa
orden (`frontend/src/lib/actions.ts`, que un test compara con `servicios.ACCIONES`);
quien solo puede mirar (rol `consulta`) no ve ninguno. Cada orden abre un diálogo que
dice en palabras normales qué va a pasar (la frase de confirmación del catálogo en lo
que mueve dinero, BTW o el banco), **una sola vez** y sin «Doorgaan?» (el botón ya dice
la orden; aparte, en una caja, solo lo que no se deshace, como anotar una aangifte), y
pide lo que hace falta (un motivo, una fecha). Después de una orden se vuelven a leer la
ficha, las listas y las insignias del menú, sin que la pantalla salte a «Laden…».

| Pantalla | Qué hay | Órdenes |
| --- | --- | --- |
| **Overzicht** | Cuatro tarjetas (Aandacht nodig: cuántas facturas esperan a alguien, con las bloqueadas, las urgentes y las excepciones abiertas; Geld binnen y Geld uit: lo pendiente y lo vencido, con un enlace a las Verkoopfacturen o las Inkoopfacturen; Btw dit kwartaal: el saldo, **un plazo ya pasado sin la aangifte anotada** («Aangifte te laat», en rojo, aunque el próximo plazo sea ya el del trimestre siguiente) y el próximo plazo) y «Als eerste»: las cinco primeras **cosas distintas** de la werklijst (dos facturas con el mismo número y relación van en una fila: «2 facturen met dit nummer») con su prioridad, número, relación, importe y por qué. Cada tarjeta abre la pantalla que la explica. Nada late | — |
| **Werklijst** | Las facturas que piden a una persona (una prioridad que no es normal, un hallazgo pendiente, una excepción abierta o campos por verificar), en el orden de la API. Fichas Alle / Geblokkeerd / Urgent / Aandacht con su cuenta, un buscador (número o relación, sin mayúsculas ni acentos) y cinco columnas: Prioriteit, Factuur (número y relación), Bedrag, Vervaldatum, Waarom | Una fila abre la factura en una pestaña |
| **Inkomend / Uitgaand** | Todas las de un sentido, con fichas como las de la Werklijst (Alle, Vervallen, Openstaand, Controle nodig, Betaald, con su cuenta) y el buscador; seis columnas: Prioriteit (la única pastilla de la fila), Factuur (número y relación; «1 van 2» si otra tiene el mismo número), Bedrag, Vervaldatum, Stand (pago y revisión, en texto gris) y Waarom | Una fila abre la factura |
| **Ficha de factura** | Arriba, qué es: el número, la relación, el importe con IVA, la prioridad con su razón con nombre, el pago y la revisión. Después **Wat aandacht nodig heeft**, con lo que dice el sistema al lado, en su pastilla («Geen bezwaren van het systeem» cuando está limpia; nunca «goedgekeurd»): cada hallazgo pendiente con su nombre, su detalle escrito desde sus valores, «Wat te doen» y sus botones; y **Afronden**: controleren, la uitzondering y una notitie. Plegado debajo: Velden (valor, fuente y calidad: Ontbreekt, Onzeker, Afwijking, Afwijkend, Geverifieerd), Factuurregels, Referenties en inkooporders, Koppelingen, Planning (los turnos conciliados), Notities, Controles zonder gegevens, Geschiedenis (en palabras normales) y el Origineel document | Aceptar un hallazgo con un motivo de 10 caracteres o más (`anular_hallazgo`, si la regla lo admite; con la segunda firma de otra persona cuando la pide), dar la segunda firma a un colega (`firmar_anulacion`), cerrar uno que ya no se ve (`cerrar_hallazgo`), verificar o corregir el campo al que apunta un hallazgo de lectura; marcar como gecontroleerd (`marcar_revisada`, con la huella de lo que se vio) o devolver (`devolver_factura`); abrir, asignar, dejar esperando y resolver la excepción; añadir una nota; cambiar un campo (antes de guardar se ve «Nu → Nieuw»), verificarlo o deshacer un cambio; confirmar o rechazar una relación propuesta; descargar el original |
| **Uitzonderingen** | Las abiertas, la más urgente primero: qué pasa (el hallazgo más urgente, en palabras normales), de qué va (la factura con su relación, el cliente, la PO o la importación), en qué estado está, quién la lleva y desde cuándo. Una fila abre un panel con lo que hay que saber y qué hacer | Zelf oppakken, toewijzen, wachten op anderen (a quién y hasta cuándo), oplossen (cómo acabó y qué se hizo); desde el panel, la factura |
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

**Concurrencia.** Cada orden lleva la `rev` de la fila (o la huella de la factura o
del hallazgo) que la persona vio. Si otra persona la cambió antes, el servidor contesta
`409` con el código `conflicto`; el diálogo dice «Iemand anders heeft dit net
gewijzigd. Laad opnieuw…» y ofrece **Opnieuw laden**, que vuelve a leer y no pisa nada.

**Lo que no hay, a propósito.** Ningún botón crea una factura, paga, aprueba un pago o
presenta el BTW: esas órdenes no existen (un test comprueba que la app solo manda
órdenes de `servicios.ACCIONES` y ninguna de esas). El IBAN del documento se enseña en
los campos («er wordt niet naar betaald») pero no se cambia ni se verifica desde ahí:
los datos bancarios van por IBAN-controles.

### 4.2 Relaciones: proveedores, clientes, Objects y PO

Cuatro listas con la misma forma: lo más urgente arriba (el orden de la API), un buscador
(nombre, código o número, sin mayúsculas ni acentos) y como mucho seis columnas, la última
«Waarom»: el hallazgo pendiente más urgente de esa relación (de sus facturas, de sus
Objects o de ella misma), escrito desde sus valores, o «N dagen te laat» cuando lo único es
lo vencido. Una fila abre su ficha en una pestaña nueva. Por debajo de 1280 px, Objecten deja
la columna Kosten e Inkooporders la de Waarde (se deducen de las otras), para que «Waarom»
quepa a 1024 px sin desplazar la tabla. Aquí solo se mira: las órdenes de una factura están
en la factura, que se abre desde la ficha.

| Pantalla | La lista | La ficha |
| --- | --- | --- |
| **Leveranciers** | Prioriteit, Naam (con cuántas facturas), Openstaand, Vervallen, Waarom | Qué es (cuántas facturas, cuánto queda), cinco cifras (prioridad, openstaand, vervallen, lo facturado este año, el plazo de pago), **Wat aandacht nodig heeft** (los hallazgos agrupados por factura, con «Wat te doen» y un botón «Factuur X openen» por factura) y, plegado: las facturas abiertas y todas, los pagos del banco, el reparto por Object, las cuentas bancarias con su estado y el teléfono de los maestros (la verificación va por IBAN-controles) y las relaciones propuestas |
| **Klanten** | Igual | Igual, con lo que queda por facturar en vez del plazo y, plegado, el trabajo del planning aún sin facturar por Object |
| **Objecten** | Prioriteit, Object (código, nombre y cliente), Opbrengst, Kosten y Marge de este año (sin btw), Waarom | El cliente y si pide PO; el periodo (Deze maand, Vorige maand, Dit jaar) con opbrengst, kosten, marge y las **horas planificadas frente a las facturadas** (a la clientela y de los proveedores); las facturas de la locatie que piden a una persona (cinco, y cuántas más); plegado: las horas por semana, las facturas a la clientela y de los proveedores y las PO |
| **Inkooporders** | Prioriteit, PO (número, de quién o para quién y hasta cuándo), Waarde, Verbruikt (con su parte), Over, Waarom | De qué cliente o para qué proveedor y de cuándo a cuándo; **waarde, verbruikt, over y la previsión** (cuándo se acaba al ritmo de las últimas semanas, y lo esperado contando lo planificado y lo aún sin facturar); lo que necesita atención (P5–P10) y, plegado, sus facturas (con lo que quedaba después de cada una) y sus Objects |

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
Una fila abre el **trimestre** en una pestaña: arriba el estado y las cifras (omzet, btw
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
`importar_datos`; sin él, la pantalla no sale en el menú.

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

- **Taal**: NL | EN | ES (el mismo interruptor de la cabecera).
- **Thema**: Donker | Licht | Volg Windows (lo mismo que en el menú de la cuenta).
- **Quién eres**: el nombre, el rol o los roles en palabras (Beheerder, Administratie,
  Alleen lezen) y, plegado con su número, **«Wat je mag doen»**: cada permiso en una
  frase (`GET /api/v2/yo`, que ahora da también los roles). Uitloggen.
- **Het bedrijf**, solo para leer: el nombre, los otros nombres, el btw-id, el KvK y las
  cuentas propias (en grupos de cuatro), tal como los usan los controles
  (`GET /api/v2/empresa`); si falta algo, lo dice, y que lo cambia quien administra el
  programa (con `empresa.bat`, que la app no nombra).
- **Afscherming**, solo para leer (`GET /api/v2/aislamiento`): que la app nunca tiene
  internet; en la instalación nativa, si la última comprobación está bien y cada papel (la
  app, el lector de PDF, la salida a internet, las órdenes) con su estado (en orden, una
  prueba que falla, sin comprobar o comprobado hace demasiado: `papeles[].estado`, §4.6);
  en Docker o a mano, una frase sobre cómo se aísla allí.
- **Personas**, solo para quien administra: el nombre y el rol de cada una
  (`GET /api/v2/personas`), y que se gestionan fuera de la app (`persona.bat`).
- **Back-ups**, una frase: los hace quien administra el programa (`copia.bat`), en el
  disco externo cifrado, y se comprueba cada copia.

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
  pantalla** (`PingScope`, revisión del paso 15): las listas (`DataTable`), las tarjetas
  del Overzicht y su «Als eerste», y las fichas de proveedores, clientes, Objects y PO van
  **quietas**; late la cabecera de la ficha de una factura bloqueada o urgente, las filas
  **Geblokkeerd** de la Werklijst (la lista donde se trabaja; las urgentes, quietas), una
  cuenta por llamar en IBAN-controles y el aislamiento. Antes latían diez pastillas a la
  vez en la Werklijst y seis en el Overzicht. Quien pide menos movimiento en el sistema
  (`prefers-reduced-motion`) no ve latir nada.
- **Una pastilla de color por fila** en Inkomend y Uitgaand: la prioridad. El pago y el
  control van en texto gris debajo («Openstaand · Controle nodig»), y lo vencido lo dice
  «Waarom»; antes eran tres pastillas por fila (49 en una pantalla).
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
  días en todas partes (Overzicht, Btw y la ficha del trimestre). La gravedad de un aviso
  dice además, al pasar el ratón, qué hace con la factura (`significa` del catálogo).
- **El tema lo decide la app, no Windows.** Las clases `dark:` del componente del dueño
  valen con la clase `.dark` que la app pone en `<html>` con el tema oscuro
  (`@custom-variant dark` en `src/index.css`), nunca con `prefers-color-scheme`: con eso,
  un Windows en oscuro las aplicaría aunque la persona hubiera elegido el claro, y el texto
  de las pastillas saldría ilegible (menos de 2:1). En oscuro, el texto de cada variante es
  el tono -400 del dueño sobre su tinte; `e2e/status.spec.ts` y `e2e/themes.spec.ts` miden
  cada pastilla en los dos temas a 4,5:1 o más, también con Windows en el modo contrario.
- **No son estados** y siguen como estaban: las insignias de la barra lateral (son
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
| `prioridad` | `bloqueada` | Geblokkeerd | Blocked | error | **sí** (cabecera de la ficha de una factura; filas de la Werklijst) | Overzicht, Werklijst, Inkomend, Uitgaand, Uitzonderingen, las listas de relaciones, Objecten e Inkooporders, y cada ficha |
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
| `pago` | `vencida` | Vervallen | Overdue | error | no | La ficha de una factura y las facturas de una ficha, Overzicht (Vervallen); en Inkomend y Uitgaand, en texto gris |
|  | `pendiente` | Openstaand | Outstanding | default | no |  |
|  | `pagada` | Betaald | Paid | success | no |  |
|  | `anulada` | Geannuleerd | Cancelled | default | no |  |
|  | `acreditada` | Gecrediteerd | Credited | default | no |  |
| `revision` | `necesita_revision` | Controle nodig | Needs review | warning | no | Ficha de factura; en Inkomend y Uitgaand, en texto gris |
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
| `fuente` | `al_dia` | Vers genoeg | Fresh enough | success | no | Importeren (frescura) y Overzicht (cuando la stand no es de hoy) * |
|  | `caducada` | Te oud (meer dan 2) | Too old (more than 2) | warning | no |  |
|  | `sin_limite` | Geen termijn | No time limit | default | no |  |
| `btw` | `abierto` | Open | Open | default | no | Btw, ficha del trimestre, Overzicht (el plazo: *) |
|  | `listo_revision` | Klaar voor controle | Ready for review | info | no |  |
|  | `presentado` | Aangegeven (door een medewerker vastgelegd) | Filed (recorded by a person) | success | no |  |
|  | `plazo_cerca` | Nog 2 dagen | 2 days left | warning | no |  |
|  | `plazo_vencido` | Aangifte te laat | Return overdue | error | no | También en el Overzicht, con los trimestres, aunque el próximo plazo ya sea el del trimestre siguiente |
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

## 5. Neerlandés, inglés y castellano

Por defecto, **neerlandés**; el interruptor **NL | EN | ES** está en la cabecera, en la
entrada y en Instellingen (cada botón lleva el nombre del idioma en ese idioma: Nederlands,
English, Español). Cada persona tiene el suyo (se guarda con su id y el entorno); la
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
- **Los textos del dominio** (cada regla, qué quiere decir y qué hacer; estados,
  prioridades, campos, fuentes, órdenes) salen de los catálogos de Python
  `src/bms_agent/textos/nl.json` y `en.json`, que la app importa al construirse, para
  que la CLI, la auditoría y la app digan lo mismo. Lo que la API manda en castellano
  (`titulo`, `detalle`, `etiqueta`, `fuente_texto`, `nota`, `motivos`) no se enseña:
  queda para la CLI y la auditoría. Solo `frontend/src/i18n/domain.ts` los importa, y
  los dos ficheros entran en la huella de `web/fuente.json`.
- **Mientras falte `es.json`** (lo prepara otro trabajo), la app en castellano dice lo del
  dominio (reglas, estados, prioridades, campos, errores, el tipo de factura) **en
  inglés**. Lo marca `DOMAIN_FALLBACK` en `frontend/src/i18n/langs.ts`, con lo que hay que
  hacer cuando llegue: importarlo en `domain.ts`, añadirlo a `frontend/build-inputs.json` y
  a `tests/test_app_local.py` (los catálogos de la huella) y quitar la entrada de
  `DOMAIN_FALLBACK`.
- **El detalle de cada hallazgo se escribe desde sus `valores`** con las plantillas
  del catálogo (el lenguaje está en `src/bms_agent/textos/LEEME.md`).
  `frontend/src/i18n/templates.ts` es ese lenguaje en TypeScript, y
  `templates.test.ts` comprueba que da exactamente lo mismo que la referencia en Python
  en cada caso de `src/bms_agent/textos/casos.json` (los bordes del lenguaje y un
  hallazgo de cada variante de cada regla), en cada idioma que traiga `casos.json` (hoy
  neerlandés e inglés; el castellano, en cuanto llegue).
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
  pruebas en el navegador en cada pantalla (en castellano se toleran los restos en inglés
  del dominio mientras dure `DOMAIN_FALLBACK`). En neerlandés y en inglés la app no nombra
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
  `localStorage` y solo desde `frontend/src/lib/storage.ts`: el idioma, el tema, si la
  barra va plegada y qué pestañas había (ids de pantalla e ids numéricos), con la clave
  `bms-app:v1:<entorno>:<persona>:…` (y `bms-app:v1:lang` y `bms-app:v1:theme`, los del
  último uso en ese ordenador, para la entrada). Lo que se lee se comprueba campo a campo; si el
  navegador no deja guardar, la app sigue igual.
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
  trimestre). Instellingen solo cambia el idioma: la empresa, las personas y las copias se
  hacen con sus órdenes.

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
| `src/components/ui/` | Los componentes de shadcn (button, sheet, dialog, input, label, tooltip, context-menu, dropdown-menu, hover-card, avatar) y los dos del dueño: la navegación (`sidebar-with-chrome-like-tabs.tsx`) y las alertas (`status.tsx`); arriba de cada uno, lo que se le cambió y por qué |
| `src/components/` | Las piezas de las pantallas: `PageHeader` y `Screen`, `SummaryCard`, `DataTable` (seis columnas como mucho, lo exige el tipo), `StatusPill` (todo estado, con el componente del dueño: §4.6), `Money`, `Hours`, `DateText`, `EmptyState`, `ErrorState` y `TechnicalDetail`, `Loading`, `HelpTip`, `Section`, `FilterChips`, `SearchBox`, `WhyCell`, `FactStrip` (las cifras de arriba de una ficha), `AttentionList` / `InvoiceAttentionList` (lo que necesita atención, agrupado por factura); `ActionDialog` / `ActionButton` (toda orden pasa por ahí; las fechas se teclean como `dd-mm-jjjj`) y `ExceptionStatus` / `ExceptionActions` |
| `src/screens/` | Las pantallas (`overview`, `work-queue`, `invoice-list`, `invoice` con `invoice-findings`, `invoice-fields` e `invoice-sections`, `exceptions`, `iban-checks`, `party-list` y `party` para proveedores y clientes, `objects` y `object`, `purchase-orders` y `purchase-order`, `cash-flow`, `vat` y `vat-quarter`, `import`, `read-invoices`, `settings`), `registry.ts` (cuáles hay, su grupo, su icono y su permiso, y las fichas) y `render.tsx` (qué pinta cada ruta) |
| `src/shell/` | El marco: la navegación con sus insignias, el idioma (`language-switch.tsx`, NL \| EN \| ES), el tema (`theme-switch.tsx`), la persona (con el tema en su menú), la marca de datos de prueba |
| `src/aurora/` | Las piezas de Aurora (paso 16), cada una con su hoja de estilos: abajo, «Aurora dentro de la app» |
| `src/lib/` | El cliente de la API (`api.ts`, con lo que contestan las lecturas en `api-types.ts`), la sesión (`session.tsx`), las órdenes y su permiso (`actions.ts`), los formatos (`format.ts`, `field-format.ts`), el tema (`theme-choice.ts`, los valores sin React; `theme.tsx`, `ThemeProvider` y `useTheme`), el «por qué» de una fila (`why.ts`), el «1 van 2» de dos facturas con el mismo número (`twins.ts`), volver a leer tras una orden (`refresh.tsx`), lo que recuerda una pestaña mientras la app está abierta (`tab-memory.ts`, solo en memoria) y lo que se guarda (`storage.ts`) |
| `src/i18n/` | Los textos de la app (`nl.ts`, `en.ts`, `es.ts`), los idiomas y `DOMAIN_FALLBACK` (`langs.ts`, sin React: lo usan también las pruebas en el navegador), el acceso a los del dominio (`domain.ts`), el lenguaje de sus plantillas (`templates.ts`) y las listas de restos de otro idioma (`leftovers.ts`) |
| `e2e/` | Las pruebas en el navegador |

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
| `logo.tsx` | `BmsMark` (la marca BMS en un SVG pequeño, trazada del PNG del dueño, en `currentColor`) y `BmsLogo` (la marca con «finance») | La entrada y la barra lateral |
| `orb/` | `AuroraOrb`, el orbe de colores (WebGL), y `AuroraMark`, su degradado fijo en pequeño; `orb-loop.ts` decide cuándo se mueve y a qué ritmo, sin React (`orb-loop.test.ts`) | La cabecera del Overzicht (se mueve mientras carga) |
| `thinking-orb/` | `ThinkingOrb`, el orbe de partículas de «Pensando…» | La búsqueda, cuando llegue |
| `meerkat/` | `MeerkatScene`, el suricato del cargador (sus sprites en el código) | El cargador de documentos |
| `processing/` | `DocumentLoader` y `loader-engine.ts` (el cargador con progreso de verdad: `setStage`), `ProcessingCard`, `ProcessingResult` (nuevas, ya leídas, posibles duplicados, fallidas), `FlowButton` | Procesar, cuando la lectura llegue a la app |
| `documents/` | `ArchiveLayout`, `Breadcrumbs`, `ArchiveHeading`, `FolderGrid`, `FolderCell`, `GlassFolder`, `TreeView`, `FolderProfile`, `DocumentPreview` (un `<dialog>` nativo dibujado desde el registro, nunca desde el PDF) | Documentos |
| `conversation/`, `composer.tsx` | `Conversation` (copiar y parar; sin pulgares, regenerar ni compartir) y `WorkspaceComposer`, la caja de escribir | El asistente local |
| `search/` | La barra de filtros, sus pastillas, los resultados, «Pensando…» y el vacío | Zoeken sobre `/api/v2/buscar` |
| `finance/` | `FinanceBento`, «Lo importante»: vencido por cobrar y por pagar, el neto de 30 días y la nota de que no es dinero disponible, desde céntimos | El resumen del asistente |
| `wheel.tsx` | `Wheel`, la rueda de navegación | La navegación, en el paso siguiente |

Hoy la app monta el logo y el orbe; las demás piezas esperan a su pantalla y no entran en
lo construido hasta que alguien las importe.

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
- **Los textos** de las piezas están en la sección `aurora` de los tres diccionarios.

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

**Lo que lee Tailwind.** `src/index.css` le quita la detección automática
(`@import "tailwindcss" source(none)`) y le da solo `src` (sin las pruebas) e `index.html`:
lo que cubre la huella de `fuente.json`. Sin eso leía todo `frontend/` (las pruebas, `e2e/`,
los scripts) y una clase escrita en una prueba cambiaba el CSS sin cambiar la huella.
`scripts/tailwind-fuentes.mjs` saca con el escáner de Tailwind los ficheros que lee;
`fuente.mjs` no construye ni da por buena la huella si alguno no está en
`build-inputs.json`, y `scripts/tailwind-fuentes.test.mjs` (vitest) lo comprueba.

**Las pruebas en el navegador** (`npm run e2e`) crean una base de prueba nueva en una
carpeta temporal (`scripts/crear_demo_e2e.py`, que da los tokens en JSON: Ana
Demo, administradora; Bram Demo, de administración; y Cas Consulta, de solo lectura,
que añade el script), arrancan `bms-agent serve` sobre ella en un puerto libre y entran
con un token de prueba. `e2e/shell.spec.ts` prueba el marco (también en el móvil, a
400 × 860 y 360 × 740: dos fichas en sus pestañas, de una a otra tocándolas y nada fuera de
la ventana), `e2e/daily.spec.ts` las pantallas del trabajo diario con órdenes de verdad (los motivos de las bloqueadas en
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
marcha y el contenido de la pestaña entero, sin esperas fijas). Las demás pruebas van en el
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
enlazar dos a mano, marcar un pago, subir la prioridad), y de las fichas de relaciones lo
que no se hace cada semana: registrar, modificar, corregir o cerrar una PO a mano y sus
Objects (`registrar_po`, `modificar_po`, `corregir_po`, `cerrar_po`, `objetos_po`),
corregir un dato maestro, poner el teléfono de verificación de un proveedor, añadir un
alias o un beneficiario. Las fichas lo enseñan todo y esas órdenes siguen en `/consola` y
en la CLI. Leer los PDF se sigue empezando con su acceso directo, a propósito.

Que alguien de la oficina lea los textos neerlandeses en la app y diga lo que no suena
natural, y mirar en el ordenador del dueño que Edge abre la ventana `--app`.

Del paso 16: la navegación de Aurora (la rueda, `src/aurora/wheel.tsx`) sustituye a la
barra lateral con pestañas en el paso siguiente (con ella, «Cola de trabajo» y su insignia
ya no se cortan en la barra); las demás piezas de `src/aurora/` esperan a la pantalla que
las use; y el catálogo de dominio en castellano (`src/bms_agent/textos/es.json`), que
prepara otro trabajo, se conecta como dice `DOMAIN_FALLBACK` (§5).
