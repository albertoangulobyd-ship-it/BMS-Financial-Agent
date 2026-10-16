-- Paso 10 (revision): las horas validadas de un turno son las de uno validado.
--
-- v_planning_estado tomaba como horas de referencia las de la columna de
-- horas validadas siempre que tuviera un numero, aunque el turno estuviera
-- planificado o realizado. Lo que dice si unas horas estan validadas es el
-- estado (reglas/turnos.horas_referencia hace la misma cuenta): de uno
-- validado, sus horas validadas; si no, las realizadas, las planificadas y,
-- solo si no hay otras, lo que traiga esa columna. 0012 ya esta aplicada y no
-- se edita: la vista se vuelve a crear aqui.

DROP VIEW v_planning_estado;

CREATE VIEW v_planning_estado AS
WITH conciliado AS (
    SELECT t.id_externo, i.sentido, sum(c.horas_mil) AS horas_mil
    FROM conciliacion AS c
    JOIN planning_turno AS t ON t.id = c.planning_turno_id
    JOIN v_imputacion_vigente AS i ON i.id = c.imputacion_id
    WHERE c.retirada_en IS NULL
    GROUP BY t.id_externo, i.sentido
)
SELECT v.id AS planning_turno_id, v.importacion_id, v.id_externo, v.nivel, v.fecha,
       v.semana_iso, v.estado, v.objeto_id, v.recurso_id, v.proveedor_id, v.cliente_id,
       CASE WHEN v.estado = 'cancelado' THEN 0
            ELSE coalesce(CASE WHEN v.estado = 'validado' THEN v.horas_aprobadas_mil END,
                          v.horas_realizadas_mil, v.horas_planificadas_mil,
                          v.horas_aprobadas_mil, 0) END AS horas_referencia_mil,
       coalesce(e.horas_mil, 0) AS horas_compra_mil,
       coalesce(s.horas_mil, 0) AS horas_venta_mil
FROM v_turno_vigente AS v
LEFT JOIN conciliado AS e ON e.id_externo = v.id_externo AND e.sentido = 'entrante'
LEFT JOIN conciliado AS s ON s.id_externo = v.id_externo AND s.sentido = 'saliente';
