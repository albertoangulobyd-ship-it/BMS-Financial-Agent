-- Migracion 0004 (paso 4 de la V1): excepciones, revision y prioridad.
--
-- Un fichero aplicado no se edita nunca (ver 0001). Lo que haga falta
-- despues va en 0005, 0006... Las tablas 41 a 44 del §5.F de la
-- especificacion: el registro (paso 3, desviacion 25) explica por que no
-- llegaron en la 0003 y por que las migraciones siguientes corren un numero.
--
-- Clases de tabla (spec.md §4):
--   excepcion: CONTROLADA. Lleva rev y la guarda de siempre (generada con
--     scripts/generar_guardas.py): cada columna que entra o cambia tiene su
--     cambio_campo en el evento en curso. No la escribe campos.py sino
--     excepciones.py, porque es estado de trabajo y no un dato de un
--     documento (ver el registro, paso 4). El estado lo pone una persona con
--     resolver_aviso; el motor solo la crea y le une hallazgos.
--   excepcion_hallazgo, revision, prioridad_manual: SOLO ESCRITURA.
--   factura_estado, prioridad: CACHE. Se rehacen en cada pasada del motor y
--     nunca son la fuente de nada; no llevan disparadores.

-- ---------------------------------------------------------------- excepcion

-- El trabajo pendiente de una entidad (una factura, un proveedor...): una
-- abierta como mucho por entidad, que agrupa sus hallazgos que bloquean o
-- retienen. Cada hallazgo sigue con su propia vida; la excepcion es quien se
-- ocupa, de que, hasta cuando y como acabo.
--
-- hallazgo_evento_hasta es el ultimo hallazgo_evento que habia al
-- resolverla: un hallazgo suyo que vuelve a abrirse, o cambia de evidencia,
-- despues de esa marca ya no esta cubierto por esta resolucion y abre otra.
CREATE TABLE excepcion (
    id                    INTEGER PRIMARY KEY,
    titulo                TEXT NOT NULL CHECK (length(trim(titulo)) > 0),
    descripcion           TEXT,
    tabla                 TEXT NOT NULL CHECK (tabla IN ('factura', 'proveedor', 'cliente', 'orden_compra', 'trimestre', 'movimiento', 'importacion')),
    fila_id               INTEGER NOT NULL,
    factura_id            INTEGER REFERENCES factura(id),
    estado                TEXT NOT NULL CHECK (estado IN ('abierta', 'asignada', 'esperando_externo', 'resuelta')),
    responsable_id        INTEGER REFERENCES usuario(id),
    esperando_a           TEXT CHECK (esperando_a IS NULL OR esperando_a IN ('proveedor', 'cliente', 'contable', 'exact', 'trnsprnt', 'banco', 'otro')),
    fecha_seguimiento     TEXT CHECK (fecha_seguimiento IS NULL OR date(fecha_seguimiento) IS fecha_seguimiento),
    resolucion            TEXT CHECK (resolucion IS NULL OR resolucion IN ('corregido', 'aceptado', 'anulado', 'no_procede', 'condicion_desaparecida')),
    resolucion_notas      TEXT,
    creada_en             TEXT NOT NULL CHECK (datetime(creada_en) IS NOT NULL),
    creada_por            INTEGER NOT NULL REFERENCES usuario(id),
    resuelta_en           TEXT CHECK (resuelta_en IS NULL OR datetime(resuelta_en) IS NOT NULL),
    resuelta_por          INTEGER REFERENCES usuario(id),
    hallazgo_evento_hasta INTEGER CHECK (hallazgo_evento_hasta IS NULL OR hallazgo_evento_hasta >= 0),
    rev                   INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0),
    CHECK (estado <> 'asignada' OR responsable_id IS NOT NULL),
    CHECK (estado <> 'esperando_externo' OR (esperando_a IS NOT NULL AND fecha_seguimiento IS NOT NULL)),
    CHECK ((estado = 'resuelta') = (resolucion IS NOT NULL)),
    CHECK ((estado = 'resuelta') = (resuelta_en IS NOT NULL)),
    CHECK ((estado = 'resuelta') = (resuelta_por IS NOT NULL)),
    CHECK ((estado = 'resuelta') = (hallazgo_evento_hasta IS NOT NULL)),
    CHECK (estado <> 'resuelta' OR length(trim(coalesce(resolucion_notas, ''))) > 0),
    CHECK (tabla <> 'factura' OR factura_id = fila_id)
) STRICT;

