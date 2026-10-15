"""Las ordenes de las personas (servicios.py): permiso, motivo, rev, peticion y recalculo.

Puertas del paso 4 que viven aqui:

- cada orden escribe sus filas, su auditoria y el recalculo en una sola
  transaccion (y si algo falla no queda nada);
- una correccion que arregla D4 lo cierra con su causa apuntada y deja la
  edicion sin resolver hasta que alguien la verifica;
- la matriz de permisos del §6, orden por orden, y ningun usuario de sistema
  firma ninguna orden de persona.
"""

from __future__ import annotations

import json

import pytest
from conftest import RAIZ, TARIFAS_V1, factura_de, persona
from test_hallazgos import SOLAPADA, _cargar, _hallazgo, _registro

from bms_agent import campos, consultas, hallazgos, permisos, servicios
from bms_agent.almacen import USUARIOS_SISTEMA, usuario_sistema
from bms_agent.campos import Automatico, Conflicto, FaltaMotivo, Persona
from bms_agent.dominio import Permiso
from bms_agent.importadores.tarifas import sembrar_tarifas
from bms_agent.ingesta import reconciliar_referencias
from bms_agent.permisos import PermisoDenegado

MOTIVO = "Comprobado con el proveedor por telefono"
# Una tercera de Van Dijk, de julio: ni se pisa ni se repite con las otras dos.
LIMPIA = dict(invoice_number="2026-3001", invoice_date="2026-07-01",
              service_period_start="2026-06-01", service_period_end="2026-06-07",
              due_date="2026-07-31")


@pytest.fixture
def escenario(almacen, tmp_path):
    """La 01 (a) y una que se pisa con ella (b, un B4), una limpia (c), los Objetos de la
    semilla, el proveedor en el maestro y una referencia impresa. Ana lo puede todo."""
    conn = almacen.conn
    _cargar(almacen, tmp_path / "out", _registro("a"), _registro("b", **SOLAPADA),
            _registro("c", **LIMPIA))
    sembrar_tarifas(conn, TARIFAS_V1)
    admin = persona(conn, "Ana", "administrador")
    campos.crear(conn, "proveedor", {"nombre": "Bouwtechniek Van Dijk BV",
                                     "btw_id": "NL001234567B01"}, Persona(admin))
    reconciliar_referencias(conn)
    a = factura_de(conn, "2026-4471")
    campos.crear(conn, "factura_referencia", {"factura_id": a, "etiqueta_doc": "PO",
                                              "valor_doc": "4500012"},
                 Automatico("extraccion", usuario_sistema(conn, "extractor")))
    hallazgos.recalcular(conn)
    return almacen


def _rev(conn, tabla: str, fila_id: int) -> int:
    return conn.execute(f"SELECT rev FROM {tabla} WHERE id = ?", (fila_id,)).fetchone()[0]


def _ids(conn) -> dict[str, int]:
    a, b, c = (factura_de(conn, n) for n in ("2026-4471", "2026-4480", "2026-3001"))
    lineas = [f[0] for f in conn.execute(
        "SELECT id FROM factura_linea WHERE factura_id = ? ORDER BY orden", (a,))]
    objetos = {f["codigo"]: f["id"] for f in conn.execute("SELECT id, codigo FROM objeto")}
    return {
        "a": a, "b": b, "c": c, "linea": lineas[0], "ultima": lineas[-1],
        "imputacion": conn.execute("SELECT id FROM factura_imputacion WHERE linea_id = ?",
                                   (lineas[0],)).fetchone()[0],
        "rijnhaven": objetos["Rijnhaven"], "schiedam": objetos["Schiedam"],
        "proveedor": conn.execute("SELECT id FROM proveedor").fetchone()[0],
        "referencia": conn.execute("SELECT id FROM factura_referencia").fetchone()[0],
        "excepcion": conn.execute("SELECT id FROM excepcion WHERE fila_id = ?",
                                  (a,)).fetchone()[0],
        "b4": _hallazgo(conn, "B4")["id"],
    }


def _preparar_revertir(conn, admin) -> None:
    a = factura_de(conn, "2026-4471")
    servicios.ejecutar(conn, "fijar_campo", {
        "tabla": "factura", "fila_id": a, "campo": "fecha_vencimiento", "valor": "2026-10-20",
        "rev": _rev(conn, "factura", a), "motivo": MOTIVO}, usuario_id=admin)


def _preparar_cerrar(conn, admin) -> None:
    b = factura_de(conn, "2026-4480")
    servicios.ejecutar(conn, "fijar_campo", {
        "tabla": "factura", "fila_id": b, "campo": "periodo_inicio", "valor": "2026-09-07",
        "rev": _rev(conn, "factura", b), "motivo": MOTIVO}, usuario_id=admin)
    assert _hallazgo(conn, "B4")["estado"] == "desaparecido"


