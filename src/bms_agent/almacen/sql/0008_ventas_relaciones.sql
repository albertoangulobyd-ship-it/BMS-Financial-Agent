-- Migracion 0008 (paso 8 de la V1): facturas de venta, relaciones entre facturas
-- y lo que mueven en los saldos y los totales.
--
-- Un fichero aplicado no se edita nunca (ver 0001). Lo que haga falta
-- despues va en 0009, 0010...
--
-- Lo que esta migracion garantiza (spec §3.20, §5.D, §5.F y §7):
--   - Lo que un documento dice de otra factura (la que abona, corrige o
--     sustituye) es una cita (factura_cita), tal como la imprime: el numero y
--     la frase. Que una cita sea una relacion lo propone el codigo casando el
--     numero con una factura de la misma contraparte, nunca el modelo.
--   - Una relacion propuesta (por la extraccion o por Exact) no mueve nada.
--     Confirmarla o rechazarla es de una persona con anular_acreditar, en su
--     propia orden; una relacion manual la da de alta una persona y entra ya
--     confirmada. Una relacion confirmada no cambia de tipo ni de importe: se
--     retira (una persona) y se enlaza otra.
--   - Entre dos facturas hay como mucho una relacion viva (ni retirada ni
--     rechazada).
--   - El estado de pago de una factura puede ser "acreditada": los abonos
--     confirmados cubren lo que quedaba sin que se pagara nada.
--   - v_factura_saldo resta lo acreditado y dice que facturas estan
--     sustituidas; v_imputacion_vigente, v_iva_vigente, v_proveedor_totales y
--     v_cliente_totales leen solo lo que cuenta (spec §5, vistas).
--
-- Clases de tabla (spec.md §4):
--   factura_cita: CONTROLADA (rev y guarda generada con
--     scripts/generar_guardas.py), escrita por campos.py.
--   factura_estado: CACHE, rehecha aqui para admitir "acreditada".

-- ------------------------------------------------------------ factura_cita

-- Una factura que un documento nombra, tal como la nombra: su numero, su
-- fecha, la frase literal ("creditnota voor factuur 2026-0412") y la relacion
-- que enuncia (related_invoices de v2, o la factura relacionada de Exact). No
-- dice que factura es: eso lo decide relaciones.py casando el numero, y si no
-- hay ninguna, R1.
CREATE TABLE factura_cita (
    id           INTEGER PRIMARY KEY,
    factura_id   INTEGER NOT NULL REFERENCES factura(id),
    numero_doc   TEXT,
    numero_norm  TEXT,
    fecha_doc    TEXT CHECK (fecha_doc IS NULL OR date(fecha_doc) IS fecha_doc),
    relacion_doc TEXT CHECK (relacion_doc IS NULL OR relacion_doc IN (
        'credits', 'corrects', 'replaces', 'cancels', 'refers_to', 'unknown')),
    texto_doc    TEXT,
    retirada_en  TEXT CHECK (retirada_en IS NULL OR datetime(retirada_en) IS NOT NULL),
    rev          INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0)
) STRICT;

CREATE INDEX factura_cita_factura ON factura_cita (factura_id);
CREATE INDEX factura_cita_numero ON factura_cita (numero_norm);

-- ------------------------------------------------------------ factura_relacion

-- Entre dos facturas, una relacion viva como mucho: la misma pareja no se
-- propone dos veces ni se enlaza encima de otra (una rechazada o retirada no
-- cuenta).
CREATE UNIQUE INDEX factura_relacion_viva ON factura_relacion (origen_id, destino_id)
    WHERE retirada_en IS NULL AND estado <> 'rechazada';

-- Quien escribe una relacion. Una manual la da de alta una persona activa con
-- anular_acreditar, en su propia orden, y entra confirmada. Una de la
-- extraccion o de Exact la propone el sistema y entra como propuesta: lo que
-- lee un modelo o importa un fichero nunca mueve un saldo solo (decision 20).
CREATE TRIGGER factura_relacion_alta BEFORE INSERT ON factura_relacion
WHEN (NEW.fuente = 'manual' AND (NEW.estado IS NOT 'confirmada' OR NOT EXISTS (
        SELECT 1 FROM evento AS e
        JOIN usuario AS u ON u.id = e.usuario_id
        JOIN usuario_rol AS ur ON ur.usuario_id = u.id
        JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id
        WHERE e.id = (SELECT max(id) FROM evento) AND e.actor = e.usuario_id
          AND u.es_sistema = 0 AND u.activo = 1 AND rp.permiso = 'anular_acreditar'
          AND ur.desde <= e.en AND (ur.hasta IS NULL OR ur.hasta > e.en))))
  OR (NEW.fuente <> 'manual' AND (NEW.estado IS NOT 'propuesta'
        OR (SELECT actor FROM evento WHERE id = (SELECT max(id) FROM evento))
           NOT IN (SELECT id FROM usuario WHERE es_sistema = 1)))