CREATE UNIQUE INDEX excepcion_abierta_por_entidad ON excepcion (tabla, fila_id)
    WHERE estado <> 'resuelta';
CREATE INDEX excepcion_factura ON excepcion (factura_id);

-- Una excepcion nace abierta; lo demas lo hace una persona.
CREATE TRIGGER excepcion_nace_abierta BEFORE INSERT ON excepcion
WHEN NEW.estado IS NOT 'abierta'
BEGIN SELECT RAISE(ABORT, 'una excepcion nace abierta: asignarla, esperar o resolverla lo hace una persona'); END;

-- A que se refiere y quien la abrio no cambian, y una resuelta ya no se toca:
-- si el problema vuelve, el motor abre otra.
CREATE TRIGGER excepcion_identidad BEFORE UPDATE ON excepcion
WHEN OLD.estado = 'resuelta'
  OR NEW.tabla IS NOT OLD.tabla OR NEW.fila_id IS NOT OLD.fila_id
  OR NEW.factura_id IS NOT OLD.factura_id
  OR NEW.creada_en IS NOT OLD.creada_en OR NEW.creada_por IS NOT OLD.creada_por
BEGIN SELECT RAISE(ABORT, 'una excepcion resuelta no se toca, y a que se refiere no cambia'); END;

-- El responsable es una persona activa, nunca un usuario de sistema.
CREATE TRIGGER excepcion_responsable_alta BEFORE INSERT ON excepcion
WHEN NEW.responsable_id IS NOT NULL
 AND (SELECT es_sistema = 0 AND activo = 1 FROM usuario WHERE id = NEW.responsable_id) IS NOT 1
BEGIN SELECT RAISE(ABORT, 'el responsable de una excepcion es una persona activa'); END;
CREATE TRIGGER excepcion_responsable BEFORE UPDATE ON excepcion
WHEN NEW.responsable_id IS NOT OLD.responsable_id AND NEW.responsable_id IS NOT NULL
 AND (SELECT es_sistema = 0 AND activo = 1 FROM usuario WHERE id = NEW.responsable_id) IS NOT 1
BEGIN SELECT RAISE(ABORT, 'el responsable de una excepcion es una persona activa'); END;

-- El estado de una excepcion lo pone una persona con resolver_aviso, en su
-- propia orden: el evento en curso es suyo (actor y usuario ella).
CREATE TRIGGER excepcion_de_persona BEFORE UPDATE ON excepcion
WHEN (NEW.estado IS NOT OLD.estado OR NEW.responsable_id IS NOT OLD.responsable_id
      OR NEW.esperando_a IS NOT OLD.esperando_a
      OR NEW.fecha_seguimiento IS NOT OLD.fecha_seguimiento
      OR NEW.resolucion IS NOT OLD.resolucion OR NEW.resolucion_notas IS NOT OLD.resolucion_notas
      OR NEW.resuelta_en IS NOT OLD.resuelta_en OR NEW.resuelta_por IS NOT OLD.resuelta_por
      OR NEW.hallazgo_evento_hasta IS NOT OLD.hallazgo_evento_hasta)
 AND NOT EXISTS (
        SELECT 1 FROM evento AS e
        JOIN usuario AS u ON u.id = e.usuario_id
        JOIN usuario_rol AS ur ON ur.usuario_id = u.id
        JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id
        WHERE e.id = (SELECT max(id) FROM evento) AND e.actor = e.usuario_id
          AND u.es_sistema = 0 AND u.activo = 1 AND rp.permiso = 'resolver_aviso'
          AND ur.desde <= e.en AND (ur.hasta IS NULL OR ur.hasta > e.en))
BEGIN SELECT RAISE(ABORT, 'el estado de una excepcion lo pone una persona con resolver_aviso, en su propia orden'); END;

