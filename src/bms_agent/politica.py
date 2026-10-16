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

from .almacen import exigir_sin_datos_de_prueba, reloj_de, transaccion, usuario_sistema
from .almacen.evidencia import foto
from .almacen.unidades import PerdidaDePrecision, a_cent, sha256_texto
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
    exigir_sin_datos_de_prueba(conn, texto, f"la politica {fichero}")
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


def politica_de(reglas: str | None, empresa_texto: str | None,
                btw_texto: str | None = None) -> Politica:
    """La Politica de las reglas con lo que dicen reglas.yaml, empresa.yaml y btw.yaml."""
    from .reglas.normas import normalizar_btw, normalizar_kvk, normalizar_nombre

    empresa_ = empresa_de_yaml(empresa_texto)
    btw = config_btw_de_yaml(btw_texto)
    nombres = tuple(sorted({n for n in (normalizar_nombre(x) for x in (
        empresa_.nombre, *empresa_.otros_nombres)) if n}))
    return Politica(**ajustes_de_reglas(reglas), empresa_nombres=nombres,
                    empresa_btw=normalizar_btw(empresa_.btw_id),
                    empresa_kvk=normalizar_kvk(empresa_.kvk),
                    empresa_ibans=tuple(sorted(empresa_.cuentas_propias)),
                    iva_tipos_habituales_pb=btw.tipos_habituales_pb,
                    kor_umbral_cent=btw.kor_umbral_cent, kor_aviso_pct=btw.kor_aviso_pct)


def politica_reglas(conn: sqlite3.Connection) -> Politica:
    """La Politica con que se evalua ahora: los ultimos reglas.yaml, empresa.yaml y btw.yaml
    cargados.

    Sin ninguno cargado valen los valores del codigo, que son los de los
    ficheros de config/ (un test lo comprueba).
    """
    reglas = vigente(conn, FICHERO_REGLAS)
    empresa_ = vigente(conn, FICHERO_EMPRESA)
    btw = vigente(conn, FICHERO_BTW)
    return politica_de(reglas["contenido"] if reglas else None,
                       empresa_["contenido"] if empresa_ else None,
                       btw["contenido"] if btw else None)


# ------------------------------------------------------------ el BTW (paso 11)

FICHERO_BTW = "btw.yaml"
PERIODICIDAD_BTW = "trimestral"
SISTEMA_BTW = "factuurstelsel"
PLAZO_BTW = "ultimo_dia_mes_siguiente"
FUERA = "fuera"
PAISES_BTW = ("nacional", "ue", "fuera_ue")
TRATAMIENTOS_BTW = ("estandar", "tipo_cero", "autoliquidacion", "exento", "kor")

# Lo que puede ser cada linea en la declaracion, segun lo que es (y no segun lo
# que diga el fichero): una venta con IVA normal va a 1a-1c (base y cuota) y solo
# a 1e si su tipo es cero (1e no lleva columna de IVA: un 21 % alli perderia la
# cuota cobrada de 5a); una sin IVA (tipo cero, IVA trasladado al cliente) va
# solo con su base a 1e o a 3a-3c; el IVA trasladado de una compra se
# autoliquida en 2a, 4a o 4b; la cuota de una compra con IVA es IVA soportado
# (5b). Un fichero que pone una linea donde no puede ir no se carga: el mapeo es
# del asesor, pero que 5b no reciba una venta es de la declaracion.
_RUBRICAS_VENTA_CON_IVA = frozenset({"1a", "1b", "1c"})
_RUBRICAS_VENTA_AL_CERO = frozenset({"1e"})
_RUBRICAS_VENTA_SIN_IVA = frozenset({"1e", "3a", "3b", "3c"})
_RUBRICAS_AUTOLIQUIDACION = frozenset({"2a", "4a", "4b"})
RUBRICAS_AUTOLIQUIDACION = _RUBRICAS_AUTOLIQUIDACION

