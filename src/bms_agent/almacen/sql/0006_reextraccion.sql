-- Migracion 0006 (paso 6 de la V1): la reextraccion con presupuesto, la
-- puerta de activacion y las ediciones manuales que una lectura nueva no
-- puede casar.
--
-- Un fichero aplicado no se edita nunca (ver 0001). Lo que haga falta
-- despues va en 0007, 0008...
--
-- Lo que esta migracion garantiza (spec §3.18 y §10):
--   - Volver a leer un documento ya leido es una pasada aparte
--     (reextraccion), con un presupuesto que la base no deja superar: la
--     estimacion alta de la pasada no puede pasar del presupuesto.
--   - Lo que esa pasada lee es una CANDIDATA (reextraccion_resultado): queda
--     guardada como cualquier extraccion, pero no es la vigente de su
--     documento hasta que una persona con admin la activa (activacion),
--     despues de la puerta de puntuacion. Hasta entonces la vigente sigue
--     siendo la de antes; nada se sobrescribe.
--   - Al activarla, la edicion manual de una linea que la lectura nueva no
--     trae (no se puede casar por su huella) queda apuntada
--     (linea_sin_casar) y es un hallazgo (M2): no se pierde ni se aplica a
--     la linea equivocada.
--
-- Clases de tabla (spec.md §4):
--   reextraccion: EVIDENCIA, como importacion: se rellena mientras esta en
--     curso o esperando su lote, y se congela al terminar.
--   reextraccion_resultado, activacion, linea_sin_casar: SOLO ESCRITURA, cada
--     fila con su evento (que lleva su foto).

-- ------------------------------------------------------------- reextraccion

-- Una pasada de `bms-agent reextraer`. Los importes estan en centimos de
-- dolar (la API cobra en dolares): el presupuesto que se dio, y la horquilla
-- que se estimo antes de pagar (la entrada contada, exacta; la salida,
-- estimada). estimacion_json lleva el detalle y si la salida se midio.
-- lote_id es el identificador del lote en la API de Batches.
CREATE TABLE reextraccion (
    id                     INTEGER PRIMARY KEY,
    modelo                 TEXT NOT NULL CHECK (length(modelo) > 0),
    prompt_version         TEXT NOT NULL CHECK (length(prompt_version) > 0),
    schema_version         TEXT NOT NULL CHECK (length(schema_version) > 0),
    via                    TEXT NOT NULL CHECK (via IN ('api', 'lote')),
    criterio_json          TEXT NOT NULL CHECK (json_valid(criterio_json)),
    documentos             INTEGER NOT NULL CHECK (documentos > 0),
    presupuesto_usd_cent   INTEGER NOT NULL CHECK (presupuesto_usd_cent >= 0),
    estimado_bajo_usd_cent INTEGER NOT NULL CHECK (estimado_bajo_usd_cent >= 0),
    estimado_alto_usd_cent INTEGER NOT NULL,
    salida_medida          INTEGER NOT NULL CHECK (salida_medida IN (0, 1)),
    estimacion_json        TEXT NOT NULL CHECK (json_valid(estimacion_json)),
    lote_id                TEXT CHECK (lote_id IS NULL OR length(lote_id) > 0),
    estado                 TEXT NOT NULL DEFAULT 'en_curso'
                           CHECK (estado IN ('en_curso', 'esperando_lote', 'terminada')),
    extraidas              INTEGER NOT NULL DEFAULT 0 CHECK (extraidas >= 0),
    reintentos             INTEGER NOT NULL DEFAULT 0 CHECK (reintentos >= 0),
    iniciada_en            TEXT NOT NULL CHECK (datetime(iniciada_en) IS NOT NULL),
    terminada_en           TEXT CHECK (terminada_en IS NULL OR datetime(terminada_en) IS NOT NULL),
    iniciada_por           INTEGER REFERENCES usuario(id),
    actor                  INTEGER NOT NULL REFERENCES usuario(id),
    -- La base no deja pagar por encima de lo que se acepto gastar.
    CHECK (estimado_alto_usd_cent >= estimado_bajo_usd_cent
           AND estimado_alto_usd_cent <= presupuesto_usd_cent),
    CHECK ((estado = 'terminada') = (terminada_en IS NOT NULL)),
    CHECK (via = 'lote' OR lote_id IS NULL),
    CHECK (estado <> 'esperando_lote' OR lote_id IS NOT NULL),
    CHECK (extraidas + reintentos <= documentos)
) STRICT;

-- La ejecuta el extractor (usuario de sistema); iniciada_por, si la hay, es
-- la persona que la lanzo.
CREATE TRIGGER reextraccion_quien BEFORE INSERT ON reextraccion
WHEN NEW.actor IS NOT (SELECT id FROM usuario WHERE nombre = 'extractor' AND es_sistema = 1)
  OR (NEW.iniciada_por IS NOT NULL
      AND (SELECT es_sistema FROM usuario WHERE id = NEW.iniciada_por) IS NOT 0)
  OR NEW.estado <> 'en_curso'
BEGIN SELECT RAISE(ABORT, 'una reextraccion la ejecuta el extractor, nace en curso, y iniciada_por es una persona'); END;

