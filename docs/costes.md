# Coste y cómo ponerle un techo

## Lo primero: son dos carteras distintas

La suscripción de Claude (claude.ai, Claude Code) y la API de Anthropic se
facturan **por separado**. No hay forma de que este agente consuma de la
suscripción.

No es una limitación que se pueda rodear con un ajuste. Un programa que llama
a la API necesita credenciales de API, y la suscripción no las da. Son dos
productos con facturación independiente.

Lo que sí se puede hacer es poner un techo que no se pueda superar, y eso la
suscripción no lo ofrece.

## El techo duro

La API funciona con **saldo prepagado**. Si dejas la recarga automática
desactivada, cuando el saldo se agota las llamadas fallan con un error claro
y no se cobra nada más.

Eso es un límite físico, no un aviso. Es la diferencia con una tarjeta a
crédito: no puede haber factura sorpresa porque no hay línea de crédito.

Tres capas, de fuera hacia dentro:

| Control | Dónde | Qué hace |
| --- | --- | --- |
| Recarga automática **desactivada** | Consola, facturación | Techo absoluto: no se gasta más de lo cargado |
| Límite de gasto mensual | Consola, *Limits* | Corta al llegar a la cifra que pongas |
| Una clave por proyecto | Consola, *API keys* | Permite cortar este agente sin tocar nada más |

Carga veinte euros, deja la recarga desactivada y usa una clave dedicada. Con
eso el riesgo máximo son esos veinte euros, pase lo que pase con el código.

## Lo que cuesta de verdad

No hace falta estimarlo: el programa lo mide. Cada extracción guarda su
consumo real, y al terminar `bms-agent extract` imprime esto:

```
Consumo
------------------------------------------
  documentos                      3
  tokens de entrada           9,120
  tokens de salida            2,840
  coste estimado            $0.1166
  por documento             $0.0389
  por cada 100                $3.89
```

Órdenes de magnitud por cada cien facturas, a falta de medirlo con las
vuestras:

| Modelo | Aproximado por 100 facturas |
| --- | --- |
| Claude Opus 5.5 con el esquema v2 (por defecto desde el paso 6 de la V1) | 6 a 7 dólares; 3 a 3,5 por lotes (estimado, sin medir) |
| Claude Opus 5 con el esquema v1 (el de antes) | 4 dólares |
| Claude Sonnet 5 | 1,60 dólares |
| Claude Haiku 4.5 | 0,80 dólares |

Opus 5.5 cobra menos por token que Opus 5 (4 y 20 dólares por millón, frente
a 5 y 25), pero el esquema v2 pide más campos y Opus 5.5 razona siempre: ese
razonamiento se cobra como salida. Por eso la cifra de Opus 5.5 es una
estimación hasta que haya extracciones v2 medidas; `bms-agent coste` la
sustituye por la medida en cuanto hay tres.

Con el volumen típico de una pyme, esto se mueve en unos pocos euros al mes.
El número real sale de la primera ejecución.

## Qué cuesta cada pasada

```powershell
.venv\Scripts\bms-agent coste
```

No llama a la API ni gasta nada: lee lo que cada extracción ya guardó. Tres
bloques:

- **Lo que ha costado**: total, media por documento, y cuál fue el más caro y
  el más barato. Si hay varios modelos mezclados, lo dice.
- **Por versión**: si hay extracciones de más de un modelo o versión del
  esquema (o alguna por lotes), una línea por cada una. Cuenta también lo
  que leyó `reextraer`, que se exporta aparte en `out/reextraccion/`. Lo
  leído por lotes se cobra a la mitad.
- **Por pasada**: una línea por ejecución, para ver cuánto costó cada una.
  Se agrupa por la hora de cada fichero; dos extracciones separadas por más
  de diez minutos cuentan como pasadas distintas.
- **Volver a lanzar lo ya leído**: cero. La caché va por el hash de los bytes
  del PDF.

### Y qué costaría la siguiente, antes de pagarla

```powershell
.venv\Scripts\bms-agent coste --estimar facturas\
```

Separa los PDF en los que ya están en caché (cero) y los nuevos, y para los
nuevos **cuenta los tokens de entrada exactos** con `messages.count_tokens`,
que es la misma petición que se va a mandar y **no se cobra**.

Los tokens de salida no se pueden saber sin generar, así que se estiman con
la mediana de vuestro propio histórico **de la misma versión del esquema y
el mismo modelo**, y el resultado sale en horquilla. Con menos de tres
extracciones de esa versión no hay mediana propia: se usa la mediana de las
demás versiones por un factor declarado (de 2 a 4: el esquema v2 pide más
campos y Opus 5.5 razona siempre), o un punto de partida declarado si no hay
ninguna, y se dice «sin medir».

```
La proxima pasada
----------------------------------------------------
  ya leidos (cache)                 9   $0.0000
  por leer                          3

  tokens de entrada            21.043   contados, exacto
  tokens de salida      2.544 a 3.180   mediana de vuestro historico

  coste estimado       $0.1704 a $0.1863
  por documento        $0.0568 a $0.0621
```

### La respuesta corta a "cuánto cuesta cada iteración"