# (caso, orden, permiso que pide, datos, preparacion)
CASOS = [
    ("rellenar_campo", "fijar_campo", "anadir_informacion", lambda c, i: {
        "tabla": "factura", "fila_id": i["a"], "campo": "plazo_pago_dias", "valor": "30",
        "rev": _rev(c, "factura", i["a"])}, None),
    ("corregir_campo", "fijar_campo", "editar_extraccion", lambda c, i: {
        "tabla": "factura", "fila_id": i["a"], "campo": "fecha_vencimiento",
        "valor": "2026-10-20", "rev": _rev(c, "factura", i["a"]), "motivo": MOTIVO}, None),
    ("verificar_campo", "verificar_campo", "editar_extraccion", lambda c, i: {
        "tabla": "factura", "fila_id": i["a"], "campo": "total_cent",
        "rev": _rev(c, "factura", i["a"])}, None),
    ("revertir_campo", "revertir_campo", "editar_extraccion", lambda c, i: {
        "tabla": "factura", "fila_id": i["a"], "campo": "fecha_vencimiento",
        "rev": _rev(c, "factura", i["a"]), "motivo": MOTIVO}, _preparar_revertir),
    ("anadir_nota", "anadir_nota", "anadir_informacion", lambda c, i: {
        "fila_id": i["a"], "texto": "Llamado el proveedor"}, None),
    ("cambiar_objeto", "cambiar_objeto", "cambiar_objeto", lambda c, i: {
        "imputacion_id": i["imputacion"], "objeto_id": i["schiedam"],
        "rev": _rev(c, "factura_imputacion", i["imputacion"]), "motivo": MOTIVO}, None),
    ("anadir_alias", "anadir_alias", "cambiar_objeto", lambda c, i: {
        "tabla": "objeto", "fila_id": i["rijnhaven"], "alias": "Rijnhaven Noord"}, None),
    ("cambiar_po", "cambiar_po", "cambiar_po", lambda c, i: {
        "referencia_id": i["referencia"], "clase": "otra",
        "rev": _rev(c, "factura_referencia", i["referencia"]), "motivo": MOTIVO}, None),
    ("excluir_linea", "excluir_linea", "editar_extraccion", lambda c, i: {
        "linea_id": i["ultima"], "rev": _rev(c, "factura_linea", i["ultima"]),
        "motivo": MOTIVO}, None),
    ("anadir_linea", "anadir_linea", "editar_extraccion", lambda c, i: {
        "factura_id": i["a"], "rev": _rev(c, "factura", i["a"]), "motivo": MOTIVO,
        "valores": {"descripcion_doc": "Toeslag", "cantidad_mil": "1", "tarifa_e4": "10",
                    "importe_cent": "10"}}, None),
    ("dividir_linea", "dividir_linea", "editar_extraccion", lambda c, i: {
        "linea_id": i["linea"], "rev": _rev(c, "factura_linea", i["linea"]), "motivo": MOTIVO,
        "partes": [{"objeto_id": i["rijnhaven"], "importe": "1000.00", "horas": "20"},
                   {"objeto_id": i["schiedam"], "importe": "593,75", "horas": "17.5"}]}, None),
    ("corregir_maestro", "corregir_maestro", "admin", lambda c, i: {
        "tabla": "proveedor", "fila_id": i["proveedor"], "campo": "email_facturacion",
        "valor": "facturen@vandijk.example", "rev": _rev(c, "proveedor", i["proveedor"])}, None),
    ("anular_factura", "anular_factura", "anular_acreditar", lambda c, i: {
        "factura_id": i["b"], "rev": _rev(c, "factura", i["b"]), "motivo": MOTIVO}, None),
    ("fusionar_factura", "fusionar_factura", "anular_acreditar", lambda c, i: {
        "factura_id": i["b"], "destino_id": i["a"], "rev": _rev(c, "factura", i["b"]),
        "motivo": MOTIVO}, None),
    ("marcar_revisada", "marcar_revisada", "revisar_factura", lambda c, i: {
        "factura_id": i["c"], "huella": consultas.detalle(c, i["c"])["huella_contenido"]}, None),
    ("devolver_factura", "devolver_factura", "revisar_factura", lambda c, i: {
        "factura_id": i["c"], "motivo": "Falta el parte de horas"}, None),
    ("crear_excepcion", "crear_excepcion", "resolver_aviso", lambda c, i: {
        "fila_id": i["c"], "titulo": "El cliente discute las horas"}, None),
    ("asignar_excepcion", "asignar_excepcion", "resolver_aviso", lambda c, i: {
        "excepcion_id": i["excepcion"], "responsable_id": permisos.usuario_por_nombre(c, "Ana"),
        "rev": _rev(c, "excepcion", i["excepcion"])}, None),
    ("esperar_externo", "esperar_externo", "resolver_aviso", lambda c, i: {
        "excepcion_id": i["excepcion"], "esperando_a": "proveedor",
        "rev": _rev(c, "excepcion", i["excepcion"])}, None),
    ("resolver_excepcion", "resolver_excepcion", "resolver_aviso", lambda c, i: {
        "excepcion_id": i["excepcion"], "resolucion": "no_procede",
        "rev": _rev(c, "excepcion", i["excepcion"]), "motivo": "Dos obras distintas"}, None),
    ("cerrar_hallazgo", "cerrar_hallazgo", "resolver_aviso", lambda c, i: {
        "hallazgo_id": i["b4"], "motivo": "Corregido el periodo con el PDF"}, _preparar_cerrar),
    ("anular_hallazgo", "anular_hallazgo", "anular_aviso", lambda c, i: {
        "hallazgo_id": i["b4"], "huella": _hallazgo(c, "B4")["huella"], "motivo": MOTIVO}, None),
    ("subir_prioridad", "subir_prioridad", "resolver_aviso", lambda c, i: {
        "entidad_id": i["c"], "nivel": "urgente", "motivo": "El proveedor amenaza con parar"},
     None),
    ("recalcular", "recalcular", "ver_facturas", lambda c, i: {}, None),
]


