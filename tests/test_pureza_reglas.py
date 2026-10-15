"""Las reglas son funciones puras, y leen solo lo que dicen que leen.

Dos pruebas, como pide el paso 3 de la especificacion:

- Leyendo el codigo (AST): ningun modulo de reglas/ salvo instantanea.py
  importa nada que toque la base, el reloj, el entorno, la red o el azar, ni
  llama a open, print o datetime.now. Un test aparte comprueba que la
  busqueda ve lo que tiene que ver.
- Ejecutandolas: cada regla corre sobre instantaneas envueltas en un proxy
  que apunta cada atributo que se lee. Lo leido tiene que estar en lo que la
  regla declara (`Regla.lee`), y entre todos los casos tiene que salir todo
  lo declarado: una declaracion de mas meteria en la huella fuentes que la
  regla no mira.
"""

from __future__ import annotations

import ast
import dataclasses
from datetime import date
from pathlib import Path

import pytest
from test_reglas import factura, instantanea, linea
from test_reglas_paso5 import escenarios as escenarios_paso5

from bms_agent.reglas import catalogo
from bms_agent.reglas.base import (
    CambioTelefono,
    Cuenta,
    EventoCuenta,
    Factura,
    Instantanea,
    Linea,
    Lote,
    Parte,
    Politica,
    Relacion,
    Resultado,
    TramoIva,
    por_factura,
)

REGLAS = Path(__file__).resolve().parent.parent / "src" / "bms_agent" / "reglas"

# Lo unico que puede importar una regla. instantanea.py es el que lee la base.
PERMITIDOS = frozenset({
    "__future__", "bisect", "collections", "collections.abc", "dataclasses", "datetime",
    "decimal", "enum", "fractions", "functools", "hashlib", "itertools", "json", "math",
    "operator", "re", "types", "typing",
})
PROPIOS = frozenset({"base", "calidad", "aritmetica", "iva", "bancaria", "unicidad", "planning",
                     "catalogo", "motor", "anomalias", "identidad", "normas"})
DEL_PAQUETE = frozenset({"dominio"})
LLAMADAS_PROHIBIDAS = frozenset({"open", "eval", "exec", "compile", "__import__", "input",
                                 "print", "breakpoint", "globals"})
ATRIBUTOS_PROHIBIDOS = frozenset({
    "now", "today", "utcnow", "fromtimestamp", "environ", "getenv", "execute", "executemany",
    "executescript", "cursor", "connect", "commit", "urandom", "system", "popen",
})


def problemas_de_pureza(fuente: str) -> list[str]:
    """Lo que hace impura una regla, leyendo su codigo."""
    problemas = []
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Import):
            for nombre in nodo.names:
                if nombre.name not in PERMITIDOS:
                    problemas.append(f"import {nombre.name}")
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level == 0 and nodo.module not in PERMITIDOS:
                problemas.append(f"from {nodo.module} import")
            elif nodo.level == 1:
                modulos = {nodo.module} if nodo.module else {n.name for n in nodo.names}
                if not modulos <= PROPIOS:
                    problemas.append(f"from .{nodo.module or ''} import {modulos - PROPIOS}")
            elif nodo.level == 2 and nodo.module not in DEL_PAQUETE:
                problemas.append(f"from ..{nodo.module} import")
            elif nodo.level > 2:
                problemas.append("import relativo de fuera del paquete")
        elif isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name):
            if nodo.func.id in LLAMADAS_PROHIBIDAS:
                problemas.append(f"llama a {nodo.func.id}()")
        elif isinstance(nodo, ast.Attribute) and nodo.attr in ATRIBUTOS_PROHIBIDOS:
            problemas.append(f"usa .{nodo.attr}")
        elif isinstance(nodo, ast.Global):
            problemas.append("usa global")
    return problemas


def _modulos_de_reglas() -> list[Path]:
    modulos = sorted(p for p in REGLAS.glob("*.py") if p.name != "instantanea.py")
    assert {p.stem for p in modulos} >= PROPIOS
    return modulos


