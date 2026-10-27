# Los textos de la app (neerlandés, inglés y castellano)

La app local de la oficina (`frontend/`, pasos 15 y 16) habla neerlandés,
inglés y castellano (cada persona elige el suyo; por defecto, neerlandés), y
nunca enseña los textos en español que también devuelve la API (`titulo`,
`detalle`, `etiqueta`, `fuente_texto`, `nota`, `motivos`): esos se quedan para
la CLI y la auditoría. Lo que enseña sale de esta carpeta:

| Fichero | Qué es |
| --- | --- |
| `nl.json`, `en.json`, `es.json` | Los tres catálogos, con **las mismas claves, las mismas condiciones y los mismos marcadores** en cada texto (lo comprueba `tests/test_textos.py`). Las claves están en español, como en el código; los valores, en el idioma del fichero |
| `casos.json` | Los casos de referencia del renderizador: lo escribe `scripts/generar_casos_textos.py` y no se edita a mano |
| `__init__.py` | El renderizador de referencia en Python (`bms_agent.textos`) |

La app importa los catálogos y `casos.json` al compilarse (`npm run
build`): si se cambia un texto hay que volver a compilarla (`frontend/`,
`fuente.json` lo vigila: cada catálogo que la app importa tiene que estar en
`frontend/build-inputs.json`) y regenerar los casos.

### El castellano no es el de la API

`es.json` (paso 16) no copia las frases en español de la API. Esas hablan
para quien mantiene el sistema (claves, reglas, códigos); el catálogo habla
para la oficina, con las mismas frases cortas que los otros dos idiomas, y el
detalle de un hallazgo sale de la misma plantilla y de los mismos `valores`.
Así, quien cambia de idioma ve lo mismo dicho de otra manera.

## Qué hay en un catálogo

```
{
  "idioma": "nl",
  "comun":       {"si", "no"},                         // cómo se escribe un sí/no
  "veredicto":   {"limpia", "limpia_sin_datos", ...},  // lo que dice el sistema de una factura
  "reglas":      {"Q1": {"titulo", "significa", "que_hacer", "detalle": {...}}, ...},
  "categorias":  {"iban": {"etiqueta", "significa"}, ...},   // las de panel.atencion
  "campos":      {"factura": {"numero": "Factuurnummer", ...}, "factura_linea": {...}, ...},
  "fuentes":     {"extraccion": {"etiqueta", "significa"}, ...},   // las siete fuentes
  "calidad":     {"faltante": {"etiqueta", "significa"}, ...},
  "estados":     {"pago": {"pendiente": "Openstaand", ...}, "revision": {...}, ...},
  "prioridad":   {"normal": {"etiqueta", "significa"}, ...},
  "severidades": {"bloqueo": {"etiqueta", "significa"}, ...},
  "acciones":    {"marcar_pagada": {"etiqueta", "descripcion", "confirmar"}, ...},
  "roles":       {"administrador": {"etiqueta", "descripcion"}, ...},
  "permisos":    {"ver_facturas": {"etiqueta", "descripcion"}, ...},
  "codigos":     {"autoliquidacion": "btw verlegd", ...}   // lo que escribe |codigo
}
```

- **reglas**: una entrada por regla de `reglas/catalogo.py`. `titulo` es el
  nombre corto; `significa`, qué quiere decir, en una frase; `que_hacer`, qué
  tiene que hacer la persona, en una frase; `detalle`, las plantillas del
  detalle de un hallazgo, por resultado: `fallo` siempre y `sin_datos` en las
  reglas que pueden no tener con qué mirar.
- **acciones**: una por orden de `servicios.ACCIONES`. `confirmar` (la frase
  del diálogo de confirmación) solo en las que cambian algo que mueve dinero,
  el IVA o los datos bancarios.
- **estados**: cada enum que devuelve la API, por grupo (`pago`, `revision`,
  `excepcion`, `hallazgo`, `relacion`, `btw`, `cuenta`...).
- **codigos**: lo que vale un código que va dentro de `valores` (un
  tratamiento de IVA, una fuente, la unidad de una línea...), escrito para ir
  en medio de una frase (en minúsculas). Es un diccionario plano: una clave
  no se reutiliza con otro significado.

## Las plantillas del detalle

El detalle de un hallazgo no se traduce del español: se vuelve a escribir
desde sus `valores`, los mismos enteros y textos que la regla comparó (los
que entran en su huella). La API los da en cada hallazgo (`valores` y
`resultado`, contrato 2.1).

`detalle[resultado]` es una lista de **variantes**, que se prueban en orden:

```
"detalle": {
  "fallo": [
    {"cuando": ["caso=numero"], "texto": "Factuurnummer {numero_norm} ..."},
    {"cuando": [], "partes": [
        {"cuando": ["btw"], "texto": "Btw-nummer ..."},
        {"cuando": ["kvk"], "texto": "KvK-nummer ..."}]},
    {"cuando": [], "texto": "Deze klant is mogelijk twee keer gefactureerd."}
  ],
  "sin_datos": [ ... ]
}
```

- Vale la **primera variante cuyas condiciones se cumplen todas**. La última
  no lleva condiciones, así que siempre hay una.
- Una condición es `ruta` (está, y no es `null` ni una lista vacía), `!ruta`
  (lo contrario) o `ruta=valor` (su texto crudo es ese: `true`/`false`, las
  cifras de un entero o el texto tal cual).
- Una variante con `partes` escribe cada parte que vale, en orden y separadas
  por un espacio (A2: el btw-id, el KvK y el nombre que difieran). Si no vale
  ninguna parte, la variante no vale y se sigue con la siguiente.
- Un resultado sin plantilla escribe el `significa` de la regla.

## El lenguaje de una plantilla

Texto con marcadores `{ruta}` o `{ruta|filtro}`; `{{` y `}}` son llaves
literales y una llave suelta se deja tal cual.

- **ruta**: claves separadas por puntos; un segmento de cifras indexa una
  lista (`{periodos.0.1}`, `{distintos.total_cent.0}`).
- **una clave que falta** se escribe como una raya (`—`) y se **apunta** (ver
  abajo). Un `null` o una lista vacía también se escriben como una raya, sin
  apuntarse: la regla dijo que no hay.
- **una lista** se escribe elemento a elemento con el formato y separada por
  `, ` (`{tipos|pct}` con `[900, 2100]` es `9%, 21%`).
- un **objeto** no se escribe: raya, y se apunta.
- `true`/`false` se escriben `ja`/`nee`, `yes`/`no` o `sí`/`no` (`comun.si`,
  `comun.no`).

Los **formatos** escriben un valor; van al final:

| Filtro | De | Escribe |
| --- | --- | --- |
| (ninguno) o `texto` | lo que sea | el texto tal cual; un entero, sus cifras (`2026`) |
| `dinero` | céntimos (`_cent`), entero | `€ 1.234,56`, `€ -1.234,56` (formato neerlandés en los tres idiomas) |
| `tarifa` | diezmilésimas de euro (`_e4`) | `€ 42,50`; con más decimales, hasta cuatro: `€ 42,505` |
| `horas` | milésimas (`_mil`, de hora o de una cantidad) | `37,5`, `8`, `1.234,25`: sin ceros de más |
| `pct` | puntos básicos (`_pb`) | `21%`, `85,99%` |
| `fecha` | `AAAA-MM-DD` (o un instante que empieza así) | `16-10-2026` |
| `trimestre` | la etiqueta del BTW de la API (`2026-T3`) | `Q3 2026` |
| `iban` | un IBAN | `NL91 ABNA 0417 1643 00`; uno enmascarado (`NL..4300`) tal cual |
| `codigo` | un código | su texto en `codigos`; uno que no está, tal cual y se apunta (`codigo:x`) |

Las **transformaciones** cambian el valor antes del formato; van delante, en
orden (`{lineas_cent|suma|dinero}`):

| Filtro | Hace |
| --- | --- |
| `cuenta` | cuántos elementos tiene una lista o un objeto (un entero se deja) |
| `suma` | la suma de una lista de enteros (`null` si alguno no lo es) |
| `abs` | el valor absoluto (de cada elemento, en una lista) |

Un número que no lo es (un texto en `dinero`) se escribe como texto. Un
número puede llegar como texto de cifras (`"181350"`) o como fracción
(`"181351/2"`, la mediana de U1): se redondea a la unidad, la mitad lejos de
cero. Ningún filtro usa floats: todo es aritmética de enteros y de textos.

Un filtro que no existe, o un formato delante de otro filtro, es una raya y se
apunta (`filtro:x`).

**Lo que sale es texto, nunca HTML.** Los valores pueden traer texto de un
documento (un nombre, un número de factura) y se escriben tal cual: la app los
pone en la página como texto.

## Lo que se apunta