def test_la_matriz_cubre_cada_orden_y_es_la_del_paragrafo_6() -> None:
    assert {orden for _c, orden, _p, _d, _pr in CASOS} == set(servicios.ACCIONES)
    for _caso, orden, permiso, _d, _pr in CASOS:
        declarado = servicios.permiso_de(orden)
        assert declarado in (permiso, None), orden
    # La tabla del §6 para las ordenes que ya existen.
    assert {o: servicios.permiso_de(o) for o in servicios.ACCIONES} == {
        "fijar_campo": None, "verificar_campo": None, "revertir_campo": None,
        "anadir_nota": "anadir_informacion", "cambiar_objeto": "cambiar_objeto",
        "anadir_alias": "cambiar_objeto", "cambiar_po": "cambiar_po",
        "excluir_linea": "editar_extraccion", "anadir_linea": "editar_extraccion",
        "dividir_linea": "editar_extraccion", "corregir_maestro": "admin",
        "anular_factura": "anular_acreditar", "fusionar_factura": "anular_acreditar",
        "marcar_revisada": "revisar_factura", "devolver_factura": "revisar_factura",
        "crear_excepcion": "resolver_aviso", "asignar_excepcion": "resolver_aviso",
        "esperar_externo": "resolver_aviso", "resolver_excepcion": "resolver_aviso",
        "cerrar_hallazgo": "resolver_aviso", "anular_hallazgo": "anular_aviso",
        "subir_prioridad": "resolver_aviso", "recalcular": "ver_facturas"}


@pytest.mark.parametrize("caso, orden, permiso, datos, preparar", CASOS,
                         ids=[c[0] for c in CASOS])
def test_cada_orden_pide_su_permiso(escenario, caso, orden, permiso, datos, preparar) -> None:
    conn = escenario.conn
    admin = permisos.usuario_por_nombre(conn, "Ana")
    if preparar is not None:
        preparar(conn, admin)
    ids = _ids(conn)
    # Una persona con todos los permisos menos ese.
    resto = set(Permiso.valores()) - {permiso}
    permisos.crear_rol(conn, f"sin_{permiso}", resto)
    sin = persona(conn, "Pedro")
    permisos.asignar_rol(conn, sin, f"sin_{permiso}")
    eventos = conn.execute("SELECT count(*) FROM evento WHERE resultado = 'ok'").fetchone()[0]
    with pytest.raises(PermisoDenegado) as error:
        servicios.ejecutar(conn, orden, datos(conn, ids), usuario_id=sin)
    assert error.value.permiso == permiso
    assert conn.execute("SELECT count(*) FROM evento WHERE resultado = 'ok'").fetchone()[0] == (
        eventos)
    denegado = conn.execute("SELECT * FROM evento ORDER BY id DESC").fetchone()
    assert (denegado["tipo"], denegado["usuario_id"]) == ("permiso_denegado", sin)
    # Con el permiso, la orden pasa.
    diferencia = servicios.ejecutar(conn, orden, datos(conn, ids), usuario_id=admin)
    assert diferencia.evento_id is not None or orden == "recalcular"
    assert diferencia.ejecucion_id is not None
    assert campos.verificar_controladas(conn) == []
    assert hallazgos.verificar(conn) == []


def test_ningun_usuario_de_sistema_firma_una_orden_de_persona(escenario) -> None:
    conn = escenario.conn
    ids = _ids(conn)
    eventos = conn.execute("SELECT count(*) FROM evento WHERE resultado = 'ok'").fetchone()[0]
    for nombre in USUARIOS_SISTEMA:
        sistema = usuario_sistema(conn, nombre)
        for _caso, orden, _permiso, datos, _pr in CASOS:
            with pytest.raises(PermisoDenegado, match="usuario de sistema"):
                servicios.ejecutar(conn, orden, datos(conn, ids), usuario_id=sistema)
    assert conn.execute("SELECT count(*) FROM evento WHERE resultado = 'ok'").fetchone()[0] == (
        eventos)
    assert conn.execute("SELECT count(*) FROM evento WHERE tipo = 'permiso_denegado'"
                        ).fetchone()[0] >= len(USUARIOS_SISTEMA) * len(CASOS)
    # Ni sin nadie detras.
    with pytest.raises(PermisoDenegado):
        servicios.ejecutar(conn, "recalcular", usuario_id=None)


