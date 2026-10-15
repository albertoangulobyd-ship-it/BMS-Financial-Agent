-- Migracion 0005 (paso 5 de la V1): el registro de cuentas bancarias, los
-- beneficiarios que no son proveedores y los ciclos de facturacion.
--
-- Un fichero aplicado no se edita nunca (ver 0001). Lo que haga falta
-- despues va en 0006, 0007... La tarifa pactada (tabla 22 del §5.C) ya llego
-- en la 0002, porque el paso 2 sembraba las tarifas de venta.
--
-- Clases de tabla (spec.md §4):
--   cuenta_bancaria: SOLO ALTA. Una fila por titular e IBAN; no se modifica
--     ni se borra. Su estado no esta en la fila: lo dicen sus eventos.
--   cuenta_evento: SOLO ESCRITURA. Lo que le pasa a una cuenta: el maestro la
--     trae o deja de traerla, una persona la verifica, la rechaza o la atesta.
--   beneficiario_conocido, ciclo_facturacion: CONTROLADAS, como los maestros
--     de la 0002 (rev y la guarda generada con scripts/generar_guardas.py).
--
-- Ningun camino lleva de una extraccion a estas dos tablas: lo que imprime un
-- documento se queda en factura.iban_doc y las reglas lo leen de alli. Solo
-- dan de alta una cuenta el importador de maestros (con su importacion en
-- curso) y una persona con confirmar_iban que la verifica por telefono; solo
-- una persona con confirmar_iban la verifica, la rechaza o la atesta.

-- ---------------------------------------------------------- cuenta_bancaria

-- primera_fuente dice como entro: con el primer maestro (baseline, el punto
-- de partida que se acepta como referencia), con un maestro posterior
-- (maestro_exact, maestro_trnsprnt) o tecleada por una persona que acaba de
-- llamar al numero del maestro (verificacion_manual). evento_id es el evento
-- de la orden que la dio de alta, y lleva su foto.
CREATE TABLE cuenta_bancaria (
    id             INTEGER PRIMARY KEY,
    titular        TEXT NOT NULL CHECK (titular IN ('proveedor', 'cliente', 'propia')),
    proveedor_id   INTEGER REFERENCES proveedor(id),
    cliente_id     INTEGER REFERENCES cliente(id),
    iban           TEXT NOT NULL CHECK (length(iban) BETWEEN 15 AND 34
                                        AND iban NOT GLOB '*[^A-Z0-9]*'
                                        AND iban GLOB '[A-Z][A-Z][0-9][0-9]*'),
    nombre_titular TEXT,
    primera_vez_en TEXT NOT NULL CHECK (datetime(primera_vez_en) IS NOT NULL),
    primera_fuente TEXT NOT NULL CHECK (primera_fuente IN ('baseline', 'maestro_exact', 'maestro_trnsprnt', 'verificacion_manual')),
    importacion_id INTEGER REFERENCES importacion(id),
    evento_id      INTEGER NOT NULL REFERENCES evento(id),
    CHECK ((titular = 'proveedor') = (proveedor_id IS NOT NULL)),
    CHECK ((titular = 'cliente') = (cliente_id IS NOT NULL)),
    CHECK ((primera_fuente = 'verificacion_manual') = (importacion_id IS NULL))
) STRICT;

-- Una cuenta por titular e IBAN. Con una expresion porque en un UNIQUE de
-- SQLite dos NULL son distintos, y cliente_id es NULL en las de proveedor.
CREATE UNIQUE INDEX cuenta_bancaria_unica ON cuenta_bancaria
    (titular, coalesce(proveedor_id, 0), coalesce(cliente_id, 0), iban);
CREATE INDEX cuenta_bancaria_iban ON cuenta_bancaria (iban);