CREATE TRIGGER reextraccion_sin_update BEFORE UPDATE ON reextraccion
WHEN OLD.estado = 'terminada'
  OR NEW.id IS NOT OLD.id OR NEW.modelo IS NOT OLD.modelo
  OR NEW.prompt_version IS NOT OLD.prompt_version OR NEW.schema_version IS NOT OLD.schema_version
  OR NEW.via IS NOT OLD.via OR NEW.criterio_json IS NOT OLD.criterio_json
  OR NEW.documentos IS NOT OLD.documentos
  OR NEW.presupuesto_usd_cent IS NOT OLD.presupuesto_usd_cent
  OR NEW.estimado_bajo_usd_cent IS NOT OLD.estimado_bajo_usd_cent
  OR NEW.estimado_alto_usd_cent IS NOT OLD.estimado_alto_usd_cent
  OR NEW.salida_medida IS NOT OLD.salida_medida OR NEW.estimacion_json IS NOT OLD.estimacion_json
  OR (OLD.lote_id IS NOT NULL AND NEW.lote_id IS NOT OLD.lote_id)
  OR NEW.iniciada_en IS NOT OLD.iniciada_en OR NEW.iniciada_por IS NOT OLD.iniciada_por
  OR NEW.actor IS NOT OLD.actor
  OR NEW.extraidas < OLD.extraidas OR NEW.reintentos < OLD.reintentos
BEGIN SELECT RAISE(ABORT, 'una reextraccion solo se modifica mientras esta en curso o esperando su lote, y sin cambiar lo que se acepto pagar'); END;
CREATE TRIGGER reextraccion_sin_delete BEFORE DELETE ON reextraccion
BEGIN SELECT RAISE(ABORT, 'reextraccion es evidencia de lo que se pago: no se borra'); END;

-- ------------------------------------------------------ reextraccion_resultado

-- Lo que dio cada documento de una reextraccion: una extraccion candidata
-- (guardada, no vigente hasta su activacion) o un reintento (un rechazo, un
-- error, un lote caducado o cancelado, una salida que no es el esquema).
-- anterior_id es la extraccion vigente del documento cuando se leyo.
CREATE TABLE reextraccion_resultado (
    id              INTEGER PRIMARY KEY,
    reextraccion_id INTEGER NOT NULL REFERENCES reextraccion(id),
    documento_id    INTEGER NOT NULL REFERENCES documento(id),
    resultado       TEXT NOT NULL CHECK (resultado IN ('candidata', 'reintento')),
    extraccion_id   INTEGER REFERENCES extraccion(id),
    anterior_id     INTEGER REFERENCES extraccion(id),
    motivo          TEXT CHECK (motivo IS NULL OR motivo IN (
                        'rechazo', 'error', 'caducado', 'cancelado', 'invalido')),
    detalle         TEXT,
    en              TEXT NOT NULL CHECK (datetime(en) IS NOT NULL),
    evento_id       INTEGER NOT NULL REFERENCES evento(id),
    CHECK ((resultado = 'candidata') = (extraccion_id IS NOT NULL)),
    CHECK ((resultado = 'reintento') = (motivo IS NOT NULL))
) STRICT;

CREATE UNIQUE INDEX reextraccion_resultado_extraccion ON reextraccion_resultado (extraccion_id)
    WHERE extraccion_id IS NOT NULL;
CREATE INDEX reextraccion_resultado_documento ON reextraccion_resultado (documento_id);

-- Una candidata es una extraccion de su documento, con el modelo y las
-- versiones de su reextraccion, que entra mientras la reextraccion esta
-- abierta y en el evento en curso (el ultimo), que es del extractor.
CREATE TRIGGER reextraccion_resultado_alta BEFORE INSERT ON reextraccion_resultado
WHEN NEW.evento_id IS NOT (SELECT max(id) FROM evento)
  OR (SELECT actor FROM evento WHERE id = NEW.evento_id)
        IS NOT (SELECT id FROM usuario WHERE nombre = 'extractor' AND es_sistema = 1)
  OR (SELECT estado FROM reextraccion WHERE id = NEW.reextraccion_id)
        NOT IN ('en_curso', 'esperando_lote')
  OR (NEW.extraccion_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM extraccion AS e JOIN reextraccion AS r ON r.id = NEW.reextraccion_id
        WHERE e.id = NEW.extraccion_id AND e.documento_id = NEW.documento_id
          AND e.modelo = r.modelo AND e.prompt_version = r.prompt_version
          AND e.schema_version = r.schema_version AND e.via = r.via))
BEGIN SELECT RAISE(ABORT, 'una candidata es una extraccion de su documento y de las versiones de su reextraccion abierta, en el evento del extractor'); END;

CREATE TRIGGER reextraccion_resultado_sin_update BEFORE UPDATE ON reextraccion_resultado
BEGIN SELECT RAISE(ABORT, 'reextraccion_resultado es de solo escritura'); END;
CREATE TRIGGER reextraccion_resultado_sin_delete BEFORE DELETE ON reextraccion_resultado
BEGIN SELECT RAISE(ABORT, 'reextraccion_resultado es de solo escritura: no se borra'); END;