@pytest.mark.parametrize("modulo", _modulos_de_reglas(), ids=lambda p: p.name)
def test_ninguna_regla_toca_la_base_el_reloj_el_entorno_ni_la_red(modulo) -> None:
    assert problemas_de_pureza(modulo.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("fuente", [
    "import sqlite3",
    "import os",
    "import time",
    "import random",
    "from pathlib import Path",
    "from urllib.request import urlopen",
    "from ..almacen import abrir",
    "from ..reloj import RELOJ_SISTEMA",
    "from .instantanea import construir",
    "from ... import algo",
    "x = datetime.now()",
    "x = date.today()",
    "x = os.environ['BMS_DB']",
    "x = os.getenv('BMS_DB')",
    "conn.execute('SELECT 1')",
    "open('fichero')",
    "print('hola')",
    "def f():\n    global X\n    X = 1",
])
def test_la_busqueda_de_impurezas_ve_lo_que_tiene_que_ver(fuente) -> None:
    assert problemas_de_pureza(fuente)


def test_solo_instantanea_lee_la_base() -> None:
    fuente = (REGLAS / "instantanea.py").read_text(encoding="utf-8")
    assert "import sqlite3" in fuente
    for modulo in _modulos_de_reglas():
        assert "sqlite3" not in modulo.read_text(encoding="utf-8"), modulo.name


# --- el proxy que apunta lo que se lee ---

_TIPOS = {Instantanea: "instantanea", Factura: "factura", Linea: "linea",
          TramoIva: "tramo_iva", Relacion: "relacion", Politica: "politica",
          Parte: "parte", Cuenta: "cuenta", EventoCuenta: "evento_cuenta",
          CambioTelefono: "cambio_telefono", Lote: "lote"}


class Grabadora:
    """Un objeto de la instantanea que apunta cada atributo que se le lee."""

    __slots__ = ("_objeto", "_tipo", "_lecturas")

    def __init__(self, objeto, lecturas: set[str]) -> None:
        self._objeto = objeto
        self._tipo = _TIPOS[type(objeto)]
        self._lecturas = lecturas

    def __getattr__(self, nombre: str):
        self._lecturas.add(f"{self._tipo}.{nombre}")
        return _envolver(getattr(self._objeto, nombre), self._lecturas)


def _envolver(valor, lecturas: set[str]):
    if type(valor) in _TIPOS:
        return Grabadora(valor, lecturas)
    if isinstance(valor, tuple) and not hasattr(valor, "_fields"):
        return tuple(_envolver(v, lecturas) for v in valor)
    return valor


def _escenarios() -> list[Instantanea]:
    """Instantaneas que pasan por cada rama de cada regla."""
    sin_periodo = factura(7, periodo_inicio=None, periodo_fin=None, lineas=(
        linea(70, fecha_inicio=date(2026, 9, 7), fecha_fin=date(2026, 9, 13),
              fecha_trabajo=date(2026, 9, 8)),))
    ilegible = factura(8, base_cent=None, iva_cent=None, total_cent=None, tipo_iva_pb=None,
                       tratamiento_iva=None, fecha_factura=None, numero=None, numero_norm=None,
                       emisor_nombre_doc=None, emisor_btw_doc=None, emisor_kvk_doc=None,
                       parte=None, ilegibles=frozenset({"base_cent", "total_cent"}),
                       lineas=(linea(80, cantidad_mil=None, tarifa_e4=None, importe_cent=None,
                                     tipo_iva_pb=None,
                                     ilegibles=frozenset({"importe_cent"})),))
    solo_kvk = factura(9, emisor_nombre_doc=None, emisor_btw_doc=None, parte="kvk:87654321")
    venta_v1 = factura(10, sentido="saliente", emisor_nombre_doc="BM Support BV", parte=None,
                       no_solicitados=frozenset({"receptor_nombre_doc", "receptor_btw_doc"}))
    venta = factura(11, sentido="saliente", cliente_id=3, parte="cliente:3",
                    receptor_nombre_doc="Havenbedrijf", receptor_btw_doc="NL009999999B01")
    traslado = factura(12, tratamiento_iva="autoliquidacion", tipo_iva_pb=None, iva_cent=None,
                       total_cent=34000, receptor_btw_doc=None,
                       ilegibles=frozenset({"receptor_btw_doc"}))
    traslado_v1 = factura(13, tratamiento_iva="autoliquidacion", iva_cent=0, total_cent=34000,
                          no_solicitados=frozenset({"receptor_btw_doc"}))
    traslado_sin_btw = factura(14, tratamiento_iva="autoliquidacion", iva_cent=0,
                               total_cent=34000)
    kor = factura(15, tratamiento_iva="kor", iva_cent=None, base_cent=None, total_cent=None)
    desglose = factura(16, desglose=(TramoIva(160, 2100, 20000, 4200),
                                     TramoIva(161, None, None, None)))
    desglose_malo = factura(17, desglose=(TramoIva(170, 900, 10000, 950),))
    duplicadas = [factura(20, numero_norm="DUP"), factura(21, numero_norm="DUP",
                                                          fecha_factura=date(2026, 9, 20))]
    abono = factura(22, tipo="nota_credito")
    al_reves = factura(23, periodo_inicio=date(2026, 9, 20), periodo_fin=date(2026, 9, 1),
                       parte="btw:NL007777777B01")
    tarifas = [factura(30 + i, parte="btw:NL005555555B01", numero_norm=f"T{i}",
                       fecha_factura=date(2026, 3 + i, 5),
                       periodo_inicio=date(2026, 3 + i, 1), periodo_fin=date(2026, 3 + i, 2),
                       lineas=(linea(300 + i, tarifa_e4=425000 + i * 10000),))
               for i in range(3)]
    fuera = [factura(40, anulada=True), factura(41, fusionada_en_id=1)]
    todas = [factura(1), factura(2, iban_doc=None, moneda="USD"), sin_periodo, ilegible,
             solo_kvk, venta_v1, venta, traslado, traslado_v1, traslado_sin_btw, kor, desglose,
             desglose_malo, *duplicadas, abono, al_reves, *tarifas, *fuera,
             factura(3, iban_doc="NL00XXXX", lineas=(linea(30, importe_cent=1),))]
    return [
        instantanea(*todas, relaciones=[Relacion(31, 32, "sustituye")]),
        instantanea(factura(50, lineas=())),
        instantanea(factura(51, fusionada_en_id=None, lineas=(), base_cent=None)),
        # Paso 5: con maestros, registro de cuentas, telefonos e importaciones.
        *escenarios_paso5(),
    ]


@pytest.mark.parametrize("regla", catalogo.CATALOGO, ids=lambda r: r.id)
def test_cada_regla_lee_solo_lo_que_declara_y_todo_lo_que_declara(regla) -> None:
    leidas: set[str] = set()
    for escenario in _escenarios():
        lecturas: set[str] = set()
        list(regla.evaluar(Grabadora(escenario, lecturas)))
        assert lecturas <= regla.lee, f"{regla.id} lee sin declararlo: {lecturas - regla.lee}"
        leidas |= lecturas
    assert regla.lee <= leidas, f"{regla.id} declara y no lee: {regla.lee - leidas}"


def test_el_proxy_da_lo_mismo_que_la_instantanea() -> None:
    """Envolver no cambia lo que dice una regla: lo que se mide es lo que corre."""
    for escenario in _escenarios():
        for regla in catalogo.CATALOGO:
            directo = list(regla.evaluar(escenario))
            envuelto = list(regla.evaluar(Grabadora(escenario, set())))
            assert envuelto == directo, regla.id


def test_una_regla_que_lee_de_mas_se_ve() -> None:
    def curiosa(f, _politica):
        return [Resultado("D4", "factura", f.id, "ok", str(f.iban_doc))]

    regla = dataclasses.replace(catalogo.regla("D4"), evaluar=por_factura("D4", curiosa))
    lecturas: set[str] = set()
    list(regla.evaluar(Grabadora(_escenarios()[0], lecturas)))
    assert "factura.iban_doc" in lecturas - regla.lee
