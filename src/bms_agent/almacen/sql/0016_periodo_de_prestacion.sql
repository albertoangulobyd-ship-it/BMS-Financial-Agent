-- Migracion 0016 (revision del paso 12 de la V1): el periodo de prestacion de
-- una factura, tal como lo entiende el resto del sistema.
--
-- Un fichero aplicado no se edita nunca (ver 0001). Lo que haga falta
-- despues va en 0017, 0018...
--
-- v_factura_listado (0015) sacaba el periodo de una factura sin periodo en la
-- cabecera solo de las fechas de sus lineas. Una factura de horas que imprime
-- "semana 37" en cada linea, sin fechas (lo normal en las de personal), no
-- tenia periodo, y los filtros periodo_desde y periodo_hasta no la
-- encontraban nunca, aunque la vista del Objeto y las horas la pusieran en
-- 2026-W37. El periodo tiene que salir de la misma cuenta que esos:
-- turnos.dias_de (las fechas de cada imputacion, las de su linea, la semana
-- impresa con el ano de la fecha de la factura y, al final, la cabecera).
--
-- El ano de una semana impresa no se puede calcular en la vista (SQLite 3.45
-- no tiene %V en strftime, y "la semana 52 de una factura del 6 de enero" es
-- la del ano anterior: turnos.semana_impresa). Por eso el periodo lo escribe
-- el motor en la cache factura_estado, como el vencimiento efectivo, y la
-- vista lo lee de ahi. Antes de la primera pasada (sin fila en la cache) la
-- vista sigue dando lo de 0015, que nunca es mas de lo que sabe el motor.
--
-- Clases de tabla (spec.md §4): factura_estado sigue siendo CACHE, rehecha
-- por estados.recalcular en cada pasada.

ALTER TABLE factura_estado ADD COLUMN periodo_desde TEXT
    CHECK (periodo_desde IS NULL OR date(periodo_desde) IS periodo_desde);
ALTER TABLE factura_estado ADD COLUMN periodo_hasta TEXT
    CHECK (periodo_hasta IS NULL OR date(periodo_hasta) IS periodo_hasta);

DROP VIEW v_factura_listado;

CREATE VIEW v_factura_listado AS
SELECT f.id, f.sentido, f.tipo, f.origen, f.numero, f.numero_norm,
       CASE WHEN f.sentido = 'entrante' THEN f.emisor_nombre_doc
            ELSE f.receptor_nombre_doc END AS contraparte,
       f.proveedor_id, f.cliente_id, f.fecha_factura,
       CASE WHEN e.factura_id IS NOT NULL THEN e.periodo_desde
            ELSE coalesce(f.periodo_inicio, (
                SELECT min(coalesce(l.fecha_inicio, l.fecha_trabajo)) FROM factura_linea AS l
                WHERE l.factura_id = f.id AND l.retirada_en IS NULL)) END AS periodo_desde,
       CASE WHEN e.factura_id IS NOT NULL THEN e.periodo_hasta
            ELSE coalesce(f.periodo_fin, (
                SELECT max(coalesce(l.fecha_fin, l.fecha_trabajo, l.fecha_inicio))
                FROM factura_linea AS l
                WHERE l.factura_id = f.id AND l.retirada_en IS NULL)) END AS periodo_hasta,
       f.base_cent, f.iva_cent, f.total_cent,
       coalesce(f.base_cent, f.total_cent) AS importe_cent,
       f.anulada, f.fusionada_en_id, r.sustituida_por,
       (f.anulada = 0 AND f.fusionada_en_id IS NULL AND r.sustituida_por IS NULL) AS cuenta,
       e.estado_pago, e.pendiente_cent, e.vencimiento, e.dias_vencida, e.estado_revision,
       e.calidad, e.editada, e.suplementada, e.corregida, e.sin_resolver, e.dudosos,
       e.pendientes, e.sin_datos, e.excepcion_id, e.nivel, e.puntos, e.suelo, e.motivos_json,
       e.ejecucion_id
FROM factura AS f
JOIN v_factura_relaciones AS r ON r.factura_id = f.id
LEFT JOIN factura_estado AS e ON e.factura_id = f.id;
