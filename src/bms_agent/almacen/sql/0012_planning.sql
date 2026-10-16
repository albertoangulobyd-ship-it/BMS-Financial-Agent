-- Migracion 0012 (paso 10 de la V1): el planning de TRNSPRNT y la conciliacion
-- de las horas facturadas con sus turnos.
--
-- Un fichero aplicado no se edita nunca (ver 0001). Lo que haga falta
-- despues va en 0013, 0014...
--
-- Lo que esta migracion garantiza (spec §3.8, §5.B tabla 12, §5.E tabla 34,
-- §7 "Planning" y arquitectura.md, regla 9 y §5):
--   - Cada importacion aceptada del planning es una foto congelada: sus turnos
--     (planning_turno) son evidencia, entran todos o ninguno con su
--     importacion en curso y no se tocan despues. Su evento
--     (planning_registrado, sobre la importacion) lleva la foto de cada turno,
--     y `db verificar` compara las filas con ella.
--   - El planning que vale (v_turno_vigente) es, para cada fecha, el de la
--     importacion aceptada mas nueva que la cubre (cubre_desde a cubre_hasta).
--     Que el planning cambie despues de facturar es la diferencia entre dos
--     fotos (G7, V9), no un turno reescrito.
--   - La traza de una linea de factura a sus turnos es conciliacion: cada
--     imputacion con los turnos de su celda y las horas que se les asignaron.
--     La escribe el motor en cada pasada (conciliacion.py, por campos.py) y no
--     cambia despues: si el planning cambia, la conciliacion sigue diciendo con
--     que turnos se facturo (regla 9); si cambia la imputacion, se retira y se
--     vuelve a conciliar.
--
-- Clases de tabla (spec.md §4):
--   planning_turno: EVIDENCIA (sin UPDATE ni DELETE).
--   conciliacion: CONTROLADA (rev y la guarda generada con
--     scripts/generar_guardas.py), escrita por campos.py.

-- ------------------------------------------------------------ planning_turno

-- Un turno de una importacion del planning, como lo da el fichero. nivel dia:
-- un turno de un dia (fecha es ese dia). nivel semana: una fila de la
-- exportacion semanal pivotada, que se lee a nivel de semana (fecha es el lunes
-- de la semana y dias, los dias de la semana con horas). id_externo es el
-- identificador del turno en TRNSPRNT; si el fichero no lo trae, una clave
-- sintetica (fecha o semana, Objeto, persona, horas de inicio y fin, turno),
-- marcada clave_fragil: no sobrevive a que TRNSPRNT cambie la hora de un turno.
-- estado validado es el turno cuyas horas dio por buenas el planning (las
-- "approved hours" del §7; no es la aprobacion de ningun pago). Los *_ref_doc
-- son como el fichero nombra a cada cosa; los *_id, lo que se resolvio contra
-- el maestro al importar (por coincidencia exacta; nada se crea solo). Uno que
-- no se resolvio entonces se vuelve a buscar en cada pasada (la instantanea),
-- sin tocar la fila.
CREATE TABLE planning_turno (
    id                     INTEGER PRIMARY KEY,
    importacion_id         INTEGER NOT NULL REFERENCES importacion(id),
    posicion               INTEGER NOT NULL CHECK (posicion >= 1),
    id_externo             TEXT NOT NULL CHECK (length(id_externo) > 0),
    clave_fragil           INTEGER NOT NULL CHECK (clave_fragil IN (0, 1)),
    nivel                  TEXT NOT NULL CHECK (nivel IN ('dia', 'semana')),
    fecha                  TEXT NOT NULL CHECK (date(fecha) IS fecha),
    semana_iso             TEXT NOT NULL CHECK (semana_iso GLOB '[0-9][0-9][0-9][0-9]-W[0-5][0-9]'),
    dias                   INTEGER NOT NULL CHECK (dias BETWEEN 0 AND 7),
    hora_inicio            TEXT CHECK (hora_inicio IS NULL OR hora_inicio GLOB '[0-2][0-9]:[0-5][0-9]'),
    hora_fin               TEXT CHECK (hora_fin IS NULL OR hora_fin GLOB '[0-2][0-9]:[0-5][0-9]'),
    pausa_min              INTEGER CHECK (pausa_min IS NULL OR pausa_min >= 0),
    horas_planificadas_mil INTEGER CHECK (horas_planificadas_mil IS NULL OR horas_planificadas_mil >= 0),
    horas_realizadas_mil   INTEGER CHECK (horas_realizadas_mil IS NULL OR horas_realizadas_mil >= 0),
    horas_aprobadas_mil    INTEGER CHECK (horas_aprobadas_mil IS NULL OR horas_aprobadas_mil >= 0),
    estado                 TEXT NOT NULL
                           CHECK (estado IN ('planificado', 'realizado', 'validado', 'cancelado')),
    objeto_ref_doc         TEXT,
    recurso_ref_doc        TEXT,
    proveedor_ref_doc      TEXT,
    cliente_ref_doc        TEXT,
    po_ref_doc             TEXT,
    objeto_id              INTEGER REFERENCES objeto(id),
    recurso_id             INTEGER REFERENCES recurso(id),
    proveedor_id           INTEGER REFERENCES proveedor(id),
    cliente_id             INTEGER REFERENCES cliente(id),
    tipo_servicio          TEXT,
    tipo_turno             TEXT,
    facturable             INTEGER CHECK (facturable IS NULL OR facturable IN (0, 1)),
    tarifa_compra_e4       INTEGER CHECK (tarifa_compra_e4 IS NULL OR tarifa_compra_e4 >= 0),
    tarifa_venta_e4        INTEGER CHECK (tarifa_venta_e4 IS NULL OR tarifa_venta_e4 >= 0),
    datos_origen_json      TEXT NOT NULL CHECK (json_valid(datos_origen_json)),
    UNIQUE (importacion_id, id_externo),
    CHECK (nivel = 'semana' OR dias = 1),
    CHECK (nivel = 'dia' OR strftime('%w', fecha) = '1'),
    CHECK (estado <> 'validado' OR horas_aprobadas_mil IS NOT NULL)
) STRICT;