-- ------------------------------------------------------------- activacion

-- Una candidata que pasa a vigente de su documento. La activa una persona
-- con admin, en su propia orden, despues de la puerta: comparacion_sha256 es
-- el hash de la comparacion de versiones que la dejo pasar.
CREATE TABLE activacion (
    id                 INTEGER PRIMARY KEY,
    extraccion_id      INTEGER NOT NULL UNIQUE REFERENCES extraccion(id),
    documento_id       INTEGER NOT NULL REFERENCES documento(id),
    anterior_id        INTEGER REFERENCES extraccion(id),
    comparacion_sha256 TEXT NOT NULL CHECK (length(comparacion_sha256) = 64),
    usuario_id         INTEGER NOT NULL REFERENCES usuario(id),
    en                 TEXT NOT NULL CHECK (datetime(en) IS NOT NULL),
    evento_id          INTEGER NOT NULL REFERENCES evento(id)
) STRICT;

CREATE TRIGGER activacion_alta BEFORE INSERT ON activacion
WHEN NEW.evento_id IS NOT (SELECT max(id) FROM evento)
  OR (SELECT usuario_id FROM evento WHERE id = NEW.evento_id) IS NOT NEW.usuario_id
  OR (SELECT actor FROM evento WHERE id = NEW.evento_id) IS NOT NEW.usuario_id
  OR NOT EXISTS (
        SELECT 1 FROM reextraccion_resultado
        WHERE extraccion_id = NEW.extraccion_id AND documento_id = NEW.documento_id
          AND resultado = 'candidata')
  OR NOT EXISTS (
        SELECT 1 FROM usuario AS u
        JOIN usuario_rol AS ur ON ur.usuario_id = u.id
        JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id
        WHERE u.id = NEW.usuario_id AND u.es_sistema = 0 AND u.activo = 1
          AND rp.permiso = 'admin'
          AND ur.desde <= NEW.en AND (ur.hasta IS NULL OR ur.hasta > NEW.en))
BEGIN SELECT RAISE(ABORT, 'activa una candidata de su documento una persona con admin, en su propia orden'); END;

CREATE TRIGGER activacion_sin_update BEFORE UPDATE ON activacion
BEGIN SELECT RAISE(ABORT, 'activacion es de solo escritura'); END;
CREATE TRIGGER activacion_sin_delete BEFORE DELETE ON activacion
BEGIN SELECT RAISE(ABORT, 'activacion es de solo escritura: no se borra'); END;

-- ---------------------------------------------------------- linea_sin_casar

-- Una linea que una persona edito (o excluyo) y que la extraccion vigente de
-- su factura ya no trae: no se pudo casar por su huella con ninguna linea
-- nueva. Se conserva (nada de lo que escribio una persona se pierde) y la
-- regla M2 la convierte en hallazgo. excluida dice si la persona la habia
-- excluido: su exclusion no se ha podido llevar a la lectura nueva.
CREATE TABLE linea_sin_casar (
    id            INTEGER PRIMARY KEY,
    factura_id    INTEGER NOT NULL REFERENCES factura(id),
    linea_id      INTEGER NOT NULL REFERENCES factura_linea(id),
    extraccion_id INTEGER NOT NULL REFERENCES extraccion(id),
    excluida      INTEGER NOT NULL CHECK (excluida IN (0, 1)),
    campos_json   TEXT NOT NULL CHECK (json_valid(campos_json)),
    en            TEXT NOT NULL CHECK (datetime(en) IS NOT NULL),
    evento_id     INTEGER NOT NULL REFERENCES evento(id),
    UNIQUE (linea_id, extraccion_id)
) STRICT;

CREATE INDEX linea_sin_casar_factura ON linea_sin_casar (factura_id);

-- La apunta el extractor al tipar, para la extraccion vigente de la factura
-- y una linea de esa factura, en el evento en curso.
CREATE TRIGGER linea_sin_casar_alta BEFORE INSERT ON linea_sin_casar
WHEN NEW.evento_id IS NOT (SELECT max(id) FROM evento)
  OR (SELECT actor FROM evento WHERE id = NEW.evento_id)
        IS NOT (SELECT id FROM usuario WHERE nombre = 'extractor' AND es_sistema = 1)
  OR (SELECT factura_id FROM factura_linea WHERE id = NEW.linea_id) IS NOT NEW.factura_id
  OR (SELECT extraccion_vigente_id FROM factura WHERE id = NEW.factura_id) IS NOT NEW.extraccion_id
BEGIN SELECT RAISE(ABORT, 'una linea sin casar la apunta el extractor, de su factura y de la extraccion vigente'); END;

CREATE TRIGGER linea_sin_casar_sin_update BEFORE UPDATE ON linea_sin_casar
BEGIN SELECT RAISE(ABORT, 'linea_sin_casar es de solo escritura'); END;
CREATE TRIGGER linea_sin_casar_sin_delete BEFORE DELETE ON linea_sin_casar
BEGIN SELECT RAISE(ABORT, 'linea_sin_casar es de solo escritura: no se borra'); END;