BEGIN SELECT RAISE(ABORT, 'una relacion manual la confirma una persona con anular_acreditar al crearla; una de la extraccion o de Exact entra propuesta, escrita por el sistema'); END;

-- Confirmar, rechazar o retirar una relacion es de una persona activa con
-- anular_acreditar en ese instante, en su propia orden. Solo se decide una
-- propuesta, una vez. El sistema puede retirar una propuesta (la cita que la
-- traia ya no esta), nunca una relacion que una persona decidio.
CREATE TRIGGER factura_relacion_decision BEFORE UPDATE OF estado, retirada_en ON factura_relacion
WHEN (NEW.estado IS NOT OLD.estado OR NEW.retirada_en IS NOT OLD.retirada_en) AND (
        (NEW.estado IS NOT OLD.estado AND OLD.estado IS NOT 'propuesta')
     OR (OLD.retirada_en IS NOT NULL)
     OR ((NEW.estado IS NOT OLD.estado OR OLD.estado IS NOT 'propuesta') AND NOT EXISTS (
        SELECT 1 FROM evento AS e
        JOIN usuario AS u ON u.id = e.usuario_id
        JOIN usuario_rol AS ur ON ur.usuario_id = u.id
        JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id
        WHERE e.id = (SELECT max(id) FROM evento) AND e.actor = e.usuario_id
          AND u.es_sistema = 0 AND u.activo = 1 AND rp.permiso = 'anular_acreditar'
          AND ur.desde <= e.en AND (ur.hasta IS NULL OR ur.hasta > e.en))))
BEGIN SELECT RAISE(ABORT, 'confirmar, rechazar o retirar una relacion es de una persona con anular_acreditar, sobre una propuesta (o retirando una decidida), una vez'); END;

-- Lo decidido no cambia: una relacion confirmada o rechazada no cambia de
-- tipo ni de importe ni de facturas. Se retira y se enlaza otra.
CREATE TRIGGER factura_relacion_decidida_fija BEFORE UPDATE OF tipo, importe_cent, origen_id, destino_id ON factura_relacion
WHEN OLD.estado IS NOT 'propuesta' AND (
        NEW.tipo IS NOT OLD.tipo OR NEW.importe_cent IS NOT OLD.importe_cent
     OR NEW.origen_id IS NOT OLD.origen_id OR NEW.destino_id IS NOT OLD.destino_id)
BEGIN SELECT RAISE(ABORT, 'una relacion decidida no cambia: se retira y se enlaza otra'); END;

-- ------------------------------------------------------------ factura_estado

-- CACHE: se rehace con la primera pasada. Las mismas columnas que en la 0004,
-- con "acreditada" en el estado de pago.
DROP TABLE factura_estado;

