-- Migracion 0010 (paso 9 de la V1): ordenes de compra, los Objetos que cubren y
-- sus modificaciones.
--
-- Un fichero aplicado no se edita nunca (ver 0001). Lo que haga falta
-- despues va en 0011, 0012...
--
-- Lo que esta migracion garantiza (spec §5.C, §7 "Purchase orders"):
--   - Una PO es de un lado: la que un cliente da a BM Support BV (lado
--     cliente, la consumen las facturas de venta a ese cliente) o la que BM
--     Support BV da a un proveedor (lado proveedor, la consumen sus facturas de
--     compra). Es unica por lado, parte y numero normalizado.
--   - El valor original y la fecha de fin original no cambian: el valor y el
--     fin vigentes son los de la ultima modificacion (por su fecha y, a igual
--     fecha, la ultima apuntada). orden_compra_modificacion es de solo
--     escritura: una modificacion equivocada se arregla con otra.
--   - Una modificacion la firma una persona con cambiar_po en ese momento, en
--     su propia orden o en la importacion que ella lanzo (la hoja de POs que
--     teclea una persona); nunca el sistema solo.
--   - orden_compra_id de una imputacion, de una referencia o de una tarifa
--     pactada apunta a una PO que existe (la 0002 no podia declarar la clave
--     foranea: la tabla no existia).
--   - v_po_consumo: lo consumido de cada PO sin depender de hoy, lo mismo que
--     reglas/ordenes.consumo en SQL. Lo consumido es la base (sin IVA) de las
--     imputaciones activas de las facturas que cuentan (ni anuladas, ni
--     fusionadas, ni sustituidas o corregidas: v_imputacion_vigente), del
--     sentido que consume ese lado; un abono resta solo si tiene una relacion
--     confirmada que diga a que factura abona (acredita o anula). Lo que no
--     esta en euros no tiene importe (X1) y no cuenta. Los porcentajes van en
--     puntos basicos, truncados hacia cero.
--
-- Clases de tabla (spec.md §4):
--   orden_compra, orden_compra_objeto: CONTROLADAS (rev y guarda generada con
--     scripts/generar_guardas.py), escritas por campos.py.
--   orden_compra_modificacion: SOLO ESCRITURA, evidencia con su evento
--     (almacen/evidencia.py, como una nota).

-- ------------------------------------------------------------- orden_compra

CREATE TABLE orden_compra (
    id                  INTEGER PRIMARY KEY,
    numero              TEXT NOT NULL CHECK (length(trim(numero)) > 0),
    numero_norm         TEXT NOT NULL CHECK (length(numero_norm) > 0),
    lado                TEXT NOT NULL CHECK (lado IN ('cliente', 'proveedor')),
    cliente_id          INTEGER REFERENCES cliente(id),
    proveedor_id        INTEGER REFERENCES proveedor(id),
    fecha_emision       TEXT CHECK (fecha_emision IS NULL OR date(fecha_emision) IS fecha_emision),
    fecha_inicio        TEXT CHECK (fecha_inicio IS NULL OR date(fecha_inicio) IS fecha_inicio),
    fecha_fin           TEXT CHECK (fecha_fin IS NULL OR date(fecha_fin) IS fecha_fin),
    valor_original_cent INTEGER NOT NULL CHECK (valor_original_cent > 0),
    documento_id        INTEGER REFERENCES documento(id),
    cerrada             INTEGER NOT NULL DEFAULT 0 CHECK (cerrada IN (0, 1)),
    fuente              TEXT NOT NULL CHECK (fuente IN ('manual', 'po_csv', 'exact', 'trnsprnt')),
    rev                 INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0),
    CHECK ((lado = 'cliente') = (cliente_id IS NOT NULL)),
    CHECK ((lado = 'proveedor') = (proveedor_id IS NOT NULL)),
    CHECK (fecha_inicio IS NULL OR fecha_fin IS NULL OR fecha_inicio <= fecha_fin)
) STRICT;

CREATE UNIQUE INDEX orden_compra_unica ON orden_compra
    (lado, coalesce(cliente_id, proveedor_id), numero_norm);
CREATE INDEX orden_compra_numero ON orden_compra (numero_norm);

-- La parte, el lado y el numero son la identidad de la PO: no cambian (una PO
-- de otro cliente es otra PO). El valor y el fin originales tampoco: lo que
-- cambia se apunta como modificacion.
CREATE TRIGGER orden_compra_identidad_fija BEFORE UPDATE OF numero, numero_norm, lado, cliente_id,
    proveedor_id, valor_original_cent, fecha_fin, fuente ON orden_compra
