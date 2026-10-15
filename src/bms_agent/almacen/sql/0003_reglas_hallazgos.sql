-- Migracion 0003 (paso 3 de la V1): el motor de reglas y sus hallazgos.
--
-- Un fichero aplicado no se edita nunca (ver 0001). Lo que haga falta
-- despues va en 0004, 0005...
--
-- Clases de tabla (spec.md §4):
--   ejecucion_reglas: una fila por pasada del motor. Se rellena mientras
--     esta en curso y se congela al cerrarse (como importacion); no se borra.
--   evaluacion: CACHE. El ultimo resultado de cada regla sobre cada fila,
--     tambien los que pasan. Se rehace entera en cada pasada y nunca es la
--     fuente de nada.
--   hallazgo: una fila por hallazgo (clave UNIQUE). Su estado y su huella
--     solo cambian si el ultimo hallazgo_evento dice esos mismos: no hay
--     cambio de estado sin su historia. No se borra.
--   hallazgo_objetivo: CACHE de a que filas (y campos) se refiere hoy un
--     hallazgo; se rehace cuando cambian.
--   hallazgo_evento, anulacion: SOLO ESCRITURA. La historia de cada aviso y
--     las anulaciones que firmo cada persona.
--
-- La identidad de un hallazgo (clave: regla, objetivo y llave) va separada de
-- su evidencia (huella: los valores comparados, sus fuentes y los parametros
-- de la politica). Una anulacion queda atada a la huella que acepto: si la
-- evidencia cambia, deja de valer.
--
-- Las transiciones que se permiten las dice el disparador
-- hallazgo_evento_transicion. En particular, un hallazgo de una regla
-- pegajosa no se puede cerrar solo (cerrado_automatico): queda
-- desaparecido hasta que una persona lo resuelve.

-- --------------------------------------------------------- ejecucion_reglas

-- hasta_evento_id es el ultimo evento de auditoria que habia al empezar: la
-- siguiente pasada busca la causa de cada cambio entre los posteriores.
CREATE TABLE ejecucion_reglas (
    id              INTEGER PRIMARY KEY,
    motivo          TEXT NOT NULL CHECK (motivo IN ('ingesta', 'importacion', 'edicion', 'diaria', 'manual')),
    hoy             TEXT NOT NULL CHECK (date(hoy) IS hoy),
    iniciada_en     TEXT NOT NULL CHECK (datetime(iniciada_en) IS NOT NULL),
    terminada_en    TEXT CHECK (terminada_en IS NULL OR datetime(terminada_en) IS NOT NULL),
    usuario_id      INTEGER REFERENCES usuario(id),
    actor           INTEGER NOT NULL REFERENCES usuario(id),
    version_codigo  TEXT NOT NULL CHECK (length(version_codigo) > 0),
    catalogo_sha256 TEXT NOT NULL CHECK (length(catalogo_sha256) = 64),
    politica_sha256 TEXT NOT NULL CHECK (length(politica_sha256) = 64),
    hasta_evento_id INTEGER NOT NULL CHECK (hasta_evento_id >= 0),
    causa_evento_id INTEGER REFERENCES evento(id),
    resumen_json    TEXT CHECK (resumen_json IS NULL OR json_valid(resumen_json)),
    CHECK (terminada_en IS NULL OR terminada_en >= iniciada_en)
) STRICT;

CREATE TRIGGER ejecucion_reglas_quien BEFORE INSERT ON ejecucion_reglas
WHEN (SELECT es_sistema FROM usuario WHERE id = NEW.actor) IS NOT 1
  OR (NEW.usuario_id IS NOT NULL
      AND (SELECT es_sistema FROM usuario WHERE id = NEW.usuario_id) IS NOT 0)
BEGIN SELECT RAISE(ABORT, 'el motor actua como usuario de sistema; usuario_id es la persona que lo lanzo'); END;