-- No se resuelve mientras un hallazgo suyo que bloquea siga abierto (sin
-- anular), y la resuelve quien firma la orden.
CREATE TRIGGER excepcion_resolver BEFORE UPDATE ON excepcion
WHEN NEW.estado = 'resuelta' AND (
       EXISTS (SELECT 1 FROM excepcion_hallazgo AS eh JOIN hallazgo AS h ON h.id = eh.hallazgo_id
               WHERE eh.excepcion_id = NEW.id AND h.severidad = 'bloqueo' AND h.estado = 'abierto')
    OR NEW.resuelta_por IS NOT (SELECT usuario_id FROM evento WHERE id = (SELECT max(id) FROM evento)))
BEGIN SELECT RAISE(ABORT, 'una excepcion con un hallazgo que bloquea abierto y sin anular no se resuelve'); END;

-- ------------------------------------------------------- excepcion_hallazgo

-- Que hallazgos agrupa cada excepcion. Solo se anaden, en el evento en curso
-- (el de la pasada del motor o el de la persona que abre una a mano), y a
-- una excepcion que no esta resuelta.
CREATE TABLE excepcion_hallazgo (
    id           INTEGER PRIMARY KEY,
    excepcion_id INTEGER NOT NULL REFERENCES excepcion(id),
    hallazgo_id  INTEGER NOT NULL REFERENCES hallazgo(id),
    vinculado_en TEXT NOT NULL CHECK (datetime(vinculado_en) IS NOT NULL),
    evento_id    INTEGER NOT NULL REFERENCES evento(id),
    UNIQUE (excepcion_id, hallazgo_id)
) STRICT;

CREATE INDEX excepcion_hallazgo_hallazgo ON excepcion_hallazgo (hallazgo_id);

CREATE TRIGGER excepcion_hallazgo_en_su_evento BEFORE INSERT ON excepcion_hallazgo
WHEN NEW.evento_id IS NOT (SELECT max(id) FROM evento)
  OR (SELECT estado FROM excepcion WHERE id = NEW.excepcion_id) IS 'resuelta'
BEGIN SELECT RAISE(ABORT, 'un hallazgo se une a una excepcion sin resolver, en el evento en curso'); END;

CREATE TRIGGER excepcion_hallazgo_sin_update BEFORE UPDATE ON excepcion_hallazgo
BEGIN SELECT RAISE(ABORT, 'excepcion_hallazgo es de solo escritura: no se modifica'); END;
CREATE TRIGGER excepcion_hallazgo_sin_delete BEFORE DELETE ON excepcion_hallazgo
BEGIN SELECT RAISE(ABORT, 'excepcion_hallazgo es de solo escritura: no se borra'); END;

-- ----------------------------------------------------------------- revision

-- Una persona con revisar_factura revisa una factura (revisada) o la
-- devuelve (devuelta, con una nota que diga por que). La revision guarda la
-- huella del contenido que vio: cualquier cambio despues la deja sin efecto,
-- sin tocar esta fila. autorrevisada: la persona revisa algo que cambio o
-- anulo ella misma y no hay otra con el permiso (politica "si hay dos").
CREATE TABLE revision (
    id               INTEGER PRIMARY KEY,
    factura_id       INTEGER NOT NULL REFERENCES factura(id),
    resultado        TEXT NOT NULL CHECK (resultado IN ('revisada', 'devuelta')),
    huella_contenido TEXT NOT NULL CHECK (length(huella_contenido) = 64),
    autorrevisada    INTEGER NOT NULL DEFAULT 0 CHECK (autorrevisada IN (0, 1)),
    usuario_id       INTEGER NOT NULL REFERENCES usuario(id),
    en               TEXT NOT NULL CHECK (datetime(en) IS NOT NULL),
    nota             TEXT,
    evento_id        INTEGER NOT NULL UNIQUE REFERENCES evento(id),
    CHECK (resultado = 'revisada' OR length(trim(coalesce(nota, ''))) > 0),
    CHECK (autorrevisada = 0 OR resultado = 'revisada')
) STRICT;

CREATE INDEX revision_factura ON revision (factura_id, id);

CREATE TRIGGER revision_de_persona BEFORE INSERT ON revision
WHEN NOT EXISTS (
        SELECT 1 FROM usuario AS u
        JOIN usuario_rol AS ur ON ur.usuario_id = u.id
        JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id
        WHERE u.id = NEW.usuario_id AND u.es_sistema = 0 AND u.activo = 1
          AND rp.permiso = 'revisar_factura'
          AND ur.desde <= NEW.en AND (ur.hasta IS NULL OR ur.hasta > NEW.en))
  OR NEW.evento_id IS NOT (SELECT max(id) FROM evento)
  OR (SELECT usuario_id FROM evento WHERE id = NEW.evento_id) IS NOT NEW.usuario_id
  OR (SELECT actor FROM evento WHERE id = NEW.evento_id) IS NOT NEW.usuario_id