WHEN NEW.numero IS NOT OLD.numero OR NEW.numero_norm IS NOT OLD.numero_norm
  OR NEW.lado IS NOT OLD.lado OR NEW.cliente_id IS NOT OLD.cliente_id
  OR NEW.proveedor_id IS NOT OLD.proveedor_id
  OR NEW.valor_original_cent IS NOT OLD.valor_original_cent
  OR NEW.fecha_fin IS NOT OLD.fecha_fin OR NEW.fuente IS NOT OLD.fuente
BEGIN SELECT RAISE(ABORT, 'el numero, la parte, el valor y el fin originales de una PO no cambian: se apunta una modificacion'); END;

-- ------------------------------------------------------ orden_compra_objeto

-- Los Objetos que cubre una PO. Una PO sin ninguno cubre cualquiera de su
-- parte. Un Objeto que deja de cubrir se retira (no se borra).
CREATE TABLE orden_compra_objeto (
    id              INTEGER PRIMARY KEY,
    orden_compra_id INTEGER NOT NULL REFERENCES orden_compra(id),
    objeto_id       INTEGER NOT NULL REFERENCES objeto(id),
    retirada_en     TEXT CHECK (retirada_en IS NULL OR datetime(retirada_en) IS NOT NULL),
    rev             INTEGER NOT NULL DEFAULT 0 CHECK (rev >= 0)
) STRICT;

CREATE UNIQUE INDEX orden_compra_objeto_vivo ON orden_compra_objeto (orden_compra_id, objeto_id)
    WHERE retirada_en IS NULL;

CREATE TRIGGER orden_compra_objeto_fijo BEFORE UPDATE OF orden_compra_id, objeto_id
    ON orden_compra_objeto
WHEN NEW.orden_compra_id IS NOT OLD.orden_compra_id OR NEW.objeto_id IS NOT OLD.objeto_id
BEGIN SELECT RAISE(ABORT, 'un Objeto de una PO no cambia: se retira y se anade otro'); END;

-- ------------------------------------------------ orden_compra_modificacion

-- Una modificacion de una PO: un valor nuevo, un fin nuevo o los dos, desde
-- una fecha, con su motivo. La firma una persona con cambiar_po; si viene de
-- una hoja importada, la importacion en curso que ella lanzo.
CREATE TABLE orden_compra_modificacion (
    id               INTEGER PRIMARY KEY,
    orden_compra_id  INTEGER NOT NULL REFERENCES orden_compra(id),
    fecha            TEXT NOT NULL CHECK (date(fecha) IS fecha),
    valor_nuevo_cent INTEGER CHECK (valor_nuevo_cent IS NULL OR valor_nuevo_cent > 0),
    fecha_fin_nueva  TEXT CHECK (fecha_fin_nueva IS NULL OR date(fecha_fin_nueva) IS fecha_fin_nueva),
    motivo           TEXT NOT NULL CHECK (length(trim(motivo)) > 0),
    documento_id     INTEGER REFERENCES documento(id),
    importacion_id   INTEGER REFERENCES importacion(id),
    usuario_id       INTEGER NOT NULL REFERENCES usuario(id),
    en               TEXT NOT NULL CHECK (datetime(en) IS NOT NULL),
    evento_id        INTEGER NOT NULL UNIQUE REFERENCES evento(id),
    CHECK (valor_nuevo_cent IS NOT NULL OR fecha_fin_nueva IS NOT NULL)
) STRICT;

CREATE INDEX orden_compra_modificacion_po ON orden_compra_modificacion (orden_compra_id, fecha, id);

CREATE TRIGGER orden_compra_modificacion_de_persona BEFORE INSERT ON orden_compra_modificacion
WHEN NOT EXISTS (
        SELECT 1 FROM usuario AS u
        JOIN usuario_rol AS ur ON ur.usuario_id = u.id
        JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id
        WHERE u.id = NEW.usuario_id AND u.es_sistema = 0 AND u.activo = 1
          AND rp.permiso = 'cambiar_po'
          AND ur.desde <= NEW.en AND (ur.hasta IS NULL OR ur.hasta > NEW.en))
  OR NEW.evento_id IS NOT (SELECT max(id) FROM evento)
  OR (SELECT usuario_id FROM evento WHERE id = NEW.evento_id) IS NOT NEW.usuario_id
  OR NOT ((SELECT actor FROM evento WHERE id = NEW.evento_id) IS NEW.usuario_id
          OR (NEW.importacion_id IS NOT NULL
              AND (SELECT actor FROM evento WHERE id = NEW.evento_id)
                  IS (SELECT id FROM usuario WHERE nombre = 'importador' AND es_sistema = 1)
              AND (SELECT estado FROM importacion WHERE id = NEW.importacion_id) = 'en_curso'
              AND (SELECT iniciada_por FROM importacion WHERE id = NEW.importacion_id)
                  IS NEW.usuario_id))