CREATE TRIGGER ejecucion_reglas_sin_update BEFORE UPDATE ON ejecucion_reglas
WHEN OLD.terminada_en IS NOT NULL
  OR NEW.id IS NOT OLD.id OR NEW.motivo IS NOT OLD.motivo OR NEW.hoy IS NOT OLD.hoy
  OR NEW.iniciada_en IS NOT OLD.iniciada_en OR NEW.usuario_id IS NOT OLD.usuario_id
  OR NEW.actor IS NOT OLD.actor OR NEW.version_codigo IS NOT OLD.version_codigo
  OR NEW.catalogo_sha256 IS NOT OLD.catalogo_sha256
  OR NEW.politica_sha256 IS NOT OLD.politica_sha256
  OR NEW.hasta_evento_id IS NOT OLD.hasta_evento_id
  OR NEW.causa_evento_id IS NOT OLD.causa_evento_id
BEGIN SELECT RAISE(ABORT, 'una ejecucion de reglas solo se cierra, una vez, mientras esta en curso'); END;
CREATE TRIGGER ejecucion_reglas_sin_delete BEFORE DELETE ON ejecucion_reglas
BEGIN SELECT RAISE(ABORT, 'una ejecucion de reglas es evidencia de lo que se evaluo: no se borra'); END;

-- --------------------------------------------------------------- evaluacion

-- clave es la del hallazgo que daria esta evaluacion si fallara (la misma de
-- hallazgo.clave): en una regla de grupo (B2, B3, B4, G3) cada factura del
-- grupo tiene su fila y todas comparten la clave del grupo. valores_json va
-- en los fallos y en los sin_datos; en un ok son los valores de la factura.
-- Que no haya dos resultados de una regla para la misma fila y clave lo
-- comprueba el motor antes de escribir (motor.ResultadoDuplicado); aqui basta
-- el indice de "que dicen las reglas de esta factura", que es mas barato de
-- mantener al reescribir decenas de miles de filas.
CREATE TABLE evaluacion (
    id           INTEGER PRIMARY KEY,
    ejecucion_id INTEGER NOT NULL REFERENCES ejecucion_reglas(id),
    regla        TEXT NOT NULL CHECK (length(regla) > 0),
    tabla        TEXT NOT NULL CHECK (length(tabla) > 0),
    fila_id      INTEGER NOT NULL,
    clave        TEXT NOT NULL CHECK (length(clave) > 0),
    resultado    TEXT NOT NULL CHECK (resultado IN ('ok', 'fallo', 'sin_datos', 'no_aplica')),
    detalle      TEXT NOT NULL,
    valores_json TEXT CHECK (valores_json IS NULL OR json_valid(valores_json))
) STRICT;

CREATE INDEX evaluacion_fila ON evaluacion (tabla, fila_id);

-- ----------------------------------------------------------------- hallazgo

CREATE TABLE hallazgo (
    id                  INTEGER PRIMARY KEY,
    clave               TEXT NOT NULL UNIQUE CHECK (length(clave) > 0),
    regla               TEXT NOT NULL CHECK (length(regla) > 0),
    regla_version       INTEGER NOT NULL CHECK (regla_version >= 1),
    huella              TEXT NOT NULL CHECK (length(huella) = 64),
    tabla               TEXT NOT NULL CHECK (length(tabla) > 0),
    fila_id             INTEGER NOT NULL,
    factura_id          INTEGER REFERENCES factura(id),
    severidad           TEXT NOT NULL CHECK (severidad IN ('bloqueo', 'retencion', 'aviso')),
    calidad             TEXT CHECK (calidad IS NULL OR calidad IN ('faltante', 'discrepancia', 'anomalia', 'dudoso', 'verificado')),
    ambito              TEXT NOT NULL CHECK (ambito IN ('factura', 'proveedor', 'cliente', 'orden_compra', 'trimestre', 'movimiento', 'importacion')),
    pegajosa            INTEGER NOT NULL CHECK (pegajosa IN (0, 1)),
    anulable            INTEGER NOT NULL CHECK (anulable IN (0, 1)),
    titulo              TEXT NOT NULL CHECK (length(titulo) > 0),
    detalle             TEXT NOT NULL,
    valores_json        TEXT NOT NULL CHECK (json_valid(valores_json)),
    estado              TEXT NOT NULL CHECK (estado IN ('abierto', 'aceptado', 'desaparecido', 'cerrado', 'resuelto')),
    primera_vez_en      TEXT NOT NULL CHECK (datetime(primera_vez_en) IS NOT NULL),
    ultima_vez_en       TEXT NOT NULL CHECK (datetime(ultima_vez_en) IS NOT NULL),
    ultima_ejecucion_id INTEGER NOT NULL REFERENCES ejecucion_reglas(id)
) STRICT;

