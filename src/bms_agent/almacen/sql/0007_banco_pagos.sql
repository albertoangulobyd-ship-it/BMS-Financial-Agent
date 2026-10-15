-- Migracion 0007 (paso 7 de la V1): los extractos del banco, sus movimientos
-- y lo que se ha pagado de cada factura.
--
-- Un fichero aplicado no se edita nunca (ver 0001). Lo que haga falta
-- despues va en 0008, 0009...
--
-- Lo que esta migracion garantiza (spec §3.5, §5.B, §5.E y §9):
--   - Un extracto y sus movimientos son evidencia: entran con su importacion
--     del banco en curso, todos o ninguno, y no se tocan despues. Su evento
--     (extracto_registrado) lleva la foto del extracto y de cada movimiento,
--     y `db verificar` compara las filas con ella.
--   - Un movimiento repetido no entra dos veces: su huella (UNIQUE) cubre lo
--     que dice el banco y la posicion entre filas identicas del fichero.
--   - Lo que se paga de una factura es una aplicacion (aplicacion_pago), con
--     su importe de verdad: un pago parcial deja la factura con su saldo.
--     Ninguna tabla guarda plazos ni un estado "aprobado para pagar": aqui se
--     apunta lo que ya se pago, nunca lo que se va a pagar.
--   - Una aplicacion automatica (o propuesta) la escribe el sistema: el motor
--     al casar un movimiento, el importador con lo que dice Exact. Una manual
--     (marcar pagada, enlazar un movimiento) la escribe una persona con
--     marcar_pagada, con su motivo; confirmar una propuesta tambien.
--
-- Clases de tabla (spec.md §4):
--   extracto_bancario, movimiento_bancario: EVIDENCIA (sin UPDATE ni DELETE).
--   aplicacion_pago: CONTROLADA (rev y la guarda generada con
--     scripts/generar_guardas.py), escrita por campos.py.
--
-- El extracto es de una cuenta de BM Support BV (config/empresa.yaml): lo
-- comprueba el importador, que rechaza el fichero entero si no.

-- ---------------------------------------------------------- extracto_bancario

-- Un extracto de una cuenta propia, como lo da el fichero. con_saldos = 0 en
-- los CSV del banco (no traen saldos fiables): con ellos no se evalua la
-- continuidad (K6). entradas son las que traia el fichero para este
-- extracto, tambien las que no entraron por repetidas.
CREATE TABLE extracto_bancario (
    id                  INTEGER PRIMARY KEY,
    importacion_id      INTEGER NOT NULL REFERENCES importacion(id),
    cuenta_propia_iban  TEXT NOT NULL CHECK (length(cuenta_propia_iban) BETWEEN 15 AND 34
                                             AND cuenta_propia_iban NOT GLOB '*[^A-Z0-9]*'
                                             AND cuenta_propia_iban GLOB '[A-Z][A-Z][0-9][0-9]*'),
    identificador       TEXT,
    secuencia           INTEGER CHECK (secuencia IS NULL OR secuencia >= 0),
    moneda              TEXT NOT NULL CHECK (length(moneda) = 3),
    saldo_inicial_cent  INTEGER,
    saldo_final_cent    INTEGER,
    fecha_saldo_inicial TEXT CHECK (fecha_saldo_inicial IS NULL
                                    OR date(fecha_saldo_inicial) IS fecha_saldo_inicial),
    fecha_saldo_final   TEXT CHECK (fecha_saldo_final IS NULL
                                    OR date(fecha_saldo_final) IS fecha_saldo_final),
    desde               TEXT CHECK (desde IS NULL OR date(desde) IS desde),
    hasta               TEXT CHECK (hasta IS NULL OR date(hasta) IS hasta),
    con_saldos          INTEGER NOT NULL CHECK (con_saldos IN (0, 1)),
    entradas            INTEGER NOT NULL CHECK (entradas >= 0),
    formato             TEXT NOT NULL CHECK (length(formato) > 0),
    CHECK (con_saldos = 0 OR (saldo_inicial_cent IS NOT NULL AND saldo_final_cent IS NOT NULL)),
    CHECK (desde IS NULL OR hasta IS NULL OR desde <= hasta)
) STRICT;

