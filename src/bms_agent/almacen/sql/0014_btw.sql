-- Migracion 0014 (paso 11 de la V1): el BTW. El estado de cada trimestre, la hoja
-- de trabajo que se reviso y se presento, y lo que se declaro de cada factura.
--
-- Un fichero aplicado no se edita nunca (ver 0001). Lo que haga falta
-- despues va en 0015, 0016...
--
-- Lo que esta migracion garantiza (spec §5.G, §7 C4, arquitectura.md regla 5):
--   - La declaracion se prepara, no se presenta: nada aqui habla con la
--     Belastingdienst. periodo_btw apunta lo que hizo una persona fuera.
--   - El estado de un trimestre (abierto, listo_revision, presentado) lo pone
--     una persona activa con gestionar_btw, en su propia orden. Un trimestre
--     sin fila esta abierto.
--   - Se presenta desde listo_revision, con la referencia de la presentacion,
--     lo declarado y la hoja de trabajo que se reviso: su sha256 es el de una
--     hoja guardada de ese trimestre. Presentado no cambia nunca mas: ni
--     vuelve atras ni se toca ninguna columna.
--   - hoja_btw: el texto entero de cada hoja de trabajo que se marco lista o se
--     presento, con su sha256 (db verificar lo vuelve a calcular). Solo
--     escritura.
--   - periodo_btw_declarada: lo que se declaro de cada factura al presentar
--     (su huella de IVA), en el evento de la presentacion y en ningun otro.
--     Es contra lo que C4 compara despues: una factura que llega tarde a un
--     trimestre presentado, o que cambia despues, se ve. Solo escritura.
--   - v_btw_linea: las lineas de IVA de cada factura que cuenta (ni anulada,
--     ni fusionada, ni sustituida), con su trimestre. Lo que dice el desglose
--     (factura_iva) o, sin el, la cabecera (una factura v1 no tiene
--     desglose). La rubrica de la declaracion no esta aqui: sale de
--     config/btw.yaml, que la base no lee (btw.py la aplica).
--
-- Clases de tabla (spec.md §4):
--   periodo_btw: CONTROLADA (rev y guarda generada con
--     scripts/generar_guardas.py), escrita por btw.py, como la excepcion.
--   hoja_btw, periodo_btw_declarada: SOLO ESCRITURA, evidencia con su evento
--     (almacen/evidencia.py).

-- ------------------------------------------------------------- hoja_btw