CREATE INDEX hallazgo_factura ON hallazgo (factura_id);
CREATE INDEX hallazgo_estado ON hallazgo (estado);

-- Un hallazgo nace abierto; lo que le pase despues lo dice su historia.
CREATE TRIGGER hallazgo_nace_abierto BEFORE INSERT ON hallazgo
WHEN NEW.estado IS NOT 'abierto'
BEGIN SELECT RAISE(ABORT, 'un hallazgo nace abierto: lo demas lo dicen sus eventos'); END;

-- La identidad no cambia nunca, y el estado y la huella solo como diga el
-- ultimo evento del hallazgo.
CREATE TRIGGER hallazgo_guarda_update BEFORE UPDATE ON hallazgo
WHEN NEW.id IS NOT OLD.id OR NEW.clave IS NOT OLD.clave OR NEW.regla IS NOT OLD.regla
  OR NEW.primera_vez_en IS NOT OLD.primera_vez_en
  OR ((NEW.estado IS NOT OLD.estado OR NEW.huella IS NOT OLD.huella) AND NOT EXISTS (
        SELECT 1 FROM hallazgo_evento
        WHERE id = (SELECT max(id) FROM hallazgo_evento WHERE hallazgo_id = NEW.id)
          AND estado IS NEW.estado AND huella IS NEW.huella))
BEGIN SELECT RAISE(ABORT, 'el estado y la huella de un hallazgo los dice su ultimo evento'); END;

CREATE TRIGGER hallazgo_sin_delete BEFORE DELETE ON hallazgo
BEGIN SELECT RAISE(ABORT, 'un hallazgo no se borra: se cierra o se resuelve'); END;

-- A que filas se refiere hoy un hallazgo, y en cuales con un campo concreto
-- (la marca de un campo en la consola). Una regla de grupo cubre varias
-- facturas: la principal y las relacionadas.
CREATE TABLE hallazgo_objetivo (
    id          INTEGER PRIMARY KEY,
    hallazgo_id INTEGER NOT NULL REFERENCES hallazgo(id),
    tabla       TEXT NOT NULL CHECK (length(tabla) > 0),
    fila_id     INTEGER NOT NULL,
    campo       TEXT,
    papel       TEXT NOT NULL CHECK (papel IN ('principal', 'relacionado'))
) STRICT;

CREATE UNIQUE INDEX hallazgo_objetivo_unico ON hallazgo_objetivo
    (hallazgo_id, tabla, fila_id, coalesce(campo, ''));
CREATE INDEX hallazgo_objetivo_fila ON hallazgo_objetivo (tabla, fila_id);

-- ---------------------------------------------------------- hallazgo_evento

