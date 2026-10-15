-- Migracion 0002 (paso 2 de la V1): nucleo tipado, una sola via de escritura,
-- procedencia de cada campo y notas.
--
-- Un fichero aplicado no se edita nunca (ver 0001). Lo que haga falta
-- despues va en 0003, 0004...
--
-- Clases de tabla (spec.md §4):
--   CONTROLADAS (TRACKED): maestros, tarifas y facturas con sus hijas. Llevan
--     rev. Solo las escribe campos.py, y la base lo exige con dos disparadores
--     por tabla, generados columna a columna:
--       <tabla>_guarda_insert: la fila entra con rev 0, y cada columna con
--         valor tiene su cambio_campo (rev 0, mismo valor) en el evento en curso;
--       <tabla>_guarda_update: rev sube de uno en uno, hay al menos un
--         cambio_campo de la fila con la rev nueva en el evento en curso, y
--         cada columna que cambia tiene el suyo, con el valor anterior y el
--         nuevo exactos.
--     <tabla>_sin_delete: una fila no se borra; se retira (retirada_en) o se
--     desactiva (activo = 0).
--   procedencia_campo: una fila por campo, mutable, pero solo dentro de un
--     evento que nombra ese campo (por un cambio_campo o en datos.campos).
--   SOLO ESCRITURA: nota.
--
-- "Evento en curso" es el ultimo evento: campos.py registra primero el evento
-- con todos sus cambio_campo y despues escribe las filas. Un UPDATE suelto,
-- sin su evento, aborta; uno con un evento viejo, tambien.
--
-- Dinero y cantidades son enteros con el sufijo de su escala (_cent, _mil,
-- _e4, _pb); solo almacen/unidades.py convierte. Ninguna columna REAL.
--
-- orden_compra_id no lleva clave foranea: la tabla orden_compra llega en la
-- 0006, y SQLite no deja declarar una clave foranea hacia una tabla que no
-- existe (lo mismo que factura_id en la 0001).

-- ------------------------------------------------------------------ maestros

CREATE TABLE proveedor (
    id                    INTEGER PRIMARY KEY,
    nombre                TEXT NOT NULL CHECK (length(trim(nombre)) > 0),
    tipo                  TEXT CHECK (tipo IS NULL OR tipo IN ('zzp', 'empresa')),
    kvk                   TEXT,
    btw_id                TEXT,
    regimen_iva           TEXT CHECK (regimen_iva IS NULL OR regimen_iva IN (
        'estandar', 'autoliquidacion', 'kor', 'exento', 'tipo_cero', 'desconocido')),
    plazo_pago_dias       INTEGER CHECK (plazo_pago_dias IS NULL OR plazo_pago_dias >= 0),
    direccion             TEXT,
    email_facturacion     TEXT,
    telefono_verificacion TEXT,
    activo                INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    exact_id              TEXT UNIQUE,
    trnsprnt_id           TEXT UNIQUE,
    rev                   INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0)
) STRICT;

CREATE INDEX proveedor_btw ON proveedor (btw_id);
CREATE INDEX proveedor_kvk ON proveedor (kvk);

CREATE TABLE cliente (
    id                      INTEGER PRIMARY KEY,
    nombre                  TEXT NOT NULL CHECK (length(trim(nombre)) > 0),
    kvk                     TEXT,
    btw_id                  TEXT,
    plazo_pago_dias         INTEGER CHECK (plazo_pago_dias IS NULL OR plazo_pago_dias >= 0),
    requiere_po             INTEGER CHECK (requiere_po IS NULL OR requiere_po IN (0, 1)),
    tratamiento_iva_defecto TEXT CHECK (tratamiento_iva_defecto IS NULL OR tratamiento_iva_defecto IN (
        'estandar', 'autoliquidacion', 'kor', 'exento', 'tipo_cero', 'desconocido')),
    verlegd_elegible        INTEGER NOT NULL DEFAULT 0 CHECK (verlegd_elegible IN (0, 1)),
    activo                  INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    exact_id                TEXT UNIQUE,
    trnsprnt_id             TEXT UNIQUE,
    rev                     INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0)
) STRICT;

CREATE INDEX cliente_btw ON cliente (btw_id);
CREATE INDEX cliente_kvk ON cliente (kvk);

-- Una persona de contacto de un proveedor o de un cliente, nunca de los dos.
CREATE TABLE contacto (
    id           INTEGER PRIMARY KEY,
    proveedor_id INTEGER REFERENCES proveedor(id),
    cliente_id   INTEGER REFERENCES cliente(id),
    nombre       TEXT NOT NULL CHECK (length(trim(nombre)) > 0),
    email        TEXT,
    telefono     TEXT,
    funcion      TEXT,
    activo       INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    rev          INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0),
    CHECK ((proveedor_id IS NULL) <> (cliente_id IS NULL))
) STRICT;

-- Un Objeto (obra, locatie, proyecto). requiere_po NULL hereda el del cliente.
CREATE TABLE objeto (
    id           INTEGER PRIMARY KEY,
    codigo       TEXT NOT NULL UNIQUE CHECK (length(trim(codigo)) > 0),
    nombre       TEXT NOT NULL CHECK (length(trim(nombre)) > 0),
    cliente_id   INTEGER REFERENCES cliente(id),
    requiere_po  INTEGER CHECK (requiere_po IS NULL OR requiere_po IN (0, 1)),
    activo_desde TEXT CHECK (activo_desde IS NULL OR date(activo_desde) IS activo_desde),
    activo_hasta TEXT CHECK (activo_hasta IS NULL OR date(activo_hasta) IS activo_hasta),
    trnsprnt_id  TEXT UNIQUE,
    rev          INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0),
    CHECK (activo_desde IS NULL OR activo_hasta IS NULL OR activo_desde <= activo_hasta)
) STRICT;

CREATE TABLE recurso (
    id           INTEGER PRIMARY KEY,
    nombre       TEXT NOT NULL CHECK (length(trim(nombre)) > 0),
    tipo         TEXT CHECK (tipo IS NULL OR tipo IN ('empleado', 'zzp', 'personal_proveedor')),
    proveedor_id INTEGER REFERENCES proveedor(id),
    trnsprnt_id  TEXT UNIQUE,
    activo       INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    rev          INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0)
) STRICT;

-- Otro nombre con el que se reconoce una fila de un maestro. La busqueda es
-- exacta sobre alias_norm (identidad.normalizar_nombre) y solo con alias
-- confirmados. Un IBAN nunca es un alias: el CHECK rechaza lo que tiene la
-- forma de uno (dos letras, dos digitos y letras o digitos, de 15 a 34).
CREATE TABLE alias (
    id         INTEGER PRIMARY KEY,
    tabla      TEXT NOT NULL CHECK (tabla IN ('proveedor', 'cliente', 'objeto', 'recurso')),
    alias      TEXT NOT NULL CHECK (length(trim(alias)) > 0),
    alias_norm TEXT NOT NULL CHECK (length(alias_norm) > 0),
    fila_id    INTEGER NOT NULL,
    origen     TEXT NOT NULL CHECK (origen IN ('maestro', 'manual', 'config')),
    confirmado INTEGER NOT NULL DEFAULT 0 CHECK (confirmado IN (0, 1)),
    activo     INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    rev        INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0),
    UNIQUE (tabla, alias_norm),
    CHECK (NOT (length(replace(alias_norm, ' ', '')) BETWEEN 15 AND 34
                AND upper(replace(alias_norm, ' ', '')) GLOB '[A-Z][A-Z][0-9][0-9]*'
                AND upper(replace(alias_norm, ' ', '')) NOT GLOB '*[^A-Z0-9]*'))
) STRICT;

-- La fila a la que apunta un alias tiene que existir en su tabla.
CREATE TRIGGER alias_destino_insert BEFORE INSERT ON alias
WHEN NOT CASE NEW.tabla
    WHEN 'proveedor' THEN EXISTS (SELECT 1 FROM proveedor WHERE id = NEW.fila_id)
    WHEN 'cliente'   THEN EXISTS (SELECT 1 FROM cliente   WHERE id = NEW.fila_id)
    WHEN 'objeto'    THEN EXISTS (SELECT 1 FROM objeto    WHERE id = NEW.fila_id)
    WHEN 'recurso'   THEN EXISTS (SELECT 1 FROM recurso   WHERE id = NEW.fila_id)
    ELSE 0 END
BEGIN SELECT RAISE(ABORT, 'el alias apunta a una fila que no existe'); END;

CREATE TRIGGER alias_destino_update BEFORE UPDATE OF tabla, fila_id ON alias
WHEN NOT CASE NEW.tabla
    WHEN 'proveedor' THEN EXISTS (SELECT 1 FROM proveedor WHERE id = NEW.fila_id)
    WHEN 'cliente'   THEN EXISTS (SELECT 1 FROM cliente   WHERE id = NEW.fila_id)
    WHEN 'objeto'    THEN EXISTS (SELECT 1 FROM objeto    WHERE id = NEW.fila_id)
    WHEN 'recurso'   THEN EXISTS (SELECT 1 FROM recurso   WHERE id = NEW.fila_id)
    ELSE 0 END
BEGIN SELECT RAISE(ABORT, 'el alias apunta a una fila que no existe'); END;

-- Una tarifa pactada, de compra o de venta, de lo mas concreto (recurso +
-- Objeto + tipo de turno) a lo mas general (la parte). Llega aqui y no en la
-- 0004 porque el paso 2 siembra las tarifas de venta de config/tarifas.yaml.
CREATE TABLE tarifa_acordada (
    id              INTEGER PRIMARY KEY,
    sentido         TEXT NOT NULL CHECK (sentido IN ('compra', 'venta')),
    proveedor_id    INTEGER REFERENCES proveedor(id),
    recurso_id      INTEGER REFERENCES recurso(id),
    cliente_id      INTEGER REFERENCES cliente(id),
    objeto_id       INTEGER REFERENCES objeto(id),
    orden_compra_id INTEGER,
    tipo_servicio   TEXT,
    tipo_turno      TEXT,
    unidad          TEXT,
    tarifa_e4       INTEGER NOT NULL,
    vigente_desde   TEXT CHECK (vigente_desde IS NULL OR date(vigente_desde) IS vigente_desde),
    vigente_hasta   TEXT CHECK (vigente_hasta IS NULL OR date(vigente_hasta) IS vigente_hasta),
    fuente          TEXT NOT NULL CHECK (fuente IN (
        'config', 'maestro', 'exact', 'trnsprnt', 'manual', 'documento')),
    documento_id    INTEGER REFERENCES documento(id),
    rev             INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0),
    CHECK (vigente_desde IS NULL OR vigente_hasta IS NULL OR vigente_desde <= vigente_hasta),
    CHECK (sentido = 'compra' OR proveedor_id IS NULL),
    CHECK (sentido = 'venta' OR cliente_id IS NULL)
) STRICT;

-- ------------------------------------------------------------------ facturas

-- Una tabla para las dos direcciones. Lo que acaba en _doc es texto de un
-- tercero tal como lo imprime: se ensena con textContent y nunca se
-- interpreta. iban_doc es lo que dice el documento; nunca se usa para pagar.
-- No hay clave unica de (proveedor, numero) a proposito: B2 tiene que poder
-- ver un duplicado. Una factura fusionada en otra conserva su fila con
-- fusionada_en_id y queda fuera de todos los totales.
CREATE TABLE factura (
    id                         INTEGER PRIMARY KEY,
    sentido                    TEXT NOT NULL CHECK (sentido IN ('entrante', 'saliente')),
    tipo                       TEXT NOT NULL CHECK (tipo IN ('factura', 'nota_credito')),
    origen                     TEXT NOT NULL CHECK (origen IN ('extraccion', 'exact', 'trnsprnt', 'manual')),
    documento_id               INTEGER REFERENCES documento(id),
    extraccion_vigente_id      INTEGER REFERENCES extraccion(id),
    fuente_externa             TEXT,
    id_externo                 TEXT,
    numero                     TEXT,
    numero_norm                TEXT,
    proveedor_id               INTEGER REFERENCES proveedor(id),
    cliente_id                 INTEGER REFERENCES cliente(id),
    contacto_id                INTEGER REFERENCES contacto(id),
    emisor_nombre_doc          TEXT,
    emisor_direccion_doc       TEXT,
    emisor_kvk_doc             TEXT,
    emisor_btw_doc             TEXT,
    receptor_nombre_doc        TEXT,
    receptor_btw_doc           TEXT,
    contacto_nombre_doc        TEXT,
    fecha_factura              TEXT CHECK (fecha_factura IS NULL OR date(fecha_factura) IS fecha_factura),
    fecha_recepcion            TEXT CHECK (fecha_recepcion IS NULL OR date(fecha_recepcion) IS fecha_recepcion),
    fecha_envio                TEXT CHECK (fecha_envio IS NULL OR date(fecha_envio) IS fecha_envio),
    periodo_inicio             TEXT CHECK (periodo_inicio IS NULL OR date(periodo_inicio) IS periodo_inicio),
    periodo_fin                TEXT CHECK (periodo_fin IS NULL OR date(periodo_fin) IS periodo_fin),
    fecha_vencimiento          TEXT CHECK (fecha_vencimiento IS NULL OR date(fecha_vencimiento) IS fecha_vencimiento),
    plazo_pago_dias            INTEGER CHECK (plazo_pago_dias IS NULL OR plazo_pago_dias >= 0),
    condiciones_pago_doc       TEXT,
    base_cent                  INTEGER,
    iva_cent                   INTEGER,
    total_cent                 INTEGER,
    tipo_iva_pb                INTEGER CHECK (tipo_iva_pb IS NULL OR tipo_iva_pb BETWEEN 0 AND 10000),
    tratamiento_iva            TEXT CHECK (tratamiento_iva IS NULL OR tratamiento_iva IN (
        'estandar', 'autoliquidacion', 'kor', 'exento', 'tipo_cero', 'desconocido')),
    kor_mencionada             INTEGER CHECK (kor_mencionada IS NULL OR kor_mencionada IN (0, 1)),
    autoliquidacion_mencionada INTEGER CHECK (autoliquidacion_mencionada IS NULL OR autoliquidacion_mencionada IN (0, 1)),
    referencia_pago            TEXT,
    iban_doc                   TEXT,
    moneda_doc                 TEXT,
    notas_doc                  TEXT,
    anulada                    INTEGER NOT NULL DEFAULT 0 CHECK (anulada IN (0, 1)),
    fusionada_en_id            INTEGER REFERENCES factura(id),
    rev                        INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0),
    CHECK (sentido = 'entrante' OR proveedor_id IS NULL),
    CHECK (sentido = 'saliente' OR cliente_id IS NULL),
    CHECK (sentido = 'entrante' OR fecha_recepcion IS NULL),
    CHECK (sentido = 'saliente' OR fecha_envio IS NULL),
    CHECK (origen <> 'extraccion' OR documento_id IS NOT NULL),
    CHECK (extraccion_vigente_id IS NULL OR origen = 'extraccion'),
    CHECK ((fuente_externa IS NULL) = (id_externo IS NULL)),
    CHECK (fusionada_en_id IS NULL OR fusionada_en_id <> id),
    CHECK (periodo_inicio IS NULL OR periodo_fin IS NULL OR periodo_inicio <= periodo_fin)
) STRICT;

