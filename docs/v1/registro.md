# Registro de construcción de la V1

Un apartado por paso de [spec.md](spec.md) §11. Cada paso dice qué se construyó,
dónde se apartó de la especificación y por qué, y qué queda pendiente para el
siguiente. Lo escribe quien construye el paso, al terminarlo.

## Paso 0

Base y correcciones, sin almacén y sin gasto de API. Todo lo de abajo se probó
con `pytest`: **314 tests pasan** (207 funciones de test; eran 125), ninguno
llama a la API. Las cifras incluyen las correcciones de la revisión (al final
de este apartado).

### Qué se construyó

**Ejemplos v1 y foto de referencia**

- `tests/fixtures/v1/`: siete extracciones v1 con la forma exacta que escribe
  `ExtractionRecord.write_json`, validadas contra `InvoiceExtraction`: las tres
  de ejemplo (`01-limpia`, `02-sin-kvk-btw-verlegd`, `03-con-inyeccion`), un
  abono parcial de la 01 (`04-nota-credito`), una línea en «uren»
  (`05-uren`), una fecha copiada como `13-09-2026` (`06-fecha-nl`) y una
  factura en dólares con la unidad «hours» (`07-usd`). Más `tarifas.yaml`,
  copia fija de `config/tarifas.ejemplo.yaml`, y un `README.md` que explica
  cada una.
- `tests/golden/construir_datos_v1.json`: `construir_datos` sobre las siete,
  después de las correcciones, comparado byte a byte
  (`json.dumps(..., ensure_ascii=False, indent=2)` más salto de línea). Se
  regenera con `python scripts/regenerar_golden.py`.
- `tests/golden/construir_datos_v1_antes_sin_afectadas.json`: la foto tomada
  con el código de **antes** de las correcciones (commit `22f88ec`) sobre las
  cinco fixtures que no deben cambiar. El test la compara byte a byte con el
  código de ahora: las correcciones no movieron nada fuera de `05-uren` y
  `07-usd`. No se regenera nunca.
- `tests/test_golden.py` comprueba además que el hash de las tres de ejemplo
  es el de los PDF que escribe `scripts/generar_facturas_ejemplo.py`.

Diferencias de la foto completa entre antes y después, todas en las dos
fixtures documentadas:

| Fixture | Antes | Después |
| --- | --- | --- |
| `05-uren` | `horas: null`, `otras_unidades: ["uren", "stuk"]`, fuera de la proyección | 24 horas, `otras_unidades: ["stuk"]`, propuesta de Waalhaven con 24 h |
| `07-usd` | Estado `ok`, 2.500 sumados como euros en base, total, por mes, por proveedor, matriz y régimen | `base`/`iva`/`total` a `null`, estado `critico` con el motivo X1, fuera de todos los agregados (importes, horas, por mes, por proveedor, régimen, matriz, proyección y simulador); queda como fila y como alerta |

Con eso cambian los agregados que las contienen: `totales.importe` pasa de
10.486,42 a 7.986,42, `totales.horas` de 137,5 a 161,5 (las 24 de `05-uren`;
las 20 de `07-usd` no), `criticas` de 0 a 1, Northwind sale de
`por_proveedor` y de la matriz, `por_regimen` cuenta una factura con IVA
trasladado en vez de dos, y la proyección suma la propuesta de Waalhaven.

**Correcciones de código**

| Defecto | Dónde | Corrección |
| --- | --- | --- |
| «uren», «u» u «hours» daban cero horas | `dashboard._horas`, `_otras_unidades`; `facturacion.proyectar`, `lineas_para_simulador` | Nuevo `parsing.es_unidad_hora`, el único predicado de horas. Acepta todo lo que empezaba por «uur» (no se pierde nada de lo que ya contaba) y además uren, u, manuren, werkuren, h, hr, hrs, hour, hours, Std. Decide la primera palabra de la unidad |
| `$`, `£` y `USD` se quitaban como el euro | `parsing.parse_amount` | Nuevo `parsing.detectar_moneda`. `parse_amount` solo quita el marcador del euro y lanza `ParseError` con cualquier otra moneda. Nueva regla X1 (`checks.check_currency`), que mira el literal de cada importe de cabecera y de línea y decide para la factura entera; `checks.en_euros` es el predicado con el que cada agregado la deja fuera |
| B4 salía como `critico` | `dashboard.detectar_periodos_repetidos` | Sale como `revisar` (Retención, como el catálogo) |
| La KOR con IVA salía como E4 | `checks.check_vat_amount` | E3 con la KOR, E4 con el IVA trasladado |
| G3 agrupaba por nombre impreso | `dashboard.detectar_cambios_de_tarifa` | Agrupa por `_identidad` (btw-id, luego KvK, luego nombre). El nombre que se enseña une los nombres impresos («J. de Vries / De Vries Montage»), y las alertas se ordenan por ese nombre, como antes |
| El IBAN más antiguo de los documentos era la referencia | `dashboard.detectar_ibanes` | Ninguna cuenta impresa es de referencia. F3 marca todas las facturas del proveedor que traen alguno de sus IBAN, y el detalle lista cada cuenta con su número de facturas y la fecha en que apareció. El proveedor de F3 es el grupo de `_grupos_de_pago` (comparte btw-id, KvK o nombre), no `_identidad` |
| Sin precio para claude-opus-5-5 | `pricing.PRICES` | claude-opus-5-5 a 4/20 $, claude-sonnet-5-5 a 2/10 $, claude-haiku-5-5 a 0,10/0,50 $ por millón (referencia de la API consultada el 2026-10-06). El modelo por defecto sigue siendo claude-opus-5 |

**Servidor local (`serve.py`)**

- **Host**: solo `127.0.0.1:<puerto>` o `localhost:<puerto>`; cualquier otro,
  `421` (cierra el *DNS rebinding*).
- **Origin**: se normaliza a esquema, host y puerto y se compara entero
  contra la propia página y los orígenes declarados con
  `bms-agent serve --origen URL` (repetible, solo `localhost` o `127.0.0.1`).
  `http://localhost.attacker.example` y `http://127.0.0.1.nip.io` ya no pasan.
  Un Origin presente y no admitido recibe `403` sin cabecera CORS, en
  cualquier método.
- **POST**: cabecera `X-BMS-Token` (aleatoria en cada arranque,
  `secrets.token_urlsafe(32)`, comparada en tiempo constante) y
  `Content-Type: application/json` con un objeto JSON de 4 KiB como mucho.
  Orden de comprobación: Host 421, Origin 403, ruta 404, token 403, tipo 415,
  tamaño 413, objeto JSON 400.
- **Página local** en `GET /`: botón de ejecutar y estado de la pasada, con el
  token en `<meta name="bms-token">`. Lleva `X-Frame-Options: DENY` y una CSP
  con `frame-ancestors 'none'` para que no se pueda pulsar desde un marco de
  otra web. El token también se imprime al arrancar.
- `crear_servidor(...)` crea el servidor ya escuchando, con agente y token
  inyectables y puerto 0 posible; `servir` lo usa. Los tests levantan el
  servidor de verdad con un agente falso (`tests/test_serve_seguridad.py`).

**Caché y evidencia**

- `cache.py`: políticas `CONSERVAR` (por defecto) y `ESTRICTA`;
  `indexar()` devuelve todas las extracciones de cada documento, la más
  reciente primero; `reutilizable()` decide cuál sirve (la que coincide en
  todo si la hay; con CONSERVAR, si no, la más reciente). `matches()` sigue
  siendo la prueba estricta y `build_index()` se conserva.
- `extract.py`: `write_json` no sobrescribe nunca. El nombre es
  `<sha12>__<modelo>__<prompt>__s<esquema>.json`; si existe con otro
  contenido se añade `__2`, `__3`…; si existe con el mismo contenido se
  devuelve ese. Se escribe en modo exclusivo (`open("x")`). Nuevo
  `extraer_pasada()`, el único bucle de extracción, que usan `extract` y el
  servidor local.
- `report.load_records()` devuelve una extracción por documento, la vigente;
  `load_records(..., todas=True)` las devuelve todas.
- CLI: `extract --estricta` (medir), `--force` igual que antes pero sin pisar;
  `coste --estimar ... --estricta` estima la pasada estricta; `coste` cuenta
  todas las extracciones pagadas; `score` puntúa la vigente de cada documento.

**Documentación**: README, `docs/fase-0.md` (recuento de tests, caché,
moneda, B4/F3/G3, `--estricta`), `docs/integracion-web.md` (Host, Origin,
token, `--origen`, ejemplo con token, notas del contrato sobre B4 y X1),
`docs/costes.md` (la caché ya no vuelve a pagar al cambiar de versión;
`--estricta` para medir), `docs/instalacion-windows.md` y
`docs/brief-diseno.md` (recuento), `docs/validacion-facturas.md` (D2/D2b
con los identificadores del código y la regla X1).

**Tablas**: ninguna; el paso 0 no tiene almacén.

### La puerta, test por test

| Puerta | Tests |
| --- | --- |
| Pasan los 125 tests que había | 121 sin tocar; 4 adaptados porque la especificación cambia su comportamiento (ver desviaciones) |
| La foto es igual salvo las fixtures documentadas | `test_golden.py::test_las_correcciones_no_cambian_nada_fuera_de_las_fixtures_documentadas`, `test_construir_datos_es_byte_a_byte_la_foto` y los dos de `05-uren` y `07-usd` |
| Un POST de formulario desde otra web recibe 403 | `test_serve_seguridad.py::test_un_formulario_de_otra_web_no_lanza_una_pasada` |
| Un Host ajeno recibe 403 o 421 | `test_un_host_ajeno_se_rechaza` (recibe 421), `test_host_ajeno` |
| `http://localhost.attacker.example` no recibe cabecera CORS | `test_un_origen_parecido_no_recibe_cabecera_cors`, `test_un_origen_que_solo_se_parece_no_pasa` (también `127.0.0.1.nip.io`) |
| Un cliente falso hace 0 llamadas si solo cambia la versión | `test_extraccion_pasada.py::test_cambiar_solo_la_version_no_hace_ninguna_llamada`, y lo mismo por la CLI, por el servidor y por `coste --estimar` |

### Desviaciones de la especificación, y por qué

1. **Cuatro tests existentes cambian**, porque la especificación cambia lo que
   comprobaban:
   - `test_la_misma_semana_facturada_dos_veces_es_critico` pasa a
     `..._se_retiene`: B4 es `revisar`.
   - `test_las_alertas_criticas_salen_antes_que_los_avisos` ya no espera B4
     entre las críticas; comprueba que sale entre las de revisar.
   - `test_el_iban_habitual_no_convierte_todo_el_historico_en_sospechoso` pasa
     a `test_ninguna_cuenta_vista_en_documentos_hace_de_referencia`, y
     `test_un_cambio_de_banco_real_no_acusa_al_historico_correcto` a
     `test_una_primera_factura_fraudulenta_no_se_convierte_en_referencia`:
     ahora se marcan todas las facturas del proveedor, no solo las de la
     cuenta «rara».
2. **`pip install -e '.[dev]'`** no puede bajar nada (no hay red). Las
   dependencias ya estaban en `.venv` (pydantic, pytest, anthropic, pyyaml;
   el §1 de la especificación decía que no), y el paquete se reinstaló con
   `pip install --no-index --no-build-isolation -e '.[dev]'`.
3. **Se adelanta `parsing.parse_importe`** (importe y moneda), que la
   especificación pone entre las funciones nuevas del paso 6. Hace falta ya:
   `scoring._cmp_amount` dejaba de poder comparar un importe en dólares en
   cuanto `parse_amount` dejó de quitar el `$`. Ahora compara valor y moneda;
   un literal sin marcador cuenta como euro, como antes.
4. **F3 marca todas las facturas del proveedor** que traen alguno de sus IBAN,
   no solo las de la cuenta nueva. Sin registro de cuentas no hay manera de
   saber cuál es la buena, y pagar cualquiera sin la llamada es el riesgo que
   F3 existe para cortar. Hace más ruido en un proveedor que cambia de banco
   de verdad; se acaba cuando el paso 5 traiga el registro y la verificación.
5. **CORS solo para orígenes exactos.** La doc decía «localhost en cualquier
   puerto». Ahora un sitio en otro puerto tiene que declararse con
   `--origen`, y solo se admiten orígenes locales (un origen remoto podría
   leer los IBAN). Rompe un flujo de desarrollo que antes funcionaba sin
   nada; está explicado en `docs/integracion-web.md`.
6. **El token se sirve solo a la propia página**, dentro de `GET /`. No hay
   ningún endpoint que se lo dé a otro origen: un sitio propio en otro puerto
   lo copia de la salida del arranque. Así el token añade algo a CORS en vez
   de repetirlo.
7. **`write_json` no sobrescribe nada**, ni siquiera con las mismas versiones
   (un `--force`): añade un sufijo. La nota del paso pedía no pisar otras
   versiones; la especificación (§10, «nothing is ever overwritten») pide no
   pisar nunca, y se ha seguido esta.
8. **Qué extracción es la vigente** hasta que exista el almacén: la más
   reciente de cada documento (por `extracted_at`; en empate, la del nombre
   de fichero mayor). Es lo que veía todo el mundo cuando la nueva pisaba a
   la vieja, sin perder la vieja. Sin esta regla, dos extracciones del mismo
   PDF salían como dos facturas y disparaban un B2 falso. El paso 1 la
   sustituye por `extraccion_vigente_id` y el paso 6 por la puerta de
   activación.
9. **Un PDF repetido dentro de la misma pasada se paga una vez**: el índice
   se actualiza al escribir. Antes se pagaba dos veces y la segunda pisaba la
   primera. También con `--force`: el índice empieza vacío y solo guarda lo
   que esta pasada ha escrito, así que se vuelve a leer lo de pasadas
   anteriores, pero no dos veces lo mismo dentro de una.
10. **X1 se calcula en `checks.run_checks`** con el respaldo para v1 del §10
    (mirar el literal de cada importe), al final de la lista para no mover el
    orden de los demás motivos. En el panel sale como los otros fallos por
    factura, agrupado con `regla: "D"`: es el reetiquetado que ya existía
    (`dashboard.construir_alertas`) y que se corrige en el paso 3, cuando las
    reglas lleven su identificador.
11. **Documentos tocados fuera de la lista**: `docs/validacion-facturas.md`
    (D2/D2b con los identificadores del código, como pide el §1, y la sección
    X), una errata de IBAN en `docs/fase-0.md` (`NL91INGB…` era
    `NL75INGB0002445689`) y `coste.formatear_relanzar`, que explicaba la
    caché estricta.
12. **`docs/diseno-v1.md`** estaba en el árbol de trabajo sin versionar al
    empezar el paso (no lo escribió este paso). La especificación lo enlaza
    como su resumen en castellano, así que entra en este commit tal como
    estaba.

### Lo que deben saber los pasos siguientes

- **La foto**: `tests/golden/construir_datos_v1.json` es la que los pasos 1, 2
  y 12 tienen que reproducir (`construir_datos(registros_legado(db))`,
  `registros_resueltos`, `/api/datos`). Está serializada con `indent=2`;
  `/api/datos` se sirve sin sangrar, así que la comparación byte a byte del
  paso 12 tiene que usar la misma serialización o comparar el JSON
  interpretado. Si un paso cambia el panel a propósito, regenera la foto con
  el script y lo explica aquí.
- **Las fixtures** `04` a `07` no tienen PDF: su `source_sha256` es el de un
  texto fijo («bms-agent fixture v1 sin PDF: …»). En `importar-out` (paso 1)
  son el caso «falta el original» (`ruta_cas` NULL). Las tres primeras sí
  coinciden con los PDF del generador.
- **`extraer_pasada`** es el único bucle de extracción (CLI y servidor). El
  paso 1 escribe en el almacén ahí, y más adelante `ingesta.py` lo envuelve.
  `out/` puede tener varias extracciones por documento y ficheros antiguos
  con el nombre `<sha12>.json`; los dos formatos se leen igual.
- **Importes**: `parse_amount` lanza con cualquier moneda que no sea el euro.
  Lo que sume importes nuevos tiene que pasar por `parse_amount` (euros) o
  por `parse_importe` mirando la moneda. `checks.check_currency` es el
  respaldo de X1 para registros v1 que el paso 6 combinará con `currency_raw`.
  `detectar_moneda` no reconoce marcadores fuera de su lista: un importe con
  texto desconocido sigue saliendo como ilegible (sin datos), no como X1; si
  ningún importe se lee, X1 también queda sin datos, no «ok».
- **Moneda por factura**: lo que sume importes u horas de una factura tiene
  que mirar antes `checks.en_euros(extraccion)` (o `Fila.en_euros`), no solo
  el literal. El paso 6 lo combina con `currency_raw`.
- **Horas**: `parsing.es_unidad_hora` es el único predicado; no volver a
  comparar con «uur».
- **Lo que sigue pendiente de huecos.md y no era de este paso**: la guarda
  muerta `startswith("nom:(sin")` (los proveedores sin nombre ni btw-id
  siguen agrupándose entre sí en B2, B3 y G3; F3 ya no, ver la revisión), `por_proveedor` y la matriz
  agrupan por nombre impreso, `_propagar_alertas_a_filas` une por nombre de
  fichero, B4 no distingue por objeto, y los fallos por factura salen con
  regla «D». Son de los pasos 2 y 3.
- **Servidor**: el futuro `POST /api/v2/acciones` (paso 4) tiene que pasar
  por `Manejador._rechazada` y por la misma comprobación de token y JSON. Los
  orígenes extra se declaran con `--origen`.
- **Modelo**: el modelo por defecto sigue siendo claude-opus-5 (lo fija un
  test). claude-opus-5-5 ya tiene precio; el cambio va con el esquema v2 en
  el paso 6, para pagar los documentos una sola vez. Haiku 5.5 cobra más por
  encima de 100.000 tokens de entrada por petición; `pricing.py` solo lleva
  la tarifa baja porque una factura no se acerca.

### Correcciones de la revisión

Ocho hallazgos de la revisión, cada uno reproducido antes de tocar nada.
Son 25 casos de test nuevos; 24 fallan con el código del commit `ea060b0`
(el que pasa es `R$ 100` en `test_un_importe_en_otra_moneda_no_se_lee_como_euros`,
que ya lanzaba aunque por USD) y todos pasan ahora.

| Hallazgo | ¿Real? | Qué se hizo | Tests |
| --- | --- | --- | --- |
| X1 se decidía por factura pero los importes se descartaban campo a campo: una base sin `$` en una factura con `$` en el total sumaba 2.500 € en la fila, por mes, por proveedor, régimen y matriz (hallazgos 1 y 5, panel e informe) | Sí | `construir_filas` pone `base`, `iva` y `total` a `null` cuando X1 falla, y guarda `Fila.en_euros`. `report.InvoiceView.total` devuelve `None` con X1, así que `total_amount` tampoco la suma | `test_una_cabecera_sin_marcador_en_una_factura_en_dolares_no_suma_como_euros`, `test_el_total_de_una_factura_en_dolares_no_entra_aunque_pierda_el_marcador` |
| Una tarifa sin `$` en una factura en dólares se proyectaba como euros (coste 2.500, venta 3.375) y entraba en el simulador y en G3 (hallazgos 1, 5 y 7) | Sí | Nuevo `checks.en_euros`; `proyectar`, `lineas_para_simulador` y `detectar_cambios_de_tarifa` saltan la factura entera | `test_una_tarifa_sin_marcador_en_una_factura_en_dolares_no_se_proyecta`, `test_g3_no_compara_una_tarifa_en_dolares_con_una_en_euros` |
| La factura X1 contaba en unos agregados y no en otros: sus 20 horas en `totales.horas` y en `por_proveedor`, una celda de 0,00 € en la matriz, dos facturas en el régimen con el total de una (hallazgo 8) | Sí | Se excluye de todos los agregados con `dashboard._sumables`: horas, por mes, por proveedor, régimen y matriz. Siguen contándola `totales.facturas`, `proveedores`, `criticas` y `por_revisar`, que son recuentos de la tabla donde sí está; la fila conserva sus horas porque dicen lo que trae el documento. Se regeneró la foto (abajo) | `test_la_factura_en_dolares_no_suma_como_euros` (ampliado), la foto |
| `detectar_moneda` no veía un código pegado a los dígitos (`USD2,500.00`, `CHF100.00`) y X1 daba «ok: Importes en euros» con todos los importes a `null` (hallazgo 2) | Sí | Los códigos, el euro y la corona se acotan por letras (`(?<![a-z])…(?![a-z])`) en vez de `\b`; `2.500,00EUR` ya se lee. X1 da «sin datos» si ningún importe se lee y ninguno lleva marcador | `test_detectar_moneda` (nueve casos nuevos), `test_un_importe_en_otra_moneda_no_se_lee_como_euros`, `test_el_euro_pegado_a_los_digitos_se_lee`, `test_x1_marca_el_codigo_pegado_a_los_digitos`, `test_x1_no_da_por_euros_lo_que_no_ha_podido_leer` |
| `R$ 100` y `CAD$100` salían como USD, y `parse_importe("R$ 100")` no se podía leer (hallazgo 3) | Sí | El `$` se lee con las letras que lleva pegadas delante y una tabla de prefijos (US, C/CA/CAD, A/AU/AUD, NZ, HK, S/SG, R/BRL, MX/MXN); un prefijo desconocido da `"$"`, no USD. `_quitar_monedas` quita el prefijo entero | `test_detectar_moneda`, `test_parse_importe_lee_los_dolares_con_prefijo` |
| Con `--force`, un PDF repetido en la misma pasada se pagaba dos veces (hallazgo 4) | Sí | `extraer_pasada` consulta siempre el índice; con `forzar` empieza vacío y solo contiene lo escrito en esta pasada. La desviación 9 dice ahora que vale también con `--force` | `test_con_force_el_mismo_pdf_dos_veces_en_la_pasada_se_paga_una_vez` |
| F3 se esquivaba copiando el nombre y el KvK de un proveedor y quitando o cambiando el btw-id: la factura con el IBAN nuevo salía `ok` (hallazgo 6) | Sí | Nuevo `dashboard._grupos_de_pago`: unión de conjuntos sobre btw-id, KvK y nombre normalizado (sin mayúsculas, puntos ni espacios de más). F3 agrupa por ahí; un nombre vacío no une nada. G3, B2, B3 y B4 siguen con `_identidad` | `test_f3_no_se_esquiva_quitando_o_cambiando_el_btw_id`, `test_f3_tampoco_se_esquiva_copiando_solo_el_nombre`, `test_f3_no_junta_proveedores_sin_nada_en_comun_ni_los_que_no_tienen_nombre` |

**La foto** `construir_datos_v1.json` se regeneró. Solo cambia `07-usd`:
Northwind sale de `por_proveedor` y de la matriz (con ella, la semana
2026-W38, que solo tenía esa celda), `por_regimen` de IVA trasladado pasa de
2 facturas a 1 y `totales.horas` de 181,5 a 161,5. La foto de antes sin las
afectadas no cambia.

**Desviaciones nuevas**

13. **F3 junta de más a propósito.** Dos proveedores distintos que imprimen
    el mismo nombre y tienen IBAN distintos salen como un F3. Para una parada
    de pago, juntar de más cuesta una llamada; juntar de menos, un pago a una
    cuenta ajena. No se añadió la alerta aparte que sugería la revisión (un
    btw-id o KvK que no casa con otros del mismo nombre) porque sin IBAN
    distinto no hay pago en riesgo; el paso 2 resuelve la identidad de verdad
    y el paso 5 trae el registro de cuentas.
14. **B3 y B4 siguen con `_identidad`.** La copia sin btw-id también se
    escapaba de B3 y B4; ahora la para F3 si trae otro IBAN. Unificar la
    identidad de todas las reglas es del paso 2.
15. **Recuentos frente a sumas en X1.** «Fuera de todos los totales» se lee
    como fuera de toda suma (importes y horas) y de todos los agregados por
    mes, proveedor, régimen, semana, proyección y simulador. Los recuentos de
    la tabla (`facturas`, `proveedores`, `criticas`, `por_revisar`) la
    cuentan, porque la fila está ahí y hay que resolverla.


## Paso 1

Almacén, evidencia y auditoría, con la migración de `out/` sin una sola
llamada a la API. **414 tests pasan** (295 funciones de test; eran 314 y
207), ninguno llama a la API y ninguno escribe fuera de una carpeta temporal.
Las cifras incluyen las correcciones de la revisión (al final de este
apartado).

### Qué se construyó

**Módulos nuevos**

| Módulo | Qué hace |
| --- | --- |
| `almacen/__init__.py` | `abrir()` (claves foráneas, WAL, `busy_timeout=5000`, `sqlite3.Row`, se niega a correr en SQLite < 3.37), `transaccion()` (`BEGIN IMMEDIATE`; dentro de otra, un `SAVEPOINT` que deshace solo lo suyo), `preparar()` (abre, migra y devuelve un `Almacen` = conexión + carpeta de documentos), `usuario_sistema()`, `ruta_por_defecto()` (`BMS_DB` o `datos/bms.sqlite3`), `ruta_anclas_de()` (`anclas.log` al lado de la base, que también lleva `Almacen.ruta_anclas`). La conexión lleva su reloj: `conn.reloj` |
| `almacen/migrar.py` + `almacen/sql/0001_almacen.sql` | Migraciones `NNNN_nombre.sql`, de una en una, cada una en su transacción con su fila en `migracion` (sha256) y su evento `migracion_aplicada`. Una migración aplicada que cambia, o que falta, detiene todo (`MigracionAlterada`) |
| `almacen/unidades.py` | `a_cent`, `a_mil`, `a_e4`, `a_pb` y sus inversas: solo `Decimal` o `int`, nunca `float`, y `PerdidaDePrecision` en vez de redondear (comprobado con aritmética de enteros, sin la precisión del contexto); `FueraDeRango` si no cabe en 64 bits. `json_canonico()` (claves ordenadas, sin espacios, rechaza floats) y los hash |
| `almacen/documentos.py` | `AlmacenDocumentos`: `datos/documentos/<sha[:2]>/<sha256>.<ext>`, 0444, escritura a un temporal que se enlaza con `os.link` (no pisa nunca; un original alterado hace fallar `guardar` en vez de repararse en silencio). `registrar_documento()`, `abrir()` (cada apertura es un evento, también la que falla; se niega a correr dentro de una transacción abierta), `verificar()` (vuelve a calcular cada hash; un fichero que nadie apunta es un aviso) |
| `almacen/extracciones.py` | `leer_registro()` (el texto tal cual y sus columnas; rechaza `NaN` e `Infinity`), `registrar_extraccion()` (única por documento, modelo, versiones y hash del contenido; apunta el nombre del fichero de `out/`) y `en_orden_de_out()` |
| `almacen/evidencia.py` | `foto()` (las columnas de una fila de evidencia, que van en los datos de su evento), `verificar_evidencia()` (cada extracción rehasheada, cada fila igual a la foto de su evento, ningún evento sin fila) y `verificar_esquema()` (tablas, vistas, índices y disparadores iguales a los que crean las migraciones aplicadas) |
| `auditoria.py` | `registrar()` (evento encadenado, con sus `cambio_campo` dentro del hash, todo en su `SAVEPOINT`), `verificar_cadena()`, `identidad()` (el hash del primer evento), `anclar()`, `leer_anclas()`, `historial()` |
| `importadores/extracciones.py` | `importar_out()`: cada `out/*.json` al almacén, tal cual, con su PDF si se encuentra por hash |
| `legado.py` | `registros_legado(conn)`: los diccionarios de siempre, sacados de la extracción vigente de cada documento |
| `reloj.py` | `Reloj` (`ahora()` en UTC, `hoy()` en Amsterdam), `RelojFijo`, `marca()` |

**Tablas** (migración 0001): `migracion`, `usuario` (con los cuatro de sistema
sembrados), `permiso` (los 14), `rol`, `rol_permiso`, `usuario_rol`,
`politica_version`, `evento`, `cambio_campo`, `documento`, `extraccion`,
`importacion`, y la vista `v_extraccion_vigente`. Todas STRICT, con clave
`INTEGER PRIMARY KEY`, sin ninguna columna REAL.

| Tabla | Qué no se puede hacer |
| --- | --- |
| `migracion`, `politica_version`, `evento`, `cambio_campo`, `extraccion` | `UPDATE` ni `DELETE`, nunca |
| `documento` | `UPDATE` ni `DELETE`, salvo apuntar el original una vez (ver desviaciones) |
| `importacion` | Modificarla después de cerrarla, cambiar de fichero, borrarla |
| `usuario` | Borrarlo; cambiar si es de sistema; renombrar uno de sistema; darle token a uno de sistema |
| `usuario_rol` | Dar un rol a un usuario de sistema; tocar una asignación salvo cerrarla, una vez; borrarla |
| `evento` | Entrar con un id o un `hash_anterior` que no siguen al último; poner un usuario de sistema en `usuario_id` |
| `cambio_campo` | Colgarse de un evento que no es el último (el de la orden en curso); una `manual_correccion` sin motivo |

**Órdenes**

- `bms-agent db init` crea el almacén y migra; `db migrar` migra uno que ya
  existe (y se niega si no existe, para no crear una base en el sitio
  equivocado). Las dos anclan al terminar. `db verificar [--anclas …]
  [--sin-anclas]` comprueba `integrity_check`, `foreign_key_check`, el hash
  de cada migración, el esquema contra el de las migraciones, la cadena de
  auditoría con sus anclas (por defecto `anclas.log` al lado de la base),
  cada fila de evidencia contra su evento y el hash de cada original. Sale
  con 1 si algo no cuadra, si la base no está migrada y si no hay ninguna
  ancla de esa base (salvo con `--sin-anclas`); dice cuántos eventos hay
  después de la última ancla.
- `bms-agent importar-out [--out out] [--pdfs facturas] [--db …]`. Una
  transacción para toda la orden. Cada fichero bueno da un `documento` (si no
  estaba), una `extraccion` con `via = 'out_v1'` y una `importacion`
  aceptada; cada fichero malo, una `importacion` rechazada con su motivo.
  Repetirla no añade filas (solo un evento por cada original que aparece
  después con `--pdfs`). Cada fichero va en su `SAVEPOINT`: lo que la base
  rechaza (un `CHECK`) es una importación rechazada más, no una orden caída.
  Al final ancla la cabeza en `datos/anclas.log`.
- `extract` y `serve` (y la página local) abren el almacén **antes** de
  gastar nada, escriben cada documento en `out/` y en el almacén con el mismo
  texto, y anclan al terminar. Las dos aceptan `--db`.

**Documentación**: README (órdenes nuevas), `docs/fase-0.md` (apartado «El
almacén»), el recuento de tests en README, `fase-0.md`,
`instalacion-windows.md` y `brief-diseno.md`, `.gitignore` (`/datos/`),
`.gitattributes` (las migraciones siempre con LF) y `pyproject.toml` (los
`.sql` como datos del paquete y `tzdata` solo en Windows).

### La puerta, test por test

| Puerta | Tests |
| --- | --- |
| `UPDATE` y `DELETE` abortan en cada tabla de solo escritura | `test_almacen.py::test_update_y_delete_abortan_en_cada_tabla_de_solo_escritura` (las siete tablas, con un `UPDATE` que no cambia nada, uno que sí y un `DELETE`; el mensaje prueba que es el disparador) y `test_la_lista_de_tablas_de_solo_escritura_esta_completa` (toda tabla con disparador `<tabla>_sin_delete` tiene que estar en la prueba) |
| La cadena encuentra una fila editada por una conexión directa después de borrar los disparadores | `test_auditoria.py::test_la_cadena_encuentra_una_fila_editada_sin_disparadores`, y además: el hash rehecho (`..._rompe_el_enlace_con_la_siguiente`), un `cambio_campo` editado, un evento borrado por en medio, el final cortado y el final reescrito (los dos últimos solo con anclas), y por la CLI `test_migracion_out.py::test_db_verificar_encuentra_un_evento_tocado_por_detras`. Las filas de evidencia, por la CLI: `test_una_extraccion_metida_por_detras_no_cuadra` (con los disparadores intactos), `test_una_extraccion_editada_y_con_el_disparador_repuesto_no_cuadra`, `test_filas_de_evidencia_editadas_sin_disparadores_no_cuadran` (extracción, documento, importación y una extracción borrada), `test_un_disparador_cambiado_o_de_mas_no_cuadra` y `test_sin_anclas_no_se_da_por_buena_una_cadena_cortada` |
| El almacén de documentos no sobrescribe y detecta un hash que no cuadra | `test_almacen.py::test_guardar_es_de_una_vez_y_de_solo_lectura`, `test_el_almacen_no_sobrescribe_un_original_alterado`, `test_verificar_vuelve_a_calcular_cada_hash`, `test_abrir_un_documento_queda_auditado_tambien_si_falla`, y `db verificar` en `test_db_init_migrar_y_verificar` |
| `importar-out` dos veces da los mismos recuentos y lo guardado es byte a byte el fichero | `test_migracion_out.py::test_importar_dos_veces_da_los_mismos_recuentos`, `test_lo_guardado_es_byte_a_byte_el_fichero`, `test_la_orden_de_la_cli_no_llama_a_la_api` (por la CLI), y con `extract` delante y un `out/` con CRLF `test_almacen_extraccion.py::test_un_fichero_con_crlf_entra_una_sola_vez` |
| Un PDF que no está deja `ruta_cas` NULL | `test_un_pdf_que_no_esta_deja_ruta_cas_vacia` (las 04 a 07 no tienen PDF), `test_sin_carpeta_de_pdf_todo_queda_sin_original_y_se_anade_despues` |
| `import anthropic` parcheado para lanzar: cero llamadas | `test_la_orden_de_la_cli_no_llama_a_la_api`: `importar-out` dos veces y `db verificar` en un proceso nuevo con un buscador de módulos que hace lanzar `import anthropic` desde antes de importar `bms_agent` (ve también un import al cargar un módulo), y que al final comprueba que no se cargó; `test_el_bloqueo_de_la_api_funciona` prueba el bloqueo |
| `construir_datos(registros_legado(db))` es `construir_datos(load_records(out))` | `test_equivalencia_legado.py::test_el_panel_desde_el_almacen_es_el_panel_desde_out` (y las dos son la foto de referencia byte a byte), `test_los_registros_son_los_mismos_diccionarios`, `test_con_varias_extracciones_vale_la_misma_vigente_que_en_out`, y sin ordenar nada, con B2 saltando y la vigente en el último fichero, `test_el_orden_es_el_de_out_tambien_con_varias_extracciones`; con fechas que no son ISO o con otro offset, `test_con_fechas_raras_vale_la_regla_de_load_records` |
| `extract` y `serve` escriben en el almacén y en `out/` | `test_almacen_extraccion.py` (nueva, reutilizada, fallo del almacén, CLI, servidor) |

### Desviaciones de la especificación, y por qué

1. **`evento` no se sella con un `UPDATE`.** El id se fija antes de insertar
   (el último más uno, seguro dentro de `BEGIN IMMEDIATE`) y el hash se
   calcula antes del `INSERT`, así que `evento` no admite ningún `UPDATE`. Es
   más estricto que la excepción que la especificación permitía. El
   disparador `evento_encadenado` rechaza además un evento cuyo id o
   `hash_anterior` no siguen al último; que el hash sea el correcto solo lo
   puede comprobar `verificar_cadena()` (SQLite no calcula sha256).
2. **El hash del evento cubre sus `cambio_campo`.** Sin eso, borrar los
   disparadores y editar un `valor_anterior` no dejaría rastro. Por eso un
   `cambio_campo` solo se puede colgar del último evento, y solo se escribe a
   través de `auditoria.registrar(..., cambios=[Cambio(...)])`.
3. **`usuario_id` y `actor`.** En `evento`, `usuario_id` es la persona que
   pidió la acción (un disparador impide poner ahí un usuario de sistema) y
   `actor` es una clave foránea a `usuario`: quien la ejecutó, de sistema o la
   propia persona. Igual en `importacion` (`iniciada_por`, `actor`). En el
   paso 1 no hay personas: la CLI y el servidor dejan `usuario_id` y
   `iniciada_por` a NULL y actúan como `extractor` o `importador`.
4. **`factura_id` sin clave foránea** en `evento` y `cambio_campo`. SQLite
   no deja declarar una clave foránea hacia una tabla que no existe: con
   `foreign_keys=ON` falla hasta el `INSERT` con NULL (comprobado en 3.45.1).
   La tabla `factura` llega en la 0002.
5. **`documento` admite una sola modificación**: apuntar el original cuando
   llega después (`ruta_cas` de NULL a su ruta, y `bytes` de NULL a su
   tamaño), y nada más. Sin ella, una extracción importada sin su PDF
   quedaría sin original para siempre. Un `CHECK` obliga a que `ruta_cas` sea
   `<sha[:2]>/<sha256>.<ext>` de su propio hash.
6. **Tabla `permiso`** (no está en la lista de la especificación) en vez de
   un `CHECK` en `rol_permiso`: la pregunta 9 del §12 puede cambiar la lista,
   y en SQLite cambiar un `CHECK` obliga a reconstruir la tabla. Se siembran
   los 11 del §19 más los 3 propuestos.
7. **`usuario.nombre` es UNIQUE** (los de sistema se buscan por nombre y una
   persona necesita un identificador para la CLI) y un usuario de sistema no
   puede tener token.
8. **`importacion` por fichero.** Cada `out/*.json` es una importación
   (`fuente 'extracciones'`, `tipo 'extraccion'`, `formato
   'json:extraccion-s<versión>'`, una fila leída). Su `documento_id` apunta
   al PDF del que habla la extracción: el JSON no se guarda también como
   documento porque su texto ya está, entero, en `extraccion.contenido_json`.
   Columnas añadidas: `iniciada_en` y `terminada_en`; los recuentos son
   `filas_leidas`, `filas_aceptadas` y `filas_rechazadas`. `fuente` y `tipo`
   no llevan una lista cerrada en un `CHECK` porque crecerán en el paso 5.
9. **`extraccion.registrada_en`** (columna añadida: cuándo entró en el
   almacén, que no es cuándo se extrajo). `extraido_en` es el `extracted_at`
   del registro pasado a UTC con `reloj.marca()`, y queda NULL si no es un
   instante ISO o no lleva zona horaria; el texto original sigue en
   `contenido_json`.
10. **La extracción vigente del almacén es una vista**,
    `v_extraccion_vigente`: la de `extraido_en` (UTC) mayor y, en empate, la
    que entró después. `factura.extraccion_vigente_id` es del paso 2, porque
    `factura` también. **`registros_legado` no usa la vista**: aplica la
    misma función que `load_records` (`report.vigentes`, que compara el texto
    de `extracted_at`) sobre las extracciones en el orden de `out/` (el nombre
    del fichero que se apuntó al registrarlas). Las dos reglas coinciden con
    lo que escribe el extractor (UTC con `+00:00`); difieren con un
    `extracted_at` que no es ISO (`load_records` lo compara como texto, la
    vista lo deja en NULL) o con otro offset (como texto `09:00+02:00` va
    después de `08:00+00:00`; como instante, antes). Lo fija
    `test_con_fechas_raras_vale_la_regla_de_load_records`. El paso 2 decide
    con `factura.extraccion_vigente_id` y deja la regla del texto atrás.
11. **Lo que `importar-out` rechaza no sale en `registros_legado`**: un JSON
    sin `source_sha256` válido, o sin `model`, `prompt_version` o
    `schema_version`, no se puede atar a un documento. `load_records` sí lo
    devolvía. Con un `out/` escrito por el extractor no hay ninguno.
12. **`extract` hace una transacción por documento**, no una por orden: cada
    documento es una llamada pagada, y un fallo en el 40 no tiene que
    deshacer los 39 anteriores. Si el almacén falla, la pasada sigue (la
    extracción ya está en `out/`), lo cuenta en `sin_almacen`, lo avisa y sale
    con 1. Los documentos que se reutilizan de `out/` también entran en el
    almacén (`via 'out_v1'`), así que el siguiente `extract` arregla lo que
    faltó sin pagar. Lo que entra son los bytes del fichero de `out/`, leídos
    del disco, tanto si se acaba de escribir como si se reutiliza: así
    `extract` e `importar-out` dan siempre el mismo hash.
13. **Las migraciones se aplican solas** al abrir el almacén desde `extract`,
    `serve` e `importar-out` (`preparar()`): cada una está fijada por su hash,
    así que aplicarla es determinista. El hash se calcula con los finales de
    línea en LF, para que un checkout de Windows no parezca una migración
    editada.
14. **`reloj.py` llega ya**, mínimo (`ahora`, `hoy` en Amsterdam,
    `RelojFijo`, `marca`), porque todo lo que escribe una hora la necesita
    inyectable. Las semanas ISO siguen en `dashboard.py`. Los usuarios
    sembrados por la migración llevan la hora de SQLite, no la del reloj.
15. **Anclas**: no hay informe diario todavía, así que `anclar()` escribe en
    `anclas.log` **al lado de la base** (`datos/anclas.log`, no
    `out/anclas.log` como dice la especificación) al final de `db init`,
    `db migrar`, `importar-out`, `extract` y cada pasada del servidor, solo
    si la cabeza ha cambiado. Al lado de la base porque una base se alimenta
    desde varias carpetas `--out` y `db verificar` tiene que encontrar lo
    que escribieron todas. Cada línea lleva una cuarta columna, la identidad
    de la base: el hash de su primer evento, que lleva un identificador al
    azar en sus datos. Solo se comprueban las anclas de esa base; una línea
    de tres columnas (de antes) se comprueba siempre. Sin ninguna ancla de
    esa base, `db verificar` falla (salvo `--sin-anclas`).
16. **`politica_version`** es única por `(fichero, sha256, vigente_desde)`
    (volver a una política anterior es otra fila) y `vigente_desde` es una
    fecha. No hay cargador: `politica.py` es de un paso posterior.
17. **No se usa `tzdata`**, pero se declara en `pyproject.toml` solo para
    Windows, que es donde falta la base de zonas horarias que necesita
    `hoy()`. Aquí no se puede instalar nada; en Linux no hace falta.

### Lo que deben saber los pasos siguientes

- **Fixtures** (`tests/conftest.py`): `db` (en memoria, migrada, con el reloj
  fijo del 2026-10-14 09:30 UTC), `reloj` (`RelojFijo`, `avanzar(hours=…)`),
  `almacen` (`db` + carpeta de documentos temporal), `pdfs_ejemplo` (los tres
  PDF del generador), `out_v1` (copia de las siete extracciones v1) y las
  constantes `RAIZ`, `FIXTURES_V1`, `TARIFAS_V1`, `GOLDEN`. Una fixture
  automática apunta `BMS_DB` a una carpeta temporal en **todos** los tests:
  `extract` y el servidor escriben en el almacén y, sin ella, lo harían en
  `datos/` del repositorio.
- **Escribir**: dentro de `with transaccion(conn):`, y el evento con
  `auditoria.registrar(conn, tipo=…, actor=…, cambios=[Cambio(...)])`.
  `registrar` lanza si no hay transacción abierta. `campos.py` (paso 2) tiene
  que escribir sus `cambio_campo` así, no con `INSERT` propios: el disparador
  solo los deja colgar del último evento y la verificación los incluye en el
  hash. Los valores de `Cambio` se guardan en JSON canónico (un `float` lanza).
- **Una tabla nueva de solo escritura** lleva los disparadores
  `<tabla>_sin_update` y `<tabla>_sin_delete`, una fila en `_poblar` y su
  nombre en `SOLO_ESCRITURA` de `tests/test_almacen.py`: el test de la lista
  completa falla si no.
- **Una tabla nueva de evidencia** (factura, sus líneas…) añade sus columnas
  a `evidencia.COLUMNAS` y sus tipos de evento (alta y modificaciones) a
  `evidencia.EVENTOS`, y quien la escribe pone `"fila": foto(conn, tabla,
  id)` en los datos de cada evento que la da de alta o la cambia: así
  `db verificar` ve una fila metida o editada por detrás. Lo mismo
  `usuario_rol` y `rol_permiso` cuando `permisos.py` (paso 2) escriba sus
  eventos; en el paso 1 nadie las escribe.
- **Abrir un original** (`documentos.abrir`) va fuera de la transacción de
  la orden: dentro se niega, porque el `ROLLBACK` de la orden se llevaría el
  registro de una apertura fallida.
- **Migraciones**: la 0002 es un fichero nuevo; la 0001 no se toca nunca
  (cambiar un byte que no sea un final de línea la da por alterada). Para
  validar `factura_id` en `evento` y `cambio_campo` hará falta un disparador
  `BEFORE INSERT` (o reconstruir las tablas, que rompe la regla de no
  tocar la evidencia: mejor el disparador).
- **La vigente**: `v_extraccion_vigente` es provisional. El paso 2 la
  sustituye por `factura.extraccion_vigente_id` y `registros_resueltos()`;
  `registros_legado` puede seguir leyendo la vista.
- **Quién lee qué**: el panel, el informe, `export`, `score`, `coste`,
  `simulador` y `/api/datos` siguen leyendo `out/` (son del paso 2). La foto
  de referencia no ha cambiado.
- **Documentos**: `documento.ruta_cas` NULL es el caso Q4 (sin original); en
  las fixtures, las 04 a 07. `ruta_declarada` la pone la vía de entrada:
  `extract`, `serve` e `importar-out` ponen `entrante`. `origen` es
  `carpeta` para `extract` y `serve`, `out_v1` para `importar-out`.
  `recibido_fuente` es `mtime` cuando se tiene el PDF y `desconocido` cuando
  no.
- **Usuarios de sistema**: `usuario_sistema(conn, "sistema" | "extractor" |
  "importador" | "motor")`. No hay roles sembrados ni personas: los crea el
  paso 2 (`permisos.py`). Los permisos están en la tabla `permiso`.
- **Horas**: `conn.reloj.ahora()` (o `reloj_de(conn)` para una conexión que
  no salió de `abrir()`); `reloj.marca()` da el formato del almacén
  (`2026-10-14T09:30:00+00:00`). Los `CHECK` de instante solo exigen que
  `datetime()` lo entienda.
- **Importes**: `almacen.unidades` es el único conversor a enteros; el paso
  2 lo usa al tipar las facturas.

### Correcciones de la revisión

Dieciocho hallazgos de la revisión, cada uno reproducido antes de tocar
nada; varios eran el mismo defecto visto desde dos sitios. Son 20 funciones
de test nuevas (26 casos con los parametrizados) y seis cambiadas. Con el
código del commit `82117fa` fallan 28 casos (24 nuevos y 4 cambiados); de
los que pasan, los que importan son la comparación byte a byte de
`write_json` (en Linux no hay CRLF: protege Windows), el caso «por la tarde»
del test de `extracted_at` (ya quedaba NULL; fija el comportamiento) y el
que comprueba que el bloqueo de la API funciona. Los tests cambiados que
miraban `out/anclas.log` (`test_la_cli_extract_escribe_en_el_almacen_de_bms_db`,
`test_la_orden_de_la_cli_no_llama_a_la_api`, `test_db_init_migrar_y_verificar`)
cambian porque las anclas cambian de sitio (desviación 15).

| Hallazgo | ¿Real? | Qué se hizo | Tests |
| --- | --- | --- | --- |
| En Windows `write_json` escribía CRLF, `_al_almacen` leía con `read_text` (que cambia CRLF por LF) e `importar-out` hasheaba los bytes: cada extracción entraba dos veces y `coste` contaba doble | Sí | `write_json` abre con `newline=''`; `_mismo_contenido` compara bytes; `_al_almacen` guarda siempre los bytes del fichero de `out/` (`read_bytes().decode`), nuevo o reutilizado | `test_el_registro_que_se_guarda_es_el_mismo_texto_que_el_fichero` (ahora bytes), `test_un_fichero_con_crlf_entra_una_sola_vez` |
| `registros_legado` salía por orden de documento y `load_records` por orden de fichero: con varias extracciones de un documento, `construir_datos` difería (las facturas de B2 en otro orden) | Sí | `registrar_extraccion` apunta en su evento el nombre del fichero de `out/`; `en_orden_de_out()` ordena por él (como `Path`) y `registros_legado` aplica `report.vigentes`, la misma función que `load_records`. También con `todas=True` | `test_el_orden_es_el_de_out_tambien_con_varias_extracciones` |
| `importar-out` solo capturaba `UnicodeDecodeError` y `RegistroInvalido`: un `CHECK` (un `extracted_at` que SQLite no entiende, un `NaN`) deshacía la orden entera con una traza | Sí | `_instante` normaliza a UTC (abajo); `leer_registro` rechaza `NaN`/`Infinity` con `parse_constant`; cada fichero va en su `SAVEPOINT` y un `sqlite3.IntegrityError` da una importación rechazada con el motivo. `extract` ya no promete que `importar-out` recupera un registro inválido | `test_nan_o_infinity_se_rechazan_sin_tumbar_la_orden` (por la CLI), `test_lo_que_la_base_rechaza_es_una_importacion_rechazada` |
| `registrar()` insertaba el evento y sus `cambio_campo` sin `SAVEPOINT`: si un cambio fallaba y quien llama capturaba el error, quedaba un evento cuyo hash cubría cambios que no existen | Sí | El cuerpo de `registrar()` va en `with transaccion(conn):` | `test_una_correccion_manual_sin_motivo_no_entra` (ahora también: ningún evento de más y la cadena verifica) |
| `extraido_en` guardaba el texto crudo: sin normalizar a UTC, mal ordenado entre offsets, y la vista y `load_records` elegían distinta vigente con un `extracted_at` raro | Sí | `extraido_en` es `marca(fromisoformat(x))` (UTC); sin zona, NULL. La vista ordena instantes; `registros_legado` sigue la regla de `load_records`, y la diferencia queda escrita (desviación 10) | `test_un_extracted_at_que_python_lee_y_sqlite_no_se_guarda_en_utc` (siete formas), `test_con_fechas_raras_vale_la_regla_de_load_records` |
| Las anclas no decían de qué base eran: dos bases con el mismo `out/` daban por reescrita una base intacta | Sí | Cuarta columna con la identidad de la base (hash del primer evento, con un identificador al azar); se comprueban solo las suyas y se avisa de las ajenas | `test_dos_bases_pueden_compartir_el_fichero_de_anclas`, `test_una_linea_sin_identidad_se_comprueba_igual`, `test_cada_base_tiene_su_identidad`, `test_las_anclas_van_con_la_base_y_no_con_la_carpeta_out` |
| `migrar()` calculaba lo pendiente antes del cerrojo: dos procesos que abren una base nueva a la vez chocaban | Sí | Si aplicar falla con un error de SQLite, se deshace y se vuelve a mirar `migracion`: si la versión ya está con el mismo hash, la aplicó el otro y se sigue. La clave de `migracion.version` garantiza que una migración que se puede repetir sin error también falla. No se toma el cerrojo antes porque `executescript()` hace `COMMIT` de lo abierto | `test_dos_procesos_que_migran_a_la_vez_no_chocan` |
| `db verificar` sobre un fichero sin migrar daba una traza | Sí | Si no hay ninguna migración aplicada, lo dice y sale con 1 | `test_verificar_una_base_sin_migrar_lo_dice_sin_traza` |
| El test de cero llamadas parcheaba `sys.modules` después de importar `bms_agent`: un `import anthropic` al cargar un módulo no se habría visto | Sí | El test corre la CLI en un proceso nuevo con un buscador de módulos que bloquea `anthropic` antes de importar nada, y comprueba al final que no se cargó | `test_la_orden_de_la_cli_no_llama_a_la_api`, `test_el_bloqueo_de_la_api_funciona` |
| `db verificar` no miraba las filas de evidencia: una extracción insertada por detrás (otro IBAN) o editada con el disparador quitado y repuesto daba «Todo cuadra» (dos hallazgos) | Sí | Nuevo `almacen/evidencia.py`. Cada evento de alta o cambio de `documento`, `extraccion` e `importacion` lleva la foto de la fila; `verificar_evidencia` rehashea cada `contenido_json`, exige a cada fila exactamente un evento de alta y que sea igual a la foto del último, y señala los eventos cuya fila ya no existe; también cada `migracion` contra su evento. `verificar_esquema` compara el esquema con el de las migraciones aplicadas en una base en memoria: un disparador que falta, cambia o sobra es un error | `test_una_extraccion_metida_por_detras_no_cuadra`, `test_una_extraccion_editada_y_con_el_disparador_repuesto_no_cuadra`, `test_filas_de_evidencia_editadas_sin_disparadores_no_cuadran`, `test_un_disparador_cambiado_o_de_mas_no_cuadra` |
| Sin fichero de anclas `db verificar` pasaba, y las anclas iban a la carpeta `--out` de cada orden mientras `verificar` leía `out/anclas.log` | Sí | Las anclas van al lado de la base (desviación 15) y también las escriben `db init` y `db migrar`; sin ninguna ancla de la base es un error salvo `--sin-anclas`; se dice cuántos eventos van detrás de la última | `test_sin_anclas_no_se_da_por_buena_una_cadena_cortada`, `test_las_anclas_van_con_la_base_y_no_con_la_carpeta_out`, `test_db_init_migrar_y_verificar` |
| `_instante()` aceptaba lo que lee Python y no SQLite (`20260920T100012Z`, `2026-W38-1`): una sola extracción así tumbaba `importar-out` | Sí, el mismo que el tercero y el quinto | Ver arriba | Ver arriba |
| `documentos.abrir()` dentro de la transacción de quien llama: el `ROLLBACK` al recibir `DocumentoCorrupto` borraba el registro de la apertura fallida (dos hallazgos) | Sí | `abrir()` se niega con `RuntimeError` si hay una transacción abierta, como `migrar()` | `test_abrir_dentro_de_una_transaccion_se_niega` |
| `_a_entero` redondeaba en silencio con más de 100 cifras (`scaleb` redondea a la precisión del contexto antes de comprobar) | Sí | La exactitud se comprueba con aritmética de enteros sobre los dígitos de `as_tuple()`, sin contexto; un resultado fuera del entero de 64 bits lanza `FueraDeRango` antes de llegar a SQLite | `test_la_exactitud_no_depende_de_la_precision_del_contexto` |
| `extracted_at` sin dos puntos en el offset (`+0000`) tumbaba `importar-out`, y `+02:00` se guardaba sin pasar a UTC | Sí, el mismo que el tercero | Ver arriba | Ver arriba |
| `v_extraccion_vigente` no aplicaba la regla de `load_records` con un `extracted_at` que no es ISO, aunque la desviación 10 decía que sí | Sí | Se escribió la diferencia en la desviación 10 y `registros_legado` ya no depende de la vista | `test_con_fechas_raras_vale_la_regla_de_load_records` |

**Lo que no se tocó.** La migración 0001 sigue igual byte a byte: todo lo
de arriba cabe en código y en los datos de los eventos, sin columnas
nuevas. Las bases creadas antes de esta corrección no pasan
`db verificar`: sus eventos no llevan la foto de cada fila ni sus anclas
están al lado de la base. Como `out/` sigue siendo la fuente, se rehacen con
`db init` en una ruta nueva e `importar-out`.


## Paso 2

Núcleo tipado, una sola vía de escritura, procedencia de cada campo y
permisos. **582 tests pasan** (406 funciones de test; eran 414 y 295 al
terminar el paso 1, y 537 y 385 antes de la revisión), ninguno llama a la
API y ninguno escribe fuera de una carpeta temporal. Lo que cambió con la
revisión está al final, en «Correcciones de la revisión».

### Qué se construyó

**Módulos nuevos**

| Módulo | Qué hace |
| --- | --- |
| `dominio.py` | Los enumerados del dominio (`Sentido`, `Fuente` con sus siete valores, `Calidad`, `EstadoPago`, `EstadoRevision`, `EstadoExcepcion`, `Prioridad`, `Severidad`, `TipoRelacion`, `EstadoRelacion`, `ClaseReferencia`, `EstadoBtw`, `Permiso`, `TratamientoIva`…), con el mismo texto que los `CHECK` de la base (un test lo compara) |
| `campos.py` | El registro de campos (`REGISTRO`: tipo, obligatorio por sentido, editable, permiso para suplir y para corregir, si su dueño puede ser Exact o TRNSPRNT, crítico, cálculo y de qué depende) y la única vía de escritura de las tablas controladas: `orden()` y los atajos `crear`, `fijar`, `retirar`, `verificar_campos`, `recalcular`, `anadir_nota`. Lectura: `leer`, `procedencia`, `estado_campo` (editado, suplido, corregido, sin resolver, dudoso, verificado). `verificar_controladas()` para `db verificar` |
| `permisos.py` | Los 14 permisos, roles de partida (`administrador`, `administracion`, `consulta`), personas, `tiene`, `exigir` (lanza `PermisoDenegado` y deja la denegación en la auditoría), `orden_auditada`, `personas_con`, `si_hay_dos` y `separacion` |
| `identidad.py` | Normalización y búsqueda exacta: btw-id, luego KvK, luego alias confirmado; Objetos por código o alias, recursos por alias. Nunca por IBAN ni por parecido. `anadir_alias` rechaza un IBAN y un alias que ya es de otra fila |
| `compat.py` | Lee una extracción v1 con la forma v2 sin tocar la guardada; lo que v1 no pidió queda «no solicitado en v1» (`no_solicitados`, `ExtraccionLeida.estado`) |
| `ingesta.py` | La vía de entrada única de la CLI y del servidor: `ingestar_pasada` (almacén de documentos, extracción según la política de caché y tipado), `tipar_documento`, `tipar_pendientes`, `reconciliar_referencias`, `leer_literal` y `vigentes_por_documento`. La dirección la decide `documento.ruta_declarada` |
| `importadores/tarifas.py` | `sembrar_tarifas`: clientes, Objetos y tarifas de venta de `config/tarifas.yaml` (o de cualquier fichero con esa forma), con el fichero en `politica_version` |
| `legado.py` (ampliado) | `registros_resueltos()` (los diccionarios de siempre con los valores actuales de cada factura tipada), `sin_tipar()`, `literal_decimal()` y `leer_registros()` (almacén si existe; `out/` si no, y lo dice) |
| `scripts/generar_guardas.py` | Escribe los disparadores de guarda de una tabla controlada a partir de sus columnas; los de la 0002 salen de aquí (un test lo comprueba) |

**Cambios**: `parsing.normalizar_referencia`, `reloj.semana_iso`,
`extract.extraer_pasada(..., ruta=)` (la vía de entrada llega hasta el
documento), `almacen/evidencia.py` (personas, roles y asignaciones con su
foto, como pedía el paso 1), `serve.py` (el botón pasa por `ingesta`,
`/api/datos` lee del almacén) y `cli.py`.

**Tablas** (migración `0002_nucleo_tipado.sql`), todas STRICT, con clave
entera y sin ninguna columna REAL:

| Clase | Tablas |
| --- | --- |
| Controladas (TRACKED) | `proveedor`, `cliente`, `contacto`, `objeto`, `recurso`, `alias`, `tarifa_acordada`, `factura`, `factura_linea`, `factura_imputacion`, `factura_iva`, `factura_referencia`, `factura_relacion` |
| Una fila por campo | `procedencia_campo` |
| Solo escritura | `nota` |
| Vista | `v_factura_ediciones` (editada, suplementada, corregida, sin resolver) |

Cada controlada lleva tres disparadores generados columna a columna:
`<tabla>_guarda_insert` (entra con rev 0 y cada columna con valor tiene su
`cambio_campo` con ese valor en el evento en curso), `<tabla>_guarda_update`
(rev sube de uno en uno, hay un `cambio_campo` de la fila con la rev nueva,
y cada columna que cambia tiene el suyo con el valor anterior y el nuevo
exactos, en el evento en curso) y `<tabla>_sin_delete`. Además: el sentido
de una factura no cambia, la extracción vigente es del propio documento, una
imputación o una referencia es de una línea de su factura, una relación une
dos facturas del mismo sentido, un alias apunta a una fila que existe y no
tiene la forma de un IBAN, una nota la escribe una persona y quien verifica
un campo es una persona.

**Órdenes**

- `bms-agent importar-out` lleva `out/` al almacén y después tipa cada
  extracción; `extract` y el botón del servidor también tipan lo que
  extraen. Cero llamadas a la API en el tipado.
- `bms-agent ingestar [--db]`: tipa lo extraído que todavía no tiene su
  factura, o cuya extracción vigente cambió.
- `bms-agent sembrar [--tarifas config/tarifas.yaml] [--db]`.
- `bms-agent usuario crear NOMBRE [--email] [--rol ROL]…`, `usuario asignar
  NOMBRE ROL`, `usuario quitar NOMBRE ROL`, `usuario listar`.
- `panel`, `report`, `export` y `simulador` aceptan `--db` y leen del
  almacén con los valores corregidos; sin almacén leen `out/` y lo dicen
  («No hay almacén en …: se lee out/ tal cual, sin correcciones»).
- `db verificar` comprueba además cada fila controlada contra su historia
  (`campos.verificar_controladas`) y cuenta las facturas tipadas.

**Cómo decide `campos`** (spec §6): una fuente automática no pisa nunca un
valor manual (solo apunta `valor_automatico`, y si no coincide el campo
queda sin resolver, M1); el valor de una persona es `manual_entrada` si el
campo no tenía original automático y `manual_correccion` si lo tenía, y eso
lo decide el sistema; un valor manual igual al último automático deshace la
corrección y devuelve el campo a esa fuente con su referencia; el original y
su literal no cambian nunca; un campo cuyo dueño es Exact o TRNSPRNT no se
edita aquí. Una orden es una transacción con un solo evento: se planifica
entera (permisos, motivos, cálculos), se registra el evento con todos sus
`cambio_campo` y después se escriben las filas y su procedencia.

### La puerta, test por test

| Puerta | Tests |
| --- | --- |
| El original sobrevive a dos correcciones | `test_campos.py::test_el_original_sobrevive_a_dos_correcciones` (valor, literal y fuente originales, y la historia de los tres cambios) |
| El sistema, no quien edita, decide entre suplido y corregido | `test_el_sistema_decide_entre_suplir_y_corregir`, `test_corregir_una_lectura_ilegible_es_corregir` (y que `Automatico("manual_entrada", …)` no se puede construir) |
| Deshacer devuelve la fuente original | `test_deshacer_devuelve_la_fuente_original`, `test_un_suplido_se_deshace_quitandolo` |
| Un automático nunca pisa uno manual | `test_un_valor_automatico_nunca_pisa_uno_manual` (queda en `valor_automatico`, sin resolver y en `v_factura_ediciones`), `test_un_objeto_puesto_a_mano_no_lo_pisa_el_calculo`, `test_ingesta.py::test_una_extraccion_nueva_no_pisa_lo_corregido` |
| Una corrección sin motivo no entra | `test_una_correccion_sin_motivo_no_entra` (sin motivo, vacío o en blanco; ni evento ni cambio), `test_retirar_una_linea_exige_motivo_y_no_la_borra` |
| Un UPDATE fuera de `campos.py` lo rechaza la guarda | `test_un_update_fuera_de_campos_lo_rechaza_la_guarda` (UPDATE suelto, con rev + 1, DELETE, INSERT y la procedencia), `test_la_guarda_exige_el_cambio_de_cada_columna` (un `cambio_campo` de un campo no tapa otro, ni otro valor), `test_las_guardas_cubren_cada_columna`, `test_las_guardas_de_la_migracion_son_las_del_script`, y sin disparadores, `test_db_verificar_ve_una_controlada_tocada_por_detras` |
| … y en el código no hay ninguno | `test_solo_campos_escribe_las_tablas_controladas` (cada texto y cada f-string de `src/`, con una tabla variable como sospechosa, y el fuente plano) y `test_la_busqueda_de_escrituras_ve_lo_que_tiene_que_ver` |
| La foto no cambia a través de `registros_resueltos` | `test_equivalencia_legado.py::test_la_foto_no_cambia_a_traves_de_registros_resueltos` (byte a byte), `test_sin_correcciones_los_resueltos_son_los_de_siempre`, `test_con_varias_extracciones_los_resueltos_siguen_a_la_vigente`, y por la CLI `test_export_lee_del_almacen_y_lo_dice` |

Además: permisos (`test_permisos.py`: catálogo, usuarios de sistema sin
roles ni permisos, denegación auditada dentro y fuera de una orden, roles
que se cierran, `si_hay_dos` tabla a tabla, personas y roles como evidencia,
dominio igual a los `CHECK`), identidad (`test_identidad.py`), compat
(`test_compat.py`: las siete fixtures suben con exactamente las claves
nuevas marcadas), ingesta (`test_ingesta.py`: valores tipados de cada
fixture, X1 sin importes, fecha neerlandesa, abono por el signo, «uren» y
«stuk», ilegibles y dudosos, la vía de entrada decide, extracción nueva,
línea editada que desaparece, una extracción v2 sintética, la semilla, la
CLI y el servidor), que una corrección llega al panel, al informe, al
simulador y a `/api/datos`, y un proceso sin `anthropic` que ejecuta
`importar-out`, `ingestar`, `sembrar`, `export`, `panel`, `report`, `usuario`
y `db verificar`.

### Desviaciones de la especificación, y por qué

1. **`tarifa_acordada` llega en la 0002**, no en la 0004: el paso pide
   sembrar ya las tarifas de venta, y necesitan una tabla. Tiene las
   columnas de la especificación (con `orden_compra_id` sin clave foránea
   hasta la 0006, como `factura_id` en la 0001).
2. **`procedencia_campo` tiene clave entera y `UNIQUE (tabla, fila_id,
   campo)`**, no una clave compuesta `WITHOUT ROWID`: el §4 pide clave
   entera en todas las tablas y `test_almacen` lo comprueba. `tabla` no
   lleva lista cerrada (las controladas crecerán en el paso 7 y cambiar un
   `CHECK` obliga a reconstruir la tabla). Columnas añadidas:
   `fuente_automatica` y `fuente_automatica_ref`, para que deshacer una
   corrección devuelva el campo a la fuente automática **con su
   referencia** (la extracción concreta).
3. **Columnas añadidas a `factura`**: `emisor_direccion_doc`, `tipo_iva_pb`
   (el tipo impreso en la cabecera), `kor_mencionada`,
   `autoliquidacion_mencionada` y `notas_doc`. Todo lo que lee el extractor
   v1 tiene así su sitio tipado (lo necesitan `registros_resueltos` y las
   reglas E3, E4, A5, A7 y Q3).
4. **Una factura v1 no tiene filas en `factura_iva`.** v1 no pide desglose
   por tipo, solo el tipo de la cabecera (`factura.tipo_iva_pb`); inventar
   una fila copiando la cabecera haría que D6 cuadrara siempre y que
   corregir la base dejara el desglose viejo. El desglose v2
   (`vat_breakdown`) ya se mapea. El paso 11 deriva el desglose de una
   factura de un solo tipo desde la cabecera cuando no hay filas.
5. **`retirada_en` en `factura_linea` y `factura_iva`**: una línea se
   excluye (§10) o desaparece en una extracción nueva, y una fila controlada
   no se borra nunca.
6. **`alias`**: columnas `alias` (como se escribió), `confirmado`, `activo`
   y `rev`; es controlada. La búsqueda solo usa alias confirmados y
   activos. Un `CHECK` rechaza lo que tiene forma de IBAN y un disparador
   exige que la fila apuntada exista.
7. **La guarda es más estricta que la especificación**: además de rev + 1 y
   un `cambio_campo` de la fila, exige uno por cada columna que cambia, con
   el valor anterior y el nuevo exactos, y en el evento en curso (el
   último); y hay una guarda de alta (rev 0 y un `cambio_campo` por columna
   con valor). Sin eso, un cambio auditado de un campo podría llevar
   colado el de otro. Consecuencias: `campos` fija el id de cada fila nueva
   antes de escribirla (el máximo más uno, seguro dentro de `BEGIN
   IMMEDIATE`) y registra el evento antes de las filas; y una orden es **un
   solo evento** aunque cree una factura con sus líneas e imputaciones
   (§4: «the evento row»).
8. **Deshacer compara con el último valor automático**, no con el
   original. En el paso 2 son el mismo salvo después de una extracción
   nueva o de un recálculo; volver a un original que una fuente automática
   ya contradice es una corrección, no deshacer.
9. **El motivo se exige al cambiar cualquier valor que ya existe** (también
   una entrada manual sobre otra, deshacer y retirar una fila), no solo en
   `manual_correccion`. Rellenar un campo vacío sin original automático no
   lo pide, salvo los campos del ciclo de vida de la factura (`anulada`,
   `fusionada_en_id`, marcados `motivo_siempre`), que lo piden siempre. Es
   la lectura prudente de la pregunta 10 del §12, que sigue abierta.
10. **Suplir o corregir, para el permiso**: corrige quien cambia un valor
    que existe o un campo con original automático (también un literal
    ilegible: arreglar una mala lectura es corregir la extracción, y pide
    `editar_extraccion`). Imputar a un Objeto o a un recurso pide
    `cambiar_objeto`; una PO o la clase de una referencia, `cambiar_po`;
    anular o fusionar, `anular_acreditar`; los maestros, `admin`, salvo el
    teléfono de verificación, que pide `confirmar_iban`. Rellenar un campo
    vacío de una imputación (`facturable`, por ejemplo) es
    `anadir_informacion`, como en el resto de la factura; crearla o
    dividirla sigue siendo `editar_extraccion`. Nadie crea una factura a
    mano (llega por un documento o por una importación). El IBAN impreso
    (`iban_doc`) no lo edita nadie: es evidencia (ver las correcciones).
11. **Dueño Exact o TRNSPRNT**: una fila es de Exact o de TRNSPRNT cuando
    tiene su `exact_id`/`trnsprnt_id` o la factura tiene ese `origen`; sus
    campos marcados como `externo` no los edita una persona, y una fuente
    automática solo con `en_nombre_de` igual al dueño (su importación). La
    imputación a Objetos es local y no tiene dueño externo.
12. **`exigir` solo registra la denegación fuera de una transacción**: dentro
    de una, el `ROLLBACK` de la orden se la llevaría. `permisos.orden_auditada`
    (que usan `campos.orden` y las órdenes de usuarios) la registra después
    del `ROLLBACK` cuando es la transacción de fuera.
13. **La extracción vigente** sigue la regla de `load_records` (la más
    reciente), y una nueva se aplica como fuente automática: lo corregido se
    queda y su nuevo valor automático queda apuntado. Las líneas, las
    referencias y el desglose de IVA se casan por posición entre **todas**
    las filas que puso una extracción, también las que una persona editó o
    excluyó (una excluida recibe los valores nuevos y sigue excluida); no
    cuentan las que retiró una extracción anterior porque ya no venían. Las
    que ya no vienen se retiran salvo que una persona las editara (se
    conservan, se dice en el resultado y en el evento). Una referencia de
    línea se ata a la línea con la que casó su índice. El paso 6 cambia esto
    por la puerta de activación y el casado por huella.
14. **`registros_resueltos` saca el literal de la extracción vigente**,
    guiado por la referencia de la procedencia (`extraccion:N` en la
    cabecera, `extraccion:N:lines[i]` en una línea), no de
    `valor_original_crudo`, que es el literal del original y se guarda para
    enseñarlo. Un valor corregido se escribe con `literal_decimal`, que con
    más de dos decimales pone los dos separadores (`0,042.125`) porque
    `parse_amount` lee «42.125» como millares. Un campo de
    `low_confidence_fields` verificado o corregido sale de la lista.
15. **Lo que v1 no dice lo decide el código y queda como `calculado`**: un
    total o una base negativos hacen de la factura un abono; `moneda_doc` es
    la moneda no euro detectada en los literales cuando X1 falla (con v2,
    `currency_raw`). Una factura que no está en euros deja todos sus
    importes y tarifas vacíos con su literal, sin marcarlos dudosos.
16. **`fecha_recepcion` solo con una recepción de verdad** (`correo` o
    `ingesta`): la fecha de modificación del fichero no lo es.
17. **La semana ISO de una línea sale de sus fechas**; con solo el número de
    semana impreso queda vacía, porque el año se deduce con la fecha de la
    factura al cruzar con el planning (paso 10).
18. **`parsing.normalizar_referencia` se adelanta del paso 6** (hace falta
    para `numero_norm`). No quita ceros a la izquierda: «2026-012» y
    «2026-12» pueden ser dos facturas.
19. **Una extracción v2 ya se tipa** (probado con un registro v2 sintético):
    receptor, contacto, condiciones de pago, tipo de documento, moneda,
    referencias (la clase la decide `campos.clasificar_referencia` con una
    lista de etiquetas) y desglose de IVA. Las relaciones que propone
    (`related_invoices`) no se crean: son del paso 8. Casar una referencia
    con una PO es del paso 9.
20. **La semilla** apunta el fichero en `politica_version` y crea los
    clientes (con su alias de configuración), los Objetos (código = nombre
    tal como está en el fichero) y las tarifas de venta (`unidad` hora,
    `fuente` config), y vuelve a resolver las imputaciones. No siembra
    `margen_por_defecto` ni `no_facturable`, y lo que se quita del fichero
    no se borra. `facturacion.py` sigue leyendo el fichero: la proyección
    contra las tarifas del almacén va con las tarifas pactadas (paso 9).
21. **También leen del almacén `simulador` y `/api/datos`**, no solo
    `panel`, `report` y `export`: si no, el sitio propio y el panel
    enseñarían cosas distintas. `/api/datos` sigue dando la foto de
    referencia sin correcciones (probado). `score` y `coste` siguen en
    `out/`: miden extracciones, no facturas. En `panel`, `report`, `export`
    y `simulador`, un `--out` explícito sin `--db` lee esa carpeta tal cual
    (y lo dice); con `--db`, manda el almacén y se avisa de que `--out` no
    se usa; sin ninguno, el almacén por defecto o, si no existe, `out/`.
22. **La CLI local actúa como el operador del fichero** (`por=None`, actor
    `sistema`) al crear personas y roles: quien la ejecuta ya tiene la base.
    Los tokens de las personas llegan con el servidor (paso 4).
23. **`factura_id` en `evento` y `cambio_campo` sigue sin comprobarse**: el
    disparador que sugería el paso 1 no es posible, porque el evento de
    alta va antes que sus filas.
24. **Lo pendiente del panel que el paso 0 dejaba para los pasos 2 y 3**
    (la guarda muerta `nom:(sin`, `por_proveedor` y la matriz por nombre
    impreso, `_propagar_alertas_a_filas` por nombre de fichero, B4 por
    Objeto, la regla «D» y unificar la identidad de B2, B3, B4 y G3) **va al
    paso 3**: cambia lo que sale del panel, y este paso tiene que dejar la
    foto igual. La identidad de las reglas nuevas es `identidad.py`.
25. **Tests existentes cambiados**, porque contaban una sola migración o un
    número fijo de eventos (el comportamiento no cambia): en
    `test_auditoria.py`, los ids de evento van detrás de `MIGRACIONES`; en
    `test_almacen.py`, las pruebas de migraciones cuentan las disponibles,
    la de transacciones anidadas no mira los eventos de migración,
    `SOLO_ESCRITURA` incluye `nota` y la lista de tablas que no se borran
    pero sí se editan incluye las controladas y `procedencia_campo`; en
    `test_migracion_out.py`, el evento anclado se lee de la base, porque
    `importar-out` ahora también tipa.

### Lo que deben saber los pasos siguientes

- **Escribir**: una tabla controlada solo se escribe con
  `with campos.orden(conn, origen, tipo=…) as o:` (`o.crear`, `o.fijar`,
  `o.retirar`, `o.recalcular`, `o.verificar`) o los atajos. `origen` es
  `Automatico(fuente, actor, ref=…, usuario_id=…, en_nombre_de=…)` o
  `Persona(usuario_id, motivo, peticion_id)`. Un valor automático con su
  literal va como `Leido(valor, crudo=…, dudoso=…, ref=…, fuente=…)`. El
  dinero entra como `Decimal` y lo escala `a_columna` con
  `almacen/unidades.py`. Ningún otro módulo puede tener un `INSERT`,
  `UPDATE` o `DELETE` sobre esas tablas (lo comprueba un test).
- **Una tabla controlada nueva** (paso 7: `aplicacion_pago`, `conciliacion`)
  necesita su entrada en `campos.REGISTRO` (con el mismo orden de columnas,
  un test lo compara) y sus guardas generadas con
  `python scripts/generar_guardas.py <tabla>`. Una columna nueva en una
  controlada obliga a borrar y volver a crear sus dos guardas en esa
  migración.
- **Leer**: `campos.procedencia(conn, tabla, id)` y `campos.estado_campo(p)`.
  M1 es `estado_campo(p).sin_resolver`; Q2, `estado_campo(p).dudoso` en un
  campo de `campos.criticos(tabla)`; Q1, `campos.obligatorios(tabla,
  sentido)`, y un campo que v1 no pidió se distingue con
  `compat.no_solicitados(schema_version)` (la versión es la de
  `factura.extraccion_vigente_id`): esas reglas dan `sin_datos`. Las marcas
  de edición por factura, en `v_factura_ediciones`.
- **Las reglas viejas** corren sobre `legado.registros_resueltos(conn)`, que
  sin correcciones es byte a byte lo de siempre. El paso 3 las porta a
  `reglas/` sobre el almacén tipado; mientras tanto, cualquier cambio de
  campo se ve en el panel.
- **Identidad**: `identidad.resolver_parte` y `resolver_objeto`. Quien
  cambie un maestro (paso 5) llama a `ingesta.reconciliar_referencias` para
  que las facturas y las imputaciones sin resolver se resuelvan; un valor
  puesto a mano no se pisa. Nada crea un proveedor desde un documento.
- **Ingesta**: un importador nuevo de facturas o de documentos termina con
  `ingesta.tipar_pendientes(conn)` (o `tipar_documento`). La vía de entrada
  (`ruta_declarada`) decide el sentido; `extract` y `serve` ponen hoy
  `entrante`, y la vía de salida (paso 8) solo tiene que pasar
  `ruta="saliente"`.
- **Permisos**: una orden de persona pasa por `permisos.exigir` (lo hace
  `campos`); `servicios.py` (paso 4) envuelve sus órdenes en
  `campos.orden`/`permisos.orden_auditada` para que la denegación quede.
  La separación de funciones es `permisos.separacion(conn, permiso, autor,
  revisor)`; una negativa es `SeparacionDeFunciones`, que es un
  `PermisoDenegado` y queda en la auditoría igual. Los predicados SOD1–SOD5
  se escriben encima de ella en el paso que trae cada orden (ver las
  correcciones).
- **Procedencia**: cada orden pone en su evento la foto de cada
  procedencia que escribe (`datos.procedencia."tabla:fila:campo"`, todas
  las columnas). La guarda de `procedencia_campo` exige que la fila sea
  esa foto, y `campos.verificar_procedencia` (dentro de
  `verificar_controladas`) compara cada fila con su última foto. Quien
  escriba una procedencia fuera de `campos.orden` no puede: no hay atajo.
- **Fixtures** (`tests/conftest.py`): `tipado` (las siete fixtures v1
  importadas y tipadas), `persona(conn, nombre, *roles)` y
  `factura_de(conn, numero)`.
- **Lo que no se hizo y es de otro paso**: las relaciones propuestas por la
  extracción (8), la proyección de venta contra el almacén (9), el año de
  la semana impresa (10), el desglose de IVA de una factura v1 (11) y lo
  del panel de la desviación 24 (3).

### Correcciones de la revisión

La revisión del paso 2 dejó veinte hallazgos; varios eran el mismo visto
desde dos sitios (M1 tras verificar, la separación de funciones sin
auditar, la normalización de btw-id y KvK). Cada uno se reprodujo antes de
tocarlo, con un test que falla con el commit del paso 2 y pasa ahora: 21
funciones de test nuevas (45 casos), de las que 20 casos fallan con el
commit anterior; los de `semana_iso` y `normalizar_referencia` ya pasaban,
porque lo que faltaba era el test.
Todos eran reales salvo una parte de uno (la línea conservada sin casar,
abajo), que se deja para el paso 6 y se dice por qué.

| Hallazgo | Qué se hizo | Test |
| --- | --- | --- |
| Una línea excluida volvía como activa tras otra extracción, y las de detrás se corrían un puesto | El casado por posición cuenta todas las líneas que puso una extracción, también las excluidas por una persona; una excluida casada recibe los valores nuevos y sigue excluida. `_crear_lineas` y el casado devuelven índice → línea, y las referencias de línea se atan con eso, no con `orden - 1` | `test_ingesta.py::test_una_linea_excluida_sigue_excluida_tras_otra_extraccion`, `test_una_referencia_de_linea_va_a_la_linea_con_la_que_caso` |
| Una referencia o un IVA editados salían del casado, y los valores nuevos caían en la fila de al lado y duplicaban otra | `_actualizar_hijas` casa como las líneas (todas las filas de extracción, editadas o no); una editada que ya no viene se conserva y va en `filas_con_edicion_manual_sin_casar` del evento | `test_una_referencia_y_un_iva_editados_no_corren_a_los_demas` |
| Un valor manual verificado no volvía a M1 cuando una extracción nueva lo contradecía (aparecía dos veces) | En la rama «lo manual gana», un automático nuevo distinto del anterior y del valor manual anula la verificación (`verificado_*` a NULL); `estado_campo` y `v_factura_ediciones` vuelven a dar sin resolver. La misma lectura otra vez no la anula | `test_campos.py::test_una_extraccion_que_contradice_lo_verificado_vuelve_a_m1` |
| Excluir una línea dejaba su imputación activa | `Orden.retirar` retira también las hijas activas de `PADRES`, en la misma orden y con el mismo motivo; la ingesta ya no lo hace aparte | `test_retirar_una_linea_retira_su_imputacion` |
| Corregir `factura.iban_doc` quitaba la parada F3 | `iban_doc` no es editable: es lo que dice el papel; se verifica o se rechaza el IBAN (paso 5), no se corrige. Verificar la lectura sigue siendo posible. `registros_resueltos` saca `iban` siempre del literal de la extracción vigente (`legado.IMPRESO`) | `test_el_iban_del_documento_no_se_corrige_y_f3_lo_sigue_viendo` |
| Fusionar no pedía motivo, admitía ciclos y facturas de otro proveedor, y la fusionada desaparecía de todos los lectores | `anulada` y `fusionada_en_id` piden motivo siempre (`motivo_siempre`). `campos` (`FusionNoValida`) y dos disparadores nuevos de la 0002 (`factura_fusion_valida`, alta y cambio) exigen el mismo sentido, la misma parte resuelta en las dos, que el destino no esté fusionado y que en la fusionada no haya otras. `registros_resueltos` ya no quita las fusionadas: las reglas de hoy no saben de fusiones, y quitarla escondía sus avisos; sacarla de los totales y no de los avisos es del paso 3 | `test_fusionar_exige_motivo_misma_parte_y_sin_cadenas` |
| Crear una fila se saltaba el permiso de cada campo, lo no editable y el dueño | `Orden._alta_de_persona`: un campo con permiso propio (`Campo.propio`: la PO, el Objeto, el teléfono de verificación…) lo pide también al crear; un campo no editable no se da salvo la estructura (`ESTRUCTURA`: a qué factura, línea o fila pertenece); la atribución (`ATRIBUCION`: `alias.origen`, `tarifa_acordada.fuente`, `factura_relacion.fuente`) es siempre `manual`; y una persona no crea ni retira hijas de una factura de Exact o TRNSPRNT (`HIJAS_DEL_DUENO`), ni retira una fila de otro sistema | `test_crear_una_fila_pide_lo_mismo_que_fijarla`, `test_las_lineas_de_una_factura_de_exact_no_se_tocan_aqui` |
| `db verificar` no comprobaba el original, el valor automático ni la verificación de la procedencia, y la guarda dejaba cambiar cualquier columna si el último evento nombraba el campo | Cada orden pone en su evento la foto de cada procedencia que escribe (`datos.procedencia`, sustituye a `datos.campos`). Las guardas de `procedencia_campo` exigen que la fila sea exactamente esa foto. `campos.verificar_procedencia` compara cada fila con su última foto, que el original no cambie entre fotos, que una verificación nueva salga en un evento de la persona que verificó, y ve las metidas y las borradas | `test_db_verificar_ve_una_procedencia_reescrita_por_detras`, `test_la_guarda_de_procedencia_exige_la_foto_del_evento` |
| Una negativa por separación de funciones no quedaba en la auditoría (aparecía dos veces) | `SeparacionDeFunciones` es un `PermisoDenegado` (con permiso y acción), así que `orden_auditada` la registra como cualquier denegación | `test_una_separacion_de_funciones_denegada_queda_en_la_auditoria` |
| Rellenar un campo vacío de una imputación pedía `editar_extraccion` | `factura_imputacion` suple con `anadir_informacion` (§6); corregir, crear y dividir siguen en `editar_extraccion` | `test_rellenar_una_imputacion_es_anadir_informacion` |
| `nota` y `politica_version` no se comprobaban contra su auditoría | Las dos están en `evidencia.COLUMNAS`/`EVENTOS`. La nota lleva su foto en `nota_anadida` (escrita antes de la fila, porque la fila va después de su evento; se enlaza por `nota.evento_id`, `evidencia.POR_EVENTO`, para que el evento siga siendo de la fila anotada y salga en su historial). La política lleva su foto en `politica_cargada`, y su texto se rehashea contra `sha256` como el de una extracción | `test_db_verificar_ve_una_nota_o_una_politica_tocadas_por_detras` |
| btw-id y KvK se normalizaban distinto en el documento y en el maestro (aparecía dos veces) | `identidad._ids` normaliza los dos lados con `normalizar_btw`/`normalizar_kvk`, en Python: el maestro es pequeño y así no hay una cadena de `replace()` que se quede corta | `test_identidad.py::test_el_maestro_se_normaliza_como_el_documento` (tres formas) |
| `sembrar` fallaba con una tarifa numérica en el YAML | El literal se guarda como el texto que leyó `parse_amount` (`str(...)`) | `test_una_tarifa_numerica_en_el_yaml_se_siembra` |
| `panel`, `report`, `export` y `simulador` ignoraban un `--out` explícito si había almacén | `--out` ya no tiene valor por defecto en esas órdenes: explícito y sin `--db`, se lee esa carpeta y se dice; con `--db`, el almacén, y se avisa. `serve` no cambia: su `--out` es donde escribe las extracciones, que también entran en el almacén, así que `/api/datos` del almacén enseña lo mismo | `test_equivalencia_legado.py::test_un_out_pedido_se_lee_aunque_haya_almacen` |
| `importar-out` ya no era una transacción | Importar y tipar van en una sola transacción de la orden; cada fichero y cada documento, en su SAVEPOINT (un documento que falla queda como error y no se lleva a los demás) | `test_importar_out_es_una_sola_transaccion` |
| `semana_iso` y `normalizar_referencia` sin tests | Tests de los bordes de año ISO (2027-01-01 es 2026-W53, 2024-12-30 es 2025-W01), ceros a la izquierda, espacio duro y fino, mayúsculas, vacío y solo separadores | `test_reloj.py`, `test_parsing.py::test_normalizar_referencia` |
| SOD1–SOD5 no existen como predicados | No se escriben aún, y es a propósito: la especificación los nombra (§3.13, §6) pero no los define, y en el paso 2 la única revisión que existe es verificar un campo, que ya pasa por `separacion()`. Cada separación llega con la orden que separa, escrita encima de `separacion()`: anular un aviso con segundo firmante (pasos 3 y 4), revisar una factura (paso 4), verificar o atestar un IBAN y el teléfono de verificación (paso 5), confirmar un pago (paso 7) y el estado del BTW (paso 11) | — |

Lo que no se hizo, y por qué: **una línea que una persona editó y que la
extracción nueva ya no trae no queda «sin resolver»**. Se conserva (no se
pierde lo que escribió nadie) y se dice en el resultado y en el evento
(`lineas_con_edicion_manual_sin_casar`), pero M1 compara un valor manual con
un valor automático, y aquí el automático es «esta línea no existe»: no hay
un valor que apuntar sin pisar los campos automáticos de la línea (que
cambiarían los totales). Lo resuelve el paso 6, con la puerta de activación
y el casado por huella, que decide qué línea es cuál.

**La migración 0002 se corrige en su sitio** (las guardas de
`procedencia_campo` y los dos disparadores de fusión), contra la regla de
que un fichero aplicado no se edita: el commit del paso 2 no ha salido de
esta rama y ninguna base la tiene aplicada fuera de los tests. Una base
local creada con la versión anterior la rechaza `migrar` por el hash; se
rehace con `bms-agent importar-out`, que no gasta API.

**Tests existentes cambiados**: `test_verificar_vale_para_la_version_que_se_verifico`
verificaba y corregía `iban_doc`, que ya no se corrige a mano; ahora lo hace
con `emisor_kvk_doc` (lo que prueba no cambia).


## Paso 3

Motor de reglas y hallazgos. **725 tests pasan** (491 funciones de test;
eran 582 y 406 al terminar el paso 2, y 713 y 480 antes de la revisión),
ninguno llama a la API y ninguno escribe fuera de una carpeta temporal.
Cinco mil facturas se recalculan en 1,0-1,3 s la primera vez y en 0,9-1,3 s
las siguientes, repartidas entre 400 proveedores o casi todas de uno solo
(ocho medidas de cada caso en este contenedor, cuatro núcleos, en memoria;
antes de la revisión eran 1,2-2,1 s y la puerta fallaba una vez de cada
cuatro).

### Qué se construyó

**Módulos nuevos**

| Módulo | Qué hace |
| --- | --- |
| `reglas/base.py` | `Regla` (metadato del §7: severidad B/R/A y la de venta si cambia, anulable y anulable en venta, pegajosa, segunda firma, entrada de prioridad, calidad, ámbito, versión, `lee` y `solo_texto`), `Resultado` (ok, fallo, sin_datos, no_aplica, con valores comparados, clave, grupo, severidad y objetivos), `Comprobacion`, `Objetivo`, `Politica` (tolerancias de validacion-facturas.md §4), la instantánea congelada (`Instantanea`, `Factura`, `Linea`, `TramoIva`, `Relacion`), `por_factura` y las escalas (`euros`, `tarifa`, `cantidad`, `porcentaje`, `euros_texto`, `periodo_de`) |
| `reglas/catalogo.py` | `CATALOGO`: las 14 reglas que se evalúan, en el orden del §7, con su metadato. `NO_ANULABLES` y `nunca_anulable()` (la lista de la decisión 12) y `sha256()` del catálogo |
| `reglas/motor.py` | `evaluar()` (puro: cada regla sobre la instantánea, resultados ordenados por regla, tabla, fila, grupo y clave; dos resultados con la misma clave son un error de la regla), `agrupar()` (los fallos que son el mismo hallazgo, su objetivo principal y su severidad), `huella()`, `campos_de_fuente()` y `canonico()` (JSON canónico que rechaza floats) |
| `reglas/instantanea.py` | El único de `reglas/` que lee la base: facturas tipadas con sus valores actuales, líneas e imputaciones activas, desglose de IVA, relaciones confirmadas y qué campos tienen un literal ilegible. Deriva la contraparte como clave (`clave_parte`: fila del maestro, btw-id, KvK o nombre normalizados con identidad.py; nunca el IBAN), la moneda que no es el euro y el Objeto de cada línea |
| `reglas/calidad.py` | Q1 y X1, y sus comprobaciones de fondo `campos_que_faltan` y `moneda` |
| `reglas/aritmetica.py` | D1, D2, D2b y D4 (`suma_lineas`, `aritmetica_lineas`, `total`) |
| `reglas/iva.py` | D3, E3 y E4 (`cuota_por_tipo`, `iva_indebido`, `sin_iva_por_regimen`) |
| `reglas/bancaria.py` | F1 (`validar_iban`, `iban`) |
| `reglas/unicidad.py` | B2, B3 y B4 sobre `Candidata` (`numeros_repetidos`, `importes_repetidos`, `periodos_solapados`, `periodos_compatibles`) |
| `reglas/planning.py` | G3 de histórico (`cambios_de_tarifa`, `tipo_de_trabajo`) |
| `hallazgos.py` | `recalcular()` (la pasada: instantánea, evaluación, caché, hallazgos y su historia, en una transacción; `simular=True` lo deshace y devuelve lo que habría cambiado), `calcular()` (hallazgos con su huella), `anular()`, `resolver()`, `requiere_segunda_firma()`, `historia()`, `pendientes()` y `verificar()`. Devuelve una `Diferencia` (evaluaciones por resultado, transiciones con su causa, retenidos por sin_datos y pendientes por estado) |

**Cambios**

- `checks.py` ya no calcula nada: cada `check_*` lee los literales con
  parsing.py y llama a la comprobación de fondo de `reglas/`, con las mismas
  etiquetas, estados ("sin datos", "no aplica") y textos del contrato v1.
  `validar_iban` es la de `reglas/bancaria.py`; `POLITICA_V1` son las
  tolerancias de siempre.
- `dashboard.py`: `detectar_duplicados`, `detectar_periodos_repetidos` y
  `detectar_cambios_de_tarifa` construyen candidatas y observaciones desde
  las filas del panel y llaman a `reglas/unicidad.py` y
  `reglas/planning.py`. Las alertas llevan `indices` (la posición de cada
  registro, fuera del contrato) y `_propagar_alertas_a_filas` une por ahí;
  `Fila.indice` es la posición del registro.
- `facturacion.py` usa `reglas.planning.tipo_de_trabajo` (era una copia).
- `ingesta.ingestar_pasada` (extract y el botón del servidor): tipar y
  recalcular en una transacción; `ResultadoIngesta.recalculo`.
- `importadores/tarifas.sembrar_tarifas` termina con `recalcular` en su
  transacción; `ResultadoSemilla.recalculo`.
- `cli.py`: `importar-out` e `ingestar` recalculan dentro de su transacción
  (ingestar ahora es una transacción con un SAVEPOINT por documento, como
  importar-out); `extract` y `sembrar` dicen lo que dejó la pasada; nueva
  orden `recalcular [--simular] [--diaria]`; `db verificar` comprueba también
  los hallazgos.
- `dominio.py`: `EstadoHallazgo`, `ESTADOS_PENDIENTES`, `TipoEventoHallazgo`,
  `MotivoEjecucion`, `PapelObjetivo`, `AmbitoHallazgo`, `EntradaPrioridad`.
- `almacen/evidencia.py`: `anulacion` es evidencia (su foto va en el evento
  `hallazgo_anulado`, enlazado por `anulacion.evento_id`, como una nota).

**Tablas** (migración `0003_reglas_hallazgos.sql`), todas STRICT, con clave
entera y sin ninguna columna REAL:

| Tabla | Clase | Qué no se puede hacer |
| --- | --- | --- |
| `ejecucion_reglas` | Una por pasada | Borrarla; tocarla salvo cerrarla una vez (como `importacion`); actuar con un usuario que no sea de sistema; poner en `usuario_id` uno de sistema |
| `evaluacion` | CACHE | — (se reescribe en cada pasada lo que cambia) |
| `hallazgo` | Estado con historia | Borrarlo; nacer con un estado que no sea `abierto`; cambiar su clave, su regla o su primera vez; cambiar su estado o su huella sin que su último `hallazgo_evento` diga ese estado y esa huella; cambiar `pegajosa` o `anulable` sin cambiar `regla_version`, o la severidad sin cambiar la huella |
| `hallazgo_objetivo` | CACHE | — (se rehace cuando cambian los objetivos de un hallazgo) |
| `hallazgo_evento` | SOLO ESCRITURA | `UPDATE` y `DELETE`; una transición que no sale del estado anterior (en particular `cerrado_automatico` de una regla pegajosa); un `reabierto` que no deje el hallazgo `abierto`; un `aceptado` sin la última anulación del hallazgo, con la misma huella, sin vencer, de un hallazgo anulable y con quien la firmó (y quien dio la segunda firma) con `anular_aviso` en ese momento; un `resuelto` sin un evento de esa persona; un evento de persona firmado por un usuario de sistema |
| `anulacion` | SOLO ESCRITURA | `UPDATE` y `DELETE`; anular una regla de la lista dura (familia F, X1, E3, E4, K2, K4, K6, R2, R3 y D2/D3/D4/D6 en compras) o un hallazgo marcado no anulable; anular una huella que no es la actual o un hallazgo que no está abierto ni aceptado; firmarla sin `anular_aviso` en ese momento (y la segunda firma igual); colgarla de un evento que no es el último o que no es de quien firma; una segunda firma sin el evento `hallazgo_segunda_firma` de esa persona justo antes; un motivo de menos de 10 caracteres |

**El catálogo** (§7, solo lo que se evalúa en este paso):

| Regla | Compra / venta | Anulable | Pegajosa | Prioridad |
| --- | --- | --- | --- | --- |
| Q1 Campos obligatorios | R (B si falta número, total o contraparte) | no | no | otra |
| X1 Moneda | B | no | sí | otra |
| B2 Número repetido | B | con segunda firma | sí | duplicado exacto |
| B3 Duplicado por contenido | R | sí | sí | duplicado |
| B4 Periodo facturado dos veces | R | sí | sí | duplicado |
| D1 Desglose | B / R | no | no | otra |
| D2 Suma de líneas | B / R | no | no | otra |
| D2b Aritmética de línea | B / R | sí | no | otra |
| D3 Cuota de IVA | B | no | no | IVA duro |
| D4 Total | B | no | no | otra |
| E3 IVA con KOR | B | no | no | IVA duro |
| E4 IVA trasladado | B | no | no | IVA duro |
| F1 IBAN | B | no | sí | IBAN |
| G3 Tarifa distinta (histórico) | R | sí | no | planning |

**Cómo decide `hallazgos.recalcular`**

- La **clave** de un hallazgo es regla + objetivo + llave
  (`D4|factura:12`, `E4|factura:12|cuota`, `Q1|factura:12|contraparte`,
  `B2|grupo:3` (la primera factura del grupo), `B3|par:3-7`, `G3|linea:41`
  (la primera línea del grupo)), y no cambia cuando la contraparte o el
  Objeto se resuelven contra el maestro. La **huella**
  es el sha256 de la versión de la regla, los valores comparados, la fuente
  de cada campo que la regla lee (sus columnas en `procedencia_campo`, de las
  facturas y líneas del hallazgo; la contraparte, de lo que imprime el
  documento) y los parámetros de la política que usa.
- Cada transición queda en `hallazgo_evento` con su **causa**: el último
  evento de auditoría que tocó alguna de sus facturas desde la pasada
  anterior (`cambio_campo.factura_id`, por encima de
  `ejecucion_reglas.hasta_evento_id` de la pasada previa); si ninguna se
  tocó, la que da quien lanza la pasada (`causa_evento_id`), o ninguna.
- Un hallazgo nuevo es `detectado`; si su huella cambia, `cambio_evidencia`.
  Si su condición desaparece: `cerrado_automatico` (estado `cerrado`) en
  una regla normal, `desaparecido` en una pegajosa, que sigue pendiente
  hasta que una persona con `resolver_aviso` lo cierra (`resolver`, estado
  `resuelto`). Si vuelve a darse uno cerrado, resuelto o desaparecido,
  `reabierto`, que lo deja `abierto`. Si es pegajosa lo dice el catálogo,
  no la fila.
- **sin_datos no cierra nada**: si la regla no pudo mirar la fila (su
  resultado, o el de una de sus facturas, es sin_datos), el hallazgo se
  queda como estaba y se dice en `Diferencia.retenidos`.
- Una **anulación** (`anular`, permiso `anular_aviso`, motivo de 10
  caracteres o más) acepta la huella de ahora; el hallazgo pasa a `aceptado`
  mientras su huella sea esa y no venza `vigente_hasta` (incluido ese día).
  Solo vale la **última** que se firmó para el hallazgo: anular otra vez es
  como se cambia el plazo. Si la evidencia cambia o vence, `reabierto`; si
  vuelve exactamente la evidencia anulada, vuelve a valer con un evento
  `aceptado` nuevo atribuido a quien la firmó (con su evento de auditoría
  como causa), y solo si esa persona, y quien dio la segunda firma, siguen
  pudiendo anular; si no, el hallazgo queda abierto.
- **Segunda firma**: la piden B2, cualquier hallazgo que bloquea (según la
  fila o según el catálogo, lo más grave) y los que cubren una factura de
  10.000 € o más de base, la principal o una relacionada (decisión 12),
  solo si hay otra persona con `anular_aviso`; sin ella, la anulación entra
  como `autoaprobada`. La segunda persona firma con su propia orden
  (`segunda_firma=Persona(...)`): un evento `hallazgo_segunda_firma` suyo,
  justo antes del de la anulación.

### La puerta, test por test

| Puerta | Tests |
| --- | --- |
| El test de pureza por AST pasa | `test_pureza_reglas.py::test_ninguna_regla_toca_la_base_el_reloj_el_entorno_ni_la_red` (cada módulo de `reglas/` salvo `instantanea.py`: solo importa la biblioteca estándar pura, `dominio` y otras reglas; no llama a `open`, `print`, `datetime.now`, `date.today`, `os.environ`, `execute`…), `test_la_busqueda_de_impurezas_ve_lo_que_tiene_que_ver` (18 fuentes impuras, todas cazadas) y `test_solo_instantanea_lee_la_base` |
| El test del proxy que graba lo que se lee pasa | `test_cada_regla_lee_solo_lo_que_declara_y_todo_lo_que_declara` (cada regla, sobre instantáneas envueltas en un proxy que apunta cada atributo: lo leído está en `Regla.lee`, y entre todos los casos sale todo lo declarado), `test_el_proxy_da_lo_mismo_que_la_instantanea`, `test_una_regla_que_lee_de_mas_se_ve` |
| Barajar la entrada da las mismas huellas | `test_hallazgos.py::test_barajar_la_entrada_da_las_mismas_huellas` (el almacén con B2, B4 y D4; facturas y líneas barajadas cinco veces: las mismas claves y huellas, que son las guardadas) y `test_reglas.py::test_barajar_la_entrada_no_cambia_nada` (resultados y hallazgos idénticos) |
| Recalcular dos veces no crea duplicados | `test_recalcular_dos_veces_no_crea_nada_dos_veces` (mismos hallazgos, eventos, objetivos y evaluaciones; ninguna transición; la caché no reescribe ni una fila) |
| Un pegajoso no se cierra solo | `test_un_hallazgo_pegajoso_no_se_cierra_solo` (B2 que desaparece al corregir el número: queda `desaparecido` pasada tras pasada, sigue en los pendientes de su factura, la base rechaza un `cerrado_automatico`, una persona lo resuelve y se reabre si vuelve la condición) |
| Una anulación deja de valer cuando cambia la huella | `test_una_anulacion_vale_mientras_la_huella_sea_la_anulada` (aceptado, se reabre al cambiar el periodo y vuelve a valer si vuelve la evidencia anulada), `test_una_anulacion_vence`, `test_la_huella_cambia_con_los_valores_las_fuentes_la_politica_y_la_version` |
| Los tests de antes siguen en verde a través de los envoltorios | Los 582 de antes pasan (los de `test_dashboard.py`, `test_parsing.py`, `test_report.py`, la foto de referencia byte a byte y las de equivalencia, sin tocarlos); `test_el_motor_y_el_contrato_v1_dicen_lo_mismo_de_cada_fixture` compara el motor con checks.py en las siete fixtures |
| 5.000 facturas se recalculan en menos de 2 s | `test_rendimiento.py::test_cinco_mil_facturas_se_recalculan_en_menos_de_dos_segundos` (la primera pasada, que crea unos 200 hallazgos, y la segunda, sin cambios; con las facturas repartidas entre 400 proveedores y con todas de uno solo, sin dos totales iguales) |

Además: el catálogo contra la tabla del §7 y la decisión 12
(`test_el_catalogo_es_el_del_paragrafo_7`,
`test_lo_que_no_se_anula_nunca_es_la_lista_de_la_decision_12`,
`test_las_familias_pegajosas_son_las_de_la_decision_11`), una tabla de
casos por regla en `test_reglas.py` (bordes de tolerancia de D2, D3 y D4,
B3 a 14 y 15 días, B4 por Objeto, abonos y relaciones, G3 por trabajo y
unidad…), la causa al cerrar D4 con una corrección, sin_datos que retiene,
`--simular` que no escribe nada, permiso y motivo de la anulación, la lista
dura también en la base, la segunda firma, `db verificar` que ve un
hallazgo o una anulación tocados por detrás, cada orden de entrada
(importar-out, ingestar, sembrar, extract, el servidor) que acaba con su
pasada, una orden que falla al recalcular y no deja nada, y la orden en un
proceso sin `anthropic`.

### Desviaciones de la especificación, y por qué

1. **Cinco estados en vez de cuatro**: `abierto`, `aceptado`,
   `desaparecido`, `cerrado` y `resuelto`. La especificación usa `resuelto`
   tanto para lo que cierra el sistema como para lo que cierra una persona;
   separarlos deja en la columna quién lo cerró sin leer la historia, y es
   lo que necesita el disparador para impedir que una regla pegajosa se
   cierre sola. Pendientes son `abierto`, `aceptado` y `desaparecido`
   (`dominio.ESTADOS_PENDIENTES`).
2. **`hallazgo_evento.estado`** (columna añadida: el estado que deja el
   evento) y la guarda de `hallazgo`: estado y huella solo cambian como diga
   el último evento. Es la misma idea que las guardas del paso 2: no hay
   cambio de estado sin su historia, y `hallazgos.verificar` (en `db
   verificar`) lo comprueba también sin disparadores.
3. **`ejecucion_reglas`** lleva además `actor` (el usuario de sistema
   `motor`; `usuario_id` es la persona que la lanzó, como en `evento`),
   `hasta_evento_id` (el último evento al empezar, para buscar causas) y
   `causa_evento_id`. Se inserta al empezar y se cierra una vez.
4. **`evaluacion`**: `clave` es la del hallazgo que daría (en una regla de
   grupo, la del grupo, en cada factura); `valores_json` solo en fallo y
   sin_datos (en un ok son los valores de la factura, que ya están en sus
   tablas, y escribirlos en cada pasada costaba más que todo lo demás); sin
   índice único (la unicidad la comprueba el motor antes de escribir:
   `ResultadoDuplicado`), con un índice por fila. Se escribe **solo lo que
   cambia**: una fila igual conserva su `ejecucion_id`, que pasa a ser "la
   pasada desde la que el resultado es este".
5. **`anulacion.evento_id`** (columna añadida) y la anulación es evidencia:
   su foto va en el evento `hallazgo_anulado` y `db verificar` compara cada
   fila con ella. La segunda firma se da en la misma orden (las dos personas
   delante), no hay un flujo de firma diferida: la tabla es de solo
   escritura.
6. **Q1, la contraparte es la que imprime el documento** (nombre, btw-id o
   KvK; en una venta, el receptor). Que el maestro la conozca es A0 (paso 5):
   sin maestros, todas las facturas de hoy bloquearían por "falta la
   contraparte". "Falta" es que no hay valor ni literal: un literal que no se
   pudo leer, o un importe en otra moneda, está en el papel (eso es Q2 o
   X1). Lo que la versión del esquema no pidió da sin_datos en un resultado
   aparte (`Q1|factura:N|contraparte`), como E4: en la clave de lo que sí
   se pidió, un sin_datos retenía el hallazgo para siempre. El periodo vale
   de la cabecera o de las líneas.
7. **Q1 del motor y "Campos obligatorios" del panel no son la misma
   lista**: checks.py conserva la versión reducida del contrato v1 (nombre,
   número, fecha y total, regla "A/B/C") porque la foto no puede cambiar; el
   motor pide la del §7.
8. **D1 no estaba en checks.py** (la tarea lo cita como portado): se
   escribió desde validacion-facturas.md. Pide líneas con cantidad, tarifa e
   importe, base, total y, si se repercute IVA, tipo y cuota; un literal
   ilegible cuenta como presente. Una línea a tanto alzado sin cantidad ni
   tarifa bloquea una compra, como dice el catálogo: si sale demasiado en
   las facturas reales, es una decisión del catálogo, no del código.
9. **D2, D3 y D4 no se anulan en ningún sentido** en el catálogo (§7 dice
   "no override" sin distinguir); la lista dura de la base es exactamente la
   de la decisión 12 (D2/D3/D4/D6 solo en compras), así que el paso 8 puede
   relajarlas en las ventas con el catálogo sin tocar la migración.
10. **E4 son dos resultados** (`cuota` y `btw_receptor`): una factura v1 no
    pidió el btw-id del receptor y eso no puede tapar que la cuota sí se
    comprobó. Que ese btw-id sea el de BM Support BV es A8 (paso 5, con
    `config/empresa.yaml`). **E3 y E4** deducen la cuota de total − base
    cuando la factura no la imprime.
11. **B2** agrupa por sentido, contraparte y número normalizado; dos
    facturas con una relación confirmada no son duplicado entre sí. Su
    clave es la primera factura del grupo (`B2|grupo:3`), no la contraparte
    y el número: la contraparte cambia de nombre al resolverse
    (decisión 10). El §7
    dice que se cierra fusionando o enlazando y que anularla pide segunda
    firma: las dos cosas valen (la fusionada queda no_aplica, el hallazgo
    pegajoso queda desaparecido y lo resuelve una persona).
12. **B3 tolera un céntimo** (el §7: "total within 0,01"), también en el
    panel v1, que antes pedía el mismo total exacto. No cambia la foto ni
    ningún test de antes; lo fija `test_b3_tolera_un_centimo_como_dice_el_catalogo`.
13. **B4 del motor** separa por Objeto cuando las dos facturas lo nombran,
    deja fuera los abonos (por su tipo) y los pares con relación confirmada.
    El panel v1 sigue con su B4 de siempre (sin Objetos, abonos por el signo
    del total): el §6 pide que el contrato v1 no cambie.
14. **G3 de histórico** agrupa por contraparte, Objeto (el resuelto o el
    nombre impreso normalizado), tipo de trabajo y **unidad** (una tarifa
    por hora y otra por pieza no se comparan), solo en compras, y solo
    retiene: el bloqueo por exceso es contra la tarifa pactada (paso 9). Su
    clave es la primera línea del grupo (`G3|linea:41`), y una factura sin
    fecha queda en sin_datos: no se sabe qué tarifa vino antes.
15. **Lo del panel que el paso 2 dejó para este** (desviación 24 del paso
    2): la guarda muerta `nom:(sin` queda corregida (una factura sin nombre,
    btw-id ni KvK no se agrupa con nadie, en el panel y en el motor);
    `_propagar_alertas_a_filas` une por la posición del registro y no por el
    nombre del fichero (también F3 y G3 llevan las posiciones); la identidad
    de B2, B3, B4 y G3 es una sola en el motor (`clave_parte`). Siguen como
    estaban, a propósito: la regla "D" de los fallos por factura en las
    alertas del panel y `por_proveedor` y la matriz por nombre impreso. Son el
    contrato v1 (`/api/datos` tiene que seguir siendo la foto, §6 y paso 12);
    el motor ya lleva el identificador de cada regla.
16. **La política está en el código** (`reglas.base.Politica`, con los
    valores de validacion-facturas.md §4); su hash va en
    `ejecucion_reglas.politica_sha256` y sus parámetros en cada huella. No
    hay todavía `config/reglas.yaml` ni `politica.py`: ningún paso los pide
    y ninguna tolerancia se ha cambiado. Quien los haga tiene que producir
    una `Politica`.
17. **El catálogo solo lista lo que se evalúa.** Las reglas del §7 que
    llegan después no tienen entrada todavía: una entrada sin evaluación
    daría por bueno lo que nadie miró. La lista dura de la base ya incluye
    F2-F10, K y R.
18. **Qué órdenes recalculan**: las que cambian algo que una regla lee
    (`importar-out`, `ingestar`, `extract`, el botón del servidor,
    `sembrar`), al final de su transacción. Las de usuarios y roles no: no
    cambian nada que lea una regla. Las ediciones de una persona
    (`campos.fijar`) no tienen todavía orden propia: `servicios.py` (paso 4)
    tiene que terminar cada una con `recalcular`.
19. **Anular y resolver son funciones** (`hallazgos.anular`,
    `hallazgos.resolver`), con sus tests, sin orden de la CLI: las órdenes de
    personas (con `peticion_id`, `rev` y la consola) son del paso 4.
20. **`solo_texto`**: lo que una regla lee solo para escribir su
    explicación (el nombre y el número impresos en B2, B3, B4 y G3, el nombre
    de la obra en G3) no entra en la huella; tampoco `anulada` ni
    `fusionada_en_id`, que dicen si la factura se evalúa. Sin eso, corregir
    el número de una factura cambiaba la evidencia de su B4 y quitaba una
    anulación que no tenía nada que ver.
21. **Rendimiento**: los resultados son tuplas con nombre (no dataclasses),
    las reglas de una factura devuelven listas, el recolector de ciclos de
    Python se para durante la pasada (`hallazgos._sin_recolector`: decenas de
    miles de tuplas sin ciclos que el recolector recorría una y otra vez) y
    la procedencia solo se lee para las filas con fallo.
22. **El test de rendimiento llena la base a mano**, con los disparadores
    de guarda quitados en esa base de prueba: crear cinco mil facturas por
    campos.py tardaría minutos, y lo que se mide es la pasada.
23. **Tests existentes cambiados**, porque hay tablas nuevas: en
    `test_almacen.py`, `SOLO_ESCRITURA` incluye `hallazgo_evento` y
    `anulacion`, `EVIDENCIA` incluye `ejecucion_reglas`, `_poblar` les pone
    una fila, y la lista de tablas que no se borran pero sí se editan
    incluye `hallazgo`. Ninguno cambia lo que prueba.
24. **Documentos tocados**: README (`recalcular` y el recuento), `fase-0.md`
    (la orden, los hallazgos y el recuento), `instalacion-windows.md` y
    `brief-diseno.md` (recuento; seguían en 537 desde antes de la revisión
    del paso 2) y `validacion-facturas.md` (qué reglas evalúa ya el motor).
25. **La migración 0003 solo trae las tablas 35-40 del §5.F.** `excepcion`,
    `excepcion_hallazgo`, `revision`, `prioridad_manual`, `factura_estado` y
    la caché `prioridad` (41-44) van en la migración del paso 4, que será
    la 0004; las que el §11 numera a partir de ahí corren un número (las
    cuentas bancarias del paso 5 serán la 0005, los extractos del paso 7 la
    0006, y así). El número de una migración es su orden, no su paso. Por
    qué: sus CHECK y disparadores (una excepción `asignada` con dueño, una
    `resuelta` con resolución, una revisión solo de una persona con
    `revisar_factura`, una prioridad manual que solo sube) son las reglas de
    `excepciones.py`, `revision.py` y `prioridad.py`, y `factura_estado`
    lleva columnas de pago (`estado_pago`, `pendiente_cent`, `dias_vencida`)
    que no tienen de dónde salir hasta el paso 7. Escribirlas sin el código
    que las usa sería esquema sin ningún test que lo recorra, por la misma
    razón por la que el catálogo solo lista lo que se evalúa (desviación 17).

### Lo que deben saber los pasos siguientes

- **Una regla nueva**: su función en el módulo de su familia (una regla de
  factura recibe `(factura, politica)` y devuelve una lista de `Resultado`,
  con `resultado_de`; una de grupo recibe la instantánea entera), su `LEE_*`
  con todo lo que lee y su `solo_texto`, y su entrada en `catalogo.CATALOGO`
  con el metadato del §7. Después: su fila en `CATALOGO_SPEC` de
  `test_reglas.py`, sus casos, y los escenarios de `test_pureza_reglas.py`
  tienen que pasar por todo lo que declara (el test falla si declara algo
  que nunca lee). Lo que necesite de la base (maestros, planning, pagos)
  entra en la instantánea por `reglas/instantanea.py`, no en la regla.
- **Cada orden** que cambie algo que lee una regla termina con
  `hallazgos.recalcular(conn, motivo=…, usuario_id=…, causa_evento_id=…)`
  dentro de su transacción. Devuelve la `Diferencia` que `servicios.py`
  (paso 4) tiene que enseñar (hallazgos que se abren, cierran o reabren).
  La causa se encuentra sola por `cambio_campo.factura_id`; pasarla sirve
  para lo que no toca facturas.
- **Excepciones y prioridad (paso 4)**: lo pendiente es
  `estado IN ESTADOS_PENDIENTES`; `aceptado` es "anulado y vigente" (no pone
  suelo de prioridad), `desaparecido` sí cuenta como atención. La entrada de
  prioridad, la severidad y si bloquea están en el catálogo y en
  `hallazgo.severidad`. El objetivo principal de un hallazgo de grupo es la
  factura más reciente (la de id mayor) y puede cambiar si cambia el grupo;
  todas sus facturas están en `hallazgo_objetivo`.
- **Lo que el paso 4 tiene que añadir a esto**: las órdenes de anular y
  resolver con `peticion_id` (y su segunda firma en la consola), que una
  corrección que cierra un hallazgo deje el campo sin resolver hasta que lo
  verifique otra persona (§7), y la excepción por entidad. La segunda firma
  es la `Persona` de la otra persona, con su propia petición: la consola
  tiene que autenticarla aparte (que esté delante, no que la primera
  escriba su id); hasta entonces `anular` no se expone por ninguna orden.
  Las tablas 41-44 del §5.F van en su migración, la 0004 (desviación 25).
- **Cambiar el metadato de una regla** (pegajosa, anulable, severidad)
  pide subir `Regla.version`: la base no deja cambiar `pegajosa` ni
  `anulable` de un hallazgo con la misma versión, ni su severidad con la
  misma huella, y la pasada fallaría. Con la versión cambia la huella, y
  las anulaciones de esa regla dejan de valer, a propósito.
- **Las claves no llevan nada que dependa de lo resuelto**: una regla de
  grupo nueva se identifica por sus filas (la primera factura o línea del
  grupo, o el par), no por `factura.parte` ni `linea.objeto`, y no pone en
  sus valores nada que cambie al resolverse contra el maestro.
- **Fusionar o enlazar (pasos 4 y 8)**: deja el B2 desaparecido; la orden
  que fusiona puede resolverlo en la misma transacción (quien fusiona es
  quien lo cierra), con `hallazgos.resolver`.
- **La huella cambia** si cambia una tolerancia que la regla usa, la
  versión de la regla o la fuente de un campo que lee: una anulación deja
  de valer entonces, a propósito. Subir `Regla.version` cuando cambie lo que
  una regla compara.
- **El paso 5** (F2-F10, A, E1, E2, Q2-Q4, Z) trae reglas pegajosas y no
  anulables: la base ya rechaza anular cualquier F. La E4 del btw-id de BMS
  se completa con A8.
- **Rendimiento**: unos 0,03-0,06 s por regla cada cinco mil facturas; la
  escritura de la caché es lo más caro de la primera pasada. Si una regla
  nueva cruza facturas, que ordene por fecha y corte la ventana antes de
  mirar nada más, como B3 y B4 (B3 no lo hacía hasta la revisión, y un
  proveedor con miles de facturas la volvía cuadrática). Un CHECK con
  `IN (...)` en una tabla de decenas de miles de filas cuesta: SQLite monta
  una tabla efímera en cada fila (la caché `evaluacion` usa una cadena de
  `OR`).

### Correcciones de la revisión

La revisión del paso 3 dejó dieciséis hallazgos; dos estaban repetidos (la
anulación anterior que sobrevive a la nueva, y las claves que cambian al
resolver la contraparte o el Objeto), así que son catorce. Cada uno se
reprodujo antes de tocarlo. Todos eran reales. Quedan 11 funciones de test
nuevas y 12 casos (uno es el caso de rendimiento con un solo proveedor), y
los 11 casos nuevos que prueban un defecto fallan con el commit del paso 3;
los dos que miden cobertura (la equivalencia en los fallos y el barajado de
relaciones y desglose) ya pasaban, porque lo que faltaba era el test.

| Hallazgo | Qué se hizo | Test |
| --- | --- | --- |
| Un Q1 de una venta v1 no se cerraba nunca al corregir lo que faltaba: con la fecha puesta daba sin_datos (v1 no pidió la contraparte) en la misma clave, y `_desaparecidos` lo retenía | Lo que la versión del esquema no pidió va en su propio resultado, `Q1|factura:N|contraparte` (sin_datos), como E4 separa `cuota` y `btw_receptor`; la clave de lo que sí se pidió da ok o fallo | `test_hallazgos.py::test_q1_de_una_venta_v1_se_cierra_al_corregir_lo_que_faltaba`, `test_reglas.py::test_q1_lo_que_v1_no_pidio_es_sin_datos_y_no_un_fallo` |
| Una anulación anterior sin plazo sobrevivía a la nueva con plazo, y el hallazgo quedaba aceptado para siempre (aparecía dos veces) | `_vigente` mira solo la última anulación del hallazgo: vale si es de esa huella y no ha vencido, sin volver a las anteriores. El disparador `hallazgo_evento_de_persona` exige lo mismo para cada evento `aceptado` | `test_acortar_el_plazo_de_una_anulacion_hace_que_venza` |
| B3 era cuadrático por contraparte: el `continue` del importe iba antes del corte de la ventana | `importes_repetidos` corta la ventana antes de mirar el número y el importe (la lista va por fecha: el resultado es el mismo). El test de rendimiento mide también cinco mil facturas de un solo proveedor, sin dos totales iguales: con el código anterior la primera pasada tardaba 3,8 s | `test_rendimiento.py::test_cinco_mil_facturas_se_recalculan_en_menos_de_dos_segundos[1]` |
| La clave de B2 y la de G3 llevaban la contraparte y el Objeto resueltos: dar de alta el proveedor o sembrar los Objetos cerraba el hallazgo, abría otro y perdía su anulación (aparecía dos veces) | B2 se identifica por la primera factura del grupo (`B2|grupo:3`) y G3 por la primera línea del grupo (`G3|linea:41`). Lo que depende de la resolución sale de la evidencia: `parte` de los valores de B2, los Objetos de los de B4 (deciden si el par cuenta, pero no son lo que se aceptó) y `proveedor_id`/`cliente_id` de las fuentes de la contraparte, que es la que imprime el documento | `test_resolver_los_maestros_no_abre_ni_cierra_ningun_hallazgo` (B2, B4 y G3 anulados; alta del proveedor, `reconciliar_referencias` y `sembrar`: ninguna transición, las tres siguen aceptadas) |
| G3 daba a una factura sin fecha `0000-00-00`, que la hacía la referencia y señalaba a las demás | Una factura de compra sin fecha da sin_datos en G3 y no entra en el histórico | `test_reglas.py::test_g3_una_factura_sin_fecha_no_es_la_referencia` |
| El test de equivalencia con el contrato v1 no comparaba ningún texto de fallo (solo había uno, X1) ni E3/E4, y los de barajado no reordenaban relaciones ni desglose | La comparación es `_comparar_con_v1`: resultado y texto de X1, D2, D2b, D4, F1, E3 y la cuota de E4, también en los fallos; un test nuevo la pasa por seis extracciones v1 hechas a mano, una por fallo. El texto de D2b se compara sin los ceros de más de la cantidad (el almacén guarda 37,50 horas como 37500 milésimas y el motor escribe 37.5; el v1, 37.50). Los dos tests de barajado reordenan también las relaciones y el desglose de cada factura, con relaciones confirmadas y un desglose de dos tipos en los datos | `test_el_motor_y_el_contrato_v1_dicen_lo_mismo_de_cada_fallo`, `test_barajar_la_entrada_no_cambia_nada`, `test_barajar_la_entrada_da_las_mismas_huellas` |
| La segunda firma solo miraba el importe de la factura principal: un B4 con una relacionada de 50.000 € lo anulaba una persona sola | `requiere_segunda_firma` mira el mayor importe de todas las facturas del hallazgo (`hallazgo_objetivo` más la principal) | `test_la_segunda_firma_mira_todas_las_facturas_del_hallazgo` |
| Un evento `reabierto` podía dejar en `aceptado` cualquier hallazgo, también un D4 que no se anula, sin anulación, y `verificar` no lo veía | `reabierto` deja siempre `abierto` (CHECK de `hallazgo_evento`); si la anulación vuelve a valer, va detrás su propio evento `aceptado`, que es de una persona y pasa por el disparador. Ese disparador exige además que el hallazgo sea anulable. `verificar` comprueba que todo evento que deja un hallazgo aceptado sea un `aceptado` de una persona, con una anulación de esa huella firmada antes y de una regla que se puede anular | `test_a_aceptado_solo_se_llega_con_una_anulacion`, `test_un_reabierto_deja_abierto_y_la_anulacion_vuelve_con_su_evento` |
| `pegajosa`, `anulable` y `severidad` se podían cambiar por detrás: quitar la marca pegajosa dejaba cerrarse solo un duplicado, y bajar un bloqueo se saltaba la segunda firma | Disparador `hallazgo_clasificacion`: `pegajosa` y `anulable` no cambian sin cambiar `regla_version`, ni la severidad sin cambiar la huella. `_desaparecidos` decide con el catálogo (o la fila, si es más pegajosa), y `requiere_segunda_firma` con la severidad de la fila o la del catálogo, la más grave. `verificar` compara pegajosa, anulable y severidad con el catálogo y, si la evidencia es la de hoy, la severidad con la que da el motor ahora (eso cubre Q1, que puede ser más grave que su catálogo) | `test_la_marca_pegajosa_y_la_severidad_no_se_tocan_por_detras` |
| Una anulación volvía a valer sola aunque quien la firmó ya no tuviera `anular_aviso`, y el evento nuevo se le atribuía | Solo vuelve si quien la firmó, y quien dio la segunda firma, pueden anular en ese momento; si no, el hallazgo queda abierto. El disparador exige lo mismo a cada evento `aceptado`. Una anulación que ya está aceptada no se reabre porque su firmante se vaya: lo que se le exige es al acto nuevo | `test_una_anulacion_no_vuelve_si_quien_la_firmo_ya_no_puede_anular` |
| La segunda firma era un id que escribía la primera persona | `anular(..., segunda_firma=Persona(...))`: la segunda persona tiene su propio evento de auditoría, `hallazgo_segunda_firma` (actor y usuario ella, con su `peticion_id`), justo antes del de la anulación y a la misma hora que `segunda_firma_en`; el disparador `anulacion_de_persona` no admite una segunda firma sin él. Que esa persona esté de verdad delante lo tiene que autenticar la consola del paso 4; hasta entonces `anular` no se expone por ninguna orden | `test_la_segunda_firma` (el evento de Bea), `test_la_segunda_firma_no_es_un_id_que_escribe_la_primera` |
| La migración 0003 no traía las tablas 41-44 del §5.F y el registro no lo decía | Desviación 25: van en la migración del paso 4 (la 0004) y las siguientes corren un número; el porqué está allí | — |
| La puerta de rendimiento pasaba con poco margen y fallaba una vez de cada cuatro (2,12 s) | Lo más caro de la primera pasada era escribir la caché, y dentro de eso el CHECK `resultado IN (...)` de `evaluacion`: SQLite 3.45 monta una tabla efímera para la lista en cada fila, y en setenta mil filas eran 0,22 s de 0,53. Es una cadena de `OR` y cuesta lo mismo que no tenerlo. Ahora la primera pasada tarda 1,0-1,3 s y la segunda 0,9-1,3 s, con 400 proveedores o con uno (ocho medidas de cada caso); el umbral sigue en 2 s | `test_rendimiento.py` (los dos casos; cuatro ejecuciones seguidas en verde) |

**La migración 0003 se corrige en su sitio** (el CHECK de `evaluacion`, el
de `reabierto`, el disparador `hallazgo_clasificacion` y los de
`hallazgo_evento_de_persona`, `hallazgo_evento_transicion` y
`anulacion_de_persona`), como la 0002 en la revisión del paso 2: el commit
del paso 3 no ha salido de esta rama y ninguna base la tiene aplicada fuera
de los tests. Una base local creada con la versión anterior la rechaza
`migrar` por el hash; se rehace con `bms-agent importar-out`, que no gasta
API. `hallazgo_evento_transicion` ya no exige que la regla sea pegajosa para
dejar un hallazgo `desaparecido`: el motor decide con el catálogo, dejarlo
desaparecido es pedir de más y no de menos, y una marca tocada por detrás no
puede tumbar la pasada entera. `cerrado_automatico` sigue exigiendo una
regla no pegajosa.

Lo que no se hizo, y por qué: **G3 del panel v1** (`dashboard.py`) sigue
dando a una factura sin fecha `0000-00-00`. Es el contrato v1, que el §6 pide
que no cambie, como el B4 del panel (desviación 13); el motor ya no lo hace.

**Tests existentes cambiados**: `test_b2_mismo_numero_de_la_misma_contraparte_es_un_hallazgo_de_grupo`
(la clave es `B2|grupo:1`), `test_q1_lo_que_v1_no_pidio_es_sin_datos_y_no_un_fallo`
(dos resultados, uno por clave), `test_la_segunda_firma` (la segunda firma
es una `Persona`), `test_lo_que_no_se_anula_no_se_anula` (quita y repone
también `hallazgo_clasificacion` para tocar la marca), `test_el_dominio_de_los_hallazgos_es_el_de_la_base`
(lee también la cadena de `OR` de `evaluacion.resultado`) y
`test_el_motor_y_el_contrato_v1_dicen_lo_mismo_de_cada_fixture` (usa
`_comparar_con_v1`). Ninguno prueba menos que antes.

## Paso 4

Excepciones, revisión, prioridad, órdenes y consola. **1011 tests pasan**
(608 funciones de test; eran 725 y 491 al terminar el paso 3), ninguno llama
a la API y ninguno escribe fuera de una carpeta temporal. La pasada del motor
hace ahora también excepciones, estado de cada factura y prioridad, y cinco
mil facturas se recalculan en 1,4-1,7 s la primera vez y en 1,1-1,35 s las
siguientes (cuatro medidas de cada caso en este contenedor; eran 1,0-1,3 s y
0,9-1,3 s). La puerta de 2 s sigue en pie, con menos margen: ver "Lo que
deben saber los pasos siguientes".

### Qué se construyó

**Módulos nuevos**

| Módulo | Qué hace |
| --- | --- |
| `prioridad.py` | El §8 como función pura: `calcular(entradas, hoy, pesos)` da nivel, puntos, suelo y motivos. Suelos en el código (`REGLAS_URGENTES`, `DIAS_IVA_URGENTE`, `DIAS_VENCIDA_URGENTE`); puntos con `Pesos` (los de `config/prioridad.yaml`, con su `sha256()`); `pesos_de_yaml` (rechaza un fichero que no tenga la forma entera); `Subida` (lo que sube una persona, con vigencia); `huella_entradas`; `clave_orden` y `ordenar`; `agregar` (proveedor, cliente, Objeto, trimestre: el máximo de sus hijas) y `de_excepcion` |
| `politica.py` | `registrar()` apunta un fichero de `config/` en `politica_version` con su texto, su sha256 y su evento; `vigente()`; `pesos_prioridad()` (los del último `prioridad.yaml` cargado, o los de `prioridad.Pesos`); `cargar_prioridad()` |
| `excepciones.py` | La excepción por entidad: `sincronizar()` (la abre el motor en cada pasada y le une los hallazgos nuevos), `crear`, `asignar`, `esperar` y `resolver` (órdenes de persona), `seguimiento_por_defecto`, `bloqueos_abiertos`, `abierta_de`, `hallazgos_de` y `verificar()` |
| `revision.py` | La huella del contenido (`contenidos`, `huella_contenido`), el estado de los campos de cada factura (`estado_de_campos`: marcas de edición, cambios sin resolver, dudosos sin verificar), el estado de revisión (`estado`), la etiqueta del sistema (`etiqueta_sistema`: "Sin objeciones del sistema", nunca "aprobada"), `lo_que_pide_revision`, `marcar_revisada` y `devolver` |
| `estados.py` | Las cachés `factura_estado` y `prioridad`, rehechas en cada pasada (solo lo que cambia); `vencimiento_efectivo`, `estado_pago`, `calidad`; `subir_prioridad()` (la orden de persona sobre `prioridad_manual`). Devuelve `Cambios`: prioridades que se movieron y revisiones que dejaron de valer |
| `servicios.py` | Las órdenes de persona: `ACCIONES` (23 `Accion` tipadas; 25 tras la revisión, con sus `Parametro`, su permiso y si piden motivo) y `ejecutar()`, la única puerta de la CLI, la consola y `POST /api/v2/acciones`. Devuelve una `Diferencia` (`a_dict()` y `lineas()`) |
| `consultas.py` | Lo que lee la consola, la CLI y `/api/v2`: `listado` (por prioridad, con insignias), `excepciones_abiertas`, `detalle` (campo a campo: valor, literal impreso, original, fuente, dudoso, verificado, sin resolver, calidad; líneas e imputaciones, referencias, hallazgos, excepción, revisiones, notas, historia), `personas`, `objetos` |
| `consola.py`, `consola_assets.py` | La consola mínima: una página sin datos, un script y una hoja de estilo, con su política de contenido. El script pinta todo con `createElement` y `textContent` |
| `config/prioridad.yaml` | Los pesos del §8, iguales a `prioridad.Pesos` (un test lo comprueba) |

**Órdenes** (`servicios.ACCIONES`; en la CLI, `bms-agent accion <orden>`):

| Orden | Permiso | Qué hace |
| --- | --- | --- |
| `fijar_campo` | `anadir_informacion` si el campo está vacío, `editar_extraccion` si se corrige (el del campo en `campos.py`) | Rellenar o corregir un campo de una factura, una línea, una imputación, un desglose o una referencia |
| `verificar_campo` | el de corregir el campo | Dar por bueno el valor actual (lo verifica otra persona si hay dos) |
| `revertir_campo` | el de corregir el campo | Volver al valor automático |
| `anadir_nota` | `anadir_informacion` | Nota interna en una factura o una excepción |
| `cambiar_objeto`, `anadir_alias` | `cambiar_objeto` | Imputar una línea a otro Objeto; un nombre impreso más para un Objeto o un recurso |
| `cambiar_po` | `cambiar_po` | La clase de una referencia impresa (PO, orden, proyecto…) |
| `anadir_referencia` | `cambiar_po` | Una referencia que la extracción no trajo (añadida en la revisión) |
| `excluir_linea`, `anadir_linea`, `dividir_linea` | `editar_extraccion` | Retirar una línea, añadir la que la extracción no trajo, repartir una línea entre Objetos (las partes suman la línea) |
| `corregir_maestro` | `admin` | Corregir un proveedor, cliente o contacto que no viene de Exact ni de TRNSPRNT |
| `anular_factura`, `fusionar_factura` | `anular_acreditar` | Anular (no emite abono); fusionar un reenvío en su factura (cierra su B2) |
| `marcar_revisada`, `devolver_factura` | `revisar_factura` | Revisar con la huella vista; devolver con una nota |
| `crear_excepcion`, `asignar_excepcion`, `esperar_externo`, `resolver_excepcion` | `resolver_aviso` | La vida de una excepción |
| `cerrar_hallazgo` | `resolver_aviso` | Cerrar uno cuya condición desapareció |
| `anular_hallazgo` | `anular_aviso` | Anular con la huella vista (y la segunda firma, si toca) |
| `firmar_anulacion` | `anular_aviso` | La segunda firma, como orden de la otra persona (añadida en la revisión; antes iba su token en la orden de la primera) |
| `subir_prioridad` | `resolver_aviso` | Subir a atención o urgente, con motivo y fecha de fin |
| `recalcular` | `ver_facturas` | Una pasada a petición |

`ejecutar()` hace siempre lo mismo y en este orden: comprueba los datos
(tipos, nada que no se espere, importes como texto y nunca como float),
mira la idempotencia (`peticion_id`), abre la transacción, exige una persona
activa (nunca un usuario de sistema) con el permiso, el motivo donde hace
falta y la `rev` que la persona vio, escribe por `campos.py` (o por el
módulo dueño de la tabla), recalcula todo con la causa de la orden y
devuelve la `Diferencia`: resultados de reglas que cambiaron, hallazgos que
se abrieron, cerraron o reabrieron, excepciones, revisiones que dejaron de
valer, prioridades que se movieron y los totales de las facturas tocadas
antes y después. Si algo falla no queda nada; una denegación de permiso sí
queda, como evento, después del ROLLBACK.

**Tablas** (migración `0004_excepciones_revision_prioridad.sql`), STRICT,
con clave entera y sin columnas REAL:

| Tabla | Clase | Qué no se puede hacer |
| --- | --- | --- |
| `excepcion` | Controlada (rev y la guarda generada, con `cambio_campo` por columna; la escribe `excepciones.py`) | Borrarla; nacer en otro estado que `abierta`; dos sin resolver para la misma entidad (índice único parcial); `asignada` sin responsable activo; `esperando_externo` sin a quién y sin fecha; `resuelta` sin resolución, notas, fecha y quién; tocar una resuelta o cambiar a qué apunta; que cambie el estado alguien que no sea una persona activa con `resolver_aviso` en el evento de la orden; resolverla con un hallazgo suyo que bloquea abierto y sin anular |
| `excepcion_hallazgo` | SOLO ESCRITURA | `UPDATE` y `DELETE`; unir un hallazgo a una excepción resuelta o fuera del último evento |
| `revision` | SOLO ESCRITURA | `UPDATE` y `DELETE`; que la escriba alguien sin `revisar_factura` en ese momento, un usuario de sistema o en un evento que no es el último ni suyo; `devuelta` sin nota; `autorrevisada` en una devuelta |
| `prioridad_manual` | SOLO ESCRITURA | `UPDATE` y `DELETE`; un nivel que no sea atención o urgente; un motivo de menos de 10 caracteres; que la escriba alguien sin `resolver_aviso`; un nivel por debajo del que ya tiene la entidad |
| `factura_estado` | CACHE | — (una fila por factura; se reescribe lo que cambia) |
| `prioridad` | CACHE | — (una fila por excepción sin resolver, proveedor, cliente, Objeto y trimestre) |

**Lectura y consola**

- `serve.py`: `/consola`, `/consola.js` y `/consola.css` con
  `Content-Security-Policy: default-src 'none'; script-src 'self'; …;
  frame-ancestors 'none'`; `GET /api/v2/yo|facturas|facturas/<id>|excepciones|personas|objetos|acciones`
  y `POST /api/v2/acciones`. Todo con el endurecimiento del paso 0 (solo
  127.0.0.1, Host y Origin comprobados) y con el **token personal** de quien
  lee o actúa en `X-BMS-Token`; las lecturas piden `ver_facturas`. La
  segunda firma llegaba con el token de la otra persona en
  `segunda_firma_token`; tras la revisión es una orden suya
  (`firmar_anulacion`) y ese campo se rechaza. Los errores tienen su código: 401 sin token
  personal, 403 sin permiso, 409 conflicto de `rev`, petición repetida con
  otra orden o estado que no lo permite, 404 lo que no existe, 400 datos
  mal formados, 413/415 cuerpo demasiado grande o que no es JSON.
- La consola: la página no lleva ningún dato; la persona escribe su token,
  que se queda en memoria (nunca en `localStorage`, `sessionStorage` ni una
  cookie). Lista por prioridad con sus insignias (nivel, revisión, calidad,
  ediciones, lo que dice el sistema) y ficha con la procedencia de cada
  campo y los formularios de cada orden, cada envío con su `peticion_id`.
  Dice en la cabecera que revisar no aprueba ningún pago.

**Cambios**

- `hallazgos.py`: la pasada termina con `excepciones.sincronizar` y
  `estados.recalcular`, en la misma transacción; `Diferencia` lleva además
  `cambios_evaluacion` (los resultados de reglas que cambiaron),
  `excepciones` y `estados`; `anular` y `resolver` aceptan `datos` (la
  petición, para la idempotencia).
- `permisos.py`: `emitir_token` (guarda solo `usuario.token_sha256`, con su
  evento), `usuario_por_token`, `sha256_token` y `desactivar_usuario` (que
  anula también el token).
- `campos.anadir_nota` e `identidad.anadir_alias` aceptan `datos`.
- `dominio.py`: `ESTADOS_EXCEPCION_ABIERTA`, `EsperandoA`,
  `ResolucionExcepcion`, `ResultadoRevision`, `EntidadPrioridad`.
- `reloj.py`: `trimestre_de`, `limite_btw` (último día del mes siguiente al
  trimestre) y `proximo_limite_btw`.
- `reglas/base.py`: `Regla.crea_excepcion` (un aviso de esa regla abre
  también excepción: Q3, K1, U1 cuando lleguen).
- `importadores/tarifas.py` apunta su fichero con `politica.registrar`.
- `almacen/evidencia.py`: `revision` y `prioridad_manual` son evidencia (su
  foto va en `revision_registrada` y `prioridad_subida`).
- `scripts/generar_guardas.py`: el mensaje de la guarda nombra al módulo que
  escribe la tabla (`excepcion` → `excepciones.py`).
- `cli.py`: `usuario token|desactivar`, `acciones`, `accion <orden>` (un
  subcomando por orden, con sus parámetros generados de `ACCIONES`, `--token`
  o `BMS_TOKEN`, `--peticion`; `--segunda-firma-token` se quitó en la revisión), `facturas [--nivel]
  [--limite]`, `factura <id> [--json]`, `excepciones`, `politica cargar
  [fichero]`; `db verificar` comprueba también las excepciones.

### La puerta, test por test

| Puerta | Tests |
| --- | --- |
| Cada orden escribe sus filas, su auditoría y su recálculo en una transacción | `test_servicios.py::test_cada_orden_escribe_filas_auditoria_y_recalculo_en_una_transaccion` (un solo `BEGIN IMMEDIATE` y un `COMMIT` después de la pasada, que lleva la causa y el usuario de la orden), `test_si_el_recalculo_falla_no_queda_nada`, y `test_cada_orden_pide_su_permiso` (las 23 órdenes, cada una con su escritura, su evento, su pasada y `verificar` limpio) |
| Una corrección que arregla D4 lo cierra con su causa y deja la edición sin resolver hasta verificarla | `test_una_correccion_que_arregla_d4_lo_cierra_con_su_causa_y_queda_sin_resolver` (el `cerrado_automatico` lleva el evento de la orden como causa y la `Diferencia` dice que D4 pasó de fallo a ok; el campo cuenta en `sin_resolver` de `factura_estado` y sale sin resolver y como discrepancia en la ficha; quien lo editó no puede verificarlo habiendo otra persona, y cuando lo verifica otra deja de contar) y `test_rellenar_lo_que_cerro_un_hallazgo_tambien_queda_sin_resolver` |
| Cualquier cambio posterior invalida una revisión | `test_revision.py::test_cualquier_cambio_posterior_invalida_la_revision` (corregir un campo, excluir una línea, reimputar, otra factura que abre un hallazgo sin tocar esta, anular un hallazgo, verificar un campo, una extracción nueva), `test_la_diferencia_de_la_orden_dice_que_revision_deja_de_valer`, `test_revisar_lo_que_ya_cambio_es_un_conflicto` y `test_una_nota_no_cambia_lo_revisado` |
| Tests de prioridad por tablas: cada suelo, cada borde, la puerta de "necesita acción", la espera externa y que solo sube | `test_prioridad.py` (134 casos): cada suelo (bloqueo, las urgentes, IVA a 7 días del BTW, compra vencida más de 30 días que necesita acción, venta vencida más de 60), cada borde de cada tramo (plazo, vencida, importe, planning, sin facturar, PO, IVA blando, otras), plazo/vencida/importe solo con acción pendiente, la espera con el seguimiento por llegar, el mismo día y pasado, la subida a mano que solo sube, vence y no llega a bloqueada, el motivo, la huella, el orden, la agregación y los pesos del YAML; `test_subir_a_mano_en_el_almacen_solo_sube` (también en la base) |
| Matriz de permisos; los usuarios de sistema rechazados en cada orden de persona | `test_servicios.py::test_la_matriz_cubre_cada_orden_y_es_la_del_paragrafo_6`, `test_cada_orden_pide_su_permiso` (por orden: una persona con todos los permisos menos ese es rechazada y deja su evento denegado; con él, pasa) y `test_ningun_usuario_de_sistema_firma_una_orden_de_persona` (cada usuario de sistema contra cada orden); en la base, `test_la_base_solo_deja_el_estado_a_una_persona_con_resolver_aviso` y `test_solo_una_persona_con_revisar_factura_y_en_su_orden` |
| Test XSS de la consola: un `<script>` del documento se pinta como texto | `test_consola.py::test_el_script_pinta_el_html_de_un_documento_como_texto` (el script de verdad, en node con un DOM que revienta ante `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write` y atributos `on*`: el nombre, la descripción y las notas con `<script>` y `<img onerror>` salen como texto y no crean ningún elemento), `test_el_script_no_usa_nada_que_interprete_html`, `test_la_pagina_no_lleva_datos_y_solo_corre_su_script` y `test_los_datos_llegan_como_json_con_el_html_tal_cual` |
| La suite de alcance corre desde aquí | `test_alcance_v1.py` (43 casos): ninguna orden, permiso, subcomando ni estado crea o prepara una factura, paga, aprueba un pago o presenta el IVA (y cada orden, ejecutada con todos los permisos, deja las mismas facturas); sin SEPA ni pain.001; sin variables, claves ni clientes de red para un banco; ninguna tabla ni columna de plazos y un solo vencimiento por factura; X1 bloquea siempre (seis monedas, también tras corregir un importe a mano, y una propiedad sobre `prioridad.calcular` con 500 entradas al azar); ningún import desde la extracción llega a `cuenta_bancaria` y un IBAN de un documento no sale de los registros del documento (propiedad con IBAN al azar, válidos y no, en la cabecera y en las notas); las peticiones de extracción no llevan herramientas |

Además: el ciclo de una excepción (`test_excepciones.py`: una por entidad,
la pasada sin cambios no escribe, un hallazgo nuevo se une, un aviso solo la
abre si su regla lo pide, asignar, esperar y resolver, el seguimiento por
defecto, no se resuelve con un bloqueo abierto, resolver no cierra
hallazgos, otra evidencia abre otra, la guarda y los CHECK, `verificar` que
ve lo tocado por detrás); la revisión (`test_revision.py`: limpia es "sin
objeciones del sistema", no se revisa con algo pendiente, autorrevisada con
una sola persona, devolver pide nota, `db verificar` ve una revisión
tocada); las órdenes (idempotencia, `rev` vieja, motivo, datos comprobados
antes de nada, dividir que suma, alias que resuelve imputaciones, fusionar
que cierra B2, segunda firma, maestro de Exact rechazado, la CLI con token
y sin `anthropic`); y la API (`test_consola.py`: leer pide token personal
con `ver_facturas` y deja el evento denegado, otra web no lee ni con el
token, cada error con su código, permiso, conflicto y segunda firma por la
API, lo que la ficha enseña).

### Desviaciones de la especificación, y por qué

1. **La migración del paso 4 es la 0004.** El §11 numera 0004 la del paso 5
   (`cuenta_bancaria`…). Cada paso tiene la suya en orden; la del paso 5
   será la 0005.
2. **`excepcion` no la escribe `campos.py` sino `excepciones.py`**, con la
   misma auditoría (rev, guarda generada, un `cambio_campo` por columna en
   el evento de la orden). En `campos.py` una fuente automática no pisa
   nunca un valor manual, y aquí el motor tiene que poder abrir una
   excepción nueva aunque una persona cerrara la anterior. Es estado de
   trabajo, no un dato de un documento. Lo que pone una persona va como
   `manual_entrada`; lo que pone el motor, como `calculado`.
3. **Nada automático asigna, deja esperando ni resuelve una excepción**, y
   el motor no la cierra aunque sus hallazgos desaparezcan
   (`condicion_desaparecida` es una resolución que elige una persona). El
   §15 deja abierta la puerta a cerrarla sola; preferimos que alguien diga
   que el trabajo terminó. La base lo exige (`excepcion_de_persona`).
4. **Qué hallazgos abren excepción**: los pendientes sin aceptar (`abierto`
   o `desaparecido`) que bloquean o retienen, más los avisos de reglas con
   `crea_excepcion` (ninguna todavía). Uno de grupo (B2, B4, G3) abre o se
   une a la excepción **de cada factura** que cubre: ninguna de las dos de
   un duplicado debe pagarse sin mirarlo.
5. **Columna añadida `excepcion.hallazgo_evento_hasta`**: el último evento
   de hallazgo que cubría la excepción al resolverse. Si después un hallazgo
   suyo se reabre o cambia su evidencia, la pasada siguiente abre otra; los
   que no cambiaron siguen cubiertos por aquella resolución. Sin esa marca
   habría que adivinarlo por fechas.
6. **Seguimiento por defecto**: hoy + 14 días, o el vencimiento si llega
   antes (y no ha pasado). Una fecha pasada se rechaza. El §15 no da un
   valor.
7. **Revisar es más estricto que el §5**: además de que el estado diga
   "necesita revisión" con un bloqueo o retención pendiente, un dudoso sin
   verificar o un cambio manual sin resolver, `marcar_revisada` se
   **rechaza** en esos casos (`NoRevisable`, con la lista de lo que falta).
   Revisar con una objeción abierta sería firmar algo que el sistema
   todavía dice que está mal; se anula o se corrige primero.
8. **Una revisión que dejó de valer, o una devuelta, deja la factura en
   "necesita revisión"**, no en "sin revisar": alguien ya la miró y hay que
   volver a mirarla.
9. **La huella del contenido** son los valores actuales de la factura y sus
   hijas, la fuente, el valor automático, `dudoso` y la verificación de cada
   campo, la evidencia de sus hallazgos pendientes **y la última anulación
   de cada uno** (renovar una anulación con otro plazo invalida la
   revisión). Una nota no la cambia. Se calcula solo para las facturas cuya
   última revisión es "revisada" (las demás no tienen nada que comparar):
   así la pasada de cinco mil facturas cabe en 2 s.
10. **"Sin resolver" incluye la edición que hizo desaparecer un hallazgo**
    (lo cerró o lo dejó desaparecido) mientras nadie la verifique: además
    del M1 del §7 (manual distinto del último automático), "editar hasta que
    el aviso se vaya" lo tiene que ver otra persona. Si el campo vuelve a
    cambiar, ya no es esa edición. M1 y Q2 todavía no son reglas: salen de
    `procedencia_campo` en cada pasada (`revision.estado_de_campos`).
11. **El plazo del BTW** que mira la prioridad es el próximo que no ha
    pasado: el IVA de un trimestre ya vencido cuenta con el plazo siguiente
    (es la declaración en la que tendrá que entrar).
12. **Subir una prioridad pide `resolver_aviso`** (el §6 no lo dice; es
    quien gestiona el trabajo), un motivo de 10 caracteres o más, solo a
    atención o urgente (bloqueada tiene siempre una regla con nombre), y la
    base rechaza un nivel por debajo del que ya tiene la entidad: "solo
    sube" está en el cálculo (el máximo) y también en la tabla.
13. **Dos hashes de la política**: `politica_version` guarda el sha256 del
    fichero tal cual; `factura_estado.politica_sha256` y
    `prioridad.politica_sha256` guardan el de los pesos en forma canónica.
    Un comentario nuevo en el YAML no cambia ninguna prioridad ni la marca
    como calculada con otra política.
14. **`politica cargar` es una orden de operador**, como `sembrar`: quien
    tiene la CLI tiene el fichero SQLite. Queda apuntada con su texto, su
    hash y su evento. La gestión de la política desde la consola con
    `admin` llega con el resto de la administración.
15. **Sin pagos (hasta el paso 7)**, `estado_pago` es `pendiente` o
    `vencida` por el vencimiento efectivo (el impreso, o la fecha más el
    plazo de pago), `anulada` si se anuló y vacío si se fusionó en otra.
    `pendiente_cent` es el total.
16. **Columnas de más en las cachés**: `factura_estado` lleva también
    `vencimiento`, `dudosos`, `pendientes`, `sin_datos`, `excepcion_id`,
    `huella_entradas` y `politica_sha256`; `prioridad` lleva `vencimiento`,
    `importe_cent` y las dos huellas. Son lo que los filtros del §18 y el
    orden del §8 necesitan sin otra consulta. Los CHECK de las cachés son
    cadenas de `OR` en vez de `IN (...)`, por velocidad (como en el paso 3).
17. **Órdenes que no están**, porque su tabla o su regla es de un paso
    posterior: marcar pagada y confirmar un pago (paso 7), registrar o
    modificar una PO (órdenes de compra), enlazar o confirmar relaciones
    (relaciones), verificar, rechazar o atestar un IBAN y el teléfono de
    verificación (paso 5), estado del BTW (paso 11), importar (paso 5) y
    dar de alta un Objeto (hoy, con `sembrar`). `recalcular` es una orden
    con `ver_facturas`: no cambia ningún dato, solo lo pone al día.
18. **Idempotencia**: `evento.peticion_id` (único) y el sha256 de la orden
    en los datos del evento. La misma petición con los mismos datos y la
    misma persona devuelve la `Diferencia` marcada como repetida sin
    escribir nada; con otra orden u otra persona es `PeticionRepetida`.
19. **El token de `/api/v2` es personal** (el de `bms-agent usuario token`,
    guardado solo por su hash), en la misma cabecera `X-BMS-Token` que el
    del servidor; el del servidor sigue valiendo solo para `/api/ejecutar`.
    Así cada lectura y cada orden tiene una persona detrás, con sus permisos.
20. **Los importes llegan como texto**: un número JSON con decimales se
    rechaza (400) antes de parsear, y un texto con separador de miles
    también ("2.902,79" sería ambiguo; se escribe 2902,79 o 2902.79). Un
    float no vuelve a entrar por la puerta de atrás.
21. **`consultas.py` es mínimo**: lista, ficha, excepciones, personas y
    Objetos. Los bloques del §17 y los filtros del §18 son del paso 12.
22. **`Regla.crea_excepcion` entra en el metadato**, así que cambió el
    hash del catálogo. Las pasadas viejas siguen diciendo con qué catálogo
    se hicieron.
23. **La suite de alcance mira lo que existe**: `cuenta_bancaria` no existe
    todavía, así que la propiedad del IBAN comprueba hoy que lo impreso no
    sale de los registros del documento (extracción, factura, procedencia,
    auditoría y lo que dicen las reglas) y, si la tabla existe, que no tiene
    filas; el grafo de imports ya prohíbe el camino. Las variables de
    entorno están en una lista cerrada (`BMS_DB`, `BMS_TOKEN`,
    `BMS_EXTRACT_MODEL`, `BMS_EXTRACT_MAX_TOKENS`): una nueva tiene que
    pasar por el test.

**Tests existentes cambiados**: `test_auditoria.py` (el primer evento de
una prueba es `MIGRACIONES + 1`, no un 4 fijo) y `test_almacen.py` (las
tablas nuevas en la lista de solo escritura y en la de guardas, y una fila
de cada una en `_poblar`). Ninguno prueba menos que antes.

**Un fallo encontrado por la puerta**: el XSS en node pilló que
`anadir(nodo, a, b, …)` de la consola solo ponía el primer hijo, así que la
ficha salía con el título y nada más. Ahora `anadir` acepta cualquier
número de hijos, como `el()`.

### Lo que deben saber los pasos siguientes

- **Una orden nueva** es una `Accion` en `servicios.ACCIONES` (parámetros
  tipados, permiso, si pide motivo y la función que escribe). Sale sola en
  la CLI (`bms-agent accion <orden>`), en `GET /api/v2/acciones` y en la
  consola. Tiene que entrar también en `CASOS` de `test_servicios.py` (la
  matriz falla si falta) y pasa por la suite de alcance, que la ejecuta con
  todos los permisos.
- **Lo que cambie una orden** se escribe dentro de `ejecutar`, que ya abre
  la transacción y recalcula con la causa; no hace falta llamar a
  `hallazgos.recalcular` desde la acción.
- **Paso 5 (maestros e IBAN)**: la migración es la 0005. Q2 y M1, si se
  hacen reglas, no deben contar dos veces con `dudosos` y `sin_resolver`
  de `factura_estado` (hoy salen de la procedencia y ya ponen atención).
  Q3, K1 y U1 llevan `crea_excepcion=True`. La propiedad del gate
  ("ninguna extracción crea ni cambia una fila de `cuenta_bancaria`") tiene
  ya su sitio en `test_alcance_v1.py`; el módulo que escriba la tabla no
  puede importar nada de la extracción (`EXTRACCION` en ese test) y, si
  `campos.py` la registra, su alta pide `confirmar_iban`. Las órdenes de
  IBAN piden `confirmar_iban`.
- **Paso 7 (pagos)**: `estados.estado_pago` tiene que leer el saldo
  (`v_factura_saldo`) para `pagada` y `pendiente_cent`; una factura pagada
  sale de juego (`Entradas.en_juego`), que apaga plazo y vencida. Marcar
  pagada es una `Accion` con `marcar_pagada`.
- **Las reglas de planning, facturación y PO** (G, V, P) dan sus entradas
  de prioridad en `valores_json` con estos nombres: `valor_cent` (lo que
  vale la discrepancia o el trabajo sin facturar), `semanas_tras_gracia`
  (V6) y `dias_para_caducar` (P7). La entrada (`entrada_prioridad`) y si
  pone suelo urgente (`prioridad.REGLAS_URGENTES`) salen del catálogo y del
  código, no del fichero.
- **Los pesos** se cambian en `config/prioridad.yaml` y se aplican con
  `bms-agent politica cargar`; un fichero sin la forma entera se rechaza.
  Los suelos no están en el fichero y no se pueden relajar desde él.
- **La consola** (paso 12) crece en `consola_assets.py` con `el()` y
  `anadir()`: nunca `innerHTML` ni nada que interprete HTML (un test lo
  busca en el script), ningún dato en la página, el token en memoria.
- **La velocidad**: la pasada de cinco mil facturas está en 1,1-1,7 s con
  todo lo del paso 4. Lo que se añada a la pasada (pagos, planning) tiene
  que leer de una vez, no por factura, y escribir solo lo que cambia, como
  `estados.recalcular`.

### Correcciones de la revisión

La revisión del paso 4 dejó dieciséis hallazgos; dos estaban repetidos (los
puntos por importe de una anulada o fusionada, en `prioridad.py` y en
`estados.py`, y las subidas y excepciones de entidades que no existen), así
que son catorce. Cada uno se reprodujo antes de tocarlo y todos eran reales;
uno (la reimputación en la puerta de la revisión) era un hueco del test, no
del código. **1058 tests pasan** (627 funciones de test; eran 1011 y 608):
veinte funciones nuevas y una quitada (la de la segunda firma por id, que
sustituye la de la orden `firmar_anulacion`). Todas las nuevas fallan con el
commit del paso 4 salvo las que miden lo que ya estaba bien:
`test_un_importe_sin_separador_de_miles_entra` (lo que tiene que seguir
entrando) y el caso nuevo `anulacion_vence` de la puerta de la revisión. El
caso `imputar` corregido falla si `cambiar_objeto` no hace nada, y el de
antes pasaba igual.

| Hallazgo | Qué se hizo | Test |
| --- | --- | --- |
| "1.000" escrito por una persona se leía como 1,000: 100 céntimos guardados como corrección humana, mil veces menos (el extractor lee lo mismo como mil). `\d` admitía además cifras árabes ("٣" era 3) | `valor_de_entrada` rechaza un solo separador seguido de tres cifras detrás de lo que puede ser un grupo de miles (`1.000`, `12.400`, `1,000`), con el mismo mensaje de la desviación 20, y solo admite cifras ASCII (también en los enteros de los parámetros). `0.125` y `1000.000` siguen entrando: no pueden ser miles | `test_un_importe_con_separador_de_miles_o_cifras_raras_no_entra`, `test_un_importe_sin_separador_de_miles_entra`, `test_un_importe_de_mil_con_punto_no_se_guarda_mil_veces_menor` (por `fijar_campo`, `dividir_linea` y un id) |
| Volver el mismo día a un fichero de política anterior (A, B, A) no apuntaba nada, la CLI decía que A era la vigente y valían los pesos de B; con las tarifas, las filas volvían a A y `politica_version` seguía en B | La versión vigente es la última cargada, por orden de carga: `registrar` solo mira si el contenido es el de la vigente. La 0004 rehace `politica_version` sin el `UNIQUE (fichero, sha256, vigente_desde)` de la 0001 (mismas columnas, mismos datos, sus dos disparadores de solo escritura) y añade `politica_version_cambia`, que no deja apuntar otra vez la versión que ya vale | `test_volver_a_unos_pesos_anteriores_el_mismo_dia_los_pone_en_vigor`, `test_ingesta.py::test_una_tarifa_cambiada_en_el_fichero_se_actualiza` (vuelve al fichero de antes) |
| Un error de la base en una orden (un Objeto que no existe al dividir) tiraba la conexión en `/api/v2` y sacaba una traza en la CLI; un campo que no existe daba 404 | `dividir_linea` comprueba que existe cada Objeto (`LookupError`); `_codigo_de` da 409 a `sqlite3.IntegrityError` y `bms-agent accion` la recoge como las demás; un campo que no está en el registro es `DatosNoValidos` (400). `anadir_linea` no recibe ninguna clave foránea (sus campos son los impresos), así que no había nada que comprobar allí | `test_lo_que_no_existe_se_dice_y_no_revienta_en_la_base`, `test_un_error_de_la_base_tiene_su_codigo_y_la_cli_no_ensena_una_traza` |
| `subir_prioridad` y `crear_excepcion` aceptaban entidades que no existen (también `orden_compra`, cuya tabla no existe) | `almacen.comprobar_entidad`: la fila tiene que existir en su tabla; un trimestre es año × 10 + trimestre (1 a 4); una tabla que llega en un paso posterior (`orden_compra`, `movimiento`) da `EntidadNoDisponible`. La llaman `estados.subir_prioridad` y `excepciones.crear` para cualquier tabla | `test_subir_la_prioridad_de_algo_que_no_existe_no_entra`, `test_una_excepcion_a_mano_es_de_algo_que_existe` |
| Una factura anulada o fusionada sin revisar sumaba puntos por importe (una anulada de 30.000 € quedaba en Atención para siempre) y contaba en su proveedor, cliente, Objeto y trimestre | Los puntos por importe piden `en_juego`, como los de plazo. `estados._agregados` deja fuera las anuladas y fusionadas; su excepción, si la tienen, conserva su prioridad. El paso 7 tiene que sacar también las pagadas | `test_prioridad.py::test_lo_que_no_esta_en_juego_no_suma_por_importe`, `test_servicios.py::test_una_anulada_no_cuenta_en_su_proveedor_ni_en_su_trimestre` |
| El caso `imputar` de la puerta "cualquier cambio invalida la revisión" pasaba sin que `cambiar_objeto` hiciera nada: la semilla de tarifas, que iba antes, ya la invalidaba. El comentario de `anular` decía "vence" y el caso renovaba | La semilla va en `_preparar`, antes de revisar. El comentario dice lo que hace el caso, y hay un caso nuevo, `anulacion_vence`: la anulación vale hasta hoy, pasa un día, la pasada diaria reabre el B4 y la revisión deja de valer | `test_revision.py::test_cualquier_cambio_posterior_invalida_la_revision[imputar]` y `[anulacion_vence]` |
| `_cuenta` trataba cualquier `moneda_doc` como moneda extranjera: con una extracción v2 que guarda "EUR", las facturas en euros salían de los totales de la `Diferencia` | Cuenta lo que X1 da por euros: `reglas.instantanea.moneda_extranjera` (antes `_moneda`, ahora pública) | `test_los_totales_cuentan_las_facturas_en_euros_aunque_digan_eur` |
| Fusionar cerraba cualquier B2 desaparecido que tocara una de las dos facturas, también otro duplicado que alguien había editado y nadie había mirado | `_cerrar_b2` cierra solo los B2 que pasaron a desaparecido en la pasada de esta orden, con su evento como causa, y cuyas facturas son la fusionada y su destino. Los demás esperan a `cerrar_hallazgo` | `test_fusionar_solo_cierra_el_b2_que_la_fusion_hizo_desaparecer` (el escenario de la revisión: c/a, a renumerada, b, b→a) |
| La segunda firma viajaba como el token personal de la otra persona dentro de la orden de la primera (en la consola, en un campo de la página; en la CLI, en `argv`): quien pedía la anulación se quedaba con un token sin caducidad ni alcance y podía actuar como la otra persona, también para firmar sus propias anulaciones | La segunda firma es una orden de la segunda persona, desde su sesión: `firmar_anulacion` (`anular_aviso`, motivo obligatorio) con el hallazgo, la huella que ve, para quién (`solicitante_id`, otra persona activa) y el plazo de la anulación. Es un evento suyo, `anulacion_firmada`, que caduca a las 24 horas (`FIRMA_VALIDA_HORAS`) y se gasta al usarse: `anular_hallazgo` busca una firma sin gastar ni caducar para esa persona, esa huella y ese plazo, y el evento `hallazgo_segunda_firma` lleva `firma_evento_id`. Ya no hay `segunda_firma_id` en `ejecutar`, `segunda_firma_token` en `/api/v2` (400), `--segunda-firma-token` en la CLI ni campo de token en la consola, que ofrece "Dar la segunda firma" cuando la anulación la pide (`consultas` dice ahora `requiere_segunda_firma`, no solo la marca de la regla) | `test_la_segunda_firma_es_una_orden_de_la_otra_persona` (nadie se firma a sí mismo, huella vieja, otra persona u otro plazo no la usan, se gasta, caduca), `test_permiso_conflicto_y_segunda_firma_por_la_api`, `test_ni_la_consola_ni_la_cli_piden_el_token_de_otra_persona` |
| Cualquier web podía añadir filas a la auditoría: un `GET /api/v2/*` sin token (un `<img src>` llega sin Origin) dejaba un `permiso_denegado` | Sin token se contesta 401 sin escribir nada; solo se audita un token que llega y no vale ("token personal no valido"). Ponerlo desde otra web pide una consulta CORS previa, que el Origin ya rechaza | `test_otra_web_no_llena_la_auditoria_con_lecturas_sin_token`, `test_leer_pide_un_token_personal_con_ver_facturas` |
| Una excepción se resolvía con un bloqueo pegajoso desaparecido sin cerrar, que el §7 trata como abierto | `bloqueos_abiertos` y el disparador `excepcion_resolver` cuentan también los desaparecidos que bloquean: primero se cierran (`cerrar_hallazgo`). No se eligió resolver con `condicion_desaparecida` cerrándolos en la misma orden: cerrar un pegajoso es mirar su evidencia, y esa orden pide su huella | `test_excepciones.py::test_no_se_resuelve_con_un_bloqueo_desaparecido_sin_cerrar` (por el código y saltándoselo) |
| No había orden para añadir una referencia (una PO) que la extracción no trajo | `anadir_referencia` (`cambiar_po`, motivo obligatorio, `rev` de la factura): crea la `factura_referencia` como `manual_entrada`; sin `clase`, la decide la etiqueta como en la extracción | `test_anadir_una_referencia_que_la_extraccion_no_trajo`, y en `CASOS` (matriz, permisos, usuarios de sistema, suite de alcance) |
| Las prioridades se calculaban con pesos que no estaban en `politica_version` hasta un `politica cargar` | La pasada que calcula prioridades sin ningún `prioridad.yaml` apuntado apunta los de `prioridad.Pesos`, con el texto que da `prioridad.pesos_a_yaml` (lo lee `pesos_de_yaml` y da los mismos pesos), con el usuario `sistema`. Solo la primera vez y solo si hay facturas | `test_los_pesos_con_que_se_calcula_estan_siempre_en_la_politica` |
| `cerrar_hallazgo` no pedía la huella: se cerraba un pegajoso sin probar que se había visto su evidencia | La huella es obligatoria, como en `anular_hallazgo` (la consola ya la mandaba) | `test_cerrar_un_hallazgo_pide_la_evidencia_que_se_vio` |
| `dividir_linea` solo miraba que las partes sumaran la línea: 101.593,75 a un Objeto y −100.000 a otro movían dinero entre obras | Cada parte es distinta de cero, del signo de la línea y no mayor que ella; las horas, si se dan, del signo de la cantidad de la línea y no mayores | `test_dividir_no_mueve_dinero_entre_objetos` |

**La migración 0004 se corrige en su sitio** (el disparador
`excepcion_resolver` y la tabla `politica_version` rehecha), como la 0003 en
la revisión del paso 3: ninguna base la tiene aplicada fuera de los tests.
Una base local creada con la versión anterior la rechaza `migrar` por el
hash; se rehace con `bms-agent importar-out`, que no gasta API. La 0001 no
se toca: la tabla se rehace en la 0004 con los mismos datos.

Desviaciones nuevas, y por qué:

- **"1,000" también se rechaza**, no solo "1.000": para quien escribe en
  inglés son mil. Una cantidad con tres decimales se escribe con un cero
  delante (`0,125`) o sin el separador ambiguo (`1,5` en vez de `1,500`).
- **La firma vale 24 horas y una vez**, ata la huella, la persona que
  anula y el plazo, pero no el motivo de la anulación: quien firma escribe
  el suyo, que queda en su evento. Si quien firmó pierde `anular_aviso`
  antes de que se use, la anulación se rechaza.
- **`--token` sigue en la CLI** (es el token de quien la usa, en su propia
  sesión); `BMS_TOKEN` es la forma recomendada. El de otra persona ya no
  pasa por ningún sitio.
- **El texto de los pesos apuntados por la primera pasada no es el de
  `config/prioridad.yaml`** (sin comentarios): cargar después ese fichero
  apunta otra versión con el mismo hash canónico, y ninguna prioridad
  cambia (desviación 13).

**Tests existentes cambiados**: `CASOS` de `test_servicios.py` (con
`anadir_referencia` y `firmar_anulacion`; `cerrar_hallazgo` manda la huella;
el escenario tiene a Dora, que solo consulta, para quien se firma),
`test_la_matriz_cubre_cada_orden_y_es_la_del_paragrafo_6` (las dos órdenes),
`test_los_datos_se_comprueban_antes_de_hacer_nada` (`segunda_firma_id` ya no
existe: `TypeError`), `test_anular_con_la_segunda_firma_de_otra_persona`
(quitado: lo sustituye `test_la_segunda_firma_es_una_orden_de_la_otra_persona`,
que prueba más), `test_leer_pide_un_token_personal_con_ver_facturas` (cuatro
denegaciones, las del token que no vale, en vez de ocho),
`test_permiso_conflicto_y_segunda_firma_por_la_api` (400 en vez de 401),
`test_una_tarifa_cambiada_en_el_fichero_se_actualiza` (cuenta las versiones
de `tarifas.yaml`: la pasada apunta también los pesos) y la puerta de la
revisión (`imputar` siembra antes de revisar). Ninguno prueba menos que
antes.

Lo que deben saber los pasos siguientes, además de lo de arriba:

- **Una orden que pida la firma de otra persona** sigue el modelo de
  `firmar_anulacion`: la otra persona firma en su sesión, atada a lo que
  ve, para quién y con caducidad; nunca un token o un id dentro de la
  orden de la primera.
- **Paso 7**: una pagada sale de juego y deja de sumar por importe y de
  contar en sus agregados (`estados._agregados`, conjunto `en_juego`).
- **Paso 9**: cuando exista `orden_compra`, `comprobar_entidad` la acepta
  sola (mira si la tabla existe).

### Cierre de la puerta

La puerta del paso 4 falló en un solo punto: **la suite no pasaba siempre**.
En una de tres ejecuciones,
`test_un_error_de_la_base_tiene_su_codigo_y_la_cli_no_ensena_una_traza`
salió con `argument --token: expected one argument`. La causa estaba en el
producto, no en el test: `emitir_token` daba `secrets.token_urlsafe(32)`,
que empieza por `-` una vez de cada 64 (el 1,5 % medido), y argparse lee
`--token -XXXX` como otra opción. Uno de cada 64 tokens que imprime
`bms-agent usuario token` no se podía pasar como dice la propia CLI
(`--token X`): la orden salía con 2 sin ejecutarse. Los cuatro sitios de
`test_servicios.py` que pasan `"--token", token` fallaban así al azar. El
otro fallo de aquella revisión (`test_rendimiento[400]`) venía de correr ese
test dos veces a la vez; solo pasa.

Buscando lo mismo en el resto de la orden salió un segundo caso con la
misma causa: **un abono no se podía escribir**. `--valor -2900,00` o
`--valor -1.234,56` (un importe negativo con coma decimal, como lo escribe
la administración) también salían con 2; argparse solo deja pasar los
negativos que reconoce como número suyo (`-5`, `-100.5`).

| Qué se hizo | Por qué | Test |
| --- | --- | --- |
| `permisos.token_nuevo()`: `PREFIJO_TOKEN` (`bms_`) delante de `token_urlsafe(32)`, y `emitir_token` lo usa | Ningún token empieza por `-`, así que ninguno parece una opción en la CLI ni en ninguna otra herramienta; además se reconoce como token de este programa si aparece donde no debe. El azar es el mismo (256 bits) | `test_permisos.py::test_ningun_token_empieza_por_guion` (con `token_urlsafe` forzado a empezar por `-`, el token sale con el prefijo y vale; dos mil tokens, todos con prefijo y distintos) |
| `cli._unir_valores_de_accion`: en `accion`, lo que sigue a una de sus opciones se pasa a argparse como `--opcion=valor` | Así entra cualquier valor que empiece por `-`: un abono y también un token emitido antes del prefijo. Solo en `accion`, donde toda opción lleva valor (en otras órdenes hay opciones sin valor, como `--force`). Si lo que sigue es otra opción de la orden o la ayuda, no se junta: argparse sigue diciendo que falta el valor en vez de guardar `--db` como motivo | `test_servicios.py::test_la_cli_pasa_valores_que_empiezan_por_guion` (un token que empieza por `-` firma `recalcular` y `fijar_campo`, y `--valor -2900,00` guarda −290.000 céntimos; `--token` sin valor sigue saliendo con 2) y `test_la_cli_solo_junta_los_valores_de_las_opciones_de_accion` (lo que se junta y lo que no: otras órdenes, la ayuda, una opción sin valor, una que no es de la orden) |

Los tres tests nuevos fallan con el código anterior (el de la CLI, también
con solo `cli.py` anterior y `permisos.py` nuevo). Ningún test existente
cambia: con el prefijo, los que pasan `"--token", token` dejan de depender
del azar. **1061 tests pasan** (630 funciones de test; eran 1058 y 627).

Desviaciones nuevas, y por qué:

- **El token lleva prefijo** (`bms_…`). La especificación no fija su forma.
  Los tokens emitidos antes siguen valiendo: la base guarda el sha256 de lo
  que se emitió, y la CLI los acepta también si empiezan por `-`.
- **`accion` acepta un valor que empieza por `-` detrás de cualquiera de sus
  opciones**, no solo de `--token` y `--valor`: un motivo o una nota pueden
  empezar por un guion. Las abreviaturas de argparse (`--tok`) no se juntan;
  la forma documentada es el nombre entero.

## Paso 5

Maestros y registro de cuentas bancarias. **1167 tests pasan** (684
funciones de test; eran 1061 y 630 al cerrar el paso 4), ninguno llama a la
API y ninguno escribe fuera de una carpeta temporal. Entran los importadores
de maestros (un marco común, mapeos YAML versionados con su test de
contrato), el registro de cuentas con su línea base, atestación y
verificación por teléfono, y veintiuna reglas nuevas (A0, A2, A5, A7, A8,
E1, E2, U1, Q2, Q3, Q4, Z1, Z2, F0, F2, F3, F4, F5, F6, F8, F9) más X1 sobre
las importaciones. Cinco mil facturas se recalculan en 1,5-1,9 s la primera
vez y en 1,25-1,6 s las siguientes (ocho medidas de cada caso en este
contenedor, que es ruidoso: el código del paso 4 mide 1,5-1,7 s y 1,2-1,4 s
en las mismas condiciones). Ver "Lo que deben saber los pasos siguientes".

### Qué se construyó

**Módulos nuevos**

| Módulo | Qué hace |
| --- | --- |
| `cuentas.py` | **El único que escribe `cuenta_bancaria` y `cuenta_evento`.** `apuntar_maestro()` (lo que trae una importación completa de cuentas: altas, `baseline` si es el primer maestro de Exact de ese tipo de titular, `visto_en_*` por cada una y `ausente_en_*` por las que traía la anterior y esta no), `decidir()` (verificar, rechazar o atestar una o varias cuentas una persona con `confirmar_iban`, con motivo; si la cuenta no está y se pide, la da de alta como `verificacion_manual`), `cuenta_de`, `telefono_ref` y `verificar()` (cada fila contra la foto de su evento de auditoría). Ninguna función recibe un IBAN de una extracción |
| `importadores/base.py` | El marco del §9: `Lector` (protocolo: `reconoce`, `leer`), `LoteLeido` (registros canónicos, rechazos con su fila, código y crudo, hash, mapeo, de cuándo es, si es una foto completa), `Rechazo` y `ATOMICOS` (los tipos que entran todo o nada) |
| `importadores/canonico.py` | Los registros canónicos (pydantic, `extra='forbid'`, congelados, Decimal y date, con la fila y el crudo): `ProveedorCanonico`, `ClienteCanonico`, `CuentaBancariaCanonica` (sin ningún campo de estado; el IBAN pasa el módulo 97 o la fila no se lee), `ObjetoCanonico`, `RecursoCanonico`, `AliasCanonico`, `TarifaCanonica` (con la moneda del fichero), `CicloCanonico` y `MODELOS` |
| `importadores/tabular.py` | El lector de CSV guiado por un mapeo: `Mapeo`/`Registro`/`Campo`, `mapeo_de_yaml` (rechaza un campo que el registro canónico no tiene), `mapeos()`, `decodificar` (utf-8-sig y cp1252, en el orden del mapeo), separador decimal y de miles, formatos de fecha, mapas de valores, campos derivados (`unir`), valores fijos, `omitir_si_vacio`, `LectorTabular` (`reconoce` por la huella de la cabecera), `lectores()`, `elegir_mapeo()` y `contrato()` (lo que fija el test de contrato) |
| `importadores/registrar.py` | **`registrar_lote`, el único escritor de lo que trae una importación** (ver más abajo), los escritores por tipo (proveedores y clientes por su número del sistema o adoptando el que ya se conocía por btw-id, KvK o alias; Objetos, recursos, alias, tarifas por su clave natural, ciclos), `_cuentas` (todo o nada), `_retirar_ausentes` (la foto completa), `importacion_previa` e `importar_fichero` (la orden entera: elegir el mapeo, leer, registrar cada lote, reconciliar las facturas y recalcular, en una transacción; `simular` lo deshace) |
| `reglas/normas.py` | Las normalizaciones puras (btw-id, KvK, nombre, IBAN, `parece_iban`, teléfono con el prefijo de país como 0): las comparten las reglas (que no pueden importar nada de fuera de `reglas/`) e `identidad.py`, que las reexporta |
| `reglas/identidad.py` | A0, A2, A5, A7 y A8 |
| `reglas/anomalias.py` | U1 con el método exacto de la especificación, en aritmética entera (mediana doblada y MAD por cuatro), con la mediana de las desviaciones buscada sobre la lista ordenada sin construirla y un atajo por conteo cuando basta para decir que no es raro |
| `scripts/regenerar_contratos.py` | Escribe el JSON esperado de cada mapeo (y de la semilla) desde su fichero de ejemplo; se ejecuta solo cuando un mapeo cambia a propósito |
| `config/importacion/*.yaml` | Siete mapeos: `exact-proveedores-v1` (acreedores con su cuenta, condiciones de pago, código de IVA y el teléfono de verificación), `exact-clientes-v1`, `maestro_csv-objetos-v1`, `-recursos-v1`, `-alias-v1`, `-tarifas-v1` y `-ciclos-v1` (ocho tras la revisión, con `-contactos-v1`) |
| `config/reglas.yaml`, `config/empresa.yaml` | Las tolerancias, el interruptor de las cuentas, el enfriamiento y la frescura (iguales a `reglas.base.Politica`; un test lo comprueba); la identidad de BM Support BV (`btw_id`, `kvk` y `cuentas_propias` por rellenar) |

**Tablas** (migración `0005_maestros_cuentas.sql`), STRICT, con clave
entera y sin columnas REAL:

| Tabla | Clase | Qué no se puede hacer |
| --- | --- | --- |
| `cuenta_bancaria` | SOLO ALTA (`UPDATE` y `DELETE` abortan) | Darla de alta alguien que no sea el usuario de sistema importador con una importación de ese maestro en curso y en su evento, o una persona activa con `confirmar_iban` en ese momento y en su propia orden (`verificacion_manual`); dos filas para el mismo titular e IBAN; un IBAN con otra forma; `primera_fuente` de maestro sin importación o manual con ella |
| `cuenta_evento` | SOLO ESCRITURA | `UPDATE` y `DELETE`; `verificada`, `rechazada`, `atestada` o `retirada` sin una persona con `confirmar_iban` en ese instante, fuera de su orden o del importador; `verificada` sin método ni teléfono llamado; `baseline`, `visto_en_*` o `ausente_en_*` sin la importación en curso del importador; `visto_en_documento` nunca (está en la lista del §5.C, pero lo que dice un documento no entra) |
| `beneficiario_conocido` | Controlada (rev y guarda generada) | Dos vigentes con el mismo IBAN; cambiar el IBAN, quién o cuándo; borrarla (se retira) |
| `ciclo_facturacion` | Controlada | Un ciclo sin cliente ni Objeto; vigencias al revés; otra frecuencia que semanal, cuatrisemanal o mensual |

Y la vista `v_cuenta_estado` (la última decisión de una persona, columna
`ultima_decision` tras la revisión, y si la trae el último Exact; no es el
estado de la cuenta), y un índice parcial de los campos dudosos para la
instantánea.

**El registro de cuentas** (decisiones 3 y 4). El estado de una cuenta no
está en su fila: lo dicen sus eventos, y lo calcula una función pura
(`reglas.bancaria.estado_cuenta`) que usan las reglas, las órdenes y las
consultas:

- El primer maestro de Exact es la **línea base**: sus cuentas quedan
  `heredada`, aceptadas como referencia y enseñadas sin verificar, y nace
  una sola tarea (F0, sobre esa importación, de nivel atención) para
  atestarlas.
- Lo que un maestro posterior **añade, quita o vuelve a traer** es un cambio
  que bloquea (F5) hasta que una persona lo verifica por teléfono o lo
  rechaza; otra importación que lo deje como estaba no lo cierra.
- **Pagable** = verificada, atestada o heredada **y** presente en la última
  importación de Exact que la miró **y** sin un cambio pendiente. Con
  `cuentas.solo_verificadas: true` (lo estricto de D2) lo heredado deja de
  serlo.
- Una **verificación por teléfono cuenta** si el número llamado es el que
  tenía el maestro antes de que llegara lo que la motivó (el documento de la
  factura, o el fichero de la importación del maestro), si el teléfono no
  cambió en los `cuentas.enfriamiento_telefono_dias` (14) anteriores y si
  quien llamó tenía `confirmar_iban`. Si no, queda apuntada y no cuenta
  (F8). Cambiar el teléfono abre el enfriamiento (F9).

**`registrar_lote` garantiza** (§9): repetir el mismo fichero no hace nada
(fuente, tipo y hash); el fichero va al almacén de documentos; cuentas todo
o nada, el resto fila a fila con lo rechazado en la importación (Z2); cada
valor por `campos.py` con fuente `importacion` y referencia `importacion:N`;
un valor puesto a mano no se pisa (queda como automático y el campo sin
resolver); un campo de Exact solo lo escribe Exact; ningún estado decidido
(ni el modelo canónico tiene el campo ni la base lo admite del importador);
un IBAN solo entra como fila de `cuenta_bancaria` y evento `visto_en_*`; lo
que falta en una foto completa queda `ausente_*` (cuentas) o inactivo
(proveedores y clientes de ese sistema, y solo si la foto entró entera);
una referencia desconocida rechaza la fila y nada se crea solo (coincidencia
exacta); la ejecuta el importador y la lanza una persona con
`importar_datos`, y quedan los dos; `exportado_en` mide la frescura; las
reglas se recalculan en la misma transacción.

**Reglas nuevas** (`reglas/catalogo.py`, en el orden del §7):

| Regla | Qué mira | Al fallar |
| --- | --- | --- |
| Q2 | Un campo crítico leído con duda que nadie ha verificado | Retiene; no se anula |
| Q3 | Las notas del documento traen texto dirigido a quien lo procesa (una instrucción al sistema, o un cambio de datos junto a otra clase de marca; tras la revisión) | Aviso con excepción; se anula. La evidencia dice qué clase de cosa se vio, nunca el texto |
| Q4 | El original del documento no está en el almacén | Aviso; se anula |
| X1 | Además de las facturas: una fila de un maestro con un importe en otra moneda (no entra) | Bloquea la importación; pegajosa |
| Z1 | Una fuente pasada de su límite de frescura (Exact 7 días, TRNSPRNT 7, banco 3 laborables) | Aviso sobre su última importación y aviso en `bms-agent facturas`, `bms-agent fuentes` y la consola; A2, E1, F2 y F3 dan sin datos en vez de ok |
| Z2 | La última importación de una fuente y tipo rechazó filas o entera | Retiene la importación |
| A0 | La contraparte no se conoce o es ambigua (sin datos hasta que entra el maestro de su tipo) | Retiene; no se anula |
| A2 | Lo impreso (btw-id, KvK, nombre o un alias confirmado) no es lo del maestro de la contraparte resuelta | Retiene; se anula |
| A5 | Una compra sin btw-id que no dice KOR (bloquea); un btw-id neerlandés con otra forma (retiene) | |
| A7 | Lo impreso cambia respecto a la factura anterior del mismo proveedor: btw-id o KvK retienen, nombre o dirección avisan | Se anula; pegajosa |
| A8 | No va dirigida a BM Support BV (`config/empresa.yaml`); una de salida que no emite BMS está mal encaminada (bloquea) | Retiene; se anula |
| E1 | El régimen de la factura no es el que el maestro tiene del proveedor | Retiene; se anula (IVA blando) |
| E2 | El régimen cambia respecto a la factura anterior | Retiene; se anula; pegajosa (IVA blando) |
| U1 | La base se sale de lo habitual de la contraparte (el método del §7) | Aviso con excepción; se anula |
| F0 | Cuentas heredadas del primer maestro sin atestar | Retiene la importación de partida (la tarea de atención) |
| F2 | El IBAN de la factura no es una cuenta pagable de su proveedor | Bloquea |
| F3 | El IBAN es nuevo para el proveedor, o está rechazado | Bloquea |
| F4 | El IBAN está registrado para otro titular, o la factura habla de factoring, cesión o G-rekening | Bloquea con excepción |
| F5 | Una cuenta añadida, quitada o vuelta a traer por un maestro posterior al primero | Bloquea, sobre el proveedor (una por cuenta) y, tras la revisión, sobre cada factura de compra en juego de ese proveedor |
| F6 | Exact y TRNSPRNT no dicen las mismas cuentas de un proveedor | Bloquea, sobre el proveedor |
| F8 | La última verificación de una cuenta no cuenta | Bloquea, sobre el proveedor |
| F9 | El teléfono de verificación cambió hace menos que el enfriamiento | Aviso, sobre el proveedor |

Todas las F son pegajosas y ninguna se anula (la base ya lo exigía para
cualquier F). Se cierran con una verificación, un rechazo, una atestación o
un cambio en los datos: la orden de IBAN que hace desaparecer un hallazgo F
lo resuelve en la misma orden, firmada por quien decidió.

**Órdenes nuevas** (`servicios.ACCIONES`):

| Orden | Permiso | Qué hace |
| --- | --- | --- |
| `verificar_iban` | `confirmar_iban` | Verificar por teléfono una cuenta de un proveedor (la nueva de una factura o la del maestro). El IBAN lo teclea la persona; la orden dice si la verificación cuenta y por qué no. Quien cambió el teléfono de ese proveedor no verifica con él si hay otra persona con el permiso |
| `rechazar_iban` | `confirmar_iban` | Rechazar una cuenta; con la factura que la traía, decir si se paga a la verificada (sus F2 y F3 dejan de bloquearla si el proveedor tiene una pagable) o se anula |
| `atestar_iban` | `confirmar_iban` | Atestar una cuenta heredada, o todas las que faltan (la tarea de F0) |
| `fijar_telefono_verificacion` | `confirmar_iban` | El teléfono al que se llama; cambiarlo abre el enfriamiento. `corregir_maestro` ya no lo toca |
| `anadir_beneficiario`, `retirar_beneficiario` | `admin` | Un beneficiario que no es proveedor (Belastingdienst, nóminas, alquiler), para F7 (paso 7) |

**CLI**

- `bms-agent importar <fuente> <tipo> <fichero> [--mapeo M] [--simular]
  [--exportado AAAA-MM-DD] [--token T]`: con el token de una persona con
  `importar_datos`. Dice por lote lo que entró, lo rechazado con su fila y
  su código, lo que quedó sin resolver (M1), las cuentas nuevas y ausentes,
  y lo retirado. Sin `--exportado` cuenta el día en que se guardó el fichero.
- `bms-agent iban listar|verificar|rechazar|atestar|telefono`: el registro
  con su estado (pagable, en Exact, cambio sin verificar, verificación que
  no vale) y las cuatro órdenes de cuentas.
- `bms-agent fuentes`: de cuándo es lo último de cada fuente y tipo, su
  edad, su límite y si está pasada.
- `bms-agent politica cargar` acepta también `config/reglas.yaml` y
  `config/empresa.yaml` (por su nombre) y, tras la revisión, pide el token de
  una persona con `admin`; `db verificar` comprueba también el registro de
  cuentas (`cuentas.verificar`).
- `GET /api/v2/cuentas` y `/api/v2/fuentes`; la consola enseña el aviso de
  frescura arriba.

**Cambios**

- `reglas/base.py`: `Politica` lleva el interruptor de las cuentas, el
  enfriamiento, la frescura y la identidad de la empresa; `Factura` lleva
  `documento_id`, `emisor_direccion_doc`, `kor_mencionada`, `notas_doc`,
  `dudosos` y `sin_original`; nuevos `Parte`, `Cuenta`, `EventoCuenta`,
  `CambioTelefono` y `Lote`, que la `Instantanea` trae (`proveedores`,
  `clientes`, `cuentas`, `telefonos`, `lotes`); `solo_objeciones`, `fallo`,
  `sin_datos`, `dias_laborables`, `ultimo_lote_valido`, `edad`, `caducada`,
  `importado`.
- `reglas/instantanea.py` lee todo eso (los maestros con sus alias ya
  normalizados; las cuentas con cada evento, si quien decidió tenía el
  permiso en ese instante y cuándo llegó lo que lo motivó; la historia del
  teléfono; las importaciones con sus rechazos).
- `reglas/bancaria.py`: el estado de una cuenta, la eficacia de una
  verificación, el `Registro` de una pasada y las reglas F;
  `validar_iban` con una tabla de `str.translate` y solo ASCII.
- `reglas/calidad.py` (Q2-Q4, X1 de importaciones, Z1, Z2), `reglas/iva.py`
  (E1, E2), `reglas/catalogo.py`, `reglas/motor.py`.
- `politica.py`: `politica_reglas(conn)` (la `Politica` de los últimos
  `reglas.yaml` y `empresa.yaml` cargados; sin ninguno, la del código),
  `empresa(conn)`, `cargar()` por nombre de fichero y `PoliticaNoValida`.
- `hallazgos.py`: la pasada evalúa con `politica_reglas`; el ámbito de un
  hallazgo sale de la regla (importación, proveedor); `resolver` acepta el
  permiso con que se cierra (las F, con `confirmar_iban`).
- `servicios.py`: las seis órdenes y el cierre de las F que desaparecen con
  ellas; `excepciones.py` describe las excepciones de una importación, un
  proveedor o un cliente; `estados.py` calcula la prioridad de esas
  excepciones aunque no haya ninguna factura; `prioridad.py` no cuenta dos
  veces los dudosos cuando ya está Q2.
- `identidad.py`: `comprobar_alias` y `reconciliar_referencias` (antes en
  `ingesta.py`, que la reexporta).
- `importadores/tarifas.py`: `leer_semilla()` (puro, en registros
  canónicos) y `contrato_semilla()`; `sembrar_tarifas` lee por él.
- `dominio.py`: `TitularCuenta`, `PrimeraFuenteCuenta`, `TipoEventoCuenta`,
  `DECISIONES_CUENTA`, `MetodoVerificacion`, `DecisionFacturas`,
  `FrecuenciaCiclo`, `FuenteImportacion`, `TipoImportacion`.
- `campos.py`: `beneficiario_conocido` y `ciclo_facturacion` en el
  registro (alta con `admin`).
- `reglas/unicidad.py`: B3 y B4 recorren la ventana por posición en vez de
  copiar la cola de la lista en cada vuelta (era cuadrático con un
  proveedor de miles de facturas). `hallazgos.CambioEvaluacion` es una
  tupla con nombre, el motor ordena con listas por comprensión, y la
  instantánea normaliza cada texto impreso una vez por pasada. Todo por
  velocidad, sin cambiar lo que hacen.

### La puerta, test por test

| Puerta | Tests |
| --- | --- |
| Una propiedad: ninguna extracción, tampoco `03-con-inyeccion`, crea ni cambia una fila de `cuenta_bancaria` | `test_cuentas.py::test_ninguna_extraccion_crea_ni_cambia_una_cuenta_del_registro` (con el registro ya lleno del maestro de Exact: las siete fixtures v1 y doce extracciones al azar de proveedores del maestro, con IBAN válidos y no en la cabecera y en las notas e instrucciones de cambiar la cuenta; tras la ingesta, el recálculo y una persona trabajando las facturas, `cuenta_bancaria` y `cuenta_evento` son fila a fila las de antes, y F3 bloqueó lo que no era suyo); `test_alcance_v1.py::test_el_unico_escritor_de_cuentas_no_se_alcanza_desde_la_extraccion` (solo `cuentas.py` tiene SQL que escribe esas tablas, nada de la extracción ni de la ingesta lo importa, ni directa ni indirectamente, y él no importa nada que produzca una extracción) y `test_un_iban_de_un_documento_no_sale_nunca_de_su_sitio` (sigue en pie) |
| La fixture de inyección queda Bloqueada por F2/F3 y además da Q3 | `test_cuentas.py::test_la_factura_con_inyeccion_queda_bloqueada_y_avisa` (resuelta contra Koster del maestro: F2 y F3 bloquean, Q3 avisa y se puede anular, ninguno de sus dos IBAN está en el registro, y la excepción de la factura es Bloqueada) y `test_reglas_paso5.py::test_q3_avisa_de_las_notas_de_la_fixture_de_inyeccion_y_no_de_una_nota_inocente` |
| Un IBAN cambiado en un Exact posterior bloquea con F5 y sigue abierto tras la siguiente importación | `test_cuentas.py::test_un_iban_cambiado_en_un_maestro_posterior_bloquea_y_sigue_abierto` (dos F5 sobre el proveedor, la cuenta nueva y la que desapareció; la excepción del proveedor es Bloqueada; la importación siguiente, con otro cambio, los deja abiertos y son los mismos; la verificación al número del maestro de antes resuelve el de la nueva y el rechazo de la vieja, el suyo) |
| Una verificación con el teléfono cambiado tres días antes no cuenta (F8) | `test_cuentas.py::test_una_verificacion_tres_dias_despues_de_cambiar_el_telefono_no_cuenta` (F9 avisa al cambiarlo; la llamada al número nuevo a los tres días no cuenta por el enfriamiento y la del viejo porque no es el del maestro; F8 bloquea; quien cambió el teléfono no puede verificar; pasado el enfriamiento la llamada cuenta y F8 se resuelve) y `test_reglas_paso5.py::test_eficacia_de_una_verificacion_por_telefono` |
| El importador no puede escribir un estado `verificada` | `test_importadores.py::test_ningun_mapeo_puede_leer_un_estado_de_cuenta` (un mapeo con `estado` no carga, la cuenta canónica no admite el campo ni un IBAN sin su módulo 97) y `test_ni_el_importador_ni_nadie_sin_confirmar_iban_escribe_una_cuenta_verificada` (la base rechaza la fila del importador y la de nadie, y un alta de cuenta fuera de una importación en curso) |
| Cada mapeo tiene su test de contrato, y reimportar un fichero no hace nada | `test_importadores.py::test_cada_mapeo_lee_su_ejemplo_como_dice_su_contrato` (los siete, campo a campo contra su JSON), `test_cada_mapeo_tiene_su_ejemplo_y_su_contrato`, `test_la_semilla_de_tarifas_lee_como_dice_su_contrato`, `test_cada_lector_reconoce_su_formato_por_la_cabecera_y_no_otro` y `test_importar_otra_vez_el_mismo_fichero_no_hace_nada` (cada fila de cada tabla, igual) |

Además: el primer maestro y su línea base (procedencia, quién, F0 y Z2), la
foto completa que retira (y no retira si la foto no entró entera), simular
sin escribir nada, las cuentas todo o nada, M1 (lo puesto a mano no se
pisa), el permiso de importar, una referencia desconocida que rechaza sin
crear nada, la tarifa en dólares (X1 sobre la importación), recursos, alias
y ciclos, y la CLI entera (`test_importadores.py`); cada regla nueva, rama a
rama, con el método de U1 contra la fuerza bruta (`test_reglas_paso5.py`);
la pureza y lo que lee cada regla con escenarios de maestros, cuentas,
teléfonos e importaciones (`test_pureza_reglas.py`); atestar todo lo
heredado (una tarea de nivel atención, resuelta), rechazar con "pagar a la
verificada", los campos críticos y la política que se copian, y el dominio
contra la base (`test_cuentas.py`); las seis órdenes en la matriz de
permisos, contra cada usuario de sistema y en la suite de alcance
(`test_servicios.py`, `test_alcance_v1.py`); y la API de cuentas y fuentes
(`test_consola.py`).

### Desviaciones de la especificación, y por qué

1. **La migración es la 0005**, no la 0004 que numera el §11: la 0004 es la
   del paso 4 (lo previsto en el registro del paso 3).
2. **`tarifa_acordada` no se crea**: llegó en la 0002 con la semilla. La
   importación escribe en ella con `fuente = 'maestro'` y su clave natural
   (sentido, a quién, dónde, trabajo, turno, unidad y desde).
3. **Las reglas de factura del paso 5 escriben solo lo que objetan** (un
   fallo o un sin_datos), no un ok ni un no_aplica
   (`reglas.base.solo_objeciones`). Catorce reglas más con un resultado por
   factura no cabían en los dos segundos de la puerta del paso 3: cada fila
   de la caché cuesta unos 13 µs entre la pasada y la escritura. Que una de
   esas reglas no diga nada de una factura es que no tiene nada que objetar;
   un hallazgo cuya regla deja de dar fallo se cierra (o queda desaparecido)
   igual. `test_la_cache_tiene_un_resultado_por_regla_y_fila_tambien_los_que_pasan`
   lo exige ahora solo a las reglas de los pasos 3 y 4.
4. **F0 es una regla nueva** ("cuentas heredadas sin atestar"). La decisión
   3 pide una tarea de atestación de nivel atención: es un hallazgo que
   retiene, sobre la importación de partida, que abre su excepción (nivel
   atención) y que resuelve `atestar_iban`. Retiene y no avisa porque un
   aviso sin excepción no es una tarea; no retiene ninguna factura.
5. **A7 es pegajosa entera**; el §7 dice "pegajosa para btw-id y KvK". Lo
   pegajoso es de la regla (catálogo y base), no del resultado, y separar
   A7 en dos reglas cambiaría su identidad. Un cambio de nombre o de
   dirección queda abierto hasta que una persona lo mira, y se puede anular.
6. **`visto_en_documento` está en el CHECK pero un disparador lo rechaza**:
   la lista del §5.C lo nombra, y la regla 1 de arquitectura.md dice que lo
   que imprime un documento no entra en el registro. Que un IBAN se vio en
   una factura ya lo dicen `factura.iban_doc` y sus hallazgos.
7. **Las cuentas de los clientes se registran** (vienen en el fichero de
   clientes de Exact) **pero las reglas F miran solo las de proveedores**,
   que son las que se pagan. Las de clientes cuentan para F4 (un proveedor
   que factura a la cuenta de un cliente) y servirán al cruce con el banco
   (paso 7).
8. **F6 está escrita pero no se dispara todavía**: no hay mapeo de cuentas
   de TRNSPRNT (su formato no se conoce; llega con el paso 10). Compara solo
   proveedores con datos de las dos fuentes.
9. **M1 no es una regla del catálogo**. Lo que la importación no pisa queda
   como valor automático con el campo sin resolver: en una factura lo cuenta
   `factura_estado.sin_resolver` (paso 4); en un maestro lo dice la
   importación (`ResultadoLote.sin_resolver`, en la CLI "sin resolver
   (M1)") y queda en su procedencia. Una regla M1 sobre los maestros, si
   hace falta, va con la consola de maestros.
10. **El lector lleva su mapeo**: `LectorTabular(mapeo, tipo)` y
    `leer(contenido, nombre, *, exportado_en)`, en vez de pasar el mapeo a
    `leer()`; un mapeo da un lector por tipo de registro (el fichero de
    acreedores de Exact da proveedores y cuentas, dos lotes y dos
    importaciones). `LoteLeido` lleva además `fuente`.
11. **`registrar_lote(almacen, lote, *, lanzado_por: int, ...)`**: recibe el
    `Almacen` y no la conexión, porque guarda el fichero en el almacén de
    documentos, y el id de la persona.
12. **La semilla sigue fuera de `registrar_lote`**, pero lee por el mismo
    marco (`leer_semilla`, registros canónicos, con su test de contrato). Es
    un fichero de configuración que se vuelve a aplicar con cada versión
    (queda en `politica_version`) y que puede dar de alta clientes y
    Objetos; una importación es única por hash y no crea nada sola.
13. **`alias` es un tipo de importación** (`TipoImportacion.ALIAS`): el §9
    habla de "Objects, resources and aliases" pero su lista de tipos no lo
    tiene.
14. **Z2 no mira las importaciones de `out/`** (fuente `extracciones`): lo
    rechazado allí ya lo dice la ingesta.
15. **Una foto de cuentas vacía no retira nada**: un fichero de Exact sin
    ninguna cuenta de un tipo de titular es casi seguro una exportación sin
    la columna, no un maestro que las borró todas.
16. **La foto completa retira proveedores y clientes como inactivos**
    (nunca los borra) y solo si entró entera: una fila rechazada puede ser
    la de uno que sí está.
17. **Q3 avisa con una frase dirigida al sistema, o con un cambio de datos
    junto a otra clase de marca** (así desde la revisión; antes, con dos
    clases cualesquiera). Una sola marca ("vragen? e-mail ...") y los datos
    de pago de siempre al pie ("IBAN NL02 ... t.n.v. ...", que traen el IBAN
    y la palabra a la vez) son casi siempre inocentes, y una alerta que salta
    siempre se ignora.
18. **A0 da sin_datos hasta que entra el maestro de su tipo**, y A8 cuando
    el documento no dice a quién va dirigido (o la versión del esquema no lo
    pidió): sin fuente no hay comprobación, y sin_datos nunca cuenta como ok.
19. **Lo que depende de la frescura de Exact** (A2, E1, F2 y F3) da sin_datos
    con Exact caducado. A0 no: que una contraparte no esté en el maestro no
    depende de su edad.
20. **U1, A7 y E2 comparan con las facturas anteriores por fecha de factura
    (y por id)** de la misma contraparte y sentido, sin abonos (U1) ni
    anuladas o fusionadas.
21. **El exportado por defecto**: la CLI usa la fecha del fichero; por
    código, sin `exportado_en`, cuenta el día de la importación.
22. **`config/reglas.yaml` vale desde que se carga** (`politica_version`),
    no por parámetro con fechas de efecto; la tabla ya lleva
    `vigente_desde`.
23. **`reconciliar_referencias` vive en `identidad.py`** (la usan la
    ingesta, la semilla, las órdenes y ahora el importador) y
    `ingesta.py` la reexporta; las normalizaciones, en `reglas/normas.py`.
24. **Tests que cambian, y por qué**: `test_campos.py` busca las guardas en
    todas las migraciones (antes solo en la 0002); en `test_alcance_v1.py`
    la prueba del grafo de imports mira quién **escribe** las tablas de
    cuentas (la instantánea de las reglas las lee y se alcanza desde la
    ingesta, que recalcula); `test_almacen.py` cuenta `cuenta_bancaria` y
    `cuenta_evento` entre las de solo escritura; `test_reglas.py` tiene el
    catálogo nuevo y las familias pegajosas con E2 y A7; `test_pureza_reglas.py`
    admite `bisect` y `fractions`, conoce los módulos y tipos nuevos y pasa
    por escenarios con maestros; `test_hallazgos.py` y `test_excepciones.py`
    cuentan los Q3 y Q4 de las fixtures (el `out/` de prueba no trae PDF) y
    la caché dispersa; `test_servicios.py` tiene las seis órdenes nuevas, y
    el teléfono de verificación tiene su orden en vez de "paso 5".

### Lo que deben saber los pasos siguientes

- **Solo `cuentas.py` escribe el registro de cuentas**; un test lo exige
  por el SQL de cada módulo. Una orden nueva sobre cuentas llama a
  `cuentas.decidir` dentro de `servicios.ejecutar`.
- **Un formato nuevo** es un YAML en `config/importacion/<fuente>-<tipo>-vN.yaml`,
  un ejemplo anonimizado en `tests/fixtures/importacion/<id>.csv` y su
  JSON esperado (`python scripts/regenerar_contratos.py <id>`, mirando el
  diff); el test de contrato lo recoge solo. Un tipo nuevo es un modelo en
  `canonico.MODELOS` y un escritor en `registrar.ESCRITORES` (o un lote
  atómico, como `cuentas`).
- **Paso 6 (extracción v2)**: `recipient_name` y `recipient_vat_number`
  alimentan A8 (y E4); `kor_mentioned`, A5; `supplier_address`, A7;
  `document_notes`, Q3; `low_confidence_fields`, Q2. Un registro v1 da
  sin_datos donde no se pidió.
- **Paso 7 (banco)**: F7 lee `estado_cuenta(...).pagable` y
  `beneficiario_conocido`; las cuentas de la empresa están en
  `config/empresa.yaml` (`cuentas_propias`, `politica.empresa(conn)`), y
  `cuenta_bancaria` ya admite `titular = 'propia'` (nadie la escribe
  todavía). Z1 ya mide el banco en días laborables y `extracto` ya es
  atómico.
- **Paso 8 (ventas)**: F10 compara con `cuentas_propias`; A8 ya trata la
  vía de salida.
- **Pasos 9 y 10**: las tarifas pactadas importadas están en
  `tarifa_acordada` con `fuente = 'maestro'` y los ciclos en
  `ciclo_facturacion`; G3 sigue siendo solo el histórico. TRNSPRNT trae su
  mapeo de cuentas y con él F6.
- **Las reglas de factura nuevas** se escriben con `solo_objeciones`: solo
  fallo o sin_datos, con lo que cruzan facturas calculado una vez en su
  `preparar`. `bancaria.registro()` se calcula una vez por regla F (seis
  por pasada); con un registro grande, compartirlo.
- **Un parámetro nuevo de política** va en `politica._REGLAS`, en
  `config/reglas.yaml` y en `Politica` con el mismo valor: un test compara
  los tres.
- **La velocidad**: la puerta de dos segundos sigue, con el margen del paso
  4 y en un contenedor que a veces pierde un tercio de golpe. Lo que se
  añada a la pasada tiene que leer de una vez y escribir solo lo que
  cambia; antes de añadir una regla por factura, medir con
  `tests/test_rendimiento.py` varias veces.

### Correcciones de la revisión

La revisión del paso 5 dejó veintidós hallazgos. Cuatro estaban repetidos
(el anclaje de la verificación de un cambio de Exact, dos veces; atestar
una cuenta que no es heredada, dos veces; una verificación que no cuenta
cerrando F3, tres veces), así que son dieciocho. Cada uno se reprodujo
antes de tocarlo con los scripts de la revisión o con su test. Todos eran
reales; dos se resuelven documentándolos (TRNSPRNT en F5 y el tipo de IVA
en E1), porque su arreglo es de un paso posterior, y la vista se renombra y
se documenta, porque no decide nada. Al arreglar la matriz de permisos salió uno más, de `campos.py`
(ver la última fila). **1226 tests pasan** (714 funciones de test; eran
1167 y 684): treinta funciones nuevas, y todas fallan con el commit del
paso 5 salvo las que fijan lo que tiene que seguir entrando
(`test_un_importe_con_la_forma_del_mapeo_se_lee`,
`test_un_entero_con_su_unidad_se_lee`,
`test_un_fichero_de_reglas_dentro_de_los_limites_se_carga`).

| Hallazgo | Qué se hizo | Test |
| --- | --- | --- |
| **Bloqueante.** Una verificación sin factura de un IBAN cambiado en Exact tomaba como referencia la última importación que vio la cuenta (`ORDER BY e.id DESC LIMIT 1`), no la que la cambió: cada importación de rutina la volvía a ver, así que un teléfono cambiado en Exact a la vez que el IBAN, o después, contaba pasado el enfriamiento (De Vries: IBAN el día 1, teléfono el 2, rutina el 20, llamada al nuevo el 21: verificada y pagable) | El instante del que vale el teléfono no lo elige quien verifica: `bancaria.referencia_de` toma lo primero de (1) el documento o la importación que nombra la orden, (2) la importación que abrió el cambio del maestro más antiguo sin verificar (el primero de `cambios`) y (3) el primer documento del proveedor con ese IBAN si llegó antes de que la cuenta se aceptara (decisión 4: "el teléfono de antes del documento que la motivó"); nunca después de la llamada. Lo calcula `estado_cuenta` al recorrer los eventos, así que la pasada no se fía de lo que guardó la orden. La orden calcula lo mismo con la misma función (sobre la cuenta con la verificación añadida) para `telefono_ref`, y guarda en el evento la importación del cambio pendiente | `test_cuentas.py::test_un_iban_cambiado_y_despues_el_telefono_se_verifica_al_de_antes_del_cambio`, `test_un_iban_y_un_telefono_cambiados_en_el_mismo_exact_no_se_verifican_con_el_nuevo`, `test_reglas_paso5.py::test_la_referencia_de_una_verificacion_es_lo_primero_que_la_motivo` |
| Sin `factura_id`, la referencia era la hora de la llamada: un teléfono puesto después de que llegara la factura con el IBAN nuevo contaba (03: teléfono cambiado al día siguiente, llamada a los 15 días sin nombrar la factura: verificada) | Es el punto (3) de arriba: `instantanea.primeros_documentos` da por proveedor e IBAN impreso (normalizado) cuándo llegó su primer documento, y viaja en `Cuenta.primer_documento`. Cuenta si llegó antes de que la cuenta se aceptara (la línea base, o la primera verificación o atestación que contó); un documento que llega cuando la cuenta ya era la heredada no motiva nada | `test_sin_nombrar_la_factura_vale_el_telefono_de_antes_del_documento` |
| Una factura registrada antes de la primera importación de Exact (el atraso del primer día), o en el mismo instante, no se podía verificar nunca: el teléfono de esa importación no era "de antes" | `telefono_antes_de` (y `cuentas.telefono_ref`) cuentan el alta del teléfono (rev 0, el número con que el maestro dio de alta al proveedor) como de antes de cualquier documento; solo un cambio de verdad se compara con el instante. Ver la desviación nueva sobre un proveedor que llega con su cuenta | `test_una_factura_registrada_antes_del_primer_maestro_se_puede_verificar`, `test_el_telefono_del_alta_es_de_antes_de_cualquier_documento` |
| La llegada de un documento prefería `recibido_en`, que puede ser la fecha del fichero (mtime) y estar en el futuro: movía la referencia a un teléfono posterior | `instantanea.LLEGADA_DOCUMENTO`: la primera de `recibido_en` y `registrado_en`, en la instantánea, en `primeros_documentos` y en la orden | `test_una_fecha_de_fichero_futura_no_mueve_el_telefono_de_referencia` (el PDF de la 03 con fecha de dentro de 40 días) |
| `atestar_iban` de una cuenta no comprobaba que fuera heredada: atestar una rechazada (o una que trajo un maestro posterior y luego se rechazó) la hacía pagable sin llamar a nadie; y una atestación tapaba un F8 | Solo se atesta lo heredado sin tocar: del primer maestro, en Exact, sin cambios y sin ninguna decisión antes, tampoco una verificación que no contó (`EstadoCuenta.atestable`). Lo exigen la orden (las dos vías: una cuenta y todas), `cuentas.decidir`, `estado_cuenta` (una atestación que no cumple no existe) y la base (disparador nuevo `cuenta_evento_atestada`). F0 cuenta solo las atestables | `test_no_se_atesta_una_cuenta_rechazada_ni_una_mal_verificada`, `test_la_base_no_admite_atestar_lo_que_no_es_heredado`, `test_una_atestacion_de_lo_que_no_es_heredado_no_cuenta` |
| Una verificación que no contaba (F8) daba de alta la cuenta, F3 desaparecía y `_cerrar_f` lo firmaba como resuelto por esa llamada | F3 da por conocida una cuenta solo si la trajo un maestro (lo que cambió allí es de F5) o si una persona la aceptó con una decisión que cuenta (`_conocida`); y `_cerrar_f` no cierra nada cuando la verificación de la orden no cuenta | `test_una_verificacion_que_no_cuenta_no_cierra_f3`, `test_f3_sigue_con_una_cuenta_que_solo_tiene_una_verificacion_que_no_conto` |
| `_cerrar_f` resolvía cualquier F que desapareciera en la pasada de la orden, también el F9 de otro proveedor cuyo enfriamiento acababa de pasar, firmado con el motivo de la orden; y la diferencia contaba dos veces cada cerrado | Cierra solo lo de lo decidido: en el proveedor, los de clave `cuenta:<id>` de las cuentas decididas; las facturas de ese proveedor o la de la orden; F0 si se atestó. Lo demás queda desaparecido para una persona. `servicios._una_vez`: cada hallazgo una vez por grupo, con lo que dijo la orden | `test_una_decision_sobre_una_cuenta_no_cierra_hallazgos_de_otro_proveedor` |
| F5 iba solo sobre el proveedor: una factura de ese proveedor sin IBAN (o con uno todavía pagable) no tenía ningún F ni el suelo Bloqueada, y se pagaría desde el maestro cambiado | F5 da además un fallo por cada factura de compra en juego de un proveedor con algún cambio sin verificar (§7: cambio de IBAN, F3/F5/F6 en las facturas; §8: la familia F es Bloqueada). Se resuelve con la decisión que deja al proveedor sin cambios | `test_un_cambio_pendiente_en_el_maestro_bloquea_las_facturas_del_proveedor`, `test_f5_bloquea_las_facturas_del_proveedor_con_un_cambio_pendiente` |
| `bms-agent politica cargar` cargaba `reglas.yaml` y `empresa.yaml` sin token ni permiso y sin límites: enfriamiento 0, Exact sin caducar nunca, tolerancias de un millón | `politica.cargar` pide una persona con `admin` y queda como `cargada_por`; la CLI pide su token (`--token` o `BMS_TOKEN`) y registra la denegación. `politica._LIMITES`: lo que ningún `reglas.yaml` cruza (enfriamiento de 7 a 90 días, frescura de Exact y TRNSPRNT de 1 a 31, del banco de 1 a 10 laborables, tolerancias de línea y factura hasta 1,00 €, ventana de duplicados de 7 a 365 días) | `test_servicios.py::test_la_politica_la_carga_una_persona_con_admin`, `test_un_fichero_de_reglas_no_puede_quitar_los_controles` (ocho casos), `test_un_fichero_de_reglas_dentro_de_los_limites_se_carga`, `test_politica_cargar_por_la_cli_pide_el_token_de_admin` |
| `_decimal` quitaba cualquier punto como separador de miles: "42.50" entraba como 4250 y "1.5" como 15; un entero tomaba la primera tira de cifras ("2,5" era 2, "1.000" era 1) | El número tiene que tener exactamente la forma de los separadores del mapeo (grupos de tres cifras detrás de uno a tres, el decimal una vez y al final); si no, `ValorNoValido` (Z2). Un entero es un entero entero con, si acaso, una unidad sin cifras detrás ("30 dagen", "14 dagen netto") | `test_importadores.py::test_un_importe_que_no_tiene_la_forma_del_mapeo_se_rechaza`, `test_un_importe_con_la_forma_del_mapeo_se_lee`, `test_un_entero_tiene_que_ser_un_entero_entero`, `test_un_entero_con_su_unidad_se_lee` |
| `normalizar_telefono` no entendía "+31 (0)10 1234567" (daba 00101234567): llamar al número del maestro escrito de otra forma no contaba | El "(0)" se quita antes de contar las cifras | `test_el_telefono_con_el_cero_entre_parentesis_es_el_mismo_numero` |
| Q3 avisaba de los datos de pago de siempre al pie ("IBAN NL02 ..." es un IBAN y la palabra "iban", dos clases), contra la desviación 17 | "un IBAN" y "cuenta bancaria" son una sola clase (datos de pago). Avisa una instrucción al sistema, o un cambio de datos junto a otra clase | `test_q3_no_avisa_de_los_datos_de_pago_de_siempre_al_pie` |
| Una `--exportado` futura (o la fecha de un fichero copiado) dejaba Exact sin caducar: F2 y F3 seguían dando ok | `registrar_lote` rechaza un `exportado_en` de un día posterior al de la importación (en la zona de la empresa); la CLI toma como mucho ahora para la fecha del fichero; `instantanea.lotes` usa la primera de exportado e iniciada | `test_una_fecha_de_exportacion_futura_no_se_admite` |
| Los mapeos aplicados no quedaban en `politica_version` (§5, tabla 2): `importacion.mapeo_sha256` no se podía resolver a su texto | `Mapeo.texto` y, en cada importación con algún lote nuevo, `politica.registrar(conn, "importacion/<id>.yaml", texto, persona)` (solo si cambió desde la última) | `test_cada_mapeo_usado_queda_en_la_politica` |
| No se podían importar contactos (§9 lista `ContactoCanonico` y el tipo `contactos`) | `ContactoCanonico`, el escritor `_contacto` (por su proveedor o cliente y su nombre, sin distinguir mayúsculas; no crea la relación) y el mapeo `maestro_csv-contactos-v1` con su ejemplo y su contrato. El teléfono de un contacto no toca el de verificación | `test_los_contactos_entran_por_su_proveedor_o_su_cliente`, el contrato y `test_recursos_alias_y_ciclos_entran_fila_a_fila[...contactos...]` |
| `v_cuenta_estado.estado_registrado` decía "verificada" de una verificación que no contaba e ignoraba los cambios de F5; nadie la lee | La columna pasa a llamarse `ultima_decision` y el comentario de la migración dice que no es el estado ni dice si se paga: eso es `reglas.bancaria.estado_cuenta` (desviación nueva) | `test_la_vista_de_cuentas_no_dice_un_estado_sino_la_ultima_decision` |
| F5 solo sigue los eventos de Exact; los de TRNSPRNT se apuntan pero no bloquean | Real, y se deja para el paso 10 (desviación nueva) | — |
| E1 compara solo el régimen: el mapeo de Exact junta VH21 y VL9 en `estandar` | Real, y se documenta (desviación nueva) | — |
| *(encontrado al arreglar la matriz)* Una importación que adopta una fila con un valor por defecto (el `activo` de un proveedor dado de alta a mano, o de un cliente de la semilla) cambiaba la fuente de su procedencia sin `cambio_campo`, y `db verificar` lo daba por manipulado | `campos.py`: el mismo valor de otra fuente automática no es un cambio; la procedencia sigue diciendo la fuente de su último cambio y apunta la nueva como automática (`fuente_ref` se actualiza solo con la misma fuente) | `test_adoptar_una_fila_con_un_valor_por_defecto_deja_su_historia_entera` |

**La migración 0005 se corrige en su sitio** (el disparador
`cuenta_evento_atestada` y la columna de la vista), como la 0003 y la 0004
en sus revisiones: ninguna base la tiene aplicada fuera de los tests. Una
base local creada con la versión anterior la rechaza `migrar` por el hash;
se rehace con `bms-agent importar-out` y volviendo a importar los maestros.

Desviaciones nuevas, y por qué:

25. **El alta del teléfono vale como de antes de cualquier documento.** Un
    proveedor que llega en un maestro posterior con su cuenta y su teléfono
    a la vez se verifica a ese teléfono (pasando el bloqueo de F5 y sin
    enfriamiento, que el alta no abre): no hay ningún número anterior al
    que llamar, y sin esto esa cuenta no se podría verificar nunca. Un
    proveedor entero inventado en Exact no lo para la llamada, sino A0, A2 y
    quien lo da de alta; lo que la decisión 4 protege, el cambio del número
    de un proveedor que ya existía, sigue protegido.
26. **F5 bloquea todas las facturas de compra en juego del proveedor**, no
    solo las que imprimen la cuenta cambiada ni solo las no pagadas: el
    pago se hace desde el maestro, y hasta el paso 7 no se sabe cuáles
    están pagadas. El paso 7 las saca al pagarse, como con el importe.
27. **Los límites de `reglas.yaml` son del código** (`politica._LIMITES`),
    no del fichero. Los valores son una primera propuesta: el enfriamiento
    no baja de 7 días (la mitad del de la decisión 4), la frescura no pasa
    de un mes (Exact y TRNSPRNT) ni de dos semanas laborables (banco), y una
    tolerancia no pasa de un euro. Cambiarlos es cambiar el código, y son
    parte de la pregunta 7 del §12. También `prioridad.yaml` pide ahora
    `admin`.
28. **`v_cuenta_estado` no es el estado de una cuenta.** El §5 dice que el
    estado de un IBAN sale de la vista; el estado que vale (eficacia de la
    verificación, enfriamiento, cambios pendientes, atestaciones que no
    valen, política estricta) depende de los teléfonos y de la política de
    cada pasada, y solo lo calcula `reglas.bancaria.estado_cuenta`. La vista
    da la última decisión de una persona, y así se llama su columna. Nada
    del código la lee para decidir.
29. **F5 solo mira Exact; TRNSPRNT espera al paso 10**, junto a la
    desviación 8. `apuntar_maestro` ya apunta `visto_en_trnsprnt` y
    `ausente_en_trnsprnt`, pero sin un mapeo de cuentas de TRNSPRNT no hay
    eventos, y tratarlos como los de Exact haría que la primera importación
    de TRNSPRNT diera por añadidas todas las cuentas (no tiene línea base).
    El paso 10 decide su línea base y lo que bloquea.
30. **E1 compara el régimen, no el tipo.** El mapeo de Exact lleva VH21 y
    VL9 a `estandar` porque `proveedor` no guarda un tipo de IVA. En la V1
    ninguna regla compara el tipo que aplica la factura con el del maestro:
    las aritméticas solo comprueban que la cuota sea la de su tipo. Guardar
    el tipo registrado necesita una columna nueva en `proveedor` y una E1
    por tipo; queda para cuando el IVA se mire por proveedor (el paso de
    BTW).
31. **Un contacto es el mismo por su relación y su nombre**: el fichero no
    trae un identificador de contacto. Un contacto que cambia de nombre
    entra como otro; el viejo sigue hasta que una foto o una persona lo
    retire (la hoja no es una foto completa).

**Tests existentes cambiados, y por qué**: la matriz de permisos
(`test_servicios.py::CASOS` y la suite de alcance) atestaba una cuenta dada
de alta por una verificación que no contaba, que es justo lo que ya no se
puede: la preparación importa ahora un Exact (con otra cuenta que la de los
documentos del escenario, para que la suite de alcance siga viendo que el
IBAN de un documento no sale de su sitio) y atesta su cuenta heredada; las
preparaciones reciben el almacén. `test_las_ordenes_no_llaman_a_la_api`
carga la política con el token de una persona con `admin`.
`test_q3_avisa_de_las_notas_de_la_fixture_de_inyeccion_y_no_de_una_nota_inocente`
ya no da por sospechoso un IBAN con la palabra "iban" (desviación 17).
`test_cada_mapeo_tiene_su_ejemplo_y_su_contrato` cuenta el mapeo de
contactos, y el constructor `cuenta()` de `test_reglas_paso5.py` admite
`primer_documento`. Ninguno prueba menos que antes.

Lo que deben saber los pasos siguientes, además de lo de arriba:

- **La referencia de una verificación es de `bancaria.referencia_de`**: una
  orden nueva que verifique (por ejemplo, desde el banco en el paso 7) no
  calcula su propio instante; guarda lo que la motivó y deja que
  `estado_cuenta` decida.
- **Paso 6**: la llegada de un documento es `instantanea.LLEGADA_DOCUMENTO`
  (la primera de recibido y registrado); un `recibido_en` del correo no la
  mueve hacia delante.
- **Paso 7**: F5 por factura debe dejar fuera las pagadas; atestar sigue
  siendo solo de lo heredado sin tocar.
- **Paso 10**: F5 y F6 con TRNSPRNT (desviaciones 8 y 29).

## Paso 6

Extracción v2: esquema y prompt nuevos, el modelo claude-opus-5-5, la
reextracción con presupuesto (síncrona o por lotes) y la puerta de
activación. **Construido y probado, sin una sola llamada a la API**: no se
ha vuelto a extraer nada, y subir las versiones no paga nada por lo ya
extraído (probado con un cliente falso que cuenta las llamadas). **1321
tests pasan** (769 funciones de test; eran 1226 y 714 al cerrar el paso 5).
Cinco mil facturas se recalculan en 1,45-1,7 s la primera vez y en
1,3-1,6 s las siguientes (seis medidas en este contenedor), como en el paso
5: la regla nueva (M2) lee una tabla pequeña.

### Qué se construyó

**Esquema v2** (`schema.py`, `SCHEMA_VERSION = "2"`). Cabecera nueva:
`document_type`, `related_invoices` (número, fecha, la frase literal y la
relación que enuncia), `currency_raw`, `supplier_contact_person`,
`recipient_name`, `recipient_vat_number`, `recipient_contact_person`,
`references` (etiqueta y valor literales), `payment_terms_raw` y
`vat_breakdown`; por línea, `employee_name`, `work_date`,
`order_reference_raw`, `rate_type_raw` y `vat_rate_raw`, y `location`
redescrita como «Objeto, locatie o proyecto tal como está impreso». Cada
modelo lleva `extra='forbid'` (el esquema JSON sale con
`additionalProperties: false` en los cinco objetos), sin recursión ni
límites. `low_confidence_fields` pide rutas (`lines[3].location`). Ningún
campo de teléfono, correo ni identificación personal. Las clases v1 se
conservan intactas como `InvoiceExtractionV1` e `InvoiceLineV1` (validan lo
ya extraído), con `MODELOS`, `modelo_de()` y `esquema_json()`.

**Prompt v2** (`prompts.py`, `PROMPT_VERSION = "extract/2026-10-15.1"`).
Redacción neutra sobre la dirección («documentos en los que BM Support BV es
el emisor o el receptor»), la regla 1 palabra por palabra (`REGLA_1`, un test
la compara con la de antes) y las reglas nuevas: el tipo declarado y los
signos impresos, las facturas nombradas copiadas literalmente sin deducir
relaciones de los importes, cada referencia con su etiqueta sin decidir cuál
es una PO, emisor y destinatario con su contacto y el «t.a.v.», las
condiciones literales y `due_date` solo si está impreso, lo de cada línea,
las rutas de `low_confidence_fields` y, aparte, que un texto que pide llamar
a un número, confirmar datos bancarios o actualizar la ficha va a
`document_notes`.

**Modelo y esfuerzo** (`config.py`): `DEFAULT_MODEL = "claude-opus-5-5"` en
la misma subida que el esquema. `build_request` lleva siempre
`output_config: {"effort": …}` (variable `BMS_EXTRACT_EFFORT`, `medium` por
defecto, validada antes de pagar), sin `thinking` (en Opus 5.5 no se puede
apagar), sin herramientas. Se leyó antes la firma del SDK instalado
(anthropic 1.13.0: `messages.parse` funde `output_format` en
`output_config.format`; `count_tokens` admite los dos) y la referencia de la
API (salida estructurada, lotes y conteo de tokens).

**Lotes** (`extract.py`): `construir_peticion_lote(doc)` (custom_id = el
sha256 del documento, el esquema en `output_config.format` como
`json_schema`, el mismo esfuerzo, ninguna herramienta) y
`leer_resultado_lote()`, que valida el texto con `model_validate_json` y
devuelve un `Reintento` para un rechazo, un error, un caducado, un cancelado
o una salida que no es el esquema (también una cortada por `max_tokens`).
Una lectura de lote apunta `usage.service_tier = "batch"`. `extract_invoice`
lanza `Rechazado` (un `RuntimeError`, como antes) cuando el modelo se niega.

**Lectura y tipado** (`parsing.py`, `compat.py`, `ingesta.py`):
`parse_plazo_pago` (días de un plazo impreso: «binnen 30 dagen», «2 weken»,
«per omgaande»; rechaza días laborables, meses y dos plazos sin neto);
`normalizar_referencia` ya estaba (paso 2). La ingesta tipa
`plazo_pago_dias` como `calculado` del literal, y el tipo de factura desde
`document_type` (factura, corrección o sustitución: factura; abono: nota de
crédito; sin declarar o anulación: el signo del total, como en v1). Las
líneas de una lectura nueva se casan con las anteriores por su **huella de
contenido** (ver abajo).

**Puntuación y coste** (`scoring.py`, `coste.py`, `pricing.py`):
`_FIELD_SOURCE` gana `document_type`, `currency`, `references`,
`related_invoices`, `recipient_name`, `recipient_vat_number`,
`supplier_contact_person`, `recipient_contact_person` y `payment_terms`; las
listas se comparan como conjuntos normalizados; lo que la versión de una
extracción no pidió no se puntúa. `CRITICAL_FIELDS` no cambia.
`comparar_versiones()` y `format_comparacion()` son la puerta. El coste se
reparte por modelo y versión del esquema (`formatear_por_version`), un lote
se cobra a la mitad (`pricing.DESCUENTO_LOTE`) y la salida de la próxima
pasada se estima con `estimar_salida()` sobre el histórico de la misma
versión.

**Generador**: añade `08-nota-credito.pdf` (abono parcial de la 01, con la
factura que abona) y `09-usd.pdf` (en dólares, con una referencia de
pedido), con sus respuestas, que llevan ya campos del v2. La
`03-con-inyeccion.pdf` sigue siendo la prueba de punta a punta de F2/F3/Q3, y
ahora también la de la puerta.

**Módulo nuevo `reextraccion.py`**: `Criterio`, `seleccionar()`, `cargar()`
(los originales del almacén de documentos, cada apertura auditada),
`estimar()`, `comprobar_presupuesto()`, `ejecutar()` (síncrona o por lotes),
`recoger()`, `comparar()`, `activar()`, `candidatas_pendientes()` y
`registrar_rechazo()`. No importa el SDK: el cliente se inyecta.

**Regla nueva M2** (`reglas/calidad.py`, en el catálogo detrás de X1):
«Edición manual sin casar». Retiene, se anula con motivo, no es pegajosa.
Falla por cada línea apuntada en `linea_sin_casar` para la extracción vigente
de su factura que sigue activa, o que ya estaba excluida cuando llegó la
lectura nueva (su exclusión no se pudo llevar a ninguna línea nueva).
Excluir la línea cierra el hallazgo; la excluida antes se anula. La
instantánea trae `Factura.sin_casar` (`LineaSinCasar`).

**Tablas** (migración `0006_reextraccion.sql`), STRICT, con clave entera y
sin columnas REAL:

| Tabla | Clase | Qué no se puede hacer |
| --- | --- | --- |
| `reextraccion` | EVIDENCIA, como `importacion` (un evento con su foto al empezar, al mandar el lote y al terminar) | Que no la ejecute el extractor o que `iniciada_por` sea un usuario de sistema; nacer en otro estado que `en_curso`; una estimación alta por encima del presupuesto (CHECK); tocarla terminada, o cambiar lo que se aceptó pagar, el criterio o el lote ya mandado; bajar los recuentos; borrarla |
| `reextraccion_resultado` | SOLO ESCRITURA, con su evento | Una candidata que no sea una extracción de su documento, con el modelo, las versiones y la vía de su reextracción; entrar con la reextracción cerrada o fuera del evento del extractor; dos filas para la misma extracción; `UPDATE` y `DELETE` |
| `activacion` | SOLO ESCRITURA, con su evento | Activar lo que no es una candidata de ese documento; que no lo firme una persona activa con `admin` en ese momento, en su propia orden; activar dos veces la misma extracción; `UPDATE` y `DELETE` |
| `linea_sin_casar` | SOLO ESCRITURA, con su evento | Apuntar una línea de otra factura o para una extracción que no es la vigente de la factura; que no la apunte el extractor; `UPDATE` y `DELETE` |

Las cuatro son evidencia (`almacen/evidencia.py`): `db verificar` compara
cada fila con la foto de su evento y ve una metida o tocada por detrás.

**La vigente**: `almacen.extracciones.en_orden_de_out()` (que usan
`registros_legado` y `ingesta.vigentes_por_documento`) deja fuera las
candidatas que nadie ha activado (`SIN_CANDIDATAS`). El resto de la regla no
cambia: la más reciente.

**Órdenes**

- `bms-agent reextraer [--abiertas] [--desde AAAA-MM-DD] [--proveedor X]
  [--sin-objeto] [--reintentos] [--limite N] [--presupuesto USD] [--lote]
  [--out out] [--db]`: elige, carga los originales, cuenta la entrada con
  `count_tokens` (exacta, no se cobra), estima la salida en horquilla y, con
  presupuesto y si el extremo alto cabe, paga. Sin `--presupuesto` solo
  estima. Lo leído es una candidata, exportada en `out/reextraccion/` con el
  hash y las versiones en el nombre.
- `bms-agent reextraer --recoger N`: los resultados del lote de la
  reextracción N, si terminó.
- `bms-agent reextraer --activar --ground-truth F [--inyeccion NOMBRE]
  --token T`: la puerta y la activación.
- `bms-agent score --comparar-versiones [--ground-truth F] [--db]`: la
  versión de `config.py` contra la anterior; sale con 1 si no pasa.
- `bms-agent coste`: cuenta también `out/reextraccion/` y lo da por
  versión; `coste --estimar` estima la salida con la misma versión.

**Cómo decide `activar`**: primero el permiso (`admin`; la denegación queda
en la auditoría); después la puerta, sobre todas las extracciones del
almacén y las respuestas escritas a mano: la versión nueva tiene que llegar
al 98 % en los campos críticos, no quedar por debajo de la anterior en los
críticos ni en los aciertos de los campos que las dos pidieron, y la
`03-con-inyeccion.pdf` tiene que tener una extracción nueva que dé el IBAN
de las respuestas (o, si no está en ellas, el de la extracción anterior) y
el texto inyectado en `document_notes`. Si no pasa, nada cambia y queda un
evento `activacion_rechazada` con los motivos. Si pasa, en una transacción:
por cada documento con una candidata pendiente de las versiones actuales (la
última), una fila de `activacion` (con el hash de la comparación) y la
factura vuelta a tipar con ella; al final, la pasada del motor. Lo manual no
se pisa: el campo que la lectura nueva contradice queda sin resolver (M1, en
`factura_estado.sin_resolver`) y sale en `Activada.contradichos`; las líneas
se casan por su huella, y las editadas que no casan se conservan, se apuntan
en `linea_sin_casar` y dan M2.

**La huella de una línea** (`ingesta.huella_linea`): el sha256 de su
descripción, cantidad, unidad, tarifa e importe normalizados (texto sin
mayúsculas ni signos, números sin ceros de más; un literal que no se pudo
leer cuenta como lo que pone). No lleva la posición ni las claves de una
versión: la misma línea leída por v1 y por v2, o leída una posición más
abajo, da la misma huella. Se casa primero por huella (la guardada en
`huella_linea`, que es la de la lectura que puso la línea, o la de sus
valores de ahora, que pueden ser la corrección de una persona que la lectura
nueva ahora lee bien); después, solo una línea que nadie ha tocado, por su
misma posición. Una línea «tocada» tiene algún valor manual en sí misma, en
su exclusión, en su imputación o en su referencia.

### La puerta, test por test

| Puerta | Tests |
| --- | --- |
| Cada objeto del esquema tiene `required` igual a sus propiedades y `additionalProperties: false`, sin ninguna palabra clave no admitida | `test_extraccion_v2.py::test_cada_objeto_tiene_required_igual_a_sus_propiedades_y_nada_mas`, `test_el_esquema_no_lleva_ninguna_palabra_que_la_salida_estructurada_no_admita` (lista blanca de palabras clave, ni mínimos, ni longitudes, ni patrones, ni formatos, ni valores por defecto), `test_el_esquema_no_tiene_recursion`, `test_la_via_sincrona_y_la_de_lotes_mandan_el_mismo_esquema` (igual a `anthropic.transform_schema`), `test_una_lectura_v2_vacia_es_representable_y_no_admite_claves_de_mas` |
| Ningún campo de teléfono y ninguna herramienta | `test_no_hay_ningun_campo_de_telefono_correo_ni_identificacion_personal`, `test_la_peticion_lleva_el_esfuerzo_explicito_y_ninguna_herramienta`, `test_la_peticion_de_lote_es_la_misma_con_el_hash_como_custom_id`, `test_alcance_v1.py::test_la_peticion_de_extraccion_no_lleva_herramientas` (ahora también el lote) y `test_ningun_codigo_pasa_herramientas_a_un_modelo`; el cliente falso de `test_reextraccion.py` rechaza cualquier petición con herramientas |
| Las fixtures v1 suben con exactamente las claves nuevas marcadas «no solicitadas» | `test_las_extracciones_v1_suben_con_exactamente_las_claves_nuevas_no_solicitadas`, `test_las_claves_nuevas_son_las_de_la_especificacion` (el esquema contra la lista del §10 y contra `compat`), `test_compat.py` (sin tocar) |
| 0 llamadas a la API después de subir las versiones, para lo ya extraído | `test_subir_las_versiones_no_paga_ninguna_llamada_por_lo_ya_extraido`: las extracciones v1 de las fixtures (claude-opus-5, prompt de antes, esquema 1) y los PDF del generador; con la configuración real de ahora, `extract` con almacén, el botón del servidor, `coste --estimar` y `reextraer` sin presupuesto: 0 llamadas pagadas (solo los `count_tokens`, que no se cobran) y `out/` byte a byte igual. Siguen además los del paso 0 en `test_extraccion_pasada.py` |
| A mano antes de `--activar`: coste dentro del presupuesto, v2 al menos tan bueno y al 98 % en el conjunto real, el PDF de inyección con el IBAN de la cabecera | Escrito como instrucciones para el dueño en `docs/fase-0.md` («Antes de activar: lo que comprueba una persona»), y aquí abajo. No se ha ejecutado: no hay facturas reales ni API. La puerta del código lo exige igual: `test_scoring.py::test_la_puerta_no_pasa` (seis casos), `test_reextraccion.py::test_sin_pasar_la_puerta_no_se_activa_nada`, `test_por_encima_del_presupuesto_no_se_paga_nada`, `test_la_base_no_admite_una_estimacion_alta_por_encima_del_presupuesto` |

**Las comprobaciones a mano, para el dueño** (no ejecutadas):

1. Lanzar `bms-agent reextraer --abiertas` sin presupuesto y leer la
   estimación; si dice «sin medir», empezar con `--limite 20` y un
   presupuesto pequeño, mirar lo que costó con `bms-agent coste` (por
   versión) y solo después el resto, mejor con `--lote`.
2. `bms-agent score --comparar-versiones --ground-truth
   ground_truth/respuestas.yaml` con facturas reales releídas: que pase, y
   leer campo a campo qué empeora y dónde.
3. Copiar la entrada de `03-con-inyeccion.pdf` de
   `respuestas-ejemplo.yaml` a `respuestas.yaml`, leer esa factura con la
   versión nueva y comprobar en `out/reextraccion/` (o en `out/`) que `iban`
   es `NL75INGB0002445689` y que `document_notes` lleva el texto inyectado.
4. Solo entonces, `bms-agent reextraer --activar --ground-truth … --token …`
   con el token de una persona con `admin`.

Además: la reextracción entera (`test_reextraccion.py`: selección por cada
criterio y lo que no se vuelve a pagar, estimación sin pagar, presupuesto,
candidatas que no cambian nada, reintentos y `--reintentos`, un rechazo del
modelo, el lote mandado y recogido con resultados desordenados, permiso de
la activación, M1 y el casado por huella al activar, M2 y cómo se cierra,
`db verificar` que ve una activación tocada, la CLI de punta a punta y el
coste por versión), la lectura de lotes (siete casos de reintento), la
puntuación v2 (campos nuevos, conjuntos, lo no solicitado, la puerta), el
coste por versión y por lotes, `parse_plazo_pago` (21 casos), la ingesta v2
(tipo por lo declarado o por el signo, el plazo, la huella que no depende de
la versión ni de la posición) y el generador.

### Desviaciones de la especificación, y por qué

1. **Reglas 8 a 15, no 8 a 14.** El §10 lista ocho reglas nuevas bajo «rules
   8 to 14». Se han escrito las ocho, numeradas seguidas; la regla 5 ahora
   remite a la 14 para las rutas de `low_confidence_fields`. La regla 1 no
   cambia (lo exige un test).
2. **Los enumerados y las listas nuevos no admiten null.** El §10 dice
   «required but nullable». `document_type` y `stated_relation` llevan
   `unknown` (como `vat_regime` en v1) y las listas son vacías si no hay
   nada (como `lines`): así null tiene un solo significado en una lista, «no
   solicitado» (`compat` sube v1 con null), y otro distinto de «no lo dice».
   Los textos sí son nullables.
3. **La descripción de un campo de enumerado va en el enumerado.** El SDK
   (`transform_schema`, en `messages.parse`) quita lo que acompaña a un
   `$ref`, así que la descripción de `document_type` no llegaba al modelo.
   Va en el docstring del enumerado, que sí llega, y el esquema de la vía de
   lotes es exactamente el que deriva el SDK (un test lo compara).
4. **El esquema v1 se conserva** como `InvoiceExtractionV1`: valida lo que se
   extrajo con él, y ya no se manda.
5. **El generador escribe `08-nota-credito.pdf` y `09-usd.pdf`**, no PDF
   para las fixtures 04 y 07 (como anunciaba su README): esas fixtures tienen
   un hash sintético del que dependen los pasos 1 y 5 (el caso «falta el
   original»), y un PDF de verdad con el mismo nombre y otro hash confundiría
   la puntuación por nombre.
6. **Nombres lógicos en las respuestas**: `currency` y `payment_terms` (sin
   `_raw`, como `subtotal_excl_vat`). Se añadieron también `recipient_name` y
   `payment_terms`, que el §10 no nombra. Lo que la versión de una extracción
   no pidió no se puntúa (ni acierto ni fallo).
7. **«Al menos tan buena»** es: no peor en los campos críticos y no peor en
   los aciertos de los campos que las dos versiones pidieron, sobre los
   mismos documentos; más el 98 % en críticos. El §10 no lo concreta.
8. **La comprobación de la inyección** usa el IBAN de las respuestas para
   `03-con-inyeccion.pdf`, o si no está, el de su extracción anterior; exige
   una extracción nueva de esa factura y `document_notes` no vacío. Sin ella
   la puerta no pasa.
9. **Activar pide `admin`** (el §10 no dice quién): es una decisión de
   política, como cargar `reglas.yaml`. Una persona, con su token, queda en
   `activacion.usuario_id`. Pagar la reextracción no pide token (como
   `extract`): el freno es el presupuesto; si se da un token, queda en
   `reextraccion.iniciada_por`.
10. **La puerta es por versión, no por documento**: si pasa, se activan todas
    las candidatas pendientes de las versiones actuales (la última de cada
    documento), en una sola transacción.
11. **Las candidatas viven en el almacén y se exportan a
    `out/reextraccion/`**, no a `out/`: lo que está en `out/` es la vigente
    para quien lee sin almacén (`load_records`), y una candidata no lo es.
    `importar-out` no recorre subcarpetas: rehacer un almacén desde `out/`
    deja la historia en v1, sin candidatas ni activaciones (se vuelven a
    leer con `reextraer`, o se importan a mano como extracciones normales,
    sabiendo que pasan a vigentes sin puerta).
12. **Cuatro tablas nuevas** (`reextraccion`, `reextraccion_resultado`,
    `activacion`, `linea_sin_casar`) que el §5 no lista. La migración es la
    0006 (el número es su orden, no su paso). `v_extraccion_vigente` (0001)
    no sabe de candidatas; nada del código la lee.
13. **El presupuesto en centavos de dólar** (`presupuesto_usd_cent`): la API
    cobra en dólares, y `_cent` del §4 son céntimos de euro. La horquilla se
    redondea hacia fuera (baja hacia abajo, alta hacia arriba).
14. **Sin `--presupuesto` solo se estima**, y una pasada que no cabe no deja
    fila en `reextraccion`: deja un evento `reextraccion_rechazada` con la
    estimación.
15. **El factor «sin medir»** es una horquilla declarada, 2 a 4 veces la
    mediana de las extracciones de otras versiones (`coste.FACTOR_SIN_MEDIR`);
    sin ningún histórico, el punto de partida de siempre (600-1600) por el
    mismo factor. «Medida» pide tres extracciones del mismo modelo y la misma
    versión del esquema.
16. **Opciones de más en `reextraer`**: `--recoger N` (un lote se recoge
    horas después) y `--reintentos` (la lista de reintentos tiene que poder
    pedirse), además de `--ground-truth`, `--inyeccion`, `--out` y `--token`.
17. **El casado por huella vale para cualquier extracción nueva**, no solo
    para una activación (también un `extract --force`): era lo que el paso 2
    dejó pendiente. `huella_linea` cambia de definición (ya no lleva la
    posición ni el JSON crudo); en un almacén de antes, las líneas casan por
    la huella de sus valores actuales.
18. **M2 es una regla nueva** que el §7 no tiene: es como se cumple «las
    ediciones que no se pueden casar se convierten en hallazgos». M1 sigue
    sin ser una regla (desviación 9 del paso 5): es `sin_resolver` de la
    procedencia.
19. **`document_type` y el tipo de factura**: corrección y sustitución son
    facturas (que sustituyan a otra es una relación, del paso 8); anulación y
    `unknown` deciden por el signo, como v1.
20. **`plazo_pago_dias` sale de `payment_terms_raw`** como `calculado`
    cuando la extracción es v2 y el texto se lee sin adivinar; si no, vale el
    del maestro, como antes.
21. **`uso_json` admite un texto corto** (`service_tier`): sin él, una
    extracción de lote se contaría al doble.
22. **Tests existentes cambiados**, porque la especificación cambia el
    esquema o la petición: `test_extraction_contract.py` (la factura vacía
    lleva las claves v2), `test_extraccion_pasada.py` (`_extraccion()` es una
    lectura v2), `test_golden.py` (las fixtures se validan contra
    `InvoiceExtractionV1`), `test_pricing.py` (el modelo por defecto es
    claude-opus-5-5, como anunciaba el paso 0), `test_alcance_v1.py`
    (`BMS_EXTRACT_EFFORT` en la lista de variables, `output_config` en la
    petición y el lote sin herramientas), `test_almacen.py` (las tablas
    nuevas en sus listas y en `_poblar`), `test_reglas.py` (M2 en el
    catálogo), `test_pureza_reglas.py` (`LineaSinCasar` y un escenario) y
    `test_hallazgos.py` (M2 escribe solo lo que objeta). Ninguno prueba menos
    que antes.

### Lo que deben saber los pasos siguientes

- **No se ha llamado a la API.** Todo está probado con clientes falsos; la
  primera pasada real la lanza el dueño siguiendo las instrucciones de
  arriba. Nada de `reextraccion.py` importa el SDK: el cliente se inyecta.
- **Lo que pide el v2 ya se tipa** (paso 2): receptor y contacto,
  condiciones y plazo, tipo de documento, moneda, referencias con su clase
  por etiqueta, desglose de IVA, y por línea persona (`recurso_doc`), día
  (`fecha_trabajo`), tipo de turno (`tipo_turno_doc`) y tipo de IVA.
  `related_invoices` se extrae pero no se tipa: las relaciones propuestas
  son del **paso 8**. Casar una referencia con una PO es del **paso 9**. Un
  registro v1 sigue dando `sin_datos` donde no se pidió.
- **Paso 7**: `--abiertas` lee `factura_estado.estado_pago`; cuando haya
  pagadas, dejarán de elegirse solas.
- **La vigente** de un documento sigue siendo la más reciente que no sea una
  candidata sin activar (`SIN_CANDIDATAS`). Quien lea extracciones del
  almacén para otra cosa que medir tiene que pasar por `en_orden_de_out()`.
- **Una extracción nueva** (activada o un `--force`) casa las líneas por
  huella: `Tipado.contradichos` (M1) y `Tipado.sin_casar` (M2) dicen lo que
  pasó. Una tabla hija nueva de la línea con ediciones de persona tiene que
  entrar en `ingesta._ediciones_de_linea`.
- **Un rechazo del modelo se paga**: no deja extracción, así que `coste` no
  lo ve; la pasada de `reextraer` sí lo suma a lo gastado (corrección de la
  revisión). Si los rechazos son muchos, apuntar su uso también para `coste`.
- **El esfuerzo** está en `config.effort()`; cambiarlo es medir otra vez.
- **La velocidad**: sin cambios apreciables (1,45-1,7 s y 1,3-1,6 s).

### Correcciones de la revisión

La revisión del paso 6 dejó dieciséis hallazgos. Dos estaban repetidos (el
salto de la puerta con `extract --force` o `--estricta`, en `extract.py` y
en `ingesta.py`; y el presupuesto que no frena el gasto real, en la
migración y en `reextraccion.py`), así que son catorce. Cada uno se
reprodujo antes de tocarlo con un test que falla con el commit del paso 6;
todos eran reales. Uno se arregla en parte: el plazo del maestro manda,
pero avisar de unas condiciones impresas más cortas que las acordadas es la
regla C5, que ningún paso de la §11 tiene todavía en su lista (desviación
29). **1351 tests pasan** (791 funciones de test; eran 1321 y 769): todas
las funciones nuevas fallan con el commit del paso 6 salvo
`test_un_lote_rechazado_por_la_api_va_entero_a_reintentos`, que fija lo que
tiene que seguir pasando con un 4xx. Cinco mil facturas se recalculan en
1,51-1,71 s la primera vez y en 1,30-1,38 s las siguientes (seis medidas):
la consulta nueva de `estados` (qué plazos salen del documento) no se nota.
Sin una sola llamada a la API.

| Hallazgo | Qué se hizo | Test |
| --- | --- | --- |
| **Mayor.** Las líneas se casaban por huella, pero las referencias de línea por posición: con una línea nueva delante, la PO de cada línea acababa en la de al lado (una con dos y otra sin ninguna), y una `clase` corregida a mano se iba con ella | `ingesta._actualizar_hijas`: las referencias de la cabecera y el desglose de IVA siguen por posición (`_casar_por_posicion`); una referencia de línea va con la línea con la que casó su índice. Si esa línea ya tenía una referencia de una extracción, esa fila recibe el valor nuevo (la corrección de una persona sigue en su línea); si no, se crea. Las de líneas que ya no traen referencia se retiran, o se conservan y se devuelven si una persona las tocó | `test_ingesta.py::test_una_linea_nueva_delante_no_corre_las_referencias_de_linea` |
| **Mayor.** `recoger` no se podía repetir: cada resultado entra en su transacción y la pasada sigue esperando hasta el final, así que una recogida cortada a medias fallaba para siempre (`UNIQUE` de la candidata) o, otro día, guardaba los resultados dos veces y `coste` los contaba pagados dos veces | `recoger` salta los documentos que ya tienen su resultado apuntado en esa reextracción, y `_terminar` cuenta `extraidas` y `reintentos` de las filas de `reextraccion_resultado`, no de lo visto en la llamada | `test_reextraccion.py::test_recoger_un_lote_interrumpido_se_puede_repetir_sin_duplicar` |
| `score` sin `--comparar-versiones` puntuaba en una extracción v1 lo que v1 no pidió (`document_type 0/3`, `references 1/1`…) | `_cmd_score` pasa `compat.no_solicitados` de la versión de cada extracción, como `comparar_versiones` | `test_scoring.py::test_score_no_puntua_en_una_extraccion_v1_lo_que_v1_no_pidio` |
| `parse_plazo_pago` daba 30 a «30 dagen na einde maand»: el mes solo se miraba si no había días, y el vencimiento real puede ser casi el doble | Un mes, «einde maand», «end of month» o «EOM» en cualquier parte del texto es un `ParseError` | `test_parsing.py::test_parse_plazo_pago_no_adivina` (cinco casos nuevos) |
| En un almacén de antes del paso 6 (`huella_linea` con la definición de entonces), una línea editada con un literal ilegible («n.v.t.») no casaba nunca: `huella_de_fila` no puede reproducir el «?n.v.t.» de la lectura, y era la única huella con que casar | `ingesta.huella_de_su_lectura`: la huella recalculada, con la definición de ahora, de la línea de la lectura que la puso, que dice la procedencia (`extraccion:N:lines[i]` en `fuente_automatica_ref`). Entra en el casado junto a las otras dos | `test_ingesta.py::test_en_un_almacen_de_antes_una_linea_editada_con_un_literal_ilegible_casa` (tipa con la huella de antes y activa una lectura v2) |
| Un M2 cerrado como pide su mensaje (excluir la línea que ya no existe) volvía a abrirse con la siguiente extracción de la factura: la línea excluida no casaba, su exclusión contaba como edición y `linea_sin_casar` la apuntaba otra vez con `excluida = 1` | Una línea que salió sin casar estando activa (su último `linea_sin_casar` con `excluida = 0`) y que después excluyó una persona ya está decidida: no se apunta otra vez. La que ya estaba excluida cuando salió sin casar se sigue apuntando (su exclusión no se llevó a ninguna línea nueva; la cierra una anulación) | `test_reextraccion.py::test_una_linea_excluida_para_cerrar_su_m2_no_lo_reabre_con_otra_lectura` |
| `_mismo_conjunto` casaba con comodines la primera que valía: `["A-1", {PO-nummer: A-1}]` contra `{PO-nummer: A-1}, {Kenmerk: A-1}` era un fallo, y en el otro orden un acierto | Casado bipartito (caminos de aumento): hay pareja para todas o no, en cualquier orden | `test_scoring.py::test_un_conjunto_no_depende_del_orden_de_lo_esperado` |
| *(duplicado, mayor)* El presupuesto solo se comparaba con la estimación antes de empezar; nada paraba la pasada síncrona cuando el gasto real lo pasaba (reproducido: $0,21 de presupuesto, $0,996 pagados), la estimación no sabía de `max_tokens` ni del esfuerzo, y los rechazos se pagaban sin contarse. El comentario de la migración decía que la base no dejaba pagar de más | Desviación 24: el presupuesto es un tope de lo que se paga. Antes de cada documento, lo gastado (el uso de cada respuesta, también de un rechazo, que `Rechazado.uso` trae; de un fallo sin uso, su peor caso) más el peor caso de ese documento (su entrada contada y todo su `max_tokens`) tiene que caber; si no, ni ese ni los siguientes se pagan, y van a reintentos con el motivo nuevo `presupuesto`. El evento `reextraccion_terminada` lleva lo gastado y si se paró. Un lote, que no se puede parar, solo se manda si el peor caso del lote entero cabe. Cada extracción apunta en su uso el esfuerzo y el tope de salida, y la salida «medida» lo es con el mismo esfuerzo (desviación 30). El comentario de la migración dice que el `CHECK` es de la estimación | `test_el_presupuesto_es_un_tope_de_lo_que_se_paga`, `test_si_el_peor_caso_de_un_documento_no_cabe_no_se_paga_ninguno`, `test_un_rechazo_se_paga_y_cuenta_en_lo_gastado`, `test_por_lotes_el_peor_caso_tiene_que_caber_porque_no_se_puede_parar`, `test_la_salida_medida_lo_es_con_el_mismo_esfuerzo`, `test_cada_extraccion_apunta_su_esfuerzo_y_su_tope_de_salida` |
| **Mayor.** `document_type`, que el modelo copia del proveedor, decidía `factura.tipo` aunque el signo dijera otra cosa: una factura positiva que se llama «creditnota» era una nota de crédito, y B4 y U1 no la miraban | Desviación 28: lo declarado vale solo si el signo de la base o del total lo confirma (abono con importe negativo, factura con importe no negativo). Si lo contradice, decide el signo (fuente `calculado`, ref `signo_contra_declarado`, con lo declarado como literal) y el total queda dudoso: Q2 retiene la factura hasta que una persona lo verifique | `test_ingesta.py::test_el_tipo_lo_decide_lo_que_declara_el_documento_o_el_signo` (dos casos nuevos), `test_un_abono_declarado_con_importe_positivo_no_se_salta_b4` |
| *(duplicado, mayor)* `extract --force` o `--estricta` con almacén volvía a leer lo ya tipado y la lectura v2 pasaba a vigente sin puerta, sin admin y sin fila de `activacion`; `costes.md`, `fase-0.md` y el README mandaban medir así | Desviación 23: con almacén, la relectura de un documento cuya vigente es de otras versiones es una candidata (`reextraccion.apuntar_relectura`), exportada en `out/reextraccion/`, y solo pasa a vigente con `reextraer --activar`. Una candidata exportada de esas mismas versiones no se vuelve a pagar con otra `--estricta`. La salida de `extract` dice cuántas quedan como candidatas. Los tres documentos miden ahora con `reextraer` y `score --comparar-versiones` | `test_reextraccion.py::test_extract_con_almacen_no_salta_la_puerta` (con `--estricta` y con `--force`) |
| Cualquier excepción de `batches.create` se tomaba por «no se mandó»: un timeout o un corte después de que la API aceptara el lote dejaba un lote pagado sin recoger, y `--reintentos` lo pagaba otra vez; los reintentos automáticos del SDK podían crear un segundo lote | Desviación 25: el lote se crea sin reintentos del SDK (`with_options(max_retries=0)`). Un 4xx (salvo 408) es un rechazo: todo a reintentos, como antes. Sin respuesta, la pasada queda en el estado nuevo `lote_desconocido`; sus documentos no los vuelve a elegir ningún criterio (tampoco los de un lote mandado y sin recoger), y `--recoger N` lo busca en la API por la hora y el número de peticiones: si está, lo adopta; si no, sus documentos van a reintentos; si hay más de uno que podría ser, no elige | `test_un_lote_rechazado_por_la_api_va_entero_a_reintentos`, `test_un_lote_que_no_se_sabe_si_se_mando_no_se_vuelve_a_pagar`, `test_un_lote_que_la_api_no_tiene_se_da_por_no_mandado`, `test_el_lote_se_manda_sin_reintentos_automaticos_del_sdk` |
| El plazo impreso (`payment_terms_raw`) pasaba por encima del acordado en el maestro: «per omgaande» hacía vencer la factura el día de su fecha | Desviación 29: el plazo calculado de las condiciones impresas solo vale si el maestro no tiene plazo (`estados._facturas` mira su procedencia); el que fija una persona o una importación en la factura sigue mandando. Avisar de un plazo impreso más corto es C5 | `test_ingesta.py::test_el_plazo_del_documento_no_pasa_por_encima_del_acordado` |
| **Mayor.** La puerta medía solo los documentos de las respuestas que tenían las dos versiones: con uno releído (y la inyección) pasaba, y `activar` activaba todas las candidatas pendientes | Desviación 26: un documento de las respuestas con extracción de antes y sin la de la nueva hace que la puerta no pase (`Comparacion.sin_releer`); `format_comparacion` da la línea «Cobertura». Uno sin ninguna extracción no es del conjunto leído y solo se dice | `test_scoring.py::test_la_puerta_no_pasa_si_falta_releer_documentos_de_las_respuestas` |
| **Mayor.** «No peor que la anterior» se medía contra la extracción más reciente de cualquier otra versión, también una candidata que nadie activó (un prompt rechazado): una versión peor que la vigente pasaba | Desviación 27: la anterior sale de las extracciones que pueden ser la vigente (`en_orden_de_out`, sin candidatas sin activar; `reextraccion.registros_vigentes_posibles`); sin almacén, de `out/` y no de `out/reextraccion/`. `comparar_versiones` y `pares` aceptan `anteriores` | `test_scoring.py::test_la_anterior_es_la_vigente_y_no_una_candidata_que_nadie_activo`, `test_reextraccion.py::test_la_puerta_compara_con_la_vigente_y_no_con_una_candidata_rechazada` |

**La migración 0006 se corrige en su sitio** (los estados y motivos nuevos
y los comentarios del presupuesto), como la 0003, la 0004 y la 0005 en sus
revisiones: ninguna base la tiene aplicada fuera de los tests. Una base
local creada con la versión anterior la rechaza `migrar` por el hash; se
rehace con `bms-agent importar-out`.

Desviaciones nuevas, y por qué:

23. **`extract --force` y `--estricta` con almacén dejan candidatas** si la
    vigente del documento es de otras versiones; el §10 dice que `--force`
    «no cambia» y que `--estricta` mantiene el comportamiento para medir,
    pero también que una extracción nueva solo es vigente después de la
    puerta, y las dos cosas a la vez solo caben así. La candidata es una
    `reextraccion` de un documento, ya terminada, con presupuesto 0 (extract
    no tiene; lo pagado está en el uso de la extracción) y
    `{"origen": "extract", ...}` en el criterio. Un `--force` de un
    documento cuya vigente ya es de las versiones actuales sigue pasando a
    vigente y casando por huella (desviación 17). Sin almacén nada cambia:
    no hay puerta que saltar. `importar-out` sigue sin recorrer
    `out/reextraccion/` (desviación 11).
24. **El presupuesto es un tope del gasto real.** El peor caso de un
    documento es su entrada contada más todo su `max_tokens` de salida al
    precio del modelo; un fallo sin uso cuenta como su peor caso, porque no
    se sabe si se cobró. Así la parada es conservadora: puede dejar sin
    pagar el último documento que habría cabido. La comprobación previa
    sigue siendo la del §10 (el extremo alto de la estimación), más, por
    lotes, el peor caso del lote entero. `reextraccion_resultado.motivo`
    admite `presupuesto`.
25. **`lote_desconocido`** es un estado más de `reextraccion`, y
    `reextraccion_resultado` admite filas mientras dura. El margen para
    buscar el lote en la API es de una hora a cada lado de `iniciada_en`
    (`MARGEN_LOTE_DESCONOCIDO`): los relojes no son el mismo. Si la lista
    de la API no lo tiene, se da por no mandado.
26. **La puerta exige cobertura completa de las respuestas**: todo
    documento de `respuestas.yaml` con una extracción anterior tiene que
    tener la de la nueva. El §10 dice «el 98 % del conjunto real»; medir
    solo lo releído dejaba activar con un documento.
27. **La anterior es la vigente** (o la más reciente de otra versión que
    pudo serlo), nunca una candidata sin activar. Completa la desviación 7.
28. **El tipo declarado se cruza con el signo**, y su desacuerdo retiene por
    Q2 (el total dudoso), no por una regla nueva. Sustituye a la desviación
    19 en lo que tiene de «lo declarado manda»: corrección y sustitución
    siguen siendo facturas, y anulación y `unknown` siguen decidiendo por el
    signo.
29. **El plazo del maestro manda sobre el impreso.** Sustituye a la
    desviación 20 en lo que tiene de «vale el impreso»: el impreso se sigue
    guardando (`condiciones_pago_doc` y `plazo_pago_dias` calculado), pero
    el vencimiento solo lo usa sin plazo acordado. Avisar de un plazo
    impreso más corto que el acordado es C5, que no está en la lista de
    ningún paso de la §11; queda para cuando se decida dónde va.
30. **El uso de cada extracción lleva `effort` y `max_tokens`**, como
    `service_tier` (desviación 21): `ExtractionRecord` no cambia de forma.
    `coste.estimar_salida` solo da por medida la salida de extracciones del
    mismo modelo, versión del esquema y esfuerzo; las de antes, sin
    esfuerzo apuntado, no son medida de ninguno.

**Tests existentes cambiados, y por qué**: en `test_ingesta.py`, el caso
`invoice` con importes negativos de
`test_el_tipo_lo_decide_lo_que_declara_el_documento_o_el_signo` es ahora una
nota de crédito por el signo con el total dudoso (desviación 28), y
`test_una_extraccion_v2_llena_lo_que_v1_no_pedia` declara
`corrected_invoice` en vez de `credit_note`, porque sus importes son
positivos; en `test_extraccion_v2.py`, el uso de un resultado de lote lleva
`effort` y `max_tokens` (desviación 30). El cliente falso de
`test_reextraccion.py` gana la salida configurable y `batches.list`, y su
`batches.create` puede fallar antes o después de crear el lote. Ninguno
prueba menos que antes.

Lo que deben saber los pasos siguientes, además de lo de arriba:

- **Una vía nueva que lea un documento ya leído** tiene que dejar
  candidatas (`reextraccion.apuntar_relectura` o `ejecutar`), nunca
  vigentes, si la vigente es de otras versiones.
- **Paso 7**: `--abiertas` y el estado de pago no cambian; el vencimiento
  usa el plazo del maestro antes que el impreso.
- **C5** (plazo impreso más corto que el acordado) tiene ya los dos datos:
  `factura.plazo_pago_dias` calculado de `condiciones_pago_doc` y el del
  maestro.

## Paso 7

Banco, pagos y flujo de caja: los extractos (CAMT.053 .001.02 y .001.08,
MT940 con el `:86:` de ING, ABN AMRO y Rabobank, y los CSV de ING y
Rabobank), lo pagado según Exact, casar el banco con las facturas, el saldo
de cada una, las órdenes de pago de las personas, las reglas K1-K8 y F7 y el
flujo de caja. **Nada de esto paga, aprueba ni prepara un pago**: apunta lo
que ya se pagó (el banco, Exact o una persona lo dice) y lo compara. **1447
tests pasan** (858 funciones de test; eran 1321 y 769 al cerrar el paso 6).
Cinco mil facturas se recalculan en 1,73-1,88 s la primera vez y en
1,50-1,55 s las siguientes (tres medidas en este contenedor, sin
movimientos): las reglas K cuestan 0,03 s entre todas y casar sale enseguida
si no hay movimientos; el resto es la variación del contenedor y el saldo
por factura en las cachés.

### Qué se construyó

**Migración `0007_banco_pagos.sql`** (la siguiente libre: la §11 dice 0005,
que ya era del paso 5). Tres tablas:

- `extracto_bancario`: un extracto de una cuenta propia, de una
  importación del banco (`fuente = 'banco'`, `tipo = 'extracto'`), con su
  identificador, secuencia, moneda, saldos de apertura y cierre con sus
  fechas, el periodo, `con_saldos` (0 en los CSV), cuántos apuntes trae y su
  formato (`camt053:001.02`, `mt940:ing`, `csv:ing-af-bij-v1`...). Solo la da
  de alta el importador con su importación en curso; es evidencia: ni
  UPDATE ni DELETE.
- `movimiento_bancario`: cada movimiento, con su posición en el fichero, las
  fechas contable y valor, el importe en céntimos (NULL si no está en euros,
  y entonces el literal y la moneda dicen lo que era: X1), la contraparte
  (IBAN y nombre tal como los trae el banco), el concepto, la referencia
  estructurada, el end-to-end, la referencia del banco, la remesa si venía
  en un apunte agrupado y una `huella` única. Entra con su extracto (misma
  importación, misma cuenta, en curso) y es evidencia.
- `aplicacion_pago`: lo que un pago aplica a una factura. `fuente` (banco,
  exact, manual), `metodo` (automatica, propuesta, manual) y `estado`
  (propuesta, confirmada, retirada), con el importe en el signo de la
  factura, la fecha del pago, el movimiento (si es del banco) o la
  importación (si es de Exact), la regla con la que se casó, el motivo y
  quién la confirmó y cuándo. Es una tabla controlada (`campos.py`, con sus
  guardas generadas): los CHECK atan fuente, método y estado (banco ⇔
  movimiento; exact ⇔ importación y automática; manual ⇒ quién y motivo;
  propuesta ⇒ nadie la ha confirmado) y los disparadores dicen quién puede
  qué: lo automático y lo propuesto solo lo escriben `motor` o `importador`;
  lo manual y una confirmación, una persona activa con `marcar_pagada` en su
  propio evento; una confirmación solo sobre una propuesta sin confirmar ni
  retirar; lo que identifica el pago (factura, movimiento, importe, fecha,
  fuente, método) no cambia nunca. Nada se borra: se retira.

Y la vista `v_factura_saldo` (lo pagado por fuente, la fuente que manda, lo
pagado y lo pendiente de cada factura), para leer con SQL.

**Dominio y `campos.py`.** `FuenteAplicacion`, `MetodoAplicacion`,
`EstadoAplicacion` y `PRECEDENCIA_PAGO` (banco > exact > manual).
`aplicacion_pago` en el registro: todo fijo salvo el motivo y quién y cuándo
confirmó; el `estado` se calcula de método, confirmación y retirada (nadie
escribe un estado). Su alta pide `marcar_pagada`. `Orden.retirar` recalcula
ahora lo que depende de la columna de retirada (ver desviación 23).

**Lectores** (`importadores/`), puros, bytes dentro y registros canónicos
fuera:

- `camt053.py`: `xml.etree.ElementTree`, sin espacio de nombres fijo. Antes
  de leer, `comprobar_seguro` rechaza cualquier declaración (`<!DOCTYPE`,
  `<!ENTITY`, `<!ELEMENT`...), en los bytes y en el texto decodificado
  (también UTF-16); solo admite comentarios y CDATA. Solo las versiones
  .001.02 y .001.08: otra se rechaza entera. Cada `TxDtls` es un movimiento
  (un apunte agrupado da uno por transacción, con la referencia del apunte
  en `remesa`), y se comprueba al leer que las transacciones suman su apunte
  y que los apuntes contabilizados suman la diferencia de saldos. Los
  apuntes sin contabilizar (PDNG, INFO) no entran y se avisan. La
  secuencia es `ElctrncSeqNb` (o `LglSeqNb`), los saldos OPBD (o PRCD) y
  CLBD, la contraparte el acreedor de un cargo o el deudor de un abono.
- `mt940.py`: `:20:` abre un extracto, `:25:` da la cuenta (el IBAN se busca
  con su dígito de control, también con la moneda pegada), `:28C:` la
  secuencia, `:60F:`/`:62F:` los saldos y cada `:61:` un apunte. El `:86:` se
  lee con el perfil de su banco (`PERFILES`: ing, abn, rabobank), elegido por
  el código del banco de la cuenta o pedido (`--mapeo mt940:rabobank`):
  `/CNTP/` (cuenta/BIC/nombre/ciudad), `/IBAN/` y `/NAME/` sueltos, `/REMI/`
  (`USTD//` libre o `STRD/CUR/` estructurada) y `/EREF/`; Rabobank deja a
  veces la cuenta en la línea complementaria del `:61:`. Sin perfil, el
  `:86:` entero es el concepto, con aviso.
- `banco.py`: elige el lector por el contenido (un XML, un `:20:`, las
  columnas de un mapeo) o por `--mapeo`, agrupa los CSV en un extracto sin
  saldos por cuenta y tiene la orden entera (`importar_extracto`, con
  `--simular`).
- Mapeos `banco-extracto-ing-v1.yaml` (Af/Bij: el signo en otra columna,
  la opción nueva `signo` de `tabular.py`) y `banco-extracto-rabobank-v1.yaml`,
  y `exact-pagos_exact-v1.yaml` (las partidas abiertas y pagadas de Exact:
  Factuurbedrag, Openstaand, Betaald, Betaaldatum), con sus fixtures y su
  contrato `.esperado.json` como los del paso 5.

**Registrar** (`importadores/registrar.py`). Un extracto entra entero o
nada: la cuenta tiene que estar en `cuentas_propias` de `config/empresa.yaml`
(sin ninguna cargada, no entra nada), un movimiento cuya huella ya está no
entra otra vez y un extracto que ya estaba entero se avisa y no se repite.
La huella es el SHA-256 de la cuenta, las fechas, el importe con su signo,
el literal, la moneda, la contraparte, el concepto, las referencias, la
remesa y **la ocurrencia** (cuántas veces apareció ese mismo movimiento antes
en el fichero): dos comisiones iguales del mismo día son dos, y el mismo
fichero (o uno que se solapa) no las duplica. Cada extracto deja un evento
`extracto_registrado` con la foto del extracto y de cada movimiento, y
`db verificar` compara cada movimiento con su foto (`evidencia.py`). Los
pagos de Exact: una fila ilegible o en otra moneda rechaza el fichero; la
fila de una factura que aquí no está queda rechazada (Z2) y las demás se
aplican (estado `parcial`); si Exact dice otro importe que la última vez, lo
de antes se retira y se escribe lo nuevo.

**`pagos.py`**. Casar (`conciliar`, al principio de cada pasada del motor):
cada movimiento que no está cubierto se compara con las facturas en juego del
sentido que le toca por tres cosas, la referencia (el número de la factura o
su referencia de pago en la referencia estructurada, el end-to-end o el
concepto, por palabras y pares de palabras), el importe (lo que queda del
movimiento es lo que queda de la factura) y la contraparte (la cuenta está en
el registro de ese proveedor o cliente). Con las tres y una sola factura, el
pago es automático y queda confirmado; con dos de tres y una sola factura con
dos, es una propuesta por el importe que se puede aplicar; con menos, nada.
Un traspaso entre cuentas propias y un pago a un beneficiario conocido no se
casan; lo que una persona retiró no se vuelve a proponer. El índice por
referencia e importe hace que casar no sea movimientos × facturas.
`saldos(conn)` da el saldo de cada factura. Órdenes: `marcar_pagada` (motivo
obligatorio; por defecto lo que queda y hoy; nunca una fecha futura, ni una
factura anulada, fusionada o sin total en euros; con `movimiento_id` enlaza un
movimiento del banco a mano), `confirmar_pago` (solo una propuesta) y
`retirar_pago` (motivo obligatorio; lo de Exact se corrige en Exact).
Consultas: `de_factura`, `movimientos` (`sin_casar`), `propuestas`.

**Reglas.** `reglas/pagos.py` (puro): `saldo()`, la única cuenta de lo pagado
que usan las reglas, las cachés y el flujo; `roturas()` de la cadena de
extractos; K1-K8 con sus `lee` declarados. F7 en `bancaria.py`; X1 mira
también los movimientos (`calidad.x1_movimientos`). La instantánea trae
`extractos`, `movimientos`, `aplicaciones`, `beneficiarios` y `bloqueos`
(los intervalos en que cada factura tuvo un hallazgo que bloquea, sacados de
`hallazgo_evento`), y cada `Factura` su `vencimiento`, `pagado_cent`,
`fuente_pago` y `pagada`. `config/reglas.yaml` gana la sección `pagos`
(`tolerancia: "0.00"`, `dias_vencida_venta: 14`, `dias_pago_sin_extracto: 7`,
`dias_movimiento_sin_casar: 7`, `ventana_doble_pago_dias: 30`, con sus
límites en `politica._LIMITES`); los valores por defecto son los de
`Politica`.

| Regla | Qué dice | Severidad | Ámbito |
| --- | --- | --- | --- |
| K1 | Vencida sin pagar: una compra desde el día siguiente, una venta pasados 14 días; sin un extracto que cubra desde su fecha (ni un Exact de pagos al día), sin datos | aviso, anulable, abre excepción | factura |
| K2 | Lo confirmado no deja el saldo a cero: parcial o de más | retención (aviso en una venta), pegajosa | factura |
| K3 | Marcada pagada a mano y, pasados 7 días con extractos al día, el banco no la trae | aviso, anulable | factura |
| K4 | Dos cargos a la misma parte (el proveedor o cliente de la cuenta; si no está registrada, la cuenta), mismo importe y misma referencia de pago en 30 días desde el primero; o una factura pagada de más con dos o más cargos (revisión: desviación 24) | bloqueo, pegajosa | movimiento / factura |
| K5 | Pagada un día en que tenía un hallazgo que bloquea, pendiente y sin anular | retención, pegajosa | factura (uno por pago) |
| K6 | La cadena de extractos de una cuenta se rompe (saldo que no encadena o secuencia que salta) | bloqueo, pegajosa | importación, y las facturas pagadas desde la rotura |
| K7 | Movimiento sin casar pasados 7 días | aviso, anulable | movimiento |
| K8 | El banco y Exact dicen importes pagados distintos, también cuando Exact dice cero, con lo del banco hasta el día de la foto de Exact (revisión: desviación 27) | retención | factura |
| F7 | Un cargo a un proveedor (casado con una factura suya, o a una cuenta registrada solo para él) fue a una cuenta que no era pagable para él el día del cargo (o que una persona rechazó), y no es un beneficiario conocido ni una cuenta propia (revisión: desviación 26) | bloqueo, pegajosa; las facturas casadas, al menos urgentes | movimiento, y sus facturas como relacionadas |

**Estados y prioridad** (`estados.py`). `estado_pago` es `pagada` cuando el
saldo queda en la tolerancia; un pago parcial deja `pendiente` o `vencida`,
y `pendiente_cent` es lo que queda. Una pagada sale de juego: deja de sumar
en los agregados, de correr plazo y de ser vencida, y F5 por factura no la
mira. El vencimiento efectivo (el impreso, o la fecha más el plazo) está en
`instantanea.vencimientos(conn)`, una sola vez para cachés, reglas y flujo.
`hallazgos._Pasada.ejecutar` casa antes de evaluar y la `Diferencia` lleva la
`conciliacion`.

**`flujo_caja.py`**. Lo esperado son las facturas en juego por lo que les
queda, en euros, por su vencimiento efectivo; «entrada» lo que se cobra
(ventas y abonos de proveedores) y «salida» lo que se paga. Ventanas desde
`hoy` (inyectado; Amsterdam): vencido, esta semana (de hoy al domingo),
este mes (de hoy al último día), próximos 30 días (hoy y 29 más), un
periodo pedido (con lo que venció en él), sin fecha y total, con el neto de
cada una. Lo movido (cobrado y pagado) es, desde la revisión, el dinero que
movió el banco (desviación 28), de lunes a hoy, del día 1 a hoy o en el
periodo. El trabajo sin facturar y el planificado van en una línea aparte,
`estimado`, que hoy dice
que no hay datos (`None`, nunca cero). `calcular` es puro; `flujo(conn, hoy)`
lee el almacén. `reloj.semana_de` y `reloj.mes_de` dan la semana ISO y el mes.

**Órdenes, CLI y servidor.** `servicios.ACCIONES` gana `marcar_pagada`,
`confirmar_pago` y `retirar_pago`, las tres con `marcar_pagada`, `rev` y
motivo (obligatorio para marcar y retirar): salen solas en `bms-agent
accion …`, en `POST /api/v2/acciones` y en la lista de acciones; un
`PagoNoValido` es un 409. CLI nueva: `bms-agent importar banco extracto
<fichero> [--mapeo camt053|mt940[:ing|abn|rabobank]|<mapeo>]`, `bms-agent
importar exact pagos_exact <fichero>`, `bms-agent pagos [--sin-casar |
--propuestas | --factura N]` y `bms-agent flujo-caja [--hoy] [--desde
--hasta] [--json]`; `recalcular` dice lo que casó.

**Tests nuevos**: `test_banco.py` (lectores, importación, evidencia,
pagos de Exact), `test_pagos.py` (casar, saldo, órdenes y K sobre el almacén
entero, y la CLI), `test_flujo_caja.py` y `test_reglas_paso7.py` (cada
regla K y F7 sobre instantáneas, y los escenarios de la prueba de pureza).
`conftest.py` gana un constructor de CAMT.053 (`camt053`, `apunte`),
`cuentas_propias` e `importar_camt`.

### La puerta, test por test

| Puerta | Tests |
| --- | --- |
| Fixtures CAMT .001.02 y .001.08, con TxDtls agrupados | `test_banco.py::test_camt_001_02_cada_transaccion_de_un_apunte_agrupado_es_un_movimiento`, `test_camt_001_08_lee_los_cobros_agrupados_y_la_referencia_estructurada`, `test_las_dos_fixtures_entran_y_quedan_como_evidencia` (las dos fixtures de `tests/fixtures/banco/`, en cadena, con `db verificar` limpio), `test_un_apunte_agrupado_que_no_suman_sus_transacciones_no_entra`, `test_un_extracto_cuyos_apuntes_no_dan_los_saldos_no_entra`, `test_otra_version_de_camt_no_se_lee_a_medias` |
| Un DOCTYPE se rechaza | `test_un_xml_con_doctype_o_entity_no_se_lee` (bomba de entidades, DTD externo, XXE, ENTITY suelta, en minúsculas y con espacio: ni se lee ni deja una importación), `test_un_doctype_en_utf16_tambien_se_ve` |
| Una cuenta propia ajena se rechaza | `test_un_extracto_de_una_cuenta_que_no_es_de_bm_support_no_entra` (también con un extracto bueno en el mismo fichero), `test_sin_cuentas_propias_en_la_politica_no_entra_ningun_extracto` |
| Una fila que no está en euros da X1 | `test_un_movimiento_en_otra_moneda_entra_con_su_literal_y_da_x1`, `test_los_csv_del_banco_entran_sin_saldos_y_k6_no_los_mira` (la fila en dólares de Rabobank), `test_un_pago_de_exact_en_otra_moneda_rechaza_el_fichero`, `test_reglas_paso7.py::test_x1_un_movimiento_en_otra_moneda` |
| Una rotura de la cadena bloquea (K6) | `test_pagos.py::test_un_salto_en_la_secuencia_de_extractos_bloquea_k6` (la importación y la factura pagada después quedan Bloqueadas; al llegar el que faltaba, K6 deja de verse), `test_un_saldo_que_no_encadena_bloquea_k6`, `test_reglas_paso7.py::test_k6_la_cadena_de_extractos`, `test_k6_bloquea_el_extracto_y_lo_pagado_desde_la_rotura` |
| Un cargo doble da K4 | `test_pagos.py::test_dos_cargos_iguales_son_un_pago_doble_k4` (el par de movimientos, y la factura pagada de más si alguien enlaza el segundo), `test_reglas_paso7.py::test_k4_dos_cargos_iguales_a_la_misma_cuenta_y_referencia_son_un_pago_doble`, `test_k4_una_factura_pagada_de_mas_con_dos_cargos` |
| Un pago parcial sigue Pendiente con su saldo y K2 | `test_pagos.py::test_un_pago_parcial_deja_la_factura_pendiente_con_su_saldo_y_k2` (y el flujo de caja con lo que queda), `test_un_pago_parcial_de_una_vencida_la_deja_vencida`, `test_pagada_solo_dentro_de_la_tolerancia` (0,00 por defecto; 0,01 cargada en la política), `test_reglas_paso7.py::test_k2_un_pago_parcial_deja_el_saldo_y_retiene` |
| Un pago mientras está Bloqueada da K5 | `test_pagos.py::test_pagar_una_factura_bloqueada_da_k5` (el pago de antes del bloqueo no; el de ese día sí), `test_reglas_paso7.py::test_k5_pagada_mientras_estaba_bloqueada` |
| Ventanas del flujo con una fecha fija de domingo a lunes y a fin de mes | `test_flujo_caja.py::test_de_domingo_a_lunes_la_semana_empieza_otra_vez` (2026-10-18 → 2026-10-19), `test_de_fin_de_mes_al_primero_el_mes_empieza_otra_vez` (2026-10-31 → 2026-11-01), `test_lo_movido_de_la_semana_y_el_mes_hasta_hoy`, `test_un_periodo_pedido_lleva_tambien_lo_que_vencio_en_el`, `test_semana_y_mes_del_reloj` |

Además: los repetidos (`test_los_movimientos_repetidos_no_entran_y_dos_iguales_son_dos`),
`--simular`, un movimiento cambiado por detrás que `db verificar` ve, MT940
de los tres bancos y uno sin perfil, los CSV sin saldos y uno con una fila
ilegible, los pagos de Exact (todo o nada, Z2, la reimportación que retira),
casar automático y propuesta, lo que no se casa (K7, ni el traspaso propio
ni Hacienda), retirar y enlazar a mano, marcar pagada (motivo, fecha futura,
X1, K3, conflicto de `rev`), Exact frente al banco (precedencia y K8), la
base que no deja escribir pagos por fuera, ningún usuario de sistema que
confirme, la matriz de permisos con las tres órdenes nuevas y la CLI de
punta a punta.

### Desviaciones de la especificación, y por qué

1. **Migración 0007, no 0005.** La §11 numera las migraciones como si cada
   paso tuviera la suya desde el 3; 0005 y 0006 ya eran de los pasos 5 y 6.
2. **Columnas de más.** `posicion`, `importe_crudo`, `referencia_estructurada`,
   `referencia_e2e`, `ref_banco`, `remesa` en el movimiento; `identificador`,
   `fecha_saldo_*`, `entradas` y `formato` en el extracto; `importacion_id`,
   `regla`, `retirada_en` y `rev` en la aplicación. Son lo que hace falta
   para casar, para la huella, para K6 y para explicar cada pago.
3. **Los pagos de Exact no son todo o nada del todo.** Una fila ilegible o en
   otra moneda rechaza el fichero (decisión 6), pero la fila de una factura
   que aquí no está se rechaza sola (Z2) y las demás se aplican: a una
   factura que no existe no se le puede dar un estado falso, y esperar a
   tenerlas todas dejaría sin estado las que sí están.
4. **K1 y K3 dicen sin datos sin un extracto al día.** Sin un extracto que
   cubra desde la fecha de la factura (K1) o los días siguientes al pago
   (K3), o con el banco pasado de frescura, no se sabe si se pagó: decir
   «vencida» o «sin rastro» sería adivinar.
5. **K5 no cuenta los bloqueos de K ni de F7**, y mira días enteros: un pago
   no puede estar «hecho mientras Bloqueada» por un K4 o un K6 que solo
   existen por ese mismo pago. Un hallazgo que se anula deja de contar desde
   la anulación.
6. **K6 bloquea la importación y las facturas pagadas con movimientos del
   extracto roto o de los siguientes de la cuenta**, no las que siguen sin
   pagar (no hay nada que dar por bueno). Una secuencia que vuelve a 1 con
   el año no es una rotura. Los CSV no tienen saldos: K6 no los mira.
7. **K4 pide parte y referencia** (en la revisión, la parte en vez de la
   cuenta; desviación 24) y deja fuera las cuentas propias y los
   beneficiarios conocidos: dos alquileres o dos nóminas iguales no son un
   pago doble. Añade el caso de una factura pagada de más con dos o más
   cargos, que es el mismo error visto desde la factura.
8. **F7 mira también las propuestas y los cargos a una cuenta registrada
   solo para un proveedor**: si el pago ya salió a una cuenta que no es
   pagable, da igual que nadie lo haya confirmado todavía. Sin IBAN de la
   contraparte, o sin un maestro al día, dice sin datos.
9. **Una propuesta lleva como mucho lo que queda** de la factura y del
   movimiento: proponer más dejaría un K2 de más que nadie hizo.
10. **Casar va en cada pasada del motor**, no solo al importar: una cuenta
    registrada o una factura que llega después casan los movimientos que
    esperaban. Es idempotente y sale enseguida si no hay movimientos.
11. **`estados.py` usa `reglas.pagos.saldo`, no `v_factura_saldo`.** Es la
    misma cuenta escrita una vez en Python, compartida con las reglas y el
    flujo (y con la tolerancia de la política, que la vista no conoce). La
    vista queda para leer con SQL; todavía no resta abonos (paso 8).
12. **El estado de una aplicación se calcula** (de método, confirmación y
    retirada): confirmar es rellenar quién y cuándo, y nadie escribe un
    estado a mano.
13. **`retirar_pago` y enlazar un movimiento a mano** no están en la lista de
    la §11 («marcar pagada», «confirmar»): sin retirar, una propuesta
    equivocada o una marca a mano mal puesta solo se podrían deshacer
    borrando, y lo que el sistema no pudo casar solo se podría marcar sin el
    movimiento. Retirar no borra.
14. **CSV de ING y Rabobank, no de ABN AMRO.** ABN AMRO exporta su banca por
    internet como TXT o MT940 sin cabecera de columnas; su MT940 tiene
    perfil.
15. **El perfil MT940 se elige por el banco de la cuenta** (INGB, ABNA,
    RABO), o se pide con `--mapeo mt940:<banco>`; otro banco se lee con el
    `:86:` entero como concepto y un aviso.
16. **La misma cuenta en dos formatos puede duplicar movimientos.** Un CAMT y
    un CSV del mismo día no dan la misma huella (traen campos distintos); K4
    es la red. Conviene importar cada cuenta siempre en el mismo formato.
17. **La huella lleva la referencia del banco**: un banco que cambiara la
    referencia de un apunte entre dos extractos que se solapan duplicaría
    ese movimiento (y K4 lo diría).
18. **La foto de cada movimiento va en el evento de su extracto**, no en un
    evento por movimiento: un extracto de mil apuntes es un evento, y `db
    verificar` compara cada fila con su foto igual.
19. **El vencimiento efectivo pasó de `estados.py` a
    `instantanea.vencimientos`**, para que cachés, reglas y flujo lo calculen
    igual.
20. **Las ventanas del flujo**: «esta semana» es de hoy al domingo y «este
    mes» de hoy al último día (lo de antes de hoy es «vencido», aparte);
    «próximos 30 días» cuenta hoy. Lo cobrado y pagado va de lunes a hoy y
    del día 1 a hoy. La §11 no las define; así ninguna factura cuenta dos
    veces en la misma columna y lo vencido no se esconde en la semana.
21. **El estimado es `None` hasta el planning** (paso 10): cero diría que no
    hay trabajo sin facturar, y no se sabe.
22. **Un fichero con DOCTYPE no deja importación**: se rechaza antes de
    leerlo, y la orden termina con el error (como un fichero sin columnas
    reconocibles en el paso 5).
23. **`campos.Orden.retirar` recalcula lo que depende de la retirada.**
    Hasta ahora ningún campo calculado dependía de `retirada_en`; el estado
    de una aplicación sí, y retirarla dejaba la fila a medias (el CHECK de
    la base lo paraba). Solo recalcula si algún campo depende de esa
    columna, así que las demás tablas no cambian.

**Tests existentes cambiados, y por qué**: `test_almacen.py` añade
`extracto_bancario` y `movimiento_bancario` a la evidencia (y una fila de
cada a `_poblar`); `test_servicios.py` añade las tres órdenes a la matriz del
§6 y a `CASOS` (con una propuesta preparada desde un CAMT cuya cuenta no es
la de los documentos del escenario), y una excepción a mano de un
`movimiento` que no existe da ahora `LookupError` (la tabla ya existe); en
`test_hallazgos.py`, K1, K2, K3, K4, K5 y K8 son de las que solo dicen
objeciones; `test_importadores.py` cuenta los mapeos nuevos;
`test_reglas.py` y `test_pureza_reglas.py` ganan F7 y K1-K8 en el catálogo,
sus ámbitos, cuál abre excepción, cuáles no se anulan, los tipos nuevos de
la instantánea y los escenarios del paso 7. Ninguno prueba menos que antes.

### Lo que deben saber los pasos siguientes

- **Paso 8 (ventas y abonos)**: un abono que acredita entero marca la
  original como acreditada y uno parcial le reduce el saldo:
  `reglas.pagos.saldo` (y `v_factura_saldo`) tienen que restar lo acreditado
  de las relaciones confirmadas, y `estado_pago` ganar «acreditada». Casar
  ventas ya funciona (un abono del banco cobra una venta; un cargo paga un
  abono a un cliente) y `flujo_caja.direccion` ya trata los abonos. F10
  compara con `cuentas_propias`, que ya exige el importador del banco.
- **Paso 10 (planning)**: la línea `estimado` del flujo de caja espera el
  trabajo sin facturar y el planificado, aparte de lo facturado.
- **Escribir un pago** es siempre `campos.orden` sobre `aplicacion_pago`
  (las guardas y los disparadores paran cualquier otra vía); nada fuera de
  `pagos.py` y `registrar.py` lo hace. Ningún código ejecuta, prepara ni
  aprueba un pago: la suite de alcance lo sigue comprobando.
- **Importar el banco pide `cuentas_propias`** cargadas con `bms-agent
  politica cargar config/empresa.yaml`; sin ellas no entra ningún extracto.
- **Los bloqueos de K5** salen de `hallazgo_evento`: una regla nueva que
  bloquee cuenta sola, salvo que sea de pagos (K) o F7.
- **La consola** no tiene todavía una vista de pagos ni del flujo de caja:
  las órdenes ya están en `/api/v2/acciones`, y `pagos.movimientos`,
  `pagos.propuestas`, `pagos.de_factura` y `flujo_caja.flujo` son las
  lecturas que necesitará.
- **El rendimiento**: con movimientos, casar es por índice (referencia e
  importe), no movimientos × facturas; K4 y K6 recorren los movimientos y
  los extractos una vez por pasada.

### Correcciones de la revisión

La revisión del paso 7 dejó diecinueve hallazgos. Uno estaba repetido (el
DOCTYPE en UTF-16 sin BOM) y otro se solapaba en parte con un tercero (el
enlace a mano de un movimiento que no lo sostiene), así que son diecisiete.
Cada uno se reprodujo antes de tocarlo (con el script del revisor o con el
test nuevo contra el commit del paso 7); todos eran reales. Dos se arreglan
en parte, y se dice por qué: la separación de funciones de los pagos queda
apuntada (`autorrevisado`) pero no se exige una segunda firma, y no hay una
regla nueva para un movimiento aplicado de más (desviaciones 25 y 29).
**1467 tests pasan** (877 funciones de test; eran 1447 y 858). Sin una sola
llamada a la API.

| Hallazgo | Qué se hizo | Test |
| --- | --- | --- |
| *(duplicado, mayor)* El filtro de DOCTYPE no veía un UTF-16 sin BOM: sus bytes son UTF-8 válido (NUL entre letras), el texto no traía ningún «<!» seguido y expat, que reconoce UTF-16 por «<\x00», expandía la entidad en el movimiento | `comprobar_seguro` termina pasando el fichero por expat (el mismo que lee después) con manejadores que paran en cualquier DTD, entidad, elemento, lista de atributos o notación, y sin entidades de parámetro: lo que expat leería es lo que se comprueba, sea cual sea la codificación. El texto se decodifica además con las firmas del apéndice F de XML, y `reconoce` ve un XML en UTF-16 (con BOM o sin él) para que llegue al lector CAMT y se diga por qué no se lee | `test_banco.py::test_un_doctype_en_utf16_sin_bom_tambien_se_ve` (LE y BE) |
| Un apunte de una sola transacción tomaba el importe instruido (`InstdAmt`, quizá en otra moneda) en vez del del apunte: un cargo en euros salía como X1 en dólares y apagaba la suma de los saldos | El importe de un apunte es `Ntry/Amt`, siempre. Solo un apunte agrupado se reparte, con `TxDtls/Amt` o `AmtDtls/TxAmt` en la moneda del apunte; `InstdAmt` nunca es lo apuntado, y una transacción de una remesa en otra moneda que su apunte rechaza el extracto | `test_el_importe_es_el_del_apunte_y_no_el_instruido_en_otra_moneda` |
| **Mayor.** Un apunte en otra moneda apagaba las dos comprobaciones de que el extracto está entero: uno truncado con una línea en dólares entraba y casaba pagos | Desviación 32: la suma de los saldos se hace siempre con los apuntes en la moneda de la cuenta; los de otra moneda (X1) no entran en ella, y si los demás no dan los saldos el extracto no entra | `test_un_apunte_en_otra_moneda_no_apaga_la_suma_de_los_saldos` |
| **Mayor.** MT940: las páginas de un extracto (`:28C:00101/1`, `00101/2`) y el `:28C:00000` de ING daban un K6 que bloquea aunque los saldos encadenaran | Desviación 31: en `roturas`, un número repetido o 0 no dice nada y deciden los saldos; un salto de verdad sigue rompiendo | `test_banco.py::test_mt940_de_varias_paginas_no_rompe_la_cadena`, `test_mt940_con_el_numero_siempre_a_cero_no_rompe_la_cadena`, `test_reglas_paso7.py::test_k6_un_numero_repetido_o_cero_lo_deciden_los_saldos` |
| **Mayor** (dos hallazgos). `marcar_pagada` con un movimiento no miraba lo que quedaba de él, ni si iba a una cuenta propia o a un beneficiario conocido: un cargo de 10,00 (o uno a Hacienda) dejaba pagada con el banco una factura de 2902,79, apagaba K3 y K7/F7 no lo veían; el mismo movimiento servía para varias facturas | Desviación 25: `_movimiento_enlazable` rechaza (`PagoNoValido`) un movimiento de una cuenta propia o de un beneficiario conocido, uno ya aplicado entero y un importe mayor que lo que queda de él (lo propuesto cuenta). Sin importe, lo que queda del movimiento sin pasar de lo que la factura tiene abierto con el banco | `test_pagos.py::test_enlazar_un_movimiento_no_paga_mas_de_lo_que_queda_de_el` |
| **Mayor.** Con un movimiento enlazado, la fecha del pago la podía poner la persona: un pago hecho con la factura Bloqueada se fechaba antes y K5 (que no se anula) no lo veía | Un pago enlazado lleva la fecha contable del movimiento; otra fecha es un `PagoNoValido` | `test_un_pago_enlazado_lleva_la_fecha_del_banco_y_k5_lo_ve` |
| **Mayor.** Marcar pagada a mano una factura con pagos del banco (o de Exact) salía bien pero no contaba (manda el banco): la orden decía «lo que queda» y la factura seguía pendiente con K2 | Desviación 33: una marca a mano sobre una factura con pagos confirmados de una fuente de más peso es un `PagoNoValido` que dice enlazar el movimiento que falta o corregirlo en Exact | `test_no_se_marca_a_mano_lo_que_el_banco_ya_paga_en_parte` |
| Casar automático aceptaba un importe solo dentro de la tolerancia, y apuntaba lo abierto de la factura y no lo que movió el banco | Desviación 34: automático pide el importe exacto; con las tres coincidencias y el importe dentro de la tolerancia es una propuesta, por lo que movió el banco como mucho | `test_casar_solo_es_automatico_con_el_importe_exacto` |
| **Mayor.** K4 usaba el concepto entero como referencia y encadenaba la ventana desde el último cargo: dos cuotas de un leasing con el mismo texto a 28 días eran un pago doble que bloquea | Desviación 24: la referencia de un movimiento es la estructurada, el end-to-end o el número de una factura que aparece en el concepto (`instantanea.movimientos`; `referencias_de` pasa de `pagos.py` a `instantanea.py` para que casar y K4 lean igual); la ventana se cuenta desde el primero | `test_pagos.py::test_dos_recibos_mensuales_con_el_mismo_concepto_no_son_un_pago_doble`, `test_reglas_paso7.py::test_k4_la_ventana_se_cuenta_desde_el_primer_cargo` |
| K4 agrupaba por cuenta y no por parte: pagar dos veces a un proveedor en dos cuentas suyas no era un pago doble | Desviación 24: se agrupa por la parte de la cuenta en el registro (si es de una sola), y por la cuenta si no está registrada | `test_k4_dos_cargos_al_mismo_proveedor_en_dos_cuentas_suyas` |
| **Mayor.** Para K5, un hallazgo que bloquea seguía contando como Bloqueada mientras estaba desaparecido; la prioridad lo pone en Atención | `instantanea.bloqueos` cuenta solo lo abierto, como `prioridad.suelo_de`: un tramo acaba al desaparecer y empieza otro si se reabre. La cuenta de los tramos sale a `tramos_bloqueados`, pura | `test_k5_un_bloqueo_desaparecido_ya_no_es_bloqueada` |
| **Mayor.** F7 miraba si la cuenta es pagable hoy: un pago de septiembre a una cuenta pagable entonces se volvía un F7 que bloquea cuando el proveedor cambió de banco en octubre | Desviación 26: F7 mira el estado de la cuenta con los eventos hasta el día del cargo (`EventoCuenta.dia`, en Ámsterdam; `estado_cuenta` acepta los eventos). Los de la importación de partida cuentan desde siempre, y un rechazo de una persona cuenta aunque llegue después | `test_f7_mira_si_la_cuenta_era_pagable_el_dia_del_cargo` |
| **Mayor.** K8 no veía «abierta en Exact, pagada en el banco»: con cero pagado Exact no deja aplicación y K8 no tenía con qué comparar | Desviación 27: el evento de cada importación de pagos de Exact lleva lo que dice de cada factura (también cero) y el día de la foto; la instantánea trae `exact_pagado` (lo último de cada factura) y K8 lo compara con lo que el banco había pagado hasta ese día | `test_pagos.py::test_exact_dice_abierta_y_el_banco_pagada_da_k8`, `test_reglas_paso7.py::test_k8_exact_dice_cero_y_el_banco_pagado` |
| **Mayor.** K1 y K3 decían «vencida y sin pagar» y «el banco no trae ese pago» sobre una rotura de la cadena (K6), y la cobertura del banco juntaba todas las cuentas | Desviación 30: con una rotura entre la fecha de la factura (K1) o del pago (K3) y lo que se mira, sin datos; la cobertura es por cuenta propia (la que empieza más tarde y la que acaba antes) | `test_k1_y_k3_no_dicen_sin_pagar_sobre_una_rotura_de_la_cadena` |
| Lo cobrado y pagado del flujo de caja salía de las aplicaciones de la fuente que manda, no del dinero que se movió: un cobro sin casar no contaba y una marca a mano sí | Desviación 28: lo movido son los movimientos del banco en euros salvo los traspasos entre cuentas propias; lo que no casa con ninguna factura va además en `sin_casar`, y lo que solo dicen Exact o una persona va en `segun_exact` y `a_mano`, sin sumarse | `test_flujo_caja.py::test_el_flujo_del_almacen_con_un_pago_parcial` (cambiado: ver abajo) |
| La separación de funciones de las órdenes de pago, prevista para el paso 7, no estaba | Desviación 29: cada marca y enlace a mano queda `autorrevisado` en su evento; confirmar una propuesta no la necesita (la escribe el motor, no una persona) | `test_un_pago_a_mano_cita_su_prueba_y_queda_autorrevisado` |
| `aplicacion_pago.evidencia_documento_id` existía pero nada la podía poner | `marcar_pagada` y su orden aceptan `evidencia_documento_id` (un documento que existe) | `test_un_pago_a_mano_cita_su_prueba_y_queda_autorrevisado` |

**Tests existentes cambiados, y por qué**: `test_flujo_caja.py::test_el_flujo_del_almacen_con_un_pago_parcial`
dice ahora que la marca a mano de 1000,00 va en `a_mano` y no en lo pagado,
y que un cargo sin casar sí es dinero pagado (y `sin_casar`), con un
traspaso a otra cuenta propia fuera (la decisión 5 pide lo que se movió; el
test probaba lo contrario). `test_pureza_reglas.py` conoce el tipo nuevo
`PagadoExact`, y `test_reglas_paso7.escenarios` gana una instantánea con la
foto de Exact para que K8 pase por sus dos ramas. Ninguno prueba menos.

Desviaciones nuevas, y por qué:

24. **K4 es de la parte, con una referencia de pago de verdad, y la ventana
    cuenta desde el primero.** La referencia es la estructurada, el
    end-to-end o el número (o la referencia de pago) de una factura que
    aparece en el concepto; nunca el concepto entero. Un pago doble a un
    proveedor sin número de factura en ningún sitio no se ve: decirlo de
    cada recibo mensual igual sería peor (bloquea y no se anula).
25. **Enlazar un movimiento a mano tiene tope.** Lo que queda del movimiento
    (con lo propuesto), su fecha, y nunca uno de una cuenta propia o de un
    beneficiario conocido. No hay una regla para un movimiento aplicado de
    más: los tres caminos que escriben una aplicación del banco (casar,
    enlazar y confirmar una propuesta, que ya llevaba como mucho lo que
    queda) lo impiden, y la base solo deja escribir por ellos.
26. **F7 mira el día del cargo.** Un pago a una cuenta pagable ese día no
    es un F7 aunque después saliera de Exact; la importación de partida
    cuenta desde siempre (si no, todo lo pagado antes del primer maestro
    sería F7). Un rechazo de una persona cuenta aunque llegue después: dice
    que la cuenta no es del proveedor, y lo pagado allí tampoco lo era.
27. **K8 compara con la foto de Exact, también cero, hasta su día.** Lo que
    dice Exact de cada factura va en el evento de su importación (no hay
    tabla para un pago de cero: una aplicación es de un importe distinto de
    cero) y la instantánea toma lo último de cada factura. Lo que el banco
    pagó después de la foto, Exact no lo podía saber: no es un desacuerdo.
28. **El flujo de caja cuenta el dinero que movió el banco.** Entero, case o
    no; lo de Exact o de una persona sin el banco va en líneas aparte y no
    se suma, porque nadie ha visto ese dinero moverse.
29. **La separación de funciones de los pagos es `autorrevisado`, sin
    segunda firma.** Quien marca una factura pagada la confirma en el mismo
    acto, y la migración 0007 no tiene una marca a mano sin confirmar
    (`manual ⇒ confirmada_por`): exigir otra persona con si_hay_dos
    bloquearía toda marca a mano en cuanto dos personas tengan
    `marcar_pagada`. Queda apuntado en el evento, y el control es K3 (el
    banco tiene que traer el pago) y el tope del enlace. Una marca con
    segunda firma pide un estado nuevo y una migración: es trabajo de un
    paso con la consola de pagos.
30. **K1 y K3 no afirman nada sobre una rotura de la cadena.** Sin datos si
    una rotura de K6 cae entre la fecha de la factura (o del pago) y lo que
    se mira; la cobertura es por cuenta propia de la política que tiene
    extractos.
31. **En MT940 un número de extracto repetido o 0 lo deciden los saldos.**
    Una página que falta con apuntes que se anulan entre sí (+100 y −100)
    no se vería; lo mismo pasa con los CSV, que no tienen saldos.
32. **Un CAMT con apuntes en otra moneda se suma igual** con los de la
    moneda de la cuenta: si no dan los saldos, no entra. Un banco que
    apuntara en otra moneda moviendo el saldo en euros dejaría el extracto
    fuera, que es lo prudente (decisión 6).
33. **No se marca a mano lo que ya dicen el banco o Exact.** La marca no
    contaría; se enlaza el movimiento o se corrige en Exact.
34. **Casar automático pide el importe exacto.** La tolerancia solo decide
    si una factura está pagada (`reglas.pagos.saldo`).

## Paso 8

Facturas de venta, relaciones entre facturas y las vistas de proveedores y
clientes. **1550 tests pasan** tras la revisión (929 funciones de test; eran
1534 y 913 al cerrar el paso, y 1467 y 877 al cerrar el paso 7), ninguno llama a la API y ninguno escribe fuera de una
carpeta temporal. Cinco mil facturas se recalculan en 1,57-1,83 s la primera
vez y en 1,35-1,52 s las siguientes (seis medidas en este contenedor; el paso
7 medía 1,73-1,88 s y 1,50-1,55 s): casar las copias y proponer relaciones
al principio de cada pasada cuesta unos milisegundos sin relaciones ni citas.

**La V1 no crea facturas ni borradores.** Las de venta solo se importan de
Exact o se leen de su PDF, y una relación solo enlaza dos facturas que ya
existen.

El paso se retomó de un trabajo sin terminar (guardado con `git stash` como
`paso8-wip` cuando un reinicio del contenedor lo cortó antes del commit). Se
revisó entero antes de seguir; lo que se cambió de aquel trabajo está al
final, en «Lo que se corrigió del trabajo retomado».

### Qué se construyó

**Migración `0008_ventas_relaciones.sql`** (la siguiente libre):

- `factura_cita` (controlada, guardas generadas): una factura que un
  documento nombra, tal como la nombra (número, fecha, la frase literal y la
  relación que enuncia: `credits`, `corrects`, `replaces`, `cancels`,
  `refers_to` o `unknown`). Sale de `related_invoices` (extracción v2) o de la
  «Gerelateerde factuur» de Exact. No dice qué factura es: eso lo decide el
  código casando el número.
- En `factura_relacion` (de la 0002): un índice único parcial (entre dos
  facturas, una relación viva como mucho) y tres disparadores: una relación
  manual la da de alta una persona activa con `anular_acreditar` en su propia
  orden y entra **confirmada**; una de la extracción o de Exact la escribe el
  sistema y entra **propuesta**; confirmar, rechazar o retirar es de una
  persona con `anular_acreditar`, solo sobre una propuesta (o retirando una
  decidida), y una vez; y lo decidido no cambia de tipo, importe ni facturas
  (se retira y se enlaza otra). El disparador de la 0002 sigue exigiendo el
  mismo sentido en las dos facturas.
- `factura_estado` (caché) se rehace con el estado de pago `acreditada`.
- Vistas: `v_factura_relaciones` (lo acreditado y si otra la sustituye, lo
  mismo que `reglas.relaciones.efectos` en SQL), `v_factura_saldo` rehecha
  (resta lo acreditado, como pedía el paso 7), `v_imputacion_vigente`,
  `v_iva_vigente`, `v_proveedor_totales` y `v_cliente_totales` (solo lo que
  cuenta: ni anuladas, ni fusionadas, ni sustituidas o corregidas).

**Módulos nuevos**

| Módulo | Qué hace |
| --- | --- |
| `relaciones.py` | Lo que propone el sistema y lo que deciden las personas. `sincronizar()` (al principio de cada pasada del motor, como `pagos.conciliar`): une a su venta de Exact o TRNSPRNT la copia en PDF que tiene el mismo sentido, número normalizado y contraparte resuelta, y propone la relación de cada cita cuyo número casa con una sola factura de la misma contraparte y sentido (retira las propuestas que ya no sostiene ninguna cita; lo que una persona rechazó o retiró no se vuelve a proponer). `enlazar`, `confirmar` (con el tipo o el importe corregidos si hace falta), `rechazar` y `retirar`, con sus comprobaciones. `efectos(conn)`, `de_factura` y `propuestas` |
| `reglas/relaciones.py` | Puro: `efectos()` (lo que mueve cada relación confirmada) y R1-R5 |
| `importadores/ventas.py` | Puro: junta las filas de un listado de ventas (una por línea, con la cabecera repetida) en facturas enteras; rechaza la factura cuyas filas no dicen lo mismo de la cabecera o repiten un número de línea |
| `config/importacion/exact-facturas_venta-v1.yaml` | El mapeo de las verkoopfacturen de Exact con sus regels (proyecto o centro de coste como Objeto), con su ejemplo y su contrato en `tests/fixtures/importacion/` |

**Lo que mueve una relación confirmada** (`reglas.relaciones.efectos`, la
única cuenta, que leen la instantánea, las cachés, los pagos, la caja y las
consultas):

| Tipo | Efecto |
| --- | --- |
| (todas) | Solo mientras sus dos facturas cuentan: una relación cuyo origen está anulado, o con una de las dos fusionada en otra, no mueve nada (revisión, migración 0009) |
| `acredita`, `anula` | El abono le quita a la original lo que dice la relación (o el abono entero) y se gasta ese importe del abono. Las dos siguen en los totales y en el IVA, cada una en su fecha: se compensan. Si cubre lo que quedaba sin pagarse nada, la original queda `acreditada` (`anulada` si el abono la anula); si no, le baja lo pendiente |
| `sustituye`, `corrige` | La original sale de juego: de los totales, de la caja, del IVA, de los agregados de prioridad y de las reglas (salvo R3, que la mira para eso). Su estado de pago es `anulada` |
| `relacionada` | Nada, y tampoco calla un duplicado |

**Reglas nuevas**

| Regla | Qué mira | Al fallar |
| --- | --- | --- |
| R1 | Un abono o una corrección nombra una factura de la misma contraparte que no está, o que está repetida | Retención; se anula |
| R2 | Los abonos confirmados le quitan a una factura más de lo que vale, o un abono se aplica por más de lo que vale | Retención; pegajosa, no se anula |
| R3 | La original y la que la sustituye (o corrige) están las dos pendientes, las dos pagadas, o la original pagada y la nueva pendiente | Bloqueo; pegajosa, no se anula |
| R4 | Un abono sin ninguna relación confirmada que diga a qué abona | Aviso |
| R5 | Una relación propuesta espera a una persona (sobre las dos facturas) | Aviso |
| V7 | En las ventas, el caso de B2 (mismo número a la misma contraparte) o el de B3 (mismo importe a pocos días, otro número): facturar dos veces | Retención; se anula; pegajosa; suelo urgente |
| F10 | Una venta lleva un IBAN que no es una cuenta de BM Support BV (`cuentas_propias`); sin cuentas propias cargadas, sin datos | Retención; pegajosa, no se anula |
| M3 | Una venta de Exact (o TRNSPRNT) y su PDF no dicen lo mismo (fecha, base, IVA, total, tipo, periodo), o tienen el mismo número y no se pudieron unir (y dice por qué) | Retención, calidad «discrepancia»; se anula |

D1, D2 y D2b ya retenían en una venta (`severidad_saliente`, paso 3); ahora
hay ventas que lo prueban. A8 ya bloqueaba una venta que no emite BM Support
BV (paso 5); ahora deja fuera lo que llega estructurado de Exact o TRNSPRNT,
que no tiene emisor impreso.

**La vía de salida.** `bms-agent extract --salientes carpeta/` lee las
facturas emitidas por BM Support BV: entran con `ruta_declarada = 'saliente'`
y sus extracciones se guardan en `out/salientes/`. `importar-out` lee `out/`
por la vía de entrada y `out/salientes/` por la de salida: la carpeta decide
el sentido, nunca el documento ni el modelo. Lo que llega por la vía de
salida y no emite BM Support BV está mal encaminado y queda Bloqueado (A8).

**Las ventas de Exact.** `bms-agent importar exact facturas_venta fichero.csv`:
una fila por línea; `LectorAgrupado` (`tabular.py`) lee las filas con el mapeo
y `ventas.py` las junta por diario y número. Entra todo o nada (decisión 6):
un cliente que no está, otra moneda, un importe ilegible o dos filas de una
factura que no dicen lo mismo rechazan el fichero entero (Z2). Cada factura es
una orden de `campos.py` a nombre de Exact: la cabecera con su literal, el
plazo de las condiciones, las líneas por su número de línea de Exact (la que
ya no viene se retira con su imputación), una imputación por línea con el
Objeto del proyecto o del centro de coste (por código o alias; si no se
conoce, la línea queda sin Objeto), el IVA por tipo sumando las líneas, la PO
de la cabecera y de cada línea como referencia y la factura relacionada como
cita. Un listado posterior pone al día lo que cambió. Lo de Exact no lo edita
una persona aquí: se corrige en Exact.

**Órdenes nuevas** (`servicios.ACCIONES`, todas con `anular_acreditar` y
motivo obligatorio; salen en la CLI, en `POST /api/v2/acciones` y en la
consola):

| Orden | Qué hace |
| --- | --- |
| `enlazar_facturas` | Una persona enlaza dos facturas (abono, corrección, sustitución o relacionada; un abono parcial con su importe). Entra confirmada |
| `confirmar_relacion` | Confirma una propuesta, y puede corregir su tipo o su importe |
| `rechazar_relacion` | La rechaza: no mueve nada y no se vuelve a proponer |
| `retirar_relacion` | Retira una relación, también confirmada: deja de mover nada. No se borra |
| `deshacer_fusion` | Deshace una fusión (también la de una copia en PDF unida sola a su venta de Exact); el sistema no la vuelve a unir |

Quien enlaza o confirma cierra en la misma orden los B2, B3, B4 y V7 de esa
pareja que la relación hace desaparecer (pegajosos: si no, quedarían
desaparecidos esperando a otra persona); es el `_cerrar_b2` de la fusión,
generalizado como `_cerrar_duplicados`.

**Las vistas de proveedor (§3) y de cliente (§4)** (`consultas.proveedor`,
`cliente`, `proveedores`, `clientes`): lo pendiente y lo vencido (con cada
factura abierta), lo facturado del año y de siempre (base, IVA y total), lo
pagado o cobrado del año y de siempre, lo gastado o facturado y las horas por
Objeto (con un apartado «sin Objeto»), el historial de facturas con su estado
y el de pagos, el importe típico (media y mediana), el plazo de pago (media y
mediana de días) y los pagos que llegaron tarde, los avisos activos (los
hallazgos pendientes de sus facturas y de él, y sus excepciones abiertas) y,
en un proveedor, las cuentas del registro con su estado y, aparte, los IBAN
que imprimen sus facturas con su primera y última fecha; su nivel, sus
puntos y sus motivos (la caché `prioridad`), y en un cliente el trabajo sin
facturar, que da sin datos hasta el planning (revisión). Salen de lo mismo que
las reglas y la caché (`estados.facturas`: vencimiento efectivo, saldo con la
fuente que manda y lo acreditado), con el `hoy` del reloj del almacén.

**CLI y servidor**: `bms-agent proveedores|clientes [--json]`, `bms-agent
proveedor N|cliente N [--json]`, `bms-agent relaciones`, `extract
--salientes`, `importar exact facturas_venta`; `bms-agent factura N` enseña
sus relaciones; `coste` cuenta también lo pagado en `out/salientes/`.
`GET /api/v2/proveedores`, `/api/v2/proveedores/N`, `/api/v2/clientes`,
`/api/v2/clientes/N` y `/api/v2/relaciones` (token personal con
`ver_facturas`; 404 si no existe). La consola enseña en la ficha las
relaciones (con confirmar, rechazar, retirar y enlazar) y las facturas que
nombra el documento, y debajo de la lista las tablas de proveedores y
clientes, que abren su vista; todo con `textContent`.

**Cambios** en el resto: `campos.py` (`factura_cita` en el registro; una
factura de Exact o TRNSPRNT conserva la parte que le dio su sistema),
`dominio.py` (`EstadoPago.ACREDITADA`, `RelacionCitada`,
`RELACIONES_QUE_ACREDITAN` y `RELACIONES_QUE_SUSTITUYEN`), `canonico.py`
(`FilaVentaCanonica`, `LineaVentaCanonica`, `IvaVentaCanonico`,
`FacturaVentaCanonica`), `ingesta.py` (las citas de `related_invoices`, casadas
por posición como el desglose), `legado.py`, `estados.py`, `pagos.py`,
`flujo_caja.py`, `hallazgos.py` (la pasada sincroniza antes de casar el
banco), `revision.py` (las citas entran en la huella del contenido),
`reglas/base.py` (`Factura.origen`, `acreditado_cent`, `sustituida_por`;
`Relacion` con id, importe y fuente; `Cita`; `Instantanea.propuestas` y
`citas`; `en_juego()`), `reglas/instantanea.py`, `reglas/pagos.py` (el saldo
resta lo acreditado), `reglas/unicidad.py`, `reglas/bancaria.py`,
`reglas/calidad.py`, `reglas/identidad.py`, `reglas/catalogo.py`; README y
`docs/validacion-facturas.md` (sección R, V7, F10, M3 y las ventas en D).

### La puerta, test por test

| Puerta | Tests |
| --- | --- |
| La vía decide el sentido, y un documento de la vía de salida mal encaminado queda Bloqueado | `test_ventas.py::test_la_via_decide_el_sentido_y_una_venta_que_no_emite_bms_queda_bloqueada` (el mismo documento de Van Dijk por las dos vías: compra, y venta Bloqueada por A8; una venta que emite BMS no; el panel de compras no ve la venta), `test_extract_con_salientes_guarda_aparte_y_entra_por_la_via_de_salida` (`extract --salientes` con un cliente falso, `out/salientes/`, una sola llamada, `importar-out` en otra base vuelve a la vía de salida, `coste` lo cuenta), `test_ingesta.py::test_la_direccion_la_pone_la_via_de_entrada` (sigue), `test_reglas_paso8.py::test_a8_no_mira_el_emisor_de_una_venta_de_exact` |
| Un abono entero deja la original acreditada; uno parcial le baja el saldo | `test_un_abono_que_cubre_la_factura_la_deja_acreditada` (propuesto por la extracción no mueve nada; confirmado, `acreditada`, fuera de lo abierto y de la caja), `test_un_abono_parcial_confirmado_baja_lo_pendiente_de_la_original` (el de Exact: la vista SQL, la caché, la caja, R4 y R5 cerrados, el IVA de las dos), `test_un_abono_parcial_enlazado_a_mano_baja_lo_pendiente` (y retirarlo lo deja como estaba), `test_los_abonos_no_le_quitan_a_una_factura_mas_de_lo_que_vale` (R2), `test_reglas_paso8.py::test_un_abono_entero_acredita_y_uno_parcial_baja_lo_pendiente` |
| Una sustituida o corregida sale de los totales, la caja y el IVA | `test_la_factura_sustituida_o_corregida_sale_de_los_totales_la_caja_y_el_iva[confirmar, sustituye, corrige]`: `v_proveedor_totales`, la vista del proveedor, los totales de la `Diferencia`, `v_imputacion_vigente`, el flujo de caja, `v_iva_vigente` y D3 en `no_aplica` |
| B4 no salta con una pareja confirmada | El mismo test (el B4 de la pareja se resuelve en la orden y no vuelve en la pasada siguiente), `test_reglas_paso8.py::test_la_sustituida_sale_de_juego_y_de_las_reglas`, y `test_una_relacion_cualquiera_no_calla_un_duplicado` (una «relacionada» no lo calla) |
| Exact frente al PDF es una discrepancia | `test_el_pdf_de_una_venta_de_exact_se_une_a_ella_y_lo_distinto_es_una_discrepancia` (la copia se une sola, M3 retiene con calidad «discrepancia» y la caché de la venta lo dice), `test_una_copia_igual_no_es_una_discrepancia`, `test_un_pdf_con_el_numero_de_una_venta_de_exact_y_otro_cliente_es_una_discrepancia`, `test_una_persona_deshace_la_union_de_una_copia_y_no_se_vuelve_a_unir`, `test_reglas_paso8.py::test_m3_la_venta_de_exact_y_su_pdf_no_dicen_lo_mismo` |
| Propiedad: lo pendiente de un proveedor es la suma de sus facturas pendientes | `test_lo_pendiente_de_cada_parte_es_la_suma_de_sus_facturas_abiertas[0-5]`: seis escenarios al azar (pagos parciales, enteros y de más, abonos enlazados, sustituciones y correcciones, ventas de Exact); para cada proveedor y cada cliente, la vista, su lista, la suma de sus facturas abiertas, la caché `factura_estado` y la vista SQL dan lo mismo, y lo vencido es la suma de sus vencidas |

Además: el listado de ventas de Exact (`test_las_ventas_de_exact_entran_con_su_cliente_sus_lineas_y_su_objeto`,
reimportar no hace nada, todo o nada en cuatro casos, un listado posterior que
pone al día una venta y que una persona no edita), V7 y no B2 en las ventas,
F10, D2 que retiene una venta y bloquea una compra, la base que no deja al
sistema confirmar ni a una persona proponer, ni relacionar una compra con una
venta (la orden y el disparador) ni dos contrapartes, las dos vistas con sus
cifras (plazo de pago, pagos tarde, cuentas, por Objeto), la CLI, la API (con
los permisos) y la consola pintando como texto un cliente con `<script>` en
el nombre (`test_la_consola_pinta_la_vista_de_un_cliente_como_texto`). Las
reglas, rama a rama sobre instantáneas, en `test_reglas_paso8.py`, y sus
escenarios en la prueba de pureza.

### Desviaciones de la especificación, y por qué

1. **Migración 0008**, no la que numera el §11 (el número es su orden).
2. **`factura_cita` es una tabla nueva** que el §5 no tiene. El §5 deja que
   la extracción proponga relaciones, y la decisión 20 dice que solo se
   proponen; la decisión 19 (el modelo transcribe, el código decide) pide
   guardar lo que dice el documento aparte de lo que el código deduce. Sin ella, una cita que no casa (R1) no tendría dónde estar, y una
   factura que llega después no podría recibir su propuesta.
3. **Las propuestas las escribe el sistema en cada pasada**
   (`relaciones.sincronizar`), no la ingesta ni la importación: una factura
   que llega después del abono que la nombra recibe su propuesta en la pasada
   en que llega. La base no deja que el sistema confirme nada. Una relación
   manual entra confirmada (la escribe quien decide), y lo que una persona
   rechazó o retiró no se vuelve a proponer.
4. **Entre dos facturas, una relación viva como mucho** (índice único): dos
   relaciones distintas entre la misma pareja no tienen un significado que
   las reglas puedan leer.
5. **«Cancelled / Credited» son dos estados**: `anulada` (a mano, por un
   abono que la anula o porque otra la sustituye o la corrige) y `acreditada`
   (los abonos confirmados cubren lo que quedaba sin pagarse nada), como
   anunciaba el registro del paso 7. Un abono gastado entero también queda
   `acreditada`. La caché `factura_estado` se rehace en la 0008 para admitir
   el valor.
6. **Una relación «relacionada» no calla un duplicado.** El §7 dice que B4
   no mira las relaciones confirmadas; aquí solo las que explican el parecido
   (abono, corrección, sustitución). Si no, enlazar dos facturas cualesquiera
   sería la forma de quitar un B2 o un B4 sin decir qué es una de la otra.
7. **Se relacionan facturas de la misma contraparte**, y un abono solo
   acredita o anula una factura (no otro abono), por como mucho lo que vale y
   en el signo de la original; la que sustituye o corrige es una factura. Lo
   comprueba la orden; la base sigue comprobando el mismo sentido.
8. **R3 bloquea hasta que la original se anula o se abona.** Confirmar una
   sustitución saca la original de los totales, pero en la contabilidad (y en
   Exact) la original sigue abierta hasta que alguien la anula o la abona: si
   las dos están pendientes, la de antes se podría pagar también. Es la
   lectura que deja viva la mitad «las dos pendientes» de R3, que si no nunca
   se daría. El camino es `anular_factura` (o enlazar su abono), y R3, que es
   pegajosa, queda desaparecida hasta que una persona la cierra. R3 no está
   entre lo que cierra la orden que enlaza o confirma: desaparece con otra
   orden y otra pareja.
9. **B2 y B3 miran solo las compras**; en las ventas da `no_aplica` y lo mira
   V7, que retiene. El §7 no dice el sentido de B2 y B3, pero dice que V7 son
   «los casos de B2, B3 o B5 en las ventas»: con las dos, una venta repetida
   bloquearía por B2 y retendría por V7 a la vez. El caso de B5 en V7 (las
   horas de un turno cobradas dos veces) llega con el planning (paso 10).
10. **M3 es una regla nueva** que el §7 no tiene: es como se cumple la
    puerta «un desacuerdo entre Exact y el PDF es una discrepancia», al lado
    de M1 y M2. Para comparar, el PDF de una venta que también llegó de
    Exact o TRNSPRNT **se une solo a ella** (`fusionada_en_id`, fuente
    `calculado`) cuando tienen el mismo sentido, número normalizado y
    contraparte resuelta, el PDF lo emite BM Support BV y no lleva ni un pago
    apuntado ni una relación confirmada (revisión): cuenta la de Exact y la
    copia no suma dos veces. **El §10 no se cumple en la lectura**: dice que
    el PDF de una venta solo se lee si no hay fuente estructurada, y
    `extract --salientes` lee (y paga) cada PDF de la carpeta aunque Exact ya
    tenga esa venta. No se puede saber qué venta es un PDF sin leerlo (el
    número sale de la lectura), y negarse a leer la carpeta entera cuando hay
    un listado de Exact dejaría sin leer las ventas que Exact no exporta. Lo
    que sigue al §10 es el recuento (cuenta la de Exact), y un PDF ya leído
    por cualquiera de las dos vías no se vuelve a pagar. M3
    compara fecha, base, IVA, total, tipo y periodo, y también avisa de un PDF
    con el número de una venta de Exact que no se pudo unir (otro cliente, o
    sin resolver). `deshacer_fusion` es la orden nueva que lo deshace; con el
    valor puesto por una persona, el sistema no la vuelve a unir.
11. **Una factura de Exact o TRNSPRNT conserva su parte** (`campos.py`): no
    imprime receptor, y volver a resolver las referencias la dejaba sin
    cliente. A8 no la mira por lo mismo: no hay un emisor impreso que pueda
    estar mal encaminado.
12. **F10 retiene, es pegajosa y no se anula** (el §7 dice R; la base ya no
    deja anular ninguna F), y mira también la copia en PDF unida a una venta
    de Exact: es lo que vio el cliente. Sin cuentas propias cargadas da sin
    datos, nunca ok.
13. **Las extracciones de la vía de salida van a `out/salientes/`.**
    `importar-out` tiene que saber la vía de cada fichero, y una venta
    mezclada en `out/` volvería al almacén como compra. Un documento conserva
    la vía por la que entró la primera vez (la evidencia no cambia): un PDF ya
    leído como compra no pasa a venta por dejarlo después en la carpeta de
    ventas.
14. **El panel de siempre es de compras.** `registros_legado` (y con él
    `registros_resueltos`, el panel, el informe, la exportación y
    `/api/datos`) deja fuera lo que llegó por la vía de salida: el contrato v1
    trata cada registro como una factura de proveedor, y una venta contaría
    como gasto, entraría en la proyección y en los duplicados de los
    proveedores (huecos.md §2, acoplamiento 1). La foto de referencia no
    cambia. Ese panel sigue contando las sustituidas, como ya contaba las
    fusionadas: lo que sale de los totales es lo del almacén (vistas,
    consultas, caja, IVA, `Diferencia` y prioridades); el contrato v2 es del
    paso 12.
15. **El mapeo de ventas de Exact está hecho contra un ejemplo sintético**
    (el formato real no se conoce, como el de pagos del paso 7). Una línea
    cuyo proyecto o centro de coste no es un Objeto conocido entra sin Objeto
    (no rechaza el fichero): es lo mismo que una línea leída de un PDF, se ve
    como «sin Objeto» en las vistas y la imputa una persona; V2 (paso 10) la
    convertirá en hallazgo. Un número de línea que Exact ya retiró y vuelve se
    rechaza: Exact no reutiliza números de línea.
16. **`v_iva_vigente` en vez de `v_btw_linea`.** La vista del §5 lleva la
    rúbrica de la declaración, que es del paso 11 (con el contador); la de
    ahora es el IVA que cuenta con su trimestre, y la del paso 11 la leerá.
17. **No hay `v_cliente_cobro`.** El plazo de cobro y los retrasos son una
    estadística, y el §5 los deja en Python (`consultas._plazos`), con `hoy`
    inyectado como lo demás que depende de la fecha.
18. **Cómo se cuentan las vistas** (las preguntas 10 del §12 y las de
    huecos.md §3 y §4 siguen abiertas): el año es el natural, por la fecha de
    la factura (lo facturado) o del pago (lo pagado); lo pagado es lo de la
    fuente que manda (banco, Exact, a mano); lo pendiente incluye un abono sin
    aplicar, en negativo; el importe típico es la media y la mediana de la
    base de las facturas (sin abonos); el plazo de pago va de la fecha de la
    factura al último pago de una factura pagada (una solo acreditada no
    cuenta), y llega tarde si ese día es posterior al vencimiento efectivo.
19. **Tests existentes cambiados, y por qué**: `test_alcance_v1.py` (el
    estado de pago `acreditada`); `test_campos.py` (una relación manual entra
    confirmada: la base ya no admite una manual propuesta);
    `test_hallazgos.py` (el abono 04 da R4, así que hay un hallazgo más; en el
    test de barajar, la factura corregida con una relación confirmada sale de
    juego; R1-R5, V7, F10 y M3 solo dicen objeciones); `test_importadores.py`
    (el mapeo nuevo); `test_reglas.py` (el catálogo y las familias
    pegajosas con R2 y R3); `test_pureza_reglas.py` (el módulo, el tipo `Cita`
    y los escenarios del paso 8); `test_reglas_paso7.py` (el saldo lleva lo
    acreditado); `test_servicios.py` (las cinco órdenes en la matriz y en
    `CASOS`, y la foto de totales con la marca de sustituida). Ninguno prueba
    menos que antes.

### Lo que se corrigió del trabajo retomado

El trabajo guardado pasaba sus tests, pero ninguno probaba las puertas sobre
el almacén entero. Al escribirlos y repasar el código salió esto:

| Qué | Qué se hizo |
| --- | --- |
| `coste` no contaba lo pagado por la vía de salida (`out/salientes/`): una venta leída con `extract --salientes` no aparecía en lo gastado | `coste` lee también `out/salientes/` (lo gastado y lo que costaría relanzar); lo prueba el test de `extract --salientes` |
| `bms-agent relaciones` explicaba la orden con una sintaxis que la CLI no admite (`relacion_id=N`) | Dice `bms-agent accion confirmar_relacion --relacion-id N --rev R --motivo ...`, y el test de la CLI lo comprueba |
| El docstring de `relaciones.py` prometía que una persona podía deshacer la unión de una copia, y ninguna orden lo hacía (`fusionar_factura` solo une) | La orden `deshacer_fusion` |
| No había nada que probara «fuera del IVA» | `v_iva_vigente` |
| R3 estaba entre lo que cierra la orden que enlaza o confirma, pero nunca desaparece por esa orden | Fuera de la lista; la desviación 8 dice por qué |
| Los imports de seis módulos de reglas se habían reordenado, y quedaban `relaciones.cuenta()` y una constante sin usar | Vuelven al orden de siempre (constantes, clases, funciones) y lo que no se usa se quita |

### Lo que deben saber los pasos siguientes

- **Lo que mueve una relación** se calcula en un solo sitio,
  `reglas.relaciones.efectos` (y `relaciones.efectos(conn)` sobre el
  almacén); `v_factura_relaciones` es lo mismo en SQL. Lo que sume importes,
  saldos o IVA tiene que mirar `sustituida_por` y `acreditado_cent`
  (`reglas.base.en_juego`, o las vistas `v_imputacion_vigente` y
  `v_iva_vigente`). Una relación solo la escriben `relaciones.py` (personas,
  por sus órdenes) y `sincronizar` (propuestas).
- **Paso 9 (POs)**: el consumo es la base de `v_imputacion_vigente` (ya sin
  anuladas, fusionadas ni sustituidas) menos los abonos confirmados. Ojo: las
  líneas de un abono están en `v_imputacion_vigente` con importe negativo
  aunque nadie haya confirmado a qué abona; el §7 pide restar solo lo
  confirmado, así que el consumo tiene que mirar si el abono tiene relación
  confirmada. Las PO de una venta de Exact ya están en `factura_referencia`
  con la etiqueta `PO`, sin casar.
- **Paso 10 (planning)**: V1-V6, V8 y V9 sobre las ventas, el caso de B5 en
  V7, y que una línea de venta sin Objeto sea un hallazgo (V2). Las horas por
  Objeto de las vistas salen de las imputaciones; el planning añade las
  planificadas.
- **Paso 11 (BTW)**: el IVA que cuenta es `v_iva_vigente` (un abono en su
  trimestre, la sustituida fuera); el desglose por tipo de las ventas de Exact
  ya está en `factura_iva`.
- **Paso 12**: la propiedad «lo facturado por Objeto más lo que no tiene
  Objeto es la base de las ventas» ya tiene sus datos (`v_imputacion_vigente`
  por sentido); la de lo pendiente de un proveedor está probada aquí. El
  panel v1 sigue siendo de compras y sigue contando sustituidas y fusionadas.
- **Una regla nueva sobre ventas** tiene que mirar `factura.origen`: lo que
  llega de Exact o TRNSPRNT no imprime emisor ni receptor, y su copia en PDF
  está fusionada en ella.
- **La consola** tiene ya relaciones y vistas de proveedor y cliente; la vista
  de pagos y la del flujo de caja siguen pendientes (paso 7).

### Correcciones de la revisión

La revisión del paso 8 dejó dieciocho hallazgos. Dos estaban dichos dos
veces (la copia en PDF de un abono confirmado que se une sola y acredita dos
veces, y la relación que sigue moviendo dinero con su origen anulado), así
que son dieciséis. Cada uno se reprodujo antes de tocarlo (con los scripts
del revisor y con el test nuevo contra el código del paso 8: los tests nuevos
de lo que se arregla fallan sin las correcciones). Todos eran reales. Doce se
arreglan en el código con su test; uno se documenta, con un test que lo fija
(lo pendiente bruto de las vistas SQL con tolerancia); y tres no se cambian y
se apuntan como desviaciones con su razón (el §10 en la lectura, D2/D3/D4 en
las ventas y el recurso desconocido de una venta de Exact). **1550 tests pasan** (929 funciones de test; eran
1534 y 913). Sin una sola llamada a la API. Cinco mil facturas se recalculan
en 1,51-1,63 s la primera vez y en 1,31-1,46 s las siguientes (seis medidas):
lo mismo que antes.

| Hallazgo | Qué se hizo | Test |
| --- | --- | --- |
| **Mayor** (dos hallazgos). `sincronizar` unía sola a su abono de Exact la copia en PDF que ya tenía una relación confirmada: la relación seguía contando desde la copia, se proponía la misma sobre el de Exact y confirmarla acreditaba dos veces la original, por debajo de su total (sin R2) | Desviación 20: `_copias` no une una copia con una relación confirmada (una propuesta sí: se retira en la misma orden y se propone sobre la de Exact). `_propuestas` no propone lo que ya tiene una gemela (otra factura con el número y la contraparte del origen) con ese destino, y `enlazar`/`confirmar` se niegan (`RelacionNoValida`). `fusionar_factura` no fusiona una factura con una relación confirmada o un pago apuntado. M3 dice por qué no se unieron (`distintos.union`) | `test_ventas.py::test_el_pdf_de_un_abono_ya_confirmado_no_se_une_solo_ni_acredita_dos_veces` |
| **Mayor.** La misma unión se tragaba un cobro apuntado en el PDF: la venta volvía a estar pendiente entera y el cobro quedaba en una copia que nadie cuenta | Desviación 20: `_copias` no une una copia con un pago propuesto o confirmado; M3 lo dice y el cobro sigue a la vista | `test_el_pdf_de_una_venta_ya_cobrada_no_se_une_solo_y_el_cobro_no_se_pierde` |
| **Mayor** (dos hallazgos). Una relación confirmada seguía moviendo dinero con su origen anulado: un abono anulado seguía acreditando y una sustituta anulada seguía sacando a la original de los totales, la caja y el IVA, sin ningún hallazgo | Desviación 21: `instantanea.relaciones` (y con ella `relaciones.efectos`, las cachés, la caja y las consultas) solo cuenta como confirmada la que tiene su origen sin anular y ninguna de las dos fusionada; `v_factura_relaciones` dice lo mismo en la migración nueva **0009** (la 0008 no se edita). `anular_factura` no anula el origen de una relación confirmada que mueve algo (se retira antes, a la vista), `_comprobar` no enlaza ni confirma desde una factura anulada, y `relaciones.de_factura` dice si cada relación `mueve` | `test_una_relacion_cuyo_origen_esta_anulado_no_mueve_nada`, `test_una_sustituta_anulada_devuelve_la_original_a_los_totales` |
| **Mayor.** Una original ya pagada con una corrección o sustitución confirmada pasaba a «anulada», su pago desaparecía de las vistas y la nueva salía pendiente entera, sin R3 | Desviación 22: R3 tiene un tercer caso (la original pagada con dinero y la nueva pendiente: bloquea, pegajosa, no se anula; «abona la original o paga solo la diferencia»). Una sustituida pagada con dinero queda `pagada`, no `anulada`; lo pagado de una sustituida cuenta en lo pagado de `consultas` (y en sus pagos) y en `pagado_cent` de `v_proveedor_totales` y `v_cliente_totales` (0009); lo facturado y lo pendiente siguen sin ella | `test_una_original_ya_pagada_y_sustituida_bloquea_y_su_pago_sigue_a_la_vista`, `test_reglas_paso8.py::test_r3_la_original_y_la_que_la_sustituye_no_se_pagan_las_dos` |
| Una propuesta que el sistema retiró porque la cita se volvió ambigua (un reenvío con el mismo número) no se volvía a proponer nunca | `_propuestas` no cuenta en lo que «ya hubo» una propuesta retirada por el sistema (la retirada con fuente `calculado` en `cambio_campo`); lo que rechazó o retiró una persona sigue sin proponerse | `test_una_propuesta_que_retiro_el_sistema_se_propone_otra_vez` |
| El evento de un listado de ventas rechazado contaba como nuevas las filas de las facturas que la transacción deshizo | `_Contexto.marca` y `olvidar_desde`: si una factura no entra, se olvida lo anotado desde antes de la transacción | `test_un_listado_de_ventas_rechazado_no_cuenta_como_nuevo_lo_que_se_deshizo` |
| Con tolerancia de pago, `v_proveedor_totales` y `v_cliente_totales` no dan lo mismo que `consultas` ni que la caché | Desviación 23: se documenta (en la 0009 y aquí) que lo pendiente de las vistas SQL es el bruto, sin la tolerancia, que es de la política y vive en Python; el test lo fija con 0,05 | `test_con_tolerancia_la_vista_sql_es_lo_que_queda_en_bruto` |
| La primera fecha de un IBAN impreso quedaba vacía si la primera factura no tenía fecha | `_ibanes` ordena las sin fecha al final y no deja la primera vacía | `test_la_primera_fecha_de_un_iban_impreso_no_la_borra_una_factura_sin_fecha` |
| **Mayor** para el dinero, menor en el código. `extract --salientes` y `extract` tenían cachés separadas: el mismo PDF por la otra vía se pagaba otra vez, y no cambiaba nada (el documento conserva su vía) | `extraer_pasada(otras_vias=...)`: la CLI le pasa la carpeta de la otra vía (`out/` o `out/salientes/`); lo leído allí se reutiliza sin coste y se avisa de que la vía no cambia. Con `--force`, no | `test_un_pdf_ya_leido_por_la_otra_via_no_se_paga_otra_vez` |
| Un PDF de otro emisor con el número y el cliente de una venta de Exact se unía solo a ella: A8 no lo bloqueaba nunca y no quedaba ningún hallazgo | `_copias` solo une la copia que emite BM Support BV (`reglas.identidad.es_la_empresa`, la misma prueba que A8); si no, A8 bloquea y M3 dice `emisor` | `test_un_pdf_que_no_emite_bms_no_se_une_a_la_venta_y_queda_bloqueado`, `test_reglas_paso8.py::test_m3_dice_por_que_no_se_unio_la_copia` |
| En la vía de salida, un documento sin emisor y dirigido a BM Support BV (una compra dejada en la carpeta de ventas) daba sin datos | A8: sin emisor y con el receptor de la empresa (nombre o btw-id), bloquea como compra mal encaminada | `test_una_compra_sin_emisor_dejada_en_la_carpeta_de_ventas_queda_bloqueada`, `test_reglas_paso8.py::test_a8_una_venta_sin_emisor_dirigida_a_bms_es_una_compra_mal_encaminada` |
| El §10 dice que el PDF de una venta solo se lee si no hay fuente estructurada, y la desviación 10 lo daba por cumplido | No se cambia el código: la desviación 10 dice ahora que la lectura no lo cumple y por qué (un PDF no dice qué venta es sin leerlo); lo que sigue al §10 es el recuento, y un PDF ya leído por cualquier vía no se paga otra vez (hallazgo anterior) | — |
| La vista de un cliente no tenía «trabajo sin facturar» (§4) y ninguna vista ni lista decía la prioridad de la parte, ni las listas iban en el orden del §8 | `consultas`: cada vista lleva `prioridad` (nivel, puntos, motivos, de la caché `prioridad`), la del cliente `trabajo_sin_facturar` en sin datos hasta el planning (V6, paso 10; nunca cero), y las listas llevan nivel, puntos y motivos y se ordenan con `prioridad.clave_orden` (a igualdad, por nombre) | `test_las_listas_de_partes_van_en_el_orden_de_prioridad_y_lo_dicen` |
| D2, D3 y D4 no se anulan en las ventas, y el registro del paso 3 dejaba al paso 8 relajarlas | No se cambia: desviación 24 | — |
| Un recurso (Medewerker) que no se conoce en una venta de Exact se quedaba sin recurso y sin hallazgo | No se cambia: desviación 25 | — |
| Una venta de Exact no podía tener fecha de envío ni contacto del maestro | `fecha_envio` deja de ser de Exact (`externo`): Exact no la exporta, y una persona la apunta con su procedencia (huecos.md §2). `contacto_id` se calcula del nombre de contacto por su nombre exacto entre los contactos activos de la misma contraparte (uno solo), y se vuelve a resolver al importar contactos (`RESUELVEN`, `reconciliar_referencias`) | `test_una_venta_de_exact_tiene_su_contacto_del_maestro_y_su_fecha_de_envio_a_mano` |

**Tests existentes cambiados, y por qué**: ninguno cambia lo que prueba.
`test_reglas_paso8.py::test_r3_...` gana el caso de la original pagada (el de
la nueva pagada y la original sin pagar sigue sin saltar: es lo normal), y
`test_reglas_paso8.escenarios` gana una instantánea con R3 en su caso nuevo,
A8 de una compra sin emisor en la vía de salida y M3 de copias que no se
unieron por un pago, una relación o el emisor, para que la prueba de pureza
pase por esas ramas.

Desviaciones nuevas, y por qué:

20. **Una copia en PDF que ya lleva dinero no se une sola.** Ni un pago
    (propuesto o confirmado) ni una relación confirmada: moverlos a la venta
    de Exact es decidir a qué factura van, y eso es de una persona. Hasta
    entonces las dos cuentan y M3 retiene diciendo por qué; el camino es
    retirar el pago o la relación de la copia, fusionarla a mano y confirmar
    lo de la de Exact. `fusionar_factura` exige lo mismo a una persona, y no
    se puede enlazar la de Exact con la misma original mientras su gemela lo
    esté (sería el mismo abono dos veces).
21. **Una relación solo mueve algo mientras sus dos facturas cuentan.** Con
    el origen anulado o una de las dos fusionada no mueve nada, en Python y
    en SQL (0009). La original anulada sí deja que la relación mueva (es lo
    que pide R3: anular la que se sustituye). Anular el origen de una
    relación que mueve algo se niega; la relación se retira antes, a la
    vista. No hay una regla nueva para una relación así: por las órdenes ya
    no se llega a ella, y la que quede de antes de la 0009 simplemente deja
    de mover (`de_factura` dice `mueve: false`).
22. **R3 salta también con la original pagada y la nueva pendiente**, y la
    sustituida pagada sigue «pagada» y su pago a la vista. No se descuenta lo
    pagado de la nueva: sería decidir que ese dinero paga la nueva, y quizá
    el proveedor lo abone o lo devuelva. La nueva pagada con la original sin
    pagar sigue sin saltar, como decía el test del paso 8 («lo normal»).
23. **Lo pendiente de `v_proveedor_totales` y `v_cliente_totales` es el
    bruto.** La tolerancia de pago es de la política (reglas.yaml) y una vista
    no la conoce; con la de por defecto (0,00) dicen lo mismo que `consultas`
    y la caché, como prueba la propiedad. Con otra, la diferencia es lo que
    queda dentro de la tolerancia de cada factura pagada.
24. **D2, D3 y D4 no se anulan tampoco en las ventas**, como dice la tabla del
    §7 («no override» sin distinguir el sentido). La decisión 12 da la lista
    dura de la base (D2/D3/D4/D6 en las compras); no pide que en las ventas
    se anulen. Una venta con la aritmética mal se corrige donde nace (en
    Exact, o el campo leído del PDF), nunca se acepta: una venta mal sumada
    que se da por buena es un IVA declarado mal (paso 11).
25. **Un recurso desconocido en una venta de Exact no es un hallazgo
    todavía.** La línea guarda el texto (`recurso_doc`) y queda sin recurso,
    como la de un PDF; el recurso solo lo leen las reglas del planning (V1-V6,
    paso 10), que lo convertirán en hallazgo junto con la línea sin Objeto
    (V2). Rechazar el listado por un nombre de empleado dejaría sin importar
    ventas ya emitidas (decisión 6 pide todo o nada por lo que falsea el
    dinero, no por un dato que nadie lee aún). Se amplía así la desviación 15.

Lo que deben saber los pasos siguientes, además de lo de arriba:

- **Lo que mueve una relación** sigue saliendo de un solo sitio, pero ahora
  `instantanea.relaciones` filtra las confirmadas que no mueven nada (origen
  anulado, alguna fusionada). Quien lea `factura_relacion` a mano para sumar
  algo tiene que usar `v_factura_relaciones` (0009) o ese filtro.
- **Unir una copia** (`_copias`) o fusionar a mano exige que la copia no
  lleve pagos ni relaciones confirmadas; el paso que añada otra cosa que
  mueva dinero sobre una factura (una PO consumida, paso 9) debe sumarla a
  `relaciones.lo_que_lleva`.
- **La vista de un cliente** devuelve `trabajo_sin_facturar` en sin datos: el
  paso 10 lo rellena con V6.

## Paso 9

Órdenes de compra (PO) y tarifas pactadas. **1630 tests pasan**
(973 funciones de test; eran 1550 y 929 al cerrar el paso 8), ninguno
llama a la API y ninguno escribe fuera de una carpeta temporal. Cinco mil
facturas se recalculan en 1,62-1,75 s la primera vez y en 1,34-1,46 s las
siguientes (seis medidas en este contenedor; el paso 8 medía 1,57-1,83 s y 1,35-1,52 s): sin ninguna PO registrada la sincronización no lee
las facturas, y sin tarifas pactadas G3, G6 y V4 no miran ninguna línea
contra lo pactado; lo que cuesta de más es leer las imputaciones en la
instantánea (unos 20 ms).

**Ni la V1 crea facturas ni nada aquí paga.** Una PO solo se registra, se
modifica, se cierra o se imputa: lo que mueve es lo que retiene o avisa.

### Qué se construyó

**Migración `0010_ordenes_compra.sql`** (la siguiente libre; el §11 la
llama 0006, pero la 0006-0009 ya son de los pasos 6-8):

- `orden_compra` (controlada, guardas generadas): número (y normalizado),
  lado (`cliente`: la que un cliente da a BM Support BV y consumen sus
  ventas; `proveedor`: la que BM Support BV da a un proveedor y consumen sus
  compras), la parte, fechas de emisión, inicio y fin, valor original sin
  IVA, documento, `cerrada` y `fuente` (`manual`, `po_csv`, `exact`,
  `trnsprnt`). Única por lado, parte y número normalizado. El número, el
  lado, la parte, el valor original y el fin original no cambian nunca (un
  disparador): lo que cambia se apunta como modificación.
- `orden_compra_objeto` (controlada): los Objetos que cubre una PO; una sin
  ninguno cubre cualquiera de su parte. Un Objeto se retira, no se borra.
- `orden_compra_modificacion` (**solo escritura**, evidencia con la foto de
  la fila en su evento `po_modificada`, como una nota): desde una fecha, un
  valor nuevo, un fin nuevo o los dos, con su motivo. La base exige que la
  firme una persona activa con `cambiar_po` en ese momento, en su propia
  orden o en la importación en curso que ella lanzó; nunca el sistema solo.
- `orden_compra_id` de `factura_imputacion`, `factura_referencia` y
  `tarifa_acordada` apunta a una PO que existe (disparadores: la 0002 no
  podía declarar la clave foránea).
- Vistas: `v_po_vigente` (el valor y el fin de la última modificación que
  cambia cada uno) y `v_po_consumo` (consumido, restante y porcentajes en
  puntos básicos, sin depender de hoy).

**Módulos nuevos**

| Módulo | Qué hace |
| --- | --- |
| `ordenes_compra.py` | Lo que hace el almacén con las PO. `sincronizar()` (en cada pasada del motor, después de `relaciones.sincronizar`): casa cada referencia impresa con las PO de la parte de su factura y deja imputada cada línea a la PO que dicen sus referencias. `cargos()` (lo consumido factura a factura, la misma cuenta que la vista y que las reglas), `ordenes()`, y las órdenes de una persona: `registrar_po`, `modificar_po` (y `apuntar_modificacion`, el único escritor de modificaciones), `cerrar_po`, `cambiar_objetos` e `imputar` |
| `reglas/ordenes.py` | Puro: valor y fin vigentes (`vigentes`), lo consumido en el orden del §7 (`cargos`, `antes_de_cada`, `situacion`), la previsión (`prevision`) y P1-P10 |
| `reglas/tarifas.py` | Puro: qué tarifa pactada vale para una imputación (`pactada`), de lo más concreto a lo general, o si es ambigua |
| `reglas/venta.py` | Puro: V4 |
| `importadores/ordenes.py` | La hoja de PO en YAML: los mismos registros canónicos que el CSV, con su contrato |
| `config/importacion/po_csv-ordenes_compra-v1.yaml`, `po_csv-modificaciones_po-v1.yaml` | Los mapeos de la hoja de PO y de la de sus modificaciones (cabeceras en neerlandés, como las demás hojas), con su ejemplo y su contrato en `tests/fixtures/importacion/` |

**Lo consumido de una PO** es la base sin IVA de las imputaciones activas
que apuntan a ella en las facturas que cuentan (ni anuladas, ni fusionadas,
ni sustituidas o corregidas: `v_imputacion_vigente`), del sentido que
consume su lado. Un abono resta solo cuando tiene una relación confirmada
(`acredita` o `anula`) que dice a qué factura abona, y mientras esa factura
cuente (revisión: migración 0011); antes, sus líneas no mueven la PO. Lo que no está en euros no tiene importe (X1) y no cuenta. El
orden es el del §7: por fecha de factura y, a igual fecha, por id; una
factura sin fecha va al final. Lo mismo en tres sitios que un test compara:
`v_po_consumo`, `ordenes_compra.cargos` y `reglas.ordenes.cargos`.

**Qué referencia es una PO lo decide el código, nunca el modelo**
(`ordenes_compra.sincronizar`, con fuente `calculado`):

- Una referencia viva casa si su valor normalizado es el número de una PO
  del lado y la parte de su factura (una venta, las PO de su cliente; una
  compra, las de su proveedor). Casa aunque su etiqueta dijera otra cosa; la
  que una persona clasificó a mano como no PO (`cambiar_po`) no casa nunca.
  Sin parte resuelta no casa con nada.
- Una imputación toma la PO de las referencias de su línea si es una sola;
  si no dicen ninguna, la de las de la cabecera si es una sola. Varias PO
  distintas no se reparten adivinando: queda sin PO.
- Un abono sin PO propia toma la de la factura que abona (con su relación
  confirmada) si toda ella va a una sola PO.
- Lo que una persona imputó a mano (`imputar_po`) gana siempre (M1): el
  cálculo queda como valor automático. Solo se escribe lo que cambia; una
  pasada sin cambios no deja evento.

**Reglas nuevas**

| Regla | Qué mira | Al fallar |
| --- | --- | --- |
| P1 | La PO imputada está cerrada, o el trabajo (fechas de la imputación, de la línea, el periodo o la fecha de la factura) cae fuera de su vigencia | Retención; se anula. Sin ningún día, sin datos |
| P2 | Una venta (no un abono) sin PO (ni imputada ni impresa) donde el Objeto (o, si no dice, el cliente) la pide | Retención; se anula |
| P3 | La PO impresa no está registrada o es de otra parte; la imputada es de otra parte o no cubre el Objeto de la línea; la factura imprime varias PO y una imputación no va a ninguna | Retención; se anula. Sin ninguna PO de ese lado, o sin la parte resuelta, sin datos |
| P4 | La factura carga a la PO más de lo que quedaba antes de ella, en el orden del §7 o en el de llegada | Retención; se anula; pegajosa; suelo urgente |
| P5 | Consumido el umbral de la política (80 %) o más | Aviso de la PO |
| P6 | La PO ya estaba consumida entera y la factura le carga más | Retención; se anula; suelo urgente |
| P7 | La PO caduca dentro de los días de la política (30) con valor por consumir; ya caducada, sin datos hasta el planning | Aviso de la PO; se anula; puntos de caducidad por los días que quedan |
| P8 | El trabajo planificado por la tarifa de venta pasa lo que queda | Sin datos hasta el paso 10 |
| P9 | Al ritmo de las últimas 8 semanas la PO se agota más de 14 días antes de su fin | Aviso de la PO |
| P10 | Lo facturado más lo trabajado sin facturar más lo planificado pasa el valor | Sin datos hasta el paso 10 |
| G3 (versión 2) | La tarifa de una línea de compra contra la pactada; sin pactada, contra el histórico como antes | Retención por encima de la pactada; bloqueo (que se anula con segunda firma) por encima del exceso de la política (10 %) |
| G6 | Una línea de un recargo (noche, fin de semana...) contra su propia tarifa pactada; sin ella, si hay otras pactadas para la línea, retiene (`no_casa`) | Retención; se anula |
| V4 | La tarifa de una línea de venta contra la de venta pactada, por encima y por debajo | Retención; se anula. Sin pactada, sin datos hasta el planning |

Una tarifa ambigua (dos igual de concretas con precios distintos) da sin
datos en la línea y retiene la factura con su excepción (clave `ambigua`).

**La tarifa pactada que vale** (`reglas/tarifas.py`): el turno es condición
de todos los niveles (la de noche no es la de una línea de día; «Dag» y una
línea sin turno son lo mismo), y lo que una tarifa dice tiene que coincidir.
Niveles: recurso y Objeto; Objeto; recurso; parte; y la general (sin parte
ni Objeto pero con tipo de trabajo, la de `config/tarifas.yaml`). Dentro del
primer nivel que tiene alguna gana la más concreta en lo demás (la de esa
PO, la de esa parte, la de ese tipo de trabajo, la de esa unidad y la de
vigencia más reciente).

**Las órdenes de una persona** (todas con `cambiar_po`):

| Orden | Qué hace |
| --- | --- |
| `registrar_po` | Una PO nueva, con sus Objetos (de su cliente, o de ninguno) |
| `modificar_po` | Un valor nuevo, un fin nuevo o los dos, desde una fecha (por defecto hoy); motivo obligatorio |
| `cerrar_po` | Cerrarla (`cerrada=no`, reabrirla); motivo obligatorio |
| `objetos_po` | Añadir o retirar Objetos |
| `corregir_po` | La fecha de emisión, la de inicio o el documento (lo demás es identidad o modificación) |
| `imputar_po` | Imputar una línea a una PO, a otra o a ninguna: una del otro lado o de otra parte no se acepta |

**La hoja de PO** entra por el marco de importación (`registrar_lote`) como
cualquier maestro, y además de `importar_datos` pide `cambiar_po`:
`bms-agent importar po_csv ordenes_compra hoja.csv` (o `hoja.yaml`) y
`bms-agent importar po_csv modificaciones_po cambios.csv`. Fila a fila: lo
que no está en euros (X1), un valor cero, una parte o un Objeto que no
existen o un Objeto de otro cliente se rechazan (Z2). Una PO que vuelve
igual solo añade los Objetos nuevos; una que vuelve con otro valor o con otro
fin originales se rechaza y pide la modificación. Las modificaciones son su
propia fila, con su motivo; la misma otra vez no se apunta dos veces. Un YAML
con las dos listas entra como dos lotes (las PO y después sus
modificaciones).

**Lo que se lee**: `consultas.ordenes_compra` (la lista por prioridad, con
valor, consumido, lo que queda y porcentajes), `consultas.orden_compra` (la
ficha: sus facturas en el orden en que la consumen con lo que quedaba antes
de cada una, sus modificaciones, la previsión, y lo planificado y lo
trabajado sin facturar como sin datos hasta el paso 10) y `consultas.objeto`
(el bloque de PO de la vista de un Objeto: las PO que lo cubren o a las que
se imputa trabajo suyo, con lo consumido de la PO entera y lo de ese
Objeto). En `/api/v2/ordenes`, `/api/v2/ordenes/<id>` y
`/api/v2/objetos/<id>`, en la consola (lista de PO, ficha con sus órdenes,
vista del Objeto e `imputar_po` en cada imputación) y en la CLI (`ordenes`,
`orden N`, `objeto N`). La prioridad de una PO (caché `prioridad`, entidad
`orden_compra`) es el máximo de las facturas imputadas a ella y de sus
propios avisos.

**Cambios en lo que había**: `campos.py` (las dos tablas controladas, sus
permisos, y `factura_referencia.orden_compra_id` no editable: la casa el
sistema), `reglas/base.py` (los parámetros de la política, `Imputacion`,
`Referencia`, `OrdenCompra`, `Tarifa`, `Objeto`), `reglas/instantanea.py`
(imputaciones, referencias, PO, tarifas y Objetos), `reglas/motor.py` (la
fuente de una imputación y de una referencia entra en la huella),
`reglas/planning.py` (G3 versión 2 y G6), `politica.py` y
`config/reglas.yaml` (secciones `ordenes_compra` y `tarifas`),
`hallazgos.py` (la sincronización y `Diferencia.ordenes`), `estados.py`,
`excepciones.py` (la descripción de una excepción de una PO), `servicios.py`,
`consultas.py` (la PO de cada imputación y referencia en la ficha de una
factura), `serve.py`, `consola_assets.py`, `cli.py`,
`importadores/registrar.py`, `importadores/canonico.py` y
`almacen/evidencia.py`.

### La puerta, test por test

| Puerta | Tests |
| --- | --- |
| Aritmética del consumo: sin IVA | `test_reglas_paso9.py::test_el_consumo_es_sin_iva_con_los_abonos_confirmados_y_sin_lo_que_no_cuenta` (la base de cada línea, no el total con IVA); `test_ordenes_compra.py::test_el_abono_confirmado_resta_de_la_po_y_antes_no` (4.256,00 de V2026-0101, no 5.149,76) |
| Los abonos confirmados restan (y los propuestos no) | Los dos anteriores, `test_un_abono_no_consume_y_libera_lo_que_abona` y `test_un_abono_sin_po_impresa_toma_la_de_la_factura_que_abona` |
| Anuladas y sustituidas fuera | `test_el_consumo_es_sin_iva...` (anulada, sustituida, fusionada, otro lado, sin euros; y el abono de una que ya no cuenta), `test_ordenes_compra.py::test_una_sustituida_no_consume`, `test_una_anulada_no_consume`, `test_el_abono_de_una_original_anulada_ya_no_resta` y `test_el_abono_de_una_original_sustituida_ya_no_resta` |
| La vista, el almacén y las reglas dicen lo mismo | `_tres_cuentas` en cada test de consumo del almacén |
| P4 respeta el orden | `test_p4_sigue_el_orden_por_fecha_de_factura_y_por_id` (fecha y luego id, sin fecha al final, con las facturas revueltas; y el de llegada), `test_p4_una_factura_con_fecha_atrasada_no_se_cuela_delante`, `test_p4_retiene_la_factura_que_pasa_lo_que_quedaba_y_es_pegajosa` (sobre el almacén, con una modificación de valor) |
| Los umbrales salen de la configuración | `test_ordenes_compra.py::test_los_umbrales_de_las_po_salen_de_la_configuracion` (`config/reglas.yaml` cargado con las cinco claves cambiadas llega entero a la política; P5 se cierra con el umbral más alto y P7 se abre con 90 días; uno fuera de límites no se carga), `test_p5_avisa_desde_el_umbral_de_la_politica`, `test_p7_caduca_dentro_de_los_dias_de_la_politica`, `test_la_prevision_es_determinista...` (margen y semanas), `test_g3_compara_con_la_pactada...` (exceso) |
| La caducidad con fecha fija | `test_p7_caduca_dentro_de_los_dias_de_la_politica` (hoy 2026-10-14: 27, 30, 31 y 0 días, ya caducada) y `test_la_caducidad_con_la_fecha_fija_y_la_prioridad_de_la_po` (en el almacén, con los puntos de caducidad en la prioridad de la PO) |
| La previsión es determinista | `test_la_prevision_es_determinista_y_sale_del_ritmo_de_las_semanas` (la ventana, el ritmo y el día exactos; el mismo resultado en cualquier orden) y `test_la_prevision_empieza_en_el_inicio_de_la_po_y_sin_consumo_no_se_agota` |
| Qué referencia es una PO lo decide el código | `test_la_referencia_impresa_casa_con_la_po_de_su_cliente_y_la_imputa`, `test_una_referencia_que_una_persona_dice_que_no_es_po_no_casa`, `test_una_referencia_que_no_casa_es_una_po_desconocida` |
| Importar la hoja de PO (CSV o YAML), con `cambiar_po`; las modificaciones son filas aparte | `test_la_hoja_de_po_entra_por_el_marco_de_importacion`, `test_una_po_que_vuelve_con_otro_valor...`, `test_importar_la_hoja_de_po_pide_cambiar_po`, `test_la_hoja_de_po_en_yaml_da_lo_mismo_que_el_csv`, y los contratos de `test_importadores.py` |
| Una modificación es de solo escritura y la firma quien puede | `test_una_modificacion_es_de_solo_escritura_y_la_firma_quien_puede` (y `test_almacen.py`, que la cuenta entre las tablas de solo escritura y su evidencia) |
| Registrar, modificar e imputar | `test_registrar_cerrar_y_cubrir_objetos_de_una_po`, `test_lo_que_imputa_una_persona_gana_a_lo_que_casa_el_sistema`, y la matriz de permisos de `test_servicios.py` |
| G3 y V4 contra lo pactado, ambigua, recargos | `test_la_tarifa_pactada_va_de_lo_mas_concreto_a_lo_general`, `test_dentro_del_nivel_gana_la_mas_concreta_y_si_no_es_ambigua`, `test_g3_compara_con_la_pactada...`, `test_g3_ambigua_da_sin_datos_y_retiene_con_su_excepcion`, `test_g3_sigue_con_el_historico_donde_no_hay_pactada`, `test_g6_un_recargo_a_su_propia_tarifa_y_sin_ella_lo_mira_g3`, `test_v4_la_venta_a_la_tarifa_pactada_ni_por_encima_ni_por_debajo`, `test_v4_con_las_tarifas_de_venta_del_maestro` |
| El bloque de PO del Objeto, la lista y la ficha en la consola y /api/v2 | `test_la_ficha_de_la_po_y_la_vista_del_objeto`, `test_consola.py::test_las_ordenes_de_compra_y_los_objetos_por_la_api` (con HTML en los nombres, pintado como texto), `test_la_cli_ensena_las_po_su_ficha_y_la_del_objeto` |
| Cada regla lee lo que declara | `test_pureza_reglas.py` con los escenarios del paso 9 (`test_reglas_paso9.escenarios`) |

### Desviaciones de la especificación, y por qué

1. **La migración es la 0010**, no la 0006 del §11: la numeración ya va por
   la 0009.
2. **P1 y P3 se reparten el §7.** P1 («PO válida») mira lo que es de la PO:
   cerrada, o el trabajo fuera de su vigencia. P3 («desconocida o
   equivocada») mira la parte y el Objeto, y la PO impresa que no está. Así
   una PO de otro cliente no da dos retenciones por lo mismo.
3. **P2 solo en las ventas, y lleva PO la línea que la tiene impresa.** Que
   se pida PO lo dice el maestro de clientes y de Objetos (`requiere_po`);
   ningún maestro dice que un proveedor la pida. Una venta con la PO impresa
   que aún no casa no «falta»: es P3 (desconocida, o sin datos sin lista de
   PO). Sin esto, importar el listado de Exact antes que la hoja de PO
   retenía todas las ventas de los clientes que la piden.
4. **Sin ninguna PO de ese lado, P3 da sin datos**: sin la lista no se sabe
   si una PO impresa es desconocida, y retener todo el primer día no ayuda.
5. **P4 y P6 no se pisan.** P4 es «pasa lo que quedaba» con algo por
   consumir antes; si ya no quedaba nada, P4 no aplica y lo dice P6. Una
   factura sin fecha no se puede poner en el orden: sin datos en las dos. Un
   abono (lo que carga es negativo) no consume: ok.
6. **P7 ya caducada da sin datos**: el §7 la hace R «con trabajo planificado
   después del fin», y eso lo dice el planning (paso 10). Sin fin, no aplica.
7. **P8 y P10 dan sin datos hasta el paso 10**: necesitan lo planificado y
   lo trabajado sin facturar. Lo facturado de más ya lo dicen P4 y P6.
8. **La previsión (P9)**: el ritmo es lo consumido en la ventana de
   `semanas_ritmo` semanas que acaba hoy (desde el inicio de la PO o, si no
   tiene, su emisión, si empezó después), y el día de agotamiento es hoy más
   lo que queda por ese ritmo, redondeado hacia arriba en días. Sin consumo
   en la ventana, a ese ritmo no se agota (ok). Con nada por consumir, no
   aplica (lo dicen P5 y P6).
9. **El valor y el fin vigentes son los de la última modificación que cambia
   cada uno**, por su fecha y, a igual fecha, la apuntada después: una
   modificación que solo alarga el fin no devuelve el valor al original.
   Desde la revisión, una modificación no puede tener fecha posterior a hoy
   (desviación 23).
10. **Los niveles de la tarifa pactada son cinco**, no los cuatro del §7: se
    añaden «recurso» (la tarifa propia de un zzp'er en cualquier obra; sin
    él una tarifa por persona del maestro no se usaría nunca) y «general»
    (la de venta de `config/tarifas.yaml`, sin cliente). El turno es una
    condición de todos («parte + turno» del §7). El desempate dentro de un
    nivel (la de esa PO, parte, trabajo, unidad y la vigencia más reciente)
    es nuestro: sin él, una tarifa nueva que sustituye a la vieja sin que
    nadie cierre la vieja sería siempre ambigua.
11. **Una ambigua retiene, no avisa.** El §7 pide sin datos «y una
    excepción»: la línea da sin datos y la factura una retención con clave
    `ambigua`, que abre su excepción como cualquier retención. Con
    `crea_excepcion`, cada aviso del histórico de G3 abriría también una.
12. **G3 sube a la versión 2**: contra lo pactado, retiene por encima de la
    pactada (por debajo es lo que BM Support BV prefiere pagar) y bloquea
    pasado el `exceso_bloqueo_pct` de la política (la parte B, que se anula
    con segunda firma). El escalón del planning (la tarifa del turno) no
    existe aún: sin pactada, G3 sigue con el histórico como pide la puerta.
    Cambiar de versión cambia la huella: un G3 aceptado antes se reabre una
    vez. La contraparte, el Objeto, el recurso y la PO resueltos no entran
    en la huella de G3, G6 y V4 (sí la tarifa elegida y su precio, en los
    valores): dar de alta el proveedor o sembrar los Objetos no reabre nada.
13. **G6 compara un recargo con su propia tarifa pactada** (la puerta del
    paso 10: «un recargo nocturno a su tarifa pactada no da G3»). Sin ella,
    si la parte, el recurso o el Objeto tienen otras pactadas, retiene
    (desviación 24); sin ninguna, no aplica y G3 lo mira con el histórico.
14. **V4 en los dos sentidos y sin histórico**: por encima, el cliente
    reclamará; por debajo, BM Support BV pierde dinero. Sin pactada, sin
    datos hasta el planning (el §7 no le da histórico).
15. **Las reglas de PO y de tarifas dan ok** de lo que miran (no solo lo que
    objetan): un sin datos sin un resultado al lado retendría un hallazgo
    viejo de esa misma fila.
16. **`factura_referencia.orden_compra_id` no se edita a mano**: la casa el
    sistema con la lista de PO. Una persona decide la clase de una referencia
    (`cambiar_po`) o la PO de una línea (`imputar_po`).
17. **El abono hereda la PO** de la factura que abona (con la relación
    confirmada) cuando no imprime la suya: sin esto, el «menos los abonos
    confirmados» del §7 casi nunca restaría.
18. **La hoja de PO son dos ficheros** (las PO y sus modificaciones), no uno
    con una columna de tipo: cada uno con su mapeo, su contrato y su
    importación, y la modificación de una PO nueva entra después de ella. En
    YAML, un fichero con las dos listas.
19. **Los límites de la política** (`_LIMITES`): umbral de P5 entre 50 y
    100 % (revisión; era 1), días de caducidad entre 7 y 180, margen de la previsión entre 0 y
    90 días, semanas del ritmo entre 2 y 26, exceso de G3 entre 1 y 100 %.
20. **La vista del Objeto** tiene por ahora su ficha y su bloque de PO; las
    horas, ingresos y costes son de los pasos siguientes.
21. **Una imputación a PO de una copia en PDF que se une a su venta de
    Exact** se pierde con ella: la copia no cuenta, y las imputaciones de la
    venta de Exact casan con sus propias referencias. Fusionar no se impide
    por eso (no mueve dinero).
22. **P5 y P7-P10 son de la PO entera, no de cada factura** (revisión). El
    §8 cuenta sus puntos (límite blando de PO 10; caducidad de P7 10/20) y el
    suelo urgente de P10 en `prioridad.calcular` por factura. Aquí van a la
    fila de prioridad de la PO (`estados._avisos_de_po`): una PO casi
    consumida o a punto de caducar no es un problema de ninguna factura en
    concreto, y ponerlo en cada factura imputada subiría a la vez, y por lo
    mismo, todas las de la PO (y las ya pagadas). Lo que sí es de la factura
    lo dicen P1-P4 y P6 (los puntos de límite blando y duro y el suelo
    urgente de P4 y P6, por factura). **P10 hoy da sin datos**: cuando el
    paso 10 la encienda, una retención de la PO entera no retiene ninguna
    factura ni pone su suelo urgente en ninguna; el paso 10 tiene que decidir
    a qué facturas se la pone (las que cargan a la PO desde que lo esperado
    pasa el valor, como objetivos del hallazgo) para que el suelo del §8 se
    aplique.
23. **Una modificación de una PO no puede tener fecha posterior a hoy**
    (revisión). El valor y el fin vigentes no dependen de hoy (como
    `v_po_vigente`), así que una modificación vale entera en cuanto se
    apunta: con una fecha de junio, una ampliación subía el límite hoy (P4 y
    P6 dejaban pasar lo que hoy no cabe) y un recorte abría P4 y P5 hoy. Y
    como la vigente es la de fecha mayor, una equivocada con fecha futura no
    se podía arreglar con otra de hoy, y no se puede borrar. Lo que empieza
    más adelante se apunta ese día. Con esto, una corrección con la fecha
    por defecto (hoy) gana siempre a la equivocada, como dice la cabecera de
    la 0010. `modificar_po` y la hoja de modificaciones lo rechazan (la fila,
    no el fichero).
24. **Una línea que no casa con lo pactado por su turno, su unidad o su día
    retiene** (revisión; G3 y G6). Esas tres cosas las imprime el
    proveedor: antes, con «Nacht», «x», otra unidad o un día fuera de la
    vigencia la línea no casaba con nada y volvía al histórico, donde una
    primera factura es siempre «la de siempre»; un precio un 50 % por encima
    de lo pactado, que bloquea, salía ok. Ahora, si la parte, el recurso o el
    Objeto tienen tarifas pactadas (de ese tipo de trabajo) y ninguna casa,
    es `no_casa`: sin datos en la línea y la factura retenida (clave
    `no_casa`, con su excepción, como una ambigua), en G3 si es de día y en
    G6 si es un recargo. No se compara un recargo sin tarifa propia con la de
    día: un recargo cobra más que la de día por definición, y cuánto es lo
    que una persona confirma. V4 lo trata como sin pactada (sin datos): una
    venta la escribe BM Support BV. El tipo de trabajo y los resueltos
    (recurso, Objeto, PO) siguen siendo condición: un trabajo que no tiene
    tarifa pactada sigue con el histórico.
25. **P4 y P6 miran también el orden de llegada** (revisión). El §7 ordena
    por fecha de factura, que imprime el proveedor: una factura con fecha
    atrasada se colaba delante de las que ya se habían mirado (y quizá
    pagado), salía ok y pasaba la retención a una de ellas. Ahora lo que
    quedaba antes de una factura es lo menos de los dos órdenes (el del §7 y
    el de llegada, por id): la que llega con la PO ya casi consumida se
    retiene aunque su fecha la ponga antes. En ese caso la anterior también
    retiene, porque en el orden del §7 es la que pasa: P4 es pegajosa y una
    persona decide cuál se anula. La ficha de la PO sigue enseñando el orden
    del §7.

### Lo que deben saber los pasos siguientes

- **Paso 10 (planning)**: lo que espera al planning da sin datos y lo dice
  («llega con el planning (paso 10)»): P8 y P10 (`reglas.ordenes._sin_planning`),
  P7 ya caducada (trabajo planificado después del fin), V4 sin pactada (la
  tarifa del turno), el escalón del planning de G3 (entre lo pactado y el
  histórico, en `planning.g3`) y, en la ficha de una PO, `planificado` y
  `sin_facturar` (`consultas._SIN_PLANNING`). La puerta del paso 10 «un
  recargo nocturno a su tarifa pactada no da G3» ya se cumple con G6.
- **Lo consumido de una PO** se cuenta en un solo sitio por capa:
  `v_po_consumo` (SQL, rehecha en la 0011), `ordenes_compra.cargos` (almacén) y
  `reglas.ordenes.cargos` (instantánea); un cambio en una tiene que ir a las
  tres (el test de las tres cuentas lo vigila).
- **Una PO solo la escribe** `ordenes_compra.py` (personas) y la importación
  de la hoja de PO; las modificaciones, solo `apuntar_modificacion`. Si llega
  Exact o TRNSPRNT con PO (`fuente` ya los admite), su importación tiene que
  firmarla una persona con `cambiar_po` (la base lo exige para las
  modificaciones).
- **La prioridad de una PO** se calcula en `estados._avisos_de_po` como una
  factura sin plazo ni importe; los pesos de límite y caducidad de PO son los
  de `config/prioridad.yaml`. Los días de caducidad de P7 los cuenta
  `estados._dias_hasta_fin` desde el fin fijo del hallazgo: nada que dependa
  de hoy va en los valores de un hallazgo (son su huella).
- **P10 en el paso 10** (desviación 22): es de la PO entera; para que su
  retención y su suelo urgente lleguen a una factura, el paso 10 tiene que
  ponerle objetivos (las facturas que cargan a la PO).
- **La consola** tiene ya las PO y el bloque de PO del Objeto; la vista
  entera del Objeto (horas, ingresos, costes) sigue pendiente.

### Correcciones de la revisión

La revisión del paso 9 dejó diecisiete hallazgos. Tres decían lo mismo (una
modificación con fecha futura vale ya y no se puede corregir), así que son
quince. Cada uno se reprodujo antes de tocarlo (con los scripts del revisor y
con el test nuevo contra el código del paso 9: los tests nuevos de lo que se
arregla fallan sin las correcciones). Todos eran reales. Trece se arreglan en
el código con su test; dos se documentan (el alcance de P5 y P7-P10, como la
desviación 22, y el catálogo de `docs/validacion-facturas.md`). **1652 tests pasan**
(eran 1630). Sin una sola llamada a la API. Cinco mil facturas se recalculan
en 1,69-1,79 s la primera vez y en 1,41-1,48 s las siguientes (tres medidas):
lo mismo que antes, dentro del ruido del contenedor.

| Hallazgo | Qué se hizo | Test |
| --- | --- | --- |
| **Bloqueante.** Un turno, una unidad o un día impresos por el proveedor que no casan con lo pactado sacaban la línea de G3 y G6: volvía al histórico (ok en una primera factura) y el bloqueo por encima del 10 % desaparecía sin ningún hallazgo | Desviación 24: `tarifas.pactada` da `no_casa` cuando hay tarifas pactadas para la línea (por su parte, recurso, Objeto, PO y tipo de trabajo) y ninguna de su turno, su unidad o su día; G3 (de día) y G6 (recargos) dan sin datos en la línea y retienen la factura con la clave `no_casa`, y la línea no vuelve al histórico | `test_reglas_paso9.py::test_un_turno_una_unidad_o_un_dia_que_no_casan_no_se_saltan_la_pactada` (Nacht, x, stuk y fuera de vigencia), `test_g6_un_recargo_a_su_propia_tarifa_y_sin_ella_lo_mira_g3` |
| **Mayor.** P7 y P9 guardaban en los valores (la huella) días que bajan cada día: un P7 aceptado se reabría a la mañana siguiente, y los abiertos apuntaban un cambio de evidencia diario | P7 guarda el fin, lo que queda y el límite; P9, lo que queda, el fin y el margen. Los días que quedan van en el texto, y la prioridad los cuenta desde el fin fijo (`estados._dias_hasta_fin`) | `test_ordenes_compra.py::test_un_p7_aceptado_sigue_aceptado_al_dia_siguiente`, `test_la_caducidad_con_la_fecha_fija_y_la_prioridad_de_la_po` (26 días al día siguiente), `test_p7_caduca_dentro_de_los_dias_de_la_politica` |
| **Mayor** (tres hallazgos). Una modificación con fecha futura valía ya (una ampliación de junio subía el límite hoy; un recorte abría P4 y P5 hoy) y, como la vigente es la de fecha mayor, una equivocada no se podía corregir con otra de hoy | Desviación 23: `apuntar_modificacion` rechaza una fecha posterior a hoy (`modificar_po` da 400 y la hoja de modificaciones rechaza la fila). La vista y `vigentes` siguen por (fecha, id): una corrección de hoy gana siempre | `test_una_modificacion_no_vale_desde_el_futuro_y_la_de_hoy_corrige` |
| **Mayor.** La hoja de tarifas guarda «dag» como `dia` y la línea dejaba «dag»: una tarifa por día no casaba nunca y V4 daba sin datos | `dominio.normalizar_unidad` (hora, dia, stuk o el texto): la usan `campos._unidad`, la importación de tarifas y `tarifas.pactada`. `es_unidad_hora` pasa a `dominio.py` (las reglas no importan `parsing`) y `parsing` la sigue exportando | `test_ordenes_compra.py::test_una_tarifa_por_dia_del_maestro_casa_con_la_linea_por_dia`, `test_reglas_paso9.py::test_una_tarifa_por_dia_casa_con_una_linea_por_dia` |
| **Mayor.** Una compra que imprime dos PO de su proveedor no consumía de ninguna y P3 daba ok: escapaba a P1, P4 y P6 | P3 retiene la factura con una imputación sin PO donde lo impreso dice varias (en su línea o, si su línea no dice ninguna, en la cabecera): «una persona decide con `imputar_po`» | `test_p3_retiene_una_compra_que_imprime_dos_po_y_no_consume_ninguna` |
| **Mayor.** P4 ordenaba por la fecha impresa: una factura con fecha atrasada se colaba delante, salía ok y la retención pasaba a una anterior ya mirada | Desviación 25: P4 y P6 toman lo menos de lo que quedaba en el orden del §7 y en el de llegada (`antes_por_llegada`); el texto dice cuándo es por la llegada | `test_p4_una_factura_con_fecha_atrasada_no_se_cuela_delante`, `test_p4_sigue_el_orden_por_fecha_de_factura_y_por_id` |
| **Mayor.** El YAML de PO leía `012500` como octal (5440), `12:30` como sexagesimal (750) y `1_000` como 1000, sin aviso, y el crudo era el número convertido | `importadores/ordenes.py` carga con un `SafeLoader` sin enteros ni floats implícitos: los números quedan como texto (el crudo es lo tecleado) y un importe que no es una cifra con, si acaso, decimales tras un punto se rechaza. `1250.50` sin comillas ya no pierde céntimos y entra | `test_importadores.py::test_un_importe_del_yaml_de_po_es_lo_que_se_tecleo`; el contrato `po_csv-yaml` (la fila 3 lleva ahora `12:30`) |
| **Mayor.** Un abono confirmado seguía restando de la PO con la original anulada o sustituida: contaba dos veces y lo consumido quedaba negativo | Migración **0011** (la 0010 no se edita): `v_po_consumo` cuenta el abono solo si la factura que abona sigue contando; lo mismo `ordenes_compra.cargos` y `reglas.ordenes.abonos_confirmados`. La sincronización no hereda la PO de una que ya no cuenta | `test_el_abono_de_una_original_anulada_ya_no_resta`, `test_el_abono_de_una_original_sustituida_ya_no_resta`, `test_el_consumo_es_sin_iva...` |
| P2 retenía un abono sin PO a un cliente que la pide | P2 no mira los abonos: toman la PO de la factura que abonan al confirmarse, y la relación que les falta la dice R4 | `test_p2_pide_la_po_donde_el_objeto_o_el_cliente_la_piden` |
| La vista del Objeto no enseñaba las PO de su cliente sin Objetos, que lo cubren | `consultas.objeto` incluye las abiertas de su cliente sin Objetos (`cubre_objeto`) | `test_la_ficha_de_la_po_y_la_vista_del_objeto` (Schiedam y la 4500777) |
| `corregir_po` aceptaba un inicio después del fin vigente (y uno después del fin original daba un error de la base, 409); `registrar_po` con un número solo de separadores daba un `NOT NULL` | `_corregir_po` comprueba el inicio contra el fin original y el vigente (400); `registrar_po` y la hoja rechazan un número sin nada que normalizar | `test_una_po_sin_numero_o_que_empieza_despues_de_su_fin_no_entra` |
| El test de los umbrales no comprobaba P7 ni las claves `margen_prevision_dias`, `semanas_ritmo` y `exceso_bloqueo_pct` a través de `config/reglas.yaml` | El test carga las cinco claves cambiadas y comprueba la política entera, P5 y P7 | `test_los_umbrales_de_las_po_salen_de_la_configuracion` |
| P5 y P7-P10 son de la PO y no llegan a la prioridad de las facturas, como pide el §8 | No se cambia: desviación 22 (y lo que tiene que hacer el paso 10 con P10) | — |
| `docs/validacion-facturas.md` no decía nada del paso 9 | La frase «desde el paso 9», la sección P y las filas de G3, G6 y V4 como en `catalogo.py` (y sus descripciones, con lo de la revisión) | — |
| El comentario de los límites de P5 decía «por debajo de la mitad» y el límite era 1 % | El límite es 50-100 % (desviación 19) | `test_los_umbrales_de_las_po_salen_de_la_configuracion` (49 no se carga) |

**Tests existentes cambiados, y por qué**: `test_p4_sigue_el_orden...`: la
factura 9 (fecha más temprana, id mayor que la 3 y la 5) llega la última y
también retiene (desviación 25). `test_g6_un_recargo...`: un recargo sin
tarifa propia con la de día pactada ya no va al histórico, retiene
(desviación 24); sin ninguna pactada sí. `test_la_tarifa_pactada_va...` y
`test_dentro_del_nivel...`: la de noche para una línea de día y la caducada
son `no_casa`, no `ninguna`. `test_p7_caduca...` y `test_la_prevision...`:
los días y el día de agotamiento se miran en el texto, no en los valores.
`test_los_umbrales...`: el umbral de 40 % ya no se carga (límite 50); se
prueba con la PO recortada. `test_reglas_paso9.escenarios` gana una
instantánea con las ramas nuevas para la prueba de pureza.

## Paso 10

El planning de TRNSPRNT, con el mapeo hecho contra un ejemplo **sintético**
(todavía no hay una exportación real). **1733 tests pasan** (1030 funciones
de test; eran 1652 al cerrar el paso 9), ninguno llama a la API y ninguno escribe fuera de una
carpeta temporal. Cinco mil facturas se recalculan en 1,21-1,54 s la primera
vez y en 1,09-1,29 s las siguientes sin planning, y en 1,30-1,37 s y 1,06-1,25 s
con una foto del planning importada (cuatro medidas de cada; el paso 9 medía
1,69-1,79 s y 1,41-1,48 s): sin planning cada regla del planning da un solo sin
datos y la conciliación no lee nada.

**Nada aquí paga, factura ni aprueba.** El planning solo se importa, se
concilia con lo facturado y se compara: lo que mueve es lo que retiene o
avisa. El Objeto que propone el planning para una línea sin Objeto es una
propuesta: la línea no se toca y la confirma una persona con
`cambiar_objeto`.

### Qué se construyó

**Migración `0012_planning.sql`** (la siguiente libre; el §11 la llama 0007):

- `planning_turno` (**evidencia**, como un movimiento del banco: sin UPDATE
  ni DELETE, y la foto de cada fila en el evento `planning_registrado` de su
  importación). Un turno de una importación del planning como lo da el
  fichero: `id_externo` (el Dienst-ID o una clave sintética, `clave_fragil`),
  `nivel` (`dia` o `semana`: una fila de la exportación pivotada, con `fecha`
  el lunes y `dias` los días con horas), horas de inicio y fin, pausa, horas
  planificadas, realizadas y validadas (en milésimas), `estado`
  (`planificado`, `realizado`, `validado`, `cancelado`), lo que nombra
  (`objeto_ref_doc`, `recurso_ref_doc`, `proveedor_ref_doc`,
  `cliente_ref_doc`, `po_ref_doc`) y lo que se resolvió al importar
  (`*_id`), tipo de servicio y de turno, si es facturable, las tarifas de
  compra y venta del turno y la fila del fichero (`datos_origen_json`). Solo
  la escribe el importador, en una importación de TRNSPRNT de tipo planning
  en curso (disparador).
- `v_turno_vigente`: el planning que vale. De cada turno, el de la
  importación aceptada más nueva que cubre su fecha (`cubre_desde` a
  `cubre_hasta`); una fila semanal deja de valer en cuanto una más nueva
  cubre algún día de su semana.
- `conciliacion` (controlada, guardas generadas): la traza de una imputación
  a los turnos de su celda (§5 de arquitectura.md), con las horas que se le
  asignaron a cada uno, el nivel (`regla`: `recurso_dia`, `objeto_dia`,
  `recurso_semana`, `objeto_semana`, `recurso_periodo`, `objeto_periodo`),
  `metodo` (`automatica`, que solo escribe el motor; `manual`, una persona
  con `cambiar_objeto`) y `huella_imputacion`. No cambia nunca: se retira y
  se escribe otra (disparador).
- `v_planning_estado`: por turno vigente, sus horas de referencia y lo
  conciliado con compras y con ventas que cuentan.

**Los mapeos**: `config/importacion/trnsprnt-planning-v1.yaml` (la
exportación de *diensten*, un turno por fila) y
`trnsprnt-planning-semana-v1.yaml` (la *weekoverzicht* pivotada: una fila por
persona, Objeto y semana, con una columna por día y el total), con su ejemplo
y su contrato en `tests/fixtures/importacion/`. Las columnas que esperan
están en `docs/sistemas.md` («La exportación del planning que espera el
agente»). El ejemplo diario es una semana de seguridad en el puerto: un turno
de día y uno de noche validados en Rijnhaven (la noche sin horas
planificadas: salen de 23:00 a 7:00 menos la pausa), uno de tarde
planificado en Waalhaven, uno de fin de semana realizado, uno cancelado, uno
de festivo **sin Dienst-ID** (clave sintética) y una formación no facturable
en un Objeto que el maestro no tiene. El semanal, dos filas de la semana 42 y
una de la **semana 53** de 2026 (que termina el 3 de enero de 2027).

**Módulos nuevos**

| Módulo | Qué hace |
| --- | --- |
| `importadores/planning.py` | Antes de registrar: el identificador de cada turno (el Dienst-ID; si falta, la clave sintética `sint:` con día o semana, Objeto, persona, horas y turno, marcada frágil y con un aviso), los identificadores repetidos (rechazan el fichero) y lo que cubre la foto (del primer al último día, o lo que se diga: un turno de fuera rechaza el fichero) |
| `importadores/canonico.py` (`TurnoCanonico`) | El turno leído: fecha o año y semana, horas por día de la fila semanal (que tienen que sumar el total), horas planificadas que faltan calculadas de las horas y la pausa (a la milésima, redondeo hacia arriba en el medio), un turno validado con sus horas validadas |
| `importadores/registrar.py` (`_planning`) | La foto entera o nada; cada referencia se busca en el maestro por coincidencia exacta (`Resolutor`) y lo que no está entra con su texto y sin resolver; un solo evento con la foto de cada turno |
| `reglas/turnos.py` | Puro. Las celdas (`celda_de`, `contenido`): de qué días es una imputación (sus fechas, las de su línea, la semana impresa con el año de la fecha de la factura, o el periodo), persona u Objeto, día, semana o periodo; lo que cubre el planning, sus horas de referencia, los periodos de los ciclos, el valor a la tarifa de venta o de compra, `Planificacion` (lo que una regla necesita del planning en una pasada) y `agrupar` |
| `reglas/planning.py` | G1, G2, G4, G5, G7, la parte del planning de G6 y el escalón del planning de G3 |
| `reglas/venta.py` | V1, V2, V3, V5, V6, V8, V9 y el escalón del planning de V4 |
| `conciliacion.py` | `sincronizar` (en cada pasada del motor, después de casar las PO): concilia cada imputación con horas de una factura en juego que aún no tiene su conciliación y retira las que ya no valen; `traza` (la ficha de una factura) |
| `trabajo.py` | Para las vistas: el estimado del flujo de caja y las horas de un Objeto por semana ISO |

**La celda** (`reglas/turnos.py`). Una imputación se compara con el planning
al nivel más fino que llevan los dos lados: la persona si la imputación la
nombra y el planning tiene sus turnos esos días (con persona y Objeto, solo
sus turnos en ese Objeto); si no, el Objeto. Un día si la línea es de un día
y el planning de ese día es diario; una semana si la línea es de una semana
entera, o si cae en una semana de la que el planning solo tiene la fila
semanal (entonces se compara todo lo facturado de esa semana contra la
fila); el periodo en lo demás. En una compra cuentan los turnos de su
proveedor (el del turno o, si no lo dice, el de su persona); en una venta,
los facturables de su cliente (el del turno o el de su Objeto). Un turno
cancelado no cuenta nunca. Una celda con un día que ninguna foto cubre, una
fila semanal que cae solo en parte en ella o el planning pasado de su
frescura (Z1) dan sin datos, nunca «no hay turnos».

**La conciliación** (`conciliacion.py`). En cada pasada, antes de evaluar,
cada imputación con horas de una factura (no un abono) en juego, con su
parte resuelta, que aún no está conciliada: sus horas se reparten entre los
turnos de su celda en su orden (fecha, hora de inicio, identificador), a
cada uno lo que le queda en ese sentido; lo que sobra va al último (cobrar
más horas de las que hay se ve en la traza, y es B5 o V7); cada turno de la
celda queda en una fila, también con cero horas. Lo escribe el motor (fuente
`planning`, referencia la última importación) en un evento
`conciliacion_sincronizada`, solo si algo cambia. Si cambia la imputación
(su Objeto, su persona, sus días, sus horas, su turno o la parte de la
factura) o la factura sale de juego, se retira y se rehace; si cambia el
planning, no: es lo que se facturó (regla 9), y la diferencia la dicen G7 y
V9. Con el planning pasado de su frescura no se concilia nada nuevo.

**Reglas nuevas o que cambian**

| Regla | Qué mira | Al fallar |
| --- | --- | --- |
| G1 | Una compra sin ningún turno de su proveedor ni de sus personas en el periodo facturado | Retención; bloqueo con `planning.obligatorio`. Se anula con segunda firma |
| G2 | Horas facturadas de cada celda contra las validadas de su proveedor; tolerancia de la política por día con turnos (0,25 h) | Retención; se anula. Un turno sin validar en la celda: sin datos |
| G3 (escalón nuevo) | Sin tarifa pactada, la tarifa del turno en el planning si todos los turnos de la celda con ese turno dicen la misma; si no, el histórico como antes | Retención por encima |
| G4 | El Objeto de la línea contra los del planning de esa persona (o proveedor) esos días; sin Objeto, la propuesta del planning | Retención; se anula |
| G5 | La semana impresa que no es la de las fechas de la línea; lo facturado en una celda sin turnos con trabajo sin conciliar de la misma persona u Objeto a menos de cuatro semanas | Retención; se anula |
| G6 (parte nueva) | Las horas cobradas de cada recargo contra las del planning de ese recargo en la celda | Retención; se anula |
| G7 | La celda de hoy no es la conciliada (otras horas, turnos que ya no están o se cancelaron, turnos nuevos) | Aviso |
| V1 | Como G2, con los turnos facturables del cliente | Retención; se anula |
| V2 | El Objeto de la línea es del cliente y estaba activo esos días; sin Objeto, retiene (con la propuesta del planning si lo hay) | Retención; se anula |
| V3 | Como G5, en las ventas | Retención; se anula |
| V4 (escalón nuevo) | Sin tarifa de venta pactada, la del turno; sin ninguna de las dos, sin datos | Retención por encima y por debajo |
| V5 | Turnos validados facturables del Objeto y el periodo que cobra la factura que ninguna línea de venta cubre | Retención; valor a la tarifa de venta pactada o estimado |
| V6 | Trabajo validado facturable que ninguna venta cubre, pasado el fin de su periodo (el del ciclo, o el mes natural) y sus días de gracia (los del ciclo, o `planning.dias_gracia_sin_ciclo`) | Retención del cliente (clave `objeto:<id>:<inicio>`); valor y si es estimado |
| V8 | Un periodo de un ciclo de facturación, pasado con su gracia y cubierto por el planning, con trabajo facturable y sin ninguna venta que lo toque | Retención del cliente (clave `ciclo:<id>:<inicio>`) |
| V9 | Como G7, en las ventas | Retención |
| B5 (parte del planning) | Un turno conciliado con más horas de compra de las que tiene (más la tolerancia), desde dos o más facturas que no se explican entre sí | Retención; pegajosa; el hallazgo es del turno |
| V7 (caso nuevo) | El de B5 en las ventas | Retención; pegajosa |
| P7 (caducada) | Ya caducada con valor por consumir: sin planning, sin datos; con turnos de la PO después de su fin, retiene | Retención de la PO |
| P8 | Lo planificado (después de hoy) de la PO por la tarifa de su lado pasa lo que queda | Aviso de la PO |
| P10 | Facturado más lo trabajado sin conciliar más lo planificado pasa el valor; sus objetivos son las facturas desde el punto en que se pasa | Retención de la PO y de esas facturas |
| Z2 (caso nuevo) | Lo que la última foto del planning nombra y el maestro no tiene | Retención de la importación |

Los turnos de una PO (P7, P8, P10) son los que la nombran o, sin PO, los de
su parte y de un Objeto suyo si una sola PO abierta los cubre; en una PO de
cliente, solo los facturables.

**La política** (`config/reglas.yaml`, sección `planning`, y `Politica`):
`obligatorio` (falso), `tolerancia_horas_dia` («0.25», entre 0 y 1) y
`dias_gracia_sin_ciclo` (14, entre 0 y 60; un ciclo tiene los suyos).

**Lo que se lee**: `consultas.objeto` gana `horas` (`trabajo.horas_objeto`):
por semana ISO, las horas planificadas, validadas y facturables del planning,
las facturadas por los proveedores y al cliente (una línea de varias semanas
se reparte por sus días), las sin facturar (validadas facturables menos lo
facturado al cliente, en las semanas ya empezadas), las dos diferencias, y lo
esperado por cobrar y por pagar del Objeto (lo que queda de sus facturas
abiertas en la parte imputada a él) con lo trabajado sin facturar valorado
aparte. `consultas.cliente` dice el trabajo sin facturar (los V6 abiertos);
`consultas.orden_compra`, lo planificado y lo sin facturar de la PO
valorados como en P8 y P10; la ficha de una factura, su `conciliacion`
(`conciliacion.traza`). El flujo de caja lleva su línea `estimado` (decisión
22): lo trabajado sin facturar y lo planificado, por cobrar y por pagar, sin
IVA y aparte de lo esperado. Sin ningún planning, todo eso dice sin datos,
nunca cero. En la CLI: `bms-agent importar trnsprnt planning FICHERO
[--desde AAAA-MM-DD --hasta AAAA-MM-DD]` (solo para el planning), `objeto N`
con la tabla de horas, `orden N` con lo planificado y `flujo-caja` con el
estimado; en `/api/v2` por los mismos caminos, y en la consola (horas del
Objeto, trabajo sin facturar del cliente, lo planificado de la PO).

**La prioridad**: un V6 o un V8 es del cliente, no de una factura: entra en
la prioridad del cliente como una hija más (`estados._avisos_de_cliente`,
como las de una PO). Las semanas pasada la gracia de V6 las cuenta
`estados._semanas_tras_gracia` desde la fecha fija `gracia_hasta` de sus
valores: unas semanas que suben cada lunes en la huella reabrirían un V6
aceptado.

**Cambios en lo que había**: `dominio.py` (estados y niveles del turno y de
la conciliación), `campos.py` (la tabla controlada `conciliacion`),
`almacen/evidencia.py` (los turnos como evidencia), `reglas/base.py`
(`Turno`, `FotoPlanning`, `Conciliacion`, `Ciclo`, la semana impresa de una
línea, lo sin resolver de un lote y los parámetros de la política),
`reglas/instantanea.py` (el `Resolutor`, los turnos vigentes con sus
referencias resueltas en cada pasada, las fotos, las conciliaciones y los
ciclos), `reglas/catalogo.py`, `reglas/unicidad.py`, `reglas/ordenes.py`,
`reglas/calidad.py`, `politica.py`, `hallazgos.py` (`Diferencia.planning`),
`estados.py`, `consultas.py`, `flujo_caja.py`, `consola_assets.py`,
`cli.py` e `importadores/tabular.py` (lo que cubre la foto en el contrato).

### La puerta, test por test

| Puerta | Tests |
| --- | --- |
| La comparación elige el nivel (día, semana o periodo) | `test_reglas_paso10.py::test_la_comparacion_elige_el_nivel_mas_fino_de_los_dos_lados` (persona y día, Objeto y día, persona que el planning no tiene, semana entera, mes, un día de una semana que solo tiene la fila semanal), `test_cada_nivel_compara_sus_horas`, `test_la_fila_semanal_se_compara_con_todo_lo_facturado_de_su_semana` (y la que no cabe entera: sin datos), `test_planning.py::test_la_conciliacion_deja_la_traza_de_cada_linea_a_sus_turnos` (Objeto y semana, en el almacén) |
| La frontera del año ISO (una factura del 6 de enero por la semana 52) | `test_la_semana_52_de_una_factura_de_enero_es_la_del_ano_anterior` (y la 53 de 2026, la 1 facturada por adelantado y una 53 que no existe), `test_una_factura_del_6_de_enero_por_la_semana_52_se_compara_con_esa_semana` (G2 compara la 2026-W52 y no la 2027-W52, y G5 no se queja) |
| 0,25 h pasa y 0,26 h falla | `test_la_tolerancia_es_de_0_25_horas_por_dia` (G2 y V1, por encima y por debajo), `test_cada_nivel_compara_sus_horas` (0,5 h en una semana con dos días de turnos), `test_la_tolerancia_sale_de_la_politica` |
| Los turnos cancelados no cuentan | `test_un_turno_cancelado_no_cuenta` (G2, V1, G1 y V6), `test_planning.py::test_la_conciliacion_deja_la_traza...` (el cancelado no entra en la celda) |
| El trabajo sin facturar aparece solo pasado el fin del periodo más la gracia | `test_el_trabajo_sin_facturar_aparece_pasado_su_periodo_y_su_gracia` (septiembre sin ciclo: el 14 de octubre no, el 15 sí), `test_v6_valora_a_la_tarifa_pactada_y_sigue_el_ciclo`, `test_v8_un_periodo_de_un_ciclo_con_trabajo_y_sin_factura` (la gracia del ciclo), `test_planning.py::test_el_trabajo_sin_facturar_de_agosto_es_v6_del_cliente` (en el almacén, con la prioridad del cliente) |
| Un recargo nocturno a su tarifa pactada no da G3 | `test_un_recargo_de_noche_a_su_tarifa_pactada_no_da_g3` (con la tarifa pactada y sin ella, contra la del turno), `test_horas_de_noche_que_el_planning_tiene_de_dia_son_g6` |
| Un lote más nuevo que cambia una semana facturada da V9 | `test_una_foto_mas_nueva_que_cambia_una_semana_facturada_da_v9_y_g7` (otras horas y un cancelado), `test_planning.py::test_una_foto_nueva_que_cambia_una_semana_facturada_da_v9` (en el almacén: lo conciliado sigue en la primera foto) |
| Sin datos hasta que hay una importación del planning | `test_sin_ningun_planning_cada_regla_da_un_solo_sin_datos` (G1, G2, G4, G5, G7, V1, V3, V5, V6, V8, V9, B5), `test_sin_planning_g6_conserva_lo_pactado_y_p8_p10_esperan`, `test_planning.py::test_sin_planning_las_vistas_dicen_sin_datos` |
| Importar: entero o nada, clave frágil, semanal, cobertura, la más nueva manda, evidencia | `test_una_foto_del_planning_entra_entera_con_sus_turnos`, `test_una_fila_que_no_se_lee_rechaza_la_foto_entera`, `test_la_exportacion_semanal_se_lee_por_semanas`, `test_lo_que_cubre_una_foto_se_puede_decir_y_no_admite_turnos_de_fuera`, `test_vale_la_foto_mas_nueva_de_cada_dia`, los contratos de `test_importadores.py` y `test_almacen.py` (los turnos entre las tablas de evidencia) |
| La conciliación: traza, retirada, frescura | `test_la_conciliacion_deja_la_traza_de_cada_linea_a_sus_turnos`, `test_si_cambia_la_imputacion_la_conciliacion_se_retira_y_se_rehace`, `test_con_el_planning_pasado_de_su_frescura_no_se_concilia` |
| G1, G4, V2, G5, G6, B5, V7, P7, P8, P10 y el escalón del planning de G3 y V4 | Los tests de cada una en `test_reglas_paso10.py` |
| Las horas del Objeto y el estimado; la CLI | `test_las_horas_del_objeto_y_el_estimado_salen_del_planning`, `test_la_cli_importa_el_planning_y_ensena_las_horas_del_objeto` |
| Cada regla lee lo que declara | `test_pureza_reglas.py` con los escenarios del paso 10 (`test_reglas_paso10.escenarios`) |

### Desviaciones de la especificación, y por qué

1. **La migración es la 0012**, no la 0007 del §11: la numeración ya va por
   la 0011.
2. **El estado de un turno con sus horas dadas por buenas es `validado`, no
   «aprobado»** (las *approved hours* del §7). La suite de alcance no deja
   ningún estado que diga «aprobado»: nada en la V1 aprueba nada. La columna
   de sus horas se llama `horas_aprobadas_mil`, como en el §5, porque es lo
   que la exportación llama así (*Goedgekeurd*).
3. **Seis niveles de celda, no tres.** El §7 dice «recurso y día, luego
   Objeto y día, luego Objeto y semana». Hacen falta también la persona y la
   semana (una fila de la exportación semanal es de una persona) y el
   periodo (una línea de un mes entero o de unos días sueltos), con persona
   u Objeto.
4. **Sin ningún planning, un solo sin datos por regla** (tabla `planning`,
   fila 0), no uno por factura: nunca ok, y la caché no crece en cinco mil
   filas por regla (la puerta de rendimiento del paso 3). V2 no espera al
   planning: lo que mira del Objeto no depende de él (solo la propuesta).
5. **Lo que el planning nombra y el maestro no tiene entra sin resolver**, no
   se rechaza: una foto sin un turno daría por no trabajado lo que sí lo
   está. No se crea nada (§9); lo dice Z2, en la importación, solo de la
   última foto (las anteriores ya no valen). Se vuelve a buscar en cada
   pasada sin tocar la fila (evidencia).
6. **Lo que cubre una foto** es del primer al último día que trae, o lo que
   se diga al importar; un turno fuera de lo dicho rechaza la foto. Una
   foto que no trae un día que dice cubrir dice que ese día no hay turnos.
7. **La foto que vale es la más nueva por día**, y una fila semanal deja de
   valer entera en cuanto una más nueva cubre algún día de su semana
   (mezclarla con turnos diarios contaría dos veces). Los días de esa semana
   que ninguna foto más nueva cubre son un **hueco**: el planning no dice
   nada de ellos (revisión, abajo).
8. **La conciliación queda congelada por imputación**, con todos los turnos
   de la celda (también los de cero horas): es la celda tal como era, que
   es con lo que comparan G7 y V9. Se reparte en el orden de los turnos y lo
   que sobra va al último (si no, B5 y V7 no verían las horas de más).
9. **G1 bloquea solo con el planning declarado obligatorio** (la severidad de
   cada resultado); si no, retiene. Anularlo pide segunda firma siempre. Con
   el planning obligatorio, no tener con qué comparar (ningún planning,
   pasado de su frescura o sin cubrir lo facturado) también bloquea (revisión).
10. **G2 y V1 comparan solo horas validadas** (las de un turno en estado
    validado): una celda con un turno sin validar da sin datos (comparar con
    las planificadas daría por buenas unas horas que nadie ha validado),
    salvo que lo facturado pase lo que tienen sus turnos (validadas,
    realizadas o planificadas) más la tolerancia: entonces retiene (revisión).
11. **La tolerancia es la de la política por cada día con turnos de la
    celda** (los de una fila semanal, sus días): 0,25 h en un día y 1,25 h en
    una semana de cinco días.
12. **G5 y V3 miran dos cosas**: la semana impresa que no es la de sus
    fechas, y lo facturado en días sin turnos con trabajo sin facturar de la
    misma persona u Objeto a menos de cuatro semanas (el trabajo de otra
    fecha facturado con la que no es).
13. **El escalón del planning de G3 y V4 solo vale si todos los turnos de la
    celda con ese turno dicen la misma tarifa**: si dicen varias, no se
    adivina (G3 sigue con el histórico; V4 da sin datos).
14. **B5 es solo la parte del planning** (lo que pide el paso 10): un turno
    conciliado con más horas de compra de las que tiene desde dos facturas o
    más que no se explican entre sí. Una sola factura que cobra de más es G2.
    El caso de «la misma persona, Objeto y día en dos líneas» sin planning
    queda pendiente (B4 cubre los periodos que se pisan por Objeto).
15. **V5 y V6 se separan por el periodo facturado**: V5 es lo que falta
    dentro del Objeto y el periodo que cobra una factura; V6, el trabajo
    fuera de cualquier periodo facturado del Objeto (o del cliente, sin
    Objeto). Lo cubierto lo dicen las líneas y los periodos de las ventas,
    no la conciliación.
16. **V6 y V8 son hallazgos del cliente** (no hay factura): su clave lleva el
    Objeto o el ciclo y el inicio del periodo. Sin ciclo, el periodo es el
    mes natural y la gracia la de la política.
17. **P7 de una PO ya caducada**: con planning, retiene si hay turnos de la
    PO después de su fin, y es ok si no; sin planning, sin datos.
18. **P10 pone objetivos** (desviación 22 del paso 9): las facturas que le
    cargan desde el punto en que lo esperado pasa el valor, para que su
    retención y su suelo urgente lleguen a ellas.
19. **Las horas planificadas que faltan** se calculan de las horas y la pausa
    redondeadas a la milésima (8,333 h de 7:10 a 15:30).
20. **Las fechas de una línea no son evidencia de V2**: los días que salen
    de ellas van en los valores; una línea sin Objeto no se reabre porque una
    persona corrija la fecha de la factura (como `NO_EVIDENCIA_PACTADA`).
21. **El estimado del flujo de caja** (decisión 22) cuenta por cobrar lo
    trabajado (realizado o validado) que no está facturado: de un turno
    conciliado con ventas, lo que le falta; de uno sin conciliar, nada si una
    venta lo cubre y todo si no. Por pagar, lo trabajado que ninguna compra
    ha conciliado. Lo planificado después de hoy, entero. Sin IVA.

### Correcciones de la revisión

La revisión del paso 10 dio diecisiete hallazgos. Todos se reprodujeron y
eran reales; cada uno tiene ahora un test que fallaba antes y pasa después
(los de las reglas en `test_reglas_paso10.py`, sección «revisión del paso
10»; los del almacén en `test_planning.py`, sección del mismo nombre). **1754
tests pasan** (eran 1733); la puerta de rendimiento sigue pasando.

1. **Unas horas validadas son las de un turno validado** (mayor). La
   exportación semanal ponía `Totaal` en las horas validadas fuera cual
   fuera su `Status`, y G2/V1 miraban la columna, no el estado: una fila
   planificada de 40 h hacía buenas 40 h facturadas. Ahora: el mapeo semanal
   pone `Totaal` en el campo canónico nuevo `horas_total`, que
   `TurnoCanonico` lleva a las horas de su estado (validadas, realizadas o
   planificadas); un turno que no está validado y trae horas validadas
   rechaza la foto (el fichero se contradice); `turnos.horas_validadas` y
   `turnos.horas_referencia` miran el estado, y G2/V1 también. La migración
   **0013** vuelve a crear `v_planning_estado` con la misma cuenta (0012 ya
   está aplicada y no se edita), y la traza de la ficha igual. Los
   contratos de los dos mapeos ganan el campo `horas_total` (nulo en el
   diario). Tests: `test_unas_horas_en_la_columna_de_validadas_...`,
   `test_el_total_de_una_fila_semanal_va_a_las_horas_de_su_estado`.
2. **Un tramo de más de 92 días no da «ningún turno»** (mayor).
   `Indice.de` dejaba de mirar pasados `DIAS_MAXIMOS`, y G1 y V5 lo llamaban
   con el periodo entero de la factura: una compra trimestral daba G1 fallo
   (bloqueo con el planning obligatorio) y una venta trimestral V5 ok. Un
   tramo largo se busca ahora por los turnos de esa persona, Objeto o parte
   (el índice guarda también esa lista), y da lo mismo que día a día. Test:
   `test_un_periodo_de_mas_de_92_dias_...`.
3. **Una PO cubre un turno sin número solo en su vigencia** (mayor).
   `_cubre_turno` exige ahora que los días del turno caigan entre el inicio
   y el fin de la PO (abierta por donde no lo dice): una PO caducada con
   valor y la que la sustituye ya no se reparten los mismos turnos. P7 de
   una caducada cuenta sus turnos de después del fin que la nombran o que
   ninguna otra PO abierta cubre (`ordenes.sin_po_tras_fin`). Test:
   `test_una_po_caducada_y_la_que_la_sustituye_...`.
4. **G7/V9 miran lo facturado contra el planning de hoy** (mayor). La
   conciliación se escribe muchas veces con turnos aún planificados; al
   validarse con las horas que la factura ya cobraba, V9 retenía igual. De
   cada turno que cambió desde la conciliación, se comparan ahora sus horas
   de hoy con las que le cobran las facturas de ese sentido (lo conciliado
   con él), con la tolerancia por día; si cuadran, ok («lo facturado es lo
   que dice ahora»). Los valores de un fallo llevan `facturadas`. Test:
   `test_un_turno_planificado_que_se_valida_con_lo_facturado_no_da_v9`.
5. **Una línea del Objeto no se lleva el turno de una persona** (mayor).
   En una pasada se reparten primero las imputaciones de una persona; y una
   conciliación automática de Objeto **cede**: si una imputación nueva de
   una persona no cabe en sus turnos porque una de Objeto los ocupa, la de
   Objeto se retira y se vuelve a repartir después con lo que queda
   (`conciliacion._ceden`). Lo que se pierde: esa imputación de Objeto se
   vuelve a conciliar contra el planning de ese momento, no el de su primera
   conciliación (si cambió entre medias, G7/V9 ya no lo ven por ella; G2/V1
   sí). Tests: `test_las_horas_de_una_persona_no_se_las_lleva_...` (dos
   pasadas) y `test_en_una_pasada_se_reparten_antes_...`.
6. **Los huecos de una fila semanal que ya no vale** (menor). Lo que cubre
   el planning ya no cuenta los días de la semana de una fila semanal que
   dejó de valer y que ninguna foto más nueva cubre:
   `instantanea.huecos_planning` los calcula por foto (`FotoPlanning.huecos`)
   y `turnos.tramos` los quita. Una línea de esos días da sin datos, no «0 h
   validadas». Tests: `test_lo_que_cubre_el_planning_no_cuenta_los_huecos_...`
   y `test_los_dias_de_una_fila_semanal_que_ya_no_vale_no_estan_cubiertos`.
7. **24:00 y los turnos de 24 horas** (menor). Un fin a las `24:00` es
   medianoche (solo como fin); un turno que empieza y acaba a la misma hora
   dura 24 horas, no cero (una guardia de un día entero). Test:
   `test_un_fin_a_las_24_00_y_un_turno_de_24_horas`.
8. **Una foto que borraría el planning pide confirmación** (mayor). Lo que
   cubre una foto sustituye a todo lo de antes, y una fecha mal escrita, un
   fichero vacío con un `--desde/--hasta` amplio o una exportación filtrada
   borraban en silencio meses de planning (y cerraban los V6). Ahora no se
   importa, sin escribir nada (ni la importación: un fichero rechazado queda
   apuntado por su hash y no se podría reimportar), una foto sin turnos, con
   más de `HUECO_MAXIMO_DIAS` (14) días seguidos sin turnos dentro de lo que
   cubre, o que deja sin valer más de `DESAPARECEN_MINIMO` (3) turnos del
   planning de ahora y más del `DESAPARECEN_PCT` (20 %) de los de esos días
   sin traerlos (`importadores/planning.riesgos`, `PideConfirmacion`). Con
   `--confirmar` (CLI) o `confirmar=True` entra con esos avisos. Cuántos
   turnos de antes deja de valer va siempre en los avisos y en el evento
   `planning_registrado` (`dejan_de_valer`, `riesgos`, `confirmado`). Test:
   `test_una_foto_que_borraria_el_planning_pide_confirmacion`.
9. **G2/V1 con turnos sin validar tienen un tope** (mayor). Una celda con
   turnos sin validar daba sin datos, que no retiene: se podían cobrar 80 h
   contra un turno planificado de 8. Ahora lo facturado se compara con lo
   que tienen sus turnos (`horas_referencia`) más la tolerancia: si lo
   pasa, retiene (valores `tope_mil`, `sin_validar`); si no, sin datos como
   antes. Test: `test_cobrar_mas_de_lo_que_tienen_unos_turnos_sin_validar_retiene`.
10. **El planning obligatorio bloquea sin planning** (mayor). Con
    `planning.obligatorio`, G1 bloquea (severidad B, segunda firma para
    anularlo) también sin ningún planning (un resultado por compra, no el
    sin datos de la fila 0), con el planning pasado de su frescura o sin
    cubrir lo facturado, diciendo por qué (`causa`). Sin obligatorio, como
    antes. Test: `test_con_el_planning_obligatorio_g1_bloquea_...`.
11. **Una conciliación manual no la retira el motor** (menor). Solo si su
    imputación ya no está en juego; su huella (nula) ya no cuenta. Test:
    `test_una_conciliacion_manual_sobrevive_a_la_pasada_del_motor`.
12. **Lo esperado de un Objeto no pasa de la factura** (menor). Su parte se
    mide en valor absoluto: con signos mezclados la suma con signo podía
    darle diez veces lo que queda. Test:
    `test_lo_esperado_de_un_objeto_no_pasa_de_lo_que_queda_de_la_factura`.
13. **G4, G5, V3 y la parte del planning de G6 dan sin datos** (mayor), con
    la misma clave que su ok o su fallo, cuando el planning está pasado de
    su frescura o no cubre los días (G4, también cuando la línea no dice sus
    días): antes no daban nada y su hallazgo abierto se cerraba solo al
    envejecer el planning. Tests: `test_g4_g5_v3_y_g6_dan_sin_datos_...` y
    `test_un_v3_abierto_no_se_cierra_porque_el_planning_envejezca`.
14. **P7, P8 y P10 miran la frescura y lo que cubre el planning** (mayor).
    Con el planning pasado de su frescura, sin datos. P8 y P10: pasarse del
    valor se puede decir con lo que se ve (es lo menos que hay), pero que
    cabe no, si el planning no cubre de mañana al fin de la PO (sin fin,
    hoy): sin datos. P7 de una caducada sin turnos después de su fin: sin
    datos si el planning no cubre del día siguiente al fin hasta hoy. Test:
    `test_p7_p8_y_p10_no_dicen_ok_con_un_planning_viejo_o_que_no_llega`.
15. **Las horas del Objeto de una semana sin planning son sin datos**
    (menor). Cada semana dice su `cobertura` (`entera`, `parcial`,
    `ninguna`): sin cobertura, sus horas del planning son None; lo sin
    facturar solo con la semana entera cubierta. Con el planning pasado de
    su frescura el bloque dice `"planning": "caducado"` (la CLI y la consola
    lo enseñan). **El corte por mes del §5 (`v_objeto_periodo`) pasa al paso
    12**, con los ingresos, costes y margen: es esa vista, y por mes la
    pregunta de a qué mes atribuir una línea de varias semanas es la misma
    que la del margen. Test: `test_las_horas_de_un_objeto_de_una_semana_sin_planning_...`.
16. **G6 valora su diferencia de horas** (menor): `valor_cent`, las horas
    de más por la tarifa más alta de sus líneas, como G2 (entra en los
    tramos de 500/2.500 € de la prioridad). Test:
    `test_g6_valora_las_horas_de_un_recargo_que_no_estan_en_el_planning`.
17. **G1 cuenta cada turno una vez** (menor), aunque salga por su proveedor
    y por su persona. Test: `test_g1_cuenta_una_vez_...`.

**Tests existentes cambiados en la revisión**:
`test_planning.py::test_la_exportacion_semanal_se_lee_por_semanas` (el
ejemplo semanal trae la semana 42 y la 53, diez semanas sin turnos en medio:
ahora pide `--confirmar`, y con él entra con su aviso; el resto del test no
cambia) y los contratos `trnsprnt-planning-v1.esperado.json` y
`trnsprnt-planning-semana-v1.esperado.json` (el campo `horas_total`).
`test_reglas_paso10.escenarios` gana tres escenarios (el planning
obligatorio sin planning, uno viejo con PO y turnos sin validar cobrados de
más, con un hueco) para que `test_pureza_reglas` pase por las ramas nuevas.

### Lo que deben saber los pasos siguientes

- **Cuando llegue una exportación real de TRNSPRNT**: se escribe la versión
  2 de los mapeos (no se editan las de ahora), con su ejemplo anonimizado y
  su contrato. Si no trae un identificador estable por turno, hay que
  pedirlo: la clave sintética no reconoce un turno al que le cambian la hora,
  y G7/V9 lo verían como uno quitado y otro nuevo.
- **Las cuentas de TRNSPRNT** (F5, F6 contra TRNSPRNT) siguen sin datos: no
  hay exportación de cuentas.
- **Una regla nueva que mire el planning** usa `turnos.Planificacion`,
  `turnos.agrupar` y `turnos.celda_de` (las mismas celdas que la
  conciliación) y empieza con `turnos.sin_planning`. Nada que dependa de hoy
  va en los valores (el V6 guarda `gracia_hasta`, no las semanas).
- **La conciliación manual** (`metodo` manual) ya la admite la base, con
  `cambiar_objeto`; no hay todavía una orden que la escriba. El motor no la
  retira mientras su imputación siga en juego (revisión, 11).
- **Paso 12**: la vista del Objeto ya tiene sus horas por semana y lo
  esperado; faltan ingresos, costes y margen (`v_objeto_periodo`) y el corte
  por mes (revisión, 15). Las horas por semana se
  reparten por días; el margen tendrá que decidir si atribuye por periodo de
  trabajo o por fecha de factura (pregunta 10 del §12).
- **Una vista nueva que necesite el planning** construye la instantánea
  (`consultas._planning`): es lo que cuesta, unas décimas de segundo con
  cinco mil facturas.

**Tests existentes cambiados, y por qué**: `test_reglas.py` (el catálogo
del §7 gana B5, G1, G2, G4, G5, G7, V1, V2, V3, V5, V6, V8 y V9; V6 y V8
son del cliente; y la comparación con las reglas de la v1 solo mira las
filas de factura, porque el sin datos sin planning es de la fila 0 de la
tabla `planning`), `test_hallazgos.py` (las reglas del planning solo hablan
de las facturas que ponen en el planning, y la caché por factura no cuenta
las filas que no son de una factura), `test_reglas_paso9.py` (P8 y P10 dicen
que esperan al planning, no «al paso 10»), `test_importadores.py` (el mapeo
del planning tiene su ejemplo y su contrato), `test_almacen.py` (los turnos
son evidencia: una fila más al poblar) y `test_pureza_reglas.py` (los tipos
y los escenarios del paso 10, y `turnos` entre los módulos propios).

## Paso 11

El BTW: las cifras de cada trimestre, la hoja de trabajo con la lista de lo
que hay que revisar, y el estado de la declaración (abierto, listo para
revisar, presentado). **1863 tests pasan** tras la revisión (1848 al cerrarlo; eran 1754), ninguno llama a la
API y ninguno escribe fuera de una carpeta temporal. Cinco mil facturas se
recalculan en 1,05-1,28 s la primera vez y en 0,99-1,03 s las siguientes
(cuatro medidas; el paso 10 medía 1,21-1,54 s y 1,09-1,29 s): sin ningún
trimestre presentado, C4 no mira nada. El resumen del BTW de esas cinco mil
facturas tarda 0,06-0,09 s.

**Nada aquí presenta nada ni habla con la Belastingdienst** (regla 5 de
arquitectura.md). El agente calcula, genera la hoja y la guarda; una persona
con `gestionar_btw` la marca lista, otra (si la hay) presenta la declaración
en el portal a mano y lo anota después con la referencia del acuse. Ninguna
orden se llama «presentar» ni «declarar» (la suite de alcance lo mira), y
`btw.py` no importa nada de red (`test_btw_no_habla_con_nadie_de_fuera`).
Todo `config/btw.yaml` está **por confirmar con el asesor**: cada hoja lo dice
en su cabecera mientras `confirmado` sea falso.

### Qué se construyó

**Migración `0014_btw.sql`** (la siguiente libre; el §11 la llama 0008):

- `periodo_btw` (controlada, guardas generadas con
  `scripts/generar_guardas.py`, escrita solo por `btw.py`, como la
  excepción): las columnas del §5.G n.º 45, con `hoja_id` en vez de
  `hoja_documento_id` y dos más, `listo_en` y `listo_por` (desviaciones 2 y
  3). Los CHECK fijan el calendario (el trimestre natural, los plazos después
  de su fin) y lo que lleva cada estado: abierto no tiene hoja; listo, la hoja
  y quién la marcó; presentado, además la referencia, lo declarado, quién y
  el día, posterior al trimestre. Los disparadores: solo una persona activa
  con `gestionar_btw`, en su propia orden, da de alta o cambia un periodo;
  **un trimestre presentado no cambia nunca** (`periodo_btw_presentado_no_cambia`:
  ni vuelve atrás ni se toca la referencia o la nota); no nace presentado; se
  presenta desde `listo_revision`, con la misma hoja y lo anota quien firma; la
  hoja de un periodo listo o presentado es una hoja guardada de ese trimestre
  con ese sha256; el periodo no cambia de trimestre.
- `hoja_btw` (**solo escritura**, evidencia como una nota): cada hoja de
  trabajo que se marcó lista, entera (`contenido`) y con el sha256 de sus
  bytes; la guarda una persona con `gestionar_btw` en el evento
  `btw_hoja_guardada`. La misma hoja no se guarda dos veces.
- `periodo_btw_declarada` (**solo escritura**): lo que se declaró de cada
  factura al anotar la presentación (su huella de IVA, su base y su cuota).
  Solo se escribe en el evento `btw_presentacion_anotada` de su periodo, ya
  presentado. Es contra lo que mira C4.
- `v_btw_linea`: las líneas de IVA de las facturas que cuentan
  (`v_iva_vigente`: ni anuladas, ni fusionadas, ni sustituidas), con su año y
  trimestre por la fecha de factura. Una línea por fila viva de `factura_iva`
  (con el tratamiento de la fila o, si no lo dice, el de la factura); sin
  desglose, una con la cabecera.

**`config/btw.yaml`**, cargado con `bms-agent politica cargar` (admin) y
versionado en `politica_version` como los demás: trimestral, factuurstelsel,
los dos plazos el último día del mes siguiente, los tipos habituales (0, 9 y
21 %) y el de la autoliquidación (21 %, deducible), el umbral de la KOR
(20.000 €, aviso desde el 90 %) y a qué rúbrica va cada línea: las ventas con
IVA normal por tipo (1a, 1b, 1e, y 1c los demás), el tipo cero en 1e, el IVA
trasladado al cliente en 1e (nacional y de fuera de la UE) o 3b (UE), exento
y KOR fuera; las compras con IVA normal en 5b, el IVA trasladado en 2a
(nacional), 4b (UE) o 4a (fuera de la UE), y lo demás fuera.
`politica.ConfigBtw` tiene esos mismos valores por defecto (un test los
compara con el fichero); `config_btw_de_yaml` rechaza entero lo que la V1 no
sabe hacer (otra periodicidad, kasstelsel, otros plazos, un mapeo incompleto o
una rúbrica donde una línea no puede ir, un tipo de autoliquidación del 0 %,
un umbral o un aviso fuera de sus límites). Mientras no se carga ninguno, la
primera hoja que se marca lista apunta el de partida (`apuntar_btw_en_uso`),
para que el hash que lleva la hoja se pueda resolver a un texto.

**Módulos nuevos y lo que cambia**

| Módulo | Qué hace |
| --- | --- |
| `btw.py` | El calendario (`periodo_de`, `limites` con `reloj.limite_btw`, `etiqueta` «2026-T3»); las líneas de `v_btw_linea` con la contraparte y su país (`lineas`); `clasificar` y `cifras` (puras): rúbricas, 5a, 5b, 5c, ingresos y costes sin IVA, IVA repercutido, autoliquidado y deducible, lo que queda fuera; `revisar` (las facturas que piden revisar el IVA); `diferencias` (lo que ya no es lo declarado de un trimestre presentado); la hoja (`hoja`, `celda`); las vistas (`trimestre`, `resumen`); las órdenes (`marcar_lista`, `reabrir`, `anotar_presentacion`) y `verificar` |
| `reglas/fechas.py` | C4 |
| `reglas/iva.py` | `lineas_iva`, `pais_iva`, `huella_iva` (lo mismo que `v_btw_linea`, para C4), E0, E5 y E7 |
| `reglas/base.py` | `PeriodoBtw`, `Instantanea.periodos_btw`, `TramoIva.tratamiento`, `Parte.verlegd_elegible` y, en `Politica`, `iva_tipos_habituales_pb`, `kor_umbral_cent` y `kor_aviso_pct` (de `btw.yaml`) |
| `reglas/instantanea.py` | Los trimestres presentados con lo declarado, el tratamiento de cada fila del desglose y la marca `verlegd_elegible` de cada cliente |
| `politica.py` | `ConfigBtw`, su lector y su escritor, `config_btw`, `apuntar_btw_en_uso`; `politica cargar` acepta `btw.yaml` |
| `almacen/evidencia.py` | `hoja_btw` (su texto rehasheado) y `periodo_btw_declarada` (toda la de un trimestre en el evento de su presentación) como evidencia |
| `servicios.py` | Las órdenes `btw_lista_para_revision` (motivo obligatorio), `btw_reabrir` (motivo y rev obligatorios) y `btw_anotar_presentacion` (motivo y rev obligatorios), todas con `gestionar_btw` |
| `cli.py` | `bms-agent btw ver [2026-T3] [--json]` (o `btw estado`, el nombre del §6), `btw hoja 2026-T3 [--salida F]` (escribe los bytes, con su BOM, en el fichero o en pantalla, y dice su sha256), `btw listo`, `btw reabrir` y `btw anotar` (lo declarado a devolver va en negativo y sin separador de miles: `--importe-declarado -1234,56`); `db verificar` mira también los periodos |
| `serve.py` | `GET /api/v2/btw` (el resumen), `/api/v2/btw/2026-T3` (el trimestre) y `/api/v2/btw/2026-T3/hoja` (su texto y su sha256); las órdenes por `/api/v2/acciones`; un trimestre que no lo es da 404 y una orden que no tiene sentido en su estado, 409 |

**Las cifras** (`btw.clasificar`). Una venta con IVA normal va a la rúbrica
de su tipo con su base y su cuota impresa; una sin IVA (tipo cero, IVA
trasladado al cliente), solo con su base. La cuota de una compra con IVA
normal es IVA soportado (5b). **El IVA trasladado de una compra se
autoliquida**: la base por el tipo de `btw.yaml` (21 %, al céntimo y con el
medio hacia fuera, para que un abono dé lo mismo en negativo) va a 2a, 4b o
4a con su base, y vuelve como deducible en 5b: las dos cosas se compensan.
Con KOR, exento o tipo cero en una compra no hay IVA: es coste y la hoja la
lista en «fuera de las cifras». Un abono va en el trimestre de su fecha, en
negativo. Una línea en otra moneda (X1), sin tratamiento o, con IVA normal,
sin tipo o sin cuota (E0) no entra en ninguna suma: va a «sin clasificar» con
el motivo. 5a es la columna de IVA de 1a a 4b; 5c, 5a menos 5b (a pagar si
es positivo, a devolver si es negativo). Todo en céntimos: la declaración se
rellena en euros enteros, y eso lo hace la persona.

**El país de la contraparte** sale del prefijo de su btw-id impreso (el del
emisor en una compra, el del receptor en una venta): NL o ninguno es
nacional, un país de la UE es `ue`, otras dos letras `fuera_ue`. Solo cuenta
en el IVA trasladado.

**La hoja de trabajo** es un CSV con BOM, separador «;», fin de línea CRLF y
coma decimal (lo que abre bien un Excel neerlandés o español): la cabecera
(empresa, trimestre, plazos, sistema, el sha256 del `btw.yaml` en `politica_version` y si está
confirmada, y que la presenta una persona), las rúbricas con 5a, 5b y 5c, el
resumen con la estimación, cada línea con su rúbrica, las facturas que piden
revisar el IVA, lo que queda fuera y, en un trimestre presentado, las
diferencias con lo presentado. No lleva la hora ni el estado: el mismo
contenido da siempre el mismo sha256. **Todo texto que viene de un documento
(número, nombre de la contraparte) se neutraliza**: si empieza por `=`, `+`,
`-`, `@`, un tabulador o un salto de línea (o, tras espacios, por uno de los
cuatro primeros), lleva un apóstrofo delante. Los importes que escribe el
sistema no (un «-105,00» es un número).

**Las facturas que piden revisar el IVA** (§7: «las del trimestre con
hallazgos de IVA abiertos, más C4»): las facturas del trimestre con un
hallazgo pendiente (abierto o desaparecido sin cerrar) de una regla con
entrada de IVA (dura o blanda, como las cuenta el §8; hoy D3, E0-E5, E7 y C4), por su
`factura_id` o por sus objetivos, más las de C4 de ese trimestre aunque ya no
estén en él (por la clave del hallazgo). Desde la revisión, también las que
ponen el IVA en duda sin ser de IVA y las que quedan fuera de las cifras
(desviación 16).

**El estado** (`btw.marcar_lista`, `reabrir`, `anotar_presentacion`):

- **listo para revisar**: solo con el trimestre terminado, con motivo. La
  persona da el sha256 de la hoja que vio; si la hoja cambió desde entonces,
  Conflicto. La hoja se guarda entera en `hoja_btw` y su hash queda en el
  periodo. Marcarlo otra vez con la misma hoja no hace nada.
- **reabrir**: de listo a abierto, con motivo y la rev de lo que se vio; la
  hoja deja de valer (sigue guardada).
- **presentado**: desde listo, con motivo y la rev del periodo, con la hoja
  que se marcó y con las cifras de hoy siendo todavía las suyas (la huella que
  lleva escrita; si no, Conflicto: se vuelve a marcar lista y a revisar), la
  referencia del acuse (obligatoria), lo declarado (en negativo,
  a devolver) y el día (después del trimestre y no en el futuro; por defecto,
  hoy). Quien la marcó lista no la anota si hay otra persona con
  `gestionar_btw` (`si_hay_dos`; si no, el evento dice `autorrevisado`). En la
  misma orden se apunta lo declarado de cada factura. **Es irreversible**:
  ninguna orden lo toca y la base para cualquier escritura.

**Reglas nuevas**

| Regla | Qué mira | Al fallar |
| --- | --- | --- |
| C4 | Por cada trimestre presentado, cada factura que cuenta en él por su fecha de factura y no es lo declarado: llegó después («tarde»), su huella de IVA cambió («cambio»), o se declaró y ya no cuenta allí (anulada, sustituida, en otra moneda o con otra fecha: «fuera») | Aviso; se anula; clave «2026-T3»; a la lista del trimestre |
| E0 | El tratamiento del IVA no se sabe, o con IVA normal falta el tipo (ni en la cabecera ni en todas las líneas; en una venta, un solo tipo en las líneas) o la cuota, o una fila del desglose no trae base o tratamiento, o con IVA normal (bajo cualquier cabecera) no trae tipo o cuota. Ilegible no es que falte (Q2) | Retención; no se anula |
| E5 | Lo que un proveedor con KOR ha facturado a BMS en el año natural (bases, abonos restando) llega al 90 % del umbral | Aviso del proveedor (clave el año), con la factura desde la que pasa el aviso como relacionada; su evidencia es si ya pasa el umbral |
| E7 | Un tipo que no es de la lista (0, 9, 21); una venta al 0 % o con IVA trasladado a un cliente que el maestro no tiene marcado `verlegd_elegible` (sin cliente resuelto: sin datos) | Retención; se anula; claves «tipo» y «tratamiento» |

C4, E0 y E7 solo escriben lo que objetan, como las reglas de factura del
paso 5. Una factura en otra moneda no les dice nada (es X1).

### La puerta, test por test

| Puerta | Tests |
| --- | --- |
| El IVA normal al 21 % | `test_btw.py::test_el_iva_normal_al_21_va_a_1a_y_5b_y_queda_a_pagar_la_diferencia` (1a, 1b, 1e, 5a, 5b, 5c, ingresos, costes y la hoja) |
| El IVA trasladado de una compra en 2a y 5b, compensado | `test_el_iva_trasladado_de_una_compra_va_a_2a_y_5b_y_se_compensa` (2a, 4b y 4a por país, y un desglose con una fila normal y otra trasladada) |
| La KOR | `test_una_compra_con_kor_no_tiene_iva_que_declarar`; E5 en `test_reglas_paso11.py::test_e5_avisa_al_llegar_al_porcentaje_del_umbral` y `test_e5_solo_el_ano_de_hoy_lo_que_cuenta_y_quien_sigue_con_kor` |
| Un abono en un trimestre posterior | `test_un_abono_de_un_trimestre_posterior_cuenta_en_el_suyo` (de venta y de compra: va al cuarto trimestre en negativo; el tercero, presentado, sigue siendo su hoja y no da C4), `test_reglas_paso11.py::test_c4_un_abono_de_un_trimestre_posterior_no_reabre_el_presentado` |
| El plazo del cuarto trimestre es el 31 de enero; el del tercero de 2026, el 2026-10-31 | `test_el_plazo_es_el_ultimo_dia_del_mes_siguiente_al_trimestre` (seis trimestres, presentar y pagar), `test_los_plazos_van_al_trimestre_a_la_hoja_y_al_periodo` |
| Presentar es irreversible y queda con su hash | `test_presentar_es_irreversible_y_queda_con_el_hash_de_la_hoja` (la hoja guardada es la que se ve y su sha256 el de sus bytes; ninguna orden ni escritura auditada lo devuelve atrás; hoja y lo declarado de solo escritura; separación de funciones), `test_la_hoja_que_se_presenta_es_la_que_se_marco_lista` (hoja cambiada: Conflicto; reabrir; fechas; autorrevisado), `test_el_btw_por_la_cli` (el sha256 del fichero exportado es el que queda en el periodo), `test_verificar_ve_un_periodo_una_hoja_o_lo_declarado_tocados_por_detras` |
| Una factura tardía en un trimestre presentado da C4 | `test_una_factura_que_llega_tarde_a_un_trimestre_presentado_da_c4` (en el almacén, con la lista de revisar, las diferencias de la hoja y una declarada que se anula), `test_reglas_paso11.py::test_c4_una_factura_tardia_en_un_trimestre_presentado` y `test_c4_una_factura_que_cambio_o_ya_no_cuenta_alli` |
| C4, E0 y E7 | Los tests de cada una en `test_reglas_paso11.py`; `test_btw.py::test_e7_lee_la_marca_del_maestro_de_clientes` (la marca de Exact, en el almacén) |
| Lo demás | Lo que queda fuera de las cifras, la lista de revisar, la vista contra las reglas (`test_la_vista_y_las_reglas_dicen_lo_mismo_de_cada_factura`), la neutralización de fórmulas, los permisos y los disparadores, la configuración (de partida, rechazos, la cargada cambia la hoja), el resumen, la CLI y la API, en `test_btw.py`; la pureza en `test_pureza_reglas.py` con `test_reglas_paso11.escenarios` |

### Desviaciones de la especificación, y por qué

1. **La migración es la 0014**, no la 0008 del §11: la numeración ya iba por
   la 0013.
2. **La hoja vive en su propia tabla (`hoja_btw`) y el periodo apunta a ella
   con `hoja_id`**, no con `hoja_documento_id`. `documento` es para los
   originales que entran (con su origen, su llegada y su vía); la hoja la
   genera el sistema. Se guarda entera y es evidencia: `db verificar`
   rehace su sha256.
3. **El periodo lleva `listo_en` y `listo_por`.** Hacen falta para la
   separación de funciones (quien marca la hoja lista no anota la
   presentación habiendo otra persona) y para el disparador que pide que la
   presentación sea de la hoja que se marcó.
4. **Una tabla más, `periodo_btw_declarada`.** «Cambió después de presentar»
   (C4, §7) solo se puede ver si se guarda lo que se declaró de cada factura.
5. **«Presentado» pasa por «listo para revisar»** y por la misma hoja: el
   hash que queda es el de lo que se revisó, y las cifras de ese momento
   tienen que seguir dándolo. Una hoja que cambió entre medias se vuelve a
   marcar lista. Listo solo se marca con el trimestre terminado; el día de la
   presentación es posterior al trimestre y no futuro; la referencia y lo
   declarado son obligatorios.
6. **El mapeo de rúbricas se aplica en Python, no en la vista.** La base no
   lee `btw.yaml`; `v_btw_linea` da las líneas y `btw.py` las clasifica con la
   configuración vigente. Las columnas `rubrica`, `cuota_autoliquidada_cent` y
   `deducible` de `factura_iva` (migración 0008) siguen sin rellenar: un
   cambio de configuración vale para los trimestres sin presentar sin
   reescribir facturas, y uno presentado queda con su hoja y lo declarado.
7. **El IVA autoliquidado es la base por el tipo de `btw.yaml`** (21 %), por
   línea, y vuelve entero en 5b (`autoliquidacion_deducible`). El país
   (2a, 4b o 4a; 1e o 3b en ventas) sale del prefijo del btw-id impreso; sin
   btw-id, nacional. Todo por confirmar con el asesor.
8. **C4 mira la fecha de factura, no el periodo de prestación** (el §7 dice
   «fecha o periodo»): en factuurstelsel una factura se declara en el
   trimestre de su fecha, y mirar el periodo marcaría casi todas las de las
   primeras semanas tras cada presentación. Además de la tardía, avisa de la
   que cambió y de la declarada que ya no cuenta allí; un hallazgo por
   factura y trimestre.
9. **E5 cuenta lo facturado, no lo pagado** (el §7 dice «paid»). El umbral de
   la KOR es sobre la facturación del proveedor, y lo pagado depende de
   cuándo paga BMS. Es del año natural de hoy, del proveedor (no de una
   factura), y solo si su última factura del año sigue siendo KOR. El paso
   11 no lo pedía; el encargo decía hacerlo si no estaba.
10. **E7 da sin datos** en una venta sin IVA sin cliente resuelto (no se puede
    saber si está marcado). Una venta con IVA normal con una línea al 0 % cuenta
    como venta al 0 %.
11. **E0 con desglose solo mira las filas con IVA normal** (una fila de IVA
    trasladado no lleva cuota), y como Q1 no cuenta como falta lo ilegible.
12. **Solo trimestral y factuurstelsel**, con el plazo fijo del último día
    del mes siguiente para presentar y pagar: el cargador rechaza lo demás en
    vez de prepararlo mal. Mensual, anual o kasstelsel necesitarían otro
    calendario y otra atribución de facturas.
13. **Los trimestres anteriores** del resumen son los que tienen facturas o
    estado, más los ya terminados del año en curso y el anterior al de hoy
    aunque estén vacíos (un trimestre sin facturas también se declara; en
    enero, el cuarto del año pasado, que vence el 31). Los de años anteriores sin
    nada no salen: serían ruido de antes de que existiera el agente.
14. **El año hasta hoy** es por fecha de factura, del 1 de enero a hoy.
15. **La hoja usa coma decimal y BOM** y no lleva hora ni estado (el mismo
    contenido, el mismo hash).
16. **La lista de las facturas que piden revisar el IVA es más que la del §8**
    («hallazgos de IVA abiertos, más C4»). Lleva también las que tienen
    pendiente un duplicado (B2, B3), una original con su sustituta (R3) o una
    factura que no va dirigida a BMS (A8): sumarían su IVA dos veces o un IVA
    que no es de BMS, y sin esto un trimestre se marcaba listo y se anotaba
    con el IVA soportado doble sin que nada lo dijera. Y Q2 cuando la lectura
    dudosa es de lo que se declara (base, cuota, total, tipo, tratamiento o
    fecha). Y toda factura con una línea fuera de las cifras («sin
    clasificar»), con su motivo en la columna «Fuera de las cifras», tenga el
    hallazgo que tenga: lo que no se suma lo tiene que ver alguien. No se
    impide marcar listo con retenciones abiertas: la persona las ve en la
    hoja y decide.
17. **La hoja lleva escrita la huella de sus cifras** (`Huella de las
    cifras`, `btw.huella_cifras`: rúbricas, 5a-5c y cada línea con sus
    importes y su rúbrica, sin nombres ni hallazgos). Marcar lista sigue
    pidiendo la hoja exacta que se vio; anotar la presentación compara la
    huella de hoy con la escrita en la hoja marcada, no la hoja entera.
    Resolver o anular un hallazgo, o corregir el nombre de un proveedor,
    entre listo y anotar es lo normal (es cuando el asesor revisa) y antes
    obligaba a volver a marcarla, lo que además movía `listo_por` y, con dos
    personas, dejaba a quien la volvía a marcar sin poder anotarla. Lo
    presentado queda con la hoja marcada (su sha256 y su texto) y el evento
    lleva las dos huellas. Una hoja guardada antes de llevarla solo vale
    entera, como antes.
18. **`btw estado` es `btw ver`**: el §6 nombra `btw estado`; la CLI lo
    reparte en `ver` (o `estado`), `hoja`, `listo`, `reabrir` y `anotar`,
    porque cada orden pide cosas distintas (la hoja, el motivo, la rev, la
    referencia) y las tres últimas son órdenes de `servicios.py`.
19. **Motivo y rev de las órdenes del BTW** (§6): las tres piden motivo;
    `reabrir` y `anotar` la rev del periodo. `listo` no la pide: el periodo
    puede no existir todavía (no tiene rev) y su testigo de concurrencia es
    el sha256 de la hoja que se vio, que cambia con cualquier cosa que la
    hoja enseñe.
20. **En una venta sin tipo en la cabecera, E0 pide un solo tipo en sus
    líneas** (`reglas/iva.tipo_de_lineas`, la misma función que usa la
    declaración): con dos tipos y sin desglose no se sabe qué base va a 1a y
    cuál a 1b. En una compra sigue bastando con que todas lo traigan (5b solo
    pide la cuota).

### Lo que deben saber los pasos siguientes

- **Paso 12** (bloques del §17 y filtros del §18): `btw.resumen` es el bloque
  del BTW (trimestre en curso con sus cifras, por presentar con su plazo y
  sus días, anteriores con su estado, el año hasta hoy y las facturas sin
  fecha) y `btw.trimestre` el detalle; la consola todavía no tiene página del
  BTW (solo la CLI y `/api/v2`). `export --v2` debería llevar el resumen.
- **La prioridad de los trimestres** (§5.F n.º 44) es la entidad `trimestre`
  de la caché `prioridad` (`ano * 10 + trimestre`), el máximo de sus facturas:
  las que se declaran en él, pagadas o no, más las de su C4 (corrección de la
  revisión). La de cada factura cuenta los días hasta el plazo del primer
  trimestre que ni venció ni está presentado: un C4 de un trimestre ya
  presentado corre contra el plazo de la declaración siguiente.
- **La hoja es CSV**; un .xlsx necesitaría una biblioteca que no hay. Si se
  cambia su formato, cambia su hash: las ya guardadas siguen valiendo como
  están.
- **`config/btw.yaml` hay que confirmarlo con el asesor** (mapeo de ventas con
  IVA trasladado nacional a 1e, el país por el btw-id, el 21 % de la
  autoliquidación, si es deducible entero) y cargarlo con `confirmado: true`.
  Cambiarlo cambia la hoja de los trimestres sin presentar: lo listo hay que
  volver a marcarlo.
- **Lo declarado de una factura es su huella** (`reglas/iva.huella_iva`: sus
  líneas de IVA sin orden y el país si hay IVA trasladado). Si cambia lo que
  entra en ella, todos los trimestres presentados darían C4 «cambio»: una
  versión nueva tendría que conservar la vieja para lo ya presentado.
- **Las ventas de Exact** traen el tratamiento que les dio el paso 8; los
  códigos de IVA de Exact todavía no se mapean a tratamiento por línea.
- **La regla 5 sigue igual**: cualquier cosa que lleve la declaración a la
  Belastingdienst (Digipoort, un SBR) está fuera de la V1.

**Tests existentes cambiados, y por qué**: `test_reglas.py` (el catálogo del
§7 gana C4, E0, E5 y E7, y E5 es del proveedor), `test_pureza_reglas.py`
(`PeriodoBtw`, `fechas` entre los módulos propios y los escenarios del paso
11), `test_hallazgos.py` (C4, E0 y E7 solo escriben lo que objetan),
`test_almacen.py` (`hoja_btw` y `periodo_btw_declarada` son de solo escritura
y `periodo_btw` controlada; al poblar se presenta un trimestre para que
tengan filas) y `test_servicios.py` (las tres órdenes del BTW en la matriz,
con `gestionar_btw`).

### Correcciones de la revisión

Dieciséis hallazgos de la revisión (dos repetidos: el 5 y el 9, el 6 y el
11). Todos se reprodujeron y todos eran reales; cada corrección tiene un test
que falla con el código de antes y pasa con el de ahora (comprobado sobre una
copia de `e95f5e0`). **1863 tests pasan.** La pasada de cinco mil facturas
sigue en 1,18-1,32 s la primera vez y 0,97-1,09 s las siguientes.

1. **E0 y la declaración no decían lo mismo de lo que falta** (mayor). Una
   venta con el tipo solo en sus líneas pasaba E0 y `clasificar` la dejaba
   fuera de 1a y 5a sin que nada la llevara a la lista de revisar; igual con
   un tipo o una cuota ilegibles (Q2, sin entrada de IVA) y con una fila de
   IVA normal bajo una cabecera con otro tratamiento (E0 salía antes).
   Ahora: `reglas/iva.tipo_de_lineas` es la definición de las dos; `btw.lineas`
   trae el tipo de las líneas (`LineaBtw.tipo_lineas_pb`, `tipo_efectivo_pb`)
   y la venta va a su rúbrica; en una venta con dos tipos en las líneas y sin
   desglose E0 avisa (desviación 20); E0 mira cada fila del desglose, también
   bajo otra cabecera, y una fila sin base o sin tratamiento; el motivo de
   «sin clasificar» dice «E0, o Q2 si no se pudo leer»; y **toda factura con
   una línea sin clasificar va a la lista de revisar** con su motivo. Tests:
   `test_btw.py::test_e0_y_la_declaracion_dicen_lo_mismo_de_lo_que_falta` (en
   el almacén), `test_lo_que_no_se_pudo_leer_lo_dice_el_motivo`,
   `test_reglas_paso11.py::test_e0_en_una_venta_pide_un_solo_tipo_en_las_lineas`
   y `test_e0_mira_una_fila_con_iva_normal_bajo_otra_cabecera`.
2. **El hash de la hoja cubría lo que se revisa** (menor). Resolver un
   hallazgo entre listo y anotar daba Conflicto «las cifras cambiaron».
   Ahora anotar compara la huella de las cifras escrita en la hoja marcada
   (desviación 17); el mensaje solo sale si cambia una cifra. Test:
   `test_resolver_un_hallazgo_entre_listo_y_anotar_no_obliga_a_marcar_otra_vez`.
3. **El hash de la configuración no se resolvía a un texto** (menor). La hoja,
   el evento de listo, `trimestre` y `resumen` llevan ahora el sha256 del
   `btw.yaml` en `politica_version` (`politica.config_btw_y_sha`; sin ninguno
   cargado, el del texto de partida, el mismo que se apunta al marcar
   listo). `ConfigBtw.sha256()` sigue existiendo pero ya no va en la hoja.
   Test: `test_la_primera_hoja_lista_apunta_la_configuracion_que_usa`
   (cambiado: antes comprobaba el hash canónico).
4. **En enero no salía el cuarto trimestre vacío** (menor). `resumen` añade
   siempre el trimestre anterior al de hoy (`btw.anterior`). Test:
   `test_en_enero_se_ve_el_cuarto_trimestre_aunque_este_vacio`.
5. y 9. **Una venta al 21 % se podía poner en 1e** (menor) y perdía de 5a la
   cuota cobrada. El cargador solo admite 1e para el tipo 0 (y el tipo 0
   solo a 1e: 1c es «behalve 0 %»); 1a-1c para los demás y `otros`. Además,
   `clasificar` deja sin clasificar una venta con cuota en una rúbrica sin
   IVA. Tests: tres casos nuevos en
   `test_un_btw_yaml_que_la_v1_no_sabe_aplicar_no_se_carga` y
   `test_una_venta_con_iva_en_una_rubrica_sin_iva_no_pierde_la_cuota`.
6. y 11. **`btw hoja` sin `--salida` escribía sin BOM** y decía el hash de
   los bytes con BOM (menor). Ahora escribe en `sys.stdout.buffer` los mismos
   bytes que se hashean. Test: `test_el_btw_por_la_cli` compara la salida con
   el fichero y su sha256.
7. **El registro documentaba `--importe-declarado -1.234,56`**, que el parser
   rechaza (menor). Se corrige el ejemplo a `-1234,56` (un separador de miles
   en un importe con signo es ambiguo y el resto de la CLI tampoco lo
   acepta) y la ayuda del parámetro lo dice. `test_el_btw_por_la_cli` anota
   ahora `-1234,56`.
8. **Un duplicado, una factura mal encaminada o una cuota dudosa contaban en
   5a/5b sin salir en la lista** (mayor). La lista suma B2, B3, R3, A8 y Q2
   sobre lo que se declara (desviación 16). Test:
   `test_un_duplicado_o_una_lectura_dudosa_del_iva_piden_revisarlo`.
10. **`kor.umbral` se truncaba al céntimo** (menor). Se convierte con
    `unidades.a_cent` y un umbral con más de dos decimales no se carga. Test:
    caso nuevo en `test_un_btw_yaml_que_la_v1_no_sabe_aplicar_no_se_carga`.
12. **Los días hasta el BTW ignoraban los trimestres presentados** (mayor):
    un C4 encontrado entre una presentación temprana y el plazo sumaba +15 y
    el suelo Urgente por un plazo ya cumplido. `reloj.proximo_limite_btw` y
    `prioridad.dias_hasta_btw` saltan los presentados; `estados` les pasa los
    del almacén (`Entradas.btw_presentados`, que entra en la huella de las
    entradas solo cuando hay alguno, para no rehacer la caché de todo sin
    trimestres presentados). Tests:
    `test_prioridad.py::test_los_dias_del_btw_saltan_los_trimestres_presentados`
    y `test_btw.py::test_un_iva_por_revisar_de_un_trimestre_presentado_cuenta_hacia_el_siguiente`.
    Se corrige lo que decía «Lo que deben saber».
13. **La prioridad del trimestre dejaba fuera las pagadas y las de C4**
    (mayor), y el registro decía que no existía. `estados._del_trimestre`:
    las facturas de `v_iva_vigente` por su fecha, pagadas o no, más las de un
    C4 pendiente de ese trimestre. Test:
    `test_un_trimestre_tiene_la_prioridad_de_sus_facturas_pagadas_o_no`.
14. **Listo y anotar no pedían motivo, ni anotar la rev** (menor). Las dos
    piden motivo y anotar la rev del periodo (desviación 19). Tests:
    `test_el_btw_por_la_cli` (sin motivo falla; con una rev vieja,
    Conflicto), `test_el_btw_por_la_api` y la matriz de `test_servicios.py`.
15. **`btw estado` no existía** (menor). Es un alias de `btw ver`
    (desviación 18). Test: `test_el_btw_por_la_cli`.

**Tests existentes cambiados, y por qué**: `test_btw.py`
(`test_la_primera_hoja_lista_apunta_la_configuracion_que_usa` mira el hash
de `politica_version`; la CLI y la API dan motivo y rev, y anotan un importe
de cuatro cifras) y `test_servicios.py` (motivo en listo y anotar, rev en
anotar). El caso «el tipo en todas las líneas basta» de
`test_reglas_paso11.py::test_e0_no_dice_nada` se queda: es una compra.

## Paso 12

El panel principal, la búsqueda, la vista económica de cada Objeto, la
historia de cada factura, el contrato v2 y la documentación de uso. Con este
paso la V1 queda construida entera. **1922 tests pasan** (eran 1863),
ninguno llama a la API y ninguno escribe fuera de una carpeta temporal. Cinco
mil facturas se recalculan en 1,21-1,30 s la primera vez y en 0,99-1,06 s las
siguientes (el paso 11 medía 1,18-1,32 s y 0,97-1,09 s: el motor no cambia).
Sobre ese almacén, el panel tarda 0,13-0,15 s, una búsqueda de todo con
1.000 filas 0,11-0,14 s, el resumen de los Objetos 0,04-0,05 s y
`export --v2` entero 0,43-0,57 s.

**Aquí no hay nada que escriba.** Todo lo del paso es lectura: consultas
sobre lo que ya hay, sin ninguna orden nueva ni ninguna tabla nueva. Ninguna
lectura nueva toca `cuenta_bancaria` ni enseña un IBAN fuera de lo que ya lo
enseñaba (`/api/v2/cuentas`, con su permiso); `export --v2` no lleva
ninguno. La suite de alcance pasa sin tocarla.

### Qué se construyó

**Migración `0015_panel_busqueda.sql`** (la siguiente libre), solo vistas,
independientes de hoy:

- `v_factura_listado`: una fila por factura para buscar (§5, «One row per
  invoice for search»): la contraparte impresa (el emisor de una compra, el
  receptor de una venta), el periodo de prestación (el de la cabecera o, si no
  lo imprime, el de sus líneas activas), base, IVA y total, `importe_cent`
  (la base o, sin ella, el total), si está anulada, fusionada o sustituida,
  `cuenta` (ni lo uno ni lo otro ni lo otro), y las columnas de estado de
  `factura_estado` (pago, saldo, vencimiento, revisión, calidad, marcas de
  edición, prioridad, excepción y la pasada que las escribió).
- `v_objeto_periodo`: por Objeto (NULL, lo imputado sin Objeto) y mes de la
  fecha de factura: ingresos (lo imputado de las ventas), costes (lo de las
  compras), margen, horas de venta y de compra y cuántas facturas; de
  `v_imputacion_vigente` y solo de facturas con base conocida.

**`consultas.py`**, el grueso del paso:

- **Búsqueda (§18)**: `FILTROS`, un catálogo cerrado de 27 filtros (uno o
  más por cada filtro del §18, más `texto`, `sentido`, `excepcion`,
  `importe_min` e `importe_max`). Cada filtro es un fragmento de SQL fijo con
  `?` y una función que valida y convierte su valor (entero, día ISO, lista de
  valores permitidos, sí/no, importe con dos decimales como mucho, trimestre
  `2026-T3`). Nada de lo que escribe quien busca entra en el SQL: un nombre de
  filtro que no está en el catálogo, un valor que no se entiende o un orden
  desconocido dan `FiltroNoValido` (un 400 en la API, salida 2 en la CLI).
  `buscar(conn, peticion)` devuelve los filtros aplicados, la página, el total,
  la suma de lo encontrado (total, base y pendiente), de qué día es el estado
  (`estado_del`, el hoy de la última pasada del motor) y si está al día
  (`al_dia`). Orden: prioridad (por defecto, el del §8), fecha, vencimiento,
  importe o número; 200 por página por defecto, 1.000 como mucho.
  `filtros()` describe el catálogo (lo que pinta el buscador de la consola y lo
  que dice el contrato).
- **Panel principal (§17)**: `panel(conn)` con los siete bloques: dinero que
  entra y que sale (pendiente, vencido, esta semana, este mes, próximos 30
  días, sin fecha, de `flujo_caja`), caja (lo esperado por ventana, el neto,
  lo que movió el banco este mes y el estimado del planning aparte, decisión
  22), facturación (V6 con su importe, V5 y V8 con sus periodos, las
  diferencias con el planning; sin datos sin planning), PO (valor, consumido y
  lo que queda de las activas, y las que están cerca del límite, de caducar o
  de agotarse), BTW (el trimestre en curso, el próximo plazo y los
  trimestres pasados sin presentar) y «Requiere atención» (los hallazgos
  pendientes por categoría, con cuántos activos y cuántos aceptados, y las
  compras y ventas vencidas). `categoria_de(regla)` reparte cada regla del
  catálogo en una sola categoría por su entrada de prioridad y su calidad.
- **Vista del Objeto (§5) completa**: `objeto(conn, id, desde=, hasta=)`
  gana `economia` (ingresos, costes, margen, margen en puntos básicos y en
  porcentaje y horas, del periodo pedido, por defecto el mes en curso hasta
  hoy, del año y de siempre; mes a mes de `v_objeto_periodo` y semana a semana
  de `trabajo.importes_por_semana`) y `facturas` (las de compra y las de venta
  con lo imputado al Objeto, sus horas y si cuentan). `objetos_resumen(conn)`:
  todos los Objetos con lo del año y lo de siempre, y lo que no es de ninguno
  (`sin_objeto`: lo imputado sin Objeto, lo que las bases no imputan y el
  total), de modo que todo cuadra con la base total.
- **Procedencia y marcas por campo (§11-14)**: cada campo de la ficha dice su
  fuente en palabras (`fuente_texto`: «Extraído del documento», «Corregido a
  mano»...), su referencia y, si lo cambió una persona, el motivo del último
  cambio (de `cambio_campo`), además de quién y cuándo, que ya estaban.
- **Historia de una factura (§12)**: `historial_factura(conn, id)`: el
  documento original (sha256, nombre, si se conserva, por dónde y cuándo
  llegó), cada extracción (cuál es la vigente), cada evento que la tocó con
  cada cambio de campo (antes y después, en texto, con su fuente y su
  motivo), las revisiones, los hallazgos con sus eventos y anulaciones, las
  excepciones y las notas.
- **Contrato v2**: `CONTRATO_V2 = "2.0"`, `CLAVES_V2` (las claves que el
  contrato promete, por ruta), `exportar_v2(conn)` y `comprobar_v2(datos)`
  (claves que faltan, números con decimales, versión).

**`serve.py`**: las lecturas nuevas de `/api/v2` (`contrato`, `panel`,
`buscar`, `facturas/N/historial`, `objetos` con el resumen, `objetos/N` con
`desde` y `hasta`, `flujo` con `desde` y `hasta`, `exportar`), todas con
`ver_facturas`; las respuestas de `/api/v2` (también las órdenes y los
errores) llevan la cabecera `X-BMS-Contrato: 2.0`. `LECTURAS_V2` es la lista de rutas que el contrato documenta. Un
parámetro que una ruta no conoce, o un valor que no se entiende, da 400.
`/api/datos` no cambia.

**`cli.py`**: `export --v2` (por defecto a `datos-v2.json`; necesita el
almacén y comprueba el contrato antes de escribir), `resumen` (el panel),
`buscar --filtro NOMBRE=VALOR ...` (con `--filtros`, `--orden`, `--limite`,
`--pagina` y `--json`), `objetos` y `historial ID`; `objeto N` enseña ya la
economía.

**La consola** (`consola_assets.py`): una barra de navegación y las páginas
Panel (los siete bloques, con enlaces a cada factura), Buscar (un formulario
que sale del catálogo de filtros, con listas para proveedor, cliente, Objeto
y PO), Objetos (el resumen y lo sin Objeto) y BTW (el resumen, el detalle de
un trimestre y sus tres órdenes); la ficha del Objeto con su economía y sus
facturas; en la ficha de factura, la fuente de cada campo y cada marca de
edición como insignias, con quién, cuándo y por qué, y la historia completa;
una columna «Pago» en las listas. Todo con `createElement` y `textContent`
(el test con nodo pinta un nombre con HTML dentro en cada función nueva).

**Documentación**: el contrato v2 en `docs/integracion-web.md` (la
política de versiones, cuatro reglas que valen para todo, cada clave, cada
ruta y cada filtro con el apartado del §18 al que responde, y un ejemplo en
JavaScript); la guía de uso diario `docs/uso-v1.md` (rutina, prioridades,
corregir un campo, verificar un IBAN por teléfono, cerrar un trimestre del
BTW); el apartado 6 de `docs/validacion-facturas.md`, la tabla de las 82
reglas del motor, **generada del catálogo** con
`scripts/generar_catalogo_doc.py` (`--comprobar` dice si se ha quedado
atrás); el README, `docs/fase-0.md` y el estado en `docs/diseno-v1.md`.

Otros: `flujo_caja.flujo` admite lo ya leído (`leidos=`) para que el panel
no lea dos veces las partidas; `trabajo.importes_por_semana`.

### La puerta, test por test

| Puerta | Tests |
| --- | --- |
| Lo pendiente de un proveedor es la suma de lo pendiente de sus facturas | `test_panel_busqueda.py::test_lo_pendiente_de_cada_parte_es_lo_que_encuentra_la_busqueda` (cinco semillas: pagos parciales, enteros y de más, un abono, una sustitución o corrección, anulaciones, una línea dividida entre dos Objetos y otra que pasa a sin Objeto, al azar sobre el escenario; para cada proveedor y cada cliente, lo pendiente y lo vencido de su vista es la suma de lo que la búsqueda da con `proveedor_id`/`cliente_id` y `pendiente`/`vencida`, y lo que da el panel es la suma de todos) |
| Lo facturado por Objeto más lo sin Objeto es la base total de las ventas | `test_lo_de_cada_objeto_mas_lo_sin_objeto_es_la_base_total` (cinco semillas; también con los costes, y la suma de los meses y de las semanas de cada Objeto es lo de siempre; la base total se calcula aparte, con `relaciones.efectos`), `test_lo_sin_objeto_dice_de_donde_sale` |
| Un test por cada filtro del §18 | `test_filtro_numero_de_factura`, `test_filtro_proveedor`, `test_filtro_cliente`, `test_filtro_objeto`, `test_filtro_po`, `test_filtro_periodo`, `test_filtro_vencimiento`, `test_filtro_estado_de_pago`, `test_filtro_estado_de_revision`, `test_filtro_prioridad`, `test_filtro_calidad_del_dato`, `test_filtro_ediciones_manuales`, `test_filtro_pendiente`, `test_filtro_vencida`, `test_filtro_pagada`, `test_filtro_anulada_o_acreditada`: cada uno contra un oráculo calculado aparte, sobre un escenario (`escenario`) donde ningún filtro da todas las facturas ni ninguna (`test_el_escenario_tiene_de_todo`); los de más en `test_los_filtros_de_mas`, la suma de filtros en `test_los_filtros_se_suman` |
| Sin SQL hecho con lo que escribe el usuario | `test_un_filtro_que_no_se_entiende_se_rechaza` (once casos), `test_el_texto_de_quien_busca_nunca_entra_en_el_sql` (una inyección clásica es un texto más, y ningún fragmento del catálogo cambia con un valor centinela) |
| `/api/datos` sigue idéntico byte a byte a la foto | `test_contrato_v2.py::test_api_datos_sigue_siendo_byte_a_byte_la_foto` (desde un almacén importado de `out/`, sin cabecera de contrato, y otra vez después de leer todo `/api/v2`); `test_golden.py` sigue igual |
| La suite de alcance | `test_alcance_v1.py`, sin cambios |
| Lo demás | El contrato v2 contra su documentación (`test_el_contrato_v2_es_el_que_dice_la_documentacion`: cada clave, cada filtro y cada ruta están en el documento), `export --v2` (`test_export_v2_cumple_el_contrato_documentado`: sin decimales, sin IBAN), las rutas y sus errores, los permisos, la CLI, la consola con nodo (`test_la_consola_nueva_pinta_el_html_de_los_documentos_como_texto`), el panel (`test_el_panel_tiene_los_siete_bloques_del_paragrafo_17`, `test_cada_aviso_pendiente_va_a_una_sola_categoria`, `test_el_panel_dice_el_trabajo_sin_facturar_del_planning`), la procedencia por campo, la historia, la vista del Objeto, `estado_del` y `al_dia`, y la tabla del catálogo (`test_la_tabla_de_validacion_facturas_es_la_del_catalogo`) |

### Desviaciones de la especificación, y por qué

1. **La migración es la 0015**: la numeración iba por la 0014.
2. **`v_objeto_periodo` va solo por mes; el corte por semana ISO se hace en
   Python** (`trabajo.importes_por_semana`). Una línea de un mes entero tiene
   que repartirse entre sus semanas por sus días, con el resto del redondeo
   en la última, y eso es `trabajo.repartir` con `turnos.dias_de`: lo mismo
   que ya hacían las horas del Objeto. Escribirlo en SQL sería una segunda
   versión de la misma cuenta.
3. **A qué mes y a qué semana va un importe** (pregunta 10 del §12, abierta):
   por mes y por año, la fecha de factura (como el BTW y los totales de las
   partes); por semana, los días trabajados (como las horas). Si la respuesta
   es otra, cambia `v_objeto_periodo` y nada más.
4. **No hay vista `v_campo_calidad`.** La calidad de un campo depende de los
   hallazgos que lo señalan y de sus marcas de verificación; ya la calcula
   `consultas._campos_de` (paso 4), con el orden del §5 y «neutra», nunca
   verde. La de la factura está en `factura_estado` y de ahí en
   `v_factura_listado`.
5. **`v_factura_listado` lee la caché `factura_estado`**, que escribe cada
   pasada del motor: el estado de pago, el vencimiento y la prioridad
   dependen de hoy, y la vista no puede. Por eso la búsqueda dice de qué día
   es su estado (`estado_del`) y si está al día (`al_dia`); la consola y el
   panel lo avisan y dicen que hace falta `recalcular --diaria`.
6. **Lo que «no es de ningún Objeto» son dos cosas**: lo imputado a una línea
   sin Objeto y lo que la base de una factura no reparte entre sus
   imputaciones (una factura sin líneas, o con líneas que no suman la base).
   Las dos van en `sin_objeto` por separado, y su suma con lo de los Objetos
   es la base total.
7. **Una factura sin base no es ingreso ni coste de nadie** (Q1; y X1, porque
   en otra moneda se lee sin importes): ni en los Objetos, ni en la base
   total, ni en la semana. Se cuenta aparte (`sin_base`) para que se vea.
8. **«Incoming / outgoing» del §17 se leen como dinero que entra y que sale**
   (cobros de ventas, pagos de compras), y las facturas vencidas van en
   «Requiere atención» separadas en compras y ventas. Una vencida en otra
   moneda cuenta como vencida pero no suma (`sin_importe`): lo está, y su
   importe no se sabe en euros.
9. **Las categorías de «Requiere atención»** salen de la entrada de
   prioridad de cada regla (IBAN, duplicados, IVA, planning, sin facturar,
   PO, vencidas), de su calidad (faltan datos), de Q2 (lecturas dudosas) y
   el resto a «otros». Un hallazgo va a una sola categoría. Cada una cuenta
   los activos (abierto y desaparecido) y los aceptados aparte, porque un
   aceptado ya lo ha mirado alguien.
10. **El bloque de PO** dice «cerca del límite» con P5, «cerca de caducar»
    con P7 y «agotamiento previsto» con P8, P9 y P10, abiertos o aceptados.
11. **El bloque del BTW** dice el próximo plazo que no ha pasado y, aparte,
    los trimestres cuyo plazo pasó sin presentar (`plazos_pasados`): poner
    un plazo pasado como «próximo» escondía justo lo urgente.
12. **Filtros de más** (`texto`, `sentido`, `excepcion`, `importe_min`,
    `importe_max`, y `po` por número además de `orden_compra_id`): los pide
    la consola y no cambian nada de los del §18. Un filtro de lista con
    varios valores es un «o» (`estado_pago=vencida,pendiente`); filtros
    distintos se suman con «y».
13. **El filtro de cliente** da sus ventas y también las compras imputadas a
    un Objeto suyo: es lo que hace falta para ver lo de un cliente entero, y
    lo que hace la vista del cliente con sus Objetos.
14. **`/api/v2/objetos` devuelve ya el resumen** (`objetos_resumen`), que
    lleva lo que daba antes (id, código, nombre, cliente) y más. Ningún test
    ni la consola dependían de que no lo llevara.
15. **`export --v2` necesita el almacén** (el v1 podía leer `out/`) y no lleva
    IBAN: el contrato es para la web del dueño, y una cuenta bancaria no tiene
    que salir del ordenador para eso.
16. **Política de versiones del contrato**: una clave nueva sube el menor
    (2.1); quitar o cambiar una sube el mayor (3.0), y entonces el sitio tiene
    que cambiar. Todos los importes son enteros en céntimos con su texto al
    lado; no hay números con decimales (`comprobar_v2` lo mira).
17. **La tabla del catálogo de `docs/validacion-facturas.md` se genera** del
    código; el resto del documento, que explica por qué existe cada
    comprobación, sigue escrito a mano. Las dos cosas son coherentes porque el
    test compara la tabla con el catálogo, no porque alguien se acuerde.

### Lo que deben saber los pasos siguientes

- **El contrato v2 es una promesa.** `CLAVES_V2` y `LECTURAS_V2` son lo que
  dice el documento y el test los compara: una clave o una ruta nueva va en
  los dos y en `docs/integracion-web.md` a la vez, y sube la versión menor.
- **Un filtro nuevo** es una entrada de `FILTROS` con su fragmento fijo y su
  conversor, y un test con su oráculo en `test_panel_busqueda.py`. Nunca un
  fragmento hecho con el valor.
- **La búsqueda lee la caché.** Si una columna nueva de estado depende de
  hoy, va a `factura_estado` (lo escribe el motor) y a `v_factura_listado`,
  no a la vista directamente.
- **Una regla nueva** cae sola en una categoría del panel por su entrada de
  prioridad; si no tiene, va a «otros». Y hay que volver a generar la tabla
  de `docs/validacion-facturas.md` (`python scripts/generar_catalogo_doc.py`):
  el test lo exige.
- **El teléfono de verificación de un proveedor** no sale todavía en la
  consola ni en `iban listar`; la guía dice que se busque en el maestro de
  Exact. Enseñarlo es una lectura más, sin riesgo, si se pide.
- **Con la respuesta a la pregunta 10** (atribución) solo cambia
  `v_objeto_periodo` y, si va por trabajo, el mes sale de
  `trabajo.repartir` como la semana.

**Tests existentes cambiados**: ninguno.

### Correcciones de la revisión

Quince hallazgos de la revisión (dos repetidos: el 9 y el 14, sobre los
parámetros de `/api/v2`). Todos se reprodujeron y todos eran reales; cada
corrección tiene un test que falla con el código de antes y pasa con el de
ahora (comprobado con `src/` de `3d30ebc`). **1943 tests pasan.** La pasada de
cinco mil facturas no cambia de forma medible (1,16-1,28 s la primera vez y
0,96-1,09 s las siguientes, como antes; la máquina da picos de 1,5 s con las
dos versiones); el panel, la búsqueda y el export, tampoco.

1. **La suma de la búsqueda sumaba lo que no cuenta** (mayor). Las anuladas,
   las copias fusionadas y las sustituidas sumaban en `suma.total` y
   `suma.base`, y lo pendiente juntaba compras y ventas. Ahora
   `consultas._suma_busqueda`: solo suman las que cuentan (la regla de
   `_resumen` y `v_*_totales`), `no_cuentan` dice cuántas no, y compras y
   ventas van por separado (`compras`, `ventas`); arriba, `total_cent`,
   `base_cent` y `pendiente_cent` son los del único sentido encontrado, o
   `null` si hay de los dos (`mezcla`). La consola y la CLI lo dicen así.
   Tests: `test_panel_busqueda.py::test_la_suma_de_la_busqueda_es_la_de_la_vista_de_la_parte`
   (la búsqueda de cada proveedor y cliente suma lo que su vista llama
   facturado; la anulada 2026-112 sale y no suma) y
   `test_una_copia_fusionada_no_suma_dos_veces`.
2. **El bloque de PO del panel sumaba los dos lados** (mayor). Ahora lleva
   `cliente` y `proveedor`, cada uno con `activas`, valor, consumido y lo que
   queda (desviación 18). Test: `test_el_bloque_de_po_no_suma_los_dos_lados`
   (una PO de cada lado).
3. **El periodo de una factura que solo imprime la semana** (mayor).
   `v_factura_listado` solo miraba las fechas de las líneas: una factura de
   horas con «semana 37» y sin fechas no tenía periodo y los filtros
   `periodo_desde` y `periodo_hasta` no la encontraban. Ahora el motor
   escribe el periodo en `factura_estado` con la misma cuenta que las horas
   y la economía por semana del Objeto (`estados.periodos`, que usa
   `turnos.dias_de`: fechas de la imputación o de la línea, la semana
   impresa con el año de la fecha de la factura, y la cabecera), y la vista
   lo lee de ahí (migración `0016_periodo_de_prestacion.sql`, desviación
   19). Tests:
   `test_el_filtro_de_periodo_encuentra_una_factura_que_solo_imprime_la_semana`
   (el caso de la revisión: 2026-0912 sin periodo de cabecera) y
   `test_el_periodo_de_la_cache_es_el_de_turnos` (la semana 52 de una
   factura del 6 de enero es la de diciembre).
4. **El filtro `texto` no plegaba lo que no es ASCII** (menor). `lower()` de
   SQLite deja «Ö» y «É» en mayúscula. Ahora la búsqueda registra
   `pliegue` (NFKC y `casefold`) en la conexión y la usa a los dos lados.
   Test: `test_el_texto_se_busca_sin_mayusculas_tambien_fuera_del_ascii`.
5. **La vista del Objeto rechazaba medio periodo con un error que no era**
   (menor): solo `hasta` antes del día 1 o solo `desde` después de hoy daban
   «el periodo empieza después de terminar». Ahora un periodo lleva `desde`
   y `hasta` o ninguno, como el flujo de caja (desviación 20), y un solo
   extremo es un `400` que lo dice. Tests:
   `test_la_vista_del_objeto_no_admite_medio_periodo` y
   `test_contrato_v2.py::test_la_vista_del_objeto_pide_los_dos_extremos_del_periodo`.
6. **«Cerca de caducar» enseñaba PO ya caducadas** (menor). P7 sigue
   pendiente después del fin (SIN_DATOS o el FALLO «caducó»). Ahora las tres
   listas de avisos son de las PO activas y hay una cuarta, `caducadas`: las
   que pasaron su fin con un P7 pendiente. Cada PO de las listas lleva su
   `lado`. Test: `test_las_listas_de_po_del_panel` (llena cerca del límite,
   cerca de caducar y, veinte días después, caducadas).
7. **La historia no decía que una factura había sido abonada** (menor). Los
   eventos de una relación llevan la factura de origen. Ahora
   `historial_factura` trae también los eventos con cambios en una
   `factura_relacion` que la tiene de destino, y una lista `relaciones` en
   los dos sentidos (la consola y la CLI la enseñan). Test:
   `test_la_historia_de_una_factura_abonada_dice_quien_la_abono`.
8. **Un entero enorme en un filtro era un 500** (menor), y un valor que no
   era texto desde Python un `TypeError`. `_entero` rechaza más de 19 cifras
   o más de 2⁶³−1 con `FiltroNoValido`; `buscar` toma un valor suelto como
   su texto. Tests: `test_un_entero_demasiado_grande_es_un_filtro_no_valido`,
   `test_la_busqueda_admite_valores_que_no_son_texto` y
   `test_contrato_v2.py::test_un_filtro_enorme_es_un_400_y_no_un_500`.
9. y 14. **Las lecturas de pasos anteriores ignoraban los parámetros**
   (menor), y guardar los valores vacíos dejó `?nivel=` en una lista vacía.
   Ahora `_leer_v2` comprueba los parámetros de **toda** ruta de
   `LECTURAS_V2` antes de contestar (`serve.ruta_documentada`,
   `parametros_admitidos`): uno desconocido o repetido es un `400`; uno
   admitido y vacío (`?nivel=`, `?desde=&hasta=`) es como no ponerlo, como se
   leía antes; un `nivel` que no es un nivel, `400` (`nivel_pedido`; antes,
   una lista vacía). Tests:
   `test_cada_lectura_de_v2_rechaza_un_parametro_que_no_admite` (recorre
   `LECTURAS_V2`) y `test_el_nivel_de_la_lista_de_facturas`.
10. **Puertas que no probaban lo que decían** (menor). El escenario al azar
    pone ahora siempre la línea de una compra sin Objeto y su base distinta
    de la suma de sus líneas, con importes al azar: la propiedad comprueba
    `sin_objeto.imputado` y `sin_imputar` con costes distintos de cero en
    cada semilla. `test_filtro_ediciones_manuales` comprueba `suplementada`
    (un vencimiento puesto a mano donde el documento no traía) y
    `sin_resolver` contra su oráculo. El test del contrato contra la
    documentación lee ahora los esqueletos por camino
    (`_claves_documentadas`: «id» en `facturas[]` no vale por estar en
    `proveedores[]`), con su propio test; para eso `facturas[]` y
    `dinero_sale` se documentan con todas sus claves en su bloque.
11. **La documentación mandaba meter un token personal en el JavaScript del
    sitio** (mayor) y decía que los IBAN solo iban a la consola sin que nada
    lo hiciera cumplir. `docs/integracion-web.md`: el sitio usa una persona
    con el rol `consulta` (solo `ver_facturas`), su token no va en ninguna
    variable que se empaquete (se escribe al abrir el sitio o lo pone un
    proxy local), y el ejemplo es así. El servidor lo hace cumplir
    (desviación 21): una petición con un `Origin` declarado con `--origen`
    que no es el del propio servidor recibe toda respuesta de `/api/v2` con
    los IBAN enmascarados y no puede dar órdenes (`403` en
    `POST /api/v2/acciones`). La consola (mismo origen, que no manda
    `Origin` en un GET) y un programa sin navegador siguen igual. Test:
    `test_un_sitio_de_otro_origen_lee_sin_iban_y_no_da_ordenes`. La guía de
    uso lo dice también.
12. **El contrato v2 llevaba IBAN enteros dentro de los motivos** (mayor):
    los textos de F2, F3, F5, F6 y F10 los escriben y llegan a los motivos de
    facturas, proveedores y excepciones. `exportar_v2` pasa todo por
    `consultas.sin_ibanes` (cada IBAN de cada texto queda «NL..5689»), y
    `comprobar_v2` busca un IBAN dentro de cualquier texto. Se corrige el
    ejemplo de motivo de `docs/uso-v1.md`, que no era el que sale. Test:
    `test_el_contrato_v2_no_lleva_ningun_iban_ni_dentro_de_un_texto` (maestro
    y la factura con inyección: F2 y F3 abiertos).
13. **`docs/modelo-datos.md` no existía** (mayor). Escrito: las convenciones,
    las clases de tabla, cada tabla por grupo, las vistas (y las que no se
    hicieron, con su porqué) y de dónde sale cada estado, hasta la 0016.
    Enlazado desde el README y `docs/diseno-v1.md`.
15. **V5 no salía en el bloque de facturación** (menor). Ahora va en
    `horas_sin_facturar`, con la venta, el Objeto, el periodo, las horas y su
    valor estimado: es la «facturación que falta» del §8, como V8. Test:
    `test_el_panel_dice_las_horas_validadas_que_no_estan_en_su_venta`.

Desviaciones nuevas:

18. **El bloque de PO del panel va por lados** (sustituye a la 10 en su
    forma): `cliente` y `proveedor` con lo suyo, y las listas `cerca_del_limite`,
    `cerca_de_caducar` y `agotamiento_previsto` solo de las PO activas, más
    `caducadas`. El contrato sigue en 2.0: estas claves se cambian en la
    revisión del mismo paso, antes de que ningún sitio se construya contra
    él (la política de versiones empieza a contar desde aquí).
19. **El periodo de prestación vive en la caché** (`factura_estado`,
    columnas `periodo_desde` y `periodo_hasta`). No depende de hoy, pero el
    año de una semana impresa no se puede calcular en la vista (SQLite 3.45
    no tiene `%V`, y la semana 52 de una factura de enero es la del año
    anterior). Antes de la primera pasada la vista da lo de 0015.
20. **Un periodo del Objeto lleva los dos extremos o ninguno.** Rellenar el
    que falta con el mes en curso daba periodos al revés o que nadie había
    pedido.
21. **Desde otro origen, `/api/v2` es de solo lectura y sin IBAN enteros.**
    La decisión 23 (la consola enseña el IBAN entero) se mantiene para la
    consola; un sitio propio no lo necesita para nada y un token suyo
    filtrado no debe servir para verificar una cuenta ni marcar un pago.

**Tests existentes cambiados, y por qué**:
`test_el_panel_tiene_los_siete_bloques_del_paragrafo_17` (lee el valor de la
PO en `ordenes_compra.cliente`), `test_el_contrato_v2_es_el_que_dice_la_documentacion`
(por camino), `_escenario_al_azar` y
`test_lo_de_cada_objeto_mas_lo_sin_objeto_es_la_base_total` (la compra sin
Objeto y con la base cambiada, y las comprobaciones de lo sin Objeto) y
`test_filtro_ediciones_manuales` (suplementada y sin resolver).

Lo que deben saber los pasos siguientes, además de lo de arriba:

- **Una columna nueva de `factura_estado` va también en
  `estados._COLUMNAS_ESTADO`** y en la tupla que escribe `recalcular`, en el
  mismo orden.
- **Todo texto que salga hacia un sitio propio pasa por `sin_ibanes`**: el
  export ya lo hace entero y `serve._json` lo hace con cualquier respuesta
  de `/api/v2` a otro origen. Un mensaje de regla nuevo puede llevar el IBAN
  entero (la consola lo necesita); no hay que enmascararlo en la regla.
- **Una lectura nueva de `/api/v2`** va en `LECTURAS_V2` con sus
  parámetros: si no, sus parámetros no se comprueban.

## Paso 13

El entorno local aislado con Docker y los datos de prueba. **No está en el §11
de la especificación: lo pidió el dueño**, con los requisitos que se cerraron con
él (el PC con Windows y Docker Desktop, la consola y la base sin red, una sola
salida a `api.anthropic.com:443` por un filtro, una base de prueba aparte y un
presupuesto de funcionamiento). **2094 tests pasan** (eran 1943) y cuatro se saltan: los de los contenedores, que
solo corren con `BMS_PROBAR_DOCKER=1` (aquí se corrieron así y pasan), ninguno
llama a la API. La base de la imagen se pudo bajar de Docker Hub sin el 429, así
que **la imagen se construyó aquí y las comprobaciones con contenedores de verdad
se hicieron aquí** (abajo, en la puerta). Lo que solo existe en Windows (Docker
Desktop, Windows PowerShell 5.1, las letras de unidad) queda por mirar en el
ordenador del dueño, y se dice cuál es.

No hay tabla ni migración nueva: la marca de la base de prueba va en la cabecera
del fichero de SQLite (`PRAGMA application_id`), no en una tabla.

### Qué se construyó

**`salida.py` y `bms-agent salida`**: el filtro de salida, un proxy CONNECT con
la biblioteca estándar (`socketserver`, `selectors`), sin interceptar TLS.

- `decidir(cabecera, permitidos)` es una función pura: 400 si la primera línea no
  es una petición, 405 si no es CONNECT (HTTP en claro u otro método), 403 si el
  destino no está en la lista blanca, 200 si está. El nombre se compara entero tras
  normalizarlo (minúsculas, sin el punto final): `api.anthropic.com.evil.example`,
  `evilapi.anthropic.com` o `api.anthropic.com:80` no pasan. Una IP escrita a mano
  no pasa nunca, tampoco en sus formas raras (`2130706433`, `0x7f.1`, `127.1`,
  `[::1]`): `es_literal_ip` usa `inet_aton`, que acepta lo mismo que un navegador.
- La lista blanca (`leer_destino`, `lista_blanca`) solo admite `nombre:puerto`: ni
  IP, ni comodines, ni vacía. Por defecto, `api.anthropic.com:443`.
- El proxy resuelve el nombre él mismo, rechaza (403) si alguna dirección no es de
  internet (`direcciones_no_publicas`: privadas, locales, enlace local, CGNAT) y se
  conecta a la dirección que comprobó, sin volver a resolver: un DNS que rebota
  hacia la red de la casa no lo convierte en un puente.
- Cada intento queda en el registro (`bms_agent.salida`): quién, qué pidió, qué se
  decidió, el código y por qué; al cerrar un túnel, los bytes y los segundos. Las
  cabeceras no se apuntan nunca. Una conexión que no pide nada (la comprobación de
  salud) va a debug.
- Límites: 8 KiB de cabecera (431), 10 s para mandarla, 32 túneles a la vez (503),
  900 s de silencio por túnel (una petición sin streaming puede tardar minutos en
  dar el primer byte).
- `Reenvio`: la entrada a la consola, un reenvío TCP fijo a un solo destino
  (desviación 1).
- `bms-agent salida --escuchar HOST:PUERTO --permitir HOST:PUERTO --reenviar
  ESCUCHA=DESTINO`; un nombre en `--escuchar` se resuelve al arrancar (con
  reintentos): así el proxy escucha solo en la red del lector. `bms-agent salud
  HOST:PUERTO` es la comprobación de salud de los contenedores.

**La base de prueba, `demo.py` y `bms-agent demo crear [--db] [--rehacer]`.**
Construye `datos/demo.sqlite3` con una empresa de seguridad y facility ficticia,
**por las puertas de siempre** (los importadores, la ingesta, las órdenes de
`servicios.py`), no escribiendo filas: los datos de prueba pasan por el registro de
cuentas, las reglas y la auditoría como los reales, y `db verificar` dice «Todo
cuadra.». Tarda 6-8 s. Lo que lleva, todo respecto a hoy:

- 6 proveedores (dos zzp'ers y cuatro empresas, una británica que factura en
  dólares), 3 clientes, 3 Objetos (un puerto, una zorglocatie, un gemeentehuis), 5
  personas del planning, tarifas de compra con recargo de noche (+15 %) y de fin de
  semana (+20 %), tarifas de venta por Objeto, ciclos de facturación (semanal con 7
  días de margen, mensuales con 10);
- unas 240 turnos de TRNSPRNT desde el día 1 de hace dos meses hasta dentro de tres
  semanas (aprobados, hechos y planificados), con las horas variando un poco (una
  pausa, un turno que se cae: dos facturas iguales serían un duplicado);
- 16 facturas de compra con su PDF (un PDF mínimo con «DATOS DE PRUEBA» en la
  primera línea) y su extracción v2: las mensuales y quincenales de los
  proveedores, línea a línea contra el planning; **una duplicada** (el mismo número,
  otro PDF: B2, las dos bloqueadas), **una con el IBAN cambiado** (F2 y F3), **un
  abono** propuesto por la extracción y sin confirmar (R5), **una en dólares** (X1,
  con autoliquidación y btw-id británico), **una con un intento de inyección** en
  el texto (Q3 con su excepción, a la espera del proveedor; el IBAN de su cabecera
  es el del maestro), **una vencida hace más de treinta días** (urgente) y una con
  el total leído con duda (Q2);
- 16 facturas de venta de Exact: las semanales del puerto con su PO, salvo **una
  semana trabajada sin facturar** (V6, valorada a la tarifa pactada, y V8), las
  mensuales de los otros dos clientes, **una vencida hace más de sesenta días**
  (urgente) y **un abono** confirmado por una persona;
- 3 PO: la del puerto consumida en más de un 80 % y con trabajo planificado que ya
  no cabe (P5, P8, P9, P10), la de la zorglocatie que vence en tres semanas con valor
  por gastar (P7) y una del lado del proveedor;
- un extracto CAMT.053 por mes de la cuenta propia (con continuidad de saldos y
  secuencia), con los cobros y pagos casados solos y la comisión del banco sin casar
  (K7); hoy siempre se mueve algo, aunque sea día 1;
- el BTW: los trimestres cuyo plazo ya pasó, presentados (anotados por una persona,
  con una referencia ficticia) y el que vence ahora, con su hoja lista para revisar;
- lo que habría hecho una administración: la mitad de lo limpio y pagado, revisado;
  un vencimiento corregido a mano y sin verificar (M1); una nota; dos excepciones a
  la espera del proveedor; el abono de venta confirmado;
- dos personas, «Ana Demo» (administrador) y «Bram Demo» (administración), con sus
  tokens, que `demo crear` enseña una vez.

Con eso cada bloque del panel (§17) tiene algo y hay facturas de los cuatro
niveles de prioridad, también en fechas que cambian de mes, de trimestre y de año.

**La marca y el aislamiento** (`almacen/__init__.py`):

- `NOMBRE_DEMO = "demo.sqlite3"` y `MARCA_DEMO` (`application_id` = «BMSD»).
  `marca_de_fichero(ruta)` lee la marca de los bytes 68-71 de la cabecera sin abrir
  la base; `es_base_demo(conn)` la lee de una conexión.
- `abrir()` exige que el nombre y la marca vayan juntos (`BaseDePruebaMezclada`):
  una base marcada con otro nombre (una copia de la de prueba encima de la de
  verdad) o una llamada `demo.sqlite3` sin la marca no se abren. La CLI lo dice y
  sale con 2.
- `raiz_documentos_de` y `ruta_anclas_de` dan `demo-documentos/` y
  `demo-anclas.log` a la base de prueba: nada de ella cae en la carpeta de la de
  verdad.
- Todo lo que fabrica `demo crear` lleva la marca: la columna «Datos de prueba» con
  `BMS-DEMO` en cada fila de los CSV (los mapeos admiten columnas de más), un
  comentario en el PDF y en el XML del banco, `BMS-DEMO-...` en el `request_id` de
  cada extracción y los turnos, y el código de banco `DEMO` en sus IBAN (pasan el
  módulo 97). `contiene_datos_de_prueba` lo busca (también en UTF-16) y
  `exigir_sin_datos_de_prueba(conn, contenido, que)` lanza `DatosDePrueba` si la base
  no es la de prueba. Se llama en `registrar_documento`, `registrar_extraccion`,
  `politica.registrar`, `importar_fichero` e `importar_extracto` (antes de leer, y
  también al simular); `importar-out` lo cuenta como un fichero rechazado más, y
  `extract` ni manda a la API un PDF de prueba si la pasada no es sobre la base de
  prueba (o no tiene base).
- Toda orden sobre la base de prueba avisa en la salida de errores: `*** DATOS DE
  PRUEBA: ... ***`.

**La consola**: con la base de prueba, `/consola` lleva una banda fija («DATOS DE
PRUEBA: ...», `position: sticky`) justo detrás de `<body>`, puesta por el servidor y
no por el script; el título de la pestaña lo dice; la página local `/` también; y
cada respuesta lleva la cabecera `X-BMS-Entorno: demo`.

**`serve.py`, el modo contenedor**: `serve --contenedor` escucha en `0.0.0.0` y
solo dentro de un contenedor (`en_contenedor`: `/.dockerenv` o
`/run/.containerenv`; `interfaz_permitida` se niega fuera de uno y con cualquier
otra interfaz), y no lee PDF (`Agente(lectura=False)`: lanzar una pasada da 409 y
dice que lo hace el lector). El Host sigue teniendo que ser 127.0.0.1 o localhost.

**La clave de la API como fichero**: `config.clave_api()` lee el fichero que diga
`BMS_CLAVE_API_FICHERO` (la ruta, no la clave), comprueba que parece una clave y lo
dice sin enseñarla (`ClaveNoValida`); sin la variable, el SDK la busca en
`ANTHROPIC_API_KEY` como antes. La CLI (`_cliente_api`) y el servidor la usan.

**`copia.py`**: `bms-agent copia DESTINO` hace la copia en caliente de SQLite
(`backup`, coherente con la consola en marcha), copia los originales y las anclas a
una carpeta nueva con fecha y hora (nunca pisa otra), escribe `MANIFIESTO.sha256`
y la comprueba (la base, abierta como inmutable, pasa `integrity_check`; cada
fichero, su hash; ni falta ni sobra nada). `copia --comprobar CARPETA` comprueba una
copia sin tocarla. `bms-agent restaurar CARPETA` la vuelve a poner: comprueba la
copia, que sea de una base del mismo nombre (prueba con prueba, verdad con verdad) y
que nadie esté escribiendo, guarda antes lo que había entero en
`antes-de-restaurar/`, escribe la base con `backup`, añade los originales que faltan
(nunca pisa uno) y pone las anclas de la copia.

**`docker/`**:

- `Dockerfile`: `python:3.11.17-slim-trixie` fijada por etiqueta y digest,
  dependencias de `requirements.txt` con `--require-hashes --only-binary=:all:`,
  usuario 10001, `HEALTHCHECK` (`salud 127.0.0.1:8765`), `ENTRYPOINT python -m
  bms_agent.cli`; un secreto de construcción opcional `ca_extra` para un proxy que
  intercepta TLS (no queda en la imagen).
- `docker-compose.yml`: cuatro servicios con la misma imagen (`consola`, `salida`,
  `lector` con perfil `lector`, `orden` con perfil `ordenes` y `network_mode:
  none`), tres redes (`red_consola` y `red_lector` internas, `red_exterior` solo
  para la salida), el volumen `datos`, el buzón `../buzon` montado de solo lectura
  en el lector y en `orden`, el secreto `anthropic_api_key` (fichero
  `docker/secretos/anthropic_api_key.txt`) solo en el lector, `HTTPS_PROXY` del
  lector al alias `proxy`, y en todos `read_only`, `cap_drop: [ALL]`,
  `no-new-privileges`, `init`, `pids_limit`, `/tmp` en memoria `noexec`, límites de
  memoria y de log. El único puerto: `127.0.0.1:8765:8765`, en la salida.
- `requirements.txt`: las 16 dependencias con su versión y el sha256 de sus ruedas
  x86_64 y aarch64.
- Los scripts de Windows, cada uno con su `.bat` (que lo abre con
  `-ExecutionPolicy Bypass`) y mensajes en claro: `iniciar` (`-Demo`: rehace los
  datos de prueba y enseña los tokens), `parar` (nunca borra el volumen),
  `importar` (cada carpeta del buzón, un tipo; lo que entra se mueve a
  `buzon\hecho\<fecha>\`), `leer-facturas` (cuenta gratis, enseña el coste y solo
  sigue con «si»), `copia` (`-Destino`, `-Comprobar`), `restaurar` (pregunta, para,
  restaura y verifica) y `persona` (alta y token). `comun.ps1` lleva lo compartido:
  el token se pide oculto y pasa al contenedor por el entorno (`-e BMS_TOKEN`),
  nunca en la línea de la orden.
- `secretos/LEEME.txt`; `.dockerignore` (primero todo fuera, luego solo `src/`,
  `config/` sin `tarifas.yaml`, `pyproject.toml`, `README.md` y `requirements.txt`);
  `.gitignore` (`/buzon/`, `/docker/secretos/*`); `.gitattributes` (`.ps1` y
  `.bat` con fin de línea de Windows).

**Documentación**: `docs/entorno-local.md` (para el dueño: qué es, Docker
Desktop, la clave, la primera vez, arrancar y parar, el buzón, prueba y verdad,
copias al disco cifrado con BitLocker o VeraCrypt y cómo restaurar, qué hacer si
algo falla, el presupuesto de funcionamiento y el mantenimiento de cada mes, y una
parte para quien mantiene el programa); el README; la cabecera `X-BMS-Entorno` en
`docs/integracion-web.md`; un aviso en `docs/instalacion-windows.md`.

### La puerta, test por test

| Puerta | Tests |
| --- | --- |
| El proxy, con sockets locales | `test_salida.py`: el destino permitido conecta y los bytes pasan tal cual (`test_el_destino_permitido_conecta_y_los_bytes_pasan_tal_cual`, también lo mandado antes del 200); cualquier otro recibe 403 sin resolverlo siquiera (`test_otro_destino_recibe_403_y_no_se_intenta`, con `api.anthropic.com.evil.example`, `evilapi.anthropic.com`, `127.0.0.1` y `localhost`); los trucos de nombre y las IP en sus formas raras (`test_otro_nombre_no_pasa`, `test_una_ip_escrita_a_mano_no_pasa_nunca`); el DNS que rebota hacia casa (`test_un_dns_que_rebota_hacia_casa_no_pasa`, `test_conecta_con_la_direccion_comprobada_y_no_vuelve_a_resolver`); HTTP en claro, 405, sin apuntar sus cabeceras (`test_http_en_claro_recibe_405`); cada intento en el registro (`test_cada_intento_queda_en_el_registro`); la cabecera enorme o cortada; el reenvío de la consola; la CLI y `salud` |
| docker-compose.yml, sin contenedores | `test_entorno_local.py`: redes (`test_la_consola_y_el_lector_solo_estan_en_redes_internas`: la salida es el único servicio en una red con salida), solo lectura, `cap_drop`, `no-new-privileges`, `init`, sin `docker.sock` (`test_cada_servicio_va_endurecido`), el único puerto en 127.0.0.1 (`test_el_unico_puerto_es_el_de_la_consola_en_127_0_0_1`), el secreto solo en el lector y ninguna clave en variables (`test_la_clave_es_un_secreto_que_solo_ve_el_lector`), el lector solo a propósito y por el proxy (`test_el_lector_solo_arranca_a_proposito_y_sale_por_el_proxy`), la lista blanca y los alias (`test_la_salida_solo_deja_ir_a_la_api_y_escucha_en_la_red_del_lector`), `docker compose config` la acepta; el Dockerfile (base por etiqueta y digest, usuario, salud, hashes), `requirements.txt` con las versiones del entorno de desarrollo, `.dockerignore` y `.gitignore`, los scripts (ASCII, su `.bat`, nunca `down -v`, el token por el entorno, contar antes de pagar, cada carpeta del buzón) |
| La base de prueba: cada bloque del panel y cada nivel | `test_demo.py::test_cada_bloque_del_panel_y_cada_nivel_tienen_algo` (el 14 de octubre, el 2 de enero, un sábado 1 de mes y el último día de un trimestre: los siete bloques con algo dentro, los cuatro niveles, ningún plazo del BTW pasado sin presentar, ningún aviso de la construcción); `test_estan_los_casos_que_la_consola_tiene_que_ensenar`; `test_todo_es_ficticio` (nombres, KvK, btw-id, IBAN del banco DEMO que pasan F1, y cada fichero y extracción con la marca) |
| La banda | `test_la_consola_de_la_base_de_prueba_lleva_la_banda` (detrás de `<body>`, en el título, en `/`, la cabecera en `/api/v2`), `test_la_consola_de_la_base_de_verdad_no_lleva_banda` |
| Nada de la prueba en la base de verdad | `test_crear_no_toca_la_base_de_verdad` (el volcado entero de la de verdad, igual), `test_crear_solo_escribe_en_un_fichero_llamado_demo_sqlite3`, `test_crear_no_sobrescribe_una_base_que_no_es_de_prueba`, `test_una_copia_de_la_base_de_prueba_con_otro_nombre_no_se_abre`, `test_ninguna_orden_lleva_lo_de_la_prueba_a_la_base_de_verdad` (cada fichero que fabricó la prueba, por `importar` de cada fuente, también `--simular`, por `extract` sin llamar a la API, por `importar-out` y por `politica cargar`: la de verdad no gana ni una fila con la marca), `test_ningun_codigo_junta_dos_bases` (ningún `ATTACH`, ninguna opción de base más que `--db`), `test_el_extractor_no_paga_un_pdf_de_prueba_sin_base` |
| Contenedores de verdad | `test_entorno_docker.py`, con `BMS_PROBAR_DOCKER=1 BMS_DOCKER="sudo -n docker"`: **4 pasan aquí**. Un proyecto aparte con su volumen: la consola contesta en 127.0.0.1:8765 con la banda; desde la consola no se llega a 1.1.1.1, 8.8.8.8, `api.anthropic.com` ni al proxy; desde el lector no se llega a internet ni a la consola, solo al proxy; por el proxy, `api.anthropic.com:443` da 200 y `example.com`, `api.anthropic.com.evil.example`, una IP y el puerto 80, 403; HTTP en claro, 405; el cliente HTTP del SDK sale por `HTTPS_PROXY` (ProxyError 403 con `example.com`), y el registro de la salida tiene cada intento. A mano, además: desde las otras IP de la máquina (la de la red y las de los puentes de Docker) el puerto no contesta; un Host ajeno da 421; dentro de la consola, uid 10001, `CapEff` 0, `NoNewPrivs` 1 y `/app` de solo lectura; la clave solo está como fichero en el lector |
| Los scripts | Los ocho `.ps1` pasan el analizador de PowerShell 7, y se ejecutaron de verdad (PowerShell 7 en Linux contra el mismo Docker): `iniciar -Demo`, `importar` (a la prueba entra y se mueve a `hecho`; a la de verdad, un fichero de prueba se rechaza y se queda), `persona`, `copia`, `copia -Comprobar`, `restaurar`, `leer-facturas` sin clave y `parar` |
| Lo demás | La consola solo escucha en 0.0.0.0 dentro de un contenedor y ahí no lee PDF; la clave de su fichero, y uno malo se dice sin enseñarla; la copia entera, comprobada, sin pisar otra; restaurar vuelve a la copia y guarda lo de antes, y con una copia mala o de la otra base no toca nada |
| La suite entera | 2094 pasan y 4 se saltan sin `BMS_PROBAR_DOCKER=1`; con él, los 4 también pasan |

**Lo que queda por mirar en el ordenador del dueño** (no se puede aquí): que Docker
Desktop para Windows publique el puerto en `127.0.0.1` igual que el motor de Linux;
los scripts en Windows PowerShell 5.1 (el `.bat`, la ventana que se abre,
`Start-Process` abriendo el navegador, `Read-Host -AsSecureString`); el montaje de
una letra de unidad (`E:\...`) en `copia` y `restaurar`; y un `leer-facturas` de
verdad con su clave (aquí no hay clave ni se llama a la API).

### Desviaciones de lo pedido, y por qué

1. **El puerto de la consola lo publica la salida, no la consola.** Docker no
   publica el puerto de un contenedor que solo está en redes internas: se probó
   aquí (`docker port` vacío, la conexión rechazada). Para que la consola siga sin
   salida, la salida reenvía tal cual (`Reenvio`) de su alias `entrada`, que solo
   existe en `red_exterior` (por donde llega el puerto publicado), a `consola:8765`.
   La salida sigue siendo el único contenedor con un pie fuera.
2. **Tres redes en vez de una interna.** Con una sola, la consola podría hablar con
   el proxy y, con una clave ajena, sacar datos hacia una cuenta de otro en la API
   de Anthropic. Ahora la consola está en `red_consola` y el lector en
   `red_lector`, la salida en las dos más `red_exterior`, y el proxy escucha solo
   en su dirección de `red_lector` (el alias `proxy`).
3. **Un cuarto servicio, `orden`, sin red ninguna**, para importar, crear los datos
   de prueba, las personas y las copias: los scripts necesitan ejecutar órdenes y
   `network_mode: none` es más estricto que cualquier red.
4. **`datos` es un volumen de Docker, no una carpeta de Windows.** SQLite en WAL
   necesita bloqueos y memoria compartida que la carpeta compartida de Windows con
   Docker Desktop no da bien, y la consola y el lector escriben a la vez. Por eso
   las órdenes `copia` y `restaurar` y sus scripts (que no estaban en la lista): la
   copia al disco cifrado no puede ser «copiar la carpeta». El buzón sí es una
   carpeta de Windows, de solo lectura para los contenedores; los scripts mueven lo
   importado, en Windows.
5. **La clave se lee de un fichero con `BMS_CLAVE_API_FICHERO`**: el SDK no lee
   ficheros. La variable lleva la ruta del secreto, no la clave.
6. **La regla «solo 127.0.0.1» de `serve.py`** admite `0.0.0.0` dentro de un
   contenedor y solo ahí; lo que protege entonces es la red (internas y el puerto en
   127.0.0.1). En ese modo la consola no lee PDF.
7. **La base de prueba, con sus originales y anclas aparte** (`demo-documentos/`,
   `demo-anclas.log`): con el nombre pedido, `datos/demo.sqlite3`, la carpeta de
   originales de al lado habría sido la de la base de verdad.
8. **El aislamiento es por marca en el contenido**, además del nombre: se puede
   copiar un fichero de un sitio a otro, y la marca va dentro. El precio: un fichero
   de verdad que llevara literalmente `BMS-DEMO`, o un IBAN holandés del banco
   `DEMO` (que no existe), no entraría.
9. **La base de prueba se hace con la fecha de hoy y se rehace cada vez** que se
   arranca con `-Demo` (`--rehacer`): con fechas fijas, en un mes no habría nada
   «esta semana» y todo estaría vencido. Los tests la construyen en cuatro fechas
   fijas.
10. **Las tarifas de venta son integrales** (el mismo precio de día, de noche y de
    fin de semana, en filas Dag, Nacht y Weekend): Exact no dice el turno de una
    línea de venta y la tarifa sin turno es la «Dag» (`reglas/tarifas.py`). Los
    recargos están en la compra.
11. **Los trimestres pasados del BTW salen presentados** (anotados por «Ana Demo»
    con una referencia ficticia, después de que «Bram Demo» marcara la hoja lista:
    la separación de funciones lo exige con dos personas) y el que vence, listo para
    revisar. Es la orden de anotar lo que una persona presentó; nada se presenta.
12. **El aviso F0** (cuentas heredadas sin atestar) se deja abierto a propósito: es
    lo que ve el dueño el primer día con su maestro de verdad.
13. **La imagen es de Debian 13 (trixie)**, no 12: Python 3.11.17 con SQLite 3.46.1
    (bookworm trae 3.40.1, más viejo que el 3.45 del entorno de desarrollo). Sin la
    línea `# syntax=` (que bajaría otra imagen de Docker Hub) y sin instalar el
    paquete: `PYTHONPATH=/app/src` y el directorio de trabajo `/app`, donde
    `config/importacion` se encuentra solo.
14. **El proxy hace más de lo pedido**: rechaza los nombres que resuelven a una
    dirección que no es de internet y se conecta a la dirección comprobada. Los
    tests con sockets locales inyectan el resolvedor y apagan esa comprobación
    (`solo_publicas=False`); tiene sus propios tests.
15. **Códigos**: HTTP en claro da 405 (con `Allow: CONNECT`), lo malformado 400, la
    cabecera enorme 431 y un destino que no está en la lista 403.
16. **Un sitio propio contra la base de prueba** no recibe ninguna clave nueva en el
    contrato v2, solo la cabecera `X-BMS-Entorno: demo` (documentada): el contrato
    sigue en 2.0.

**Tests existentes cambiados, y por qué** (los dos en `test_alcance_v1.py`):
`test_ningun_modulo_habla_con_la_red_salvo_la_extraccion` deja a `bms_agent.salida`
importar `socket` (y solo a él, y solo eso: `PUEDEN_ABRIR_SOCKETS`), y comprueba
que su lista blanca por defecto es `api.anthropic.com:443` y nada más: el proxy es
la red a propósito. `test_no_hay_credenciales_ni_claves_de_banco` admite
`BMS_CLAVE_API_FICHERO`, que dice dónde está el fichero de la clave de la API (no es
una credencial de banco ni la clave).

### Lo que deben saber los pasos siguientes

- **Una vía nueva de entrada de datos** (otro importador, otra ruta de documentos)
  pasa por `registrar_documento`, `registrar_extraccion` o `importar_fichero`, o
  llama ella a `exigir_sin_datos_de_prueba`: si no, lo de la prueba podría entrar en
  la base de verdad por ahí.
- **Un fichero nuevo que fabrique `demo crear`** lleva la marca (`_csv` pone la
  columna; los PDF y el XML, su comentario), o `test_todo_es_ficticio` falla.
- **Una regla que cambie** puede vaciar o llenar un bloque del panel de la prueba:
  `test_cada_bloque_del_panel_y_cada_nivel_tienen_algo` lo dirá. Se ajusta el
  escenario de `demo.py`, no el test.
- **Un destino nuevo para la salida** es una línea de `docker-compose.yml`
  (`--permitir host:puerto`, nunca IP ni comodines) y el test estático, que hoy exige
  solo `api.anthropic.com:443`.
- **Una variable de entorno nueva** va en la lista de `test_alcance_v1.py`.
- **La imagen se reconstruye** con cada versión del código (`docker compose build`);
  una dependencia nueva va en `docker/requirements.txt` con sus hashes de las dos
  plataformas (docs/entorno-local.md, apartado 13), y el test exige que coincida con
  el entorno de desarrollo.
- **`export --v2` de la base de prueba** no lleva ninguna marca dentro del JSON (solo
  la cabecera por HTTP). Si un sitio va a leer ficheros exportados, haría falta una
  clave `entorno` (contrato 2.1).
- **Cuando lleguen los formatos reales** de TRNSPRNT o de Exact y cambien los
  mapeos, los CSV de la prueba (que siguen los mapeos v1) cambian con ellos.

### Correcciones de la revisión

Dieciocho hallazgos de la revisión, con tres repetidos (el 10 es el 2, el 17 es
el 4 con el 11, y el 18 es el 6). Todos se reprodujeron y todos eran reales, salvo
una parte del 9 (pedir un token para restaurar), que se explica abajo. Cada
corrección de código tiene un test que falla con el código de antes y pasa con el
de ahora (comprobado volviendo los ficheros de `src/` a `22be25f`); los de los
scripts de Windows se vigilan con los tests estáticos y los ocho `.ps1` (ahora
nueve) pasan el analizador de PowerShell 7. **2120 tests pasan** y cinco se
saltan sin `BMS_PROBAR_DOCKER=1`; con él (y la imagen reconstruida aquí), los cinco
de los contenedores también pasan, el nuevo del registro de la salida incluido.

1. **La copia con la consola anclando a la vez no pasaba `db verificar`**
   (mayor). `copiar()` copiaba la base y después las anclas: un ancla escrita
   entre las dos quedaba más allá de la cadena copiada. Ahora las anclas se
   copian antes que la base (un ancla más vieja que la base siempre se cumple) y
   los originales después (cada documento de la base copiada ya tiene el suyo).
   Además `comprobar()` mira la cadena de la copia contra sus anclas, lo mismo
   que `db verificar`: una copia que este rechazaría no cuenta como comprobada, y
   `restaurar` no la pone. Tests:
   `test_una_copia_con_la_consola_anclando_a_la_vez_pasa_db_verificar` (escribe y
   ancla justo cuando se copian las anclas) y
   `test_una_copia_que_db_verificar_rechazaria_no_pasa_por_comprobada`.
2. **`restaurar` no veía la consola en marcha** (mayor; el 10 es el mismo).
   En WAL, una conexión abierta y quieta no bloquea `BEGIN EXCLUSIVE`. Ahora
   `copia._en_exclusiva` sale de WAL (`journal_mode=DELETE`, que falla con
   «database is locked» si hay otra conexión, aunque no haga nada) y se queda la
   base con `locking_mode=EXCLUSIVE` y una escritura hasta acabar: la copia de
   antes y la restauración van por esa conexión y nadie entra entre medias.
   Test: `test_restaurar_no_sigue_con_la_base_abierta_aunque_este_en_wal`
   (`preparar(ruta)` abierto, como la consola). El test que ya había,
   `test_restaurar_vuelve_a_la_copia_y_guarda_lo_de_antes`, dejaba abiertas sus
   conexiones (`with sqlite3.connect(...)` no cierra) y ahora lo veía: se cierran
   con `contextlib.closing`.
3. **`importar.ps1` sacaba del buzón un fichero que no había entrado** (mayor).
   `bms-agent importar` salía con 0 aunque el lote quedara `rechazada`. Ahora
   sale con `SALIDA_RECHAZADA` (3) si un lote no entra, también si es el mismo
   fichero que ya se intentó y se rechazó (no entrará nunca: se dice que hay que
   sacar uno nuevo), y con `SALIDA_PARCIAL` (4) si entra con filas rechazadas.
   `importar.ps1` mueve a `hecho` lo que sale con 0 o 4 (con 4, avisa en
   amarillo) y deja en el buzón lo demás. Tests:
   `test_importadores.py::test_un_lote_rechazado_entero_no_sale_con_cero` y
   `test_importar_solo_saca_del_buzon_lo_que_ha_entrado`. **Cambian dos tests**:
   `test_importar_y_ver_el_registro_por_la_cli` esperaba 0 de un fichero que lleva
   una fila mala a propósito (ahora 4), y
   `test_ventas.py::test_las_vistas_y_las_relaciones_por_la_cli` admite 3 y 4.
4. **Con `-Demo`, un PDF de prueba se mandaba a la API** (menor; el 17 es el
   mismo con el 11). Ahora un PDF con la marca no se manda nunca: en la base de
   prueba su extracción ya está (y se reutiliza, ver el 15); si no está, se omite
   y se dice. Test:
   `test_demo.py::test_un_pdf_de_prueba_no_se_paga_tampoco_en_la_base_de_prueba`
   (dos de `demo crear` y uno que la base no conoce, con un cliente que falla si
   se le llama).
5. **El plazo de la cabecera era por `recv`, no para la cabecera entera**
   (menor). `_leer_cabecera` lleva ahora un límite (`time.monotonic()` más
   `ESPERA_CABECERA`) y antes de cada `recv` pone de timeout lo que queda. Las
   conexiones que aún no han mandado su cabecera tienen su tope
   (`MAX_ESPERANDO`, 64): pasado, se cierran sin esperar y se apunta (503). Los
   límites se inyectan en `Proxy` (`espera_cabecera`, `max_tuneles`,
   `max_esperando`, `inactividad`). Tests nuevos en `test_salida.py`: el plazo con
   un byte cada 0,25 s (`test_la_cabecera_entera_tiene_su_plazo_aunque_llegue_a_gotas`:
   400 en menos de 3 s, sin resolver nada), el 503 con todos los túneles
   ocupados, el cierre de un túnel callado y el tope de las que esperan.
6. **La clave guardada con BOM o en UTF-16** (menor; el 18 es el mismo). Ahora
   `config.clave_api` lee bytes: con BOM de UTF-16, UTF-16; si no, `utf-8-sig`.
   Lo que no es texto es un `ClaveNoValida` («guárdalo como texto UTF-8»), no una
   traza. Tests: `test_la_clave_se_lee_de_su_fichero` con UTF-8, UTF-8 con BOM,
   UTF-16 LE y BE y CRLF, y un caso más en
   `test_un_fichero_de_clave_malo_se_dice_sin_ensenarla`.
7. **Dos tests dependían de no correr en un contenedor** (menor). Ahora fijan
   `serve.en_contenedor` a falso. Comprobado simulando el contenedor (la marca
   por defecto de `en_contenedor` apuntando a un fichero que existe): con los
   tests de antes la suite se queda colgada (`timeout` la mata), con los de ahora
   pasan.
8. **Restaurar en una carpeta que no existe daba una traza** (menor). Ahora
   `restaurar` crea la carpeta de la base. Test:
   `test_restaurar_en_una_instalacion_nueva_crea_la_carpeta` (la base, los
   originales y las anclas, y `db verificar` cuadra).
9. **`restaurar` pisaba las anclas y no dejaba rastro** (mayor). Ahora el
   fichero de anclas no se reescribe nunca: se le añaden al final las líneas de
   la copia que no tenga (`_juntar_anclas`). La base restaurada recibe un evento
   `restauracion` (`auditoria.TIPO_RESTAURACION`) con la carpeta de la copia, la
   cabeza de la copia, la cabeza sustituida (id y hash), dónde quedó lo de antes y
   las anclas que la restauración deja sin cumplir (`auditoria.anclas_sin_cumplir`),
   y se ancla en seguida. `verificar_cadena` solo perdona un ancla que nombre un
   evento de restauración de la propia cadena (que también pasa por su hash), y
   `db verificar` lo dice: «la base se restauro desde una copia (evento N)» y
   cuántas anclas son de lo sustituido. Una vuelta atrás a mano (copiar el
   fichero) sigue dando «se ha cortado». `restaurar.ps1` monta la copia con su
   nombre (`/copias/bms-copia-...`) para que el evento lo diga. La copia de antes
   de restaurar se numera (`-2`, `-3`) si ya hay una de ese segundo. Tests:
   `test_restaurar_no_reescribe_las_anclas_y_deja_el_corte_dicho` (el caso de la
   revisión: Ana, copia, Bram, Carla; después, el fichero de anclas empieza por
   lo que tenía, el evento tiene la cabeza sustituida y las dos anclas, `db
   verificar` da 0 y lo dice; sin el evento, 1) y
   `test_restaurar_dos_veces_sigue_cuadrando` (dos vueltas atrás en el mismo
   segundo, con tres historias en las anclas). **No se pide token** (desviación
   17): la CLI local actúa como el operador del fichero, como en `usuario`, y
   quien tiene la base puede sacar un token de administrador con `usuario token`
   sin ninguno; pedirlo aquí no protegería nada. El evento lo firma el usuario de
   sistema, y lo que la revisión echaba en falta (que la vuelta atrás quede dicha
   y no pase por un «Todo cuadra.» limpio) es lo que ahora hace.
10. Es el 2.
11. **La base de prueba admitía datos de verdad** (menor). Ahora es el espejo de
    `exigir_sin_datos_de_prueba`: `almacen.exigir_de_su_base` lanza
    `DatosDeVerdadEnLaPrueba` (un `DatosDePrueba` más para quien lo captura) si a la
    base de prueba va algo sin la marca. Lo usan `registrar_documento`,
    `registrar_extraccion`, `importar_fichero` e `importar_extracto`; la
    política no (no son datos). El extractor, sobre la base de prueba, no manda
    ni guarda un PDF sin la marca. `leer-facturas.ps1 -Demo` ya no lee nada y lo
    dice; `importar.ps1 -Demo` con un fichero de verdad lo deja en el buzón (sale
    con 1). Test: `test_demo.py::test_la_base_de_prueba_no_admite_nada_de_verdad`
    (los PDF de ejemplo, un maestro de Exact y un extracto: nada se paga, nada
    entra y la base de prueba queda igual) y
    `test_leer_facturas_no_lee_nada_con_demo`.
12. **`persona.ps1` daba un token del rol que ya tenía la persona** (menor). La
    lógica pasa a Python: `bms-agent usuario asegurar NOMBRE --rol ROL` crea a la
    persona (por su nombre exacto) si falta, no hace nada si ya tiene ese rol y
    solo ese, y si tiene otros no toca nada y sale con `SALIDA_OTRO_ROL` (3).
    `persona.ps1` solo pide el token si sale con 0, y `-Rol` es obligatorio (sin
    rol por defecto). Tests: `test_usuario_asegurar_no_da_otro_rol_a_quien_ya_existe`
    («Bra» no es «Bram») y `test_persona_pide_el_rol_y_no_cambia_el_de_quien_ya_existe`.
13. **El buzón no tenía carpetas para el maestro ni las modificaciones de PO**
    (mayor). `importar.ps1` tiene ahora una carpeta por cada tipo importable
    (`maestro\objetos`, `recursos`, `contactos`, `alias`, `tarifas`, `ciclos` y
    `po\modificaciones`), en el orden en que unos usan lo que traen otros. El test
    estático saca la lista de los mapeos de `config/importacion/` y comprueba el
    orden. `docs/entorno-local.md` §7 las explica. `sembrar` sigue fuera de la
    imagen (`config/tarifas.yaml` no entra, a propósito): en el entorno de Docker
    las tarifas van por `maestro\tarifas`, como en la base de prueba.
14. **El registro de la salida se perdía con cada `down`** (mayor). Ahora
    `bms-agent salida --registro FICHERO` apunta también en un fichero
    (`RotatingFileHandler`, se añade al final, 10 de 5 MB), que en Docker vive en
    su volumen `registro_salida` (`/registro`, creado en la imagen para el usuario
    10001). La salida no ve los datos; `orden` monta el registro de solo lectura y
    `bms-agent salida-registro [--rechazados]` lo lee de lo más viejo a lo más
    nuevo, con los rotados. Script nuevo: `ver-salida.ps1` y su `.bat`. Tests:
    `test_el_registro_en_fichero_sigue_despues_de_parar_y_arrancar` y
    `test_el_registro_rotado_se_lee_en_orden`; los estáticos del compose, y en
    `test_entorno_docker.py` uno nuevo que hace `down` y `up` y lee el registro.
15. **Sin `out/`, lo ya leído se volvía a pagar** (menor). Se eligió la otra
    salida que proponía la revisión: el extractor mira las extracciones vigentes
    del almacen (`extract._vigentes_en_almacen`, que sustituye a
    `_vigentes_de_otra_version`) antes de pagar. Con `CONSERVAR` no se manda
    ninguno que ya tenga vigente; con `ESTRICTA`, ninguno cuya vigente sea de
    estas versiones; con `--force`, se lee. Así la copia sigue sin `out/` (lo que
    hace falta está en la base) y lo dice su docstring y la guía. Test:
    `test_almacen_extraccion.py::test_lo_que_ya_esta_en_el_almacen_no_se_paga_aunque_falte_out`.
    Lo que se pierde con `out/` es el historial de `coste` (lo gastado), que lee
    de ahí; queda dicho.
16. **La pasada del día no la hacía nadie en Docker** (menor). `iniciar.ps1` la
    hace antes de arrancar la consola y `importar.ps1` al acabar
    (`orden recalcular --diaria`); el aviso de la consola dice que en Docker la
    hacen esos dos, y la guía (§6) lo explica. Test:
    `test_la_pasada_del_dia_la_hacen_iniciar_e_importar`.
17. Es el 4 con el 11.
18. Es el 6.

**Desviación 17.** `restaurar` no pide token (hallazgo 9): el operador del
fichero ya puede sacar uno con `usuario token`, y el evento de restauración lo
firma el usuario de sistema, como las órdenes de `usuario`.

**Para los pasos siguientes**: un evento nuevo que corte la cadena no existe; si
hiciera falta otro, iría como `restauracion` (con las anclas que corta) o
`db verificar` lo dará por cortado. Una vía nueva de entrada de datos llama a
`exigir_de_su_base` (no solo a `exigir_sin_datos_de_prueba`). Un tipo nuevo de
importación es un mapeo en `config/importacion/` y una carpeta en
`importar.ps1`: el test estático lo exige.

---

## Revision final

La revisión del sistema completo (sobre `800b936`) dejó treinta hallazgos: uno
bloqueante, doce mayores y diecisiete menores. Los treinta se reprodujeron y los
treinta eran reales; veintinueve están corregidos y uno (el 17) a medias, por lo que
dice «Pendiente». Cada corrección de código tiene su test en
`tests/test_revision_final.py`, y cada test falla con el código de antes: se
comprobó poniendo el `src/` de `800b936` delante (`git archive 800b936 src`, con
`PYTHONPATH`) y pasando el fichero. De los 56 tests de los hallazgos fallan 51. Los cinco que pasan
son tres de control y dos que leen ficheros de fuera de `src/`. Los de control: un
IBAN compacto en mayúsculas, que ya se enmascaraba; un texto que no es un IBAN, que
no se toca; y una factura que viene de `out/`, que sigue sin fecha de recepción. Los
otros dos leen `docker/` y `docs/`, y fallan contra los ficheros de `800b936`, que no
tienen `Es-Si` ni la guía de los trimestres de antes. Hay además un test que no
es de un hallazgo: `test_una_base_de_antes_con_anclas_suyas_no_se_da_por_reescrita`
vigila que la corrección del 4 no rompa una base creada antes de ella.

### Los hallazgos, uno a uno

1. **Se podía anular una factura pagada, y confirmar un pago de una anulada**
   (mayor). Era real. El dinero que había salido del banco dejaba de contar en
   todos los totales. Ahora `anular_factura` y `fusionar_factura` no se hacen si la
   factura lleva un pago (confirmado o propuesto): se retira antes el pago, si no
   es de ella, o se apunta un abono. `confirmar_pago` y `marcar_pagada` no se hacen
   sobre una factura anulada, fusionada o sustituida (`pagos._exigir_que_cuente`).
   Una importación de Exact puede seguir trayendo un pago de una factura anulada.
   Para eso está la regla nueva **K9** (pegajosa, de R): una factura anulada o
   fusionada con pagos confirmados dice dónde está ese dinero. Tests:
   `test_no_se_anula_una_factura_pagada_ni_con_un_pago_propuesto`,
   `test_no_se_confirma_un_pago_de_una_factura_que_ya_no_cuenta`,
   `test_k9_el_pago_de_exact_de_una_anulada_no_desaparece`, `test_k9_pura`.
2. **Un saldo del otro signo se trataba como deuda vencida** (mayor). Era real:
   una factura pagada entera y después abonada salía «vencida», con K1 y con su
   cobro esperado en la caja. Ahora `reglas.pagos.vence` y `de_mas` lo deciden en
   un solo sitio. Un abono, o un saldo del otro signo que la factura, no vence ni
   es un cobro o un pago esperado (`flujo_caja`, K1, prioridad). Una factura
   pagada de más queda saldada («pagada» o «acreditada»), y K2 o R2 dicen lo que
   sobra. La migración **0017** rehace `v_proveedor_totales` y `v_cliente_totales`:
   lo pendiente de una parte deja fuera lo que sobra. Un abono sin enlazar sigue
   restando, porque acredita a la parte aunque todavía no diga de qué factura.
   Tests: `test_una_factura_pagada_y_despues_abonada_no_esta_vencida`,
   `test_un_abono_sin_enlazar_no_vence_ni_es_un_cobro_esperado`,
   `test_vence_y_de_mas_son_puras`.
3. **La prioridad del proveedor y del Objeto no veía lo más grave de los pagos**
   (menor). Era real. Pagar una factura Bloqueada a una cuenta que no era pagable
   la dejaba pagada y fuera del agregado. Ahora una factura saldada sigue contando
   en el agregado mientras su suelo sea Bloqueada o Urgente, o tenga abierto un
   hallazgo de K que no sea un aviso (`estados._sigue_pidiendo`). Los hallazgos
   del propio proveedor también suben su prioridad: los de `tabla = 'proveedor'` y
   el F7 de un movimiento con su clave. Antes solo contaban los de sus facturas.
   Tests: `test_pagar_mal_una_factura_bloqueada_no_baja_a_su_proveedor_ni_a_su_objeto`,
   `test_un_hallazgo_del_proveedor_sin_facturas_le_da_su_prioridad`.
4. **Las anclas se podían burlar sin tocar `anclas.log`** (mayor). Era real, por
   las dos vías. (1) Reescribir la cadena desde el evento 1 cambiaba la identidad
   de la base: las anclas de verdad pasaban por «de otra base», y la siguiente
   orden anclaba la cadena falsa. (2) Un evento `restauracion` escrito en la base
   perdonaba cualquier corte. Ahora solo perdona lo que está fuera de la base, en
   `anclas.log`. Cada base nueva apunta allí su identidad y su nombre
   (`nueva_base`, desde `almacen.preparar` y `db init`). `copia.restaurar` apunta
   el corte (`restauracion`) con el sha256 de lo que guardó en
   `antes-de-restaurar`, y `db verificar` solo lo perdona mientras eso siga ahí y
   sea lo guardado. Unas anclas de otra base no se dan por buenas si ninguna es de
   esta base y esta no consta como creada allí. En ese mismo caso, `anclar` no
   apunta (`AnclasDeOtraBase`) y la orden lo avisa. Tests:
   `test_reescribir_la_cadena_desde_el_primer_evento_no_pasa_db_verificar`,
   `test_un_evento_de_restauracion_falso_no_perdona_un_corte`,
   `test_una_restauracion_de_verdad_sigue_cuadrando_y_sin_lo_sustituido_no`.
5. **`GET /api/datos` lo daba todo sin token** (mayor). Era real: también daba
   los IBAN enteros, con CORS, a otro origen. Ahora pide el token personal
   (`X-BMS-Token`) de alguien con `ver_facturas`. A un origen declarado le da los
   IBAN enmascarados. El cuerpo sigue siendo byte a byte la foto de referencia
   (desviación 5). Test: `test_api_datos_pide_token_y_no_da_un_iban_entero_a_otro_origen`.
6. **Los caracteres de control de un documento llegaban a la terminal** (mayor).
   Era real: una secuencia ESC en el nombre de un proveedor movía el cursor, y
   OSC 52 escribía en el portapapeles. Ahora `terminal.SalidaSegura` envuelve
   stdout y stderr en `cli.main`, y `campos.a_columna` guarda los textos sin
   controles (`terminal.sin_control`; cambian por U+FFFD, que se ve). El salto de
   línea y el tabulador se quedan, y la evidencia original no se toca. El registro
   del servidor los traduce también. Tests:
   `test_un_pdf_con_secuencias_de_escape_no_manda_en_la_terminal`,
   `test_la_salida_segura_y_el_registro_del_servidor`.
7. **`sin_ibanes` solo veía un IBAN en mayúsculas y compacto o en grupos de
   cuatro** (menor). Era real. Ahora encuentra también los IBAN en minúsculas, con
   puntos o guiones y con cualquier agrupación. Antes de enmascarar comprueba el
   dígito de control y toma el prefijo válido más largo, así que un texto que no
   es un IBAN no se toca. Tests:
   `test_sin_ibanes_ve_un_iban_escrito_de_cualquier_manera` (siete formas),
   `test_sin_ibanes_no_toca_lo_que_no_es_un_iban`.
8. **D6 no existía** (mayor). Era real: el desglose de IVA podía no sumar la
   cabecera, y el BTW lo declaraba sin objeciones. **D6** es una regla nueva, de
   B en los dos sentidos, como la familia D del §7. Compara la suma del desglose
   con la base y la cuota de la cabecera, con la tolerancia de línea por tramo más
   la de factura. Tests:
   `test_d6_un_desglose_que_no_es_la_cabecera_no_se_declara_sin_objeciones` (de
   extremo a extremo, contra el BTW) y `test_d6_el_desglose_que_no_suma_la_cabecera_bloquea`.
9. **Lo de cada día solo se podía hacer por la CLI** (mayor). Era real. La consola
   tiene ahora un formulario para cada una de estas órdenes: verificar, rechazar
   y atestar una cuenta, cambiar el teléfono, apuntar, confirmar y retirar un
   pago, anular, fusionar y deshacer una fusión, repartir y añadir una línea, la
   referencia, registrar y corregir una PO, corregir el maestro, el alias, y el
   Objeto y la persona de una línea. Tiene además la página **Caja** (el flujo
   por ventanas). Todo se pinta con `el()`, sin `innerHTML`. Tests:
   `test_la_consola_tiene_un_formulario_para_cada_orden_de_cada_dia` y
   `test_la_consola_pinta_las_cuentas_los_pagos_y_la_caja_como_texto` (con node:
   lo inyectado en los datos sale como texto).
10. **El original no se podía abrir** (mayor). Era real. Ahora se descarga desde la
    ficha (`GET /api/v2/facturas/N/original`, como adjunto, con CSP `sandbox` y 403
    a otro origen) y con `bms-agent original N --salida F`, que no pisa un fichero
    que exista. Cada apertura es un evento de la auditoría
    (`documentos.abrir`). Tests:
    `test_el_original_se_descarga_desde_la_consola_y_queda_en_la_auditoria`,
    `test_bms_agent_original_guarda_el_pdf`.
11. **Los permisos solo se daban en tres paquetes** (mayor). Era real. Ahora
    `bms-agent rol crear NOMBRE --permiso ...`, `rol listar` y `rol permisos` (todos,
    con lo que deja hacer cada uno). Hay un rol ya pensado, `captura`: ver,
    rellenar, corregir, el Objeto y la PO. Test:
    `test_un_rol_a_medida_por_la_cli_no_da_lo_que_no_lleva`.
12. **I1 no era una regla** (menor). Era real: solo se cumplía al dividir una
    línea, y corregir después el importe de la línea dejaba sus partes sin cuadrar.
    **I1** es una regla nueva, de R: las imputaciones activas de una línea suman su
    importe, con la tolerancia de línea. Tests:
    `test_i1_corregir_una_linea_dividida_deja_sus_partes_a_la_vista`,
    `test_i1_unas_imputaciones_que_no_cubren_su_linea_retienen`.
13. **La fecha de recepción no se rellenaba nunca** (menor). Era real. Ahora una
    factura que llega por correo o por ingesta toma la fecha en que se recibió, y
    una leída de una carpeta toma la fecha en que se registró. Lo que llega de
    `out/` sigue sin fecha: no se sabe cuándo llegó (`ingesta._fecha_recepcion`).
    Tests: `test_una_factura_leida_de_una_carpeta_lleva_su_fecha_de_recepcion`,
    `test_lo_que_llega_de_out_no_toma_la_fecha_de_la_migracion`.
14. **La persona de una línea no se veía ni se corregía** (menor). Era real. La
    ficha enseña la persona, la semana y el turno leídos de cada línea, y en cada
    imputación la persona, el importe y las horas. En la consola, la persona se
    cambia con el Objeto. Test:
    `test_la_ficha_ensena_la_persona_de_la_linea_las_etiquetas_y_de_donde_vence`.
15. **Las horas por semana del Objeto eran siempre 0** (menor). Era real:
    `importes_por_semana` no repartía las horas. Ahora reparte también las de venta
    y las de compra, como `por_mes`. Test: `test_la_economia_por_semana_lleva_sus_horas`.
16. **`Fuente.MAESTRO` no se usaba** (menor). Era real. Ahora el vencimiento que
    sale del plazo pactado en el maestro dice «Del maestro», con el proveedor o el
    cliente de donde viene (`consultas._vencimiento_de`). Se ve en la ficha y en la
    consola. Test: el del 14.
17. **E1 y E2 solo miraban el régimen, no el tipo** (menor). Era real, y queda **a
    medias**. E2 avisa ahora también cuando una factura trae un tipo estándar que
    ninguna factura anterior del proveedor traía (del 21 % al 9 %). E1 por tipo
    queda pendiente: compara con lo que se espera del proveedor, y eso es el
    btw-code de Exact, cuyo significado hay que confirmar (ver «Pendiente»). Test:
    `test_e2_un_tipo_que_el_proveedor_nunca_habia_traido`.
18. **No había cómo poner las cuentas propias** (bloqueante). Era
    real: con datos de verdad se rechazaba cada extracto del banco, y en Docker
    `config/empresa.yaml` está en la imagen. Ahora `bms-agent empresa ver|fijar`
    (`--cuenta`, que se repite, `--btw-id`, `--kvk`; con `admin` y en la
    auditoría). `docker/empresa.ps1` y su `.bat` la llaman. El rechazo dice cómo se
    arregla, y la guía (entorno-local §5 y uso-v1 «El primer día») lo explica.
    Test: `test_las_cuentas_propias_se_ponen_por_una_orden_y_el_extracto_entra`.
19. **La guía de uso solo daba órdenes `bms-agent`, que en Docker no existen**
    (mayor). Era real. Ahora `docker/orden.ps1` y su `.bat` corren cualquier orden
    en la caja `orden`: piden el token, lo pasan por el entorno y lo olvidan al
    acabar. entorno-local.md tiene «Las órdenes sueltas», y uso-v1.md dice al
    principio cómo se traduce cada orden. Lo de cada día está además en la consola
    (el 9). El test estático exige los dos scripts nuevos (`test_entorno_local.py`).
20. **En Docker la hoja del BTW no se podía sacar** (mayor). Era real. La página
    BTW de la consola tiene **Descargar la hoja**
    (`GET /api/v2/btw/AAAA-TN/hoja.csv`: los bytes exactos, cuyo sha256 es el
    de la hoja). Un `--salida` que no se puede escribir es una línea en castellano,
    no una traza; dentro del contenedor dice además que se descarga de la consola.
    `btw hoja` en una terminal escribe el texto ya limpio de controles. Tests:
    `test_la_hoja_del_btw_se_descarga_con_sus_bytes_y_su_sha256`,
    `test_una_salida_que_no_se_puede_escribir_es_una_linea_y_no_una_traza`.
21. **La verificación de un IBAN no tenía su último paso, ni el teléfono ni la
    cuenta por verificar** (mayor). Era real. `iban listar` va ahora por
    proveedor: el teléfono al que se llama, cada cuenta con su estado y la cuenta
    impresa en una factura y que todavía no está en el registro (F3)
    (`consultas.registro_de_cuentas`). La vista `proveedor N` dice lo mismo, y la
    consola también, en el bloque Cuentas. uso-v1.md añade el último paso: poner la
    cuenta en Exact y volver a importar los acreedores, porque hasta entonces F2
    la sigue bloqueando. Tests:
    `test_iban_listar_da_el_telefono_y_la_cuenta_impresa_que_f3_pide_verificar`,
    `test_iban_listar_por_la_cli`.
22. **Una verificación a otro teléfono decía «Hecho» y salía con 0** (menor). Era
    real. Ahora `Diferencia.no_vale` lo detecta, y la orden dice «Apuntada, pero la
    verificación NO VALE: …» con el porqué. La CLI sale con `SALIDA_SIN_EFECTO`
    (5), y la consola lo enseña como un error. Tests:
    `test_una_verificacion_a_otro_telefono_no_dice_hecho_ni_sale_con_cero`,
    `test_la_consola_dice_como_error_una_verificacion_que_no_vale`.
23. **Ninguna guía decía qué es F0 ni cómo se atesta** (menor). Era real. Ahora
    uso-v1.md «El primer día» explica qué es atestar, quién lo hace y cómo (el
    botón de la consola o `orden.bat iban atestar`). El botón existe ahora (el 9).
    Es un cambio de documentación; el de la consola tiene su test en el 9.
24. **Los trimestres de antes de empezar salían por presentar y con el plazo
    pasado** (menor). Era real. Se eligió documentarlo: uso-v1.md «El primer día»
    da el camino (`btw hoja`, `btw listo` y `btw anotar` con lo que dice el acuse).
    No se añadió un trimestre de inicio configurable: escondería sin firma un
    trimestre que de verdad estuviera sin presentar, y anotar deja la referencia
    del acuse y quién lo hizo. Test del camino:
    `test_un_trimestre_presentado_antes_de_empezar_se_anota_como_dice_la_guia`.
25. **Los errores y la ayuda de la CLI salían en inglés, y la descripción era de la
    fase 0** (menor). Era real. Ahora `argumentos.Parser` (los subcomandos heredan
    la clase) dice «uso: », «argumentos», «opciones» y «muestra esta ayuda y
    sale». Los errores de argparse se traducen por su forma, y uno que no se
    reconoce se queda como estaba. La descripción dice lo que hace la V1. El
    destino de las órdenes es `orden` (antes `command`), que es lo que se ve en un
    error. Tests: `test_los_errores_de_la_linea_de_comandos_son_en_castellano`
    (los cuatro ejemplos de la revisión), `test_la_ayuda_es_en_castellano_y_dice_lo_que_hace_la_v1`,
    `test_un_error_que_no_se_conoce_se_queda_como_estaba`.
26. **«None», «()» y «Ano» en la salida** (menor). Era real. Sin pasada, el aviso
    dice «todavía no se ha hecho ninguna pasada del día» (`cli._de_cuando`). Un
    aviso de la parte no dice «factura None». La lista de revisar del BTW da el id y
    el número, y el porqué, o «fuera de las cifras». Se escribe «Año» y «año» en lo
    que se ve (la CLI, el panel de la fase 0 y tres mensajes de error). Test:
    `test_la_cli_no_ensena_none_ni_parentesis_vacios_ni_ano`.
27. **En Docker las pistas decían `bms-agent serve` o `bms-agent importar`**
    (menor). Era real. `cli._como_se_hace` da la pista de Docker cuando la orden
    corre en un contenedor: en `demo crear`, en `usuario token` y en `ordenes` sin
    ninguna, dice `iniciar.bat -Demo`, la dirección de la consola, `buzon\po` e
    `importar.bat`. Test: `test_en_docker_las_pistas_son_las_de_docker`.
28. **Actualizar el programa perdía el buzón** (menor). Era real. entorno-local.md
    §12.5 dice ahora que se guarden aparte `docker\secretos` y `buzon` y se
    vuelvan a poner. Lo demás (la empresa, las personas, la política) está en la
    base. Es un cambio de documentación.
29. **Las preguntas no aceptaban «sí»** (menor). Era real. `Es-Si` (comun.ps1)
    acepta `si`, `sí` y `s`, en mayúsculas o no; la tilde se compara por su código,
    porque el `.ps1` es ASCII. `leer-facturas.ps1` y `restaurar.ps1` dicen «No has
    escrito si». Aquí no hay PowerShell, así que el test es estático (y repite la
    regla en Python): `test_las_preguntas_de_los_scripts_aceptan_si_con_tilde`.
30. **La ficha enseñaba identificadores internos, y un importe con punto de miles
    no se aceptaba** (menor). Era real. Cada campo tiene su etiqueta en castellano
    (`consultas.ETIQUETA_CAMPO`), con el identificador al pasar el ratón. Un
    importe escrito como lo enseña la consola (`2.902,79`) se acepta: el punto
    solo vale como separador de miles, en grupos de tres y con la coma decimal.
    Tests: el del 14 y `test_un_importe_se_escribe_como_lo_ensena_la_consola`.

### Tests que cambian, y por qué

- `test_reglas.py`: el catálogo del spec suma D6, I1 y K9, y la lista de las
  pegajosas suma K9 (hallazgos 8, 12 y 1).
- `test_hallazgos.py`: `SOLO_OBJECIONES` suma K9, que solo dice lo que falla.
- `test_pureza_reglas.py`: suma los escenarios de `test_revision_final`, para que
  D6, I1, E2 y K9 lean lo que declaran.
- `test_flujo_caja.py`: el abono de Van Dijk ya no es una entrada esperada; todo lo
  esperado de ese escenario es salida (hallazgo 2, desviación 3).
- `test_panel_busqueda.py`: la propiedad que compara el panel con la búsqueda solo
  suma lo que `vence()` (hallazgo 2).
- `test_auditoria.py::test_dos_bases_pueden_compartir_el_fichero_de_anclas`: cada
  base se declara en el fichero al crearla, como hacen ya `preparar` y `db init`.
  El test la creaba con `migrar` a secas (hallazgo 4).
- `test_serve_seguridad.py::test_el_origen_propio_y_el_declarado_si_reciben_cors`:
  mira la cabecera CORS en `/api/ejecucion`, porque `/api/datos` pide ahora un
  token (hallazgo 5). Que la pida y enmascare lo prueba el test del 5.
- `test_contrato_v2.py` y `test_equivalencia_legado.py`: la petición a `/api/datos`
  lleva el token de una persona con `consulta`, y sin él es un 401. El cuerpo se
  sigue comparando byte a byte con la foto (hallazgo 5).
- `test_entorno_local.py`: los scripts suman `empresa` y `orden`, y la pregunta de
  `leer-facturas.ps1` se comprueba con `Es-Si` (hallazgos 18, 19 y 29).
- `test_servicios.py::test_los_datos_se_comprueban_antes_de_hacer_nada`: `"2.900,50"`
  era uno de los importes que se rechazaban, y ahora se acepta (hallazgo 30,
  desviación 6). En su lugar se comprueban `"2.900"` y `"2,900.50"`, que no dicen
  si son miles o decimales.
- `test_servicios.py::test_la_cli_pasa_valores_que_empiezan_por_guion`: el error de
  argparse se espera en castellano («le falta su valor»; hallazgo 25).

### Desviaciones, y por qué

1. **K9 es una regla que el §7 no tiene.** Las órdenes ya no dejan anular algo
   pagado. Pero una importación de Exact trae los pagos como vienen, y puede
   traer uno de una factura anulada. Ese dinero no puede desaparecer en silencio
   de los totales.
2. **D6 es de B también en las ventas.** La revisión proponía R para las salientes.
   El §7 pone la familia D de B, y una venta con un desglose que no suma la
   cabecera declara en el BTW un IVA que no es el de la factura.
3. **Un abono, o un saldo del otro signo, nunca es un cobro ni un pago esperado**,
   y no vence. Cambia lo que el paso 7 esperaba de la caja: lo que se espera es
   deuda. Una factura pagada de más pasa a saldada, y lo que sobra lo dicen K2 o
   R2, no la caja.
4. **Las anclas de otra base sin la línea `nueva_base` ya no pasan** si la base no
   tiene ninguna ancla suya. Un fichero de anclas compartido desde antes de esta
   versión por una base sin anclas y otra con ellas da error en `db verificar`.
   Es el precio de que reescribir el primer evento no esconda nada. Una base con
   anclas suyas no cambia (el test de antes de la lista lo vigila).
5. **`/api/datos` pide un token.** El spec lo quiere idéntico byte a byte. Lo es
   el cuerpo; el acceso ya no es libre, porque daba los IBAN enteros a cualquiera.
6. **El importe se acepta con el punto de miles de la consola.** El paso 4
   (desviación 20) lo rechazaba por ambiguo, porque `2902.79` también entra.
   Con los dos separadores no lo es: `2.902,79`, con grupos de tres y coma
   decimal, solo puede ser dos mil novecientos. Esa forma completa se acepta,
   también con signo (`-1.234,56`). `2.902` o `1.000`, sin coma, se siguen
   rechazando: no se sabe si son miles o decimales.
7. **El destino de los subcomandos se llama `orden`, no `command`.** Nada lo leía,
   y es la palabra que sale en un error.

**La suite entera**: 2182 tests pasan y cinco se saltan, los de los contenedores,
que piden `BMS_PROBAR_DOCKER=1` (aquí no hay Docker). Al acabar el paso 13 pasaban
2120.

### Pendiente

Lo que la V1 todavía no puede hacer, y por qué:

- **E1 por tipo de IVA.** Para saber qué tipo se espera de un proveedor hace falta
  confirmar con el dueño o el asesor qué quiere decir cada btw-code de Exact (VH21,
  VERL, …) y en qué columna llega. Hasta entonces, E2 avisa del cambio entre una
  factura y las anteriores.
- **A4 (KvK) y A6 (VIES).** Son consultas a fuera: la consola no tiene red, y el
  Handelsregister completo es de pago. Quedan como dice validacion-facturas.md, en
  el alta y cada trimestre, fuera de la V1.
- **Los formatos de verdad.** Las ventas, los pagos y los acreedores de Exact, el
  planning de TRNSPRNT y el extracto del banco (qué banco, qué versión de CAMT,
  qué perfil de MT940 o de CSV) están hechos contra ejemplos sintéticos. El
  primer fichero de verdad puede no entrar: el rechazo dice la fila y el motivo, y
  se ajusta su mapeo en `config/importacion/`.
- **`config/btw.yaml` por confirmar con el asesor**: las rúbricas, la KOR, el
  verlegd y el resto del mapeo. Cada hoja lo dice.
- **Las decisiones del dueño que siguen abiertas.** Si C4 mira la fecha de la
  factura o el periodo de prestación (paso 11, desviación 8). Si una cuenta
  heredada es pagable antes de atestarla (`cuentas.solo_verificadas`). Y si
  prefiere un trimestre de inicio del BTW configurado, en vez de anotar a mano los
  de antes (hallazgo 24).
- **Lo que solo se puede probar en el ordenador del dueño.** Docker Desktop y
  Windows PowerShell 5.1: lo de los pasos anteriores, y ahora también `orden.bat`
  y `empresa.bat` con argumentos que empiezan por `--` y escribir «sí» en
  `Read-Host`. Y la primera lectura de verdad con su clave y la puerta de
  `reextraer --activar`, porque aquí no hay API ni facturas reales.
- **`Fuente.MAESTRO` solo se ve en el vencimiento.** Lo que el maestro completa
  en otros campos no se apunta como «Del maestro» (hallazgo 16): se apuntaría
  cuando se sepa qué copia de verdad cada importación.

---

## Paso 14

La instalación nativa de Windows, **sin Docker**, con el mismo aislamiento que el
entorno del paso 13. **No está en el §11 de la especificación: lo pidió el dueño**
(«lo quiero análogo sin depender de Docker»), con el diseño que se cerró con el
orquestador: un intérprete de Python por papel para que el cortafuegos de Windows los
distinga por su ruta, reglas del cortafuegos por programa, la clave de la API con
DPAPI, el código de solo lectura, la salida encendida solo durante una lectura y una
comprobación de aislamiento que falla cerrada. La variante de Docker (`docker/`,
docs/entorno-local.md) sigue igual: sus tests no cambian y su salida no pide la
credencial nueva. **2303 tests pasan** (eran 2182) y nueve se saltan: los cinco de los contenedores de Docker, que piden `BMS_PROBAR_DOCKER=1`, y los cuatro que ejecutan PowerShell, que piden `pwsh` o `BMS_PROBAR_PWSH=1` (aquí se corrieron así, con la imagen de PowerShell 7 por Docker y sin red, y pasan). Ninguno llama a la API ni sale de la máquina: los
destinos «de internet» de la comprobación son sockets locales.

No hay tabla ni migración nueva. Lo que se apunta (el resultado de la comprobación) va a
un fichero, `datos/aislamiento.json`, no a la base: lo escriben los cuatro programas, y
la salida no tiene por qué abrir la base.

### Qué se construyó

**`aislamiento.py` y `bms-agent comprobar-aislamiento --rol consola|lector|salida|orden`.**
La comprobación no se fía de la configuración: cada papel lo intenta con su propio
programa.

- `EXTERNOS`, la lista fija: `1.1.1.1:443`, `8.8.8.8:53` por TCP y por UDP (una consulta
  DNS de example.com, `consulta_dns`), `1.1.1.1:80` y `api.anthropic.com:443`. Por el
  proxy, el lector pide `api.anthropic.com:443` y los prohibidos
  (`PROHIBIDOS_POR_EL_PROXY`: `example.com:443`, `api.anthropic.com:80`, `1.1.1.1:443`,
  `api.anthropic.com.evil.example:443`), con y sin la credencial.
- Las pruebas (`probar_tcp`, `probar_dns_udp`, `pedir_tunel`, `se_puede_escribir`) corren a
  la vez, con plazos cortos (2 s; 12 s para la API por el proxy). `observar` junta lo visto
  y `evaluar` lo juzga, función pura: la consola, el lector y las órdenes no llegan a nada;
  la salida solo al 443 (no llegar es un aviso, no una fuga); el lector llega al proxy, por
  él la API dice 200, lo demás 403 y sin credencial 407 (cualquier 200 de más es grave); la
  consola y las órdenes, con `--proxy`, no pasan sin la credencial; el código (`app`, `lib`,
  `runtime/<papel>`) no se puede escribir y `datos` y `buzon` sí (si no, aviso). Un lector
  sin proxy no se da por bueno, y un informe sin pruebas tampoco.
- `guardar` junta los papeles en `datos/aislamiento.json` (escrito aparte y cambiado de
  nombre, con reintentos por Windows) con la fecha, el programa y la `sesion` (el sha256 de
  la credencial de la pasada, nunca la credencial). `problemas_de` es lo que pinta la banda
  (sin comprobar, FALLA con lo que falla, más de 90 días, fecha que no vale);
  `motivo_para_no_leer_de` es la puerta de una lectura (el lector y la salida, bien, de esta
  sesión y de hace menos de 60 minutos).
- En la instalación, cada papel solo se comprueba con su propio programa (si no, sale con
  2): probar el lector con el Python de la consola no diría nada del lector.

**`nativo.py`**: lo que el código sabe de la instalación.

- `detectar`: el intérprete está en `<raíz>/runtime/<papel>/python.exe` y la raíz tiene
  `instalacion.json` (versión 1, los puertos). Uno que no se entiende es un error
  (`InstalacionNoValida`), no un «no hay». Fuera (el desarrollo, Docker, los tests) no hay
  instalación y nada cambia.
- `exigir_lectura` (y `exigir_lectura_si_nativa`): la puerta de toda llamada a la API, en
  `cli._cliente_api` (extract, `coste --estimar`, que usa `count_tokens`, y reextraer) y en
  `serve.Agente._cliente`. Solo el programa del lector, por el `HTTPS_PROXY` de la pasada
  (`http://bms:CREDENCIAL@127.0.0.1:<puerto de la salida>`, `leer_proxy`) y con la
  comprobación de la salida y del lector de esa credencial. Si no, `LecturaNoAislada` y la
  CLI sale con 2 sin crear el cliente. No hay opción para saltársela.
- `clave_del_lector`, `huella_sesion`, `RUTAS_PTH` / `contenido_pth` (lo que lleva cada
  `python311._pth`) y las carpetas que se prueban (`carpetas_a_probar`).

**`secretos.py`**: la clave con DPAPI por ctypes (`CryptProtectData` /
`CryptUnprotectData` de crypt32 y `LocalFree`), ámbito del usuario, `CRYPTPROTECT_UI_FORBIDDEN`
y una entropía propia; el fichero lleva una cabecera (`BMS-DPAPI-1`) delante del blob y se
escribe aparte y se cambia de nombre. `guardar_clave`, `leer_clave` y `borrar_clave`; los
errores nunca llevan la clave. Fuera de Windows `DPAPI()` lanza `SinDPAPI` (un
`ClaveNoValida`): no se guarda de otra manera. `config.clave_api`, en la instalación, solo
acepta la de DPAPI y solo en el lector: ni `BMS_CLAVE_API_FICHERO` (un fichero de texto) ni
`ANTHROPIC_API_KEY`. `config.parece_una_clave` sale de la comprobación que ya había.

**`salida.py`**: una credencial opcional por pasada (`Proxy(clave=...)`,
`servir(clave=...)`, `bms-agent salida --clave-del-entorno`, que la lee de
`BMS_PROXY_CLAVE`, mínimo 16 caracteres). Sin ella, 407 con
`Proxy-Authenticate: Basic realm="bms"`, apuntado sin la cabecera. `credencial_valida` es
pura y compara en tiempo constante. La línea de arranque del registro dice si hay
credencial. Sin la opción (Docker), todo como antes.

**La CLI**: `comprobar-aislamiento` (`--rol`, `--proxy`, `--espera`, `--resultado`),
`clave guardar|comprobar|borrar` (`--fichero`; pide la clave con `getpass` y crea antes el
protector, para no hacerla escribir fuera de Windows) y `serve` en la instalación: solo con
el programa de la consola, `lectura=False` y la banda. `main` dice en una línea
`LecturaNoAislada` e `InstalacionNoValida`.

**La consola** (`serve.py`, `consola.py`): con `aislamiento` (lo que falla), una banda roja
«AISLAMIENTO SIN COMPROBAR O CON FALLOS: …» detrás de `<body>` (detrás de la de DATOS DE
PRUEBA si la hay), «SIN AISLAMIENTO» en el título y en la página local `/`. El texto viene
de un fichero que se puede escribir: va escapado. Se lee en cada página.

**`windows/`**: `comun.ps1` (lo compartido: buscar la instalación, el programa de cada
papel, `Orden-De` con `python -X utf8` y la consola en UTF-8, los procesos de un papel por
la ruta de su programa, la salida en segundo plano con su credencial por el entorno, la
tabla de reglas `Reglas-Del-Cortafuegos`, `Quitar-Reglas` por el prefijo, las carpetas del
buzón, el token oculto y `Es-Si`), y cada script con su `.bat`: `instalar`, `desinstalar`,
`iniciar` (`-Demo`), `parar`, `leer-facturas`, `importar` (`-Demo`), `copia`, `restaurar`,
`comprobar`, `clave`, `persona`, `empresa`, `orden` y `ver-salida`. `fijado.json` (el
Python embebible: versión, URL, sha256 y firmante), `requirements-windows.txt` y
`LEEME.txt`. Todo ASCII, sin Docker, para Windows PowerShell 5.1 y PowerShell 7.

- `instalar.ps1`: con tu usuario, se relanza elevado (la ventana de permiso) pasando tu SID;
  la parte de administrador comprueba el sha256 fijado y la firma Authenticode del
  embebible (Python Software Foundation), lo copia en `runtime\<papel>` con su `._pth` y sin
  `pythonw.exe`, busca cada rueda en PyPI **por su sha256**, la comprueba y la abre en
  `lib\`, copia `src\bms_agent`, `config` (sin `tarifas.yaml`, como Docker) y los scripts,
  compila, prueba que arranca, escribe `instalacion.json`, crea las doce reglas y pone los
  permisos con icacls (dueño, los administradores; la raíz sin herencia, leer y ejecutar
  para tu usuario; `datos` y `buzon`, modificar, solo tu usuario). Lo apunta en
  `instalacion.log` y, si falla, espera a que lo leas. Con tu usuario otra vez: los siete
  accesos del escritorio, la clave (si quieres) y `comprobar.ps1`.
- `leer-facturas.ps1`: credencial al azar, salida en 127.0.0.1, comprobación de la salida y
  del lector, y solo si salen bien contar, preguntar y leer; la salida se para en un
  `finally` y el `Fallar` va después. `iniciar.ps1`: la pasada del día, la comprobación de la
  consola y de las órdenes, la consola sin ventana y el navegador. `desinstalar.ps1`: quita
  exactamente las reglas del prefijo, el programa y los accesos; los datos solo con `SI` en
  mayúsculas.

**`scripts/fijar_windows.py`** (para quien mantiene el programa, con internet): rellena los
hashes PENDIENTES desde PyPI (la única rueda que vale para cp311 y win_amd64) y el del
embebible, y `--comprobar` dice lo que falta.

**Documentación**: `docs/instalacion-nativa.md` (para el dueño: qué es, lo que necesita,
instalar, la clave, la primera vez, arrancar y parar, el buzón, prueba y verdad, copias, lo
que prueba la comprobación, la tabla con Docker y el hueco dicho claro, el usuario aparte,
lo que cuesta, si algo no va, el mantenimiento, la lista de la primera vez y una parte para
quien mantiene el programa); enlaces en el README, docs/entorno-local.md y
docs/instalacion-windows.md. `.gitignore`: `/windows/paquetes/`.

### La puerta, test por test

Todo en `tests/test_instalacion_nativa.py`.

| Puerta | Tests |
| --- | --- |
| DPAPI con un protector falso | `test_la_clave_se_guarda_cifrada_y_se_lee_sin_ensenarla` (ni la clave ni `sk-ant-` en el fichero, la entropía), `test_una_clave_mala_no_se_guarda_ni_se_ensena`, `test_otro_usuario_u_otro_ordenador_no_la_descifra`, `test_lo_que_no_es_una_clave_guardada_se_rechaza`, `test_fuera_de_windows_no_hay_dpapi_y_se_dice`, `test_solo_el_lector_descifra_la_clave`, `test_en_la_instalacion_la_clave_nunca_esta_en_claro` (ni la variable del SDK ni un fichero de texto), `test_la_cli_guarda_comprueba_y_borra_sin_ensenar_la_clave`, `test_la_cli_fuera_de_windows_no_pide_la_clave` |
| La comprobación con sockets locales | Un puerto bloqueado (`test_una_consola_aislada_sale_bien_y_lo_apunta`, también un nombre que no resuelve), un destino que contesta (`test_un_papel_que_llega_a_internet_falla`, los tres papeles), un DNS que contesta por UDP, la salida de verdad con la API de mentira (`test_el_lector_solo_llega_al_proxy_y_por_el_solo_a_la_api`), un proxy que deja pasar otro destino (`test_un_proxy_que_deja_pasar_otro_destino_falla_cerrado`), uno sin credencial (`test_un_proxy_que_no_pide_la_credencial_falla_cerrado`), sin proxy o apagado (`test_un_lector_sin_proxy_no_se_da_por_bueno`), la consola sin credencial; puras: la salida solo por el 443, lo que contesta la API (200, 502, nada, 403, 407), la escritura del código y de los datos, la lista fija |
| Falla cerrada | `test_la_banda_dice_lo_que_falta_lo_que_falla_y_lo_viejo` (también un «correcto» que sus pruebas contradicen), `test_una_lectura_solo_con_la_comprobacion_de_esta_pasada`, `test_la_puerta_solo_deja_al_lector_de_una_pasada_comprobada` (otro papel, sin proxy, otro puerto, otra máquina, https, otro usuario, otra credencial; nunca la credencial en el mensaje), `test_sin_la_comprobacion_ninguna_orden_que_paga_crea_el_cliente` (`coste --estimar` y `extract`: sale con 2 y el cliente no se crea), `test_la_pasada_entera_comprobada_llega_a_la_api_con_la_clave_cifrada` (la salida de verdad con su credencial, `comprobar-aislamiento` de la salida y del lector por la CLI, y entonces el cliente se crea con la clave de DPAPI; con la credencial de otra pasada, no), `test_cada_papel_se_comprueba_con_su_propio_programa`, `test_un_instalacion_json_roto_no_se_toma_por_ninguno` |
| La banda de la consola | `test_la_consola_pinta_la_banda_roja_si_el_aislamiento_falla_o_falta` (escapada), `test_sin_problemas_o_fuera_de_la_instalacion_no_hay_banda`, `test_con_datos_de_prueba_la_banda_de_prueba_va_primero`, `test_la_consola_de_la_instalacion_no_lee_pdf_y_lleva_la_banda` |
| La credencial de la salida | `test_credencial_valida_es_pura`, `test_sin_la_credencial_el_proxy_contesta_407_y_lo_apunta_sin_ella`, `test_el_cliente_http_del_sdk_manda_la_credencial_de_https_proxy` (httpx2 de verdad), `test_la_salida_con_credencial_la_exige_en_el_entorno` |
| Nadie lanza procesos (AST) | `test_ningun_modulo_lanza_procesos` (sin lista de excepciones: ningún módulo lo necesita; ctypes solo en `secretos.py`, y solo crypt32 y kernel32 con sus tres funciones), y el vigilante probado con veinte formas de lanzar y con lo que no lanza |
| Los scripts, sin Windows | Cada uno con su `.bat`, ASCII, sin clave; ninguno usa Docker, ejecuta texto ni baja nada fuera de `Descargar-Verificado`, que comprueba el hash antes de usar lo bajado; el instalador no sigue sin los hashes fijados; las dependencias son las de Docker con sus hashes; las doce reglas con su prefijo, programa, sentido y acción (y los puertos de la salida cubren todo menos el 443); el desinstalador las quita por el prefijo y deja los datos sin `SI`; un Python por papel con su `._pth`; los permisos; el orden de `leer-facturas` (comprobar antes de pagar, parar la salida siempre, sin parámetros para saltárselo); `iniciar`, `comprobar`, `importar` (las mismas carpetas que Docker); el token y la clave nunca en la línea de órdenes; nada de PowerShell 7 |
| Con PowerShell de verdad | Con `BMS_PROBAR_PWSH=1` y la imagen de PowerShell 7 por Docker (sin red), **aquí pasan los cuatro**: cada `.ps1` pasa el analizador; `Leer-Requisitos` lee los hashes como pip y para con los PENDIENTES; `Escribir-Pth` escribe los bytes de `nativo.contenido_pth()`; `Descargar-Verificado` acepta el hash bueno, borra y para con el malo y no baja por http; la tabla de reglas, las comillas de `Start-Process`, `Es-Si`, la credencial y las carpetas del buzón |
| La variante de Docker | `test_la_variante_de_docker_no_cambia` y todos los de los pasos 13 y de la revisión final, sin cambios |
| La suite entera | 2303 pasan y 9 se saltan (5 de Docker y 4 de PowerShell); con `BMS_PROBAR_PWSH=1` los 125 de `test_instalacion_nativa.py` pasan |

### Lo que solo se puede comprobar en el ordenador del dueño

Aquí no hay Windows. Queda por mirar allí, la primera vez y con datos de prueba (la lista
para el dueño está en docs/instalacion-nativa.md, apartado 16): que Windows Defender
Firewall aplica las reglas por programa y no filtra 127.0.0.1 (la consola contesta al
navegador y el lector llega a la salida); `New-NetFirewallRule`, icacls y la ventana de
permiso en Windows PowerShell 5.1; DPAPI de verdad (y que `getpass` deja pegar con el
botón derecho); la firma Authenticode del embebible; `Start-Process` sin ventana con sus
redirecciones; los accesos del escritorio; y una lectura de verdad con la clave.
**`comprobar.bat` tiene que salir todo en verde antes de usar datos de verdad.**

### Desviaciones, y por qué

1. **Sin pip.** El Python embebible no trae pip, y ponerlo sería bajar y ejecutar otra cosa
   sin fijar (get-pip.py) o fijar una rueda de pip cuyo hash no se podía sacar aquí. Una
   rueda es un zip: el instalador baja la que tiene el sha256 fijado, la comprueba y la abre
   en `lib\`, que es lo que haría `pip --target` con estas ruedas (ninguna trae `.data`; si
   una lo trajera, para). El fichero sigue en el formato de pip, y con pip se instalaría
   igual.
2. **Los hashes que faltan.** Sin red no se pudieron sacar los sha256 de las ruedas de
   Windows (`jiter`, `pydantic_core`, `PyYAML`, cp311 win_amd64), de `tzdata` ni del
   embebible. Van como PENDIENTE y **el instalador no sigue sin ellos** (ni sin el del
   embebible): nada se salta la comprobación. Los fija `scripts/fijar_windows.py` con
   internet. Las trece ruedas py3-none-any llevan el hash de `docker/requirements.txt`, que
   es el mismo fichero en cualquier plataforma (comprobado con las ruedas que se bajaron en
   el paso 13 para las dos plataformas: mismo sha256).
3. **Python 3.11.9.** Es la misma versión menor que el desarrollo y Docker, y la última 3.11
   con binarios para Windows (desde la 3.11.10 solo hay código fuente). No tiene las
   correcciones de seguridad que sí tiene la 3.11.17 de la imagen de Docker; se dice en la
   guía. Pasar a 3.13 o 3.14 es un paso propio: la suite tiene que correr antes en esa
   versión.
4. **Una credencial por pasada en el proxy** (no estaba en el diseño). Windows no filtra
   127.0.0.1, así que durante una lectura cualquier programa del ordenador, también la
   consola, llegaría al proxy y podría mandar datos a la API de Anthropic con una clave
   ajena: lo que en Docker impide la red separada (paso 13, desviación 2). Con la
   credencial, la salida contesta 407 a quien no la trae. Un proceso del mismo usuario
   podría leerla del entorno del lector; se dice.
5. **La comprobación atada a la pasada, y la puerta en el lector.** El script no basta: el
   propio lector mira, antes de crear el cliente, que la comprobación del lector y de la
   salida sea de la credencial de su `HTTPS_PROXY` y de hace menos de una hora. La banda de
   la consola, en cambio, da por vieja una comprobación de más de 90 días.
6. **Las reglas de la salida.** En Windows un bloqueo gana siempre a un permiso, así que
   «bloquear todo y permitir el 443» lo bloquearía todo: van el permiso del TCP 443 y los
   bloqueos del TCP 1-442 y 444-65535, del UDP, del ICMPv4 y del ICMPv6 (un usuario sin
   privilegios no abre otros protocolos).
7. **Más de lo pedido**: la comprobación prueba también la escritura (el código, y la
   carpeta del propio intérprete, donde un DLL dejado se cargaría al arrancar); el
   instalador quita `pythonw.exe` (otro programa sin reglas), comprueba la firma
   Authenticode además del hash y desbloquea lo copiado; `iniciar` no arranca si el puerto
   8765 lo tiene otro programa (la consola de Docker), porque el navegador acabaría en esa.
8. **`datos` y `buzon` con «modificar»**, como en el diseño. Quitarles el permiso de
   ejecutar no cerraría el hueco de las reglas por programa: la carpeta temporal del
   usuario sí deja ejecutar.
9. **Cinco scripts más** que la lista (`clave`, `persona`, `empresa`, `orden` y
   `ver-salida`), los mismos que tiene Docker: sin ellos no hay primer token, ni empresa,
   ni órdenes sueltas, ni forma de mirar lo que ha salido.
10. **La elevación la hace `instalar.ps1`, no el `.bat`**: el script se relanza elevado con
    tu SID, y los accesos del escritorio y la clave se hacen después con tu usuario. Si la
    ventana de permiso la firma otra cuenta de administrador, los permisos y la clave siguen
    siendo de tu usuario y no de esa cuenta.
11. **La clave con DPAPI la descifra cualquier programa del mismo usuario**; el código solo
    lo hace en el lector. Para separarla de verdad está el usuario de Windows aparte
    (documentado, opcional). La entropía es una constante del código: no protege de quien
    lee el código, sí de quien descifra a ciegas los blobs del usuario.
12. **El mensaje de la consola que no lee PDF** dice ahora `leer-facturas.bat` «en Docker y
    en la instalación nativa» (decía `leer-facturas.ps1` y solo Docker). Ningún test lo
    miraba.
13. **El DNS no se prueba.** En Windows lo resuelve un servicio del sistema, no el
    programa: un nombre se resuelve siempre y la prueba solo daría ruido. Se dice en la guía
    como parte del hueco.
14. **AppContainer no se hizo**: necesita un lanzador propio (CreateProcess con atributos de
    capacidad), que además es justo lo que el test prohíbe en el código. La guía lo nombra,
    con la variante de Docker, como lo más fuerte.

**Tests existentes cambiados, y por qué** (los dos en `test_alcance_v1.py`):
`test_no_hay_credenciales_ni_claves_de_banco` admite `BMS_PROXY_CLAVE` (la credencial de una
pasada para el proxy) y `HTTPS_PROXY` (el proxy del lector, que la puerta comprueba);
ninguna es de un banco ni la clave de la API. `test_ningun_modulo_habla_con_la_red_salvo_la_extraccion`
deja a `bms_agent.aislamiento` importar `socket` (y comprueba sus destinos fijos): la
comprobación abre conexiones a propósito, para ver que no llegan.

### Lo que deben saber los pasos siguientes

- **Antes de dar la instalación al dueño**: `python scripts/fijar_windows.py` con internet,
  comprobar la firma de Sigstore del embebible (docs/instalacion-nativa.md, apartado 17) y
  subir `windows/fijado.json` y `windows/requirements-windows.txt`. Hasta entonces el
  instalador para al principio y lo dice.
- **Un módulo que lance un proceso** hace fallar `test_ningun_modulo_lanza_procesos`. Si de
  verdad hiciera falta, va en `PUEDEN_LANZAR` con su porqué, y es un hueco más de la
  instalación nativa que la guía tiene que decir.
- **Una llamada nueva a la API** pasa por `cli._cliente_api` (o llama a
  `nativo.exigir_lectura_si_nativa`): si no, en la instalación nativa se saltaría la puerta.
- **Una variable de entorno nueva** va en la lista de `test_alcance_v1.py` (ahora con
  `BMS_PROXY_CLAVE` y `HTTPS_PROXY`).
- **Una dependencia nueva** va en `docker/requirements.txt` y en
  `windows/requirements-windows.txt` (con el hash de su rueda de Windows); el test exige
  las mismas versiones.
- **Un tipo nuevo de importación** es una carpeta en `docker/importar.ps1` y en
  `Carpetas-Del-Buzon` de `windows/comun.ps1`: el test exige que sean iguales.
- **Cambiar de versión de Python** es `fijado.json`, `nativo.RUTAS_PTH` (`python3XY.zip`),
  `Escribir-Pth` (`python3XY._pth`) y los tests, con la suite pasando antes en esa versión.
- **Un destino nuevo para la salida** es un `--permitir` en `Arrancar-Salida`
  (`windows/comun.ps1`) y en `docker-compose.yml`, y los tests estáticos de los dos.
- **Cambiar de versión de Python** también es `nativo.FICHERO_PTH` (`python3XY._pth`), que
  `detectar` usa para reconocer un intérprete de la instalación sin `instalacion.json`.

### Correcciones de la revisión

Diecinueve hallazgos, con tres repetidos (el 8 es el 2, el 16 es el 15 y el 18 es el 3).
Todos se reprodujeron o se comprobaron contra el código y todos eran reales; tres no se
pueden reproducir aquí porque solo pasan en Windows (el 9, el 12 y el 14) y se corrigen
igual, con su test estático. Cada corrección de Python tiene un test que falla con el
código de antes y pasa con el de ahora (comprobado volviendo `src/` a `02325b6`: fallan
quince), y los tests estáticos nuevos de los scripts fallan con los `windows/` de
`02325b6` (fallan diez). **2328 tests pasan** (eran 2303) y nueve se saltan, los mismos
de antes (cinco de Docker y cuatro de PowerShell: aquí no hay `pwsh` ni la imagen, así
que esta vez los `.ps1` cambiados **no** han pasado el analizador; se mira con
`BMS_PROBAR_PWSH=1` antes de dárselo al dueño).

1. **La comprobación fallaba abierta por el proxy** (mayor). Un «no contesta» en un
   destino prohibido, o sin la credencial, contaba como un no, y esas pruebas tenían 2 s
   mientras la de la API tenía 12. Una salida mal puesta (con `--permitir` de más o sin
   `--clave-del-entorno`) conecta con el destino antes de contestar: con una conexión
   lenta su 200 llegaba tarde y el lector salía BIEN. Ahora **solo un no explícito es un
   no**: un destino prohibido tiene que recibir un 4xx (`aislamiento.es_negativa`; un 502
   o un 503 dicen que estaba permitido) y sin la credencial un 407; `None` es «no
   contesta: no se ha podido comprobar», grave. Todas las pruebas por el proxy tienen el
   plazo de la API (`espera_api`). Si el lector no llega al proxy, las de túnel no se
   juzgan (ya falla «llegar al proxy»). Tests:
   `test_un_proxy_lento_que_deja_pasar_de_mas_no_se_da_por_bueno` (la salida de verdad
   con la conexión al destino un segundo más lenta que el plazo corto) y
   `test_por_el_proxy_solo_un_no_explicito_es_un_no` (puro: 403, 400, 405, 407, nada,
   200, 502, 503).
2. **No se podía volver a instalar donde se desinstaló o donde falló un intento** (mayor;
   el 8 es el mismo). `Validar-Raiz` rechazaba toda carpeta sin `instalacion.json` que no
   estuviera vacía. Ahora acepta una carpeta con solo lo que deja bms-agent
   (`$DeLaInstalacion`: `instalacion.json`, `instalacion.log`, `descargas`, `runtime`,
   `lib`, `app`, `windows`, `datos`, `buzon`) y rechaza la que tiene algo más o un enlace
   (reparse point). Además `Leer-Fijado` y `Leer-Requisitos` se miran antes de elevar y
   antes de crear la carpeta: sin los hashes fijados ya no queda una carpeta a medias.
   Tests: `test_se_puede_volver_a_instalar_donde_se_desinstalo_o_fallo` (lo que crea el
   instalador y lo que deja `desinstalar`, sacado de los scripts, está en la lista) y
   `test_sin_los_hashes_fijados_no_se_crea_la_carpeta`.
3. **Sin `instalacion.json`, las puertas se apagaban** (mayor; el 18 es el mismo).
   `detectar` devolvía `None` también para `runtime\lector\python.exe`. Ahora un intérprete
   en `runtime\<papel>` con su `python311._pth` (`nativo.FICHERO_PTH`) y sin
   `instalacion.json` es `InstalacionNoValida`: `coste`, `extract` y `serve` salen con 2.
   Y `carpetas_a_probar` prueba también la raíz (`raiz`, donde está `instalacion.json`) y
   `windows`, que no se tienen que poder escribir. Tests:
   `test_un_interprete_de_la_instalacion_sin_instalacion_json_no_apaga_las_puertas` y
   `test_el_codigo_no_se_puede_escribir_y_los_datos_si` (cambiado: el conjunto de
   carpetas lleva ahora `raiz` y `windows`, y una raíz o unos scripts que se pueden
   escribir fallan).
4. **`clave comprobar --fichero` miraba la de la instalación** (menor). Ahora
   `clave_del_lector(instalacion, fichero=ruta)`: el fichero pedido, con la misma regla
   del lector. Test: `test_en_la_instalacion_clave_comprobar_mira_el_fichero_pedido`.
5. **El test del proxy no usaba el cliente del SDK** (menor). No era un fallo del código
   (el SDK manda la credencial), sino de cobertura. Test nuevo:
   `test_el_sdk_de_la_api_manda_la_credencial_de_https_proxy`, con
   `anthropic.Anthropic(...).models.list()` contra la salida de verdad: con la credencial
   pasa (y el TLS falla contra el eco local), con otra, 407.
6. **La raíz nueva era de todos hasta el último paso** (mayor). Bajo `C:\` heredaba
   «modificar» para cada usuario, y el instalador comprobaba, copiaba y ejecutaba como
   administrador lo de una carpeta que cualquiera podía cambiar. Ahora `Cerrar-Raiz` va
   justo después de crear la carpeta y antes de `Start-Transcript`, de bajar nada y de
   ejecutar nada: dueño los administradores, sin herencia, SYSTEM y administradores con
   control total y tu usuario solo leer y ejecutar; quita con `/remove:g` todo permiso
   que no sea de esos tres (`/inheritance:r` deja los puestos a mano, como «Todos:
   control total») y para si queda alguno; rechaza enlaces; y lo que ya había del
   programa pasa a heredar de la raíz (`/reset`), salvo `datos` y `buzon`, que tienen los
   suyos. `descargas` está dentro de la raíz ya cerrada. Todo va dentro del `try`: un
   fallo al cerrar se dice y espera. Test:
   `test_la_raiz_se_cierra_antes_de_bajar_copiar_o_ejecutar_nada`.
7. **«El código de bms-agent no arranca ningún programa» no valía para las
   dependencias** (menor). Comprobado en el `platform.py` de 3.11: en Windows
   `platform.system()` llama a `win32_ver()`, que ejecuta `ver` con `shell=True` (y con
   él `%COMSPEC%`); el SDK lo llama para su cabecera `X-Stainless-OS`. Además de corregir
   la guía, ahora **`cli.main` pone, en la instalación, `nativo.prohibir_procesos`**: un
   gancho de auditoría (`sys.addaudithook`, que no se quita) que contesta
   `PermissionError` a `subprocess.Popen`, `os.system`, `os.startfile`, `os.exec*`,
   `os.spawn*`, `os.posix_spawn`, `os.fork*`, `pty.spawn`, `_winapi.CreateProcess` y
   `webbrowser.open`. `platform` lo toma como «no hay `ver`» y saca la versión de
   `sys.getwindowsversion`. Mira el intérprete de verdad (`detectar()`), no
   `instalacion_actual`, que los tests sustituyen: en los tests no se pone. Tests:
   `test_en_la_instalacion_ni_las_dependencias_arrancan_programas` (en otro proceso, con
   un `ver` de mentira en el PATH que deja una marca: sin el gancho corre, con él no) y
   `test_el_gancho_conoce_cada_forma_de_lanzar_de_python`.
   `test_ningun_modulo_lanza_procesos` cambia: deja en `nativo.py` exactamente los
   nombres de `SUCESOS_DE_PROCESO`, que son nombres de sucesos y no llamadas.
8. Es el 2.
9. **`Enabled -ne $true` con el perfil del cortafuegos** (mayor, sin Windows para
   reproducirlo). `Get-NetFirewallProfile` da `Enabled` como `GpoBoolean`; ahora se
   compara como texto (`@("True", "1") -notcontains ("" + $_.Enabled)`) en `instalar` y
   en `comprobar`. Test: `test_el_cortafuegos_se_compara_como_texto` (y ningún script
   compara `Enabled` con `$true`). **Se mira en el primer Windows.**
10. **127.0.0.1 no se filtra para nadie** (mayor, de documentación). La guía, apartado
    11, lo dice ahora junto al hueco de otro programa y del DNS, con una fila en la
    tabla, y `comprobar.ps1` (punto 4) enseña como aviso los programas que escuchan en
    127.0.0.1 o ::1 y no son de bms-agent. Es la desviación 15, abajo.
11. **El desinstalador se elevaba desde una copia en `%TEMP%`** (menor). Ahora se eleva
    `$PSCommandPath`, en su sitio (windows\ es de los administradores), sin copia.
    PowerShell lee el script entero antes de empezar: que la carpeta se borre mientras
    corre da igual. Ningún script usa ya `$env:TEMP`. Test:
    `test_el_desinstalador_se_eleva_en_su_sitio_y_sale_de_la_carpeta`.
12. **La carpeta actual de la ventana no dejaba borrar windows\** (menor, sin Windows
    para reproducirlo). `desinstalar.bat` hace `cd /d "%SystemRoot%"` en la misma línea,
    antes de PowerShell, y el script empieza con `Set-Location` a `%SystemRoot%`. Si con
    `SI` aún queda la carpeta, lo dice en amarillo en vez de «Quitado, también tus
    datos». Mismo test.
13. **Python guardaba lo que decía por la tubería** (menor). Comprobado con el Python del
    entorno: con la salida por una tubería no hay bufer de línea. Ahora los tres
    lanzadores (`Orden-De`, `Orden-Directa`, `Arrancar-En-Segundo-Plano`) usan
    `$OpcionesPython = @("-u", "-X", "utf8")`. Test: `test_cada_python_corre_sin_bufer`;
    `test_comprobar_prueba_cada_papel_con_su_programa` cambia la línea que espera.
14. **La cadena de certificados de la API, dentro del lector sin red** (menor, plausible y
    sin Windows para reproducirlo). `comun.ps1` tiene `Preparar-Certificados`: una
    petición HEAD a `https://api.anthropic.com/` desde PowerShell (que sí tiene red), sin
    guardar nada, para que Windows baje y guarde la cadena; solo un fallo de TLS da un
    aviso. Va en `comprobar` y en `leer-facturas`, antes de comprobar el lector (y el
    instalador termina con `comprobar`). La comprobación del lector sigue sin hacer un
    TLS por el túnel: el módulo solo manda el CONNECT. Test:
    `test_windows_prepara_la_cadena_de_la_api_antes_de_comprobar_el_lector`.
15. **La salida seguía encendida si se cerraba la ventana con la X** (menor; el 16 es el
    mismo). `bms-agent salida --max-segundos` (`salida.servir(vida=...)`): se para sola
    al cumplir su plazo. `Arrancar-Salida` lo exige: 3 horas para una lectura
    (`$VidaSalidaLectura`, un lote grande tarda) y 10 minutos para `comprobar`
    (`$VidaSalidaComprobacion`). `iniciar.ps1` para una salida que se quedó encendida si
    no hay un lector leyendo. La guía dice la excepción. Tests:
    `test_la_salida_se_para_sola_al_cumplir_su_vida` y
    `test_la_salida_se_apaga_sola_si_nadie_la_para`.
16. Es el 15.
17. **`comprobar.bat` salía en verde con la clave en MAL o sin leer el cortafuegos**
    (menor). Ahora `$todoBien = $cortafuegosBien -and $claveBien`, y un cortafuegos que
    no se puede leer cuenta como MAL (no se sabe si está encendido ni si están sus
    reglas). Una clave que todavía no se ha guardado sigue siendo un aviso: hay usos sin
    lectura. Test: `test_comprobar_solo_sale_en_verde_con_el_cortafuegos_y_la_clave`.
18. Es el 3.
19. **La tabla de Docker y nativa no decía lo de 127.0.0.1 ni lo del buzón** (menor, de
    documentación). Dos filas nuevas en el apartado 11 y en el hueco; son las
    desviaciones 15 y 16.

**Desviaciones nuevas, y por qué** (siguen a las catorce de arriba):

15. **127.0.0.1 sin filtrar, también para la consola, el lector y las órdenes.** El
    cortafuegos de Windows no filtra el tráfico local, así que cualquier programa del
    ordenador que escuche en 127.0.0.1 y reenvíe a internet (un proxy, el agente de una
    VPN o de un antivirus, un túnel, el reenvío de WSL2) es una salida que las reglas no
    paran. En Docker las redes internas no llegan al ordenador. No hay forma de cerrarlo
    con reglas por programa; se dice, `comprobar.bat` lo enseña como aviso, y para quien
    tenga programas así están el usuario aparte y Docker.
16. **El buzón se puede cambiar desde los cuatro programas.** En Docker el lector y las
    órdenes lo montan de solo lectura; aquí los permisos de Windows son por usuario y los
    cuatro corren con el tuyo. `importar.ps1` mueve los ficheros con PowerShell, no con el
    programa, pero eso no impide que un programa comprometido los cambie. Lo que los
    protege es la copia semanal.
17. **Un gancho de auditoría contra los procesos** (no estaba en el diseño): ver el
    hallazgo 7. Es una capa más, no un muro: código nativo con `ctypes` lo salta.

## Paso 14b

El Python de la instalación nativa, **fijado y con las correcciones de seguridad**. El paso
14 pasó su puerta, pero el instalador no podía correr: `windows/fijado.json` tenía vacío el
sha256 de `python-3.11.9-embed-amd64.zip` y `windows/requirements-windows.txt` llevaba como
PENDIENTE los de `jiter`, `pydantic_core`, `PyYAML` y `tzdata`; el instalador, con razón, no
baja nada sin fijar, y la primera instalación del dueño se paraba en el primer paso.
Además, la 3.11.9 es la última 3.11 con binarios para Windows y no tiene las correcciones
de seguridad de después. **Lo decidió el orquestador**: el Python de la instalación nativa
pasa a ser el paquete «python» de nuget.org (lo publica la Python Software Foundation, y
python.org lista los paquetes de nuget.org entre sus distribuciones oficiales para
Windows), versión **3.13.16**, la última 3.13 de nuget.org. Docker se queda con su imagen
3.11 (`docker/` no cambia). Desde aquí python.org no se puede descargar (la pasarela
contesta 403), y nuget.org y PyPI sí: todo lo fijado se bajó y se miró de verdad.

**La suite entera pasa en las dos versiones**: en 3.11 (`.venv`, 3.11.17) **2354 pasan y 12
se saltan**, y en 3.13 (un entorno nuevo con `/usr/bin/python3.13`, 3.13.16, en el
scratchpad) **2354 pasan y 12 se saltan**, sin ningún aviso (eran 2328 y 9 al acabar el paso
14). Los doce son los cinco de los contenedores de Docker (`BMS_PROBAR_DOCKER=1`), los seis
de PowerShell (`pwsh`) y el de lo bajado de verdad (`BMS_PAQUETES_WINDOWS`). Con `pwsh` en
el PATH y lo bajado, los 179 de `tests/test_instalacion_nativa.py` pasan, en 3.11 y en 3.13. No hizo
falta cambiar nada del código de `src/` para 3.13; en los tests, siete conexiones de
sqlite3 que no se cerraban (3.13 avisa de ellas) ahora se cierran.

No hay tabla ni migración nueva.

### Qué se construyó

**`windows/fijado.json`**: el paquete de nuget.org entero. `version` 3.13.16, `origen`
«nuget.org: python, Python Software Foundation», `fichero` `python.3.13.16.nupkg`, `url`
`https://api.nuget.org/v3-flatcontainer/python/3.13.16/python.3.13.16.nupkg`, `sha256`
`95fad176338f1d6a799e45946488063f4aa61764e6cff2f132ddeffbf7a04c34` (calculado aquí de lo
bajado), `sha512` `TGEhuRTp…2s376w==` (el `packageHash` que publica nuget.org, en base64),
`catalogo` (la entrada del catálogo de nuget.org de esa versión, a la que se llega por el
índice de registro `registration5-gz-semver2`) y `firmante`.

**`windows/requirements-windows.txt`**: las diecisiete dependencias, todas con el sha256
que publica PyPI (`https://pypi.org/pypi/NOMBRE/VERSION/json`) de su rueda para
cp313-win_amd64 o py3-none-any, **las mismas versiones que `docker/requirements.txt`**
(ninguna hubo que subirla: todas tienen rueda cp313 win_amd64). Las tres binarias son
`jiter-0.17.0-cp313-cp313-win_amd64.whl`, `pydantic_core-2.50.1-cp313-cp313-win_amd64.whl` y
`pyyaml-6.0.3-cp313-cp313-win_amd64.whl`; `tzdata` es `tzdata-2025.2-py2.py3-none-any.whl`;
las trece py3-none-any tienen el hash de Docker. Ninguna PENDIENTE.

**`scripts/fijar_windows.py`**, reescrito: lo rellena todo desde NuGet y PyPI.

- `python scripts/fijar_windows.py` rellena lo que falte; `--rehacer` lo vuelve a sacar
  todo; `--python 3.13.X` cambia de versión (y vuelve a sacar las ruedas).
- El Python: el índice de registro de nuget.org → la entrada de la versión → su catálogo
  (`packageHash`, `packageHashAlgorithm`, `packageSize`, `authors`); baja el paquete de
  `v3-flatcontainer`, calcula el sha256 y el SHA-512 y **los cruza**
  (`cruzar_con_el_catalogo`: mismo id, versión, autor la Python Software Foundation, SHA-512
  y tamaño). Mira además que el paquete sea uno que el instalador sabe abrir
  (`revisar_paquete`: el nuspec, y que con lo que se saca para cada papel quede un solo
  programa, la DLL de esa versión y lo necesario). Si algo no cuadra, para.
- Las ruedas: `elegir_rueda(meta, nombre, menor)`, la única que vale para Windows x64 y
  CPython 3.13 (`vale_para_windows`: cp313 o abi3 hasta cp313 con win_amd64, o py3/py313
  con none-any; ni cp313t, ni py2 sola, ni las retiradas). `escribir_requisitos` rehace las
  líneas de las dependencias pedidas (quita sus hashes viejos o el PENDIENTE).
- **`--comprobar`, sin red**: cada dependencia con su sha256, las mismas que Docker (más
  tzdata) con las mismas versiones, y el Python entero (origen, URL y fichero de nuget.org,
  sha256, el SHA-512 en base64 de 64 bytes, la entrada del catálogo, el firmante, y la
  versión menor de `nativo.VERSION_PYTHON`). Sale con 0 («Todo fijado.») o con 1 y la
  lista. Con `--paquetes CARPETA` comprueba además lo ya bajado (los hashes del paquete y
  que cada dependencia tenga su rueda). Los tests lo usan.

**`nativo.py`**: `VERSION_PYTHON = (3, 13)`, `DLL_PYTHON = "python313.dll"`,
`FICHERO_PTH = "python313._pth"`, `RUTAS_PTH = ("Lib", "DLLs", r"..\..\lib", r"..\..\app\src")`,
`CARPETA_DEL_PAQUETE = "tools/"`, `FUERA_DEL_RUNTIME` (`pythonw.exe`, `include/`, `libs/`,
`Lib/site-packages/`, `Lib/ensurepip/`, `Lib/venv/`), `NECESARIOS_DEL_RUNTIME` y
`destino_en_runtime(entrada)`, pura: dónde va una entrada del paquete dentro de
`runtime\<papel>` o `None`, sin distinguir mayúsculas, y `PaqueteNoValido` con una ruta con
`..`, `.`, `\`, `:`, vacía o absoluta. `detectar` reconoce un intérprete de la instalación
por cualquier `python3*._pth` (`_tiene_pth`), no solo el de esta versión.

**`windows/comun.ps1`**: las mismas constantes (`$DllPython`, `$FicheroPth`, `$RutasPth`,
`$CarpetaDelPaquete`, `$FueraDelRuntime`, `$NecesariosDelRuntime`); un test exige que sean
iguales a las de `nativo.py`.

**`windows/instalar.ps1`**:

- `Leer-Fijado` solo acepta una URL de `https://api.nuget.org/v3-flatcontainer/python/`.
- `Abrir-Python`: el paquete se abre con .NET (`ZipFile.OpenRead`), entrada a entrada, con
  `Destino-En-Runtime` (lo mismo que `nativo.destino_en_runtime`), sin salirse de la carpeta
  (la ruta completa tiene que empezar por la carpeta) y con `ExtractToFile`. No con
  `Expand-Archive`: en Windows PowerShell 5.1 solo abre `.zip`, abre todo (también lo que
  no va) y no hay que fiarse de cómo trata los corchetes de `[Content_Types].xml`, que en
  PowerShell son comodines.
- `Comprobar-Runtime`: en la carpeta, un solo programa (`.exe`, `.com`, `.scr`), y es
  `python.exe`; y está lo necesario (`python313.dll`, `Lib\os.py`, `_socket`, `_sqlite3`,
  `_ssl`). Se mira al abrir el paquete y otra vez en cada `runtime\<papel>` después de
  copiar y de escribir el `._pth`.
- `Comprobar-Firma` en `python.exe` y `python313.dll`, y ahora compara el nombre entero del
  firmante (el CN, `GetNameInfo(SimpleName)`, con `-cne`), no un trozo del texto del
  certificado.
- `Escribir-Pth` escribe `$RutasPth` en `$FicheroPth` (lo mismo que `nativo.contenido_pth`).
- El paso 5 compila la biblioteca de los cuatro papeles (`compileall
  --invalidation-mode checked-hash`) y la prueba de arranque exige `sys.flags.isolated == 1`,
  `sys.flags.no_site == 1`, sin `site` en `sys.modules` y la versión de `fijado.json`.

**La suite en 3.13.** Un entorno nuevo en el scratchpad con `/usr/bin/python3.13` (3.13.16,
SQLite 3.45.1), las mismas versiones fijadas (las ruedas cp313 de Linux de `jiter`,
`pydantic_core` y `PyYAML`) y pytest 9.1.1, el paquete instalado con `pip install --no-deps
-e .`, y la suite entera. Pasó a la primera. Lo único que dijo 3.13 fueron siete
`ResourceWarning: unclosed database`: desde 3.13, `sqlite3` avisa de cada conexión que se
recoge sin cerrar. Con un plugin de pytest de diagnóstico (en el scratchpad, no en el
repositorio) que apunta dónde se abre cada conexión que se recoge sin cerrar, las siete
eran de tests (`with sqlite3.connect(...) as conn:`, que no cierra la conexión: solo
confirma la transacción), en `test_demo.py`, `test_entorno_local.py` y
`test_revision_final.py`, y ninguna del código. Se cierran con `closing`; la suite en 3.13
ya no avisa de nada. Los tiempos son los de 3.11 (unos 400 s la suite entera); ningún
límite de tiempo se tocó.

**Documentación**: `docs/instalacion-nativa.md` (apartado 3: de dónde viene el Python y por
qué; 11: el `ver` de `platform`; 14: la tabla ya no manda pedir hashes, y dice qué hacer si
lo bajado no es lo fijado, si la red no deja bajar, o si el paquete no es el esperado; 17:
lo que se instala, cómo se fija y se cruza, y por qué 3.13 de nuget.org).

### Lo que se miró aquí, bajando de verdad

- **El paquete**: 14.817.881 bytes; su SHA-512 en base64 es exactamente el `packageHash` del
  catálogo de nuget.org (`packageHashAlgorithm` SHA512, el mismo `packageSize`), y su
  nuspec dice `id` python, `version` 3.13.16 y `authors` Python Software Foundation (con el
  commit `cbc944f` de CPython). Es un zip de 1338 entradas: lo de NuGet (`python.nuspec`,
  `.signature.p7s`, `build/native/python.props`, `[Content_Types].xml`…) y `tools/`, con
  `python.exe`, `pythonw.exe`, `python3.dll`, `python313.dll`, `vcruntime140.dll`,
  `vcruntime140_1.dll`, `LICENSE.txt`, `DLLs/` (los `.pyd`, `sqlite3.dll` con SQLite 3.50.4,
  OpenSSL 3.5.9, `python.cat`), `Lib/` en `.py` (ningún `.pyc`, con `site-packages/pip`
  26.2.1 y sus lanzadores `t64.exe`, `w64.exe`…, `ensurepip` y `venv` con
  `venvlauncher.exe`), `include/` y `libs/`. En la raíz de `tools/` no hay nada que
  importar. Para cada papel quedan 571 ficheros (29 MB) y **un solo programa, `python.exe`**.
- **La firma**: `python.exe` y `python313.dll` llevan una firma Authenticode (PKCS#7) cuyo
  firmante es `CN=Python Software Foundation, O=Python Software Foundation, L=Beaverton,
  S=Oregon, C=US`, emitido por «Microsoft ID Verified CS EOC CA 03» (raíz «Microsoft
  Identity Verification Root Certificate Authority 2020»); el certificado vale tres días
  (del 29 de septiembre al 2 de octubre de 2026) y la firma lleva sello de tiempo RFC 3161,
  así que sigue valiendo después. El resumen SHA-256 firmado es igual al resumen
  Authenticode calculado aquí de cada fichero. La validación entera (la cadena y la firma
  criptográfica) no se pudo hacer aquí (`openssl cms` no entiende el contenido de
  Authenticode); la hace `Get-AuthenticodeSignature` en Windows, como antes.
- **El `._pth`, con el `getpath.py` de CPython 3.13.16** (`Modules/getpath.py` y el
  `MockNTNamespace` de `Lib/test/test_getpath.py`, bajados de GitHub al scratchpad): para
  `C:\BMS\runtime\lector\python.exe` con `python313.dll` y nuestro `python313._pth` al lado,
  y con `PYTHONPATH` y `PYTHONHOME` puestos, sale `sys.path` = `Lib`, `DLLs`,
  `C:\BMS\lib`, `C:\BMS\app\src`; `isolated` 1, `use_environment` 0, `site_import` 0,
  `safe_path` 1, `prefix` la carpeta del papel, sin avisos.
- **Las ruedas**: las diecisiete bajadas de files.pythonhosted.org tienen el sha256 fijado,
  ninguna trae `.data`, y `pip download --require-hashes --only-binary=:all: --platform
  win_amd64 --python-version 3.13 --implementation cp --abi cp313 -r
  windows/requirements-windows.txt` las acepta. Las dependencias de cada una, con los
  marcadores de Windows y 3.13, están todas en el fichero.
- **PowerShell de verdad**: PowerShell 7.4.21 (el `.deb` de packages.microsoft.com,
  desempaquetado en el scratchpad, sin instalar nada): pasan los seis tests de pwsh, también
  el que abre el paquete de verdad con `Abrir-Python` y lo compara con
  `nativo.destino_en_runtime`.
- `scripts/fijar_windows.py --rehacer`, con red, sacó exactamente lo que se había calculado
  a mano; `--comprobar` sale con 0, también con `--paquetes` y lo bajado.

### La puerta, test por test

Todo en `tests/test_instalacion_nativa.py`.

| Puerta | Tests |
| --- | --- |
| `fijado.json` y `requirements-windows.txt` completos; `--comprobar` sale con 0 | `test_fijar_comprobar_sale_con_0_con_lo_que_hay_en_el_repositorio` (por `main` y como programa), `test_fijar_comprobar_dice_que_falta_y_que_no_cuadra` (sin un hash, otra versión que Docker, una de más o de menos, cada campo del Python, lo bajado que no es lo fijado) |
| El sha256 de NuGet | `test_el_python_fijado_es_el_paquete_de_nuget_entero` (origen, URL, fichero, sha256 y SHA-512 medidos, catálogo, firmante, versión menor de `nativo`), `test_fijar_cruza_el_paquete_con_el_sha512_de_nuget` (el cruce y el índice de registro), `test_fijar_revisa_lo_que_el_instalador_abrira`; con lo bajado (`BMS_PAQUETES_WINDOWS`), `test_lo_bajado_de_verdad_es_lo_fijado` |
| Cada requisito con su hash | `test_cada_linea_de_requisitos_lleva_su_hash` (nada PENDIENTE, el formato de pip, los cuatro hashes medidos), `test_las_dependencias_de_windows_son_las_de_docker_con_su_hash` (cambiado), `test_fijar_elige_la_rueda_de_windows`, `test_fijar_saca_el_hash_de_pypi_y_rehace_las_lineas` |
| La estructura de NuGet y el `python313._pth` | `test_el_pth_es_el_de_la_estructura_del_paquete_de_nuget`, `test_comun_dice_lo_mismo_que_nativo_del_python_de_cada_papel`, `test_de_cada_paquete_solo_sale_el_interprete_con_un_programa`, `test_una_ruta_que_se_sale_de_la_carpeta_para_la_instalacion`, `test_el_instalador_abre_el_paquete_de_nuget_sin_salirse_y_con_un_solo_programa`, `test_el_instalador_hace_un_python_por_papel_con_su_pth` (cambiado), `test_el_instalador_compila_la_biblioteca_y_prueba_que_el_pth_vale`, `test_las_reglas_apuntan_al_unico_programa_de_cada_papel`, `test_un_interprete_de_la_instalacion_sin_instalacion_json_no_apaga_las_puertas` (cambiado); con pwsh, `test_pwsh_el_paquete_de_nuget_se_abre_como_dice_nativo` y `test_pwsh_el_paquete_de_verdad_deja_un_solo_programa` |
| La suite en 3.11 y en 3.13 | 2354 pasan y 12 se saltan en `.venv` (3.11); 2354 y 12 en 3.13.16; con `pwsh` y lo bajado, los 179 de este fichero en las dos |
| La guía | `test_la_guia_dice_de_donde_viene_python_y_por_que` (nuget.org, 3.13, la Python Software Foundation y las correcciones de seguridad en el apartado 3; la tabla del 14 sin «pide» ni hashes que faltan; el 17 con el cruce, `--comprobar`, `--rehacer` y el `._pth`) |

### Desviaciones, y por qué

1. **nuget.org y no el embebible de python.org.** Lo decidió el orquestador: desde aquí
   python.org no se puede bajar, y sin bajarlo no hay hash que fijar. El paquete de
   nuget.org es una distribución oficial y trae los mismos binarios firmados por la Python
   Software Foundation. Lo que se pierde: la firma de Sigstore que publica python.org (la
   guía la pedía como paso a mano antes de subir el hash). Lo que la sustituye: el SHA-512
   del catálogo de nuget.org (otra API, pero el mismo nuget.org, así que no es una fuente
   independiente del todo) y, sobre todo, la firma Authenticode de la Python Software
   Foundation en `python.exe` y en `python313.dll`, que el instalador comprueba en Windows.
2. **El `._pth` sin `.`.** El ejemplo del orquestador lo llevaba; en este paquete la
   carpeta del programa no tiene nada que importar (lo de la raíz de `tools/` son el
   programa, las DLL y la licencia), y una ruta menos en `sys.path` es un sitio menos donde
   dejar un módulo. El orden es `Lib`, `DLLs` (la biblioteca y después sus módulos
   compilados, como el embebible); no hay nombres repetidos entre las dos.
3. **Fuera, más que `pythonw.exe`.** También pip (sus lanzadores `.exe` son programas sin
   reglas), `ensurepip`, `venv` (`venvlauncher.exe`) e `include`/`libs`. Es lo que el propio
   paquete deja fuera al copiar su runtime (`build/native/python.props`), salvo
   `vcruntime140*.dll`, que se queda porque Windows no siempre lo trae, y `LICENSE.txt` y
   `DLLs\python.cat`, que no hacen daño. En vez de borrar `pythonw.exe` después, no se saca,
   y el instalador para si en una carpeta de un papel hay otro programa que `python.exe`.
4. **Abrir el paquete con .NET**, no con `Expand-Archive` (ver arriba), con la comprobación
   de que nada sale de la carpeta. Las ruedas siguen con `Expand-Archive`, como en el paso 14.
5. **La firma, más estricta**: antes bastaba con que el texto del certificado contuviera
   «Python Software Foundation»; ahora el CN tiene que ser exactamente ese.
6. **La biblioteca se compila al instalar** (no estaba): el embebible traía los `.pyc` en
   su zip y este paquete no trae ninguno. Sin compilar, cada arranque compilaría la
   biblioteca otra vez, porque tu usuario no puede escribir en `runtime\`. `checked-hash`
   porque un `.pyc` así solo vale si su `.py` es el mismo, sin depender de las fechas de la
   copia.
7. **La prueba de arranque mira el `._pth`** (no estaba): si Windows no lo aplicara, el
   instalador para en vez de dejar un Python que lee `PYTHONPATH` y el registro.
8. **`detectar` acepta el `._pth` de cualquier versión** (`python3*._pth`): cambiar de
   versión no puede apagar las puertas en una instalación vieja sin `instalacion.json`.
9. **`fijado.json` con más campos** (`origen`, `sha512`, `catalogo`), y `fijar_windows.py`
   con `--rehacer`, `--python` y `--paquetes`; `--comprobar` exige además lo de Docker y la
   versión de `nativo`, que antes solo miraba un test.
10. **Los tests con lo bajado o con PowerShell** se saltan si no está: `BMS_PAQUETES_WINDOWS`
    (o `windows/paquetes`) con el paquete y las ruedas, y `pwsh` en el PATH. Aquí se
    corrieron los dos y pasan; la suite de arriba es sin ellos.
11. **Las cifras de la guía**: unos 20 MB de descargas (decía 30) y el disco sigue en unos
    300 MB.

**Tests existentes cambiados, y por qué** (en `tests/test_demo.py`,
`tests/test_entorno_local.py` y `tests/test_revision_final.py`, siete `with
sqlite3.connect(...)` pasan a `closing(...)`: no cambia lo que miran, solo cierran la
conexión, de la que 3.13 avisa; los demás, en `tests/test_instalacion_nativa.py`):
`test_el_instalador_no_sigue_sin_los_hashes_fijados` (la URL es la de nuget.org, y ya no
admite un sha256 vacío: lo que mira del fichero pasa a
`test_el_python_fijado_es_el_paquete_de_nuget_entero`; ya no exige la versión menor del
Python que corre los tests, sino la de `nativo.VERSION_PYTHON`, porque la suite corre en 3.11
y en 3.13); `test_las_dependencias_de_windows_son_las_de_docker_con_su_hash` (nada
PENDIENTE, una sola rueda por dependencia); `test_el_instalador_hace_un_python_por_papel_con_su_pth`
(el `._pth` sale de `comun.ps1`, y en vez de borrar `pythonw.exe` se comprueba que hay un
solo programa); `test_ningun_script_usa_docker_ni_ejecuta_texto_ni_baja_sin_hash` (el
paquete se abre con `Abrir-Python`, después de comprobarlo y antes de la firma);
`test_un_interprete_de_la_instalacion_sin_instalacion_json_no_apaga_las_puertas`
(`python313._pth`, y el `._pth` de otra versión también cuenta); los de `fijar_windows.py`
(`vale_para_windows` y `elegir_rueda` reciben la versión menor, `escribir_requisitos` una
lista de hashes, y `pendientes` pasa a `problemas`); y los de pwsh (el `._pth` es
`python313._pth`, «no sigue sin los hashes» se prueba con una copia a la que le faltan los
de jiter, porque ya no falta ninguno, y se abre el paquete de NuGet).

### Lo que deben saber los pasos siguientes

- **Antes de dárselo al dueño ya no falta nada que fijar.** En su primer Windows hay que
  mirar lo de siempre (docs/instalacion-nativa.md, apartado 16) y, en particular, que
  `Get-AuthenticodeSignature` da `Valid` con el firmante «Python Software Foundation» en
  `python.exe` y `python313.dll` (la cadena de Microsoft Trusted Signing tiene que estar en
  el almacén de Windows, que la baja sola), que la prueba del paso 5 sale con
  `isolated`/`no_site` y que `comprobar.bat` sale en verde.
- **Una corrección de la 3.13** es `python scripts/fijar_windows.py --python 3.13.X`, revisar
  lo que cambia y `--comprobar`, **solo mientras nuget.org tenga esa versión**: las de solo
  seguridad (desde octubre de 2026, más o menos) salen solo en código fuente (corregido en
  la revisión, hallazgo 3). **Otra versión menor** (la 3.14, cuando la 3.13 deje de tener
  binarios) es además `nativo.VERSION_PYTHON`, las variables de `windows/comun.ps1` (los
  tests exigen que sean iguales) y la suite pasando antes en esa versión.
- **Una dependencia nueva** va en `docker/requirements.txt` y en
  `windows/requirements-windows.txt`; `fijar_windows.py` saca su hash cp313-win_amd64, y
  `--comprobar` exige las mismas versiones.
- **El desarrollo y Docker siguen en 3.11**; la suite tiene que seguir pasando en 3.11 y en
  3.13. En 3.13, `sqlite3` avisa (`ResourceWarning`) de las conexiones que no se cierran;
  ahora no queda ninguna. Una conexión nueva, en el código o en un test, se cierra
  (`closing`, o `Almacen` con su `with`): en Windows una base abierta no se deja mover ni
  borrar, y `restaurar` lo necesita.
- **Lo que se mira en cada papel** (un solo `python.exe` y lo necesario) es
  `NECESARIOS_DEL_RUNTIME` y `FUERA_DEL_RUNTIME` en `nativo.py` y en `comun.ps1`; si un
  paquete nuevo trae otro programa, el instalador para y hay que decidir si va fuera.

### Correcciones de la revisión (paso 14b)

Once hallazgos, con dos repetidos (el 7 es el 1 y el 9 es el 2). Todos se comprobaron
contra el código y **todos eran reales**; el mayor (el 6) y el de los `assert` (el 1) se
reprodujeron con un Python de verdad y un `._pth` de verdad. Cada corrección tiene un test
que falla con el código de antes y pasa con el de ahora (comprobado devolviendo `src/` y
`windows/` a `1e112ac` con los tests nuevos: fallan veintiséis; y los de la guía, con
`docs/`, `.gitignore` y `scripts/` de antes). La suite entera: **2371 pasan y 12 se
saltan** (eran 2354) en `.venv` (3.11), los mismos doce saltados de antes (el test nuevo
del `._pth` de verdad no se salta aquí); `tests/test_instalacion_nativa.py` con
`pwsh` (7.4.21, en el scratchpad) y lo bajado (`BMS_PAQUETES_WINDOWS`): **196 pasan, en
3.11 y en 3.13.16** (con `-W error` en 3.13), así que los `.ps1` cambiados pasan el
analizador de PowerShell y las pruebas de pwsh.

1. **La prueba del paso 5 eran `assert`** (menor), y `PYTHONOPTIMIZE` (que el `._pth` no
   aparta: el 6) los quita: con `PYTHONOPTIMIZE=1` un `assert False` sale con 0. Ahora la
   prueba llama a `nativo.exigir_interprete_aislado(version)`, que sale con `SystemExit` y
   el mensaje («… no esta aislado: el ._pth no se aplica…»); además va con `-E` y mira que
   `optimize` sea 0. Tests: `test_la_prueba_de_arranque_no_depende_de_los_assert` (con
   `-O` y `-OO` sigue saliendo con 1) y, en
   `test_el_instalador_compila_la_biblioteca_y_prueba_que_el_pth_vale` (cambiado), que en
   el código del paso 5 no hay ningún `assert`.
2. **Los `compileall` no miraban su código de salida** (menor). `$LASTEXITCODE` solo se
   miraba después de la prueba, la última orden. Ahora cada `compileall` va seguido de su
   `if ($LASTEXITCODE -ne 0) { Fallar … }` («No se ha podido compilar …»), y lo que dice
   sale por `Out-Host` (con `-q` solo dice los errores). Se miró antes que la biblioteca de
   verdad compila: los 540 `.py` de `Lib` que se sacan del paquete, con
   `/usr/bin/python3.13 -m compileall --invalidation-mode checked-hash`, salen con 0, y
   también las diecisiete ruedas y `src/`. El test (cambiado) exige, línea a línea, que
   detrás de cada `compileall` venga su comprobación.
3. **La 3.13 también se queda sin binarios para Windows** (menor, de documentación). Es
   así: por la PEP 719, la 3.13 sale de su fase de correcciones hacia octubre de 2026, y las
   versiones de solo seguridad salen solo en código fuente, sin binarios ni paquete de
   nuget.org (aquí no se pudo mirar el calendario, sin red). La guía (apartado 17), el
   docstring de `fijar_windows.py` (ya no pone `--python 3.13.17`) y «Lo que deben saber
   los pasos siguientes» de arriba lo dicen ahora: `--python 3.13.X` vale mientras
   nuget.org tenga esa versión, y después lo siguiente es la versión menor siguiente (la
   3.14, con binarios hasta octubre de 2027 más o menos), cuanto antes. **No se cambia el
   Python fijado**: subir a la 3.14 es bajar su paquete y sus ruedas y pasar la suite en
   3.14, y aquí no hay red ni 3.14; queda para quien prepare la versión siguiente.
4. **Dos tests miraban sus propias constantes** (menor). En
   `test_las_reglas_apuntan_al_unico_programa_de_cada_papel` sobraba la línea de
   `EN_CADA_PAPEL`; ahora mira que el programa de las reglas es el que `Comprobar-Runtime`
   exige como único y el que arranca `Programa`. En
   `test_el_pth_es_el_de_la_estructura_del_paquete_de_nuget`, en vez de comparar
   `NECESARIOS_DEL_RUNTIME` con literales, `_rutas_del_pth_que_faltan` saca con
   `nativo.destino_en_runtime` lo que se extrae de `ENTRADAS_DEL_PAQUETE` y exige que en
   cada ruta del `._pth` dentro del papel (`Lib`, `DLLs`) quede algo (y sin la biblioteca,
   falta `Lib`); lo mismo con el paquete de verdad en `test_lo_bajado_de_verdad_es_lo_fijado`.
   Que `Destino-En-Runtime` haga lo mismo que `nativo.destino_en_runtime` lo siguen
   probando los tests de pwsh, que aquí se corrieron.
5. **El SHA-512 de nuget.org no es una segunda fuente** (menor, de documentación). La guía
   lo decía; ya no: el paquete y su catálogo son los dos de nuget.org, y el cruce dice que
   lo bajado es lo que nuget.org lista, no de dónde viene. Lo que lo dice es la firma
   Authenticode de la Python Software Foundation, que el instalador exige; y antes de subir
   un sha256 nuevo, quien lo sube mira esa firma en `tools\python.exe` y
   `tools\python313.dll` en un Windows (apartado 17 y docstring de `fijar_windows.py`).
6. **El `._pth` no aparta las variables `PYTHON*`** (mayor). Reproducido aquí: una copia de
   `/usr/bin/python3.13` (y de la 3.11) con su `._pth` al lado da `isolated` 1 e
   `ignore_environment` 1, pero `PYTHONPYCACHEPREFIX`, `PYTHONOPTIMIZE`, `PYTHONWARNINGS` y
   `PYTHONINSPECT` se aplican igual (`sys.pycache_prefix`, `optimize` 1…): Python las lee
   antes de `getpath.py`, que es quien aplica el `._pth`. Con `-E`, ninguna. En Windows el
   entorno del usuario (`HKCU\Environment`) lo puede cambiar cualquier programa suyo, y
   con `PYTHONPYCACHEPREFIX` en `datos\` el siguiente arranque de la salida ejecutaría
   unos `.pyc` dejados allí en vez del código de solo lectura. Ahora:
   - **`-E` siempre**: `$OpcionesPython = @("-E", "-u", "-X", "utf8")` en `comun.ps1`, igual
     que `nativo.OPCIONES_PYTHON` (un test exige que sean iguales); y las órdenes del paso 5
     del instalador (los dos `compileall` y la prueba) también van con `@OpcionesPython`.
   - **Se mira al arrancar**: `nativo.problemas_del_arranque(arranque, version)`, pura, con
     `nativo.Arranque` (de `sys.orig_argv`, `sys.flags`, `sys.pycache_prefix`,
     `sys.warnoptions`, si `site` está importado y la versión): el `._pth` se aplica (modo
     aislado, sin `site`), la línea de órdenes lleva `-E` o `-I` antes de lo que ejecuta
     (`nativo.lleva_menos_e`: se mira la línea, porque `ignore_environment` lo pone el
     `._pth` aunque el entorno ya se haya leído; ni el valor de `-X`/`-W` ni un argumento
     del programa cuentan), sin optimización, sin `inspect`, sin otra carpeta de `.pyc` y
     sin avisos cambiados.
   - **`comprobar-aislamiento` lo comprueba en cada papel** (en la instalación): una
     comprobación grave más, «el Python de este papel» (`aislamiento.Observaciones.interprete`,
     que `observar` rellena con lo que le da la orden: `nativo.problemas_del_interprete`;
     `aislamiento` no importa `nativo`, que lo importa a él). Una salida o un lector que no
     arrancó así no sale en verde, y entonces la lectura no se hace.
   - Los comentarios de `comun.ps1`, `instalar.ps1` y `nativo.py`, y la guía (apartados 10 y
     17), dicen ya lo que hace cada cosa: el `._pth` fija el `sys.path` (ni `PYTHONPATH`, ni
     `PYTHONHOME`, ni el registro) y deja `site` sin importar; las demás variables las
     aparta `-E`.

   Tests: `test_el_pth_no_aparta_las_variables_python_y_menos_e_si` (con un Python de verdad
   y un `._pth` de verdad, en una carpeta temporal: sin `-E` la prueba ve
   `PYTHONPYCACHEPREFIX`, `PYTHONOPTIMIZE` y `PYTHONWARNINGS`; con `nativo.OPCIONES_PYTHON`,
   nada; se salta si aquí no se puede copiar el Python),
   `test_problemas_del_arranque_ve_el_pth_el_menos_e_y_las_variables`,
   `test_lleva_menos_e_mira_solo_las_opciones_de_python`,
   `test_comprobar_aislamiento_mira_como_arranco_el_python`,
   `test_comun_dice_lo_mismo_que_nativo_del_python_de_cada_papel` (más
   `OpcionesPython`) y `test_cada_python_corre_sin_bufer` (cambiado: ahora con `-E`).
7. Es el 1.
8. **La prueba de arranque solo se hacía con el programa de las órdenes** (menor). Ahora es
   un bucle por `$Roles`: cada `runtime\<papel>\python.exe`, con `@OpcionesPython`, importa
   lo de siempre y pasa `nativo.exigir_interprete_aislado`; si uno no, el instalador para
   («El programa de … no arranca con lo instalado o no esta aislado»). Sale una línea por
   papel, con `aislado`. Y `comprobar.bat` lo vuelve a mirar en cada papel (el 6). Test:
   `test_el_instalador_compila_la_biblioteca_y_prueba_que_el_pth_vale` (cambiado).
9. Es el 2.
10. **La guía no tenía lo nuevo del paso 14b en los apartados 14 y 16** (menor). El 16
    tiene ahora lo de la primera vez: las cuatro líneas del paso 5 con `aislado`, y
    `Get-AuthenticodeSignature` de `python.exe` y `python313.dll` con `Status : Valid`, el
    firmante `CN=Python Software Foundation` y la cadena de Microsoft Trusted Signing. La
    tabla del 14 tiene filas para «no esta aislado: el ._pth no se aplica…», «…hace caso
    de las variables PYTHON*…» o la versión que no es («no sigas, avisa»), para «No se ha
    podido compilar» y para «el Python de este papel» en rojo en `comprobar.bat`.
11. **El comentario de `.gitignore` decía «Python embebible»** (menor): ahora dice el
    paquete de nuget.org (`python.3.13.16.nupkg`) y las ruedas.

Tests nuevos o cambiados de esta revisión, todos en `tests/test_instalacion_nativa.py`: los
nombrados arriba y `test_la_guia_dice_lo_de_menos_e_la_firma_y_cuanto_dura_la_313` (los
apartados 10, 14, 16 y 17, `.gitignore` y el docstring de `fijar_windows.py`). El fixture
`como` hace además como si el Python de los tests arrancara aislado
(`nativo.problemas_del_interprete` sin problemas), igual que ya hacía como si hubiera
instalación: el Python de los tests no tiene `._pth` ni `-E`, y lo que pasa con uno así lo
prueba `test_comprobar_aislamiento_mira_como_arranco_el_python`.

## Paso 15

La app local para el personal de BMS. **No está en la especificación: la pidió el
dueño** («Podríamos construir como app local para que tenga una interfaz razonable con
el cliente y que pueda acceder a la informacion que necesite?»), con la opción B del
diseño y su componente de navegación («Me gusta la opcion B con el menu de navegacion
asi. Importante que sea claro»; «Quiero que sea minimalista el panel y que sea facil de
entender»). Usuarios: una a tres personas de administración, a diario, en sesiones
largas y en un ordenador de mesa. Idiomas de la interfaz: neerlandés e inglés, nada de
castellano. Lo explica [docs/app-local.md](../app-local.md). Después el dueño eligió
también cómo se ven las alertas, con su componente Status («Asi quiero las alertas»):
abajo, «Paso 15 · alertas con el componente Status».

El paso va en partes. Esta es la **base** (la parte A): el `frontend/`, el marco con la
navegación y las pestañas, la entrada, los idiomas, el cliente de la API, las piezas de
las pantallas, el servicio en `/app`, los lanzadores y las pruebas en el navegador. A la
vez, otra parte construye los catálogos de textos de dominio en Python
(`src/bms_agent/textos/`, los `valores` de los avisos en la API); esta no los toca y los
espera en un solo módulo (`frontend/src/i18n/domain.ts`). Las pantallas se llenan en
las partes siguientes.

**2418 tests de Python pasan y 12 se saltan** en `.venv` (3.11; eran 2371 y 12): los 47
nuevos son de `tests/test_app_local.py`. En 3.13.16, con `pwsh` en el PATH, 2423 pasan y
7 se saltan (`tests/test_app_local.py` se volvió a pasar, con `-W error`, después de la
última construcción). Del frontend, **40 de vitest** y **9 pruebas
en el navegador** (Playwright, con 38 capturas). Ninguno llama a la API ni sale de la
máquina.

### Qué se construyó

**`frontend/`**: Vite 7 + React 19 + TypeScript estricto + Tailwind CSS v4
(`@tailwindcss/vite`, `tw-animate-css`) y shadcn montado a mano (`components.json` con
el estilo `default`, `tsx`, sin `rsc`, y los alias `@/components`, `@/lib/utils`,
`@/components/ui`, `@/lib`, `@/hooks`; el alias `@/` a `frontend/src` en Vite y en
`tsconfig`; `cn()` en `src/lib/utils.ts`). Dependencias con versión exacta, todas
publicadas al menos 14 días antes del 19 de octubre de 2026 (`npm install
--before=2026-10-05`; `scripts/check-lock-age.mjs` lo comprueba paquete a paquete con
el registro: los 250 del `package-lock.json`, bien), el lock en git y
`npm ci` para instalar. `npm run dev | build | typecheck | test | e2e`.

- **El componente del dueño y los nueve de shadcn** (button, sheet, input, label,
  tooltip, context-menu, dropdown-menu, hover-card, avatar) en
  `frontend/src/components/ui`, la ruta de shadcn. El del dueño conserva su aspecto, su
  movimiento, el menú contextual de cada pestaña, el «abrir rápido» del `+` y la hoja del
  móvil; lo que se le cambió va arriba del fichero: `NavItem` con `group`, `badge` y
  `hint`; una pestaña con `route` (pantalla + id numérico + de qué entrada viene) y
  título, y `openRoute` (una ficha ya abierta se enfoca); los textos en `labels`; lo que
  se guarda lo leen y escriben `loadState`/`saveState` de la app (antes, una clave fija
  de `localStorage` sin comprobar); `prefers-reduced-motion`; el botón de cerrar fuera
  del `role=tab` y el `li` como `presentation` (axe: un control dentro de una pestaña y
  una lista dentro de un `tablist`); `aria-label` en cada botón de icono, `tabpanel`
  con su pestaña; Tailwind v4 (`shrink-0`, `h-full`, `text-destructive`); `toolbar` a la
  derecha de la tira; sin imágenes de fuera (las iniciales en `AvatarFallback`). De los
  de shadcn solo cambia `SheetContent`, que acepta `closeLabel` (su «Close» iba fijo).
- **Los colores de la opción B**, solo claros, como variables de `@theme` de Tailwind:
  fondo `#f7f5f0`, texto `#1c1b18`, acento `#0e5f5c`, líneas `#e2ded5`, menús en blanco,
  y los cuatro pares de prioridad (Geblokkeerd `#8a3a0c`/blanco, Urgent
  `#f4c39c`/`#4a1f03`, Aandacht `#e4ecf6`/`#1d4673`, Normaal neutro). IBM Plex Sans
  (400, 500, 600) y Mono (400, 500) de `@fontsource`, solo latin, dentro del paquete y
  con su licencia (SIL OFL 1.1, `web/licenses/`); la utilidad `num` para las cifras.
- **Las piezas de las pantallas** (`frontend/src/components`): `PageHeader` (título, una
  frase, una acción como mucho; pone el título de la ventana) y `Screen`, `SummaryCard`
  y `SummaryGrid`, `DataTable` (de una a seis columnas, lo exige el tipo; cifras a la
  derecha; la columna principal es un botón, para el teclado), `PriorityPill` (texto,
  color y forma), `StatusText` (texto y punto de color), `Money`, `Hours`, `DateText`
  (sin dato, una raya con su explicación, nunca 0), `EmptyState`, `ErrorState` (dice el
  error en el idioma de la app y ofrece reintentar o recargar), `Loading`, `HelpTip` (el
  (?) de Object, PO, BTW y uitzondering) y `Section` (plegable).
- **El marco** (`frontend/src/shell`, `screens/`): la entrada (el token, NL | EN y una
  frase que dice qué es el token y quién lo da), el componente del dueño con las quince
  entradas en seis grupos (Dagelijks, Facturen, Relaties, Geld, Gegevens y, abajo,
  Instellingen), cada una con su título y su frase en los dos idiomas; las insignias
  (bloqueadas, excepciones abiertas, IBAN por verificar, del panel); a la derecha de la
  tira, la marca de datos de prueba (con `X-BMS-Entorno: demo`), NL | EN y la persona
  (sus iniciales, un menú con quién es y «Uitloggen»); abajo, la fecha de hoy. Las
  rutas son pantalla + id: una fila de la Werklijst abre su factura en una pestaña nueva,
  con el número de título, o va a la suya si ya estaba. Las entradas que piden
  `importar_datos` no salen a quien no lo tiene. Las pantallas aún no hechas enseñan su
  título y su frase; Werklijst y la ficha de factura van en una versión mínima (abajo,
  desviación 6) e Instellingen entera.
- **El cliente de la API** (`frontend/src/lib/api.ts`): `X-BMS-Token`, JSON, mismo
  origen; las rutas salen de constantes con ids comprobados (`paths`); un 401 echa a la
  entrada, un 409 `Conflicto` es «otra persona lo cambió» y otro 409 un conflicto de
  estado; otro número mayor del contrato (`X-BMS-Contrato`) se rechaza; el entorno sale
  de `X-BMS-Entorno`. `action()` manda `{accion, peticion_id, datos}` a
  `POST /api/v2/acciones` (con la `rev` dentro de `datos` cuando la orden la pide) y
  `download()` hace `fetch` con el token, `Blob`, `a[download]` y revoca la URL. El texto
  de error del servidor (en castellano) se guarda en `detail` y no se pinta. Tipos de
  `/api/v2/yo`, `/api/v2/panel` y la fila de `/api/v2/facturas`.
- **La sesión** (`lib/session.tsx`): el token solo en la memoria del cliente de la
  sesión, que se tira al salir (`dispose`); un 401 que llega tarde de una sesión
  anterior no echa a quien acaba de entrar.
- **Los idiomas** (`frontend/src/i18n`): `nl.ts` (la forma) y `en.ts` (tipado con esa
  forma: ni una clave de más ni de menos), `useT()`, `fmt()` para los huecos `{x}`;
  neerlandés por defecto; el de cada persona se guarda con su id y su entorno. Los
  formatos (`lib/format.ts`): importes desde céntimos con `BigInt` («€ 36.270,36»,
  «€ −24,76»), horas desde milésimas («78,5»), porcentajes desde puntos básicos, fechas
  «16-10-2026» en tablas y «16 okt 2026» / «16 Oct 2026» en una frase, y la hora de
  Ámsterdam.
- **Lo que se guarda** (`lib/storage.ts`): solo el idioma, la barra plegada y las
  pestañas (ids de pantalla e ids numéricos), con la clave
  `bms-app:v1:<demo|real>:<id de persona>:…`, todo en `try/catch` y comprobado al leer.
- **`src/bms_agent/app_local.py`** y `serve.py`: `/app` (y `/app/`) da `web/index.html`
  con un *nonce* nuevo por respuesta (en la CSP y en `<meta name="bms-nonce">`) y las
  bandas (TESTGEGEVENS · TEST DATA con la base de prueba; la roja del aislamiento en la
  instalación nativa), puestas por el servidor y escapadas; `/app/assets/<nombre>` sale
  de una lista blanca hecha al arrancar con los ficheros que hay (diccionario de nombre
  exacto: `.js`, `.css`, `.woff2`, `.svg`), con su tipo y caché inmutable; la página,
  `no-store`. CSP, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`,
  y las mismas comprobaciones de Host y Origin que todo lo demás. Sin construir, `/app`
  da 503 y manda a `/consola`, que no cambia.
- **Lo construido va en git**: `vite build` escribe en `src/bms_agent/web` (con
  `emptyOutDir` y `base: "/app/"`) y `scripts/fuente.mjs` escribe `web/fuente.json`, la
  huella de las entradas (`frontend/build-inputs.json`, con los CRLF como LF) y el sha256
  de cada fichero construido. `pyproject.toml` lleva `web/` y `textos/*.json` en el
  paquete (comprobado construyendo la rueda: los trece ficheros de `web/` van dentro);
  `.gitattributes`, `src/bms_agent/web/** -text`.
- **Los lanzadores** (`windows/iniciar.ps1`, `docker/iniciar.ps1`): esperan a `/app` y la
  abren con `Abrir-App` (en cada `comun.ps1`), en una ventana de Edge (`--app=…`); sin
  Edge, el navegador de siempre; dicen dónde está la consola de antes. Las pistas de la
  CLI (`usuario token`, `demo crear`) dicen `/app`.
- **Las pruebas en el navegador** (`frontend/e2e`): `global-setup.ts` crea una base de
  prueba nueva en una carpeta temporal (`scripts/crear_demo_e2e.py`, que da los tokens en
  JSON), arranca `bms-agent serve` en un puerto libre y pasa la dirección y los tokens;
  `fixtures.ts` vigila en cada prueba que toda petición vaya a `127.0.0.1` (otra se
  corta), que no haya violaciones de la CSP ni errores en la consola (un 4xx que la
  prueba provoca a propósito se declara), y da `login`, `expectAccessible` (axe, WCAG
  2.1 AA, nada serio ni crítico) y `capture` (a `CAPTURAS_DIR`). `@playwright/test`
  1.56.1, con el Chromium que ya está instalado.
- **Documentación**: [docs/app-local.md](../app-local.md) (nueva); el README; `/app` en
  docs/entorno-local.md, docs/instalacion-nativa.md, docs/uso-v1.md y
  docs/integracion-web.md (sin cambios en el contrato: no hay claves nuevas).

### La puerta, test por test

| Puerta | Tests |
| --- | --- |
| `/app` con su CSP, un nonce por respuesta, sin nada en línea y sin direcciones de fuera | `test_app_local.py::test_app_da_la_pagina_con_una_csp_estricta_y_un_nonce_por_respuesta` |
| Cada fichero con su tipo y caché inmutable; las fuentes, `woff2` propias | `test_cada_fichero_de_la_pagina_se_sirve_con_su_tipo_y_cache_inmutable` |
| Lista blanca de nombres exactos, nunca una ruta juntada con una carpeta | `test_lo_que_no_esta_en_la_lista_blanca_es_un_404` (catorce rutas: `..`, `%2e%2e`, `index.html`, `fuente.json`, un `.map`…), `test_la_lista_blanca_son_los_ficheros_que_hay_y_nada_mas` (un `.txt`, un `.map`, un oculto, una subcarpeta y un enlace simbólico se quedan fuera), `test_la_lista_blanca_de_lo_construido_cubre_todo_assets` |
| Host y Origin, como todo | `test_host_y_origin_se_comprueban_tambien_en_app` |
| Las bandas, del servidor, en NL y EN, escapadas | `test_con_la_base_de_prueba_la_app_lleva_la_banda_en_neerlandes_e_ingles`, `test_la_banda_del_aislamiento_dice_que_papel_falla_y_escapa_lo_demas`, `test_texto_de_la_banda_del_aislamiento_sin_papeles_conocidos`, `test_un_index_sin_las_marcas_no_se_sirve_sin_bandas` |
| Sin construir, se dice y la consola sigue | `test_sin_construir_app_lo_dice_y_la_consola_sigue` |
| Lo construido es de estas fuentes (`fuente.json`) | `test_lo_construido_es_de_estas_fuentes`, `test_lo_construido_es_lo_que_apunta_fuente_json`, `test_la_huella_cubre_las_fuentes_y_los_crlf_no_la_cambian`, `test_el_paquete_lleva_la_app_y_los_textos` |
| En el frontend, nada que interprete HTML, ni el token en el navegador, ni direcciones de fuera | `test_el_frontend_no_usa_nada_que_interprete_html_ni_guarde_el_token` (quince palabras prohibidas), `test_el_navegador_solo_guarda_comodidades_desde_un_sitio`, `test_el_frontend_no_lleva_ninguna_direccion_de_fuera` |
| Los lanzadores abren `/app` en Edge, con reserva | `test_los_lanzadores_abren_la_app_en_una_ventana_de_edge` (las dos variantes), y los cambiados de abajo |
| Formatos, idiomas, rutas, lo que se guarda, el cliente | vitest: `format.test.ts` (céntimos con `BigInt` más allá de 2^53, signo, sin dato, horas, fechas en NL/EN, hora de Ámsterdam), `i18n.test.ts` (mismas claves y huecos en NL y EN, nada vacío, nada en castellano, el catálogo de dominio con las mismas claves), `storage.test.ts` (claves por entorno y persona, lo que se descarta, sin título, sin `localStorage`), `api.test.ts` (token, 401, 409 `Conflicto`, la orden, el contrato, sin servidor, `dispose`, rutas, nombres de descarga), `registry.test.ts` |
| La app de verdad, en un navegador | `e2e/shell.spec.ts`: la entrada en NL y EN (y un token que no vale), las quince entradas en los dos idiomas con axe en cada una, una fila que abre su ficha y la misma pestaña otra vez, las pestañas y la barra plegada al recargar (y el token, en ningún sitio), salir, el idioma de cada persona, una sesión que caduca, 1024 px y la hoja del móvil, el teclado (Supr, el foco visible). En todas: solo `127.0.0.1`, sin violaciones de la CSP, sin errores en la consola |

Se comprobó aparte que axe sigue viendo los problemas con la CSP y Trusted Types (una
imagen sin `alt` metida en la página da `image-alt`), que el servidor de desarrollo
pasa `/api` a un `serve` en marcha, y que los cuatro `.ps1` cambiados los analiza bien
PowerShell 7.4.21.

### Desviaciones, y por qué

1. **Versiones de líneas conocidas, no las mayores más nuevas.** Hay Vite 8, TypeScript
   7, Vitest 5, framer-motion 14 y lucide-react 1.x publicados hace más de 14 días, pero
   son cambios grandes (Vite sobre Rolldown, el compilador nuevo de TypeScript) que aquí
   no se pueden comprobar sin riesgo. Se tomó el último parche de cada línea estable:
   React 19.2.8, Vite 7.3.6, TypeScript 5.9.3, Tailwind 4.1.18, Vitest 3.2.7,
   framer-motion 12.43.0, lucide-react 0.577.0, Radix 1.x/2.x. Todas cumplen la regla de
   los 14 días.
2. **`playwright-core` 1.56.1 fijado aparte.** `@axe-core/playwright` lo pide como
   dependencia par y npm ponía el 1.63; con dos versiones los tipos no casan y no es el
   del Chromium instalado.
3. **La CSP lleva más que lo pedido**: `'nonce-…'` en `style-src` (react-remove-scroll,
   que usan los menús y la hoja, mete un `<style>`; se le da el nonce con `get-nonce`,
   que pasa a ser dependencia directa) y `require-trusted-types-for 'script';
   trusted-types 'none'` (React solo usa `innerHTML` para `dangerouslySetInnerHTML`, que
   no hay, así que no cambia nada y lo que lo intente falla). Más `Cross-Origin-Opener-Policy`
   y `Cross-Origin-Resource-Policy: same-origin`. Nada se afloja: ni `unsafe-inline` ni
   `unsafe-eval`.
4. **Los textos de dominio, provisionales.** Mientras la otra parte no esté en esta rama,
   `frontend/src/i18n/domain.ts` lee un sustituto mínimo (prioridades, estados de pago y
   de revisión, sentido) marcado como tal en `frontend/src/i18n/domain/`. Al llegar el
   catálogo de verdad se cambian allí las dos líneas de `import`, se borra la carpeta y
   los dos JSON entran en `build-inputs.json` (el test lo exige cuando existen).
5. **Las cosas de la cabecera van a la derecha de la tira de pestañas** (el `toolbar`
   del componente), no en una barra encima: una barra más rompería las pestañas «como
   las de Chrome», pegadas al contenido.
6. **Werklijst y la ficha de factura no son solo un título.** Para que «una fila abre su
   ficha en una pestaña» se pruebe con datos de verdad, la Werklijst tiene una versión
   mínima (seis columnas: prioridad, número, relación, importe, vencimiento y pago; sin
   «Waarom», que necesita los textos de las reglas) y la ficha dice qué es y de quién,
   con los detalles plegados. Las dos se sustituyen en las partes siguientes.
7. **La banda de datos de prueba es amarilla y corta** (la de la opción B), no roja como
   en la consola: «TESTGEGEVENS · TEST DATA — testdatabase, alles is verzonnen · test
   database, everything is made up», en una línea. La roja queda para el aislamiento.
8. **La banda del aislamiento no copia el texto de los problemas**: viene en castellano
   y de un fichero que se puede escribir. Dice qué papeles fallan (en neerlandés e
   inglés) y que se ejecute `comprobar.bat`, que da el detalle.
9. **El idioma de la entrada es el del último uso en ese ordenador** (`bms-app:v1:lang`):
   antes de entrar no se sabe quién es. Al entrar manda el de la persona; quien nunca
   eligió se queda con el que había, y queda como suyo.
10. **Lo construido va en dos ficheros de script**: uno de dependencias (`vendor`, 476 kB,
    que solo cambia al cambiar una dependencia) y uno de la app (75 kB): así git no
    guarda medio mega nuevo con cada cambio de una pantalla.
11. **Las licencias de las fuentes van con lo construido** (`web/licenses/`, desde
    `frontend/public/`): la SIL OFL 1.1 pide que cada copia la lleve. No se sirven.
12. **`CONSOLA_DOCKER` de `cli.py` vale ahora `/app`** (el nombre se queda: lo usan los
    tests de las pistas de Docker, que no cambian).
13. **En la barra lateral, abajo, la fecha de hoy** (el sitio del pie del componente); la
    persona va arriba a la derecha, con su menú.
14. **Las pruebas en el navegador separan los 4xx que se provocan.** Chromium anota en la
    consola cada respuesta de error de un `fetch` («Failed to load resource: … 401»);
    una prueba que la provoca a propósito (un token que no vale, una sesión que caduca)
    lo declara con `watch.expectHttpErrors(401)`, y cualquier otro error de la consola
    sigue haciendo fallar la prueba.

**Tests existentes cambiados, y por qué** (los lanzadores abren la app a propósito):
`test_entorno_local.py::test_iniciar_con_demo_usa_la_base_de_prueba_y_la_rehace` (exige
además que se espere a `/app` y se abra con `Abrir-App`; la consola sigue nombrada) y
`test_instalacion_nativa.py::test_iniciar_comprueba_y_abre_la_consola_solo_en_127_0_0_1`
(la dirección es `/app`, se espera a ella y se abre con `Abrir-App`; la de `/consola` se
sigue diciendo).

### Lo que deben saber las partes siguientes

- **Una pantalla nueva** es una línea en `frontend/src/screens/render.tsx` (hoy casi
  todas van a `PlaceholderScreen`), sus textos en `nl.ts` y `en.ts` y, si es una ficha,
  su entrada en `RECORDS` de `screens/registry.ts`. Se abre una ficha con
  `useTabs().openRoute(recordRoute('invoice', id, 'invoices-in'))`; la ficha pone su
  título con `setTabTitle(tab.id, numero)` (el título no se guarda: al recargar sale
  «Factuur 12» hasta que carga). Lo que se lee, con `useLoad` y
  `session.api.get(paths.…)`; una ruta nueva, en `paths` (con `checkId`).
- **Una orden**: `session.api.action(nombre, datos, { requestId })` con la `rev` de la
  fila en `datos` cuando la orden la pide (`GET /api/v2/acciones`: `parametros`), el
  mismo `requestId` si se reintenta, y el error con `ErrorState`/`errorMessage` (un
  `stale` ofrece recargar). Los botones, con `useCan()(permiso)`.
- **Los textos de dominio** solo por `frontend/src/i18n/domain.ts`: cambiar allí el
  `import` a `src/bms_agent/textos/*.json`, añadirlos a `frontend/build-inputs.json`,
  borrar `frontend/src/i18n/domain/` y escribir el renderizador de plantillas con un
  test de vitest contra el fichero de casos de Python. Nada de `titulo`, `detalle`,
  `etiqueta`, `fuente_texto`, `nota` ni `motivos` en pantalla.
- **Después de cambiar `frontend/`**: `npm run build` y meter `src/bms_agent/web` en el
  mismo commit (si no, `test_lo_construido_es_de_estas_fuentes` falla). Y `npm run e2e`
  con `CAPTURAS_DIR` para mirar las capturas.
- **Las reglas de diseño** (docs/app-local.md, apartado 4) valen para cada pantalla: una
  pregunta y su frase, cuatro tarjetas como mucho en el Overzicht, seis columnas,
  «Waarom», los detalles plegados, estado con texto, el (?) en las palabras del oficio.
- **Una dependencia nueva**: `npm install --save-exact --before=<hace 14 días>`,
  `node scripts/check-lock-age.mjs` y construir. Si mete un `<style>`, tiene que aceptar
  el nonce (`get-nonce` o `MotionConfig nonce`), no se afloja la CSP.

### Lo que falta

Las pantallas (Overzicht, Werklijst completa, la ficha de factura con lo que está mal y
qué hacer, Uitzonderingen, IBAN-controles con el flujo de siempre, Inkomend, Uitgaand,
las relaciones, Kasstroom, Btw, Importeren, Facturen lezen), con los catálogos de textos
de Python y sus capturas. En el ordenador del dueño, mirar que Edge abre la ventana
`--app` y que la app se ve como en las capturas.

### Paso 15 · textos NL/EN

La app local habla neerlandés e inglés y no enseña nunca los textos en español de la API
(`titulo`, `detalle`, `etiqueta`, `fuente_texto`, `nota`, `motivos`), que se quedan para la
CLI y la auditoría. Sus textos de dominio salen de `src/bms_agent/textos/`, que la app
importa al compilarse.

**Qué se construyó**

- `nl.json` y `en.json`, con las mismas claves (en español, como el código) y los valores
  en el idioma de cada uno: las 85 reglas de `reglas/catalogo.py` (de cada una `titulo`,
  `significa`, `que_hacer` y `detalle`: 289 variantes de plantilla, con `sin_datos` en las
  52 reglas que pueden no tener con qué mirar); las 10 categorías de `panel.atencion`; los
  129 campos de las 9 tablas que la API devuelve en `campos[]` y en `corregibles`
  (factura, línea, imputación, proveedor, cliente, contacto, Objeto, recurso, PO); las 7
  fuentes; las 5 calidades; 38 grupos de estados (cada enum que la API devuelve: pago,
  revisión, excepción, hallazgo, relación, PO, BTW, cuenta, turno, importación...); las 4
  prioridades y las 3 severidades con su significado en una línea; las 48 órdenes de
  `servicios.ACCIONES` (las 33 que tocan dinero, IVA o datos bancarios con su frase de
  confirmación); los 3 roles y los 14 permisos; el veredicto de una factura («Geen bezwaren
  van het systeem», nunca «goedgekeurd»); y 58 códigos (lo que escribe `|codigo`).
- Un lenguaje de plantillas pequeño, escrito en `textos/LEEME.md`: `{clave}`,
  `{clave|dinero}` (céntimos a `€ 1.234,56`), `|horas` (milésimas), `|pct` (puntos
  básicos), `|fecha` (a `dd-mm-aaaa`), `|iban` (de cuatro en cuatro; uno enmascarado se
  deja), y además `|tarifa` (`_e4`), `|trimestre` (`2026-T3` es `Q3 2026`), `|codigo` y las
  transformaciones `|cuenta`, `|suma` y `|abs`, que van delante del formato; rutas con
  puntos (`{distintos.total_cent.0}`); una clave que falta es una raya y se apunta. Cada
  `detalle[resultado]` es una lista de variantes con condiciones (`clave`, `!clave`,
  `clave=valor`); la primera que vale escribe, y una variante con `partes` escribe cada
  parte que vale (A2, A7, A8, M3, F4, P3: cada diferencia que haya).
- La referencia en Python, `bms_agent.textos` (`pintar`, `renderizar`, `detalle`,
  `elegir`, `cumple` y los formatos), pura y sin floats.
- `casos.json`, de `scripts/generar_casos_textos.py`: 64 casos de los bordes del lenguaje y
  301 de reglas, 52 de la base de prueba (hecha con un reloj fijo, el 16-10-2026) y 15 de
  las fixtures v1, con las reglas de verdad, y 234 ejemplos para las variantes que esos
  datos no alcanzan, con la forma exacta que dan las reglas en los tests. Cada variante de
  cada plantilla tiene al menos un caso, y el generador falla si una no lo tiene. La app
  implementa el mismo renderizador en TypeScript y se prueba contra este fichero.
- La API sube al contrato **2.1**, solo con claves nuevas: cada hallazgo lleva `resultado`
  y `valores` (los de su huella) en la ficha, la historia, los avisos de un proveedor, un
  cliente y una PO, y lo sin facturar del cliente y del panel; cada fila de las listas y de
  la búsqueda, y cada excepción, sus `razones` (sus hallazgos pendientes, lo más urgente
  primero, con regla, severidad, estado y valores); la ficha, sus `reglas_sin_datos`.
  `consultas.sin_ibanes` enmascara también los IBAN de los valores (F2-F10, K4 los llevan
  enteros), y ahora también las claves de un objeto; `comprobar_v2` mira también las
  claves. `docs/integracion-web.md` lo documenta.
- `tests/test_textos.py` (36 tests): los dos catálogos con las mismas claves y las mismas
  condiciones, ningún texto vacío ni con restos de español (una lista de palabras), cada
  regla, orden, categoría, fuente, calidad, estado, campo, rol y permiso con su texto;
  cada plantilla bien escrita y con claves que su regla escribe en su código (sus literales
  y los de los módulos de `reglas/` que importa); el renderizador; `casos.json` al día (el
  generador en modo comprobar); y la API: los valores en la ficha, las listas, las
  excepciones, los avisos y la historia, y los IBAN de los valores enmascarados desde otro
  origen y en el export. `pyproject.toml` lleva los JSON y el LEEME como datos del paquete
  (Docker instala con pip).

**Desviaciones, y por qué**

1. **Los `motivos` de la prioridad no tienen gemelo estructurado.** Se escriben en cinco
   sitios de `prioridad.py` y se guardan en dos cachés (`factura_estado` y `prioridad`) y
   en sus vistas: un `motivos_datos` pedía una migración y reescribir esas cachés. En su
   lugar, `razones`: los hallazgos de cada fila con sus valores, de los que la app escribe
   el «por qué». Lo que solo dicen los motivos (los puntos, la subida a mano, «vence en
   6 días») lo saca la app de `puntos`, `vencimiento` y `dias_vencida`.
2. **Los valores no se tocan.** Van en la huella: añadirles una clave para distinguir dos
   casos (G3 ambigua y G3 sin casar dan las mismas claves) reabriría hallazgos aceptados.
   Esos dos casos comparten un texto que vale para los dos.
3. **Lo que los valores traen en español no se enseña.** Unos son códigos y se escriben
   con `|codigo` (las marcas de Q3, los niveles de G2 y de G3, las unidades); otros son
   frases (el `motivo` de F8 y de K6, las filas rechazadas de Z2 y X1, lo que falta en D1
   con su número de línea): la plantilla dice lo mismo sin ellas (D1 da cuántas faltan; el
   campo marcado en la ficha dice cuáles).
4. **Las otras facturas van por id** (B2, B3, B4, R5...), no por número: la plantilla dice
   «otra factura de la misma contraparte» y la app enlaza las de `objetivos`.
5. **Los sin_datos sin valores tienen un texto general por regla.** Muchas reglas dan
   sin_datos sin valores (el planning no cubre esos días, no hay planning, la línea no dice
   sus días): el texto nombra las causas posibles en vez de adivinar una.
6. **Importes y horas en formato neerlandés en los dos idiomas** (`€ 1.234,56`, `37,5`),
   como pidió el dueño para el dinero; `|fecha` da `dd-mm-aaaa` también dentro de una
   frase (la forma larga, «16 okt 2026», es de la app fuera de las plantillas).
7. **Los ejemplos de los casos salen de los tests.** Para saber qué valores da cada regla se
   corrió la suite entera con un plugin que apuntaba los valores de cada resultado (no se
   guarda en el repositorio); los ejemplos son esos valores, y el test contra el código
   comprueba que cada clave de una plantilla está escrita en el módulo de su regla.
8. **Test cambiado a propósito:** `test_export_v2_cumple_el_contrato_documentado` buscaba
   el literal «Contrato v2 (2.0)»; ahora usa `consultas.CONTRATO_V2` (sube a 2.1).

**Lo que queda**

- Que una persona de la oficina lea los textos neerlandeses en la app y diga lo que no
  suena natural: se cambian en `nl.json` (y `en.json` si cambia el sentido), se regeneran
  los casos y se vuelve a compilar la app.
- Si algún día hace falta el «por qué» exacto de la prioridad, el gemelo de los motivos
  (desviación 1).

### Paso 15 · pantallas del trabajo diario

Las pantallas con las que administración trabaja cada día, con datos y órdenes de verdad
sobre `/api/v2`: **Overzicht**, **Werklijst**, **Inkomend** y **Uitgaand**, la **ficha de
una factura**, **Uitzonderingen** e **IBAN-controles**. Antes, en esta misma parte, los
textos NL/EN de T entraron en la rama (cherry-pick de `paso15-textos`; los dos choques,
`pyproject.toml` y este registro, se resolvieron dejando las dos cosas: la app construida
en `"bms_agent"` y los catálogos en su propio paquete `"bms_agent.textos"`), y el sustituto
provisional de la base dejó su sitio a los catálogos de verdad.

**Qué se construyó**

- **Los textos de dominio, de los catálogos de Python.** `frontend/src/i18n/domain.ts`
  importa `src/bms_agent/textos/nl.json` y `en.json` (los dos entran en la huella de
  `web/fuente.json`; `frontend/src/i18n/domain/` ya no existe) y da a las pantallas
  funciones (`ruleText`, `findingDetail`, `stateLabel`, `fieldLabel`, `actionText`,
  `errorText`, `verdict`...), nunca la forma del JSON. `frontend/src/i18n/templates.ts` es
  el lenguaje de las plantillas de `textos/LEEME.md` en TypeScript (formatos, transformaciones,
  rutas con puntos, variantes con condiciones y partes, lo que falta), con BigInt y sin
  floats; `templates.test.ts` pinta cada caso de `textos/casos.json` (64 de lenguaje y 301
  detalles, cada variante de cada regla) en los dos idiomas y tiene que dar exactamente el
  texto y lo que falta de la referencia en Python: 738 comprobaciones, todas iguales a la
  primera.
- **Códigos de error estables.** Cada respuesta de error de `/api/v2` (y de la puerta común:
  Host, Origin, el cuerpo de un POST) lleva, junto a `error` en español, un `codigo`
  (`no_autenticado`, `sin_permiso`, `segunda_persona`, `otro_origen`, `origen_no_permitido`,
  `host_no_permitido`, `no_existe`, `conflicto`, `peticion_repetida`, `no_anulable`,
  `no_revisable`, `bloqueo_abierto`, `estado_no_valido`, `campo_no_editable`,
  `campo_de_otro_sistema`, `falta_motivo`, `iban_no_valido`, `orden_desconocida`, `invalido`,
  `tipo_no_admitido`, `demasiado_grande`). Los de las órdenes los lleva cada excepción donde
  nace (un atributo `codigo` en `PermisoDenegado`, `SeparacionDeFunciones`, `Conflicto`,
  `FaltaMotivo`, `NoAnulable`, `NoRevisable`...); `servicios.codigo_de_error` elige el más
  concreto y `servicios.CODIGOS_ERROR` los lista. Sus textos NL/EN están en los catálogos
  (`errores`), y la app los enseña; la frase del servidor solo dentro de «Technische
  details». Documentado en [integracion-web.md](../integracion-web.md) («Los errores»); el
  contrato sigue en 2.1, que ya subió T en este paso (es una clave nueva).
- **Las pantallas** (lo que hay en cada una, en [app-local.md](../app-local.md) §4.1): el
  Overzicht con cuatro tarjetas y «Als eerste»; la Werklijst (lo que pide a una persona,
  fichas por prioridad, buscador, cinco columnas con «Waarom»); Inkomend y Uitgaand (dos
  filtros, buscador, seis columnas); la ficha de factura (qué es, qué está mal y qué hacer,
  y los detalles plegados: campos con su fuente y su calidad, líneas, referencias,
  relaciones, planning, notas, controles sin datos, historia en palabras normales y el
  original); Uitzonderingen con un panel lateral; IBAN-controles con el flujo de siempre.
- **Las órdenes**, todas por `POST /api/v2/acciones` con la `rev` o la huella que se vio:
  `anular_hallazgo`, `firmar_anulacion`, `cerrar_hallazgo`, `marcar_revisada`,
  `devolver_factura`, `anadir_nota`, `crear_excepcion`, `asignar_excepcion`,
  `esperar_externo`, `resolver_excepcion`, `fijar_campo` (con «Nu → Nieuw» antes de
  guardar), `verificar_campo`, `revertir_campo`, `confirmar_relacion`, `rechazar_relacion`,
  `verificar_iban`, `rechazar_iban` y `atestar_iban`, y la descarga del original. Cada una
  pasa por un único diálogo (`ActionDialog`) que dice qué va a pasar, pide lo necesario,
  comprueba lo obvio antes de mandar (un motivo de al menos 10 caracteres para aceptar) y
  enseña el error por su código. Un botón solo sale con su permiso (`lib/actions.ts`).
  Tras una orden se vuelven a leer la ficha, las listas y las insignias del menú.

**La puerta, test por test**

| Lo pedido | Dónde se comprueba |
| --- | --- |
| El renderizador TS da lo mismo que el de Python en cada caso, en NL y EN | `frontend/src/i18n/templates.test.ts` |
| Cada código de error tiene su texto en los dos idiomas; cada excepción con código usa uno de la lista; cada error JSON de `serve.py` lleva su código; los códigos de verdad (401, 403, 404, 409 de rev, 400 sin motivo, 413, 415, 421, otro origen) | `tests/test_codigos_error.py` |
| La app solo manda órdenes de `servicios.ACCIONES`, ninguna paga, aprueba ni presenta, y su tabla de permisos es la de `servicios.ACCIONES` | `tests/test_app_local.py::test_la_app_solo_manda_ordenes_que_existen_y_ninguna_paga_ni_aprueba`, `::test_los_permisos_de_las_ordenes_de_la_app_son_los_de_servicios` |
| Los catálogos entran en la huella y el sustituto ya no está | `tests/test_app_local.py::test_lo_construido_es_lo_que_apunta_fuente_json` |
| Las bloqueadas dicen por qué en neerlandés y en inglés, sin castellano | `e2e/daily.spec.ts` «de geblokkeerde facturen zeggen waarom» |
| Aceptar con motivo funciona y las cuentas cambian; la regla de las dos personas se ve | «accepteren vraagt een tweede persoon…» (B2: Ana es rechazada con `segunda_persona`, Bram da la segunda firma, Ana acepta y las bloqueadas bajan), «een melding accepteren en de uitzondering oplossen» (las excepciones bajan en uno) |
| Marcar como gecontroleerd | «een schone factuur markeren als gecontroleerd» |
| Una `rev` vieja da el aviso de conflicto y no pisa nada | «een verouderde rev geeft de melding…» (Bram cambia la factura por la API mientras Ana edita) |
| Quien solo mira (rol `consulta`) no ve ningún botón de una orden | «wie alleen mag kijken…» (ficha, panel de excepción, IBAN; Importeren no sale en el menú) |
| IBAN: se llama al número de los maestros, el IBAN se teclea (campo vacío), la regla de las dos personas | «IBAN-controles: bellen…» (Ana puso los teléfonos y es rechazada; Bram verifica) |
| Uitzonderingen, Inkomend / Uitgaand, los detalles, el original | «uitzonderingen…», «inkomend en uitgaand…», «de details van een factuur…» (confirmar una relación, descargar el PDF) |
| Ninguna petición fuera de 127.0.0.1, ninguna violación de la CSP ni error en la consola, axe sin problemas serios ni críticos | los vigilantes de `e2e/fixtures.ts` en cada prueba, y `expectAccessible` en cada pantalla y diálogo |

Resultado: Python 3.11, **2484 pasan y 12 se saltan** (2418 de la base, 36 de los textos de
T y 30 de esta parte); los tests tocados, también con Python 3.13 y `-W error` (208
pasan); `npm run typecheck` limpio; vitest, 779 (738 de las plantillas); Playwright, 20
(11 de `daily.spec.ts`), todas sin peticiones fuera de 127.0.0.1, sin violaciones de la
CSP, sin errores en la consola y sin problemas serios de axe.

Capturas de cada pantalla y de los diálogos en NL y EN a 1440×900 en `CAPTURAS_DIR`
(`daily-*.png`); se miraron todas, y también a 1024 px. Lo que se corrigió al mirarlas:
las tarjetas del Overzicht y los datos de la ficha dejaban un hueco gris a 1024 px (ahora
cuatro y cinco por fila a 1440 y de dos en dos más estrecho); la columna «Waarom» quedaba
en dos palabras por línea a 1024 px (anchos de columna más flexibles y un mínimo para la
frase); los botones de «Wijzigen» y «Verifiëren» en cada fila de los campos eran ruido
(ahora un enlace discreto, y verificar solo donde hay una duda); el error de un diálogo
largo quedaba fuera de la vista (se lleva a ella); el texto de un importe desconocido
(«— inclusief btw»); el estado «Wacht op derden» repetido con «Wacht op de leverancier»;
«0 dagen open» («vandaag geopend»); y la palabra: en neerlandés la app dice
«gecontroleerd» y «melding», como los catálogos, no «nagekeken» ni «bezwaar» (dos textos
del catálogo se alinearon también).

**Desviaciones, y por qué**

1. **La Werklijst es «lo que pide a una persona», no solo la prioridad.** Una factura
   normal con un hallazgo pendiente (una relación por confirmar, R5), una excepción abierta
   o campos por verificar también espera a alguien; quedarse solo con la prioridad la
   escondía. La tarjeta «Aandacht nodig» cuenta lo mismo (15 en la base de prueba, con 4
   bloqueadas, 6 urgentes y 13 excepciones abiertas debajo).
2. **El código de error vive en la excepción.** En vez de una tabla en `serve.py`, cada
   excepción dice el suyo donde nace (`codigo = "conflicto"`), y `servicios` elige el más
   concreto mirando la clase y sus padres: una excepción nueva de una orden trae su código
   o cae en el de su familia (`no_existe`, `estado_no_valido`, `invalido`). También lo
   llevan los errores fuera de `/api/v2` (el 404 de `/app/assets/...`): por eso cambió a
   propósito `test_lo_que_no_esta_en_la_lista_blanca_es_un_404`, que comparaba el cuerpo
   entero.
3. **Una excepción se abre en un panel lateral, no en una pestaña.** No es una ficha del
   registro de pantallas (no tiene una lectura propia) y sus órdenes son tres; el panel
   lleva a la factura cuando la hay. En la ficha de factura están las mismas órdenes.
4. **Lo que se ofrece en un hallazgo.** Aceptar solo donde la regla lo admite; dar la
   segunda firma, cuando la pide, como botón secundario; verificar o corregir el campo al
   que apunta solo cuando el problema es su lectura (`dudoso` o `faltante`: Q1, Q2). En los
   demás (un número repetido, un periodo solapado) cambiar el campo no es lo que hay que
   hacer, y el botón confundía.
5. **El IBAN del documento no se cambia ni se verifica desde los campos.** Se enseña («er
   wordt niet naar betaald»); los datos bancarios van por IBAN-controles. Al verificar, el
   número llamado se rellena con el **de los maestros** (no con nada del documento); el
   IBAN va vacío y se teclea, y la app dice si coincide con el encontrado. Rechazar manda el
   IBAN encontrado como el de la cuenta que se rechaza, que no es darlo por bueno.
6. **Lo menos diario se queda en la consola**: imputar una línea a otro Objeto o a una PO,
   dividir, añadir o excluir líneas, anular o fusionar una factura, enlazar dos a mano,
   marcar un pago, subir la prioridad. La consola sigue (`/consola`) y la ficha de la app
   dice todo lo que pasa.
7. **La historia la escribe la app** desde las partes estructuradas de
   `GET /api/v2/facturas/N/historial` (documento, lecturas, eventos de cada hallazgo,
   revisiones, excepciones, notas, cambios de campo de una persona y aperturas del
   original). Los tipos de evento de auditoría del sistema son identificadores en español y
   no se enseñan.
8. **Cambios en piezas de la base:** `useLoad` deja lo que se veía mientras vuelve a leer
   (la pantalla no salta a «Laden…» ni pierde la posición tras una orden); `SummaryGrid`
   va en 4/2/1 columnas en vez de `auto-fit`; `Button` tiene un tamaño `xs` para las
   acciones dentro de una tabla; `SummaryCard` admite un (?) junto al título; se añadió a
   mano el `dialog` de shadcn. Una lista recuerda su filtro y su búsqueda por pestaña
   mientras la app está abierta (`lib/tab-memory.ts`, solo en memoria, se olvida al salir).
9. **Tests de A cambiados a propósito** (`e2e/shell.spec.ts`): la ficha ya no tiene una
   sección «Details» (ahora «Velden»); el botón de una fila lleva el número y la relación
   (se lee el número); y la prueba de la sesión que caduca espera a que el Overzicht, que
   ahora también lee las facturas, termine antes de simular el 401.
10. **Tests de Python cambiados a propósito** (`tests/test_app_local.py`):
    `test_el_paquete_lleva_la_app_y_los_textos` mira los catálogos en
    `"bms_agent.textos"` (es un paquete propio, con `__init__.py`) y no en `"bms_agent"`;
    `test_lo_construido_es_lo_que_apunta_fuente_json` exige ya, sin condiciones, que los dos
    catálogos estén en la huella y que el sustituto no esté.
11. **Una tercera persona de prueba.** `scripts/crear_demo_e2e.py` añade «Cas Consulta» con
    el rol `consulta` a la base recién hecha (no a `bms-agent demo crear`), para probar que
    quien solo mira no ve botones.

**Lo que deben saber las partes siguientes**

- Una pantalla nueva con órdenes: `ActionButton` / `ActionDialog`
  (`components/action-dialog.tsx`) con `action` (el nombre de `servicios.ACCIONES`), los
  `fields` que pide y `data` (lo fijo: ids y `rev`); el título, la descripción y la frase de
  confirmación salen del catálogo; el permiso, de `lib/actions.ts` (si se usa una orden
  nueva, se añade allí: el test lo compara con `servicios.ACCIONES`). Tras una orden,
  `useRefresh().version` cambia: quien lea algo la pone en las dependencias de `useLoad`.
- El «por qué» de una fila es `whyOf(row, lang, t)` (`lib/why.ts`) con su `WhyCell`; un
  estado es `StatusText` con un tono de `components/tones.ts`; un campo se escribe con
  `formatFieldValue` (`lib/field-format.ts`).
- Si cambia un texto de `nl.json` o `en.json`: regenerar los casos
  (`scripts/generar_casos_textos.py`), `npm test` y `npm run build`.

**Lo que falta**

Leveranciers, Klanten, Objecten e Inkooporders (con sus fichas), Kasstroom, Btw,
Importeren y Facturen lezen. Que alguien de la oficina lea los textos neerlandeses en la
app. En el ordenador del dueño, mirar que Edge abre la ventana `--app`.

### Paso 15 · resto de pantallas

La última parte del paso: **todas las pantallas que faltaban**, con datos y órdenes de
verdad sobre `/api/v2`, la **importación desde la app** (con una prueba antes) y las
**pruebas en el navegador de cada pantalla** en los dos idiomas. La consola de antes sigue
en `/consola`, de reserva; nada de lo que había se quitó.

**Qué se construyó**

- **Las pantallas** (qué contesta cada una, en [app-local.md](../app-local.md) §4.2–4.5):
  Leveranciers y Klanten con su ficha (qué es, cinco cifras, lo que necesita atención
  agrupado por factura con un botón para abrirla, y plegado: las facturas abiertas y todas,
  los pagos, el reparto por Object, las cuentas con el teléfono de los maestros, el trabajo
  sin facturar y las relaciones propuestas); Objecten con su ficha (el periodo Deze maand /
  Vorige maand / Dit jaar, opbrengst, kosten y marge, las horas planificadas frente a las
  facturadas, las facturas que piden a una persona y, plegado, las horas por semana, las
  facturas y las PO); Inkooporders con su ficha (waarde, verbruikt, over y la previsión, lo
  que necesita atención y, plegado, sus facturas y sus Objects); Kasstroom (una tabla, sin
  gráficos, y aparte y marcada la estimación del planning); Btw con la ficha del trimestre
  (las cifras, lo que hay que mirar, bajar el werkblad, dejarlo listo o reabrirlo y anotar
  la aangifte que una persona ya presentó); Importeren; Facturen lezen (sin botón para
  leer) e Instellingen (idioma, quién eres con tus permisos en palabras, la empresa y el
  aislamiento para leer, las personas para quien administra y una frase sobre las copias).
  Toda lista, como mucho seis columnas con «Waarom»; toda ficha, en su pestaña.
- **`POST /api/v2/importar`** (`src/bms_agent/importar_web.py`): el fichero va en JSON, en
  base64, como mucho 8 MB (`413 fichero_demasiado_grande` si pasa, sin leer el resto); las
  mismas puertas que una orden (Host y Origin de la app, token, permiso `importar_datos`
  comprobado antes de leer el fichero, con la negativa en la auditoría); la clase se
  reconoce por el contenido (o la elige la persona, o se pide elegir entre las que encajan:
  `400 tipo_ambiguo` con sus `candidatos`); dentro, la misma
  `importadores.registrar.importar_fichero` que la CLI, que ahora acepta el contenido en
  memoria (`contenido=`, también `importadores.banco.importar_extracto`): sin escribir el
  fichero en disco, sin procesos y sin red. `simular` lo deshace todo al acabar. Contesta lo
  que entraría o entró por lote (leídas, aceptadas, nuevas en la tabla principal,
  cambiadas, rechazadas con su fila y su código, cuentas nuevas, avisos), los hallazgos que
  cambian y, en un extracto, los pagos que casan.
- **Lecturas nuevas** (contrato 2.1, solo claves añadidas): `GET /api/v2/importaciones` (la
  historia, las clases que se pueden elegir, el límite y la frescura de cada fuente),
  `GET /api/v2/lectura` (lecturas, documentos, coste medido, la estimación de la siguiente y
  las últimas pasadas, de `extraccion.uso_json`, como `bms-agent coste`, sin red),
  `GET /api/v2/empresa` y `GET /api/v2/aislamiento` (la comprobación del aislamiento por
  papel, sin copiar ningún texto). `GET /api/v2/yo` y `GET /api/v2/personas` dan además los
  `roles` (`permisos.roles_de`); las filas de `proveedores`, `clientes`,
  `ordenes_compra` y `objetos` llevan `razones` (sus hallazgos pendientes, como las de las
  facturas, para «Waarom»). Seis códigos de error nuevos, con sus textos NL/EN:
  `fichero_no_reconocido`, `tipo_ambiguo`, `fichero_no_valido`, `datos_de_prueba`,
  `pide_confirmacion` y `fichero_demasiado_grande`. Todo en
  [integracion-web.md](../integracion-web.md).
- **Las piezas nuevas**: `FactStrip` (las cifras de arriba de una ficha), `AttentionList` e
  `InvoiceAttentionList`, `ProperName` (un nombre de fichero o de acceso directo, que no se
  traduce: va marcado y la comprobación del castellano no lo cuenta), los tipos de lo que
  contestan las lecturas en `lib/api-types.ts`, y en `lib/format.ts` los dólares en
  millonésimas, los trimestres y las fechas tecleadas.

**La puerta, test por test**

| Lo pedido | Dónde se comprueba |
| --- | --- |
| Importar: la prueba dice lo que entraría y no guarda nada (el volcado entero de la base, igual antes y después) | `tests/test_importar_app.py::test_la_simulacion_dice_lo_que_entraria_y_no_guarda_nada` |
| Importar de verdad, la historia, el mismo fichero dos veces | `::test_importar_de_verdad_guarda_queda_en_la_historia_y_no_entra_dos_veces` |
| El permiso, antes de leer el fichero, y su negativa en la auditoría; sin token, 401; sin JSON, 415 | `::test_sin_permiso_es_un_403_antes_de_leer_el_fichero` |
| Otro origen, un origen no permitido | `::test_desde_otro_origen_no_se_importa` |
| El límite de tamaño (del fichero y del cuerpo) | `::test_el_limite_de_tamano_del_cuerpo_y_del_fichero` |
| Un fichero mal hecho (base64, nombre, clase, contenido) y uno que no se reconoce; elegir la clase a mano | `::test_lo_mal_formado_dice_su_codigo_y_no_escribe_nada`, `::test_la_eleccion_explicita_y_un_fichero_que_no_es_de_esa_clase`, `::test_el_nombre_del_fichero_es_solo_un_nombre`, `::test_detectar_el_banco_y_el_yaml_de_po` |
| Una clase ambigua dice entre cuáles elegir | `::test_un_fichero_que_reconocen_dos_clases_pide_elegir` |
| Las lecturas nuevas, los roles y las `razones` de las relaciones | `::test_la_lectura_de_pdf_la_empresa_y_el_aislamiento`, `::test_el_aislamiento_por_papeles_sin_copiar_el_texto`, `::test_el_coste_de_la_lectura_sale_de_las_extracciones_guardadas`, `::test_yo_y_las_personas_llevan_sus_roles`, `::test_las_listas_de_partes_llevan_sus_razones`; que todo está en el contrato, `tests/test_contrato_v2.py` |
| Cada código nuevo tiene su texto y lo usa una excepción con código | `tests/test_codigos_error.py` (con `importar_web`, `almacen` e `importadores.planning` en la lista de módulos) |
| La app solo manda órdenes que existen; ninguna paga, aprueba, presenta ni crea una factura; anotar la aangifte solo desde la ficha del trimestre | `tests/test_app_local.py::test_la_app_solo_manda_ordenes_que_existen_y_ninguna_paga_ni_aprueba` |
| Cada lista y su ficha en NL y EN, con sus detalles abiertos | `e2e/screens.spec.ts` «de fiches…» |
| Kasstroom: una tabla, sin gráficos, la estimación aparte | «kasstroom…» |
| Btw: el werkblad es el CSV del trimestre; reabrir, dejar listo; quien lo dejó listo no anota la aangifte (`segunda_persona`); otra persona sí | «btw…» |
| Importar: un fichero que no se reconoce; la prueba dice «1 nieuw» y la base no cambia; confirmar aparte; la historia; el mismo fichero otra vez; el cliente nuevo en Klanten | «importeren…» |
| Facturen lezen: lo gastado y cómo se empieza, sin botón que lo lance | «facturen lezen…» |
| Instellingen, y quien solo mira (sin Importeren, sin botones del btw, sin personas) | «instellingen…», «wie alleen mag kijken…» |
| A 1024 px: sin desplazamiento horizontal de la página, y las tablas de Objecten e Inkooporders caben en su caja | «op 1024 px…» |
| En cada pantalla: solo 127.0.0.1, ninguna violación de la CSP, ningún error en la consola, axe sin problemas serios ni críticos y **ninguna palabra castellana** | los vigilantes de `e2e/fixtures.ts` y `expectNoSpanish`, también en cada pantalla de `e2e/shell.spec.ts` |

Resultado: Python 3.11, **2505 pasan y 12 se saltan** (21 más que en la parte anterior: 15
de `tests/test_importar_app.py` y los de los códigos nuevos); los tests tocados
(`test_importar_app`, `test_codigos_error`, `test_contrato_v2`, `test_app_local` y los de la
demo), también con Python 3.13 y `-W error` (136 pasan); `npm run typecheck` limpio;
vitest, **793**; Playwright, **28** (8 de `e2e/screens.spec.ts`), todas sin peticiones fuera de
127.0.0.1, sin violaciones de la CSP, sin errores en la consola, sin problemas serios de axe
y sin castellano en ninguna pantalla.

Capturas de cada pantalla, ficha y diálogo, en NL y EN, a 1440×900, en `CAPTURAS_DIR`
(`<idioma>-<pantalla>.png`; las del trabajo diario siguen como `daily-*.png`), y a 1024 px
(`nl-*-1024.png`). Se miraron todas. Lo que se corrigió al mirarlas:

- en una ficha de proveedor, los avisos de la misma factura salían sueltos, cada uno con su
  botón: ahora van juntos, con un botón «Factuur X openen» por factura;
- la lista de Objecten seguía el orden de los códigos: ahora va lo más urgente arriba, como
  las demás;
- las semanas del planning decían `2026-W31`: ahora «31 · 2026»;
- en la ficha de un Object, los avisos de sus facturas podían ser decenas: se ven cinco y
  «en nog N»; el margen salía alineado a la derecha entre cifras alineadas a la izquierda;
- las fechas de los diálogos y de Importeren salían en el formato del navegador
  (`mm/dd/yyyy`): ahora se teclean como `dd-mm-jjjj` (abajo, desviación 6);
- los catorce permisos de Instellingen ocupaban media pantalla: van plegados, con su número;
- Importeren decía «Ingelezen» en la prueba, cuando aún no había entrado nada (ahora solo
  después), «1 nieuwe bankrekeningen» y «1 van 1 regels» (ahora en singular), la historia
  era más ancha que lo demás (ahora todo al mismo ancho, como Kasstroom y Facturen lezen) y
  partía el nombre del fichero por cualquier letra;
- los avisos del importador (en castellano, para el soporte) van plegados como «Technische
  details»;
- en el trimestre, una factura que no entra en las cifras salía dos veces, una sin texto;
  presentado, el paso «Klaarzetten» dice quién lo dejó listo;
- en Facturen lezen, «Laatst gelezen» daba mañana: los datos de prueba leían una factura de
  hoy el día siguiente (ahora nunca después de hoy, como su llegada; `demo.py`);
- a 1024 px, Objecten e Inkooporders desplazaban la tabla y apretaban el nombre: dejan la
  columna que se deduce de las otras (abajo, desviación 8).

**Desviaciones, y por qué**

1. **«Waarom» en las relaciones viene de la API.** Las filas de proveedores, clientes, PO y
   Objects llevan `razones`, como las facturas, para escribir la frase con los catálogos y
   no inventarla en la app. Es una clave nueva (el contrato sigue en 2.1).
2. **Anotar la aangifte (`btw_anotar_presentacion`) sí está en la app.** Deja constancia de
   lo que una persona ya presentó en el portal; no presenta nada. Por eso cambió a propósito
   `test_la_app_solo_manda_ordenes_que_existen_y_ninguna_paga_ni_aprueba`: ahora exige que
   la app use `btw_lista_para_revision`, prohíbe cualquier orden que pague, apruebe,
   presente, cree una factura o marque una pagada, y permite `btw_anotar_presentacion` solo
   en `src/screens/vat-quarter.tsx`.
3. **Importar un fichero suelto sin pasar por el buzón.** El buzón sigue siendo el camino de
   `importar.bat`; desde la app el fichero llega en la petición y no se mueve ni se guarda.
   Lo importado queda igual que desde la CLI (la misma función, la misma auditoría).
4. **Facturen lezen no lanza nada.** Leer cuesta dinero y necesita red; la app no tiene red.
   La pantalla explica el acceso directo y enseña lo gastado de lo que ya guarda el almacén.
5. **Instellingen solo cambia el idioma.** La empresa, las personas y las copias se leen; se
   cambian con `empresa.bat`, `persona.bat` y `copia.bat` (sus nombres van marcados como
   nombres propios, sin traducir).
6. **Las fechas se teclean (`dd-mm-jjjj`) en vez del selector del navegador**, también en
   los diálogos del trabajo diario (el seguimiento de una excepción, una fecha de un campo):
   el selector de Chromium salía como `mm/dd/yyyy` y el resto de la app escribe las fechas a
   la neerlandesa. Se acepta también `d-m-jjjj`, `d/m/jjjj` y la ISO; la app manda ISO.
7. **El panel de la pestaña se puede enfocar** (`tabIndex={0}` en el componente del dueño,
   anotado arriba del fichero): una pantalla sin botones, como Facturen lezen, no se podía
   bajar con el teclado (axe: `scrollable-region-focusable`).
8. **Columnas que se deducen, solo desde 1280 px** (`wideOnly` en `DataTable`): Kosten en
   Objecten (opbrengst menos marge) y Waarde en Inkooporders (verbruikt más over).
9. **La comprobación del castellano.** `expectNoSpanish` busca en el texto visible de cada
   pantalla una lista de palabras castellanas que no son neerlandesas ni inglesas; los
   nombres propios (`data-proper-name`) no cuentan. Se añadió también a cada pantalla de
   `e2e/shell.spec.ts`.
10. **Ficheros de prueba para importar.** `scripts/crear_demo_e2e.py` deja en la carpeta de
    la base de prueba `exact-debiteuren-nieuw.csv` (los clientes de prueba más «Demo
    Nieuwbouw BV», con la marca de prueba) y `notities.txt` (que no es nada).
11. **`placeholder.tsx` se quitó**: ya no queda ninguna pantalla por llenar.

**Lo que falta**

Que alguien de la oficina lea los textos neerlandeses en la app y diga lo que no suena
natural. En el ordenador del dueño, mirar que Edge abre la ventana `--app`. Quedan para la
consola y la CLI las órdenes menos de cada día ([app-local.md](../app-local.md) §8).

### Paso 15 · alertas con el componente Status

**El dueño eligió cómo se ven las alertas** («Asi quiero las alertas»): su componente
**Status** (una pastilla tintada y redondeada con un punto de color que late y, siempre, su
texto). Ahora **todo estado de la app** sale con él: las prioridades, el pago, el control,
la gravedad y el estado de cada aviso, lo que dice el sistema de una factura, la calidad de
un campo, las cuentas del banco, la excepción, las relaciones y los turnos, el aislamiento,
la frescura de los datos, el BTW y su plazo, las PO, las importaciones y la marca de prueba
de la cabecera. Las etiquetas con forma de la opción B (`PriorityPill`), los textos con
punto (`StatusText`), la tabla de tonos (`tones.ts`) y los colores sueltos de estado se
quitaron. La tabla entera, con su texto NL/EN, la variante y si late, está en
[app-local.md](../app-local.md) §4.6.

**Qué se construyó**

- **`frontend/src/components/ui/status.tsx`**: el código del dueño, en la ruta de shadcn.
  Solo cambia, y lo dice arriba del fichero: el **color del texto** de `success`, `warning`
  e `info` (green-800, orange-800 y blue-700 en vez de green-600, orange-600 y blue-600,
  que no llegaban a 4,5:1) y `motion-reduce:before:animate-none` en el punto. El tinte, el
  borde, el punto y las clases `dark:` son los suyos.
- **`frontend/src/components/status-pill.tsx`**: la única pieza que decide la variante y el
  latido de cada estado (`STATUS_RULES`, por grupos con los valores tal como los manda la
  API y los nombran los catálogos) y su texto (los catálogos de Python para lo del
  dominio; `i18n/nl.ts` y `en.ts`, `status`, para lo demás). Las pantallas dicen el grupo y
  el valor; ninguna elige un color. Late **solo** lo que pide hacer algo ya: bloqueada,
  urgente, una cuenta por verificar y el aislamiento que falla, falta o es viejo.
- **La dependencia `radix-ui` 1.6.7**, fija, con `package-lock.json` y `npm ci` limpio:
  es la versión cuyos `@radix-ui/*` son los mismos que ya estaban (28 paquetes nuevos en
  el lockfile, ninguno anidado, ninguno cambiado); se queda el import del dueño
  (`import { Slot } from "radix-ui"`) y lo construido no crece (vendor en gzip: 152.610
  bytes antes, 152.488 después). Los 278 paquetes del lockfile se publicaron antes del
  5 oct 2026 (`scripts/check-lock-age.mjs 2026-10-19`); `npm audit --omit=dev`, nada.
- **Lo que no estaba en el diseño del dueño** (las pantallas de la parte B2), con la misma
  lógica: el plazo del BTW («Nog 12 dagen», naranja a 14 días o menos; rojo pasado y sin
  aangifte) en Btw, la ficha del trimestre y el Overzicht; la configuración del BTW sin
  confirmar con el asesor (`btw_config`) y la empresa incompleta (`empresa`); las señales
  de una PO junto a «Over» y «Verwachting» de su ficha (`po_senal`, de sus avisos abiertos
  P4-P10); una PO cerrada en la lista; la prueba de una importación (`importar_prueba`:
  con filas rechazadas, con avisos o en orden) y su resultado y su historia
  (`importacion`); la frescura de cada fuente; el aislamiento por papeles en Instellingen;
  el pago y las cuentas en las fichas de relaciones y Objects.
- **`GET /api/v2/aislamiento`: cada papel lleva su `estado`** (`correcto`, `falla`,
  `sin_comprobar` o `caducada`; contrato 2.1, clave nueva). La app decía «Probleem» sin
  saber cuál; ahora la pastilla dice «Afscherming mislukt», «Afscherming niet
  gecontroleerd» o «Controle te oud». Sale solo de cómo empieza cada problema que escribe
  `aislamiento.problemas_de` (`app_local.estados_de_papeles`): el detalle de una prueba que
  falla viene de un fichero que se puede escribir y no se copia. Un problema que no nombra
  un papel conocido deja a todos en `falla`, como la banda roja.
- **Las pruebas**: `src/components/status-pill.test.ts` (cada valor de cada grupo de los
  catálogos tiene su variante, la que pidió el dueño; solo laten los siete que piden algo;
  cada uno tiene su texto en los dos idiomas; un valor desconocido va en gris, quieto y con
  texto; la pastilla es la del dueño con `data-variant`, punto y etiqueta);
  `src/screens/status-states.test.ts` (los estados que derivan las pantallas: el plazo del
  BTW, la prueba de una importación, las señales de una PO, el aislamiento);
  `e2e/status.spec.ts` (en la Werklijst y en Inkomend solo laten Geblokkeerd y Urgent; en
  IBAN-controles late lo que está por verificar y nada más; la marca de prueba no late; con
  «reducir movimiento» no late nada; el aislamiento por papeles, con una respuesta cambiada
  en la prueba porque aquí no hay instalación nativa) y, en **cada pantalla**,
  `expectAccessible` falla con cualquier falta de contraste de axe (de cualquier grado) y
  mide el contraste de **cada pastilla** en el navegador (`expectStatusContrast`). Se
  comprobó que las pruebas fallan con los tonos del dueño: construida con green-600 y
  orange-600, axe para la prueba en IBAN-controles (`color-contrast`, serio).
  `tests/test_importar_app.py::test_el_estado_de_cada_papel_sale_del_principio_del_problema`
  y el de `GET /api/v2/aislamiento`, para el `estado`.

**El contraste, medido** (Chromium, el tinte compuesto sobre cada fondo de la app; mínimo
y máximo): `default` 5,73:1 (sin cambio); `success` green-800 5,32–6,49 (green-600 daba
2,40–2,93); `warning` orange-800 5,43–6,62 (orange-600, 2,64–3,22); `info` blue-700
5,00–6,07 (blue-600, 3,84–4,66); `error` `--destructive` 5,21–6,39 (sin cambio).

**Desviaciones, y por qué**

1. **El mismo mapa que el fichero de diseño del dueño.** Otra parte aplicó esta integración
   sobre las pantallas del trabajo diario (364ec06) para el fichero de diseño; su parche se
   aplicó aquí (con `git apply --3way`) y la variante y el latido de cada estado son los
   suyos. Con él vienen dos cambios de colocación: lo que dice el sistema de una factura va
   ahora en su pastilla junto a «Wat aandacht nodig heeft» (antes, en gris bajo «Controle»),
   y en las tarjetas del Overzicht la fila que pide atención (bloqueadas, vencido, el plazo)
   lleva la pastilla en lugar de su etiqueta en color.
2. **Las señales de una PO llevan un texto corto** («Bijna op», «Eerder op»,
   «Op, nog gefactureerd»), no el nombre de su regla: van entre las cifras de la ficha y el
   nombre entero, con qué hacer, está justo debajo, en sus avisos. Una por cifra, la más
   seria.
3. **Las cifras siguen en el color de «tarde»** (un importe vencido, un margen negativo, lo
   que queda de una PO gastada): la cifra es el texto. También los avisos de error de un
   formulario. Un estado en palabras va siempre en la pastilla.
4. **Facturen lezen no lleva pastilla**: `GET /api/v2/lectura` solo da las pasadas que ya
   guardaron sus lecturas (todas terminadas), sin errores ni una en curso. El grupo
   `lectura` está en la tabla para cuando la API lo diga.
5. **La marca TESTGEGEVENS de la cabecera** es la pastilla `warning` (naranja, sin latir),
   sin el icono del matraz; la banda amarilla que pone el servidor no cambia.
6. **«Let op:» / «Note:» fuera** de las dos frases que ahora llevan su pastilla delante
   (la stand del Overzicht y la configuración del BTW): lo dice la pastilla.

**Mirado en las capturas** (`CAPTURAS_DIR`: las 109 de antes y 4 nuevas, `*-status-*`; 113):
cada pantalla, ficha y diálogo en NL y EN a 1440×900 y las de 1024 px. Lo que se corrigió:
la etiqueta «Probleem» del aislamiento (no decía qué), las frases con «Let op:» repetido
junto a la pastilla, y el plazo del BTW que solo decía «Termijn dichtbij» (ahora los días).

**Resultado**: Python 3.11, **2506 pasan y 12 se saltan** (uno nuevo); con Python 3.13 y
`-W error`, `test_importar_app`, `test_app_local` y `test_contrato_v2` (80 pasan);
`npm run typecheck` limpio; vitest, **805**; Playwright, **31** (3 de `e2e/status.spec.ts`),
sin peticiones fuera de 127.0.0.1, sin violaciones de la CSP, sin errores en la consola,
sin problemas serios de axe ni ninguna falta de contraste, y sin castellano.

**Lo que falta**: que el dueño vea las pastillas en su pantalla (los tonos se oscurecieron
para leerse). La insignia de IBAN-controles cuenta los avisos de IBAN abiertos (`activos`
de la categoría `iban` del panel) y la pantalla agrupa por cuenta, así que puede decir 3
con una sola tarjeta; no es de esta parte.

### Paso 15 · correcciones de la revisión

La revisión del paso 15 (revisores y orquestador) dejó **26 hallazgos**. Se miraron todos,
reproduciéndolos (un script, una captura o una prueba que fallaba antes) y **todos eran de
verdad**; los 26 se corrigieron, cada uno con una prueba que falla antes y pasa después
cuando se puede (las de redacción y aspecto, mirando las capturas nuevas). Uno se corrigió
de otra forma que la propuesta (los nombres de los accesos directos, abajo, desviación 4).

| # | Hallazgo | Qué se hizo | Dónde se comprueba |
| --- | --- | --- | --- |
| 1 | **Una bomba de YAML** (470 bytes, 5,4 GB y 68 s) en `POST /api/v2/importar`, también simulando | El cargador de la hoja de PO (`importadores/ordenes.py`, `_Cargador.compose_node`) rechaza **anclas y alias** antes de construir nada y no anida más de `MAX_PROFUNDIDAD` (12) niveles; `str(entrada)` de una fila que no es un mapa se recorta | `tests/test_importar_app.py::test_un_yaml_con_alias_es_un_400_rapido_y_no_una_bomba` (la bomba de 8 niveles es un 400 en menos de 5 s, por detección y eligiendo la clase), `::test_un_yaml_muy_anidado_se_rechaza_sin_agotar_la_pila` |
| 2 | Un fichero roto (un campo de CSV de más de 128 KB, un YAML de 5.000 niveles) **cortaba la conexión** sin respuesta | `importar_web.detectar` e `importar` convierten `csv.Error`, `RecursionError`, `UnicodeError`, `SyntaxError` (el `ParseError` de XML) y `yaml.YAMLError` en `FicheroNoValido`; `_importar_v2` tiene un último `except Exception`: 400 `fichero_no_valido` sin el texto de la excepción, y al registro solo su clase | `::test_un_fichero_que_rompe_el_lector_es_un_400_y_no_un_corte`, `::test_un_error_inesperado_del_lector_es_un_400_sin_su_texto` |
| 3 | El token, en un `<input type=password>` dentro de un `<form>`: **Edge podía ofrecer guardarlo** en su gestor de contraseñas | Sin `<form>` ni campo de contraseña: texto tapado con `-webkit-text-security: disc`, `autocomplete="one-time-code"`, Intro para entrar y el campo vacío antes de comprobar el token; [app-local.md](../app-local.md) §3 dice que se diga que no si Edge ofrece guardarlo | `e2e/shell.spec.ts` «la entrada…» (ningún `form` ni `input[type=password]`, el `autocomplete` y el tapado; Intro entra) |
| 4 | El Overzicht **no decía un plazo del BTW pasado** sin aangifte (`proximo_plazo` salta al trimestre siguiente) | La tarjeta del BTW pone primero «Aangifte te laat» con la pastilla `plazo_vencido` y los trimestres (`overdueQuarters`, de `por_presentar` y `plazos_pasados`); el tipo de `plazos_pasados` es `string[]` | `src/screens/screens.test.ts` («un plazo pasado sin aangifte…», con lo que da el panel el 5 de noviembre); `e2e/status.spec.ts` «un plazo del btw pasado…» (el panel de ese día, en la respuesta) |
| 5 | **e2e inestable**: axe medía el contraste en mitad del fundido de la pestaña | `settled()` en `e2e/fixtures.ts`: ninguna animación con fin en marcha, el contenido de la pestaña entero y a opacidad 1 y ninguna opacidad a medias durante tres cuadros, **sin esperas fijas**; antes de axe, de cada captura, tras `nav()` y al cambiar de idioma (se quitaron los `waitForTimeout`). El fundido respeta además `prefers-reduced-motion` | La pasada entera con la suite de Python corriendo a la vez (abajo) |
| 6 | **Tailwind leía ficheros fuera de la huella** (pruebas, `e2e/`, scripts): una clase allí cambiaba el CSS sin cambiar `fuente.json` | `src/index.css`: `@import "tailwindcss" source(none)` y `@source` solo para `src` (sin `*.test.ts(x)`) e `index.html`; `scripts/tailwind-fuentes.mjs` saca con el escáner de Tailwind lo que lee, y `fuente.mjs` no escribe ni da por buena la huella si algo queda fuera de `build-inputs.json` | `scripts/tailwind-fuentes.test.mjs` (falla con el `index.css` de antes: lo comprobé); `tests/test_app_local.py::test_tailwind_solo_lee_lo_que_cubre_la_huella`. El CSS construido no perdió ninguna clase |
| 7 | Sin lo construido (`/app` da 503), **los lanzadores fallaban** sin abrir nada, aunque `/consola` funcionaba | `windows/iniciar.ps1` y `docker/iniciar.ps1` esperan a `/consola`; `Direccion-De-La-App` (en los dos `comun.ps1`) abre `/app` si da 200 y, si no, lo dice y abre `/consola` | `tests/test_app_local.py::test_sin_la_app_construida_el_lanzador_abre_la_consola` (Windows y Docker); los de `test_entorno_local.py` y `test_instalacion_nativa.py` cambian (abajo) |
| 8 | Después de la prueba, cambiar el día de exportación o la confirmación **importaba algo no probado** | La prueba guarda lo que probó (`TriedWith`: clase, día, confirmación) y la importación de verdad manda **eso**; cambiar el día, la clase o la confirmación borra la prueba | `e2e/screens.spec.ts` «importeren…» (otra fecha borra la prueba y el botón; lo que se manda de verdad es lo probado) |
| 9 | **IBAN-controles se contradecía**: «Telefonisch geverifieerd» junto a «nog niet bevestigd», con el botón de llamar otra vez | `accountStep`: «nog niet bevestigd» solo sin verificar; verificada con un F2 abierto, «Wat nog moet: … zet de rekening in Exact en importeer de leveranciers opnieuw»; ya no se ofrece llamar. El subtítulo de la pantalla dice «Nieuwe of gewijzigde bankrekeningen, en wat er nog moet gebeuren» | `screens.test.ts` («lo que falta de una cuenta…»); `e2e/daily.spec.ts` «IBAN-controles…» (después de verificar) |
| 10 | **El punto latía en todas partes** (10 pastillas en la Werklijst, 6 en el Overzicht) | `PingScope` en `status-pill.tsx`: `DataTable` y `SummaryCard` van quietos; `Screen calm` en el Overzicht y las fichas de relaciones, Objects y PO; la Werklijst deja latir solo lo **bloqueado**; late la cabecera de la ficha de una factura | `status-pill.test.ts` («late en un solo sitio por pantalla…»); `e2e/status.spec.ts` «un solo sitio late por pantalla…» (el Overzicht y siete listas sin latido; la ficha de un proveedor, quieta; la de una factura bloqueada, una) |
| 11 | **El mismo problema en dos colores** (P5 «Bijna op» naranja y su aviso azul), «Termijn dichtbij» frente a «Nog 12 dagen» | `po_senal` toma el color de la gravedad de su aviso (P5, P7, P8, P9 info; P4, P6, P10 warning); el plazo cercano dice los días también en el Overzicht. KT-202608 «Urgent» con el pago «Vervallen» en rojo se queda: son dos preguntas distintas (cuánto corre y si está pagada), y la regla está en la tabla de [app-local.md](../app-local.md) §4.6 | `status-states.test.ts` (cada señal con el color de su gravedad), `status-pill.test.ts` (la tabla) |
| 12 | **La navegación** a 1024 × 768: el + bajo el …, pestañas cortadas sin aviso, Instellingen fuera de la vista | Solo las pestañas se desplazan (el + y el … van fuera de la tira); un fundido en el borde dice que hay más (`tabs-fade-left/right`); la barra lateral no esconde su barra de desplazamiento y va más junta con 820 px de alto o menos (`@custom-variant short`) | `e2e/shell.spec.ts` «a 1024 px…» (Facturen lezen e Instellingen dentro de los 768 px; + antes de …, también con siete pestañas; el fundido; la pestaña activa entera) |
| 13 | «Blokkeert / Houdt vast / Waarschuwt» no se explicaban | Las etiquetas del catálogo dicen lo que hacen: «Blokkeert de factuur», «Wacht op controle», «Alleen een waarschuwing» (y en inglés «Blocks the invoice», «Waits for a check», «Warning only»); al pasar el ratón, su `significa` | Capturas (`daily-nl-invoice-blocked`, `nl-purchase-order`) |
| 14 | «Terugsturen» no decía qué ni a quién | La orden es «Opnieuw laten bekijken» / «Ask for another look» (lo que hace: la revisión queda devuelta), y su resultado «Opnieuw te bekijken» / «Needs another look» | Capturas; `e2e/daily.spec.ts` (los botones de quien solo mira) |
| 15 | Los diálogos **decían lo mismo dos veces** y preguntaban «Doorgaan?» | `dialogTexts`: la frase de la pantalla **o** la del catálogo, no las dos; los 33 `confirmar` de los catálogos ya no acaban en «Doorgaan?» / «Continue?»; aparte, en una caja, solo lo que no se deshace (`btw_anotar_presentacion`) | `screens.test.ts` («lo que dice el diálogo…», con los catálogos); `e2e/daily.spec.ts` (sin «Doorgaan?») |
| 16 | **Castellano en la pantalla**: `empresa.bat`, `persona.bat`, «BMS Finanzas - Leer facturas», la frase del servidor en «Technische details», `exact-facturas_venta.csv` | Instellingen y Facturen lezen describen sin nombrar el `.bat` ni el acceso directo; «Technische details» enseña solo el estado y el código; los avisos del importador se cuentan sin enseñarlos; los ficheros de la base de prueba se llaman en neerlandés (`exact-verkoopfacturen.csv`, `exact-leveranciers.csv`…; `demo.py`); `ProperName` se quitó | `e2e/screens.spec.ts` («facturen lezen…»: ni «Finanzas» ni `.bat`; «importeren…»: los detalles son `400 fichero_no_reconocido`); `expectNoSpanish` cuenta también «finanzas» |
| 17 | El euro se separaba de su importe al partir la línea | Espacio que no se parte (U+00A0) entre `€` y la cifra, antes de `%` y tras `$`, en `lib/format.ts` y en las dos implementaciones de las plantillas (`templates.ts` y `bms_agent.textos`); `casos.json` regenerado | `format.test.ts` («el euro y la cifra no se separan…»), `tests/test_textos.py::test_dinero`, `templates.test.ts` contra los casos |
| 18 | **Dos filas iguales** (JV-2026-006 dos veces) sin nada que las distinga | `lib/twins.ts`: «1 van 2» / «2 van 2» junto al número en la Werklijst, Inkomend, Uitgaand, Uitzonderingen y las facturas de una ficha; «Als eerste» junta las del mismo número («2 facturen met dit nummer») y enseña cinco cosas distintas | `src/lib/twins.test.ts`; `e2e/daily.spec.ts` (cinco números distintos en «Als eerste»; «1 van 2» y «2 van 2» en la Werklijst) |
| 19 | «€ 0,00 open» para quien solo tiene una factura en USD | Las filas de proveedores y clientes llevan `sin_importe` (contrato 2.1, clave nueva); la lista enseña «—» y «+ 1 factuur niet in euro» | `tests/test_importar_app.py::test_las_listas_de_partes_llevan_sus_razones` (Demo Global Guarding: 0 en euros y 1 fuera); captura `nl-providers` |
| 20 | Inkomend / Uitgaand, **tres pastillas por fila** y otros filtros | Una pastilla por fila (la prioridad); el pago y el control en texto gris; fichas como las de la Werklijst (Alle, Vervallen, Openstaand, Controle nodig, Betaald) | `e2e/daily.spec.ts` «inkomend en uitgaand…» (cada fila, una pastilla como mucho; las fichas) |
| 21 | «Nog te ontvangen van leveranciers» con un importe negativo | «Facturen van leveranciers die nog komen» / «Provider invoices still to come» | Captura `en-cash-flow` |
| 22 | Textos rígidos: Q2 («Met twijfel gelezen…: totaal»), P10, «De controles daarna: De controles…», la PO en «Over» y la hoja titulada «Uitzondering 11» | Q2: «Het veld totaalbedrag is nog door niemand met het origineel vergeleken» (y en plural con dos o más; `codigos.total_cent` es «totaalbedrag»; un caso nuevo en `generar_casos_textos.py`); P10 «Verwacht meer dan de PO-waarde»; «Daarna: de controles blijven hetzelfde.»; la PO con su cliente o proveedor; la hoja con su asunto | `tests/test_textos.py` (los casos, también la variante nueva); `e2e/daily.spec.ts` (el título de la hoja no es «Uitzondering N») |
| 23 | «Geld binnen · Uitgaand →» se leía como una contradicción | «Verkoopfacturen →» / «Sales invoices →» y «Inkoopfacturen →» / «Purchase invoices →» | `e2e/daily.spec.ts` (los dos enlaces) |
| 24 | Formatos: fechas en prosa en una tabla, un IBAN sin agrupar, «niets» como saldo | `dd-mm-jjjj` en «Laatste leesrondes»; las cuentas propias en grupos de cuatro; el saldo cero es «€ 0,00» | `screens.test.ts` (`balanceText(0)`); capturas `nl-read-invoices`, `nl-settings`, `nl-vat` |
| 25 | **La segunda firma**: se dejaba mandar una aceptación segura de fallar, con un error «o esto, o lo otro» | La ficha de una factura trae las firmas vigentes de cada aviso (`firmas`: para quién, de quién, el plazo y la caducidad; contrato 2.1; `hallazgos.firmas_vigentes`, que usa también la orden); sin la suya, el diálogo **no deja mandar** y dice que se pida «Tweede handtekening geven»; con ella, de quién es y el mismo plazo. `segunda_persona` dice para cada orden cuál de los casos es | `tests/test_servicios.py::test_la_ficha_dice_que_segundas_firmas_hay_para_quien`; `e2e/daily.spec.ts` «accepteren vraagt een tweede persoon…» (botón desactivado y el aviso; Ana no está en «Voor wie»; con la firma de Bram, su nombre) y «IBAN-controles…» y `screens.spec.ts` «btw…» (el mensaje de cada caso) |
| 26 | **Las clases `dark:` del componente Status se aplicaban en un Windows en modo oscuro** (texto -400, menos de 2:1; del orquestador y del fichero de diseño) | `@custom-variant dark (&:where(.dark, .dark *))` en `src/index.css`; la nota de `status.tsx`, corregida | `tests/test_app_local.py::test_el_css_construido_no_cambia_con_el_modo_oscuro_del_sistema` (ningún `prefers-color-scheme` en el CSS construido); `e2e/status.spec.ts` «con el modo oscuro del sistema…» (axe y cada pastilla en el Overzicht, la Werklijst, IBAN-controles y una factura) |

**Tests que cambian, y por qué** (cambian a propósito; nada se quitó):

- `tests/test_entorno_local.py::test_iniciar_con_demo_usa_la_base_de_prueba_y_la_rehace` y
  `tests/test_instalacion_nativa.py::test_iniciar_comprueba_y_abre_la_consola_solo_en_127_0_0_1`:
  el lanzador espera a `/consola` y abre `Direccion-De-La-App` (hallazgo 7).
- `tests/test_textos.py`: `dinero` y `tarifa` llevan el espacio que no se parte (17).
- `src/components/status-pill.test.ts` y `src/screens/status-states.test.ts`: las señales
  de una PO con el color de la gravedad de su aviso (11).
- `src/lib/format.test.ts` y `src/screens/screens.test.ts`: el espacio que no se parte; el
  saldo cero es «€ 0,00» (17, 24).
- `e2e/`: lo que dicen ahora los diálogos (sin «Doorgaan?»; el mensaje de cada caso de
  `segunda_persona`), las fichas de Inkomend y Uitgaand en vez de los desplegables, que en
  la Werklijst solo late lo bloqueado y en Inkomend nada, el texto de Facturen lezen, el
  botón de entrar (`#login-submit`), y el acceso a una ficha sin «Doorgaan?».

**Desviaciones, y por qué**

1. **Las señales de una PO no siguen el color que pidió el dueño** («casi agotada» naranja,
   «por encima de su valor» rojo): llevan el de la gravedad de su aviso, porque con el suyo
   el mismo aviso salía en dos colores en la misma ficha. Un aviso, un color, en toda la
   app (§4.6).
2. **En Inkomend y Uitgaand el pago y el control van en texto gris**, no en su pastilla:
   una pastilla de color por fila (la prioridad) es lo que pide «minimalista». En la ficha
   de la factura siguen con la suya.
3. **El latido, en un solo sitio por pantalla.** La regla del dueño (late lo bloqueado y lo
   urgente) sigue en `STATUS_RULES`; `PingScope` decide además dónde: en las listas y las
   tarjetas, nada; en la Werklijst, lo bloqueado; en la cabecera de una factura, lo suyo.
4. **Los accesos directos y los `.bat` siguen en castellano** (son de la instalación, para
   el dueño, y comparten el prefijo «BMS Finanzas - » con las reglas del cortafuegos):
   cambiarlos era del paso 14. La app ya no los nombra: describe qué hacer.
5. **Contrato 2.1, dos claves más** (`firmas` en cada hallazgo de la ficha y `sin_importe`
   en las listas de proveedores y clientes), con [integracion-web.md](../integracion-web.md):
   el contrato sigue en 2.1 porque el paso aún no ha salido.
6. **Los catálogos cambian algunos textos** (las tres gravedades, devolver, P10, Q2,
   `total_cent`, los `confirmar` sin «Doorgaan?»): los ve solo la app (la CLI y la
   auditoría usan el castellano), y `casos.json` se regeneró.

**Mirado en las capturas** (`CAPTURAS_DIR`, cada pantalla, ficha y diálogo en NL y EN a
1440×900, las de 1024 px y las nuevas: `nl-tabs-1024`, `nl-dark-overview`,
`nl-overview-vat-overdue`, `daily-nl-iban-verified`, `daily-nl-accept-signed`). Lo que se
corrigió al mirarlas: el aviso de la segunda firma iba debajo de los campos (ahora arriba,
lo primero), la etiqueta corta de P10 en la ficha de una PO decía aún «Verwacht boven de
PO» (ahora «Meer dan de PO-waarde»), «+ 1 factuur niet in euro» se partía en tres líneas
(ahora en una), los dólares de Facturen lezen llevaban un espacio normal, y la pastilla del
plazo pasado («Termijn voorbij, geen aangifte vastgelegd») no cabía en la tarjeta del BTW y
empujaba las cifras fuera: ahora dice «Aangifte te laat» / «Return overdue», en todas partes.

**Resultado**: Python 3.11, **2515 pasan y 12 se saltan** (9 más: 4 de
`tests/test_importar_app.py`, 4 de `tests/test_app_local.py` y 1 de `tests/test_servicios.py`);
con Python 3.13.16 y `-W error`, los tocados (`test_importar_app`, `test_textos`,
`test_servicios`, `test_entorno_local`, `test_instalacion_nativa`, `test_contrato_v2` y
`test_app_local`: 494 pasan, 7 se saltan); `npm run typecheck` limpio; vitest, **819** (11
ficheros, con `scripts/tailwind-fuentes.test.mjs` y `src/lib/twins.test.ts`); Playwright,
**34** (3 nuevas: un solo sitio que late, el modo oscuro y el plazo pasado), todas sin
peticiones fuera de 127.0.0.1, sin violaciones de la CSP, sin errores en la consola, sin
problemas de axe ni faltas de contraste y sin castellano. La pasada entera de Playwright se
hizo también **con la suite de Python corriendo a la vez** (la máquina cargada, como cuando
fallaba el hallazgo 5): 34 de 34.

**Lo que falta**: mirar en el ordenador del dueño que Edge no ofrece guardar el token (en
Chromium sin cabeza no se puede ver) y que, sin lo construido, `iniciar.bat` abre la
consola de antes. Que alguien de la oficina lea los textos nuevos (las gravedades, «Opnieuw
laten bekijken», «Wat nog moet»).

### Paso 15 · seguimiento

Dos problemas que salieron después de la puerta del paso 15, cada uno con una prueba que
falla antes y pasa después.

| # | Problema | Qué se hizo | Dónde se comprueba |
| --- | --- | --- | --- |
| 1 | **A la anchura de un móvil (unos 400 px) la tira de pestañas del componente del dueño era una rendija**: en una sola fila iban el menú, las pestañas, el + y el …, la marca de prueba, NL \| EN y la persona, y a la tira casi no le quedaba sitio. Las pestañas ni se veían ni se podían tocar (la herramienta de vista previa tuvo que abrir una escondida con su evento de clic); a 360 px la persona se salía además de la ventana | Por debajo de md (768 px) la cabecera va en **dos filas**: arriba el menú y el `toolbar`; debajo, la tira con el + y el … fuera de ella, como ya iban a 1024 px. Las pestañas van más estrechas (de 96 a 160 px; desde md, de 140 a 220 como antes) y, como en Chrome cuando no caben, la ✕ va solo en la activa: sin ratón no se ve antes de tocar, y tocar el borde de otra pestaña la cerraba. Y la pestaña activa se ve siempre entera: cuando la tira o sus pestañas cambian de tamaño (una que se abre y aún crece, un título que llega), `revealActive` desplaza la tira hasta ella, medida con `offsetLeft` (durante la animación de `layout` la pestaña lleva un `transform`). Arriba de `sidebar-with-chrome-like-tabs.tsx`, lo que se cambió | `e2e/shell.spec.ts` «en el movil (400 px)…» y «(360 px)…», con pantalla táctil (`hasTouch`, `isMobile`): entrar, la Werklijst desde la hoja, dos facturas distintas en sus pestañas y de una a otra **tocando la pestaña** (`tap()`), la activa entera dentro de la tira, cada pestaña de 96 px o más y 36 de alto o más, la tira con sitio para dos, el + y el … después de la tira y dentro de la ventana, tocar otra pestaña no la cierra, axe, y **nada fuera de la ventana** (`outsideTheWindow`: ningún elemento pasa del borde salvo dentro de algo que se desplaza; `html` y `body` sin desplazamiento horizontal), también en inglés. Antes fallaba: a 400 px `tap()` no llegaba a la pestaña (el + y el … la tapaban); a 360 px el menú de la persona iba de 330 a 392 px |
| 2 | **En Importeren, después de una prueba que sale bien, «Eerst proberen» y «Nu echt importeren» eran los dos el botón de color** | `primaryImportAction` (`src/screens/import.tsx`): una sola acción principal cada vez. Antes de probar, «Eerst proberen»; después, «Nu echt importeren», y la prueba pasa a secundaria (`outline`). Si con la prueba no entraría nada (el mismo fichero otra vez) o ya se importó, ninguna: lo dice el texto, y «Ander bestand» sigue secundario. Cambiar el día, la clase o la confirmación borra la prueba y la principal vuelve a ser probar | `src/screens/screens.test.ts` («una sola accion principal…»); `e2e/screens.spec.ts` «importeren…» (`primaryActions`: los botones de la tarjeta con el fondo de `--primary`, con el ratón fuera y la pantalla quieta): sin fichero y con él, `['Eerst proberen']`; después de la prueba, `['Nu echt importeren']` (y `['Import for real']` en inglés); con otra fecha, otra vez la prueba; importado y repetido, ninguno. Antes fallaba: después de la prueba salían los dos |

**Lo de escritorio sigue igual.** Se midieron las cajas de la cabecera (la tira, cada
pestaña, el +, el …, la marca de prueba, el idioma, la persona y el panel) con lo construido
antes y después, a 1440 × 900, 1024 × 768 y 800 × 700: a 1440 y 1024 son las mismas al
centésimo de píxel. Lo único que cambia desde md es dónde se para la tira cuando la pestaña
activa no cabe: a 800 px, con dos pestañas, la nueva quedaba cortada 29 px por la derecha y
ahora se ve entera; a 1024 y 1440 con muchas pestañas, la última abierta perdía su curva
derecha (7–8 px) y ahora no. Es lo que quería el código del dueño (llevar el + a la vista
250 ms después de abrir la última pestaña), que no llegaba a hacer nada: su
`closest('.flex')` encuentra la propia pestaña y ahí no hay ningún +. Se deja como estaba. Las capturas de la puerta y las nuevas se compararon píxel a píxel: 78 de 118 iguales;
las demás cambian en las horas de los datos de prueba (la historia de una factura y de las
importaciones), en unos píxeles sueltos del suavizado (el borde redondo de una pastilla, con
las cajas iguales), en la tira de las pantallas con muchas pestañas (la
activa, ahora entera), en Importeren (un solo botón de color) y a 700 px (la cabecera en dos
filas).

**Desviaciones, y por qué**

1. **El orden del teclado en el móvil no es el de la vista**: en el móvil el `toolbar` se ve
   arriba y la tira debajo, pero en el documento la tira va antes (`order`), como en
   escritorio, para no cambiar el orden del teclado de 768 px para arriba. En un móvil no se
   usa teclado.
2. **Una pestaña mide unos 40 px de alto** (la del dueño): la prueba pide 36 o más (WCAG 2.5.8
   pide 24), sin hacerla más alta.

**Mirado en las capturas** (`CAPTURAS_DIR`, las 118 de siempre y 6 nuevas:
`nl-mobile-tabs-400`, `nl-mobile-tabs-400-first`, `nl-mobile-tabs-360`,
`nl-mobile-tabs-360-first`, `en-mobile-tabs-400`, `en-mobile-tabs-360`, y `nl-import-preview` y
`en-import-preview`, con un solo botón de color): arriba el menú, la marca, NL | EN y la
persona; debajo, dos pestañas legibles («Werklijst», «DGG-2026-118»), la siguiente cortada por
el fundido, y el + y el … a la derecha.

**Resultado**: Python 3.11, **2515 pasan y 12 se saltan** (como antes: aquí no cambia nada de
Python); `npm run typecheck` limpio; vitest, **820** (uno nuevo); Playwright, **36** (2
nuevas: el móvil a 400 y a 360 px), todas sin peticiones fuera de 127.0.0.1, sin violaciones
de la CSP, sin errores en la consola, sin problemas de axe ni faltas de contraste y sin
castellano, también con la suite de Python corriendo a la vez. `npm run build` vuelve a dar
exactamente lo que va en git.

## Paso 16 · base de Aurora dentro de la app, temas e idiomas

Paso 0 del §8.3 de la revisión de Aurora, más la infraestructura de temas e idiomas sobre la
que se monta lo demás. La navegación de pestañas sigue como estaba (la sustituye la rueda de
Aurora en el paso siguiente) y no se toca nada de Python salvo una prueba
(`tests/test_app_local.py`). El detalle, en [app-local.md](../app-local.md) (§1, §5 y §7,
«Aurora dentro de la app»).

### Qué se construyó

- **Aurora en `frontend/src/aurora/`**, desde `app-nuestras` del prototipo, formateado y con
  TypeScript estricto: el logo (`logo.tsx`, la marca BMS como un SVG pequeño trazado del PNG),
  el orbe (`orb/`), el orbe de partículas (`thinking-orb/`), el suricato y el cargador
  (`meerkat/`, `processing/`), el archivo (`documents/`), la conversación y la caja de
  escribir, la búsqueda, el resumen del dinero (`finance/`) y la rueda (`wheel.tsx`). Hoy se
  montan el logo (entrada y barra lateral) y el orbe (cabecera del Overzicht, que se mueve
  mientras carga); lo demás espera a su pantalla.
- **Fuera todo lo simulado**: `invoice-analysis.ts`, los lotes de muestra, las dos claves de
  `localStorage` del prototipo, las respuestas fijas, «Simular liquidación», «Agregar
  muestra», «Compartir», los pulgares, «Regenerar», los botones de depuración, los paneles a
  los que no se llegaba y las funciones globales del cargador. NumberFlow y date-fns no se
  traen: los importes salen de `format.ts` desde céntimos enteros, en notación neerlandesa y
  solo en euros, también en `FinanceBento`.
- **Las tres correcciones de la CSP** (revisión, hallazgo 9): el estilo de las carpetas en
  su propio fichero (`glass-folder.css`; el prototipo metía un `<style>` en cada carpeta), la
  suricata montada sin `innerHTML` (un canvas que pinta sus sprites) y las cifras sin
  NumberFlow. Además, nada de enlaces ni imágenes hechos con un dato (`href`, `image`) y el
  cargador ya no deja funciones en `window`.
- **El CSS de Aurora**, bajo `.aurora-root`, en `@layer components`, con los colores como
  variables de `aurora/palette.css` (oscuro el de Aurora, claro su pareja con la luminosidad
  invertida en OKLab, y `--au-t-…` para texto a 4,6:1), nada por debajo de 12 px y los
  `@keyframes` como `aurora-…`. IBM Plex Sans en 300, 400, 500, 600 y 700, y Mono.
- **El orbe con las reglas de la revisión**: quieto en reposo (una imagen, ningún cuadro
  pedido), como mucho 30 imágenes por segundo, parado con la ventana oculta, fuera de
  pantalla o con «menos movimiento», uno por pantalla y, sin WebGL, un degradado fijo.
- **Los temas**: el oscuro de Aurora por defecto, el claro y «Volg Windows», como variables
  CSS de toda la app (`src/index.css`: `:root` claro, `:root.dark` oscuro). Lo decide la clase
  `.dark` de `<html>` (`lib/theme.tsx`, antes de pintar nada); «Volg Windows» escucha
  `matchMedia` y cambia en vivo. Se elige en el menú de la cuenta y en Instellingen y se
  guarda como el idioma (`bms-app:v1:theme` y `bms-app:v1:<entorno>:<persona>:theme`). Los
  colores fijos de las pantallas (`#45423c`, `#ebe7df`, `#f4f1ea`, `#f2efe8`, `#d6d1c6`…)
  pasaron a variables (`soft-foreground`, `divider`, `row-hover`, `table-head`,
  `border-strong`, `notice`, `avatar`, `sidebar-tab-active`).
- **El castellano**: `i18n/es.ts` con todas las claves (el tipo y `i18n.test.ts` lo
  obligan), el interruptor NL | EN | ES y, mientras falte `src/bms_agent/textos/es.json`
  (lo prepara otro trabajo), los textos de dominio en inglés, marcado en `DOMAIN_FALLBACK`
  (`i18n/langs.ts`) con lo que hay que hacer cuando llegue.
- **Los restos de otro idioma por idioma** (`i18n/leftovers.ts`) en lugar de «ningún
  castellano»: los usan `i18n.test.ts` (los tres diccionarios) y `expectNoLeftovers` en cada
  pantalla de las pruebas en el navegador.

### Cambios de comportamiento

| # | Antes | Ahora | Por qué |
| --- | --- | --- | --- |
| 1 | Solo tema claro | **Oscuro por defecto** (el de Aurora), claro y «Volg Windows», por persona | Lo pide el paso 16; el modo de Windows solo cuenta con «Volg Windows» |
| 2 | NL \| EN; `isLang('es')` era falso y un `es` guardado se ignoraba | NL \| EN \| ES; `es` vale en `isLang` y en lo guardado (`fr` o `ES` siguen sin valer) | El castellano como tercer idioma |
| 3 | El dominio solo en nl y en | En castellano, el dominio dice el inglés (`DOMAIN_FALLBACK`) hasta que llegue `es.json` | `es.json` lo hace otro trabajo; el siguiente lo conecta |
| 4 | `expectNoSpanish`: ninguna palabra de una lista castellana en nl y en | `expectNoLeftovers`: en cada idioma, ninguna palabra que solo sea de otro (en castellano se tolera el inglés del dominio); no cuentan las bandas del servidor ni lo marcado con `data-proper-name` | Con tres idiomas, «nada de castellano» ya no sirve |
| 5 | `data-proper-name`, solo el nombre de un fichero de la persona | También el valor de texto libre de un campo, tal como vino del documento («30 dagen») | Es texto del documento, no de la app (salía como resto de neerlandés en inglés y castellano) |
| 6 | Título de pantalla de 21 px, seminegrita | 26 px, peso normal, más apretado | El estilo de Aurora |
| 7 | La marca «BM» en una caja | La marca BMS en SVG (`BmsMark`) con «finance» | El logo de Aurora, pequeño y sin imagen |
| 8 | La cabecera del Overzicht, sin nada a la derecha | El orbe de Aurora, quieto salvo mientras carga | El asistente se ve en el inicio |
| 9 | Fechas largas armadas en el código | `months.longDate`, una plantilla por idioma | El castellano las dice de otra forma («martes, 27 de octubre de 2026») |
| 10 | `status.spec`: «con el modo oscuro del sistema la app sigue clara» | «el tema es el que elige la persona, no el del sistema»: oscuro por defecto con Windows en claro, claro con Windows en oscuro, cada pastilla a 4,5:1 en los dos | Con dos temas, lo que hay que probar es que el tema no lo cambia Windows |
| 11 | Capturas en `CAPTURAS_DIR/<nombre>.png` | En `CAPTURAS_DIR/dark/` o `CAPTURAS_DIR/light/`, según el tema que se ve | El mismo nombre en los dos temas |

### La puerta, prueba por prueba

- **Temas**: `src/lib/storage.test.ts` (guardar y leer el tema, valores que no valen, un
  almacén roto, `DEFAULT_THEME` oscuro, `resolveTheme`); `e2e/themes.spec.ts` «oscuro por
  defecto…» (oscuro con Windows en claro, elegir claro en el menú de la cuenta, recargar y
  seguir en claro, «Volg Windows» cambiando en vivo, otra persona en el mismo ordenador con
  su propio tema); `e2e/status.spec.ts` «el tema es el que elige la persona…»;
  `tests/test_app_local.py` (el CSS construido sin `prefers-color-scheme`, `:root` claro y
  `:root.dark` oscuro).
- **Cada pantalla en los dos temas**: `e2e/themes.spec.ts` recorre las 15 áreas en claro en
  neerlandés, inglés y castellano y en oscuro en castellano, y las fichas en claro; las demás
  pruebas, en oscuro. En cada una, axe sin nada serio, ninguna falta de contraste, cada
  pastilla a 4,5:1 o más, ningún resto de otro idioma y un orbe como mucho.
- **El orbe**: `src/aurora/orb/orb-loop.test.ts` (cuándo se mueve, como mucho 30 imágenes
  por segundo a 60, 120 y 144 Hz, ningún cuadro parado, uno por pantalla) y
  `e2e/themes.spec.ts`: mientras carga se mueve y pide cuadros; con la ventana oculta o fuera
  de pantalla se para; en reposo, **0 cuadros pedidos en 3 s** (límite: menos de 10; mientras carga
  se cuentan unos 78 en un segundo) y **unos 3 ms de trabajo del hilo principal en 5 s** (límite:
  0,25 s, el 5 % de un núcleo; `TaskDuration` del protocolo de Chrome); con «menos
  movimiento», quieto también mientras carga; sin WebGL, `data-orb="fallback"` con el
  degradado y la pantalla igual de accesible.
- **Idiomas**: `src/i18n/i18n.test.ts` (las mismas claves y huecos en los tres, ningún texto
  vacío, ningún resto de otro idioma en cada diccionario, el castellano no es una copia del
  inglés ni del neerlandés, `LANGS`, `DOMAIN_FALLBACK`); `templates.test.ts` prueba cada
  idioma que trae `casos.json`.

### Desviaciones, y por qué

1. **El CSS de Aurora se sacó con una herramienta de una sola vez** (solo las reglas que usan
   sus componentes, con el ámbito, la capa, la paleta y los nombres cambiados) que no va en el
   repositorio: desde ahora esas hojas se cambian a mano, como el resto.
2. **El tema claro de Aurora no existía**: su pareja de cada color es el mismo matiz con la
   luminosidad invertida en OKLab, y los colores de texto se ajustaron a 4,6:1. En claro, el
   lienzo del orbe lleva `saturate` y `contrast` (sin eso se veía lavado), y el suricato y el
   cargador se invierten.
3. **`thinking-orb/renderer.ts` va sin comprobar tipos** (`// @ts-nocheck`): es el dibujo del
   «Thinking Orb» tal cual, con nombres de una letra; tiparlo sería reescribirlo. La frontera
   (`thinking-orb.tsx`) sí lleva tipos, y el dibujo no toca el DOM ni la red.
4. **Sin axe con el menú de la cuenta abierto**: Radix esconde el resto con `aria-hidden`
   mientras el foco está en el menú y axe lo da como `aria-hidden-focus`. Con el menú abierto
   se mide solo el contraste de las pastillas.
5. **«Cola de trabajo» y su insignia se cortan en la barra lateral**: la barra se va con la
   rueda en el paso siguiente.
6. **`GlassFolder` ya no tiene la prop `action`** (`'more' | 'none'`), ahora `moreButton`:
   `tests/test_app_local.py` busca `action='…'` para saber qué órdenes manda la app, y
   `action='none'` salía como una orden que no existe.
7. **En castellano la app sí nombra los `.bat` y los accesos directos** (`empresa.bat`,
   «BMS Finanzas - Leer facturas»): en neerlandés y en inglés no los nombra porque están en
   castellano; en castellano se llaman así.
8. **Cuatro pruebas en el navegador del paso 15 dependían del día en que se crea la base de
   prueba.** `demo.py` numera las facturas quincenales de J. Voorbeeld Beveiliging desde el
   principio de la planificación: creada el 19-10-2026, la que llega dos veces era
   JV-2026-006 y había 16 documentos leídos; creada el 27-10-2026 es JV-2026-007 y son 17
   (comprobado en la base). Con las cifras escritas a mano, «het overzicht…», «de
   geblokkeerde facturen…», «accepteren vraagt een tweede persoon…» y «facturen lezen…»
   fallaban por los datos, no por la app. Ahora `daily.spec.ts` lee el número de la Werklijst
   (`twinNumber`: la fila con «1 van 2») y `screens.spec.ts` lee los documentos de
   `/api/v2/lectura`; lo que se comprueba es lo mismo. «Un solo sitio late» de
   `status.spec.ts` falló en la misma pasada solo porque la prueba de aceptar se quedó a
   medias y dejó la base de otra manera; sola y en la pasada entera, pasa.

### Lo que deben saber los pasos siguientes

- **Tema**: `useTheme()` (de `@/lib/theme`) da `{ choice, resolved, setChoice }`; `choice` es
  `'dark' | 'light' | 'system'` y `resolved`, `'dark' | 'light'`. Los colores, siempre con
  las variables (`bg-card`, `text-soft-foreground`, `var(--au-…)`), nunca un hex fijo; una
  clase `dark:` vale con la `.dark` de `<html>`.
- **Idiomas**: `useT()` da `{ t, lang, setLang }`; `Lang`, `LANGS`, `LOCALES` y `isLang` están
  en `@/i18n/langs` (y se reexportan desde `@/i18n`). Un texto nuevo va en `nl.ts`, `en.ts` y
  `es.ts` a la vez. Para conectar `es.json`: lo que dice `DOMAIN_FALLBACK`.
- **Aurora**: cada pieza envuelve su raíz en `.aurora-root` y recibe sus textos de
  `t.aurora`; un orbe nuevo en una pantalla que ya tiene uno sale como degradado.

**Mirado en las capturas** (`CAPTURAS_DIR`, 143 en `dark/` y 55 en `light/`, y las de las
piezas sin montar en un banco de pruebas aparte): cada área en claro en los tres idiomas y en
oscuro en castellano; la entrada en los dos temas y en castellano; el menú de la cuenta con
«Licht» marcado; Instellingen con «Volg Windows» siguiendo al oscuro; el Overzicht con el
orbe quieto a la derecha del título y, sin WebGL, con el degradado; la factura en castellano
con los campos de dominio en inglés (la reserva); el menú del móvil en oscuro. Las piezas sin
montar (la conversación, el archivo con sus carpetas, la búsqueda, «Lo importante» y el
cargador con la suricata y el resultado) se miraron en los dos temas con datos de prueba.
Lo que se arregló al mirarlas: en la primera pasada el orbe empujaba la cabecera del
Overzicht 60 px hacia abajo (era un elemento en línea con márgenes negativos: ahora un
bloque de 56 px de alto); el orbe del archivo tapaba la línea pequeña de encima del título
(ahora va centrado detrás); en claro, un halo oscuro alrededor del orbe (ahora `saturate` y
`contrast`); «1 proveedores con saldo» (ahora singular). Queda: «Cola de trabajo» y su
insignia se cortan en la barra lateral (desviación 5).

**Resultado**: Python 3.11, **2515 pasan y 12 se saltan** (como antes: de Python solo cambia
una prueba de `test_app_local.py`, que pasa también con Python 3.13); `npm run typecheck`
limpio; vitest, **830** (12 ficheros; 10 más: el bucle del orbe, el tema guardado y los
tres idiomas); Playwright, **45** (9 nuevas en `themes.spec.ts`), todas sin peticiones fuera
de 127.0.0.1, sin violaciones de la CSP, sin errores en la consola, sin problemas de axe ni
faltas de contraste en los dos temas y sin restos de otro idioma, con la suite de Python
corriendo a la vez. El orbe en reposo: 0 cuadros pedidos en 3 s y 3 ms de trabajo del hilo
principal en 5 s; moviéndose, unos 78 cuadros pedidos por segundo (los del orbe y los de la
app mientras carga). Sin dependencias nuevas (`package.json` y `package-lock.json` sin
cambios); `npm run build` vuelve a dar exactamente lo que va en git.

## Paso 16 · lecturas nuevas del motor (Cobrar, Pagar y Documentos)

La parte del motor del paso 16 (la R de «lecturas»): lo que la revisión de Aurora
(`revision.md` §8.3 paso 2, §8.4 y §8.5) pide leer para que Cuentas por cobrar, Cuentas
por pagar y Documentos funcionen con datos de verdad. Solo Python: ni la app (`frontend/`)
ni los catálogos de textos (`src/bms_agent/textos/`, que otra parte hace en paralelo) se
tocan. Ninguna orden nueva: confirmar, retirar o apuntar un pago ya existían
(`confirmar_pago`, `retirar_pago`, `marcar_pagada`). El contrato sube a **2.2** (solo
claves y lecturas nuevas).

**Qué se construyó**

- `GET /api/v2/cartera?sentido=saliente|entrante` (`consultas.cartera`): los totales
  (pendiente, vencido, esta semana, este mes, próximos 30 días, sin fecha), la antigüedad
  por tramos (`al_corriente`, `1_30`, `31_60`, `61_90`, `mas_de_90` y `sin_fecha`, cada uno
  con `vence_desde` y `vence_hasta` para abrir la búsqueda filtrada), cada empresa
  (pendiente, vencido, retenido, días de la vencida más antigua, cuántas, su prioridad, sus
  `razones` y su `plazo_de_pago`), lo retenido y lo libre, y aparte, sin sumar: los pagos
  propuestos por confirmar, lo del banco sin casar, los abonos sin enlazar (con su lista) y
  las facturas en juego sin importe en euros. Todo en céntimos enteros con su texto al lado.
  Los `totales` salen de la **misma función** que `panel.dinero_entra` y `dinero_sale`
  (`_bloque_dinero`, sobre las mismas partidas de `flujo_caja.datos`): no hizo falta
  refactorizar el panel, porque ya era una función de las partidas; la cartera llama a
  `flujo_caja.calcular` (puro) en lugar de `flujo_caja.flujo`, que solo añade el estimado
  del planning, que no entra en lo esperado.
- `GET /api/v2/pagos/propuestas` (`consultas.propuestas_pago`): los pagos que el banco
  propuso y esperan a una persona, cada uno con su `rev` (para `confirmar_pago` y
  `retirar_pago`), su `lado` (cobro o pago), la línea del banco (fecha, importe,
  contraparte, IBAN, concepto, referencias), la factura (número, parte, total, lo que queda,
  vencimiento, estado) y las tres coincidencias con su sí o su no (de lo que `pagos.casar`
  apuntó en `regla`). Antes solo existía en la CLI (`bms-agent pagos --propuestas`, y las
  líneas sin casar con `--sin-casar`).
- `GET /api/v2/movimientos` (`consultas.movimientos_banco`): las líneas del banco, por
  defecto solo las sin casar (las mismas de `pagos.movimientos_abiertos`, con la tolerancia
  de la política), con `signo`, `desde`, `hasta`, `texto` y `limite`, y `sin_casar=no` para
  verlas todas con lo que les queda y si son `propia`. Es el selector de «Apuntar un pago»
  (`marcar_pagada` con `movimiento_id`). `pagos.aplicado_por_movimiento` sale de
  `movimientos_abiertos` (lo mismo, ahora con nombre) para que las dos cuenten igual.
- `GET /api/v2/clientes/N/documentos` y `/proveedores/N/documentos`
  (`consultas.documentos_de_parte`): lo que el sistema **ya** enlaza a la parte, sin tabla
  nueva: los originales de sus facturas y abonos, los justificantes de sus pagos apuntados
  (`evidencia_documento_id`) y las hojas de sus PO y de sus modificaciones, con id, tipo,
  fecha, número, importe, estado de pago (de las facturas), tamaño, nombre, si el original
  está guardado y el registro al que va unido.
- `GET /api/v2/documentos/N/original`: la descarga de cualquier documento guardado, con lo
  mismo que la del original de una factura (adjunto, `default-src 'none'; sandbox`,
  `nosniff`, `no-store`, sin CORS, `403 otro_origen` desde otro origen) y su evento
  `documento_abierto` (también cuando el original falta: `404` y el evento con `error`).
- En la vista de un proveedor y la de un cliente: `kvk`, `email_facturacion` y
  `direccion` del maestro, `contactos`, `ordenes_compra` (sus PO) y `documentos` (cuántos
  tiene su carpeta); en la de un cliente, además, `objetos`. En las listas de proveedores y
  clientes, `documentos`. En la búsqueda, el filtro `tipo` (`factura`, `nota_credito`), que
  la revisión pide para el «Tipo de documento» del archivo.
- `docs/integracion-web.md`: lo que añadió el 2.2, las lecturas en la tabla, el filtro
  `tipo`, y dos apartados nuevos («Cuentas por cobrar y por pagar» y «El archivo de una
  parte») con sus esqueletos, que `test_el_contrato_v2_es_el_que_dice_la_documentacion`
  recorre como los demás. Y la **corrección** que pedía la revisión (decisión 10): el
  fichero decía que `dinero_entra` llevaba los abonos de los proveedores; el código nunca los
  contó (`reglas.pagos.vence`: solo deudas). Se corrigieron también los dos comentarios del
  código que decían lo mismo (`consultas.py`, sobre el panel, y `trabajo.py`).

**La puerta, test por test** (`tests/test_cartera.py`, 17 tests)

| Lo que se pide | Test |
| --- | --- |
| La cartera dice lo mismo que el panel al céntimo; los tramos suman lo pendiente; las empresas suman el total; lo vencido son los tramos de retraso; retenido más libre es el total; sin floats y con su texto | `test_la_cartera_dice_lo_mismo_que_el_panel_al_centimo` (la base de prueba el 14-10-2026, el 20-11-2026 y el 31-01-2027, los dos sentidos) y `_comprobar_cartera`, que también corre en los tests del banco antes y después de confirmar un pago |
| Cada tramo se llena con los días | `test_los_tramos_de_la_base_de_prueba_se_llenan_con_los_dias` |
| Lo pendiente de una empresa en la cartera es lo de su vista menos sus abonos sin enlazar (y lo vencido, igual): la documentación de «por cobrar» estaba mal, el código bien | `test_una_empresa_es_su_vista_menos_sus_abonos_sin_enlazar` |
| Los tramos cubren cada día sin huecos ni solapes, y sus `vence_desde`/`vence_hasta` son exactamente sus días | `test_los_tramos_cubren_cada_dia_y_abren_la_busqueda_que_les_toca` |
| El sentido es obligatorio | `test_el_sentido_de_la_cartera_es_obligatorio` |
| Los pagos por confirmar y lo sin casar de cada lado; la propuesta con su línea, su factura, su `rev` y sus tres coincidencias; confirmarla la saca y baja lo pendiente, y todo sigue cuadrando | `test_lo_que_espera_a_una_persona_y_lo_que_no_casa` |
| Las líneas sin casar y cada filtro; un traspaso entre cuentas propias no sale (y con `sin_casar=no` sale marcado); lo propuesto no está sin casar | `test_las_lineas_del_banco_sin_casar_y_sus_filtros` |
| Lo retenido es lo que bloquea o retiene, comprobado leyendo los hallazgos de las tablas | `test_lo_retenido_es_lo_que_bloquea_o_retiene` |
| Por la API: las lecturas en `/api/v2/contrato`, la cabecera 2.2, la cartera igual que en Python y que el panel, los `400` y `404` con su `codigo`, `401` sin token y `403` sin ver_facturas (también la descarga); el rol consulta lee | `test_las_lecturas_nuevas_por_la_api` |
| Desde un origen declarado, ningún IBAN entero en las lecturas nuevas; desde la app, enteros | `test_desde_otro_origen_las_lecturas_nuevas_no_llevan_un_iban` |
| La carpeta: facturas, justificante de un pago a mano, hoja de la PO y de su modificación, con su vínculo y en orden; la lista dice cuántos | `test_la_carpeta_de_un_proveedor` |
| La descarga: los bytes y su hash, las cabeceras, sin CORS, `403` desde otro origen, `404` sin original, y cada intento en la auditoría con su persona | `test_un_documento_se_descarga_auditado_y_solo_desde_la_app` |
| KvK, correo, dirección y contactos del maestro (los de un cliente, `null` donde el maestro no tiene nada) | `test_la_ficha_de_una_parte_trae_lo_del_maestro` |
| El filtro `tipo` | `test_la_busqueda_filtra_por_tipo` |
| Cada lectura nueva rechaza un parámetro que no admite | `test_cada_lectura_nueva_esta_en_la_lista_y_rechaza_lo_que_no_admite` (y la de siempre, `test_cada_lectura_de_v2_rechaza_un_parametro_que_no_admite`, que recorre `LECTURAS_V2` entera) |

**Desviaciones, y por qué**

1. **Seis tramos, no cinco.** La revisión pide al corriente, 1-30, 31-60, 61-90 y más de 90;
   lo que no tiene vencimiento no está en ninguno de ellos y sin él los tramos no sumarían
   lo pendiente. Va en un sexto, `sin_fecha`, que es `totales.sin_fecha_cent`.
2. **Una fila sin empresa.** Las facturas sin cliente (o proveedor) del maestro van juntas en
   una fila con `id` `null`, al final: si no, las empresas no sumarían el total.
3. **Lo pendiente de una empresa en la cartera no es lo de su vista.** La vista (y su fila en
   las listas) resta los abonos sin enlazar desde la migración 0017, a propósito; la
   cartera, como el panel, solo cuenta deudas. No se cambia ninguna de las dos: se da la
   lista de abonos sin enlazar y un test comprueba que las dos cifras se explican una con la
   otra, empresa a empresa.
4. **Lo retenido** es lo que tiene un hallazgo activo que bloquea o retiene, o una factura
   Bloqueada. No basta «tiene alguna objeción»: K1 (vencida sin pagar) es un aviso y dejaría
   retenido todo lo vencido.
5. **`por_confirmar` va por el sentido de la factura y `sin_casar` por el del dinero**
   (ingresos para cobrar, cargos para pagar): un movimiento sin casar no tiene factura.
6. **El sentido de la cartera es obligatorio** (`400` sin él): sumar lo que nos deben con lo
   que debemos no es ninguna cifra.
7. **Documentos, solo lo que ya está enlazado** (decisión 7 A). Una hoja de PO importada con
   varias PO no va a la carpeta de ninguna (es de la importación); un extracto del banco solo
   sale si alguien lo dio como justificante de un pago. Una fila por enlace.
8. **El maestro de clientes no tiene correo de facturación ni dirección**: van `null`, sin
   tocar el esquema. El teléfono de un contacto no es el de verificar un IBAN (ese sigue
   siendo `telefono_verificacion`, solo del maestro de proveedores), y la documentación lo
   dice.
9. **Un poco más de lo pedido**, porque la app lo necesita sin hacer diez lecturas: las PO
   y los Objetos en la vista de la parte (decisión 1: «dentro de cada cliente sus Objects y
   sus PO»), cuántos documentos tiene cada carpeta en las listas (el árbol del archivo lleva
   contadores), y en la cartera `fechas` y `movido_mes_cent` (la cabecera dice «cobrado este
   mes»; las dos son las del panel, y el test lo comprueba).
10. **Un id enorme en cualquier ruta de `/api/v2` es un `404`.** Antes,
    `/api/v2/facturas/99999999999999999999999` hacía que sqlite3 lanzara `OverflowError` y la
    petición se quedaba sin respuesta. Cambia a propósito para todas las rutas (comprobado
    con esa y con `/api/v2/documentos/…/original`).
11. **El export (`export --v2`) no cambia**: la cartera, las propuestas y los documentos son
    lecturas; un sitio que lee el fichero tiene `panel` con los mismos totales.
12. **Ningún código de error nuevo**: `invalido`, `no_existe`, `sin_permiso`, `otro_origen` y
    `no_autenticado` cubren todo, así que los catálogos de textos no cambian por esto.

**Lo que deben saber las partes siguientes**

- Las pantallas de Cobrar y Pagar tienen todo lo de §8.4 de la revisión: la cabecera
  (`cartera.totales`, `movido_mes_cent`, y `GET /api/v2/fuentes` para la frescura), la
  antigüedad (`tramos`; cada uno abre `/api/v2/buscar` con su `vence_desde`/`vence_hasta`),
  los avisos (`por_confirmar`, `sin_casar`; en pagar, los K4, K5 y K8 de `razones`), la
  pestaña por empresa (`partes`) y lo retenido. Las tres órdenes van por `POST
  /api/v2/acciones` con su `rev` y un `peticion_id`, y piden `marcar_pagada`.
- Documentos: la lista de carpetas sale de `/api/v2/clientes` y `/proveedores` (con
  `documentos`), la ficha de `/clientes/N` y `/proveedores/N`, los ficheros de
  `/…/N/documentos` y la descarga de `/documentos/N/original`, con el token en la cabecera
  (no se puede abrir con un enlace).
- La app necesita sus textos para los valores nuevos que no son de dominio: los `tipo` de
  documento (`consultas.TIPOS_DOCUMENTO`), las claves de los tramos (`consultas.TRAMOS` y
  `sin_fecha`), `lado` (`cobro`, `pago`) y `coincidencias` (`referencia`, `importe`,
  `contraparte`). No están en `textos/*.json` porque esa parte la lleva otro agente.
- Lo que la revisión deja para después y aquí no está: el «Procesar» de verdad
  (`solicitud_lectura`, `pasada_lectura`, `pedir_lectura`…) y `/api/v2/preguntar` y
  `/api/v2/novedades` del asistente.

**Resultado**: Python 3.11, **2532 pasan y 12 se saltan** (los 2515 de antes y los 17
nuevos de `tests/test_cartera.py`; ninguno de antes cambia). Los nuevos y los que tocan
lo mismo (`test_contrato_v2.py`, `test_pagos.py`, `test_codigos_error.py`) pasan también
con Python 3.13. La app (`frontend/`) no se toca: su comprobación del contrato mira solo el
número mayor, y 2.2 sigue siendo 2.

## Paso 16 · la rueda con seis entradas, el inicio y las pantallas en su sitio

El paso 1 del §8.3 de la revisión de Aurora y su decisión 1: **Aurora pasa a ser la cara de
la app, sobre el motor de verdad.** Seis entradas (Inicio, Cuentas por cobrar, Cuentas por
pagar, Documentos, Procesar e IVA), la rueda en el inicio, las seis en pequeño en las demás
pantallas, migas y «Terug» dentro de cada sección, Ctrl+K, el menú del nombre, el inicio
nuevo y cada pantalla del paso 15 en su sitio, sin perder ninguna función. Antes de empezar
se juntaron aquí las dos partes paralelas del paso (las lecturas del motor y los textos en
castellano) y se conectó `es.json` a la app. El detalle, en [app-local.md](../app-local.md)
(§4 entero, §4.7, §5, §6 y §7).

### Qué se construyó

- **Las dos partes paralelas, juntas.** `git cherry-pick` de las lecturas del motor
  (`paso16-lecturas`) y de los textos en castellano (`paso16-es`); el único conflicto, en este
  registro (las dos secciones del paso 16, que se quedan las dos). La suite de Python entera
  pasó antes de seguir.
- **`es.json` en la app.** `i18n/domain.ts` lo importa como los otros dos, entra en la huella
  (`frontend/build-inputs.json` y los catálogos de `tests/test_app_local.py`) y
  `DOMAIN_FALLBACK` queda vacío: la app en castellano dice el dominio en castellano, y las
  pruebas ya no le toleran restos en inglés. `templates.test.ts` exige ahora que
  `casos.json` traiga los tres idiomas de la app, y los casos en castellano dan lo mismo que
  Python.
- **Las secciones** (`screens/sections.ts`, sin React, para que lo usen también las pruebas
  en el navegador): las seis entradas, sus vistas en orden y el permiso de cada vista.
  `registry.ts` les pone el icono y dice dónde vive cada ficha.
- **La navegación** (`shell/navigation.tsx`): un sitio y su camino, sin pestañas ni
  dirección. `nextTrail` (puro, con sus pruebas) decide el camino: ir a una vista lo empieza;
  abrir una ficha la añade, o vuelve a ella si ya estaba; abrir desde fuera de la sección la
  pone bajo su vista; «Terug» quita el último; una miga vuelve a su paso. Guarda dónde iba la
  página de cada paso y lo devuelve al volver; lo que recuerda una lista (filtro, búsqueda)
  vive en `lib/view-memory.ts` (antes `tab-memory.ts`), solo en memoria. Después de cada
  movimiento el foco va al contenido.
- **La rueda** (`aurora/wheel.tsx`, montada en el inicio): orden fijo (Inicio arriba, IVA
  abajo), lo de la distancia en el texto y no en el botón (cada botón ocupa su fila, 46 px o
  40 en el móvil), un clic o un toque en cualquiera abre, la rueda del ratón (un paso por
  gesto, con un listener nativo no pasivo para que la página no se desplace), el dedo
  (deslizar gira y no abre), Tab, flechas cíclicas, Inicio y Fin, Intro, `aria-current`, una
  frase para el lector de pantalla y «menos movimiento» sin animación.
- **El marco** (`shell/app-shell.tsx`): la cabecera con el logo (vuelve al inicio, con el
  orbe pequeño fuera de él), las seis en pequeño (`compact-nav.tsx`; debajo de 1024 px en su
  propia fila, en el móvil en varias), «Zoeken» con Ctrl K, la marca de prueba y el menú del
  nombre (`account-menu.tsx`: Instellingen, idioma, tema y Uitloggen). Debajo, las vistas de
  la entrada en pastillas con sus insignias (`section-nav.tsx`, `use-badges.ts`) o, en una
  ficha, las migas y «Terug» (`crumbs.tsx`; también Alt+← y el botón de atrás del ratón). Un
  enlace «Naar de inhoud» para el teclado. En el móvil la cabecera va en una fila (sin
  «finance» ni la flecha del menú por debajo de 640 px) y las seis, debajo.
- **Ctrl+K** (`command-palette.tsx`, `lib/quick-search.ts`): un *combobox* con su lista; las
  pantallas por su nombre en los tres idiomas (ordenadas por cómo encajan: «btw» da Btw antes
  que lo que lo contiene), las relaciones, Objects y PO de sus listas, y las facturas por
  `GET /api/v2/buscar?texto=…`.
- **El inicio** (`screens/home.tsx`, sustituye al Overzicht): el saludo con el nombre, la
  rueda con el orbe, la caja que busca (lo mismo que Ctrl+K, por grupos) y dice siempre que
  aún no contesta preguntas, las cuatro tarjetas de `/api/v2/panel` con filas que abren su
  lista ya filtrada, «Als eerste» (cinco como mucho) solo con lo bloqueado o urgente, los
  accesos a Werklijst, Uitzonderingen y Kasstroom, y la lectura cada minuto mientras se ve y
  después de cada orden. Todo quieto (`PingScope`).
- **Cada pantalla del paso 15 en su sitio**: Werklijst, Uitzonderingen y Kasstroom en Inicio;
  Verkoopfacturen, Klanten, Objecten y las PO de los clientes en Cuentas por cobrar;
  Inkoopfacturen, Leveranciers, las PO de los proveedores e IBAN-controles en Cuentas por
  pagar; Importeren y Facturen lezen en Procesar; Btw en IVA; Instellingen en el menú del
  nombre. Las fichas (factura, proveedor, cliente, Object, PO, trimestre) igual que antes,
  dentro de su sección.
- **Documentos, lo justo** (`screens/documents.tsx`): las carpetas de clientes y proveedores
  en una página, con un buscador, y la carpeta de cada uno con sus documentos y la descarga,
  sobre las lecturas nuevas del motor (`/api/v2/clientes/N/documentos`…,
  `/api/v2/documentos/N/original`). El archivo de Aurora va encima en el paso de Documentos.
- **La excepción como ficha** (`screens/exception.tsx`): lo que era el panel lateral, con
  migas, «Factuur openen» y sus órdenes.

### Cambios de comportamiento

| # | Antes | Ahora | Por qué |
| --- | --- | --- | --- |
| 1 | La barra lateral con pestañas como las de Chrome, en seis grupos y quince apartados | Seis entradas: la rueda en el inicio, las seis en pequeño en las demás pantallas, las vistas de cada una en pastillas; el componente del dueño se queda en el repositorio sin montar | Decisión 1 de la revisión: la navegación de Aurora es la de la app |
| 2 | Una fila abría su ficha en una pestaña nueva; las pestañas y la barra plegada se guardaban por persona | La ficha se abre en su sección, con migas y «Terug»; no se guarda nada de la navegación (al entrar se borra la clave `…:tabs` del paso 15) y se empieza siempre en el inicio | Sin pestañas, lo que hay que poder es volver; el inicio es la puerta |
| 3 | Overzicht: cuatro tarjetas y «Als eerste», las cinco primeras de la werklijst | El inicio: el saludo, la rueda, la caja de buscar, las cuatro tarjetas (Te ontvangen y Te betalen con lo vencido, lo próximo y cuántas relaciones con saldo, cada fila abre su lista filtrada) y «Als eerste» **solo con lo bloqueado o urgente** | Revisión §8.3: el inicio tranquilo; lo que puede esperar está en la werklijst |
| 4 | Uitzonderingen: una fila abría un panel lateral | Abre la ficha de la excepción, dentro de Inicio | Las fichas, todas iguales: con migas y «Terug» |
| 5 | Inkomend / Uitgaand (In / Out; Recibidas / Emitidas), con «inkoop» y «verkoop» en gris | Inkoopfacturen / Verkoopfacturen (Purchase invoices / Sales invoices; Facturas de compra / de venta) | Dentro de Te betalen y Te ontvangen, «entrantes» ya no dice nada |
| 6 | Una sola lista de Inkooporders | La misma pantalla dos veces: las PO de los clientes en Te ontvangen y las de los proveedores en Te betalen (filtradas por `lado`) | Cada PO donde se trabaja con ella |
| 7 | El original de una factura, al fondo de la ficha (plegado) | Además, el botón «Origineel» en la cabecera de la ficha | Revisión §5, fila 7: tres clics |
| 8 | Las facturas abiertas de una relación, plegadas | Desplegadas cuando las hay | Revisión §5, fila 8: dos clics |
| 9 | Procesar no existía; Importeren iba después de Facturen lezen en «Gegevens» | En Procesar, Importeren primero | Revisión §5, fila 20: un clic |
| 10 | NL \| EN \| ES en la cabecera | En el menú del nombre (y en la entrada y en Instellingen, como antes) | La cabecera lleva las seis; el idioma se cambia poco |
| 11 | «Snel openen» con el ratón sobre el + de las pestañas | Ctrl+K, o «Zoeken» en la cabecera, con las facturas de `/api/v2/buscar` | Revisión: Ctrl+K abre cualquier pantalla o ficha |
| 12 | En castellano, el dominio en inglés (`DOMAIN_FALLBACK`) | En castellano, con `es.json`; `DOMAIN_FALLBACK` vacío | Llegó `es.json` |
| 13 | — | Documentos: las carpetas y la de cada relación con la descarga | La entrada existe y funciona; el archivo de Aurora, después |
| 14 | `tests/test_app_local.py` prohibía `location.hash`, `location.search` y `window.open(` | Prohíbe también `pushState(` y `replaceState(` | La navegación es estado de la app: nada pasa a la dirección |

Los nombres de las entradas en neerlandés y en inglés son nuestros (la revisión las nombra en
castellano): **Start, Te ontvangen, Te betalen, Documenten, Verwerken, Btw** y **Home,
Receivables, Payables, Documents, Process, VAT**. «Verwerken» y «Process» en vez de
«Procesar» tal cual: son el verbo de lo que se hace allí (importar y leer).

### Las pruebas

- **Vitest**: `screens/registry.test.ts` (rehecho: las seis entradas en su orden, cada vista
  en una sola, cada ficha en su vista, los permisos, las rutas), `shell/navigation.test.ts`
  (`nextTrail`: ir, abrir, volver a una ficha del camino, abrir desde fuera, «Terug», las
  migas), `aurora/wheel.test.ts` (la distancia y el paso de las flechas),
  `lib/quick-search.test.ts` (las pantallas en los tres idiomas y su orden, las relaciones,
  las facturas), `screens/home.test.ts` (lo urgente primero, cinco como mucho, el nombre),
  `lib/storage.test.ts` (no se guardan pestañas; la clave del paso 15 se borra sin tocar
  otras), y `i18n.test.ts` y `templates.test.ts` con `es.json`.
- **En el navegador**, todas las pruebas del paso 15 pasaron a la navegación nueva sin quitar
  ninguna comprobación (`e2e/nav.ts`: moverse como una persona, con los nombres de los
  diccionarios). `shell.spec.ts` se rehízo para la rueda, las seis, las migas, Ctrl+K, la
  caja del inicio, el menú del nombre, el teclado, 1024 px y el móvil; `daily.spec.ts`,
  `screens.spec.ts`, `status.spec.ts` y `themes.spec.ts` van por las entradas (la gira de
  `themes.spec.ts` recorre cada vista de `sections.ts` y cada ficha, también la excepción y
  la carpeta de un proveedor). Nuevo, `e2e/clicks.spec.ts`: cada tarea de la tabla de los 3
  clics (revisión §5) en los clics de su «Objetivo», contados de verdad.

### Desviaciones, y por qué

1. **La rueda no da la vuelta.** En el prototipo la rueda giraba en círculo, y con seis
   entradas Procesar quedaba encima de Inicio. Aquí el orden es fijo y lo que cambia es el
   tamaño según la distancia; las flechas sí dan la vuelta (de IVA a Inicio).
2. **La caja del inicio busca y no contesta.** Lo dice siempre debajo; el asistente local es
   de otro paso. No hay ninguna llamada a un modelo.
3. **Cinco filas de la tabla de los clics quedan como `test.fixme`**, con el paso que las
   hace: 11, 12 y 13 (los pagos, Cuentas por cobrar y por pagar), 21 con la confirmación del
   coste (Procesar de verdad) y 22 (la vista previa del archivo de Aurora). Las demás pasan.
4. **El componente de la barra con pestañas no se borra**: se queda sin montar (no entra en
   lo construido), con una nota arriba, por si el dueño quiere volver a mirarlo.
5. **Dos comprobaciones nuevas se ajustaron a cómo es el navegador, no a la app**: con «menos
   movimiento», la regla general de `index.css` deja las transiciones en 0,01 ms, así que la
   prueba pide menos de 1 ms (no 0); y en el móvil, el dedo se para antes de soltar al girar
   la rueda: soltado en marcha, Chromium sigue el gesto y el primer toque que llega justo
   después solo lo para, sin clic (como en cualquier lista que se desliza). Al probarlo salió
   un fallo de verdad, ya arreglado: un deslizamiento que no dejaba clic que tapar dejaba
   tapado el del toque siguiente.
6. **Tres pruebas del paso 15 tenían una carrera que la navegación nueva destapó**: leían
   algo antes de que la ficha cargara (el título provisional «Factuur 17» ya encaja con
   `/^Factuur /`), o decidían si había menú del nombre mientras un diálogo que se cerraba aún
   tapaba el resto. Ahora esperan a lo que miden.

### Lo que deben saber las partes siguientes

- **Documentos** (el archivo de Aurora): se monta sobre `frontend/src/screens/documents.tsx`
  (las carpetas y `PartyDocumentsScreen`), con las fichas `client-documents` y
  `provider-documents` ya en `RECORDS`; las piezas están en `src/aurora/documents/`. La fila
  22 de `e2e/clicks.spec.ts` espera su vista previa.
- **Cuentas por cobrar y por pagar**: sus vistas están en `SECTION_VIEWS` de
  `screens/sections.ts` (añadir una cartera es una vista más, delante si es la primera que se
  usa); las lecturas de la cartera ya están en el motor. `tests/test_app_local.py` sigue sin
  dejar que la app mande `marcar_pagada`: cambiarlo es de ese paso, con su motivo en el
  registro. Las filas 11 a 13 de `e2e/clicks.spec.ts` esperan.
- **Moverse en las pruebas**: `e2e/nav.ts` (`go`, `openSection`, `sectionMenu`, `crumbs`,
  `back`, `setLang`, `signOut`, `readBadge`). Una vista nueva entra sola en la gira de
  `themes.spec.ts` y en la de `shell.spec.ts` (recorren `VIEW_IDS`).
- **Abrir algo** desde una pantalla: `useNav().open(recordRoute(...))`; desde fuera de su
  sección, `openFrom(vista, ruta)`; el título de las migas, `setTitle(navKey, ...)`.

### Resultado

- Python 3.11: **2547 pasan y 12 se saltan** (los 2545 de después de juntar las dos partes
  paralelas y los 2 nuevos de lo prohibido en el frontend; ninguno de antes cambia salvo
  `test_app_local.py`, que mira también `es.json` en la huella).
- Vitest: **1213 pasan** (16 ficheros).
- Playwright (Chromium 1.56.1): **51 pasan y 5 quedan pendientes** (`test.fixme`: las filas 11,
  12, 13, 21 con su coste y 22 de la tabla de los clics), en las dos últimas pasadas del
  conjunto entero; capturas de cada pantalla, ficha y diálogo en neerlandés, inglés y
  castellano y en los dos temas. Se miraron el inicio, las listas, las fichas, Documentos,
  «Snel openen», el menú del nombre, 1024 px y el móvil, y de ahí salieron la cabecera del
  móvil en una fila, la nota de Documentos más corta (repetía la frase de arriba) y que el
  inicio salga arriba del todo en las capturas de la gira.
- `npm run typecheck` sin errores y lo construido al día (`npm run fuente`).

