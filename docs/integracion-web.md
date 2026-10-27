# Conectar el agente con un sitio web propio

## Sobre el botón de "ejecutar el agente"

El instinto es correcto: administración tiene que poder lanzar una pasada sin
abrir una terminal. Pero hay dos cosas que decidir antes, y una tiene
consecuencias de seguridad.

### Dónde vive el botón

| Dónde | ¿Vale? | Por qué |
| --- | --- | --- |
| Herramienta interna, en el ordenador de administración o dentro de la red, detrás de autenticación | **Sí** | Es una consola de operación. Es su sitio natural |
| Portal público de consulta (clientes, trabajadores, asesor) | **No** | Cada pulsación cuesta dinero real. Un endpoint público que lanza trabajo es una forma de vaciar el saldo de la API: basta con encontrar la URL y pulsarlo en bucle. Y rompe la garantía de solo lectura sobre la que se apoya toda la arquitectura del portal |

Esto no contradice la regla de que *el portal nunca gana un botón*: la consola
interna y el portal son dos aplicaciones distintas, con dos audiencias y dos
niveles de acceso distintos. Lo que no puede pasar es que sean la misma página.

### Qué forma tiene el botón

**No puede ser una llamada síncrona.** Leer cincuenta facturas tarda minutos.
Un botón que se queda girando, o que agota el tiempo de espera del navegador,
o que se dispara dos veces porque el usuario creyó que no había pasado nada,
es el diseño equivocado.

La forma correcta es un **trabajo**:

1. `POST /api/ejecutar` lanza y devuelve enseguida.
2. El navegador consulta `GET /api/ejecucion` cada pocos segundos.
3. Cuando el estado pasa a `terminado`, el sitio recarga los datos.

Tres detalles que hay que resolver sí o sí:

- **Un solo trabajo a la vez.** Dos clics seguidos son dos extracciones
  concurrentes sobre la misma carpeta: el doble de gasto para nada. Cerrojo.
- **Progreso visible.** Sin él, el usuario vuelve a pulsar.
- **El coste de la pasada, al terminar.** Es la cifra que evita que alguien se
  acostumbre a pulsar el botón por costumbre.

---

## Los tres niveles de conexión

Van en orden. Cada uno sirve para una fase distinta del proyecto.

### Nivel 1 · Un fichero JSON (funciona hoy)

```bash
bms-agent export --file datos.json        # contrato v1: el panel de compras de siempre
bms-agent export --v2 --file datos-v2.json   # contrato v2: todo lo de la V1 (ver abajo)
```

Escribe todo lo que el panel necesita. El sitio lo lee con un `fetch`. Sin
servidor, sin base de datos, sin nada que desplegar. Es el camino más rápido
para tener un sitio funcionando, y sirve mientras el agente se ejecute a mano.

El **contrato v1** (sin `--v2`) es el panel de compras de la fase 0 y no
cambia (abajo, «El contrato de datos v1»). El **contrato v2** (`--v2`) sale del
almacén y lleva el panel principal, la búsqueda, las vistas de proveedores,
clientes, Objetos y órdenes de compra, el BTW y el flujo de caja: es el que
debería leer un sitio propio nuevo (abajo, «El contrato v2»).

### Nivel 2 · Servidor local de desarrollo (funciona hoy)

```bash
bms-agent serve
bms-agent serve --origen http://localhost:5173   # si el sitio va en otro puerto
```

Levanta en `http://127.0.0.1:8765`:

| Endpoint | Qué hace |
| --- | --- |
| `GET /` | Página local mínima con el botón de ejecutar y el estado de la pasada |
| `GET /api/datos` | Los mismos datos que el export, siempre frescos. Pide el token **personal** de quien lee en `X-BMS-Token` (como `/api/v2`), y desde un origen declarado con `--origen` sale con los IBAN enmascarados |
| `GET /api/ejecucion` | Estado de la última pasada |
| `POST /api/ejecutar` | Lanza una pasada. Pide cabecera `X-BMS-Token` y cuerpo JSON. Devuelve `409` si ya hay una |
| `GET /api/v2/...` | El contrato v2, por partes (abajo): piden el token **personal** de quien lee en `X-BMS-Token` |
| `POST /api/v2/acciones` | Las órdenes de las personas (corregir un campo, revisar, verificar un IBAN...), con su token personal |
| `GET /app` | La app local (paso 15, [app-local.md](app-local.md)): la que abren los lanzadores. Se pinta con lo de `/api/v2`, como la consola |
| `GET /app/assets/...` | Sus ficheros (script, estilo, fuentes), de una lista blanca de lo construido |
| `GET /consola` | La consola interna de antes, que se pinta con lo de `/api/v2`. Sigue, de reserva |

**Escucha solo en `127.0.0.1`, a propósito.** No acepta una IP de red. Es un
servidor de desarrollo para construir el sitio contra datos reales, no un paso
hacia producción.

Escuchar en `127.0.0.1` no basta: el navegador de quien tiene el servidor
abierto también visita otras webs, y cualquiera de ellas podría intentar leer
los datos (IBAN incluidos) o lanzar pasadas que se pagan. Por eso el servidor
comprueba tres cosas en cada petición:

| Comprobación | Qué cierra | Si falla |
| --- | --- | --- |
| **Host** exactamente `127.0.0.1:<puerto>` o `localhost:<puerto>` | Una web que hace rebotar su DNS hacia `127.0.0.1` (*DNS rebinding*) llega con su propio nombre en el Host | `421` |
| **Origin** igual, entero, a uno de los admitidos: la propia página y los que se declaren con `--origen` (solo `localhost` o `127.0.0.1`) | Antes se comparaba por prefijo, y `http://localhost.attacker.example` o `http://127.0.0.1.nip.io` pasaban y recibían la cabecera CORS | `403`, sin cabecera CORS |
| En `POST`, cabecera **`X-BMS-Token`** y cuerpo **`application/json`** | Un formulario de otra web no puede poner ninguna de las dos cosas, así que no puede lanzar una pasada | `403` sin token, `415` si no es JSON |

El token es aleatorio en cada arranque. Se imprime al arrancar y va dentro de
la página que sirve `GET /`, en `<meta name="bms-token">`. Esa página no se
deja meter en un marco de otra web (`X-Frame-Options: DENY`), para que nadie
pueda hacer pulsar el botón con un clic disfrazado.

Ejemplo de uso desde un sitio en `http://localhost:5173`, arrancado con
`bms-agent serve --origen http://localhost:5173` y con el token que imprimió
al arrancar en la configuración del sitio:

```js
const BMS = 'http://127.0.0.1:8765'
const TOKEN = import.meta.env.VITE_BMS_TOKEN   // el que imprime `bms-agent serve`

// El token personal de una persona de solo lectura (token(), en «Ejemplo», abajo), no el de arriba.
const datos = await (await fetch(`${BMS}/api/datos`, {
  headers: {'X-BMS-Token': token()},
})).json()

async function ejecutar() {
  const r = await fetch(`${BMS}/api/ejecutar`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-BMS-Token': TOKEN},
    body: '{}',
  })
  if (r.status === 409) return   // ya hay una en curso
  const timer = setInterval(async () => {
    const e = await (await fetch(`${BMS}/api/ejecucion`)).json()
    pintarProgreso(e)                       // e.procesadas de e.total
    if (e.estado === 'terminado' || e.estado === 'error') {
      clearInterval(timer)
      recargarDatos()                       // e.coste dice lo que costó
    }
  }, 2000)
}
```

Una pasada lanzada desde aquí sigue la misma política de caché que
`bms-agent extract`: lo ya leído se reutiliza aunque haya cambiado el modelo o
la versión, y no se sobrescribe nada.

### Nivel 3 · API de verdad (cuando toque desplegar)

Base de datos, API autenticada por rol y modelo de lectura separado. Ver
[portal-consulta.md](portal-consulta.md): ahí está la razón por la que la API
del portal no puede ser esta misma en otro puerto.

---

## El contrato de datos v1

Lo que devuelven `bms-agent export` (sin `--v2`) y `GET /api/datos`. Es
estable: si cambia, cambia con una nota en este fichero. Desde la revisión
final, `GET /api/datos` pide el token personal de alguien con `ver_facturas`
(antes lo leía cualquier proceso del ordenador, IBAN enteros incluidos) y,
pedido desde un origen declarado con `--origen`, enmascara cada IBAN como
`/api/v2`; a la consola (el mismo origen) le llega byte a byte como siempre. Desde la V1 es el
panel de compras de siempre, con los valores corregidos del almacén: un test
comprueba que `GET /api/datos` sigue siendo byte a byte la foto de referencia
(`tests/golden/construir_datos_v1.json`). Lo nuevo de la V1 no entra aquí: va
en el contrato v2.