CREATE UNIQUE INDEX factura_externa ON factura (fuente_externa, id_externo)
    WHERE id_externo IS NOT NULL;
CREATE UNIQUE INDEX factura_documento ON factura (documento_id) WHERE origen = 'extraccion';
CREATE INDEX factura_proveedor ON factura (proveedor_id);
CREATE INDEX factura_cliente ON factura (cliente_id);
CREATE INDEX factura_numero ON factura (numero_norm);

-- La extraccion vigente es una extraccion del propio documento de la factura.
CREATE TRIGGER factura_extraccion_del_documento BEFORE INSERT ON factura
WHEN NEW.extraccion_vigente_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM extraccion WHERE id = NEW.extraccion_vigente_id AND documento_id = NEW.documento_id)
BEGIN SELECT RAISE(ABORT, 'la extraccion vigente no es de este documento'); END;

CREATE TRIGGER factura_extraccion_del_documento_update BEFORE UPDATE OF extraccion_vigente_id, documento_id ON factura
WHEN NEW.extraccion_vigente_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM extraccion WHERE id = NEW.extraccion_vigente_id AND documento_id = NEW.documento_id)
BEGIN SELECT RAISE(ABORT, 'la extraccion vigente no es de este documento'); END;

-- Lo que dice el papel, linea a linea; las reglas de aritmetica leen esto.
-- orden es la posicion en la extraccion que la creo (1, 2, 3...).
CREATE TABLE factura_linea (
    id              INTEGER PRIMARY KEY,
    factura_id      INTEGER NOT NULL REFERENCES factura(id),
    orden           INTEGER NOT NULL CHECK (orden >= 1),
    huella_linea    TEXT CHECK (huella_linea IS NULL OR length(huella_linea) = 64),
    descripcion_doc TEXT,
    objeto_doc      TEXT,
    recurso_doc     TEXT,
    unidad_doc      TEXT,
    semana_doc      INTEGER,
    tipo_turno_doc  TEXT,
    fecha_inicio    TEXT CHECK (fecha_inicio IS NULL OR date(fecha_inicio) IS fecha_inicio),
    fecha_fin       TEXT CHECK (fecha_fin IS NULL OR date(fecha_fin) IS fecha_fin),
    fecha_trabajo   TEXT CHECK (fecha_trabajo IS NULL OR date(fecha_trabajo) IS fecha_trabajo),
    semana_iso      TEXT CHECK (semana_iso IS NULL OR semana_iso GLOB '[0-9][0-9][0-9][0-9]-W[0-5][0-9]'),
    unidad          TEXT,
    cantidad_mil    INTEGER,
    tarifa_e4       INTEGER,
    importe_cent    INTEGER,
    tipo_iva_pb     INTEGER CHECK (tipo_iva_pb IS NULL OR tipo_iva_pb BETWEEN 0 AND 10000),
    tipo_servicio   TEXT,
    retirada_en     TEXT CHECK (retirada_en IS NULL OR datetime(retirada_en) IS NOT NULL),
    rev             INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0),
    UNIQUE (factura_id, orden)
) STRICT;

-- La "Invoice Line / Allocation" de la lista de funciones: todo total lee
-- de aqui. Cada linea tiene una imputacion por defecto; dividir una linea es
-- retirar su imputacion y crear otras.
CREATE TABLE factura_imputacion (
    id              INTEGER PRIMARY KEY,
    factura_id      INTEGER NOT NULL REFERENCES factura(id),
    linea_id        INTEGER REFERENCES factura_linea(id),
    objeto_id       INTEGER REFERENCES objeto(id),
    recurso_id      INTEGER REFERENCES recurso(id),
    orden_compra_id INTEGER,
    descripcion     TEXT,
    fecha_inicio    TEXT CHECK (fecha_inicio IS NULL OR date(fecha_inicio) IS fecha_inicio),
    fecha_fin       TEXT CHECK (fecha_fin IS NULL OR date(fecha_fin) IS fecha_fin),
    semana_iso      TEXT CHECK (semana_iso IS NULL OR semana_iso GLOB '[0-9][0-9][0-9][0-9]-W[0-5][0-9]'),
    horas_mil       INTEGER,
    tarifa_e4       INTEGER,
    importe_cent    INTEGER,
    tipo_servicio   TEXT,
    tipo_turno      TEXT,
    facturable      INTEGER CHECK (facturable IS NULL OR facturable IN (0, 1)),
    retirada_en     TEXT CHECK (retirada_en IS NULL OR datetime(retirada_en) IS NOT NULL),
    rev             INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0)
) STRICT;

CREATE INDEX factura_imputacion_factura ON factura_imputacion (factura_id);
CREATE INDEX factura_imputacion_linea ON factura_imputacion (linea_id);
CREATE INDEX factura_imputacion_objeto ON factura_imputacion (objeto_id);

CREATE TRIGGER factura_imputacion_linea_insert BEFORE INSERT ON factura_imputacion
WHEN NEW.linea_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM factura_linea WHERE id = NEW.linea_id AND factura_id = NEW.factura_id)
BEGIN SELECT RAISE(ABORT, 'la linea de la imputacion es de otra factura'); END;

CREATE TRIGGER factura_imputacion_linea_update BEFORE UPDATE OF linea_id, factura_id ON factura_imputacion
WHEN NEW.linea_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM factura_linea WHERE id = NEW.linea_id AND factura_id = NEW.factura_id)
BEGIN SELECT RAISE(ABORT, 'la linea de la imputacion es de otra factura'); END;

-- El desglose de IVA por tipo. Una extraccion v1 no lo pide (solo el tipo de
-- la cabecera, factura.tipo_iva_pb): sus facturas no tienen filas aqui.
CREATE TABLE factura_iva (
    id                       INTEGER PRIMARY KEY,
    factura_id               INTEGER NOT NULL REFERENCES factura(id),
    tipo_iva_pb              INTEGER CHECK (tipo_iva_pb IS NULL OR tipo_iva_pb BETWEEN 0 AND 10000),
    tratamiento              TEXT CHECK (tratamiento IS NULL OR tratamiento IN (
        'estandar', 'autoliquidacion', 'kor', 'exento', 'tipo_cero', 'desconocido')),
    base_cent                INTEGER,
    cuota_cent               INTEGER,
    cuota_autoliquidada_cent INTEGER,
    deducible                INTEGER CHECK (deducible IS NULL OR deducible IN (0, 1)),
    rubrica                  TEXT,
    retirada_en              TEXT CHECK (retirada_en IS NULL OR datetime(retirada_en) IS NOT NULL),
    rev                      INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0)
) STRICT;

CREATE INDEX factura_iva_factura ON factura_iva (factura_id);

-- Cada referencia impresa con su etiqueta literal. Que una es una PO lo
-- decide el codigo (clase), no el modelo.
CREATE TABLE factura_referencia (
    id              INTEGER PRIMARY KEY,
    factura_id      INTEGER NOT NULL REFERENCES factura(id),
    linea_id        INTEGER REFERENCES factura_linea(id),
    etiqueta_doc    TEXT,
    valor_doc       TEXT NOT NULL,
    valor_norm      TEXT,
    clase           TEXT NOT NULL CHECK (clase IN ('po', 'orden', 'proyecto', 'ref_cliente', 'otra')),
    orden_compra_id INTEGER,
    retirada_en     TEXT CHECK (retirada_en IS NULL OR datetime(retirada_en) IS NOT NULL),
    rev             INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0)
) STRICT;

CREATE INDEX factura_referencia_factura ON factura_referencia (factura_id);
CREATE INDEX factura_referencia_valor ON factura_referencia (valor_norm);

CREATE TRIGGER factura_referencia_linea_insert BEFORE INSERT ON factura_referencia
WHEN NEW.linea_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM factura_linea WHERE id = NEW.linea_id AND factura_id = NEW.factura_id)
BEGIN SELECT RAISE(ABORT, 'la linea de la referencia es de otra factura'); END;

CREATE TRIGGER factura_referencia_linea_update BEFORE UPDATE OF linea_id, factura_id ON factura_referencia
WHEN NEW.linea_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM factura_linea WHERE id = NEW.linea_id AND factura_id = NEW.factura_id)
BEGIN SELECT RAISE(ABORT, 'la linea de la referencia es de otra factura'); END;

-- Una factura que acredita, anula, corrige o sustituye a otra. Solo una
-- relacion confirmada mueve saldos, IVA o B4; lo que propone la extraccion
-- es siempre una propuesta.
CREATE TABLE factura_relacion (
    id            INTEGER PRIMARY KEY,
    origen_id     INTEGER NOT NULL REFERENCES factura(id),
    destino_id    INTEGER NOT NULL REFERENCES factura(id),
    tipo          TEXT NOT NULL CHECK (tipo IN ('acredita', 'anula', 'corrige', 'sustituye', 'relacionada')),
    importe_cent  INTEGER,
    estado        TEXT NOT NULL CHECK (estado IN ('propuesta', 'confirmada', 'rechazada')),
    fuente        TEXT NOT NULL CHECK (fuente IN ('extraccion', 'exact', 'manual')),
    evidencia_doc TEXT,
    retirada_en   TEXT CHECK (retirada_en IS NULL OR datetime(retirada_en) IS NOT NULL),
    rev           INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0),
    CHECK (origen_id <> destino_id)
) STRICT;

CREATE INDEX factura_relacion_origen ON factura_relacion (origen_id);
CREATE INDEX factura_relacion_destino ON factura_relacion (destino_id);

CREATE TRIGGER factura_relacion_mismo_sentido_insert BEFORE INSERT ON factura_relacion
WHEN (SELECT sentido FROM factura WHERE id = NEW.origen_id)
     IS NOT (SELECT sentido FROM factura WHERE id = NEW.destino_id)
BEGIN SELECT RAISE(ABORT, 'una relacion une dos facturas del mismo sentido'); END;

CREATE TRIGGER factura_relacion_mismo_sentido_update BEFORE UPDATE OF origen_id, destino_id ON factura_relacion
WHEN (SELECT sentido FROM factura WHERE id = NEW.origen_id)
     IS NOT (SELECT sentido FROM factura WHERE id = NEW.destino_id)
BEGIN SELECT RAISE(ABORT, 'una relacion une dos facturas del mismo sentido'); END;

-- El sentido de una factura no cambia: lo decidio la via de entrada.
CREATE TRIGGER factura_sentido_fijo BEFORE UPDATE OF sentido ON factura
WHEN NEW.sentido IS NOT OLD.sentido
BEGIN SELECT RAISE(ABORT, 'el sentido de una factura lo decide la via de entrada y no cambia'); END;

-- --------------------------------------------------------------- procedencia

