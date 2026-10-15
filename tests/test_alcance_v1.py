"""La suite de alcance de V1 (§11, corre desde el paso 4): lo que V1 no hace.

- ninguna orden ni ningun estado crea o prepara una factura, paga, aprueba un
  pago o presenta el IVA;
- no hay generador SEPA ni pain.001, ni credenciales ni claves de banco;
- ninguna entidad modela pagos a plazos;
- lo que no esta en euros queda siempre Bloqueado;
- ningun camino lleva de una extraccion a cuenta_bancaria (grafo de imports
  y una propiedad sobre la base);
- las peticiones de extraccion no llevan herramientas.

Las comprobaciones miran el codigo y la base enteros, no una lista de
ficheros: un modulo nuevo que se salga del alcance tiene que hacer fallar
esto sin que nadie se acuerde de anadirlo aqui.
"""

from __future__ import annotations

import ast
import json
import random
import re
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from conftest import RAIZ, factura_de, persona
from test_hallazgos import _cargar, _de_factura, _registro
from test_servicios import CASOS, MOTIVO, _ids, escenario  # noqa: F401 (fixture)

from bms_agent import campos, consultas, extract, hallazgos, prioridad, servicios
from bms_agent.campos import CampoNoEditable, Persona
from bms_agent.documents import SourceDocument
from bms_agent.dominio import Permiso
from bms_agent.permisos import PermisoDenegado, usuario_por_nombre
from bms_agent.reglas import catalogo

SRC = RAIZ / "src" / "bms_agent"
PAQUETE = "bms_agent"


def _modulos() -> dict[str, Path]:
    """Cada modulo del paquete por su nombre con puntos."""
    salida = {}
    for ruta in sorted(SRC.rglob("*.py")):
        partes = list(ruta.relative_to(SRC.parent).with_suffix("").parts)
        if partes[-1] == "__init__":
            partes.pop()
        salida[".".join(partes)] = ruta
    return salida


MODULOS = _modulos()


