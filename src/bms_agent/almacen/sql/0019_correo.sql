-- Migracion 0019 (paso 18): el correo de facturas y la lectura automatica con tope.
--
-- Un fichero aplicado no se edita nunca (ver 0001). Lo que haga falta
-- despues va en 0020, 0021...
--
-- Lo que llega: un componente de correo que solo trae (lee un buzon dedicado
-- de Microsoft 365, sin escribir nada en el) y deja los PDF en su bandeja; la
-- orden `correo registrar`, sin red, que los mete en el almacen de originales
-- y apunta cada mensaje y cada adjunto; y la lectura automatica: gastar en
-- leer sin que una persona diga si cada vez, solo dentro de una autorizacion
-- permanente que firma en la app una persona con admin, con topes por dia,
-- por mes, por ronda y por factura. Nada de esto aprueba, paga ni crea una
-- factura: solo trae documentos y gasta en leerlos.
--
-- Lo que esta migracion garantiza:
--   - Dos usuarios de sistema nuevos: correo (registra lo que trajo el
--     correo) y automatico (firma, en nombre de la autorizacion vigente, las
--     lecturas automaticas, sus exclusiones y la pausa por volumen). Como los
--     de 0001, sin roles ni token. Si ya hubiera una persona que se llama
--     exactamente asi, la migracion para (nombre UNIQUE): no se mezclan.
--   - lectura_automatica: cada version de la autorizacion; la vigente es la
--     de mayor id, y sin ninguna, apagada. La firma siempre una persona. Los
--     techos (20 USD al dia, 200 al mes) acotan un error o un token robado, y
--     una automatica solo la acepta la vigente, encendida, con un tope que no
--     pasa del de su dia: un error al aceptarla tampoco gasta mas.
--   - solicitud_lectura y pasada_lectura se rehacen (SQLite no cambia un
--     CHECK) con los mismos datos, para admitir la lectura automatica: origen
--     y aprobada_via 'automatica' con la autorizacion que la cubre
--     (autorizacion_id), y los motivos nuevos de una peticion que termina sin
--     leer (los topes, las exclusiones, sin autorizacion) o que la API paro
--     (saldo, clave_rechazada, api_no_disponible). Una persona no puede dar el
--     si a una automatica, ni una automatica sale de otro sitio.
--   - Del correo se guarda lo que hace falta para la evidencia y para que una
--     persona reconozca el mensaje, y nada mas: ni el cuerpo, ni las
--     cabeceras, ni los destinatarios. Remitente, asunto y nombres de adjunto
--     son texto de fuera (*_doc): se ensenan y nunca deciden nada.
--
-- Clases de tabla (spec.md §4, como en docs/modelo-datos.md):
--   lectura_automatica, exclusion_automatica, pausa_lectura_automatica,
--     correo_atendido: SOLO ESCRITURA (lo que deciden las personas, o el sistema
--     en nombre de la autorizacion, como una anulacion o una nota).
--   mensaje_correo, adjunto_correo, ronda_correo: EVIDENCIA (lo que llego de
--     fuera: el buzon y lo que conto el componente de correo).
--   En las siete, UPDATE y DELETE abortan siempre (<tabla>_sin_update,
--     <tabla>_sin_delete).
--   solicitud_lectura, pasada_lectura: como en 0018 (avanzan por sus estados
--     y fases solo como dice lectura.py; terminadas, no cambian; no se borran).
--   estado_correo, estado_ciclo: CACHE. Una fila cada una, que se reescribe;
--     nunca son la fuente de nada (el estado del correo sale de su bandeja, y
--     el del ciclo, de la ultima vez que paso).

-- ------------------------------------------------------- usuarios de sistema