-- La historia de cada aviso. estado es el que queda despues del evento.
-- causa_evento_id es el evento de auditoria que lo causo: la edicion o la
-- importacion que hizo aparecer, cambiar o desaparecer la condicion, o la
-- orden de la persona que lo acepto o lo resolvio.
CREATE TABLE hallazgo_evento (
    id              INTEGER PRIMARY KEY,
    hallazgo_id     INTEGER NOT NULL REFERENCES hallazgo(id),
    tipo            TEXT NOT NULL CHECK (tipo IN ('detectado', 'cambio_evidencia', 'desaparecido', 'cerrado_automatico', 'resuelto', 'aceptado', 'reabierto')),
    estado          TEXT NOT NULL CHECK (estado IN ('abierto', 'aceptado', 'desaparecido', 'cerrado', 'resuelto')),
    huella          TEXT NOT NULL CHECK (length(huella) = 64),
    causa_evento_id INTEGER REFERENCES evento(id),
    ejecucion_id    INTEGER REFERENCES ejecucion_reglas(id),
    usuario_id      INTEGER REFERENCES usuario(id),
    en              TEXT NOT NULL CHECK (datetime(en) IS NOT NULL),
    nota            TEXT,
    CHECK ((tipo IN ('resuelto', 'aceptado')) = (usuario_id IS NOT NULL)),
    CHECK (tipo NOT IN ('resuelto', 'aceptado') OR causa_evento_id IS NOT NULL),
    CHECK (tipo IN ('resuelto', 'aceptado') OR ejecucion_id IS NOT NULL),
    CHECK (estado = CASE tipo
        WHEN 'detectado' THEN 'abierto'
        WHEN 'cambio_evidencia' THEN 'abierto'
        WHEN 'desaparecido' THEN 'desaparecido'
        WHEN 'cerrado_automatico' THEN 'cerrado'
        WHEN 'resuelto' THEN 'resuelto'
        WHEN 'aceptado' THEN 'aceptado'
        ELSE estado END),
    CHECK (tipo <> 'reabierto' OR estado IN ('abierto', 'aceptado'))
) STRICT;

CREATE INDEX hallazgo_evento_hallazgo ON hallazgo_evento (hallazgo_id, id);

-- Las transiciones posibles desde el estado del ultimo evento. Una regla
-- pegajosa no se cierra sola: su condicion desaparecida la deja
-- desaparecido, y solo una persona la resuelve.
CREATE TRIGGER hallazgo_evento_transicion BEFORE INSERT ON hallazgo_evento
WHEN NOT (
       (NEW.tipo = 'detectado' AND NOT EXISTS (
            SELECT 1 FROM hallazgo_evento WHERE hallazgo_id = NEW.hallazgo_id))
    OR (NEW.tipo = 'cambio_evidencia' AND (
            SELECT estado FROM hallazgo_evento WHERE hallazgo_id = NEW.hallazgo_id
            ORDER BY id DESC LIMIT 1) = 'abierto')
    OR (NEW.tipo = 'aceptado' AND (
            SELECT estado FROM hallazgo_evento WHERE hallazgo_id = NEW.hallazgo_id
            ORDER BY id DESC LIMIT 1) IN ('abierto', 'aceptado'))
    OR (NEW.tipo = 'desaparecido'
        AND (SELECT pegajosa FROM hallazgo WHERE id = NEW.hallazgo_id) = 1
        AND (SELECT estado FROM hallazgo_evento WHERE hallazgo_id = NEW.hallazgo_id
             ORDER BY id DESC LIMIT 1) IN ('abierto', 'aceptado'))
    OR (NEW.tipo = 'cerrado_automatico'
        AND (SELECT pegajosa FROM hallazgo WHERE id = NEW.hallazgo_id) = 0
        AND (SELECT estado FROM hallazgo_evento WHERE hallazgo_id = NEW.hallazgo_id
             ORDER BY id DESC LIMIT 1) IN ('abierto', 'aceptado'))
    OR (NEW.tipo = 'resuelto' AND (
            SELECT estado FROM hallazgo_evento WHERE hallazgo_id = NEW.hallazgo_id
            ORDER BY id DESC LIMIT 1) = 'desaparecido')
    OR (NEW.tipo = 'reabierto' AND (
            SELECT estado FROM hallazgo_evento WHERE hallazgo_id = NEW.hallazgo_id
            ORDER BY id DESC LIMIT 1) IN ('aceptado', 'desaparecido', 'cerrado', 'resuelto')))