def _ficheros_de_texto() -> list[Path]:
    """Lo que se distribuye o configura: codigo, SQL, YAML, scripts y el pyproject."""
    ficheros = [p for p in SRC.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    ficheros += [p for p in (RAIZ / "config").rglob("*") if p.is_file()]
    ficheros += [p for p in (RAIZ / "scripts").rglob("*.py")]
    ficheros.append(RAIZ / "pyproject.toml")
    return ficheros


def _tokens(nombre: str) -> set[str]:
    return {t for t in re.split(r"[_\-.\s]+", nombre.lower()) if t}


def _esquema(conn) -> dict[str, list[str]]:
    tablas = [f[0] for f in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    return {t: [c[1] for c in conn.execute(f"PRAGMA table_info({t})")] for t in tablas}


# ============================================================ ni facturar, ni pagar, ni presentar

# Verbos de lo que V1 no hace. Marcar pagada lo que ya se pago fuera (§6,
# paso 7) y anotar que el IVA se presento (§5, paso 11) si caben: son
# constancias de algo que hizo una persona, no ordenes al sistema.
ORDENES_PROHIBIDAS = re.compile(
    r"pagar|aprob|borrador|emitir|facturar|crear_factura|anadir_factura|presentar|declarar|"
    r"transfer|sepa|remesa|ordenar_pago|enviar")
ESTADOS_PROHIBIDOS = re.compile(
    r"aprob|approv|borrador|draft|por_pagar|a_pagar|pago_ordenado|orden_pago|en_pago|"
    r"programad|transferid|enviad|remesa|sepa")


def test_ninguna_orden_ni_permiso_se_llama_como_lo_que_v1_no_hace(capsys) -> None:
    assert not [n for n in servicios.ACCIONES if ORDENES_PROHIBIDAS.search(n)]
    assert not [p for p in Permiso.valores() if ORDENES_PROHIBIDAS.search(p)]
    # Ni un subcomando de la CLI: las ordenes de persona salen de la misma tabla.
    from bms_agent import cli

    with pytest.raises(SystemExit):
        cli.main(["--help"])
    [subcomandos] = re.findall(r"\{([a-z0-9_,\-]+)\}", capsys.readouterr().out)[:1]
    assert "recalcular" in subcomandos.split(",")
    assert not [c for c in subcomandos.split(",") if ORDENES_PROHIBIDAS.search(c)]


def test_ningun_estado_dice_aprobado_ni_borrador_ni_pago_en_marcha(almacen) -> None:
    import enum

    from bms_agent import dominio

    valores: set[str] = set()
    for objeto in vars(dominio).values():
        if isinstance(objeto, type) and issubclass(objeto, enum.Enum):
            valores |= {str(m.value) for m in objeto}
    conn = almacen.conn
    for (sql,) in conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND sql "
                               "IS NOT NULL"):
        valores |= set(re.findall(r"'([a-z_]+)'", sql))
    assert "pagada" in valores                      # se mira lo que hay, no una lista vacia
    assert not sorted(v for v in valores if ESTADOS_PROHIBIDOS.search(v))
    # Revisar no es aprobar: los resultados de una revision y lo que dice el sistema.
    assert set(dominio.ResultadoRevision.valores()) == {"revisada", "devuelta"}


def test_nadie_da_de_alta_una_factura_a_mano(almacen) -> None:
    conn = almacen.conn
    ana = persona(conn, "Ana", "administrador")
    assert campos.PERMISO_ALTA["factura"] is None
    with pytest.raises(PermisoDenegado, match="nadie puede"):
        campos.crear(conn, "factura", {"numero": "BORRADOR-1"}, Persona(ana, MOTIVO))
    assert conn.execute("SELECT count(*) FROM factura").fetchone()[0] == 0


def _iban_doc(conn) -> dict[str, str]:
    return {re.sub(r"\s", "", f[0]).upper(): f[0] for f in conn.execute(
        "SELECT iban_doc FROM factura WHERE iban_doc IS NOT NULL")}


@pytest.mark.parametrize("caso, orden, permiso, datos, preparar", CASOS,
                         ids=[c[0] for c in CASOS])
def test_ninguna_orden_crea_facturas_ni_paga_ni_presenta(escenario, caso, orden, permiso, datos,
                                                        preparar) -> None:
    """Cada orden que existe, con todos los permisos: las facturas son las mismas."""
    conn = escenario.conn
    ana = usuario_por_nombre(conn, "Ana")
    if preparar is not None:
        preparar(conn, ana)
    ids = _ids(conn)
    facturas = [tuple(f) for f in conn.execute(
        "SELECT id, origen, sentido, numero FROM factura ORDER BY id")]
    ultimo = conn.execute("SELECT max(id) FROM evento").fetchone()[0]
    servicios.ejecutar(conn, orden, datos(conn, ids), usuario_id=ana)
    assert [tuple(f) for f in conn.execute(
        "SELECT id, origen, sentido, numero FROM factura ORDER BY id")] == facturas
    tipos = {f[0] for f in conn.execute("SELECT tipo FROM evento WHERE id > ?", (ultimo,))}
    assert tipos or orden == "recalcular"          # recalcular sin cambios no deja evento
    assert not [t for t in tipos if ORDENES_PROHIBIDAS.search(t) or ESTADOS_PROHIBIDOS.search(t)]
    assert _fuera_de_su_sitio(conn, _iban_doc(conn)) == []


# ============================================================ ni SEPA, ni banco

# "sepa" en minusculas es tambien el verbo ("quien mira sepa por que"): en
# minusculas solo cuenta pegado a un identificador.
SEPA = re.compile(r"\bSEPA\b|\bsepa_|_sepa\b|(?i:pain\.0\d\d|CstmrCdtTrfInitn|CdtTrfTxInf|PmtInf|"
                  r"\bebics\b|\bpsd2\b|open\s?banking)")
BANCO = {"bank", "banco", "bancaria", "bancario", "ebics", "psd2", "sepa", "swift", "bic",
         "openbanking", "iban"}
CREDENCIAL = {"password", "passwd", "contrasena", "clave", "secret", "secreto", "token",
              "credencial", "credenciales", "api", "apikey", "pin", "certificado", "cert",
              "usuario", "user"}
RED_SALIENTE = {"urllib.request", "http.client", "requests", "httpx", "aiohttp", "smtplib",
                "ftplib", "paramiko", "socket", "ssl", "imaplib", "poplib"}


def test_no_hay_generador_sepa_ni_pain_001() -> None:
    encontrados = []
    for ruta in _ficheros_de_texto():
        try:
            texto = ruta.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        encontrados += [f"{ruta.relative_to(RAIZ)}: {m.group(0)}" for m in SEPA.finditer(texto)]
    assert encontrados == []


def _variables_de_entorno() -> dict[str, set[str]]:
    """Las variables que lee cada modulo: os.environ[...], .get(...) y os.getenv(...)."""
    salida: dict[str, set[str]] = {}
    for nombre, ruta in MODULOS.items():
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        constantes = {n.targets[0].id: n.value.value for n in arbol.body
                      if isinstance(n, ast.Assign) and len(n.targets) == 1
                      and isinstance(n.targets[0], ast.Name)
                      and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)}

        def valor(nodo):
            if isinstance(nodo, ast.Constant):
                return nodo.value
            if isinstance(nodo, ast.Name):
                return constantes.get(nodo.id, f"?{nodo.id}")
            return "?"

        for nodo in ast.walk(arbol):
            leida = None
            if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
                destino = ast.unparse(nodo.func.value)
                if (nodo.func.attr == "get" and destino.endswith("environ")) or (
                        nodo.func.attr == "getenv"):
                    leida = valor(nodo.args[0]) if nodo.args else "?"
            elif isinstance(nodo, ast.Subscript) and ast.unparse(nodo.value).endswith("environ"):
                leida = valor(nodo.slice)
            if leida is not None:
                salida.setdefault(nombre, set()).add(str(leida))
    return salida