-- De donde sale el valor actual de cada campo de una tabla controlada, cual
-- era el original (y su literal impreso) y el ultimo automatico, aunque gane
-- uno manual. Una fila por campo; su historia esta en cambio_campo.
-- Los valores van en JSON canonico (el valor de la columna); NULL es "sin
-- valor". El original no cambia nunca. valor_automatico y su fuente (con su
-- referencia) son los del ultimo valor automatico, para que deshacer una
-- correccion devuelva el campo a esa fuente.
-- Tiene clave entera y UNIQUE (tabla, fila_id, campo) en vez de una clave
-- compuesta WITHOUT ROWID, como todas las tablas del almacen (spec §4).
-- tabla no lleva una lista cerrada: las controladas creceran (pagos,
-- conciliacion) y cambiar un CHECK obliga a reconstruir la tabla. Que tablas
-- son controladas lo dice campos.REGISTRO, y solo campos.py escribe aqui.
CREATE TABLE procedencia_campo (
    id                   INTEGER PRIMARY KEY,
    tabla                TEXT NOT NULL CHECK (length(tabla) > 0),
    fila_id              INTEGER NOT NULL,
    campo                TEXT NOT NULL CHECK (length(campo) > 0),
    fuente               TEXT NOT NULL CHECK (fuente IN (
        'extraccion', 'importacion', 'planning', 'maestro',
        'manual_entrada', 'manual_correccion', 'calculado')),
    fuente_ref           TEXT,
    valor_actual         TEXT CHECK (valor_actual IS NULL OR json_valid(valor_actual)),
    valor_original       TEXT CHECK (valor_original IS NULL OR json_valid(valor_original)),
    valor_original_crudo TEXT CHECK (valor_original_crudo IS NULL OR json_valid(valor_original_crudo)),
    fuente_original      TEXT NOT NULL CHECK (fuente_original IN (
        'extraccion', 'importacion', 'planning', 'maestro',
        'manual_entrada', 'manual_correccion', 'calculado')),
    valor_automatico     TEXT CHECK (valor_automatico IS NULL OR json_valid(valor_automatico)),
    fuente_automatica    TEXT CHECK (fuente_automatica IS NULL OR fuente_automatica IN (
        'extraccion', 'importacion', 'planning', 'maestro', 'calculado')),
    fuente_automatica_ref TEXT,
    dudoso               INTEGER NOT NULL DEFAULT 0 CHECK (dudoso IN (0, 1)),
    rev_campo            INTEGER NOT NULL CHECK (rev_campo >= 0),
    cambiado_en          TEXT NOT NULL CHECK (datetime(cambiado_en) IS NOT NULL),
    cambiado_por         INTEGER NOT NULL REFERENCES usuario(id),
    verificado_por       INTEGER REFERENCES usuario(id),
    verificado_en        TEXT CHECK (verificado_en IS NULL OR datetime(verificado_en) IS NOT NULL),
    verificado_rev       INTEGER,
    UNIQUE (tabla, fila_id, campo),
    CHECK ((verificado_por IS NULL) = (verificado_en IS NULL)),
    CHECK ((verificado_por IS NULL) = (verificado_rev IS NULL)),
    CHECK (valor_automatico IS NULL OR fuente_automatica IS NOT NULL)
) STRICT;

CREATE INDEX procedencia_campo_fuente ON procedencia_campo (fuente);

-- Solo dentro del evento en curso, y solo si ese evento nombra el campo: por
-- un cambio_campo suyo, o en la lista datos.campos ("tabla:fila_id:campo"),
-- que es lo que usan una verificacion o un valor automatico que no gana.
CREATE TRIGGER procedencia_campo_guarda_insert BEFORE INSERT ON procedencia_campo
WHEN NOT EXISTS (
        SELECT 1 FROM cambio_campo
        WHERE evento_id = (SELECT max(id) FROM evento)
          AND tabla = NEW.tabla AND fila_id = NEW.fila_id AND campo = NEW.campo)
 AND NOT EXISTS (
        SELECT 1 FROM json_each(coalesce(
            (SELECT datos_json FROM evento ORDER BY id DESC LIMIT 1), '{}'), '$.campos')
        WHERE value = NEW.tabla || ':' || NEW.fila_id || ':' || NEW.campo)
BEGIN SELECT RAISE(ABORT, 'procedencia_campo solo cambia dentro del evento que nombra ese campo'); END;

CREATE TRIGGER procedencia_campo_guarda_update BEFORE UPDATE ON procedencia_campo
WHEN NEW.id IS NOT OLD.id OR NEW.tabla IS NOT OLD.tabla OR NEW.fila_id IS NOT OLD.fila_id
  OR NEW.campo IS NOT OLD.campo
  OR NEW.valor_original IS NOT OLD.valor_original
  OR NEW.valor_original_crudo IS NOT OLD.valor_original_crudo
  OR NEW.fuente_original IS NOT OLD.fuente_original
  OR (NOT EXISTS (
        SELECT 1 FROM cambio_campo
        WHERE evento_id = (SELECT max(id) FROM evento)
          AND tabla = NEW.tabla AND fila_id = NEW.fila_id AND campo = NEW.campo)
      AND NOT EXISTS (
        SELECT 1 FROM json_each(coalesce(
            (SELECT datos_json FROM evento ORDER BY id DESC LIMIT 1), '{}'), '$.campos')
        WHERE value = NEW.tabla || ':' || NEW.fila_id || ':' || NEW.campo))
BEGIN SELECT RAISE(ABORT, 'procedencia_campo solo cambia dentro del evento que nombra ese campo, y su original no cambia nunca'); END;

CREATE TRIGGER procedencia_campo_sin_delete BEFORE DELETE ON procedencia_campo
BEGIN SELECT RAISE(ABORT, 'procedencia_campo no se borra'); END;

-- Quien verifica es una persona.
CREATE TRIGGER procedencia_campo_verifica_persona BEFORE UPDATE OF verificado_por ON procedencia_campo
WHEN NEW.verificado_por IS NOT NULL
 AND (SELECT es_sistema FROM usuario WHERE id = NEW.verificado_por) IS NOT 0
BEGIN SELECT RAISE(ABORT, 'un campo lo verifica una persona, no un usuario de sistema'); END;

-- --------------------------------------------------------------------- notas

-- Una nota de una persona sobre cualquier fila. Solo se anade.
CREATE TABLE nota (
    id         INTEGER PRIMARY KEY,
    tabla      TEXT NOT NULL CHECK (length(tabla) > 0),
    fila_id    INTEGER NOT NULL,
    texto      TEXT NOT NULL CHECK (length(trim(texto)) > 0),
    usuario_id INTEGER NOT NULL REFERENCES usuario(id),
    en         TEXT NOT NULL CHECK (datetime(en) IS NOT NULL),
    evento_id  INTEGER NOT NULL REFERENCES evento(id)
) STRICT;

CREATE INDEX nota_fila ON nota (tabla, fila_id);

CREATE TRIGGER nota_persona BEFORE INSERT ON nota
WHEN (SELECT es_sistema FROM usuario WHERE id = NEW.usuario_id) IS NOT 0
  OR NEW.evento_id IS NOT (SELECT max(id) FROM evento)
BEGIN SELECT RAISE(ABORT, 'una nota la escribe una persona, dentro de su evento'); END;

CREATE TRIGGER nota_sin_update BEFORE UPDATE ON nota
BEGIN SELECT RAISE(ABORT, 'nota es de solo escritura: no se modifica'); END;
CREATE TRIGGER nota_sin_delete BEFORE DELETE ON nota
BEGIN SELECT RAISE(ABORT, 'nota es de solo escritura: no se borra'); END;

-- --------------------------------------------------------------------- vistas

-- Las marcas de edicion manual de cada factura (§11), sacadas de la
-- procedencia de la factura y de sus hijas. sin_resolver: un valor manual
-- que no es el ultimo automatico y nadie ha verificado.
CREATE VIEW v_factura_ediciones AS
WITH campos AS (
    SELECT p.*, f.id AS factura_id FROM procedencia_campo AS p
    JOIN factura AS f ON p.tabla = 'factura' AND f.id = p.fila_id
    UNION ALL
    SELECT p.*, l.factura_id FROM procedencia_campo AS p
    JOIN factura_linea AS l ON p.tabla = 'factura_linea' AND l.id = p.fila_id
    UNION ALL
    SELECT p.*, i.factura_id FROM procedencia_campo AS p
    JOIN factura_imputacion AS i ON p.tabla = 'factura_imputacion' AND i.id = p.fila_id
    UNION ALL
    SELECT p.*, v.factura_id FROM procedencia_campo AS p
    JOIN factura_iva AS v ON p.tabla = 'factura_iva' AND v.id = p.fila_id
    UNION ALL
    SELECT p.*, r.factura_id FROM procedencia_campo AS p
    JOIN factura_referencia AS r ON p.tabla = 'factura_referencia' AND r.id = p.fila_id
)
SELECT
    f.id AS factura_id,
    coalesce(sum(c.fuente IN ('manual_entrada', 'manual_correccion')), 0) > 0 AS editada,
    coalesce(sum(c.fuente = 'manual_entrada'), 0) > 0 AS suplementada,
    coalesce(sum(c.fuente = 'manual_correccion'), 0) > 0 AS corregida,
    coalesce(sum(
        c.fuente IN ('manual_entrada', 'manual_correccion')
        AND c.valor_automatico IS NOT NULL
        AND c.valor_automatico IS NOT c.valor_actual
        AND c.verificado_rev IS NOT c.rev_campo), 0) AS sin_resolver
FROM factura AS f
LEFT JOIN campos AS c ON c.factura_id = f.id
GROUP BY f.id;

-- ------------------------------------------------- guardas de las controladas
--
-- Generadas columna a columna (una por columna salvo id y rev): una columna
-- nueva en una migracion posterior obliga a recrear las dos guardas de su
-- tabla, y test_campos.py comprueba que cada columna esta en ellas.

CREATE TRIGGER proveedor_guarda_insert BEFORE INSERT ON proveedor
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.nombre IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = 0
        AND campo = 'nombre' AND json_extract(valor_nuevo, '$') IS NEW.nombre))
    OR (NEW.tipo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tipo' AND json_extract(valor_nuevo, '$') IS NEW.tipo))
    OR (NEW.kvk IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = 0
        AND campo = 'kvk' AND json_extract(valor_nuevo, '$') IS NEW.kvk))
    OR (NEW.btw_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = 0
        AND campo = 'btw_id' AND json_extract(valor_nuevo, '$') IS NEW.btw_id))
    OR (NEW.regimen_iva IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = 0
        AND campo = 'regimen_iva' AND json_extract(valor_nuevo, '$') IS NEW.regimen_iva))
    OR (NEW.plazo_pago_dias IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = 0
        AND campo = 'plazo_pago_dias' AND json_extract(valor_nuevo, '$') IS NEW.plazo_pago_dias))
    OR (NEW.direccion IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = 0
        AND campo = 'direccion' AND json_extract(valor_nuevo, '$') IS NEW.direccion))
    OR (NEW.email_facturacion IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = 0
        AND campo = 'email_facturacion' AND json_extract(valor_nuevo, '$') IS NEW.email_facturacion))
    OR (NEW.telefono_verificacion IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = 0
        AND campo = 'telefono_verificacion' AND json_extract(valor_nuevo, '$') IS NEW.telefono_verificacion))
    OR (NEW.activo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = 0
        AND campo = 'activo' AND json_extract(valor_nuevo, '$') IS NEW.activo))
    OR (NEW.exact_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = 0
        AND campo = 'exact_id' AND json_extract(valor_nuevo, '$') IS NEW.exact_id))
    OR (NEW.trnsprnt_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = 0
        AND campo = 'trnsprnt_id' AND json_extract(valor_nuevo, '$') IS NEW.trnsprnt_id))
BEGIN SELECT RAISE(ABORT, 'proveedor es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER proveedor_guarda_update BEFORE UPDATE ON proveedor
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.nombre IS NOT OLD.nombre AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'nombre' AND json_extract(valor_anterior, '$') IS OLD.nombre
        AND json_extract(valor_nuevo, '$') IS NEW.nombre))
    OR (NEW.tipo IS NOT OLD.tipo AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tipo' AND json_extract(valor_anterior, '$') IS OLD.tipo
        AND json_extract(valor_nuevo, '$') IS NEW.tipo))
    OR (NEW.kvk IS NOT OLD.kvk AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'kvk' AND json_extract(valor_anterior, '$') IS OLD.kvk
        AND json_extract(valor_nuevo, '$') IS NEW.kvk))
    OR (NEW.btw_id IS NOT OLD.btw_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'btw_id' AND json_extract(valor_anterior, '$') IS OLD.btw_id
        AND json_extract(valor_nuevo, '$') IS NEW.btw_id))
    OR (NEW.regimen_iva IS NOT OLD.regimen_iva AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'regimen_iva' AND json_extract(valor_anterior, '$') IS OLD.regimen_iva
        AND json_extract(valor_nuevo, '$') IS NEW.regimen_iva))
    OR (NEW.plazo_pago_dias IS NOT OLD.plazo_pago_dias AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'plazo_pago_dias' AND json_extract(valor_anterior, '$') IS OLD.plazo_pago_dias
        AND json_extract(valor_nuevo, '$') IS NEW.plazo_pago_dias))
    OR (NEW.direccion IS NOT OLD.direccion AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'direccion' AND json_extract(valor_anterior, '$') IS OLD.direccion
        AND json_extract(valor_nuevo, '$') IS NEW.direccion))
    OR (NEW.email_facturacion IS NOT OLD.email_facturacion AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'email_facturacion' AND json_extract(valor_anterior, '$') IS OLD.email_facturacion
        AND json_extract(valor_nuevo, '$') IS NEW.email_facturacion))
    OR (NEW.telefono_verificacion IS NOT OLD.telefono_verificacion AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'telefono_verificacion' AND json_extract(valor_anterior, '$') IS OLD.telefono_verificacion
        AND json_extract(valor_nuevo, '$') IS NEW.telefono_verificacion))
    OR (NEW.activo IS NOT OLD.activo AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'activo' AND json_extract(valor_anterior, '$') IS OLD.activo
        AND json_extract(valor_nuevo, '$') IS NEW.activo))
    OR (NEW.exact_id IS NOT OLD.exact_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'exact_id' AND json_extract(valor_anterior, '$') IS OLD.exact_id
        AND json_extract(valor_nuevo, '$') IS NEW.exact_id))
    OR (NEW.trnsprnt_id IS NOT OLD.trnsprnt_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'proveedor' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'trnsprnt_id' AND json_extract(valor_anterior, '$') IS OLD.trnsprnt_id
        AND json_extract(valor_nuevo, '$') IS NEW.trnsprnt_id))