CREATE INDEX planning_turno_fecha ON planning_turno (fecha);
CREATE INDEX planning_turno_externo ON planning_turno (id_externo);

-- Lo da de alta el importador, con la importacion del planning en curso.
CREATE TRIGGER planning_turno_alta BEFORE INSERT ON planning_turno
WHEN (SELECT estado FROM importacion WHERE id = NEW.importacion_id) IS NOT 'en_curso'
  OR (SELECT fuente FROM importacion WHERE id = NEW.importacion_id) IS NOT 'trnsprnt'
  OR (SELECT tipo FROM importacion WHERE id = NEW.importacion_id) IS NOT 'planning'
  OR (SELECT actor FROM importacion WHERE id = NEW.importacion_id)
         IS NOT (SELECT id FROM usuario WHERE nombre = 'importador' AND es_sistema = 1)
BEGIN SELECT RAISE(ABORT, 'un turno lo da de alta el importador del planning, con su importacion en curso'); END;

CREATE TRIGGER planning_turno_sin_update BEFORE UPDATE ON planning_turno
BEGIN SELECT RAISE(ABORT, 'planning_turno es evidencia: no se modifica'); END;
CREATE TRIGGER planning_turno_sin_delete BEFORE DELETE ON planning_turno
BEGIN SELECT RAISE(ABORT, 'planning_turno es evidencia: no se borra'); END;

-- El planning que vale: de cada turno, el de la importacion aceptada mas
-- nueva (por cuando se exporto y, a igual hora, la que entro despues) que
-- cubre su fecha. Una fila semanal deja de valer en cuanto una importacion mas
-- nueva cubre algun dia de su semana: mezclarla con turnos diarios de esa
-- semana contaria las mismas horas dos veces. Los cancelados estan, con su
-- estado: los que no cuentan los deja fuera quien lee. Lo mismo que
-- reglas/instantanea.turnos_vigentes, que lee de aqui.
CREATE VIEW v_turno_vigente AS
SELECT t.*
FROM planning_turno AS t
JOIN importacion AS i ON i.id = t.importacion_id
WHERE i.estado IN ('aceptada', 'parcial')
  AND NOT EXISTS (
    SELECT 1 FROM importacion AS n
    WHERE n.fuente = i.fuente AND n.tipo = 'planning' AND n.estado IN ('aceptada', 'parcial')
      AND n.id <> i.id
      AND n.cubre_desde <= CASE t.nivel WHEN 'semana' THEN date(t.fecha, '+6 days') ELSE t.fecha END
      AND n.cubre_hasta >= t.fecha
      AND (coalesce(n.exportado_en, n.iniciada_en) > coalesce(i.exportado_en, i.iniciada_en)
           OR (coalesce(n.exportado_en, n.iniciada_en) = coalesce(i.exportado_en, i.iniciada_en)
               AND n.id > i.id)));