# Los valores de partida, los mismos que config/btw.yaml (un test lo comprueba).
_VENTAS_DE_PARTIDA = (
    ("autoliquidacion:fuera_ue", "1e"), ("autoliquidacion:nacional", "1e"),
    ("autoliquidacion:ue", "3b"), ("estandar:0", "1e"), ("estandar:2100", "1a"),
    ("estandar:900", "1b"), ("estandar:otros", "1c"), ("exento", FUERA), ("kor", FUERA),
    ("tipo_cero", "1e"),
)
_COMPRAS_DE_PARTIDA = (
    ("autoliquidacion:fuera_ue", "4a"), ("autoliquidacion:nacional", "2a"),
    ("autoliquidacion:ue", "4b"), ("estandar", "5b"), ("exento", FUERA), ("kor", FUERA),
    ("tipo_cero", FUERA),
)


@dataclass(frozen=True)
class ConfigBtw:
    """Como se prepara la declaracion del BTW (config/btw.yaml), por confirmar con el asesor.

    `ventas` y `compras` dicen a que rubrica va cada linea de IVA, por su clave:
    el tratamiento y, con IVA normal en una venta, el tipo en puntos basicos
    ("estandar:2100", "estandar:otros") o, con el IVA trasladado, de donde es la
    contraparte ("autoliquidacion:ue"). FUERA: no va en la declaracion. La
    periodicidad, el sistema y los plazos solo admiten lo que sabe hacer la V1:
    trimestral, por fecha de factura (factuurstelsel) y el ultimo dia del mes
    siguiente al trimestre.
    """

    confirmado: bool = False
    periodicidad: str = PERIODICIDAD_BTW
    sistema: str = SISTEMA_BTW
    plazo_presentacion: str = PLAZO_BTW
    plazo_pago: str = PLAZO_BTW
    tipos_habituales_pb: tuple[int, ...] = (0, 900, 2100)
    tipo_autoliquidacion_pb: int = 2100
    autoliquidacion_deducible: bool = True
    kor_umbral_cent: int = 2_000_000
    kor_aviso_pct: int = 90
    ventas: tuple[tuple[str, str], ...] = _VENTAS_DE_PARTIDA
    compras: tuple[tuple[str, str], ...] = _COMPRAS_DE_PARTIDA

    def rubrica(self, sentido: str, clave: str) -> str | None:
        """La rubrica de una clave (None si el fichero no la dice)."""
        return dict(self.ventas if sentido == "saliente" else self.compras).get(clave)

    def como_dict(self) -> dict[str, Any]:
        return {"confirmado": self.confirmado, "periodicidad": self.periodicidad,
                "sistema": self.sistema, "plazo_presentacion": self.plazo_presentacion,
                "plazo_pago": self.plazo_pago,
                "tipos_habituales_pb": list(self.tipos_habituales_pb),
                "tipo_autoliquidacion_pb": self.tipo_autoliquidacion_pb,
                "autoliquidacion_deducible": self.autoliquidacion_deducible,
                "kor_umbral_cent": self.kor_umbral_cent, "kor_aviso_pct": self.kor_aviso_pct,
                "ventas": dict(self.ventas), "compras": dict(self.compras)}

    def sha256(self) -> str:
        """El hash de lo que dice, sin comentarios ni orden: va en cada hoja de trabajo."""
        from .almacen.unidades import json_canonico

        return sha256_texto(json_canonico(self.como_dict()))


def _porcentaje_pb(texto: Any, donde: str) -> int:
    from .almacen.unidades import PerdidaDePrecision, a_pb

    if isinstance(texto, (float, bool)) or texto is None:
        raise PoliticaNoValida(f"{donde}: un tipo se escribe entre comillas (\"21\")")
    try:
        valor = Decimal(str(texto).strip().rstrip("%").replace(",", "."))
        pb = a_pb(valor)
    except (InvalidOperation, PerdidaDePrecision):
        raise PoliticaNoValida(f"{donde}: {texto!r} no es un porcentaje") from None
    if not 0 <= pb <= 10000:
        raise PoliticaNoValida(f"{donde}: un tipo va de 0 a 100")
    return pb


