"""Los codigos de error de /api/v2 (paso 15): cada error lleva un `codigo` estable.

La app de la oficina no ensena la frase en espanol del servidor (`error`, que se
queda para la CLI y la auditoria): escribe el texto en neerlandes o en ingles a
partir del codigo (textos/nl.json y en.json, "errores"). Aqui se comprueba:

- que cada codigo tiene su texto en los dos catalogos, y nada mas;
- que cada excepcion que lleva un codigo usa uno de la lista;
- que cada error JSON que escribe serve.py lleva su codigo (leyendo el codigo);
- con el servidor de verdad, los codigos de cada caso: sin token, sin permiso,
  lo que no existe, una rev vieja, sin motivo, un cuerpo que no vale, otro origen.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import json
from pathlib import Path

import pytest
from test_consola import _orden, _pedir, con_guion, servidor  # noqa: F401 (fixtures)

from bms_agent import servicios, textos
from bms_agent.serve import CABECERA_TOKEN

RAIZ = Path(__file__).resolve().parent.parent
SERVE = RAIZ / "src" / "bms_agent" / "serve.py"


def test_cada_codigo_tiene_su_texto_en_los_dos_idiomas() -> None:
    for idioma in textos.IDIOMAS:
        errores = textos.catalogo(idioma)["errores"]
        assert list(errores) == list(servicios.CODIGOS_ERROR), idioma
    assert len(set(servicios.CODIGOS_ERROR)) == len(servicios.CODIGOS_ERROR)


_MODULOS = ("permisos", "campos", "hallazgos", "excepciones", "revision", "estados", "pagos",
            "btw", "cuentas", "servicios")


def test_cada_excepcion_con_codigo_usa_uno_de_la_lista() -> None:
    vistos = set()
    for nombre in _MODULOS:
        modulo = importlib.import_module(f"bms_agent.{nombre}")
        for _n, clase in inspect.getmembers(modulo, inspect.isclass):
            if issubclass(clase, BaseException) and "codigo" in clase.__dict__:
                assert clase.__dict__["codigo"] in servicios.CODIGOS_ERROR, clase
                vistos.add(clase.__dict__["codigo"])
    assert {"sin_permiso", "segunda_persona", "conflicto", "falta_motivo", "no_anulable",
            "no_revisable"} <= vistos


def test_el_codigo_es_el_mas_concreto() -> None:
    import sqlite3

    from bms_agent.campos import Conflicto, FaltaMotivo
    from bms_agent.permisos import PermisoDenegado, SeparacionDeFunciones

    assert servicios.codigo_de_error(SeparacionDeFunciones(1, "x", "y")) == "segunda_persona"
    assert servicios.codigo_de_error(PermisoDenegado(1, "x", "y")) == "sin_permiso"
    assert servicios.codigo_de_error(Conflicto("x")) == "conflicto"
    assert servicios.codigo_de_error(FaltaMotivo("x")) == "falta_motivo"
    assert servicios.codigo_de_error(LookupError("x")) == "no_existe"
    assert servicios.codigo_de_error(sqlite3.IntegrityError("x")) == "estado_no_valido"
    assert servicios.codigo_de_error(ValueError("x")) == "invalido"


def test_cada_error_json_de_serve_lleva_su_codigo() -> None:
    """Cada self._json(<4xx o 5xx>, {...}) con un diccionario escrito ahi lleva "codigo"."""
    arbol = ast.parse(SERVE.read_text(encoding="utf-8"))
    errores = 0
    for nodo in ast.walk(arbol):
        if not (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr == "_json" and len(nodo.args) >= 2):
            continue
        estado, cuerpo = nodo.args[0], nodo.args[1]
        if not isinstance(cuerpo, ast.Dict):
            continue
        claves = {k.value for k in cuerpo.keys if isinstance(k, ast.Constant)}
        if "error" not in claves:
            continue
        if isinstance(estado, ast.Constant):
            assert estado.value >= 400, ast.unparse(nodo)
        assert "codigo" in claves, f"linea {nodo.lineno}: {ast.unparse(nodo)}"
        errores += 1
    assert errores >= 20


# ------------------------------------------------------------ con el servidor de verdad

def _cuerpo(datos: bytes) -> dict:
    return json.loads(datos)


def test_lecturas_sin_token_sin_permiso_y_lo_que_no_existe(servidor) -> None:  # noqa: F811
    puerto, tokens, _factura, _db = servidor
    estado, _c, datos = _pedir(puerto, "GET", "/api/v2/panel")
    assert (estado, _cuerpo(datos)["codigo"]) == (401, "no_autenticado")
    estado, _c, datos = _pedir(puerto, "GET", "/api/v2/panel", {CABECERA_TOKEN: tokens["nadie"]})
    assert (estado, _cuerpo(datos)["codigo"]) == (403, "sin_permiso")
    estado, _c, datos = _pedir(puerto, "GET", "/api/v2/facturas/99999",
                               {CABECERA_TOKEN: tokens["ana"]})
    assert (estado, _cuerpo(datos)["codigo"]) == (404, "no_existe")
    estado, _c, datos = _pedir(puerto, "GET", "/api/v2/nada", {CABECERA_TOKEN: tokens["ana"]})
    assert (estado, _cuerpo(datos)["codigo"]) == (404, "no_existe")
    estado, _c, datos = _pedir(puerto, "GET", "/api/v2/facturas?nivel=raro",
                               {CABECERA_TOKEN: tokens["ana"]})
    assert (estado, _cuerpo(datos)["codigo"]) == (400, "invalido")
    # La frase en espanol sigue ahi, para la CLI y la auditoria.
    assert _cuerpo(datos)["error"]


def test_las_ordenes_dicen_su_codigo(servidor) -> None:  # noqa: F811
    puerto, tokens, factura, _db = servidor
    nota = {"accion": "anadir_nota", "datos": {"fila_id": factura, "texto": "x"}}
    estado, r = _orden(puerto, tokens["carla"], nota)
    assert (estado, r["codigo"]) == (403, "sin_permiso")
    viejo = {"accion": "fijar_campo", "datos": {
        "tabla": "factura", "fila_id": factura, "campo": "plazo_pago_dias", "valor": "30",
        "rev": 7}}
    estado, r = _orden(puerto, tokens["ana"], viejo)
    assert (estado, r["codigo"], r["tipo"]) == (409, "conflicto", "Conflicto")
    estado, r = _orden(puerto, tokens["ana"], {"accion": "pagar_factura", "datos": {}})
    assert (estado, r["codigo"]) == (400, "orden_desconocida")
    estado, r = _orden(puerto, tokens["ana"], {"accion": "devolver_factura",
                                                "datos": {"factura_id": factura}})
    assert (estado, r["codigo"]) == (400, "falta_motivo")
    estado, r = _orden(puerto, tokens["ana"], {"accion": "anadir_nota",
                                                "datos": {"fila_id": 999, "texto": "x"}})
    assert (estado, r["codigo"]) == (404, "no_existe")
    estado, r = _orden(puerto, tokens["ana"], b"[1]")
    assert (estado, r["codigo"]) == (400, "invalido")
    estado, r = _orden(puerto, tokens["ana"], nota, Origin="http://evil.example")
    assert (estado, r["codigo"]) == (403, "origen_no_permitido")
    estado, _c, datos = _pedir(puerto, "POST", "/api/v2/acciones", {
        "Content-Type": "text/plain", CABECERA_TOKEN: tokens["ana"]}, b"{}")
    assert (estado, _cuerpo(datos)["codigo"]) == (415, "tipo_no_admitido")
    estado, _c, datos = _pedir(puerto, "POST", "/api/v2/acciones", {
        "Content-Type": "application/json", CABECERA_TOKEN: tokens["ana"]}, b"{" * 70000)
    assert (estado, _cuerpo(datos)["codigo"]) == (413, "demasiado_grande")


def test_otra_persona_y_un_host_ajeno(servidor) -> None:  # noqa: F811
    puerto, tokens, factura, _db = servidor
    estado, _c, datos = _pedir(puerto, "GET", "/api/v2/panel",
                               {"Host": "evil.example", CABECERA_TOKEN: tokens["ana"]})
    assert (estado, _cuerpo(datos)["codigo"]) == (421, "host_no_permitido")


@pytest.mark.parametrize("codigo", servicios.CODIGOS_ERROR)
def test_ningun_texto_de_error_promete_lo_que_el_sistema_no_hace(codigo) -> None:
    for idioma in textos.IDIOMAS:
        texto = textos.catalogo(idioma)["errores"][codigo].lower()
        assert "goedgekeurd" not in texto and "approved" not in texto