```
{
  "totales": {
    "facturas", "importe", "iva", "horas", "proveedores",
    "criticas", "por_revisar", "coste_lectura", "desde", "hasta"
  },
  "filas": [ {                          // una por factura
    "fichero", "proveedor", "numero",
    "fecha",                            // como la imprime la factura
    "orden",                            // AAAA-MM-DD normalizado, para ordenar
    "periodo", "ubicaciones", "semanas",
    "semanas_iso": ["2026-W37"],        // ya resueltas al año ISO correcto
    "horas", "base", "iva", "total",    // números, no cadenas
    "regimen",                          // standard | reverse_charged | kor_exempt | unknown
    "iban", "vencimiento",
    "estado",                           // ok | revisar | critico
    "motivos": [],                      // por qué no está en ok
    "otras_unidades": []                // unidades distintas de la hora
  } ],
  "por_mes":       [ {"mes": "2026-09", "facturas", "total"} ],
  "por_proveedor": [ {"proveedor", "facturas", "total", "horas", "primera", "ultima", "avisos"} ],
  "por_regimen":   [ {"clave", "etiqueta", "facturas", "total"} ],
  "matriz": {
    "semanas": ["2026-W21", ...],       // rango continuo, con los huecos
    "proveedores": [ {"proveedor", "total",
                      "celdas": {"2026-W21": {"importe", "n", "estado"}}} ],
    "maximo"                            // para escalar la rampa de color
  },
  "alertas": [ {"severidad", "regla", "titulo", "detalle", "facturas": []} ],

  "facturacion": {                      // proyeccion de venta, NO facturas emitidas
    "configurada",                      // false si no hay tabla de tarifas
    "margen_por_defecto",
    "propuestas": [ {
      "cliente", "obra", "semana",      // agrupado por los tres
      "lineas": [ {"trabajo", "horas", "coste", "venta",
                   "tarifa_venta", "origen_tarifa"} ],   // tabla | margen
      "horas", "coste", "venta", "margen", "margen_pct",
      "facturas_origen": [], "proveedores": [],
      "avisos": []                      // obra sin cliente, coste que varia...
    } ],
    "sin_mapear": [],                   // obras sin cliente en la tabla
    "no_facturable": [ {"trabajo", "horas"} ],           // horas que no se refacturan
    "totales": {"propuestas", "clientes", "horas", "coste", "venta", "margen", "margen_pct"}
  }
}
```

### Sobre `facturacion`: es una proyección, no una factura

Se calcula desde lo que **los autónomos os han facturado**, no desde las horas
registradas en el planning. Tres cosas que la pantalla tiene que dejar claras:

- Si un autónomo facturó de más o de menos, la proyección hereda el error. El
  cruce contra el planning es lo que lo corrige, y llega en la fase 2.
- Las horas que se pagan no son las que se facturan. Las de viaje son el caso
  típico: van en `no_facturable`.
- **Una obra no es un cliente.** Las facturas de compra dicen "Rijnhaven", no
  de quién es. Ese mapeo está en `config/tarifas.yaml`, y lo que falte sale en
  `sin_mapear` en vez de inventarse.

`origen_tarifa` dice de dónde salió cada precio: `tabla` si estaba pactado,
`margen` si se aplicó el porcentaje sobre el coste. Conviene que se vea en la
pantalla, porque son dos niveles de confianza distintos.

Con `configurada: false` no hay tabla puesta y todo sale sin mapear: es el
estado por defecto y la pantalla debería invitar a rellenarla, no mostrar
ceros.

### Tres cosas que conviene saber al construir contra esto

**Todos los importes agregados van en BASE IMPONIBLE**: `por_mes`,
`por_proveedor`, `por_regimen` y las celdas de la matriz. Comparar regímenes
por el total con IVA premia al régimen y no al gasto, porque una factura con
el IVA trasladado no lleva cuota y otra al 21% sí. El total con IVA está en
cada fila, para cuando lo que interesa es lo que sale del banco.

**Todo el texto de `filas` y de `alertas` viene de PDF de terceros.** Llega sin
escapar, tal como lo dice el documento, y algunos documentos traen texto
diseñado para que un sistema lo obedezca. En el navegador va al DOM con
`textContent`, nunca con `innerHTML`. Si lo exportas a CSV, neutraliza las
celdas que empiezan por `=`, `+`, `-` o `@`, que Excel las ejecuta.

**`estado` ya viene cruzado con todo el histórico.** Una factura señalada por
un duplicado o por un cambio de IBAN sale como `critico` aunque ella sola
parezca correcta; una con el periodo solapado con otra (B4) sale como
`revisar`. No hay que recalcularlo en el cliente.

**Una factura que no está en euros no suma.** Sus `base`, `iva` y `total`
llegan como `null`, sale `critico` y el motivo dice la moneda (regla X1).
Basta con que un importe lleve otra moneda: los que no llevan marcador
tampoco cuentan como euros. Sale en `filas` con sus `horas`, y cuenta en
`totales.facturas`, `proveedores`, `criticas` y `por_revisar`, que son
recuentos de la tabla; no entra en ninguna suma: ni `totales.importe`,
`iva` u `horas`, ni `por_mes`, `por_proveedor`, `por_regimen`, `matriz` o
`facturacion`.

Las líneas en «uur», «uren», «u» u «hours» son horas.


---

## El contrato v2

Lo que devuelven `bms-agent export --v2` y `GET /api/v2/exportar`, y por partes
las lecturas de `/api/v2`. Es el contrato con el que construir un sitio propio
(por ejemplo, el panel en React del dueño) contra la V1. Lo escribe
`consultas.exportar_v2` y lo comprueba `consultas.comprobar_v2`, clave a clave
con lo que dice esta sección (`tests/test_contrato_v2.py`).

### La versión

```
{"contrato": "2.3", ...}
```

Cada respuesta de `/api/v2` lleva además la cabecera `X-BMS-Contrato: 2.3`. El
número sube así:

- **2.x → 2.(x+1)** cuando se **añade** una clave: un sitio que ignora lo que
  no conoce sigue funcionando;
- **2.x → 3.0** cuando una clave **cambia de forma o desaparece**: el sitio
  tiene que cambiar, y este fichero dice qué.

Cuando el servidor corre sobre la base de **datos de prueba** (`demo.sqlite3`,
[entorno-local.md](entorno-local.md)), cada respuesta lleva también la cabecera
`X-BMS-Entorno: demo`. No es una clave del contrato ni cambia su versión: es
para que un sitio en desarrollo pueda pintar su propio aviso de «datos de
prueba» y no confunda lo ficticio con lo real. Con la base de verdad la
cabecera no aparece.

Un sitio debería comprobar el número mayor al leer y negarse a pintar uno que
no conoce.

**Lo que añadió el 2.1 (paso 15).** Claves nuevas, ninguna cambia ni se quita:

- cada **hallazgo**, donde sale uno (la ficha de una factura, su historia, los
  avisos de un proveedor, un cliente o una PO, lo sin facturar de un cliente y
  del panel), lleva `resultado` (siempre `"fallo"`: lo que no se pudo mirar no
  abre ningún hallazgo) y `valores`: lo que su regla comparó, los mismos
  enteros y textos que van en su huella (`hallazgo.valores_json`);
- cada **factura** de las listas y de la búsqueda, y cada **excepción**, lleva
  `razones`: sus hallazgos pendientes, lo más urgente primero, cada uno con
  `id`, `regla`, `severidad`, `estado`, `resultado` y `valores`;
- la **ficha** de una factura lleva `reglas_sin_datos`: las reglas que no
  pudieron mirarla (`regla`, `clave`, `resultado` `"sin_datos"`, `detalle` y
  `valores`);
- cada **respuesta de error** lleva, junto a su frase en español (`error`), un
  `codigo` estable (abajo, «Los errores»);
- cada fila de las listas de **proveedores**, **clientes**, **Objetos** y
  **órdenes de compra** lleva también `razones` (la misma forma): los hallazgos
  pendientes de sus facturas y los que la señalan a ella (lo sin facturar de un
  cliente, V6 y V8; los límites de una PO, P5-P10), lo más urgente primero;
- `GET /api/v2/yo` lleva los `roles` de la persona, y cada persona de
  `GET /api/v2/personas` los suyos;
- cuatro lecturas nuevas para la app (`GET /api/v2/importaciones`,
  `GET /api/v2/lectura`, `GET /api/v2/empresa`, `GET /api/v2/aislamiento`) y una
  orden, `POST /api/v2/importar` (abajo, «Importar desde la app»);
- cada papel de `GET /api/v2/aislamiento` lleva, además de `bien`, su `estado`
  (`correcto`, `falla`, `sin_comprobar` o `caducada`), para que la pastilla de la
  app diga cuál de las tres cosas pasa;
- cada hallazgo de la **ficha** de una factura lleva `firmas`: las segundas firmas que
  otra persona ya dio para anularlo y aún valen (con la huella de ahora, sin caducar ni
  gastar), cada una con `solicitante_id` (para quién), `firmante_id` y `firmante` (de
  quién), `vigente_hasta` (el plazo firmado: la anulación tiene que llevar el mismo) y
  `caduca_en`. La app no deja mandar `anular_hallazgo` cuando `segunda_firma` es `true`,
  hay otra persona que podría firmar y no hay una firma para quien acepta;