BEGIN SELECT RAISE(ABORT, 'una factura la revisa una persona con revisar_factura, en su propia orden'); END;

CREATE TRIGGER revision_sin_update BEFORE UPDATE ON revision
BEGIN SELECT RAISE(ABORT, 'revision es de solo escritura: no se modifica'); END;
CREATE TRIGGER revision_sin_delete BEFORE DELETE ON revision
BEGIN SELECT RAISE(ABORT, 'revision es de solo escritura: no se borra'); END;

-- -------------------------------------------------------- prioridad_manual

-- Una persona sube la prioridad de algo, con un motivo y, si quiere, hasta
-- una fecha. Solo se sube: una fila nueva nunca baja nada (la prioridad es
-- el maximo de los suelos, los puntos y las subidas vigentes), no se puede
-- subir a bloqueada (detras de un bloqueo hay siempre una regla con nombre)
-- y no se admite una "subida" por debajo de lo que ya se ve.
-- entidad_id de un trimestre es ano * 10 + trimestre (20263 es 2026-T3).
CREATE TABLE prioridad_manual (
    id         INTEGER PRIMARY KEY,
    entidad    TEXT NOT NULL CHECK (entidad IN ('factura', 'excepcion', 'proveedor', 'cliente', 'objeto', 'orden_compra', 'trimestre')),
    entidad_id INTEGER NOT NULL,
    nivel      TEXT NOT NULL CHECK (nivel IN ('atencion', 'urgente')),
    motivo     TEXT NOT NULL CHECK (length(trim(motivo)) >= 10),
    usuario_id INTEGER NOT NULL REFERENCES usuario(id),
    en         TEXT NOT NULL CHECK (datetime(en) IS NOT NULL),
    hasta      TEXT CHECK (hasta IS NULL OR date(hasta) IS hasta),
    evento_id  INTEGER NOT NULL UNIQUE REFERENCES evento(id)
) STRICT;

CREATE INDEX prioridad_manual_entidad ON prioridad_manual (entidad, entidad_id);

CREATE TRIGGER prioridad_manual_de_persona BEFORE INSERT ON prioridad_manual
WHEN NOT EXISTS (
        SELECT 1 FROM usuario AS u
        JOIN usuario_rol AS ur ON ur.usuario_id = u.id
        JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id
        WHERE u.id = NEW.usuario_id AND u.es_sistema = 0 AND u.activo = 1
          AND rp.permiso = 'resolver_aviso'
          AND ur.desde <= NEW.en AND (ur.hasta IS NULL OR ur.hasta > NEW.en))
  OR NEW.evento_id IS NOT (SELECT max(id) FROM evento)
  OR (SELECT usuario_id FROM evento WHERE id = NEW.evento_id) IS NOT NEW.usuario_id
BEGIN SELECT RAISE(ABORT, 'una prioridad la sube una persona con resolver_aviso, en su propia orden'); END;

CREATE TRIGGER prioridad_manual_solo_sube BEFORE INSERT ON prioridad_manual
WHEN (CASE NEW.nivel WHEN 'atencion' THEN 1 WHEN 'urgente' THEN 2 ELSE 9 END) < coalesce((
        SELECT max(CASE nivel WHEN 'normal' THEN 0 WHEN 'atencion' THEN 1
                              WHEN 'urgente' THEN 2 WHEN 'bloqueada' THEN 3 END)
        FROM (SELECT nivel FROM factura_estado
              WHERE NEW.entidad = 'factura' AND factura_id = NEW.entidad_id
              UNION ALL
              SELECT nivel FROM prioridad
              WHERE entidad = NEW.entidad AND entidad_id = NEW.entidad_id)), -1)
BEGIN SELECT RAISE(ABORT, 'una prioridad solo se sube: esta ya esta por encima del nivel pedido'); END;