BEGIN SELECT RAISE(ABORT, 'proveedor es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER proveedor_sin_delete BEFORE DELETE ON proveedor
BEGIN SELECT RAISE(ABORT, 'proveedor no se borra: una fila se retira o se desactiva'); END;

CREATE TRIGGER cliente_guarda_insert BEFORE INSERT ON cliente
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.nombre IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = 0
        AND campo = 'nombre' AND json_extract(valor_nuevo, '$') IS NEW.nombre))
    OR (NEW.kvk IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = 0
        AND campo = 'kvk' AND json_extract(valor_nuevo, '$') IS NEW.kvk))
    OR (NEW.btw_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = 0
        AND campo = 'btw_id' AND json_extract(valor_nuevo, '$') IS NEW.btw_id))
    OR (NEW.plazo_pago_dias IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = 0
        AND campo = 'plazo_pago_dias' AND json_extract(valor_nuevo, '$') IS NEW.plazo_pago_dias))
    OR (NEW.requiere_po IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = 0
        AND campo = 'requiere_po' AND json_extract(valor_nuevo, '$') IS NEW.requiere_po))
    OR (NEW.tratamiento_iva_defecto IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tratamiento_iva_defecto' AND json_extract(valor_nuevo, '$') IS NEW.tratamiento_iva_defecto))
    OR (NEW.verlegd_elegible IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = 0
        AND campo = 'verlegd_elegible' AND json_extract(valor_nuevo, '$') IS NEW.verlegd_elegible))
    OR (NEW.activo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = 0
        AND campo = 'activo' AND json_extract(valor_nuevo, '$') IS NEW.activo))
    OR (NEW.exact_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = 0
        AND campo = 'exact_id' AND json_extract(valor_nuevo, '$') IS NEW.exact_id))
    OR (NEW.trnsprnt_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = 0
        AND campo = 'trnsprnt_id' AND json_extract(valor_nuevo, '$') IS NEW.trnsprnt_id))
BEGIN SELECT RAISE(ABORT, 'cliente es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER cliente_guarda_update BEFORE UPDATE ON cliente
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.nombre IS NOT OLD.nombre AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'nombre' AND json_extract(valor_anterior, '$') IS OLD.nombre
        AND json_extract(valor_nuevo, '$') IS NEW.nombre))
    OR (NEW.kvk IS NOT OLD.kvk AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'kvk' AND json_extract(valor_anterior, '$') IS OLD.kvk
        AND json_extract(valor_nuevo, '$') IS NEW.kvk))
    OR (NEW.btw_id IS NOT OLD.btw_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'btw_id' AND json_extract(valor_anterior, '$') IS OLD.btw_id
        AND json_extract(valor_nuevo, '$') IS NEW.btw_id))
    OR (NEW.plazo_pago_dias IS NOT OLD.plazo_pago_dias AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'plazo_pago_dias' AND json_extract(valor_anterior, '$') IS OLD.plazo_pago_dias
        AND json_extract(valor_nuevo, '$') IS NEW.plazo_pago_dias))
    OR (NEW.requiere_po IS NOT OLD.requiere_po AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'requiere_po' AND json_extract(valor_anterior, '$') IS OLD.requiere_po
        AND json_extract(valor_nuevo, '$') IS NEW.requiere_po))
    OR (NEW.tratamiento_iva_defecto IS NOT OLD.tratamiento_iva_defecto AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tratamiento_iva_defecto' AND json_extract(valor_anterior, '$') IS OLD.tratamiento_iva_defecto
        AND json_extract(valor_nuevo, '$') IS NEW.tratamiento_iva_defecto))
    OR (NEW.verlegd_elegible IS NOT OLD.verlegd_elegible AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'verlegd_elegible' AND json_extract(valor_anterior, '$') IS OLD.verlegd_elegible
        AND json_extract(valor_nuevo, '$') IS NEW.verlegd_elegible))
    OR (NEW.activo IS NOT OLD.activo AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'activo' AND json_extract(valor_anterior, '$') IS OLD.activo
        AND json_extract(valor_nuevo, '$') IS NEW.activo))
    OR (NEW.exact_id IS NOT OLD.exact_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'exact_id' AND json_extract(valor_anterior, '$') IS OLD.exact_id
        AND json_extract(valor_nuevo, '$') IS NEW.exact_id))
    OR (NEW.trnsprnt_id IS NOT OLD.trnsprnt_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'cliente' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'trnsprnt_id' AND json_extract(valor_anterior, '$') IS OLD.trnsprnt_id
        AND json_extract(valor_nuevo, '$') IS NEW.trnsprnt_id))
BEGIN SELECT RAISE(ABORT, 'cliente es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER cliente_sin_delete BEFORE DELETE ON cliente
BEGIN SELECT RAISE(ABORT, 'cliente no se borra: una fila se retira o se desactiva'); END;

CREATE TRIGGER contacto_guarda_insert BEFORE INSERT ON contacto
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'contacto' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.proveedor_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'contacto' AND fila_id = NEW.id AND rev = 0
        AND campo = 'proveedor_id' AND json_extract(valor_nuevo, '$') IS NEW.proveedor_id))
    OR (NEW.cliente_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'contacto' AND fila_id = NEW.id AND rev = 0
        AND campo = 'cliente_id' AND json_extract(valor_nuevo, '$') IS NEW.cliente_id))
    OR (NEW.nombre IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'contacto' AND fila_id = NEW.id AND rev = 0
        AND campo = 'nombre' AND json_extract(valor_nuevo, '$') IS NEW.nombre))
    OR (NEW.email IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'contacto' AND fila_id = NEW.id AND rev = 0
        AND campo = 'email' AND json_extract(valor_nuevo, '$') IS NEW.email))
    OR (NEW.telefono IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'contacto' AND fila_id = NEW.id AND rev = 0
        AND campo = 'telefono' AND json_extract(valor_nuevo, '$') IS NEW.telefono))
    OR (NEW.funcion IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'contacto' AND fila_id = NEW.id AND rev = 0
        AND campo = 'funcion' AND json_extract(valor_nuevo, '$') IS NEW.funcion))
    OR (NEW.activo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'contacto' AND fila_id = NEW.id AND rev = 0
        AND campo = 'activo' AND json_extract(valor_nuevo, '$') IS NEW.activo))
BEGIN SELECT RAISE(ABORT, 'contacto es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER contacto_guarda_update BEFORE UPDATE ON contacto
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'contacto' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.proveedor_id IS NOT OLD.proveedor_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'contacto' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'proveedor_id' AND json_extract(valor_anterior, '$') IS OLD.proveedor_id
        AND json_extract(valor_nuevo, '$') IS NEW.proveedor_id))
    OR (NEW.cliente_id IS NOT OLD.cliente_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'contacto' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'cliente_id' AND json_extract(valor_anterior, '$') IS OLD.cliente_id
        AND json_extract(valor_nuevo, '$') IS NEW.cliente_id))
    OR (NEW.nombre IS NOT OLD.nombre AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'contacto' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'nombre' AND json_extract(valor_anterior, '$') IS OLD.nombre
        AND json_extract(valor_nuevo, '$') IS NEW.nombre))
    OR (NEW.email IS NOT OLD.email AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'contacto' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'email' AND json_extract(valor_anterior, '$') IS OLD.email
        AND json_extract(valor_nuevo, '$') IS NEW.email))
    OR (NEW.telefono IS NOT OLD.telefono AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'contacto' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'telefono' AND json_extract(valor_anterior, '$') IS OLD.telefono
        AND json_extract(valor_nuevo, '$') IS NEW.telefono))
    OR (NEW.funcion IS NOT OLD.funcion AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'contacto' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'funcion' AND json_extract(valor_anterior, '$') IS OLD.funcion
        AND json_extract(valor_nuevo, '$') IS NEW.funcion))
    OR (NEW.activo IS NOT OLD.activo AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'contacto' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'activo' AND json_extract(valor_anterior, '$') IS OLD.activo
        AND json_extract(valor_nuevo, '$') IS NEW.activo))
BEGIN SELECT RAISE(ABORT, 'contacto es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER contacto_sin_delete BEFORE DELETE ON contacto
BEGIN SELECT RAISE(ABORT, 'contacto no se borra: una fila se retira o se desactiva'); END;

CREATE TRIGGER objeto_guarda_insert BEFORE INSERT ON objeto
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'objeto' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.codigo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'objeto' AND fila_id = NEW.id AND rev = 0
        AND campo = 'codigo' AND json_extract(valor_nuevo, '$') IS NEW.codigo))
    OR (NEW.nombre IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'objeto' AND fila_id = NEW.id AND rev = 0
        AND campo = 'nombre' AND json_extract(valor_nuevo, '$') IS NEW.nombre))
    OR (NEW.cliente_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'objeto' AND fila_id = NEW.id AND rev = 0
        AND campo = 'cliente_id' AND json_extract(valor_nuevo, '$') IS NEW.cliente_id))
    OR (NEW.requiere_po IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'objeto' AND fila_id = NEW.id AND rev = 0
        AND campo = 'requiere_po' AND json_extract(valor_nuevo, '$') IS NEW.requiere_po))
    OR (NEW.activo_desde IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'objeto' AND fila_id = NEW.id AND rev = 0
        AND campo = 'activo_desde' AND json_extract(valor_nuevo, '$') IS NEW.activo_desde))
    OR (NEW.activo_hasta IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'objeto' AND fila_id = NEW.id AND rev = 0
        AND campo = 'activo_hasta' AND json_extract(valor_nuevo, '$') IS NEW.activo_hasta))
    OR (NEW.trnsprnt_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'objeto' AND fila_id = NEW.id AND rev = 0
        AND campo = 'trnsprnt_id' AND json_extract(valor_nuevo, '$') IS NEW.trnsprnt_id))
BEGIN SELECT RAISE(ABORT, 'objeto es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER objeto_guarda_update BEFORE UPDATE ON objeto
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'objeto' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.codigo IS NOT OLD.codigo AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'objeto' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'codigo' AND json_extract(valor_anterior, '$') IS OLD.codigo
        AND json_extract(valor_nuevo, '$') IS NEW.codigo))
    OR (NEW.nombre IS NOT OLD.nombre AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'objeto' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'nombre' AND json_extract(valor_anterior, '$') IS OLD.nombre
        AND json_extract(valor_nuevo, '$') IS NEW.nombre))
    OR (NEW.cliente_id IS NOT OLD.cliente_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'objeto' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'cliente_id' AND json_extract(valor_anterior, '$') IS OLD.cliente_id
        AND json_extract(valor_nuevo, '$') IS NEW.cliente_id))
    OR (NEW.requiere_po IS NOT OLD.requiere_po AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'objeto' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'requiere_po' AND json_extract(valor_anterior, '$') IS OLD.requiere_po
        AND json_extract(valor_nuevo, '$') IS NEW.requiere_po))
    OR (NEW.activo_desde IS NOT OLD.activo_desde AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'objeto' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'activo_desde' AND json_extract(valor_anterior, '$') IS OLD.activo_desde
        AND json_extract(valor_nuevo, '$') IS NEW.activo_desde))
    OR (NEW.activo_hasta IS NOT OLD.activo_hasta AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'objeto' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'activo_hasta' AND json_extract(valor_anterior, '$') IS OLD.activo_hasta
        AND json_extract(valor_nuevo, '$') IS NEW.activo_hasta))
    OR (NEW.trnsprnt_id IS NOT OLD.trnsprnt_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'objeto' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'trnsprnt_id' AND json_extract(valor_anterior, '$') IS OLD.trnsprnt_id
        AND json_extract(valor_nuevo, '$') IS NEW.trnsprnt_id))
