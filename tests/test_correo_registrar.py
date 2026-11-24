"""`correo registrar` (paso 18, paso 10 del plan; diseno §3.8; solo Docker): lo que trajo el
correo, a la base, con todo lo de la bandeja tratado como no confiable.

- las tres carpetas con lstat y dir_fd: una cambiada por un enlace no se toca; un fichero que es
  un enlace, un nombre que no es el de la bandeja, un JSON enorme, roto o con claves de mas, un
  sha que no casa, sin %PDF-: rechazado (y fuera de la bandeja) o ignorado;
- una llegada "del futuro" (el reloj de este equipo atrasado) espera, y el correo dice `reloj`;
- 2 500 ficheros: mira 2 000, los mas antiguos;
- el acuse: tras registrar, la bandeja queda sin lo registrado ni lo rechazado;
- idempotencia: el mismo mensaje dos veces, el mismo PDF en dos mensajes, el mismo PDF ya llegado
  por buzon\\facturas;
- los metadatos del documento (origen, recibido_fuente, mensaje_id) y sus eventos, con el actor
  correo; db verificar ve una fila metida por detras;
- estado.json a estado_correo y ronda_correo, `--fallo`, y la pausa por volumen;
- y, de punta a punta en Python (§7.3): GraphFalso -> correo traer -> correo registrar -> la
  lectura automatica con el cliente falso -> la factura con su fecha de recepcion, sin pagar
  dos veces, y un PDF que la API no acepta esperando a una persona.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import RAIZ, persona

from bms_agent import cli, consultas, lectura
from bms_agent import lectura_automatica as auto
from bms_agent.almacen import Almacen, abrir, preparar, transaccion, usuario_sistema
from bms_agent.almacen.documentos import AlmacenDocumentos, registrar_documento
from bms_agent.almacen.evidencia import verificar_evidencia
from bms_agent.almacen.migrar import migrar
from bms_agent.almacen.unidades import sha256_bytes
from bms_agent.correo import bandeja, registrar
from bms_agent.reloj import RelojFijo, marca

SRC = RAIZ / "src" / "bms_agent"
AHORA = datetime(2026, 11, 24, 10, 0, tzinfo=timezone.utc)
UTC = timezone.utc


def pdf(marca_pdf: str, relleno: int = 0) -> bytes:
    """Un PDF de prueba que el cliente falso de la API sabe leer (por su marca)."""
    return (b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
            + f"%marca:{marca_pdf}\n".encode() + b"0" * relleno)


@pytest.fixture
def reloj() -> RelojFijo:
    return RelojFijo(AHORA)


@pytest.fixture
def almacen(reloj, tmp_path) -> Almacen:
    conn = abrir(":memory:", reloj=reloj)
    migrar(conn)
    try:
        yield Almacen(conn, AlmacenDocumentos(tmp_path / "documentos"))
    finally:
        conn.close()


class Bandeja:
    """La bandeja y el estado del correo, como los deja el componente `correo`."""

    def __init__(self, raiz: Path) -> None:
        self.entrada = raiz / "entrada"
        self.estado = raiz / "estado"
        self.llegadas = self.entrada / "llegadas"
        self.pdf = self.entrada / "pdf"
        for carpeta in (self.entrada, self.estado, self.llegadas, self.pdf):
            carpeta.mkdir(parents=True)
        self._ids = iter(range(1, 1_000_000))

    def llegada(self, *adjuntos: dict, carpeta: str = "bandeja", graph_id: str | None = None,
                recibido_en: str = "2026-11-23T08:14:02Z", **cambios) -> dict:
        graph_id = graph_id or f"AAMkAGI2THVSAAA{next(self._ids):06d}="
        datos = {"version": 1, "carpeta": carpeta, "graph_id": graph_id,
                 "internet_message_id": "<0412.factuur@proveedor.example.test>",
                 "recibido_en": recibido_en, "remitente": "facturen@proveedor.example.test",
                 "asunto": "Factuur 2026-0412", "en_linea": 0,
                 "traido_en": "2026-11-23T08:15:10Z", "adjuntos": list(adjuntos)}
        datos.update(cambios)
        self.escribir_llegada(datos)
        return datos

    def nombre(self, datos: dict) -> str:
        return bandeja.nombre_llegada(bandeja.clave(datos["graph_id"], datos["carpeta"]))

    def escribir_llegada(self, datos: dict, nombre: str | None = None,
                         contenido: bytes | None = None) -> Path:
        ruta = self.llegadas / (nombre or self.nombre(datos))
        ruta.write_bytes(contenido if contenido is not None else bandeja.como_json(datos))
        return ruta

    def adjunto_pdf(self, contenido: bytes, nombre: str = "factuur-0412.pdf", *,
                    escribir: bool = True, id_: str | None = None) -> dict:
        sha = hashlib.sha256(contenido).hexdigest()
        if escribir:
            (self.pdf / f"{sha}.pdf").write_bytes(contenido)
        return {"id": id_ or f"AAMkAd{next(self._ids)}", "nombre": nombre,
                "tipo": "application/pdf", "bytes": len(contenido), "resultado": "pdf",
                "sha256": sha, "detalle": None}

    def adjunto(self, resultado: str, nombre: str = "factuur.xml") -> dict:
        return {"id": f"AAMkAd{next(self._ids)}", "nombre": nombre, "tipo": "application/xml",
                "bytes": 812, "resultado": resultado, "sha256": None,
                "detalle": "algo" if resultado != "pdf" else None}

    def estado_json(self, *, empezada: str = "2026-11-24T09:55:00Z", codigo: str | None = None,
                    mensajes: int = 1, pdf: int = 1, aviso: bool = False,
                    fecha: str = "2026-11-24", **cambios) -> dict:
        datos = {"version": 1,
                 "ronda": {"empezada": empezada, "terminada": empezada,
                           "resultado": "bien" if codigo is None else "fallo",
                           "error_codigo": codigo, "mensajes": mensajes, "pdf_nuevos": pdf,
                           "bytes": 1500},
                 "hoy": {"fecha": fecha, "mensajes": 3, "pdf": 2, "bytes": 4000},
                 "ultima_consulta": empezada, "ultima_buena": "2026-11-24T09:55:00Z",
                 "buzon": "facturen@contoso.onmicrosoft.com",
                 "certificado": {"caduca_en": "2028-11-23T09:55:00Z"},
                 "alcance": {"comprobado_en": "2026-11-24T09:00:00Z", "bien": True,
                             "motivo_codigo": None},
                 "delta_reiniciado_en": None, "retenido_hasta": None, "aviso_volumen": aviso}
        datos.update(cambios)
        (self.estado / "estado.json").write_bytes(bandeja.como_json(datos))
        return datos

    def ficheros(self) -> list[str]:
        return sorted(p.relative_to(self.entrada).as_posix() for p in self.entrada.rglob("*")
                      if not p.is_dir() or p.is_symlink())


@pytest.fixture
def caja(tmp_path) -> Bandeja:
    return Bandeja(tmp_path / "correo")


def _registrar(almacen, caja) -> registrar.Resultado:
    return registrar.registrar(almacen, entrada=caja.entrada, estado=caja.estado)


def _filas(conn, tabla: str) -> list[dict]:
    return [dict(f) for f in conn.execute(f"SELECT * FROM {tabla} ORDER BY id")]


# ============================================================ una llegada

def test_una_llegada_entra_y_sale_de_la_bandeja(almacen, caja) -> None:
    conn = almacen.conn
    contenido = pdf("una")
    adjunto = caja.adjunto_pdf(contenido)
    llegada = caja.llegada(adjunto, caja.adjunto("xml"), en_linea=2)
    hecho = _registrar(almacen, caja)
    assert (hecho.mensajes, hecho.documentos_nuevos, hecho.rechazados) == (1, 1, [])
    # El acuse: la llegada y su PDF ya no estan en la bandeja.
    assert caja.ficheros() == []

    [mensaje] = _filas(conn, "mensaje_correo")
    correo = usuario_sistema(conn, "correo")
    assert {k: mensaje[k] for k in ("graph_id", "carpeta", "internet_message_id_doc",
                                    "recibido_en", "remitente_doc", "asunto_doc", "adjuntos",
                                    "en_linea", "traido_en", "registrado_en",
                                    "registrado_por")} == {
        "graph_id": llegada["graph_id"], "carpeta": "bandeja",
        "internet_message_id_doc": "<0412.factuur@proveedor.example.test>",
        "recibido_en": "2026-11-23T08:14:02+00:00",
        "remitente_doc": "facturen@proveedor.example.test", "asunto_doc": "Factuur 2026-0412",
        "adjuntos": 2, "en_linea": 2, "traido_en": "2026-11-23T08:15:10+00:00",
        "registrado_en": marca(AHORA), "registrado_por": correo}
    [documento] = _filas(conn, "documento")
    assert {k: documento[k] for k in ("sha256", "nombre_original", "tipo_mime", "bytes",
                                      "origen", "ruta_declarada", "mensaje_id", "recibido_en",
                                      "recibido_fuente", "registrado_por")} == {
        "sha256": adjunto["sha256"], "nombre_original": "factuur-0412.pdf",
        "tipo_mime": "application/pdf", "bytes": len(contenido), "origen": "correo",
        "ruta_declarada": "entrante", "mensaje_id": "<0412.factuur@proveedor.example.test>",
        "recibido_en": "2026-11-23T08:14:02+00:00", "recibido_fuente": "correo",
        "registrado_por": correo}
    assert almacen.documentos.leer(documento["ruta_cas"], adjunto["sha256"]) == contenido
    assert [(a["graph_adjunto_id"], a["resultado"], a["documento_id"], a["sha256"], a["bytes"])
            for a in _filas(conn, "adjunto_correo")] == [
        (adjunto["id"], "documento", documento["id"], adjunto["sha256"], len(contenido)),
        (llegada["adjuntos"][1]["id"], "xml", None, None, 812)]
    # Los eventos, con el usuario de sistema correo y sin persona.
    eventos = conn.execute("SELECT tipo, actor, usuario_id, tabla FROM evento WHERE tipo IN "
                           "('documento_registrado', 'correo_mensaje_registrado') ORDER BY id"
                           ).fetchall()
    assert [tuple(e) for e in eventos] == [
        ("documento_registrado", correo, None, "documento"),
        ("correo_mensaje_registrado", correo, None, "mensaje_correo")]
    assert verificar_evidencia(conn) == []


def test_una_fila_del_correo_metida_por_detras_se_ve(almacen, caja) -> None:
    conn = almacen.conn
    caja.llegada(caja.adjunto_pdf(pdf("una")), caja.adjunto("enlace"))
    _registrar(almacen, caja)
    assert verificar_evidencia(conn) == []
    conn.execute("DROP TRIGGER adjunto_correo_sin_update")
    conn.execute("UPDATE adjunto_correo SET resultado = 'no_pdf' WHERE resultado = 'enlace'")
    conn.execute("DROP TRIGGER mensaje_correo_sin_update")
    conn.execute("UPDATE mensaje_correo SET asunto_doc = 'Otro'")
    problemas = verificar_evidencia(conn)
    assert any(p.startswith("adjunto_correo") and "por detras" in p for p in problemas)
    assert any(p.startswith("mensaje_correo") and "por detras" in p for p in problemas)
    with transaccion(conn):
        conn.execute("INSERT INTO ronda_correo (empezada_en, resultado, registrada_en) "
                     "VALUES (?, 'bien', ?)", (marca(AHORA), marca(AHORA)))
    assert any(p.startswith("ronda_correo") and "por detras" in p
               for p in verificar_evidencia(conn))


def test_lo_que_no_es_pdf_se_apunta_sin_documento(almacen, caja) -> None:
    resultados = ("no_es_pdf", "demasiado_grande", "xml", "reenvio", "no_pdf", "enlace",
                  "error")
    caja.llegada(*(caja.adjunto(r, f"a-{r}") for r in resultados))
    caja.llegada(caja.adjunto("no_deseado"), carpeta="no_deseado")
    assert _registrar(almacen, caja).mensajes == 2
    filas = _filas(almacen.conn, "adjunto_correo")
    assert [a["resultado"] for a in filas] == [*resultados, "no_deseado"]
    assert {a["documento_id"] for a in filas} == {None}
    assert _filas(almacen.conn, "documento") == [] and caja.ficheros() == []


def test_textos_de_terceros_saneados(almacen, caja) -> None:
    raro = "Fac\u202etuur\u200b\x07 2026\n0412\u2028"
    caja.llegada(caja.adjunto_pdf(pdf("una"), nombre="fac\u202ftuur\u200e\x00.pdf"),
                 asunto=raro, remitente="ana\u202e@proveedor.example.test")
    _registrar(almacen, caja)
    [mensaje] = _filas(almacen.conn, "mensaje_correo")
    assert mensaje["asunto_doc"] == "Factuur 2026 0412"
    assert mensaje["remitente_doc"] == "ana@proveedor.example.test"
    [adjunto] = _filas(almacen.conn, "adjunto_correo")
    assert adjunto["nombre_doc"] == "fac tuur.pdf"
    assert _filas(almacen.conn, "documento")[0]["nombre_original"] == "fac tuur.pdf"


def test_sin_fecha_de_recepcion_antes_del_2000(almacen, caja) -> None:
    caja.llegada(caja.adjunto_pdf(pdf("vieja")), recibido_en=bandeja.SIN_FECHA)
    _registrar(almacen, caja)
    [documento] = _filas(almacen.conn, "documento")
    assert (documento["recibido_en"], documento["recibido_fuente"]) == (None, "desconocido")
    assert _filas(almacen.conn, "mensaje_correo")[0]["recibido_en"] == (
        "1970-01-01T00:00:00+00:00")


# ============================================================ la bandeja no es de fiar

def test_nombres_que_no_son_de_la_bandeja_se_ignoran(almacen, caja) -> None:
    datos = caja.llegada(caja.adjunto("xml"))
    bueno = caja.llegadas / caja.nombre(datos)
    contenido = bueno.read_bytes()
    bueno.unlink()
    hexa = caja.nombre(datos)[:-5]
    raros = ["..json", f"{hexa.upper()}.json", f"{hexa}.JSON", f"{hexa}.json.tmp",
             f"x{hexa[1:]}.json", "a\\b.json", "c:d.json", f"{hexa[:-1]}.json",
             ".parcial-123", "estado.json"]
    for nombre in raros:
        (caja.llegadas / nombre).write_bytes(contenido)
    (caja.pdf / "otro.pdf").write_bytes(pdf("x"))
    hecho = _registrar(almacen, caja)
    assert (hecho.mensajes, hecho.rechazados) == (0, [])
    assert _filas(almacen.conn, "mensaje_correo") == []
    assert len(caja.ficheros()) == len(raros) + 1      # no se toca lo que no es suyo


def test_un_fichero_que_es_un_enlace_se_rechaza_sin_seguirlo(almacen, caja, tmp_path) -> None:
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    datos = caja.llegada(caja.adjunto("xml"))
    llegada = caja.llegadas / caja.nombre(datos)
    objetivo = fuera / "secreto.json"
    objetivo.write_bytes(llegada.read_bytes())
    llegada.unlink()
    llegada.symlink_to(objetivo)
    contenido = pdf("una")
    sha = hashlib.sha256(contenido).hexdigest()
    (fuera / "x.pdf").write_bytes(contenido)
    (caja.pdf / f"{sha}.pdf").symlink_to(fuera / "x.pdf")
    hecho = _registrar(almacen, caja)
    assert hecho.mensajes == 0 and len(hecho.rechazados) == 2
    assert all("no es un fichero normal" in r for r in hecho.rechazados)
    # Se quitan los enlaces, no lo que senalan.
    assert caja.ficheros() == [] and objetivo.exists() and (fuera / "x.pdf").exists()
    assert _filas(almacen.conn, "mensaje_correo") == []


@pytest.mark.parametrize("carpeta", ["pdf", "llegadas", "estado"])
def test_una_carpeta_cambiada_por_un_enlace_no_se_toca(almacen, caja, tmp_path, carpeta,
                                                       capsys) -> None:
    contenido = pdf("una")
    caja.llegada(caja.adjunto_pdf(contenido))
    caja.estado_json()
    real = {"pdf": caja.pdf, "llegadas": caja.llegadas, "estado": caja.estado}[carpeta]
    otra = tmp_path / "otra-parte"
    real.rename(otra)
    real.symlink_to(otra, target_is_directory=True)
    antes = sorted(p.name for p in otra.iterdir())
    hecho = _registrar(almacen, caja)
    assert hecho.carpetas_malas == [f"entrada/{carpeta}" if carpeta != "estado" else "estado"]
    assert sorted(p.name for p in otra.iterdir()) == antes      # nada borrado alli
    if carpeta != "estado":
        assert hecho.mensajes == 0 and _filas(almacen.conn, "mensaje_correo") == []
    estado = almacen.conn.execute("SELECT * FROM estado_correo").fetchone()
    assert estado["error_codigo"] == "interno"


def test_json_que_no_vale_se_rechaza_y_se_quita(almacen, caja) -> None:
    base = caja.llegada(caja.adjunto("xml"))
    (caja.llegadas / caja.nombre(base)).unlink()
    casos = {
        "enorme": bandeja.como_json(dict(base, asunto=None, relleno="x" * 70_000)),
        "roto": b'{"version": 1, ',
        "no_utf8": b"\xff\xfe{}",
        "de_mas": bandeja.como_json(dict(base, cuerpo="hola")),
        "de_menos": bandeja.como_json({k: v for k, v in base.items() if k != "asunto"}),
        "repetida": bandeja.como_json(base)[:-2] + b', "asunto": "otro"}\n',
        "nan": bandeja.como_json(base).replace(b'"en_linea": 0', b'"en_linea": NaN'),
        "bool": bandeja.como_json(dict(base, en_linea=True)),
        "version": bandeja.como_json(dict(base, version=2)),
        "carpeta": bandeja.como_json(dict(base, carpeta="enviados")),
        "graph_id": bandeja.como_json(dict(base, graph_id="AAMk/../x y")),
        "message_id": bandeja.como_json(dict(base, internet_message_id="<a b@c>")),
        "fecha": bandeja.como_json(dict(base, recibido_en="2026-11-23 08:14:02")),
        "asunto": bandeja.como_json(dict(base, asunto="x" * 201)),
        "remitente": bandeja.como_json(dict(base, remitente=["a"])),
        "adjuntos": bandeja.como_json(dict(base, adjuntos=[caja.adjunto("xml")] * 51)),
        "resultado": bandeja.como_json(dict(base, adjuntos=[dict(caja.adjunto("xml"),
                                                                 resultado="documento")])),
        "sha_sin_pdf": bandeja.como_json(dict(base, adjuntos=[dict(caja.adjunto("xml"),
                                                                   sha256="a" * 64)])),
        "pdf_sin_sha": bandeja.como_json(dict(base, adjuntos=[dict(caja.adjunto("pdf"),
                                                                   sha256=None)])),
        "id_repetido": bandeja.como_json(dict(base, adjuntos=[caja.adjunto("xml")] * 2)),
        "profundo": b'{"a":' * 5000 + b"1" + b"}" * 5000,
    }
    for i, (_caso, contenido) in enumerate(casos.items()):
        datos = dict(base, graph_id=f"AAMkAGcaso{i:04d}")
        caja.escribir_llegada(datos, contenido=contenido.replace(
            base["graph_id"].encode(), datos["graph_id"].encode()))
    # Y uno bueno, con el nombre de otro mensaje: tampoco vale.
    caja.escribir_llegada(base, nombre=caja.nombre(dict(base, graph_id="AAMkAGotro")))
    hecho = _registrar(almacen, caja)
    assert hecho.mensajes == 0
    assert len(hecho.rechazados) == len(casos) + 1
    assert caja.ficheros() == [] and _filas(almacen.conn, "mensaje_correo") == []
    # Lo que dice no copia nada de lo que venia.
    assert not any("hola" in r or "enviados" in r or "otro" in r for r in hecho.rechazados)


def test_un_pdf_que_no_casa_o_no_es_pdf_queda_error(almacen, caja) -> None:
    bueno = pdf("bueno")
    cambiado = caja.adjunto_pdf(pdf("original"), escribir=False)
    (caja.pdf / f"{cambiado['sha256']}.pdf").write_bytes(pdf("otro"))       # sha que no casa
    html = b"<html>no soy un pdf</html>"
    no_pdf = caja.adjunto_pdf(html)                                       # sin %PDF-
    falta = caja.adjunto_pdf(pdf("falta"), escribir=False)                # no esta
    caja.llegada(caja.adjunto_pdf(bueno), cambiado, no_pdf, falta)
    hecho = _registrar(almacen, caja)
    assert hecho.mensajes == 1 and hecho.documentos_nuevos == 1
    assert [(a["resultado"], a["sha256"]) for a in _filas(almacen.conn, "adjunto_correo")] == [
        ("documento", sha256_bytes(bueno)), ("error", None), ("error", None), ("error", None)]
    assert len(hecho.rechazados) == 2 and caja.ficheros() == []


def test_un_pdf_de_mas_de_20_mib_queda_error(almacen, caja, monkeypatch) -> None:
    monkeypatch.setattr(registrar, "MAX_PDF", 4096)
    grande = caja.adjunto_pdf(pdf("grande", 5000))
    caja.llegada(grande)
    _registrar(almacen, caja)
    assert [a["resultado"] for a in _filas(almacen.conn, "adjunto_correo")] == ["error"]
    assert caja.ficheros() == []


def test_un_pdf_de_los_datos_de_prueba_no_entra(almacen, caja) -> None:
    prueba = pdf("x") + b"\n% BMS-DEMO\n"
    caja.llegada(caja.adjunto_pdf(prueba))
    caja.llegada(caja.adjunto_pdf(prueba, nombre="otra-vez.pdf"))
    hecho = _registrar(almacen, caja)
    assert hecho.mensajes == 2 and hecho.documentos_nuevos == 0
    assert [a["resultado"] for a in _filas(almacen.conn, "adjunto_correo")] == [
        "de_prueba", "de_prueba"]
    assert _filas(almacen.conn, "documento") == [] and caja.ficheros() == []


def test_la_base_de_prueba_no_registra_nada(almacen, caja) -> None:
    from bms_agent.almacen import MARCA_DEMO

    almacen.conn.execute(f"PRAGMA application_id = {MARCA_DEMO}")
    caja.llegada(caja.adjunto_pdf(pdf("una")))
    with pytest.raises(registrar.NoSeRegistra, match="prueba"):
        _registrar(almacen, caja)
    with pytest.raises(registrar.NoSeRegistra):
        registrar.apuntar_fallo(almacen, "salida")
    assert len(caja.ficheros()) == 2
    assert almacen.conn.execute("SELECT count(*) FROM estado_correo").fetchone()[0] == 0


# ============================================================ el reloj

def test_una_llegada_del_futuro_espera_y_el_correo_dice_reloj(almacen, caja, reloj) -> None:
    conn = almacen.conn
    caja.estado_json()
    futura = caja.llegada(caja.adjunto_pdf(pdf("futura")), recibido_en="2026-11-24T10:06:00Z")
    casi = caja.llegada(caja.adjunto_pdf(pdf("casi")), recibido_en="2026-11-24T10:04:59Z")
    hecho = _registrar(almacen, caja)
    assert (hecho.mensajes, hecho.esperan_reloj, hecho.error_codigo) == (1, 1, "reloj")
    assert [m["graph_id"] for m in _filas(conn, "mensaje_correo")] == [casi["graph_id"]]
    assert (caja.llegadas / caja.nombre(futura)).exists()        # se queda
    estado = conn.execute("SELECT * FROM estado_correo").fetchone()
    assert (estado["error_codigo"], estado["error_desde"]) == ("reloj", marca(AHORA))
    # El reloj se pone bien (y el correo hace otra ronda): entra, con su fecha del servidor.
    reloj.avanzar(minutes=10)
    caja.estado_json(empezada="2026-11-24T10:09:00Z", mensajes=0, pdf=0)
    hecho = _registrar(almacen, caja)
    assert (hecho.mensajes, hecho.esperan_reloj, hecho.error_codigo) == (1, 0, None)
    assert _filas(conn, "documento")[-1]["recibido_en"] == "2026-11-24T10:06:00+00:00"
    assert caja.ficheros() == []


# ============================================================ cuantos por pasada

def test_2500_ficheros_mira_2000_los_mas_antiguos(almacen, caja) -> None:
    nombres = []
    for i in range(2500):
        datos = caja.llegada(caja.adjunto("xml"), asunto=None)
        ruta = caja.llegadas / caja.nombre(datos)
        os.utime(ruta, ns=(1_700_000_000_000_000_000 + i * 1000,) * 2)
        nombres.append(ruta.name)
    hecho = _registrar(almacen, caja)
    assert hecho.mensajes == 2000 and hecho.quedan
    assert sorted(p.name for p in caja.llegadas.iterdir()) == sorted(nombres[2000:])
    hecho = _registrar(almacen, caja)
    assert hecho.mensajes == 500 and not hecho.quedan
    assert caja.ficheros() == []


# ============================================================ idempotencia

def test_el_mismo_mensaje_dos_veces(almacen, caja) -> None:
    conn = almacen.conn
    contenido = pdf("una")
    datos = caja.llegada(caja.adjunto_pdf(contenido))
    _registrar(almacen, caja)
    eventos = conn.execute("SELECT count(*) FROM evento").fetchone()[0]
    # La delta volvio a empezar: el correo lo escribe otra vez, con su PDF.
    caja.escribir_llegada(datos)
    (caja.pdf / f"{sha256_bytes(contenido)}.pdf").write_bytes(contenido)
    hecho = _registrar(almacen, caja)
    assert (hecho.mensajes, hecho.repetidos, hecho.documentos_nuevos) == (0, 1, 0)
    assert len(_filas(conn, "mensaje_correo")) == 1 and caja.ficheros() == []
    assert conn.execute("SELECT count(*) FROM evento").fetchone()[0] == eventos


def test_el_mismo_pdf_en_dos_mensajes_es_un_documento(almacen, caja) -> None:
    conn = almacen.conn
    contenido = pdf("una")
    caja.llegada(caja.adjunto_pdf(contenido))
    _registrar(almacen, caja)
    # El segundo correo llega cuando el primero ya se registro (y su PDF salio de la bandeja):
    # el correo lo vuelve a bajar...
    caja.llegada(caja.adjunto_pdf(contenido, nombre="copia.pdf"))
    # ...o no lo encuentra (otro mensaje con el mismo PDF lo pudo borrar): da igual.
    caja.llegada(caja.adjunto_pdf(contenido, nombre="otra.pdf", escribir=False))
    hecho = _registrar(almacen, caja)
    assert (hecho.mensajes, hecho.documentos_nuevos) == (2, 0)
    [documento] = _filas(conn, "documento")
    assert documento["nombre_original"] == "factuur-0412.pdf"       # el del primero
    assert [(a["resultado"], a["documento_id"]) for a in _filas(conn, "adjunto_correo")] == [
        ("documento", documento["id"])] * 3
    assert caja.ficheros() == []
    assert verificar_evidencia(conn) == []


def test_el_mismo_pdf_ya_llegado_por_el_buzon(almacen, caja) -> None:
    conn = almacen.conn
    contenido = pdf("una")
    with transaccion(conn):
        antes = registrar_documento(
            almacen, sha256=sha256_bytes(contenido), contenido=contenido,
            nombre_original="factuur.pdf", tipo_mime="application/pdf", origen="carpeta",
            ruta_declarada="entrante", recibido_en=None, recibido_fuente="desconocido",
            actor=usuario_sistema(conn, "extractor"))
    caja.llegada(caja.adjunto_pdf(contenido))
    hecho = _registrar(almacen, caja)
    assert (hecho.mensajes, hecho.documentos_nuevos) == (1, 0)
    [documento] = _filas(conn, "documento")
    assert (documento["id"], documento["origen"]) == (antes.id, "carpeta")   # no cambia
    assert _filas(conn, "adjunto_correo")[0]["documento_id"] == antes.id
    assert caja.ficheros() == []


def test_un_pdf_suelto_ya_registrado_sale_de_la_bandeja(almacen, caja) -> None:
    contenido = pdf("una")
    caja.llegada(caja.adjunto_pdf(contenido))
    _registrar(almacen, caja)
    # Otro mensaje con el mismo PDF y otro adjunto aun pendiente: su PDF ya esta en pdf/ sin su
    # llegada. El que ya esta en la base sale; el que no, espera a su llegada.
    (caja.pdf / f"{sha256_bytes(contenido)}.pdf").write_bytes(contenido)
    otro = pdf("pendiente")
    (caja.pdf / f"{sha256_bytes(otro)}.pdf").write_bytes(otro)
    hecho = _registrar(almacen, caja)
    assert hecho.pdf_borrados == 1
    assert caja.ficheros() == [f"pdf/{sha256_bytes(otro)}.pdf"]


# ============================================================ estado.json y las rondas

def test_estado_json_a_estado_correo(almacen, caja) -> None:
    conn = almacen.conn
    caja.estado_json(retenido_hasta="2026-11-24T23:00:00Z",
                     delta_reiniciado_en="2026-11-20T10:00:00Z")
    hecho = _registrar(almacen, caja)
    assert hecho.estado_copiado and hecho.ronda_registrada
    estado = dict(conn.execute("SELECT * FROM estado_correo").fetchone())
    assert estado == {
        "id": 1, "buzon": "facturen@contoso.onmicrosoft.com",
        "ultima_consulta": "2026-11-24T09:55:00+00:00",
        "ultima_buena": "2026-11-24T09:55:00+00:00", "error_codigo": None,
        "error_desde": None, "alcance_comprobado_en": "2026-11-24T09:00:00+00:00",
        "alcance_bien": 1, "credencial_caduca_en": "2028-11-23T09:55:00+00:00",
        "delta_reiniciado_en": "2026-11-20T10:00:00+00:00",
        "retenido_hasta": "2026-11-24T23:00:00+00:00",
        "hoy_json": json.dumps({"bytes": 4000, "fecha": "2026-11-24", "mensajes": 3, "pdf": 2},
                               sort_keys=True),
        "aviso_volumen": 0, "actualizado_en": marca(AHORA)}
    [ronda] = _filas(conn, "ronda_correo")
    assert {k: ronda[k] for k in ("empezada_en", "terminada_en", "resultado", "error_codigo",
                                  "mensajes", "documentos_nuevos")} == {
        "empezada_en": "2026-11-24T09:55:00+00:00", "terminada_en": "2026-11-24T09:55:00+00:00",
        "resultado": "bien", "error_codigo": None, "mensajes": 1, "documentos_nuevos": 1}
    # La misma ronda otra vez (registrar sin que el correo haya corrido): no se repite.
    assert not _registrar(almacen, caja).ronda_registrada
    # Una ronda sin nada y con el mismo codigo: no se apunta (no 288 filas al dia).
    caja.estado_json(empezada="2026-11-24T10:00:00Z", mensajes=0, pdf=0)
    assert not _registrar(almacen, caja).ronda_registrada
    # Una que cambia de error, si; y la que vuelve a ir bien, tambien.
    caja.estado_json(empezada="2026-11-24T10:05:00Z", mensajes=0, pdf=0, codigo="limitado")
    assert _registrar(almacen, caja).ronda_registrada
    estado = conn.execute("SELECT * FROM estado_correo").fetchone()
    assert (estado["error_codigo"], estado["error_desde"]) == ("limitado",
                                                              "2026-11-24T10:05:00+00:00")
    caja.estado_json(empezada="2026-11-24T10:10:00Z", mensajes=0, pdf=0, codigo="limitado")
    assert not _registrar(almacen, caja).ronda_registrada
    # El mismo error sigue siendo de cuando empezo.
    assert conn.execute("SELECT error_desde FROM estado_correo").fetchone()[0] == (
        "2026-11-24T10:05:00+00:00")
    caja.estado_json(empezada="2026-11-24T10:15:00Z", mensajes=0, pdf=0)
    assert _registrar(almacen, caja).ronda_registrada
    assert [(r["error_codigo"], r["resultado"]) for r in _filas(conn, "ronda_correo")] == [
        (None, "bien"), ("limitado", "fallo"), (None, "bien")]
    eventos = conn.execute("SELECT actor FROM evento WHERE tipo = 'correo_ronda_registrada'"
                           ).fetchall()
    assert {e[0] for e in eventos} == {usuario_sistema(conn, "correo")} and len(eventos) == 3
    assert verificar_evidencia(conn) == []


def test_sin_estado_json_el_correo_sigue_sin_configurar(almacen, caja) -> None:
    hecho = _registrar(almacen, caja)
    assert not hecho.estado_copiado
    assert almacen.conn.execute("SELECT * FROM estado_correo").fetchone() is None


@pytest.mark.parametrize("cambio", [
    {"version": 2}, {"aviso_volumen": 1}, {"buzon": "a\u202eb@contoso.onmicrosoft.com"},
    {"ronda": {"empezada": "x"}}, {"hoy": {"fecha": "hoy", "mensajes": 0, "pdf": 0, "bytes": 0}},
    {"alcance": {"comprobado_en": None, "bien": True, "motivo_codigo": None}},
    {"sobra": 1}])
def test_un_estado_json_que_no_vale_es_interno(almacen, caja, cambio) -> None:
    datos = caja.estado_json()
    datos.update(cambio)
    (caja.estado / "estado.json").write_bytes(bandeja.como_json(datos))
    hecho = _registrar(almacen, caja)
    assert not hecho.estado_copiado and hecho.error_codigo == "interno"
    assert almacen.conn.execute("SELECT error_codigo FROM estado_correo").fetchone()[0] == (
        "interno")


def test_el_codigo_que_no_es_de_la_ronda_no_lo_tapa_una_ronda_vieja(almacen, caja, reloj
                                                                    ) -> None:
    """`registrar --fallo salida`: el ciclo no pudo traer nada. Un estado.json de antes (el
    correo no corrio) no lo quita; la ronda siguiente del correo, si."""
    conn = almacen.conn
    caja.estado_json()
    _registrar(almacen, caja)
    reloj.avanzar(minutes=5)
    assert registrar.apuntar_fallo(almacen, "salida")
    assert not registrar.apuntar_fallo(almacen, "salida")          # ya estaba: sin fila nueva
    reloj.avanzar(minutes=1)
    assert _registrar(almacen, caja).error_codigo == "salida"
    fila = conn.execute("SELECT error_codigo, error_desde FROM estado_correo").fetchone()
    assert tuple(fila) == ("salida", marca(AHORA + timedelta(minutes=5)))
    reloj.avanzar(minutes=5)
    caja.estado_json(empezada="2026-11-24T10:10:00Z", mensajes=0, pdf=0)
    assert _registrar(almacen, caja).error_codigo is None
    filas = _filas(conn, "ronda_correo")
    assert [(r["error_codigo"], r["terminada_en"] is None) for r in filas] == [
        (None, False), ("salida", True)]
    assert verificar_evidencia(conn) == []


def test_fallo_sin_estado_previo(almacen) -> None:
    assert registrar.apuntar_fallo(almacen, "disco")
    estado = almacen.conn.execute("SELECT * FROM estado_correo").fetchone()
    assert (estado["error_codigo"], estado["hoy_json"], estado["buzon"]) == ("disco", "{}", None)
    with pytest.raises(ValueError):
        registrar.apuntar_fallo(almacen, "ocupado")


# ============================================================ la pausa por volumen

def test_la_pausa_por_volumen_al_ver_aviso_volumen(almacen, caja, reloj) -> None:
    conn = almacen.conn
    caja.estado_json(aviso=True, fecha="2026-11-23")      # el de ayer: no pausa hoy
    assert not _registrar(almacen, caja).pausa_volumen
    assert auto.pausa_vigente(conn) is None
    caja.estado_json(aviso=True)
    assert _registrar(almacen, caja).pausa_volumen
    pausa = auto.pausa_vigente(conn)
    assert (pausa["motivo"], pausa["por"]) == ("volumen", usuario_sistema(conn, "automatico"))
    # Una persona la quita: hoy no vuelve aunque estado.json lo siga diciendo.
    ana = persona(conn, "Ana", "administrador")
    auto.reanudar(conn, ana, "lo he mirado")
    reloj.avanzar(minutes=5)
    assert not _registrar(almacen, caja).pausa_volumen
    assert auto.pausa_vigente(conn) is None


# ============================================================ la CLI

def test_la_cli(tmp_path, caja, capsys, monkeypatch) -> None:
    db = tmp_path / "datos" / "bms.sqlite3"
    caja.llegada(caja.adjunto_pdf(pdf("una")), asunto="Asunto-que-no-se-dice",
                 remitente="quien@nadie.example.test")
    argumentos = ["correo", "registrar", "--entrada", str(caja.entrada), "--estado",
                  str(caja.estado), "--db", str(db)]
    assert cli.main(argumentos) == 0
    salida = capsys.readouterr()
    assert "1 mensajes, 1 documentos nuevos" in salida.out
    assert cli.main(["correo", "registrar", "--fallo", "salida", "--db", str(db)]) == 0
    assert "salida" in capsys.readouterr().out
    assert cli.main(["correo", "registrar", "--db", str(db)]) == 2          # faltan carpetas
    caja.escribir_llegada({}, nombre="0" * 64 + ".json", contenido=b"Asunto-que-no-se-dice{")
    assert cli.main(argumentos) == cli.CORREO_FALLO
    salida = capsys.readouterr()
    for texto in ("Asunto-que-no-se-dice", "quien@nadie", "Factuur"):
        assert texto not in salida.out + salida.err
    with preparar(db) as almacen:
        assert almacen.conn.execute("SELECT count(*) FROM mensaje_correo").fetchone()[0] == 1
    # En la instalacion nativa no hay correo.
    monkeypatch.setattr("bms_agent.nativo.instalacion_actual", lambda: object())
    assert cli.main(argumentos) == 2


def test_registrar_no_trae_graph_ni_el_certificado() -> None:
    """§7.2: registrar (en `orden`) no importa el cliente de Graph, el certificado, httpx2 ni
    cryptography; y la CLI no carga cryptography para registrar."""
    codigo = ("import sys; sys.path.insert(0, sys.argv[1]); "
              "import bms_agent.correo.registrar; "
              "print('\\n'.join(sorted(sys.modules)))")
    proceso = subprocess.run([sys.executable, "-c", codigo, str(SRC.parent)],
                             capture_output=True, text=True, timeout=60)
    assert proceso.returncode == 0, proceso.stderr
    cargados = set(proceso.stdout.split())
    prohibidos = {"bms_agent.correo.graph", "bms_agent.correo.certificado",
                  "bms_agent.correo.traer", "httpx2", "httpcore2", "cryptography", "anthropic"}
    assert cargados & prohibidos == set()


# ============================================================ de punta a punta (§7.3)

def test_de_punta_a_punta_sin_red(almacen, caja, reloj, tmp_path) -> None:
    """GraphFalso -> correo traer -> correo registrar (la bandeja queda vacia) -> lectura
    siguiente -> tomar --automatica -> contar -> autorizar -> leer (el cliente falso) -> las
    facturas en la cola, con la fecha de recepcion del servidor. El mismo correo otra vez: nada
    nuevo, nada pagado. Y con un PDF que la API no acepta en medio: los demas se leen y ese
    espera a una persona. Los topes de la autorizacion se cumplen."""
    from graph_falso import GraphFalso, crear_certificado, fixture, mensajes
    from test_lectura import DEL_DOCUMENTO, ClienteQueFalla
    from test_lectura_automatica import _ronda

    from bms_agent.correo import ajustes, traer

    conn = almacen.conn
    pem, cer = crear_certificado(tmp_path / "secretos-correo", AHORA)
    inquilino, aplicacion = "1111abcd-2222-4333-8444-55555555ef55", (
        "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")
    buzon, control = "facturen@contoso.onmicrosoft.com", "bms-control@contoso.onmicrosoft.com"
    falso = GraphFalso(certificado=cer.read_bytes(), inquilino=inquilino, aplicacion=aplicacion,
                       buzon=buzon, control=control, ahora=reloj.ahora)
    ruta_ajustes = tmp_path / "correo_ajustes.json"
    ajustes.escribir(ruta_ajustes, ajustes.Ajustes(
        inquilino=inquilino, aplicacion=aplicacion, buzon=buzon, buzon_control=control,
        desde=date(2026, 10, 25), limites=ajustes.Limites()))
    lista = fixture("adjuntos.json")["factura"]
    numero = iter(range(1, 100))

    def llega(*marcas: str, recibido: str = "2026-11-23T08:14:02Z") -> None:
        mensaje = dict(mensajes()["factura"], receivedDateTime=recibido)
        mensaje["id"] = mensaje["id"][:-6] + f"{next(numero):04d}AA"
        adjuntos = [dict(lista[0], id=f"AAMkAGUzY5QKjAAABEgAQ{i:04d}=", name=f"{m}.pdf")
                    for i, m in enumerate(marcas)]
        falso.llega(mensaje, "inbox", adjuntos,
                    {a["id"]: pdf(m) for a, m in zip(adjuntos, marcas, strict=True)})

    def ronda_del_correo() -> registrar.Resultado:
        hecho = traer.traer(ajustes=ruta_ajustes, certificado=pem, estado=caja.estado,
                            entrada=caja.entrada, transporte=falso.transporte,
                            ahora=reloj.ahora, dormir=lambda _s: None)
        assert hecho.codigo is None, hecho.detalle
        registrado = _registrar(almacen, caja)
        assert caja.ficheros() == []         # la bandeja: solo lo que aun no se ha registrado
        return registrado

    llega("una")
    llega("dos", recibido="2026-11-23T23:30:00Z")      # el 24 en Amsterdam
    assert ronda_del_correo().documentos_nuevos == 2
    out = tmp_path / "out"
    client = ClienteQueFalla(al_contar={"rara": DEL_DOCUMENTO["413"]})
    # Sin autorizacion, nada se lee solo.
    assert _ronda(almacen, client, out) == (lectura.NADA, None)
    ana = persona(conn, "Ana", "administrador")
    auto.fijar(conn, ana, activa=1, **auto.POR_DEFECTO, motivo="Las del correo, solas")
    estado, solicitud = _ronda(almacen, client, out)
    assert estado == "hecha" and sorted(client.leidos) == ["dos", "una"]
    fila = conn.execute("SELECT * FROM solicitud_lectura WHERE id = ?", (solicitud,)).fetchone()
    assert (fila["origen"], fila["aprobada_via"]) == ("automatica", "automatica")
    assert fila["tope_usd_micro"] <= auto.POR_DEFECTO["tope_dia_usd_micro"]
    pasada = conn.execute("SELECT * FROM pasada_lectura WHERE solicitud_id = ?",
                          (solicitud,)).fetchone()
    assert 0 < pasada["coste_usd_micro"] <= fila["tope_usd_micro"]
    # Las facturas, en la cola, con el dia en que llegaron al servidor (en Amsterdam).
    recepcion = {f["numero"]: f["fecha_recepcion"] for f in conn.execute(
        "SELECT numero, fecha_recepcion FROM factura")}
    assert recepcion == {"F-una": "2026-11-23", "F-dos": "2026-11-24"}
    assert {f["numero"] for f in consultas.listado(conn)} >= {"F-una", "F-dos"}

    # El mismo correo otra vez (la delta vuelve a empezar): nada nuevo, nada pagado.
    (caja.estado / "delta-bandeja.json").unlink()
    (caja.estado / "vistos.json").unlink()
    reloj.avanzar(minutes=5)
    contados, leidos = list(client.contados), list(client.leidos)
    hecho = ronda_del_correo()
    assert (hecho.mensajes, hecho.repetidos, hecho.documentos_nuevos) == (0, 2, 0)
    assert _ronda(almacen, client, out) == (lectura.NADA, None)
    assert (client.contados, client.leidos) == (contados, leidos)

    # Un correo con un PDF que la API no acepta entre dos buenos: los buenos se leen y ese
    # espera a una persona, sin bloquear nada.
    reloj.avanzar(hours=2)
    llega("tres", "rara", "cuatro", recibido="2026-11-24T11:00:00Z")
    assert ronda_del_correo().documentos_nuevos == 3
    estado, _solicitud = _ronda(almacen, client, out)
    assert estado == "hecha" and sorted(client.leidos) == ["cuatro", "dos", "tres", "una"]
    esperan = auto.esperan_persona(conn)
    assert [(d["nombre_original"], d["motivo_codigo"]) for d in esperan["documentos"]] == [
        ("rara.pdf", "rechazado_api")]
    assert auto.elegibles(conn) == []
    # Lo gastado no pasa de los topes del dia y del mes.
    dia, mes = auto.gastado(conn)
    assert 0 < dia <= auto.POR_DEFECTO["tope_dia_usd_micro"] and mes == dia
    assert verificar_evidencia(conn) == []
    falso.comprobar()
