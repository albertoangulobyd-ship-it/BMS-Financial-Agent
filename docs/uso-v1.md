# Guía de uso de la V1

Para quien lleva la administración de BMS Support día a día y no programa.
Explica qué hacer cada mañana, qué quiere decir cada prioridad, cómo se
corrige un dato mal leído, cómo se verifica una cuenta bancaria por teléfono y
cómo se cierra un trimestre del BTW. Lo técnico (cómo se instala, cómo se
conecta una web) está en [instalacion-windows.md](instalacion-windows.md) y en
[integracion-web.md](integracion-web.md).

> **Lo que el agente no hace nunca.** No paga: no prepara ficheros de pago ni
> aprueba nada. No presenta el BTW: prepara la hoja y una persona lo presenta
> en el portal de la Belastingdienst. No crea facturas de venta. No toma un
> IBAN de una factura para pagar. Lee, compara y avisa; las decisiones las
> firma una persona.

---

## Antes de empezar: entrar

Cada persona tiene su usuario y su **token personal** (una contraseña larga
que solo se ve una vez). Lo crea quien administra:

```bash
bms-agent usuario crear Ana --rol administracion
bms-agent usuario token Ana
```

Guarda el token en un gestor de contraseñas. Si se pierde, se pide otro: el
anterior deja de valer.

Un sitio web propio (el panel del dueño, por ejemplo) **no** usa el token de
nadie de administración: lleva su propia persona con el rol `consulta`, que
solo puede ver (`bms-agent usuario crear Web --rol consulta`), y su token no se
escribe dentro del sitio. Lo explica [integracion-web.md](integracion-web.md).

Para trabajar con la consola:

```bash
bms-agent serve
```

y abre `http://127.0.0.1:8765/consola` en el navegador del mismo ordenador.
Escribe tu token en «Token personal». La consola no lo guarda: al cerrar la
pestaña hay que volver a escribirlo.

Arriba verás la barra con las páginas: **Panel**, **Buscar**, **Facturas**,
**Proveedores y clientes**, **Objetos**, **Órdenes de compra**, **BTW** y
**Ficha** (la factura abierta).

---

## La rutina diaria

Unos veinte minutos por la mañana, en este orden.

### 1. Traer lo nuevo

Lo que haya llegado desde ayer: las facturas en PDF, el extracto del banco y,
cuando toque, las exportaciones de Exact y del planning.

```bash
bms-agent extract facturas/                      # los PDF nuevos (lo ya leído no se paga dos veces)
bms-agent importar banco extracto extracto.xml --token ...   # el extracto del banco
bms-agent recalcular --diaria                    # las comprobaciones con la fecha de hoy
```

`recalcular --diaria` es lo que pone al día lo que depende del calendario:
qué ha vencido, qué plazo del BTW se acerca, qué PO caduca. Cada corrección
que hagas ya vuelve a pasar las comprobaciones de esa factura; la diaria hace
falta una vez al día.

### 2. Mirar el panel

La página **Panel** tiene siete bloques:

| Bloque | Qué dice |
| --- | --- |
| **Entra (cobros)** | Lo que nos deben los clientes: lo pendiente, lo vencido y lo que vence esta semana, este mes y en los próximos 30 días. |
| **Sale (pagos)** | Lo mismo de lo que debemos a los proveedores. |
| **Caja** | Lo que se espera que entre y salga en cada una de esas ventanas, el neto, y lo que el banco movió de verdad este mes. Lo estimado desde el planning va aparte y se dice. |
| **Facturación** | Trabajo del planning que nadie ha facturado, periodos sin factura, horas validadas que no están en la venta que cobra su periodo, y diferencias con el planning. |
| **Órdenes de compra** | Lo que vale, lo consumido y lo que queda de las PO activas, por separado las de clientes (lo que BMS puede facturar) y las de proveedores (lo que nos pueden facturar); las que están cerca de su límite, de caducar o de agotarse, y las que ya caducaron con el aviso pendiente. |
| **BTW** | El trimestre en curso, el próximo plazo y los trimestres terminados que aún no se han presentado. |
| **Requiere atención** | Lo pendiente por tipo: IBAN, duplicados, IVA, planning, sin facturar, PO, vencidas, faltan datos, lecturas dudosas y otros. |