def _mapa(datos: Any, donde: str, claves: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(datos, dict):
        raise PoliticaNoValida(f"{donde}: se espera un mapa")
    sobran = sorted(set(map(str, datos)) - set(claves))
    faltan = sorted(set(claves) - set(map(str, datos)))
    if sobran or faltan:
        raise PoliticaNoValida(f"{donde}: " + "; ".join(
            ([f"no lleva {', '.join(sobran)}"] if sobran else [])
            + ([f"falta {', '.join(faltan)}"] if faltan else [])))
    return {str(k): v for k, v in datos.items()}


def _rubrica(valor: Any, donde: str, admitidas: frozenset[str]) -> str:
    texto = str(valor).strip().lower() if isinstance(valor, str) else None
    if texto not in admitidas:
        raise PoliticaNoValida(f"{donde}: {valor!r} no puede ir ahi; va a "
                               f"{', '.join(sorted(admitidas))}")
    return texto


def _por_pais(datos: Any, donde: str, admitidas: frozenset[str]) -> dict[str, str]:
    mapa = _mapa(datos, donde, PAISES_BTW)
    return {f"autoliquidacion:{p}": _rubrica(mapa[p], f"{donde}.{p}", admitidas)
            for p in PAISES_BTW}


def config_btw_de_yaml(texto: str | None) -> ConfigBtw:
    """La configuracion del BTW de un btw.yaml (la de partida si no hay fichero).

    Se rechaza entero lo que la V1 no sabe hacer (otra periodicidad, kasstelsel,
    otros plazos), un mapeo incompleto o una linea donde no puede ir: un
    fichero que no se entiende no prepara ninguna declaracion.
    """
    if texto is None:
        return ConfigBtw()
    datos = yaml.safe_load(texto) or {}
    if not isinstance(datos, dict):
        raise PoliticaNoValida("btw.yaml es un mapa")
    datos = _mapa(datos, "btw.yaml", ("confirmado", "periodicidad", "sistema", "plazos",
                                      "tipos", "kor", "ventas", "compras"))
    if not isinstance(datos["confirmado"], bool):
        raise PoliticaNoValida("btw.yaml: confirmado es true o false")
    if datos["periodicidad"] != PERIODICIDAD_BTW:
        raise PoliticaNoValida(f"btw.yaml: la V1 solo prepara la declaracion "
                               f"{PERIODICIDAD_BTW}, no {datos['periodicidad']!r}")
    if datos["sistema"] != SISTEMA_BTW:
        raise PoliticaNoValida(f"btw.yaml: la V1 solo sabe el {SISTEMA_BTW} (por fecha de "
                               f"factura), no {datos['sistema']!r}")
    plazos = _mapa(datos["plazos"], "btw.yaml: plazos", ("presentacion", "pago"))
    for clave, valor in plazos.items():
        if valor != PLAZO_BTW:
            raise PoliticaNoValida(f"btw.yaml: plazos.{clave} solo puede ser {PLAZO_BTW}")
    tipos = _mapa(datos["tipos"], "btw.yaml: tipos",
                  ("habituales", "autoliquidacion", "autoliquidacion_deducible"))
    if not isinstance(tipos["habituales"], list) or not tipos["habituales"]:
        raise PoliticaNoValida("btw.yaml: tipos.habituales es una lista de tipos")
    habituales = tuple(sorted({_porcentaje_pb(t, "btw.yaml: tipos.habituales")
                               for t in tipos["habituales"]}))
    autoliquidacion = _porcentaje_pb(tipos["autoliquidacion"], "btw.yaml: tipos.autoliquidacion")
    if autoliquidacion == 0:
        raise PoliticaNoValida("btw.yaml: el IVA trasladado no se autoliquida al 0 %")
    if not isinstance(tipos["autoliquidacion_deducible"], bool):
        raise PoliticaNoValida("btw.yaml: tipos.autoliquidacion_deducible es true o false")
    kor = _mapa(datos["kor"], "btw.yaml: kor", ("umbral", "aviso_pct"))
    umbral = _valor(kor["umbral"], Decimal, "btw.yaml: kor.umbral")
    if not Decimal(1000) <= umbral <= Decimal(1_000_000):
        raise PoliticaNoValida("btw.yaml: kor.umbral va de 1.000 a 1.000.000 euros")
    try:
        umbral_cent = a_cent(umbral)
    except PerdidaDePrecision:
        raise PoliticaNoValida(f"btw.yaml: kor.umbral {kor['umbral']!r} tiene mas de dos "
                               "decimales") from None
    aviso = _valor(kor["aviso_pct"], int, "btw.yaml: kor.aviso_pct")
    if not 50 <= aviso <= 100:
        raise PoliticaNoValida("btw.yaml: kor.aviso_pct va de 50 a 100: por debajo avisaria "
                               "de cualquier proveedor con KOR")

    ventas_ = _mapa(datos["ventas"], "btw.yaml: ventas", TRATAMIENTOS_BTW)
    ventas: dict[str, str] = {}
    estandar = ventas_["estandar"]
    if not isinstance(estandar, dict) or "otros" not in estandar:
        raise PoliticaNoValida("btw.yaml: ventas.estandar es un mapa de tipo a rubrica, con "
                               "otros")
    for tipo, rubrica in estandar.items():
        clave = "otros" if tipo == "otros" else str(_porcentaje_pb(
            tipo, "btw.yaml: ventas.estandar"))
        ventas[f"estandar:{clave}"] = _rubrica(
            rubrica, f"btw.yaml: ventas.estandar.{tipo}",
            _RUBRICAS_VENTA_AL_CERO if clave == "0" else _RUBRICAS_VENTA_CON_IVA)
    ventas["tipo_cero"] = _rubrica(ventas_["tipo_cero"], "btw.yaml: ventas.tipo_cero",
                                   _RUBRICAS_VENTA_SIN_IVA | {FUERA})
    ventas.update(_por_pais(ventas_["autoliquidacion"], "btw.yaml: ventas.autoliquidacion",
                            _RUBRICAS_VENTA_SIN_IVA))
    for tratamiento in ("exento", "kor"):
        ventas[tratamiento] = _rubrica(ventas_[tratamiento], f"btw.yaml: ventas.{tratamiento}",
                                       frozenset({"1e", FUERA}))

    compras_ = _mapa(datos["compras"], "btw.yaml: compras", TRATAMIENTOS_BTW)
    compras = {"estandar": _rubrica(compras_["estandar"], "btw.yaml: compras.estandar",
                                    frozenset({"5b", FUERA}))}
    compras.update(_por_pais(compras_["autoliquidacion"], "btw.yaml: compras.autoliquidacion",
                             _RUBRICAS_AUTOLIQUIDACION))
    for tratamiento in ("tipo_cero", "exento", "kor"):
        compras[tratamiento] = _rubrica(compras_[tratamiento],
                                        f"btw.yaml: compras.{tratamiento}", frozenset({FUERA}))
    return ConfigBtw(confirmado=datos["confirmado"], tipos_habituales_pb=habituales,
                     tipo_autoliquidacion_pb=autoliquidacion,
                     autoliquidacion_deducible=tipos["autoliquidacion_deducible"],
                     kor_umbral_cent=umbral_cent, kor_aviso_pct=aviso,
                     ventas=tuple(sorted(ventas.items())), compras=tuple(sorted(compras.items())))


def _tipo_texto(pb: int) -> str:
    """Un tipo en puntos basicos como se escribe en el fichero: 2100 es "21", 550 "5.5"."""
    from .almacen.unidades import de_pb

    texto = format(de_pb(pb).normalize(), "f")
    return texto


def btw_a_yaml(config: ConfigBtw) -> str:
    """Una configuracion como texto de btw.yaml (lo lee config_btw_de_yaml y da la misma)."""
    def por_pais(mapa: dict[str, str]) -> dict[str, str]:
        return {p: mapa[f"autoliquidacion:{p}"] for p in PAISES_BTW}

    ventas, compras = dict(config.ventas), dict(config.compras)
    estandar = {("otros" if k == "estandar:otros" else _tipo_texto(int(k.split(":")[1]))): v
                for k, v in ventas.items() if k.startswith("estandar:")}
    datos = {
        "confirmado": config.confirmado, "periodicidad": config.periodicidad,
        "sistema": config.sistema,
        "plazos": {"presentacion": config.plazo_presentacion, "pago": config.plazo_pago},
        "tipos": {"habituales": [_tipo_texto(t) for t in config.tipos_habituales_pb],
                  "autoliquidacion": _tipo_texto(config.tipo_autoliquidacion_pb),
                  "autoliquidacion_deducible": config.autoliquidacion_deducible},
        "kor": {"umbral": f"{Decimal(config.kor_umbral_cent).scaleb(-2):.2f}",
                "aviso_pct": config.kor_aviso_pct},
        "ventas": {"estandar": estandar, "tipo_cero": ventas["tipo_cero"],
                   "autoliquidacion": por_pais(ventas), "exento": ventas["exento"],
                   "kor": ventas["kor"]},
        "compras": {"estandar": compras["estandar"], "autoliquidacion": por_pais(compras),
                    "tipo_cero": compras["tipo_cero"], "exento": compras["exento"],
                    "kor": compras["kor"]},
    }
    return ("# btw.yaml apuntado por el sistema con los valores de partida del codigo "
            "(politica.ConfigBtw).\n" + yaml.safe_dump(datos, sort_keys=False,
                                                        allow_unicode=True))


def config_btw(conn: sqlite3.Connection) -> ConfigBtw:
    """La configuracion del BTW que vale ahora: la del ultimo btw.yaml cargado."""
    fila = vigente(conn, FICHERO_BTW)
    return config_btw_de_yaml(fila["contenido"] if fila else None)


def config_btw_y_sha(conn: sqlite3.Connection) -> tuple[ConfigBtw, str]:
    """La configuracion que vale y el sha256 de su texto en politica_version.

    Es el hash que lleva la hoja de trabajo: se resuelve a un texto con una
    consulta. Mientras no hay ninguno cargado es el del texto de partida
    (btw_a_yaml), el mismo que apuntar_btw_en_uso apunta al marcar una hoja lista.
    """
    fila = vigente(conn, FICHERO_BTW)
    if fila is not None:
        return config_btw_de_yaml(fila["contenido"]), fila["sha256"]
    config = ConfigBtw()
    return config, sha256_texto(btw_a_yaml(config))


def apuntar_btw_en_uso(conn: sqlite3.Connection, usuario_id: int | None = None) -> ConfigBtw:
    """La configuracion del BTW que vale, apuntada en politica_version si no habia ninguna.

    Como los pesos de la prioridad: la hoja de trabajo que se marca lista o se
    presenta lleva el hash de su configuracion, y ese hash tiene que poder
    resolverse a un texto.
    """
    fila = vigente(conn, FICHERO_BTW)
    if fila is not None:
        return config_btw_de_yaml(fila["contenido"])
    config = ConfigBtw()
    registrar(conn, FICHERO_BTW, btw_a_yaml(config), usuario_id)
    return config


def empresa(conn: sqlite3.Connection) -> Empresa:
    fila = vigente(conn, FICHERO_EMPRESA)
    return empresa_de_yaml(fila["contenido"] if fila else None)


def cargar(conn: sqlite3.Connection, ruta: str | Path,
           usuario_id: int | None) -> tuple[str, bool]:
    """Valida y apunta un fichero de config/ por su nombre. Devuelve un resumen y si era nuevo.

    prioridad.yaml (los pesos), reglas.yaml (tolerancias, frescura, el
    interruptor de las cuentas y el enfriamiento del telefono), empresa.yaml
    (la identidad de BM Support BV, que A8 y F10 comparan) o btw.yaml (la
    declaracion del BTW, el umbral de la KOR y los tipos habituales). Lo carga una
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
    if ruta.name == FICHERO_BTW:
        btw = config_btw_de_yaml(texto)
        return (f"BTW {btw.periodicidad}, {btw.sistema}"
                + ("" if btw.confirmado else " (por confirmar con el asesor)"),
                registrar(conn, FICHERO_BTW, texto, usuario_id))
    raise PoliticaNoValida(f"{ruta.name}: se cargan {FICHERO_PRIORIDAD}, {FICHERO_REGLAS}, "
                           f"{FICHERO_EMPRESA} o {FICHERO_BTW}")