-- Una hoja de trabajo tal como se genero: CSV con separador ";" y BOM. Su
-- sha256 es el de los bytes del texto en UTF-8, los mismos que se exportan.
CREATE TABLE hoja_btw (
    id          INTEGER PRIMARY KEY,
    ano         INTEGER NOT NULL CHECK (ano BETWEEN 2000 AND 9999),
    trimestre   INTEGER NOT NULL CHECK (trimestre BETWEEN 1 AND 4),
    sha256      TEXT NOT NULL UNIQUE CHECK (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
    contenido   TEXT NOT NULL CHECK (length(contenido) > 0),
    generada_en TEXT NOT NULL CHECK (datetime(generada_en) IS NOT NULL),
    usuario_id  INTEGER NOT NULL REFERENCES usuario(id),
    evento_id   INTEGER NOT NULL REFERENCES evento(id)
) STRICT;

CREATE TRIGGER hoja_btw_sin_update BEFORE UPDATE ON hoja_btw
BEGIN SELECT RAISE(ABORT, 'hoja_btw es de solo escritura: una hoja guardada no cambia'); END;

CREATE TRIGGER hoja_btw_sin_delete BEFORE DELETE ON hoja_btw
BEGIN SELECT RAISE(ABORT, 'hoja_btw es de solo escritura: una hoja guardada no se borra'); END;

-- La guarda una persona activa con gestionar_btw, en su propia orden: el
-- evento en curso es el suyo, btw_hoja_guardada.
CREATE TRIGGER hoja_btw_de_persona BEFORE INSERT ON hoja_btw
WHEN NOT EXISTS (
        SELECT 1 FROM evento AS e
        JOIN usuario AS u ON u.id = e.usuario_id
        JOIN usuario_rol AS ur ON ur.usuario_id = u.id
        JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id
        WHERE e.id = (SELECT max(id) FROM evento) AND e.id = NEW.evento_id
          AND e.tipo = 'btw_hoja_guardada' AND e.actor = e.usuario_id
          AND e.usuario_id = NEW.usuario_id
          AND u.es_sistema = 0 AND u.activo = 1 AND rp.permiso = 'gestionar_btw'
          AND ur.desde <= e.en AND (ur.hasta IS NULL OR ur.hasta > e.en))
BEGIN SELECT RAISE(ABORT, 'una hoja de trabajo del BTW la guarda una persona con gestionar_btw, en su propia orden'); END;

-- ------------------------------------------------------------- periodo_btw

CREATE TABLE periodo_btw (
    id                      INTEGER PRIMARY KEY,
    ano                     INTEGER NOT NULL CHECK (ano BETWEEN 2000 AND 9999),
    trimestre               INTEGER NOT NULL CHECK (trimestre BETWEEN 1 AND 4),
    inicio                  TEXT NOT NULL CHECK (date(inicio) IS inicio),
    fin                     TEXT NOT NULL CHECK (date(fin) IS fin),
    limite_presentacion     TEXT NOT NULL CHECK (date(limite_presentacion) IS limite_presentacion),
    limite_pago             TEXT NOT NULL CHECK (date(limite_pago) IS limite_pago),
    estado                  TEXT NOT NULL CHECK (estado IN ('abierto', 'listo_revision', 'presentado')),
    listo_en                TEXT CHECK (listo_en IS NULL OR datetime(listo_en) IS NOT NULL),
    listo_por               INTEGER REFERENCES usuario(id),
    presentado_en           TEXT CHECK (presentado_en IS NULL OR date(presentado_en) IS presentado_en),
    presentado_por          INTEGER REFERENCES usuario(id),
    referencia_presentacion TEXT,
    importe_declarado_cent  INTEGER,
    hoja_id                 INTEGER REFERENCES hoja_btw(id),
    hoja_sha256             TEXT CHECK (hoja_sha256 IS NULL OR (length(hoja_sha256) = 64
                                        AND hoja_sha256 NOT GLOB '*[^0-9a-f]*')),
    nota                    TEXT,
    rev                     INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0),
    UNIQUE (ano, trimestre),
    -- El trimestre natural: del dia 1 de su primer mes al ultimo de su tercero.
    CHECK (inicio = printf('%04d-%02d-01', ano, (trimestre - 1) * 3 + 1)),
    CHECK (fin = date(inicio, '+3 months', '-1 day')),
    CHECK (limite_presentacion > fin AND limite_pago > fin),
    -- Abierto no tiene hoja ni nada de una presentacion; listo_revision tiene
    -- la hoja que se reviso y quien la marco; presentado, ademas, la
    -- referencia, lo declarado, quien y el dia, que es posterior al trimestre.
    CHECK (estado <> 'abierto' OR (hoja_id IS NULL AND hoja_sha256 IS NULL
                                   AND listo_en IS NULL AND listo_por IS NULL)),
    CHECK (estado = 'abierto' OR (hoja_id IS NOT NULL AND hoja_sha256 IS NOT NULL
                                  AND listo_en IS NOT NULL AND listo_por IS NOT NULL)),
    CHECK (estado = 'presentado' OR (presentado_en IS NULL AND presentado_por IS NULL
                                     AND referencia_presentacion IS NULL
                                     AND importe_declarado_cent IS NULL)),
    CHECK (estado <> 'presentado' OR (presentado_en IS NOT NULL AND presentado_por IS NOT NULL
                                      AND length(trim(referencia_presentacion)) > 0
                                      AND importe_declarado_cent IS NOT NULL
                                      AND presentado_en > fin))
) STRICT;

