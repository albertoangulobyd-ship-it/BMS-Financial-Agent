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