`bms_agent.textos.pintar(plantilla, valores, idioma)` devuelve un `Pintado`
con el `texto` y `faltan`: las rutas que faltaban, `codigo:x` y `filtro:x`.
Quien lee solo ve la raya; `faltan` es para los tests: una plantilla que pide
una clave que su regla no da está mal. `detalle(regla, resultado, valores,
idioma)` elige la variante y la pinta. La app (TypeScript) hace lo mismo y
devuelve lo mismo.

## Los casos (`casos.json`)

```
{
  "version": 1, "nota": "...", "instante": "2026-10-16T08:00:00+00:00",
  "plantillas": [ {"plantilla", "valores", "nl", "en", "es", "faltan"} ],
  "detalles":   [ {"origen", "regla", "resultado", "valores", "variante", "nl", "en", "es", "faltan"} ]
}
```

- `plantillas`: los bordes del lenguaje (formatos, negativos, unicode, claves
  que faltan, llaves literales). `pintar(plantilla, valores, idioma)` tiene
  que dar `nl` (o `en`, o `es`) y `faltan`.
- `detalles`: hallazgos de verdad (`origen` `demo` o `fixtures_v1`: las reglas
  sobre la base de prueba hecha con un reloj fijo y sobre las fixtures v1) y,
  para cada variante que esos datos no alcanzan, un ejemplo con la forma que
  dan las reglas en los tests (`origen` `ejemplo`). `detalle(regla, resultado,
  valores, idioma)` tiene que elegir `variante` y dar `nl` (o `en`, o `es`), sin nada
  en `faltan`. Cada variante de cada plantilla tiene al menos un caso.

Para regenerarlo, desde la raíz del repositorio:

```
python scripts/generar_casos_textos.py              # lo reescribe
python scripts/generar_casos_textos.py --comprobar  # 1 si no está al día (lo hace el test)
```

Si el generador se queja de una variante sin caso, falta un ejemplo en
`EJEMPLOS` (en el propio script), con los valores que da la regla.

## Cómo se añade o se cambia un texto

1. Cambia el valor en `nl.json`, en `en.json` **y** en `es.json` (las tres
   claves, siempre). Una regla nueva del catálogo necesita sus textos en los
   tres: el test falla si falta uno, si una variante o una condición solo
   está en uno, o si un texto lleva en un idioma un marcador (o un filtro)
   que no lleva en otro. El orden de los marcadores sí puede cambiar con la
   frase.
2. Una plantilla solo usa claves que su regla da en `valores` (míralo en el
   código de la regla) con el filtro de su unidad (`_cent` → `dinero`, `_mil`
   → `horas`, `_pb` → `pct`, `_e4` → `tarifa`).
3. `python scripts/generar_casos_textos.py` y `python -m pytest
   tests/test_textos.py tests/test_textos_es.py`.
4. Vuelve a compilar la app (`cd frontend; npm run build`).

El neerlandés tiene que leerse como lo escribiría un administrativo
neerlandés: frases cortas, sin jerga, `btw` en minúsculas, `factuurregel` para
una línea (una `regel` a secas es ambigua) y `controle` para una regla.

El castellano, como lo leería cualquier administrativo hispanohablante, sin
regionalismos (`archivo`, no `fichero`; nada de `vosotros`), tuteando como el
resto del programa (`Comprueba el original`) y siempre con tildes. Las
etiquetas de las acciones van en infinitivo (`Anotar pago`) y su descripción
en imperativo (`Anota que una factura se pagó...`). Se dejan tal cual los
términos de BMS: `zzp'er`, `BTW` (en mayúsculas y siempre BTW, nunca IVA,
para no hacer pensar en dos impuestos), `Object` (`el Object`, `los
Objects`), `PO` (`la PO`), `Exact`, `TRNSPRNT`, `IBAN`, `KvK` y `KOR`. El
resto, en castellano llano: `datos maestros` (stamgegevens), `hallazgo`
(bevinding), `control` (controle), `excepción`, `nota de crédito`,
`autoliquidación` (BTW verlegd), `planificación` (el planning de TRNSPRNT),
`casar` un movimiento con una factura, `retener` y `bloquear`. Los formatos
no cambian con el idioma: el importe va en formato neerlandés con el euro
delante y el trimestre es `Q3 2026` en los tres, como en el Belastingdienst
y en Exact.

`tests/test_textos_es.py` comprueba que en `es.json` no queda ninguna
palabra que solo existe en neerlandés o en inglés, que ningún texto es igual
al inglés salvo esos términos, las tildes de las palabras que siempre las
llevan y que el impuesto se llama siempre BTW; `tests/test_textos.py`, que en
`nl.json` y en `en.json` no se cuela el castellano.