- cada fila de las listas de **proveedores** y **clientes** lleva `sin_importe`: cuántas
  de sus facturas no tienen importe en euros (otra moneda, X1). Quedan fuera de
  `pendiente_cent` y `vencido_cent`, así que un `0` ahí no quiere decir «no se debe nada».

Con eso la app de la oficina (`/app`) escribe en neerlandés o en inglés el
detalle de cada hallazgo y el «por qué» de cada fila, con las plantillas de
`src/bms_agent/textos/` (su lenguaje está en `src/bms_agent/textos/LEEME.md`),
y no enseña nunca los textos en español (`titulo`, `detalle`, `etiqueta`,
`fuente_texto`, `motivos`), que siguen ahí para la CLI y la auditoría. Los
`motivos` de la prioridad no tienen un gemelo estructurado: harían falta
columnas nuevas en las dos cachés de prioridad; las `razones` dicen lo mismo
desde los hallazgos. Los `valores` de F2-F10 y K4 traen IBAN enteros: desde
otro origen salen enmascarados como cualquier texto (abajo).

**Lo que añadió el 2.2 (paso 16).** Para Cuentas por cobrar, Cuentas por pagar y
el archivo de Documentos de la app. Claves y lecturas nuevas; ninguna cambia ni
se quita:

- seis lecturas: la cartera de un lado (`GET /api/v2/cartera`), los pagos que
  el banco propuso y esperan a una persona (`GET /api/v2/pagos/propuestas`), las
  líneas del banco sin casar (`GET /api/v2/movimientos`), los documentos de un
  cliente o un proveedor (`GET /api/v2/clientes/N/documentos` y
  `GET /api/v2/proveedores/N/documentos`) y la descarga auditada de cualquier
  documento guardado (`GET /api/v2/documentos/N/original`). Abajo, «Cuentas por
  cobrar y por pagar» y «El archivo de una parte»;
- la vista de un proveedor y la de un cliente llevan `kvk`, `email_facturacion`
  y `direccion` (lo que tenga el maestro: el de clientes no guarda correo ni
  dirección, y van `null`), `contactos` (las personas de contacto del maestro,
  las activas primero: `id`, `nombre`, `email`, `telefono`, `funcion`, `activo`),
  `ordenes_compra` (sus PO, como cada fila de `GET /api/v2/ordenes`) y
  `documentos` (cuántos tiene su carpeta); la de un cliente, además, `objetos`
  (sus Objetos del maestro: `id`, `codigo`, `nombre`, `activo_desde`,
  `activo_hasta`). El teléfono de un contacto no es el de verificar una cuenta:
  ese es `telefono_verificacion`, el del maestro de proveedores;
- cada fila de las listas de **proveedores** y **clientes** lleva `documentos`:
  cuántos documentos tiene su carpeta;
- la búsqueda admite el filtro `tipo` (`factura` o `nota_credito`).

Y una corrección de este fichero, no del código: decía que `dinero_entra` («lo
que se espera cobrar») llevaba los abonos de los proveedores. Nunca los ha
llevado: solo cuentan las deudas (`reglas.pagos.vence`), y un abono, de quien
sea, no es un cobro con fecha. Lo que queda de un abono sin enlazar lo da la
cartera aparte (`abonos_sin_enlazar`), con su aviso R4.

**Lo que añadió el 2.3 (paso 16, Cuentas por cobrar y por pagar en la app).** Claves
nuevas; ninguna cambia ni se quita:

- cada pago de la ficha de una factura (`pagos`) lleva quién lo confirmó o lo apuntó
  (`persona`: solo si fue una persona; lo que casó el banco solo va con `null`) y
  cuándo (`confirmada_en`), cuándo se retiró (`retirada_en`), lo que escribió esa
  persona (`motivo`: texto), el documento que lo prueba (`evidencia_documento_id`) y
  el día y el importe de su línea del banco (`movimiento_fecha`,
  `movimiento_importe_cent`) y, de uno retirado, quién y por qué (`retirada_por`,
  `motivo_retirada`, de su evento). Con eso la app dice «apuntado a mano por Ana» y enseña
  la línea del banco al lado de cada pago;
- cada factura de las listas y de la búsqueda lleva su `rev`, para que una orden dada
  desde una lista (apuntar un pago enlazando una línea del banco) lleve la que se vio;
- la cartera (`GET /api/v2/cartera`) lleva `esta_semana`, lo que toca hasta el domingo
  (lo vencido y lo que vence esta semana), con lo retenido y lo que no y cada factura
  con por qué; en `retenido.lista`, cada factura retenida con su razón (también las que
  vencen después); y `avisos_pago`, las facturas de ese sentido con un aviso de pago raro
  activo (K2, K3, K4, K5, K8 o K9). Abajo, «La cartera».

### Cuatro reglas que valen para todo

**Importes en enteros, con su texto al lado.** `_cent` son céntimos de euro
con signo (un abono es negativo), `_mil` milésimas de hora, `_pb` puntos
básicos (2100 es 21 %). Al lado va el mismo valor ya escrito como se lee en la
empresa (`"pendiente": "2.902,79"`). Ningún número lleva decimales: un
`float` no entra nunca (lo comprueba el test). Los importes agregados son
**sin IVA** salvo los de dinero (`dinero_entra`, `dinero_sale`, `caja`,
`pendiente_cent`), que son lo que sale del banco.

**El texto de un documento llega tal cual.** `contraparte`, `numero`, los
nombres de proveedores, clientes y Objetos y los motivos pueden traer HTML o
texto escrito para que un sistema lo obedezca. Van al DOM con `textContent`,
nunca con `innerHTML`; en un CSV, neutralizando lo que empieza por `=`, `+`,
`-` o `@`.

**Sin datos no es cero.** Lo que no se puede saber (sin planning, sin
extractos del banco) llega como `null` o con `"estado": "sin_datos"` y un
`detalle` que dice por qué: el sitio lo enseña así, nunca como 0.

**No lleva ningún IBAN entero.** El export (`export --v2` y
`GET /api/v2/exportar`) enmascara cada IBAN, también el que va dentro de un
texto: los avisos de las cuentas (F2, F3, F5, F6, F10) lo escriben y de ahí
pasa a los `motivos`, que salen como «Bloqueada: El IBAN NL..5689 de la
factura no es pagable…» (el país y las cuatro últimas cifras: basta para
reconocer la cuenta al teléfono y no para pagarle). `comprobar_v2` busca un
IBAN dentro de cada texto y el test lo comprueba con F2 y F3 abiertos.

El servidor lo hace cumplir también en las lecturas, según de dónde venga la
petición:

| Quién pide | IBAN | Órdenes (`POST /api/v2/acciones`) |
| --- | --- | --- |
| La app (`/app`) o la consola (`/consola`), del mismo origen que la API, o un programa sin navegador | Enteros, donde los haya (el registro de cuentas, la vista de un proveedor, los avisos): la consola es donde se verifican | Sí, con su permiso |
| Un sitio en un origen declarado con `--origen` (`http://localhost:5173`) | Enmascarados en **toda** respuesta de `/api/v2` | **No**: `403`. Verificar un IBAN, marcar un pago o anular un aviso se firma en la consola |

El portal de consulta, cuando exista, no tendrá ni eso: su base no guarda
ningún IBAN ([portal-consulta.md](portal-consulta.md)).

**El token de un sitio propio es el de una persona de solo lectura, y no va
dentro del sitio.** Ver «Ejemplo» al final de esta sección.

### Lo de arriba

```
{
  "contrato": "2.3",
  "generado_en",                      // instante UTC del export
  "hoy",                              // el día con que se calcula (Ámsterdam)
  "estado_del", "al_dia",             // de qué día es el estado de las facturas;
                                      // false: falta `bms-agent recalcular --diaria`
  "panel": {...},                     // el panel principal (§17), abajo
  "facturas": [ {...} ],              // todas, la más urgente primero (la búsqueda sin filtros)
  "proveedores": [ {...} ],           // como GET /api/v2/proveedores
  "clientes": [ {...} ],              // como GET /api/v2/clientes
  "objetos": {...},                   // como GET /api/v2/objetos
  "ordenes_compra": [ {...} ],        // como GET /api/v2/ordenes
  "btw": {...},                       // como GET /api/v2/btw
  "flujo_caja": {...},                // como GET /api/v2/flujo
  "excepciones": [ {...} ],           // las abiertas, la más urgente primero
  "fuentes": [ {...} ],               // de cuándo es lo último de cada fuente (Z1)
  "filtros": [ {...} ]                // los filtros de la búsqueda, como /api/v2/contrato
}
```

### El panel principal (`panel`, `GET /api/v2/panel`)