-- Quien da de alta una cuenta. Del maestro: el usuario de sistema importador,
-- con la importacion de ese maestro en curso y en su evento. A mano: una
-- persona activa con confirmar_iban, en su propia orden. Nadie mas: ni el
-- extractor, ni el motor, ni una persona sin el permiso.
CREATE TRIGGER cuenta_bancaria_alta BEFORE INSERT ON cuenta_bancaria
WHEN NEW.evento_id IS NOT (SELECT max(id) FROM evento)
  OR (NEW.primera_fuente <> 'verificacion_manual' AND (
        (SELECT actor FROM evento WHERE id = NEW.evento_id)
            IS NOT (SELECT id FROM usuario WHERE nombre = 'importador' AND es_sistema = 1)
     OR (SELECT estado FROM importacion WHERE id = NEW.importacion_id) IS NOT 'en_curso'
     OR (SELECT fuente FROM importacion WHERE id = NEW.importacion_id)
            IS NOT (CASE NEW.primera_fuente WHEN 'maestro_trnsprnt' THEN 'trnsprnt' ELSE 'exact' END)))
  OR (NEW.primera_fuente = 'verificacion_manual' AND (
        (SELECT usuario_id FROM evento WHERE id = NEW.evento_id)
            IS NOT (SELECT actor FROM evento WHERE id = NEW.evento_id)
     OR NOT EXISTS (
            SELECT 1 FROM usuario AS u
            JOIN usuario_rol AS ur ON ur.usuario_id = u.id
            JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id
            WHERE u.id = (SELECT usuario_id FROM evento WHERE id = NEW.evento_id)
              AND u.es_sistema = 0 AND u.activo = 1 AND rp.permiso = 'confirmar_iban'
              AND ur.desde <= NEW.primera_vez_en
              AND (ur.hasta IS NULL OR ur.hasta > NEW.primera_vez_en))))
BEGIN SELECT RAISE(ABORT, 'una cuenta la da de alta el importador de maestros o una persona con confirmar_iban, en su propia orden'); END;

CREATE TRIGGER cuenta_bancaria_sin_update BEFORE UPDATE ON cuenta_bancaria
BEGIN SELECT RAISE(ABORT, 'cuenta_bancaria es de solo escritura: una cuenta no se modifica, se le anaden eventos'); END;
CREATE TRIGGER cuenta_bancaria_sin_delete BEFORE DELETE ON cuenta_bancaria
BEGIN SELECT RAISE(ABORT, 'cuenta_bancaria es de solo escritura: una cuenta no se borra'); END;

-- ------------------------------------------------------------ cuenta_evento

-- Lo que le pasa a una cuenta. Del maestro (baseline, visto_en_*,
-- ausente_en_*): cada importacion aceptada de cuentas apunta las que trae y
-- las que traia la anterior y ya no. De una persona (verificada, rechazada,
-- atestada, retirada): con confirmar_iban. Una verificacion dice como se hizo
-- (metodo), a que numero se llamo (telefono_usado) y, si era el del maestro,
-- el cambio que lo puso alli (telefono_ref); que cuente o no lo decide la
-- regla F8 (el numero de antes del documento, el enfriamiento tras un cambio).
-- documento_id o importacion_id es lo que la motivo: la factura con el IBAN
-- nuevo, o la importacion del maestro que lo cambio.
-- visto_en_documento esta en la lista de la especificacion pero nadie la
-- escribe: lo que dice un documento no entra en el registro (disparador
-- cuenta_evento_sin_documento).
CREATE TABLE cuenta_evento (
    id                 INTEGER PRIMARY KEY,
    cuenta_id          INTEGER NOT NULL REFERENCES cuenta_bancaria(id),
    tipo               TEXT NOT NULL CHECK (tipo IN ('baseline', 'visto_en_exact', 'ausente_en_exact', 'visto_en_trnsprnt', 'ausente_en_trnsprnt', 'visto_en_documento', 'verificada', 'rechazada', 'atestada', 'retirada')),
    importacion_id     INTEGER REFERENCES importacion(id),
    documento_id       INTEGER REFERENCES documento(id),
    metodo             TEXT CHECK (metodo IS NULL OR metodo IN ('llamada', 'videollamada', 'visita')),
    telefono_usado     TEXT,
    telefono_ref       INTEGER REFERENCES cambio_campo(id),
    persona_contactada TEXT,
    decision_facturas  TEXT CHECK (decision_facturas IS NULL OR decision_facturas IN ('pagar_a_verificada', 'anular')),
    usuario_id         INTEGER REFERENCES usuario(id),
    en                 TEXT NOT NULL CHECK (datetime(en) IS NOT NULL),
    nota               TEXT,
    evento_id          INTEGER NOT NULL REFERENCES evento(id),
    CHECK (tipo <> 'verificada' OR (metodo IS NOT NULL
                                    AND length(trim(coalesce(telefono_usado, ''))) > 0)),
    CHECK ((tipo IN ('verificada', 'rechazada', 'atestada', 'retirada')) = (usuario_id IS NOT NULL)),
    CHECK (tipo NOT IN ('baseline', 'visto_en_exact', 'ausente_en_exact', 'visto_en_trnsprnt',
                        'ausente_en_trnsprnt') OR importacion_id IS NOT NULL)
) STRICT;