Si el estado de las facturas no es de hoy, el panel lo dice arriba en un aviso:
falta el `recalcular --diaria` de hoy. Si una fuente lleva demasiados días sin
importarse (el banco, Exact o el planning), también sale un aviso arriba (y
`bms-agent fuentes` lo dice): lo que depende de esa fuente puede no ser lo de
hoy, así que tráela antes de decidir nada con ella.

### 3. Trabajar la lista, de arriba abajo

En **Facturas** la lista ya viene ordenada: la más urgente primero. Trabaja
primero todo lo **Bloqueada**, después lo **Urgente** y luego lo de
**Atención**. Lo **Normal** puede esperar a la revisión de la semana.

Al abrir una factura ves su ficha:

- **Campos**: cada dato con su valor, lo que ponía el documento y de dónde
  viene (insignia de fuente, ver más abajo).
- **Avisos**: cada comprobación que falla, con su explicación.
- **Historia**: todo lo que le ha pasado a la factura, quién lo hizo, cuándo y
  por qué.
- Los botones **Marcar revisada** (pide una nota) y **Devolver** (pide el
  porqué).

**Marcar revisada no aprueba ningún pago.** Quiere decir «lo he mirado y está
bien»; el pago se hace fuera, en el banco, como siempre. Si después alguien
cambia un dato de esa factura, la revisión deja de valer y la factura vuelve a
la lista.

### 4. Buscar lo que haga falta

**Buscar** encuentra facturas por número, proveedor, cliente, Objeto, PO,
periodo, vencimiento, estado de pago, de revisión, prioridad, calidad del dato
o ediciones a mano, y por pendientes, vencidas, pagadas o anuladas y abonadas.
Los filtros se suman: «proveedor Van Dijk» y «vencida» da las vencidas de Van
Dijk. Abajo sale la suma de lo encontrado: solo suma lo que cuenta (una
factura anulada, una copia fusionada o una sustituida sale en la lista, pero
no suma, igual que en la vista del proveedor), y compras y ventas por
separado.

Lo mismo por línea de comandos:

```bash
bms-agent buscar --filtros                                    # qué filtros hay
bms-agent buscar --filtro proveedor_id=3 --filtro vencida=si
```

### 5. Al final del día

Mira que no quede nada **Bloqueada** sin una excepción abierta o sin alguien a
cargo. Lo que espera a un tercero (un proveedor que tiene que mandar un abono,
el cliente que tiene que confirmar unas horas) se apunta con «esperando a» y
una fecha de seguimiento: hasta ese día su plazo y su vencimiento pesan la
mitad en la prioridad, y el día del seguimiento vuelve a subir.

---

## Qué quiere decir cada prioridad

La prioridad la calcula el sistema; no la elige nadie a ojo. Hay cuatro
niveles:

| Nivel | Qué quiere decir | Qué hacer |
| --- | --- | --- |
| **Bloqueada** | Hay algo que impide pagarla o darla por buena: una cuenta bancaria sin verificar, un posible duplicado, una factura en otra moneda, un dato esencial que no se pudo leer. Siempre hay una comprobación con nombre detrás. | No se paga hasta resolverlo. Lee el aviso y haz lo que dice (verificar, corregir, anular o hablar con el proveedor). |
| **Urgente** | El tiempo apremia o algo se ha pasado de la raya: lleva más de 30 días vencida (compra) o 60 (venta), tiene un problema de IVA a 7 días o menos del plazo del BTW, factura por encima de lo que queda en su PO, un posible cobro doble (el mismo periodo o las mismas horas facturadas dos veces), un pago que salió estando Bloqueada o a una cuenta que no era pagable. O se acumulan puntos (vence en días, importe alto...). | Hoy. |
| **Atención** | Hay algo por mirar, pero no corre prisa: una retención, una excepción abierta, una lectura dudosa, un cambio a mano que nadie ha verificado. | Esta semana. |
| **Normal** | Las comprobaciones no ven nada. No quiere decir que una persona la haya mirado. | En la revisión semanal. |