-- El estado de un trimestre lo pone una persona activa con gestionar_btw, en
-- su propia orden: el evento en curso es suyo (actor y usuario ella). Al
-- darlo de alta y en cada cambio.
CREATE TRIGGER periodo_btw_de_persona_insert BEFORE INSERT ON periodo_btw
WHEN NOT EXISTS (
        SELECT 1 FROM evento AS e
        JOIN usuario AS u ON u.id = e.usuario_id
        JOIN usuario_rol AS ur ON ur.usuario_id = u.id
        JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id
        WHERE e.id = (SELECT max(id) FROM evento) AND e.actor = e.usuario_id
          AND u.es_sistema = 0 AND u.activo = 1 AND rp.permiso = 'gestionar_btw'
          AND ur.desde <= e.en AND (ur.hasta IS NULL OR ur.hasta > e.en))
BEGIN SELECT RAISE(ABORT, 'el estado del BTW lo pone una persona con gestionar_btw, en su propia orden'); END;

CREATE TRIGGER periodo_btw_de_persona_update BEFORE UPDATE ON periodo_btw
WHEN NOT EXISTS (
        SELECT 1 FROM evento AS e
        JOIN usuario AS u ON u.id = e.usuario_id
        JOIN usuario_rol AS ur ON ur.usuario_id = u.id
        JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id
        WHERE e.id = (SELECT max(id) FROM evento) AND e.actor = e.usuario_id
          AND u.es_sistema = 0 AND u.activo = 1 AND rp.permiso = 'gestionar_btw'
          AND ur.desde <= e.en AND (ur.hasta IS NULL OR ur.hasta > e.en))
BEGIN SELECT RAISE(ABORT, 'el estado del BTW lo pone una persona con gestionar_btw, en su propia orden'); END;

-- Presentado es irreversible: no vuelve atras y no se toca nada.
CREATE TRIGGER periodo_btw_presentado_no_cambia BEFORE UPDATE ON periodo_btw
WHEN OLD.estado = 'presentado'
BEGIN SELECT RAISE(ABORT, 'un trimestre presentado no cambia: la presentacion es irreversible'); END;

-- Nace abierto o listo para revision; nunca presentado.
CREATE TRIGGER periodo_btw_nace BEFORE INSERT ON periodo_btw
WHEN NEW.estado = 'presentado'
BEGIN SELECT RAISE(ABORT, 'un trimestre se presenta desde listo_revision, no al darlo de alta'); END;

-- La hoja de un trimestre listo o presentado es una hoja guardada de ese
-- trimestre, con ese sha256, y la marca quien firma la orden. Lo que ya esta
-- presentado no cambia (periodo_btw_presentado_no_cambia).
CREATE TRIGGER periodo_btw_hoja_insert BEFORE INSERT ON periodo_btw
WHEN NEW.estado = 'listo_revision' AND (
       NOT EXISTS (SELECT 1 FROM hoja_btw WHERE id = NEW.hoja_id AND sha256 = NEW.hoja_sha256
                   AND ano = NEW.ano AND trimestre = NEW.trimestre)
    OR NEW.listo_por IS NOT (SELECT usuario_id FROM evento WHERE id = (SELECT max(id) FROM evento)))
BEGIN SELECT RAISE(ABORT, 'la hoja de un trimestre listo es una hoja guardada de ese trimestre, y la marca quien firma'); END;

CREATE TRIGGER periodo_btw_hoja_update BEFORE UPDATE ON periodo_btw
WHEN OLD.estado <> 'presentado' AND NEW.estado <> 'abierto' AND (
       NOT EXISTS (SELECT 1 FROM hoja_btw WHERE id = NEW.hoja_id AND sha256 = NEW.hoja_sha256
                   AND ano = NEW.ano AND trimestre = NEW.trimestre)
    OR (NEW.estado = 'listo_revision' AND NEW.listo_por IS NOT (
            SELECT usuario_id FROM evento WHERE id = (SELECT max(id) FROM evento))))
BEGIN SELECT RAISE(ABORT, 'la hoja de un trimestre listo o presentado es una hoja guardada de ese trimestre, y la marca quien firma'); END;