# ------------------------------------------------------------ una transaccion

def test_cada_orden_escribe_filas_auditoria_y_recalculo_en_una_transaccion(escenario) -> None:
    conn = escenario.conn
    ids = _ids(conn)
    admin = permisos.usuario_por_nombre(conn, "Ana")
    sentencias: list[str] = []
    conn.set_trace_callback(sentencias.append)
    try:
        diferencia = servicios.ejecutar(conn, "fijar_campo", {
            "tabla": "factura", "fila_id": ids["a"], "campo": "total_cent", "valor": "2900.00",
            "rev": _rev(conn, "factura", ids["a"]), "motivo": MOTIVO}, usuario_id=admin)
    finally:
        conn.set_trace_callback(None)
    abiertas = [s for s in sentencias if s.strip().upper().startswith("BEGIN")]
    cerradas = [s for s in sentencias if s.strip().upper() in ("COMMIT", "ROLLBACK")]
    assert abiertas == ["BEGIN IMMEDIATE"] and cerradas == ["COMMIT"]
    # La escritura, su evento y la pasada que causo, dentro de esa transaccion.
    assert sentencias.index("COMMIT") > max(
        i for i, s in enumerate(sentencias) if "INSERT INTO ejecucion_reglas" in s)
    ejecucion = conn.execute("SELECT * FROM ejecucion_reglas WHERE id = ?",
                             (diferencia.ejecucion_id,)).fetchone()
    assert (ejecucion["motivo"], ejecucion["causa_evento_id"], ejecucion["usuario_id"]) == (
        "edicion", diferencia.evento_id, admin)


def test_si_el_recalculo_falla_no_queda_nada(escenario, monkeypatch) -> None:
    conn = escenario.conn
    ids = _ids(conn)
    admin = permisos.usuario_por_nombre(conn, "Ana")
    antes = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
             for t in ("evento", "cambio_campo", "ejecucion_reglas", "nota")}
    total = conn.execute("SELECT total_cent FROM factura WHERE id = ?", (ids["a"],)).fetchone()[0]

    def fallar(*_a, **_k):
        raise RuntimeError("el motor se cayo")

    monkeypatch.setattr(hallazgos, "recalcular", fallar)
    with pytest.raises(RuntimeError):
        servicios.ejecutar(conn, "fijar_campo", {
            "tabla": "factura", "fila_id": ids["a"], "campo": "total_cent", "valor": "2900.00",
            "rev": _rev(conn, "factura", ids["a"]), "motivo": MOTIVO}, usuario_id=admin)
    with pytest.raises(RuntimeError):
        servicios.ejecutar(conn, "anadir_nota", {"fila_id": ids["a"], "texto": "no queda"},
                           usuario_id=admin)
    assert {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in antes} == antes
    assert conn.execute("SELECT total_cent FROM factura WHERE id = ?",
                        (ids["a"],)).fetchone()[0] == total


# ------------------------------------------------------------ la puerta de D4

def test_una_correccion_que_arregla_d4_lo_cierra_con_su_causa_y_queda_sin_resolver(
        almacen, tmp_path) -> None:
    conn = almacen.conn
    _cargar(almacen, tmp_path / "out", _registro("a", total_incl_vat_raw="2.903,79"))
    hallazgos.recalcular(conn)
    f = factura_de(conn, "2026-4471")
    assert _hallazgo(conn, "D4")["estado"] == "abierto"
    ana = persona(conn, "Ana", "administracion")
    bea = persona(conn, "Bea", "administracion")

    dif = servicios.ejecutar(conn, "fijar_campo", {
        "tabla": "factura", "fila_id": f, "campo": "total_cent", "valor": "2902,79",
        "rev": _rev(conn, "factura", f), "motivo": "El total del PDF es 2.902,79"},
        usuario_id=ana)
    cerrados = dif.hallazgos["cerrados"]
    assert [(h["regla"], h["tipo"], h["causa_evento_id"]) for h in cerrados] == [
        ("D4", "cerrado_automatico", dif.evento_id)]
    d4 = _hallazgo(conn, "D4")
    assert d4["estado"] == "cerrado"
    assert hallazgos.historia(conn, d4["id"])[-1]["causa_evento_id"] == dif.evento_id
    assert {"regla": "D4", "tabla": "factura", "fila_id": f, "clave": d4["clave"],
            "antes": "fallo", "despues": "ok"} in dif.resultados

    # La edicion queda sin resolver: en la cache, en la ficha y en lo que pide revision.
    def sin_resolver() -> int:
        return conn.execute("SELECT sin_resolver FROM factura_estado WHERE factura_id = ?",
                            (f,)).fetchone()[0]

    assert sin_resolver() == 1
    campo = next(c for c in consultas.detalle(conn, f)["campos"] if c["campo"] == "total_cent")
    assert campo["sin_resolver"] and campo["calidad"] == "discrepancia"
    # La verifica otra persona: Ana, que la hizo, no (hay dos).
    with pytest.raises(permisos.SeparacionDeFunciones):
        servicios.ejecutar(conn, "verificar_campo", {
            "tabla": "factura", "fila_id": f, "campo": "total_cent",
            "rev": _rev(conn, "factura", f)}, usuario_id=ana)
    servicios.ejecutar(conn, "verificar_campo", {
        "tabla": "factura", "fila_id": f, "campo": "total_cent",
        "rev": _rev(conn, "factura", f)}, usuario_id=bea)
    assert sin_resolver() == 0


