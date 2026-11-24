"""Una ronda del correo de facturas: `correo traer` y `correo comprobar` (paso 18, paso 9 del
plan; solo Docker).

Contra GraphFalso (tests/graph_falso.py):

- la bandeja: nombres que genera el codigo (pdf/<sha256>.pdf, llegadas/<sha256(id|carpeta)>.json),
  escritos de una vez, con lo que dice cada adjunto (§3.3) y nunca el cuerpo;
- los topes por adjunto, por mensaje, por ronda y por dia (retenido hasta manana, sin pedir
  nada a Graph), y el de la bandeja (`disco`);
- el mensaje raro entre dos buenos (los buenos se traen; el raro, al tercer intento, `error`), un
  corte a mitad de un mensaje que cuenta su intento, los pendientes durante 24 horas;
- "no deseado" sin bajar nada, y el mismo mensaje despues en la bandeja (se trae);
- el cerrojo del sistema, la idempotencia, estado.json, el delta que caduca;
- y que `correo traer` no abre la base ni importa el SDK de la API.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx2
import pytest
from conftest import RAIZ
from graph_falso import GraphFalso, crear_certificado, fixture, mensajes, pdf

from bms_agent import cli
from bms_agent.correo import MAX_PDF, ajustes, bandeja, graph, traer

SRC = RAIZ / "src" / "bms_agent"
AHORA = datetime(2026, 11, 24, 10, 0, tzinfo=timezone.utc)
INQUILINO = "1111abcd-2222-4333-8444-55555555ef55"
APLICACION = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
BUZON = "facturen@contoso.onmicrosoft.com"
CONTROL = "bms-control@contoso.onmicrosoft.com"
CLAVES_LLEGADA = {"version", "carpeta", "graph_id", "internet_message_id", "recibido_en",
                  "remitente", "asunto", "en_linea", "traido_en", "adjuntos"}
CLAVES_ADJUNTO = {"id", "nombre", "tipo", "bytes", "resultado", "sha256", "detalle"}


class Reloj:
    def __init__(self) -> None:
        self.instante = AHORA

    def __call__(self) -> datetime:
        return self.instante

    def avanzar(self, **delta: float) -> None:
        self.instante += timedelta(**delta)


class Corte(BaseException):
    """Lo que no es una excepcion del programa: un corte de luz, el proceso que muere."""


@pytest.fixture(scope="module")
def certificado_de_prueba(tmp_path_factory) -> tuple[Path, Path]:
    return crear_certificado(tmp_path_factory.mktemp("cert") / "secretos-correo", AHORA)


@pytest.fixture
def reloj() -> Reloj:
    return Reloj()


@pytest.fixture
def falso(certificado_de_prueba, reloj):
    falso = GraphFalso(certificado=certificado_de_prueba[1].read_bytes(), inquilino=INQUILINO,
                       aplicacion=APLICACION, buzon=BUZON, control=CONTROL, ahora=reloj)
    yield falso
    falso.comprobar()


class Correo:
    """Las carpetas del contenedor `correo` (los secretos, el estado y la bandeja) y una
    ronda contra el falso."""

    def __init__(self, raiz: Path, pem: Path, falso: GraphFalso, reloj: Reloj) -> None:
        self.ajustes = raiz / "secretos" / "correo_ajustes.json"
        self.ajustes.parent.mkdir()
        self.pem = pem
        self.estado = raiz / "estado"
        self.entrada = raiz / "entrada"
        self.estado.mkdir()
        self.entrada.mkdir()
        self.falso, self.reloj = falso, reloj
        self.dormidas: list[float] = []
        self.fijar()

    def fijar(self, **limites: int) -> None:
        ajustes.escribir(self.ajustes, ajustes.Ajustes(
            inquilino=INQUILINO, aplicacion=APLICACION, buzon=BUZON, buzon_control=CONTROL,
            desde=date(2026, 10, 25), limites=ajustes.Limites(**limites)))

    def ronda(self, **opciones) -> traer.Resultado:
        return traer.traer(ajustes=self.ajustes, certificado=self.pem, estado=self.estado,
                           entrada=self.entrada, transporte=self.falso.transporte,
                           ahora=self.reloj, dormir=self.dormidas.append, **opciones)

    def comprobar(self) -> traer.Resultado:
        return traer.comprobar(ajustes=self.ajustes, certificado=self.pem, estado=self.estado,
                               transporte=self.falso.transporte, ahora=self.reloj,
                               dormir=self.dormidas.append)

    def llegadas(self) -> dict[str, dict]:
        carpeta = self.entrada / "llegadas"
        return {p.name: json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(carpeta.glob("*"))} if carpeta.is_dir() else {}

    def llegada(self, mensaje: dict, carpeta: str = "bandeja") -> dict:
        return self.llegadas()[f"{bandeja.clave(mensaje['id'], carpeta)}.json"]

    def pdfs(self) -> dict[str, bytes]:
        carpeta = self.entrada / "pdf"
        return {p.name: p.read_bytes() for p in carpeta.glob("*")} if carpeta.is_dir() else {}

    def estado_json(self) -> dict:
        return json.loads((self.estado / "estado.json").read_text(encoding="utf-8"))

    def json(self, nombre: str) -> dict:
        return json.loads((self.estado / nombre).read_text(encoding="utf-8"))

    def registrar(self) -> None:
        """Lo que hara `orden` (paso 10): se lleva lo de la bandeja."""
        for carpeta in ("llegadas", "pdf"):
            for fichero in (self.entrada / carpeta).glob("*"):
                fichero.unlink()

    def parciales(self) -> list[Path]:
        return [p for p in self.entrada.rglob("*") if p.name.startswith(".parcial-")] + [
            p for p in self.estado.rglob("*") if p.name.startswith(".parcial-")]


@pytest.fixture
def correo(tmp_path, certificado_de_prueba, falso, reloj) -> Correo:
    return Correo(tmp_path, certificado_de_prueba[0], falso, reloj)


def _con_adjuntos(falso: GraphFalso, nombre: str, contenidos: dict[str, bytes] | None = None,
                  carpeta: str = "inbox", **cambios) -> dict:
    """Un mensaje de las fixtures, con sus adjuntos y lo que baja cada uno (un PDF por
    defecto)."""
    mensaje = {**mensajes()[nombre], **cambios}
    lista = fixture("adjuntos.json").get(nombre, [])
    if contenidos is None:
        contenidos = {a["id"]: pdf(f"{nombre} {a['id']}", 1500) for a in lista}
    falso.llega(mensaje, carpeta, lista, contenidos)
    return mensaje


def _otro(base: str, numero: int, **cambios) -> dict:
    """Otro mensaje como `base`, con otro id."""
    mensaje = dict(mensajes()[base], **cambios)
    mensaje["id"] = mensaje["id"][:-6] + f"{numero:04d}AA"
    return mensaje


# ============================================================ una ronda entera

def test_una_ronda_entera(correo, falso) -> None:
    falso.extra_en_mensajes = {"body": {"contentType": "html", "content": "CUERPO-SECRETO"},
                               "bodyPreview": "CUERPO-SECRETO", "toRecipients": [
                                   {"emailAddress": {"address": "otro@contoso.onmicrosoft.com"}}]}
    variado = fixture("adjuntos.json")["variado"]
    contenidos = {variado[0]["id"]: pdf("octet", 3072), variado[1]["id"]: pdf("mayusculas", 4096),
                  variado[2]["id"]: b"<html>no soy un pdf</html>"}
    factura = _con_adjuntos(falso, "factura")
    varios = _con_adjuntos(falso, "variado", contenidos)
    sin = _con_adjuntos(falso, "sin_adjuntos")
    spam = _con_adjuntos(falso, "spam", carpeta="junkemail")
    resultado = correo.ronda()
    assert (resultado.codigo, resultado.mensajes, resultado.pdf_nuevos) == (None, 4, 3)

    # Los nombres los pone el codigo: el sha256 de "id|carpeta" y el del PDF.
    llegadas = correo.llegadas()
    assert set(llegadas) == {f"{bandeja.clave(m['id'], c)}.json" for m, c in (
        (factura, "bandeja"), (varios, "bandeja"), (sin, "bandeja"), (spam, "no_deseado"))}
    pdfs = correo.pdfs()
    assert set(pdfs) == {f"{hashlib.sha256(d).hexdigest()}.pdf" for d in pdfs.values()}
    assert len(pdfs) == 3 and correo.parciales() == []
    for llegada in llegadas.values():
        assert set(llegada) == CLAVES_LLEGADA and llegada["version"] == 1
        assert all(set(a) == CLAVES_ADJUNTO for a in llegada["adjuntos"])

    una = correo.llegada(factura)
    assert {k: una[k] for k in ("carpeta", "graph_id", "internet_message_id", "recibido_en",
                                "remitente", "asunto", "en_linea", "traido_en")} == {
        "carpeta": "bandeja", "graph_id": factura["id"],
        "internet_message_id": "<0412.factuur@proveedor.example.test>",
        "recibido_en": "2026-11-23T08:14:02Z", "remitente": "facturen@proveedor.example.test",
        "asunto": "Factuur 2026-0412", "en_linea": 0, "traido_en": "2026-11-24T10:00:00Z"}
    [adjunto] = una["adjuntos"]
    contenido = falso.contenidos[(factura["id"], adjunto["id"])]
    assert adjunto == {"id": adjunto["id"], "nombre": "factuur-0412.pdf",
                       "tipo": "application/pdf", "bytes": len(contenido), "resultado": "pdf",
                       "sha256": hashlib.sha256(contenido).hexdigest(), "detalle": None}
    assert pdfs[f"{adjunto['sha256']}.pdf"] == contenido

    # Cada adjunto del variado, lo que dice §3.3; el de la imagen en linea solo se cuenta.
    otra = correo.llegada(varios)
    assert otra["en_linea"] == 1
    assert [(a["nombre"], a["resultado"]) for a in otra["adjuntos"]] == [
        ("factuur-octet", "pdf"), ("FACTUUR-MAYUSCULAS.PDF", "pdf"),
        ("no-soy-un.pdf", "no_es_pdf"), ("enorme.pdf", "demasiado_grande"),
        ("factuur-0412.xml", "xml"), ("reenviado.eml", "reenvio"),
        ("Draft sales invoice template.docx", "no_pdf"),
        ("Reminder - please bring laptop", "reenvio"), ("Sales Invoice Template.docx", "enlace")]
    assert [a["sha256"] is not None for a in otra["adjuntos"]] == [True, True] + [False] * 7
    # Solo se bajaron los tres candidatos que podian ser PDF y no pasaban de 20 MiB: ni el
    # enorme, ni el XML, ni el reenvio, ni el itemAttachment ni el enlace (el falso falla con
    # cualquier $value de esos dos).
    assert sorted(p.ruta.split("/")[-2] for p in falso.de_tipo("valor")) == sorted(
        [adjunto["id"], variado[0]["id"], variado[1]["id"], variado[2]["id"]])

    assert correo.llegada(sin)["adjuntos"] == [] and correo.llegada(sin)["en_linea"] == 0
    basura = correo.llegada(spam, "no_deseado")
    assert [a["resultado"] for a in basura["adjuntos"]] == ["no_deseado"]

    # Nunca el cuerpo ni los destinatarios: ni pedidos (el falso lo mira) ni guardados.
    for fichero in [*correo.entrada.rglob("*"), *correo.estado.rglob("*")]:
        if fichero.is_file():
            datos = fichero.read_bytes()
            assert b"CUERPO-SECRETO" not in datos and b"otro@contoso" not in datos
    assert all("body" not in p.consulta.lower() for p in falso.peticiones)


def test_lo_que_queda_apuntado_del_estado(correo, falso) -> None:
    _con_adjuntos(falso, "factura")
    correo.ronda()
    estado = correo.estado_json()
    assert set(estado) == {"version", "ronda", "hoy", "ultima_consulta", "ultima_buena", "buzon",
                           "certificado", "alcance", "delta_reiniciado_en", "retenido_hasta",
                           "aviso_volumen"}
    assert estado["ronda"] == {"empezada": "2026-11-24T10:00:00Z",
                               "terminada": "2026-11-24T10:00:00Z", "resultado": "bien",
                               "error_codigo": None, "mensajes": 1, "pdf_nuevos": 1,
                               "bytes": 1500}
    assert estado["hoy"] == {"fecha": "2026-11-24", "mensajes": 1, "pdf": 1, "bytes": 1500}
    assert estado["alcance"] == {"comprobado_en": "2026-11-24T10:00:00Z", "bien": True,
                                 "motivo_codigo": None}
    assert (estado["ultima_consulta"], estado["ultima_buena"]) == ("2026-11-24T10:00:00Z",) * 2
    assert estado["buzon"] == BUZON and estado["certificado"]["caduca_en"].startswith("2028-11-23")
    assert (estado["delta_reiniciado_en"], estado["retenido_hasta"],
            estado["aviso_volumen"]) == (None, None, False)
    delta = correo.json("delta-bandeja.json")
    assert graph.enlace_valido(delta["enlace"]) and "$deltatoken=" in delta["enlace"]
    assert delta["al_dia_en"] == "2026-11-24T10:00:00Z"
    assert correo.json("intentos.json")["mensajes"] == {} if (
        correo.estado / "intentos.json").exists() else True


def test_la_ronda_siguiente_solo_trae_lo_nuevo(correo, falso, reloj) -> None:
    factura = _con_adjuntos(falso, "factura")
    correo.ronda()
    primera = correo.llegadas()
    marcas = {p.name: p.stat().st_mtime_ns for p in (correo.entrada / "llegadas").glob("*")}
    reloj.avanzar(minutes=5)
    assert correo.ronda().mensajes == 0
    assert correo.llegadas() == primera and {p.name: p.stat().st_mtime_ns for p in (
        correo.entrada / "llegadas").glob("*")} == marcas
    # orden registra y se lleva lo de la bandeja; lo mismo otra vez no vuelve.
    correo.registrar()
    reloj.avanzar(minutes=5)
    assert correo.ronda().mensajes == 0 and correo.llegadas() == {}
    # Solo lo nuevo, y una vez cada cosa.
    nuevo = _otro("factura", 1)
    falso.llega(nuevo, "inbox", fixture("adjuntos.json")["factura"],
                {fixture("adjuntos.json")["factura"][0]["id"]: pdf("otra", 900)})
    reloj.avanzar(minutes=5)
    assert correo.ronda().mensajes == 1
    assert list(correo.llegadas()) == [f"{bandeja.clave(nuevo['id'], 'bandeja')}.json"]
    assert len(falso.de_tipo("valor")) == 2
    assert len(falso.de_tipo("adjuntos")) == 2
    assert factura["id"] != nuevo["id"]


# ============================================================ nombres, tamanos y tipos malos

def test_nombres_tamanos_y_tipos_de_terceros(correo, falso) -> None:
    malos = [
        {"@odata.type": "#microsoft.graph.fileAttachment", "id": "AAMk01", "name":
         "../../../etc/passwd.pdf", "contentType": "application/pdf", "size": 100,
         "isInline": False},
        {"@odata.type": "#microsoft.graph.fileAttachment", "id": "AAMk02", "name":
         "C:\\Windows\\factura\u202egnp.pdf", "contentType": "application/pdf; name=x",
         "size": "mucho", "isInline": False},
        {"@odata.type": "#microsoft.graph.fileAttachment", "id": "AAMk03", "name":
         "linea\r\nnueva\x1b[2J\x00.pdf", "contentType": None, "size": -5, "isInline": "no"},
        {"@odata.type": "#microsoft.graph.fileAttachment", "id": "AAMk04", "name": "x" * 900
         + ".pdf", "contentType": "application/pdf", "size": 10 ** 12, "isInline": False},
        {"@odata.type": "#microsoft.graph.fileAttachment", "id": "AAMk05", "name": 12345,
         "contentType": ["application/pdf"], "size": 50, "isInline": False},
        {"id": "AAMk06", "name": "sin tipo.pdf", "contentType": "application/pdf", "size": 1},
        {"@odata.type": "#microsoft.graph.fileAttachment", "id": "AAMk07", "name": "factura.xml",
         "contentType": "application/octet-stream", "size": 10, "isInline": False},
    ]
    mensaje = dict(mensajes()["factura"], subject="Pago\u202e urgente\x07\n" + "y" * 400,
                   **{"from": {"emailAddress": {"address": "a" * 400 + "@x.example.test"}}},
                   internetMessageId="<con espacios y\u00f1@x>")
    contenidos = {"AAMk01": pdf("uno"), "AAMk02": pdf("dos"), "AAMk03": pdf("tres"),
                  "AAMk05": b"no", "AAMk06": pdf("seis")}
    falso.llega(mensaje, "inbox", malos, contenidos)
    assert correo.ronda().codigo is None
    llegada = correo.llegada(mensaje)
    assert len(llegada["asunto"]) == 200 and "\u202e" not in llegada["asunto"]
    assert llegada["asunto"].startswith("Pago urgente y") and "\x07" not in llegada["asunto"]
    assert len(llegada["remitente"]) == 320 and llegada["internet_message_id"] is None
    por_id = {a["id"]: a for a in llegada["adjuntos"]}
    assert por_id["AAMk01"]["nombre"] == "../../../etc/passwd.pdf"     # texto, nunca una ruta
    assert por_id["AAMk02"]["nombre"] == "C:\\Windows\\facturagnp.pdf"
    # Un tamano declarado que no es un numero no impide bajarlo: cuenta lo que llega.
    assert por_id["AAMk02"]["bytes"] == len(contenidos["AAMk02"])
    assert por_id["AAMk02"]["resultado"] == "pdf"
    assert por_id["AAMk03"]["nombre"] == "linea nueva[2J.pdf" and por_id["AAMk03"]["tipo"] is None
    assert por_id["AAMk03"]["bytes"] == len(contenidos["AAMk03"])
    assert len(por_id["AAMk04"]["nombre"]) == 255
    assert por_id["AAMk04"]["resultado"] == "demasiado_grande"
    assert por_id["AAMk05"]["nombre"] is None and por_id["AAMk05"]["resultado"] == "no_pdf"
    assert por_id["AAMk06"]["resultado"] == "no_pdf"            # sin @odata.type: no se baja
    assert por_id["AAMk07"]["resultado"] == "xml"               # el nombre gana al tipo
    # En la bandeja solo hay nombres de sha256 en sus dos carpetas.
    for fichero in correo.entrada.rglob("*"):
        assert fichero.parent in (correo.entrada, correo.entrada / "pdf",
                                  correo.entrada / "llegadas")
        assert fichero.is_dir() or bandeja.NOMBRE_PDF.fullmatch(fichero.name) or (
            bandeja.NOMBRE_LLEGADA.fullmatch(fichero.name))
    assert {p.ruta.split("/")[-2] for p in falso.de_tipo("valor")} == {
        "AAMk01", "AAMk02", "AAMk03"}


def test_un_pdf_que_pasa_de_20_mib_al_bajarlo_se_corta(correo, falso) -> None:
    def sin_fin():
        yield b"%PDF-1.7\n"
        while True:
            yield b"0" * (64 * 1024)

    lista = fixture("adjuntos.json")["factura"]
    falso.llega(mensajes()["factura"], "inbox", lista, {lista[0]["id"]: sin_fin})
    resultado = correo.ronda()
    [adjunto] = correo.llegada(mensajes()["factura"])["adjuntos"]
    assert adjunto["resultado"] == "demasiado_grande" and adjunto["sha256"] is None
    assert MAX_PDF < adjunto["bytes"] <= MAX_PDF + 64 * 1024 + 16
    assert correo.pdfs() == {} and correo.parciales() == []
    assert resultado.pdf_nuevos == 0 and resultado.bytes == adjunto["bytes"]


def test_20_adjuntos_tratados_y_50_apuntados(correo, falso) -> None:
    lista = [{"@odata.type": "#microsoft.graph.fileAttachment", "id": f"AAMk{n:03d}",
              "name": f"f{n}.pdf", "contentType": "application/pdf", "size": 100,
              "isInline": False} for n in range(60)]
    falso.llega(mensajes()["factura"], "inbox", lista,
                {a["id"]: pdf(a["id"]) for a in lista})
    correo.ronda()
    adjuntos = correo.llegada(mensajes()["factura"])["adjuntos"]
    assert len(adjuntos) == 50
    assert [a["resultado"] for a in adjuntos] == ["pdf"] * 20 + ["no_pdf"] * 30
    assert all("demasiados adjuntos" in a["detalle"] for a in adjuntos[20:])
    assert len(falso.de_tipo("valor")) == 20


# ============================================================ los topes

def test_tope_de_mensajes_por_ronda(correo, falso, monkeypatch, reloj) -> None:
    monkeypatch.setattr(traer, "MENSAJES_RONDA", 2)
    falso.max_pagina = 2
    for numero in range(5):
        falso.llega(_otro("sin_adjuntos", numero))
    assert [correo.ronda().mensajes for _ in range(4)] == [2, 2, 1, 0]
    assert len(correo.llegadas()) == 5


def test_tope_de_paginas_por_ronda(correo, falso, monkeypatch, reloj) -> None:
    """Una delta que vuelve a empezar da paginas de lo ya visto (que no cuenta como mensaje):
    tambien se para tras PAGINAS_RONDA paginas, y la ronda siguiente sigue donde quedo."""
    for numero in range(3):
        falso.llega(_otro("sin_adjuntos", numero))
    assert correo.ronda().mensajes == 3
    monkeypatch.setattr(traer, "PAGINAS_RONDA", 2)
    falso.max_pagina = 1
    falso.fallar("delta", 410)
    reloj.avanzar(minutes=5)
    antes = len(falso.de_tipo("delta"))
    assert correo.ronda().mensajes == 0
    assert len(falso.de_tipo("delta")) - antes == 3        # el 410 y dos paginas
    reloj.avanzar(minutes=5)
    antes = len(falso.de_tipo("delta"))
    assert correo.ronda().mensajes == 0
    # Sigue en la tercera (ultima) pagina y, en la misma ronda, la delta de "no deseado".
    assert len(falso.de_tipo("delta")) - antes == 2
    assert "$deltatoken=" in correo.json("delta-bandeja.json")["enlace"]


def test_tope_de_bytes_por_ronda(correo, falso, monkeypatch, reloj) -> None:
    monkeypatch.setattr(traer, "BYTES_RONDA", 300 * 1024)
    lista = fixture("adjuntos.json")["factura"]
    for numero in range(4):
        falso.llega(_otro("factura", numero), "inbox", lista,
                    {lista[0]["id"]: pdf(f"n{numero}", 200 * 1024)})
    primera = correo.ronda()
    assert (primera.codigo, primera.mensajes, primera.pdf_nuevos, primera.pendientes) == (
        None, 2, 2, 1)
    reloj.avanzar(minutes=5)
    segunda = correo.ronda()          # el pendiente primero, despues lo que sigue
    assert (segunda.mensajes, segunda.pdf_nuevos, segunda.pendientes) == (2, 2, 0)
    assert len(correo.llegadas()) == 4 and len(falso.de_tipo("valor")) == 4


def test_tope_del_dia_retiene_hasta_manana_sin_pedir_nada(correo, falso, reloj) -> None:
    correo.fijar(pdf_dia=2)
    lista = fixture("adjuntos.json")["factura"]
    for numero in range(4):
        falso.llega(_otro("factura", numero), "inbox", lista,
                    {lista[0]["id"]: pdf(f"n{numero}")})
    primera = correo.ronda()
    manana = datetime(2026, 11, 24, 23, 0, tzinfo=timezone.utc)    # 00:00 en Amsterdam
    assert (primera.codigo, primera.pdf_nuevos, primera.retenido_hasta) == (None, 2, manana)
    assert correo.estado_json()["retenido_hasta"] == "2026-11-24T23:00:00Z"
    antes = len(falso.peticiones)
    reloj.avanzar(hours=2)
    segunda = correo.ronda()
    assert (segunda.codigo, segunda.retenido_hasta) == (None, manana)
    assert len(falso.peticiones) == antes            # ni el token
    estado = correo.estado_json()
    assert estado["ronda"]["resultado"] == "bien" and estado["hoy"]["pdf"] == 2
    assert estado["ultima_consulta"] == "2026-11-24T10:00:00Z"
    reloj.instante = manana + timedelta(minutes=1)
    tercera = correo.ronda()
    # El pendiente primero y lo que seguia: otros dos, el tope de hoy, que vuelve a retener.
    assert (tercera.pdf_nuevos, tercera.retenido_hasta) == (2, manana + timedelta(days=1))
    assert len(correo.llegadas()) == 4 and correo.estado_json()["hoy"] == {
        "fecha": "2026-11-25", "mensajes": 2, "pdf": 2, "bytes": 2 * len(pdf("n0"))}


def test_tope_de_mib_al_dia(correo, falso) -> None:
    correo.fijar(mib_dia=1)
    lista = fixture("adjuntos.json")["factura"]
    for numero in range(3):
        falso.llega(_otro("factura", numero), "inbox", lista,
                    {lista[0]["id"]: pdf(f"n{numero}", 700 * 1024)})
    resultado = correo.ronda()
    assert (resultado.pdf_nuevos, resultado.pendientes) == (2, 1)
    assert resultado.retenido_hasta is not None


def test_la_bandeja_llena_da_disco(correo, falso, monkeypatch) -> None:
    monkeypatch.setattr(traer, "MAX_BANDEJA", 10)
    (correo.entrada / "pdf").mkdir()
    (correo.entrada / "pdf" / ("0" * 64 + ".pdf")).write_bytes(b"%PDF-" + b"0" * 20)
    _con_adjuntos(falso, "factura")
    resultado = correo.ronda()
    assert resultado.codigo == "disco" and falso.peticiones == []
    assert correo.estado_json()["ronda"]["error_codigo"] == "disco"


def test_aviso_de_volumen(correo, falso, monkeypatch) -> None:
    monkeypatch.setattr(traer, "AVISO_VOLUMEN", 2)
    for numero in range(3):
        falso.llega(_otro("sin_adjuntos", numero))
    correo.ronda()
    assert correo.estado_json()["aviso_volumen"] is True


# ============================================================ cada mensaje con su limite

def test_el_mensaje_raro_entre_dos_buenos(correo, falso, reloj) -> None:
    factura = _con_adjuntos(falso, "factura")
    raro = _con_adjuntos(falso, "raro")
    sin = _con_adjuntos(falso, "sin_adjuntos")
    falso.llega(mensajes()["sin_id"])
    clave_raro = bandeja.clave(raro["id"], "bandeja")
    for intento in (1, 2, 3):
        resultado = correo.ronda()
        assert (resultado.codigo, resultado.fallidos) == (None, 1)
        assert set(correo.llegadas()) == ({f"{bandeja.clave(m['id'], 'bandeja')}.json"
                                           for m in (factura, sin)} if intento == 1 else set())
        assert correo.json("intentos.json")["mensajes"][clave_raro]["n"] == intento
        # La pagina no se termino: no hay enlace guardado; lo bueno no se vuelve a traer
        # aunque `orden` ya se lo haya llevado de la bandeja (vistos.json).
        assert not (correo.estado / "delta-bandeja.json").exists()
        correo.registrar()
        reloj.avanzar(minutes=5)
    assert len(falso.de_tipo("valor")) == 1
    resultado = correo.ronda()
    assert resultado.fallidos == 0
    assert list(correo.llegadas()) == [f"{clave_raro}.json"]
    llegada = correo.llegada(raro)
    assert llegada["recibido_en"] == bandeja.SIN_FECHA      # antes de 2000: no se sabe
    assert [(a["nombre"], a["resultado"], a["detalle"]) for a in llegada["adjuntos"]] == [
        ("raro.pdf", "error", "no se ha podido procesar el mensaje")]
    assert correo.json("intentos.json")["mensajes"] == {}
    assert graph.enlace_valido(correo.json("delta-bandeja.json")["enlace"])
    assert len(json.loads((correo.estado / "vistos.json").read_text())["claves"]) == 3
    # El que no tiene id no tiene llegada.


def test_un_corte_a_mitad_de_un_mensaje_cuenta_su_intento(correo, falso, reloj) -> None:
    factura = _con_adjuntos(falso, "factura")
    clave = bandeja.clave(factura["id"], "bandeja")
    falso.fallar("valor", excepcion=Corte(), veces=3)
    for intento in (1, 2, 3):
        with pytest.raises(Corte):
            correo.ronda()
        assert correo.json("intentos.json")["mensajes"][clave]["n"] == intento
        assert correo.llegadas() == {} and not (correo.estado / "estado.json").exists()
        reloj.avanzar(minutes=5)
    correo.ronda()
    assert [a["resultado"] for a in correo.llegada(factura)["adjuntos"]] == ["error"]
    assert correo.parciales() == [] and correo.pdfs() == {}


def test_un_corte_y_despues_bien_borra_el_contador(correo, falso, reloj) -> None:
    factura = _con_adjuntos(falso, "factura")
    falso.fallar("valor", excepcion=Corte())
    with pytest.raises(Corte):
        correo.ronda()
    reloj.avanzar(minutes=5)
    assert correo.ronda().mensajes == 1
    assert correo.json("intentos.json")["mensajes"] == {}
    assert [a["resultado"] for a in correo.llegada(factura)["adjuntos"]] == ["pdf"]


def test_sin_red_no_cuenta_contra_el_mensaje(correo, falso, reloj) -> None:
    factura = _con_adjuntos(falso, "factura")
    falso.fallar("adjuntos", excepcion=httpx2.ConnectError("sin red"), veces=5)
    for _ in range(5):
        assert correo.ronda().codigo == "sin_conexion"
        reloj.avanzar(minutes=5)
    assert correo.json("intentos.json")["mensajes"] == {}
    assert correo.ronda().mensajes == 1
    assert correo.estado_json()["ronda"]["error_codigo"] is None
    assert [a["resultado"] for a in correo.llegada(factura)["adjuntos"]] == ["pdf"]


def test_una_lista_de_adjuntos_de_mas_de_4_mib_es_fallo_del_mensaje(correo, falso,
                                                                     reloj) -> None:
    lista = fixture("adjuntos.json")["factura"]
    grande = _otro("factura", 7)
    falso.llega(grande, "inbox", lista, {lista[0]["id"]: pdf("g", 5 * 1024 * 1024)})
    falso.contenido_en_la_lista = True
    for _ in range(3):
        assert correo.ronda().fallidos == 1
        reloj.avanzar(minutes=5)
    falso.contenido_en_la_lista = False
    correo.ronda()
    assert [a["resultado"] for a in correo.llegada(grande)["adjuntos"]] == ["error"]


# ============================================================ pendientes 24 horas

def test_un_adjunto_que_no_se_pudo_bajar_espera_24_horas(correo, falso, reloj) -> None:
    factura = _con_adjuntos(falso, "factura")
    clave = bandeja.clave(factura["id"], "bandeja")
    falso.fallar("valor", 500, veces=100)
    primera = correo.ronda()
    assert (primera.codigo, primera.mensajes, primera.pendientes) == (None, 0, 1)
    assert correo.llegadas() == {} and clave in correo.json("pendientes.json")["mensajes"]
    assert graph.enlace_valido(correo.json("delta-bandeja.json")["enlace"])
    reloj.avanzar(minutes=10)
    correo.ronda()
    assert len(falso.de_tipo("valor")) == 1                 # como mucho cada 30 minutos
    reloj.avanzar(minutes=25)
    correo.ronda()
    assert len(falso.de_tipo("valor")) == 2
    reloj.instante = AHORA + timedelta(hours=24)
    correo.ronda()
    [adjunto] = correo.llegada(factura)["adjuntos"]
    assert (adjunto["resultado"], adjunto["detalle"]) == (
        "error", "no se ha podido traer en 24 horas")
    assert correo.json("pendientes.json")["mensajes"] == {}


def test_un_pendiente_que_luego_se_baja(correo, falso, reloj) -> None:
    factura = _con_adjuntos(falso, "factura")
    falso.fallar("valor", 404, fixture("error-no-existe.json"))
    correo.ronda()
    reloj.avanzar(minutes=31)
    assert correo.ronda().mensajes == 1
    assert [a["resultado"] for a in correo.llegada(factura)["adjuntos"]] == ["pdf"]


def test_sin_red_al_bajar_queda_pendiente_y_la_ronda_para(correo, falso, reloj) -> None:
    factura = _con_adjuntos(falso, "factura")
    _con_adjuntos(falso, "sin_adjuntos")
    falso.fallar("valor", excepcion=httpx2.ReadError("corte"))
    resultado = correo.ronda()
    assert (resultado.codigo, resultado.pendientes) == ("sin_conexion", 1)
    assert correo.llegadas() == {} and correo.json("intentos.json")["mensajes"] == {}
    reloj.avanzar(minutes=31)
    assert correo.ronda().mensajes == 2
    assert [a["resultado"] for a in correo.llegada(factura)["adjuntos"]] == ["pdf"]


# ============================================================ no deseado

def test_no_deseado_sin_bajar_nada_y_despues_en_la_bandeja(correo, falso, reloj) -> None:
    spam = _con_adjuntos(falso, "spam", carpeta="junkemail")
    correo.ronda()
    assert [a["resultado"] for a in correo.llegada(spam, "no_deseado")["adjuntos"]] == [
        "no_deseado"]
    assert falso.de_tipo("valor") == []
    # Una persona lo pasa a la bandeja ("No es correo no deseado"): el mismo id inmutable,
    # otra llegada, que si se trae.
    falso.carpetas["junkemail"].remove(next(m for m in falso.carpetas["junkemail"]
                                            if m["id"] == spam["id"]))
    falso.carpetas["junkemail"].append({"id": spam["id"], "@removed": {"reason": "deleted"}})
    falso.carpetas["inbox"].append(dict(spam))
    reloj.avanzar(minutes=5)
    assert correo.ronda().pdf_nuevos == 1
    assert [a["resultado"] for a in correo.llegada(spam)["adjuntos"]] == ["pdf"]
    assert len(correo.llegadas()) == 2


# ============================================================ comprobar

def test_comprobar_cuando_toca(correo, falso, reloj) -> None:
    correo.ronda()
    assert len(falso.de_tipo("control")) == 1
    reloj.avanzar(hours=23)
    correo.ronda()
    assert len(falso.de_tipo("control")) == 1
    correo.ronda(comprobar=True)
    assert len(falso.de_tipo("control")) == 2
    reloj.avanzar(hours=24, minutes=1)
    correo.ronda()
    assert len(falso.de_tipo("control")) == 3


def test_tras_un_fallo_de_la_credencial_se_comprueba_otra_vez(correo, falso, reloj) -> None:
    correo.ronda()
    reloj.avanzar(minutes=5)
    falso.fallar("token", 401, fixture("token-invalid_client.json"))
    assert correo.ronda().codigo == "credencial"
    assert len(falso.de_tipo("control")) == 1
    reloj.avanzar(minutes=5)
    assert correo.ronda().codigo is None
    assert len(falso.de_tipo("control")) == 2


def test_una_comprobacion_que_falla_no_trae_nada_y_se_repite(correo, falso, reloj) -> None:
    _con_adjuntos(falso, "factura")
    falso.estado_control = 200
    resultado = correo.ronda()
    assert resultado.codigo == "alcance" and falso.de_tipo("delta") == []
    assert correo.estado_json()["alcance"]["bien"] is False
    assert correo.estado_json()["alcance"]["motivo_codigo"] == "alcance"
    falso.estado_control = 403
    reloj.avanzar(minutes=5)
    assert correo.ronda().mensajes == 1
    assert len(falso.de_tipo("control")) == 2


def test_sin_red_al_comprobar_no_cambia_el_alcance(correo, falso, reloj) -> None:
    correo.ronda()
    alcance = correo.estado_json()["alcance"]
    reloj.avanzar(hours=25)
    falso.fallar("token", excepcion=httpx2.ConnectError("sin red"))
    assert correo.ronda().codigo == "sin_conexion"
    assert correo.estado_json()["alcance"] == alcance


def test_correo_comprobar_solo(correo, falso) -> None:
    resultado = correo.comprobar()
    assert resultado.codigo is None and resultado.alcance == graph.Alcance(True)
    assert {p.tipo for p in falso.peticiones} == {"token", "buzon", "control", "usuarios"}
    estado = correo.estado_json()
    assert estado["alcance"]["bien"] is True and estado["ronda"]["mensajes"] == 0
    falso.estado_control = 404
    assert correo.comprobar().codigo == "control_no_existe"
    assert correo.estado_json()["ronda"]["error_codigo"] == "control_no_existe"
    assert not (correo.entrada / "llegadas").exists()


# ============================================================ sin configurar

def test_sin_ajustes_o_sin_certificado(correo, falso, tmp_path) -> None:
    correo.ajustes.unlink()
    assert correo.ronda().codigo == "sin_configurar"
    assert correo.estado_json()["ronda"]["error_codigo"] == "sin_configurar"
    correo.fijar()
    correo.pem = tmp_path / "no-esta.pem"
    assert correo.ronda().codigo == "sin_configurar"
    malo = tmp_path / "malo.pem"
    malo.write_text("-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n")
    correo.pem = malo
    resultado = correo.ronda()
    assert resultado.codigo == "credencial" and falso.peticiones == []


def test_un_certificado_caducado_da_credencial(correo, falso, reloj) -> None:
    reloj.instante = AHORA + timedelta(days=900)
    assert correo.ronda().codigo == "credencial"
    assert falso.peticiones == []


# ============================================================ la delta

def test_un_delta_caducado_empieza_de_nuevo_tres_dias_antes(correo, falso, reloj) -> None:
    _con_adjuntos(falso, "factura")
    correo.ronda()
    reloj.avanzar(days=1)
    falso.fallar("delta", 410, cabeceras={"Location": "https://graph.microsoft.com/v1.0/"})
    _con_adjuntos(falso, "sin_adjuntos")
    resultado = correo.ronda()
    assert (resultado.codigo, resultado.mensajes) == (None, 1)     # la factura, ya vista
    primera = falso.de_tipo("delta")[-2]
    assert primera.parametros["$filter"] == ["receivedDateTime ge 2026-11-21T10:00:00Z"]
    assert correo.estado_json()["delta_reiniciado_en"] == "2026-11-25T10:00:00Z"


def test_un_enlace_guardado_que_no_vale_no_se_sigue(correo, falso) -> None:
    (correo.estado / "delta-bandeja.json").write_text(json.dumps(
        {"version": 1, "enlace": "https://evil.example/v1.0/users/x/messages/delta",
         "al_dia_en": None}))
    _con_adjuntos(falso, "sin_adjuntos")
    assert correo.ronda().mensajes == 1
    assert all(p.host == "graph.microsoft.com" or p.tipo == "token" for p in falso.peticiones)
    assert correo.estado_json()["delta_reiniciado_en"] is not None


def test_un_enlace_malo_de_graph_para_la_ronda(correo, falso) -> None:
    falso.max_pagina = 1
    falso.siguiente_malo = "https://graph.microsoft.com:8443/v1.0/users/x/messages/delta"
    for numero in range(2):
        falso.llega(_otro("sin_adjuntos", numero))
    resultado = correo.ronda()
    assert resultado.codigo == "interno"
    assert not (correo.estado / "delta-bandeja.json").exists()


# ============================================================ escribir de una vez

def test_lo_que_se_escribe_es_entero_o_nada(correo, falso, monkeypatch) -> None:
    _con_adjuntos(falso, "sin_adjuntos")
    real = os.replace

    def falla(origen, destino):
        if "llegadas" in str(destino):
            raise OSError(28, "No space left on device")
        return real(origen, destino)

    monkeypatch.setattr(os, "replace", falla)
    resultado = correo.ronda()
    assert resultado.codigo == "disco"
    assert correo.llegadas() == {} and correo.parciales() == []
    monkeypatch.setattr(os, "replace", real)
    assert correo.ronda().mensajes == 1


def test_lo_que_dejo_una_ronda_muerta_se_limpia(correo, falso, reloj) -> None:
    (correo.entrada / ".parcial-abc").write_bytes(b"%PDF-a medias")
    (correo.estado / ".parcial-def").write_bytes(b"{")
    (correo.entrada / "llegadas").mkdir()
    viejo = correo.entrada / "llegadas" / ("a" * 64 + ".json")
    viejo.write_text("{}")
    hace = (AHORA - timedelta(days=46)).timestamp()
    os.utime(viejo, (hace, hace))
    correo.ronda()
    assert correo.parciales() == [] and not viejo.exists()


# ============================================================ el cerrojo

def test_un_cerrojo_que_se_quedo_en_disco_no_bloquea(correo, falso) -> None:
    (correo.estado / "traer.cerrojo").write_text("de una ronda que murio")
    assert not correo.ronda().ocupado


def test_un_cerrojo_tomado_por_otro_proceso_da_ocupado(correo, falso) -> None:
    codigo = ("import fcntl, os, sys; f = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT); "
              "fcntl.flock(f, fcntl.LOCK_EX); print('tomado', flush=True); sys.stdin.read()")
    otro = subprocess.Popen([sys.executable, "-c", codigo, str(correo.estado / "traer.cerrojo")],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert otro.stdout.readline().strip() == "tomado"
        assert correo.ronda().ocupado and correo.comprobar().ocupado
        # La CLI: una ronda ocupada no es un error; una comprobacion que no se hace, si.
        assert cli.main(_argumentos(correo)) == 0
        assert cli.main(_argumentos(correo, "comprobar")) == 1
        assert falso.peticiones == [] and not (correo.estado / "estado.json").exists()
    finally:
        otro.communicate("", timeout=10)
    assert not correo.ronda().ocupado


# ============================================================ la CLI, sin base y sin la API

def _argumentos(correo: Correo, que: str = "traer") -> list[str]:
    return ["correo", que, "--ajustes", str(correo.ajustes), "--certificado-fichero",
            str(correo.pem), "--estado", str(correo.estado)] + (
        ["--entrada", str(correo.entrada)] if que == "traer" else [])


@pytest.fixture
def por_el_falso(monkeypatch, falso):
    """La CLI crea su cliente sin transporte (sale por HTTPS_PROXY): aqui, al falso."""
    original = httpx2.Client

    class AlFalso(original):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = falso.transporte
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(graph.httpx2, "Client", AlFalso)


def test_la_cli_dice_lo_que_paso_sin_datos_del_buzon(correo, falso, por_el_falso, capsys,
                                                     monkeypatch) -> None:
    # El reloj de la ronda, el del falso (la CLI usa el del sistema).
    monkeypatch.setattr(traer, "traer", _con_reloj(traer.traer))
    monkeypatch.setattr(traer, "comprobar", _con_reloj(traer.comprobar))
    _con_adjuntos(falso, "factura")
    assert cli.main(_argumentos(correo)) == 0
    salida = capsys.readouterr()
    assert "ronda bien: 1 mensajes, 1 PDF nuevos" in salida.out
    texto = salida.out + salida.err
    for privado in (BUZON, "proveedor.example.test", "Factuur", *falso.tokens, INQUILINO):
        assert privado not in texto
    assert cli.main(_argumentos(correo, "comprobar")) == 0
    falso.estado_control = 200
    assert cli.main(_argumentos(correo, "comprobar")) == cli.CORREO_FALLO
    assert "alcance" in capsys.readouterr().err
    correo.ajustes.unlink()
    assert cli.main(_argumentos(correo)) == cli.CORREO_SIN_CONFIGURAR


def _con_reloj(funcion):
    def llamar(**kwargs):
        kwargs.setdefault("ahora", lambda: AHORA)
        kwargs.setdefault("dormir", lambda _s: None)
        return funcion(**kwargs)
    return llamar


def test_en_la_nativa_no_hay_ronda(correo, capsys, monkeypatch) -> None:
    from bms_agent import nativo

    monkeypatch.setattr(nativo, "instalacion_actual", lambda: object())
    assert cli.main(_argumentos(correo)) == 2
    assert "solo de la variante Docker" in capsys.readouterr().err


SIN_BASE_NI_API = r'''
import json, sqlite3, sys
from datetime import date, datetime, timezone
sys.path[:0] = [sys.argv[1], sys.argv[2]]
abiertas = []
def no(*a, **k):
    abiertas.append(a)
    raise AssertionError("correo traer abre la base")
sqlite3.connect = no
import httpx2
from graph_falso import GraphFalso, fixture, mensajes, pdf
ahora = datetime(2026, 11, 24, 10, 0, tzinfo=timezone.utc)
falso = GraphFalso(certificado=open(sys.argv[4], "rb").read(), inquilino=sys.argv[5],
                   aplicacion=sys.argv[6], buzon=sys.argv[7], control=sys.argv[8],
                   ahora=lambda: ahora)
lista = fixture("adjuntos.json")["factura"]
falso.llega(mensajes()["factura"], "inbox", lista, {lista[0]["id"]: pdf("x")})
original = httpx2.Client
class AlFalso(original):
    def __init__(self, *a, **k):
        k["transport"] = falso.transporte
        super().__init__(*a, **k)
httpx2.Client = AlFalso
from bms_agent import reloj
reloj.RELOJ_SISTEMA.ahora = lambda: ahora
from bms_agent import cli
argumentos = json.loads(sys.argv[3])
codigo = cli.main(argumentos)
falso.comprobar()
print(json.dumps({"codigo": codigo, "abiertas": len(abiertas),
                  "anthropic": sorted(m for m in sys.modules if m.split(".")[0] == "anthropic")}))
'''


def test_correo_traer_no_abre_la_base_ni_importa_la_api(correo, certificado_de_prueba) -> None:
    """La CLI de verdad (`python -m bms_agent.cli correo traer`, la del contenedor) en otro
    proceso: con sqlite3.connect que falla y sin que se cargue anthropic."""
    proceso = subprocess.run(
        [sys.executable, "-c", SIN_BASE_NI_API, str(SRC.parent), str(RAIZ / "tests"),
         json.dumps(_argumentos(correo)), str(certificado_de_prueba[1]), INQUILINO, APLICACION,
         BUZON, CONTROL], capture_output=True, text=True, timeout=120)
    assert proceso.returncode == 0, proceso.stderr
    resultado = json.loads(proceso.stdout.strip().splitlines()[-1])
    assert resultado == {"codigo": 0, "abiertas": 0, "anthropic": []}
    assert len(correo.llegadas()) == 1 and len(correo.pdfs()) == 1


def test_el_correo_no_ve_la_base(tmp_path) -> None:
    """Los modulos del correo que corren en su contenedor no traen (tampoco por otro modulo) ni
    la base, ni la lectura, ni el SDK de la API (§7.2). socket y ssl si: httpx2 sale a Microsoft
    por su salida, y cryptography.x509 importa email.utils (desviaciones, paso 7)."""
    codigo = ("import sys; sys.path.insert(0, sys.argv[1]); "
              "import bms_agent.correo.traer, bms_agent.correo.graph, bms_agent.correo.bandeja; "
              "print('\\n'.join(sorted(sys.modules)))")
    proceso = subprocess.run([sys.executable, "-c", codigo, str(SRC.parent)],
                             capture_output=True, text=True, timeout=60)
    assert proceso.returncode == 0, proceso.stderr
    cargados = set(proceso.stdout.split())
    # (urllib.request y http.client los carga httpx2 para leer HTTPS_PROXY: no salen por ahi;
    # la guarda de test_alcance_v1 mira que nuestro codigo no los use.)
    prohibidos = {"sqlite3", "bms_agent.almacen", "bms_agent.lectura", "bms_agent.extract",
                  "bms_agent.ingesta", "bms_agent.serve", "bms_agent.cli", "anthropic", "httpx",
                  "requests", "urllib3"}
    assert cargados & prohibidos == set()
    assert {"httpx2", "bms_agent.correo.certificado"} <= cargados


def test_el_correo_no_lee_variables_de_entorno_ni_escribe_registros() -> None:
    for modulo in ("traer.py", "graph.py", "bandeja.py"):
        texto = (SRC / "correo" / modulo).read_text(encoding="utf-8")
        assert "environ" not in texto and "getenv" not in texto
        assert "print(" not in texto and ".info(" not in texto and ".debug(" not in texto
