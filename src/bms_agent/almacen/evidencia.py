"""La evidencia comprobada contra su propia auditoria, sin fiarse de los disparadores.

La cadena de auditoria solo cubre evento y cambio_campo. Las filas de
evidencia (documento, extraccion, importacion) las protegen disparadores,
pero alguien con el fichero puede borrarlos, insertar una extraccion falsa
(otro IBAN, otro importe) o editar una y volver a crearlos. Esto lo
encuentra `db verificar` de tres formas:

- cada extraccion se vuelve a hashear: contenido_json tiene que dar su
  contenido_sha256;
- cada fila tiene su evento de alta, y el evento lleva la foto de la fila
  (`foto()`: todas sus columnas) tal cual quedo. Como el evento esta en la
  cadena, la foto no se puede cambiar sin que se note, y la fila tiene que
  ser igual a ella. Una fila sin su evento es una fila metida por detras;
  un evento sin su fila, una fila borrada;
- el esquema (tablas, vistas, indices y disparadores) tiene que ser el que
  crean las migraciones aplicadas, texto a texto: un disparador borrado o
  cambiado se ve aunque nadie haya tocado todavia una fila.

Una tabla nueva de evidencia (paso 2 en adelante) anade aqui sus columnas y
sus tipos de evento, y su escritor pone `foto()` en los datos del evento.
Las del paso 2 son politica_version y nota; la del paso 3, anulacion (la
foto la escribe hallazgos.anular antes de la fila, como la de una nota); las
del paso 4, revision y prioridad_manual (igual); las del paso 6, reextraccion
(como importacion, con un evento por cada cambio mientras espera su lote),
reextraccion_resultado, activacion y linea_sin_casar (como una nota). La
procedencia de los campos
de las tablas controladas tiene su propia comprobacion, con la misma idea
(campos.verificar_procedencia), y la excepcion la suya
(excepciones.verificar).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .unidades import sha256_texto

# Columnas que se fotografian (todas menos el id; de extraccion, tampoco el
# texto, que ya cubre contenido_sha256 y se comprueba aparte).
COLUMNAS: dict[str, tuple[str, ...]] = {
    "documento": (
        "sha256", "nombre_original", "tipo_mime", "bytes", "ruta_cas", "origen",
        "ruta_declarada", "mensaje_id", "recibido_en", "recibido_fuente", "registrado_en",
        "registrado_por",
    ),
    "extraccion": (
        "documento_id", "modelo", "prompt_version", "schema_version", "via", "extraido_en",
        "request_id", "uso_json", "contenido_sha256", "registrada_en",
    ),
    "importacion": (
        "fuente", "tipo", "formato", "documento_id", "fichero_sha256", "mapeo_sha256",
        "exportado_en", "cubre_desde", "cubre_hasta", "completa", "estado", "filas_leidas",
        "filas_aceptadas", "filas_rechazadas", "rechazos_json", "iniciada_en", "terminada_en",
        "iniciada_por", "actor",
    ),
    # Las personas y sus permisos (paso 2, permisos.py). Los usuarios de
    # sistema los siembra la migracion 0001 sin evento: ver FILTROS.
    "usuario": ("nombre", "email", "es_sistema", "activo", "token_sha256", "creado_en"),
    "rol": ("nombre", "descripcion"),
    "rol_permiso": ("rol_id", "permiso"),
    "usuario_rol": ("usuario_id", "rol_id", "desde", "hasta"),
    # Paso 2: la politica cargada (sin su texto, que cubre sha256 y se
    # rehashea aparte, como una extraccion) y las notas de las personas.
    "politica_version": ("sha256", "fichero", "vigente_desde", "cargada_en", "cargada_por"),
    "nota": ("tabla", "fila_id", "texto", "usuario_id", "en"),
    # Paso 3: lo que firma una persona al anular un hallazgo.
    "anulacion": ("hallazgo_id", "huella", "motivo", "usuario_id", "en", "vigente_hasta",
                  "segunda_firma_usuario_id", "segunda_firma_en", "autoaprobada"),
    # Paso 4: lo que firma una persona al revisar una factura o subir una prioridad.
    "revision": ("factura_id", "resultado", "huella_contenido", "autorrevisada", "usuario_id",
                 "en", "nota"),
    "prioridad_manual": ("entidad", "entidad_id", "nivel", "motivo", "usuario_id", "en", "hasta"),
    # Paso 6: lo que se acepto pagar al volver a leer, lo que dio cada
    # documento, lo que una persona activo y las lineas que no se pudieron casar.
    "reextraccion": (
        "modelo", "prompt_version", "schema_version", "via", "criterio_json", "documentos",
        "presupuesto_usd_cent", "estimado_bajo_usd_cent", "estimado_alto_usd_cent",
        "salida_medida", "estimacion_json", "lote_id", "estado", "extraidas", "reintentos",
        "iniciada_en", "terminada_en", "iniciada_por", "actor",
    ),
    "reextraccion_resultado": ("reextraccion_id", "documento_id", "resultado", "extraccion_id",
                               "anterior_id", "motivo", "detalle", "en"),
    "activacion": ("extraccion_id", "documento_id", "anterior_id", "comparacion_sha256",
                   "usuario_id", "en"),
    "linea_sin_casar": ("factura_id", "linea_id", "extraccion_id", "excluida", "campos_json",
                        "en"),
}

# Filas que no se comprueban contra un evento porque no lo tienen: las
# siembra una migracion, que ya esta fijada por su hash.
FILTROS: dict[str, str] = {"usuario": "es_sistema = 0"}

# Por tabla: el evento que da de alta la fila, y los que la modifican despues
# (cada uno con la foto nueva). La foto que vale es la del ultimo.
EVENTOS: dict[str, tuple[str, tuple[str, ...]]] = {
    "documento": ("documento_registrado", ("documento_original_anadido",)),
    "extraccion": ("extraccion_registrada", ()),
    "importacion": ("importacion", ()),
    "usuario": ("usuario_creado", ("usuario_modificado",)),
    "rol": ("rol_creado", ()),
    "rol_permiso": ("rol_permiso_anadido", ()),
    "usuario_rol": ("rol_asignado", ("rol_cerrado",)),
    "politica_version": ("politica_cargada", ()),
    "nota": ("nota_anadida", ()),
    "anulacion": ("hallazgo_anulado", ()),
    "revision": ("revision_registrada", ()),
    "prioridad_manual": ("prioridad_subida", ()),
    "reextraccion": ("reextraccion_iniciada", ("reextraccion_lote_enviado",
                                               "reextraccion_terminada")),
    "reextraccion_resultado": ("reextraccion_resultado", ()),
    "activacion": ("extraccion_activada", ()),
    "linea_sin_casar": ("linea_sin_casar", ()),
}

# Tablas cuya fila apunta a su evento (columna evento_id) en vez de que el
# evento apunte a la fila: el evento de una nota es de la fila anotada, para
# que salga en su historial. La foto la lleva igual el evento.
POR_EVENTO: dict[str, str] = {"nota": "evento_id", "anulacion": "evento_id",
                               "revision": "evento_id", "prioridad_manual": "evento_id",
                               "reextraccion_resultado": "evento_id",
                               "activacion": "evento_id", "linea_sin_casar": "evento_id"}


_FALTA = object()
_NOMBRES = {"table": "la tabla", "view": "la vista", "index": "el indice", "trigger": "el disparador"}


def foto(conn: sqlite3.Connection, tabla: str, fila_id: int) -> dict[str, Any]:
    """Las columnas de una fila de evidencia, para los datos de su evento."""
    columnas = COLUMNAS[tabla]
    fila = conn.execute(
        f"SELECT {', '.join(columnas)} FROM {tabla} WHERE id = ?", (fila_id,)
    ).fetchone()
    if fila is None:
        raise LookupError(f"no hay {tabla} {fila_id}")
    return {columna: fila[columna] for columna in columnas}


def _datos(evento: sqlite3.Row) -> dict[str, Any]:
    try:
        datos = json.loads(evento["datos_json"] or "null")
    except json.JSONDecodeError:
        return {}
    return datos if isinstance(datos, dict) else {}


def _eventos_de_evidencia(conn: sqlite3.Connection) -> dict[tuple[str, int], list[sqlite3.Row]]:
    tipos = sorted({t for alta, mods in EVENTOS.values() for t in (alta, *mods)})
    marcas = ", ".join("?" * len(tipos))
    por_fila: dict[tuple[str, int], list[sqlite3.Row]] = {}
    for evento in conn.execute(
        f"SELECT id, tipo, tabla, fila_id, datos_json FROM evento WHERE tipo IN ({marcas}) "
        "ORDER BY id", tipos,
    ):
        if evento["tabla"] in EVENTOS and evento["tabla"] not in POR_EVENTO and evento["tipo"] in (
            EVENTOS[evento["tabla"]][0], *EVENTOS[evento["tabla"]][1]
        ):
            por_fila.setdefault((evento["tabla"], evento["fila_id"]), []).append(evento)
    return por_fila


def _comprobar_fila(
    tabla: str, fila_id: int, actual: dict[str, Any], eventos: list[sqlite3.Row]
) -> list[str]:
    alta, modificaciones = EVENTOS[tabla]
    altas = [e for e in eventos if e["tipo"] == alta]
    if not altas:
        return [f"{tabla} {fila_id} no tiene su evento {alta}: se ha metido por detras"]
    if len(altas) > 1:
        return [f"{tabla} {fila_id} tiene {len(altas)} eventos {alta}"]
    validos = [e for e in eventos if e["tipo"] == alta or (
        e["tipo"] in modificaciones and e["id"] > altas[0]["id"])]
    ultimo = validos[-1]
    esperada = _datos(ultimo).get("fila")
    if not isinstance(esperada, dict):
        return [f"el evento {ultimo['id']} de {tabla} {fila_id} no lleva la foto de la fila"]
    distintas = [c for c in COLUMNAS[tabla] if esperada.get(c, _FALTA) != actual[c]]
    if distintas:
        return [
            f"{tabla} {fila_id}: {', '.join(distintas)} no es lo que registro el evento "
            f"{ultimo['id']}: se ha modificado por detras"
        ]
    return []



def _verificar_por_evento(conn: sqlite3.Connection, tabla: str, columna: str) -> list[str]:
    """Una tabla de POR_EVENTO: cada fila igual a la foto de su evento, cada evento con fila."""
    alta = EVENTOS[tabla][0]
    eventos = {e["id"]: e for e in conn.execute(
        "SELECT id, tipo, datos_json FROM evento WHERE tipo = ?", (alta,))}
    problemas = []
    con_fila = set()
    for fila_id, evento_id in conn.execute(f"SELECT id, {columna} FROM {tabla} ORDER BY id"):
        evento = eventos.get(evento_id)
        if evento is None or evento_id in con_fila:
            problemas.append(
                f"{tabla} {fila_id} no tiene su evento {alta}: se ha metido por detras")
            continue
        con_fila.add(evento_id)
        problemas.extend(_comprobar_fila(tabla, fila_id, foto(conn, tabla, fila_id), [evento]))
    for evento_id in sorted(set(eventos) - con_fila):
        problemas.append(
            f"el evento {evento_id} registro una fila de {tabla} que ya no existe: se ha borrado")
    return problemas


def verificar_evidencia(conn: sqlite3.Connection) -> list[str]:
    """Lo que no cuadra entre las filas de evidencia y su auditoria. Vacio si nada."""
    problemas = []
    for fila in conn.execute("SELECT id, contenido_json, contenido_sha256 FROM extraccion"):
        if sha256_texto(fila["contenido_json"]) != fila["contenido_sha256"]:
            problemas.append(
                f"extraccion {fila['id']}: contenido_json no da su contenido_sha256: "
                "el texto se ha modificado"
            )

    for fila in conn.execute("SELECT id, contenido, sha256 FROM politica_version"):
        if sha256_texto(fila["contenido"]) != fila["sha256"]:
            problemas.append(
                f"politica_version {fila['id']}: su contenido no da su sha256: "
                "el texto se ha modificado"
            )

    for tabla, columna in POR_EVENTO.items():
        problemas.extend(_verificar_por_evento(conn, tabla, columna))

    eventos = _eventos_de_evidencia(conn)
    for tabla in (t for t in EVENTOS if t not in POR_EVENTO):
        filtro = f" WHERE {FILTROS[tabla]}" if tabla in FILTROS else ""
        ids = [f[0] for f in conn.execute(f"SELECT id FROM {tabla}{filtro} ORDER BY id")]
        for fila_id in ids:
            problemas.extend(_comprobar_fila(
                tabla, fila_id, foto(conn, tabla, fila_id), eventos.get((tabla, fila_id), [])))
        existentes = set(ids)
        for (de_tabla, fila_id), lista in sorted(eventos.items()):
            if de_tabla == tabla and fila_id not in existentes:
                problemas.append(
                    f"el evento {lista[0]['id']} registro {tabla} {fila_id}, que ya no existe: "
                    "se ha borrado"
                )

    aplicadas = {f["fila_id"]: _datos(f) for f in conn.execute(
        "SELECT fila_id, datos_json FROM evento WHERE tipo = 'migracion_aplicada' "
        "AND tabla = 'migracion'")}
    for fila in conn.execute("SELECT version, nombre, sha256 FROM migracion ORDER BY version"):
        datos = aplicadas.get(fila["version"])
        if datos is None:
            problemas.append(f"la migracion {fila['nombre']} no tiene su evento migracion_aplicada")
        elif (datos.get("nombre"), datos.get("sha256")) != (fila["nombre"], fila["sha256"]):
            problemas.append(
                f"la migracion {fila['version']} no es la que registro su evento"
            )
    return problemas


def _esquema(conn: sqlite3.Connection) -> dict[tuple[str, str], tuple[str, str | None]]:
    return {
        (fila[0], fila[1]): (fila[2], fila[3])
        for fila in conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    }


def verificar_esquema(conn: sqlite3.Connection, directorio: str | Path | None = None) -> list[str]:
    """Que el esquema sea el que crean las migraciones aplicadas, ni mas ni menos.

    Se compara con una base en memoria a la que se aplican los mismos
    ficheros. Un disparador borrado y vuelto a crear con el mismo texto no
    se ve aqui; lo que haya cambiado mientras no estaba lo ven las fotos.
    """
    from .migrar import aplicadas, disponibles

    versiones = set(aplicadas(conn))
    referencia = sqlite3.connect(":memory:")
    try:
        for migracion in disponibles(directorio):
            if migracion.version in versiones:
                referencia.executescript(migracion.sql)
        esperado = _esquema(referencia)
    finally:
        referencia.close()
    actual = _esquema(conn)

    problemas = []
    for (tipo, nombre), definicion in sorted(esperado.items()):
        if (tipo, nombre) not in actual:
            problemas.append(f"falta {_NOMBRES.get(tipo, tipo)} {nombre}, que crea una migracion")
        elif actual[(tipo, nombre)] != definicion:
            problemas.append(
                f"{_NOMBRES.get(tipo, tipo)} {nombre} ha cambiado: no es la definicion de su migracion"
            )
    for tipo, nombre in sorted(set(actual) - set(esperado)):
        problemas.append(f"sobra {_NOMBRES.get(tipo, tipo)} {nombre}: no sale de ninguna migracion")
    return problemas