```
"panel": {
  "contrato", "hoy", "estado_del", "al_dia",
  "fuentes_caducadas": [ {"fuente", "tipo", "exportado", "edad", "limite"} ],
  "dinero_entra": {                   // lo que se espera cobrar: lo que queda de las ventas
                                      // (solo deudas: un abono, tampoco el de un proveedor,
                                      // no es un cobro con fecha; ver «La cartera»)
    "facturas", "vencidas",
    "pendiente_cent", "vencido_cent", "semana_cent", "mes_cent",
    "proximos_30_cent", "sin_fecha_cent"          // y cada uno sin _cent, como texto
  },
  "dinero_sale": {                    // lo mismo, lo que se espera pagar de las compras
    "facturas", "vencidas",
    "pendiente_cent", "vencido_cent", "semana_cent", "mes_cent",
    "proximos_30_cent", "sin_fecha_cent"
  },
  "caja": {
    "ventanas": {"vencido"|"semana"|"mes"|"proximos_30"|"total":
                 {"entrada_cent", "salida_cent", "neto_cent"}},
    "fechas",                         // de qué día a qué día es cada ventana
    "cobrado_mes_cent", "pagado_mes_cent",        // lo que movió el banco este mes
    "estimado": {"importe_cent", "nota", ...}     // trabajo sin facturar y planificado,
                                                  // aparte; null sin planning
  },
  "facturacion": {"estado": "ok"|"sin_datos", "detalle",
                  "sin_facturar",               // V6: trabajo validado sin facturar
                  "periodos_sin_factura",       // V8: periodos sin ninguna factura
                  "horas_sin_facturar",         // V5: horas validadas que no están en la
                                                // venta que cobra su periodo
                  "diferencias_planning"},
  "ordenes_compra": {
    "activas",                        // cuántas PO activas hay, de los dos lados
    "cliente": {"activas", "valor_cent", "consumido_cent", "restante_cent"},
                                      // lo que BMS puede facturar a sus clientes
    "proveedor": {"activas", "valor_cent", "consumido_cent", "restante_cent"},
                                      // lo que los proveedores pueden facturar a BMS
    "cerca_del_limite", "cerca_de_caducar", "agotamiento_previsto",   // de las activas
    "caducadas"                       // ya pasó su fin y su aviso (P7) sigue pendiente
  },
  "btw": {"trimestre", "estado", "ingresos_cent", "iva_repercutido_cent",
          "iva_deducible_cent", "saldo_cent", "limite_presentacion", "limite_pago",
          "proximo_plazo", "plazos_pasados", "por_presentar", "revisar"},
  "atencion": {
    "compras_vencidas", "ventas_vencidas",        // {"facturas", "pendiente_cent", "lista"}
    "categorias": [ {"clave", "titulo", "activos", "aceptados", "reglas",
                     "facturas", "factura_ids"} ],
    "hallazgos", "aceptados",                     // avisos activos y aceptados
    "excepciones", "bloqueadas", "urgentes", "atencion"
  }
}
```

Los dos lados de las PO no se suman nunca: una PO de cliente y una de
proveedor no son la misma cifra. Cada PO de las cuatro listas lleva su `lado`.
Las ventanas son las del flujo de caja: «esta semana» va de hoy al domingo,
«este mes» de hoy al último día, «próximos 30 días» cuenta hoy; lo vencido va
aparte. Las categorías de `atencion` son, en este orden: `iban`, `duplicados`,
`iva`, `planning`, `sin_facturar`, `ordenes_compra`, `vencidas`,
`faltan_datos`, `lecturas_dudosas` y `otros`; cada regla va a una sola.

### Una factura (`facturas[]`, la búsqueda y la lista)

```
"facturas": [ {
  "id", "numero", "sentido",          // entrante (compra) | saliente (venta)
  "tipo",                             // factura | nota_credito
  "contraparte",                      // el nombre impreso: TEXTO DE UN DOCUMENTO
  "proveedor_id", "cliente_id",       // del maestro, o null
  "fecha_factura", "vencimiento",     // el vencimiento efectivo
  "periodo_desde", "periodo_hasta",   // de la cabecera o, si no lo imprime, de sus
                                      // líneas: sus fechas o la semana impresa
                                      // («semana 37», con el año de la fecha)
  "base_cent", "total_cent", "total",
  "pendiente_cent", "pendiente",      // lo que queda (null si no está en euros: X1)
  "estado_pago",                      // pendiente | vencida | pagada | anulada | acreditada
  "estado_revision",                  // sin_revisar | necesita_revision | revisada
  "calidad",                          // faltante | discrepancia | anomalia | dudoso |
                                      // verificado | null (neutra: nunca verde)
  "nivel", "puntos", "motivos",       // normal | atencion | urgente | bloqueada, y por qué
  "editada", "suplementada", "corregida", "sin_resolver",   // las marcas de edición (§11)
  "cuenta",                           // false: anulada, fusionada o sustituida
  "objetos",                          // los códigos de sus Objetos
  "etiqueta",                         // «Sin objeciones del sistema»... nunca «aprobada»
  "razones"                           // 2.1: sus hallazgos pendientes, lo más urgente
                                      // primero: {"id", "regla", "severidad", "estado",
                                      // "resultado", "valores"}
} ]
```

### Proveedores, clientes, Objetos y órdenes de compra

```
"proveedores": [ {"id", "nombre", "facturas", "pendiente_cent", "vencido_cent", "nivel",
                  "razones", "documentos", ...} ],
"clientes":    [ {"id", "nombre", "facturas", "pendiente_cent", "vencido_cent", "nivel",
                  "razones", "documentos", ...} ],
"objetos": {
  "objetos": [ {"id", "codigo", "nombre", "cliente", "siempre", "ano", "nivel", "razones"} ],
  "sin_objeto": {"imputado", "sin_imputar", "total"},
  "totales": {"ingresos_cent", "costes_cent", "sin_base", ...}
},
"ordenes_compra": [ {"id", "numero", "lado", "parte", "valor_cent", "consumido_cent",
                     "restante_cent", "fecha_fin", "cerrada", "nivel", "razones", ...} ]
```

Cada `siempre`, `ano`, `imputado`, `sin_imputar`, `total` y `totales` lleva
`ingresos_cent`, `costes_cent`, `margen_cent` y `margen_pb` (sin IVA). Los
ingresos de cada Objeto más `sin_objeto.total` son la base de todas las
ventas que cuentan (`totales.ingresos_cent`), y lo mismo con los costes: un
test lo comprueba con escenarios al azar. `sin_base` cuenta las facturas sin
base o en otra moneda, que no suman en ningún sitio hasta que se corrigen.

### El BTW y el flujo de caja

```
"btw": {"hoy", "configuracion", "actual", "por_presentar", "anteriores",
        "ano_hasta_hoy", "sin_fecha"},
"flujo_caja": {"hoy", "ventanas", "esperado", "real", "estimado", "facturas", "fuentes"}
```

`btw.actual` es el trimestre en curso con sus rúbricas (`cifras`), lo que hay
que revisar y sus plazos; el detalle de cualquier trimestre está en
`GET /api/v2/btw/AAAA-TN`. El agente no presenta nada: el estado
«presentado» lo anota una persona después de presentarlo en el portal.

### Las lecturas de `/api/v2`

Todas piden el token personal de quien lee (`X-BMS-Token`) con el permiso
`ver_facturas`; sin token, `401`; sin permiso, `403`; lo que no existe, `404`;
un parámetro que no admiten (en **todas**, también las de pasos anteriores),
uno repetido o un valor que no se entiende, `400` (no se ignora en silencio).
Un parámetro admitido pero vacío (`?nivel=`, `?desde=&hasta=`) es como no
ponerlo; en la búsqueda, un filtro vacío es un `400` («lleva un valor»).