BEGIN SELECT RAISE(ABORT, 'una PO la modifica una persona con cambiar_po, en su propia orden o en la importacion que lanzo'); END;

CREATE TRIGGER orden_compra_modificacion_sin_update BEFORE UPDATE ON orden_compra_modificacion
BEGIN SELECT RAISE(ABORT, 'orden_compra_modificacion es de solo escritura: no se modifica'); END;
CREATE TRIGGER orden_compra_modificacion_sin_delete BEFORE DELETE ON orden_compra_modificacion
BEGIN SELECT RAISE(ABORT, 'orden_compra_modificacion es de solo escritura: no se borra'); END;

-- ------------------------------------------- orden_compra_id, a una que existe

CREATE TRIGGER factura_imputacion_po_insert BEFORE INSERT ON factura_imputacion
WHEN NEW.orden_compra_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM orden_compra WHERE id = NEW.orden_compra_id)
BEGIN SELECT RAISE(ABORT, 'la imputacion apunta a una PO que no existe'); END;

CREATE TRIGGER factura_imputacion_po_update BEFORE UPDATE OF orden_compra_id ON factura_imputacion
WHEN NEW.orden_compra_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM orden_compra WHERE id = NEW.orden_compra_id)
BEGIN SELECT RAISE(ABORT, 'la imputacion apunta a una PO que no existe'); END;

CREATE TRIGGER factura_referencia_po_insert BEFORE INSERT ON factura_referencia
WHEN NEW.orden_compra_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM orden_compra WHERE id = NEW.orden_compra_id)
BEGIN SELECT RAISE(ABORT, 'la referencia apunta a una PO que no existe'); END;

CREATE TRIGGER factura_referencia_po_update BEFORE UPDATE OF orden_compra_id ON factura_referencia
WHEN NEW.orden_compra_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM orden_compra WHERE id = NEW.orden_compra_id)
BEGIN SELECT RAISE(ABORT, 'la referencia apunta a una PO que no existe'); END;

CREATE TRIGGER tarifa_acordada_po_insert BEFORE INSERT ON tarifa_acordada
WHEN NEW.orden_compra_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM orden_compra WHERE id = NEW.orden_compra_id)
BEGIN SELECT RAISE(ABORT, 'la tarifa apunta a una PO que no existe'); END;

CREATE TRIGGER tarifa_acordada_po_update BEFORE UPDATE OF orden_compra_id ON tarifa_acordada
WHEN NEW.orden_compra_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM orden_compra WHERE id = NEW.orden_compra_id)
BEGIN SELECT RAISE(ABORT, 'la tarifa apunta a una PO que no existe'); END;

-- ------------------------------------------------------------------ vistas

-- El valor y el fin vigentes de cada PO: los de la ultima modificacion que los
-- cambia (por su fecha y, a igual fecha, la ultima apuntada); si no, los
-- originales.
CREATE VIEW v_po_vigente AS
SELECT o.id AS orden_compra_id, o.numero, o.lado, o.cliente_id, o.proveedor_id, o.cerrada,
       o.fecha_inicio, o.valor_original_cent,
       coalesce((SELECT m.valor_nuevo_cent FROM orden_compra_modificacion AS m
                 WHERE m.orden_compra_id = o.id AND m.valor_nuevo_cent IS NOT NULL
                 ORDER BY m.fecha DESC, m.id DESC LIMIT 1), o.valor_original_cent) AS valor_cent,
       coalesce((SELECT m.fecha_fin_nueva FROM orden_compra_modificacion AS m
                 WHERE m.orden_compra_id = o.id AND m.fecha_fin_nueva IS NOT NULL
                 ORDER BY m.fecha DESC, m.id DESC LIMIT 1), o.fecha_fin) AS fecha_fin
FROM orden_compra AS o;