def test_no_hay_credenciales_ni_claves_de_banco() -> None:
    variables = set().union(*_variables_de_entorno().values())
    # Las que hay, todas resueltas: una nueva tiene que pasar por aqui.
    assert variables == {"BMS_DB", "BMS_TOKEN", "BMS_EXTRACT_MODEL", "BMS_EXTRACT_MAX_TOKENS"}
    assert not [v for v in variables if _tokens(v) & BANCO]

    def claves(datos, camino=()):
        if isinstance(datos, dict):
            for k, v in datos.items():
                yield (*camino, str(k))
                yield from claves(v, (*camino, str(k)))
        elif isinstance(datos, list):
            for v in datos:
                yield from claves(v, camino)

    for ruta in (RAIZ / "config").glob("*.y*ml"):
        for camino in claves(yaml.safe_load(ruta.read_text(encoding="utf-8"))):
            assert not _tokens(camino[-1]) & (BANCO | CREDENCIAL), (ruta.name, camino)
    # Ni una columna de la configuracion: el contenido de config/ ni el de pyproject.
    assert not SEPA.search((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))


def test_ningun_modulo_habla_con_la_red_salvo_la_extraccion() -> None:
    """Sin cliente de red no hay banco al que conectarse. El de Anthropic solo en la CLI y el
    servidor, y solo para extraer (lo importan dentro de la funcion que extrae)."""
    malos = []
    for nombre, ruta in MODULOS.items():
        for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Import):
                importados = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
                importados = [nodo.module]
            else:
                continue
            for modulo in importados:
                if modulo in RED_SALIENTE or modulo.split(".")[0] in RED_SALIENTE:
                    malos.append((nombre, modulo))
                if modulo.split(".")[0] == "anthropic" and nombre not in (
                        "bms_agent.cli", "bms_agent.serve"):
                    malos.append((nombre, modulo))
    assert malos == []


# ============================================================ sin plazos

PLAZOS = {"plazos", "cuotas", "instalment", "installment", "instalments", "installments",
          "termijn", "termijnen", "aplazamiento", "aplazado", "fraccionamiento", "fraccionado",
          "plan", "calendario", "amortizacion"}