INSERT INTO usuario (nombre, es_sistema, creado_en) VALUES
    ('correo',     1, strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')),
    ('automatico', 1, strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'));

-- ------------------------------------------------------- lectura_automatica

-- Cada cambio (encender, cambiar un tope, apagar) es una fila nueva, con quien
-- la firmo, cuando y por que. En millonesimas de dolar, como lo gastado.
CREATE TABLE lectura_automatica (
    id                          INTEGER PRIMARY KEY,
    activa                      INTEGER NOT NULL CHECK (activa IN (0, 1)),
    tope_dia_usd_micro          INTEGER NOT NULL CHECK (tope_dia_usd_micro BETWEEN 1 AND 20000000),
    tope_mes_usd_micro          INTEGER NOT NULL CHECK (tope_mes_usd_micro BETWEEN tope_dia_usd_micro AND 200000000),
    max_documentos              INTEGER NOT NULL CHECK (max_documentos BETWEEN 1 AND 100),
    max_por_documento_usd_micro INTEGER NOT NULL CHECK (max_por_documento_usd_micro BETWEEN 1 AND tope_dia_usd_micro),
    fijada_por                  INTEGER NOT NULL REFERENCES usuario(id),
    fijada_en                   TEXT NOT NULL CHECK (datetime(fijada_en) IS NOT NULL),
    motivo                      TEXT
) STRICT;

-- La autoriza una persona, nunca un usuario de sistema.
CREATE TRIGGER lectura_automatica_personas_alta BEFORE INSERT ON lectura_automatica
WHEN (SELECT es_sistema FROM usuario WHERE id = NEW.fijada_por) IS NOT 0
BEGIN SELECT RAISE(ABORT, 'la lectura automatica la autoriza una persona, nunca un usuario de sistema'); END;

CREATE TRIGGER lectura_automatica_sin_update BEFORE UPDATE ON lectura_automatica
BEGIN SELECT RAISE(ABORT, 'lectura_automatica es de solo escritura: no se modifica'); END;
CREATE TRIGGER lectura_automatica_sin_delete BEFORE DELETE ON lectura_automatica
BEGIN SELECT RAISE(ABORT, 'lectura_automatica es de solo escritura: no se borra'); END;

-- ---------------------------------------- solicitud_lectura y pasada_lectura

-- Se rehacen las dos con sus id, en este orden y no en otro (registro del paso
-- 18): con las claves foraneas encendidas y pasadas que apuntan a peticiones,
-- la comprobacion se aplaza al COMMIT, y la pasada nueva apunta a la peticion
-- NUEVA. Si apuntara al nombre final, el DROP de la vieja dejaria una
-- violacion aplazada que nada deshace y el COMMIT fallaria. El RENAME de la
-- peticion reescribe la referencia de la pasada. Los disparadores de 0018 no
-- saltan al copiar: son de las tablas viejas, y los nuevos se crean despues,
-- con los mismos nombres.
PRAGMA defer_foreign_keys = ON;

CREATE TABLE solicitud_lectura_nueva (
    id                  INTEGER PRIMARY KEY,
    origen              TEXT NOT NULL CHECK (origen IN ('app', 'lector', 'automatica')),
    pedida_por          INTEGER REFERENCES usuario(id),
    pedida_en           TEXT NOT NULL CHECK (datetime(pedida_en) IS NOT NULL),
    estado              TEXT NOT NULL CHECK (estado IN (
        'pedida', 'comprobando', 'contando', 'esperando_aprobacion', 'aprobada', 'leyendo',
        'hecha', 'fallida', 'caducada', 'cancelada', 'nada_que_leer')),
    motivo              TEXT,
    motivo_codigo       TEXT CHECK (motivo_codigo IS NULL OR motivo_codigo IN (
        'buzon_vacio', 'clave', 'salida', 'aislamiento', 'contar', 'sin_tarifa', 'estimacion',
        'lectura', 'interrumpida', 'abandonada', 'ya_leidas',
        'limite_dia', 'limite_mes', 'excluidas', 'sin_autorizacion',
        'saldo', 'clave_rechazada', 'api_no_disponible')),
    tomada_en           TEXT CHECK (tomada_en IS NULL OR datetime(tomada_en) IS NOT NULL),
    pdf_nuevos          INTEGER CHECK (pdf_nuevos IS NULL OR pdf_nuevos >= 0),
    pdf_ya_leidos       INTEGER CHECK (pdf_ya_leidos IS NULL OR pdf_ya_leidos >= 0),
    coste_min_usd_micro INTEGER CHECK (coste_min_usd_micro IS NULL OR coste_min_usd_micro >= 0),
    coste_max_usd_micro INTEGER,
    huella_estimacion   TEXT CHECK (huella_estimacion IS NULL OR length(huella_estimacion) = 64),
    estimacion_json     TEXT CHECK (estimacion_json IS NULL OR json_valid(estimacion_json)),
    contada_en          TEXT CHECK (contada_en IS NULL OR datetime(contada_en) IS NOT NULL),
    caduca_en           TEXT CHECK (caduca_en IS NULL OR datetime(caduca_en) IS NOT NULL),
    aprobada_por        INTEGER REFERENCES usuario(id),
    aprobada_en         TEXT CHECK (aprobada_en IS NULL OR datetime(aprobada_en) IS NOT NULL),
    aprobada_via        TEXT CHECK (aprobada_via IS NULL OR aprobada_via IN (
        'app', 'ventana', 'automatica')),
    -- La autorizacion permanente que cubre una automatica (la vigente al aceptarla).
    autorizacion_id     INTEGER REFERENCES lectura_automatica(id),
    tope_usd_micro      INTEGER CHECK (tope_usd_micro IS NULL OR tope_usd_micro > 0),
    huella_aprobada     TEXT CHECK (huella_aprobada IS NULL OR length(huella_aprobada) = 64),
    cancelada_por       INTEGER REFERENCES usuario(id),
    cancelada_en        TEXT CHECK (cancelada_en IS NULL OR datetime(cancelada_en) IS NOT NULL),
    cancelada_via       TEXT CHECK (cancelada_via IS NULL OR cancelada_via IN ('app', 'ventana')),
    terminada_en        TEXT CHECK (terminada_en IS NULL OR datetime(terminada_en) IS NOT NULL),
    actualizada_en      TEXT NOT NULL CHECK (datetime(actualizada_en) IS NOT NULL),
    -- La de la app la pide una persona; la del lector, nadie (quien abrio la ventana); la
    -- automatica, nadie (el ciclo, con la autorizacion vigente).
    CHECK ((origen = 'app') = (pedida_por IS NOT NULL)),
    CHECK (coste_max_usd_micro IS NULL OR coste_max_usd_micro >= coste_min_usd_micro),
    -- Esperar el si exige la estimacion entera y un plazo.
    CHECK (estado <> 'esperando_aprobacion' OR (
        huella_estimacion IS NOT NULL AND coste_max_usd_micro IS NOT NULL
        AND pdf_nuevos > 0 AND caduca_en IS NOT NULL)),
    -- El si: cuando, por donde, con que tope y para que huella, todo junto. Desde la app
    -- lo da una persona; desde la ventana del lector, quien la tiene delante; en una
    -- automatica, la autorizacion permanente que firmo una persona.
    CHECK ((aprobada_en IS NULL) = (aprobada_via IS NULL)
           AND (aprobada_en IS NULL) = (tope_usd_micro IS NULL)
           AND (aprobada_en IS NULL) = (huella_aprobada IS NULL)),
    CHECK ((aprobada_via = 'app') = (aprobada_por IS NOT NULL)),
    -- La automatica lleva su autorizacion, y solo ella (IS: sin si, tampoco autorizacion).
    CHECK ((aprobada_via IS 'automatica') = (autorizacion_id IS NOT NULL)),
    -- Solo una automatica se acepta sola, y una automatica no la acepta nadie mas.
    CHECK (aprobada_via IS NOT 'automatica' OR origen = 'automatica'),
    CHECK (origen IS NOT 'automatica' OR aprobada_via IS NULL OR aprobada_via = 'automatica'),
    -- El tope no pasa del extremo alto de lo que se vio.
    CHECK (tope_usd_micro IS NULL OR tope_usd_micro <= coste_max_usd_micro),
    CHECK (estado NOT IN ('aprobada', 'leyendo', 'hecha') OR aprobada_en IS NOT NULL),
    CHECK ((cancelada_en IS NULL) = (cancelada_via IS NULL)),
    CHECK ((cancelada_via = 'app') = (cancelada_por IS NOT NULL)),
    CHECK (estado <> 'cancelada' OR cancelada_en IS NOT NULL),
    CHECK ((terminada_en IS NULL) = (estado IN (
        'pedida', 'comprobando', 'contando', 'esperando_aprobacion', 'aprobada', 'leyendo')))
) STRICT;

INSERT INTO solicitud_lectura_nueva (
    id, origen, pedida_por, pedida_en, estado, motivo, motivo_codigo, tomada_en, pdf_nuevos,
    pdf_ya_leidos, coste_min_usd_micro, coste_max_usd_micro, huella_estimacion, estimacion_json,
    contada_en, caduca_en, aprobada_por, aprobada_en, aprobada_via, tope_usd_micro,
    huella_aprobada, cancelada_por, cancelada_en, cancelada_via, terminada_en, actualizada_en)
SELECT id, origen, pedida_por, pedida_en, estado, motivo, motivo_codigo, tomada_en, pdf_nuevos,
       pdf_ya_leidos, coste_min_usd_micro, coste_max_usd_micro, huella_estimacion,
       estimacion_json, contada_en, caduca_en, aprobada_por, aprobada_en, aprobada_via,
       tope_usd_micro, huella_aprobada, cancelada_por, cancelada_en, cancelada_via,
       terminada_en, actualizada_en
FROM solicitud_lectura ORDER BY id;

CREATE TABLE pasada_lectura_nueva (
    id               INTEGER PRIMARY KEY,
    solicitud_id     INTEGER NOT NULL UNIQUE REFERENCES solicitud_lectura_nueva(id),
    fase             TEXT NOT NULL CHECK (fase IN (
        'cargando', 'leyendo', 'comparando', 'analizando', 'organizando',
        'hecha', 'fallida', 'cancelada', 'tope')),
    total            INTEGER NOT NULL DEFAULT 0 CHECK (total >= 0),
    leidas           INTEGER NOT NULL DEFAULT 0 CHECK (leidas >= 0),
    ya_leidas        INTEGER NOT NULL DEFAULT 0 CHECK (ya_leidas >= 0),
    fallidas         INTEGER NOT NULL DEFAULT 0 CHECK (fallidas >= 0),
    coste_usd_micro  INTEGER NOT NULL DEFAULT 0 CHECK (coste_usd_micro >= 0),
    documento_actual TEXT,
    documento_fase   TEXT CHECK (documento_fase IS NULL OR documento_fase IN (
        'leyendo', 'comparando', 'guardando')),
    -- Cada fase con el instante en que empezo, en orden: [{"fase", "en"}].
    fases_json       TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(fases_json)),
    -- Lo que fue de cada documento: [{"documento_id", "nombre", "estado", ...}].
    resultado_json   TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(resultado_json)),
    motivo           TEXT,
    empezada_en      TEXT NOT NULL CHECK (datetime(empezada_en) IS NOT NULL),
    terminada_en     TEXT CHECK (terminada_en IS NULL OR datetime(terminada_en) IS NOT NULL),
    actualizada_en   TEXT NOT NULL CHECK (datetime(actualizada_en) IS NOT NULL),
    CHECK (leidas + ya_leidas + fallidas <= total),
    CHECK ((documento_actual IS NULL) = (documento_fase IS NULL)),
    CHECK ((terminada_en IS NULL) = (fase IN (
        'cargando', 'leyendo', 'comparando', 'analizando', 'organizando')))
) STRICT;

