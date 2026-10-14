-- Migracion 0001 (paso 1 de la V1): infraestructura, acceso, auditoria y evidencia.
--
-- Un fichero aplicado no se edita nunca: migrar.py guarda su sha256 y se
-- niega a seguir si cambia. Lo que haga falta despues va en 0002, 0003...
--
-- Clases de tabla (spec.md §4):
--   SOLO ESCRITURA: migracion, politica_version, evento, cambio_campo,
--     extraccion. UPDATE y DELETE abortan siempre.
--   EVIDENCIA CON UNA EXCEPCION: documento aborta UPDATE y DELETE salvo una
--     sola cosa, apuntar el original cuando aparece despues (ruta_cas de NULL
--     a su ruta, que se deriva del propio hash).
--   importacion: se actualiza solo mientras esta en_curso; no se borra.
--   usuario, usuario_rol: no se borran (se desactivan o se cierran con hasta).
--
-- Los disparadores que hacen de una tabla una tabla de solo escritura se
-- llaman <tabla>_sin_update y <tabla>_sin_delete; los tests los buscan por
-- ese nombre.
--
-- Fechas en TEXT YYYY-MM-DD comprobadas con date(); instantes en UTC con el
-- formato 2026-09-20T10:00:12+00:00. Ninguna columna REAL.

-- ---------------------------------------------------------------- migracion

CREATE TABLE migracion (
    version     INTEGER PRIMARY KEY,
    nombre      TEXT NOT NULL UNIQUE,
    sha256      TEXT NOT NULL CHECK (length(sha256) = 64),
    aplicada_en TEXT NOT NULL CHECK (datetime(aplicada_en) IS NOT NULL)
) STRICT;

CREATE TRIGGER migracion_sin_update BEFORE UPDATE ON migracion
BEGIN SELECT RAISE(ABORT, 'migracion es de solo escritura: no se modifica'); END;
CREATE TRIGGER migracion_sin_delete BEFORE DELETE ON migracion
BEGIN SELECT RAISE(ABORT, 'migracion es de solo escritura: no se borra'); END;

-- ------------------------------------------------------- usuarios y permisos

-- Un usuario de sistema (sistema, extractor, importador, motor) actua, pero
-- nunca tiene roles ni token: ninguna orden de persona puede llegar como el.
CREATE TABLE usuario (
    id           INTEGER PRIMARY KEY,
    nombre       TEXT NOT NULL UNIQUE CHECK (length(trim(nombre)) > 0),
    email        TEXT UNIQUE,
    es_sistema   INTEGER NOT NULL DEFAULT 0 CHECK (es_sistema IN (0, 1)),
    activo       INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    token_sha256 TEXT UNIQUE CHECK (token_sha256 IS NULL OR length(token_sha256) = 64),
    creado_en    TEXT NOT NULL CHECK (datetime(creado_en) IS NOT NULL),
    CHECK (es_sistema = 0 OR token_sha256 IS NULL)
) STRICT;

CREATE TRIGGER usuario_sin_delete BEFORE DELETE ON usuario
BEGIN SELECT RAISE(ABORT, 'un usuario no se borra: se desactiva'); END;

CREATE TRIGGER usuario_sistema_fijo BEFORE UPDATE ON usuario
WHEN NEW.id IS NOT OLD.id
  OR NEW.es_sistema IS NOT OLD.es_sistema
  OR (OLD.es_sistema = 1 AND NEW.nombre IS NOT OLD.nombre)
BEGIN SELECT RAISE(ABORT, 'ni el id, ni si es de sistema, ni el nombre de un usuario de sistema cambian'); END;