BEGIN SELECT RAISE(ABORT, 'objeto es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER objeto_sin_delete BEFORE DELETE ON objeto
BEGIN SELECT RAISE(ABORT, 'objeto no se borra: una fila se retira o se desactiva'); END;

CREATE TRIGGER recurso_guarda_insert BEFORE INSERT ON recurso
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'recurso' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.nombre IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'recurso' AND fila_id = NEW.id AND rev = 0
        AND campo = 'nombre' AND json_extract(valor_nuevo, '$') IS NEW.nombre))
    OR (NEW.tipo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'recurso' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tipo' AND json_extract(valor_nuevo, '$') IS NEW.tipo))
    OR (NEW.proveedor_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'recurso' AND fila_id = NEW.id AND rev = 0
        AND campo = 'proveedor_id' AND json_extract(valor_nuevo, '$') IS NEW.proveedor_id))
    OR (NEW.trnsprnt_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'recurso' AND fila_id = NEW.id AND rev = 0
        AND campo = 'trnsprnt_id' AND json_extract(valor_nuevo, '$') IS NEW.trnsprnt_id))
    OR (NEW.activo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'recurso' AND fila_id = NEW.id AND rev = 0
        AND campo = 'activo' AND json_extract(valor_nuevo, '$') IS NEW.activo))
BEGIN SELECT RAISE(ABORT, 'recurso es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER recurso_guarda_update BEFORE UPDATE ON recurso
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'recurso' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.nombre IS NOT OLD.nombre AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'recurso' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'nombre' AND json_extract(valor_anterior, '$') IS OLD.nombre
        AND json_extract(valor_nuevo, '$') IS NEW.nombre))
    OR (NEW.tipo IS NOT OLD.tipo AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'recurso' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tipo' AND json_extract(valor_anterior, '$') IS OLD.tipo
        AND json_extract(valor_nuevo, '$') IS NEW.tipo))
    OR (NEW.proveedor_id IS NOT OLD.proveedor_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'recurso' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'proveedor_id' AND json_extract(valor_anterior, '$') IS OLD.proveedor_id
        AND json_extract(valor_nuevo, '$') IS NEW.proveedor_id))
    OR (NEW.trnsprnt_id IS NOT OLD.trnsprnt_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'recurso' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'trnsprnt_id' AND json_extract(valor_anterior, '$') IS OLD.trnsprnt_id
        AND json_extract(valor_nuevo, '$') IS NEW.trnsprnt_id))
    OR (NEW.activo IS NOT OLD.activo AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'recurso' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'activo' AND json_extract(valor_anterior, '$') IS OLD.activo
        AND json_extract(valor_nuevo, '$') IS NEW.activo))
BEGIN SELECT RAISE(ABORT, 'recurso es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER recurso_sin_delete BEFORE DELETE ON recurso
BEGIN SELECT RAISE(ABORT, 'recurso no se borra: una fila se retira o se desactiva'); END;

CREATE TRIGGER alias_guarda_insert BEFORE INSERT ON alias
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'alias' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.tabla IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'alias' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tabla' AND json_extract(valor_nuevo, '$') IS NEW.tabla))
    OR (NEW.alias IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'alias' AND fila_id = NEW.id AND rev = 0
        AND campo = 'alias' AND json_extract(valor_nuevo, '$') IS NEW.alias))
    OR (NEW.alias_norm IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'alias' AND fila_id = NEW.id AND rev = 0
        AND campo = 'alias_norm' AND json_extract(valor_nuevo, '$') IS NEW.alias_norm))
    OR (NEW.fila_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'alias' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fila_id' AND json_extract(valor_nuevo, '$') IS NEW.fila_id))
    OR (NEW.origen IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'alias' AND fila_id = NEW.id AND rev = 0
        AND campo = 'origen' AND json_extract(valor_nuevo, '$') IS NEW.origen))
    OR (NEW.confirmado IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'alias' AND fila_id = NEW.id AND rev = 0
        AND campo = 'confirmado' AND json_extract(valor_nuevo, '$') IS NEW.confirmado))
    OR (NEW.activo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'alias' AND fila_id = NEW.id AND rev = 0
        AND campo = 'activo' AND json_extract(valor_nuevo, '$') IS NEW.activo))
BEGIN SELECT RAISE(ABORT, 'alias es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER alias_guarda_update BEFORE UPDATE ON alias
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'alias' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.tabla IS NOT OLD.tabla AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'alias' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tabla' AND json_extract(valor_anterior, '$') IS OLD.tabla
        AND json_extract(valor_nuevo, '$') IS NEW.tabla))
    OR (NEW.alias IS NOT OLD.alias AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'alias' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'alias' AND json_extract(valor_anterior, '$') IS OLD.alias
        AND json_extract(valor_nuevo, '$') IS NEW.alias))
    OR (NEW.alias_norm IS NOT OLD.alias_norm AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'alias' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'alias_norm' AND json_extract(valor_anterior, '$') IS OLD.alias_norm
        AND json_extract(valor_nuevo, '$') IS NEW.alias_norm))
    OR (NEW.fila_id IS NOT OLD.fila_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'alias' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fila_id' AND json_extract(valor_anterior, '$') IS OLD.fila_id
        AND json_extract(valor_nuevo, '$') IS NEW.fila_id))
    OR (NEW.origen IS NOT OLD.origen AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'alias' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'origen' AND json_extract(valor_anterior, '$') IS OLD.origen
        AND json_extract(valor_nuevo, '$') IS NEW.origen))
    OR (NEW.confirmado IS NOT OLD.confirmado AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'alias' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'confirmado' AND json_extract(valor_anterior, '$') IS OLD.confirmado
        AND json_extract(valor_nuevo, '$') IS NEW.confirmado))
    OR (NEW.activo IS NOT OLD.activo AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'alias' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'activo' AND json_extract(valor_anterior, '$') IS OLD.activo
        AND json_extract(valor_nuevo, '$') IS NEW.activo))
BEGIN SELECT RAISE(ABORT, 'alias es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER alias_sin_delete BEFORE DELETE ON alias
BEGIN SELECT RAISE(ABORT, 'alias no se borra: una fila se retira o se desactiva'); END;

CREATE TRIGGER tarifa_acordada_guarda_insert BEFORE INSERT ON tarifa_acordada
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.sentido IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = 0
        AND campo = 'sentido' AND json_extract(valor_nuevo, '$') IS NEW.sentido))
    OR (NEW.proveedor_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = 0
        AND campo = 'proveedor_id' AND json_extract(valor_nuevo, '$') IS NEW.proveedor_id))
    OR (NEW.recurso_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = 0
        AND campo = 'recurso_id' AND json_extract(valor_nuevo, '$') IS NEW.recurso_id))
    OR (NEW.cliente_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = 0
        AND campo = 'cliente_id' AND json_extract(valor_nuevo, '$') IS NEW.cliente_id))
    OR (NEW.objeto_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = 0
        AND campo = 'objeto_id' AND json_extract(valor_nuevo, '$') IS NEW.objeto_id))
    OR (NEW.orden_compra_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = 0
        AND campo = 'orden_compra_id' AND json_extract(valor_nuevo, '$') IS NEW.orden_compra_id))
    OR (NEW.tipo_servicio IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tipo_servicio' AND json_extract(valor_nuevo, '$') IS NEW.tipo_servicio))
    OR (NEW.tipo_turno IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tipo_turno' AND json_extract(valor_nuevo, '$') IS NEW.tipo_turno))
    OR (NEW.unidad IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = 0
        AND campo = 'unidad' AND json_extract(valor_nuevo, '$') IS NEW.unidad))
    OR (NEW.tarifa_e4 IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tarifa_e4' AND json_extract(valor_nuevo, '$') IS NEW.tarifa_e4))
    OR (NEW.vigente_desde IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = 0
        AND campo = 'vigente_desde' AND json_extract(valor_nuevo, '$') IS NEW.vigente_desde))
    OR (NEW.vigente_hasta IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = 0
        AND campo = 'vigente_hasta' AND json_extract(valor_nuevo, '$') IS NEW.vigente_hasta))
    OR (NEW.fuente IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fuente' AND json_extract(valor_nuevo, '$') IS NEW.fuente))
    OR (NEW.documento_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = 0
        AND campo = 'documento_id' AND json_extract(valor_nuevo, '$') IS NEW.documento_id))
BEGIN SELECT RAISE(ABORT, 'tarifa_acordada es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER tarifa_acordada_guarda_update BEFORE UPDATE ON tarifa_acordada
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.sentido IS NOT OLD.sentido AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'sentido' AND json_extract(valor_anterior, '$') IS OLD.sentido
        AND json_extract(valor_nuevo, '$') IS NEW.sentido))
    OR (NEW.proveedor_id IS NOT OLD.proveedor_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'proveedor_id' AND json_extract(valor_anterior, '$') IS OLD.proveedor_id
        AND json_extract(valor_nuevo, '$') IS NEW.proveedor_id))
    OR (NEW.recurso_id IS NOT OLD.recurso_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'recurso_id' AND json_extract(valor_anterior, '$') IS OLD.recurso_id
        AND json_extract(valor_nuevo, '$') IS NEW.recurso_id))
    OR (NEW.cliente_id IS NOT OLD.cliente_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'cliente_id' AND json_extract(valor_anterior, '$') IS OLD.cliente_id
        AND json_extract(valor_nuevo, '$') IS NEW.cliente_id))
    OR (NEW.objeto_id IS NOT OLD.objeto_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'objeto_id' AND json_extract(valor_anterior, '$') IS OLD.objeto_id
        AND json_extract(valor_nuevo, '$') IS NEW.objeto_id))
    OR (NEW.orden_compra_id IS NOT OLD.orden_compra_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'orden_compra_id' AND json_extract(valor_anterior, '$') IS OLD.orden_compra_id
        AND json_extract(valor_nuevo, '$') IS NEW.orden_compra_id))
    OR (NEW.tipo_servicio IS NOT OLD.tipo_servicio AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tipo_servicio' AND json_extract(valor_anterior, '$') IS OLD.tipo_servicio
        AND json_extract(valor_nuevo, '$') IS NEW.tipo_servicio))
    OR (NEW.tipo_turno IS NOT OLD.tipo_turno AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tipo_turno' AND json_extract(valor_anterior, '$') IS OLD.tipo_turno
        AND json_extract(valor_nuevo, '$') IS NEW.tipo_turno))
    OR (NEW.unidad IS NOT OLD.unidad AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'unidad' AND json_extract(valor_anterior, '$') IS OLD.unidad
        AND json_extract(valor_nuevo, '$') IS NEW.unidad))
    OR (NEW.tarifa_e4 IS NOT OLD.tarifa_e4 AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tarifa_e4' AND json_extract(valor_anterior, '$') IS OLD.tarifa_e4
        AND json_extract(valor_nuevo, '$') IS NEW.tarifa_e4))
    OR (NEW.vigente_desde IS NOT OLD.vigente_desde AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'vigente_desde' AND json_extract(valor_anterior, '$') IS OLD.vigente_desde
        AND json_extract(valor_nuevo, '$') IS NEW.vigente_desde))
    OR (NEW.vigente_hasta IS NOT OLD.vigente_hasta AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'vigente_hasta' AND json_extract(valor_anterior, '$') IS OLD.vigente_hasta
        AND json_extract(valor_nuevo, '$') IS NEW.vigente_hasta))
    OR (NEW.fuente IS NOT OLD.fuente AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fuente' AND json_extract(valor_anterior, '$') IS OLD.fuente
        AND json_extract(valor_nuevo, '$') IS NEW.fuente))
    OR (NEW.documento_id IS NOT OLD.documento_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'tarifa_acordada' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'documento_id' AND json_extract(valor_anterior, '$') IS OLD.documento_id
        AND json_extract(valor_nuevo, '$') IS NEW.documento_id))