INSERT INTO pasada_lectura_nueva (
    id, solicitud_id, fase, total, leidas, ya_leidas, fallidas, coste_usd_micro,
    documento_actual, documento_fase, fases_json, resultado_json, motivo, empezada_en,
    terminada_en, actualizada_en)
SELECT id, solicitud_id, fase, total, leidas, ya_leidas, fallidas, coste_usd_micro,
       documento_actual, documento_fase, fases_json, resultado_json, motivo, empezada_en,
       terminada_en, actualizada_en
FROM pasada_lectura ORDER BY id;

DROP TABLE pasada_lectura;
DROP TABLE solicitud_lectura;

ALTER TABLE solicitud_lectura_nueva RENAME TO solicitud_lectura;
ALTER TABLE pasada_lectura_nueva RENAME TO pasada_lectura;

-- Los indices y los disparadores de 0018, con sus nombres de 0018. Cambia solo
-- solicitud_lectura_fija, que congela tambien la autorizacion de una automatica,
-- y se anade solicitud_lectura_automatica_vigente.

-- Viva, una sola: dos lectores no leen a la vez ni gastan dos veces (tampoco una
-- automatica y una de una persona).
CREATE UNIQUE INDEX solicitud_lectura_una_viva ON solicitud_lectura ((estado IS NOT NULL))
    WHERE estado IN ('pedida', 'comprobando', 'contando', 'esperando_aprobacion', 'aprobada',
                     'leyendo');