CREATE INDEX extracto_bancario_cuenta ON extracto_bancario (cuenta_propia_iban, desde);

-- Lo da de alta el importador, con la importacion del banco en curso.
CREATE TRIGGER extracto_bancario_alta BEFORE INSERT ON extracto_bancario
WHEN (SELECT estado FROM importacion WHERE id = NEW.importacion_id) IS NOT 'en_curso'
  OR (SELECT fuente FROM importacion WHERE id = NEW.importacion_id) IS NOT 'banco'
  OR (SELECT tipo FROM importacion WHERE id = NEW.importacion_id) IS NOT 'extracto'
  OR (SELECT actor FROM importacion WHERE id = NEW.importacion_id)
         IS NOT (SELECT id FROM usuario WHERE nombre = 'importador' AND es_sistema = 1)
BEGIN SELECT RAISE(ABORT, 'un extracto lo da de alta el importador del banco, con su importacion en curso'); END;

CREATE TRIGGER extracto_bancario_sin_update BEFORE UPDATE ON extracto_bancario
BEGIN SELECT RAISE(ABORT, 'extracto_bancario es evidencia: no se modifica'); END;
CREATE TRIGGER extracto_bancario_sin_delete BEFORE DELETE ON extracto_bancario
BEGIN SELECT RAISE(ABORT, 'extracto_bancario es evidencia: no se borra'); END;

-- -------------------------------------------------------- movimiento_bancario

-- Un apunte del banco. Cada transaccion de un apunte agrupado es un
-- movimiento (remesa dice de que apunte viene). importe_cent con signo: un
-- cargo es negativo. Lo que no esta en euros guarda su literal y su moneda,
-- con el importe vacio (X1): no entra en ninguna suma. Los *_doc y la cuenta
-- de la contraparte son lo que dice el banco: se usan para casar y para
-- comparar con el registro de cuentas (F7), nunca para registrar una cuenta.
CREATE TABLE movimiento_bancario (
    id                      INTEGER PRIMARY KEY,
    importacion_id          INTEGER NOT NULL REFERENCES importacion(id),
    extracto_id             INTEGER NOT NULL REFERENCES extracto_bancario(id),
    cuenta_propia_iban      TEXT NOT NULL,
    posicion                INTEGER NOT NULL CHECK (posicion >= 1),
    fecha_contable          TEXT NOT NULL CHECK (date(fecha_contable) IS fecha_contable),
    fecha_valor             TEXT CHECK (fecha_valor IS NULL OR date(fecha_valor) IS fecha_valor),
    importe_cent            INTEGER,
    importe_crudo           TEXT NOT NULL CHECK (length(importe_crudo) > 0),
    moneda                  TEXT NOT NULL CHECK (length(moneda) = 3),
    contraparte_iban        TEXT,
    contraparte_nombre_doc  TEXT,
    concepto_doc            TEXT,
    referencia_estructurada TEXT,
    referencia_e2e          TEXT,
    ref_banco               TEXT,
    remesa                  TEXT,
    huella                  TEXT NOT NULL UNIQUE CHECK (length(huella) = 64),
    CHECK ((moneda = 'EUR') = (importe_cent IS NOT NULL))
) STRICT;

CREATE INDEX movimiento_bancario_extracto ON movimiento_bancario (extracto_id);
CREATE INDEX movimiento_bancario_fecha ON movimiento_bancario (fecha_contable);

-- Entra con su extracto: de la misma importacion, en curso, y de la misma cuenta.
CREATE TRIGGER movimiento_bancario_alta BEFORE INSERT ON movimiento_bancario
WHEN (SELECT importacion_id FROM extracto_bancario WHERE id = NEW.extracto_id)
         IS NOT NEW.importacion_id
  OR (SELECT cuenta_propia_iban FROM extracto_bancario WHERE id = NEW.extracto_id)
         IS NOT NEW.cuenta_propia_iban
  OR (SELECT estado FROM importacion WHERE id = NEW.importacion_id) IS NOT 'en_curso'
BEGIN SELECT RAISE(ABORT, 'un movimiento entra con su extracto, en la importacion en curso'); END;