La primera pasada sobre unas facturas se paga. **Las siguientes sobre esas
mismas facturas cuestan cero**, porque la caché reconoce los bytes. Lo que se
paga es cada documento nuevo, una vez.

Cambiar de modelo o subir la versión del prompt o del esquema **tampoco
vuelve a pagar**: por defecto se conserva cualquier extracción ya hecha de
esos mismos bytes, la hiciera quien la hiciera. Antes no era así, y una
subida de versión volvía a pagar la carpeta entera sin avisar.

Lo que sí se paga, y conviene tenerlo claro:

- Una **corrección** es otro fichero. Bytes distintos, documento distinto,
  hay que leerlo para saber qué dice. Se paga.
- `--estricta` solo reutiliza lo leído con el mismo modelo y las mismas
  versiones. Es la opción de medir: si estás comprobando si un modelo más
  barato aguanta, reutilizar lo viejo escondería justo la diferencia que
  quieres ver. Lo que no coincide se paga.
- `--force` vuelve a leerlo todo, a propósito.

En los tres casos la extracción anterior se queda donde estaba: nada se
sobrescribe. `bms-agent coste --estimar` sigue la misma política, y con
`--estricta` estima la pasada estricta.

## Volver a leer lo ya leído: `reextraer`

Lo leído con el esquema v1 no se vuelve a pagar solo. Si hace falta lo que
pide el v2 (el tipo de documento, las referencias, el receptor…) en las
facturas que siguen abiertas, se pide aparte y con un techo:

```powershell
.venv\Scripts\bms-agent reextraer --abiertas                      # solo estima
.venv\Scripts\bms-agent reextraer --abiertas --presupuesto 15     # paga si cabe
.venv\Scripts\bms-agent reextraer --abiertas --presupuesto 8 --lote   # la mitad, en horas
.venv\Scripts\bms-agent reextraer --recoger 1                     # los resultados del lote
```

- Elige por `--abiertas`, `--desde AAAA-MM-DD`, `--proveedor`, `--sin-objeto`
  o `--reintentos`, con `--limite`. Nunca vuelve a pagar un documento que ya
  tiene una extracción de la versión actual, y dice cuáles no puede leer
  porque su original no está guardado.
- Cuenta la entrada exacta con `count_tokens` (no se cobra) y estima la
  salida como `coste --estimar`. **Sin `--presupuesto` solo estima. Si el
  extremo alto de la horquilla pasa del presupuesto, no paga nada**, y el
  intento queda en la auditoría; la base tampoco admite una pasada cuya
  estimación alta pase de su presupuesto.
- Lo leído queda como **candidata**: guardado en el almacén y exportado en
  `out/reextraccion/`, pero las facturas no cambian hasta
  `reextraer --activar` (ver [fase-0.md](fase-0.md), «Antes de activar»).
- Por lotes, lo que el modelo rechaza, lo que caduca, lo que se cancela o lo
  que no es el esquema va a una lista de reintentos (`--reintentos`): la API
  de lotes no reintenta sola.

La historia cerrada y pagada no necesita volver a leerse: una persona puede
rellenar a mano lo que le falte.

## Palancas para bajarlo, en orden

**1. Medir antes de tocar nada.** Ya está instrumentado. Una decisión de coste
sin el número delante es una corazonada.

**2. Probar un modelo más barato contra el conjunto dorado.**

```powershell
$env:BMS_EXTRACT_MODEL = "claude-sonnet-5"
.venv\Scripts\bms-agent coste --estimar facturas\ --estricta
.venv\Scripts\bms-agent extract --estricta facturas\
.venv\Scripts\bms-agent score
```

Sin `--estricta`, `extract` reutilizaría las extracciones del modelo anterior
y `score` puntuaría lo mismo de antes.

Si la precisión aguanta el 98 por ciento, te quedas el ahorro. Si no, no.
Esto es exactamente por lo que el modelo es configurable: la respuesta es un
número, no una opinión. **No bajes de modelo por intuición**, que en
extracción de facturas lo que se ahorra en tokens se paga en revisión manual.

**3. Procesar por lotes.** La API de lotes cuesta la mitad y tarda más, lo
cual da igual: las facturas no tienen prisa, se procesan de noche. Es la
palanca más grande y la que mejor encaja con este caso. Desde el paso 6 de
la V1 la usa `reextraer --lote`; `extract` sigue siendo síncrono.

**4. Caché del prompt.** El prompt de sistema es idéntico en todas las
llamadas. Ojo: hay un tamaño mínimo para que la caché entre, y nuestro prompt
puede quedarse por debajo. Verificar `cache_read_input_tokens` antes de dar
por hecho el ahorro.

**5. Bajar el esfuerzo.** Extraer campos de una factura no es un problema
difícil. Vale la pena medir si un esfuerzo menor mantiene la precisión. En
Opus 5.5 el razonamiento no se puede apagar, y el esfuerzo se fija siempre
de forma explícita: `BMS_EXTRACT_EFFORT` (`low`, `medium` por defecto,
`high`…). Cambiarlo es medir otra vez con `--estricta` y `score`.

## Lo que no hay que hacer

Poner la recarga automática con un tope alto "por si acaso". Es justo lo que
convierte un bucle infinito en una factura. Prefiere quedarte sin saldo y
recargar a mano.