BEGIN SELECT RAISE(ABORT, 'transicion de hallazgo no permitida desde su estado (una regla pegajosa no se cierra sola)'); END;

-- Lo que hace una persona lo hace una persona, y con su orden: resolver es
-- un evento suyo, y aceptar es una anulacion suya con la misma huella.
CREATE TRIGGER hallazgo_evento_de_persona BEFORE INSERT ON hallazgo_evento
WHEN NEW.usuario_id IS NOT NULL AND (
       (SELECT es_sistema FROM usuario WHERE id = NEW.usuario_id) IS NOT 0
    OR (NEW.tipo = 'resuelto'
        AND (SELECT usuario_id FROM evento WHERE id = NEW.causa_evento_id) IS NOT NEW.usuario_id)
    OR (NEW.tipo = 'aceptado' AND NOT EXISTS (
            SELECT 1 FROM anulacion
            WHERE hallazgo_id = NEW.hallazgo_id AND huella = NEW.huella
              AND evento_id = NEW.causa_evento_id AND usuario_id = NEW.usuario_id)))
BEGIN SELECT RAISE(ABORT, 'resolver o aceptar un hallazgo es de una persona, con su orden y su anulacion'); END;

CREATE TRIGGER hallazgo_evento_sin_update BEFORE UPDATE ON hallazgo_evento
BEGIN SELECT RAISE(ABORT, 'hallazgo_evento es de solo escritura: no se modifica'); END;
CREATE TRIGGER hallazgo_evento_sin_delete BEFORE DELETE ON hallazgo_evento
BEGIN SELECT RAISE(ABORT, 'hallazgo_evento es de solo escritura: no se borra'); END;

-- ---------------------------------------------------------------- anulacion

-- Una persona con anular_aviso acepta la evidencia que ve (huella), con un
-- motivo de al menos 10 caracteres y, si se quiere, hasta una fecha. Vale
-- mientras la huella del hallazgo sea esa y no haya vencido. Va con el
-- evento de auditoria de su orden (evento_id), que lleva su foto.
CREATE TABLE anulacion (
    id                       INTEGER PRIMARY KEY,
    hallazgo_id              INTEGER NOT NULL REFERENCES hallazgo(id),
    huella                   TEXT NOT NULL CHECK (length(huella) = 64),
    motivo                   TEXT NOT NULL CHECK (length(trim(motivo)) >= 10),
    usuario_id               INTEGER NOT NULL REFERENCES usuario(id),
    en                       TEXT NOT NULL CHECK (datetime(en) IS NOT NULL),
    vigente_hasta            TEXT CHECK (vigente_hasta IS NULL OR date(vigente_hasta) IS vigente_hasta),
    segunda_firma_usuario_id INTEGER REFERENCES usuario(id),
    segunda_firma_en         TEXT CHECK (segunda_firma_en IS NULL OR datetime(segunda_firma_en) IS NOT NULL),
    autoaprobada             INTEGER NOT NULL DEFAULT 0 CHECK (autoaprobada IN (0, 1)),
    evento_id                INTEGER NOT NULL UNIQUE REFERENCES evento(id),
    CHECK ((segunda_firma_usuario_id IS NULL) = (segunda_firma_en IS NULL)),
    CHECK (segunda_firma_usuario_id IS NULL OR segunda_firma_usuario_id <> usuario_id),
    CHECK (autoaprobada = 0 OR segunda_firma_usuario_id IS NULL)
) STRICT;

CREATE INDEX anulacion_hallazgo ON anulacion (hallazgo_id);