CREATE TRIGGER movimiento_bancario_sin_update BEFORE UPDATE ON movimiento_bancario
BEGIN SELECT RAISE(ABORT, 'movimiento_bancario es evidencia: no se modifica'); END;
CREATE TRIGGER movimiento_bancario_sin_delete BEFORE DELETE ON movimiento_bancario
BEGIN SELECT RAISE(ABORT, 'movimiento_bancario es evidencia: no se borra'); END;

-- ------------------------------------------------------------ aplicacion_pago

-- Lo que se ha pagado de una factura, con su importe en el signo de la
-- factura (lo que baja su saldo). fuente: banco (un movimiento), exact (lo
-- que dice Exact en una importacion) o manual (una persona, sin movimiento).
-- metodo: automatica (el motor casa referencia, importe y contraparte; o
-- Exact), propuesta (el motor casa a medias y una persona confirma) o manual
-- (una persona). estado lo calcula campos.py: retirada si se retiro,
-- confirmada si es automatica o manual o una persona confirmo la propuesta,
-- propuesta si no. Solo lo confirmado cuenta para el saldo, y de cada factura
-- manda el banco sobre Exact y Exact sobre lo manual.
CREATE TABLE aplicacion_pago (
    id                     INTEGER PRIMARY KEY,
    factura_id             INTEGER NOT NULL REFERENCES factura(id),
    movimiento_id          INTEGER REFERENCES movimiento_bancario(id),
    importacion_id         INTEGER REFERENCES importacion(id),
    importe_cent           INTEGER NOT NULL CHECK (importe_cent <> 0),
    fecha_pago             TEXT NOT NULL CHECK (date(fecha_pago) IS fecha_pago),
    fuente                 TEXT NOT NULL CHECK (fuente IN ('banco', 'exact', 'manual')),
    metodo                 TEXT NOT NULL CHECK (metodo IN ('automatica', 'propuesta', 'manual')),
    estado                 TEXT NOT NULL CHECK (estado IN ('propuesta', 'confirmada', 'retirada')),
    regla                  TEXT,
    motivo                 TEXT,
    evidencia_documento_id INTEGER REFERENCES documento(id),
    confirmada_por         INTEGER REFERENCES usuario(id),
    confirmada_en          TEXT CHECK (confirmada_en IS NULL OR datetime(confirmada_en) IS NOT NULL),
    retirada_en            TEXT CHECK (retirada_en IS NULL OR datetime(retirada_en) IS NOT NULL),
    rev                    INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0),
    CHECK ((fuente = 'banco') = (movimiento_id IS NOT NULL)),
    CHECK ((fuente = 'exact') = (importacion_id IS NOT NULL)),
    CHECK (fuente <> 'manual' OR metodo = 'manual'),
    CHECK (fuente <> 'exact' OR metodo = 'automatica'),
    CHECK (metodo <> 'manual' OR (confirmada_por IS NOT NULL
                                  AND length(trim(coalesce(motivo, ''))) > 0)),
    CHECK ((confirmada_por IS NULL) = (confirmada_en IS NULL)),
    CHECK ((estado = 'retirada') = (retirada_en IS NOT NULL)),
    CHECK (estado <> 'propuesta' OR (metodo = 'propuesta' AND confirmada_por IS NULL)),
    CHECK (estado <> 'confirmada' OR metodo <> 'propuesta' OR confirmada_por IS NOT NULL)
) STRICT;

CREATE INDEX aplicacion_pago_factura ON aplicacion_pago (factura_id);
CREATE INDEX aplicacion_pago_movimiento ON aplicacion_pago (movimiento_id);

-- Quien escribe una aplicacion. Una automatica o propuesta, el sistema: el
-- motor (al casar un movimiento) o el importador (lo que dice Exact). Una
-- manual, una persona con marcar_pagada en ese momento, en su propia orden, y
-- es ella quien la confirma.
CREATE TRIGGER aplicacion_pago_alta BEFORE INSERT ON aplicacion_pago
WHEN (NEW.metodo IN ('automatica', 'propuesta') AND (SELECT actor FROM evento WHERE id = (SELECT max(id) FROM evento))
          NOT IN (SELECT id FROM usuario WHERE es_sistema = 1 AND nombre IN ('motor', 'importador')))
  OR (NEW.metodo = 'manual' AND (
        (SELECT usuario_id FROM evento WHERE id = (SELECT max(id) FROM evento)) IS NOT NEW.confirmada_por
     OR (SELECT actor FROM evento WHERE id = (SELECT max(id) FROM evento)) IS NOT NEW.confirmada_por))