| Lectura | Qué da | Parámetros |
| --- | --- | --- |
| `GET /api/v2/contrato` | La versión, las lecturas y los filtros de la búsqueda | — |
| `GET /api/v2/yo` | Quién es el token y sus permisos | — |
| `GET /api/v2/panel` | El panel principal | — |
| `GET /api/v2/buscar` | La búsqueda (abajo) | los filtros, `orden`, `limite`, `pagina` |
| `GET /api/v2/facturas` | Todas, la más urgente primero | `nivel` (`normal`, `atencion`, `urgente`, `bloqueada`; otro, `400`) |
| `GET /api/v2/facturas/N` | La ficha: cada campo con su valor, su original, su fuente, sus marcas y su calidad | — |
| `GET /api/v2/facturas/N/historial` | La historia (§12): original, extracciones, sus relaciones en los dos sentidos (la que abona, sustituye o corrige, y la abonada, sustituida o corregida), cada cambio con quién, cuándo y por qué (también el de una relación que la tiene de destino), revisiones, avisos y su resolución, excepciones | — |
| `GET /api/v2/facturas/N/original` | El original, como fichero adjunto (sus bytes tal cual, con su tipo). Cada descarga queda en la auditoría (`documento_abierto`). Solo desde la consola: desde otro origen, `403` y sin CORS | — |
| `GET /api/v2/excepciones` | Las abiertas | — |
| `GET /api/v2/personas` | Las personas activas | — |
| `GET /api/v2/recursos` | Las personas y recursos del maestro (los de las líneas de horas), para imputar una línea a uno de ellos | — |
| `GET /api/v2/proveedores` | Los proveedores | — |
| `GET /api/v2/proveedores/N` | La vista de un proveedor (§3), con su registro de cuentas (IBAN enmascarados si se pide desde otro origen) | — |
| `GET /api/v2/clientes` | Los clientes | — |
| `GET /api/v2/clientes/N` | La vista de un cliente (§4) | — |
| `GET /api/v2/objetos` | Los Objetos con ingresos, costes y margen, y lo sin Objeto | — |
| `GET /api/v2/objetos/N` | La vista de un Objeto (§5): PO, horas, economía por mes y por semana, sus facturas | `desde` y `hasta`, los dos juntos (el periodo de «ingresos»; sin ninguno, el mes en curso hasta hoy; uno solo, `400`) |
| `GET /api/v2/ordenes` | Las órdenes de compra | — |
| `GET /api/v2/ordenes/N` | La ficha de una PO (§6) | — |
| `GET /api/v2/relaciones` | Las relaciones propuestas | — |
| `GET /api/v2/btw` | El BTW de un vistazo | — |
| `GET /api/v2/btw/AAAA-TN` | Un trimestre | — |
| `GET /api/v2/btw/AAAA-TN/hoja` | Su hoja de trabajo y su sha256 | — |
| `GET /api/v2/btw/AAAA-TN/hoja.csv` | La hoja como fichero adjunto, con los bytes exactos que se hashean (su sha256 es el que se anota al presentar). Solo desde la consola | — |
| `GET /api/v2/flujo` | El flujo de caja | `desde`, `hasta` (un periodo pedido) |
| `GET /api/v2/fuentes` | De cuándo es cada fuente | — |
| `GET /api/v2/cuentas` | El registro de cuentas de los proveedores (IBAN enmascarados si se pide desde otro origen) | — |
| `GET /api/v2/acciones` | Las órdenes que existen, con sus parámetros | — |
| `GET /api/v2/exportar` | El contrato v2 entero, como `export --v2` | — |
| `GET /api/v2/importaciones` | Las últimas 30 importaciones (qué, de cuándo, quién, cómo acabó), lo que se puede importar (`tipos`: cada `fuente` y `tipo`), el tamaño máximo de un fichero (`limite_bytes`) y de cuándo es cada fuente (`fuentes`, como `GET /api/v2/fuentes`) | — |
| `GET /api/v2/lectura` | Lo que ha costado leer los PDF y lo que costaría uno más, de lo que guarda el almacén (como `bms-agent coste`, sin llamar a la API): `extracciones`, `documentos`, `coste_usd_micro` (millonésimas de dólar), `por_documento_usd_micro`, `pasadas` (las diez últimas), `estimacion` (horquilla por documento) y `lee_aqui` (si este servidor lee PDF: en la instalación nativa y en Docker, no) | — |
| `GET /api/v2/empresa` | La identidad de BM Support BV que usan las reglas (`nombre`, `otros_nombres`, `btw_id`, `kvk`, `cuentas_propias`, `completa`). Se cambia con `empresa.bat`, no desde la app | — |
| `GET /api/v2/cartera` | Lo que nos deben (`sentido=saliente`) o lo que debemos (`sentido=entrante`): los totales del panel, la antigüedad por tramos, cada empresa, lo retenido y lo que espera aparte (abajo, «La cartera») | `sentido` (obligatorio: sin él, o con otro valor, `400`) |
| `GET /api/v2/pagos/propuestas` | Los pagos que el banco propuso y esperan a una persona, cada uno con su línea del banco, su factura y las tres coincidencias | `sentido` (de la factura) |
| `GET /api/v2/movimientos` | Las líneas del banco, la más reciente primero: por defecto, solo las sin casar | `sin_casar` (`si` por defecto, o `no`), `signo` (`entrada` o `salida`), `desde`, `hasta`, `texto`, `limite` (de 1 a 1000, 200) |
| `GET /api/v2/clientes/N/documentos` | La carpeta de un cliente: los documentos que el sistema ya le enlaza (abajo, «El archivo de una parte») | — |
| `GET /api/v2/proveedores/N/documentos` | La carpeta de un proveedor | — |
| `GET /api/v2/documentos/N/original` | Cualquier documento guardado, como fichero adjunto, con las mismas cabeceras que el original de una factura. Cada descarga queda en la auditoría (`documento_abierto`). Solo desde la app o la consola: desde otro origen, `403` y sin CORS | — |
| `GET /api/v2/aislamiento` | Lo que dice la banda roja, por papeles: `aplica` (solo en la instalación nativa), `entorno` (`nativo`, `contenedor` o `local`), `correcto` y `papeles` (`papel`, `bien` y `estado`: `correcto`, `falla`, `sin_comprobar` o `caducada`, comprobado hace demasiado o con una fecha que no vale). No copia el texto de los problemas (sale de un fichero que se puede escribir): `estado` sale solo de cómo empieza cada problema | — |

### Los errores (`error` y `codigo`)

Toda respuesta de error de `/api/v2` (y de la puerta que comparten todas las
rutas: el `Host`, el `Origin`, el cuerpo de un `POST`) es un objeto JSON con
dos claves, más `tipo` en las órdenes:

```
{"error": "la factura 12 cambio desde que se cargo: vuelve a mirarla",   // español, para la CLI y la auditoría
 "codigo": "conflicto",                                                  // estable: de él sale el texto del sitio
 "tipo": "Conflicto"}                                                    // solo en POST /api/v2/acciones
```

`error` puede cambiar de redacción en cualquier versión; **`codigo` no**: un
sitio decide qué decir (y en qué idioma) por el `codigo`. La app de la oficina
escribe el texto neerlandés o inglés de cada uno desde los catálogos
(`src/bms_agent/textos/nl.json` y `en.json`, apartado `errores`) y enseña la
frase en español solo dentro de un desplegable «Technische details». Un
código nuevo se añade (2.x → 2.(x+1)); uno que existe no cambia de
significado. La lista la da `servicios.CODIGOS_ERROR`, y el test
(`tests/test_codigos_error.py`) comprueba que cada uno tiene su texto en los
dos idiomas y que cada error que escribe `serve.py` lleva el suyo.

| `codigo` | HTTP | Cuándo |
| --- | --- | --- |
| `no_autenticado` | 401 | Sin token personal, o uno que no vale (y el `403` de `/api/ejecutar` sin el token del servidor) |
| `sin_permiso` | 403 | La persona no tiene el permiso de la lectura o de la orden |
| `segunda_persona` | 403 | La regla de las dos personas: lo hace o lo firma otra persona (quien cambió algo no lo revisa ni lo verifica él mismo, una anulación que pide segunda firma, nadie firma la suya) |
| `otro_origen` | 403 | Una orden o una descarga desde un sitio declarado con `--origen`: solo desde `/app` o `/consola` |
| `origen_no_permitido` | 403 | Un `Origin` que no está en la lista |
| `host_no_permitido` | 421 | Un `Host` que no es `127.0.0.1:<puerto>` ni `localhost:<puerto>` |
| `no_existe` | 404 | La ruta, la factura, la fila o la persona no existen |
| `conflicto` | 409 | La fila cambió desde que se leyó (su `rev`, o la huella de la factura o del hallazgo): hay que volver a cargarla |
| `peticion_repetida` | 409 | El mismo `peticion_id` llega con otra orden o de otra persona |
| `no_anulable` | 409 | La regla de ese hallazgo no se puede anular: se corrige el dato o se resuelve el caso |
| `no_revisable` | 409 | La factura tiene algo pendiente que pide revisión |
| `bloqueo_abierto` | 409 | Un hallazgo que bloquea sigue abierto: la excepción no se resuelve |
| `estado_no_valido` | 409 | La orden no tiene sentido en el estado en que está (el hallazgo, la excepción, el trimestre, el pago, la prioridad) o la base no la admite |
| `campo_no_editable` | 409 | El campo lo pone el sistema |
| `campo_de_otro_sistema` | 409 | El campo es de Exact o de TRNSPRNT: se corrige allí |
| `falta_motivo` | 400 | La orden pide un motivo (anular un hallazgo, de al menos 10 caracteres) |
| `iban_no_valido` | 400 | El IBAN no pasa el dígito de control |
| `orden_desconocida` | 400 | No hay ninguna orden con ese nombre |
| `invalido` | 400 | Un parámetro, un filtro o un dato que no se entiende, o un cuerpo que no es `{accion, peticion_id, datos}` |
| `tipo_no_admitido` | 415 | El cuerpo no es `application/json` |
| `demasiado_grande` | 413 | El cuerpo pasa del límite |
| `fichero_no_reconocido` | 400 | Al importar sin decir qué es: ninguna clase de fichero lo reconoce |
| `tipo_ambiguo` | 400 | Al importar sin decir qué es: lo reconocen varias; van en `candidatos` (`fuente`, `tipo`) |
| `fichero_no_valido` | 400 | El fichero no se lee como la clase elegida (columnas, codificación, XML, YAML, una fecha de exportación futura), o rompe el lector: un campo de CSV de más de 128 KB, un XML o YAML que anida demasiado, un YAML de PO con anclas o alias (`&`, `*`: unos cientos de bytes que se expandirían a gigas), o cualquier fallo del lector que nadie previó (sin su texto) |
| `datos_de_prueba` | 400 | Un fichero de los datos de prueba en la base de verdad, o uno de verdad en la de prueba |
| `pide_confirmacion` | 409 | Un planning que dejaría sin valer mucho del de ahora o con semanas vacías: se repite con `confirmar` |
| `fichero_demasiado_grande` | 413 | El fichero que se importa pasa de 8 MB |

