-- Migracion 0015 (paso 12 de la V1): el panel principal, la busqueda y la
-- vista economica de cada Objeto.
--
-- Un fichero aplicado no se edita nunca (ver 0001). Lo que haga falta
-- despues va en 0016, 0017...
--
-- Solo vistas: no hay ninguna tabla nueva. Las dos son independientes de la
-- fecha de hoy y suman enteros (spec §5, "Views"); lo que depende de hoy
-- (vencida, esta semana, el ano hasta hoy) lo calcula consultas.py con el
-- `hoy` del reloj del almacen.
--
--   - v_factura_listado: una fila por factura para la busqueda (§18), con lo
--     que la cache factura_estado dice de ella (estado de pago, revision,
--     calidad, marcas de edicion, prioridad) y si cuenta en los totales. La
--     busqueda solo la filtra con fragmentos fijos y valores como parametros:
--     ningun texto de quien busca entra en el SQL.
--   - v_objeto_periodo: lo facturado (ingresos), lo comprado (costes), el
--     margen y las horas de cada Objeto por mes de la fecha de factura (§5).
--     objeto_id NULL es lo imputado sin Objeto. Solo las imputaciones que
--     cuentan (v_imputacion_vigente: ni anuladas, ni fusionadas, ni
--     sustituidas) de facturas con base conocida: una factura sin base (Q1,
--     o en otra moneda, X1, que se lee sin importes) no es ingreso ni coste de
--     nadie hasta que se corrige, igual que no entra en la base total.

-- ------------------------------------------------------------- v_factura_listado

-- El periodo de una factura es el de su cabecera o, si no lo imprime, el de
-- sus lineas activas (el primer inicio o dia de trabajo y el ultimo fin o dia
-- de trabajo). Sin ninguno de los dos, NULL: una busqueda por periodo no la
-- encuentra, porque no se sabe de cuando es.
CREATE VIEW v_factura_listado AS
SELECT f.id, f.sentido, f.tipo, f.origen, f.numero, f.numero_norm,
       CASE WHEN f.sentido = 'entrante' THEN f.emisor_nombre_doc
            ELSE f.receptor_nombre_doc END AS contraparte,
       f.proveedor_id, f.cliente_id, f.fecha_factura,
       coalesce(f.periodo_inicio, (
           SELECT min(coalesce(l.fecha_inicio, l.fecha_trabajo)) FROM factura_linea AS l
           WHERE l.factura_id = f.id AND l.retirada_en IS NULL)) AS periodo_desde,
       coalesce(f.periodo_fin, (
           SELECT max(coalesce(l.fecha_fin, l.fecha_trabajo, l.fecha_inicio))
           FROM factura_linea AS l
           WHERE l.factura_id = f.id AND l.retirada_en IS NULL)) AS periodo_hasta,
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

-- ------------------------------------------------------------- v_objeto_periodo

-- Por Objeto y mes de la fecha de factura ('sin_fecha' si no la tiene). El
-- corte por semana ISO no esta aqui: una linea de un mes entero tiene que
-- repartirse entre sus semanas por sus dias, y eso lo hace consultas.py con
-- trabajo.repartir, la misma cuenta que las horas por semana del Objeto.
CREATE VIEW v_objeto_periodo AS
SELECT i.objeto_id,
       coalesce(substr(i.fecha_factura, 1, 7), 'sin_fecha') AS mes,
       sum(CASE WHEN i.sentido = 'saliente' THEN coalesce(i.importe_cent, 0) ELSE 0 END)
           AS ingresos_cent,
       sum(CASE WHEN i.sentido = 'entrante' THEN coalesce(i.importe_cent, 0) ELSE 0 END)
           AS costes_cent,
       sum(CASE WHEN i.sentido = 'saliente' THEN coalesce(i.importe_cent, 0)
                ELSE -coalesce(i.importe_cent, 0) END) AS margen_cent,
       sum(CASE WHEN i.sentido = 'saliente' THEN coalesce(i.horas_mil, 0) ELSE 0 END)
           AS horas_venta_mil,
       sum(CASE WHEN i.sentido = 'entrante' THEN coalesce(i.horas_mil, 0) ELSE 0 END)
           AS horas_compra_mil,
       count(DISTINCT CASE WHEN i.sentido = 'saliente' THEN i.factura_id END) AS facturas_venta,
       count(DISTINCT CASE WHEN i.sentido = 'entrante' THEN i.factura_id END)
           AS facturas_compra
FROM v_imputacion_vigente AS i
JOIN factura AS f ON f.id = i.factura_id
WHERE f.base_cent IS NOT NULL
GROUP BY i.objeto_id, coalesce(substr(i.fecha_factura, 1, 7), 'sin_fecha');