BEGIN SELECT RAISE(ABORT, 'una aplicacion automatica la escribe el sistema; una manual, la persona que la confirma, en su orden'); END;

-- Confirmar es de una persona activa con marcar_pagada en ese instante, en su
-- propia orden, y solo una propuesta sin confirmar ni retirar.
CREATE TRIGGER aplicacion_pago_confirmar BEFORE UPDATE ON aplicacion_pago
WHEN NEW.confirmada_por IS NOT OLD.confirmada_por AND (
        OLD.confirmada_por IS NOT NULL
     OR OLD.metodo IS NOT 'propuesta'
     OR OLD.retirada_en IS NOT NULL
     OR (SELECT usuario_id FROM evento WHERE id = (SELECT max(id) FROM evento)) IS NOT NEW.confirmada_por)
BEGIN SELECT RAISE(ABORT, 'confirmar un pago es de la persona que lo confirma, sobre una propuesta sin confirmar'); END;

CREATE TRIGGER aplicacion_pago_confirmada_por_persona BEFORE INSERT ON aplicacion_pago
WHEN NEW.confirmada_por IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM usuario AS u
        JOIN usuario_rol AS ur ON ur.usuario_id = u.id
        JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id
        WHERE u.id = NEW.confirmada_por AND u.es_sistema = 0 AND u.activo = 1
          AND rp.permiso = 'marcar_pagada'
          AND ur.desde <= NEW.confirmada_en AND (ur.hasta IS NULL OR ur.hasta > NEW.confirmada_en))
BEGIN SELECT RAISE(ABORT, 'un pago lo confirma una persona con marcar_pagada'); END;

CREATE TRIGGER aplicacion_pago_confirmada_por_persona_update BEFORE UPDATE ON aplicacion_pago
WHEN NEW.confirmada_por IS NOT OLD.confirmada_por AND NEW.confirmada_por IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM usuario AS u
        JOIN usuario_rol AS ur ON ur.usuario_id = u.id
        JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id
        WHERE u.id = NEW.confirmada_por AND u.es_sistema = 0 AND u.activo = 1
          AND rp.permiso = 'marcar_pagada'
          AND ur.desde <= NEW.confirmada_en AND (ur.hasta IS NULL OR ur.hasta > NEW.confirmada_en))
BEGIN SELECT RAISE(ABORT, 'un pago lo confirma una persona con marcar_pagada'); END;

-- Lo que no cambia de una aplicacion despues de escribirla: a que factura y
-- movimiento va, cuanto, de cuando, de donde y como se encontro. Se retira y
-- se escribe otra.
CREATE TRIGGER aplicacion_pago_fija BEFORE UPDATE ON aplicacion_pago
WHEN NEW.factura_id IS NOT OLD.factura_id OR NEW.movimiento_id IS NOT OLD.movimiento_id
  OR NEW.importacion_id IS NOT OLD.importacion_id OR NEW.importe_cent IS NOT OLD.importe_cent
  OR NEW.fecha_pago IS NOT OLD.fecha_pago OR NEW.fuente IS NOT OLD.fuente
  OR NEW.metodo IS NOT OLD.metodo OR (OLD.retirada_en IS NOT NULL AND NEW.retirada_en IS NOT OLD.retirada_en)
BEGIN SELECT RAISE(ABORT, 'una aplicacion de pago no cambia de factura, movimiento, importe, fecha ni origen: se retira y se escribe otra'); END;

-- --------------------------------------------------------------- v_factura_saldo