-- Lo consumido de cada PO (ver la cabecera): sin depender de hoy.
CREATE VIEW v_po_consumo AS
WITH abonos_confirmados AS (
    SELECT DISTINCT r.origen_id AS factura_id
    FROM factura_relacion AS r
    JOIN factura AS o ON o.id = r.origen_id
    JOIN factura AS d ON d.id = r.destino_id
    WHERE r.estado = 'confirmada' AND r.retirada_en IS NULL AND r.tipo IN ('acredita', 'anula')
      AND o.anulada = 0 AND o.fusionada_en_id IS NULL AND d.fusionada_en_id IS NULL
),
consumo AS (
    SELECT i.orden_compra_id, sum(i.importe_cent) AS cent
    FROM v_imputacion_vigente AS i
    JOIN factura AS f ON f.id = i.factura_id
    JOIN orden_compra AS po ON po.id = i.orden_compra_id
    WHERE i.importe_cent IS NOT NULL
      AND f.sentido = CASE po.lado WHEN 'cliente' THEN 'saliente' ELSE 'entrante' END
      AND (f.tipo = 'factura' OR f.id IN (SELECT factura_id FROM abonos_confirmados))
    GROUP BY i.orden_compra_id
)
SELECT v.orden_compra_id, v.numero, v.lado, v.cliente_id, v.proveedor_id, v.cerrada,
       v.valor_original_cent, v.valor_cent, v.fecha_inicio, v.fecha_fin,
       coalesce(c.cent, 0) AS consumido_cent,
       v.valor_cent - coalesce(c.cent, 0) AS restante_cent,
       coalesce(c.cent, 0) * 10000 / v.valor_cent AS consumido_pb,
       (v.valor_cent - coalesce(c.cent, 0)) * 10000 / v.valor_cent AS restante_pb
FROM v_po_vigente AS v LEFT JOIN consumo AS c ON c.orden_compra_id = v.orden_compra_id;

-- -------------------------------------------------- guardas (generadas)

CREATE TRIGGER orden_compra_guarda_insert BEFORE INSERT ON orden_compra
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.numero IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = 0
        AND campo = 'numero' AND json_extract(valor_nuevo, '$') IS NEW.numero))
    OR (NEW.numero_norm IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = 0
        AND campo = 'numero_norm' AND json_extract(valor_nuevo, '$') IS NEW.numero_norm))
    OR (NEW.lado IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = 0
        AND campo = 'lado' AND json_extract(valor_nuevo, '$') IS NEW.lado))
    OR (NEW.cliente_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = 0
        AND campo = 'cliente_id' AND json_extract(valor_nuevo, '$') IS NEW.cliente_id))
    OR (NEW.proveedor_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = 0
        AND campo = 'proveedor_id' AND json_extract(valor_nuevo, '$') IS NEW.proveedor_id))
    OR (NEW.fecha_emision IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fecha_emision' AND json_extract(valor_nuevo, '$') IS NEW.fecha_emision))
    OR (NEW.fecha_inicio IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fecha_inicio' AND json_extract(valor_nuevo, '$') IS NEW.fecha_inicio))
    OR (NEW.fecha_fin IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fecha_fin' AND json_extract(valor_nuevo, '$') IS NEW.fecha_fin))
    OR (NEW.valor_original_cent IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = 0
        AND campo = 'valor_original_cent' AND json_extract(valor_nuevo, '$') IS NEW.valor_original_cent))
    OR (NEW.documento_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = 0
        AND campo = 'documento_id' AND json_extract(valor_nuevo, '$') IS NEW.documento_id))
    OR (NEW.cerrada IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = 0
        AND campo = 'cerrada' AND json_extract(valor_nuevo, '$') IS NEW.cerrada))
    OR (NEW.fuente IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = 0
        AND campo = 'fuente' AND json_extract(valor_nuevo, '$') IS NEW.fuente))