BEGIN SELECT RAISE(ABORT, 'tarifa_acordada es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER tarifa_acordada_sin_delete BEFORE DELETE ON tarifa_acordada
BEGIN SELECT RAISE(ABORT, 'tarifa_acordada no se borra: una fila se retira o se desactiva'); END;

CREATE TRIGGER factura_guarda_insert BEFORE INSERT ON factura
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.sentido IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'sentido' AND json_extract(valor_nuevo, '$') IS NEW.sentido))
    OR (NEW.tipo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tipo' AND json_extract(valor_nuevo, '$') IS NEW.tipo))
    OR (NEW.origen IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'origen' AND json_extract(valor_nuevo, '$') IS NEW.origen))
    OR (NEW.documento_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'documento_id' AND json_extract(valor_nuevo, '$') IS NEW.documento_id))
    OR (NEW.extraccion_vigente_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'extraccion_vigente_id' AND json_extract(valor_nuevo, '$') IS NEW.extraccion_vigente_id))
    OR (NEW.fuente_externa IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fuente_externa' AND json_extract(valor_nuevo, '$') IS NEW.fuente_externa))
    OR (NEW.id_externo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'id_externo' AND json_extract(valor_nuevo, '$') IS NEW.id_externo))
    OR (NEW.numero IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'numero' AND json_extract(valor_nuevo, '$') IS NEW.numero))
    OR (NEW.numero_norm IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'numero_norm' AND json_extract(valor_nuevo, '$') IS NEW.numero_norm))
    OR (NEW.proveedor_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'proveedor_id' AND json_extract(valor_nuevo, '$') IS NEW.proveedor_id))
    OR (NEW.cliente_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'cliente_id' AND json_extract(valor_nuevo, '$') IS NEW.cliente_id))
    OR (NEW.contacto_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'contacto_id' AND json_extract(valor_nuevo, '$') IS NEW.contacto_id))
    OR (NEW.emisor_nombre_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'emisor_nombre_doc' AND json_extract(valor_nuevo, '$') IS NEW.emisor_nombre_doc))
    OR (NEW.emisor_direccion_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'emisor_direccion_doc' AND json_extract(valor_nuevo, '$') IS NEW.emisor_direccion_doc))
    OR (NEW.emisor_kvk_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'emisor_kvk_doc' AND json_extract(valor_nuevo, '$') IS NEW.emisor_kvk_doc))
    OR (NEW.emisor_btw_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'emisor_btw_doc' AND json_extract(valor_nuevo, '$') IS NEW.emisor_btw_doc))
    OR (NEW.receptor_nombre_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'receptor_nombre_doc' AND json_extract(valor_nuevo, '$') IS NEW.receptor_nombre_doc))
    OR (NEW.receptor_btw_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'receptor_btw_doc' AND json_extract(valor_nuevo, '$') IS NEW.receptor_btw_doc))
    OR (NEW.contacto_nombre_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'contacto_nombre_doc' AND json_extract(valor_nuevo, '$') IS NEW.contacto_nombre_doc))
    OR (NEW.fecha_factura IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fecha_factura' AND json_extract(valor_nuevo, '$') IS NEW.fecha_factura))
    OR (NEW.fecha_recepcion IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fecha_recepcion' AND json_extract(valor_nuevo, '$') IS NEW.fecha_recepcion))
    OR (NEW.fecha_envio IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fecha_envio' AND json_extract(valor_nuevo, '$') IS NEW.fecha_envio))
    OR (NEW.periodo_inicio IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'periodo_inicio' AND json_extract(valor_nuevo, '$') IS NEW.periodo_inicio))
    OR (NEW.periodo_fin IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'periodo_fin' AND json_extract(valor_nuevo, '$') IS NEW.periodo_fin))
    OR (NEW.fecha_vencimiento IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fecha_vencimiento' AND json_extract(valor_nuevo, '$') IS NEW.fecha_vencimiento))
    OR (NEW.plazo_pago_dias IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'plazo_pago_dias' AND json_extract(valor_nuevo, '$') IS NEW.plazo_pago_dias))
    OR (NEW.condiciones_pago_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'condiciones_pago_doc' AND json_extract(valor_nuevo, '$') IS NEW.condiciones_pago_doc))
    OR (NEW.base_cent IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'base_cent' AND json_extract(valor_nuevo, '$') IS NEW.base_cent))
    OR (NEW.iva_cent IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'iva_cent' AND json_extract(valor_nuevo, '$') IS NEW.iva_cent))
    OR (NEW.total_cent IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'total_cent' AND json_extract(valor_nuevo, '$') IS NEW.total_cent))
    OR (NEW.tipo_iva_pb IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tipo_iva_pb' AND json_extract(valor_nuevo, '$') IS NEW.tipo_iva_pb))
    OR (NEW.tratamiento_iva IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tratamiento_iva' AND json_extract(valor_nuevo, '$') IS NEW.tratamiento_iva))
    OR (NEW.kor_mencionada IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'kor_mencionada' AND json_extract(valor_nuevo, '$') IS NEW.kor_mencionada))
    OR (NEW.autoliquidacion_mencionada IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'autoliquidacion_mencionada' AND json_extract(valor_nuevo, '$') IS NEW.autoliquidacion_mencionada))
    OR (NEW.referencia_pago IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'referencia_pago' AND json_extract(valor_nuevo, '$') IS NEW.referencia_pago))
    OR (NEW.iban_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'iban_doc' AND json_extract(valor_nuevo, '$') IS NEW.iban_doc))
    OR (NEW.moneda_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'moneda_doc' AND json_extract(valor_nuevo, '$') IS NEW.moneda_doc))
    OR (NEW.notas_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'notas_doc' AND json_extract(valor_nuevo, '$') IS NEW.notas_doc))
    OR (NEW.anulada IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'anulada' AND json_extract(valor_nuevo, '$') IS NEW.anulada))
    OR (NEW.fusionada_en_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fusionada_en_id' AND json_extract(valor_nuevo, '$') IS NEW.fusionada_en_id))
BEGIN SELECT RAISE(ABORT, 'factura es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER factura_guarda_update BEFORE UPDATE ON factura
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.sentido IS NOT OLD.sentido AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'sentido' AND json_extract(valor_anterior, '$') IS OLD.sentido
        AND json_extract(valor_nuevo, '$') IS NEW.sentido))
    OR (NEW.tipo IS NOT OLD.tipo AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tipo' AND json_extract(valor_anterior, '$') IS OLD.tipo
        AND json_extract(valor_nuevo, '$') IS NEW.tipo))
    OR (NEW.origen IS NOT OLD.origen AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'origen' AND json_extract(valor_anterior, '$') IS OLD.origen
        AND json_extract(valor_nuevo, '$') IS NEW.origen))
    OR (NEW.documento_id IS NOT OLD.documento_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'documento_id' AND json_extract(valor_anterior, '$') IS OLD.documento_id
        AND json_extract(valor_nuevo, '$') IS NEW.documento_id))
    OR (NEW.extraccion_vigente_id IS NOT OLD.extraccion_vigente_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'extraccion_vigente_id' AND json_extract(valor_anterior, '$') IS OLD.extraccion_vigente_id
        AND json_extract(valor_nuevo, '$') IS NEW.extraccion_vigente_id))
    OR (NEW.fuente_externa IS NOT OLD.fuente_externa AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fuente_externa' AND json_extract(valor_anterior, '$') IS OLD.fuente_externa
        AND json_extract(valor_nuevo, '$') IS NEW.fuente_externa))
    OR (NEW.id_externo IS NOT OLD.id_externo AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'id_externo' AND json_extract(valor_anterior, '$') IS OLD.id_externo
        AND json_extract(valor_nuevo, '$') IS NEW.id_externo))
    OR (NEW.numero IS NOT OLD.numero AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'numero' AND json_extract(valor_anterior, '$') IS OLD.numero
        AND json_extract(valor_nuevo, '$') IS NEW.numero))
    OR (NEW.numero_norm IS NOT OLD.numero_norm AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'numero_norm' AND json_extract(valor_anterior, '$') IS OLD.numero_norm
        AND json_extract(valor_nuevo, '$') IS NEW.numero_norm))
    OR (NEW.proveedor_id IS NOT OLD.proveedor_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'proveedor_id' AND json_extract(valor_anterior, '$') IS OLD.proveedor_id
        AND json_extract(valor_nuevo, '$') IS NEW.proveedor_id))
    OR (NEW.cliente_id IS NOT OLD.cliente_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'cliente_id' AND json_extract(valor_anterior, '$') IS OLD.cliente_id
        AND json_extract(valor_nuevo, '$') IS NEW.cliente_id))
    OR (NEW.contacto_id IS NOT OLD.contacto_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'contacto_id' AND json_extract(valor_anterior, '$') IS OLD.contacto_id
        AND json_extract(valor_nuevo, '$') IS NEW.contacto_id))
    OR (NEW.emisor_nombre_doc IS NOT OLD.emisor_nombre_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'emisor_nombre_doc' AND json_extract(valor_anterior, '$') IS OLD.emisor_nombre_doc
        AND json_extract(valor_nuevo, '$') IS NEW.emisor_nombre_doc))
    OR (NEW.emisor_direccion_doc IS NOT OLD.emisor_direccion_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'emisor_direccion_doc' AND json_extract(valor_anterior, '$') IS OLD.emisor_direccion_doc
        AND json_extract(valor_nuevo, '$') IS NEW.emisor_direccion_doc))
    OR (NEW.emisor_kvk_doc IS NOT OLD.emisor_kvk_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'emisor_kvk_doc' AND json_extract(valor_anterior, '$') IS OLD.emisor_kvk_doc
        AND json_extract(valor_nuevo, '$') IS NEW.emisor_kvk_doc))
    OR (NEW.emisor_btw_doc IS NOT OLD.emisor_btw_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'emisor_btw_doc' AND json_extract(valor_anterior, '$') IS OLD.emisor_btw_doc
        AND json_extract(valor_nuevo, '$') IS NEW.emisor_btw_doc))
    OR (NEW.receptor_nombre_doc IS NOT OLD.receptor_nombre_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'receptor_nombre_doc' AND json_extract(valor_anterior, '$') IS OLD.receptor_nombre_doc
        AND json_extract(valor_nuevo, '$') IS NEW.receptor_nombre_doc))
    OR (NEW.receptor_btw_doc IS NOT OLD.receptor_btw_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'receptor_btw_doc' AND json_extract(valor_anterior, '$') IS OLD.receptor_btw_doc
        AND json_extract(valor_nuevo, '$') IS NEW.receptor_btw_doc))
    OR (NEW.contacto_nombre_doc IS NOT OLD.contacto_nombre_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'contacto_nombre_doc' AND json_extract(valor_anterior, '$') IS OLD.contacto_nombre_doc
        AND json_extract(valor_nuevo, '$') IS NEW.contacto_nombre_doc))
    OR (NEW.fecha_factura IS NOT OLD.fecha_factura AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fecha_factura' AND json_extract(valor_anterior, '$') IS OLD.fecha_factura
        AND json_extract(valor_nuevo, '$') IS NEW.fecha_factura))
    OR (NEW.fecha_recepcion IS NOT OLD.fecha_recepcion AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fecha_recepcion' AND json_extract(valor_anterior, '$') IS OLD.fecha_recepcion
        AND json_extract(valor_nuevo, '$') IS NEW.fecha_recepcion))
    OR (NEW.fecha_envio IS NOT OLD.fecha_envio AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fecha_envio' AND json_extract(valor_anterior, '$') IS OLD.fecha_envio
        AND json_extract(valor_nuevo, '$') IS NEW.fecha_envio))
    OR (NEW.periodo_inicio IS NOT OLD.periodo_inicio AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'periodo_inicio' AND json_extract(valor_anterior, '$') IS OLD.periodo_inicio
        AND json_extract(valor_nuevo, '$') IS NEW.periodo_inicio))
    OR (NEW.periodo_fin IS NOT OLD.periodo_fin AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'periodo_fin' AND json_extract(valor_anterior, '$') IS OLD.periodo_fin
        AND json_extract(valor_nuevo, '$') IS NEW.periodo_fin))
    OR (NEW.fecha_vencimiento IS NOT OLD.fecha_vencimiento AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fecha_vencimiento' AND json_extract(valor_anterior, '$') IS OLD.fecha_vencimiento
        AND json_extract(valor_nuevo, '$') IS NEW.fecha_vencimiento))
    OR (NEW.plazo_pago_dias IS NOT OLD.plazo_pago_dias AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'plazo_pago_dias' AND json_extract(valor_anterior, '$') IS OLD.plazo_pago_dias
        AND json_extract(valor_nuevo, '$') IS NEW.plazo_pago_dias))
    OR (NEW.condiciones_pago_doc IS NOT OLD.condiciones_pago_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'condiciones_pago_doc' AND json_extract(valor_anterior, '$') IS OLD.condiciones_pago_doc
        AND json_extract(valor_nuevo, '$') IS NEW.condiciones_pago_doc))
    OR (NEW.base_cent IS NOT OLD.base_cent AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'base_cent' AND json_extract(valor_anterior, '$') IS OLD.base_cent
        AND json_extract(valor_nuevo, '$') IS NEW.base_cent))
    OR (NEW.iva_cent IS NOT OLD.iva_cent AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'iva_cent' AND json_extract(valor_anterior, '$') IS OLD.iva_cent
        AND json_extract(valor_nuevo, '$') IS NEW.iva_cent))
    OR (NEW.total_cent IS NOT OLD.total_cent AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'total_cent' AND json_extract(valor_anterior, '$') IS OLD.total_cent
        AND json_extract(valor_nuevo, '$') IS NEW.total_cent))
    OR (NEW.tipo_iva_pb IS NOT OLD.tipo_iva_pb AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tipo_iva_pb' AND json_extract(valor_anterior, '$') IS OLD.tipo_iva_pb
        AND json_extract(valor_nuevo, '$') IS NEW.tipo_iva_pb))
    OR (NEW.tratamiento_iva IS NOT OLD.tratamiento_iva AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tratamiento_iva' AND json_extract(valor_anterior, '$') IS OLD.tratamiento_iva
        AND json_extract(valor_nuevo, '$') IS NEW.tratamiento_iva))
    OR (NEW.kor_mencionada IS NOT OLD.kor_mencionada AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'kor_mencionada' AND json_extract(valor_anterior, '$') IS OLD.kor_mencionada
        AND json_extract(valor_nuevo, '$') IS NEW.kor_mencionada))
    OR (NEW.autoliquidacion_mencionada IS NOT OLD.autoliquidacion_mencionada AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'autoliquidacion_mencionada' AND json_extract(valor_anterior, '$') IS OLD.autoliquidacion_mencionada
        AND json_extract(valor_nuevo, '$') IS NEW.autoliquidacion_mencionada))
    OR (NEW.referencia_pago IS NOT OLD.referencia_pago AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'referencia_pago' AND json_extract(valor_anterior, '$') IS OLD.referencia_pago
        AND json_extract(valor_nuevo, '$') IS NEW.referencia_pago))
    OR (NEW.iban_doc IS NOT OLD.iban_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'iban_doc' AND json_extract(valor_anterior, '$') IS OLD.iban_doc
        AND json_extract(valor_nuevo, '$') IS NEW.iban_doc))
    OR (NEW.moneda_doc IS NOT OLD.moneda_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'moneda_doc' AND json_extract(valor_anterior, '$') IS OLD.moneda_doc
        AND json_extract(valor_nuevo, '$') IS NEW.moneda_doc))
    OR (NEW.notas_doc IS NOT OLD.notas_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'notas_doc' AND json_extract(valor_anterior, '$') IS OLD.notas_doc
        AND json_extract(valor_nuevo, '$') IS NEW.notas_doc))
    OR (NEW.anulada IS NOT OLD.anulada AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'anulada' AND json_extract(valor_anterior, '$') IS OLD.anulada
        AND json_extract(valor_nuevo, '$') IS NEW.anulada))
    OR (NEW.fusionada_en_id IS NOT OLD.fusionada_en_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fusionada_en_id' AND json_extract(valor_anterior, '$') IS OLD.fusionada_en_id
        AND json_extract(valor_nuevo, '$') IS NEW.fusionada_en_id))