-- -------------------------------------------------------------- conciliacion

-- La traza de una imputacion (una linea de factura, o una parte de ella) a los
-- turnos con que se comparo: todos los turnos de su celda (persona o Objeto y
-- dia, semana o periodo; reglas/turnos.py) en el planning
-- que valia al conciliarla, cada uno con las horas de la imputacion que se le
-- asignaron (cero si la imputacion ya no tenia horas para el). huella_imputacion
-- es lo que tenia la imputacion entonces (Objeto, persona, dias, horas): si
-- cambia, la conciliacion se retira y se rehace. Si cambia el planning, no: es
-- lo que se facturo, y la diferencia la dicen G7 y V9.
CREATE TABLE conciliacion (
    id                 INTEGER PRIMARY KEY,
    imputacion_id      INTEGER NOT NULL REFERENCES factura_imputacion(id),
    planning_turno_id  INTEGER NOT NULL REFERENCES planning_turno(id),
    horas_mil          INTEGER NOT NULL CHECK (horas_mil >= 0),
    metodo             TEXT NOT NULL CHECK (metodo IN ('automatica', 'manual')),
    regla              TEXT NOT NULL CHECK (regla IN ('recurso_dia', 'objeto_dia', 'recurso_semana',
                                                       'objeto_semana', 'recurso_periodo',
                                                       'objeto_periodo')),
    huella_imputacion  TEXT CHECK (huella_imputacion IS NULL OR length(huella_imputacion) = 64),
    retirada_en        TEXT CHECK (retirada_en IS NULL OR datetime(retirada_en) IS NOT NULL),
    rev                INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0)
) STRICT;

CREATE INDEX conciliacion_imputacion ON conciliacion (imputacion_id);
CREATE INDEX conciliacion_turno ON conciliacion (planning_turno_id);

-- Una conciliacion automatica la escribe el motor; una manual, una persona
-- activa con cambiar_objeto en su propia orden.
CREATE TRIGGER conciliacion_alta BEFORE INSERT ON conciliacion
WHEN (NEW.metodo = 'automatica'
      AND (SELECT actor FROM evento WHERE id = (SELECT max(id) FROM evento))
          IS NOT (SELECT id FROM usuario WHERE nombre = 'motor' AND es_sistema = 1))
  OR (NEW.metodo = 'manual' AND NOT EXISTS (
        SELECT 1 FROM evento AS e
        JOIN usuario AS u ON u.id = e.usuario_id
        JOIN usuario_rol AS ur ON ur.usuario_id = u.id
        JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id
        WHERE e.id = (SELECT max(id) FROM evento) AND e.actor = e.usuario_id
          AND u.es_sistema = 0 AND u.activo = 1 AND rp.permiso = 'cambiar_objeto'
          AND ur.desde <= e.en AND (ur.hasta IS NULL OR ur.hasta > e.en)))
BEGIN SELECT RAISE(ABORT, 'una conciliacion automatica la escribe el motor; una manual, una persona con cambiar_objeto'); END;

-- Lo que dice una conciliacion no cambia: se retira (una vez) y se escribe otra.
CREATE TRIGGER conciliacion_fija BEFORE UPDATE ON conciliacion
WHEN NEW.imputacion_id IS NOT OLD.imputacion_id
  OR NEW.planning_turno_id IS NOT OLD.planning_turno_id
  OR NEW.horas_mil IS NOT OLD.horas_mil OR NEW.metodo IS NOT OLD.metodo
  OR NEW.regla IS NOT OLD.regla OR NEW.huella_imputacion IS NOT OLD.huella_imputacion
  OR OLD.retirada_en IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'una conciliacion no cambia: se retira y se escribe otra'); END;