def test_ninguna_entidad_modela_pagos_a_plazos(almacen) -> None:
    conn = almacen.conn
    esquema = _esquema(conn)
    for tabla, columnas in esquema.items():
        assert not _tokens(tabla) & PLAZOS, tabla
        for columna in columnas:
            assert not _tokens(columna) & PLAZOS, f"{tabla}.{columna}"
            assert "pago_parcial" not in columna and "pagos_parciales" not in columna
    # Una factura vence una vez: ninguna tabla guarda varios vencimientos de una factura.
    for tabla, columnas in esquema.items():
        if tabla == "factura" or "factura_id" not in columnas:
            continue
        if any("vencimiento" in c for c in columnas):
            unicos = [conn.execute(f"PRAGMA index_info({i[1]})").fetchall()
                      for i in conn.execute(f"PRAGMA index_list({tabla})") if i[2]]
            pk = [c[1] for c in conn.execute(f"PRAGMA table_info({tabla})") if c[5]]
            assert pk == ["factura_id"] or any(
                [c[2] for c in u] == ["factura_id"] for u in unicos), tabla
    # Ni un estado de pago que no sea los cuatro del §5.
    from bms_agent.dominio import EstadoPago

    assert set(EstadoPago.valores()) == {"pendiente", "vencida", "pagada", "anulada"}


# ============================================================ fuera del euro, Bloqueada

def test_x1_es_un_bloqueo_pegajoso_que_nadie_anula() -> None:
    x1 = catalogo.regla("X1")
    assert (x1.severidad, x1.pegajosa) == ("bloqueo", True)
    assert all(catalogo.nunca_anulable("X1", s) for s in ("entrante", "saliente", None))


MONEDAS = [
    dict(currency_raw="USD"),
    dict(currency_raw="GBP"),
    dict(currency_raw="CHF"),
    dict(currency_raw="PLN"),
    dict(currency_raw=None, total_incl_vat_raw="£ 2.903,79"),
    dict(currency_raw=None, subtotal_excl_vat_raw="$2,400.00"),
]


@pytest.mark.parametrize("cambios", MONEDAS, ids=[str(m) for m in MONEDAS])
def test_lo_que_no_esta_en_euros_queda_bloqueado(almacen, tmp_path, cambios) -> None:
    conn = almacen.conn
    _cargar(almacen, tmp_path / "out", _registro("a", **cambios))
    hallazgos.recalcular(conn)
    f = factura_de(conn, "2026-4471")
    x1 = _de_factura(conn, "X1", f)
    assert (x1["estado"], x1["severidad"], x1["anulable"]) == ("abierto", "bloqueo", 0)
    estado = conn.execute("SELECT * FROM factura_estado WHERE factura_id = ?", (f,)).fetchone()
    assert estado["nivel"] == "bloqueada"
    assert consultas.detalle(conn, f)["etiqueta"] != "Sin objeciones del sistema"
    ana = persona(conn, "Ana", "administrador")
    with pytest.raises(hallazgos.NoAnulable):
        hallazgos.anular(conn, x1["id"], Persona(ana, MOTIVO))
    # Corregir un importe a mano no la mete en euros: sigue bloqueada.
    servicios.ejecutar(conn, "fijar_campo", {
        "tabla": "factura", "fila_id": f, "campo": "total_cent", "valor": "2903.79",
        "rev": conn.execute("SELECT rev FROM factura WHERE id = ?", (f,)).fetchone()[0],
        "motivo": MOTIVO}, usuario_id=ana)
    assert _de_factura(conn, "X1", f)["estado"] == "abierto"
    assert conn.execute("SELECT nivel FROM factura_estado WHERE factura_id = ?",
                        (f,)).fetchone()[0] == "bloqueada"


