"""Interfaz de linea de comandos de la fase 0.

Ninguna orden escribe en ningun sistema de la empresa:

    bms-agent schema              muestra el esquema de extraccion
    bms-agent extract facturas/   extrae los PDF de una carpeta a out/ y al almacen
    bms-agent score               compara out/ con las respuestas a mano
    bms-agent coste               que ha costado, y que costaria la proxima
    bms-agent db init|migrar|verificar   el almacen (datos/bms.sqlite3)
    bms-agent importar-out        lleva out/*.json al almacen, sin llamar a la API

`extract` conserva por defecto lo ya leido: un PDF con cualquier extraccion
guardada no vuelve a la API aunque cambie el modelo o la version. Para medir
un modelo o un prompt nuevo hace falta pedirlo con --estricta.

El almacen esta en datos/bms.sqlite3, o donde diga --db o la variable BMS_DB;
los originales, en la carpeta documentos/ de al lado.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config
from .almacen import ruta_por_defecto
from .cache import CONSERVAR, ESTRICTA, indexar, reutilizable
from .documents import UnsupportedDocument, iter_pdfs, load_pdf
from .extract import build_request, extraer_pasada
from .panel import escribir_panel
from .report import build_report, load_records, render_html
from .pricing import format_cost_summary
from .schema import InvoiceExtraction
from .scoring import Report, load_ground_truth, score_document, format_report


def _cmd_schema(args: argparse.Namespace) -> int:
    print(json.dumps(InvoiceExtraction.model_json_schema(), indent=2, ensure_ascii=False))
    return 0


_AYUDA_DB = "almacen SQLite (por defecto: BMS_DB o datos/bms.sqlite3)"

_ETIQUETAS_PASO = {"omitido": "omitido", "cache": "cache", "error": "ERROR", "ok": "ok"}


def _imprimir_paso(tipo: str, nombre: str, detalle: str) -> None:
    separador = ": " if tipo in ("omitido", "error") else " -> "
    print(f"  {_ETIQUETAS_PASO[tipo]:<8} {nombre}{separador}{detalle}")


def _cmd_extract(args: argparse.Namespace) -> int:
    try:
        import anthropic
    except ImportError:
        print("Falta el paquete anthropic. Instala con: pip install -e .", file=sys.stderr)
        return 2

    pdfs = list(iter_pdfs(args.directory))
    if not pdfs:
        print(f"No hay PDF en {args.directory}", file=sys.stderr)
        return 1

    # El almacen se abre antes de gastar nada: si no se puede, no se paga.
    try:
        almacen = _abrir_almacen(args.db)
    except Exception as exc:
        print(f"No se puede abrir el almacen: {exc}", file=sys.stderr)
        return 2
    with almacen:
        codigo = extraer_carpeta(
            anthropic.Anthropic(), pdfs, Path(args.out),
            politica=ESTRICTA if args.estricta else CONSERVAR, forzar=args.force,
            almacen=almacen,
        )
        _anclar(almacen, Path(args.out))
    return codigo


def _ruta_db(valor: str | None) -> Path:
    return Path(valor) if valor else ruta_por_defecto()


def _abrir_almacen(valor: str | None):
    from .almacen import preparar

    return preparar(_ruta_db(valor))


def _anclar(almacen, out_dir: Path) -> None:
    """Apunta la cabeza de la auditoria en out/anclas.log (ver auditoria.anclar)."""
    from .auditoria import anclar

    anclar(almacen.conn, out_dir / "anclas.log")


def extraer_carpeta(
    client: object, pdfs: list[Path], out_dir: Path, *, politica: str, forzar: bool,
    almacen=None,
) -> int:
    """El cuerpo de `extract`, con el cliente inyectado para poder probarlo."""
    model = config.model_id()
    print(f"Extrayendo {len(pdfs)} documentos con {model}")
    if forzar:
        print("--force: se vuelven a leer todos, aunque ya esten leidos (gasta creditos)")
    else:
        guardadas = len(indexar(out_dir))
        if guardadas:
            modo = ("solo si coinciden modelo y versiones" if politica == ESTRICTA
                    else "con cualquier modelo o version")
            print(f"{guardadas} documentos ya leidos en {out_dir}/, se reutilizan {modo}")
    print()

    r = extraer_pasada(
        client, pdfs, out_dir, model=model, politica=politica, forzar=forzar,
        informar=_imprimir_paso, almacen=almacen,
    )

    print(f"\nHecho. {r.extraidas} extraidos, {r.reutilizadas} reutilizados, "
          f"{r.fallidas} con problemas, de {len(pdfs)} documentos en {out_dir}/\n")
    if almacen is not None:
        print(f"Almacen: {r.almacenadas} documentos guardados con su extraccion")
        if r.sin_almacen:
            print(f"  {r.sin_almacen} no se pudieron guardar; estan en {out_dir}/ y "
                  "`bms-agent importar-out` los recupera sin pagar")
        print()
    if r.extraidas:
        print(format_cost_summary(model, r.extraidas, r.tokens_entrada, r.tokens_salida))
    return 1 if r.fallidas or r.sin_almacen else 0


def _cmd_score(args: argparse.Namespace) -> int:
    truth = load_ground_truth(args.ground_truth)
    if not truth:
        print(f"{args.ground_truth} esta vacio", file=sys.stderr)
        return 1

    # Una extraccion por documento, la vigente: si hay varias versiones del
    # mismo PDF, se puntua la mas reciente, que es la que se acaba de medir.
    by_name = {}
    for payload in load_records(args.out):
        if "source_name" in payload:
            by_name[payload["source_name"]] = payload

    scores = []
    missing = []
    for source_name, expected in truth.items():
        payload = by_name.get(source_name)
        if payload is None:
            missing.append(source_name)
            continue
        scores.append(score_document(source_name, payload["extraction"], expected))

    if missing:
        print(f"Sin extraccion para {len(missing)} documentos: {', '.join(missing)}\n")

    if not scores:
        print("No hay nada que puntuar.", file=sys.stderr)
        return 1

    print(format_report(Report(documents=scores)))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    records = load_records(args.out)
    if not records:
        print(f"No hay extracciones en {args.out}/", file=sys.stderr)
        return 1

    data = build_report(records)
    target = Path(args.file)
    target.write_text(render_html(data), encoding="utf-8")

    print(f"Informe de {len(data.invoices)} facturas escrito en {target}")
    importe = f"{data.total_amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    print(f"  importe total     {importe} EUR")
    print(f"  con avisos        {data.with_flags}")
    print(f"  coste de lectura  ${data.total_cost:.4f}")
    print(f"\nAbrelo con:  start {target}")
    return 0


def _cmd_panel(args: argparse.Namespace) -> int:
    registros = load_records(args.out)
    if not registros:
        print(f"No hay extracciones en {args.out}/", file=sys.stderr)
        return 1

    destino = escribir_panel(registros, args.file, tarifas_path=args.tarifas)
    from .dashboard import construir_datos

    datos = construir_datos(registros, tarifas_path=args.tarifas)
    t = datos["totales"]
    importe = f"{t['importe'] or 0:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

    print(f"Panel de {t['facturas']} facturas escrito en {destino}")
    print(f"  proveedores       {t['proveedores']}")
    print(f"  importe total     {importe} EUR")
    print(f"  criticas          {t['criticas']}")
    print(f"  por revisar       {t['por_revisar']}")
    print(f"  avisos agrupados  {len(datos['alertas'])}")
    print(f"\nAbrelo con:  start {destino}")
    return 0


def _cmd_simulador(args: argparse.Namespace) -> int:
    from .simulador import escribir_simulador

    registros = load_records(args.out)
    if not registros:
        print(f"No hay extracciones en {args.out}/", file=sys.stderr)
        return 1

    destino = escribir_simulador(registros, args.file, tarifas=args.tarifas)
    print(f"Simulador escrito en {destino}")
    print("  Mueve el margen o escribe una tarifa y todo se recalcula en la pagina.")
    print(f"\nAbrelo con:  start {destino}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from .serve import servir

    try:
        servir(carpeta_pdf=args.facturas, carpeta_salida=args.out, puerto=args.puerto,
               origenes_extra=args.origen, ruta_db=_ruta_db(args.db))
    except ValueError as exc:
        print(f"No se arranca el servidor: {exc}", file=sys.stderr)
        return 2
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    from .dashboard import construir_datos

    registros = load_records(args.out)
    if not registros:
        print(f"No hay extracciones en {args.out}/", file=sys.stderr)
        return 1

    datos = construir_datos(registros, tarifas_path=args.tarifas)
    destino = Path(args.file)
    destino.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"{len(datos['filas'])} facturas exportadas a {destino}")
    print(f"  {destino.stat().st_size:,} bytes")
    return 0


def _cmd_coste(args: argparse.Namespace) -> int:
    from .coste import (
        Estimacion, agrupar_en_pasadas, contar_entrada, formatear_estimacion,
        formatear_gastado, formatear_pasadas, formatear_relanzar,
        horquilla_de_salida, leer_documentos,
    )

    # Lo gastado cuenta cada extraccion pagada, tambien las que ya no son la
    # vigente de su documento. Lo que costaria relanzar va por documento.
    documentos = leer_documentos(load_records(args.out, todas=True))
    print(formatear_gastado(documentos))
    if documentos:
        print()
        print(formatear_pasadas(agrupar_en_pasadas(documentos)))
        print()
        print(formatear_relanzar(leer_documentos(load_records(args.out))))

    if not args.estimar:
        if not documentos:
            print("\nPara saber que costaria una pasada antes de pagarla:"
                  "\n  bms-agent coste --estimar facturas/")
        return 0

    try:
        import anthropic
    except ImportError:
        print("Falta el paquete anthropic. Instala con: pip install -e .", file=sys.stderr)
        return 2

    pdfs = list(iter_pdfs(args.estimar))
    if not pdfs:
        print(f"\nNo hay PDF en {args.estimar}", file=sys.stderr)
        return 1

    client = anthropic.Anthropic()
    model = config.model_id()
    politica = ESTRICTA if args.estricta else CONSERVAR
    indice = indexar(args.out)
    bajo, alto, medida = horquilla_de_salida(documentos)

    en_cache = entrada = nuevos = 0
    for path in pdfs:
        try:
            doc = load_pdf(path)
        except UnsupportedDocument as exc:
            print(f"  omitido  {path.name}: {exc}")
            continue
        if reutilizable(
            indice.get(doc.sha256), politica=politica, model=model,
            prompt_version=config.PROMPT_VERSION, schema_version=config.SCHEMA_VERSION,
        ) is not None:
            en_cache += 1
            continue
        nuevos += 1
        entrada += contar_entrada(client, build_request(doc, model=model))

    print()
    print(formatear_estimacion(Estimacion(
        modelo=model, en_cache=en_cache, nuevos=nuevos, entrada=entrada,
        salida_baja=bajo * nuevos, salida_alta=alto * nuevos, salida_medida=medida,
    )))
    return 0


def _cmd_db(args: argparse.Namespace) -> int:
    from .almacen import abrir
    from .almacen.migrar import MigracionAlterada, migrar, pendientes

    ruta = _ruta_db(args.db)
    if args.accion != "init" and not ruta.exists():
        print(f"No existe el almacen {ruta}. Crealo con: bms-agent db init", file=sys.stderr)
        return 1
    if args.accion == "verificar":
        return _verificar_db(ruta, Path(args.anclas))

    existia = ruta.exists()
    conn = abrir(ruta)
    try:
        if args.accion == "migrar" and not pendientes(conn):
            print(f"{ruta}: no hay migraciones pendientes")
        hechas = migrar(conn)
    except MigracionAlterada as exc:
        print(f"No se migra: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    if args.accion == "init":
        print(f"Almacen {'abierto' if existia else 'creado'} en {ruta}")
    for migracion in hechas:
        print(f"  aplicada {migracion.nombre}  ({migracion.sha256[:12]})")
    return 0


def _verificar_db(ruta: Path, anclas_ruta: Path) -> int:
    """Integridad de SQLite, migraciones, cadena de auditoria, anclas y originales."""
    from .almacen import Almacen, abrir, raiz_documentos_de
    from .almacen.documentos import AlmacenDocumentos, verificar
    from .almacen.migrar import comprobar, pendientes
    from .auditoria import leer_anclas, verificar_cadena

    conn = abrir(ruta)
    almacen = Almacen(conn, AlmacenDocumentos(raiz_documentos_de(ruta)))
    errores: list[str] = []
    avisos: list[str] = []
    try:
        integridad = [fila[0] for fila in conn.execute("PRAGMA integrity_check")]
        if integridad != ["ok"]:
            errores.extend(f"SQLite: {linea}" for linea in integridad)
        for fila in conn.execute("PRAGMA foreign_key_check"):
            errores.append(f"clave foranea rota en {fila[0]}, fila {fila[1]} -> {fila[2]}")
        errores.extend(comprobar(conn))
        sin_aplicar = pendientes(conn)
        if sin_aplicar:
            avisos.append("migraciones pendientes: " + ", ".join(m.nombre for m in sin_aplicar))

        anclas, malas = leer_anclas(anclas_ruta)
        errores.extend(malas)
        cadena = verificar_cadena(conn, anclas)
        errores.extend(cadena.problemas)

        problemas_doc = verificar(almacen)
        errores.extend(p.detalle for p in problemas_doc if p.gravedad == "error")
        avisos.extend(p.detalle for p in problemas_doc if p.gravedad == "aviso")
        documentos = conn.execute(
            "SELECT count(*), count(ruta_cas) FROM documento"
        ).fetchone()
        extracciones = conn.execute("SELECT count(*) FROM extraccion").fetchone()[0]
    finally:
        conn.close()

    print(f"Almacen {ruta}")
    print(f"  eventos de auditoria  {cadena.eventos}"
          + (f"  (cabeza {cadena.cabeza.id} {cadena.cabeza.hash[:12]})" if cadena.cabeza else ""))
    print(f"  anclas comprobadas    {cadena.anclas}"
          + ("" if anclas_ruta.exists() else f"  (no hay {anclas_ruta})"))
    print(f"  documentos            {documentos[0]}  ({documentos[1]} con el original)")
    print(f"  extracciones          {extracciones}")
    for aviso in avisos:
        print(f"  aviso: {aviso}")
    if errores:
        print(f"\n{len(errores)} problemas:")
        for error in errores:
            print(f"  - {error}")
        return 1
    print("\nTodo cuadra.")
    return 0


def _cmd_importar_out(args: argparse.Namespace) -> int:
    from .importadores.extracciones import importar_out

    out_dir = Path(args.out)
    if not out_dir.is_dir():
        print(f"No existe la carpeta {out_dir}", file=sys.stderr)
        return 1
    pdfs = Path(args.pdfs) if args.pdfs else None
    try:
        almacen = _abrir_almacen(args.db)
    except Exception as exc:
        print(f"No se puede abrir el almacen: {exc}", file=sys.stderr)
        return 2
    with almacen:
        r = importar_out(almacen, out_dir, pdfs)
        _anclar(almacen, out_dir)

    print(f"{r.ficheros} ficheros en {out_dir}/, sin ninguna llamada a la API")
    print(f"  importados          {r.importadas}")
    print(f"  ya estaban          {r.ya_estaban}")
    print(f"  rechazados          {r.rechazadas}")
    print(f"  documentos nuevos   {r.documentos_nuevos}")
    print(f"  originales copiados {r.originales_guardados}")
    if r.sin_original:
        donde = f"en {pdfs}/" if pdfs and pdfs.is_dir() else "porque no hay carpeta de PDF"
        print(f"  sin original        {r.sin_original}  (no se encontro su PDF {donde}; "
              "se puede anadir despues con --pdfs)")
    for nombre, motivo in r.rechazos:
        print(f"  rechazado {nombre}: {motivo}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bms-agent", description="Fase 0: observador. No escribe en ningun sistema."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_schema = sub.add_parser("schema", help="muestra el esquema de extraccion")
    p_schema.set_defaults(func=_cmd_schema)

    p_extract = sub.add_parser("extract", help="extrae los PDF de una carpeta")
    p_extract.add_argument("directory", help="carpeta con los PDF")
    p_extract.add_argument("--out", default="out", help="carpeta de salida (por defecto: out)")
    p_extract.add_argument(
        "--force",
        action="store_true",
        help="vuelve a extraer aunque ya exista el documento (gasta creditos)",
    )
    p_extract.add_argument(
        "--estricta",
        action="store_true",
        help=(
            "reutiliza solo lo leido con el mismo modelo y versiones; para medir "
            "un modelo o un prompt nuevo (gasta creditos en lo demas)"
        ),
    )
    p_extract.add_argument("--db", help=_AYUDA_DB)
    p_extract.set_defaults(func=_cmd_extract)

    p_score = sub.add_parser("score", help="compara las extracciones con las respuestas")
    p_score.add_argument("--out", default="out", help="carpeta con las extracciones")
    p_score.add_argument(
        "--ground-truth",
        default="ground_truth/respuestas.yaml",
        help="fichero de respuestas escritas a mano",
    )
    p_score.set_defaults(func=_cmd_score)

    p_report = sub.add_parser("report", help="genera un informe HTML de lo extraido")
    p_report.add_argument("--out", default="out", help="carpeta con las extracciones")
    p_report.add_argument(
        "--file", default="informe.html", help="fichero de salida (por defecto: informe.html)"
    )
    p_report.set_defaults(func=_cmd_report)

    p_panel = sub.add_parser("panel", help="panel con todo el historico y sus anomalias")
    p_panel.add_argument("--out", default="out", help="carpeta con las extracciones")
    p_panel.add_argument(
        "--file", default="panel.html", help="fichero de salida (por defecto: panel.html)"
    )
    p_panel.add_argument(
        "--tarifas", default="config/tarifas.yaml", help="tabla de tarifas de venta"
    )
    p_panel.set_defaults(func=_cmd_panel)

    p_export = sub.add_parser("export", help="exporta los datos del panel a JSON")
    p_export.add_argument("--out", default="out", help="carpeta con las extracciones")
    p_export.add_argument("--file", default="datos.json", help="fichero JSON de salida")
    p_export.add_argument(
        "--tarifas", default="config/tarifas.yaml",
        help="tabla de tarifas de venta (por defecto: config/tarifas.yaml)",
    )
    p_export.set_defaults(func=_cmd_export)

    p_sim = sub.add_parser(
        "simulador", help="simulador de tarifas de venta, con recalculo en vivo"
    )
    p_sim.add_argument("--out", default="out", help="carpeta con las extracciones")
    p_sim.add_argument("--file", default="simulador.html", help="fichero de salida")
    p_sim.add_argument(
        "--tarifas", default="config/tarifas.yaml", help="tabla de tarifas de partida"
    )
    p_sim.set_defaults(func=_cmd_simulador)

    p_coste = sub.add_parser(
        "coste", help="que ha costado cada pasada, y que costaria la siguiente"
    )
    p_coste.add_argument("--out", default="out", help="carpeta con las extracciones")
    p_coste.add_argument(
        "--estimar", metavar="CARPETA",
        help="cuenta los tokens de esos PDF antes de pagarlos (contar no se cobra)",
    )
    p_coste.add_argument(
        "--estricta", action="store_true",
        help="estima como `extract --estricta`: lo leido con otra version cuenta como nuevo",
    )
    p_coste.set_defaults(func=_cmd_coste)

    p_serve = sub.add_parser(
        "serve", help="servidor local de desarrollo (solo 127.0.0.1)"
    )
    p_serve.add_argument("--facturas", default="facturas", help="carpeta con los PDF")
    p_serve.add_argument("--out", default="out", help="carpeta de extracciones")
    p_serve.add_argument("--puerto", type=int, default=8765, help="puerto (por defecto 8765)")
    p_serve.add_argument(
        "--origen", action="append", default=[], metavar="URL",
        help=(
            "otro origen local que puede llamar al servidor, por ejemplo "
            "http://localhost:5173; se puede repetir"
        ),
    )
    p_serve.add_argument("--db", help=_AYUDA_DB)
    p_serve.set_defaults(func=_cmd_serve)

    p_db = sub.add_parser("db", help="el almacen: crear, migrar y verificar")
    sub_db = p_db.add_subparsers(dest="accion", required=True)
    for accion, ayuda in (
        ("init", "crea el almacen y aplica las migraciones"),
        ("migrar", "aplica las migraciones pendientes a un almacen que ya existe"),
        ("verificar", "comprueba la cadena de auditoria, las migraciones y cada original"),
    ):
        p_accion = sub_db.add_parser(accion, help=ayuda)
        p_accion.add_argument("--db", help=_AYUDA_DB)
        if accion == "verificar":
            p_accion.add_argument(
                "--anclas", default="out/anclas.log",
                help="fichero de anclas de la auditoria (por defecto: out/anclas.log)",
            )
    p_db.set_defaults(func=_cmd_db)

    p_importar = sub.add_parser(
        "importar-out", help="lleva las extracciones de out/ al almacen (no llama a la API)"
    )
    p_importar.add_argument("--out", default="out", help="carpeta con las extracciones")
    p_importar.add_argument(
        "--pdfs", default="facturas",
        help="carpeta donde buscar cada PDF por su hash (por defecto: facturas)",
    )
    p_importar.add_argument("--db", help=_AYUDA_DB)
    p_importar.set_defaults(func=_cmd_importar_out)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