CREATE INDEX solicitud_lectura_estado ON solicitud_lectura (estado);

-- Quien pide, aprueba o cancela desde la app es una persona, nunca un usuario de sistema.
CREATE TRIGGER solicitud_lectura_personas_alta BEFORE INSERT ON solicitud_lectura
WHEN (NEW.pedida_por IS NOT NULL
      AND (SELECT es_sistema FROM usuario WHERE id = NEW.pedida_por) IS NOT 0)
  OR NEW.estado NOT IN ('pedida', 'comprobando')
  OR NEW.aprobada_en IS NOT NULL OR NEW.cancelada_en IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'una solicitud de lectura nace pedida (o comprobando, si la crea el lector), sin si ni no, y la pide una persona'); END;

CREATE TRIGGER solicitud_lectura_personas BEFORE UPDATE ON solicitud_lectura
WHEN (NEW.aprobada_por IS NOT NULL
      AND (SELECT es_sistema FROM usuario WHERE id = NEW.aprobada_por) IS NOT 0)
  OR (NEW.cancelada_por IS NOT NULL
      AND (SELECT es_sistema FROM usuario WHERE id = NEW.cancelada_por) IS NOT 0)
BEGIN SELECT RAISE(ABORT, 'el si o el no desde la app lo da una persona'); END;

-- Una automatica la acepta la autorizacion vigente (la de mayor id), y solo si
-- esta encendida, con un tope que no pasa del de un dia de esa autorizacion (lo
-- que queda hoy nunca es mas). El tope lo calcula `lectura autorizar`; esto es
-- para que un error suyo tampoco acepte con una autorizacion vieja o apagada, ni
-- deje gastar en una sola lectura mas que el dia entero.
CREATE TRIGGER solicitud_lectura_automatica_vigente BEFORE UPDATE ON solicitud_lectura
WHEN NEW.aprobada_via IS 'automatica' AND OLD.aprobada_en IS NULL
 AND (NEW.autorizacion_id IS NOT (SELECT max(id) FROM lectura_automatica)
      OR (SELECT activa FROM lectura_automatica WHERE id = NEW.autorizacion_id) IS NOT 1
      OR coalesce(NEW.tope_usd_micro <= (SELECT tope_dia_usd_micro FROM lectura_automatica
                                         WHERE id = NEW.autorizacion_id), 0) = 0)
BEGIN SELECT RAISE(ABORT, 'una automatica la acepta la autorizacion vigente y encendida, con un tope que no pasa del de su dia'); END;

