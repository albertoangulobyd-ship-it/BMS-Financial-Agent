-- Migracion 0009 (revision del paso 8 de la V1): una relacion solo mueve algo
-- mientras sus dos facturas cuentan.
--
-- Un fichero aplicado no se edita nunca (ver 0001). Lo que haga falta
-- despues va en 0010, 0011...
--
-- Lo que esta migracion garantiza (spec §5.D y §7, y el registro del paso 8):
--   - Una relacion confirmada cuyo origen esta anulado (el abono emitido por
--     error, la sustituta que se retiro) o con una de sus dos facturas
--     fusionada en otra (es la copia de otra factura) no mueve nada: ni baja
--     lo pendiente de la original ni la saca de los totales. Es lo mismo que
--     reglas/instantanea.relaciones, que no la cuenta entre las confirmadas.
--     Antes, un abono anulado seguia acreditando y una sustituta anulada
--     seguia sacando a la original de todo, sin que ninguna regla lo viera.
--   - v_proveedor_totales y v_cliente_totales cuentan en lo pagado tambien lo
--     pagado de una factura sustituida o corregida: ese dinero salio del banco
--     aunque la factura ya no cuente en lo facturado ni en lo pendiente. Lo
--     demas (facturas, base, IVA, total, pendiente) sigue sin las sustituidas.
--   - pendiente_cent de las dos vistas es la suma bruta de lo que queda de
--     cada factura que cuenta (total menos pagado menos acreditado), sin la
--     tolerancia de la politica: lo que queda dentro de la tolerancia (una
--     factura que el codigo da por pagada) suma aqui y no en consultas.py ni
--     en la cache factura_estado. Con la tolerancia por defecto (0,00) dicen lo
--     mismo; la tolerancia es de la politica y vive en Python.
--
-- Las vistas que dependen de v_factura_relaciones (v_factura_saldo,
-- v_imputacion_vigente, v_iva_vigente) la leen por su nombre: rehacerla basta.

DROP VIEW v_factura_relaciones;

CREATE VIEW v_factura_relaciones AS
WITH vivas AS (
    SELECT r.origen_id, r.destino_id, r.tipo,
           coalesce(r.importe_cent, -o.total_cent) AS importe_cent
    FROM factura_relacion AS r
    JOIN factura AS o ON o.id = r.origen_id
    JOIN factura AS d ON d.id = r.destino_id
    WHERE r.estado = 'confirmada' AND r.retirada_en IS NULL
      AND o.anulada = 0 AND o.fusionada_en_id IS NULL AND d.fusionada_en_id IS NULL
),
movido AS (
    SELECT destino_id AS factura_id, importe_cent AS cent FROM vivas
    WHERE tipo IN ('acredita', 'anula')
    UNION ALL
    SELECT origen_id, -importe_cent FROM vivas WHERE tipo IN ('acredita', 'anula')
)
SELECT f.id AS factura_id,
       coalesce((SELECT sum(cent) FROM movido AS m WHERE m.factura_id = f.id), 0)
           AS acreditado_cent,
       (SELECT min(origen_id) FROM vivas AS v WHERE v.destino_id = f.id
          AND v.tipo IN ('sustituye', 'corrige')) AS sustituida_por,
       EXISTS (SELECT 1 FROM vivas AS v WHERE v.destino_id = f.id AND v.tipo = 'anula')
           AS anulada_por_abono
FROM factura AS f;

DROP VIEW v_proveedor_totales;

CREATE VIEW v_proveedor_totales AS
SELECT f.proveedor_id,
       count(CASE WHEN s.sustituida_por IS NULL THEN 1 END) AS facturas,
       coalesce(sum(CASE WHEN s.sustituida_por IS NULL THEN f.base_cent END), 0) AS base_cent,
       coalesce(sum(CASE WHEN s.sustituida_por IS NULL THEN f.iva_cent END), 0) AS iva_cent,
       coalesce(sum(CASE WHEN s.sustituida_por IS NULL THEN f.total_cent END), 0) AS total_cent,
       coalesce(sum(s.pagado_cent), 0) AS pagado_cent,
       coalesce(sum(CASE WHEN s.sustituida_por IS NULL THEN s.pendiente_cent END), 0)
           AS pendiente_cent
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
       coalesce(sum(CASE WHEN s.sustituida_por IS NULL THEN s.pendiente_cent END), 0)
           AS pendiente_cent
FROM factura AS f JOIN v_factura_saldo AS s ON s.factura_id = f.id
WHERE f.sentido = 'saliente' AND f.cliente_id IS NOT NULL AND f.anulada = 0
  AND f.fusionada_en_id IS NULL
GROUP BY f.cliente_id;