Un fallo de verdad del servidor (un `500`) no es un error de la orden y no
lleva código: la orden no se aplica (va entera o nada) y la app dice «Er ging
iets mis».

### Importar desde la app (`POST /api/v2/importar`)

La pantalla «Importeren» de la app sube un fichero (una exportación de Exact,
un extracto del banco CAMT.053, MT940 o CSV, la exportación del planning de
TRNSPRNT, una hoja de PO o un maestro) y lo importa con **la misma orden** que
`bms-agent importar` (`importadores.registrar.importar_fichero`): la persona y
su permiso `importar_datos` (y `cambiar_po` para las PO), todo o nada, cada
lote en la auditoría, la pasada del motor de reglas al final y la guarda de los
datos de prueba. El fichero no se escribe en ninguna carpeta: se lee en memoria
(`importar_web.py`). Ni procesos ni red.

```
POST /api/v2/importar        X-BMS-Token: <token personal>     Content-Type: application/json
{"fichero": "crediteuren.csv",           // el nombre (solo un nombre: no se abre como ruta)
 "contenido": "77u/Q3JlZGl0ZX...",       // los bytes, en base64
 "fuente": "exact", "tipo": "proveedores",  // los dos o ninguno: sin ellos se detecta
 "simular": true,                        // se hace entero y se deshace: no guarda nada
 "exportado": "2026-10-16",              // opcional: el día en que se sacó (la frescura, Z1)
 "confirmar": false}                     // solo el planning (pide_confirmacion)
```

Contesta `{"importacion": {...}}`:

```
"importacion": {"fichero", "mapeo", "fuente", "tipo", "simulada",
                "lotes": [ {"tipo", "estado", "repetida", "importacion_id", "filas_leidas",
                            "aceptadas", "rechazadas", "rechazos", "nuevos", "nuevos_por_tabla",
                            "cambiados", "sin_resolver", "retirados", "cuentas", "avisos"} ],
                "hallazgos": {"detectado": 2, "cerrado_automatico": 1, ...},
                "pagos": {"casados", "propuestas"}}
```

`nuevos` cuenta lo nuevo de la tabla del lote (un cliente nuevo es `1`, aunque
traiga su alias); `nuevos_por_tabla`, cada fila nueva por su tabla. Cada
`rechazos[]` lleva `fila` (0 es el fichero entero), `codigo` (`fila`,
`referencia`, `X1`, `duplicada`, `sistema`) y `motivo`; `motivo` y `avisos` son
frases en español para el soporte (la app dice el código en neerlandés o en
inglés y deja la frase plegada). Simulando, `importacion_id` es `null`.

La app **siempre simula primero** y enseña lo que se añadiría, cambiaría o se
rechazaría; solo después, con un botón aparte, manda la misma petición con
`"simular": false`. Las mismas puertas que una orden: el `Host` y el `Origin`
de siempre, nunca desde otro origen (`403 otro_origen`), el token (`401`), el
permiso (`403`, antes de leer el fichero), cuerpo JSON con claves conocidas
(`400 invalido`) y un límite propio: 8 MB de fichero (`413
fichero_demasiado_grande`). El mismo fichero dos veces no entra dos veces
(`repetida`). Una importación de verdad se ancla al terminar, como cualquier
orden; una simulación no escribe nada.

### La búsqueda (`GET /api/v2/buscar`)

```
GET /api/v2/buscar?proveedor_id=3&pendiente=si&orden=vencimiento
→ {"busqueda": {"filtros", "orden", "limite", "pagina", "total",
                "suma": {"cuentan", "no_cuentan", "mezcla",
                         "total_cent", "base_cent", "pendiente_cent",
                         "compras": {"facturas", "total_cent", "base_cent", "pendiente_cent"},
                         "ventas": {"facturas", "total_cent", "base_cent", "pendiente_cent"}},
                "estado_del", "al_dia", "facturas": [ ...como facturas[]... ]}}
```

`total` cuenta todo lo encontrado, pero **solo suman las facturas que
cuentan** (ni anuladas, ni copias fusionadas, ni sustituidas o corregidas por
otra), con la misma regla que la vista de un proveedor o de un cliente: una
búsqueda por `proveedor_id` suma lo que su vista llama «facturado». Las que
no cuentan se dicen en `no_cuentan`. Compras y ventas no se suman entre sí: lo
pendiente de una compra es lo que BMS debe y el de una venta lo que le deben.
Si lo encontrado es de un solo sentido, `total_cent`, `base_cent` y
`pendiente_cent` son los suyos; si hay de los dos (`mezcla`), son `null` y las
cifras están en `compras` y `ventas`.

Los filtros se suman (y); dentro de uno de lista, basta uno de sus valores
(`estado_pago=pendiente,vencida` o el parámetro repetido). Cada filtro es un
fragmento fijo de SQL con su valor como parámetro: lo que se escribe no entra
nunca en la consulta. `limite` va de 1 a 1000 (200 por defecto). `orden`:
`prioridad` (por defecto), `fecha`, `vencimiento`, `importe` o `numero`.

| Filtro | §18 | Qué pide |
| --- | --- | --- |
| `numero` | Invoice number | Parte del número, sin espacios, puntos, guiones ni barras |
| `texto` | — | Parte del número o del nombre impreso de la contraparte, sin distinguir mayúsculas (tampoco en «Öztürk» o «Élan») |
| `sentido` | — | `entrante` (compras) o `saliente` (ventas) |
| `tipo` | — | `factura` o `nota_credito` (abono); el «Tipo de documento» del archivo |
| `proveedor_id` | Provider | Del proveedor del maestro (un id de más de 19 cifras, `400`) |
| `cliente_id` | Client | Sus ventas y las compras imputadas a un Objeto suyo |
| `objeto_id` | Object | Con alguna línea imputada al Objeto |
| `orden_compra_id` | PO | Imputada a la PO, o que la imprime |
| `po` | PO | Con ese número de PO impreso o imputado |
| `fecha_desde`, `fecha_hasta` | Period | Fecha de factura (AAAA-MM-DD, incluidas) |
| `periodo_desde`, `periodo_hasta` | Period | Periodo de prestación que se cruza con esas fechas: el de la cabecera o el de sus líneas, también si solo imprimen la semana |
| `trimestre` | Period | Fecha de factura en el trimestre del BTW (`2026-T3`) |
| `vence_desde`, `vence_hasta` | Due date | Vencimiento efectivo |
| `estado_pago` | Payment status | `pendiente`, `vencida`, `pagada`, `anulada`, `acreditada` |
| `estado_revision` | Review status | `sin_revisar`, `necesita_revision`, `revisada` |
| `nivel` | Priority | `normal`, `atencion`, `urgente`, `bloqueada` |
| `calidad` | Data-quality status | `faltante`, `discrepancia`, `anomalia`, `dudoso`, `verificado`, `neutra` |
| `edicion` | Manual edits | `editada`, `suplementada`, `corregida`, `sin_resolver` |
| `pendiente` | Outstanding | `si` (pendiente o vencida) o `no` |
| `vencida` | Overdue | `si` o `no` |
| `pagada` | Paid | `si` o `no` |
| `anulada_acreditada` | Cancelled / credited | `si` o `no` |
| `excepcion` | — | Con una excepción abierta: `si` o `no` |
| `importe_min`, `importe_max` | — | Importe sin IVA en valor absoluto (`10000` o `10000,50`, sin separador de miles) |

Lo que depende del estado (pago, revisión, prioridad, calidad, ediciones) sale
de la caché que rehace cada pasada del motor y la diaria: `estado_del` dice de
qué día es, y `al_dia` si es el de hoy.

### Cuentas por cobrar y por pagar (paso 16)

Tres lecturas para las dos pantallas del dinero de la app. Solo leen: confirmar
o retirar un pago propuesto y apuntar uno ya hecho son órdenes
(`confirmar_pago`, `retirar_pago` y `marcar_pagada` en `POST /api/v2/acciones`,
con el permiso `marcar_pagada`). Nada de esto paga, aprueba un pago ni prepara
una transferencia o un fichero de pagos.

#### La cartera (`GET /api/v2/cartera`)