-- Lo que se pidio y lo que se aprobo no cambian: el si vale para la estimacion que se vio
-- (y, en una automatica, para la autorizacion que la cubrio).
CREATE TRIGGER solicitud_lectura_fija BEFORE UPDATE ON solicitud_lectura
WHEN NEW.id IS NOT OLD.id OR NEW.origen IS NOT OLD.origen
  OR NEW.pedida_por IS NOT OLD.pedida_por OR NEW.pedida_en IS NOT OLD.pedida_en
  OR (OLD.aprobada_en IS NOT NULL AND (
        NEW.aprobada_en IS NOT OLD.aprobada_en OR NEW.aprobada_por IS NOT OLD.aprobada_por
        OR NEW.aprobada_via IS NOT OLD.aprobada_via OR NEW.tope_usd_micro IS NOT OLD.tope_usd_micro
        OR NEW.huella_aprobada IS NOT OLD.huella_aprobada
        OR NEW.huella_estimacion IS NOT OLD.huella_estimacion
        OR NEW.estimacion_json IS NOT OLD.estimacion_json
        OR NEW.coste_min_usd_micro IS NOT OLD.coste_min_usd_micro
        OR NEW.coste_max_usd_micro IS NOT OLD.coste_max_usd_micro
        OR NEW.pdf_nuevos IS NOT OLD.pdf_nuevos OR NEW.pdf_ya_leidos IS NOT OLD.pdf_ya_leidos
        OR NEW.autorizacion_id IS NOT OLD.autorizacion_id))
  OR (OLD.cancelada_en IS NOT NULL AND (
        NEW.cancelada_en IS NOT OLD.cancelada_en OR NEW.cancelada_por IS NOT OLD.cancelada_por
        OR NEW.cancelada_via IS NOT OLD.cancelada_via))
BEGIN SELECT RAISE(ABORT, 'lo pedido, lo aprobado y lo cancelado de una lectura no se cambian'); END;

-- Una lectura terminada no vuelve a vivir ni cambia.
CREATE TRIGGER solicitud_lectura_terminada BEFORE UPDATE ON solicitud_lectura
WHEN OLD.estado IN ('hecha', 'fallida', 'caducada', 'cancelada', 'nada_que_leer')
BEGIN SELECT RAISE(ABORT, 'una lectura terminada no cambia'); END;

CREATE TRIGGER solicitud_lectura_sin_delete BEFORE DELETE ON solicitud_lectura
BEGIN SELECT RAISE(ABORT, 'una solicitud de lectura no se borra'); END;

-- La pasada es de una lectura aprobada, y nace cargando.
CREATE TRIGGER pasada_lectura_alta BEFORE INSERT ON pasada_lectura
WHEN NEW.fase IS NOT 'cargando'
  OR (SELECT aprobada_en FROM solicitud_lectura WHERE id = NEW.solicitud_id) IS NULL
BEGIN SELECT RAISE(ABORT, 'una pasada de lectura es de una lectura aprobada y nace cargando'); END;

-- Lo gastado solo sube, y una pasada terminada no cambia.
CREATE TRIGGER pasada_lectura_avanza BEFORE UPDATE ON pasada_lectura
WHEN OLD.terminada_en IS NOT NULL OR NEW.solicitud_id IS NOT OLD.solicitud_id
  OR NEW.coste_usd_micro < OLD.coste_usd_micro OR NEW.empezada_en IS NOT OLD.empezada_en
BEGIN SELECT RAISE(ABORT, 'una pasada de lectura solo avanza, y terminada no cambia'); END;

CREATE TRIGGER pasada_lectura_sin_delete BEFORE DELETE ON pasada_lectura
BEGIN SELECT RAISE(ABORT, 'una pasada de lectura no se borra'); END;

-- ----------------------------------------------------------- mensaje_correo

-- Cada llegada de un mensaje al buzon. La clave es (id inmutable de Graph,
-- carpeta): el mismo mensaje que una persona pasa de "Correo no deseado" a la
-- bandeja es otra llegada, que si se trae. internetMessageId lo pone el
-- remitente: es un dato, no la clave. recibido_en es la hora del servidor de
-- Microsoft (receivedDateTime), no la del remitente. adjuntos cuenta los que
-- no van en linea; en_linea, los que si (imagenes de la firma), que no se
-- apuntan uno a uno. Lo registra el usuario de sistema correo.
CREATE TABLE mensaje_correo (
    id                      INTEGER PRIMARY KEY,
    graph_id                TEXT NOT NULL CHECK (length(graph_id) BETWEEN 1 AND 512
                                                 AND graph_id NOT GLOB '*[^A-Za-z0-9+/=_-]*'),
    carpeta                 TEXT NOT NULL CHECK (carpeta IN ('bandeja', 'no_deseado')),
    internet_message_id_doc TEXT CHECK (internet_message_id_doc IS NULL
                                        OR length(internet_message_id_doc) BETWEEN 1 AND 998),
    recibido_en             TEXT NOT NULL CHECK (datetime(recibido_en) IS NOT NULL),
    remitente_doc           TEXT CHECK (remitente_doc IS NULL OR length(remitente_doc) <= 320),
    asunto_doc              TEXT CHECK (asunto_doc IS NULL OR length(asunto_doc) <= 200),
    adjuntos                INTEGER NOT NULL CHECK (adjuntos >= 0),
    en_linea                INTEGER NOT NULL CHECK (en_linea >= 0),
    traido_en               TEXT NOT NULL CHECK (datetime(traido_en) IS NOT NULL),
    registrado_en           TEXT NOT NULL CHECK (datetime(registrado_en) IS NOT NULL),
    registrado_por          INTEGER NOT NULL REFERENCES usuario(id),
    UNIQUE (graph_id, carpeta)
) STRICT;