-- Se presenta desde listo_revision, con la misma hoja que se reviso, y lo
-- anota quien firma la orden. Lo que ya esta presentado lo para
-- periodo_btw_presentado_no_cambia. El trimestre no cambia de ano ni de numero.
CREATE TRIGGER periodo_btw_presentar BEFORE UPDATE ON periodo_btw
WHEN NEW.estado = 'presentado' AND OLD.estado <> 'presentado' AND (
       OLD.estado <> 'listo_revision'
    OR NEW.hoja_id IS NOT OLD.hoja_id OR NEW.hoja_sha256 IS NOT OLD.hoja_sha256
    OR NEW.listo_por IS NOT OLD.listo_por OR NEW.listo_en IS NOT OLD.listo_en
    OR NEW.presentado_por IS NOT (SELECT usuario_id FROM evento WHERE id = (SELECT max(id) FROM evento)))
BEGIN SELECT RAISE(ABORT, 'un trimestre se presenta desde listo_revision, con la hoja que se reviso, y lo anota quien firma'); END;

CREATE TRIGGER periodo_btw_identidad BEFORE UPDATE OF ano, trimestre, inicio, fin ON periodo_btw
WHEN NEW.ano IS NOT OLD.ano OR NEW.trimestre IS NOT OLD.trimestre
  OR NEW.inicio IS NOT OLD.inicio OR NEW.fin IS NOT OLD.fin
BEGIN SELECT RAISE(ABORT, 'un periodo del BTW no cambia de trimestre'); END;

-- ------------------------------------------------------------- periodo_btw_declarada

-- Lo que se declaro de cada factura del trimestre al presentarlo: su huella
-- de IVA (reglas/iva.huella_iva: tratamiento, tipo, base y cuota de cada
-- linea, y de donde es la contraparte en el IVA trasladado) y su base y su
-- cuota. Solo en el evento de la presentacion de ese periodo.
CREATE TABLE periodo_btw_declarada (
    id         INTEGER PRIMARY KEY,
    periodo_id INTEGER NOT NULL REFERENCES periodo_btw(id),
    factura_id INTEGER NOT NULL REFERENCES factura(id),
    huella     TEXT NOT NULL CHECK (length(huella) = 64 AND huella NOT GLOB '*[^0-9a-f]*'),
    base_cent  INTEGER,
    cuota_cent INTEGER,
    evento_id  INTEGER NOT NULL REFERENCES evento(id),
    UNIQUE (periodo_id, factura_id)
) STRICT;

CREATE INDEX periodo_btw_declarada_factura ON periodo_btw_declarada (factura_id);

CREATE TRIGGER periodo_btw_declarada_sin_update BEFORE UPDATE ON periodo_btw_declarada
BEGIN SELECT RAISE(ABORT, 'periodo_btw_declarada es de solo escritura: lo declarado no cambia'); END;

CREATE TRIGGER periodo_btw_declarada_sin_delete BEFORE DELETE ON periodo_btw_declarada
BEGIN SELECT RAISE(ABORT, 'periodo_btw_declarada es de solo escritura: lo declarado no se borra'); END;

CREATE TRIGGER periodo_btw_declarada_al_presentar BEFORE INSERT ON periodo_btw_declarada
WHEN NOT EXISTS (
        SELECT 1 FROM evento AS e JOIN periodo_btw AS p ON p.id = NEW.periodo_id
        WHERE e.id = (SELECT max(id) FROM evento) AND e.id = NEW.evento_id
          AND e.tipo = 'btw_presentacion_anotada' AND e.tabla = 'periodo_btw'
          AND e.fila_id = p.id AND p.estado = 'presentado')
BEGIN SELECT RAISE(ABORT, 'lo declarado de cada factura se apunta solo en el evento de la presentacion de su trimestre'); END;

-- ------------------------------------------------------------- v_btw_linea

-- Las lineas de IVA de las facturas que cuentan (v_iva_vigente), con su
-- trimestre por la fecha de la factura (factuurstelsel). Una factura con
-- desglose da una linea por fila viva de factura_iva (el tratamiento de la
-- fila o, si no lo dice, el de la factura); una sin desglose, una linea con la
-- cabecera. moneda_doc dice si esta en otra moneda: entonces sus importes
-- estan vacios (X1) y no entra en ninguna suma (btw.py).
CREATE VIEW v_btw_linea AS
SELECT f.factura_id, v.id AS factura_iva_id, f.sentido, f.tipo, f.fecha_factura, f.ano,
       f.trimestre, coalesce(v.tratamiento, f.tratamiento_iva) AS tratamiento,
       v.tipo_iva_pb, v.base_cent, v.cuota_cent, x.moneda_doc