def test_rellenar_lo_que_cerro_un_hallazgo_tambien_queda_sin_resolver(almacen) -> None:
    """Un suplido no contradice a ningun automatico, pero hizo desaparecer un Q1."""
    from test_ingesta import _documento_por_ruta

    from bms_agent import ingesta

    conn = almacen.conn
    _documento_por_ruta(almacen, "saliente", _registro("venta", invoice_date=None))
    ingesta.tipar_pendientes(conn)
    hallazgos.recalcular(conn)
    venta = conn.execute("SELECT id FROM factura").fetchone()[0]
    ana = persona(conn, "Ana", "administracion")
    bea = persona(conn, "Bea", "administracion")
    dif = servicios.ejecutar(conn, "fijar_campo", {
        "tabla": "factura", "fila_id": venta, "campo": "fecha_factura", "valor": "2026-09-30",
        "rev": _rev(conn, "factura", venta)}, usuario_id=ana)
    assert [h["regla"] for h in dif.hallazgos["cerrados"]] == ["Q1"]
    estado = conn.execute("SELECT sin_resolver, suplementada FROM factura_estado "
                          "WHERE factura_id = ?", (venta,)).fetchone()
    assert tuple(estado) == (1, 1)
    servicios.ejecutar(conn, "verificar_campo", {
        "tabla": "factura", "fila_id": venta, "campo": "fecha_factura",
        "rev": _rev(conn, "factura", venta)}, usuario_id=bea)
    assert conn.execute("SELECT sin_resolver FROM factura_estado WHERE factura_id = ?",
                        (venta,)).fetchone()[0] == 0


# ------------------------------------------------------------ peticion, rev y motivo

def test_la_misma_peticion_no_se_aplica_dos_veces(escenario) -> None:
    conn = escenario.conn
    ids = _ids(conn)
    admin = permisos.usuario_por_nombre(conn, "Ana")
    datos = {"fila_id": ids["a"], "texto": "Llamado el proveedor"}
    primera = servicios.ejecutar(conn, "anadir_nota", datos, usuario_id=admin, peticion_id="n-1")
    eventos = conn.execute("SELECT count(*) FROM evento").fetchone()[0]
    segunda = servicios.ejecutar(conn, "anadir_nota", datos, usuario_id=admin, peticion_id="n-1")
    assert segunda.repetida and segunda.evento_id == primera.evento_id
    assert conn.execute("SELECT count(*) FROM evento").fetchone()[0] == eventos
    assert conn.execute("SELECT count(*) FROM nota").fetchone()[0] == 1
    with pytest.raises(servicios.PeticionRepetida):
        servicios.ejecutar(conn, "anadir_nota", {**datos, "texto": "Otra cosa"},
                           usuario_id=admin, peticion_id="n-1")
    otra = persona(conn, "Bea", "administracion")
    with pytest.raises(servicios.PeticionRepetida):
        servicios.ejecutar(conn, "anadir_nota", datos, usuario_id=otra, peticion_id="n-1")


def test_una_rev_vieja_es_un_conflicto_y_no_pisa_nada(escenario) -> None:
    conn = escenario.conn
    ids = _ids(conn)
    admin = permisos.usuario_por_nombre(conn, "Ana")
    vieja = _rev(conn, "factura", ids["a"])
    servicios.ejecutar(conn, "fijar_campo", {
        "tabla": "factura", "fila_id": ids["a"], "campo": "plazo_pago_dias", "valor": "30",
        "rev": vieja}, usuario_id=admin)
    for orden, datos in (
            ("fijar_campo", {"tabla": "factura", "fila_id": ids["a"],
                             "campo": "fecha_vencimiento", "valor": "2026-10-20", "rev": vieja,
                             "motivo": MOTIVO}),
            ("anular_factura", {"factura_id": ids["a"], "rev": vieja, "motivo": MOTIVO}),
            ("anadir_linea", {"factura_id": ids["a"], "rev": vieja, "motivo": MOTIVO,
                              "valores": {"descripcion_doc": "x"}})):
        with pytest.raises(Conflicto):
            servicios.ejecutar(conn, orden, datos, usuario_id=admin)
    assert conn.execute("SELECT anulada, fecha_vencimiento FROM factura WHERE id = ?",
                        (ids["a"],)).fetchone()[0] == 0


