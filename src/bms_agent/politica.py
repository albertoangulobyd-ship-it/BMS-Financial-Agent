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
    "pagos": {"tolerancia": ("tolerancia_pago", Decimal),
              "dias_vencida_venta": ("dias_vencida_venta", int),
              "dias_pago_sin_extracto": ("dias_pago_sin_extracto", int),
              "dias_movimiento_sin_casar": ("dias_movimiento_sin_casar", int),
              "ventana_doble_pago_dias": ("ventana_doble_pago_dias", int)},
    "ordenes_compra": {"aviso_consumo_pct": ("po_aviso_consumo_pct", int),
                       "dias_caducidad": ("po_dias_caducidad", int),
                       "margen_prevision_dias": ("po_margen_prevision_dias", int),
                       "semanas_ritmo": ("po_semanas_ritmo", int)},
    "tarifas": {"exceso_bloqueo_pct": ("tarifa_exceso_bloqueo_pct", int)},
    "planning": {"obligatorio": ("planning_obligatorio", bool),
                 "tolerancia_horas_dia": ("planning_tolerancia_horas_dia", Decimal),
                 "dias_gracia_sin_ciclo": ("planning_dias_gracia", int)},
}


# Los limites que ningun reglas.yaml cruza (spec §6: politica.py no relaja lo
# duro). Dentro de ellos el umbral es del negocio (§12, pregunta 7); fuera,
# el fichero desactivaria un control: un enfriamiento de 0 dias quita F8 tras
# un cambio de telefono, una frescura de cien mil dias quita Z1 y deja a A2,
# E1, F2 y F3 dando ok contra un maestro de cualquier edad, y una tolerancia
# de un millon da por buena cualquier suma.
_LIMITES: dict[str, tuple[Decimal | int, Decimal | int]] = {
    "tolerancia_linea": (Decimal("0"), Decimal("1.00")),
    "tolerancia_factura": (Decimal("0"), Decimal("1.00")),
    "ventana_duplicado_dias": (7, 365),
    "tolerancia_duplicado": (Decimal("0"), Decimal("100.00")),
    "enfriamiento_telefono_dias": (7, 90),
    "frescura_exact_dias": (1, 31),
    "frescura_trnsprnt_dias": (1, 31),
    "frescura_banco_dias_laborables": (1, 10),
    # Paso 7: una tolerancia de pago de mas de un euro daria por pagada una
    # factura a la que le falta dinero; una ventana de pago doble de menos de
    # una semana no veria el mismo pago repetido a la semana siguiente.
    "tolerancia_pago": (Decimal("0"), Decimal("1.00")),
    "dias_vencida_venta": (0, 90),
    "dias_pago_sin_extracto": (1, 30),
    "dias_movimiento_sin_casar": (1, 60),
    "ventana_doble_pago_dias": (7, 90),
    # Paso 9: un aviso de consumo por debajo de la mitad salta con cualquier PO
    # y uno por encima del 100 % no salta nunca; una ventana de caducidad de menos
    # de una semana avisa cuando ya no hay tiempo; un ritmo de menos de dos
    # semanas es ruido y uno de mas de medio ano no ve un cambio de ritmo; un
    # exceso que bloquea por encima del 100 % no bloquearia nunca.
    "po_aviso_consumo_pct": (50, 100),
    "po_dias_caducidad": (7, 180),
    "po_margen_prevision_dias": (0, 90),
    "po_semanas_ritmo": (2, 26),
    "tarifa_exceso_bloqueo_pct": (1, 100),
    # Paso 10: una tolerancia de mas de una hora por dia da por buena una factura con
    # medio turno de mas; una gracia de mas de dos meses deja el trabajo sin
    # facturar escondido un trimestre entero.
    "planning_tolerancia_horas_dia": (Decimal("0"), Decimal("1.00")),
    "planning_dias_gracia": (0, 60),
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
            valor = _valor(texto_valor, tipo, f"{seccion}.{clave}")
            if campo in _LIMITES:
                minimo, maximo = _LIMITES[campo]
                if not minimo <= valor <= maximo:
                    raise PoliticaNoValida(f"reglas.yaml: {seccion}.{clave} = {valor} esta fuera "
                                           f"de lo que se admite ({minimo} a {maximo}): "
                                           "desactivaria el control")
            salida[campo] = valor
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
                    empresa_kvk=normalizar_kvk(empresa_.kvk),
                    empresa_ibans=tuple(sorted(empresa_.cuentas_propias)))


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
           usuario_id: int | None) -> tuple[str, bool]:
    """Valida y apunta un fichero de config/ por su nombre. Devuelve un resumen y si era nuevo.

    prioridad.yaml (los pesos), reglas.yaml (tolerancias, frescura, el
    interruptor de las cuentas y el enfriamiento del telefono) o empresa.yaml
    (la identidad de BM Support BV, que A8 y F10 comparan). Lo carga una
    persona con admin (spec §6: la politica es de admin) y queda como quien la
    cargo. Un fichero que no tiene la forma que se espera, o que cruza los
    limites de _LIMITES, no se apunta.
    """
    from .permisos import exigir

    exigir(conn, usuario_id, "admin", accion="cargar la politica")
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