Al lado del nivel sale el **motivo**, por ejemplo: «Bloqueada: El IBAN
NL75INGB0002445689 de la factura no es pagable: no está en el registro de
cuentas de este proveedor. Se paga siempre a una cuenta del maestro, nunca al
IBAN del documento (F2); La cuenta NL75INGB0002445689 es nueva para este
proveedor: verificar por teléfono… (F3) · vence hoy +20». En la consola el
IBAN sale entero, porque ahí se verifica; en el contrato v2 y en lo que lee un
sitio propio sale enmascarado («NL..5689»). Lo primero es lo
que fija el nivel mínimo; lo que sigue son puntos (plazo, importe, días
vencida) que lo pueden subir.

Una persona puede **subir** la prioridad de algo, con un motivo. **Nadie puede
bajarla**: para que baje hay que resolver lo que la sube.

---

## Cómo corregir un campo

Cuando el sistema leyó mal un dato de una factura (un número, una fecha, unas
horas, un importe, el nombre del proveedor) o no lo pudo leer:

1. Abre la factura y busca el campo en **Campos**.
2. Escribe el valor bueno en **Corregir** (o **Rellenar**, si estaba vacío).
3. Escribe el **motivo**: qué pasaba y de dónde sale el valor bueno («el PDF
   pone 12-10, no 21-10; lo confirma el correo del proveedor»). Las
   correcciones sin motivo no se aceptan.
4. **Guardar**.

Lo que pasa después:

- El campo lleva la insignia **Corregido a mano** (o **Entrado a mano**) y
  debajo quién, cuándo y por qué.
- Lo que leyó el documento **no se borra**: sigue en la columna del original y
  en la historia.
- Las comprobaciones se vuelven a pasar y la prioridad se recalcula.
- Si la factura estaba revisada, deja de estarlo.
- Una lectura posterior del mismo documento nunca pisa lo que una persona
  corrigió.

Si te equivocaste, **Deshacer** devuelve el campo a su valor automático (también
pide motivo). **Verificar** da por bueno un valor sin cambiarlo; si en la
empresa hay dos personas, lo verifica la otra.

Las insignias de fuente que verás:

| Insignia | De dónde sale el dato |
| --- | --- |
| Extraído del documento | Lo leyó el modelo del PDF. |
| Importado de otro sistema | Llegó de Exact o del banco. |
| Del planning | Del programa de planning. |
| Del maestro | De la ficha del proveedor o del cliente. |
| Entrado a mano | Faltaba y lo puso una persona. |
| Corregido a mano | Estaba mal y lo cambió una persona. |
| Calculado por el sistema | Sale de otros datos (un total, un trimestre). |

Por línea de comandos es la orden `fijar_campo`; la consola es más cómoda
porque rellena sola la tabla, la fila y la versión:

```bash
bms-agent accion fijar_campo --tabla factura --fila-id 12 --campo fecha_factura \
  --valor 2026-10-12 --rev 3 --motivo "El PDF pone 12-10; se leyó al revés"
```

**El IBAN no se corrige así.** La cuenta a la que se paga no es un campo de la
factura: vive en el registro de cuentas y solo cambia con una verificación por
teléfono (siguiente apartado).

---

## Cómo verificar un IBAN por teléfono

Cuando una factura trae una cuenta que no conocemos, o Exact dice que la
cuenta de un proveedor ha cambiado, la factura queda **Bloqueada** con un aviso
de la familia F (F3 o F5, normalmente). Es el fraude más común: alguien se
hace pasar por el proveedor y pide pagar a otra cuenta. Por eso:

1. **No llames al teléfono que pone la factura ni el correo.** Llama al
   teléfono de verificación que el proveedor ya tenía en vuestro maestro
   (la ficha del proveedor en Exact) antes de que llegara esa factura.
   `bms-agent iban listar` te dice qué cuentas están sin verificar.
2. Pregunta a la persona que conteste qué cuenta tienen. **Que te la dicte
   ella**; no le leas la de la factura.