CREATE INDEX cuenta_evento_cuenta ON cuenta_evento (cuenta_id, id);

-- Verificar, rechazar, atestar o retirar una cuenta: una persona activa con
-- confirmar_iban en ese momento, en su propia orden (el evento es el ultimo y
-- es suyo). El importador nunca escribe uno de estos.
CREATE TRIGGER cuenta_evento_de_persona BEFORE INSERT ON cuenta_evento
WHEN NEW.tipo IN ('verificada', 'rechazada', 'atestada', 'retirada') AND (
        NOT EXISTS (
            SELECT 1 FROM usuario AS u
            JOIN usuario_rol AS ur ON ur.usuario_id = u.id
            JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id
            WHERE u.id = NEW.usuario_id AND u.es_sistema = 0 AND u.activo = 1
              AND rp.permiso = 'confirmar_iban'
              AND ur.desde <= NEW.en AND (ur.hasta IS NULL OR ur.hasta > NEW.en))
     OR NEW.evento_id IS NOT (SELECT max(id) FROM evento)
     OR (SELECT usuario_id FROM evento WHERE id = NEW.evento_id) IS NOT NEW.usuario_id
     OR (SELECT actor FROM evento WHERE id = NEW.evento_id) IS NOT NEW.usuario_id)
BEGIN SELECT RAISE(ABORT, 'verificar, rechazar o atestar una cuenta es de una persona con confirmar_iban, en su propia orden'); END;

-- Lo que trae un maestro lo apunta el importador, en el evento de su
-- importacion en curso.
CREATE TRIGGER cuenta_evento_del_maestro BEFORE INSERT ON cuenta_evento
WHEN NEW.tipo IN ('baseline', 'visto_en_exact', 'ausente_en_exact', 'visto_en_trnsprnt',
                  'ausente_en_trnsprnt') AND (
        NEW.evento_id IS NOT (SELECT max(id) FROM evento)
     OR (SELECT actor FROM evento WHERE id = NEW.evento_id)
            IS NOT (SELECT id FROM usuario WHERE nombre = 'importador' AND es_sistema = 1)
     OR (SELECT estado FROM importacion WHERE id = NEW.importacion_id) IS NOT 'en_curso')
BEGIN SELECT RAISE(ABORT, 'lo que trae un maestro lo apunta el importador, con su importacion en curso'); END;

CREATE TRIGGER cuenta_evento_sin_documento BEFORE INSERT ON cuenta_evento
WHEN NEW.tipo = 'visto_en_documento'
BEGIN SELECT RAISE(ABORT, 'lo que dice un documento no entra en el registro de cuentas: se queda en la factura'); END;