FROM v_iva_vigente AS f
JOIN factura_iva AS v ON v.factura_id = f.factura_id AND v.retirada_en IS NULL
JOIN factura AS x ON x.id = f.factura_id
UNION ALL
SELECT f.factura_id, NULL AS factura_iva_id, f.sentido, f.tipo, f.fecha_factura, f.ano,
       f.trimestre, f.tratamiento_iva AS tratamiento, f.tipo_iva_pb, f.base_cent,
       f.iva_cent AS cuota_cent, x.moneda_doc
FROM v_iva_vigente AS f
JOIN factura AS x ON x.id = f.factura_id
WHERE NOT EXISTS (SELECT 1 FROM factura_iva AS v
                  WHERE v.factura_id = f.factura_id AND v.retirada_en IS NULL);

-- ------------------------------------------------------------- guardas de periodo_btw

CREATE TRIGGER periodo_btw_guarda_insert BEFORE INSERT ON periodo_btw
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.ano IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = 0
        AND campo = 'ano' AND json_extract(valor_nuevo, '$') IS NEW.ano))
    OR (NEW.trimestre IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = 0
        AND campo = 'trimestre' AND json_extract(valor_nuevo, '$') IS NEW.trimestre))
    OR (NEW.inicio IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = 0
        AND campo = 'inicio' AND json_extract(valor_nuevo, '$') IS NEW.inicio))
    OR (NEW.fin IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fin' AND json_extract(valor_nuevo, '$') IS NEW.fin))
    OR (NEW.limite_presentacion IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = 0
        AND campo = 'limite_presentacion' AND json_extract(valor_nuevo, '$') IS NEW.limite_presentacion))
    OR (NEW.limite_pago IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = 0
        AND campo = 'limite_pago' AND json_extract(valor_nuevo, '$') IS NEW.limite_pago))
    OR (NEW.estado IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = 0
        AND campo = 'estado' AND json_extract(valor_nuevo, '$') IS NEW.estado))
    OR (NEW.listo_en IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = 0
        AND campo = 'listo_en' AND json_extract(valor_nuevo, '$') IS NEW.listo_en))
    OR (NEW.listo_por IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = 0
        AND campo = 'listo_por' AND json_extract(valor_nuevo, '$') IS NEW.listo_por))
    OR (NEW.presentado_en IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = 0
        AND campo = 'presentado_en' AND json_extract(valor_nuevo, '$') IS NEW.presentado_en))
    OR (NEW.presentado_por IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = 0
        AND campo = 'presentado_por' AND json_extract(valor_nuevo, '$') IS NEW.presentado_por))
    OR (NEW.referencia_presentacion IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = 0
        AND campo = 'referencia_presentacion' AND json_extract(valor_nuevo, '$') IS NEW.referencia_presentacion))
    OR (NEW.importe_declarado_cent IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = 0
        AND campo = 'importe_declarado_cent' AND json_extract(valor_nuevo, '$') IS NEW.importe_declarado_cent))
    OR (NEW.hoja_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = 0
        AND campo = 'hoja_id' AND json_extract(valor_nuevo, '$') IS NEW.hoja_id))
    OR (NEW.hoja_sha256 IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = 0
        AND campo = 'hoja_sha256' AND json_extract(valor_nuevo, '$') IS NEW.hoja_sha256))
    OR (NEW.nota IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = 0
        AND campo = 'nota' AND json_extract(valor_nuevo, '$') IS NEW.nota))