CREATE TABLE factura_estado (
    factura_id       INTEGER PRIMARY KEY REFERENCES factura(id),
    estado_pago      TEXT CHECK (estado_pago IS NULL OR estado_pago = 'pendiente' OR estado_pago = 'vencida' OR estado_pago = 'pagada' OR estado_pago = 'anulada' OR estado_pago = 'acreditada'),
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

-- ------------------------------------------------------------ vistas

-- Lo que mueven las relaciones confirmadas de cada factura (sin depender de
-- hoy). acreditado_cent: lo que los abonos confirmados le quitan a una
-- factura, en su signo; o, en un abono, lo que ya se gasto de el (en el signo
-- del abono). Un abono sin importe en la relacion acredita entero. Una
-- factura sustituida o corregida por otra dice por cual (la de id menor si
-- fueran varias). Es lo mismo que reglas/relaciones.efectos, en SQL.
CREATE VIEW v_factura_relaciones AS
WITH vivas AS (
    SELECT r.origen_id, r.destino_id, r.tipo,
           coalesce(r.importe_cent, -o.total_cent) AS importe_cent
    FROM factura_relacion AS r JOIN factura AS o ON o.id = r.origen_id
    WHERE r.estado = 'confirmada' AND r.retirada_en IS NULL
),
movido AS (
    SELECT destino_id AS factura_id, importe_cent AS cent FROM vivas
    WHERE tipo IN ('acredita', 'anula')
    UNION ALL
    SELECT origen_id, -importe_cent FROM vivas WHERE tipo IN ('acredita', 'anula')
)
SELECT f.id AS factura_id,
       coalesce((SELECT sum(cent) FROM movido AS m WHERE m.factura_id = f.id), 0)
           AS acreditado_cent,
       (SELECT min(origen_id) FROM vivas AS v WHERE v.destino_id = f.id
          AND v.tipo IN ('sustituye', 'corrige')) AS sustituida_por,
       EXISTS (SELECT 1 FROM vivas AS v WHERE v.destino_id = f.id AND v.tipo = 'anula')
           AS anulada_por_abono
FROM factura AS f;

-- El saldo de cada factura: lo de la 0007 mas lo acreditado y si esta
-- sustituida. pendiente_cent es el total menos lo pagado (la fuente que
-- manda) menos lo acreditado. Si esta pagada o acreditada lo decide el codigo
-- con la tolerancia de la politica (reglas.pagos.saldo).
DROP VIEW v_factura_saldo;

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
),
pagado AS (
    SELECT s.*,
           CASE WHEN pagos_banco > 0 THEN 'banco' WHEN pagos_exact > 0 THEN 'exact'
                WHEN pagos_manual > 0 THEN 'manual' END AS fuente_pago,
           CASE WHEN pagos_banco > 0 THEN pagado_banco_cent WHEN pagos_exact > 0
                THEN pagado_exact_cent ELSE pagado_manual_cent END AS pagado_cent
    FROM sumas AS s
)
SELECT p.factura_id, p.sentido, p.total_cent, p.anulada, p.fusionada_en_id,
       p.pagado_banco_cent, p.pagos_banco, p.pagado_exact_cent, p.pagos_exact,
       p.pagado_manual_cent, p.pagos_manual, p.propuestas, p.fuente_pago, p.pagado_cent,
       r.acreditado_cent, r.sustituida_por, r.anulada_por_abono,
       p.total_cent - p.pagado_cent - r.acreditado_cent AS pendiente_cent
FROM pagado AS p JOIN v_factura_relaciones AS r ON r.factura_id = p.factura_id;

-- Las imputaciones activas de las facturas que cuentan (spec §5, vistas): ni
-- anuladas, ni fusionadas en otra, ni sustituidas o corregidas por otra. Lo que
-- no esta en euros ya no tiene importe (X1). De aqui sale lo gastado y lo
-- facturado por Objeto.
CREATE VIEW v_imputacion_vigente AS
SELECT i.*, f.sentido, f.proveedor_id, f.cliente_id, f.fecha_factura
FROM factura_imputacion AS i
JOIN factura AS f ON f.id = i.factura_id
JOIN v_factura_relaciones AS r ON r.factura_id = f.id
WHERE i.retirada_en IS NULL AND f.anulada = 0 AND f.fusionada_en_id IS NULL
  AND r.sustituida_por IS NULL;

-- El IVA que cuenta: el de cada factura que cuenta (ni anulada, ni fusionada en
-- otra, ni sustituida o corregida por otra), con el trimestre de su fecha. Un
-- abono cuenta en el suyo, en negativo: la original no se toca. El desglose por
-- tipo y la rubrica de la declaracion son del BTW (paso 11), que lee de aqui.
CREATE VIEW v_iva_vigente AS
SELECT f.id AS factura_id, f.sentido, f.tipo, f.fecha_factura,
       CAST(strftime('%Y', f.fecha_factura) AS INTEGER) AS ano,
       (CAST(strftime('%m', f.fecha_factura) AS INTEGER) + 2) / 3 AS trimestre,
       f.tratamiento_iva, f.tipo_iva_pb, f.base_cent, f.iva_cent, f.total_cent
FROM factura AS f JOIN v_factura_relaciones AS r ON r.factura_id = f.id
WHERE f.anulada = 0 AND f.fusionada_en_id IS NULL AND r.sustituida_por IS NULL;

-- Lo de siempre de cada proveedor y cada cliente, sin depender de hoy: cuantas
-- facturas, lo facturado (base, IVA y total, con los abonos en negativo), lo
-- pagado segun la fuente que manda y lo que queda (con los abonos aplicados:
-- una factura acreditada no debe nada, y un abono sin aplicar resta). Solo
-- cuenta lo que cuenta: ni anuladas, ni fusionadas, ni sustituidas. Lo que
-- depende de hoy (vencido, el ano en curso) y las estadisticas (plazo de cobro)
-- son de consultas.py.
CREATE VIEW v_proveedor_totales AS
SELECT f.proveedor_id, count(*) AS facturas,
       coalesce(sum(f.base_cent), 0) AS base_cent, coalesce(sum(f.iva_cent), 0) AS iva_cent,
       coalesce(sum(f.total_cent), 0) AS total_cent,
       coalesce(sum(s.pagado_cent), 0) AS pagado_cent,
       coalesce(sum(s.pendiente_cent), 0) AS pendiente_cent