def test_un_bloqueo_abierto_da_bloqueada_con_cualquier_otra_entrada() -> None:
    """Propiedad sobre prioridad.calcular: ni los puntos, ni la espera, ni una subida a mano,
    ni estar revisada bajan una factura con X1 abierto de Bloqueada."""
    azar = random.Random(20261015)
    hoy = date(2026, 10, 15)
    x1 = prioridad.Hallazgo("X1", "bloqueo", "abierto", "otra", "La factura no está en euros")
    otros = [prioridad.Hallazgo("B4", "bloqueo", "aceptado", "duplicado", "Solapada"),
             prioridad.Hallazgo("D3", "retencion", "abierto", "iva_dura", "IVA"),
             prioridad.Hallazgo("U1", "aviso", "desaparecido", "otra", "Importe alto")]
    for _ in range(500):
        dia = lambda: hoy + timedelta(days=azar.randint(-120, 120))  # noqa: E731
        entradas = prioridad.Entradas(
            sentido=azar.choice(["entrante", "saliente"]),
            vencimiento=azar.choice([None, dia()]), en_juego=azar.random() < 0.8,
            importe_cent=azar.choice([None, azar.randint(-10**7, 10**8)]),
            fecha_factura=azar.choice([None, dia()]),
            hallazgos=tuple([x1] + azar.sample(otros, azar.randint(0, len(otros)))),
            excepcion_abierta=azar.random() < 0.5, revisada=azar.random() < 0.5,
            esperando_a=azar.choice([None, "proveedor", "banco"]),
            fecha_seguimiento=azar.choice([None, dia()]),
            dudosos=azar.randint(0, 3), sin_resolver=azar.randint(0, 3),
            subidas=tuple(prioridad.Subida(azar.choice(["atencion", "urgente"]), MOTIVO,
                                           hasta=azar.choice([None, dia()]))
                          for _ in range(azar.randint(0, 2))))
        resultado = prioridad.calcular(entradas, hoy)
        assert (resultado.nivel, resultado.suelo) == ("bloqueada", "bloqueada"), entradas
        assert "(X1)" in resultado.texto


# ============================================================ de la extraccion, nada a cuenta_bancaria

# Los modulos por los que entra lo que dice un documento.
EXTRACCION = ("bms_agent.extract", "bms_agent.schema", "bms_agent.prompts",
              "bms_agent.documents", "bms_agent.parsing", "bms_agent.cache",
              "bms_agent.ingesta", "bms_agent.importadores.extracciones",
              "bms_agent.almacen.extracciones", "bms_agent.almacen.documentos")
# La infraestructura generica que todas las escrituras comparten. Si algun dia
# registra cuenta_bancaria, la propiedad de abajo exige que sea con permiso de
# persona (confirmar_iban) y que lo automatico no pueda darla de alta.
GENERICOS = ("bms_agent.campos", "bms_agent.almacen", "bms_agent.almacen.evidencia",
             "bms_agent.auditoria", "bms_agent.permisos", "bms_agent.dominio")