BEGIN SELECT RAISE(ABORT, 'periodo_btw es una tabla controlada: solo la escribe btw.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER periodo_btw_guarda_update BEFORE UPDATE ON periodo_btw
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.ano IS NOT OLD.ano AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'ano' AND json_extract(valor_anterior, '$') IS OLD.ano
        AND json_extract(valor_nuevo, '$') IS NEW.ano))
    OR (NEW.trimestre IS NOT OLD.trimestre AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'trimestre' AND json_extract(valor_anterior, '$') IS OLD.trimestre
        AND json_extract(valor_nuevo, '$') IS NEW.trimestre))
    OR (NEW.inicio IS NOT OLD.inicio AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'inicio' AND json_extract(valor_anterior, '$') IS OLD.inicio
        AND json_extract(valor_nuevo, '$') IS NEW.inicio))
    OR (NEW.fin IS NOT OLD.fin AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fin' AND json_extract(valor_anterior, '$') IS OLD.fin
        AND json_extract(valor_nuevo, '$') IS NEW.fin))
    OR (NEW.limite_presentacion IS NOT OLD.limite_presentacion AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'limite_presentacion' AND json_extract(valor_anterior, '$') IS OLD.limite_presentacion
        AND json_extract(valor_nuevo, '$') IS NEW.limite_presentacion))
    OR (NEW.limite_pago IS NOT OLD.limite_pago AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'limite_pago' AND json_extract(valor_anterior, '$') IS OLD.limite_pago
        AND json_extract(valor_nuevo, '$') IS NEW.limite_pago))
    OR (NEW.estado IS NOT OLD.estado AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'estado' AND json_extract(valor_anterior, '$') IS OLD.estado
        AND json_extract(valor_nuevo, '$') IS NEW.estado))
    OR (NEW.listo_en IS NOT OLD.listo_en AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'listo_en' AND json_extract(valor_anterior, '$') IS OLD.listo_en
        AND json_extract(valor_nuevo, '$') IS NEW.listo_en))
    OR (NEW.listo_por IS NOT OLD.listo_por AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'listo_por' AND json_extract(valor_anterior, '$') IS OLD.listo_por
        AND json_extract(valor_nuevo, '$') IS NEW.listo_por))
    OR (NEW.presentado_en IS NOT OLD.presentado_en AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'presentado_en' AND json_extract(valor_anterior, '$') IS OLD.presentado_en
        AND json_extract(valor_nuevo, '$') IS NEW.presentado_en))
    OR (NEW.presentado_por IS NOT OLD.presentado_por AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'presentado_por' AND json_extract(valor_anterior, '$') IS OLD.presentado_por
        AND json_extract(valor_nuevo, '$') IS NEW.presentado_por))
    OR (NEW.referencia_presentacion IS NOT OLD.referencia_presentacion AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'referencia_presentacion' AND json_extract(valor_anterior, '$') IS OLD.referencia_presentacion
        AND json_extract(valor_nuevo, '$') IS NEW.referencia_presentacion))
    OR (NEW.importe_declarado_cent IS NOT OLD.importe_declarado_cent AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'importe_declarado_cent' AND json_extract(valor_anterior, '$') IS OLD.importe_declarado_cent
        AND json_extract(valor_nuevo, '$') IS NEW.importe_declarado_cent))
    OR (NEW.hoja_id IS NOT OLD.hoja_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'hoja_id' AND json_extract(valor_anterior, '$') IS OLD.hoja_id
        AND json_extract(valor_nuevo, '$') IS NEW.hoja_id))
    OR (NEW.hoja_sha256 IS NOT OLD.hoja_sha256 AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'hoja_sha256' AND json_extract(valor_anterior, '$') IS OLD.hoja_sha256
        AND json_extract(valor_nuevo, '$') IS NEW.hoja_sha256))
    OR (NEW.nota IS NOT OLD.nota AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'periodo_btw' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'nota' AND json_extract(valor_anterior, '$') IS OLD.nota
        AND json_extract(valor_nuevo, '$') IS NEW.nota))
BEGIN SELECT RAISE(ABORT, 'periodo_btw es una tabla controlada: solo la escribe btw.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER periodo_btw_sin_delete BEFORE DELETE ON periodo_btw
BEGIN SELECT RAISE(ABORT, 'periodo_btw no se borra: una fila se retira o se desactiva'); END;

