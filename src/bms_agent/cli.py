"""Interfaz de linea de comandos de la fase 0.

Ninguna orden escribe en ningun sistema de la empresa:

    bms-agent schema              muestra el esquema de extraccion
    bms-agent extract facturas/   extrae los PDF de una carpeta a out/ y al almacen
    bms-agent score               compara out/ con las respuestas a mano
    bms-agent coste               que ha costado, y que costaria la proxima
    bms-agent db init|migrar|verificar   el almacen (datos/bms.sqlite3)
    bms-agent importar-out        lleva out/*.json al almacen y lo tipa, sin llamar a la API
    bms-agent ingestar            tipa lo extraido que aun no tiene su factura, sin la API
    bms-agent sembrar             clientes, Objetos y tarifas de venta de config/tarifas.yaml
    bms-agent recalcular          evalua las reglas y pone al dia los hallazgos (--simular)
    bms-agent usuario ...         personas, sus roles y sus tokens
    bms-agent acciones            lo que una persona puede hacer, con su permiso
    bms-agent accion NOMBRE ...   una orden de una persona (con su token)
    bms-agent facturas            las facturas, la mas urgente primero
    bms-agent factura N           la ficha de una factura
    bms-agent excepciones         las excepciones sin resolver
    bms-agent politica cargar     apunta config/prioridad.yaml en la politica

Cada orden que cambia algo que una regla lee (importar-out, ingestar,
extract, sembrar) termina recalculando las reglas en su misma transaccion;
`recalcular --diaria` es la pasada de cada dia, para lo que depende de la
fecha.

`panel`, `report`, `export` y `simulador` leen del almacen, con los valores
corregidos; solo si no hay almacen leen out/ tal cual, y lo dicen.

Las ordenes de una persona (`accion`) se identifican con su token
(`usuario token NOMBRE` da uno; se pasa con --token o la variable
BMS_TOKEN): cada una comprueba el permiso, el motivo y la version de la fila,
escribe, recalcula y dice lo que cambio, todo en una transaccion. Ninguna
crea una factura, paga, aprueba un pago ni presenta el BTW.

`extract` conserva por defecto lo ya leido: un PDF con cualquier extraccion
guardada no vuelve a la API aunque cambie el modelo o la version. Para medir
un modelo o un prompt nuevo hace falta pedirlo con --estricta.

El almacen esta en datos/bms.sqlite3, o donde diga --db o la variable BMS_DB;
los originales, en la carpeta documentos/ de al lado, y las anclas de la
auditoria en anclas.log, tambien al lado.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from . import config
from .almacen import ruta_por_defecto, transaccion
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
_AYUDA_OUT = ("lee esta carpeta de extracciones tal cual, sin correcciones, en vez del "
              "almacen (sin --out: el almacen, o out/ si aun no hay almacen)")

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
        _anclar(almacen)
    return codigo


def _ruta_db(valor: str | None) -> Path:
    return Path(valor) if valor else ruta_por_defecto()


def _abrir_almacen(valor: str | None):
    from .almacen import preparar

    return preparar(_ruta_db(valor))


def _anclar(almacen) -> None:
    """Apunta la cabeza de la auditoria en el anclas.log de la base (ver auditoria.anclar)."""
    from .auditoria import anclar

    if almacen.ruta_anclas is not None:
        anclar(almacen.conn, almacen.ruta_anclas)


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

    ingesta = None
    if almacen is not None:
        from .ingesta import ingestar_pasada

        r, ingesta = ingestar_pasada(
            client, pdfs, out_dir, almacen=almacen, model=model, politica=politica,
            forzar=forzar, informar=_imprimir_paso,
        )
    else:
        r = extraer_pasada(
            client, pdfs, out_dir, model=model, politica=politica, forzar=forzar,
            informar=_imprimir_paso,
        )

    print(f"\nHecho. {r.extraidas} extraidos, {r.reutilizadas} reutilizados, "
          f"{r.fallidas} con problemas, de {len(pdfs)} documentos en {out_dir}/\n")
    if almacen is not None:
        print(f"Almacen: {r.almacenadas} documentos guardados con su extraccion")
        if r.sin_almacen:
            print(f"  {r.sin_almacen} no se pudieron guardar; estan en {out_dir}/ y "
                  "`bms-agent importar-out` los recupera sin pagar")
        _imprimir_tipado(ingesta)
        _imprimir_recalculo(ingesta.recalculo)
        print()
    if r.extraidas:
        print(format_cost_summary(model, r.extraidas, r.tokens_entrada, r.tokens_salida))
    errores_tipado = len(ingesta.errores) if ingesta is not None else 0
    return 1 if r.fallidas or r.sin_almacen or errores_tipado else 0


def _imprimir_tipado(ingesta) -> None:
    """Cuantas facturas tipadas salieron de lo guardado, y las que no se pudo."""
    print(f"Facturas tipadas: {ingesta.cuenta('creada')} nuevas, "
          f"{ingesta.cuenta('actualizada')} con una extraccion nueva, "
          f"{ingesta.cuenta('sin_cambios')} sin cambios")
    for tipado in ingesta.tipados:
        if tipado.accion in ("error", "omitido"):
            print(f"  {tipado.accion} documento {tipado.documento_id}: {tipado.detalle}")


_PLURAL_TRANSICION = {
    "detectado": "nuevos", "cambio_evidencia": "con otra evidencia",
    "desaparecido": "desaparecidos (pegajosos: siguen pendientes)",
    "cerrado_automatico": "cerrados solos", "reabierto": "reabiertos",
    "aceptado": "aceptados de nuevo por su anulacion",
}
_ETIQUETA_RESULTADO = {"ok": "ok", "fallo": "fallo", "sin_datos": "sin datos",
                       "no_aplica": "no aplica"}


def _imprimir_recalculo(diferencia, *, detalle: bool = False) -> None:
    """Lo que dejo la pasada del motor de reglas: evaluaciones y hallazgos que se movieron."""
    if diferencia is None:
        return
    total = sum(diferencia.evaluaciones.values())
    cuentas = ", ".join(f"{diferencia.evaluaciones.get(r, 0)} {e}"
                        for r, e in _ETIQUETA_RESULTADO.items())
    print(f"Reglas: {total} evaluaciones ({cuentas})")
    movidos = [f"{len(diferencia.de_tipo(t))} {e}" for t, e in _PLURAL_TRANSICION.items()
               if diferencia.de_tipo(t)]
    print("Hallazgos: " + (", ".join(movidos) if movidos else "ninguno cambia"))
    if diferencia.retenidos:
        print(f"  {len(diferencia.retenidos)} se quedan como estaban: su regla no ha podido "
              "mirar (sin datos)")
    pendientes = diferencia.pendientes
    print(f"  pendientes: {pendientes.get('abierto', 0)} abiertos, "
          f"{pendientes.get('aceptado', 0)} aceptados, "
          f"{pendientes.get('desaparecido', 0)} desaparecidos")
    if detalle:
        for t in diferencia.transiciones:
            donde = f"factura {t.factura_id}" if t.factura_id is not None else t.clave
            causa = f"  (causa: evento {t.causa_evento_id})" if t.causa_evento_id else ""
            nota = f"  {t.nota}" if t.nota else ""
            print(f"  {t.tipo:<18} {t.regla:<4} {donde}{causa}{nota}")


def _cmd_recalcular(args: argparse.Namespace) -> int:
    """Evalua el catalogo de reglas y pone al dia los hallazgos. Cero llamadas a la API."""
    from .hallazgos import recalcular

    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}. Crealo con: bms-agent importar-out", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        diferencia = recalcular(almacen.conn, motivo="diaria" if args.diaria else "manual",
                                simular=args.simular)
        _anclar(almacen)
    if diferencia.simulada:
        print("Simulacion: no se ha escrito nada; esto es lo que cambiaria")
    else:
        print(f"Pasada {diferencia.ejecucion_id} del motor de reglas")
    _imprimir_recalculo(diferencia, detalle=True)
    return 0


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


def _leer(args: argparse.Namespace):
    """Los registros que pide la orden, y de donde salen.

    `--db` lee ese almacen; `--out` sin `--db`, esa carpeta tal cual (quien
    la nombra quiere verla a ella); sin ninguno, el almacen por defecto, o
    out/ si todavia no hay almacen. Con los dos manda el almacen, y se dice.
    """
    from .legado import leer_registros

    out = args.out if args.out is not None else "out"
    if args.out is not None and args.db is not None:
        print(f"Se pidio --db: se lee el almacen y no {args.out}/")
    lectura = leer_registros(out, _ruta_db(args.db),
                             out_pedido=args.out is not None and args.db is None)
    print(lectura.explicacion())
    if not lectura.registros:
        donde = (f"el almacen {lectura.ruta_db}" if lectura.desde == "almacen"
                 else f"{out}/")
        print(f"No hay extracciones en {donde}", file=sys.stderr)
    return lectura.registros


def _cmd_report(args: argparse.Namespace) -> int:
    records = _leer(args)
    if not records:
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
    registros = _leer(args)
    if not registros:
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

    registros = _leer(args)
    if not registros:
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

    registros = _leer(args)
    if not registros:
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
    from .almacen import abrir, ruta_anclas_de
    from .almacen.migrar import MigracionAlterada, migrar, pendientes
    from .auditoria import anclar

    ruta = _ruta_db(args.db)
    if args.accion != "init" and not ruta.exists():
        print(f"No existe el almacen {ruta}. Crealo con: bms-agent db init", file=sys.stderr)
        return 1
    if args.accion == "verificar":
        anclas = Path(args.anclas) if args.anclas else ruta_anclas_de(ruta)
        return _verificar_db(ruta, anclas, exigir_anclas=not args.sin_anclas)

    existia = ruta.exists()
    conn = abrir(ruta)
    try:
        if args.accion == "migrar" and not pendientes(conn):
            print(f"{ruta}: no hay migraciones pendientes")
        hechas = migrar(conn)
        anclar(conn, ruta_anclas_de(ruta))
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


def _verificar_db(ruta: Path, anclas_ruta: Path, *, exigir_anclas: bool = True) -> int:
    """Integridad de SQLite, esquema, migraciones, auditoria, anclas, evidencia y originales.

    Sin anclas, la cadena no ve que alguien corte o reescriba su final: por
    eso que falten (o que ninguna sea de esta base) es un error, salvo que
    se pida verificar sin ellas con --sin-anclas.
    """
    from .almacen import Almacen, abrir, raiz_documentos_de
    from .almacen.documentos import AlmacenDocumentos, verificar
    from .almacen.evidencia import verificar_esquema, verificar_evidencia
    from .almacen.migrar import aplicadas, comprobar, pendientes
    from .auditoria import leer_anclas, verificar_cadena

    conn = abrir(ruta)
    if not aplicadas(conn):
        conn.close()
        print(f"Almacen {ruta}\n\n1 problemas:\n"
              "  - el almacen no esta migrado (bms-agent db migrar)")
        return 1
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
        errores.extend(verificar_esquema(conn))
        sin_aplicar = pendientes(conn)
        if sin_aplicar:
            avisos.append("migraciones pendientes: " + ", ".join(m.nombre for m in sin_aplicar))

        anclas, malas = leer_anclas(anclas_ruta)
        errores.extend(malas)
        cadena = verificar_cadena(conn, anclas)
        errores.extend(cadena.problemas)
        if exigir_anclas and cadena.eventos and not cadena.anclas:
            errores.append(
                f"no hay ninguna ancla de este almacen en {anclas_ruta}: sin ellas no se ve "
                "un final de la cadena cortado o reescrito (--sin-anclas para verificar sin ellas)"
            )
        if cadena.anclas_ajenas:
            avisos.append(f"{cadena.anclas_ajenas} anclas de {anclas_ruta} son de otro almacen")
        errores.extend(verificar_evidencia(conn))
        tipado = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'factura'").fetchone()
        if tipado:
            from .campos import verificar_controladas

            errores.extend(verificar_controladas(conn))
        con_hallazgos = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'hallazgo'").fetchone()
        if con_hallazgos:
            from .hallazgos import verificar as verificar_hallazgos

            errores.extend(verificar_hallazgos(conn))
        con_excepciones = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'excepcion'").fetchone()
        if con_excepciones:
            from .excepciones import verificar as verificar_excepciones

            errores.extend(verificar_excepciones(conn))

        problemas_doc = verificar(almacen)
        errores.extend(p.detalle for p in problemas_doc if p.gravedad == "error")
        avisos.extend(p.detalle for p in problemas_doc if p.gravedad == "aviso")
        documentos = conn.execute(
            "SELECT count(*), count(ruta_cas) FROM documento"
        ).fetchone()
        extracciones = conn.execute("SELECT count(*) FROM extraccion").fetchone()[0]
        facturas = conn.execute("SELECT count(*) FROM factura").fetchone()[0] if tipado else 0
    finally:
        conn.close()

    print(f"Almacen {ruta}")
    print(f"  eventos de auditoria  {cadena.eventos}"
          + (f"  (cabeza {cadena.cabeza.id} {cadena.cabeza.hash[:12]})" if cadena.cabeza else ""))
    print(f"  anclas comprobadas    {cadena.anclas}" + _detalle_anclas(cadena, anclas_ruta))
    print(f"  documentos            {documentos[0]}  ({documentos[1]} con el original)")
    print(f"  extracciones          {extracciones}")
    print(f"  facturas tipadas      {facturas}")
    for aviso in avisos:
        print(f"  aviso: {aviso}")
    if errores:
        print(f"\n{len(errores)} problemas:")
        for error in errores:
            print(f"  - {error}")
        return 1
    print("\nTodo cuadra.")
    return 0


def _detalle_anclas(cadena, anclas_ruta: Path) -> str:
    """Donde estan, y cuantos eventos hay despues de la ultima (eso no lo cubre ninguna)."""
    if not anclas_ruta.exists():
        return f"  (no hay {anclas_ruta})"
    if cadena.ultima_ancla is None or cadena.cabeza is None:
        return f"  ({anclas_ruta})"
    detras = cadena.cabeza.id - cadena.ultima_ancla
    if detras <= 0:
        return f"  ({anclas_ruta}; la ultima es la cabeza)"
    return f"  ({anclas_ruta}; la ultima es el evento {cadena.ultima_ancla}, {detras} sin anclar)"


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
        # Una orden, una transaccion (spec §4): importar, tipar y recalcular
        # las reglas van juntos, y cada fichero y cada documento en su
        # SAVEPOINT, asi que uno que falla no se lleva a los demas y un fallo
        # de la orden no deja nada a medias.
        with transaccion(almacen.conn):
            r = importar_out(almacen, out_dir, pdfs)
            tipado = _tipar(almacen)
            tipado.recalculo = _recalcular(almacen, "importacion")
        _anclar(almacen)

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
    _imprimir_tipado(tipado)
    _imprimir_recalculo(tipado.recalculo)
    return 1 if tipado.errores else 0


def _tipar(almacen):
    from .ingesta import ResultadoIngesta, tipar_pendientes

    return ResultadoIngesta(tipar_pendientes(almacen.conn))


def _recalcular(almacen, motivo: str):
    from .hallazgos import recalcular

    return recalcular(almacen.conn, motivo=motivo)


def _cmd_ingestar(args: argparse.Namespace) -> int:
    """Tipa lo que ya esta extraido en el almacen. Cero llamadas a la API."""
    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}. Crealo con: bms-agent importar-out", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        # Tipar y recalcular, una transaccion; cada documento en su SAVEPOINT.
        with transaccion(almacen.conn):
            tipado = _tipar(almacen)
            tipado.recalculo = _recalcular(almacen, "ingesta")
        _anclar(almacen)
    _imprimir_tipado(tipado)
    _imprimir_recalculo(tipado.recalculo)
    return 1 if tipado.errores else 0


def _cmd_sembrar(args: argparse.Namespace) -> int:
    from .importadores.tarifas import sembrar_tarifas

    fichero = Path(args.tarifas)
    if not fichero.is_file():
        print(f"No existe {fichero}. Copia config/tarifas.ejemplo.yaml y rellenalo.",
              file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        r = sembrar_tarifas(almacen.conn, fichero)
        _anclar(almacen)
    print(f"{fichero} ({r.sha256[:12]}){'' if r.nueva_politica else ', ya estaba cargado'}")
    print(f"  clientes nuevos       {r.clientes_nuevos}")
    print(f"  Objetos nuevos        {r.objetos_nuevos}")
    print(f"  tarifas nuevas        {r.tarifas_nuevas}")
    print(f"  tarifas cambiadas     {r.tarifas_cambiadas}")
    print(f"  imputaciones resueltas {r.imputaciones_resueltas}")
    for aviso in r.avisos:
        print(f"  aviso: {aviso}")
    _imprimir_recalculo(r.recalculo)
    return 0


def _cmd_usuario(args: argparse.Namespace) -> int:
    """Personas y roles. La CLI local actua como el operador del fichero (permisos.py)."""
    from . import permisos

    with _abrir_almacen(args.db) as almacen:
        conn = almacen.conn
        try:
            if args.accion == "crear":
                usuario_id = permisos.crear_usuario(conn, args.nombre, email=args.email)
                print(f"Persona {args.nombre} creada (id {usuario_id})")
                for rol in args.rol:
                    permisos.asegurar_roles_base(conn)
                    permisos.asignar_rol(conn, usuario_id, rol)
                    print(f"  con el rol {rol}")
            elif args.accion == "asignar":
                permisos.asegurar_roles_base(conn)
                permisos.asignar_rol(conn, permisos.usuario_por_nombre(conn, args.nombre), args.rol)
                print(f"{args.nombre} tiene ahora el rol {args.rol}")
            elif args.accion == "quitar":
                permisos.cerrar_rol(conn, permisos.usuario_por_nombre(conn, args.nombre), args.rol)
                print(f"{args.nombre} ya no tiene el rol {args.rol}")
            elif args.accion == "token":
                token = permisos.emitir_token(conn, permisos.usuario_por_nombre(conn, args.nombre))
                print(f"Token de {args.nombre} (se ensena una sola vez; el anterior ya no vale):")
                print(f"  {token}")
                print("Con el se entra en la consola (bms-agent serve) y se firman las ordenes "
                      "de la CLI (--token o BMS_TOKEN).")
            elif args.accion == "desactivar":
                permisos.desactivar_usuario(conn, permisos.usuario_por_nombre(conn, args.nombre))
                print(f"{args.nombre} queda desactivado y su token ya no vale")
            else:
                for u in permisos.listar_usuarios(conn):
                    tipo = "sistema" if u["es_sistema"] else "persona"
                    roles = ", ".join(u["roles"]) or "sin roles"
                    print(f"  {u['id']:>3}  {u['nombre']:<20} {tipo:<8} {roles}")
        except (ValueError, LookupError) as exc:
            print(f"No se hace: {exc}", file=sys.stderr)
            return 1
        _anclar(almacen)
    return 0


VARIABLE_TOKEN = "BMS_TOKEN"


def _persona_de_token(conn, token: str | None, accion: str) -> int | None:
    """La persona del token; si no vale, el intento queda en la auditoria y None."""
    from .permisos import PermisoDenegado, registrar_denegacion, usuario_por_token

    usuario_id = usuario_por_token(conn, token)
    if usuario_id is None:
        registrar_denegacion(conn, PermisoDenegado(
            None, "ver_facturas", "token ausente o no valido", accion))
    return usuario_id


def _cmd_acciones(args: argparse.Namespace) -> int:
    """Lo que una persona puede hacer, con el permiso que pide cada cosa (spec §6)."""
    from .servicios import ACCIONES

    del_campo = "el del campo (rellenar: anadir_informacion; corregir: editar_extraccion)"
    for accion in ACCIONES.values():
        print(f"{accion.nombre}  [{accion.permiso or del_campo}]")
        print(f"    {accion.descripcion}")
        parametros = " ".join(
            f"--{p.nombre.replace('_', '-')}" + ("" if p.obligatorio else "?")
            for p in accion.parametros)
        if parametros:
            print(f"    {parametros}")
    return 0


def _cmd_accion(args: argparse.Namespace) -> int:
    """Una orden de una persona, firmada con su token. Cero llamadas a la API."""
    from . import servicios
    from .campos import Conflicto, FaltaMotivo
    from .permisos import PermisoDenegado
    from .servicios import ACCIONES, LISTA, OBJETO

    accion = ACCIONES[args.nombre]
    datos = {}
    for parametro in accion.parametros:
        valor = getattr(args, parametro.nombre, None)
        if valor is None:
            continue
        if parametro.tipo in (LISTA, OBJETO):
            try:
                valor = json.loads(valor)
            except json.JSONDecodeError:
                print(f"--{parametro.nombre.replace('_', '-')} es JSON", file=sys.stderr)
                return 1
        datos[parametro.nombre] = valor
    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        conn = almacen.conn
        token = args.token or os.environ.get(VARIABLE_TOKEN)
        usuario_id = _persona_de_token(conn, token, args.nombre)
        if usuario_id is None:
            print("Hace falta el token de una persona activa (--token o BMS_TOKEN; "
                  "lo da `bms-agent usuario token NOMBRE`)", file=sys.stderr)
            _anclar(almacen)
            return 1
        try:
            diferencia = servicios.ejecutar(conn, args.nombre, datos, usuario_id=usuario_id,
                                            peticion_id=args.peticion)
        except (PermisoDenegado, Conflicto, FaltaMotivo, ValueError, LookupError,
                TypeError, sqlite3.Error) as exc:
            print(f"No se hace: {exc}", file=sys.stderr)
            _anclar(almacen)
            return 1
        _anclar(almacen)
    for linea in diferencia.lineas():
        print(linea)
    return 0


_SIMBOLO = {"bloqueada": "BLOQ", "urgente": "URG ", "atencion": "ATN ", "normal": "    "}


def _cmd_facturas(args: argparse.Namespace) -> int:
    """Las facturas, la mas urgente primero (lo mismo que la lista de la consola)."""
    from .consultas import listado

    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        filas = listado(almacen.conn, nivel=args.nivel, limite=args.limite)
    for f in filas:
        print(f"{_SIMBOLO.get(f['nivel'], f['nivel'])} {f['puntos']:>3}  {f['id']:>5}  "
              f"{(f['numero'] or '(sin numero)'):<18} {(f['contraparte'] or '')[:28]:<28} "
              f"{f['total'] or '':>12}  {f['estado_revision'] or '':<17} {f['etiqueta']}")
        if f["motivos"]:
            print(f"{'':>12}{' · '.join(f['motivos'])}")
    return 0


def _cmd_factura(args: argparse.Namespace) -> int:
    """La ficha de una factura: campos con su original y su fuente, hallazgos y excepcion."""
    from .consultas import detalle

    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        try:
            ficha = detalle(almacen.conn, args.id)
        except LookupError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.json:
        print(json.dumps(ficha, ensure_ascii=False, indent=2, default=str))
        return 0
    estado = ficha["estado"] or {}
    print(f"Factura {ficha['id']} {ficha['numero'] or '(sin numero)'} — {ficha['contraparte']}"
          f"  (rev {ficha['rev']})")
    print(f"  {estado.get('nivel', '-')}, {estado.get('puntos', 0)} puntos; "
          f"{estado.get('estado_revision', '-')}; {ficha['etiqueta']}")
    for motivo in estado.get("motivos", []):
        print(f"    {motivo}")
    print(f"  huella del contenido: {ficha['huella_contenido']}")
    for c in ficha["campos"]:
        if c["valor"] is None and c["original_crudo"] is None:
            continue
        marcas = [m for m, si in (("editado", c["editado"]), ("sin resolver", c["sin_resolver"]),
                                  ("dudoso", c["dudoso"]), ("verificado", c["verificado"])) if si]
        original = (f"  (original {c['original_texto']!s}, impreso {c['original_crudo']!r})"
                    if c["editado"] else "")
        print(f"  {c['campo']:<26} {c['texto'] or '':<30} {c['fuente'] or '':<18}"
              f"{', '.join(marcas)}{original}")
    for h in ficha["hallazgos"]:
        print(f"  hallazgo {h['id']} {h['regla']} {h['estado']} ({h['severidad']}): {h['detalle']}")
    if ficha["excepcion"]:
        e = ficha["excepcion"]
        print(f"  excepcion {e['id']} {e['estado']} (rev {e['rev']}): {e['titulo']}")
    for r in ficha["revisiones"]:
        print(f"  revision {r['resultado']} por {r['usuario']} el {r['en']}"
              f"{' (autorrevisada)' if r['autorrevisada'] else ''}"
              f"{'' if r['vigente'] else ' — ya no vale'}")
    return 0


def _cmd_excepciones(args: argparse.Namespace) -> int:
    from .consultas import excepciones_abiertas

    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        filas = excepciones_abiertas(almacen.conn)
    for e in filas:
        quien = f", de {e['responsable']}" if e["responsable"] else ""
        espera = (f", esperando a {e['esperando_a']} hasta el {e['fecha_seguimiento']}"
                  if e["esperando_a"] else "")
        print(f"{_SIMBOLO.get(e['nivel'], e['nivel'])} {e['id']:>5} (rev {e['rev']}) "
              f"{e['estado']}{quien}{espera}: {e['titulo']} — {e['descripcion'] or ''}")
    if not filas:
        print("No hay excepciones sin resolver.")
    return 0


def _cmd_politica(args: argparse.Namespace) -> int:
    """Apunta un fichero de pesos de la prioridad y recalcula con el."""
    from .hallazgos import recalcular
    from .politica import cargar_prioridad
    from .prioridad import PesosNoValidos

    fichero = Path(args.fichero)
    if not fichero.is_file():
        print(f"No existe {fichero}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        try:
            with transaccion(almacen.conn):
                pesos, nuevo = cargar_prioridad(almacen.conn, fichero)
                diferencia = recalcular(almacen.conn, motivo="manual")
        except PesosNoValidos as exc:
            print(f"No se carga {fichero}: {exc}", file=sys.stderr)
            return 1
        _anclar(almacen)
    print(f"{fichero}: {'cargado' if nuevo else 'ya era la version vigente'} "
          f"(pesos {pesos.sha256()[:12]})")
    cambios = diferencia.estados.prioridades if diferencia.estados else []
    print(f"  prioridades que cambian: {len(cambios)}")
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
    p_report.add_argument("--out", help=_AYUDA_OUT)
    p_report.add_argument(
        "--file", default="informe.html", help="fichero de salida (por defecto: informe.html)"
    )
    p_report.add_argument("--db", help=_AYUDA_DB)
    p_report.set_defaults(func=_cmd_report)

    p_panel = sub.add_parser("panel", help="panel con todo el historico y sus anomalias")
    p_panel.add_argument("--out", help=_AYUDA_OUT)
    p_panel.add_argument(
        "--file", default="panel.html", help="fichero de salida (por defecto: panel.html)"
    )
    p_panel.add_argument(
        "--tarifas", default="config/tarifas.yaml", help="tabla de tarifas de venta"
    )
    p_panel.add_argument("--db", help=_AYUDA_DB)
    p_panel.set_defaults(func=_cmd_panel)

    p_export = sub.add_parser("export", help="exporta los datos del panel a JSON")
    p_export.add_argument("--out", help=_AYUDA_OUT)
    p_export.add_argument("--file", default="datos.json", help="fichero JSON de salida")
    p_export.add_argument(
        "--tarifas", default="config/tarifas.yaml",
        help="tabla de tarifas de venta (por defecto: config/tarifas.yaml)",
    )
    p_export.add_argument("--db", help=_AYUDA_DB)
    p_export.set_defaults(func=_cmd_export)

    p_sim = sub.add_parser(
        "simulador", help="simulador de tarifas de venta, con recalculo en vivo"
    )
    p_sim.add_argument("--out", help=_AYUDA_OUT)
    p_sim.add_argument("--file", default="simulador.html", help="fichero de salida")
    p_sim.add_argument(
        "--tarifas", default="config/tarifas.yaml", help="tabla de tarifas de partida"
    )
    p_sim.add_argument("--db", help=_AYUDA_DB)
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
                "--anclas",
                help="fichero de anclas de la auditoria (por defecto: anclas.log al lado de la base)",
            )
            p_accion.add_argument(
                "--sin-anclas", action="store_true",
                help="verificar aunque no haya anclas (no se vera un final cortado o reescrito)",
            )
    p_db.set_defaults(func=_cmd_db)

    p_importar = sub.add_parser(
        "importar-out",
        help="lleva las extracciones de out/ al almacen y las tipa (no llama a la API)"
    )
    p_importar.add_argument("--out", default="out", help="carpeta con las extracciones")
    p_importar.add_argument(
        "--pdfs", default="facturas",
        help="carpeta donde buscar cada PDF por su hash (por defecto: facturas)",
    )
    p_importar.add_argument("--db", help=_AYUDA_DB)
    p_importar.set_defaults(func=_cmd_importar_out)

    p_ingestar = sub.add_parser(
        "ingestar", help="tipa lo extraido que aun no tiene su factura (no llama a la API)"
    )
    p_ingestar.add_argument("--db", help=_AYUDA_DB)
    p_ingestar.set_defaults(func=_cmd_ingestar)

    p_sembrar = sub.add_parser(
        "sembrar", help="clientes, Objetos y tarifas de venta de config/tarifas.yaml al almacen"
    )
    p_sembrar.add_argument("--tarifas", default="config/tarifas.yaml", help="tabla de tarifas")
    p_sembrar.add_argument("--db", help=_AYUDA_DB)
    p_sembrar.set_defaults(func=_cmd_sembrar)

    p_recalcular = sub.add_parser(
        "recalcular",
        help="evalua las reglas y pone al dia los hallazgos (no llama a la API)",
    )
    p_recalcular.add_argument(
        "--simular", action="store_true",
        help="dice lo que cambiaria (hallazgos nuevos, cerrados, reabiertos) sin escribir nada",
    )
    p_recalcular.add_argument(
        "--diaria", action="store_true",
        help="la pasada programada de cada dia (queda apuntada como diaria)",
    )
    p_recalcular.add_argument("--db", help=_AYUDA_DB)
    p_recalcular.set_defaults(func=_cmd_recalcular)

    p_usuario = sub.add_parser("usuario", help="personas y sus roles")
    sub_usuario = p_usuario.add_subparsers(dest="accion", required=True)
    p_crear = sub_usuario.add_parser("crear", help="una persona nueva")
    p_crear.add_argument("nombre")
    p_crear.add_argument("--email")
    p_crear.add_argument("--rol", action="append", default=[],
                         help="administrador, administracion o consulta; se puede repetir")
    for accion, ayuda in (("asignar", "da un rol a una persona"),
                          ("quitar", "cierra un rol de una persona")):
        p_rol = sub_usuario.add_parser(accion, help=ayuda)
        p_rol.add_argument("nombre")
        p_rol.add_argument("rol")
    for accion, ayuda in (("token", "un token nuevo para una persona (el anterior deja de valer)"),
                          ("desactivar", "desactiva a una persona y anula su token")):
        sub_usuario.add_parser(accion, help=ayuda).add_argument("nombre")
    sub_usuario.add_parser("listar", help="usuarios y sus roles")
    for p_accion in sub_usuario.choices.values():
        p_accion.add_argument("--db", help=_AYUDA_DB)
    p_usuario.set_defaults(func=_cmd_usuario)

    p_acciones = sub.add_parser("acciones", help="lo que una persona puede hacer, con su permiso")
    p_acciones.set_defaults(func=_cmd_acciones)

    from .servicios import ACCIONES, ENTERO

    p_accion = sub.add_parser("accion", help="una orden de una persona, firmada con su token")
    sub_accion = p_accion.add_subparsers(dest="nombre", required=True)
    for accion in ACCIONES.values():
        p_una = sub_accion.add_parser(accion.nombre, help=accion.descripcion)
        for parametro in accion.parametros:
            p_una.add_argument(f"--{parametro.nombre.replace('_', '-')}", dest=parametro.nombre,
                               required=parametro.obligatorio and parametro.nombre != "motivo",
                               help=parametro.ayuda or (
                                   "entero" if parametro.tipo == ENTERO else parametro.tipo))
        p_una.add_argument("--token", help=f"token de la persona (o la variable {VARIABLE_TOKEN})")
        p_una.add_argument("--peticion", help="identificador de la peticion: repetirla no repite "
                                              "la orden")
        p_una.add_argument("--db", help=_AYUDA_DB)
    p_accion.set_defaults(func=_cmd_accion)

    p_facturas = sub.add_parser("facturas", help="las facturas, la mas urgente primero")
    p_facturas.add_argument("--nivel", choices=("bloqueada", "urgente", "atencion", "normal"))
    p_facturas.add_argument("--limite", type=int)
    p_facturas.add_argument("--db", help=_AYUDA_DB)
    p_facturas.set_defaults(func=_cmd_facturas)

    p_factura = sub.add_parser("factura", help="la ficha de una factura")
    p_factura.add_argument("id", type=int)
    p_factura.add_argument("--json", action="store_true", help="la ficha entera en JSON")
    p_factura.add_argument("--db", help=_AYUDA_DB)
    p_factura.set_defaults(func=_cmd_factura)

    p_excepciones = sub.add_parser("excepciones", help="las excepciones sin resolver")
    p_excepciones.add_argument("--db", help=_AYUDA_DB)
    p_excepciones.set_defaults(func=_cmd_excepciones)

    p_politica = sub.add_parser("politica", help="la politica: pesos de la prioridad")
    sub_politica = p_politica.add_subparsers(dest="accion", required=True)
    p_cargar = sub_politica.add_parser("cargar", help="apunta un fichero de pesos y recalcula")
    p_cargar.add_argument("fichero", nargs="?", default="config/prioridad.yaml")
    p_cargar.add_argument("--db", help=_AYUDA_DB)
    p_politica.set_defaults(func=_cmd_politica)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