CREATE INDEX mensaje_correo_recibido ON mensaje_correo (recibido_en);

CREATE TRIGGER mensaje_correo_sin_update BEFORE UPDATE ON mensaje_correo
BEGIN SELECT RAISE(ABORT, 'mensaje_correo es evidencia: no se modifica'); END;
CREATE TRIGGER mensaje_correo_sin_delete BEFORE DELETE ON mensaje_correo
BEGIN SELECT RAISE(ABORT, 'mensaje_correo es evidencia: no se borra'); END;

-- ----------------------------------------------------------- adjunto_correo

-- Cada adjunto de un mensaje y lo que se hizo con el. Solo un PDF se baja y
-- entra en el almacen (resultado 'documento', con su documento); lo demas se
-- apunta y se queda en el buzon. El mismo PDF en dos mensajes es un documento
-- y dos filas aqui, con el mismo documento_id: el documento no se puede
-- cambiar, y esto es lo que dice por donde llego cada vez.
CREATE TABLE adjunto_correo (
    id                 INTEGER PRIMARY KEY,
    mensaje_id         INTEGER NOT NULL REFERENCES mensaje_correo(id),
    graph_adjunto_id   TEXT NOT NULL CHECK (length(graph_adjunto_id) BETWEEN 1 AND 512),
    nombre_doc         TEXT CHECK (nombre_doc IS NULL OR length(nombre_doc) <= 255),
    tipo_declarado_doc TEXT CHECK (tipo_declarado_doc IS NULL OR length(tipo_declarado_doc) <= 255),
    bytes              INTEGER CHECK (bytes IS NULL OR bytes >= 0),
    sha256             TEXT CHECK (sha256 IS NULL
                                   OR (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*')),
    resultado          TEXT NOT NULL CHECK (resultado IN (
        'documento', 'no_es_pdf', 'demasiado_grande', 'xml', 'reenvio', 'no_pdf', 'enlace',
        'no_deseado', 'de_prueba', 'error')),
    documento_id       INTEGER REFERENCES documento(id),
    CHECK ((resultado = 'documento') = (documento_id IS NOT NULL)),
    CHECK (resultado <> 'documento' OR sha256 IS NOT NULL),
    UNIQUE (mensaje_id, graph_adjunto_id)
) STRICT;

CREATE INDEX adjunto_correo_documento ON adjunto_correo (documento_id)
    WHERE documento_id IS NOT NULL;

-- El documento de un adjunto es el de sus bytes.
CREATE TRIGGER adjunto_correo_su_documento BEFORE INSERT ON adjunto_correo
WHEN NEW.documento_id IS NOT NULL
 AND (SELECT sha256 FROM documento WHERE id = NEW.documento_id) IS NOT NEW.sha256
BEGIN SELECT RAISE(ABORT, 'el documento de un adjunto del correo es el de su sha256'); END;

CREATE TRIGGER adjunto_correo_sin_update BEFORE UPDATE ON adjunto_correo
BEGIN SELECT RAISE(ABORT, 'adjunto_correo es evidencia: no se modifica'); END;
CREATE TRIGGER adjunto_correo_sin_delete BEFORE DELETE ON adjunto_correo
BEGIN SELECT RAISE(ABORT, 'adjunto_correo es evidencia: no se borra'); END;

-- ----------------------------------------------------- exclusion_automatica

-- "Este documento no se lee solo: espera a una persona." Para siempre. grande:
-- la estimacion lo pone por encima del maximo por factura; rechazado_api: la
-- API no lo quiso contar; fallo: fallo por el documento en dos automaticas;
-- persona: una persona lo aparto (excluir_de_lectura_automatica), y tampoco
-- entra en lo que lee una persona desde Procesar. Las tres primeras las apunta
-- automatico con la peticion que las vio; la ultima, una persona, sin
-- peticion. Como mucho una del sistema y una de una persona por documento: la
-- persona puede apartar del todo una que la automatica ya aparto (una grande
-- que no quiere pagar, una que falla), y si no, entraria en cada lectura suya.
CREATE TABLE exclusion_automatica (
    id            INTEGER PRIMARY KEY,
    documento_id  INTEGER NOT NULL REFERENCES documento(id),
    motivo_codigo TEXT NOT NULL CHECK (motivo_codigo IN (
        'grande', 'fallo', 'rechazado_api', 'persona')),
    solicitud_id  INTEGER REFERENCES solicitud_lectura(id),
    por           INTEGER NOT NULL REFERENCES usuario(id),
    en            TEXT NOT NULL CHECK (datetime(en) IS NOT NULL),
    CHECK ((motivo_codigo = 'persona') = (solicitud_id IS NULL))
) STRICT;

CREATE UNIQUE INDEX exclusion_automatica_una_del_sistema ON exclusion_automatica (documento_id)
    WHERE motivo_codigo <> 'persona';
CREATE UNIQUE INDEX exclusion_automatica_una_de_persona ON exclusion_automatica (documento_id)
    WHERE motivo_codigo = 'persona';

CREATE TRIGGER exclusion_automatica_quien BEFORE INSERT ON exclusion_automatica
WHEN (NEW.motivo_codigo = 'persona')
     IS NOT ((SELECT es_sistema FROM usuario WHERE id = NEW.por) IS 0)
BEGIN SELECT RAISE(ABORT, 'una exclusion de persona la pone una persona; las demas, el sistema'); END;

CREATE TRIGGER exclusion_automatica_sin_update BEFORE UPDATE ON exclusion_automatica
BEGIN SELECT RAISE(ABORT, 'exclusion_automatica es de solo escritura: no se modifica'); END;
CREATE TRIGGER exclusion_automatica_sin_delete BEFORE DELETE ON exclusion_automatica
BEGIN SELECT RAISE(ABORT, 'exclusion_automatica es de solo escritura: no se borra'); END;

-- ------------------------------------------------- pausa_lectura_automatica

-- Cada pausa y cada reanudacion de la lectura automatica; manda la ultima fila.
-- persona: alguien paro una automatica (la peticion, en solicitud_id); dura
-- hasta `hasta` (las 00:00 de manana en Europe/Amsterdam, en UTC) o hasta que
-- alguien la reanude. volumen: llegaron mas de 200 correos en un dia; la pone
-- automatico y dura hasta que una persona la quite. Reanudar es de una persona.
CREATE TABLE pausa_lectura_automatica (
    id           INTEGER PRIMARY KEY,
    tipo         TEXT NOT NULL CHECK (tipo IN ('pausa', 'reanuda')),
    motivo       TEXT CHECK (motivo IS NULL OR motivo IN ('persona', 'volumen')),
    solicitud_id INTEGER REFERENCES solicitud_lectura(id),
    por          INTEGER NOT NULL REFERENCES usuario(id),
    en           TEXT NOT NULL CHECK (datetime(en) IS NOT NULL),
    hasta        TEXT CHECK (hasta IS NULL OR datetime(hasta) IS NOT NULL),
    CHECK ((tipo = 'pausa') = (motivo IS NOT NULL)),
    CHECK ((motivo IS 'persona') = (hasta IS NOT NULL)),
    CHECK (hasta IS NULL OR datetime(hasta) > datetime(en)),
    CHECK (solicitud_id IS NULL OR motivo IS 'persona')
) STRICT;

CREATE TRIGGER pausa_lectura_automatica_quien BEFORE INSERT ON pausa_lectura_automatica
WHEN (NEW.motivo IS 'volumen')
     IS NOT ((SELECT es_sistema FROM usuario WHERE id = NEW.por) IS 1)
BEGIN SELECT RAISE(ABORT, 'la pausa por volumen la pone el sistema; parar y reanudar, una persona'); END;

CREATE TRIGGER pausa_lectura_automatica_sin_update BEFORE UPDATE ON pausa_lectura_automatica
BEGIN SELECT RAISE(ABORT, 'pausa_lectura_automatica es de solo escritura: no se modifica'); END;
CREATE TRIGGER pausa_lectura_automatica_sin_delete BEFORE DELETE ON pausa_lectura_automatica
BEGIN SELECT RAISE(ABORT, 'pausa_lectura_automatica es de solo escritura: no se borra'); END;

-- ---------------------------------------------------------- correo_atendido

-- "Una persona ya miro este correo que el programa no podia leer": sale de la
-- lista de lo que espera a una persona. Una vez por mensaje.
CREATE TABLE correo_atendido (
    id         INTEGER PRIMARY KEY,
    mensaje_id INTEGER NOT NULL UNIQUE REFERENCES mensaje_correo(id),
    por        INTEGER NOT NULL REFERENCES usuario(id),
    en         TEXT NOT NULL CHECK (datetime(en) IS NOT NULL),
    nota       TEXT CHECK (nota IS NULL OR length(nota) <= 500)
) STRICT;

CREATE TRIGGER correo_atendido_personas_alta BEFORE INSERT ON correo_atendido
WHEN (SELECT es_sistema FROM usuario WHERE id = NEW.por) IS NOT 0
BEGIN SELECT RAISE(ABORT, 'un correo lo da por atendido una persona'); END;

CREATE TRIGGER correo_atendido_sin_update BEFORE UPDATE ON correo_atendido
BEGIN SELECT RAISE(ABORT, 'correo_atendido es de solo escritura: no se modifica'); END;
CREATE TRIGGER correo_atendido_sin_delete BEFORE DELETE ON correo_atendido
BEGIN SELECT RAISE(ABORT, 'correo_atendido es de solo escritura: no se borra'); END;

-- ------------------------------------------------------------- ronda_correo

-- Las rondas del correo que trajeron algo o cambiaron de error (no las 288
-- vacias de cada dia). Los codigos de error son la lista cerrada del correo,
-- los mismos de su estado.json, de `correo registrar --fallo` y de la API.
CREATE TABLE ronda_correo (
    id                INTEGER PRIMARY KEY,
    empezada_en       TEXT NOT NULL CHECK (datetime(empezada_en) IS NOT NULL),
    terminada_en      TEXT CHECK (terminada_en IS NULL OR datetime(terminada_en) IS NOT NULL),
    resultado         TEXT NOT NULL CHECK (resultado IN ('bien', 'fallo')),
    error_codigo      TEXT CHECK (error_codigo IS NULL OR error_codigo IN (
        'sin_configurar', 'credencial', 'reloj', 'permiso', 'alcance', 'control_no_existe',
        'sin_conexion', 'limitado', 'aislamiento', 'salida', 'disco', 'interno')),
    mensajes          INTEGER NOT NULL DEFAULT 0 CHECK (mensajes >= 0),
    documentos_nuevos INTEGER NOT NULL DEFAULT 0 CHECK (documentos_nuevos >= 0),
    registrada_en     TEXT NOT NULL CHECK (datetime(registrada_en) IS NOT NULL),
    CHECK ((resultado = 'fallo') = (error_codigo IS NOT NULL))
) STRICT;

CREATE TRIGGER ronda_correo_sin_update BEFORE UPDATE ON ronda_correo
BEGIN SELECT RAISE(ABORT, 'ronda_correo es evidencia: no se modifica'); END;
CREATE TRIGGER ronda_correo_sin_delete BEFORE DELETE ON ronda_correo
BEGIN SELECT RAISE(ABORT, 'ronda_correo es evidencia: no se borra'); END;

-- ------------------------------------------------------------ estado_correo

-- CACHE: una fila, copia del estado.json que deja el correo (validado por
-- `correo registrar`). Sin fila, el correo no esta configurado. hoy_json es
-- {fecha, mensajes, pdf, bytes} del dia de la empresa.
CREATE TABLE estado_correo (
    id                    INTEGER PRIMARY KEY CHECK (id = 1),
    buzon                 TEXT CHECK (buzon IS NULL OR length(buzon) BETWEEN 3 AND 320),
    ultima_consulta       TEXT CHECK (ultima_consulta IS NULL OR datetime(ultima_consulta) IS NOT NULL),
    ultima_buena          TEXT CHECK (ultima_buena IS NULL OR datetime(ultima_buena) IS NOT NULL),
    error_codigo          TEXT CHECK (error_codigo IS NULL OR error_codigo IN (
        'sin_configurar', 'credencial', 'reloj', 'permiso', 'alcance', 'control_no_existe',
        'sin_conexion', 'limitado', 'aislamiento', 'salida', 'disco', 'interno')),
    error_desde           TEXT CHECK (error_desde IS NULL OR datetime(error_desde) IS NOT NULL),
    alcance_comprobado_en TEXT CHECK (alcance_comprobado_en IS NULL
                                      OR datetime(alcance_comprobado_en) IS NOT NULL),
    alcance_bien          INTEGER CHECK (alcance_bien IS NULL OR alcance_bien IN (0, 1)),
    credencial_caduca_en  TEXT CHECK (credencial_caduca_en IS NULL
                                      OR datetime(credencial_caduca_en) IS NOT NULL),
    delta_reiniciado_en   TEXT CHECK (delta_reiniciado_en IS NULL
                                      OR datetime(delta_reiniciado_en) IS NOT NULL),
    retenido_hasta        TEXT CHECK (retenido_hasta IS NULL OR datetime(retenido_hasta) IS NOT NULL),
    hoy_json              TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(hoy_json)),
    aviso_volumen         INTEGER NOT NULL DEFAULT 0 CHECK (aviso_volumen IN (0, 1)),
    actualizado_en        TEXT NOT NULL CHECK (datetime(actualizado_en) IS NOT NULL),
    CHECK ((error_codigo IS NULL) = (error_desde IS NULL)),
    CHECK ((alcance_comprobado_en IS NULL) = (alcance_bien IS NULL))
) STRICT;

-- ------------------------------------------------------------- estado_ciclo

-- CACHE: una fila, el latido del ciclo automatico (`bms-agent ciclo latido`,
-- al principio de cada ciclo). Lo que la app dice de el ("el ciclo automatico
-- no corre desde...") y el espacio libre del disco de verdad, que mide el
-- ciclo desde Windows (en Docker, el contenedor solo veria el disco de WSL2).
CREATE TABLE estado_ciclo (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    visto_en          TEXT NOT NULL CHECK (datetime(visto_en) IS NOT NULL),
    variante          TEXT CHECK (variante IS NULL OR variante IN ('nativa', 'docker')),
    pausado           INTEGER NOT NULL DEFAULT 0 CHECK (pausado IN (0, 1)),
    pausado_desde     TEXT CHECK (pausado_desde IS NULL OR datetime(pausado_desde) IS NOT NULL),
    disco_libre_bytes INTEGER CHECK (disco_libre_bytes IS NULL OR disco_libre_bytes >= 0),
    actualizado_en    TEXT NOT NULL CHECK (datetime(actualizado_en) IS NOT NULL),
    CHECK (pausado = 1 OR pausado_desde IS NULL)
) STRICT;