3. Si coincide, apúntalo **tecleando** el IBAN (nunca copiado y pegado de la
   factura), con el teléfono al que llamaste y con quién hablaste:

   ```bash
   bms-agent iban verificar --proveedor-id 3 --iban NL91ABNA0417164300 \
     --telefono "+31 10 123 4567" --persona-contactada "Jan de Vries" \
     --factura-id 12 --motivo "Llamada al número del maestro; confirma la cuenta nueva"
   ```

4. Si **no** coincide, o no reconocen el cambio, recházala:

   ```bash
   bms-agent iban rechazar --proveedor-id 3 --iban NL91ABNA0417164300 \
     --factura-id 12 --motivo "El proveedor no ha cambiado de cuenta"
   ```

   y avisa a quien lleve la empresa: puede ser un intento de fraude.

La verificación **no vale** (y la factura sigue bloqueada, con el aviso F8) si
el teléfono al que llamaste no es el que tenía el maestro antes de la factura,
si ese teléfono se cambió hace menos de 14 días, o si fuiste tú quien cambió
ese teléfono y hay otra persona que puede verificar. No es desconfianza: es lo
que impide que una sola persona, o un correo falso, cambie a dónde va el
dinero.

---

## Cómo cerrar un trimestre del BTW

El agente prepara las cifras y la hoja de trabajo; **la declaración la
presenta una persona en el portal de la Belastingdienst**. El plazo es el
último día del mes siguiente al trimestre (el del cuarto trimestre, el 31 de
enero).

1. **Cuando termine el trimestre**, abre la página **BTW** y el trimestre. Sale
   lo de cada rúbrica (1a, 2a, 4a, 4b, 5a, 5b, 5c...) y la lista de facturas
   que piden revisar el IVA. Resuélvelas primero: un IVA mal leído, un
   duplicado o una factura que no está en euros cambian las cifras.
2. **Genera la hoja de trabajo** y guárdala:

   ```bash
   bms-agent btw hoja 2026-T3 --salida hoja-2026-T3.csv
   ```

   Al final imprime su **sha256**, una huella que identifica esa hoja exacta.
3. **Márcalo listo para revisar** con esa huella (en la consola, botón
   «Marcar lista para revisar»; o por comandos):

   ```bash
   bms-agent btw listo --trimestre 2026-T3 --hoja-sha256 ... --motivo "Revisada la lista de IVA"
   ```

   La hoja queda guardada entera. Si algo cambia después y hay que rehacerla,
   **Reabrir** lo devuelve a abierto (con motivo).
4. **El asesor o la otra persona revisa la hoja** y la presenta en el portal de
   la Belastingdienst, a mano.
5. **Anota la presentación** con la referencia del acuse y lo declarado (en
   la consola, «Anotar la presentación hecha a mano»; o por comandos):

   ```bash
   bms-agent btw anotar --trimestre 2026-T3 --rev 2 --hoja-sha256 ... \
     --referencia "OB-2026-123456" --importe-declarado 1234,56 \
     --motivo "Presentada en el portal"
   ```

   Esto es **irreversible**: el trimestre queda presentado con lo que se
   declaró de cada factura. Si después llega una factura con fecha de ese
   trimestre o cambia una que ya se declaró, sale el aviso **C4**: se corrige
   en la declaración siguiente o con una suplementaria, y lo decide el asesor.

---

## Si algo no cuadra

- **Una cifra del panel no coincide con la búsqueda**: mira si el panel dice
  que está al día. Si no, `bms-agent recalcular --diaria`.
- **Un aviso que no tiene sentido**: no lo anules sin más. Anular pide un
  motivo de al menos diez caracteres, algunos piden la firma de otra persona y
  los del IBAN no se pueden anular nunca. Si crees que la comprobación está
  mal, apúntalo y díselo a quien mantiene el sistema.
- **Ver quién hizo qué**: la **Historia** de la factura lo tiene todo, y
  `bms-agent historial 12` lo saca por pantalla.
- **Resumen rápido sin abrir el navegador**: `bms-agent resumen`.
