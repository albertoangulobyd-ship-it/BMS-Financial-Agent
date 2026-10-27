"""Los textos de la app en neerlandes, ingles y castellano (pasos 15 y 16): catalogos,
plantillas, casos y API.

La app de la oficina no ensena nunca los textos en espanol de la API: escribe
cada detalle desde los `valores` de su hallazgo con las plantillas de
src/bms_agent/textos/. Aqui se comprueba:

- que los tres catalogos tienen las mismas claves, las mismas condiciones y
  los mismos marcadores en cada texto, que no hay ningun texto vacio ni restos
  de espanol en nl y en (lo contrario, que no quede neerlandes ni ingles en
  es, esta en test_textos_es.py), y que cubren todo lo que la API devuelve:
  cada regla del catalogo, cada accion, cada categoria, cada fuente, cada
  estado, cada campo, cada rol y cada permiso;
- que cada plantilla esta bien escrita y solo pide claves que su regla da (en
  los casos de verdad y, donde se puede, leyendo el codigo de la regla);
- el renderizador: formatos, claves que faltan, negativos, unicode, variantes;
- que casos.json esta al dia (el generador en modo comprobar);
- que la API da los valores y el resultado de cada hallazgo, y que desde otro
  origen los IBAN de los valores salen enmascarados.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from bms_agent import campos, consultas, dominio, permisos, servicios, textos
from bms_agent.reglas.catalogo import CATALOGO

RAIZ = Path(__file__).resolve().parent.parent
REGLAS = RAIZ / "src" / "bms_agent" / "reglas"
NL, EN, ES = textos.catalogo("nl"), textos.catalogo("en"), textos.catalogo("es")
CATALOGOS = {"nl": NL, "en": EN, "es": ES}


def _hojas(valor: Any, camino: str = "") -> Iterator[tuple[str, Any]]:
    """Cada valor final del catalogo con su camino (las listas de condiciones no son texto)."""
    if isinstance(valor, dict):
        for k, v in valor.items():
            yield from _hojas(v, f"{camino}.{k}" if camino else k)
    elif isinstance(valor, list) and not camino.endswith("cuando"):
        for i, v in enumerate(valor):
            yield from _hojas(v, f"{camino}[{i}]")
    else:
        yield camino, valor


def _plantillas(catalogo: dict[str, Any]) -> Iterator[tuple[str, str, str, list[str]]]:
    """(regla, resultado, texto, condiciones) de cada plantilla de detalle."""
    for regla, texto in catalogo["reglas"].items():
        for resultado, variantes in texto["detalle"].items():
            for variante in variantes:
                if "partes" in variante:
                    for parte in variante["partes"]:
                        yield regla, resultado, parte["texto"], [*variante["cuando"],
                                                                   *parte["cuando"]]
                else:
                    yield regla, resultado, variante["texto"], variante["cuando"]


# ============================================================ los tres catalogos

def _forma(valor: Any) -> Any:
    """La estructura de un catalogo sin sus textos: las claves, las listas y las condiciones."""
    if isinstance(valor, dict):
        return {k: (v if k == "cuando" else _forma(v)) for k, v in valor.items()
                if k != "idioma"}
    if isinstance(valor, list):
        return [_forma(v) for v in valor]
    return type(valor).__name__


def test_los_idiomas_son_los_tres_catalogos() -> None:
    assert textos.IDIOMAS == ("nl", "en", "es")
    assert set(CATALOGOS) == set(textos.IDIOMAS)
    for idioma, catalogo in CATALOGOS.items():
        assert catalogo["idioma"] == idioma
    ficheros = {f.stem for f in textos.CARPETA.glob("*.json")} - {"casos"}
    assert ficheros == set(textos.IDIOMAS)


def test_los_tres_tienen_las_mismas_claves_y_condiciones() -> None:
    """Las mismas claves en el mismo orden, y las mismas condiciones en cada variante: una
    variante que solo existe en un idioma diria cosas distintas segun quien mire."""
    assert _forma(NL) == _forma(EN) == _forma(ES)


def _marcadores(texto: str) -> list[str]:
    return sorted(m.group(0) for m in _TROZO.finditer(texto) if m.group(0) not in ("{{", "}}"))


def test_los_tres_piden_los_mismos_marcadores_en_cada_texto() -> None:
    """Cada texto lleva en los tres idiomas los mismos marcadores con los mismos filtros (el
    orden puede cambiar con la frase): un importe que falta en un idioma es un dato que esa
    persona no ve."""
    hojas = {idioma: dict(_hojas(c)) for idioma, c in CATALOGOS.items()}
    for camino, valor in hojas["nl"].items():
        if camino.endswith("cuando") or camino == "idioma":
            continue
        esperado = _marcadores(valor)
        for idioma in ("en", "es"):
            assert _marcadores(hojas[idioma][camino]) == esperado, (idioma, camino)


def test_la_comprobacion_de_marcadores_ve_uno_que_falta() -> None:
    assert _marcadores("{a|dinero} y {b}") != _marcadores("{a} en {b}")
    assert _marcadores("{b} y {a|dinero}") == _marcadores("{a|dinero} en {b}")
    assert _marcadores("{{literal}} {x}") == ["{x}"]


def test_ningun_texto_vacio_y_todos_son_texto() -> None:
    for idioma, catalogo in CATALOGOS.items():
        for camino, valor in _hojas(catalogo):
            if camino.endswith("cuando"):
                assert isinstance(valor, list), (idioma, camino)
                continue
            assert isinstance(valor, str) and valor.strip() == valor and valor, (idioma, camino)


# Palabras que solo salen en espanol: un texto de nl o en que las lleva se quedo sin
# traducir. Sin las que tambien son neerlandesas o inglesas ("los", "las", "de", "en",
# "nota", "is", "no").
_ESPANOL = re.compile(
    r"\b(factura|facturas|proveedor|proveedores|cliente|clientes|importe|según|también|"
    r"está|línea|líneas|regla|reglas|hallazgo|excepción|cuenta|pagado|pagada|vencida|"
    r"periodo|trimestre|iva|anulada|ninguna|ningún|fecha|maestro|objeto|pendiente|"
    r"revisada|objeción|del|una|para|que|el|sin|cuando|valores|datos|número|turno|tarifa|"
    r"planificación|declaración|desglose|abonada|pedido|todavía|después)\b", re.IGNORECASE)


def test_no_quedan_textos_en_espanol() -> None:
    """En nl y en: el castellano de es.json no se cuela (lo contrario esta en
    test_textos_es.py)."""
    for idioma in ("nl", "en"):
        catalogo = CATALOGOS[idioma]
        for camino, valor in _hojas(catalogo):
            if camino.endswith("cuando") or not isinstance(valor, str):
                continue
            # Los marcadores llevan claves en espanol ({pendiente_cent}): no son texto.
            texto = re.sub(r"\{[^{}]*\}", "", valor)
            encontrado = _ESPANOL.search(texto)
            assert encontrado is None, (idioma, camino, encontrado and encontrado.group(0))


def test_la_heuristica_del_espanol_ve_un_texto_sin_traducir() -> None:
    assert _ESPANOL.search("La factura está vencida")
    assert not _ESPANOL.search("De factuur is vervallen; het btw-bedrag ontbreekt")
    assert not _ESPANOL.search("The invoice is overdue; the VAT amount is missing")


def test_cada_regla_del_catalogo_tiene_sus_textos() -> None:
    ids = [r.id for r in CATALOGO]
    for catalogo in CATALOGOS.values():
        assert list(catalogo["reglas"]) == ids
        for regla in ids:
            texto = catalogo["reglas"][regla]
            assert set(texto) == {"titulo", "significa", "que_hacer", "detalle"}, regla
            assert "fallo" in texto["detalle"], regla
            assert set(texto["detalle"]) <= {"fallo", "sin_datos"}, regla


def test_la_ultima_variante_vale_siempre() -> None:
    """Asi siempre hay un texto: la ultima variante de cada lista no lleva condiciones."""
    for regla, texto in NL["reglas"].items():
        for resultado, variantes in texto["detalle"].items():
            ultima = variantes[-1]
            assert ultima["cuando"] == [] and "texto" in ultima, (regla, resultado)
            for variante in variantes:
                assert ("texto" in variante) != ("partes" in variante), (regla, resultado)


def _enums() -> dict[str, set[str]]:
    """Cada enum que la API devuelve, con el grupo de `estados` que lo escribe."""
    from bms_agent.reglas import bancaria

    d = dominio
    grupos = {
        "sentido": d.Sentido, "tipo_factura": d.TipoFactura, "origen_factura": d.OrigenFactura,
        "tratamiento_iva": d.TratamientoIva, "pago": d.EstadoPago, "revision": d.EstadoRevision,
        "resultado_revision": d.ResultadoRevision, "excepcion": d.EstadoExcepcion,
        "esperando_a": d.EsperandoA, "resolucion": d.ResolucionExcepcion,
        "hallazgo": d.EstadoHallazgo, "evento_hallazgo": d.TipoEventoHallazgo,
        "resultado_regla": d.ResultadoRegla, "relacion": d.EstadoRelacion,
        "tipo_relacion": d.TipoRelacion, "fuente_relacion": d.FuenteRelacion,
        "relacion_citada": d.RelacionCitada, "clase_referencia": d.ClaseReferencia,
        "btw": d.EstadoBtw, "aplicacion": d.EstadoAplicacion,
        "fuente_aplicacion": d.FuenteAplicacion, "metodo_aplicacion": d.MetodoAplicacion,
        "metodo_verificacion": d.MetodoVerificacion, "decision_facturas": d.DecisionFacturas,
        "lado_po": d.LadoOrdenCompra, "fuente_po": d.FuenteOrdenCompra, "turno": d.EstadoTurno,
        "fuente_importacion": d.FuenteImportacion, "tipo_importacion": d.TipoImportacion,
        "ambito": d.AmbitoHallazgo, "tipo_proveedor": d.TipoProveedor,
        "tipo_recurso": d.TipoRecurso, "frecuencia": d.FrecuenciaCiclo,
    }
    salida = {g: set(e.valores()) for g, e in grupos.items()}
    salida["entidad"] = set(d.EntidadPrioridad.valores()) | {"factura"}
    salida["cuenta"] = {bancaria.HEREDADA, bancaria.REGISTRADA, d.TipoEventoCuenta.VERIFICADA.value,
                        d.TipoEventoCuenta.ATESTADA.value, d.TipoEventoCuenta.RECHAZADA.value}
    salida["cambio_cuenta"] = {"anadida_al_maestro", "retirada_del_maestro",
                               "vuelve_al_maestro"}
    salida["po"] = {"activa", "cerrada", "caducada"}
    salida["importacion"] = {"en_curso", "aceptada", "parcial", "rechazada"}
    return salida


def test_cada_estado_que_devuelve_la_api_tiene_su_nombre() -> None:
    enums = _enums()
    assert set(NL["estados"]) == set(enums)
    for grupo, valores in enums.items():
        assert set(NL["estados"][grupo]) == valores, grupo
    # Lo que la API dice de una cuenta y de un cambio del maestro es eso (bancaria.py).
    fuente = (REGLAS / "bancaria.py").read_text(encoding="utf-8")
    for cambio in enums["cambio_cuenta"]:
        assert f'"{cambio}"' in fuente
    migracion = (RAIZ / "src" / "bms_agent" / "almacen" / "sql" / "0001_almacen.sql").read_text(
        encoding="utf-8")
    assert "('en_curso', 'aceptada', 'rechazada', 'parcial')" in migracion


def test_cada_accion_categoria_fuente_calidad_prioridad_rol_y_permiso() -> None:
    assert set(NL["acciones"]) == set(servicios.ACCIONES)
    assert [c for c in NL["categorias"]] == [c for c, _t in consultas._CATEGORIAS]
    assert set(NL["fuentes"]) == set(dominio.Fuente.valores())
    assert set(NL["calidad"]) == set(dominio.Calidad.valores())
    assert set(NL["prioridad"]) == set(dominio.Prioridad.valores())
    assert set(NL["severidades"]) == set(dominio.Severidad.valores())
    assert set(NL["roles"]) == set(permisos.ROLES_BASE)
    assert set(NL["permisos"]) == set(dominio.Permiso.valores())
    for grupo in ("fuentes", "calidad", "prioridad", "severidades", "categorias"):
        for clave, texto in NL[grupo].items():
            assert set(texto) == {"etiqueta", "significa"}, (grupo, clave)
    for grupo in ("roles", "permisos"):
        for clave, texto in NL[grupo].items():
            assert set(texto) == {"etiqueta", "descripcion"}, (grupo, clave)


# Las ordenes que cambian algo que mueve dinero, el IVA o los datos bancarios: la app pide
# confirmacion con una frase propia antes de mandarlas.
CONFIRMAN = {
    "fijar_campo", "revertir_campo", "cambiar_objeto", "registrar_po", "modificar_po",
    "cerrar_po", "imputar_po", "excluir_linea", "anadir_linea", "dividir_linea",
    "corregir_maestro", "anular_factura", "fusionar_factura", "deshacer_fusion",
    "enlazar_facturas", "confirmar_relacion", "rechazar_relacion", "retirar_relacion",
    "marcar_revisada", "anular_hallazgo", "firmar_anulacion", "verificar_iban",
    "rechazar_iban", "atestar_iban", "fijar_telefono_verificacion", "anadir_beneficiario",
    "retirar_beneficiario", "marcar_pagada", "confirmar_pago", "retirar_pago",
    "btw_lista_para_revision", "btw_reabrir", "btw_anotar_presentacion",
}


def test_las_acciones_que_mueven_dinero_piden_confirmacion() -> None:
    assert CONFIRMAN <= set(servicios.ACCIONES)
    for nombre, texto in NL["acciones"].items():
        esperado = {"etiqueta", "descripcion"} | ({"confirmar"} if nombre in CONFIRMAN else set())
        assert set(texto) == esperado, nombre
    # Ninguna dice aprobar, pagar ni presentar: el sistema no hace nada de eso.
    for idioma, catalogo in CATALOGOS.items():
        for nombre, texto in catalogo["acciones"].items():
            etiqueta = texto["etiqueta"].lower()
            assert not re.search(r"goedkeur|approve|\bbetalen\b|\bpay\b|indienen|\bfile\b|"
                                 r"aprob|\bpagar\b|\bpresentar\b", etiqueta), (idioma, nombre)


_TABLAS_CAMPOS = ("factura", "factura_linea", "factura_imputacion", "proveedor", "cliente",
                  "contacto", "objeto", "recurso", "orden_compra")


def test_cada_campo_que_devuelve_la_api_tiene_su_nombre() -> None:
    assert set(NL["campos"]) == set(_TABLAS_CAMPOS)
    for tabla in _TABLAS_CAMPOS:
        assert set(NL["campos"][tabla]) == set(campos.REGISTRO[tabla]), tabla


def test_el_veredicto_no_aprueba_nada() -> None:
    for idioma, catalogo in CATALOGOS.items():
        for clave, texto in catalogo["veredicto"].items():
            assert not re.search(r"goedgekeurd|approved|aprobad", texto, re.IGNORECASE), (
                idioma, clave)
    assert textos.renderizar(NL["veredicto"]["limpia_sin_datos"], {"sin_datos": 2}, "nl") == (
        "Geen bezwaren in wat is gecontroleerd; controles zonder gegevens: 2")
    assert textos.renderizar(ES["veredicto"]["limpia_sin_datos"], {"sin_datos": 2}, "es") == (
        "Sin objeciones en lo que se ha comprobado; controles sin datos: 2")


# ============================================================ las plantillas

_TROZO = re.compile(r"\{\{|\}\}|\{[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*(?:\|[a-z]+)*\}")


def test_cada_plantilla_esta_bien_escrita() -> None:
    """Solo marcadores que el lenguaje entiende, filtros que existen (las transformaciones
    delante) y ninguna llave suelta: una llave que sobra es un marcador mal escrito."""
    textos_ = [(r, res, t) for c in CATALOGOS.values() for r, res, t, _c in _plantillas(c)]
    textos_ += [(grupo, clave, t) for c in CATALOGOS.values() for grupo in ("veredicto",)
                for clave, t in c[grupo].items()]
    for regla, resultado, texto in textos_:
        assert "{" not in _TROZO.sub("", texto) and "}" not in _TROZO.sub("", texto), (
            regla, resultado, texto)
        for ruta, filtros in textos.marcadores(texto):
            *antes, ultimo = filtros
            assert all(f in textos.TRANSFORMACIONES for f in antes), (regla, ruta, filtros)
            assert ultimo in textos.FILTROS, (regla, ruta, filtros)


def _rutas(regla: str) -> set[str]:
    """Cada segmento de ruta (sin indices) que usan las plantillas y condiciones de una regla."""
    salida = set()
    for idioma in CATALOGOS:
        for r, _res, texto, cuando in _plantillas(CATALOGOS[idioma]):
            if r != regla:
                continue
            rutas = [ruta for ruta, _f in textos.marcadores(texto)]
            rutas += [c.lstrip("!").split("=", 1)[0] for c in cuando]
            salida |= {s for ruta in rutas for s in ruta.split(".") if not s.isdigit()}
    return salida


def _textos_del_modulo(modulo: str, vistos: set[str] | None = None) -> set[str]:
    """Los textos literales de un modulo de reglas/ y de los modulos de reglas/ que importa.

    Una clave de `valores` sale escrita en el codigo de su regla (en el dict, o en
    la tabla de la que sale, como _CAMPOS_A7 o _COMPARADOS de M3): una ruta de
    plantilla que no aparece en ninguno es una errata.
    """
    vistos = vistos if vistos is not None else set()
    if modulo in vistos or not (REGLAS / f"{modulo}.py").exists():
        return set()
    vistos.add(modulo)
    arbol = ast.parse((REGLAS / f"{modulo}.py").read_text(encoding="utf-8"))
    salida = {n.value for n in ast.walk(arbol)
              if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.level == 1:
            nombres = [nodo.module] if nodo.module else [a.name for a in nodo.names]
            for nombre in nombres:
                salida |= _textos_del_modulo(nombre, vistos)
    return salida


def test_las_plantillas_solo_piden_claves_que_su_regla_da() -> None:
    """Contra el codigo: cada clave de una plantilla esta escrita en el modulo de su regla."""
    for regla in CATALOGO:
        literales = _textos_del_modulo(regla.familia)
        faltan = _rutas(regla.id) - literales
        assert not faltan, (regla.id, sorted(faltan))


def test_la_comprobacion_contra_el_codigo_ve_una_errata() -> None:
    assert "pendiente_cent" in _textos_del_modulo("pagos")
    assert "pendinte_cent" not in _textos_del_modulo("pagos")


# ============================================================ el renderizador

@pytest.mark.parametrize("cent, texto", [
    (0, "€\u00a00,00"), (1, "€\u00a00,01"), (-1, "€\u00a0-0,01"), (290279, "€\u00a02.902,79"),
    (-290279, "€\u00a0-2.902,79"), (100000000, "€\u00a01.000.000,00"),
])
def test_dinero(cent: int, texto: str) -> None:
    assert textos.dinero(cent) == texto


def test_los_demas_formatos() -> None:
    assert textos.tarifa(425000) == "€\u00a042,50" and textos.tarifa(1) == "€\u00a00,0001"
    assert textos.horas(37500) == "37,5" and textos.horas(8000) == "8"
    assert textos.horas(-250) == "-0,25" and textos.horas(1000000) == "1.000"
    assert textos.pct(2100) == "21%" and textos.pct(-825) == "-8,25%"
    assert textos.fecha("2026-10-16") == "16-10-2026" and textos.fecha("ayer") == "ayer"
    assert textos.trimestre("2026-T4") == "Q4 2026"
    assert textos.iban("NL91ABNA0417164300") == "NL91 ABNA 0417 1643 00"
    assert textos.iban("NL..4300") == "NL..4300"


def test_sin_floats() -> None:
    """Un float no es un importe: se escribe como texto y nunca se redondea con decimales."""
    assert textos.renderizar("{x|dinero}", {"x": 0.1}, "nl") == "0.1"


def test_lo_que_falta_es_una_raya_y_se_apunta() -> None:
    pintado = textos.pintar("{a} {b|dinero} {c.0}", {"b": None}, "en")
    assert pintado.texto == "— — —" and pintado.faltan == ("a", "c.0")


def test_un_texto_de_documento_sale_tal_cual() -> None:
    """El renderizador no escapa ni interpreta: escribe texto, y la app lo pone como texto."""
    valor = "<img src=x onerror=alert(1)> Öztürk & Zn. «BV»"
    assert textos.renderizar("{x}", {"x": valor}, "nl") == valor


def test_variantes_y_partes() -> None:
    valores = {"btw": ["NL001234567B02", "NL001234567B01"], "kvk": ["1", "2"]}
    pintado = textos.detalle("A2", "fallo", valores, "en")
    assert pintado.texto == ("VAT ID on the invoice: NL001234567B02; in the master data: "
                             "NL001234567B01. KvK number on the invoice: 1; in the master data: 2.")
    assert textos.detalle("A2", "fallo", {}, "nl").texto == (
        "Wat op de factuur staat, komt niet overeen met de stamgegevens.")
    assert textos.detalle("C4", "fallo", {"trimestre": "2026-T3", "motivo": "tarde"},
                          "nl").texto.startswith("Binnengekomen nadat de btw-aangifte voor Q3 2026")
    assert textos.cumple("!x", {"x": []}) and not textos.cumple("x", {"x": None})
    assert textos.cumple("pasado=true", {"pasado": True})
    assert textos.detalle("A2", "fallo", valores, "es").texto == (
        "Número de IVA en la factura: NL001234567B02; en los datos maestros: NL001234567B01. "
        "Número de KvK en la factura: 1; en los datos maestros: 2.")
    assert textos.detalle("C4", "fallo", {"trimestre": "2026-T3", "motivo": "tarde"},
                          "es").texto.startswith(
        "Llegó después de presentar la declaración de IVA de Q3 2026")


def test_un_idioma_que_no_existe() -> None:
    for idioma in ("de", "ES", "es-ES", ""):
        with pytest.raises(ValueError):
            textos.catalogo(idioma)
        with pytest.raises(ValueError):
            textos.pintar("{x}", {"x": 1}, idioma)


# ============================================================ los casos

def _generador():
    ruta = RAIZ / "scripts" / "generar_casos_textos.py"
    spec = importlib.util.spec_from_file_location("generar_casos_textos", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_el_renderizador_da_lo_que_dicen_los_casos() -> None:
    """Lo que prueba la app en TypeScript, con la referencia en Python."""
    casos = textos.casos()
    assert casos["version"] == 1 and casos["plantillas"] and casos["detalles"]
    # Cada caso trae el texto de cada idioma, y nada mas: la app (TypeScript) prueba los tres.
    for caso in casos["plantillas"]:
        assert set(caso) == {"plantilla", "valores", "faltan", *textos.IDIOMAS}, caso
    for caso in casos["detalles"]:
        assert set(caso) == {"origen", "regla", "resultado", "valores", "variante", "faltan",
                             *textos.IDIOMAS}, caso
    for caso in casos["plantillas"]:
        for idioma in textos.IDIOMAS:
            pintado = textos.pintar(caso["plantilla"], caso["valores"], idioma)
            assert (pintado.texto, list(pintado.faltan)) == (caso[idioma], caso["faltan"]), caso
    for caso in casos["detalles"]:
        variantes = NL["reglas"][caso["regla"]]["detalle"][caso["resultado"]]
        assert textos.elegir(variantes, caso["valores"])[0] == caso["variante"], caso
        assert caso["faltan"] == [], caso
        for idioma in textos.IDIOMAS:
            pintado = textos.detalle(caso["regla"], caso["resultado"], caso["valores"], idioma)
            assert pintado.texto == caso[idioma] and not pintado.faltan, caso


def test_cada_variante_tiene_un_caso_y_hay_casos_de_verdad() -> None:
    casos = textos.casos()["detalles"]
    cubiertas = {(c["regla"], c["resultado"], c["variante"]) for c in casos}
    for regla, texto in NL["reglas"].items():
        for resultado, variantes in texto["detalle"].items():
            for i in range(len(variantes)):
                assert (regla, resultado, i) in cubiertas, (regla, resultado, i)
    origenes = {c["origen"] for c in casos}
    assert {"demo", "fixtures_v1", "ejemplo"} <= origenes
    # Una regla que da sin_datos en los datos de verdad tiene plantilla para ello.
    for c in casos:
        assert c["resultado"] in NL["reglas"][c["regla"]]["detalle"], c


def test_casos_json_esta_al_dia() -> None:
    """Si cambia una plantilla, una regla o la demo, hay que regenerar los casos."""
    generador = _generador()
    actual = generador.DESTINO.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert actual == generador.texto(generador.generar()), (
        "casos.json no esta al dia: python scripts/generar_casos_textos.py")


def test_el_modo_comprobar_ve_un_fichero_viejo(tmp_path, monkeypatch, capsys) -> None:
    generador = _generador()
    viejo = tmp_path / "casos.json"
    viejo.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(generador, "DESTINO", viejo)
    monkeypatch.setattr(generador, "generar",
                        lambda: {"version": 1, "plantillas": [], "detalles": []})
    assert generador.main(["--comprobar"]) == 1
    assert "no esta al dia" in capsys.readouterr().err
    assert generador.main([]) == 0
    assert generador.main(["--comprobar"]) == 0


def test_los_ficheros_de_textos_van_en_el_paquete() -> None:
    """Docker instala el paquete con pip: los catalogos tienen que ir dentro."""
    texto = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    assert '"bms_agent.textos" = ["*.json", "LEEME.md"]' in texto


# ============================================================ la API (contrato 2.1)

INSTANTE = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def demo_conn(tmp_path_factory):
    """La base de prueba con un reloj fijo (la misma que usa el generador de los casos)."""
    from bms_agent import demo
    from bms_agent.almacen import abrir
    from bms_agent.reloj import RelojFijo

    reloj = RelojFijo(INSTANTE)
    ruta = tmp_path_factory.mktemp("demo-textos") / "demo.sqlite3"
    demo.crear(ruta, reloj=reloj)
    conn = abrir(str(ruta), reloj=reloj)
    yield conn
    conn.close()


def _id_de(conn, numero: str) -> int:
    return conn.execute("SELECT id FROM factura WHERE numero = ?", (numero,)).fetchone()[0]


def test_cada_hallazgo_de_la_ficha_trae_sus_valores_y_su_resultado(demo_conn) -> None:
    ficha = consultas.detalle(demo_conn, _id_de(demo_conn, "PW2609-01"))
    f3 = next(h for h in ficha["hallazgos"] if h["regla"] == "F3")
    assert f3["resultado"] == "fallo"
    assert f3["valores"] == {"iban": "NL37DEMO0009990301", "registrada": False}
    assert textos.detalle("F3", "fallo", f3["valores"], "nl").texto == (
        "NL37 DEMO 0009 9903 01 is nieuw voor deze leverancier.")
    assert textos.detalle("F3", "fallo", f3["valores"], "es").texto == (
        "El IBAN NL37 DEMO 0009 9903 01 es nuevo para este proveedor.")
    # Lo que no se pudo mirar va aparte, con sus valores.
    for regla in ficha["reglas_sin_datos"]:
        assert regla["resultado"] == "sin_datos" and isinstance(regla["valores"], dict)
        assert "sin_datos" in NL["reglas"][regla["regla"]]["detalle"]


def test_las_listas_y_las_excepciones_traen_sus_razones(demo_conn) -> None:
    filas = {f["numero"]: f for f in consultas.listado(demo_conn)}
    razones = filas["JV-2026-006"]["razones"]
    assert razones and razones[0]["severidad"] == "bloqueo"
    assert {"B2", "B4"} <= {r["regla"] for r in razones}
    assert all(set(r) == {"id", "regla", "severidad", "estado", "resultado", "valores"}
               for r in razones)
    excepciones_ = consultas.excepciones_abiertas(demo_conn)
    assert excepciones_ and all(e["razones"] for e in excepciones_)
    for e in excepciones_:
        assert sorted(r["id"] for r in e["razones"]) == sorted(e["hallazgos"])
        assert e["razones"] == sorted(e["razones"], key=consultas._clave_razon)


def test_los_avisos_de_un_proveedor_una_po_y_la_historia_traen_valores(demo_conn) -> None:
    proveedor = demo_conn.execute(
        "SELECT proveedor_id FROM factura WHERE numero = 'PW2609-01'").fetchone()[0]
    vista = consultas.proveedor(demo_conn, proveedor)
    assert all("valores" in h and h["resultado"] == "fallo"
               for h in vista["avisos"]["hallazgos"])
    po = demo_conn.execute("SELECT id FROM orden_compra WHERE numero = 'PO-DEMO-4501'").fetchone()[0]
    avisos = consultas.orden_compra(demo_conn, po)["avisos"]["hallazgos"]
    assert {"P5", "P8", "P9", "P10"} <= {h["regla"] for h in avisos}
    assert all(isinstance(h["valores"], dict) for h in avisos)
    historia = consultas.historial_factura(demo_conn, _id_de(demo_conn, "JV-2026-006"))
    assert all("valores" in h for h in historia["hallazgos"])


def test_desde_otro_origen_los_iban_de_los_valores_salen_enmascarados(demo_conn) -> None:
    """consultas.sin_ibanes enmascara tambien los valores (F2, F3: el IBAN entero)."""
    ficha = consultas.detalle(demo_conn, _id_de(demo_conn, "PW2609-01"))
    fuera = consultas.sin_ibanes(ficha)
    f3 = next(h for h in fuera["hallazgos"] if h["regla"] == "F3")
    assert f3["valores"]["iban"] == "NL..0301"
    assert "NL37DEMO0009990301" not in json.dumps(fuera)
    # El texto que escribe la app con un IBAN enmascarado no se inventa cifras.
    assert textos.detalle("F3", "fallo", f3["valores"], "en").texto == (
        "NL..0301 is new for this provider.")
    assert textos.detalle("F3", "fallo", f3["valores"], "es").texto == (
        "El IBAN NL..0301 es nuevo para este proveedor.")
    # El export entero tampoco lleva ninguno, ni en las razones de las listas.
    datos = consultas.exportar_v2(demo_conn)
    assert consultas.comprobar_v2(datos) == []
    assert "NL37DEMO0009990301" not in json.dumps(datos)


def test_sin_ibanes_enmascara_listas_claves_y_formas_sueltas() -> None:
    valores = {"ibans": ["NL91ABNA0417164300", "nl91 abna 0417 1643 00"],
               "NL91ABNA0417164300": 1, "exact": ["NL02 ABNA 0123 4567 89"]}
    fuera = consultas.sin_ibanes({"valores": valores})["valores"]
    assert fuera == {"ibans": ["NL..4300", "NL..4300"], "NL..4300": 1, "exact": ["NL..6789"]}
    errores = consultas.comprobar_v2({"contrato": consultas.CONTRATO_V2,
                                      "x": {"NL91ABNA0417164300": 1}})
    assert any("una clave lleva un IBAN (NL..4300)" in e for e in errores)