CREATE TRIGGER prioridad_manual_sin_update BEFORE UPDATE ON prioridad_manual
BEGIN SELECT RAISE(ABORT, 'prioridad_manual es de solo escritura: no se modifica'); END;
CREATE TRIGGER prioridad_manual_sin_delete BEFORE DELETE ON prioridad_manual
BEGIN SELECT RAISE(ABORT, 'prioridad_manual es de solo escritura: no se borra'); END;

-- ----------------------------------------------------------- factura_estado

-- CACHE. Una fila por factura, rehecha en cada pasada del motor (cada orden,
-- cada importacion y la diaria). Lleva lo que los filtros del §18 consultan
-- con SQL y el resultado de la prioridad (§8) con la huella de sus entradas y
-- el hash de la politica con que se calculo.
--
-- estado_pago: sin pagos importados (paso 7) toda factura en juego esta
-- pendiente o vencida por su vencimiento; NULL en una fusionada en otra.
-- vencimiento es el efectivo: el impreso, o la fecha de factura mas el plazo
-- de pago. sin_resolver cuenta los cambios manuales sin resolver (M1) y las
-- ediciones que cerraron un hallazgo y nadie ha verificado; dudosos, los
-- campos criticos dudosos sin verificar (Q2). huella_contenido es la de la
-- revision (revision.huella_contenido), y solo esta donde hay una revision
-- que comprobar. Los CHECK de lista son cadenas de OR y no IN (...), como en
-- evaluacion (0003): la pasada reescribe miles de filas y SQLite monta una
-- tabla efimera para cada IN en cada fila.
CREATE TABLE factura_estado (
    factura_id       INTEGER PRIMARY KEY REFERENCES factura(id),
    estado_pago      TEXT CHECK (estado_pago IS NULL OR estado_pago = 'pendiente' OR estado_pago = 'vencida' OR estado_pago = 'pagada' OR estado_pago = 'anulada'),
    pendiente_cent   INTEGER,
    vencimiento      TEXT CHECK (vencimiento IS NULL OR date(vencimiento) IS vencimiento),
    dias_vencida     INTEGER,
    estado_revision  TEXT NOT NULL CHECK (estado_revision = 'sin_revisar' OR estado_revision = 'necesita_revision' OR estado_revision = 'revisada'),
    calidad          TEXT CHECK (calidad IS NULL OR calidad = 'faltante' OR calidad = 'discrepancia' OR calidad = 'anomalia' OR calidad = 'dudoso' OR calidad = 'verificado'),
    editada          INTEGER NOT NULL CHECK (editada = 0 OR editada = 1),
    suplementada     INTEGER NOT NULL CHECK (suplementada = 0 OR suplementada = 1),
    corregida        INTEGER NOT NULL CHECK (corregida = 0 OR corregida = 1),
    sin_resolver     INTEGER NOT NULL CHECK (sin_resolver >= 0),
    dudosos          INTEGER NOT NULL CHECK (dudosos >= 0),
    pendientes       INTEGER NOT NULL CHECK (pendientes >= 0),
    sin_datos        INTEGER NOT NULL CHECK (sin_datos >= 0),
    excepcion_id     INTEGER REFERENCES excepcion(id),
    nivel            TEXT NOT NULL CHECK (nivel = 'normal' OR nivel = 'atencion' OR nivel = 'urgente' OR nivel = 'bloqueada'),
    puntos           INTEGER NOT NULL CHECK (puntos >= 0),
    suelo            TEXT NOT NULL CHECK (suelo = 'normal' OR suelo = 'atencion' OR suelo = 'urgente' OR suelo = 'bloqueada'),
    motivos_json     TEXT NOT NULL CHECK (json_valid(motivos_json)),
    huella_contenido TEXT CHECK (huella_contenido IS NULL OR length(huella_contenido) = 64),
    huella_entradas  TEXT NOT NULL CHECK (length(huella_entradas) = 64),
    politica_sha256  TEXT NOT NULL CHECK (length(politica_sha256) = 64),
    ejecucion_id     INTEGER NOT NULL REFERENCES ejecucion_reglas(id)
) STRICT;

CREATE INDEX factura_estado_nivel ON factura_estado (nivel);

-- ---------------------------------------------------------------- prioridad