CREATE TRIGGER cuenta_evento_sin_update BEFORE UPDATE ON cuenta_evento
BEGIN SELECT RAISE(ABORT, 'cuenta_evento es de solo escritura: no se modifica'); END;
CREATE TRIGGER cuenta_evento_sin_delete BEFORE DELETE ON cuenta_evento
BEGIN SELECT RAISE(ABORT, 'cuenta_evento es de solo escritura: no se borra'); END;

-- El estado registrado de cada cuenta: la ultima decision de una persona y,
-- sin ninguna, heredada (llego con el primer maestro) o registrada sin
-- verificar. en_exact dice si la trae la ultima importacion aceptada de Exact
-- que la miro. Si una verificacion cuenta (el numero era el del maestro de
-- antes del documento, fuera del enfriamiento) no lo dice la vista: lo
-- decide la regla F8, con la politica de cada pasada.
CREATE VIEW v_cuenta_estado AS
SELECT c.id AS cuenta_id, c.titular, c.proveedor_id, c.cliente_id, c.iban, c.primera_fuente,
       coalesce(
           (SELECT e.tipo FROM cuenta_evento AS e WHERE e.cuenta_id = c.id
              AND e.tipo IN ('verificada', 'rechazada', 'atestada', 'retirada')
            ORDER BY e.id DESC LIMIT 1),
           CASE WHEN EXISTS (SELECT 1 FROM cuenta_evento AS e WHERE e.cuenta_id = c.id
                               AND e.tipo = 'baseline')
                THEN 'heredada' ELSE 'registrada' END) AS estado_registrado,
       coalesce(
           (SELECT e.tipo = 'visto_en_exact' FROM cuenta_evento AS e WHERE e.cuenta_id = c.id
              AND e.tipo IN ('visto_en_exact', 'ausente_en_exact')
            ORDER BY e.id DESC LIMIT 1), 0) AS en_exact
FROM cuenta_bancaria AS c;

-- ---------------------------------------------------- beneficiario_conocido

-- A quien se paga sin ser proveedor (Belastingdienst, nominas, alquiler), para
-- que F7 (paso 7) no salte con esos cargos. Lo da de alta una persona con
-- admin; se retira, no se borra.
CREATE TABLE beneficiario_conocido (
    id          INTEGER PRIMARY KEY,
    iban        TEXT NOT NULL CHECK (length(iban) BETWEEN 15 AND 34
                                     AND iban NOT GLOB '*[^A-Z0-9]*'
                                     AND iban GLOB '[A-Z][A-Z][0-9][0-9]*'),
    nombre      TEXT NOT NULL CHECK (length(trim(nombre)) > 0),
    motivo      TEXT NOT NULL CHECK (length(trim(motivo)) > 0),
    creado_por  INTEGER NOT NULL REFERENCES usuario(id),
    creado_en   TEXT NOT NULL CHECK (datetime(creado_en) IS NOT NULL),
    retirada_en TEXT CHECK (retirada_en IS NULL OR datetime(retirada_en) IS NOT NULL),
    rev         INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0)
) STRICT;

CREATE UNIQUE INDEX beneficiario_conocido_vigente ON beneficiario_conocido (iban)
    WHERE retirada_en IS NULL;

-- ------------------------------------------------------- ciclo_facturacion

-- Cada cuanto se factura a un cliente o en un Objeto (V8, paso 10), desde que
-- dia (ancla) y con cuantos dias de gracia antes de dar el periodo por no
-- facturado.
CREATE TABLE ciclo_facturacion (
    id            INTEGER PRIMARY KEY,
    cliente_id    INTEGER REFERENCES cliente(id),
    objeto_id     INTEGER REFERENCES objeto(id),
    frecuencia    TEXT NOT NULL CHECK (frecuencia IN ('semanal', 'cuatrisemanal', 'mensual')),
    ancla         TEXT CHECK (ancla IS NULL OR date(ancla) IS ancla),
    dias_gracia   INTEGER NOT NULL DEFAULT 0 CHECK (dias_gracia >= 0),
    vigente_desde TEXT CHECK (vigente_desde IS NULL OR date(vigente_desde) IS vigente_desde),
    vigente_hasta TEXT CHECK (vigente_hasta IS NULL OR date(vigente_hasta) IS vigente_hasta),
    rev           INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0),
    CHECK (cliente_id IS NOT NULL OR objeto_id IS NOT NULL),
    CHECK (vigente_desde IS NULL OR vigente_hasta IS NULL OR vigente_desde <= vigente_hasta)
) STRICT;