BEGIN SELECT RAISE(ABORT, 'orden_compra es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER orden_compra_guarda_update BEFORE UPDATE ON orden_compra
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.numero IS NOT OLD.numero AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'numero' AND json_extract(valor_anterior, '$') IS OLD.numero
        AND json_extract(valor_nuevo, '$') IS NEW.numero))
    OR (NEW.numero_norm IS NOT OLD.numero_norm AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'numero_norm' AND json_extract(valor_anterior, '$') IS OLD.numero_norm
        AND json_extract(valor_nuevo, '$') IS NEW.numero_norm))
    OR (NEW.lado IS NOT OLD.lado AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'lado' AND json_extract(valor_anterior, '$') IS OLD.lado
        AND json_extract(valor_nuevo, '$') IS NEW.lado))
    OR (NEW.cliente_id IS NOT OLD.cliente_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'cliente_id' AND json_extract(valor_anterior, '$') IS OLD.cliente_id
        AND json_extract(valor_nuevo, '$') IS NEW.cliente_id))
    OR (NEW.proveedor_id IS NOT OLD.proveedor_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'proveedor_id' AND json_extract(valor_anterior, '$') IS OLD.proveedor_id
        AND json_extract(valor_nuevo, '$') IS NEW.proveedor_id))
    OR (NEW.fecha_emision IS NOT OLD.fecha_emision AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fecha_emision' AND json_extract(valor_anterior, '$') IS OLD.fecha_emision
        AND json_extract(valor_nuevo, '$') IS NEW.fecha_emision))
    OR (NEW.fecha_inicio IS NOT OLD.fecha_inicio AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fecha_inicio' AND json_extract(valor_anterior, '$') IS OLD.fecha_inicio
        AND json_extract(valor_nuevo, '$') IS NEW.fecha_inicio))
    OR (NEW.fecha_fin IS NOT OLD.fecha_fin AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fecha_fin' AND json_extract(valor_anterior, '$') IS OLD.fecha_fin
        AND json_extract(valor_nuevo, '$') IS NEW.fecha_fin))
    OR (NEW.valor_original_cent IS NOT OLD.valor_original_cent AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'valor_original_cent' AND json_extract(valor_anterior, '$') IS OLD.valor_original_cent
        AND json_extract(valor_nuevo, '$') IS NEW.valor_original_cent))
    OR (NEW.documento_id IS NOT OLD.documento_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'documento_id' AND json_extract(valor_anterior, '$') IS OLD.documento_id
        AND json_extract(valor_nuevo, '$') IS NEW.documento_id))
    OR (NEW.cerrada IS NOT OLD.cerrada AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'cerrada' AND json_extract(valor_anterior, '$') IS OLD.cerrada
        AND json_extract(valor_nuevo, '$') IS NEW.cerrada))
    OR (NEW.fuente IS NOT OLD.fuente AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'fuente' AND json_extract(valor_anterior, '$') IS OLD.fuente
        AND json_extract(valor_nuevo, '$') IS NEW.fuente))
BEGIN SELECT RAISE(ABORT, 'orden_compra es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER orden_compra_sin_delete BEFORE DELETE ON orden_compra
BEGIN SELECT RAISE(ABORT, 'orden_compra no se borra: una fila se retira o se desactiva'); END;


CREATE TRIGGER orden_compra_objeto_guarda_insert BEFORE INSERT ON orden_compra_objeto
WHEN
    NEW.rev IS NOT 0
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra_objeto' AND fila_id = NEW.id AND rev = 0)
    OR (NEW.orden_compra_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra_objeto' AND fila_id = NEW.id AND rev = 0
        AND campo = 'orden_compra_id' AND json_extract(valor_nuevo, '$') IS NEW.orden_compra_id))
    OR (NEW.objeto_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra_objeto' AND fila_id = NEW.id AND rev = 0
        AND campo = 'objeto_id' AND json_extract(valor_nuevo, '$') IS NEW.objeto_id))
    OR (NEW.retirada_en IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra_objeto' AND fila_id = NEW.id AND rev = 0
        AND campo = 'retirada_en' AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'orden_compra_objeto es una tabla controlada: solo la escribe campos.py, con un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER orden_compra_objeto_guarda_update BEFORE UPDATE ON orden_compra_objeto
WHEN
    NEW.id IS NOT OLD.id
    OR NEW.rev IS NOT OLD.rev + 1
    OR NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra_objeto' AND fila_id = NEW.id AND rev = NEW.rev)
    OR (NEW.orden_compra_id IS NOT OLD.orden_compra_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra_objeto' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'orden_compra_id' AND json_extract(valor_anterior, '$') IS OLD.orden_compra_id
        AND json_extract(valor_nuevo, '$') IS NEW.orden_compra_id))
    OR (NEW.objeto_id IS NOT OLD.objeto_id AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra_objeto' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'objeto_id' AND json_extract(valor_anterior, '$') IS OLD.objeto_id
        AND json_extract(valor_nuevo, '$') IS NEW.objeto_id))
    OR (NEW.retirada_en IS NOT OLD.retirada_en AND NOT EXISTS (SELECT 1 FROM cambio_campo WHERE evento_id = (SELECT max(id) FROM evento)
        AND tabla = 'orden_compra_objeto' AND fila_id = NEW.id AND rev = NEW.rev
        AND campo = 'retirada_en' AND json_extract(valor_anterior, '$') IS OLD.retirada_en
        AND json_extract(valor_nuevo, '$') IS NEW.retirada_en))
BEGIN SELECT RAISE(ABORT, 'orden_compra_objeto es una tabla controlada: solo la escribe campos.py, con rev + 1 y un cambio_campo por campo en el evento en curso'); END;

CREATE TRIGGER orden_compra_objeto_sin_delete BEFORE DELETE ON orden_compra_objeto
BEGIN SELECT RAISE(ABORT, 'orden_compra_objeto no se borra: una fila se retira o se desactiva'); END;