```
GET /api/v2/cartera?sentido=saliente
→ {"cartera": {
    "sentido",                        // saliente: por cobrar (ventas); entrante: por pagar (compras)
    "hoy", "estado_del", "al_dia",
    "totales": {"facturas", "vencidas", "pendiente_cent", "vencido_cent", "semana_cent",
                "mes_cent", "proximos_30_cent", "sin_fecha_cent"},
                                      // = panel.dinero_entra (o dinero_sale), al céntimo
    "fechas",                         // de qué día a qué día es cada ventana (= panel.caja.fechas)
    "movido_mes_cent",                // lo cobrado (o pagado) que el banco movió este mes
    "tramos": [ {"clave", "dias_desde", "dias_hasta", "vence_desde", "vence_hasta",
                 "facturas", "importe_cent"} ],
    "retenido": {"facturas", "importe_cent",       // con algo que bloquea o retiene
                 "lista": [ {"id", "numero", "parte_id", "parte", "pendiente_cent",
                             "vencimiento", "dias", "retenida", "nivel", "razones"} ]},
                                      // 2.3: cada una, la que vence antes primero
    "sin_retener": {"facturas", "importe_cent"},
    "partes": [ {"id", "nombre", "facturas", "vencidas", "pendiente_cent", "vencido_cent",
                 "retenido_cent", "mas_antigua_dias", "nivel", "puntos", "razones",
                 "plazo_de_pago": {"pagadas", "media_dias", "tarde"}} ],
    "por_confirmar": {"pagos", "importe_cent"},    // aparte: no suman
    "sin_casar": {"movimientos", "importe_cent"},
    "abonos_sin_enlazar": {"facturas", "importe_cent",
                           "lista": [ {"id", "numero", "contraparte", "parte_id", "parte",
                                       "fecha_factura", "pendiente_cent"} ]},
    "sin_importe",                    // facturas en juego sin importe en euros (X1)
    "esta_semana": {"hasta",          // 2.3: el domingo (= fechas.semana[1])
                    "retenido": {"facturas", "importe_cent"},
                    "sin_retener": {"facturas", "importe_cent"},
                    "facturas": [ {…como retenido.lista} ]},
                                      // lo vencido y lo que vence hasta el domingo:
                                      // suma vencido_cent + semana_cent
    "avisos_pago": [ {"regla",        // 2.3: K2, K3, K4, K5, K8, K9, en ese orden
                      "facturas": [ {"id", "numero", "parte_id", "parte"} ]} ]
  }}
```

`sentido` es obligatorio: sumar lo que nos deben con lo que debemos no es
ninguna cifra. Cada `_cent` lleva su texto al lado, como en todo el contrato
(`"pendiente": "36.270,36"`).

**Una sola cuenta, repartida de tres formas.** La cartera sale de las mismas
partidas que el panel (`flujo_caja.datos`: lo que queda de cada deuda en juego,
por su vencimiento efectivo) y sus `totales` de la misma función
(`consultas._bloque_dinero`): la tarjeta del inicio y la cabecera de la
pantalla dicen los mismos céntimos, y un test lo comprueba. Los tramos y las
empresas reparten esas mismas partidas, así que:

- los seis tramos suman `totales.pendiente_cent` (y sus `facturas`, las de
  `totales`);
- los cuatro tramos de retraso (`1_30` a `mas_de_90`) suman `vencido_cent`, y
  `sin_fecha` es `sin_fecha_cent`;
- las empresas suman lo pendiente, lo vencido y las facturas; `retenido` más
  `sin_retener` es el total, y las empresas suman lo retenido.

**Los tramos** son los días de retraso desde el vencimiento efectivo, con los
dos extremos incluidos, siempre en este orden: `al_corriente` (aún no ha
vencido: vence hoy o después), `1_30`, `31_60`, `61_90`, `mas_de_90` y
`sin_fecha` (sin vencimiento impreso ni plazo: no se adivina). `vence_desde` y
`vence_hasta` son los vencimientos que caen en el tramo, listos para abrir la
búsqueda filtrada
(`/api/v2/buscar?sentido=saliente&pendiente=si&vence_desde=…&vence_hasta=…`);
`null` es sin límite. La revisión de Aurora los quiere a la vista en cobrar y
plegados en pagar: eso lo decide la pantalla; la lectura da los dos.

**Las empresas** van en el orden de las listas (su prioridad; a igualdad, lo
vencido, lo pendiente y el nombre). Las facturas sin cliente (o proveedor) del
maestro van juntas en una fila con `id` y `nombre` `null`, al final, para que
las empresas sumen el total. `mas_antigua_dias` son los días de retraso de su
factura vencida más antigua (`null` si no tiene ninguna vencida);
`plazo_de_pago` es lo de su vista («paga de media en `media_dias` días, `tarde`
veces tarde»); `razones`, como en las listas.

**Lo pendiente de una empresa aquí no es lo de su vista.** La vista de un
cliente o un proveedor (y su fila en `GET /api/v2/clientes`) resta sus abonos
sin enlazar: lo que la acredita es suyo aunque todavía no diga de qué factura
(R4). La cartera, como el panel, solo cuenta deudas y los da aparte, en
`abonos_sin_enlazar`. Las dos cifras se explican una con la otra: lo pendiente
de la vista es lo de la cartera más sus abonos de esa lista (un test lo
comprueba con cada empresa de la base de prueba).

**Lo retenido** es lo de las facturas con algún hallazgo activo (ni aceptado ni
cerrado) que bloquea o retiene (IBAN sin verificar, posible duplicado, horas
que no cuadran…) o que están Bloqueadas (también si alguien las subió a mano).
Un aviso, como K1 «vencida sin pagar», no retiene. Es lo que la revisión llama
«Con objeciones o bloqueado» frente a «Sin objeciones del sistema»; nunca
«aprobado».

**Lo que va aparte, sin sumar:** `por_confirmar` son los pagos propuestos de las
facturas de ese sentido que esperan a una persona (el detalle, abajo);
`sin_casar`, lo que queda sin ninguna factura de las líneas del banco de ese
lado (ingresos para cobrar, cargos para pagar; las mismas que
`GET /api/v2/movimientos`); `abonos_sin_enlazar`, los abonos de ese sentido con
algo por descontar (importes negativos); `sin_importe`, cuántas facturas en
juego no tienen importe en euros (X1) y por eso no suman en ningún sitio.

#### Los pagos que esperan a una persona (`GET /api/v2/pagos/propuestas`)

```
→ {"propuestas": [ {"id", "rev", "lado", "importe_cent", "fecha_pago", "regla",
                    "coincidencias": {"referencia", "importe", "contraparte"},
                    "factura": {"id", "numero", "sentido", "tipo", "contraparte",
                                "proveedor_id", "cliente_id", "parte", "total_cent",
                                "pendiente_cent", "vencimiento", "estado_pago"},
                    "movimiento": {"id", "fecha", "importe_cent", "contraparte",
                                   "contraparte_iban", "concepto", "referencia",
                                   "referencia_e2e"}} ]}
```

Cada uno es un pago que el banco casó a medias con una factura (dos de las tres
coincidencias, o las tres con el importe solo dentro de la tolerancia: ver
`pagos.py`). `lado` es `cobro` o `pago` (por dónde va el dinero);
`coincidencias` dice en qué coincidieron la línea del banco y la factura (lo
que `pagos.casar` apuntó en `regla`); `factura.pendiente_cent` es lo que queda
de la factura, que una propuesta aún no baja. Lo más antiguo primero; con
`sentido`, solo los de las ventas o los de las compras.

Una persona con el permiso `marcar_pagada` la confirma o la retira con su
`rev` (si cambió desde que se leyó, `409 conflicto`):

```js
// Confirmar: el motivo es opcional
{"accion": "confirmar_pago", "peticion_id": "…", "datos": {"aplicacion_id": 7, "rev": 0}}
// No es este: el motivo es obligatorio. Lo que dice Exact no se retira aquí: se corrige en Exact
{"accion": "retirar_pago", "peticion_id": "…", "datos": {"aplicacion_id": 7, "rev": 0,
                                                         "motivo": "Es de la otra factura"}}
// Apuntar un pago ya hecho, con motivo; opcional, la línea del banco sin casar y el justificante
{"accion": "marcar_pagada", "peticion_id": "…", "datos": {"factura_id": 12, "rev": 3,
  "motivo": "Pagado en efectivo, recibo en la carpeta", "movimiento_id": 41}}
```

Lo retirado no se vuelve a proponer. «Pagada» siempre con su fuente (el banco,
Exact o lo apuntado por una persona: `pagos` en la ficha de la factura); manda
el banco, luego Exact y luego lo apuntado a mano, y K3 avisa si el banco no trae
lo apuntado.

#### Las líneas del banco (`GET /api/v2/movimientos`)

```
GET /api/v2/movimientos?signo=entrada
→ {"movimientos": {"hoy", "filtros", "limite", "total",
                   "entradas": {"movimientos", "importe_cent", "sin_casar_cent"},
                   "salidas": {"movimientos", "importe_cent", "sin_casar_cent"},
                   "lista": [ {"id", "fecha", "fecha_valor", "importe_cent", "moneda",
                               "importe_crudo", "abierto", "resto_cent", "propia",
                               "contraparte", "contraparte_iban", "concepto",
                               "referencia", "referencia_e2e", "cuenta_propia_iban",
                               "confirmadas", "propuestas", "dias"} ]}}
```

