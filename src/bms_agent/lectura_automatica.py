"""La lectura automatica (paso 18, diseno §5): la autorizacion, los topes, las pausas, las
exclusiones y lo que espera a una persona.

Leer cuesta dinero (la API cobra por factura). Hasta el paso 18, cada lectura la aceptaba una
persona en el momento (lectura.py). La lectura automatica gasta en leer sin ese si, pero solo
dentro de una autorizacion permanente que firma en la app una persona con el permiso admin
(`fijar`), con cuatro topes:

- por dia y por mes: lo gastado por las lecturas automaticas cuya pasada empezo ese dia (o ese
  mes) en la hora de la empresa (Europe/Amsterdam, con su cambio de hora), mas lo que puede
  costar la siguiente, no pasa del tope. Lo que aprueba una persona no cuenta: ya tuvo su si;
- por ronda: como mucho `max_documentos` facturas;
- por factura: una que la cuenta pone por encima de `max_por_documento_usd_micro` no se lee sola
  (se aparta: `grande`), y ninguna llamada puede costar mas que eso.

La firma de cada automatica es la del usuario de sistema "automatico", nunca la de una persona;
el evento dice que autorizacion la cubrio y quien la firmo.

Se para sola (`pausar`) si una persona para una automatica ("Stoppen": hasta las 00:00 del dia
siguiente) o si llega un volumen anormal de correo (hasta que una persona la reanude), y espera
cada vez mas tras un fallo tecnico (`espera_tras_fallo`). Lo que no se lee solo (`excluir`) espera
a una persona, que lo puede leer a mano desde Procesar, salvo lo que la API no acepta y lo que
aparto una persona (que tambien puede apartar del todo lo que aparto la automatica).

Nada de aqui habla con la red, lanza procesos, aprueba una factura ni paga: solo lee y escribe la
base. Lo que viene del correo (remitente, asunto, nombres de adjunto) es texto de fuera: se
devuelve tal cual para ensenarlo y nunca decide nada.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .almacen import reloj_de, transaccion, usuario_sistema
from .almacen.evidencia import foto
from .almacen.extracciones import SIN_CANDIDATAS
from .auditoria import registrar
from .lectura import EstadoNoValido
from .reloj import ZONA_EMPRESA, marca

# Los techos de la base (0019): lo que una autorizacion puede decir como mucho.
TECHO_DIA_USD_MICRO = 20_000_000
TECHO_MES_USD_MICRO = 200_000_000
TECHO_DOCUMENTOS = 100
# Lo que la app propone al encenderla (diseno §5.1).
POR_DEFECTO = {"tope_dia_usd_micro": 2_000_000, "tope_mes_usd_micro": 25_000_000,
               "max_documentos": 20, "max_por_documento_usd_micro": 500_000}
# Una persona aparta como mucho tantas facturas de una vez.
MAX_EXCLUIR = 200
# Lo que ensena la lista de lo que espera a una persona (el total va aparte).
ESPERAN_LIMITE = 50
NOTA_MAX = 500

# Por que una factura no se lee sola (exclusion_automatica.motivo_codigo).
EXCLUSIONES = ("grande", "fallo", "rechazado_api", "persona")
# Lo apartado que tampoco entra en lo que lee una persona desde Procesar: lo que aparto ella
# (para eso lo aparto) y lo que la API no acepta (contarlo otra vez no lo cambia, y solo, deja
# su lectura fallida). Lo grande y lo que fallo, si: leerlo es decision suya.
FUERA_DE_PROCESAR = ("persona", "rechazado_api")
PAUSAS = ("persona", "volumen")
# Los finales de una automatica que son un fallo tecnico (no de un documento): la siguiente
# espera 1 h, y el doble tras cada uno seguido, como mucho 24 h.
FALLOS_TECNICOS = ("salida", "aislamiento", "clave", "contar", "sin_tarifa", "saldo",
                   "clave_rechazada", "api_no_disponible")
ESPERA_PRIMERA = timedelta(hours=1)
ESPERA_MAXIMA = timedelta(hours=24)
# Los adjuntos que dicen que un correo no se ha podido leer (diseno §6.1).
NO_LEIDOS = ("no_deseado", "enlace", "xml", "reenvio", "demasiado_grande", "no_es_pdf", "error")

_ZONA = ZoneInfo(ZONA_EMPRESA)


class ValorNoValido(ValueError):
    """Un valor de la autorizacion o de una orden fuera de su rango (un 400 en /api/v2)."""

    codigo = "invalido"


# ------------------------------------------------------------ el dia de la empresa

def _ahora(conn: sqlite3.Connection) -> datetime:
    return reloj_de(conn).ahora()


def _dia(ahora: datetime) -> date:
    """El dia de la empresa (Amsterdam) de un instante."""
    return ahora.astimezone(_ZONA).date()


def _medianoche(dia: date) -> datetime:
    """Las 00:00 de un dia en Amsterdam, en UTC. Las 00:00 existen siempre y una sola vez: el
    cambio de hora es de madrugada (02:00 y 03:00)."""
    return datetime.combine(dia, time(0), tzinfo=_ZONA).astimezone(timezone.utc)


def manana(ahora: datetime) -> datetime:
    """Las 00:00 del dia siguiente en Amsterdam (la pausa de una persona dura hasta ahi)."""
    return _medianoche(_dia(ahora) + timedelta(days=1))


def _mes_siguiente(ahora: datetime) -> datetime:
    dia = _dia(ahora)
    return _medianoche(date(dia.year + dia.month // 12, dia.month % 12 + 1, 1))


def _limites(ahora: datetime) -> tuple[datetime, datetime, datetime, datetime]:
    """(inicio del dia, fin del dia, inicio del mes, fin del mes) de la empresa, en UTC. Un dia
    del cambio de hora dura 23 o 25 horas."""
    dia = _dia(ahora)
    return (_medianoche(dia), _medianoche(dia + timedelta(days=1)),
            _medianoche(dia.replace(day=1)), _mes_siguiente(ahora))


def _instante(texto: str | None) -> datetime | None:
    if not texto:
        return None
    valor = datetime.fromisoformat(texto.replace(" ", "T"))
    return valor if valor.tzinfo is not None else valor.replace(tzinfo=timezone.utc)


def _marca_sqlite(texto: str | None) -> str | None:
    """Un instante de SQLite (datetime(...), en UTC y sin zona) como marca del almacen."""
    instante = _instante(texto)
    return marca(instante) if instante is not None else None


# ------------------------------------------------------------ la autorizacion

def vigente(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """La autorizacion vigente: la de mayor id. Sin ninguna, la automatica esta apagada."""
    return conn.execute("SELECT * FROM lectura_automatica ORDER BY id DESC LIMIT 1").fetchone()


def encendida(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """La vigente si esta encendida; si no (o no hay ninguna), None."""
    fila = vigente(conn)
    return fila if fila is not None and fila["activa"] == 1 else None


def encendida_desde(conn: sqlite3.Connection) -> str | None:
    """Desde cuando esta encendida sin parar (la primera autorizacion despues de la ultima
    apagada: cambiar los topes no la apaga), o None si la vigente esta apagada o no hay."""
    if encendida(conn) is None:
        return None
    fila = conn.execute(
        "SELECT fijada_en FROM lectura_automatica WHERE id > coalesce((SELECT max(id) FROM "
        "lectura_automatica WHERE activa = 0), 0) ORDER BY id LIMIT 1").fetchone()
    return fila["fijada_en"] if fila is not None else None


def _entero(nombre: str, valor: Any, minimo: int, maximo: int) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ValorNoValido(f"{nombre}: se espera un entero")
    if not minimo <= valor <= maximo:
        raise ValorNoValido(f"{nombre}: de {minimo} a {maximo}")
    return valor


def validar(*, activa: Any, tope_dia_usd_micro: Any, tope_mes_usd_micro: Any,
            max_documentos: Any, max_por_documento_usd_micro: Any) -> dict[str, int]:
    """Los cinco valores de una autorizacion, comprobados con los rangos de la base (0019):
    encendida 0 o 1; el dia de 1 a 20 USD; el mes del dia a 200 USD; de 1 a 100 facturas por
    ronda; por factura, de 1 al tope del dia. En millonesimas de dolar."""
    if isinstance(activa, bool):
        activa = int(activa)
    activa = _entero("activa", activa, 0, 1)
    dia = _entero("tope_dia_usd_micro", tope_dia_usd_micro, 1, TECHO_DIA_USD_MICRO)
    mes = _entero("tope_mes_usd_micro", tope_mes_usd_micro, dia, TECHO_MES_USD_MICRO)
    documentos = _entero("max_documentos", max_documentos, 1, TECHO_DOCUMENTOS)
    por_documento = _entero("max_por_documento_usd_micro", max_por_documento_usd_micro, 1, dia)
    return {"activa": activa, "tope_dia_usd_micro": dia, "tope_mes_usd_micro": mes,
            "max_documentos": documentos, "max_por_documento_usd_micro": por_documento}


def fijar(conn: sqlite3.Connection, persona: int, *, activa: Any, tope_dia_usd_micro: Any,
          tope_mes_usd_micro: Any, max_documentos: Any, max_por_documento_usd_micro: Any,
          motivo: str | None = None, peticion_id: str | None = None,
          datos: dict[str, Any] | None = None) -> tuple[int, int]:
    """Una version nueva de la autorizacion (encender, cambiar un tope o apagar), firmada por
    una persona (la base no deja a un usuario de sistema). (su id, el id de su evento). El
    permiso (admin) lo mira servicios.py."""
    valores = validar(activa=activa, tope_dia_usd_micro=tope_dia_usd_micro,
                      tope_mes_usd_micro=tope_mes_usd_micro, max_documentos=max_documentos,
                      max_por_documento_usd_micro=max_por_documento_usd_micro)
    motivo = (motivo or "").strip() or None
    with transaccion(conn):
        fila_id = conn.execute(
            "INSERT INTO lectura_automatica (activa, tope_dia_usd_micro, tope_mes_usd_micro, "
            "max_documentos, max_por_documento_usd_micro, fijada_por, fijada_en, motivo) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (*valores.values(), persona, marca(_ahora(conn)), motivo)).lastrowid
        evento = registrar(conn, tipo="lectura_automatica_fijada", actor=persona,
                           usuario_id=persona, tabla="lectura_automatica", fila_id=fila_id,
                           motivo=motivo, peticion_id=peticion_id,
                           datos={"fila": foto(conn, "lectura_automatica", fila_id),
                                  **(datos or {})})
    return int(fila_id), evento


# ------------------------------------------------------------ lo gastado

def gastado(conn: sqlite3.Connection, ahora: datetime | None = None) -> tuple[int, int]:
    """(hoy, este mes): lo gastado por las lecturas automaticas cuya pasada empezo ese dia o
    ese mes de la empresa (Amsterdam). Lo que aprueba una persona no cuenta."""
    ahora = ahora or _ahora(conn)
    inicio_dia, fin_dia, inicio_mes, fin_mes = _limites(ahora)
    dia = mes = 0
    for fila in conn.execute(
            "SELECT p.empezada_en, p.coste_usd_micro FROM pasada_lectura AS p "
            "JOIN solicitud_lectura AS s ON s.id = p.solicitud_id "
            "WHERE s.aprobada_via = 'automatica' "
            "AND datetime(p.empezada_en) >= datetime(?) AND datetime(p.empezada_en) < datetime(?)",
            (marca(inicio_mes), marca(fin_mes))):
        empezada = _instante(fila["empezada_en"])
        if empezada is None or not inicio_mes <= empezada < fin_mes:
            continue
        mes += fila["coste_usd_micro"]
        if inicio_dia <= empezada < fin_dia:
            dia += fila["coste_usd_micro"]
    return dia, mes


@dataclass(frozen=True)
class Tope:
    """El tope que se alcanzo: limite_dia (hasta las 00:00) o limite_mes (hasta el dia 1)."""

    parada: str
    hasta: str


def tope_alcanzado(autorizacion: sqlite3.Row, gastado_dia: int, gastado_mes: int,
                   ahora: datetime) -> Tope | None:
    """Si lo que queda hoy o este mes no llega a una factura (max_por_documento): con lo que
    queda por debajo de eso no se puede leer ninguna con seguridad. El mes primero: si se
    acabo, manana tampoco se lee."""
    por_documento = autorizacion["max_por_documento_usd_micro"]
    if autorizacion["tope_mes_usd_micro"] - gastado_mes < por_documento:
        return Tope("limite_mes", marca(_mes_siguiente(ahora)))
    if autorizacion["tope_dia_usd_micro"] - gastado_dia < por_documento:
        return Tope("limite_dia", marca(manana(ahora)))
    return None


def queda(autorizacion: sqlite3.Row, gastado_dia: int, gastado_mes: int) -> int:
    """Lo que aun se puede gastar hoy: lo que queda del dia, sin pasar de lo que queda del mes."""
    return max(0, min(autorizacion["tope_dia_usd_micro"] - gastado_dia,
                      autorizacion["tope_mes_usd_micro"] - gastado_mes))


# ------------------------------------------------------------ lo que hay que leer

_SIN_VIGENTE = (f"NOT EXISTS (SELECT 1 FROM extraccion AS e WHERE e.documento_id = d.id "
                f"AND ({SIN_CANDIDATAS}))")


def _desde_el_correo(excluidas: str) -> str:
    """Los documentos que llegaron por la bandeja de entrada (no desde "no deseado"), con su
    original en el almacen y sin extraccion vigente (la regla de ingesta.vigentes_por_documento:
    cualquier extraccion que no sea una candidata sin activar), sin las exclusiones de
    `excluidas` (todas, o las que dejan algo fuera de Procesar: FUERA_DE_PROCESAR). Una fila por
    llegada: se agrupa por d.id."""
    fuera = ", ".join(f"'{m}'" for m in FUERA_DE_PROCESAR)
    filtro = {"todas": "", "a_mano": f" AND x.motivo_codigo IN ({fuera})"}[excluidas]
    return ("FROM documento AS d "
            "JOIN adjunto_correo AS a ON a.documento_id = d.id AND a.resultado = 'documento' "
            "JOIN mensaje_correo AS m ON m.id = a.mensaje_id AND m.carpeta = 'bandeja' "
            f"WHERE d.ruta_cas IS NOT NULL AND {_SIN_VIGENTE} "
            "AND NOT EXISTS (SELECT 1 FROM exclusion_automatica AS x "
            f"WHERE x.documento_id = d.id{filtro})")


def _del_correo(conn: sqlite3.Connection, *, excluidas: str, limite: int | None
                ) -> list[dict[str, Any]]:
    """Los de _desde_el_correo, los mas antiguos primero (por la primera vez que llegaron)."""
    sql = ("SELECT d.id AS documento_id, d.sha256, d.ruta_cas, d.nombre_original, "
           f"min(datetime(m.recibido_en)) AS llegada {_desde_el_correo(excluidas)} "
           "GROUP BY d.id ORDER BY llegada, d.id")
    parametros: tuple[Any, ...] = ()
    if limite is not None:
        sql += " LIMIT ?"
        parametros = (limite,)
    return [{"documento_id": f["documento_id"], "sha256": f["sha256"], "ruta_cas": f["ruta_cas"],
             "nombre_original": f["nombre_original"], "llegada": _marca_sqlite(f["llegada"])}
            for f in conn.execute(sql, parametros)]


def _cuantos(conn: sqlite3.Connection, excluidas: str) -> tuple[int, str | None]:
    """(cuantos hay, cuando llego el mas antiguo)."""
    fila = conn.execute(
        "SELECT count(*), min(llegada) FROM (SELECT min(datetime(m.recibido_en)) AS llegada "
        f"{_desde_el_correo(excluidas)} GROUP BY d.id)").fetchone()
    return int(fila[0]), _marca_sqlite(fila[1])


def pendientes_del_correo(conn: sqlite3.Connection, limite: int | None = None
                          ) -> list[dict[str, Any]]:
    """Lo del correo que falta por leer y que una persona puede leer desde Procesar: todo lo
    pendiente menos lo que una persona aparto ("Niet vanzelf lezen" no se lee a mano sin
    querer) y lo que la API no acepta (FUERA_DE_PROCESAR). Lo grande y lo que fallo leyendose
    solo, si: esperan a una persona, que puede leerlo o apartarlo del todo."""
    return _del_correo(conn, excluidas="a_mano", limite=limite)


def elegibles(conn: sqlite3.Connection, autorizacion: sqlite3.Row | None = None,
              limite: int | None = None) -> list[dict[str, Any]]:
    """Lo que la automatica puede leer: lo pendiente del correo sin ninguna exclusion, los mas
    antiguos primero; como mucho `limite` o, con una autorizacion, su max_documentos."""
    if limite is None and autorizacion is not None:
        limite = autorizacion["max_documentos"]
    return _del_correo(conn, excluidas="todas", limite=limite)


def contar_elegibles(conn: sqlite3.Connection) -> tuple[int, str | None]:
    """(cuantas elegibles hay, cuando llego la mas antigua)."""
    return _cuantos(conn, "todas")


def elegibles_que_esperan(conn: sqlite3.Connection, antes: datetime) -> int:
    """Cuantas elegibles entraron antes de `antes` (la banda de las que esperan, §6.1): por la
    primera vez que `correo registrar` las registro, no por cuando las recibio Microsoft (lo
    que llego de noche, o lo de antes de configurar el correo, no lleva horas esperando)."""
    return int(conn.execute(
        "SELECT count(*) FROM (SELECT min(datetime(m.registrado_en)) AS entrada "
        f"{_desde_el_correo('todas')} GROUP BY d.id) WHERE entrada < datetime(?)",
        (marca(antes),)).fetchone()[0])


# ------------------------------------------------------------ las exclusiones

def excluidos(conn: sqlite3.Connection, documento_ids: Iterable[int], *,
              por_una_persona: bool = False) -> set[int]:
    """Los de esos documentos que ya no se leen solos (o, con `por_una_persona`, los que
    aparto una persona)."""
    ids = sorted({int(i) for i in documento_ids})
    if not ids:
        return set()
    marcas = ", ".join("?" * len(ids))
    solo = " AND motivo_codigo = 'persona'" if por_una_persona else ""
    return {f[0] for f in conn.execute(
        f"SELECT documento_id FROM exclusion_automatica WHERE documento_id IN ({marcas}){solo}",
        ids)}


def _ids(documento_ids: Any) -> list[int]:
    if not isinstance(documento_ids, (list, tuple)):
        raise ValorNoValido("documento_ids: se espera una lista de ids de documento")
    ids: list[int] = []
    for valor in documento_ids:
        if isinstance(valor, bool) or not isinstance(valor, int) or valor < 1:
            raise ValorNoValido(f"documento_ids: {valor!r} no es un id de documento")
        if valor not in ids:
            ids.append(valor)
    return ids


def excluir(conn: sqlite3.Connection, documento_ids: Any, motivo_codigo: str, por: int, *,
            solicitud_id: int | None = None, motivo: str | None = None,
            peticion_id: str | None = None, datos: dict[str, Any] | None = None
            ) -> list[tuple[int, int]]:
    """Esos documentos no se leen solos: esperan a una persona (lo grande y lo que fallo, ella
    lo puede leer desde Procesar; FUERA_DE_PROCESAR). `persona` la pone una persona (excluir_de_lectura_automatica, hasta MAX_EXCLUIR
    de una vez, sin peticion); grande, fallo y rechazado_api, el usuario automatico con la
    peticion que lo vio. Para siempre: los que ya estaban, se dejan como estaban. Como mucho
    una del sistema y una de una persona por documento: una persona puede apartar del todo
    (tambien de Procesar) uno que la automatica ya aparto; la automatica no aparta lo que ya
    esta apartado. (id de la exclusion, id de su evento) de cada una nueva; el primer evento
    lleva `peticion_id` (la idempotencia de la orden)."""
    if motivo_codigo not in EXCLUSIONES:
        raise ValorNoValido(f"motivo de exclusion desconocido: {motivo_codigo!r}")
    ids = _ids(documento_ids)
    if motivo_codigo == "persona" and not 1 <= len(ids) <= MAX_EXCLUIR:
        raise ValorNoValido(f"documento_ids: de 1 a {MAX_EXCLUIR} documentos")
    motivo = (motivo or "").strip() or None
    hechas: list[tuple[int, int]] = []
    with transaccion(conn):
        marcas = ", ".join("?" * len(ids)) or "NULL"
        existen = {f[0] for f in conn.execute(
            f"SELECT id FROM documento WHERE id IN ({marcas})", ids)}
        faltan = [i for i in ids if i not in existen]
        if faltan:
            raise LookupError(f"no hay documento {', '.join(map(str, faltan))}")
        persona = por if motivo_codigo == "persona" else None
        ya = excluidos(conn, ids, por_una_persona=motivo_codigo == "persona")
        ahora = marca(_ahora(conn))
        for documento_id in ids:
            if documento_id in ya:
                continue
            fila_id = int(conn.execute(
                "INSERT INTO exclusion_automatica (documento_id, motivo_codigo, solicitud_id, "
                "por, en) VALUES (?, ?, ?, ?, ?)",
                (documento_id, motivo_codigo, solicitud_id, por, ahora)).lastrowid)
            evento = registrar(
                conn, tipo="lectura_excluida", actor=por, usuario_id=persona,
                tabla="exclusion_automatica", fila_id=fila_id, motivo=motivo,
                peticion_id=None if hechas else peticion_id,
                datos={"documento_id": documento_id, "motivo_codigo": motivo_codigo,
                       "solicitud_id": solicitud_id,
                       "fila": foto(conn, "exclusion_automatica", fila_id), **(datos or {})})
            hechas.append((fila_id, evento))
    return hechas


# ------------------------------------------------------------ las pausas

def pausa_vigente(conn: sqlite3.Connection, ahora: datetime | None = None
                  ) -> sqlite3.Row | None:
    """La pausa que para ahora la automatica, o None. Cuenta lo que hay despues de la ultima
    reanudacion: una de volumen sigue hasta que una persona la quite (y gana a la de una
    persona, que acaba antes); una de persona, hasta su `hasta` (las 00:00 siguientes)."""
    ahora = ahora or _ahora(conn)
    ultima = conn.execute("SELECT coalesce(max(id), 0) FROM pausa_lectura_automatica "
                          "WHERE tipo = 'reanuda'").fetchone()[0]
    pausas = conn.execute("SELECT * FROM pausa_lectura_automatica WHERE tipo = 'pausa' "
                          "AND id > ? ORDER BY id DESC", (ultima,)).fetchall()
    for fila in pausas:
        if fila["motivo"] == "volumen":
            return fila
    for fila in pausas:
        hasta = _instante(fila["hasta"])
        if fila["motivo"] == "persona" and hasta is not None and ahora < hasta:
            return fila
    return None


def pausar(conn: sqlite3.Connection, motivo: str, por: int | None = None, *,
           solicitud_id: int | None = None, ahora: datetime | None = None,
           peticion_id: str | None = None, datos: dict[str, Any] | None = None
           ) -> tuple[int, int] | None:
    """Para la automatica. `persona`: alguien paro una automatica (`solicitud_id`), y dura hasta
    las 00:00 del dia siguiente en Amsterdam o hasta que una persona la reanude; la firma esa
    persona. `volumen`: llego un volumen anormal de correo; la firma el usuario automatico, una
    vez al dia como mucho (si una persona la quita, ese dia no vuelve), y dura hasta que una
    persona la quite. (id de la pausa, id de su evento), o None si no hizo falta."""
    if motivo not in PAUSAS:
        raise ValorNoValido(f"pausa desconocida: {motivo!r}")
    ahora = ahora or _ahora(conn)
    with transaccion(conn):
        hasta = None
        if motivo == "volumen":
            por = usuario_sistema(conn, "automatico") if por is None else por
            inicio, fin, _im, _fm = _limites(ahora)
            hoy = conn.execute(
                "SELECT 1 FROM pausa_lectura_automatica WHERE tipo = 'pausa' "
                "AND motivo = 'volumen' AND datetime(en) >= datetime(?) "
                "AND datetime(en) < datetime(?)", (marca(inicio), marca(fin))).fetchone()
            actual = pausa_vigente(conn, ahora)
            if hoy is not None or (actual is not None and actual["motivo"] == "volumen"):
                return None
        else:
            if por is None:
                raise ValorNoValido("la pausa de una persona la firma esa persona")
            hasta = marca(manana(ahora))
        fila_id = int(conn.execute(
            "INSERT INTO pausa_lectura_automatica (tipo, motivo, solicitud_id, por, en, hasta) "
            "VALUES ('pausa', ?, ?, ?, ?, ?)",
            (motivo, solicitud_id, por, marca(ahora), hasta)).lastrowid)
        evento = registrar(
            conn, tipo="lectura_automatica_pausada", actor=por,
            usuario_id=por if motivo == "persona" else None, tabla="pausa_lectura_automatica",
            fila_id=fila_id, peticion_id=peticion_id,
            datos={"motivo": motivo, "solicitud_id": solicitud_id, "hasta": hasta,
                   "fila": foto(conn, "pausa_lectura_automatica", fila_id), **(datos or {})})
    return fila_id, evento


def reanudar(conn: sqlite3.Connection, por: int, motivo: str | None = None, *,
             peticion_id: str | None = None, datos: dict[str, Any] | None = None
             ) -> tuple[int, int]:
    """Una persona quita la pausa (de persona o de volumen). Sin ninguna vigente, no hay nada
    que quitar: EstadoNoValido (un 409). (id de la fila, id de su evento)."""
    motivo = (motivo or "").strip() or None
    with transaccion(conn):
        ahora = _ahora(conn)
        actual = pausa_vigente(conn, ahora)
        if actual is None:
            raise EstadoNoValido("la lectura automatica no esta en pausa: no hay nada que "
                                 "reanudar")
        fila_id = int(conn.execute(
            "INSERT INTO pausa_lectura_automatica (tipo, por, en) VALUES ('reanuda', ?, ?)",
            (por, marca(ahora))).lastrowid)
        evento = registrar(
            conn, tipo="lectura_automatica_reanudada", actor=por, usuario_id=por,
            tabla="pausa_lectura_automatica", fila_id=fila_id, motivo=motivo,
            peticion_id=peticion_id,
            datos={"pausa": actual["motivo"], "pausa_id": actual["id"],
                   "fila": foto(conn, "pausa_lectura_automatica", fila_id), **(datos or {})})
    return fila_id, evento


# ------------------------------------------------------------ la espera tras un fallo

@dataclass(frozen=True)
class Espera:
    """La automatica esta parada por fallos tecnicos seguidos: el motivo del ultimo, desde
    cuando (el primero de la racha) y cuando se vuelve a probar."""

    motivo_codigo: str
    desde: str
    proximo_intento: str
    fallos: int


def espera_tras_fallo(conn: sqlite3.Connection, ahora: datetime | None = None) -> Espera | None:
    """Tras un fallo tecnico de una automatica (la salida, el aislamiento, la clave, contar, la
    tarifa, el saldo, la clave rechazada o la API no disponible), la siguiente espera 1 h; tras
    cada uno seguido, el doble (2, 4, 8, 16 h), como mucho 24 h. Cualquier otro final de una
    automatica corta la racha. None si ya se puede probar."""
    ahora = ahora or _ahora(conn)
    racha: list[sqlite3.Row] = []
    for fila in conn.execute(
            "SELECT id, estado, motivo_codigo, terminada_en FROM solicitud_lectura "
            "WHERE origen = 'automatica' AND terminada_en IS NOT NULL ORDER BY id DESC LIMIT 12"):
        if fila["estado"] != "fallida" or fila["motivo_codigo"] not in FALLOS_TECNICOS:
            break
        racha.append(fila)
    if not racha:
        return None
    espera = min(ESPERA_PRIMERA * 2 ** (len(racha) - 1), ESPERA_MAXIMA)
    proximo = _instante(racha[0]["terminada_en"]) + espera
    if ahora >= proximo:
        return None
    return Espera(racha[0]["motivo_codigo"], racha[-1]["terminada_en"], marca(proximo),
                  len(racha))


# ------------------------------------------------------------ lo que espera a una persona

def marcar_atendido(conn: sqlite3.Connection, mensaje_id: Any, por: int,
                    nota: str | None = None, *, peticion_id: str | None = None,
                    datos: dict[str, Any] | None = None) -> tuple[int, int]:
    """Una persona ya miro un correo que el programa no podia leer: sale de la lista de lo que
    espera a una persona. Una vez por correo. (id de la fila, id de su evento)."""
    if isinstance(mensaje_id, bool) or not isinstance(mensaje_id, int):
        raise ValorNoValido("mensaje_id: se espera el id de un correo")
    nota = (nota or "").strip() or None
    if nota is not None and len(nota) > NOTA_MAX:
        raise ValorNoValido(f"nota: como mucho {NOTA_MAX} caracteres")
    with transaccion(conn):
        if conn.execute("SELECT 1 FROM mensaje_correo WHERE id = ?",
                        (mensaje_id,)).fetchone() is None:
            raise LookupError(f"no hay correo {mensaje_id}")
        if conn.execute("SELECT 1 FROM correo_atendido WHERE mensaje_id = ?",
                        (mensaje_id,)).fetchone() is not None:
            raise EstadoNoValido(f"el correo {mensaje_id} ya esta atendido")
        fila_id = int(conn.execute(
            "INSERT INTO correo_atendido (mensaje_id, por, en, nota) VALUES (?, ?, ?, ?)",
            (mensaje_id, por, marca(_ahora(conn)), nota)).lastrowid)
        evento = registrar(conn, tipo="correo_atendido", actor=por, usuario_id=por,
                           tabla="correo_atendido", fila_id=fila_id, peticion_id=peticion_id,
                           datos={"mensaje_id": mensaje_id,
                                  "fila": foto(conn, "correo_atendido", fila_id),
                                  **(datos or {})})
    return fila_id, evento


def mensaje(conn: sqlite3.Connection, fila: sqlite3.Row) -> dict[str, Any]:
    """Un correo como lo ensena la app, con sus adjuntos. El remitente, el asunto y los nombres
    son texto de fuera, tal cual (saneado al registrarlo): la app los marca "no comprobado"."""
    adjuntos = [{"nombre_doc": a["nombre_doc"], "resultado": a["resultado"], "bytes": a["bytes"],
                 "documento_id": a["documento_id"]}
                for a in conn.execute("SELECT nombre_doc, resultado, bytes, documento_id "
                                      "FROM adjunto_correo WHERE mensaje_id = ? ORDER BY id",
                                      (fila["id"],))]
    return {"mensaje_id": fila["id"], "recibido_en": fila["recibido_en"],
            "carpeta": fila["carpeta"], "remitente_doc": fila["remitente_doc"],
            "asunto_doc": fila["asunto_doc"], "adjuntos": adjuntos}


_CORREOS_QUE_ESPERAN = (
    "FROM mensaje_correo AS m "
    "WHERE NOT EXISTS (SELECT 1 FROM correo_atendido AS c WHERE c.mensaje_id = m.id) "
    "AND ((m.carpeta = 'bandeja' AND NOT EXISTS (SELECT 1 FROM adjunto_correo AS a "
    "      WHERE a.mensaje_id = m.id AND a.resultado = 'documento')) "
    "  OR EXISTS (SELECT 1 FROM adjunto_correo AS a WHERE a.mensaje_id = m.id "
    f"      AND a.resultado IN ({', '.join(repr(r) for r in NO_LEIDOS)}))) "
    # El que estaba en "no deseado" y una persona paso a la bandeja es otra llegada, que se
    # trae: el de "no deseado" ya no espera a nadie.
    "AND NOT (m.carpeta = 'no_deseado' AND EXISTS (SELECT 1 FROM mensaje_correo AS b "
    "      WHERE b.graph_id = m.graph_id AND b.carpeta = 'bandeja'))")

# Una fila por documento: la ultima exclusion (la de una persona, si aparto una que ya habia
# apartado la automatica).
_DOCUMENTOS_QUE_ESPERAN = (
    "FROM exclusion_automatica AS x JOIN documento AS d ON d.id = x.documento_id "
    f"WHERE {_SIN_VIGENTE} AND x.id = (SELECT max(y.id) FROM exclusion_automatica AS y "
    "WHERE y.documento_id = x.documento_id)")


def esperan_persona(conn: sqlite3.Connection, limite: int = ESPERAN_LIMITE) -> dict[str, Any]:
    """Lo que el programa no puede hacer solo y espera a una persona (diseno §6.1, §6.2):

    - los correos que no ha podido leer y que nadie ha dado por atendidos: los de la bandeja
      sin ningun PDF recibido, y los que tienen algun adjunto que no se trajo (no deseado, un
      enlace, XML, reenviado como adjunto, demasiado grande, no era un PDF, o no se pudo
      traer); los mas recientes primero;
    - las facturas que no se leen solas (excluidas) y aun sin leer; las ultimas apartadas
      primero.

    Cada lista con como mucho `limite` filas y su total."""
    correos = conn.execute(
        f"SELECT m.* {_CORREOS_QUE_ESPERAN} ORDER BY datetime(m.recibido_en) DESC, m.id DESC "
        "LIMIT ?", (limite,)).fetchall()
    total_correos = conn.execute(f"SELECT count(*) {_CORREOS_QUE_ESPERAN}").fetchone()[0]
    documentos = conn.execute(
        "SELECT x.documento_id, d.nombre_original, d.recibido_en, x.motivo_codigo "
        f"{_DOCUMENTOS_QUE_ESPERAN} ORDER BY x.id DESC LIMIT ?", (limite,)).fetchall()
    total_documentos = conn.execute(f"SELECT count(*) {_DOCUMENTOS_QUE_ESPERAN}").fetchone()[0]
    return {"correos": [mensaje(conn, f) for f in correos], "correos_total": total_correos,
            "documentos": [{"documento_id": f["documento_id"],
                            "nombre_original": f["nombre_original"],
                            "recibido_en": f["recibido_en"],
                            "motivo_codigo": f["motivo_codigo"]} for f in documentos],
            "documentos_total": total_documentos}


# ------------------------------------------------------------ lo que ensena la app

@dataclass(frozen=True)
class Detenida:
    """Por que la automatica no lee ahora, aunque este encendida: una pausa (persona,
    volumen), la espera tras un fallo (fallo) o un tope (limite_dia, limite_mes)."""

    parada: str
    motivo_codigo: str | None = None
    desde: str | None = None
    proximo_intento: str | None = None
    hasta: str | None = None


def detenida_por_pausa(conn: sqlite3.Connection, ahora: datetime) -> Detenida | None:
    pausa = pausa_vigente(conn, ahora)
    if pausa is None:
        return None
    return Detenida(pausa["motivo"], desde=pausa["en"], hasta=pausa["hasta"])


def detenida_por_fallo(conn: sqlite3.Connection, ahora: datetime) -> Detenida | None:
    espera = espera_tras_fallo(conn, ahora)
    if espera is None:
        return None
    return Detenida("fallo", espera.motivo_codigo, espera.desde, espera.proximo_intento)


def parada_por_pausa_o_fallo(conn: sqlite3.Connection, ahora: datetime) -> Detenida | None:
    return detenida_por_pausa(conn, ahora) or detenida_por_fallo(conn, ahora)


def resumen(conn: sqlite3.Connection, ahora: datetime | None = None) -> dict[str, Any]:
    """La lectura automatica para la app (diseno §6.2, "lectura_automatica"): la autorizacion
    vigente y quien la firmo, lo gastado hoy y este mes y lo que queda hoy, por que esta parada
    si lo esta (con la automatica encendida), y cuanto hay pendiente y elegible."""
    ahora = ahora or _ahora(conn)
    autorizacion = vigente(conn)
    dia, mes = gastado(conn, ahora)
    activa = autorizacion is not None and autorizacion["activa"] == 1
    parada: Detenida | None = None
    if activa:
        parada = parada_por_pausa_o_fallo(conn, ahora)
        if parada is None:
            tope = tope_alcanzado(autorizacion, dia, mes, ahora)
            parada = Detenida(tope.parada, hasta=tope.hasta) if tope is not None else None
    fijada_por = None
    if autorizacion is not None:
        quien = conn.execute("SELECT id, nombre FROM usuario WHERE id = ?",
                             (autorizacion["fijada_por"],)).fetchone()
        fijada_por = {"id": quien["id"], "nombre": quien["nombre"]} if quien else None
    numero, mas_antigua = contar_elegibles(conn)
    pendientes, _ = _cuantos(conn, "a_mano")

    def valor(columna: str) -> Any:
        return autorizacion[columna] if autorizacion is not None else None

    return {
        "activa": activa, "autorizacion_id": valor("id"),
        "tope_dia_usd_micro": valor("tope_dia_usd_micro"),
        "tope_mes_usd_micro": valor("tope_mes_usd_micro"),
        "max_documentos": valor("max_documentos"),
        "max_por_documento_usd_micro": valor("max_por_documento_usd_micro"),
        "fijada_por": fijada_por, "fijada_en": valor("fijada_en"),
        "gastado_hoy_usd_micro": dia, "gastado_mes_usd_micro": mes,
        "queda_hoy_usd_micro": queda(autorizacion, dia, mes) if autorizacion is not None else 0,
        "parada": parada.parada if parada is not None else None,
        "motivo_codigo": parada.motivo_codigo if parada is not None else None,
        "desde": parada.desde if parada is not None else None,
        "proximo_intento": parada.proximo_intento if parada is not None else None,
        "hasta": parada.hasta if parada is not None else None,
        "pendientes": pendientes, "elegibles": numero, "elegible_mas_antigua": mas_antigua,
    }
