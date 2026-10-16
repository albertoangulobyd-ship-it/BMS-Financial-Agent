-- Migracion 0011 (revision del paso 9 de la V1): un abono resta de una PO solo
-- mientras la factura que abona cuenta.
--
-- Un fichero aplicado no se edita nunca (ver 0001). Lo que haga falta
-- despues va en 0012, 0013...
--
-- Lo que esta migracion garantiza (spec §7 "Purchase orders": lo consumido es
-- sin IVA, menos los abonos confirmados, sin las anuladas ni las sustituidas):
--   - v_po_consumo cuenta un abono (acredita o anula, confirmado) solo si la
--     factura que abona sigue contando: ni anulada, ni fusionada en otra, ni
--     sustituida o corregida por otra. Antes, anular o sustituir la original
--     sacaba su cargo de la PO pero dejaba su abono restando: el abono contaba
--     dos veces y lo consumido podia quedar negativo. Es lo mismo que
--     ordenes_compra.cargos y reglas/ordenes.cargos (el test de las tres
--     cuentas lo vigila).
--   - El valor y el fin vigentes (v_po_vigente) no cambian: una modificacion
--     no puede tener fecha posterior a hoy (ordenes_compra.apuntar_modificacion),
--     asi que la de fecha mayor es tambien la ultima que vale.

DROP VIEW v_po_consumo;

CREATE VIEW v_po_consumo AS
WITH abonos_confirmados AS (
    SELECT DISTINCT r.origen_id AS factura_id
    FROM factura_relacion AS r
    JOIN factura AS o ON o.id = r.origen_id
    JOIN factura AS d ON d.id = r.destino_id
    JOIN v_factura_relaciones AS dr ON dr.factura_id = d.id
    WHERE r.estado = 'confirmada' AND r.retirada_en IS NULL AND r.tipo IN ('acredita', 'anula')
      AND o.anulada = 0 AND o.fusionada_en_id IS NULL
      AND d.anulada = 0 AND d.fusionada_en_id IS NULL AND dr.sustituida_por IS NULL
),
consumo AS (
    SELECT i.orden_compra_id, sum(i.importe_cent) AS cent
    FROM v_imputacion_vigente AS i
    JOIN factura AS f ON f.id = i.factura_id
    JOIN orden_compra AS po ON po.id = i.orden_compra_id
    WHERE i.importe_cent IS NOT NULL
      AND f.sentido = CASE po.lado WHEN 'cliente' THEN 'saliente' ELSE 'entrante' END
      AND (f.tipo = 'factura' OR f.id IN (SELECT factura_id FROM abonos_confirmados))
    GROUP BY i.orden_compra_id
)
SELECT v.orden_compra_id, v.numero, v.lado, v.cliente_id, v.proveedor_id, v.cerrada,
       v.valor_original_cent, v.valor_cent, v.fecha_inicio, v.fecha_fin,
       coalesce(c.cent, 0) AS consumido_cent,
       v.valor_cent - coalesce(c.cent, 0) AS restante_cent,
       coalesce(c.cent, 0) * 10000 / v.valor_cent AS consumido_pb,
       (v.valor_cent - coalesce(c.cent, 0)) * 10000 / v.valor_cent AS restante_pb
FROM v_po_vigente AS v LEFT JOIN consumo AS c ON c.orden_compra_id = v.orden_compra_id;
