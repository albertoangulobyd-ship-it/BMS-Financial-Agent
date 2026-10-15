# Extracciones v1 de referencia

Siete registros con la forma exacta que escribe `ExtractionRecord.write_json`
(esquema v1, prompt `extract/2026-09-17.1`, modelo `claude-opus-5`). Son la
base de la foto de referencia de `construir_datos` en `tests/golden/` y la
entrada que tendrán que conservar los pasos siguientes de la V1 (el almacén
del paso 1, el adaptador del paso 2, la adaptación a v2 del paso 6).

No se generaron con la API. Están escritas a mano a partir de lo que pone cada
documento y se validan contra `InvoiceExtraction` en los tests.

| Fichero | Qué prueba | ¿Cambia con las correcciones del paso 0? |
| --- | --- | --- |
| `01-limpia.json` | Factura normal al 21 %, horas por semana y obra | No |
| `02-sin-kvk-btw-verlegd.json` | Sin KvK y con IVA trasladado | No |
| `03-con-inyeccion.json` | Texto que pide cambiar el IBAN; el extraído es el de la cabecera y el texto va a `document_notes` | No |
| `04-nota-credito.json` | Abono parcial de la 01, mismo periodo, importes negativos | No |
| `05-uren.json` | Una línea con la unidad «uren» y otra en «stuk» | **Sí**: las 24 horas ya cuentan, en el panel y en la proyección |
| `06-fecha-nl.json` | Fecha de factura copiada como `13-09-2026` | No |
| `07-usd.json` | Factura en dólares, con la unidad «hours» | **Sí**: ya no suma como euros, sale crítica por X1 y queda fuera de todos los agregados, horas incluidas (sale solo como fila y alerta) |

Los tres primeros son las facturas de `scripts/generar_facturas_ejemplo.py`:
su `source_sha256` es el de los PDF que escribe el generador, y hay un test que
lo comprueba. Los otros cuatro no tienen PDF; su hash es el de un texto fijo y
se reconoce como sintético, y así siguen: son el caso «falta el original» de
los pasos 1 y 5. Desde el paso 6 el generador escribe además un abono
(`08-nota-credito.pdf`, el equivalente de la 04) y una factura en dólares
(`09-usd.pdf`, el de la 07), con otro nombre para que su extracción real no
se confunda con estas.

Desde el paso 6 el esquema vigente es el v2. Estas siete siguen siendo v1 a
propósito: se validan contra `InvoiceExtractionV1` y `compat.py` las lee con
la forma v2, con las claves nuevas marcadas «no solicitado en v1».

`tarifas.yaml` es una copia fija de `config/tarifas.ejemplo.yaml`, para que la
foto no dependa de un fichero que se puede editar.

## Las fotos

- `tests/golden/construir_datos_v1.json`: `construir_datos` sobre las siete,
  después de las correcciones. Se regenera con
  `python scripts/regenerar_golden.py`, y solo cuando un paso cambia el panel
  a propósito y lo explica en `docs/v1/registro.md`.
- `tests/golden/construir_datos_v1_antes_sin_afectadas.json`: la foto de
  **antes** de las correcciones, sin `05-uren` ni `07-usd`. Prueba que las
  correcciones no movieron nada fuera de esas dos. No se regenera nunca.