Por defecto, solo las **sin casar**: lo que queda de ellas sin ninguna factura,
propuesta ni confirmada (lo mismo que mira casar, con la tolerancia de la
política). Es la lista de la que se elige una línea al apuntar un pago
(`marcar_pagada` con su `movimiento_id`) y lo que K7 avisará a los pocos días.
No salen los traspasos entre cuentas propias ni lo que va a un beneficiario
conocido (no pagan facturas) ni lo que no está en euros (X1). Con
`sin_casar=no` salen todas, cada una con lo que le queda (`resto_cent`), si
cuenta como sin casar (`abierto`) y si es `propia`; una en otra moneda lleva
`importe_cent` `null` y su literal en `importe_crudo`.

Los importes llevan el signo del banco (un cargo es negativo). `dias` es la edad
de la línea; `confirmadas` y `propuestas`, cuántos pagos de facturas tiene.
`total` y las sumas son de todas las que cumplen los filtros, no solo de las que
caben en `limite`. Filtros: `signo` (`entrada`: ingresos; `salida`: cargos),
`desde` y `hasta` (fecha contable, incluidas), `texto` (en la contraparte o el
concepto, sin mayúsculas) y `limite` (de 1 a 1000; 200 por defecto). La
contraparte y el concepto son texto del banco: van al DOM con `textContent`.

### El archivo de una parte (paso 16)

```
GET /api/v2/proveedores/3/documentos
→ {"documentos": {"parte": {"tabla", "id", "nombre"}, "total",
                  "documentos": [ {"id", "tipo", "fecha", "numero", "importe_cent",
                                   "estado_pago", "nombre", "tipo_mime", "bytes",
                                   "guardado", "sha256", "registrado_en",
                                   "vinculo": {"tabla", "id", "factura_id",
                                               "orden_compra_id", "estado", "fuente"}} ]}}
```

La carpeta de un cliente o un proveedor en el archivo de la app: los documentos
que el sistema **ya** le enlaza, sin ninguna tabla nueva (decisión 7 de la
revisión de Aurora: los contratos y lo que no es de ningún registro, más
adelante). Cada `tipo`:

| `tipo` | De dónde | `fecha`, `numero` e `importe_cent` |
| --- | --- | --- |
| `factura_compra`, `factura_venta`, `abono_compra`, `abono_venta` | El original de cada factura o abono de la parte (`factura.documento_id`; las de su vista) | Los de la factura (el total; un abono, negativo), y su `estado_pago` |
| `justificante_pago` | El justificante de un pago apuntado de una factura suya (`aplicacion_pago.evidencia_documento_id`) | El día y el importe del pago, el número de la factura; en `vinculo`, el `estado` y la `fuente` del pago |
| `orden_compra` | La hoja de una PO suya (`orden_compra.documento_id`) | La emisión, el número y el valor original |
| `modificacion_po` | La hoja de una modificación de una PO suya | El día de la modificación, el número de la PO y el valor nuevo |

En `vinculo` va solo lo que tiene cada enlace (`factura_id` en las facturas y los
justificantes, `orden_compra_id` en las PO y sus modificaciones). Una fila por
enlace: el mismo documento sale dos veces si lo enlazan dos registros. Lo más
reciente primero; sin fecha, al final. `guardado` es `false` si el original
nunca llegó (Q4): se ve en la lista, pero no se descarga. Una hoja de PO
importada con varias PO dentro no va a ninguna carpeta: es de la importación
(Importeren), no de una PO. `nombre` es el del fichero tal como llegó: texto de
un tercero.

Cada documento con `guardado` se descarga con `GET /api/v2/documentos/N/original`
(`N` es su `id`): sus bytes tal cual, como adjunto, con las mismas cabeceras que
el original de una factura (`Content-Disposition: attachment`,
`Content-Security-Policy: default-src 'none'; sandbox`, `nosniff`, `no-store`),
sin CORS y solo desde la app o la consola (desde otro origen, `403
otro_origen`). Cada descarga, también la que falla porque el original no está,
queda en la auditoría como `documento_abierto`, con la persona y el documento.

### Ejemplo, desde un sitio en `http://localhost:5173`

Antes de escribir una línea, dos decisiones que no son de estilo:

- **El token es de una persona de solo lectura.** Un sitio propio lee; no
  verifica IBAN, no marca pagos, no anula avisos. Se crea una persona para el
  sitio con el rol `consulta`, que solo tiene `ver_facturas`, y se usa su
  token:

  ```bash
  bms-agent usuario crear Web --rol consulta
  bms-agent usuario token Web
  ```

  Nunca el token de quien trabaja en la consola: el de una persona con el rol
  `administracion` puede confirmar IBAN, marcar pagadas, anular avisos y
  revisar facturas, y un token personal dura hasta que alguien lo vuelve a
  emitir (no muere al parar el servidor, como el de `bms-agent serve`).
- **El token no va dentro del sitio.** Nada de `VITE_*`, `NEXT_PUBLIC_*` ni
  ninguna variable que el empaquetador copie al JavaScript: quien pueda cargar
  el sitio puede leerla. La persona lo escribe al abrir el sitio (y se guarda
  en `sessionStorage`, que muere con la pestaña), o un proxy local lo añade
  a cada petición sin que el navegador lo vea.

Aunque se haga mal, el servidor limita el daño: desde otro origen no se ve un
IBAN entero y `POST /api/v2/acciones` contesta `403` («Cuatro reglas», arriba).

```js
const BMS = 'http://127.0.0.1:8765'

// Lo escribe la persona al abrir el sitio: no está en el código ni en el paquete.
function token() {
  let t = sessionStorage.getItem('bms-token')
  if (!t) {
    t = prompt('Token de solo lectura (bms-agent usuario token Web)')
    sessionStorage.setItem('bms-token', t)
  }
  return t
}

async function leer(ruta) {
  const r = await fetch(`${BMS}${ruta}`, {headers: {'X-BMS-Token': token()}})
  if (r.headers.get('X-BMS-Contrato')?.split('.')[0] !== '2') throw new Error('otro contrato')
  if (!r.ok) throw new Error((await r.json()).error)
  return r.json()
}

const {panel} = await leer('/api/v2/panel')
const {busqueda} = await leer('/api/v2/buscar?vencida=si&sentido=entrante&orden=vencimiento')
// Cada nombre va al DOM con textContent: celda.textContent = factura.contraparte
```

---

## El simulador de tarifas

```bash
bms-agent simulador --tarifas config/tarifas.yaml
```

Una página aparte, para **decidir el modelo de precios** antes de fijarlo en
la configuración. Lleva las líneas de compra sin agrupar y recalcula en el
navegador: mueves el margen, escribes una tarifa pactada o marcas un concepto
como no refacturable, y las cifras se mueven al instante.

Lo que se ve: horas facturables, coste, venta, margen en euros y sobre venta;
el reparto por cliente con el coste y el margen encima; y una línea por
cliente, obra, semana y trabajo, con una etiqueta que dice si el precio vino
de una tarifa pactada o del margen.

Cuando el modelo esté decidido, esos números se escriben en
`config/tarifas.yaml` y pasan a alimentar el bloque `facturacion` del contrato
de datos.

### Incrustado en vuestro panel

```bash
python scripts/incrustar_simulador.py panel-v4.html panel-con-simulador.html \
  --extracciones out --tarifas config/tarifas.yaml
```

Escribe una **copia** del panel con el simulador dentro, como una sexta entrada
del dock. No regenera nada: vuestro fichero queda byte a byte igual y solo se
le añaden tres bloques (un `<style>` antes de `</head>`, la sección antes del
pie y un `<script>` al final) más cuatro literales del paquete compilado:

| Literal | Para qué |
| --- | --- |
| La lista de entradas del dock | Sin esto la sección existe pero no hay cómo llegar a ella: la barra de pestañas está oculta y quien navega es el dock |
| `["agent","overview",…]` | Para que la transición deslice hacia el lado correcto |
| El glosario `wl` | El título de la entrada, en inglés y neerlandés |
| La lista de exclusiones del traductor | Vuestro traductor recorre cada nodo de texto del documento en **cada** cambio del DOM. Con la sección fuera, mover el margen cuesta 30 ms en vez de 130 |

Ninguno de los cuatro toca lógica. Si un ancla no aparece exactamente una vez,
el script se para en vez de adivinar.

Los textos de la sección van en inglés y neerlandés y cambian con vuestro
interruptor EN/NL, porque el traductor ya no entra ahí. El neerlandés es una
primera pasada: se corrige en el diccionario `T` del script, no en el HTML.

**Es un parche sobre un artefacto de compilación.** Sobrevive a volver a
ejecutar el script con datos nuevos, no a recompilar el sitio. El sitio
definitivo del simulador es el código fuente de vuestro proyecto: esta versión
sirve para verlo funcionando y para decidir si el diseño de la pantalla es el
que queréis antes de escribirla ahí.
