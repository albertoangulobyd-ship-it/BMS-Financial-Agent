# Respuestas escritas a mano

Aquí va el conjunto dorado: lo que **realmente** pone cada factura, escrito
por una persona mirando el PDF. Es contra esto que se mide la extracción.

Copia `_ejemplo.yaml` a `respuestas.yaml` y ve rellenándolo. `respuestas.yaml`
está en `.gitignore` porque contiene datos reales de proveedores.

## Cómo rellenarlo

Una entrada por fichero, con el nombre del PDF tal cual. Solo hacen falta los
campos que quieras medir; los que no pongas no se puntúan.

Los importes se escriben **tal como están impresos en la factura**. El
comparador los normaliza, así que `10.575,40` y `10575,40` cuentan igual. Las
fechas admiten tanto `2026-09-15` como `15-09-2026`.

Si la factura **no lleva** un campo, escribe `null`. Detectar correctamente
una ausencia cuenta como acierto, y es justo lo que hay que medir: un sistema
que se inventa el número de KvK que falta es peor que uno que lo deja vacío.

## Campos disponibles

`supplier_name`, `supplier_address`, `kvk_number`, `vat_number`,
`invoice_number`, `invoice_date`, `service_period_start`,
`service_period_end`, `subtotal_excl_vat`, `vat_rate`, `vat_amount`,
`total_incl_vat`, `vat_regime`, `iban`, `due_date`.

Los marcados con `*` en el informe son los que deciden la métrica de salida
de la fase 0: proveedor, número, fecha, IVA, total y periodo de prestación.

## Cuántas

Doscientas facturas reales, con la mezcla que recibís de verdad: los
proveedores habituales, pero también el que manda un escaneo torcido y el que
cambia de plantilla cada mes. Un conjunto solo de facturas fáciles da un
número bonito que no sirve para decidir nada.
