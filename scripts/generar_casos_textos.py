"""Escribe src/bms_agent/textos/casos.json: los casos de referencia de los textos NL/EN/ES.

La app (frontend/) escribe el detalle de cada hallazgo en neerlandes, en
ingles o en castellano desde sus `valores`, con las plantillas de nl.json,
en.json y es.json y un renderizador propio en TypeScript. Para que diga lo
mismo que la referencia en Python (bms_agent.textos), los dos se prueban
contra este fichero: cada caso trae la plantilla (o la regla y su resultado),
los valores y el texto que tiene que salir en cada idioma (una clave por
idioma de textos.IDIOMAS: un idioma nuevo entra solo al regenerar).

De donde salen los casos de las reglas:

- la base de prueba (`bms-agent demo crear`), hecha en una carpeta temporal
  con un reloj fijo, y las siete extracciones de tests/fixtures/v1: las
  reglas de verdad sobre datos de verdad, con lo que dejan en el almacen
  (hallazgo.valores_json y, de lo que no se pudo mirar, evaluacion);
- EJEMPLOS, abajo: valores con la forma exacta que dan las reglas en los
  tests (se copiaron de ellos), para cada variante de plantilla que ni la
  demo ni las fixtures alcanzan. Sin ellos, una variante sin caso no se
  probaria en TypeScript.

Y PLANTILLAS: los bordes del lenguaje (formatos, claves que faltan, importes
negativos, unicode, llaves literales).

Uso, desde la raiz del repositorio:

  python scripts/generar_casos_textos.py              # lo reescribe
  python scripts/generar_casos_textos.py --comprobar  # 1 si no esta al dia

El test tests/test_textos.py lo llama en modo comprobar: si alguien cambia
una plantilla, una regla o la demo sin regenerar, falla.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from bms_agent import textos  # noqa: E402
from bms_agent.reglas.catalogo import CATALOGO  # noqa: E402

DESTINO = textos.CARPETA / "casos.json"
FIXTURES_V1 = RAIZ / "tests" / "fixtures" / "v1"
# El dia de las cifras del brief: con un reloj fijo la demo sale igual cada vez.
INSTANTE = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
# Cuantos casos reales se guardan de cada variante y de cada origen: bastan para
# probar la variante sin hacer del fichero un volcado de la demo.
POR_VARIANTE = 2
RESULTADOS = ("fallo", "sin_datos")
ORIGENES = ("demo", "fixtures_v1", "ejemplo")


# ------------------------------------------------------------ los bordes del lenguaje

PLANTILLAS: list[tuple[str, dict[str, Any]]] = [
    ("{x|dinero}", {"x": 0}),
    ("{x|dinero}", {"x": 5}),
    ("{x|dinero}", {"x": -5}),
    ("{x|dinero}", {"x": 123456}),
    ("{x|dinero}", {"x": -123456}),
    ("{x|dinero}", {"x": 123456789012}),
    ("{x|dinero}", {"x": "181350"}),
    ("{x|dinero}", {"x": "181351/2"}),
    ("{x|dinero}", {"x": "-25/4"}),
    ("{x|dinero}", {"x": None}),
    ("{x|dinero}", {"x": "geen bedrag"}),
    ("{x|tarifa}", {"x": 425000}),
    ("{x|tarifa}", {"x": 425050}),
    ("{x|tarifa}", {"x": 12345678}),
    ("{x|tarifa}", {"x": -4250}),
    ("{x|horas}", {"x": 0}),
    ("{x|horas}", {"x": 8000}),
    ("{x|horas}", {"x": 37500}),
    ("{x|horas}", {"x": 250}),
    ("{x|horas}", {"x": 1}),
    ("{x|horas}", {"x": 1234500}),
    ("{x|horas}", {"x": -2500}),
    ("{x|pct}", {"x": 2100}),
    ("{x|pct}", {"x": 825}),
    ("{x|pct}", {"x": 8599}),
    ("{x|pct}", {"x": 5}),
    ("{x|pct}", {"x": -50}),
    ("{x|pct}", {"x": [900, 2100]}),
    ("{x|fecha}", {"x": "2026-10-16"}),
    ("{x|fecha}", {"x": "2026-10-16T08:00:00+00:00"}),
    ("{x|fecha}", {"x": "16-10-2026"}),
    ("{x|trimestre}", {"x": "2026-T3"}),
    ("{x|trimestre}", {"x": "2026-Q3"}),
    ("{x|iban}", {"x": "NL91ABNA0417164300"}),
    ("{x|iban}", {"x": "nl91 abna 0417 1643 00"}),
    ("{x|iban}", {"x": "NL..4300"}),
    ("{x|iban}", {"x": ["DE89370400440532013000", "NL91ABNA0417164300"]}),
    ("{x|codigo}", {"x": "autoliquidacion"}),
    ("{x|codigo}", {"x": ["kor", "exento"]}),
    ("{x|codigo}", {"x": "geen_code"}),
    ("{x}", {"x": True}),
    ("{x}", {"x": False}),
    ("{x}", {"x": 2026}),
    ("{x}", {"x": -3}),
    ("{x}", {"x": "Öztürk Élan Bouw — 北京 & <b>"}),
    ("{x}", {"x": ["a", "b", "c"]}),
    ("{x}", {"x": []}),
    ("{x}", {"x": None}),
    ("{x}", {"x": {"a": 1}}),
    ("{falta}", {}),
    ("{a.0.1} {a.5} {b.c}", {"a": [[1, 2]], "b": {"c": "d"}}),
    ("{xs|suma|dinero}", {"xs": [100, 250]}),
    ("{xs|suma|dinero}", {"xs": [100, None]}),
    ("{xs|suma|dinero}", {"xs": []}),
    ("{xs|cuenta}", {"xs": [1, 2, 3]}),
    ("{xs|cuenta}", {"xs": {"a": 1, "b": 2}}),
    ("{xs|cuenta}", {"xs": None}),
    ("{x|abs|dinero}", {"x": -500}),
    ("{xs|abs|dinero}", {"xs": [-100, 200]}),
    ("{{literal}} {x} }} {{", {"x": 1}),
    ("{x|raro}", {"x": 1}),
    ("{x|dinero|suma}", {"x": 1}),
    ("Geen marker, wel { een } losse accolade", {}),
    ("{x} en {x|dinero} en {y}", {"x": 100}),
]


# ------------------------------------------------------------ ejemplos de los tests

# (regla, resultado, valores): copiados de lo que las reglas dan en los tests
# (tests/test_reglas*.py y compania), para las variantes que la demo y las
# fixtures no alcanzan. Un {} prueba la variante sin condiciones.
EJEMPLOS: list[tuple[str, str, dict[str, Any]]] = [
    ("Q1", "fallo", {"faltan": ["periodo"], "no_solicitados": []}),
    ("Q1", "fallo", {}),
    ("Q1", "sin_datos", {"no_solicitado": "contraparte"}),
    ("Q1", "sin_datos", {}),
    ("Q2", "fallo", {"campos": ["total_cent", "fecha_factura"]}),
    ("Q2", "fallo", {}),
    ("Q3", "fallo", {}),
    ("X1", "fallo", {"filas": [[3, "esta en USD: lo que no esta en euros no entra"]]}),
    ("X1", "fallo", {}),
    ("X1", "sin_datos", {}),
    ("M2", "fallo", {
        "linea_id": 600,
        "orden": 1,
        "excluida": True,
        "campos": ["factura_linea.descripcion_doc"],
    }),
    ("M2", "fallo", {
        "linea_id": 600,
        "orden": 1,
        "excluida": False,
        "campos": ["factura_linea.descripcion_doc"],
    }),
    ("M2", "fallo", {}),
    ("M3", "fallo", {
        "copia": 2,
        "factura": 1,
        "distintos": {"parte": ["cliente:3", "cliente:9"]},
    }),
    ("M3", "fallo", {"copia": 2, "factura": 1, "distintos": {"union": ["pagos"]}}),
    ("M3", "fallo", {"copia": 2, "factura": 1, "distintos": {"total_cent": [41140, 41150]}}),
    ("M3", "fallo", {}),
    ("Z1", "fallo", {"fuente": "exact", "exportado": "2026-10-14", "edad": 18, "limite": 7}),
    ("Z1", "fallo", {"fuente": "trnsprnt", "exportado": "2026-10-14", "edad": 18, "limite": 7}),
    ("Z1", "fallo", {}),
    ("Z2", "fallo", {
        "rechazadas": 1,
        "estado": "rechazada",
        "filas": [[8, "fila", "regimen_iva: 'XX' no es uno de VH21, VL9, VERL, KOR, VRIJ, 0"]],
    }),
    ("Z2", "fallo", {
        "rechazadas": 0,
        "estado": "aceptada",
        "filas": [],
        "sin_resolver": [
            [1, "recurso", "J. de Vries"],
            [4, "recurso", "J. de Vries"],
            [6, "recurso", "J. de Vries"],
            [7, "objeto", "IJsselmonde"],
            [7, "recurso", "Kees"],
            [7, "cliente", "10009"],
        ],
    }),
    ("Z2", "fallo", {
        "rechazadas": 1,
        "estado": "parcial",
        "filas": [[8, "fila", "regimen_iva: 'XX' no es uno de VH21, VL9, VERL, KOR, VRIJ, 0"]],
    }),
    ("Z2", "fallo", {}),
    ("A0", "fallo", {
        "btw": "NL003333333B01",
        "kvk": "87654321",
        "nombre": "van dijk bv",
        "candidatos": 2,
    }),
    ("A0", "fallo", {"btw": "NL008888888B01", "kvk": None, "nombre": "onbekend bv"}),
    ("A0", "fallo", {}),
    ("A2", "fallo", {"nombre": ["parte vhaven", ["havenbedrijf rotterdam bv"]]}),
    ("A2", "fallo", {}),
    ("A2", "sin_datos", {}),
    ("A5", "fallo", {"btw": "NL12345B01"}),
    ("A5", "fallo", {}),
    ("A7", "fallo", {
        "anterior": 14,
        "kvk": ["76543210", "87654321"],
        "direccion": ["industrieweg 45 2802 ag gouda", "havenstraat 14 3011 xb rotterdam"],
    }),
    ("A7", "fallo", {}),
    ("A8", "fallo", {
        "emisor": None,
        "receptor": "bm support bv",
        "receptor_btw": "NL009999999B01",
    }),
    ("A8", "fallo", {"emisor": "bouwtechniek van dijk bv", "btw": "NL001234567B01"}),
    ("A8", "fallo", {"nombre": "bms support bv"}),
    ("A8", "fallo", {}),
    ("B2", "fallo", {}),
    ("B2", "sin_datos", {}),
    ("B3", "fallo", {
        "facturas": [11, 14],
        "totales_cent": [178112, 178112],
        "fechas": ["2026-09-14", "2026-09-14"],
        "dias": 0,
        "periodos": [["2026-09-07", "2026-09-13"], ["2026-09-07", "2026-09-13"]],
    }),
    ("B3", "fallo", {}),
    ("B4", "fallo", {}),
    ("B4", "sin_datos", {}),
    ("B5", "fallo", {}),
    ("V7", "fallo", {"caso": "numero", "numero_norm": "V4", "facturas": [4, 5]}),
    ("V7", "fallo", {
        "caso": "importe",
        "facturas": [1, 2],
        "totales_cent": [54268, 54268],
        "fechas": ["2026-10-13", "2026-10-14"],
        "dias": 1,
        "periodos": [["2026-10-12", "2026-10-12"], ["2026-10-12", "2026-10-12"]],
    }),
    ("V7", "fallo", {
        "caso": "turno",
        "turno": "D-1",
        "horas_mil": 8000,
        "conciliadas_mil": 31000,
        "facturas": [21, 26, 29, 31],
    }),
    ("V7", "fallo", {}),
    ("V7", "sin_datos", {}),
    ("C4", "fallo", {
        "trimestre": "2026-T3",
        "motivo": "tarde",
        "declarada": None,
        "ahora": "5c987bb540000746a6fab711d19346b74a8bc0afc8092322564c6a52217e3a89",
    }),
    ("C4", "fallo", {
        "trimestre": "2026-T3",
        "motivo": "cambio",
        "declarada": "57c353951308912109790837ce9c70816bee8ebc5bf782654b44ce46f134718e",
        "ahora": "5c987bb540000746a6fab711d19346b74a8bc0afc8092322564c6a52217e3a89",
    }),
    ("C4", "fallo", {
        "trimestre": "2026-T3",
        "motivo": "fuera",
        "declarada": "57c353951308912109790837ce9c70816bee8ebc5bf782654b44ce46f134718e",
        "ahora": None,
    }),
    ("C4", "fallo", {}),
    ("D1", "fallo", {"faltan": ["líneas"]}),
    ("D1", "fallo", {}),
    ("D2", "fallo", {"base_cent": 239900, "lineas_cent": [159375, 70400]}),
    ("D2", "fallo", {}),
    ("D2", "sin_datos", {"base_cent": 10000, "lineas_cent": [None, None, None]}),
    ("D2b", "fallo", {}),
    ("D3", "fallo", {"tramos": [[900, 39900, 4000], [2100, 200000, 42000]]}),
    ("D3", "fallo", {"base_cent": 100000, "iva_cent": 25000, "tipo_iva_pb": 2100}),
    ("D3", "fallo", {}),
    ("D4", "fallo", {"base_cent": 239900, "iva_cent": 50379, "total_cent": 1}),
    ("D4", "fallo", {}),
    ("D6", "fallo", {
        "base_cent": 239900,
        "iva_cent": 50379,
        "tramos": [[200000, 42000], [39900, 4000]],
    }),
    ("D6", "fallo", {}),
    ("I1", "fallo", {}),
    ("E0", "fallo", {"faltan": ["iva_cent"]}),
    ("E0", "fallo", {"tramos": [[None, 50000, 10500]]}),
    ("E0", "fallo", {}),
    ("E1", "fallo", {"maestro": "tipo_cero", "factura": "autoliquidacion"}),
    ("E1", "fallo", {}),
    ("E1", "sin_datos", {}),
    ("E2", "fallo", {"anterior": 19, "antes": "autoliquidacion", "ahora": "estandar"}),
    ("E2", "fallo", {"anterior": 4, "tipos_antes": [2100], "tipos_nuevos": [900]}),
    ("E2", "fallo", {}),
    ("E3", "fallo", {
        "tratamiento_iva": "kor",
        "iva_cent": 7140,
        "base_cent": 34000,
        "total_cent": 41140,
    }),
    ("E3", "fallo", {
        "tratamiento_iva": "kor",
        "iva_cent": None,
        "base_cent": 34000,
        "total_cent": 41140,
    }),
    ("E3", "fallo", {}),
    ("E3", "sin_datos", {}),
    ("E4", "fallo", {
        "tratamiento_iva": "autoliquidacion",
        "iva_cent": 10500,
        "base_cent": 70000,
        "total_cent": 80500,
    }),
    ("E4", "fallo", {}),
    ("E5", "fallo", {"ano": 2026, "umbral_cent": 2000000, "aviso_pct": 90, "pasado": True}),
    ("E5", "fallo", {"ano": 2026, "umbral_cent": 2000000, "aviso_pct": 90, "pasado": False}),
    ("E5", "fallo", {}),
    ("E7", "fallo", {"tipos": [600]}),
    ("E7", "fallo", {"tratamiento_iva": "autoliquidacion", "cliente_id": 1}),
    ("E7", "fallo", {}),
    ("E7", "sin_datos", {"tratamiento_iva": "autoliquidacion"}),
    ("E7", "sin_datos", {}),
    ("F0", "fallo", {}),
    ("F1", "fallo", {"iban": "NL17RABO2601815909"}),
    ("F1", "fallo", {}),
    ("F2", "fallo", {"iban": "NL02ABNA0123456789", "estado": None}),
    ("F2", "fallo", {"iban": "NL02ABNA0123456789", "estado": "heredada", "pagables": 1}),
    ("F2", "fallo", {"iban": "NL02ABNA0123456789", "estado": "registrada", "pagables": 1}),
    ("F2", "fallo", {"iban": "NL02ABNA0123456789", "estado": "verificada", "pagables": 1}),
    ("F2", "sin_datos", {}),
    ("F3", "fallo", {"iban": "NL02ABNA0123456789", "registrada": True}),
    ("F3", "fallo", {}),
    ("F3", "sin_datos", {}),
    ("F4", "fallo", {
        "iban": "NL02ABNA0123456789",
        "ajenas": [["proveedor", 1]],
        "factoring": False,
    }),
    ("F4", "fallo", {}),
    ("F5", "fallo", {
        "cuenta": 2,
        "iban": "NL44RABO0123456789",
        "cambios": [["retirada_del_maestro", 16, 4]],
    }),
    ("F5", "fallo", {"proveedor": 2, "cuentas": ["NL44RABO0123456789", "NL91ABNA0417164300"]}),
    ("F5", "fallo", {}),
    ("F6", "fallo", {
        "exact": ["NL02ABNA0123456789", "NL44RABO0123456789"],
        "trnsprnt": ["NL02ABNA0123456789"],
    }),
    ("F6", "fallo", {}),
    ("F7", "fallo", {
        "proveedor": 5,
        "iban": "NL03RABO0312456789",
        "estado": None,
        "facturas": [6],
    }),
    ("F7", "fallo", {}),
    ("F7", "sin_datos", {}),
    ("F8", "fallo", {
        "cuenta": 1,
        "iban": "NL44RABO0123456789",
        "evento": 1,
        "motivo": "el maestro no tenia telefono de verificacion antes del documento que la motivo",
    }),
    ("F8", "fallo", {}),
    ("F9", "fallo", {"cambio": 305, "dia": "2026-10-14", "hasta": "2026-10-28"}),
    ("F9", "fallo", {}),
    ("F10", "fallo", {"iban": "NL02ABNA0123456789"}),
    ("F10", "fallo", {}),
    ("F10", "sin_datos", {}),
    ("K1", "fallo", {}),
    ("K2", "fallo", {
        "total_cent": 865483,
        "pagado_cent": 865483,
        "pendiente_cent": -23958,
        "fuente": "banco",
        "acreditado_cent": 23958,
    }),
    ("K2", "fallo", {
        "total_cent": 290279,
        "pagado_cent": 100000,
        "pendiente_cent": 190279,
        "fuente": "manual",
    }),
    ("K2", "fallo", {}),
    ("K2", "sin_datos", {}),
    ("K3", "fallo", {"aplicaciones": [1], "fecha_pago": "2026-10-01"}),
    ("K3", "fallo", {}),
    ("K3", "sin_datos", {}),
    ("K4", "fallo", {
        "movimientos": [1, 2],
        "importe_cent": -290279,
        "parte": "proveedor:1",
        "ibans": ["NL02ABNA0123456789"],
        "referencia": "20264471",
        "facturas": [1],
    }),
    ("K4", "fallo", {"movimientos": [1, 2], "pagado_cent": 580558, "total_cent": 290279}),
    ("K4", "fallo", {}),
    ("K5", "fallo", {"aplicacion": 2, "fecha_pago": "2026-10-14", "reglas": ["F2", "F3"]}),
    ("K5", "fallo", {}),
    ("K6", "fallo", {
        "cuenta": "NL60INGB0009988776",
        "extracto": 2,
        "motivo": "abre con 10.000,00 y el anterior cerro con 9.999,00",
    }),
    ("K6", "fallo", {"extractos": [2]}),
    ("K6", "fallo", {}),
    ("K7", "fallo", {}),
    ("K8", "fallo", {"banco_cent": 290279, "exact_cent": 50000}),
    ("K8", "fallo", {}),
    ("K9", "fallo", {"pagado_cent": 41140, "fuente": "banco", "aplicaciones": [1]}),
    ("K9", "fallo", {}),
    ("G1", "fallo", {
        "desde": "2027-03-01",
        "hasta": "2027-03-01",
        "obligatorio": True,
        "causa": "sin_planning",
    }),
    ("G1", "fallo", {
        "desde": "2027-03-01",
        "hasta": "2027-03-01",
        "obligatorio": True,
        "causa": "caducado",
    }),
    ("G1", "fallo", {
        "desde": "2027-03-01",
        "hasta": "2027-03-01",
        "obligatorio": True,
        "causa": "sin_cubrir",
    }),
    ("G1", "fallo", {}),
    ("G2", "fallo", {
        "nivel": "recurso_semana",
        "desde": "2026-10-05",
        "hasta": "2026-10-11",
        "facturadas_mil": 99000,
        "tope_mil": 24000,
        "sin_validar": 1,
        "diferencia_mil": 75000,
        "tolerancia_mil": 750,
        "turnos": ["D-1", "D-2", "D-3"],
        "valor_cent": 318750,
    }),
    ("G2", "fallo", {}),
    ("G3", "fallo", {
        "imputacion": 1280,
        "linea": 280,
        "tarifa_e4": 425000,
        "pactada_e4": 400000,
        "tarifas": [1],
        "nivel": "parte",
        "valor_cent": 2000,
    }),
    ("G3", "fallo", {
        "imputacion": 1010,
        "linea": 10,
        "tarifa_e4": 425000,
        "turno_e4": 400000,
        "valor_cent": 2000,
    }),
    ("G3", "fallo", {
        "grupo": "linea:1",
        "trabajo": "montagewerk",
        "unidad": "hora",
        "anterior_e4": 440000,
        "posteriores_e4": [425000],
        "desviadas": [1],
    }),
    ("G3", "fallo", {"imputaciones": [1220], "tarifas": [2]}),
    ("G3", "fallo", {}),
    ("G3", "sin_datos", {
        "imputacion": 1220,
        "turno": None,
        "unidad": "hora",
        "dia": "2026-09-07",
        "tarifas": [2],
    }),
    ("G3", "sin_datos", {"imputacion": 1010, "tarifas": [1, 2], "nivel": "parte"}),
    ("G4", "fallo", {
        "propuesta": 8,
        "candidatos": [8],
        "desde": "2026-10-05",
        "hasta": "2026-10-05",
    }),
    ("G4", "fallo", {
        "propuesta": None,
        "candidatos": [8],
        "desde": "2026-10-05",
        "hasta": "2026-10-05",
    }),
    ("G4", "fallo", {"objeto": 9, "planning": [8], "desde": "2026-10-05", "hasta": "2026-10-05"}),
    ("G4", "fallo", {}),
    ("G5", "fallo", {"semana_doc": 40, "fecha": "2026-10-13"}),
    ("G5", "fallo", {
        "desde": "2026-10-05",
        "hasta": "2026-10-05",
        "facturadas_mil": 8000,
        "semanas": ["2026-W44"],
        "turnos": ["D-11"],
    }),
    ("G5", "fallo", {}),
    ("G6", "fallo", {
        "imputacion": 1250,
        "linea": 250,
        "tarifa_e4": 425000,
        "pactada_e4": 370000,
        "tarifas": [2],
        "nivel": "parte",
        "valor_cent": 4400,
    }),
    ("G6", "fallo", {
        "turno": "nacht",
        "facturadas_mil": 8000,
        "planificadas_mil": 0,
        "tolerancia_mil": 1250,
        "desde": "2026-10-19",
        "hasta": "2026-10-25",
        "valor_cent": 34000,
    }),
    ("G6", "fallo", {"imputaciones": [1400], "tarifas": [1]}),
    ("G6", "fallo", {}),
    ("G6", "sin_datos", {
        "imputacion": 1400,
        "turno": "x",
        "unidad": "hora",
        "dia": "2026-09-07",
        "tarifas": [1],
    }),
    ("G7", "fallo", {}),
    ("V1", "fallo", {
        "nivel": "objeto_semana",
        "desde": "2026-10-12",
        "hasta": "2026-10-18",
        "facturadas_mil": 15000,
        "tope_mil": 8000,
        "sin_validar": 1,
        "diferencia_mil": 7000,
        "tolerancia_mil": 250,
        "turnos": ["D-2026-104213"],
        "valor_cent": 41860,
    }),
    ("V1", "fallo", {
        "nivel": "objeto_dia",
        "desde": "2026-10-14",
        "hasta": "2026-10-14",
        "facturadas_mil": 8000,
        "validadas_mil": 0,
        "diferencia_mil": 8000,
        "tolerancia_mil": 250,
        "turnos": [],
        "valor_cent": 47840,
    }),
    ("V1", "fallo", {}),
    ("V2", "fallo", {
        "propuesta": 8,
        "candidatos": [8],
        "desde": "2026-10-05",
        "hasta": "2026-10-05",
    }),
    ("V2", "fallo", {"objeto": 10, "cliente_objeto": 4}),
    ("V2", "fallo", {
        "objeto": 11,
        "desde": "2026-10-05",
        "hasta": "2026-10-05",
        "activo_desde": "2026-11-01",
        "activo_hasta": None,
    }),
    ("V2", "fallo", {"objeto": None}),
    ("V2", "fallo", {"objeto": 10}),
    ("V3", "fallo", {"semana_doc": 40, "fecha": "2026-10-13"}),
    ("V3", "fallo", {
        "desde": "2026-10-14",
        "hasta": "2026-10-14",
        "facturadas_mil": 8000,
        "semanas": ["2026-W42", "2026-W43"],
        "turnos": [
            "D-2026-104211",
            "D-2026-104212",
            "sint:2026-10-19|rijnhaven|j de vries|07:00-15:00|feestdag",
        ],
    }),
    ("V3", "fallo", {}),
    ("V4", "fallo", {
        "imputacion": 2,
        "linea": 2,
        "tarifa_e4": 740000,
        "pactada_e4": 10740000,
        "tarifas": [4],
        "nivel": "Objeto",
        "valor_cent": 2400000,
    }),
    ("V4", "fallo", {
        "imputacion": 1,
        "linea": 1,
        "tarifa_e4": 598000,
        "turno_e4": 520000,
        "valor_cent": 11700,
    }),
    ("V4", "fallo", {"imputaciones": [1], "tarifas": [4, 5]}),
    ("V4", "fallo", {}),
    ("V4", "sin_datos", {"imputacion": 1, "tarifas": [4, 5], "nivel": "Objeto"}),
    ("V4", "sin_datos", {}),
    ("V5", "fallo", {
        "objeto": 1,
        "desde": "2026-10-12",
        "hasta": "2026-10-18",
        "horas_mil": 15000,
        "valor_cent": 83850,
        "estimado": True,
        "turnos": ["D-2026-104211", "D-2026-104212"],
    }),
    ("V5", "fallo", {
        "objeto": 1,
        "desde": "2026-10-12",
        "hasta": "2026-10-18",
        "horas_mil": 15000,
        "valor_cent": 83850,
        "estimado": False,
        "turnos": ["D-2026-104211", "D-2026-104212"],
    }),
    ("V5", "fallo", {
        "objeto": 1,
        "desde": "2026-10-12",
        "hasta": "2026-10-18",
        "horas_mil": 15000,
        "valor_cent": None,
        "estimado": True,
        "turnos": ["D-2026-104211", "D-2026-104212"],
    }),
    ("V5", "fallo", {}),
    ("V6", "fallo", {
        "objeto": 1,
        "desde": "2026-07-27",
        "hasta": "2026-08-02",
        "gracia_hasta": "2026-08-09",
        "horas_mil": 39000,
        "valor_cent": 202800,
        "estimado": True,
        "turnos": ["BMS-DEMO-1001", "BMS-DEMO-1002", "BMS-DEMO-1003", "BMS-DEMO-1004"],
    }),
    ("V6", "fallo", {}),
    ("V8", "fallo", {}),
    ("V9", "fallo", {}),
    ("P1", "fallo", {
        "po": 1,
        "numero": "PO-4500123",
        "cerrada": True,
        "inicio": "2026-10-01",
        "fin": "2026-11-01",
        "fuera": [[1, "2026-09-01", "2026-09-30"], [2, "2026-09-01", "2026-09-30"]],
    }),
    ("P1", "fallo", {
        "po": 1,
        "numero": "PO-4500123",
        "cerrada": False,
        "inicio": "2026-10-01",
        "fin": "2026-11-01",
        "fuera": [[1, "2026-09-01", "2026-09-30"], [2, "2026-09-01", "2026-09-30"]],
    }),
    ("P1", "fallo", {}),
    ("P1", "sin_datos", {
        "po": 1,
        "numero": "PO-1",
        "cerrada": False,
        "inicio": "2026-09-01",
        "fin": "2026-11-10",
        "fuera": [],
    }),
    ("P1", "sin_datos", {}),
    ("P2", "fallo", {}),
    ("P3", "fallo", {"desconocidas": ["4500012"], "de_otra_parte": [], "de_otro_objeto": []}),
    ("P3", "fallo", {}),
    ("P3", "sin_datos", {}),
    ("P4", "fallo", {
        "po": 1,
        "numero": "PO-4500123",
        "valor_cent": 450000,
        "antes_cent": 24400,
        "importe_cent": 100000,
        "exceso_cent": 75600,
    }),
    ("P4", "fallo", {}),
    ("P4", "sin_datos", {
        "po": 1,
        "numero": "PO-1",
        "valor_cent": 50000,
        "antes_cent": -4000,
        "importe_cent": 34000,
        "antes_llegada_cent": -14000,
    }),
    ("P4", "sin_datos", {}),
    ("P5", "fallo", {}),
    ("P6", "fallo", {
        "po": 1,
        "numero": "PO-1",
        "valor_cent": 50000,
        "antes_cent": -20000,
        "importe_cent": 5000,
    }),
    ("P6", "fallo", {}),
    ("P6", "sin_datos", {
        "po": 1,
        "numero": "PO-1",
        "valor_cent": 50000,
        "antes_cent": -4000,
        "importe_cent": 34000,
        "antes_llegada_cent": -14000,
    }),
    ("P6", "sin_datos", {}),
    ("P7", "fallo", {
        "fin": "2026-10-01",
        "restante_cent": 10000,
        "limite_dias": 30,
        "turnos_despues": 4,
    }),
    ("P7", "fallo", {}),
    ("P7", "sin_datos", {"fin": "2026-10-30", "restante_cent": 500000, "limite_dias": 30}),
    ("P7", "sin_datos", {}),
    ("P8", "fallo", {}),
    ("P9", "fallo", {}),
    ("P10", "fallo", {}),
    ("R1", "fallo", {
        "cita": 1,
        "numero_norm": "2026999",
        "relacion": "credits",
        "encontradas": [1, 2],
    }),
    ("R1", "fallo", {
        "cita": 1,
        "numero_norm": "2026999",
        "relacion": "credits",
        "encontradas": [],
    }),
    ("R1", "fallo", {}),
    ("R1", "sin_datos", {}),
    ("R2", "fallo", {"total_cent": 41140, "acreditado_cent": 51140, "abonos": [11, 12]}),
    ("R2", "fallo", {"total_cent": -10000, "aplicado_cent": 16000, "destinos": [1, 4]}),
    ("R2", "fallo", {}),
    ("R2", "sin_datos", {}),
    ("R3", "fallo", {
        "nueva": 2,
        "original": 1,
        "tipo": "sustituye",
        "pendiente_cent": [51425, 290279],
        "pagado_cent": [0, 0],
    }),
    ("R3", "fallo", {
        "nueva": 2,
        "original": 1,
        "tipo": "corrige",
        "pendiente_cent": [51425, 290279],
        "pagado_cent": [0, 0],
    }),
    ("R3", "fallo", {}),
    ("R4", "fallo", {}),
    ("R5", "fallo", {}),
    ("U1", "fallo", {}),
    ("U1", "sin_datos", {}),
    ("E4", "fallo", {
        "tratamiento_iva": "autoliquidacion",
        "iva_cent": None,
        "base_cent": 70000,
        "total_cent": 84700,
    }),
    ("F2", "fallo", {"iban": "NL02ABNA0123456789", "estado": "rechazada", "pagables": 1}),
    ("F2", "fallo", {"estado": "verificada", "pagables": 0}),
    ("V6", "fallo", {
        "objeto": 1,
        "desde": "2026-07-27",
        "hasta": "2026-08-02",
        "gracia_hasta": "2026-08-09",
        "horas_mil": 39000,
        "valor_cent": None,
        "estimado": True,
        "turnos": ["BMS-DEMO-1001", "BMS-DEMO-1002"],
    }),
]


# ------------------------------------------------------------ casos reales

def _de_almacen(conn: Any) -> list[tuple[str, str, dict[str, Any]]]:
    """Los fallos (hallazgos) y los sin_datos (evaluacion) de un almacen, con sus valores."""
    salida = []
    for regla, valores in conn.execute("SELECT regla, valores_json FROM hallazgo ORDER BY id"):
        salida.append((regla, "fallo", json.loads(valores or "{}")))
    for regla, valores in conn.execute(
            "SELECT regla, valores_json FROM evaluacion WHERE resultado = 'sin_datos' "
            "ORDER BY id"):
        salida.append((regla, "sin_datos", json.loads(valores or "{}")))
    return salida


def _de_la_demo(carpeta: Path) -> list[tuple[str, str, dict[str, Any]]]:
    from bms_agent import demo
    from bms_agent.almacen import abrir
    from bms_agent.reloj import RelojFijo

    reloj = RelojFijo(INSTANTE)
    ruta = carpeta / "demo" / "demo.sqlite3"
    demo.crear(ruta, reloj=reloj)
    conn = abrir(str(ruta), reloj=reloj)
    try:
        return _de_almacen(conn)
    finally:
        conn.close()


def _de_las_fixtures(carpeta: Path) -> list[tuple[str, str, dict[str, Any]]]:
    from bms_agent import hallazgos
    from bms_agent.almacen import Almacen, abrir
    from bms_agent.almacen.documentos import AlmacenDocumentos
    from bms_agent.almacen.migrar import migrar
    from bms_agent.importadores.extracciones import importar_out
    from bms_agent.ingesta import tipar_pendientes
    from bms_agent.reloj import RelojFijo

    out = carpeta / "out"
    out.mkdir()
    for fichero in sorted(FIXTURES_V1.glob("*.json")):
        shutil.copy2(fichero, out / fichero.name)
    conn = abrir(":memory:", reloj=RelojFijo(INSTANTE))
    try:
        migrar(conn)
        almacen = Almacen(conn, AlmacenDocumentos(carpeta / "documentos"))
        importar_out(almacen, out, None)
        tipar_pendientes(conn)
        hallazgos.recalcular(conn)
        return _de_almacen(conn)
    finally:
        conn.close()


# ------------------------------------------------------------ escribir los casos

def _canonico(valores: Any) -> str:
    return json.dumps(valores, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _iguales(pintados: dict[str, textos.Pintado], que: str) -> list[str]:
    """Lo que falta, que tiene que ser lo mismo en todos los idiomas: las plantillas de una
    regla piden las mismas claves en neerlandes, en ingles y en castellano."""
    faltan = {idioma: p.faltan for idioma, p in pintados.items()}
    if len(set(faltan.values())) != 1:
        raise ValueError(f"{que}: los idiomas no piden lo mismo ({faltan})")
    return list(next(iter(faltan.values())))


def _pintado(regla: str, resultado: str, valores: dict[str, Any]) -> dict[str, Any]:
    variantes = textos.catalogo("nl")["reglas"][regla]["detalle"][resultado]
    variante, _ = textos.elegir(variantes, valores)
    pintados = {i: textos.detalle(regla, resultado, valores, i) for i in textos.IDIOMAS}
    faltan = _iguales(pintados, f"{regla} {resultado}")
    return {"variante": variante, **{i: p.texto for i, p in pintados.items()},
            "faltan": faltan}


def _detalles(fuentes: dict[str, list[tuple[str, str, dict[str, Any]]]]) -> list[dict]:
    """Los casos de las reglas: hasta POR_VARIANTE por variante y origen, sin repetir valores,
    y cada variante de cada plantilla con al menos uno (si no, ValueError: falta un
    ejemplo en EJEMPLOS)."""
    reglas = textos.catalogo("nl")["reglas"]
    orden = {r.id: i for i, r in enumerate(CATALOGO)}
    vistos: set[tuple[str, str, str]] = set()
    por_variante: dict[tuple[str, str, int, str], int] = defaultdict(int)
    casos = []
    for origen in ORIGENES:
        for regla, resultado, valores in fuentes.get(origen, []):
            if resultado not in reglas[regla]["detalle"]:
                raise ValueError(f"{regla} da {resultado} y su plantilla no lo tiene")
            clave = (regla, resultado, _canonico(valores))
            if clave in vistos:
                continue
            caso = {"origen": origen, "regla": regla, "resultado": resultado,
                    "valores": valores, **_pintado(regla, resultado, valores)}
            cuenta = (regla, resultado, caso["variante"], origen)
            if origen != "ejemplo" and por_variante[cuenta] >= POR_VARIANTE:
                continue
            vistos.add(clave)
            por_variante[cuenta] += 1
            casos.append(caso)
    cubiertas = {(c["regla"], c["resultado"], c["variante"]) for c in casos}
    faltan = [f"{regla} {resultado} variante {i}"
              for regla, texto in reglas.items() for resultado, variantes in texto["detalle"].items()
              for i in range(len(variantes)) if (regla, resultado, i) not in cubiertas]
    if faltan:
        raise ValueError("variantes sin ningun caso (anade un ejemplo en EJEMPLOS): "
                         + ", ".join(faltan))
    casos.sort(key=lambda c: (orden[c["regla"]], RESULTADOS.index(c["resultado"]),
                              c["variante"], ORIGENES.index(c["origen"]),
                              _canonico(c["valores"])))
    return casos


def _plantillas() -> list[dict[str, Any]]:
    salida = []
    for plantilla, valores in PLANTILLAS:
        pintados = {i: textos.pintar(plantilla, valores, i) for i in textos.IDIOMAS}
        faltan = _iguales(pintados, repr(plantilla))
        salida.append({"plantilla": plantilla, "valores": valores,
                       **{i: p.texto for i, p in pintados.items()}, "faltan": faltan})
    return salida


def generar() -> dict[str, Any]:
    """Los casos, recien calculados (no escribe nada)."""
    carpeta = Path(tempfile.mkdtemp(prefix="bms-casos-textos-"))
    try:
        fuentes = {"demo": _de_la_demo(carpeta), "fixtures_v1": _de_las_fixtures(carpeta),
                   "ejemplo": EJEMPLOS}
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
    return {
        "version": 1,
        "nota": ("Generado por scripts/generar_casos_textos.py: no se edita a mano. El "
                 "lenguaje de las plantillas esta en LEEME.md."),
        "instante": INSTANTE.isoformat(),
        "plantillas": _plantillas(),
        "detalles": _detalles(fuentes),
    }


def texto(casos: dict[str, Any]) -> str:
    return json.dumps(casos, ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--comprobar", action="store_true",
                        help="no escribe: sale con 1 si casos.json no es lo que se generaria")
    args = parser.parse_args(argv)
    nuevo = texto(generar())
    if args.comprobar:
        actual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
        if actual.replace("\r\n", "\n") != nuevo:
            print(f"{DESTINO} no esta al dia: python scripts/generar_casos_textos.py",
                  file=sys.stderr)
            return 1
        print(f"{DESTINO} esta al dia")
        return 0
    DESTINO.write_text(nuevo, encoding="utf-8", newline="\n")
    casos = json.loads(nuevo)
    print(f"{DESTINO}: {len(casos['detalles'])} casos de reglas y "
          f"{len(casos['plantillas'])} de plantillas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