-- CACHE. La prioridad de lo que no es una factura: cada excepcion sin
-- resolver (el maximo de los suelos de sus hallazgos y el nivel de su
-- factura) y cada proveedor, cliente, Objeto y trimestre (el maximo de sus
-- facturas). vencimiento e importe_cent son los de su hija mas urgente, para
-- ordenar igual que las facturas.
CREATE TABLE prioridad (
    id              INTEGER PRIMARY KEY,
    entidad         TEXT NOT NULL CHECK (entidad = 'excepcion' OR entidad = 'proveedor' OR entidad = 'cliente' OR entidad = 'objeto' OR entidad = 'orden_compra' OR entidad = 'trimestre'),
    entidad_id      INTEGER NOT NULL,
    nivel           TEXT NOT NULL CHECK (nivel = 'normal' OR nivel = 'atencion' OR nivel = 'urgente' OR nivel = 'bloqueada'),
    puntos          INTEGER NOT NULL CHECK (puntos >= 0),
    suelo           TEXT NOT NULL CHECK (suelo = 'normal' OR suelo = 'atencion' OR suelo = 'urgente' OR suelo = 'bloqueada'),
    motivos_json    TEXT NOT NULL CHECK (json_valid(motivos_json)),
    vencimiento     TEXT CHECK (vencimiento IS NULL OR date(vencimiento) IS vencimiento),
    importe_cent    INTEGER,
    huella_entradas TEXT NOT NULL CHECK (length(huella_entradas) = 64),
    politica_sha256 TEXT NOT NULL CHECK (length(politica_sha256) = 64),
    ejecucion_id    INTEGER NOT NULL REFERENCES ejecucion_reglas(id),
    UNIQUE (entidad, entidad_id)
) STRICT;

-- ------------------------------------------------- guarda de la excepcion
--
-- Generada con scripts/generar_guardas.py excepcion, como las de la 0002:
-- test_campos.py comprueba que cada columna esta en ella y que es la del
-- script.

CREATE TRIGGER excepcion_guarda_insert BEFORE INSERT ON excepcion
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.titulo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'titulo' AND json_extract(valor_nuevo, '$') IS NEW.titulo))
    OR (NEW.descripcion IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'descripcion' AND json_extract(valor_nuevo, '$') IS NEW.descripcion))
    OR (NEW.tabla IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tabla' AND json_extract(valor_nuevo, '$') IS NEW.tabla))
    OR (NEW.fila_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fila_id' AND json_extract(valor_nuevo, '$') IS NEW.fila_id))
    OR (NEW.factura_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'factura_id' AND json_extract(valor_nuevo, '$') IS NEW.factura_id))
    OR (NEW.estado IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'estado' AND json_extract(valor_nuevo, '$') IS NEW.estado))
    OR (NEW.responsable_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'responsable_id' AND json_extract(valor_nuevo, '$') IS NEW.responsable_id))
    OR (NEW.esperando_a IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'esperando_a' AND json_extract(valor_nuevo, '$') IS NEW.esperando_a))
    OR (NEW.fecha_seguimiento IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fecha_seguimiento' AND json_extract(valor_nuevo, '$') IS NEW.fecha_seguimiento))
    OR (NEW.resolucion IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'resolucion' AND json_extract(valor_nuevo, '$') IS NEW.resolucion))
    OR (NEW.resolucion_notas IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'resolucion_notas' AND json_extract(valor_nuevo, '$') IS NEW.resolucion_notas))
    OR (NEW.creada_en IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'creada_en' AND json_extract(valor_nuevo, '$') IS NEW.creada_en))
    OR (NEW.creada_por IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'creada_por' AND json_extract(valor_nuevo, '$') IS NEW.creada_por))
    OR (NEW.resuelta_en IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'resuelta_en' AND json_extract(valor_nuevo, '$') IS NEW.resuelta_en))
    OR (NEW.resuelta_por IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'resuelta_por' AND json_extract(valor_nuevo, '$') IS NEW.resuelta_por))
    OR (NEW.hallazgo_evento_hasta IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'hallazgo_evento_hasta' AND json_extract(valor_nuevo, '$') IS NEW.hallazgo_evento_hasta))