BEGIN SELECT RAISE(ABORT, 'factura es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER factura_sin_delete BEFORE DELETE ON factura
BEGIN SELECT RAISE(ABORT, 'factura no se borra: una fila se retira o se desactiva'); END;

CREATE TRIGGER factura_linea_guarda_insert BEFORE INSERT ON factura_linea
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.factura_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'factura_id' AND json_extract(valor_nuevo, '$') IS NEW.factura_id))
    OR (NEW.orden IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'orden' AND json_extract(valor_nuevo, '$') IS NEW.orden))
    OR (NEW.huella_linea IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'huella_linea' AND json_extract(valor_nuevo, '$') IS NEW.huella_linea))
    OR (NEW.descripcion_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'descripcion_doc' AND json_extract(valor_nuevo, '$') IS NEW.descripcion_doc))
    OR (NEW.objeto_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'objeto_doc' AND json_extract(valor_nuevo, '$') IS NEW.objeto_doc))
    OR (NEW.recurso_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'recurso_doc' AND json_extract(valor_nuevo, '$') IS NEW.recurso_doc))
    OR (NEW.unidad_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'unidad_doc' AND json_extract(valor_nuevo, '$') IS NEW.unidad_doc))
    OR (NEW.semana_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'semana_doc' AND json_extract(valor_nuevo, '$') IS NEW.semana_doc))
    OR (NEW.tipo_turno_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tipo_turno_doc' AND json_extract(valor_nuevo, '$') IS NEW.tipo_turno_doc))
    OR (NEW.fecha_inicio IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fecha_inicio' AND json_extract(valor_nuevo, '$') IS NEW.fecha_inicio))
    OR (NEW.fecha_fin IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fecha_fin' AND json_extract(valor_nuevo, '$') IS NEW.fecha_fin))
    OR (NEW.fecha_trabajo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fecha_trabajo' AND json_extract(valor_nuevo, '$') IS NEW.fecha_trabajo))
    OR (NEW.semana_iso IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'semana_iso' AND json_extract(valor_nuevo, '$') IS NEW.semana_iso))
    OR (NEW.unidad IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'unidad' AND json_extract(valor_nuevo, '$') IS NEW.unidad))
    OR (NEW.cantidad_mil IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'cantidad_mil' AND json_extract(valor_nuevo, '$') IS NEW.cantidad_mil))
    OR (NEW.tarifa_e4 IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tarifa_e4' AND json_extract(valor_nuevo, '$') IS NEW.tarifa_e4))
    OR (NEW.importe_cent IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'importe_cent' AND json_extract(valor_nuevo, '$') IS NEW.importe_cent))
    OR (NEW.tipo_iva_pb IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tipo_iva_pb' AND json_extract(valor_nuevo, '$') IS NEW.tipo_iva_pb))
    OR (NEW.tipo_servicio IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tipo_servicio' AND json_extract(valor_nuevo, '$') IS NEW.tipo_servicio))
    OR (NEW.retirada_en IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = 0
        AND campo = 'retirada_en' AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'factura_linea es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER factura_linea_guarda_update BEFORE UPDATE ON factura_linea
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.factura_id IS NOT OLD.factura_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'factura_id' AND json_extract(valor_anterior, '$') IS OLD.factura_id
        AND json_extract(valor_nuevo, '$') IS NEW.factura_id))
    OR (NEW.orden IS NOT OLD.orden AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'orden' AND json_extract(valor_anterior, '$') IS OLD.orden
        AND json_extract(valor_nuevo, '$') IS NEW.orden))
    OR (NEW.huella_linea IS NOT OLD.huella_linea AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'huella_linea' AND json_extract(valor_anterior, '$') IS OLD.huella_linea
        AND json_extract(valor_nuevo, '$') IS NEW.huella_linea))
    OR (NEW.descripcion_doc IS NOT OLD.descripcion_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'descripcion_doc' AND json_extract(valor_anterior, '$') IS OLD.descripcion_doc
        AND json_extract(valor_nuevo, '$') IS NEW.descripcion_doc))
    OR (NEW.objeto_doc IS NOT OLD.objeto_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'objeto_doc' AND json_extract(valor_anterior, '$') IS OLD.objeto_doc
        AND json_extract(valor_nuevo, '$') IS NEW.objeto_doc))
    OR (NEW.recurso_doc IS NOT OLD.recurso_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'recurso_doc' AND json_extract(valor_anterior, '$') IS OLD.recurso_doc
        AND json_extract(valor_nuevo, '$') IS NEW.recurso_doc))
    OR (NEW.unidad_doc IS NOT OLD.unidad_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'unidad_doc' AND json_extract(valor_anterior, '$') IS OLD.unidad_doc
        AND json_extract(valor_nuevo, '$') IS NEW.unidad_doc))
    OR (NEW.semana_doc IS NOT OLD.semana_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'semana_doc' AND json_extract(valor_anterior, '$') IS OLD.semana_doc
        AND json_extract(valor_nuevo, '$') IS NEW.semana_doc))
    OR (NEW.tipo_turno_doc IS NOT OLD.tipo_turno_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tipo_turno_doc' AND json_extract(valor_anterior, '$') IS OLD.tipo_turno_doc
        AND json_extract(valor_nuevo, '$') IS NEW.tipo_turno_doc))
    OR (NEW.fecha_inicio IS NOT OLD.fecha_inicio AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fecha_inicio' AND json_extract(valor_anterior, '$') IS OLD.fecha_inicio
        AND json_extract(valor_nuevo, '$') IS NEW.fecha_inicio))
    OR (NEW.fecha_fin IS NOT OLD.fecha_fin AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fecha_fin' AND json_extract(valor_anterior, '$') IS OLD.fecha_fin
        AND json_extract(valor_nuevo, '$') IS NEW.fecha_fin))
    OR (NEW.fecha_trabajo IS NOT OLD.fecha_trabajo AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fecha_trabajo' AND json_extract(valor_anterior, '$') IS OLD.fecha_trabajo
        AND json_extract(valor_nuevo, '$') IS NEW.fecha_trabajo))
    OR (NEW.semana_iso IS NOT OLD.semana_iso AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'semana_iso' AND json_extract(valor_anterior, '$') IS OLD.semana_iso
        AND json_extract(valor_nuevo, '$') IS NEW.semana_iso))
    OR (NEW.unidad IS NOT OLD.unidad AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'unidad' AND json_extract(valor_anterior, '$') IS OLD.unidad
        AND json_extract(valor_nuevo, '$') IS NEW.unidad))
    OR (NEW.cantidad_mil IS NOT OLD.cantidad_mil AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'cantidad_mil' AND json_extract(valor_anterior, '$') IS OLD.cantidad_mil
        AND json_extract(valor_nuevo, '$') IS NEW.cantidad_mil))
    OR (NEW.tarifa_e4 IS NOT OLD.tarifa_e4 AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tarifa_e4' AND json_extract(valor_anterior, '$') IS OLD.tarifa_e4
        AND json_extract(valor_nuevo, '$') IS NEW.tarifa_e4))
    OR (NEW.importe_cent IS NOT OLD.importe_cent AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'importe_cent' AND json_extract(valor_anterior, '$') IS OLD.importe_cent
        AND json_extract(valor_nuevo, '$') IS NEW.importe_cent))
    OR (NEW.tipo_iva_pb IS NOT OLD.tipo_iva_pb AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tipo_iva_pb' AND json_extract(valor_anterior, '$') IS OLD.tipo_iva_pb
        AND json_extract(valor_nuevo, '$') IS NEW.tipo_iva_pb))
    OR (NEW.tipo_servicio IS NOT OLD.tipo_servicio AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tipo_servicio' AND json_extract(valor_anterior, '$') IS OLD.tipo_servicio
        AND json_extract(valor_nuevo, '$') IS NEW.tipo_servicio))
    OR (NEW.retirada_en IS NOT OLD.retirada_en AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_linea' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'retirada_en' AND json_extract(valor_anterior, '$') IS OLD.retirada_en
        AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'factura_linea es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER factura_linea_sin_delete BEFORE DELETE ON factura_linea
BEGIN SELECT RAISE(ABORT, 'factura_linea no se borra: una fila se retira o se desactiva'); END;

CREATE TRIGGER factura_imputacion_guarda_insert BEFORE INSERT ON factura_imputacion
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.factura_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'factura_id' AND json_extract(valor_nuevo, '$') IS NEW.factura_id))
    OR (NEW.linea_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'linea_id' AND json_extract(valor_nuevo, '$') IS NEW.linea_id))
    OR (NEW.objeto_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'objeto_id' AND json_extract(valor_nuevo, '$') IS NEW.objeto_id))
    OR (NEW.recurso_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'recurso_id' AND json_extract(valor_nuevo, '$') IS NEW.recurso_id))
    OR (NEW.orden_compra_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'orden_compra_id' AND json_extract(valor_nuevo, '$') IS NEW.orden_compra_id))
    OR (NEW.descripcion IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'descripcion' AND json_extract(valor_nuevo, '$') IS NEW.descripcion))
    OR (NEW.fecha_inicio IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fecha_inicio' AND json_extract(valor_nuevo, '$') IS NEW.fecha_inicio))
    OR (NEW.fecha_fin IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fecha_fin' AND json_extract(valor_nuevo, '$') IS NEW.fecha_fin))
    OR (NEW.semana_iso IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'semana_iso' AND json_extract(valor_nuevo, '$') IS NEW.semana_iso))
    OR (NEW.horas_mil IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'horas_mil' AND json_extract(valor_nuevo, '$') IS NEW.horas_mil))
    OR (NEW.tarifa_e4 IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tarifa_e4' AND json_extract(valor_nuevo, '$') IS NEW.tarifa_e4))
    OR (NEW.importe_cent IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'importe_cent' AND json_extract(valor_nuevo, '$') IS NEW.importe_cent))
    OR (NEW.tipo_servicio IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tipo_servicio' AND json_extract(valor_nuevo, '$') IS NEW.tipo_servicio))
    OR (NEW.tipo_turno IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tipo_turno' AND json_extract(valor_nuevo, '$') IS NEW.tipo_turno))
    OR (NEW.facturable IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'facturable' AND json_extract(valor_nuevo, '$') IS NEW.facturable))
    OR (NEW.retirada_en IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'retirada_en' AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'factura_imputacion es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER factura_imputacion_guarda_update BEFORE UPDATE ON factura_imputacion
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.factura_id IS NOT OLD.factura_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'factura_id' AND json_extract(valor_anterior, '$') IS OLD.factura_id
        AND json_extract(valor_nuevo, '$') IS NEW.factura_id))
    OR (NEW.linea_id IS NOT OLD.linea_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'linea_id' AND json_extract(valor_anterior, '$') IS OLD.linea_id
        AND json_extract(valor_nuevo, '$') IS NEW.linea_id))
    OR (NEW.objeto_id IS NOT OLD.objeto_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'objeto_id' AND json_extract(valor_anterior, '$') IS OLD.objeto_id
        AND json_extract(valor_nuevo, '$') IS NEW.objeto_id))
    OR (NEW.recurso_id IS NOT OLD.recurso_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'recurso_id' AND json_extract(valor_anterior, '$') IS OLD.recurso_id
        AND json_extract(valor_nuevo, '$') IS NEW.recurso_id))
    OR (NEW.orden_compra_id IS NOT OLD.orden_compra_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'orden_compra_id' AND json_extract(valor_anterior, '$') IS OLD.orden_compra_id
        AND json_extract(valor_nuevo, '$') IS NEW.orden_compra_id))
    OR (NEW.descripcion IS NOT OLD.descripcion AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'descripcion' AND json_extract(valor_anterior, '$') IS OLD.descripcion
        AND json_extract(valor_nuevo, '$') IS NEW.descripcion))
    OR (NEW.fecha_inicio IS NOT OLD.fecha_inicio AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fecha_inicio' AND json_extract(valor_anterior, '$') IS OLD.fecha_inicio
        AND json_extract(valor_nuevo, '$') IS NEW.fecha_inicio))
    OR (NEW.fecha_fin IS NOT OLD.fecha_fin AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fecha_fin' AND json_extract(valor_anterior, '$') IS OLD.fecha_fin
        AND json_extract(valor_nuevo, '$') IS NEW.fecha_fin))
    OR (NEW.semana_iso IS NOT OLD.semana_iso AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'semana_iso' AND json_extract(valor_anterior, '$') IS OLD.semana_iso
        AND json_extract(valor_nuevo, '$') IS NEW.semana_iso))
    OR (NEW.horas_mil IS NOT OLD.horas_mil AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'horas_mil' AND json_extract(valor_anterior, '$') IS OLD.horas_mil
        AND json_extract(valor_nuevo, '$') IS NEW.horas_mil))
    OR (NEW.tarifa_e4 IS NOT OLD.tarifa_e4 AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tarifa_e4' AND json_extract(valor_anterior, '$') IS OLD.tarifa_e4
        AND json_extract(valor_nuevo, '$') IS NEW.tarifa_e4))
    OR (NEW.importe_cent IS NOT OLD.importe_cent AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'importe_cent' AND json_extract(valor_anterior, '$') IS OLD.importe_cent
        AND json_extract(valor_nuevo, '$') IS NEW.importe_cent))
    OR (NEW.tipo_servicio IS NOT OLD.tipo_servicio AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tipo_servicio' AND json_extract(valor_anterior, '$') IS OLD.tipo_servicio
        AND json_extract(valor_nuevo, '$') IS NEW.tipo_servicio))
    OR (NEW.tipo_turno IS NOT OLD.tipo_turno AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tipo_turno' AND json_extract(valor_anterior, '$') IS OLD.tipo_turno
        AND json_extract(valor_nuevo, '$') IS NEW.tipo_turno))
    OR (NEW.facturable IS NOT OLD.facturable AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'facturable' AND json_extract(valor_anterior, '$') IS OLD.facturable
        AND json_extract(valor_nuevo, '$') IS NEW.facturable))
    OR (NEW.retirada_en IS NOT OLD.retirada_en AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_imputacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'retirada_en' AND json_extract(valor_anterior, '$') IS OLD.retirada_en
        AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'factura_imputacion es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER factura_imputacion_sin_delete BEFORE DELETE ON factura_imputacion
BEGIN SELECT RAISE(ABORT, 'factura_imputacion no se borra: una fila se retira o se desactiva'); END;

CREATE TRIGGER factura_iva_guarda_insert BEFORE INSERT ON factura_iva
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.factura_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = 0
        AND campo = 'factura_id' AND json_extract(valor_nuevo, '$') IS NEW.factura_id))
    OR (NEW.tipo_iva_pb IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tipo_iva_pb' AND json_extract(valor_nuevo, '$') IS NEW.tipo_iva_pb))
    OR (NEW.tratamiento IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tratamiento' AND json_extract(valor_nuevo, '$') IS NEW.tratamiento))
    OR (NEW.base_cent IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = 0
        AND campo = 'base_cent' AND json_extract(valor_nuevo, '$') IS NEW.base_cent))
    OR (NEW.cuota_cent IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = 0
        AND campo = 'cuota_cent' AND json_extract(valor_nuevo, '$') IS NEW.cuota_cent))
    OR (NEW.cuota_autoliquidada_cent IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = 0
        AND campo = 'cuota_autoliquidada_cent' AND json_extract(valor_nuevo, '$') IS NEW.cuota_autoliquidada_cent))
    OR (NEW.deducible IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = 0
        AND campo = 'deducible' AND json_extract(valor_nuevo, '$') IS NEW.deducible))
    OR (NEW.rubrica IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = 0
        AND campo = 'rubrica' AND json_extract(valor_nuevo, '$') IS NEW.rubrica))
    OR (NEW.retirada_en IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = 0
        AND campo = 'retirada_en' AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'factura_iva es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER factura_iva_guarda_update BEFORE UPDATE ON factura_iva
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.factura_id IS NOT OLD.factura_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'factura_id' AND json_extract(valor_anterior, '$') IS OLD.factura_id
        AND json_extract(valor_nuevo, '$') IS NEW.factura_id))
    OR (NEW.tipo_iva_pb IS NOT OLD.tipo_iva_pb AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tipo_iva_pb' AND json_extract(valor_anterior, '$') IS OLD.tipo_iva_pb
        AND json_extract(valor_nuevo, '$') IS NEW.tipo_iva_pb))
    OR (NEW.tratamiento IS NOT OLD.tratamiento AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tratamiento' AND json_extract(valor_anterior, '$') IS OLD.tratamiento
        AND json_extract(valor_nuevo, '$') IS NEW.tratamiento))
    OR (NEW.base_cent IS NOT OLD.base_cent AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'base_cent' AND json_extract(valor_anterior, '$') IS OLD.base_cent
        AND json_extract(valor_nuevo, '$') IS NEW.base_cent))
    OR (NEW.cuota_cent IS NOT OLD.cuota_cent AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'cuota_cent' AND json_extract(valor_anterior, '$') IS OLD.cuota_cent
        AND json_extract(valor_nuevo, '$') IS NEW.cuota_cent))
    OR (NEW.cuota_autoliquidada_cent IS NOT OLD.cuota_autoliquidada_cent AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'cuota_autoliquidada_cent' AND json_extract(valor_anterior, '$') IS OLD.cuota_autoliquidada_cent
        AND json_extract(valor_nuevo, '$') IS NEW.cuota_autoliquidada_cent))
    OR (NEW.deducible IS NOT OLD.deducible AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'deducible' AND json_extract(valor_anterior, '$') IS OLD.deducible
        AND json_extract(valor_nuevo, '$') IS NEW.deducible))
    OR (NEW.rubrica IS NOT OLD.rubrica AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'rubrica' AND json_extract(valor_anterior, '$') IS OLD.rubrica
        AND json_extract(valor_nuevo, '$') IS NEW.rubrica))
    OR (NEW.retirada_en IS NOT OLD.retirada_en AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_iva' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'retirada_en' AND json_extract(valor_anterior, '$') IS OLD.retirada_en
        AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'factura_iva es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER factura_iva_sin_delete BEFORE DELETE ON factura_iva
BEGIN SELECT RAISE(ABORT, 'factura_iva no se borra: una fila se retira o se desactiva'); END;

CREATE TRIGGER factura_referencia_guarda_insert BEFORE INSERT ON factura_referencia
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_referencia' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.factura_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_referencia' AND fila_id = NEW.id AND rev = 0
        AND campo = 'factura_id' AND json_extract(valor_nuevo, '$') IS NEW.factura_id))
    OR (NEW.linea_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_referencia' AND fila_id = NEW.id AND rev = 0
        AND campo = 'linea_id' AND json_extract(valor_nuevo, '$') IS NEW.linea_id))
    OR (NEW.etiqueta_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_referencia' AND fila_id = NEW.id AND rev = 0
        AND campo = 'etiqueta_doc' AND json_extract(valor_nuevo, '$') IS NEW.etiqueta_doc))
    OR (NEW.valor_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_referencia' AND fila_id = NEW.id AND rev = 0
        AND campo = 'valor_doc' AND json_extract(valor_nuevo, '$') IS NEW.valor_doc))
    OR (NEW.valor_norm IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_referencia' AND fila_id = NEW.id AND rev = 0
        AND campo = 'valor_norm' AND json_extract(valor_nuevo, '$') IS NEW.valor_norm))
    OR (NEW.clase IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_referencia' AND fila_id = NEW.id AND rev = 0
        AND campo = 'clase' AND json_extract(valor_nuevo, '$') IS NEW.clase))
    OR (NEW.orden_compra_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_referencia' AND fila_id = NEW.id AND rev = 0
        AND campo = 'orden_compra_id' AND json_extract(valor_nuevo, '$') IS NEW.orden_compra_id))
    OR (NEW.retirada_en IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_referencia' AND fila_id = NEW.id AND rev = 0
        AND campo = 'retirada_en' AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'factura_referencia es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER factura_referencia_guarda_update BEFORE UPDATE ON factura_referencia
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_referencia' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.factura_id IS NOT OLD.factura_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_referencia' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'factura_id' AND json_extract(valor_anterior, '$') IS OLD.factura_id
        AND json_extract(valor_nuevo, '$') IS NEW.factura_id))
    OR (NEW.linea_id IS NOT OLD.linea_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_referencia' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'linea_id' AND json_extract(valor_anterior, '$') IS OLD.linea_id
        AND json_extract(valor_nuevo, '$') IS NEW.linea_id))
    OR (NEW.etiqueta_doc IS NOT OLD.etiqueta_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_referencia' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'etiqueta_doc' AND json_extract(valor_anterior, '$') IS OLD.etiqueta_doc
        AND json_extract(valor_nuevo, '$') IS NEW.etiqueta_doc))
    OR (NEW.valor_doc IS NOT OLD.valor_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_referencia' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'valor_doc' AND json_extract(valor_anterior, '$') IS OLD.valor_doc
        AND json_extract(valor_nuevo, '$') IS NEW.valor_doc))
    OR (NEW.valor_norm IS NOT OLD.valor_norm AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_referencia' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'valor_norm' AND json_extract(valor_anterior, '$') IS OLD.valor_norm
        AND json_extract(valor_nuevo, '$') IS NEW.valor_norm))
    OR (NEW.clase IS NOT OLD.clase AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_referencia' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'clase' AND json_extract(valor_anterior, '$') IS OLD.clase
        AND json_extract(valor_nuevo, '$') IS NEW.clase))
    OR (NEW.orden_compra_id IS NOT OLD.orden_compra_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_referencia' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'orden_compra_id' AND json_extract(valor_anterior, '$') IS OLD.orden_compra_id
        AND json_extract(valor_nuevo, '$') IS NEW.orden_compra_id))
    OR (NEW.retirada_en IS NOT OLD.retirada_en AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_referencia' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'retirada_en' AND json_extract(valor_anterior, '$') IS OLD.retirada_en
        AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'factura_referencia es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER factura_referencia_sin_delete BEFORE DELETE ON factura_referencia
BEGIN SELECT RAISE(ABORT, 'factura_referencia no se borra: una fila se retira o se desactiva'); END;

CREATE TRIGGER factura_relacion_guarda_insert BEFORE INSERT ON factura_relacion
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_relacion' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.origen_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_relacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'origen_id' AND json_extract(valor_nuevo, '$') IS NEW.origen_id))
    OR (NEW.destino_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_relacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'destino_id' AND json_extract(valor_nuevo, '$') IS NEW.destino_id))
    OR (NEW.tipo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_relacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'tipo' AND json_extract(valor_nuevo, '$') IS NEW.tipo))
    OR (NEW.importe_cent IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_relacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'importe_cent' AND json_extract(valor_nuevo, '$') IS NEW.importe_cent))
    OR (NEW.estado IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_relacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'estado' AND json_extract(valor_nuevo, '$') IS NEW.estado))
    OR (NEW.fuente IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_relacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fuente' AND json_extract(valor_nuevo, '$') IS NEW.fuente))
    OR (NEW.evidencia_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_relacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'evidencia_doc' AND json_extract(valor_nuevo, '$') IS NEW.evidencia_doc))
    OR (NEW.retirada_en IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_relacion' AND fila_id = NEW.id AND rev = 0
        AND campo = 'retirada_en' AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'factura_relacion es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER factura_relacion_guarda_update BEFORE UPDATE ON factura_relacion
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_relacion' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.origen_id IS NOT OLD.origen_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_relacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'origen_id' AND json_extract(valor_anterior, '$') IS OLD.origen_id
        AND json_extract(valor_nuevo, '$') IS NEW.origen_id))
    OR (NEW.destino_id IS NOT OLD.destino_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_relacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'destino_id' AND json_extract(valor_anterior, '$') IS OLD.destino_id
        AND json_extract(valor_nuevo, '$') IS NEW.destino_id))
    OR (NEW.tipo IS NOT OLD.tipo AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_relacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'tipo' AND json_extract(valor_anterior, '$') IS OLD.tipo
        AND json_extract(valor_nuevo, '$') IS NEW.tipo))
    OR (NEW.importe_cent IS NOT OLD.importe_cent AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_relacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'importe_cent' AND json_extract(valor_anterior, '$') IS OLD.importe_cent
        AND json_extract(valor_nuevo, '$') IS NEW.importe_cent))
    OR (NEW.estado IS NOT OLD.estado AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_relacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'estado' AND json_extract(valor_anterior, '$') IS OLD.estado
        AND json_extract(valor_nuevo, '$') IS NEW.estado))
    OR (NEW.fuente IS NOT OLD.fuente AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_relacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fuente' AND json_extract(valor_anterior, '$') IS OLD.fuente
        AND json_extract(valor_nuevo, '$') IS NEW.fuente))
    OR (NEW.evidencia_doc IS NOT OLD.evidencia_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_relacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'evidencia_doc' AND json_extract(valor_anterior, '$') IS OLD.evidencia_doc
        AND json_extract(valor_nuevo, '$') IS NEW.evidencia_doc))
    OR (NEW.retirada_en IS NOT OLD.retirada_en AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_relacion' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'retirada_en' AND json_extract(valor_anterior, '$') IS OLD.retirada_en
        AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'factura_relacion es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER factura_relacion_sin_delete BEFORE DELETE ON factura_relacion
BEGIN SELECT RAISE(ABORT, 'factura_relacion no se borra: una fila se retira o se desactiva'); END;