-- El saldo de cada factura, sin depender de hoy: lo confirmado de cada
-- fuente y lo que vale (banco, si hay; si no, Exact; si no, lo manual), lo
-- que queda (total menos lo pagado) y las propuestas sin confirmar. Si una
-- factura esta pagada lo decide el codigo con la tolerancia de la politica
-- (reglas.pagos.saldo, por defecto 0,00); lo que se ha acreditado con otra
-- factura llega con las relaciones (paso 8).
CREATE VIEW v_factura_saldo AS
WITH sumas AS (
    SELECT f.id AS factura_id, f.sentido, f.total_cent, f.anulada, f.fusionada_en_id,
           coalesce(sum(CASE WHEN a.estado = 'confirmada' AND a.fuente = 'banco'
                             THEN a.importe_cent END), 0) AS pagado_banco_cent,
           count(CASE WHEN a.estado = 'confirmada' AND a.fuente = 'banco' THEN 1 END) AS pagos_banco,
           coalesce(sum(CASE WHEN a.estado = 'confirmada' AND a.fuente = 'exact'
                             THEN a.importe_cent END), 0) AS pagado_exact_cent,
           count(CASE WHEN a.estado = 'confirmada' AND a.fuente = 'exact' THEN 1 END) AS pagos_exact,
           coalesce(sum(CASE WHEN a.estado = 'confirmada' AND a.fuente = 'manual'
                             THEN a.importe_cent END), 0) AS pagado_manual_cent,
           count(CASE WHEN a.estado = 'confirmada' AND a.fuente = 'manual' THEN 1 END) AS pagos_manual,
           count(CASE WHEN a.estado = 'propuesta' THEN 1 END) AS propuestas
    FROM factura AS f LEFT JOIN aplicacion_pago AS a ON a.factura_id = f.id
    GROUP BY f.id
)
SELECT factura_id, sentido, total_cent, anulada, fusionada_en_id,
       pagado_banco_cent, pagos_banco, pagado_exact_cent, pagos_exact,
       pagado_manual_cent, pagos_manual, propuestas,
       CASE WHEN pagos_banco > 0 THEN 'banco' WHEN pagos_exact > 0 THEN 'exact'
            WHEN pagos_manual > 0 THEN 'manual' END AS fuente_pago,
       CASE WHEN pagos_banco > 0 THEN pagado_banco_cent WHEN pagos_exact > 0 THEN pagado_exact_cent
            ELSE pagado_manual_cent END AS pagado_cent,
       total_cent - CASE WHEN pagos_banco > 0 THEN pagado_banco_cent
                         WHEN pagos_exact > 0 THEN pagado_exact_cent
                         ELSE pagado_manual_cent END AS pendiente_cent
FROM sumas;

-- -------------------------------------------------- guardas (generadas)