BEGIN SELECT RAISE(ABORT, 'excepcion es una tabla controlada: solo la escribe excepciones.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER excepcion_guarda_update BEFORE UPDATE ON excepcion
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.titulo IS NOT OLD.titulo AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'titulo' AND json_extract(valor_anterior, '$') IS OLD.titulo
        AND json_extract(valor_nuevo, '$') IS NEW.titulo))
    OR (NEW.descripcion IS NOT OLD.descripcion AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'descripcion' AND json_extract(valor_anterior, '$') IS OLD.descripcion
        AND json_extract(valor_nuevo, '$') IS NEW.descripcion))
    OR (NEW.tabla IS NOT OLD.tabla AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tabla' AND json_extract(valor_anterior, '$') IS OLD.tabla
        AND json_extract(valor_nuevo, '$') IS NEW.tabla))
    OR (NEW.fila_id IS NOT OLD.fila_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fila_id' AND json_extract(valor_anterior, '$') IS OLD.fila_id
        AND json_extract(valor_nuevo, '$') IS NEW.fila_id))
    OR (NEW.factura_id IS NOT OLD.factura_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'factura_id' AND json_extract(valor_anterior, '$') IS OLD.factura_id
        AND json_extract(valor_nuevo, '$') IS NEW.factura_id))
    OR (NEW.estado IS NOT OLD.estado AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'estado' AND json_extract(valor_anterior, '$') IS OLD.estado
        AND json_extract(valor_nuevo, '$') IS NEW.estado))
    OR (NEW.responsable_id IS NOT OLD.responsable_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'responsable_id' AND json_extract(valor_anterior, '$') IS OLD.responsable_id
        AND json_extract(valor_nuevo, '$') IS NEW.responsable_id))
    OR (NEW.esperando_a IS NOT OLD.esperando_a AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'esperando_a' AND json_extract(valor_anterior, '$') IS OLD.esperando_a
        AND json_extract(valor_nuevo, '$') IS NEW.esperando_a))
    OR (NEW.fecha_seguimiento IS NOT OLD.fecha_seguimiento AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fecha_seguimiento' AND json_extract(valor_anterior, '$') IS OLD.fecha_seguimiento
        AND json_extract(valor_nuevo, '$') IS NEW.fecha_seguimiento))
    OR (NEW.resolucion IS NOT OLD.resolucion AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'resolucion' AND json_extract(valor_anterior, '$') IS OLD.resolucion
        AND json_extract(valor_nuevo, '$') IS NEW.resolucion))
    OR (NEW.resolucion_notas IS NOT OLD.resolucion_notas AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'resolucion_notas' AND json_extract(valor_anterior, '$') IS OLD.resolucion_notas
        AND json_extract(valor_nuevo, '$') IS NEW.resolucion_notas))
    OR (NEW.creada_en IS NOT OLD.creada_en AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'creada_en' AND json_extract(valor_anterior, '$') IS OLD.creada_en
        AND json_extract(valor_nuevo, '$') IS NEW.creada_en))
    OR (NEW.creada_por IS NOT OLD.creada_por AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'creada_por' AND json_extract(valor_anterior, '$') IS OLD.creada_por
        AND json_extract(valor_nuevo, '$') IS NEW.creada_por))
    OR (NEW.resuelta_en IS NOT OLD.resuelta_en AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'resuelta_en' AND json_extract(valor_anterior, '$') IS OLD.resuelta_en
        AND json_extract(valor_nuevo, '$') IS NEW.resuelta_en))
    OR (NEW.resuelta_por IS NOT OLD.resuelta_por AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'resuelta_por' AND json_extract(valor_anterior, '$') IS OLD.resuelta_por
        AND json_extract(valor_nuevo, '$') IS NEW.resuelta_por))
    OR (NEW.hallazgo_evento_hasta IS NOT OLD.hallazgo_evento_hasta AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'excepcion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'hallazgo_evento_hasta' AND json_extract(valor_anterior, '$') IS OLD.hallazgo_evento_hasta
        AND json_extract(valor_nuevo, '$') IS NEW.hallazgo_evento_hasta))
BEGIN SELECT RAISE(ABORT, 'excepcion es una tabla controlada: solo la escribe excepciones.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER excepcion_sin_delete BEFORE DELETE ON excepcion
BEGIN SELECT RAISE(ABORT, 'excepcion no se borra: una fila se retira o se desactiva'); END;

