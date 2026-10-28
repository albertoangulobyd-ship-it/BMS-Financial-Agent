-- Migracion 0018 (paso 17): la lectura de los PDF pedida desde la app.
--
-- Un fichero aplicado no se edita nunca (ver 0001). Lo que haga falta
-- despues va en 0019, 0020...
--
-- La app no tiene red ni lanza programas: no puede leer un PDF. Lo que puede
-- es pedir una lectura, ver lo que costaria, dar el si (o el no) y seguir el
-- progreso. Quien lee sigue siendo el lector (leer-facturas.bat), con el orden
-- de siempre: enciende la salida, comprueba el aislamiento, cuenta, espera el
-- si, lee y apaga la salida (lectura.py, docs/instalacion-nativa.md).
--
-- solicitud_lectura es la peticion y su vida: pedida (desde la app, o la crea
-- el lector si alguien lo abre sin pedir nada), comprobando, contando,
-- esperando_aprobacion (con la estimacion, su huella y hasta cuando vale),
-- aprobada (quien dio el si, por donde, con que tope y para que huella) y
-- leyendo; y al final hecha, fallida, caducada, cancelada o nada_que_leer.
-- Viva solo puede haber una. Cada cambio de estado deja su evento en la
-- auditoria (lectura.py), y lo aprobado no se puede cambiar despues.
--
-- pasada_lectura es el progreso de la lectura de una peticion: la fase, las
-- cuentas, lo gastado, el documento de ahora y lo que fue de cada uno. Es lo
-- que la app consulta cada 2 s mientras Procesar esta abierto. No se audita
-- documento a documento (cada extraccion ya deja lo suyo); si cada cambio de
-- la peticion.
--
-- Clases de tabla (spec.md §4): las dos son EVIDENCIA de lo que se pidio, se
-- aprobo y se gasto. No se borran.

CREATE TABLE solicitud_lectura (
    id                  INTEGER PRIMARY KEY,
    origen              TEXT NOT NULL CHECK (origen IN ('app', 'lector')),
    pedida_por          INTEGER REFERENCES usuario(id),
    pedida_en           TEXT NOT NULL CHECK (datetime(pedida_en) IS NOT NULL),
    estado              TEXT NOT NULL CHECK (estado IN (
        'pedida', 'comprobando', 'contando', 'esperando_aprobacion', 'aprobada', 'leyendo',
        'hecha', 'fallida', 'caducada', 'cancelada', 'nada_que_leer')),
    motivo              TEXT,
    motivo_codigo       TEXT CHECK (motivo_codigo IS NULL OR motivo_codigo IN (
        'buzon_vacio', 'clave', 'salida', 'aislamiento', 'contar', 'sin_tarifa', 'estimacion',
        'lectura', 'interrumpida', 'abandonada', 'ya_leidas')),
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
    aprobada_via        TEXT CHECK (aprobada_via IS NULL OR aprobada_via IN ('app', 'ventana')),
    tope_usd_micro      INTEGER CHECK (tope_usd_micro IS NULL OR tope_usd_micro > 0),
    huella_aprobada     TEXT CHECK (huella_aprobada IS NULL OR length(huella_aprobada) = 64),
    cancelada_por       INTEGER REFERENCES usuario(id),
    cancelada_en        TEXT CHECK (cancelada_en IS NULL OR datetime(cancelada_en) IS NOT NULL),
    cancelada_via       TEXT CHECK (cancelada_via IS NULL OR cancelada_via IN ('app', 'ventana')),
    terminada_en        TEXT CHECK (terminada_en IS NULL OR datetime(terminada_en) IS NOT NULL),
    actualizada_en      TEXT NOT NULL CHECK (datetime(actualizada_en) IS NOT NULL),
    -- La de la app la pide una persona; la del lector, nadie (quien abrio la ventana).
    CHECK ((origen = 'app') = (pedida_por IS NOT NULL)),
    CHECK (coste_max_usd_micro IS NULL OR coste_max_usd_micro >= coste_min_usd_micro),
    -- Esperar el si exige la estimacion entera y un plazo.
    CHECK (estado <> 'esperando_aprobacion' OR (
        huella_estimacion IS NOT NULL AND coste_max_usd_micro IS NOT NULL
        AND pdf_nuevos > 0 AND caduca_en IS NOT NULL)),
    -- El si: cuando, por donde, con que tope y para que huella, todo junto. Desde la app
    -- lo da una persona; desde la ventana del lector, quien la tiene delante.
    CHECK ((aprobada_en IS NULL) = (aprobada_via IS NULL)
           AND (aprobada_en IS NULL) = (tope_usd_micro IS NULL)
           AND (aprobada_en IS NULL) = (huella_aprobada IS NULL)),
    CHECK ((aprobada_via = 'app') = (aprobada_por IS NOT NULL)),
    -- El tope no pasa del extremo alto de lo que se vio.
    CHECK (tope_usd_micro IS NULL OR tope_usd_micro <= coste_max_usd_micro),
    CHECK (estado NOT IN ('aprobada', 'leyendo', 'hecha') OR aprobada_en IS NOT NULL),
    CHECK ((cancelada_en IS NULL) = (cancelada_via IS NULL)),
    CHECK ((cancelada_via = 'app') = (cancelada_por IS NOT NULL)),
    CHECK (estado <> 'cancelada' OR cancelada_en IS NOT NULL),
    CHECK ((terminada_en IS NULL) = (estado IN (
        'pedida', 'comprobando', 'contando', 'esperando_aprobacion', 'aprobada', 'leyendo')))
) STRICT;

-- Viva, una sola: dos lectores no leen a la vez ni gastan dos veces.
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

-- Lo que se pidio y lo que se aprobo no cambian: el si vale para la estimacion que se vio.
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
        OR NEW.pdf_nuevos IS NOT OLD.pdf_nuevos OR NEW.pdf_ya_leidos IS NOT OLD.pdf_ya_leidos))
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

CREATE TABLE pasada_lectura (
    id               INTEGER PRIMARY KEY,
    solicitud_id     INTEGER NOT NULL UNIQUE REFERENCES solicitud_lectura(id),
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