def test_el_motivo_donde_hace_falta(escenario) -> None:
    conn = escenario.conn
    ids = _ids(conn)
    admin = permisos.usuario_por_nombre(conn, "Ana")
    for orden, datos in (
            ("fijar_campo", {"tabla": "factura", "fila_id": ids["a"],
                             "campo": "fecha_vencimiento", "valor": "2026-10-20",
                             "rev": _rev(conn, "factura", ids["a"])}),
            ("excluir_linea", {"linea_id": ids["ultima"],
                               "rev": _rev(conn, "factura_linea", ids["ultima"])}),
            ("anular_factura", {"factura_id": ids["b"], "rev": _rev(conn, "factura", ids["b"])}),
            ("resolver_excepcion", {"excepcion_id": ids["excepcion"], "resolucion": "aceptado",
                                    "rev": _rev(conn, "excepcion", ids["excepcion"])}),
            ("subir_prioridad", {"entidad_id": ids["c"], "nivel": "urgente",
                                 "motivo": "corto"})):
        with pytest.raises(FaltaMotivo):
            servicios.ejecutar(conn, orden, datos, usuario_id=admin)
    # Rellenar un vacio no pide motivo.
    servicios.ejecutar(conn, "fijar_campo", {
        "tabla": "factura", "fila_id": ids["a"], "campo": "plazo_pago_dias", "valor": "30",
        "rev": _rev(conn, "factura", ids["a"])}, usuario_id=admin)


def test_los_datos_se_comprueban_antes_de_hacer_nada(escenario) -> None:
    conn = escenario.conn
    ids = _ids(conn)
    admin = permisos.usuario_por_nombre(conn, "Ana")
    with pytest.raises(servicios.AccionDesconocida):
        servicios.ejecutar(conn, "pagar_factura", {}, usuario_id=admin)
    with pytest.raises(servicios.DatosNoValidos, match="no lleva"):
        servicios.ejecutar(conn, "anadir_nota", {"fila_id": ids["a"], "texto": "x", "iban": "NL"},
                           usuario_id=admin)
    with pytest.raises(servicios.DatosNoValidos, match="necesita"):
        servicios.ejecutar(conn, "anadir_nota", {"texto": "x"}, usuario_id=admin)
    rev = _rev(conn, "factura", ids["a"])
    for valor in (2900.5, "2.900,50", "dos mil"):
        with pytest.raises(servicios.DatosNoValidos):
            servicios.ejecutar(conn, "fijar_campo", {
                "tabla": "factura", "fila_id": ids["a"], "campo": "total_cent", "valor": valor,
                "rev": rev, "motivo": MOTIVO}, usuario_id=admin)
    # Lo que tiene su propia orden no se cambia con la edicion suelta.
    for campo in ("anulada", "fusionada_en_id"):
        with pytest.raises(servicios.DatosNoValidos, match="se cambia con"):
            servicios.ejecutar(conn, "fijar_campo", {
                "tabla": "factura", "fila_id": ids["a"], "campo": campo, "valor": "1", "rev": rev,
                "motivo": MOTIVO}, usuario_id=admin)
    with pytest.raises(campos.CampoNoEditable):
        servicios.ejecutar(conn, "fijar_campo", {
            "tabla": "factura", "fila_id": ids["a"], "campo": "iban_doc",
            "valor": "NL91ABNA0417164300", "rev": rev, "motivo": MOTIVO}, usuario_id=admin)
    with pytest.raises(servicios.DatosNoValidos, match="segunda firma"):
        servicios.ejecutar(conn, "anadir_nota", {"fila_id": ids["a"], "texto": "x"},
                           usuario_id=admin, segunda_firma_id=admin)


# ------------------------------------------------------------ lo que cambia, orden a orden

def test_la_diferencia_dice_totales_prioridades_y_resultados(escenario) -> None:
    conn = escenario.conn
    ids = _ids(conn)
    admin = permisos.usuario_por_nombre(conn, "Ana")
    dif = servicios.ejecutar(conn, "fijar_campo", {
        "tabla": "factura", "fila_id": ids["a"], "campo": "total_cent", "valor": "2900.00",
        "rev": _rev(conn, "factura", ids["a"]), "motivo": MOTIVO}, usuario_id=admin)
    assert {"entidad": "factura", "id": ids["a"], "campo": "total_cent", "antes": 290279,
            "despues": 290000} in dif.totales
    assert any(t["entidad"] == "proveedor" and t["campo"] == "total_cent" for t in dif.totales)
    assert [h["regla"] for h in dif.hallazgos["abiertos"]] == ["D4"]
    assert any(p["entidad"] == "factura" and p["entidad_id"] == ids["a"]
               and p["despues"] == "bloqueada" for p in dif.prioridades)
    assert json.loads(json.dumps(dif.a_dict()))["accion"] == "fijar_campo"
    assert any("hallazgos abiertos: D4" in linea for linea in dif.lineas())