-- Las reglas que no se anulan nunca (spec §3, decision 12), aunque alguien
-- cambie la marca anulable de un hallazgo: toda la familia F, X1, E3, E4,
-- K2, K4, K6, R2, R3, y D2, D3, D4 y D6 en las facturas entrantes. Ademas,
-- cualquier hallazgo cuyo catalogo dice que no se anula.
CREATE TRIGGER anulacion_solo_anulables BEFORE INSERT ON anulacion
WHEN (SELECT anulable FROM hallazgo WHERE id = NEW.hallazgo_id) IS NOT 1
  OR (SELECT regla FROM hallazgo WHERE id = NEW.hallazgo_id) GLOB 'F[0-9]*'
  OR (SELECT regla FROM hallazgo WHERE id = NEW.hallazgo_id)
        IN ('X1', 'E3', 'E4', 'K2', 'K4', 'K6', 'R2', 'R3')
  OR ((SELECT regla FROM hallazgo WHERE id = NEW.hallazgo_id) IN ('D2', 'D3', 'D4', 'D6')
      AND (SELECT f.sentido FROM hallazgo AS h JOIN factura AS f ON f.id = h.factura_id
           WHERE h.id = NEW.hallazgo_id) IS NOT 'saliente')
BEGIN SELECT RAISE(ABORT, 'este hallazgo es de una regla que no se puede anular'); END;

-- Se anula lo que se ve: la huella de ahora de un hallazgo abierto o ya
-- aceptado (para cambiar el plazo), no uno cerrado ni desaparecido.
CREATE TRIGGER anulacion_huella_actual BEFORE INSERT ON anulacion
WHEN NEW.huella IS NOT (SELECT huella FROM hallazgo WHERE id = NEW.hallazgo_id)
  OR (SELECT estado FROM hallazgo WHERE id = NEW.hallazgo_id) NOT IN ('abierto', 'aceptado')
BEGIN SELECT RAISE(ABORT, 'solo se anula la evidencia actual de un hallazgo abierto'); END;

-- Firma una persona activa con anular_aviso en ese momento (y lo mismo la
-- segunda firma), dentro de su propia orden: el evento es el ultimo y es suyo.
CREATE TRIGGER anulacion_de_persona BEFORE INSERT ON anulacion
WHEN NOT EXISTS (
        SELECT 1 FROM usuario AS u
        JOIN usuario_rol AS ur ON ur.usuario_id = u.id
        JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id
        WHERE u.id = NEW.usuario_id AND u.es_sistema = 0 AND u.activo = 1
          AND rp.permiso = 'anular_aviso'
          AND ur.desde <= NEW.en AND (ur.hasta IS NULL OR ur.hasta > NEW.en))
  OR (NEW.segunda_firma_usuario_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM usuario AS u
        JOIN usuario_rol AS ur ON ur.usuario_id = u.id
        JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id
        WHERE u.id = NEW.segunda_firma_usuario_id AND u.es_sistema = 0 AND u.activo = 1
          AND rp.permiso = 'anular_aviso'
          AND ur.desde <= NEW.segunda_firma_en
          AND (ur.hasta IS NULL OR ur.hasta > NEW.segunda_firma_en)))
  OR NEW.evento_id IS NOT (SELECT max(id) FROM evento)
  OR (SELECT usuario_id FROM evento WHERE id = NEW.evento_id) IS NOT NEW.usuario_id
BEGIN SELECT RAISE(ABORT, 'una anulacion la firma una persona con anular_aviso, en su propia orden'); END;

CREATE TRIGGER anulacion_sin_update BEFORE UPDATE ON anulacion
BEGIN SELECT RAISE(ABORT, 'anulacion es de solo escritura: no se modifica'); END;
CREATE TRIGGER anulacion_sin_delete BEFORE DELETE ON anulacion
BEGIN SELECT RAISE(ABORT, 'anulacion es de solo escritura: no se borra'); END;