-- Por turno del planning que vale: sus horas de referencia (las validadas, si
-- no las realizadas, si no las planificadas; cero si esta cancelado) y las
-- horas que tiene conciliadas con compras y con ventas que cuentan. Un turno se
-- reconoce entre fotos por su id_externo: lo conciliado con la foto de antes
-- cuenta para el mismo turno en la de ahora. Para leer con SQL; las reglas
-- hacen la misma cuenta en Python (reglas/turnos.py).
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
            ELSE coalesce(v.horas_aprobadas_mil, v.horas_realizadas_mil,
                          v.horas_planificadas_mil, 0) END AS horas_referencia_mil,
       coalesce(e.horas_mil, 0) AS horas_compra_mil,
       coalesce(s.horas_mil, 0) AS horas_venta_mil
FROM v_turno_vigente AS v
LEFT JOIN conciliado AS e ON e.id_externo = v.id_externo AND e.sentido = 'entrante'
LEFT JOIN conciliado AS s ON s.id_externo = v.id_externo AND s.sentido = 'saliente';

-- -------------------------------------------------- guardas (generadas)

CREATE TRIGGER conciliacion_guarda_insert BEFORE INSERT ON conciliacion
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'conciliacion' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.imputacion_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'conciliacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'imputacion_id' AND json_extract(valor_nuevo, '$') IS NEW.imputacion_id))
    OR (NEW.planning_turno_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'conciliacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'planning_turno_id' AND json_extract(valor_nuevo, '$') IS NEW.planning_turno_id))
    OR (NEW.horas_mil IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'conciliacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'horas_mil' AND json_extract(valor_nuevo, '$') IS NEW.horas_mil))
    OR (NEW.metodo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'conciliacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'metodo' AND json_extract(valor_nuevo, '$') IS NEW.metodo))
    OR (NEW.regla IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'conciliacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'regla' AND json_extract(valor_nuevo, '$') IS NEW.regla))
    OR (NEW.huella_imputacion IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'conciliacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'huella_imputacion' AND json_extract(valor_nuevo, '$') IS NEW.huella_imputacion))
    OR (NEW.retirada_en IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'conciliacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'retirada_en' AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'conciliacion es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER conciliacion_guarda_update BEFORE UPDATE ON conciliacion
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'conciliacion' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.imputacion_id IS NOT OLD.imputacion_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'conciliacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'imputacion_id' AND json_extract(valor_anterior, '$') IS OLD.imputacion_id
        AND json_extract(valor_nuevo, '$') IS NEW.imputacion_id))
    OR (NEW.planning_turno_id IS NOT OLD.planning_turno_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'conciliacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'planning_turno_id' AND json_extract(valor_anterior, '$') IS OLD.planning_turno_id
        AND json_extract(valor_nuevo, '$') IS NEW.planning_turno_id))
    OR (NEW.horas_mil IS NOT OLD.horas_mil AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'conciliacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'horas_mil' AND json_extract(valor_anterior, '$') IS OLD.horas_mil
        AND json_extract(valor_nuevo, '$') IS NEW.horas_mil))
    OR (NEW.metodo IS NOT OLD.metodo AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'conciliacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'metodo' AND json_extract(valor_anterior, '$') IS OLD.metodo
        AND json_extract(valor_nuevo, '$') IS NEW.metodo))
    OR (NEW.regla IS NOT OLD.regla AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'conciliacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'regla' AND json_extract(valor_anterior, '$') IS OLD.regla
        AND json_extract(valor_nuevo, '$') IS NEW.regla))
    OR (NEW.huella_imputacion IS NOT OLD.huella_imputacion AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'conciliacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'huella_imputacion' AND json_extract(valor_anterior, '$') IS OLD.huella_imputacion
        AND json_extract(valor_nuevo, '$') IS NEW.huella_imputacion))
    OR (NEW.retirada_en IS NOT OLD.retirada_en AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'conciliacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'retirada_en' AND json_extract(valor_anterior, '$') IS OLD.retirada_en
        AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'conciliacion es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER conciliacion_sin_delete BEFORE DELETE ON conciliacion
BEGIN SELECT RAISE(ABORT, 'conciliacion no se borra: una fila se retira o se desactiva'); END;