FROM factura AS f JOIN v_factura_saldo AS s ON s.factura_id = f.id
WHERE f.sentido = 'entrante' AND f.proveedor_id IS NOT NULL AND f.anulada = 0
  AND f.fusionada_en_id IS NULL AND s.sustituida_por IS NULL
GROUP BY f.proveedor_id;

CREATE VIEW v_cliente_totales AS
SELECT f.cliente_id, count(*) AS facturas,
       coalesce(sum(f.base_cent), 0) AS base_cent, coalesce(sum(f.iva_cent), 0) AS iva_cent,
       coalesce(sum(f.total_cent), 0) AS total_cent,
       coalesce(sum(s.pagado_cent), 0) AS pagado_cent,
       coalesce(sum(s.pendiente_cent), 0) AS pendiente_cent
FROM factura AS f JOIN v_factura_saldo AS s ON s.factura_id = f.id
WHERE f.sentido = 'saliente' AND f.cliente_id IS NOT NULL AND f.anulada = 0
  AND f.fusionada_en_id IS NULL AND s.sustituida_por IS NULL
GROUP BY f.cliente_id;

-- -------------------------------------------------- guardas (generadas)

CREATE TRIGGER factura_cita_guarda_insert BEFORE INSERT ON factura_cita
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_cita' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.factura_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_cita' AND fila_id = NEW.id AND rev = 0
        AND campo = 'factura_id' AND json_extract(valor_nuevo, '$') IS NEW.factura_id))
    OR (NEW.numero_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_cita' AND fila_id = NEW.id AND rev = 0
        AND campo = 'numero_doc' AND json_extract(valor_nuevo, '$') IS NEW.numero_doc))
    OR (NEW.numero_norm IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_cita' AND fila_id = NEW.id AND rev = 0
        AND campo = 'numero_norm' AND json_extract(valor_nuevo, '$') IS NEW.numero_norm))
    OR (NEW.fecha_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_cita' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fecha_doc' AND json_extract(valor_nuevo, '$') IS NEW.fecha_doc))
    OR (NEW.relacion_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_cita' AND fila_id = NEW.id AND rev = 0
        AND campo = 'relacion_doc' AND json_extract(valor_nuevo, '$') IS NEW.relacion_doc))
    OR (NEW.texto_doc IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_cita' AND fila_id = NEW.id AND rev = 0
        AND campo = 'texto_doc' AND json_extract(valor_nuevo, '$') IS NEW.texto_doc))
    OR (NEW.retirada_en IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_cita' AND fila_id = NEW.id AND rev = 0
        AND campo = 'retirada_en' AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'factura_cita es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER factura_cita_guarda_update BEFORE UPDATE ON factura_cita
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_cita' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.factura_id IS NOT OLD.factura_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_cita' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'factura_id' AND json_extract(valor_anterior, '$') IS OLD.factura_id
        AND json_extract(valor_nuevo, '$') IS NEW.factura_id))
    OR (NEW.numero_doc IS NOT OLD.numero_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_cita' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'numero_doc' AND json_extract(valor_anterior, '$') IS OLD.numero_doc
        AND json_extract(valor_nuevo, '$') IS NEW.numero_doc))
    OR (NEW.numero_norm IS NOT OLD.numero_norm AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_cita' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'numero_norm' AND json_extract(valor_anterior, '$') IS OLD.numero_norm
        AND json_extract(valor_nuevo, '$') IS NEW.numero_norm))
    OR (NEW.fecha_doc IS NOT OLD.fecha_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_cita' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fecha_doc' AND json_extract(valor_anterior, '$') IS OLD.fecha_doc
        AND json_extract(valor_nuevo, '$') IS NEW.fecha_doc))
    OR (NEW.relacion_doc IS NOT OLD.relacion_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_cita' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'relacion_doc' AND json_extract(valor_anterior, '$') IS OLD.relacion_doc
        AND json_extract(valor_nuevo, '$') IS NEW.relacion_doc))
    OR (NEW.texto_doc IS NOT OLD.texto_doc AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_cita' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'texto_doc' AND json_extract(valor_anterior, '$') IS OLD.texto_doc
        AND json_extract(valor_nuevo, '$') IS NEW.texto_doc))
    OR (NEW.retirada_en IS NOT OLD.retirada_en AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'factura_cita' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'retirada_en' AND json_extract(valor_anterior, '$') IS OLD.retirada_en
        AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'factura_cita es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER factura_cita_sin_delete BEFORE DELETE ON factura_cita
BEGIN SELECT RAISE(ABORT, 'factura_cita no se borra: una fila se retira o se desactiva'); END;