CREATE TRIGGER aplicacion_pago_guarda_insert BEFORE INSERT ON aplicacion_pago
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.factura_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = 0
        AND campo = 'factura_id' AND json_extract(valor_nuevo, '$') IS NEW.factura_id))
    OR (NEW.movimiento_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = 0
        AND campo = 'movimiento_id' AND json_extract(valor_nuevo, '$') IS NEW.movimiento_id))
    OR (NEW.importacion_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = 0
        AND campo = 'importacion_id' AND json_extract(valor_nuevo, '$') IS NEW.importacion_id))
    OR (NEW.importe_cent IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = 0
        AND campo = 'importe_cent' AND json_extract(valor_nuevo, '$') IS NEW.importe_cent))
    OR (NEW.fecha_pago IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fecha_pago' AND json_extract(valor_nuevo, '$') IS NEW.fecha_pago))
    OR (NEW.fuente IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fuente' AND json_extract(valor_nuevo, '$') IS NEW.fuente))
    OR (NEW.metodo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = 0
        AND campo = 'metodo' AND json_extract(valor_nuevo, '$') IS NEW.metodo))
    OR (NEW.estado IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = 0
        AND campo = 'estado' AND json_extract(valor_nuevo, '$') IS NEW.estado))
    OR (NEW.regla IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = 0
        AND campo = 'regla' AND json_extract(valor_nuevo, '$') IS NEW.regla))
    OR (NEW.motivo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = 0
        AND campo = 'motivo' AND json_extract(valor_nuevo, '$') IS NEW.motivo))
    OR (NEW.evidencia_documento_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = 0
        AND campo = 'evidencia_documento_id' AND json_extract(valor_nuevo, '$') IS NEW.evidencia_documento_id))
    OR (NEW.confirmada_por IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = 0
        AND campo = 'confirmada_por' AND json_extract(valor_nuevo, '$') IS NEW.confirmada_por))
    OR (NEW.confirmada_en IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = 0
        AND campo = 'confirmada_en' AND json_extract(valor_nuevo, '$') IS NEW.confirmada_en))
    OR (NEW.retirada_en IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = 0
        AND campo = 'retirada_en' AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'aplicacion_pago es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER aplicacion_pago_guarda_update BEFORE UPDATE ON aplicacion_pago
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.factura_id IS NOT OLD.factura_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'factura_id' AND json_extract(valor_anterior, '$') IS OLD.factura_id
        AND json_extract(valor_nuevo, '$') IS NEW.factura_id))
    OR (NEW.movimiento_id IS NOT OLD.movimiento_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'movimiento_id' AND json_extract(valor_anterior, '$') IS OLD.movimiento_id
        AND json_extract(valor_nuevo, '$') IS NEW.movimiento_id))
    OR (NEW.importacion_id IS NOT OLD.importacion_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'importacion_id' AND json_extract(valor_anterior, '$') IS OLD.importacion_id
        AND json_extract(valor_nuevo, '$') IS NEW.importacion_id))
    OR (NEW.importe_cent IS NOT OLD.importe_cent AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'importe_cent' AND json_extract(valor_anterior, '$') IS OLD.importe_cent
        AND json_extract(valor_nuevo, '$') IS NEW.importe_cent))
    OR (NEW.fecha_pago IS NOT OLD.fecha_pago AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fecha_pago' AND json_extract(valor_anterior, '$') IS OLD.fecha_pago
        AND json_extract(valor_nuevo, '$') IS NEW.fecha_pago))
    OR (NEW.fuente IS NOT OLD.fuente AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fuente' AND json_extract(valor_anterior, '$') IS OLD.fuente
        AND json_extract(valor_nuevo, '$') IS NEW.fuente))
    OR (NEW.metodo IS NOT OLD.metodo AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'metodo' AND json_extract(valor_anterior, '$') IS OLD.metodo
        AND json_extract(valor_nuevo, '$') IS NEW.metodo))
    OR (NEW.estado IS NOT OLD.estado AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'estado' AND json_extract(valor_anterior, '$') IS OLD.estado
        AND json_extract(valor_nuevo, '$') IS NEW.estado))
    OR (NEW.regla IS NOT OLD.regla AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'regla' AND json_extract(valor_anterior, '$') IS OLD.regla
        AND json_extract(valor_nuevo, '$') IS NEW.regla))
    OR (NEW.motivo IS NOT OLD.motivo AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'motivo' AND json_extract(valor_anterior, '$') IS OLD.motivo
        AND json_extract(valor_nuevo, '$') IS NEW.motivo))
    OR (NEW.evidencia_documento_id IS NOT OLD.evidencia_documento_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'evidencia_documento_id' AND json_extract(valor_anterior, '$') IS OLD.evidencia_documento_id
        AND json_extract(valor_nuevo, '$') IS NEW.evidencia_documento_id))
    OR (NEW.confirmada_por IS NOT OLD.confirmada_por AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'confirmada_por' AND json_extract(valor_anterior, '$') IS OLD.confirmada_por
        AND json_extract(valor_nuevo, '$') IS NEW.confirmada_por))
    OR (NEW.confirmada_en IS NOT OLD.confirmada_en AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'confirmada_en' AND json_extract(valor_anterior, '$') IS OLD.confirmada_en
        AND json_extract(valor_nuevo, '$') IS NEW.confirmada_en))
    OR (NEW.retirada_en IS NOT OLD.retirada_en AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'aplicacion_pago' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'retirada_en' AND json_extract(valor_anterior, '$') IS OLD.retirada_en
        AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'aplicacion_pago es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER aplicacion_pago_sin_delete BEFORE DELETE ON aplicacion_pago
BEGIN SELECT RAISE(ABORT, 'aplicacion_pago no se borra: una fila se retira o se desactiva'); END;