def test_dividir_una_linea_tiene_que_sumar_la_linea(escenario) -> None:
    conn = escenario.conn
    ids = _ids(conn)
    admin = permisos.usuario_por_nombre(conn, "Ana")
    datos = {"linea_id": ids["linea"], "rev": _rev(conn, "factura_linea", ids["linea"]),
             "motivo": MOTIVO, "partes": [{"objeto_id": ids["rijnhaven"], "importe": "1000"},
                                          {"objeto_id": ids["schiedam"], "importe": "500"}]}
    with pytest.raises(servicios.DatosNoValidos, match="suman"):
        servicios.ejecutar(conn, "dividir_linea", datos, usuario_id=admin)
    datos["partes"][1]["importe"] = "593,75"
    dif = servicios.ejecutar(conn, "dividir_linea", datos, usuario_id=admin)
    activas = conn.execute("SELECT objeto_id, importe_cent FROM factura_imputacion "
                           "WHERE linea_id = ? AND retirada_en IS NULL ORDER BY id",
                           (ids["linea"],)).fetchall()
    assert [tuple(f) for f in activas] == [(ids["rijnhaven"], 100000), (ids["schiedam"], 59375)]
    assert len(dif.detalle["imputaciones"]) == 2


def test_un_alias_nuevo_resuelve_las_imputaciones_sin_objeto(almacen, tmp_path) -> None:
    conn = almacen.conn
    linea = {"description": "Montagewerk", "quantity_raw": "10,00", "unit": "uur",
             "unit_rate_raw": "42,50", "line_total_raw": "425,00", "location": "Rijnhaven Nrd",
             "week_number": 36, "period_start": None, "period_end": None}
    _cargar(almacen, tmp_path / "out", _registro("a", lines=[linea], subtotal_excl_vat_raw="425,00",
                                                 vat_amount_raw="89,25",
                                                 total_incl_vat_raw="514,25"))
    sembrar_tarifas(conn, TARIFAS_V1)
    ana = persona(conn, "Ana", "administracion")
    rijnhaven = conn.execute("SELECT id FROM objeto WHERE codigo = 'Rijnhaven'").fetchone()[0]
    assert conn.execute("SELECT objeto_id FROM factura_imputacion").fetchone()[0] is None
    dif = servicios.ejecutar(conn, "anadir_alias", {"tabla": "objeto", "fila_id": rijnhaven,
                                                    "alias": "Rijnhaven Nrd"}, usuario_id=ana)
    assert dif.detalle["imputaciones_resueltas"] == 1
    assert conn.execute("SELECT objeto_id FROM factura_imputacion").fetchone()[0] == rijnhaven


def test_fusionar_un_duplicado_cierra_su_b2(almacen, tmp_path) -> None:
    conn = almacen.conn
    _cargar(almacen, tmp_path / "out", _registro("a"), _registro("b", invoice_date="2026-09-16"))
    admin = persona(conn, "Ana", "administrador")
    campos.crear(conn, "proveedor", {"nombre": "Bouwtechniek Van Dijk BV",
                                     "btw_id": "NL001234567B01"}, Persona(admin))
    reconciliar_referencias(conn)
    hallazgos.recalcular(conn)
    assert _hallazgo(conn, "B2")["estado"] == "abierto"
    a, b = sorted(f[0] for f in conn.execute("SELECT id FROM factura"))
    dif = servicios.ejecutar(conn, "fusionar_factura", {
        "factura_id": b, "destino_id": a, "rev": _rev(conn, "factura", b),
        "motivo": "Es el mismo PDF reenviado"}, usuario_id=admin)
    assert _hallazgo(conn, "B2")["estado"] == "resuelto"
    assert any(h["regla"] == "B2" and h["tipo"] == "resuelto" for h in dif.hallazgos["cerrados"])
    assert {"entidad": "factura", "id": b, "campo": "total_cent", "antes": 290279,
            "despues": None} in dif.totales


def test_anular_con_la_segunda_firma_de_otra_persona(almacen, tmp_path) -> None:
    conn = almacen.conn
    linea = {"description": "Montagewerk, locatie Rijnhaven", "quantity_raw": "10,00",
             "unit": "uur", "unit_rate_raw": "42,50", "line_total_raw": "430,00",
             "location": "Rijnhaven", "week_number": 36, "period_start": None,
             "period_end": None}
    _cargar(almacen, tmp_path / "out", _registro("c", lines=[linea],
                                                 subtotal_excl_vat_raw="430,00",
                                                 vat_amount_raw="90,30",
                                                 total_incl_vat_raw="520,30"))
    hallazgos.recalcular(conn)
    d2b = _hallazgo(conn, "D2b")
    ana = persona(conn, "Ana", "administracion")
    bea = persona(conn, "Bea", "administracion")
    datos = {"hallazgo_id": d2b["id"], "huella": d2b["huella"],
             "motivo": "La tarifa de 43 euros esta pactada"}
    # Bloquea, y hay otra persona que puede anular: sin su firma no.
    with pytest.raises(permisos.SeparacionDeFunciones):
        servicios.ejecutar(conn, "anular_hallazgo", datos, usuario_id=ana)
    dif = servicios.ejecutar(conn, "anular_hallazgo", datos, usuario_id=ana,
                             peticion_id="anular-1", segunda_firma_id=bea)
    fila = conn.execute("SELECT * FROM anulacion").fetchone()
    assert (fila["usuario_id"], fila["segunda_firma_usuario_id"], fila["autoaprobada"]) == (
        ana, bea, 0)
    assert _hallazgo(conn, "D2b")["estado"] == "aceptado"
    assert dif.hallazgos["aceptados"][0]["regla"] == "D2b"
    firma = conn.execute("SELECT * FROM evento WHERE tipo = 'hallazgo_segunda_firma'").fetchone()
    assert (firma["usuario_id"], firma["peticion_id"]) == (bea, "anular-1:segunda_firma")
    # La evidencia que se ve tiene que ser la de ahora.
    with pytest.raises(Conflicto):
        servicios.ejecutar(conn, "anular_hallazgo", {**datos, "huella": "0" * 64},
                           usuario_id=ana, segunda_firma_id=bea)


