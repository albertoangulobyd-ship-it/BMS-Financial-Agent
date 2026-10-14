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
llamada a la API. **388 tests pasan** (275 funciones de test; eran 314 y
207), ninguno llama a la API y ninguno escribe fuera de una carpeta temporal.

### Qué se construyó

**Módulos nuevos**

| Módulo | Qué hace |
| --- | --- |
| `almacen/__init__.py` | `abrir()` (claves foráneas, WAL, `busy_timeout=5000`, `sqlite3.Row`, se niega a correr en SQLite < 3.37), `transaccion()` (`BEGIN IMMEDIATE`; dentro de otra, un `SAVEPOINT` que deshace solo lo suyo), `preparar()` (abre, migra y devuelve un `Almacen` = conexión + carpeta de documentos), `usuario_sistema()`, `ruta_por_defecto()` (`BMS_DB` o `datos/bms.sqlite3`). La conexión lleva su reloj: `conn.reloj` |
| `almacen/migrar.py` + `almacen/sql/0001_almacen.sql` | Migraciones `NNNN_nombre.sql`, de una en una, cada una en su transacción con su fila en `migracion` (sha256) y su evento `migracion_aplicada`. Una migración aplicada que cambia, o que falta, detiene todo (`MigracionAlterada`) |
| `almacen/unidades.py` | `a_cent`, `a_mil`, `a_e4`, `a_pb` y sus inversas: solo `Decimal` o `int`, nunca `float`, y `PerdidaDePrecision` en vez de redondear. `json_canonico()` (claves ordenadas, sin espacios, rechaza floats) y los hash |
| `almacen/documentos.py` | `AlmacenDocumentos`: `datos/documentos/<sha[:2]>/<sha256>.<ext>`, 0444, escritura a un temporal que se enlaza con `os.link` (no pisa nunca; un original alterado hace fallar `guardar` en vez de repararse en silencio). `registrar_documento()`, `abrir()` (cada apertura es un evento, también la que falla), `verificar()` (vuelve a calcular cada hash; un fichero que nadie apunta es un aviso) |
| `almacen/extracciones.py` | `leer_registro()` (el texto tal cual y sus columnas) y `registrar_extraccion()` (única por documento, modelo, versiones y hash del contenido) |
| `auditoria.py` | `registrar()` (evento encadenado, con sus `cambio_campo` dentro del hash), `verificar_cadena()`, `anclar()`, `leer_anclas()`, `historial()` |
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
  equivocado); `db verificar [--anclas out/anclas.log]` comprueba
  `integrity_check`, `foreign_key_check`, el hash de cada migración, la cadena
  de auditoría con sus anclas y el hash de cada original. Sale con 1 si algo
  no cuadra.
- `bms-agent importar-out [--out out] [--pdfs facturas] [--db …]`. Una
  transacción para toda la orden. Cada fichero bueno da un `documento` (si no
  estaba), una `extraccion` con `via = 'out_v1'` y una `importacion`
  aceptada; cada fichero malo, una `importacion` rechazada con su motivo.
  Repetirla no añade filas (solo un evento por cada original que aparece
  después con `--pdfs`). Al final ancla la cabeza en `out/anclas.log`.
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
| La cadena encuentra una fila editada por una conexión directa después de borrar los disparadores | `test_auditoria.py::test_la_cadena_encuentra_una_fila_editada_sin_disparadores`, y además: el hash rehecho (`..._rompe_el_enlace_con_la_siguiente`), un `cambio_campo` editado, un evento borrado por en medio, el final cortado y el final reescrito (los dos últimos solo con anclas), y por la CLI `test_migracion_out.py::test_db_verificar_encuentra_un_evento_tocado_por_detras` |
| El almacén de documentos no sobrescribe y detecta un hash que no cuadra | `test_almacen.py::test_guardar_es_de_una_vez_y_de_solo_lectura`, `test_el_almacen_no_sobrescribe_un_original_alterado`, `test_verificar_vuelve_a_calcular_cada_hash`, `test_abrir_un_documento_queda_auditado_tambien_si_falla`, y `db verificar` en `test_db_init_migrar_y_verificar` |
| `importar-out` dos veces da los mismos recuentos y lo guardado es byte a byte el fichero | `test_migracion_out.py::test_importar_dos_veces_da_los_mismos_recuentos`, `test_lo_guardado_es_byte_a_byte_el_fichero`, `test_la_orden_de_la_cli_no_llama_a_la_api` (por la CLI) |
| Un PDF que no está deja `ruta_cas` NULL | `test_un_pdf_que_no_esta_deja_ruta_cas_vacia` (las 04 a 07 no tienen PDF), `test_sin_carpeta_de_pdf_todo_queda_sin_original_y_se_anade_despues` |
| `import anthropic` parcheado para lanzar: cero llamadas | `test_la_orden_de_la_cli_no_llama_a_la_api` (fixture `sin_api`: `anthropic` y sus submódulos a `None` en `sys.modules`) |
| `construir_datos(registros_legado(db))` es `construir_datos(load_records(out))` | `test_equivalencia_legado.py::test_el_panel_desde_el_almacen_es_el_panel_desde_out` (y las dos son la foto de referencia byte a byte), `test_los_registros_son_los_mismos_diccionarios`, `test_con_varias_extracciones_vale_la_misma_vigente_que_en_out` |
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
   almacén, que no es cuándo se extrajo). `extraido_en` queda NULL si el
   `extracted_at` del registro no es un instante ISO; el texto original sigue
   en `contenido_json`.
10. **La extracción vigente es una vista**, `v_extraccion_vigente`, con la
    regla de `load_records`: la de `extraido_en` mayor y, en empate, la que
    entró después. `factura.extraccion_vigente_id` es del paso 2, porque
    `factura` también. «Entró después» es el orden de los ficheros en una
    misma pasada de `importar-out`, igual que en `out/`; solo difiere si un
    fichero con el mismo `extracted_at` se importa en una pasada posterior y
    va antes por nombre (gana el que entró después).
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
    faltó sin pagar.
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
    `out/anclas.log` al final de `importar-out`, de `extract` y de cada pasada
    del servidor, solo si la cabeza ha cambiado. `db verificar` las comprueba.
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