CREATE INDEX ciclo_facturacion_cliente ON ciclo_facturacion (cliente_id);
CREATE INDEX ciclo_facturacion_objeto ON ciclo_facturacion (objeto_id);

-- ------------------------------------------------------- campos dudosos (Q2)

-- La instantanea busca en cada pasada los campos leidos con duda; son pocos
-- entre decenas de miles de procedencias, y sin este indice parcial la
-- busqueda recorre la tabla entera.
CREATE INDEX procedencia_campo_dudoso ON procedencia_campo (tabla, fila_id)
    WHERE dudoso = 1;

-- -------------------------------------------------- guardas (generadas)

CREATE TRIGGER beneficiario_conocido_guarda_insert BEFORE INSERT ON beneficiario_conocido
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'beneficiario_conocido' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.iban IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'beneficiario_conocido' AND fila_id = NEW.id AND rev = 0
        AND campo = 'iban' AND json_extract(valor_nuevo, '$') IS NEW.iban))
    OR (NEW.nombre IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'beneficiario_conocido' AND fila_id = NEW.id AND rev = 0
        AND campo = 'nombre' AND json_extract(valor_nuevo, '$') IS NEW.nombre))
    OR (NEW.motivo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'beneficiario_conocido' AND fila_id = NEW.id AND rev = 0
        AND campo = 'motivo' AND json_extract(valor_nuevo, '$') IS NEW.motivo))
    OR (NEW.creado_por IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'beneficiario_conocido' AND fila_id = NEW.id AND rev = 0
        AND campo = 'creado_por' AND json_extract(valor_nuevo, '$') IS NEW.creado_por))
    OR (NEW.creado_en IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'beneficiario_conocido' AND fila_id = NEW.id AND rev = 0
        AND campo = 'creado_en' AND json_extract(valor_nuevo, '$') IS NEW.creado_en))
    OR (NEW.retirada_en IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'beneficiario_conocido' AND fila_id = NEW.id AND rev = 0
        AND campo = 'retirada_en' AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'beneficiario_conocido es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER beneficiario_conocido_guarda_update BEFORE UPDATE ON beneficiario_conocido
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'beneficiario_conocido' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.iban IS NOT OLD.iban AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'beneficiario_conocido' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'iban' AND json_extract(valor_anterior, '$') IS OLD.iban
        AND json_extract(valor_nuevo, '$') IS NEW.iban))
    OR (NEW.nombre IS NOT OLD.nombre AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'beneficiario_conocido' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'nombre' AND json_extract(valor_anterior, '$') IS OLD.nombre
        AND json_extract(valor_nuevo, '$') IS NEW.nombre))
    OR (NEW.motivo IS NOT OLD.motivo AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'beneficiario_conocido' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'motivo' AND json_extract(valor_anterior, '$') IS OLD.motivo
        AND json_extract(valor_nuevo, '$') IS NEW.motivo))
    OR (NEW.creado_por IS NOT OLD.creado_por AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'beneficiario_conocido' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'creado_por' AND json_extract(valor_anterior, '$') IS OLD.creado_por
        AND json_extract(valor_nuevo, '$') IS NEW.creado_por))
    OR (NEW.creado_en IS NOT OLD.creado_en AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'beneficiario_conocido' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'creado_en' AND json_extract(valor_anterior, '$') IS OLD.creado_en
        AND json_extract(valor_nuevo, '$') IS NEW.creado_en))
    OR (NEW.retirada_en IS NOT OLD.retirada_en AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'beneficiario_conocido' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'retirada_en' AND json_extract(valor_anterior, '$') IS OLD.retirada_en
        AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'beneficiario_conocido es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER beneficiario_conocido_sin_delete BEFORE DELETE ON beneficiario_conocido
BEGIN SELECT RAISE(ABORT, 'beneficiario_conocido no se borra: una fila se retira o se desactiva'); END;


CREATE TRIGGER ciclo_facturacion_guarda_insert BEFORE INSERT ON ciclo_facturacion
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'ciclo_facturacion' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.cliente_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'ciclo_facturacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'cliente_id' AND json_extract(valor_nuevo, '$') IS NEW.cliente_id))
    OR (NEW.objeto_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'ciclo_facturacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'objeto_id' AND json_extract(valor_nuevo, '$') IS NEW.objeto_id))
    OR (NEW.frecuencia IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'ciclo_facturacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'frecuencia' AND json_extract(valor_nuevo, '$') IS NEW.frecuencia))
    OR (NEW.ancla IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'ciclo_facturacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'ancla' AND json_extract(valor_nuevo, '$') IS NEW.ancla))
    OR (NEW.dias_gracia IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'ciclo_facturacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'dias_gracia' AND json_extract(valor_nuevo, '$') IS NEW.dias_gracia))
    OR (NEW.vigente_desde IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'ciclo_facturacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'vigente_desde' AND json_extract(valor_nuevo, '$') IS NEW.vigente_desde))
    OR (NEW.vigente_hasta IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'ciclo_facturacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'vigente_hasta' AND json_extract(valor_nuevo, '$') IS NEW.vigente_hasta))
BEGIN SELECT RAISE(ABORT, 'ciclo_facturacion es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER ciclo_facturacion_guarda_update BEFORE UPDATE ON ciclo_facturacion
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'ciclo_facturacion' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.cliente_id IS NOT OLD.cliente_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'ciclo_facturacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'cliente_id' AND json_extract(valor_anterior, '$') IS OLD.cliente_id
        AND json_extract(valor_nuevo, '$') IS NEW.cliente_id))
    OR (NEW.objeto_id IS NOT OLD.objeto_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'ciclo_facturacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'objeto_id' AND json_extract(valor_anterior, '$') IS OLD.objeto_id
        AND json_extract(valor_nuevo, '$') IS NEW.objeto_id))
    OR (NEW.frecuencia IS NOT OLD.frecuencia AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'ciclo_facturacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'frecuencia' AND json_extract(valor_anterior, '$') IS OLD.frecuencia
        AND json_extract(valor_nuevo, '$') IS NEW.frecuencia))
    OR (NEW.ancla IS NOT OLD.ancla AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'ciclo_facturacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'ancla' AND json_extract(valor_anterior, '$') IS OLD.ancla
        AND json_extract(valor_nuevo, '$') IS NEW.ancla))
    OR (NEW.dias_gracia IS NOT OLD.dias_gracia AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'ciclo_facturacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'dias_gracia' AND json_extract(valor_anterior, '$') IS OLD.dias_gracia
        AND json_extract(valor_nuevo, '$') IS NEW.dias_gracia))
    OR (NEW.vigente_desde IS NOT OLD.vigente_desde AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'ciclo_facturacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'vigente_desde' AND json_extract(valor_anterior, '$') IS OLD.vigente_desde
        AND json_extract(valor_nuevo, '$') IS NEW.vigente_desde))
    OR (NEW.vigente_hasta IS NOT OLD.vigente_hasta AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'ciclo_facturacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'vigente_hasta' AND json_extract(valor_anterior, '$') IS OLD.vigente_hasta
        AND json_extract(valor_nuevo, '$') IS NEW.vigente_hasta))
BEGIN SELECT RAISE(ABORT, 'ciclo_facturacion es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER ciclo_facturacion_sin_delete BEFORE DELETE ON ciclo_facturacion
BEGIN SELECT RAISE(ABORT, 'ciclo_facturacion no se borra: una fila se retira o se desactiva'); END;

