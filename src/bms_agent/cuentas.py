"""El registro de cuentas bancarias: el unico modulo que escribe cuenta_bancaria y cuenta_evento.

Regla 1 de arquitectura.md: el IBAN nunca sale de un documento. Por eso
aqui solo entran dos cosas:

- lo que trae un maestro (`apuntar_maestro`), que llama el importador
  (importadores/registrar.py) con su importacion de cuentas en curso. El
  primer maestro de Exact es la referencia de partida (baseline: heredada,
  aceptada como referencia y ensenada sin verificar); lo que un maestro
  posterior anade, cambia o quita queda bloqueado (F5) hasta que una
  persona lo verifica por telefono;
- lo que decide una persona con confirmar_iban (`decidir`): verificar por
  telefono, rechazar o atestar. La verificacion apunta a que numero se llamo
  y que lo motivo; si cuenta o no lo decide F8 con el telefono que tenia el
  maestro antes de ese documento y el enfriamiento tras un cambio.

Ninguna funcion de aqui recibe un IBAN de una extraccion: el que verifica una
persona lo teclea ella. Un test recorre el grafo de imports y comprueba que
nada de la via de entrada de los documentos llega a este modulo.

Cada orden de aqui es un evento de auditoria con la foto de cada fila que da
de alta (`datos.cuentas` y `datos.eventos_cuenta`), escrito antes que las
filas: la base exige que cada fila cuelgue del ultimo evento, y `verificar`
compara despues cada fila con su foto.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .almacen import reloj_de, transaccion, usuario_sistema
from .auditoria import registrar
from .campos import FaltaMotivo, Persona
from .dominio import DECISIONES_CUENTA, Permiso, PrimeraFuenteCuenta, TipoEventoCuenta
from .permisos import exigir, orden_auditada
from .reglas.bancaria import validar_iban
from .reglas.normas import normalizar_iban, normalizar_telefono
from .reloj import marca

COLUMNAS_CUENTA = ("titular", "proveedor_id", "cliente_id", "iban", "nombre_titular",
                   "primera_vez_en", "primera_fuente", "importacion_id", "evento_id")
COLUMNAS_EVENTO = ("cuenta_id", "tipo", "importacion_id", "documento_id", "metodo",
                   "telefono_usado", "telefono_ref", "persona_contactada", "decision_facturas",
                   "usuario_id", "en", "nota", "evento_id")
FUENTES_MAESTRO = ("exact", "trnsprnt")


class IbanNoValido(ValueError):
    """El IBAN no pasa el digito de control: no se registra."""


@dataclass
class ResultadoMaestro:
    """Lo que apunto una importacion de cuentas."""

    evento_id: int | None = None
    baseline: bool = False
    nuevas: list[int] = field(default_factory=list)
    vistas: int = 0
    ausentes: list[int] = field(default_factory=list)


def _columna_parte(titular: str) -> str:
    if titular not in ("proveedor", "cliente"):
        raise ValueError(f"una cuenta del maestro es de un proveedor o de un cliente, no de "
                         f"{titular!r}")
    return f"{titular}_id"


def _siguientes(conn: sqlite3.Connection, tabla: str) -> int:
    return int(conn.execute(f"SELECT coalesce(max(id), 0) + 1 FROM {tabla}").fetchone()[0])


def _escribir(conn: sqlite3.Connection, cuentas: dict[int, dict[str, Any]],
              eventos: dict[int, dict[str, Any]]) -> None:
    for fila_id, fila in cuentas.items():
        conn.execute(f"INSERT INTO cuenta_bancaria (id, {', '.join(COLUMNAS_CUENTA)}) "
                     f"VALUES (?, {', '.join('?' * len(COLUMNAS_CUENTA))})",
                     (fila_id, *(fila[c] for c in COLUMNAS_CUENTA)))
    for fila_id, fila in eventos.items():
        conn.execute(f"INSERT INTO cuenta_evento (id, {', '.join(COLUMNAS_EVENTO)}) "
                     f"VALUES (?, {', '.join('?' * len(COLUMNAS_EVENTO))})",
                     (fila_id, *(fila[c] for c in COLUMNAS_EVENTO)))


def _fotos(cuentas: dict[int, dict[str, Any]], eventos: dict[int, dict[str, Any]],
           evento_id: int) -> dict[str, Any]:
    """Las filas tal como van a quedar (con el evento que las da de alta)."""
    for fila in (*cuentas.values(), *eventos.values()):
        fila["evento_id"] = evento_id
    return {"cuentas": {str(i): {c: f[c] for c in COLUMNAS_CUENTA} for i, f in cuentas.items()},
            "eventos_cuenta": {str(i): {c: f[c] for c in COLUMNAS_EVENTO}
                               for i, f in eventos.items()}}


def _siguiente_evento(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT coalesce(max(id), 0) + 1 FROM evento").fetchone()[0])


# ------------------------------------------------------------ lo que trae un maestro

def apuntar_maestro(
    conn: sqlite3.Connection, *, importacion_id: int, fuente: str, titular: str,
    presentes: Sequence[tuple[int, str, str | None]], usuario_id: int | None = None,
) -> ResultadoMaestro:
    """Las cuentas de una importacion completa de un maestro: altas, vistas y ausentes.

    `presentes` son (proveedor o cliente, IBAN, titular impreso) de cada fila.
    Es una foto entera: una cuenta de ese tipo de titular que la importacion
    anterior de esta fuente traia y esta no, queda ausente. La primera
    importacion de Exact para un tipo de titular es la de partida (baseline).
    La escribe el importador (usuario de sistema) con la importacion en curso;
    la base no lo admite de nadie mas, ni un estado decidido por una persona.
    """
    if fuente not in FUENTES_MAESTRO:
        raise ValueError(f"las cuentas llegan del maestro de Exact o de TRNSPRNT, no de {fuente}")
    columna = _columna_parte(titular)
    visto, ausente = f"visto_en_{fuente}", f"ausente_en_{fuente}"
    ahora = marca(reloj_de(conn).ahora())
    importador = usuario_sistema(conn, "importador")
    existentes = {(f[1], f[2]): f[0] for f in conn.execute(
        f"SELECT id, {columna}, iban FROM cuenta_bancaria WHERE titular = ?", (titular,))}
    ultimos = dict(conn.execute(
        "SELECT e.cuenta_id, e.tipo FROM cuenta_evento AS e "
        "JOIN cuenta_bancaria AS c ON c.id = e.cuenta_id "
        "WHERE c.titular = ? AND e.tipo IN (?, ?) AND e.id = ("
        "  SELECT max(id) FROM cuenta_evento WHERE cuenta_id = e.cuenta_id AND tipo IN (?, ?))",
        (titular, visto, ausente, visto, ausente)).fetchall())
    resultado = ResultadoMaestro(baseline=fuente == "exact" and not conn.execute(
        "SELECT 1 FROM cuenta_evento AS e JOIN cuenta_bancaria AS c ON c.id = e.cuenta_id "
        "WHERE c.titular = ? AND e.tipo IN ('visto_en_exact', 'ausente_en_exact') LIMIT 1",
        (titular,)).fetchone())

    cuentas: dict[int, dict[str, Any]] = {}
    eventos: dict[int, dict[str, Any]] = {}
    siguiente_cuenta = _siguientes(conn, "cuenta_bancaria")
    siguiente_evento = _siguientes(conn, "cuenta_evento")
    primera = (PrimeraFuenteCuenta.BASELINE.value if resultado.baseline
               else f"maestro_{fuente}")

    def evento(cuenta_id: int, tipo: str) -> None:
        nonlocal siguiente_evento
        eventos[siguiente_evento] = {
            "cuenta_id": cuenta_id, "tipo": tipo, "importacion_id": importacion_id,
            "documento_id": None, "metodo": None, "telefono_usado": None, "telefono_ref": None,
            "persona_contactada": None, "decision_facturas": None, "usuario_id": None,
            "en": ahora, "nota": None}
        siguiente_evento += 1

    vistas: set[int] = set()
    for parte_id, iban, nombre_titular in presentes:
        limpio = normalizar_iban(iban)
        if not validar_iban(limpio):
            raise IbanNoValido(f"{limpio!r} no pasa el digito de control: no se registra")
        cuenta_id = existentes.get((parte_id, limpio))
        if cuenta_id is None:
            cuenta_id = siguiente_cuenta
            siguiente_cuenta += 1
            existentes[(parte_id, limpio)] = cuenta_id
            cuentas[cuenta_id] = {
                "titular": titular, "proveedor_id": parte_id if titular == "proveedor" else None,
                "cliente_id": parte_id if titular == "cliente" else None, "iban": limpio,
                "nombre_titular": nombre_titular, "primera_vez_en": ahora,
                "primera_fuente": primera, "importacion_id": importacion_id}
            resultado.nuevas.append(cuenta_id)
        if cuenta_id in vistas:
            continue
        vistas.add(cuenta_id)
        if resultado.baseline:
            evento(cuenta_id, TipoEventoCuenta.BASELINE.value)
        evento(cuenta_id, visto)
    resultado.vistas = len(vistas)
    for cuenta_id, tipo in sorted(ultimos.items()):
        if tipo == visto and cuenta_id not in vistas:
            evento(cuenta_id, ausente)
            resultado.ausentes.append(cuenta_id)
    if not eventos:
        return resultado

    with transaccion(conn):
        evento_id = _siguiente_evento(conn)
        datos = {"fuente": fuente, "titular": titular, "baseline": resultado.baseline,
                 **_fotos(cuentas, eventos, evento_id)}
        resultado.evento_id = registrar(
            conn, tipo="cuentas_del_maestro", actor=importador, usuario_id=usuario_id,
            tabla="importacion", fila_id=importacion_id, datos=datos)
        _escribir(conn, cuentas, eventos)
    return resultado


# ------------------------------------------------------------ lo que decide una persona

@dataclass(frozen=True)
class Decision:
    """Una decision de una persona sobre una cuenta: lo que va en su cuenta_evento."""

    tipo: str
    metodo: str | None = None
    telefono_usado: str | None = None
    persona_contactada: str | None = None
    decision_facturas: str | None = None
    documento_id: int | None = None
    importacion_id: int | None = None
    nota: str | None = None


@dataclass
class ResultadoDecision:
    evento_id: int | None = None
    cuentas: list[int] = field(default_factory=list)
    creada: int | None = None
    telefono_ref: int | None = None


def cuenta_de(conn: sqlite3.Connection, titular: str, parte_id: int,
              iban: str) -> sqlite3.Row | None:
    columna = _columna_parte(titular)
    return conn.execute(f"SELECT * FROM cuenta_bancaria WHERE titular = ? AND {columna} = ? "
                        "AND iban = ?", (titular, parte_id, normalizar_iban(iban))).fetchone()


def telefono_ref(conn: sqlite3.Connection, proveedor_id: int, antes_de: str,
                 telefono: str | None) -> int | None:
    """El cambio que puso en el maestro el numero llamado, si era el de antes del documento.

    El alta (rev 0) cuenta como de antes de cualquier documento, como en
    reglas.bancaria.telefono_antes_de.
    """
    fila = conn.execute(
        "SELECT c.id, c.valor_nuevo FROM cambio_campo AS c JOIN evento AS e ON e.id = c.evento_id "
        "WHERE c.tabla = 'proveedor' AND c.fila_id = ? AND c.campo = 'telefono_verificacion' "
        "AND (e.en < ? OR c.rev = 0) ORDER BY c.id DESC LIMIT 1",
        (proveedor_id, antes_de)).fetchone()
    if fila is None or fila["valor_nuevo"] is None:
        return None
    valor = json.loads(fila["valor_nuevo"])
    if normalizar_telefono(valor) != normalizar_telefono(telefono):
        return None
    return int(fila["id"])


def _heredada_sin_tocar(conn: sqlite3.Connection, cuenta_id: int) -> bool:
    """Lo unico que se atesta: llego con el primer maestro, sigue en Exact, nunca falto de el
    y nadie ha decidido nada sobre ella (ni una verificacion que no conto). La base lo repite
    en el disparador cuenta_evento_atestada."""
    tipos = [f[0] for f in conn.execute(
        "SELECT tipo FROM cuenta_evento WHERE cuenta_id = ? ORDER BY id", (cuenta_id,))]
    exact = [t for t in tipos if t in ("visto_en_exact", "ausente_en_exact")]
    return ("baseline" in tipos and not set(tipos) & set(DECISIONES_CUENTA)
            and "ausente_en_exact" not in tipos and bool(exact) and exact[-1] == "visto_en_exact")


def decidir(
    conn: sqlite3.Connection, persona: Persona, *, titular: str,
    objetivos: Sequence[tuple[int, str]], decision: Decision, llegada: str | None = None,
    crear: bool = False, datos: dict[str, Any] | None = None,
) -> ResultadoDecision:
    """Una persona con confirmar_iban verifica, rechaza o atesta una o varias cuentas.

    `objetivos` son (proveedor o cliente, IBAN): atestar lo heredado del
    primer maestro es una sola orden para todas las cuentas.

    Un IBAN que el registro no tiene solo se da de alta si `crear` (una
    verificacion o un rechazo de un IBAN que la persona teclea tras llamar):
    entra como verificacion_manual. Atestar es solo para lo heredado sin
    tocar (`_heredada_sin_tocar`). El
    numero llamado se guarda normalizado, y `telefono_ref` apunta al cambio
    que lo puso en el maestro si era el de antes de `llegada` (lo que motivo
    la verificacion). La base comprueba que quien firma tiene el permiso y
    que es su orden.
    """
    if decision.tipo not in DECISIONES_CUENTA:
        raise ValueError(f"{decision.tipo!r} no es una decision de una persona sobre una cuenta")
    motivo = (persona.motivo or "").strip()
    with orden_auditada(conn):
        exigir(conn, persona.usuario_id, Permiso.CONFIRMAR_IBAN.value,
               accion=f"{decision.tipo} una cuenta")
        if not motivo:
            raise FaltaMotivo("una decision sobre una cuenta bancaria pide un motivo")
        columna = _columna_parte(titular)
        for parte_id in sorted({p for p, _i in objetivos}):
            if conn.execute(f"SELECT 1 FROM {titular} WHERE id = ?",
                            (parte_id,)).fetchone() is None:
                raise LookupError(f"no hay {titular} {parte_id}")
        ahora = marca(reloj_de(conn).ahora())
        resultado = ResultadoDecision()
        cuentas: dict[int, dict[str, Any]] = {}
        eventos: dict[int, dict[str, Any]] = {}
        siguiente_cuenta = _siguientes(conn, "cuenta_bancaria")
        siguiente_evento = _siguientes(conn, "cuenta_evento")
        telefono = normalizar_telefono(decision.telefono_usado)
        partes = {p for p, _i in objetivos}
        if titular == "proveedor" and telefono is not None and len(partes) == 1:
            resultado.telefono_ref = telefono_ref(conn, next(iter(partes)), llegada or ahora,
                                                  telefono)
        for parte_id, iban in objetivos:
            limpio = normalizar_iban(iban)
            if not validar_iban(limpio):
                raise IbanNoValido(f"{limpio!r} no pasa el digito de control: revisa lo tecleado")
            fila = cuenta_de(conn, titular, parte_id, limpio)
            if fila is None:
                if not crear:
                    raise LookupError(f"el registro no tiene la cuenta {limpio} de {titular} "
                                      f"{parte_id}")
                cuenta_id = siguiente_cuenta
                siguiente_cuenta += 1
                cuentas[cuenta_id] = {
                    "titular": titular, "proveedor_id": parte_id if columna == "proveedor_id"
                    else None, "cliente_id": parte_id if columna == "cliente_id" else None,
                    "iban": limpio, "nombre_titular": None, "primera_vez_en": ahora,
                    "primera_fuente": PrimeraFuenteCuenta.VERIFICACION_MANUAL.value,
                    "importacion_id": None}
                resultado.creada = cuenta_id
            else:
                cuenta_id = int(fila["id"])
                if decision.tipo == "atestada" and not _heredada_sin_tocar(conn, cuenta_id):
                    raise ValueError(f"la cuenta {limpio} no es una heredada sin tocar: se "
                                     "verifica por telefono, no se atesta")
            resultado.cuentas.append(cuenta_id)
            eventos[siguiente_evento] = {
                "cuenta_id": cuenta_id, "tipo": decision.tipo,
                "importacion_id": decision.importacion_id, "documento_id": decision.documento_id,
                "metodo": decision.metodo, "telefono_usado": telefono,
                "telefono_ref": resultado.telefono_ref,
                "persona_contactada": decision.persona_contactada,
                "decision_facturas": decision.decision_facturas, "usuario_id": persona.usuario_id,
                "en": ahora, "nota": decision.nota}
            siguiente_evento += 1
        if not eventos:
            raise ValueError("no hay ninguna cuenta sobre la que decidir")
        evento_id = _siguiente_evento(conn)
        resultado.evento_id = registrar(
            conn, tipo=f"cuenta_{decision.tipo}", actor=persona.usuario_id,
            usuario_id=persona.usuario_id, tabla=titular,
            fila_id=next(iter(partes)) if len(partes) == 1 else None,
            motivo=motivo, peticion_id=persona.peticion_id,
            datos={**(datos or {}), "titular": titular, "llegada": llegada,
                   **_fotos(cuentas, eventos, evento_id)})
        _escribir(conn, cuentas, eventos)
    return resultado


# ------------------------------------------------------------ verificacion

def verificar(conn: sqlite3.Connection) -> list[str]:
    """Que cada cuenta y cada evento de cuenta sea la foto que dejo su evento de auditoria.

    Sin fiarse de los disparadores: una cuenta metida por detras (otro IBAN
    para un proveedor), un evento verificada inventado o una fila editada con
    los disparadores quitados no tienen la foto de un evento de la cadena.
    """
    problemas: list[str] = []
    fotos: dict[str, dict[int, tuple[int, dict[str, Any]]]] = {"cuentas": {},
                                                               "eventos_cuenta": {}}
    for evento_id, datos_json in conn.execute(
            "SELECT id, datos_json FROM evento WHERE json_type(datos_json, '$.eventos_cuenta') "
            "= 'object' ORDER BY id"):
        datos = json.loads(datos_json)
        for clave in fotos:
            for fila_id, foto in (datos.get(clave) or {}).items():
                fotos[clave][int(fila_id)] = (int(evento_id), foto)
    for tabla, clave, columnas in (("cuenta_bancaria", "cuentas", COLUMNAS_CUENTA),
                                   ("cuenta_evento", "eventos_cuenta", COLUMNAS_EVENTO)):
        vistas = set()
        for fila in conn.execute(f"SELECT * FROM {tabla} ORDER BY id"):
            vistas.add(fila["id"])
            registrada = fotos[clave].get(fila["id"])
            if registrada is None:
                problemas.append(f"{tabla} {fila['id']} no tiene su evento: se ha metido por "
                                 "detras")
                continue
            evento_id, foto = registrada
            distintas = [c for c in columnas if foto.get(c) != fila[c]]
            if distintas or fila["evento_id"] != evento_id:
                problemas.append(f"{tabla} {fila['id']}: {', '.join(distintas or ['evento_id'])} "
                                 f"no es lo que registro el evento {evento_id} (se ha "
                                 "modificado por detras)")
        for fila_id in sorted(set(fotos[clave]) - vistas):
            problemas.append(f"el evento {fotos[clave][fila_id][0]} registro {tabla} {fila_id}, "
                             "que ya no existe: se ha borrado")
    return problemas