def test_un_maestro_de_exact_no_se_corrige_aqui(escenario) -> None:
    conn = escenario.conn
    ids = _ids(conn)
    admin = permisos.usuario_por_nombre(conn, "Ana")
    with pytest.raises(servicios.DatosNoValidos, match="paso 5"):
        servicios.ejecutar(conn, "corregir_maestro", {
            "tabla": "proveedor", "fila_id": ids["proveedor"],
            "campo": "telefono_verificacion", "valor": "+31 10 123 4567",
            "rev": _rev(conn, "proveedor", ids["proveedor"])}, usuario_id=admin)
    with pytest.raises(servicios.DatosNoValidos, match="corregir_maestro"):
        servicios.ejecutar(conn, "fijar_campo", {
            "tabla": "proveedor", "fila_id": ids["proveedor"], "campo": "nombre",
            "valor": "Otro", "rev": 0}, usuario_id=admin)


# ------------------------------------------------------------ por la CLI

def test_por_la_cli_con_el_token_de_la_persona(tmp_path, out_v1, capsys) -> None:
    from bms_agent.almacen import preparar
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no"),
                 "--db", str(db)]) == 0
    assert main(["usuario", "crear", "Ana", "--rol", "administracion", "--db", str(db)]) == 0
    capsys.readouterr()
    assert main(["usuario", "token", "Ana", "--db", str(db)]) == 0
    token = capsys.readouterr().out.splitlines()[1].strip()
    with preparar(db) as almacen:
        f = factura_de(almacen.conn, "2026-4471")
        assert almacen.conn.execute("SELECT token_sha256 FROM usuario WHERE nombre = 'Ana'"
                                    ).fetchone()[0] == permisos.sha256_token(token)
    argumentos = ["accion", "fijar_campo", "--tabla", "factura", "--fila-id", str(f),
                  "--campo", "total_cent", "--valor", "2900,00", "--rev", "0", "--motivo",
                  MOTIVO, "--db", str(db), "--peticion", "cli-1"]
    assert main([*argumentos, "--token", "no-es-un-token"]) == 1
    assert "token" in capsys.readouterr().err
    assert main([*argumentos, "--token", token]) == 0
    salida = capsys.readouterr().out
    assert "hallazgos abiertos: D4" in salida and "factura 1 total_cent" in salida
    assert main([*argumentos, "--token", token]) == 0
    assert "ya se aplico" in capsys.readouterr().out
    assert main(["facturas", "--db", str(db)]) == 0
    assert "2026-4471" in capsys.readouterr().out
    assert main(["factura", str(f), "--db", str(db)]) == 0
    assert "total_cent" in capsys.readouterr().out
    assert main(["excepciones", "--db", str(db)]) == 0
    assert "D4 Total" in capsys.readouterr().out
    assert main(["acciones"]) == 0
    assert "fijar_campo" in capsys.readouterr().out
    assert main(["db", "verificar", "--db", str(db)]) == 0
    with preparar(db) as almacen:
        denegados = almacen.conn.execute(
            "SELECT motivo FROM evento WHERE tipo = 'permiso_denegado'").fetchall()
        assert [d[0] for d in denegados] == ["token ausente o no valido"]
    assert main(["usuario", "desactivar", "Ana", "--db", str(db)]) == 0
    assert main([*argumentos, "--token", token, "--peticion", "cli-2"]) == 1


def test_las_ordenes_no_llaman_a_la_api(tmp_path, out_v1) -> None:
    from test_migracion_out import _sin_api

    db = tmp_path / "datos" / "bms.sqlite3"
    for argumentos in (
        ("importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no"), "--db", str(db)),
        ("usuario", "crear", "Ana", "--rol", "administracion", "--db", str(db)),
        ("facturas", "--db", str(db)),
        ("excepciones", "--db", str(db)),
        ("politica", "cargar", str(RAIZ / "config" / "prioridad.yaml"), "--db", str(db)),
        ("db", "verificar", "--db", str(db)),
    ):
        proceso = _sin_api(*argumentos)
        assert proceso.returncode == 0, (argumentos, proceso.stdout, proceso.stderr)
