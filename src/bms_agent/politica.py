"""La politica: los ficheros de config/ que cambian como decide el sistema, con su hash.

Cada fichero que se aplica (las tarifas que se siembran, los pesos de la
prioridad) queda en politica_version con su texto entero y su sha256, y con
su evento de auditoria: meses despues se puede saber con que pesos se
ordeno una lista o con que tabla se imputo una linea.

La version que vale de cada fichero es la ultima que se cargo, por orden de
carga y no por fecha: volver a una anterior el mismo dia la pone en vigor
(migracion 0004).

Los pesos de la prioridad que valen son los del ultimo prioridad.yaml
cargado. Hasta que se carga uno, valen los de prioridad.Pesos, que son los
mismos que trae config/prioridad.yaml (un test lo comprueba), y la primera
pasada que los usa los apunta (`apuntar_pesos_en_uso`): ninguna prioridad
guardada lleva el hash de unos pesos que politica_version no explique. Un
fichero que no tiene la forma entera se rechaza antes de apuntarse: los
suelos de la prioridad no estan en el fichero, asi que ningun fichero los
puede relajar.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from .almacen import reloj_de, transaccion, usuario_sistema
from .almacen.evidencia import foto
from .almacen.unidades import sha256_texto
from .auditoria import registrar as registrar_evento
from .prioridad import PESOS, Pesos, pesos_a_yaml, pesos_de_yaml
from .reglas.base import Politica
from .reloj import marca

FICHERO_PRIORIDAD = "prioridad.yaml"


def registrar(conn: sqlite3.Connection, fichero: str, texto: str,
              usuario_id: int | None = None) -> bool:
    """Apunta un fichero en politica_version si no es ya la version vigente. Devuelve si
    se apunto.

    Volver a una version anterior es otra fila, tambien el mismo dia: la que
    vale es la ultima que se cargo. Antes se miraba si ese contenido ya
    estaba apuntado ese dia, y volver de B a A no hacia nada aunque la CLI
    dijera que A era la vigente.
    """
    sha256 = sha256_texto(texto)
    reloj = reloj_de(conn)
    hoy = reloj.hoy().isoformat()
    ultima = vigente(conn, fichero)
    if ultima is not None and ultima["sha256"] == sha256:
        return False
    sistema = usuario_sistema(conn, "sistema")
    with transaccion(conn):
        fila_id = int(conn.execute(
            "INSERT INTO politica_version (sha256, fichero, contenido, vigente_desde, cargada_en, "
            "cargada_por) VALUES (?, ?, ?, ?, ?, ?)",
            (sha256, fichero, texto, hoy, marca(reloj.ahora()), usuario_id or sistema),
        ).lastrowid)
        registrar_evento(conn, tipo="politica_cargada", actor=sistema, usuario_id=usuario_id,
                         tabla="politica_version", fila_id=fila_id,
                         datos={"fichero": fichero, "sha256": sha256,
                                "fila": foto(conn, "politica_version", fila_id)})
    return True


def vigente(conn: sqlite3.Connection, fichero: str) -> sqlite3.Row | None:
    """La ultima version cargada de un fichero, o None."""
    return conn.execute(
        "SELECT * FROM politica_version WHERE fichero = ? ORDER BY id DESC LIMIT 1",
        (fichero,)).fetchone()


def pesos_prioridad(conn: sqlite3.Connection) -> Pesos:
    """Los pesos de la prioridad que valen ahora: los del ultimo prioridad.yaml cargado."""
    fila = vigente(conn, FICHERO_PRIORIDAD)
    return PESOS if fila is None else pesos_de_yaml(fila["contenido"])


def apuntar_pesos_en_uso(conn: sqlite3.Connection) -> Pesos:
    """Los pesos que valen, apuntados en politica_version si todavia no habia ninguno.

    Sin fichero cargado valen los de prioridad.Pesos; la primera pasada que
    calcula prioridades los apunta con su texto (`prioridad.pesos_a_yaml`),
    para que el hash que llevan las caches tenga siempre su version.
    """
    fila = vigente(conn, FICHERO_PRIORIDAD)
    if fila is not None:
        return pesos_de_yaml(fila["contenido"])
    registrar(conn, FICHERO_PRIORIDAD, pesos_a_yaml(PESOS))
    return PESOS


def cargar_prioridad(conn: sqlite3.Connection, ruta: str | Path,
                     usuario_id: int | None = None) -> tuple[Pesos, bool]:
    """Valida y apunta un fichero de pesos. Devuelve los pesos y si era nuevo.

    Un fichero que no tiene la forma entera lanza PesosNoValidos y no se
    apunta nada.
    """
    texto = Path(ruta).read_text(encoding="utf-8")
    pesos = pesos_de_yaml(texto)
    return pesos, registrar(conn, FICHERO_PRIORIDAD, texto, usuario_id)


# ------------------------------------------------------------ reglas y empresa (paso 5)

FICHERO_REGLAS = "reglas.yaml"
FICHERO_EMPRESA = "empresa.yaml"
NOMBRE_EMPRESA = "BM Support BV"


class PoliticaNoValida(ValueError):
    """Un fichero de reglas o de empresa sin la forma que se espera: no se apunta."""


# Lo que se puede ajustar de las reglas desde config/reglas.yaml, por seccion.
# Lo duro (que reglas bloquean, cuales no se anulan, cuales son pegajosas)
# esta en el codigo y no aparece aqui: ningun fichero lo puede relajar.
_REGLAS: dict[str, dict[str, tuple[str, type]]] = {
    "aritmetica": {"tolerancia_linea": ("tolerancia_linea", Decimal),
                   "tolerancia_factura": ("tolerancia_factura", Decimal)},
    "duplicados": {"ventana_dias": ("ventana_duplicado_dias", int),
                   "tolerancia": ("tolerancia_duplicado", Decimal)},
    "cuentas": {"solo_verificadas": ("iban_solo_verificadas", bool),
                "enfriamiento_telefono_dias": ("enfriamiento_telefono_dias", int)},
    "frescura": {"exact_dias": ("frescura_exact_dias", int),
                 "trnsprnt_dias": ("frescura_trnsprnt_dias", int),
                 "extractos_dias_laborables": ("frescura_banco_dias_laborables", int)},
}


@dataclass(frozen=True)
class Empresa:
    """La identidad de BM Support BV (config/empresa.yaml). Lo que falta se queda en None."""

    nombre: str = NOMBRE_EMPRESA
    otros_nombres: tuple[str, ...] = ()
    btw_id: str | None = None
    kvk: str | None = None
    cuentas_propias: tuple[str, ...] = ()


def _valor(texto: Any, tipo: type, donde: str) -> Any:
    if tipo is bool:
        if not isinstance(texto, bool):
            raise PoliticaNoValida(f"{donde}: se espera true o false")
        return texto
    if tipo is int:
        if isinstance(texto, bool) or not isinstance(texto, int) or texto < 0:
            raise PoliticaNoValida(f"{donde}: se espera un entero no negativo")
        return texto
    if isinstance(texto, float):
        raise PoliticaNoValida(f"{donde}: una tolerancia se escribe entre comillas ('0.01')")
    try:
        valor = Decimal(str(texto))
    except InvalidOperation:
        raise PoliticaNoValida(f"{donde}: {texto!r} no es un numero") from None
    if valor < 0:
        raise PoliticaNoValida(f"{donde}: no puede ser negativo")
    return valor


def ajustes_de_reglas(texto: str | None) -> dict[str, Any]:
    """Los parametros de Politica que dice un reglas.yaml (vacio si no hay fichero)."""
    if texto is None:
        return {}
    datos = yaml.safe_load(texto) or {}
    if not isinstance(datos, dict):
        raise PoliticaNoValida("reglas.yaml es un mapa de secciones")
    salida: dict[str, Any] = {}
    for seccion, valores in datos.items():
        if seccion not in _REGLAS or not isinstance(valores, dict):
            raise PoliticaNoValida(f"reglas.yaml: no hay una seccion {seccion!r} que se pueda "
                                   "ajustar")
        for clave, texto_valor in valores.items():
            if clave not in _REGLAS[seccion]:
                raise PoliticaNoValida(f"reglas.yaml: {seccion}.{clave} no se ajusta desde aqui")
            campo, tipo = _REGLAS[seccion][clave]
            salida[campo] = _valor(texto_valor, tipo, f"{seccion}.{clave}")
    return salida


def empresa_de_yaml(texto: str | None) -> Empresa:
    """La identidad de la empresa de un empresa.yaml (la de partida si no hay fichero)."""
    if texto is None:
        return Empresa()
    datos = yaml.safe_load(texto) or {}
    if not isinstance(datos, dict):
        raise PoliticaNoValida("empresa.yaml es un mapa")
    conocidas = {"nombre", "otros_nombres", "btw_id", "kvk", "cuentas_propias"}
    sobran = set(datos) - conocidas
    if sobran:
        raise PoliticaNoValida(f"empresa.yaml no lleva {', '.join(sorted(sobran))}")
    nombre = datos.get("nombre") or NOMBRE_EMPRESA
    otros = datos.get("otros_nombres") or []
    cuentas = datos.get("cuentas_propias") or []
    if not isinstance(nombre, str) or not isinstance(otros, list) or not isinstance(cuentas, list):
        raise PoliticaNoValida("empresa.yaml: nombre es un texto; otros_nombres y "
                               "cuentas_propias, listas")
    from .reglas.bancaria import validar_iban
    from .reglas.normas import normalizar_iban

    propias = tuple(normalizar_iban(c) for c in cuentas)
    malas = [c for c in propias if not validar_iban(c)]
    if malas:
        raise PoliticaNoValida(f"empresa.yaml: {', '.join(map(str, malas))} no pasa el digito "
                               "de control")
    return Empresa(nombre=nombre, otros_nombres=tuple(str(o) for o in otros),
                   btw_id=str(datos["btw_id"]) if datos.get("btw_id") else None,
                   kvk=str(datos["kvk"]) if datos.get("kvk") else None,
                   cuentas_propias=propias)


def politica_de(reglas: str | None, empresa_texto: str | None) -> Politica:
    """La Politica de las reglas con lo que dicen reglas.yaml y empresa.yaml."""
    from .reglas.normas import normalizar_btw, normalizar_kvk, normalizar_nombre

    empresa_ = empresa_de_yaml(empresa_texto)
    nombres = tuple(sorted({n for n in (normalizar_nombre(x) for x in (
        empresa_.nombre, *empresa_.otros_nombres)) if n}))
    return Politica(**ajustes_de_reglas(reglas), empresa_nombres=nombres,
                    empresa_btw=normalizar_btw(empresa_.btw_id),
                    empresa_kvk=normalizar_kvk(empresa_.kvk))


def politica_reglas(conn: sqlite3.Connection) -> Politica:
    """La Politica con que se evalua ahora: los ultimos reglas.yaml y empresa.yaml cargados.

    Sin ninguno cargado valen los valores del codigo, que son los de los
    ficheros de config/ (un test lo comprueba).
    """
    reglas = vigente(conn, FICHERO_REGLAS)
    empresa_ = vigente(conn, FICHERO_EMPRESA)
    return politica_de(reglas["contenido"] if reglas else None,
                       empresa_["contenido"] if empresa_ else None)


def empresa(conn: sqlite3.Connection) -> Empresa:
    fila = vigente(conn, FICHERO_EMPRESA)
    return empresa_de_yaml(fila["contenido"] if fila else None)


def cargar(conn: sqlite3.Connection, ruta: str | Path,
           usuario_id: int | None = None) -> tuple[str, bool]:
    """Valida y apunta un fichero de config/ por su nombre. Devuelve un resumen y si era nuevo.

    prioridad.yaml (los pesos), reglas.yaml (tolerancias, frescura, el
    interruptor de las cuentas y el enfriamiento del telefono) o empresa.yaml
    (la identidad de BM Support BV). Un fichero que no tiene la forma que se
    espera no se apunta.
    """
    ruta = Path(ruta)
    texto = ruta.read_text(encoding="utf-8")
    if ruta.name == FICHERO_PRIORIDAD:
        pesos = pesos_de_yaml(texto)
        return f"pesos {pesos.sha256()[:12]}", registrar(conn, FICHERO_PRIORIDAD, texto,
                                                         usuario_id)
    if ruta.name == FICHERO_REGLAS:
        ajustes = ajustes_de_reglas(texto)
        return (f"{len(ajustes)} parametros de las reglas",
                registrar(conn, FICHERO_REGLAS, texto, usuario_id))
    if ruta.name == FICHERO_EMPRESA:
        empresa_ = empresa_de_yaml(texto)
        return f"empresa {empresa_.nombre}", registrar(conn, FICHERO_EMPRESA, texto, usuario_id)
    raise PoliticaNoValida(f"{ruta.name}: se cargan {FICHERO_PRIORIDAD}, {FICHERO_REGLAS} o "
                           f"{FICHERO_EMPRESA}")