INSERT INTO usuario (nombre, es_sistema, creado_en) VALUES
    ('sistema',    1, strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')),
    ('extractor',  1, strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')),
    ('importador', 1, strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')),
    ('motor',      1, strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'));

-- El catalogo de permisos es una tabla y no un CHECK para poder anadir uno
-- con un INSERT en una migracion posterior, sin reconstruir rol_permiso.
CREATE TABLE permiso (
    id          INTEGER PRIMARY KEY,
    codigo      TEXT NOT NULL UNIQUE,
    descripcion TEXT NOT NULL
) STRICT;

INSERT INTO permiso (codigo, descripcion) VALUES
    ('ver_facturas',       'Ver facturas y su detalle'),
    ('editar_extraccion',  'Corregir un campo, dividir, anadir o excluir una linea, verificar o revertir'),
    ('anadir_informacion', 'Rellenar un valor que falta, anadir una nota'),
    ('cambiar_objeto',     'Cambiar la imputacion a un Objeto, anadir un alias de Objeto o recurso'),
    ('cambiar_po',         'Cambiar la imputacion a una PO, registrar o modificar una PO'),
    ('marcar_pagada',      'Marcar pagada, confirmar un pago propuesto'),
    ('anular_acreditar',   'Enlazar o confirmar relaciones, anular una factura, fusionar un duplicado'),
    ('resolver_aviso',     'Gestionar excepciones, cerrar un hallazgo cuya condicion ha desaparecido'),
    ('anular_aviso',       'Anular un hallazgo'),
    ('confirmar_iban',     'Verificar, rechazar o atestar un IBAN; fijar el telefono de verificacion'),
    ('admin',              'Usuarios, roles, politica, beneficiarios conocidos'),
    ('revisar_factura',    'Marcar una factura como revisada o devolverla'),
    ('gestionar_btw',      'Estado de los trimestres de BTW'),
    ('importar_datos',     'Lanzar importaciones');

CREATE TABLE rol (
    id          INTEGER PRIMARY KEY,
    nombre      TEXT NOT NULL UNIQUE CHECK (length(trim(nombre)) > 0),
    descripcion TEXT
) STRICT;

CREATE TABLE rol_permiso (
    id      INTEGER PRIMARY KEY,
    rol_id  INTEGER NOT NULL REFERENCES rol(id),
    permiso TEXT NOT NULL REFERENCES permiso(codigo),
    UNIQUE (rol_id, permiso)
) STRICT;

CREATE TABLE usuario_rol (
    id         INTEGER PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuario(id),
    rol_id     INTEGER NOT NULL REFERENCES rol(id),
    desde      TEXT NOT NULL CHECK (datetime(desde) IS NOT NULL),
    hasta      TEXT CHECK (hasta IS NULL OR (datetime(hasta) IS NOT NULL AND hasta >= desde))
) STRICT;

CREATE INDEX usuario_rol_usuario ON usuario_rol (usuario_id);

CREATE TRIGGER usuario_rol_sin_sistema BEFORE INSERT ON usuario_rol
WHEN (SELECT es_sistema FROM usuario WHERE id = NEW.usuario_id) = 1
BEGIN SELECT RAISE(ABORT, 'un usuario de sistema no puede tener roles'); END;

-- Un rol asignado solo se cierra (hasta), una vez; para cambiarlo se cierra
-- y se asigna otro, y queda la historia de quien tuvo que y cuando.
CREATE TRIGGER usuario_rol_solo_cierre BEFORE UPDATE ON usuario_rol
WHEN NEW.id IS NOT OLD.id OR NEW.usuario_id IS NOT OLD.usuario_id
  OR NEW.rol_id IS NOT OLD.rol_id OR NEW.desde IS NOT OLD.desde
  OR OLD.hasta IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'una asignacion de rol solo se cierra, una vez'); END;

CREATE TRIGGER usuario_rol_sin_delete BEFORE DELETE ON usuario_rol
BEGIN SELECT RAISE(ABORT, 'una asignacion de rol no se borra: se cierra con hasta'); END;

-- ----------------------------------------------------------------- politica

CREATE TABLE politica_version (
    id            INTEGER PRIMARY KEY,
    sha256        TEXT NOT NULL CHECK (length(sha256) = 64),
    fichero       TEXT NOT NULL,
    contenido     TEXT NOT NULL,
    vigente_desde TEXT NOT NULL CHECK (date(vigente_desde) IS vigente_desde),
    cargada_en    TEXT NOT NULL CHECK (datetime(cargada_en) IS NOT NULL),
    cargada_por   INTEGER NOT NULL REFERENCES usuario(id),
    UNIQUE (fichero, sha256, vigente_desde)
) STRICT;

CREATE TRIGGER politica_version_sin_update BEFORE UPDATE ON politica_version
BEGIN SELECT RAISE(ABORT, 'politica_version es de solo escritura: no se modifica'); END;
CREATE TRIGGER politica_version_sin_delete BEFORE DELETE ON politica_version
BEGIN SELECT RAISE(ABORT, 'politica_version es de solo escritura: no se borra'); END;

-- ---------------------------------------------------------------- auditoria

-- Cada evento lleva el hash del anterior y el suyo, calculados en
-- auditoria.py sobre el JSON canonico de la fila y de sus cambio_campo. El
-- disparador de abajo impide que un evento entre fuera de la cadena (con un
-- id que no sigue al ultimo, o colgando de otro hash). Que el hash sea el
-- correcto no lo puede comprobar SQLite: lo comprueba verificar_cadena().
--
-- usuario_id es la persona que lo pidio (NULL si no hay ninguna
-- identificada); actor es quien lo ejecuto, un usuario de sistema o la
-- propia persona. factura_id no lleva clave foranea porque la tabla factura
-- llega en la migracion 0002.
CREATE TABLE evento (
    id            INTEGER PRIMARY KEY,
    en            TEXT NOT NULL CHECK (datetime(en) IS NOT NULL),
    usuario_id    INTEGER REFERENCES usuario(id),
    actor         INTEGER NOT NULL REFERENCES usuario(id),
    tipo          TEXT NOT NULL CHECK (length(tipo) > 0),
    resultado     TEXT NOT NULL CHECK (resultado IN ('ok', 'denegado', 'error')),
    tabla         TEXT,
    fila_id       INTEGER,
    factura_id    INTEGER,
    motivo        TEXT,
    datos_json    TEXT CHECK (datos_json IS NULL OR json_valid(datos_json)),
    peticion_id   TEXT UNIQUE,
    hash_anterior TEXT NOT NULL CHECK (length(hash_anterior) = 64),
    hash          TEXT NOT NULL UNIQUE CHECK (length(hash) = 64)
) STRICT;

CREATE INDEX evento_fila ON evento (tabla, fila_id);
CREATE INDEX evento_factura ON evento (factura_id);

CREATE TRIGGER evento_encadenado BEFORE INSERT ON evento
WHEN NEW.id IS NOT (SELECT coalesce(max(id), 0) + 1 FROM evento)
  OR NEW.hash_anterior IS NOT coalesce(
        (SELECT hash FROM evento ORDER BY id DESC LIMIT 1),
        '0000000000000000000000000000000000000000000000000000000000000000')
BEGIN SELECT RAISE(ABORT, 'evento fuera de la cadena: el id o el hash_anterior no siguen al ultimo'); END;

CREATE TRIGGER evento_persona BEFORE INSERT ON evento
WHEN NEW.usuario_id IS NOT NULL
 AND (SELECT es_sistema FROM usuario WHERE id = NEW.usuario_id) = 1
BEGIN SELECT RAISE(ABORT, 'usuario_id es la persona que lo pidio; un usuario de sistema va en actor'); END;

CREATE TRIGGER evento_sin_update BEFORE UPDATE ON evento
BEGIN SELECT RAISE(ABORT, 'evento es de solo escritura: no se modifica'); END;
CREATE TRIGGER evento_sin_delete BEFORE DELETE ON evento
BEGIN SELECT RAISE(ABORT, 'evento es de solo escritura: no se borra'); END;

-- La historia de cada campo. Cuelga siempre del ultimo evento, que es el de
-- la orden en curso: un cambio no se puede colgar de un evento viejo, y su
-- contenido entra en el hash de su evento.
CREATE TABLE cambio_campo (
    id              INTEGER PRIMARY KEY,
    evento_id       INTEGER NOT NULL REFERENCES evento(id),
    tabla           TEXT NOT NULL,
    fila_id         INTEGER NOT NULL,
    factura_id      INTEGER,
    campo           TEXT NOT NULL CHECK (length(campo) > 0),
    rev             INTEGER NOT NULL CHECK (rev >= 0),
    valor_anterior  TEXT CHECK (valor_anterior IS NULL OR json_valid(valor_anterior)),
    valor_nuevo     TEXT CHECK (valor_nuevo IS NULL OR json_valid(valor_nuevo)),
    fuente_anterior TEXT CHECK (fuente_anterior IS NULL OR fuente_anterior IN (
        'extraccion', 'importacion', 'planning', 'maestro',
        'manual_entrada', 'manual_correccion', 'calculado')),
    fuente_nueva    TEXT NOT NULL CHECK (fuente_nueva IN (
        'extraccion', 'importacion', 'planning', 'maestro',
        'manual_entrada', 'manual_correccion', 'calculado')),
    motivo          TEXT,
    CHECK (fuente_nueva <> 'manual_correccion' OR length(trim(coalesce(motivo, ''))) > 0)
) STRICT;

CREATE INDEX cambio_campo_fila ON cambio_campo (tabla, fila_id, rev);
CREATE INDEX cambio_campo_evento ON cambio_campo (evento_id);

CREATE TRIGGER cambio_campo_del_ultimo_evento BEFORE INSERT ON cambio_campo
WHEN NEW.evento_id IS NOT (SELECT max(id) FROM evento)
BEGIN SELECT RAISE(ABORT, 'un cambio_campo solo cuelga del evento de la orden en curso'); END;

CREATE TRIGGER cambio_campo_sin_update BEFORE UPDATE ON cambio_campo
BEGIN SELECT RAISE(ABORT, 'cambio_campo es de solo escritura: no se modifica'); END;
CREATE TRIGGER cambio_campo_sin_delete BEFORE DELETE ON cambio_campo
BEGIN SELECT RAISE(ABORT, 'cambio_campo es de solo escritura: no se borra'); END;

-- ---------------------------------------------------------------- evidencia

-- Un documento por hash. ruta_cas es la ruta relativa dentro de
-- datos/documentos/ (<sha[:2]>/<sha256>.<ext>) y se deriva del hash; es NULL
-- cuando no se encontro el original (hallazgo Q4). ruta_declarada la pone la
-- via de entrada, nunca el modelo.
CREATE TABLE documento (
    id              INTEGER PRIMARY KEY,
    sha256          TEXT NOT NULL UNIQUE
                    CHECK (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
    nombre_original TEXT,
    tipo_mime       TEXT NOT NULL,
    bytes           INTEGER CHECK (bytes IS NULL OR bytes >= 0),
    ruta_cas        TEXT UNIQUE,
    origen          TEXT NOT NULL CHECK (origen IN (
        'carpeta', 'correo', 'exact', 'trnsprnt', 'banco', 'manual', 'out_v1')),
    ruta_declarada  TEXT NOT NULL CHECK (ruta_declarada IN (
        'entrante', 'saliente', 'maestro', 'banco', 'planning')),
    mensaje_id      TEXT,
    recibido_en     TEXT CHECK (recibido_en IS NULL OR datetime(recibido_en) IS NOT NULL),
    recibido_fuente TEXT NOT NULL CHECK (recibido_fuente IN (
        'correo', 'ingesta', 'mtime', 'desconocido')),
    registrado_en   TEXT NOT NULL CHECK (datetime(registrado_en) IS NOT NULL),
    registrado_por  INTEGER NOT NULL REFERENCES usuario(id),
    CHECK (ruta_cas IS NULL OR substr(ruta_cas, 1, 68) = substr(sha256, 1, 2) || '/' || sha256 || '.'),
    CHECK (ruta_cas IS NULL OR bytes IS NOT NULL),
    CHECK ((recibido_fuente = 'desconocido') = (recibido_en IS NULL))
) STRICT;

CREATE TRIGGER documento_sin_update BEFORE UPDATE ON documento
WHEN NOT (
        OLD.ruta_cas IS NULL AND NEW.ruta_cas IS NOT NULL
    AND NEW.id IS OLD.id AND NEW.sha256 IS OLD.sha256
    AND NEW.nombre_original IS OLD.nombre_original AND NEW.tipo_mime IS OLD.tipo_mime
    AND (OLD.bytes IS NULL OR NEW.bytes IS OLD.bytes)
    AND NEW.origen IS OLD.origen AND NEW.ruta_declarada IS OLD.ruta_declarada
    AND NEW.mensaje_id IS OLD.mensaje_id AND NEW.recibido_en IS OLD.recibido_en
    AND NEW.recibido_fuente IS OLD.recibido_fuente
    AND NEW.registrado_en IS OLD.registrado_en AND NEW.registrado_por IS OLD.registrado_por)
BEGIN SELECT RAISE(ABORT, 'documento es evidencia: solo se puede apuntar su original una vez'); END;
CREATE TRIGGER documento_sin_delete BEFORE DELETE ON documento
BEGIN SELECT RAISE(ABORT, 'documento es evidencia: no se borra'); END;

-- Un documento puede tener muchas extracciones y ninguna se sobrescribe.
-- contenido_json es el registro tal cual se escribio (el mismo texto que el
-- fichero de out/), y contenido_sha256 el hash de esos bytes en UTF-8.
CREATE TABLE extraccion (
    id               INTEGER PRIMARY KEY,
    documento_id     INTEGER NOT NULL REFERENCES documento(id),
    modelo           TEXT NOT NULL CHECK (length(modelo) > 0),
    prompt_version   TEXT NOT NULL,
    schema_version   TEXT NOT NULL,
    via              TEXT NOT NULL CHECK (via IN ('api', 'lote', 'out_v1')),
    extraido_en      TEXT CHECK (extraido_en IS NULL OR datetime(extraido_en) IS NOT NULL),
    request_id       TEXT,
    uso_json         TEXT CHECK (uso_json IS NULL OR json_valid(uso_json)),
    contenido_json   TEXT NOT NULL CHECK (json_valid(contenido_json)),
    contenido_sha256 TEXT NOT NULL CHECK (length(contenido_sha256) = 64),
    registrada_en    TEXT NOT NULL CHECK (datetime(registrada_en) IS NOT NULL),
    UNIQUE (documento_id, modelo, prompt_version, schema_version, contenido_sha256)
) STRICT;

CREATE INDEX extraccion_documento ON extraccion (documento_id);

CREATE TRIGGER extraccion_sin_update BEFORE UPDATE ON extraccion
BEGIN SELECT RAISE(ABORT, 'extraccion es evidencia: no se modifica'); END;
CREATE TRIGGER extraccion_sin_delete BEFORE DELETE ON extraccion
BEGIN SELECT RAISE(ABORT, 'extraccion es evidencia: no se borra'); END;

-- Un fichero importado. Importar dos veces el mismo fichero no hace nada
-- (UNIQUE de fuente, tipo y hash del fichero). Se rellena mientras esta
-- en_curso y se congela al cerrarse.
CREATE TABLE importacion (
    id               INTEGER PRIMARY KEY,
    fuente           TEXT NOT NULL CHECK (length(fuente) > 0),
    tipo             TEXT NOT NULL CHECK (length(tipo) > 0),
    formato          TEXT NOT NULL CHECK (length(formato) > 0),
    documento_id     INTEGER REFERENCES documento(id),
    fichero_sha256   TEXT NOT NULL CHECK (length(fichero_sha256) = 64),
    mapeo_sha256     TEXT CHECK (mapeo_sha256 IS NULL OR length(mapeo_sha256) = 64),
    exportado_en     TEXT CHECK (exportado_en IS NULL OR datetime(exportado_en) IS NOT NULL),
    cubre_desde      TEXT CHECK (cubre_desde IS NULL OR date(cubre_desde) IS cubre_desde),
    cubre_hasta      TEXT CHECK (cubre_hasta IS NULL OR date(cubre_hasta) IS cubre_hasta),
    completa         INTEGER NOT NULL DEFAULT 0 CHECK (completa IN (0, 1)),
    estado           TEXT NOT NULL DEFAULT 'en_curso'
                     CHECK (estado IN ('en_curso', 'aceptada', 'rechazada', 'parcial')),
    filas_leidas     INTEGER NOT NULL DEFAULT 0 CHECK (filas_leidas >= 0),
    filas_aceptadas  INTEGER NOT NULL DEFAULT 0 CHECK (filas_aceptadas >= 0),
    filas_rechazadas INTEGER NOT NULL DEFAULT 0 CHECK (filas_rechazadas >= 0),
    rechazos_json    TEXT CHECK (rechazos_json IS NULL OR json_valid(rechazos_json)),
    iniciada_en      TEXT NOT NULL CHECK (datetime(iniciada_en) IS NOT NULL),
    terminada_en     TEXT CHECK (terminada_en IS NULL OR datetime(terminada_en) IS NOT NULL),
    iniciada_por     INTEGER REFERENCES usuario(id),
    actor            INTEGER NOT NULL REFERENCES usuario(id),
    UNIQUE (fuente, tipo, fichero_sha256),
    CHECK (cubre_desde IS NULL OR cubre_hasta IS NULL OR cubre_desde <= cubre_hasta),
    CHECK (estado = 'en_curso' OR terminada_en IS NOT NULL)
) STRICT;

CREATE TRIGGER importacion_persona BEFORE INSERT ON importacion
WHEN NEW.iniciada_por IS NOT NULL
 AND (SELECT es_sistema FROM usuario WHERE id = NEW.iniciada_por) = 1
BEGIN SELECT RAISE(ABORT, 'iniciada_por es la persona que la lanzo; el usuario de sistema va en actor'); END;

CREATE TRIGGER importacion_sin_update BEFORE UPDATE ON importacion
WHEN OLD.estado <> 'en_curso'
  OR NEW.id IS NOT OLD.id OR NEW.fuente IS NOT OLD.fuente OR NEW.tipo IS NOT OLD.tipo
  OR NEW.fichero_sha256 IS NOT OLD.fichero_sha256
  OR NEW.iniciada_en IS NOT OLD.iniciada_en OR NEW.iniciada_por IS NOT OLD.iniciada_por
  OR NEW.actor IS NOT OLD.actor
BEGIN SELECT RAISE(ABORT, 'una importacion solo se modifica mientras esta en curso, y sin cambiar de fichero'); END;
CREATE TRIGGER importacion_sin_delete BEFORE DELETE ON importacion
BEGIN SELECT RAISE(ABORT, 'importacion es evidencia: no se borra'); END;

-- La extraccion vigente de cada documento, hasta que el paso 2 la fije en
-- factura.extraccion_vigente_id: la mas reciente por extraido_en, y en
-- empate la que entro despues. Es la misma regla que report.load_records
-- aplica a out/.
CREATE VIEW v_extraccion_vigente AS
SELECT e.*
FROM extraccion AS e
WHERE NOT EXISTS (
    SELECT 1 FROM extraccion AS o
    WHERE o.documento_id = e.documento_id
      AND (coalesce(o.extraido_en, '') > coalesce(e.extraido_en, '')
           OR (coalesce(o.extraido_en, '') = coalesce(e.extraido_en, '') AND o.id > e.id))
);