def _importa(nombre: str, ruta: Path) -> set[str]:
    paquete = nombre if ruta.name == "__init__.py" else nombre.rsplit(".", 1)[0]
    salida = set()
    for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.Import):
            salida |= {a.name for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level:
                base = paquete.split(".")
                base = base[:len(base) - (nodo.level - 1)]
                raiz = ".".join(base + ([nodo.module] if nodo.module else []))
            else:
                raiz = nodo.module or ""
            salida.add(raiz)
            salida |= {f"{raiz}.{a.name}" for a in nodo.names}
    return {m for m in salida if m in MODULOS}


def _alcanzables(desde: tuple[str, ...]) -> set[str]:
    vistos, pendientes = set(), list(desde)
    while pendientes:
        nombre = pendientes.pop()
        if nombre in vistos:
            continue
        vistos.add(nombre)
        pendientes += sorted(_importa(nombre, MODULOS[nombre]) - vistos)
    return vistos


def _nombra_cuenta_bancaria(ruta: Path) -> bool:
    """Si el codigo (no sus docstrings) nombra la tabla, en SQL o como identificador."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    docstrings = {id(n.value) for n in ast.walk(arbol)
                  if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and (
                id(nodo) not in docstrings and "cuenta_bancaria" in nodo.value):
            return True
        if isinstance(nodo, (ast.Name, ast.Attribute, ast.FunctionDef, ast.alias)):
            texto = getattr(nodo, "id", None) or getattr(nodo, "attr", None) or getattr(
                nodo, "name", "")
            if "cuenta_bancaria" in str(texto):
                return True
    return False


def test_ningun_import_de_la_extraccion_llega_a_cuenta_bancaria() -> None:
    assert set(EXTRACCION) <= set(MODULOS)
    alcanzables = _alcanzables(EXTRACCION)
    assert "bms_agent.campos" in alcanzables           # el grafo se recorre de verdad
    assert not [m for m in sorted(alcanzables - set(GENERICOS))
                if _nombra_cuenta_bancaria(MODULOS[m])]
    # Lo que escribe en cuenta_bancaria (paso 7) no puede importar la extraccion.
    escritores = [m for m, r in MODULOS.items()
                  if m not in GENERICOS and _nombra_cuenta_bancaria(r)]
    for escritor in escritores:
        assert not _alcanzables((escritor,)) & set(EXTRACCION), escritor


def _iban_valido(azar: random.Random) -> str:
    """Un IBAN neerlandes con su digito de control, para que F1 no lo descarte."""
    banco = azar.choice(["ABNA", "INGB", "RABO", "TRIO", "KNAB"])
    cuenta = "".join(azar.choice("0123456789") for _ in range(10))
    numerico = "".join(str(int(c, 36)) for c in f"{banco}{cuenta}NL00")
    control = 98 - int(numerico) % 97
    return f"NL{control:02d}{banco}{cuenta}"


# Donde puede estar lo que imprimio un documento: el propio documento, su
# extraccion, la factura que sale de ella, su procedencia y su auditoria, y lo
# que las reglas dicen de ella (F1 cita el IBAN que no pasa, y la prioridad
# repite esa explicacion). Nunca un maestro ni una cuenta.
SITIO_DEL_DOCUMENTO = {
    ("extraccion", "contenido_json"), ("factura", "iban_doc"), ("factura", "notas_doc"),
    ("procedencia_campo", "valor_actual"), ("procedencia_campo", "valor_original"),
    ("procedencia_campo", "valor_original_crudo"), ("procedencia_campo", "valor_automatico"),
    ("cambio_campo", "valor_anterior"), ("cambio_campo", "valor_nuevo"),
    ("evento", "datos_json"), ("evaluacion", "detalle"), ("evaluacion", "valores_json"),
    ("hallazgo", "valores_json"), ("hallazgo", "detalle"),
    ("factura_estado", "motivos_json"), ("prioridad", "motivos_json"),
}


def _fuera_de_su_sitio(conn, ibans: dict[str, str]) -> list[str]:
    """Las columnas que guardan alguno de estos IBAN fuera del sitio del documento."""
    fuera = []
    for tabla, columnas in _esquema(conn).items():
        for columna in columnas:
            if (tabla, columna) in SITIO_DEL_DOCUMENTO:
                continue
            for limpio in ibans:
                if conn.execute(
                        f"SELECT 1 FROM {tabla} WHERE replace(upper(CAST({columna} AS TEXT)), "
                        "' ', '') LIKE ? LIMIT 1", (f"%{limpio}%",)).fetchone():
                    fuera.append(f"{tabla}.{columna}")
    return fuera


def test_un_iban_de_un_documento_no_sale_nunca_de_su_sitio(almacen, tmp_path) -> None:
    """Propiedad: con IBAN al azar en la cabecera y en las notas (validos y no), tras la
    ingesta, el recalculo y una persona tocando la factura, no hay ninguno en un maestro ni
    en cuenta_bancaria, y ni una persona puede copiar el de la factura a mano."""
    conn = almacen.conn
    azar = random.Random(7)
    registros, ibans = [], {}
    for i in range(6):
        cabecera, inyectado = _iban_valido(azar), _iban_valido(azar)
        if i % 3 == 0:
            cabecera = cabecera[:-1] + str((int(cabecera[-1]) + 1) % 10)   # F1 lo ve
        ibans.update({cabecera: cabecera, inyectado: inyectado})
        registros.append(_registro(
            f"r{i}", iban=" ".join(cabecera[j:j + 4] for j in range(0, len(cabecera), 4)),
            invoice_number=f"2026-90{i}", invoice_date=f"2026-0{i + 1}-01",
            service_period_start=f"2026-0{i + 1}-01", service_period_end=f"2026-0{i + 1}-05",
            document_notes=f"Betaal voortaan op {inyectado} i.p.v. het oude nummer"))
    _cargar(almacen, tmp_path / "out", *registros)
    hallazgos.recalcular(conn)
    assert conn.execute("SELECT count(*) FROM evaluacion WHERE regla = 'F1' AND "
                        "resultado = 'fallo'").fetchone()[0] == 2
    ana = persona(conn, "Ana", "administrador")
    f = factura_de(conn, "2026-900")
    with pytest.raises(CampoNoEditable):
        servicios.ejecutar(conn, "fijar_campo", {
            "tabla": "factura", "fila_id": f, "campo": "iban_doc",
            "valor": next(iter(ibans)), "motivo": MOTIVO,
            "rev": conn.execute("SELECT rev FROM factura WHERE id = ?", (f,)).fetchone()[0]},
            usuario_id=ana)
    servicios.ejecutar(conn, "anadir_nota", {"fila_id": f, "texto": "Llamado al proveedor"},
                       usuario_id=ana)
    fuera = _fuera_de_su_sitio(conn, ibans)
    assert fuera == [], fuera
    esquema = _esquema(conn)
    assert SITIO_DEL_DOCUMENTO <= {(t, c) for t, columnas in esquema.items() for c in columnas}
    if "cuenta_bancaria" in esquema:
        assert conn.execute("SELECT count(*) FROM cuenta_bancaria").fetchone()[0] == 0
    if "cuenta_bancaria" in campos.REGISTRO:
        assert campos.PERMISO_ALTA["cuenta_bancaria"] == Permiso.CONFIRMAR_IBAN.value
    # Ninguna columna de banco en un maestro: el IBAN del maestro llega en el paso 7, por
    # su tabla, firmado por una persona.
    for tabla in ("proveedor", "cliente", "contacto", "recurso"):
        assert not [c for c in esquema.get(tabla, []) if "iban" in c or "cuenta" in c], tabla


# ============================================================ la extraccion, sin herramientas

HERRAMIENTAS = {"tools", "tool_choice", "mcp_servers"}


def test_la_peticion_de_extraccion_no_lleva_herramientas(tmp_path) -> None:
    documento = SourceDocument(path=tmp_path / "a.pdf", sha256="0" * 64, byte_size=5,
                               data_b64="JVBERi0=")
    peticion = extract.build_request(documento, model="modelo-de-prueba")
    assert set(peticion) == {"model", "max_tokens", "system", "messages", "output_format"}
    assert not HERRAMIENTAS & set(peticion)
    contenido = json.dumps(peticion["messages"])
    assert '"tool_use"' not in contenido and '"tool_result"' not in contenido

    recibido = {}

    class Cliente:
        class messages:  # noqa: N801 (la forma del SDK)
            @staticmethod
            def parse(**kwargs):
                recibido.update(kwargs)
                return SimpleNamespace(stop_reason="end_turn", parsed_output=None, usage=None)

    extract.extract_invoice(Cliente, documento, model="modelo-de-prueba")
    assert recibido and not HERRAMIENTAS & set(recibido)


def test_ningun_codigo_pasa_herramientas_a_un_modelo() -> None:
    """Ni en una peticion suelta ni en un lote: ningun argumento ni clave se llama asi."""
    usos = []
    for nombre, ruta in MODULOS.items():
        for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.keyword) and nodo.arg in HERRAMIENTAS:
                usos.append((nombre, nodo.arg))
            if isinstance(nodo, ast.Dict):
                usos += [(nombre, k.value) for k in nodo.keys
                         if isinstance(k, ast.Constant) and k.value in HERRAMIENTAS]
            if isinstance(nodo, ast.Subscript) and isinstance(nodo.slice, ast.Constant) and (
                    nodo.slice.value in HERRAMIENTAS):
                usos.append((nombre, nodo.slice.value))
    assert usos == []
