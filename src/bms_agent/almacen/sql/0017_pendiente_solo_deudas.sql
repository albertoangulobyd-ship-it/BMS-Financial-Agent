-- Migracion 0017 (revision final de la V1): lo pendiente de una parte es lo
-- que se le debe (o nos debe), no lo que sobra.
--
-- Un fichero aplicado no se edita nunca (ver 0001). Lo que haga falta
-- despues va en 0018, 0019...
--
-- Una factura pagada de mas, o pagada entera y despues abonada, deja un saldo
-- del otro signo que la factura (reglas.pagos.de_mas). El codigo la da por
-- saldada (estado "pagada" o "acreditada", y K2 o R2 dicen lo que sobra):
-- ni vence ni es deuda. Las dos vistas la sumaban en lo pendiente de la parte
-- con su signo, restando de lo que si se debe. Ahora lo pendiente de las dos
-- vistas es la suma de lo que queda en el signo de cada factura, como en
-- consultas.py y en la cache factura_estado. Un abono sin enlazar sigue
-- sumando su saldo (negativo): lo que acredita a la parte es suyo aunque
-- todavia no diga de que factura (R4).
--
-- Lo demas de las dos vistas es lo de 0009: la tolerancia de la politica vive
-- en Python, y aqui no se aplica.

DROP VIEW v_proveedor_totales;

CREATE VIEW v_proveedor_totales AS
SELECT f.proveedor_id,
       count(CASE WHEN s.sustituida_por IS NULL THEN 1 END) AS facturas,
       coalesce(sum(CASE WHEN s.sustituida_por IS NULL THEN f.base_cent END), 0) AS base_cent,
       coalesce(sum(CASE WHEN s.sustituida_por IS NULL THEN f.iva_cent END), 0) AS iva_cent,
       coalesce(sum(CASE WHEN s.sustituida_por IS NULL THEN f.total_cent END), 0) AS total_cent,
       coalesce(sum(s.pagado_cent), 0) AS pagado_cent,
       coalesce(sum(CASE WHEN s.sustituida_por IS NULL
                          AND NOT ((f.total_cent >= 0 AND s.pendiente_cent < 0)
                                   OR (f.total_cent < 0 AND s.pendiente_cent > 0))
                         THEN s.pendiente_cent END), 0) AS pendiente_cent
FROM factura AS f JOIN v_factura_saldo AS s ON s.factura_id = f.id
WHERE f.sentido = 'entrante' AND f.proveedor_id IS NOT NULL AND f.anulada = 0
  AND f.fusionada_en_id IS NULL
GROUP BY f.proveedor_id;

DROP VIEW v_cliente_totales;

CREATE VIEW v_cliente_totales AS
SELECT f.cliente_id,
       count(CASE WHEN s.sustituida_por IS NULL THEN 1 END) AS facturas,
       coalesce(sum(CASE WHEN s.sustituida_por IS NULL THEN f.base_cent END), 0) AS base_cent,
       coalesce(sum(CASE WHEN s.sustituida_por IS NULL THEN f.iva_cent END), 0) AS iva_cent,
       coalesce(sum(CASE WHEN s.sustituida_por IS NULL THEN f.total_cent END), 0) AS total_cent,
       coalesce(sum(s.pagado_cent), 0) AS pagado_cent,
       coalesce(sum(CASE WHEN s.sustituida_por IS NULL
                          AND NOT ((f.total_cent >= 0 AND s.pendiente_cent < 0)
                                   OR (f.total_cent < 0 AND s.pendiente_cent > 0))
                         THEN s.pendiente_cent END), 0) AS pendiente_cent
FROM factura AS f JOIN v_factura_saldo AS s ON s.factura_id = f.id
WHERE f.sentido = 'saliente' AND f.cliente_id IS NOT NULL AND f.anulada = 0
  AND f.fusionada_en_id IS NULL
GROUP BY f.cliente_id;
