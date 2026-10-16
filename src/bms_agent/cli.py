"""Interfaz de linea de comandos de la fase 0.

Ninguna orden escribe en ningun sistema de la empresa:

    bms-agent schema              muestra el esquema de extraccion
    bms-agent extract facturas/   extrae los PDF de una carpeta a out/ y al almacen
                                  (--salientes: facturas emitidas, a out/salientes)
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
    bms-agent relaciones          las relaciones entre facturas por confirmar
    bms-agent proveedores|clientes   lo pendiente y lo vencido de cada uno
    bms-agent proveedor|cliente N    su vista: totales, por Objeto, pagos, avisos
    bms-agent ordenes             las ordenes de compra: valor, consumido, lo que queda
    bms-agent orden N             una PO: sus facturas en orden, modificaciones y prevision
    bms-agent objeto N            un Objeto, sus PO y sus horas por semana (planning)
    bms-agent politica cargar     apunta prioridad.yaml, reglas.yaml, empresa.yaml o btw.yaml
                                  (admin)
    bms-agent btw ...             el BTW: ver (cifras, plazos, lo que revisar), hoja (la de
                                  trabajo en CSV y su sha256), listo, reabrir, anotar (la
                                  presentacion que hizo una persona en el portal)
    bms-agent importar F T FICH   importa un maestro, el banco, pagos, ventas de Exact, la
                                  hoja de PO (po_csv ordenes_compra|modificaciones_po, CSV o YAML)
                                  o el planning (trnsprnt planning, --desde/--hasta: lo que cubre;
                                  --confirmar: una foto que borraria mucho del planning de ahora)
    bms-agent iban ...            el registro de cuentas: listar, verificar, rechazar, atestar
    bms-agent fuentes             de cuando es lo ultimo de cada fuente (Z1)
    bms-agent reextraer ...       vuelve a leer lo ya leido, con presupuesto (--activar: la puerta)
    bms-agent demo crear          la base de DATOS DE PRUEBA (datos/demo.sqlite3), aparte de la
                                  de verdad (--rehacer: la borra y la vuelve a hacer)
    bms-agent copia DESTINO       copia de seguridad comprobada (base, originales y anclas)
    bms-agent restaurar ORIGEN    vuelve a poner una copia; lo que habia se guarda antes
    bms-agent salida              el proxy de salida del entorno de Docker (solo a la API de
                                  Anthropic)
    bms-agent salud HOST:PUERTO   la comprobacion de salud de un contenedor

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
guardada no vuelve a la API aunque cambie el modelo o la version. Volver a
leer lo ya leido con la version nueva es `reextraer`: cuenta antes de pagar,
el presupuesto es un tope de lo que se paga, y lo que lee no es vigente
hasta `reextraer --activar`, que exige pasar la puerta de
`score --comparar-versiones`. `extract --estricta` o `--force` con almacen
sobre un documento cuya vigente es de otras versiones tambien deja una
candidata: ninguna via cambia de version sin la puerta.

El almacen esta en datos/bms.sqlite3, o donde diga --db o la variable BMS_DB;
los originales, en la carpeta documentos/ de al lado, y las anclas de la
auditoria en anclas.log, tambien al lado. Una orden sobre la base de prueba
(demo.sqlite3) lo dice antes de nada, en la salida de errores.
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
from .scoring import INYECCION, Report, load_ground_truth, score_document, format_report


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
    ruta = "saliente" if args.salientes else "entrante"
    with almacen:
        codigo = extraer_carpeta(
            _cliente_api(anthropic), pdfs, carpeta_out(Path(args.out), ruta),
            politica=ESTRICTA if args.estricta else CONSERVAR, forzar=args.force,
            almacen=almacen, ruta=ruta,
        )
        _anclar(almacen)
    return codigo


# Lo leido por la via de salida va aparte: importar-out lee cada carpeta con
# su via, y una venta mezclada en out/ volveria al almacen como compra.
CARPETA_SALIENTES = "salientes"


def carpeta_out(out: Path, ruta: str) -> Path:
    """Donde se guardan las extracciones de una via: out/ o, las de salida, out/salientes."""
    return out / CARPETA_SALIENTES if ruta == "saliente" else out


def _carpeta_de_la_otra_via(out_dir: Path, ruta: str) -> Path:
    """La carpeta de out/ de la otra via: lo leido alli ya esta pagado (extract no lo repite)."""
    return out_dir.parent if ruta == "saliente" else out_dir / CARPETA_SALIENTES


def _cliente_api(anthropic):
    """El cliente de la API. En el entorno de Docker, con la clave del secreto (un fichero que
    solo ve el lector, config.clave_api); fuera, la busca el en ANTHROPIC_API_KEY."""
    return anthropic.Anthropic(api_key=config.clave_api())


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
    almacen=None, ruta: str = "entrante",
) -> int:
    """El cuerpo de `extract`, con el cliente inyectado para poder probarlo.

    `ruta` es la via por la que llegan los PDF: entrante (lo que nos facturan)
    o saliente (lo que factura BM Support BV, `--salientes`). La pone quien
    lanza la orden y decide la direccion de cada factura; el modelo no.
    """
    model = config.model_id()
    print(f"Extrayendo {len(pdfs)} documentos con {model}")
    if ruta == "saliente":
        print("Via de salida: son facturas emitidas por BM Support BV (ventas); una que no lo "
              "sea queda bloqueada (A8)")
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
            forzar=forzar, informar=_imprimir_paso, ruta=ruta,
            otras_vias=[_carpeta_de_la_otra_via(out_dir, ruta)],
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
        if r.candidatas:
            print(f"  {r.candidatas} relecturas con otra version quedan como candidatas "
                  f"(en {out_dir}/reextraccion/): la vigente no cambia hasta "
                  "`bms-agent reextraer --activar`, que pasa la puerta")
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
    conciliacion = getattr(diferencia, "conciliacion", None)
    if conciliacion is not None and (conciliacion.automaticas or conciliacion.propuestas):
        print(f"Banco: {len(conciliacion.automaticas)} pago(s) casado(s) solo(s), "
              f"{len(conciliacion.propuestas)} propuesta(s) para confirmar")
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


def _registros_para_comparar(args: argparse.Namespace) -> tuple[list[dict], list[dict], str]:
    """Todas las extracciones (tambien las candidatas) y las que pueden ser la vigente.

    Del almacen si lo hay; si no, de out/ (las que pueden ser la vigente) y
    out/reextraccion/ (las candidatas). La anterior de la comparacion sale
    de las segundas: una candidata que nadie activo no es la referencia.
    """
    from .reextraccion import CARPETA_EXPORTACION, registros_vigentes_posibles

    ruta = _ruta_db(args.db)
    if not args.out_explicito and ruta.exists():
        with _abrir_almacen(args.db) as almacen:
            registros = [json.loads(f[0]) for f in almacen.conn.execute(
                "SELECT contenido_json FROM extraccion ORDER BY id")]
            anteriores = registros_vigentes_posibles(almacen.conn)
        return registros, anteriores, f"el almacen {ruta}"
    out = Path(args.out)
    anteriores = load_records(out, todas=True)
    return (anteriores + load_records(out / CARPETA_EXPORTACION, todas=True), anteriores,
            f"{out}/ y {out / CARPETA_EXPORTACION}/")


def _cmd_score(args: argparse.Namespace) -> int:
    args.out_explicito = args.out is not None
    args.out = args.out or "out"
    truth = load_ground_truth(args.ground_truth)
    if not truth:
        print(f"{args.ground_truth} esta vacio", file=sys.stderr)
        return 1

    from .compat import no_solicitados

    if args.comparar_versiones:
        from .reextraccion import objetivo_actual
        from .scoring import comparar_versiones, format_comparacion

        registros, anteriores, origen = _registros_para_comparar(args)
        comparacion = comparar_versiones(truth, registros, objetivo_actual(),
                                         inyeccion=args.inyeccion, anteriores=anteriores)
        print(f"Extracciones de {origen}\n")
        print(format_comparacion(comparacion))
        return 0 if comparacion.aprobada else 1

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
        # Lo que la version de esa extraccion no pidio no se puntua (compat).
        scores.append(score_document(
            source_name, payload["extraction"], expected,
            no_solicitados=no_solicitados(str(payload.get("schema_version")))))

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
               origenes_extra=args.origen, ruta_db=_ruta_db(args.db),
               contenedor=args.contenedor)
    except ValueError as exc:
        print(f"No se arranca el servidor: {exc}", file=sys.stderr)
        return 2
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    from .dashboard import construir_datos

    if args.v2:
        return _cmd_export_v2(args)
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


def _cmd_export_v2(args: argparse.Namespace) -> int:
    """El contrato v2 (docs/integracion-web.md) del almacen, en un fichero JSON. Solo lee.

    Sin almacen no hay contrato v2: el v1 (sin --v2) sigue leyendo out/ tal cual.
    """
    from .consultas import comprobar_v2, exportar_v2

    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}: el contrato v2 sale del almacen "
              "(bms-agent importar-out lo crea desde out/)", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        datos = exportar_v2(almacen.conn)
    errores = comprobar_v2(datos)
    if errores:  # nunca deberia pasar: es el codigo el que escribe el contrato
        print("El export no cumple el contrato v2:\n  " + "\n  ".join(errores), file=sys.stderr)
        return 1
    destino = Path(args.file if args.file != "datos.json" else "datos-v2.json")
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Contrato v2 ({datos['contrato']}): {len(datos['facturas'])} facturas a {destino}")
    if not datos["al_dia"]:
        print(f"  AVISO: el estado de las facturas es del {datos['estado_del']}; "
              "bms-agent recalcular --diaria lo pone al dia")
    print(f"  {destino.stat().st_size:,} bytes")
    return 0


def _cmd_coste(args: argparse.Namespace) -> int:
    from .coste import (
        Estimacion, agrupar_en_pasadas, contar_entrada, estimar_salida, formatear_estimacion,
        formatear_gastado, formatear_pasadas, formatear_por_version, formatear_relanzar,
        leer_documentos,
    )
    from .reextraccion import CARPETA_EXPORTACION

    # Lo gastado cuenta cada extraccion pagada, tambien las que ya no son la
    # vigente de su documento, las de `reextraer` (que se exportan aparte, en
    # out/reextraccion/) y las de las ventas (`extract --salientes`, en
    # out/salientes/). Lo que costaria relanzar va por documento.
    salientes = carpeta_out(Path(args.out), "saliente")
    documentos = leer_documentos(load_records(args.out, todas=True)
                                 + load_records(salientes, todas=True)
                                 + load_records(Path(args.out) / CARPETA_EXPORTACION, todas=True))
    print(formatear_gastado(documentos))
    if documentos:
        por_version = formatear_por_version(documentos)
        if por_version:
            print()
            print(por_version)
        print()
        print(formatear_pasadas(agrupar_en_pasadas(documentos)))
        print()
        print(formatear_relanzar(leer_documentos(load_records(args.out)
                                                 + load_records(salientes))))

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

    client = _cliente_api(anthropic)
    model = config.model_id()
    politica = ESTRICTA if args.estricta else CONSERVAR
    indice = indexar(args.out)
    salida = estimar_salida(documentos, modelo=model, esquema=config.SCHEMA_VERSION,
                            esfuerzo=config.effort())

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
        salida_baja=salida.bajo * nuevos, salida_alta=salida.alto * nuevos,
        salida_medida=salida.medida, origen_salida=salida.origen,
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
        for evento_id in cadena.restauraciones:
            avisos.append(f"la base se restauro desde una copia (evento {evento_id}): lo "
                          "firmado despues de esa copia ya no esta")
        if cadena.anclas_descartadas:
            avisos.append(f"{cadena.anclas_descartadas} anclas son de lo que sustituyo una "
                          "restauracion y no se comprueban (lo sustituido sigue en "
                          "antes-de-restaurar/)")
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
        con_cuentas = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cuenta_bancaria'"
        ).fetchone()
        if con_cuentas:
            from .cuentas import verificar as verificar_cuentas

            errores.extend(verificar_cuentas(conn))
        con_btw = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'periodo_btw'"
        ).fetchone()
        if con_btw:
            from .btw import verificar as verificar_btw

            errores.extend(verificar_btw(conn))

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
        # Lo de out/salientes entra por la via de salida (extract --salientes).
        salientes = carpeta_out(out_dir, "saliente")
        with transaccion(almacen.conn):
            hechos = [(out_dir, importar_out(almacen, out_dir, pdfs))]
            if salientes.is_dir():
                hechos.append((salientes, importar_out(almacen, salientes, pdfs,
                                                       ruta="saliente")))
            tipado = _tipar(almacen)
            tipado.recalculo = _recalcular(almacen, "importacion")
        _anclar(almacen)

    for carpeta, r in hechos:
        print(f"{r.ficheros} ficheros en {carpeta}/, sin ninguna llamada a la API")
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
            elif args.accion == "asegurar":
                codigo = _asegurar_persona(conn, args.nombre, args.rol)
                if codigo:
                    _anclar(almacen)
                    return codigo
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
# `usuario asegurar` con una persona que ya existe con otros roles: no se toca (persona.ps1).
SALIDA_OTRO_ROL = 3


def _asegurar_persona(conn, nombre: str, rol: str) -> int:
    """Que exista la persona NOMBRE (el nombre exacto) con el rol ROL y solo ese.

    Si no existe, se crea con ese rol. Si existe con ese rol, no se hace nada.
    Si existe con otros roles, no se cambia nada y sale SALIDA_OTRO_ROL: quien
    pidio dar acceso de consulta a alguien que ya es administrador no debe
    acabar entregando, sin saberlo, un token de administrador (persona.ps1
    pide el token solo si esto sale con 0).
    """
    from . import permisos

    existente = next((u for u in permisos.listar_usuarios(conn)
                      if u["nombre"] == nombre and not u["es_sistema"]), None)
    if existente is None:
        usuario_id = permisos.crear_usuario(conn, nombre)
        permisos.asegurar_roles_base(conn)
        permisos.asignar_rol(conn, usuario_id, rol)
        print(f"Persona {nombre} creada (id {usuario_id}) con el rol {rol}")
        return 0
    if existente["roles"] == [rol]:
        print(f"{nombre} ya existe con el rol {rol}")
        return 0
    actuales = ", ".join(existente["roles"]) or "sin roles"
    print(f"{nombre} ya existe con {actuales}, no con {rol}: no se cambia nada ni se da "
          f"token. Para cambiarle el rol: usuario asignar / usuario quitar", file=sys.stderr)
    return SALIDA_OTRO_ROL


def _persona_de_token(conn, token: str | None, accion: str) -> int | None:
    """La persona del token; si no vale, el intento queda en la auditoria y None."""
    from .permisos import PermisoDenegado, registrar_denegacion, usuario_por_token

    usuario_id = usuario_por_token(conn, token)
    if usuario_id is None:
        registrar_denegacion(conn, PermisoDenegado(
            None, "ver_facturas", "token ausente o no valido", accion))
    return usuario_id


def _unir_valores_de_accion(argv: list[str], opciones: set[str]) -> list[str]:
    """En `accion`, lo que sigue a una de sus opciones es su valor, aunque empiece por '-'.

    argparse toma por otra opcion cualquier valor que empiece por '-' y no
    sea un numero a su manera: un abono escrito "-1.234,56" o un token que
    empiece por '-' no llegaban a la orden ("expected one argument", salida
    2). `--opcion=valor` si lo acepta, y aqui se escribe asi. Solo en
    `accion` y en las ordenes de `btw` (lo declarado a devolver va en
    negativo), donde cada opcion lleva un valor: en otras ordenes hay
    opciones sin valor (--force). Si lo que sigue es otra opcion de la orden
    (o la ayuda), se deja como esta, para que argparse diga que falta el
    valor en vez de guardar "--db" como motivo.
    """
    if len(argv) < 2 or not (argv[0] == "accion" or (argv[0] == "btw" and argv[1] in _BTW)):
        return list(argv)
    no_es_valor = opciones | {"-h", "--help"}
    unidos = list(argv[:2])
    i = 2
    while i < len(argv):
        argumento = argv[i]
        siguiente = argv[i + 1] if i + 1 < len(argv) else None
        if (argumento in opciones and siguiente is not None
                and siguiente.split("=", 1)[0] not in no_es_valor):
            unidos.append(f"{argumento}={siguiente}")
            i += 2
        else:
            unidos.append(argumento)
            i += 1
    return unidos


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
    from .consultas import fuentes

    with _abrir_almacen(args.db) as almacen:
        filas = listado(almacen.conn, nivel=args.nivel, limite=args.limite)
        pasadas = [f for f in fuentes(almacen.conn) if f["caducada"]]
    for f in pasadas:
        print(f"AVISO (Z1): lo ultimo de {f['fuente']} ({f['tipo']}) es del {f['exportado']}, "
              f"{f['edad']} {f['unidad']}: lo que depende de esa fuente esta sin datos")
    for f in filas:
        print(f"{_SIMBOLO.get(f['nivel'], f['nivel'])} {f['puntos']:>3}  {f['id']:>5}  "
              f"{(f['numero'] or '(sin numero)'):<18} {(f['contraparte'] or '')[:28]:<28} "
              f"{f['total'] or '':>12}  {f['estado_revision'] or '':<17} {f['etiqueta']}")
        if f["motivos"]:
            print(f"{'':>12}{' · '.join(f['motivos'])}")
    return 0


def _cmd_resumen(args: argparse.Namespace) -> int:
    """El panel principal (§17): lo que entra y sale, la caja, la facturacion, las PO, el BTW
    y lo que pide atencion. Solo lee."""
    from .consultas import panel

    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        p = panel(almacen.conn)
    if args.json:
        print(json.dumps(p, ensure_ascii=False, indent=2))
        return 0
    print(f"Panel a {p['hoy']}" + ("" if p["al_dia"] else
                                   f" (AVISO: el estado es del {p['estado_del']}; "
                                   "bms-agent recalcular --diaria)"))
    for f in p["fuentes_caducadas"]:
        print(f"AVISO (Z1): lo ultimo de {f['fuente']} ({f['tipo']}) es del {f['exportado']}")
    for clave, titulo in (("dinero_entra", "Entra (cobros)"), ("dinero_sale", "Sale (pagos)")):
        b = p[clave]
        print(f"{titulo:<16} pendiente {b['pendiente']:>12} en {b['facturas']} · vencido "
              f"{b['vencido']:>12} · esta semana {b['semana']:>12} · este mes {b['mes']:>12}"
              f" · 30 dias {b['proximos_30']:>12}")
    caja = p["caja"]["ventanas"]
    print(f"{'Caja':<16} neto 30 dias {caja['proximos_30']['neto']:>12} · neto total "
          f"{caja['total']['neto']:>12} · estimado: "
          + (p["caja"]["estimado"].get("nota") or "ver flujo-caja"))
    fact = p["facturacion"]
    if fact["estado"] != "ok":
        print(f"{'Facturacion':<16} {fact['detalle']}")
    else:
        print(f"{'Facturacion':<16} sin facturar {fact['sin_facturar']['valor']} "
              f"({fact['sin_facturar']['periodos']} periodos) · periodos sin factura "
              f"{len(fact['periodos_sin_factura'])} · horas fuera de su venta "
              f"{len(fact['horas_sin_facturar'])} · diferencias con el planning "
              f"{fact['diferencias_planning']['hallazgos']}")
    po = p["ordenes_compra"]
    for lado, titulo in (("cliente", "PO de clientes"), ("proveedor", "PO de proveedor")):
        c = po[lado]
        print(f"{titulo:<16} {c['activas']} activas: valor {c['valor']} · consumido "
              f"{c['consumido']} · queda {c['restante']}")
    print(f"{'':<16} cerca del limite {len(po['cerca_del_limite'])} · cerca de caducar "
          f"{len(po['cerca_de_caducar'])} · caducadas {len(po['caducadas'])}"
          f" · se agotan antes {len(po['agotamiento_previsto'])}")
    b = p["btw"]
    plazo = b["proximo_plazo"]
    print(f"{'BTW ' + b['trimestre']:<16} ingresos {b['ingresos']} · IVA {b['iva_repercutido']}"
          f" · deducible {b['iva_deducible']} · saldo {b['saldo']} ({b['estado']})"
          + (f" · proximo plazo {plazo['trimestre']} el {plazo['limite_presentacion']}"
             if plazo else ""))
    a = p["atencion"]
    print(f"Atencion: {a['bloqueadas']} bloqueadas, {a['urgentes']} urgentes, "
          f"{a['excepciones']['abiertas']} excepciones abiertas")
    print(f"  compras vencidas {a['compras_vencidas']['facturas']} "
          f"({a['compras_vencidas']['pendiente']}) · ventas vencidas "
          f"{a['ventas_vencidas']['facturas']} ({a['ventas_vencidas']['pendiente']})")
    for c in a["categorias"]:
        if c["activos"] or c["aceptados"]:
            print(f"  {c['titulo']:<44} {c['activos']:>4} activos, {c['aceptados']} aceptados"
                  f"  ({', '.join(f'{r} {n}' for r, n in c['reglas'].items())})")
    return 0


def _cmd_buscar(args: argparse.Namespace) -> int:
    """La busqueda con los filtros del §18 (`--filtro nombre=valor`, repetible). Solo lee."""
    from .consultas import FILTROS, FiltroNoValido, buscar

    if args.filtros:
        for f in FILTROS.values():
            valores = f" ({', '.join(f.valores)})" if f.valores else ""
            print(f"  {f.nombre:<20} {f.descripcion}{valores}")
        return 0
    peticion: dict[str, list[str]] = {}
    for texto in args.filtro or []:
        nombre, igual, valor = texto.partition("=")
        if not igual:
            print(f"--filtro {texto!r}: se escribe nombre=valor", file=sys.stderr)
            return 2
        peticion.setdefault(nombre.strip(), []).append(valor)
    for nombre in ("orden", "limite", "pagina"):
        if getattr(args, nombre) is not None:
            peticion[nombre] = [str(getattr(args, nombre))]
    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        try:
            r = buscar(almacen.conn, peticion)
        except FiltroNoValido as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    if not r["al_dia"]:
        print(f"AVISO: el estado es del {r['estado_del']}; bms-agent recalcular --diaria")
    for f in r["facturas"]:
        print(f"{_SIMBOLO.get(f['nivel'], f['nivel'])} {f['id']:>5}  "
              f"{(f['numero'] or '(sin numero)'):<18} {(f['contraparte'] or '')[:28]:<28} "
              f"{f['fecha_factura'] or '':<10} {f['total'] or '':>12}  "
              f"{f['estado_pago'] or '':<10} {f['estado_revision'] or ''}")
    suma = r["suma"]
    if suma["mezcla"]:
        cifras = "; ".join(
            f"{titulo} ({suma[clave]['facturas']}) suman {suma[clave]['total']} y quedan "
            f"pendientes {suma[clave]['pendiente']}"
            for clave, titulo in (("compras", "compras"), ("ventas", "ventas")))
    else:
        cifras = f"suman {suma['total']} y quedan pendientes {suma['pendiente']}"
    print(f"{r['total']} factura(s); {cifras}"
          + (f"; {suma['no_cuentan']} no cuentan (anuladas, copias o sustituidas)"
             if suma["no_cuentan"] else "")
          + (f" (pagina {r['pagina']}, de {r['limite']} en {r['limite']})"
             if r["total"] > r["limite"] else ""))
    return 0


def _cmd_objetos(args: argparse.Namespace) -> int:
    """Los Objetos con sus ingresos, costes y margen, y lo que no es de ninguno (§5)."""
    from .consultas import objetos_resumen

    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        r = objetos_resumen(almacen.conn)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    print(f"{'Objeto':<20} {'ingresos':>12} {'costes':>12} {'margen':>12} {'%':>9}"
          f"   ({r['ano']}: ingresos, margen)")
    for o in r["objetos"]:
        s_, a = o["siempre"], o["ano"]
        print(f"{o['codigo'][:20]:<20} {s_['ingresos']:>12} {s_['costes']:>12} "
              f"{s_['margen']:>12} {s_['margen_pct'] or '-':>9}   {a['ingresos']}, {a['margen']}")
    sin = r["sin_objeto"]["total"]
    print(f"{'(sin Objeto)':<20} {sin['ingresos']:>12} {sin['costes']:>12}")
    t = r["totales"]
    print(f"{'base total':<20} {t['ingresos']:>12} {t['costes']:>12}"
          + (f"   ({t['sin_base']} factura(s) sin base o en otra moneda no suman)"
             if t["sin_base"] else ""))
    return 0


def _cmd_historial(args: argparse.Namespace) -> int:
    """La historia de una factura (§12): original, cambios, revisiones y avisos. Solo lee."""
    from .consultas import historial_factura

    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        try:
            h = historial_factura(almacen.conn, args.id)
        except LookupError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.json:
        print(json.dumps(h, ensure_ascii=False, indent=2))
        return 0
    d = h["documento"]
    print(f"Factura {h['numero'] or '(sin numero)'}"
          + (f" · original {d['nombre']} ({d['sha256'][:12]}, "
             + ("guardado" if d["conservado"] else "NO guardado: Q4") + ")" if d else ""))
    for r in h["relaciones"]:
        otra = r["otra_numero"] or f"factura {r['otra_id']}"
        print(f"  relacion: " + (f"esta factura {r['tipo']} {otra}" if r["papel"] == "origen"
                                 else f"{otra} {r['tipo']} esta factura")
              + f" ({r['estado']}" + (", retirada" if r["retirada"] else "") + ")")
    for e in h["eventos"]:
        quien = e["usuario"] or e["actor"]
        print(f"  {e['en']}  {e['tipo']} ({quien})" + (f": {e['motivo']}" if e["motivo"] else ""))
        for c in e["cambios"]:
            if e["persona"] or args.todo:
                print(f"      {c['tabla']}.{c['campo']}: {c['anterior_texto'] or '-'} -> "
                      f"{c['nuevo_texto'] or '-'} [{c['fuente_nueva']}]"
                      + (f" «{c['motivo']}»" if c["motivo"] else ""))
    for r in h["revisiones"]:
        print(f"  revision: {r['resultado']} por {r['usuario']} el {r['en']}"
              + ("" if r["vigente"] else " (ya no vale)"))
    for hz in h["hallazgos"]:
        print(f"  {hz['regla']} {hz['titulo']} ({hz['estado']}): "
              + " · ".join(f"{e['tipo']} {e['en'][:10]}" for e in hz["eventos"]))
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
    for r in ficha["relaciones"]:
        print(f"  relacion {r['id']} {r['estado']}{' (retirada)' if r['retirada'] else ''}: "
              f"{r['origen_numero']} {r['tipo']} {r['destino_numero']} (de {r['fuente']})")
    return 0


def _cmd_relaciones(args: argparse.Namespace) -> int:
    """Las relaciones propuestas: las confirma o rechaza una persona (accion confirmar_relacion)."""
    from .relaciones import propuestas

    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        filas = propuestas(almacen.conn)
        numeros = {f[0]: f[1] for f in almacen.conn.execute("SELECT id, numero FROM factura")}
    for r in filas:
        print(f"  relacion {r['id']} (rev {r['rev']}, de {r['fuente']}): factura {r['origen_id']} "
              f"{numeros.get(r['origen_id']) or ''} {r['tipo']} factura {r['destino_id']} "
              f"{numeros.get(r['destino_id']) or ''}"
              + (f" — {r['evidencia_doc']}" if r["evidencia_doc"] else ""))
    if not filas:
        print("No hay relaciones por confirmar.")
    else:
        print("\nSe confirman con `bms-agent accion confirmar_relacion --relacion-id N --rev R "
              "--motivo ...` o se rechazan con `bms-agent accion rechazar_relacion` (permiso "
              "anular_acreditar).")
    return 0


def _cmd_partes(args: argparse.Namespace) -> int:
    """Los proveedores o los clientes, con lo pendiente, lo vencido y lo facturado."""
    from . import consultas

    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        filas = (consultas.proveedores if args.tabla == "proveedor"
                 else consultas.clientes)(almacen.conn)
    if args.json:
        print(json.dumps(filas, ensure_ascii=False, indent=2, default=str))
        return 0
    for f in filas:
        print(f"{f['id']:>5} {f['nombre'][:40]:<40} {f['facturas']:>4} facturas  pendiente "
              f"{f['pendiente']:>12}  vencido {f['vencido']:>12}"
              + ("" if f["activo"] else "  (inactivo)"))
    if not filas:
        print(f"No hay ningun {args.tabla}.")
    return 0


def _cmd_parte(args: argparse.Namespace) -> int:
    """La vista de un proveedor (§3) o de un cliente (§4). Solo lee."""
    from . import consultas

    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        try:
            vista = getattr(consultas, args.tabla)(almacen.conn, args.id)
        except LookupError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.json:
        print(json.dumps(vista, ensure_ascii=False, indent=2, default=str))
        return 0
    pagado = "pagado" if args.tabla == "proveedor" else "cobrado"
    print(f"{args.tabla.capitalize()} {vista['id']} {vista['nombre']}"
          f"{' (Exact ' + vista['exact_id'] + ')' if vista['exact_id'] else ''}, a {vista['hoy']}")
    print(f"  pendiente  {vista['pendiente']:>12}  en {vista['abiertas']} facturas")
    print(f"  vencido    {vista['vencido']:>12}  en {vista['vencidas']} facturas")
    ano, siempre = vista["ano_facturado"], vista["siempre_facturado"]
    print(f"  {vista['ano']}: facturado {ano['total']} ({ano['base']} sin IVA), {pagado} "
          f"{vista['ano_pagado']}")
    print(f"  siempre: facturado {siempre['total']} ({siempre['base']} sin IVA) en "
          f"{siempre['facturas']} facturas, {pagado} {vista['siempre_pagado']}")
    tipico = vista["importe_tipico"]
    if tipico["facturas"]:
        print(f"  importe tipico: media {tipico['media']}, mediana {tipico['mediana']}")
    plazo = vista["plazo_de_pago"]
    if plazo["pagadas"]:
        print(f"  plazo de pago: {plazo['media_dias']} dias de media ({plazo['pagadas']} "
              f"pagadas), {plazo['tarde']} tarde")
    for o in vista["por_objeto"]:
        print(f"  Objeto {o['objeto']:<20} {o['importe']:>12}  {o['horas'] or '0'} horas")
    if "ibanes" in vista:
        for c in vista["ibanes"]["registro"]:
            print(f"  cuenta {c['iban']} {c['estado']}" + (" (se le puede pagar)"
                                                         if c["pagable"] else ""))
    for h in vista["avisos"]["hallazgos"]:
        print(f"  aviso {h['regla']} {h['estado']} ({h['severidad']}), factura "
              f"{h['factura_id']}: {h['detalle']}")
    for f in vista["historial"][:20]:
        print(f"  {f['fecha_factura'] or '-':<10} {f['numero'] or '(sin numero)':<16} "
              f"{f['total'] or '-':>12} {f['estado_pago'] or '-'}")
    return 0


def _cmd_ordenes(args: argparse.Namespace) -> int:
    """Las ordenes de compra, la mas urgente primero (§6, §8). Solo lee."""
    from . import consultas

    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        filas = consultas.ordenes_compra(almacen.conn)
    if args.json:
        print(json.dumps(filas, ensure_ascii=False, indent=2, default=str))
        return 0
    for o in filas:
        parte = ("de " if o["lado"] == "cliente" else "a ") + (o["parte"]["nombre"] or "?")
        print(f"{o['id']:>5} {o['numero'][:18]:<18} {parte[:30]:<30} valor {o['valor']:>12}  "
              f"consumido {o['consumido']:>12} ({o['consumido_pct']})  queda "
              f"{o['restante']:>12}  fin {o['fecha_fin'] or '-'}  {o['nivel']}"
              + ("  (cerrada)" if o["cerrada"] else ""))
    if not filas:
        print("No hay ninguna orden de compra. Se registran con `bms-agent importar po_csv "
              "ordenes_compra FICHERO` o con la accion registrar_po.")
    return 0


def _cmd_orden(args: argparse.Namespace) -> int:
    """Una orden de compra (§6): lo consumido factura a factura, modificaciones y prevision."""
    from . import consultas

    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        try:
            o = consultas.orden_compra(almacen.conn, args.id)
        except LookupError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.json:
        print(json.dumps(o, ensure_ascii=False, indent=2, default=str))
        return 0
    lado = "del cliente" if o["lado"] == "cliente" else "al proveedor"
    print(f"PO {o['numero']} {lado} {o['parte']['nombre']}, a {o['hoy']}"
          + (" (cerrada)" if o["cerrada"] else ""))
    print(f"  vigencia   {o['fecha_inicio'] or '...'} a {o['fecha_fin'] or '...'}"
          + (f" (fin original {o['fecha_fin_original']})"
             if o["fecha_fin"] != o["fecha_fin_original"] else ""))
    print(f"  valor      {o['valor']:>12}  (original {o['valor_original']}), sin IVA")
    print(f"  consumido  {o['consumido']:>12}  ({o['consumido_pct']})")
    print(f"  queda      {o['restante']:>12}  ({o['restante_pct']})")
    p = o["prevision"]
    print(f"  ritmo      {p['consumido_ventana']} en {p['dias']} dias desde el {p['desde']}: "
          + (f"se agotaria el {p['agotamiento']}" if p["agotamiento"]
             else "a este ritmo no se agota"))
    for clave, nombre in (("planificado", "planificado"), ("sin_facturar", "sin facturar")):
        bloque = o[clave]
        if bloque["estado"] == "ok":
            print(f"  {nombre:<11}{bloque['valor']:>12}  (planning)"
                  + (f"; {bloque['nota']}" if bloque.get("nota") else ""))
        else:
            print(f"  {nombre}: {bloque['detalle']}")
    print("  Objetos: " + (", ".join(x["codigo"] for x in o["objetos"])
                           or "cualquiera de la parte"))
    for f in o["facturas"]:
        print(f"  {f['fecha_factura'] or '(sin fecha)':<11} {f['numero'] or '-':<16} "
              f"{f['importe']:>12}  quedaban {f['quedaba']}")
    for m in o["modificaciones"]:
        cambios = ", ".join(x for x in (
            f"valor {m['valor_nuevo']}" if m["valor_nuevo"] else "",
            f"fin {m['fecha_fin_nueva']}" if m["fecha_fin_nueva"] else "") if x)
        print(f"  modificacion desde {m['fecha']}: {cambios} ({m['usuario']}: {m['motivo']})")
    for h in o["avisos"]["hallazgos"]:
        print(f"  aviso {h['regla']} {h['estado']} ({h['severidad']}): {h['detalle']}")
    return 0


def _cmd_objeto(args: argparse.Namespace) -> int:
    """Un Objeto (§5) y sus ordenes de compra. Solo lee."""
    from . import consultas

    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        try:
            v = consultas.objeto(almacen.conn, args.id)
        except LookupError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.json:
        print(json.dumps(v, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"Objeto {v['codigo']}" + (f" ({v['nombre']})" if v["nombre"] else "")
          + f", cliente {v['cliente']['nombre'] or '-'}" + (", pide PO" if v["requiere_po"]
                                                              else ""))
    for o in v["ordenes_compra"]:
        print(f"  PO {o['numero']:<18} {o['lado']:<9} valor {o['valor']:>12}  consumido "
              f"{o['consumido']:>12} ({o['consumido_pct']})  queda {o['restante']:>12}  "
              f"de este Objeto {o['consumido_objeto']}")
    if not v["ordenes_compra"]:
        print("  Sin ordenes de compra.")
    h = v["horas"]
    if h["planning"] == "sin_datos":
        print("  Horas: sin planning importado, solo las facturadas.")
    elif h["planning"] == "caducado":
        print("  Horas: el planning esta pasado de su frescura (Z1): puede no ser el de hoy.")
    print(f"  {'semana':<10} {'planif.':>8} {'valid.':>8} {'prov.':>8} {'cliente':>8} "
          f"{'sin fact.':>9}")
    for fila in (*h["semanas"], {**h["total"], "semana": "total"}):
        print(f"  {fila['semana']:<10} {fila['planificadas'] or '-':>8} "
              f"{fila['validadas'] or '-':>8} {fila['proveedor'] or '-':>8} "
              f"{fila['cliente'] or '-':>8} {fila['sin_facturar'] or '-':>9}")
    eco = v["economia"]
    for nombre, b in (("periodo " + eco["periodo"]["desde"] + " a " + eco["periodo"]["hasta"],
                       eco["periodo"]), (f"ano {eco['ano']['ano']}", eco["ano"]),
                      ("de siempre", eco["siempre"])):
        print(f"  {nombre:<32} ingresos {b['ingresos']:>12}  costes {b['costes']:>12}  "
              f"margen {b['margen']:>12} ({b['margen_pct'] or '-'})")
    e = h["esperado"]
    print(f"  esperado: por cobrar {e['entrante']}, por pagar {e['saliente']}"
          + (f"; estimado aparte: por cobrar {e['entrante_estimado']}, por pagar "
             f"{e['saliente_estimado']}" if e["entrante_estimado"] is not None else ""))
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
    """Apunta un fichero de config/ (prioridad, reglas o empresa) y recalcula con el."""
    from .hallazgos import recalcular
    from .permisos import PermisoDenegado, orden_auditada
    from .almacen import DatosDePrueba
    from .politica import PoliticaNoValida, cargar
    from .prioridad import PesosNoValidos

    fichero = Path(args.fichero)
    if not fichero.is_file():
        print(f"No existe {fichero}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        usuario_id = _persona_con_token(almacen, args, "cargar la politica")
        if usuario_id is None:
            _anclar(almacen)
            return 1
        try:
            with orden_auditada(almacen.conn):
                resumen, nuevo = cargar(almacen.conn, fichero, usuario_id)
                diferencia = recalcular(almacen.conn, motivo="manual", usuario_id=usuario_id)
        except (PesosNoValidos, PoliticaNoValida, PermisoDenegado, DatosDePrueba) as exc:
            print(f"No se carga {fichero}: {exc}", file=sys.stderr)
            _anclar(almacen)
            return 1
        _anclar(almacen)
    print(f"{fichero}: {'cargado' if nuevo else 'ya era la version vigente'} ({resumen})")
    cambios = diferencia.estados.prioridades if diferencia.estados else []
    print(f"  prioridades que cambian: {len(cambios)}")
    return 0


def _persona_con_token(almacen, args, accion: str) -> int | None:
    token = getattr(args, "token", None) or os.environ.get(VARIABLE_TOKEN)
    usuario_id = _persona_de_token(almacen.conn, token, accion)
    if usuario_id is None:
        print("Hace falta el token de una persona activa (--token o BMS_TOKEN; "
              "lo da `bms-agent usuario token NOMBRE`)", file=sys.stderr)
    return usuario_id


_ETIQUETAS_REEXTRACCION = {"candidata": "leida", "reintento": "REINTENTO", "lote": "lote"}


def _imprimir_reextraccion(tipo: str, nombre: str, detalle: str) -> None:
    print(f"  {_ETIQUETAS_REEXTRACCION.get(tipo, tipo):<10} {nombre}: {detalle}")


def _imprimir_resultado_reextraccion(r) -> None:
    if r.sin_terminar:
        print(f"Reextraccion {r.reextraccion_id}: el lote {r.lote_id} no ha terminado; "
              "vuelve a probar mas tarde")
        return
    if r.estado == "esperando_lote":
        print(f"Reextraccion {r.reextraccion_id}: lote {r.lote_id} enviado. Cuando termine "
              f"(horas): bms-agent reextraer --recoger {r.reextraccion_id}")
        return
    if r.estado == "lote_desconocido":
        print(f"Reextraccion {r.reextraccion_id}: la API no contesto al mandar el lote y no se "
              "sabe si lo acepto. Sus documentos no se vuelven a pagar mientras tanto: "
              f"bms-agent reextraer --recoger {r.reextraccion_id} lo busca en la API")
        return
    print(f"Reextraccion {r.reextraccion_id}: {len(r.candidatas)} candidatas, "
          f"{len(r.reintentos)} para reintentar (--reintentos)")
    for documento_id, motivo, detalle in r.reintentos:
        print(f"  reintento documento {documento_id}: {motivo} {detalle}".rstrip())
    if r.candidatas:
        print("Las candidatas NO son vigentes: nada cambia en las facturas hasta "
              "`bms-agent reextraer --activar`, que pasa la puerta de "
              "`score --comparar-versiones`.")


def _cmd_reextraer(args: argparse.Namespace) -> int:
    """Vuelve a leer documentos ya leidos con la version de config.py (spec §10).

    Cuenta antes de pagar, se niega si la estimacion alta pasa del
    presupuesto, y sin --presupuesto solo estima. Lo leido queda como
    candidata; --activar la hace vigente solo si pasa la puerta.
    """
    from datetime import date

    from .coste import formatear_estimacion
    from .permisos import PermisoDenegado
    from .reextraccion import (
        Criterio, PresupuestoInsuficiente, PuertaCerrada, activar, cargar, ejecutar, estimar,
        leer_presupuesto, objetivo_actual, recoger, registrar_rechazo, seleccionar,
    )
    from .scoring import format_comparacion

    try:
        desde = date.fromisoformat(args.desde) if args.desde else None
        presupuesto = leer_presupuesto(args.presupuesto) if args.presupuesto is not None else None
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    criterio = Criterio(abiertas=args.abiertas, desde=desde, proveedor=args.proveedor,
                        sin_objeto=args.sin_objeto, reintentos=args.reintentos,
                        limite=args.limite)
    if criterio.vacio() and not args.activar and args.recoger is None:
        print("Di que volver a leer (--abiertas, --desde, --proveedor, --sin-objeto o "
              "--reintentos), --recoger N o --activar", file=sys.stderr)
        return 2
    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}: reextraer lee los originales de alli",
              file=sys.stderr)
        return 1
    objetivo = objetivo_actual()
    modelo, prompt, esquema = objetivo
    codigo = 0
    with _abrir_almacen(args.db) as almacen:
        conn = almacen.conn
        client = None
        if args.recoger is not None or not criterio.vacio():
            try:
                import anthropic
            except ImportError:
                print("Falta el paquete anthropic. Instala con: pip install -e .", file=sys.stderr)
                return 2
            client = _cliente_api(anthropic)
        token = getattr(args, "token", None) or os.environ.get(VARIABLE_TOKEN)
        lanzada_por = None
        if token:
            from .permisos import usuario_por_token

            lanzada_por = usuario_por_token(conn, token)

        if args.recoger is not None:
            try:
                r = recoger(client, almacen, args.recoger, out_dir=args.out,
                            informar=_imprimir_reextraccion)
            except (LookupError, ValueError) as exc:
                print(str(exc), file=sys.stderr)
                _anclar(almacen)
                return 1
            _imprimir_resultado_reextraccion(r)

        if not criterio.vacio():
            try:
                seleccion = seleccionar(conn, criterio, objetivo)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                _anclar(almacen)
                return 2
            print(f"Volver a leer con {modelo}, prompt {prompt}, esquema {esquema}"
                  f"{' (por lotes)' if args.lote else ''}")
            print(f"  seleccionados: {len(seleccion.documentos)}; omitidos: "
                  f"{len(seleccion.omitidos)}")
            for documento_id, motivo in seleccion.omitidos:
                print(f"    documento {documento_id}: {motivo}")
            if seleccion.documentos:
                from .almacen.documentos import DocumentoCorrupto

                try:
                    documentos = cargar(almacen, seleccion)
                except DocumentoCorrupto as exc:
                    print(f"No se paga nada: {exc} (bms-agent db verificar)", file=sys.stderr)
                    _anclar(almacen)
                    return 1
                estimacion = estimar(client, conn, documentos, objetivo, lote=args.lote,
                                     ya_leidos=seleccion.ya_leidos)
                print()
                print(formatear_estimacion(estimacion))
                print()
                if presupuesto is None:
                    print("Sin --presupuesto solo se estima: no se ha pagado nada.")
                else:
                    try:
                        r = ejecutar(client, almacen, seleccion, documentos, estimacion,
                                     presupuesto, criterio=criterio, objetivo=objetivo,
                                     out_dir=args.out, lote=args.lote,
                                     iniciada_por=lanzada_por, informar=_imprimir_reextraccion)
                    except PresupuestoInsuficiente as exc:
                        registrar_rechazo(conn, exc, criterio=criterio, objetivo=objetivo,
                                          iniciada_por=lanzada_por)
                        print(f"No se paga: {exc}", file=sys.stderr)
                        codigo = 1
                    else:
                        _imprimir_resultado_reextraccion(r)

        if args.activar and codigo == 0:
            persona = _persona_con_token(almacen, args, "activar una reextraccion")
            if persona is None:
                _anclar(almacen)
                return 1
            truth = load_ground_truth(args.ground_truth)
            try:
                resultado = activar(almacen, persona, truth, objetivo=objetivo,
                                    inyeccion=args.inyeccion)
            except PuertaCerrada as exc:
                print(format_comparacion(exc.comparacion))
                print("\nNo se activa nada.", file=sys.stderr)
                codigo = 1
            except PermisoDenegado as exc:
                print(f"No se activa: {exc}", file=sys.stderr)
                codigo = 1
            else:
                print(format_comparacion(resultado.comparacion))
                print(f"\nActivadas: {len(resultado.activadas)} (comparacion "
                      f"{resultado.comparacion_sha256[:12]})")
                for a in resultado.activadas:
                    print(f"  documento {a.documento_id}: extraccion {a.extraccion_id} "
                          f"(antes {a.anterior_id}), factura {a.factura_id} {a.accion}")
                    for campo in a.contradichos:
                        print(f"    sin resolver (M1): {campo} lo corrigio una persona y la "
                              "lectura nueva dice otra cosa")
                    for linea_id in a.sin_casar:
                        print(f"    linea {linea_id} editada a mano y sin casar (M2)")
                if resultado.diferencia is not None:
                    _imprimir_recalculo(resultado.diferencia)
        _anclar(almacen)
    return codigo


# Salida de `importar` cuando el fichero se ha leido pero no ha entrado entero: quien lo
# lanza (importar.ps1) decide con esto si el fichero sale del buzon, sin leer el texto.
SALIDA_RECHAZADA = 3
SALIDA_PARCIAL = 4


def _salida_de_importar(lotes) -> int:
    """0 si todo entro; SALIDA_RECHAZADA si algun lote no entro (tambien uno ya intentado y
    rechazado: ese mismo fichero no entrara nunca); SALIDA_PARCIAL si entro con filas
    rechazadas."""
    estados = {lote.estado for lote in lotes}
    if "rechazada" in estados:
        return SALIDA_RECHAZADA
    return SALIDA_PARCIAL if "parcial" in estados else 0


def _cmd_importar(args: argparse.Namespace) -> int:
    """Importa un fichero de un maestro con su mapeo (spec §9). Cero llamadas a la API.

    Sale con 0 si todo entra, SALIDA_RECHAZADA si un lote no entra y
    SALIDA_PARCIAL si entra con filas rechazadas: un script no puede dar por
    importado un fichero que no entro.
    """
    from datetime import date, datetime, timezone

    from .importadores.registrar import importar_fichero
    from .importadores.tabular import FicheroIlegible, MapeoNoValido
    from .permisos import PermisoDenegado

    fichero = Path(args.fichero)
    if not fichero.is_file():
        print(f"No existe {fichero}", file=sys.stderr)
        return 1
    cubre = {}
    for nombre in ("desde", "hasta"):
        texto = getattr(args, nombre, None)
        if texto:
            try:
                cubre[nombre] = date.fromisoformat(texto)
            except ValueError:
                print(f"--{nombre} es una fecha AAAA-MM-DD, no {texto!r}", file=sys.stderr)
                return 1
    if (cubre or args.confirmar) and (args.fuente, args.tipo) != ("trnsprnt", "planning"):
        print("--desde, --hasta y --confirmar solo valen para el planning (trnsprnt planning)",
              file=sys.stderr)
        return 1
    if args.exportado:
        try:
            dia = date.fromisoformat(args.exportado)
        except ValueError:
            print(f"--exportado es una fecha AAAA-MM-DD, no {args.exportado!r}", file=sys.stderr)
            return 1
        exportado = datetime(dia.year, dia.month, dia.day, 12, tzinfo=timezone.utc)
    else:
        # Sin decirlo, cuenta el dia en que se guardo el fichero: lo que mide la
        # frescura (Z1) es cuando se saco del sistema, no cuando se importa. Una
        # fecha de fichero futura (un reloj mal puesto) cuenta como ahora; una
        # --exportado futura la rechaza el importador.
        exportado = min(datetime.fromtimestamp(fichero.stat().st_mtime, tz=timezone.utc),
                        datetime.now(timezone.utc))
    with _abrir_almacen(args.db) as almacen:
        usuario_id = _persona_con_token(almacen, args, f"importar {args.fuente}/{args.tipo}")
        if usuario_id is None:
            _anclar(almacen)
            return 1
        try:
            r = importar_fichero(almacen, args.fuente, args.tipo, fichero,
                                 lanzado_por=usuario_id, mapeo=args.mapeo,
                                 exportado_en=exportado, simular=args.simular,
                                 cubre_desde=cubre.get("desde"), cubre_hasta=cubre.get("hasta"),
                                 confirmar=args.confirmar)
        except (PermisoDenegado, MapeoNoValido, FicheroIlegible, ValueError) as exc:
            print(f"No se importa: {exc}", file=sys.stderr)
            _anclar(almacen)
            return 1
        _anclar(almacen)
    print(f"{fichero} con el mapeo {r.mapeo}" + (" (simulado: no se ha escrito nada)"
                                               if r.simulada else ""))
    for lote in r.lotes:
        if lote.repetida:
            print(f"  {lote.tipo}: ya importado (importacion {lote.importacion_id}, "
                  f"{lote.estado}): no se hace nada"
                  + ("; este mismo fichero no entrara: hay que sacar uno nuevo"
                     if lote.estado == "rechazada" else ""))
            continue
        print(f"  {lote.tipo}: {lote.estado}; {lote.filas_leidas} filas, {lote.aceptadas} "
              f"aceptadas, {len(lote.rechazos)} rechazadas; {len(lote.nuevos)} filas nuevas, "
              f"{len(lote.cambiados)} campos cambiados")
        for tabla, fila_id in lote.retirados:
            print(f"    retirado: {tabla} {fila_id} ya no esta en la foto completa (inactivo)")
        for aviso in lote.avisos:
            print(f"    aviso: {aviso}")
        for tabla, fila_id, campo in lote.sin_resolver:
            print(f"    sin resolver (M1): {tabla} {fila_id} {campo} lo puso una persona y la "
                  "importacion dice otra cosa")
        for maestro in lote.cuentas:
            print(f"    cuentas: {maestro.vistas} en el fichero, {len(maestro.nuevas)} nuevas, "
                  f"{len(maestro.ausentes)} que ya no estan"
                  + (" (primer maestro: heredadas, por atestar)" if maestro.baseline else ""))
        for rechazo in lote.rechazos:
            print(f"    fila {rechazo.fila} ({rechazo.codigo}): {rechazo.motivo}")
    if r.recalculo is not None:
        _imprimir_recalculo(r.recalculo)
    return _salida_de_importar(r.lotes)


_IBAN = {"verificar": "verificar_iban", "rechazar": "rechazar_iban",
         "atestar": "atestar_iban", "telefono": "fijar_telefono_verificacion"}


def _cmd_iban(args: argparse.Namespace) -> int:
    """El registro de cuentas: verlo, verificar, rechazar, atestar y el telefono de verificacion."""
    if args.accion == "listar":
        from .consultas import cuentas

        ruta = _ruta_db(args.db)
        if not ruta.exists():
            print(f"No existe el almacen {ruta}", file=sys.stderr)
            return 1
        with _abrir_almacen(args.db) as almacen:
            filas = cuentas(almacen.conn)
        for c in filas:
            marcas = [m for m, si in (("pagable", c["pagable"]), ("en Exact", c["en_exact"]))
                      if si]
            print(f"{c['id']:>5} {c['proveedor'][:30]:<30} {c['iban']:<34} {c['estado']:<11}"
                  f"{', '.join(marcas)}"
                  + (f"  cambio sin verificar: {c['cambios']}" if c["cambios"] else "")
                  + (f"  verificacion que no vale: {c['ineficaz']}" if c["ineficaz"] else ""))
        if not filas:
            print("El registro de cuentas esta vacio: entra con `bms-agent importar exact "
                  "proveedores FICHERO`.")
        return 0
    args.nombre = _IBAN[args.accion]
    return _cmd_accion(args)


def _cmd_fuentes(args: argparse.Namespace) -> int:
    """De cuando es lo ultimo de cada fuente, y si esta pasada de su limite (Z1)."""
    from .consultas import fuentes

    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        filas = fuentes(almacen.conn)
    for f in filas:
        estado = "PASADA" if f["caducada"] else "al dia" if f["caducada"] is False else ""
        print(f"{f['fuente']:<12} {f['tipo']:<12} exportado {f['exportado'] or '-':<10} "
              f"({f['edad']} {f['unidad']}, limite "
              f"{f['limite'] if f['limite'] is not None else '-'}) "
              f"{estado}")
    if not filas:
        print("Todavia no se ha importado ninguna fuente.")
    return 0


def _euros(cent: int | None) -> str:
    if cent is None:
        return "-"
    from .almacen.unidades import de_cent
    from .reglas.base import euros_texto

    return euros_texto(de_cent(cent))


def _cmd_pagos(args: argparse.Namespace) -> int:
    """Los movimientos del banco, lo que esta sin casar y las propuestas por confirmar."""
    from . import pagos

    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        conn = almacen.conn
        if args.factura is not None:
            datos = pagos.de_factura(conn, args.factura)
            s = datos["saldo"]
            if s is None:
                print(f"No hay factura {args.factura}", file=sys.stderr)
                return 1
            print(f"Factura {args.factura}: total {_euros(s['total_cent'])}, pagado "
                  f"{_euros(s['pagado_cent'])} ({s['fuente'] or 'nada'}), quedan "
                  f"{_euros(s['pendiente_cent'])}" + (" (pagada)" if s["pagada"] else ""))
            for a in datos["aplicaciones"]:
                print(f"  pago {a['id']} (rev {a['rev']}): {_euros(a['importe_cent'])} del "
                      f"{a['fecha_pago']}, {a['fuente']}/{a['metodo']}, {a['estado']}"
                      + (f", movimiento {a['movimiento_id']}" if a["movimiento_id"] else "")
                      + (f" ({a['regla']})" if a["regla"] else ""))
            return 0
        if args.propuestas:
            filas = pagos.propuestas(conn)
            for f in filas:
                print(f"pago {f['id']} (rev {f['rev']}): {_euros(f['importe_cent'])} del "
                      f"{f['fecha_pago']} a la factura {f['numero'] or f['factura_id']} "
                      f"(movimiento {f['movimiento_id']}, coincide {f['regla']})")
            if not filas:
                print("No hay pagos propuestos por confirmar.")
            return 0
        filas = pagos.movimientos(conn, sin_casar=args.sin_casar, limite=args.limite)
        for m in filas:
            quien = m["contraparte_nombre_doc"] or m["contraparte_iban"] or "-"
            estado = ("casado" if m["confirmadas"] else
                      "propuesto" if m["propuestas"] else "sin casar")
            importe = (_euros(m["importe_cent"]) if m["importe_cent"] is not None
                       else m["importe_crudo"])
            print(f"{m['id']:>6} {m['fecha_contable']} {importe:>14} {quien[:30]:<30} {estado}")
        if not filas:
            print("No hay movimientos" + (" sin casar." if args.sin_casar else "."))
    return 0


def _cmd_flujo_caja(args: argparse.Namespace) -> int:
    """El flujo de caja: lo esperado por ventanas, lo movido y el estimado aparte."""
    import json
    from datetime import date

    from . import flujo_caja
    from .almacen import reloj_de

    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}", file=sys.stderr)
        return 1
    try:
        desde = date.fromisoformat(args.desde) if args.desde else None
        hasta = date.fromisoformat(args.hasta) if args.hasta else None
        hoy = date.fromisoformat(args.hoy) if args.hoy else None
    except ValueError as exc:
        print(f"Una fecha se escribe AAAA-MM-DD: {exc}", file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        try:
            datos = flujo_caja.flujo(almacen.conn, hoy or reloj_de(almacen.conn).hoy(),
                                     desde=desde, hasta=hasta)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.json:
        print(json.dumps(datos, ensure_ascii=False, indent=2))
        return 0
    nombres = {"vencido": "vencido", "semana": "esta semana", "mes": "este mes",
               "proximos_30": "proximos 30 dias", "periodo": "periodo", "sin_fecha": "sin fecha",
               "total": "total"}
    print(f"Flujo de caja a {datos['hoy']} ({datos['facturas']} facturas en juego)")
    print(f"  {'':<18} {'entrada':>14} {'salida':>14} {'neto':>14}")
    for clave, nombre in nombres.items():
        entrada = datos["esperado"]["entrada"][clave]
        if entrada is None:
            continue
        salida = datos["esperado"]["salida"][clave]
        print(f"  {nombre:<18} {_euros(entrada):>14} {_euros(salida):>14} "
              f"{_euros(datos['esperado']['neto'][clave]):>14}")
    real = datos["real"]
    for clave, nombre in (("semana", "semana en curso"), ("mes", "mes en curso"),
                          ("periodo", "periodo")):
        if real["cobrado"][clave] is None:
            continue
        print(f"  cobrado/pagado {nombre} (banco): {_euros(real['cobrado'][clave])} / "
              f"{_euros(real['pagado'][clave])}")
        for linea, texto in (("sin_casar", "sin casar con facturas"),
                             ("segun_exact", "segun Exact, sin el banco"),
                             ("a_mano", "a mano, sin el banco")):
            cobrado, pagado = real[linea]["cobrado"][clave], real[linea]["pagado"][clave]
            if cobrado or pagado:
                print(f"    {texto}: {_euros(cobrado)} / {_euros(pagado)}")
    estimado = datos["estimado"]
    if estimado["importe_cent"] is not None:
        print(f"  estimado (aparte, sin IVA): por cobrar "
              f"{_euros(estimado['entrada_sin_facturar_cent'])} sin facturar y "
              f"{_euros(estimado['entrada_planificada_cent'])} planificado; por pagar "
              f"{_euros(estimado['salida_sin_facturar_cent'])} sin facturar y "
              f"{_euros(estimado['salida_planificada_cent'])} planificado")
    print(f"  estimado: {estimado['nota']}")
    return 0


_BTW = {"listo": "btw_lista_para_revision", "reabrir": "btw_reabrir",
        "anotar": "btw_anotar_presentacion"}


def _cmd_btw(args: argparse.Namespace) -> int:
    """El BTW: ver un trimestre o el resumen, exportar la hoja de trabajo y su estado.

    Ninguna de estas ordenes presenta nada: `anotar` apunta la presentacion
    que hizo una persona en el portal de la Belastingdienst.
    """
    from . import btw

    if args.accion in _BTW:
        args.nombre = _BTW[args.accion]
        return _cmd_accion(args)
    ruta = _ruta_db(args.db)
    if not ruta.exists():
        print(f"No existe el almacen {ruta}", file=sys.stderr)
        return 1
    try:
        trimestre = btw.leer_etiqueta(args.trimestre) if args.trimestre else None
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    with _abrir_almacen(args.db) as almacen:
        conn = almacen.conn
        if args.accion == "hoja":
            if trimestre is None:
                print("La hoja es de un trimestre: bms-agent btw hoja 2026-T3", file=sys.stderr)
                return 1
            hoja = btw.hoja(conn, *trimestre)
            if args.salida:
                Path(args.salida).write_bytes(hoja.en_bytes())
                print(f"Hoja de trabajo {btw.etiqueta(*trimestre)} en {args.salida}")
            else:
                # Los mismos bytes que se hashean (con su BOM): una hoja guardada con
                # `> hoja.csv` da el sha256 que se dice y el que queda en el periodo.
                sys.stdout.flush()
                sys.stdout.buffer.write(hoja.en_bytes())
                sys.stdout.buffer.flush()
            print(f"sha256 {hoja.sha256}", file=sys.stderr if not args.salida else sys.stdout)
            return 0
        datos = btw.trimestre(conn, *trimestre) if trimestre else btw.resumen(conn)
    if args.json:
        print(btw.a_json(datos))
        return 0
    if trimestre is None:
        _imprimir_resumen_btw(datos)
    else:
        _imprimir_trimestre_btw(datos)
    return 0


def _imprimir_trimestre_btw(t: dict) -> None:
    from .btw import euros

    c = t["cifras"]
    print(f"BTW {t['etiqueta']} ({t['inicio']} a {t['fin']}): {t['estado']}"
          + (f", presentado el {t['presentado_en']} por {t['presentado_por']} "
             f"(referencia {t['referencia']}, declarado {euros(t['importe_declarado_cent'])})"
             if t["estado"] == "presentado" else "")
          + (f", rev {t['rev']}" if t["rev"] is not None else ""))
    print(f"  plazo de presentacion y pago: {t['limite_presentacion']} "
          f"({t['dias_para_limite']} dias)")
    for r in c["rubricas"]:
        if r["omzet_cent"] or r["btw_cent"]:
            print(f"  {r['rubrica']:<3} {euros(r['omzet_cent']):>14} {euros(r['btw_cent']):>14}  "
                  f"{r['descripcion']}")
    print(f"  5a  {'':>14} {euros(c['5a']):>14}")
    print(f"  5b  {'':>14} {euros(c['5b']):>14}")
    print(f"  5c  {'':>14} {euros(c['5c']):>14}  "
          + ("a pagar" if c["5c"] >= 0 else "a devolver"))
    print(f"  ingresos sin IVA {euros(c['ingresos_cent'])}, IVA repercutido "
          f"{euros(c['iva_repercutido_cent'])}, costes sin IVA {euros(c['costes_cent'])}, "
          f"IVA deducible {euros(c['iva_deducible_cent'])}")
    for r in t["revisar"]:
        print(f"  revisar el IVA: factura {r['numero'] or r['factura_id']} "
              f"({', '.join(r['reglas'])})")
    for f in c["sin_clasificar"] + c["fuera"]:
        print(f"  fuera de las cifras: factura {f['numero'] or f['factura_id']}: {f['motivo']}")
    for d in t["diferencias"]:
        print(f"  distinta de lo presentado: factura {d['factura_id']} ({d['motivo']})")
    print(f"  hoja de trabajo sha256 {t['hoja_sha256']}"
          + ("" if t["hoja_al_dia"] else f" (la marcada era {t['hoja_marcada_sha256']})"))
    if not t["configuracion"]["confirmada"]:
        print("  config/btw.yaml: POR CONFIRMAR CON EL ASESOR")


def _imprimir_resumen_btw(r: dict) -> None:
    from .btw import euros

    _imprimir_trimestre_btw(r["actual"])
    for a in r["por_presentar"]:
        print(f"Por presentar: {a['etiqueta']} ({a['estado']}), plazo {a['limite_presentacion']} "
              f"({a['dias_para_limite']} dias), 5c {euros(a['5c'])}")
    y = r["ano_hasta_hoy"]
    print(f"Ano {y['ano']} hasta hoy: ingresos {euros(y['ingresos_cent'])}, 5a {euros(y['5a'])}, "
          f"5b {euros(y['5b'])}, 5c {euros(y['5c'])}")
    if r["sin_fecha"]:
        print(f"{r['sin_fecha']} facturas sin fecha: no entran en ningun trimestre")


def _cmd_demo(args: argparse.Namespace) -> int:
    from . import demo
    from .almacen import BaseDePruebaMezclada, DatosDePrueba

    ruta = Path(args.db) if args.db else demo.ruta_demo()
    try:
        resumen = demo.crear(ruta, rehacer=args.rehacer)
    except (DatosDePrueba, BaseDePruebaMezclada) as exc:
        print(f"No se crea la base de prueba: {exc}", file=sys.stderr)
        return 2
    if not resumen.creada:
        print(f"La base de prueba ya existe en {ruta} y no se ha tocado.")
        print("  Para empezar de cero: bms-agent demo crear --rehacer")
        return 0
    print(f"Base de DATOS DE PRUEBA creada en {ruta}")
    print("  Todo es ficticio y vive aparte: nada de aqui pasa a la base de verdad.")
    for clave, valor in resumen.cifras.items():
        print(f"  {clave:<22} {valor}")
    for aviso in resumen.avisos:
        print(f"  aviso: {aviso}")
    print("\nTokens para entrar en la consola de prueba (solo valen en esta base):")
    for nombre, token in resumen.tokens.items():
        print(f"  {nombre:<10} {token}")
    print(f"\nAbrela con:  bms-agent serve --db {ruta}")
    return 0


def _aviso_demo(args: argparse.Namespace) -> None:
    """Una orden sobre la base de prueba lo dice antes de nada (en la salida de errores, para
    no estropear un --json)."""
    if not hasattr(args, "db") or args.func in (_cmd_demo,):
        return
    from .demo import es_demo

    ruta = _ruta_db(args.db)
    if es_demo(ruta):
        print(f"*** DATOS DE PRUEBA: esta orden trabaja sobre {ruta}, no sobre la base de "
              "verdad ***", file=sys.stderr)


def _cmd_copia(args: argparse.Namespace) -> int:
    from .copia import CopiaFallida, comprobar, copiar

    ruta = _ruta_db(args.db)
    if args.comprobar:
        carpeta = Path(args.destino)
        if not (carpeta / ruta.name).is_file():
            print(f"{carpeta} no es una copia de {ruta.name}", file=sys.stderr)
            return 1
        problemas = comprobar(carpeta, ruta.name)
        for problema in problemas:
            print(f"  - {problema}")
        print(f"{carpeta}: " + ("se abre y cada fichero tiene su hash." if not problemas
                                else f"{len(problemas)} problemas."))
        return 1 if problemas else 0
    try:
        copia = copiar(ruta, args.destino)
    except CopiaFallida as exc:
        print(f"No se ha hecho la copia: {exc}", file=sys.stderr)
        return 1
    print(f"Copia hecha y comprobada en {copia.carpeta}")
    print(f"  {copia.ficheros} ficheros ({copia.bytes // 1024} KB), {copia.documentos} originales")
    print("  La base pasa su comprobacion y cada fichero tiene el hash de MANIFIESTO.sha256.")
    return 0


def _cmd_restaurar(args: argparse.Namespace) -> int:
    from .copia import CopiaFallida, restaurar

    ruta = _ruta_db(args.db)
    try:
        hecho = restaurar(args.origen, ruta)
    except CopiaFallida as exc:
        print(f"No se ha restaurado nada: {exc}", file=sys.stderr)
        return 1
    print(f"Restaurada {ruta} desde {args.origen}")
    if hecho.antes is not None:
        print(f"  lo que habia antes queda guardado en {hecho.antes}")
    print(f"  {hecho.documentos_anadidos} originales anadidos")
    if hecho.evento_id is not None:
        print(f"  queda en la auditoria (evento {hecho.evento_id}), con "
              f"{hecho.anclas_descartadas} anclas de lo sustituido que ya no se cumplen")
    print("Comprueba con: bms-agent db verificar")
    return 0


def _cmd_salida(args: argparse.Namespace) -> int:
    import logging

    from . import salida

    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format=salida.FORMATO_REGISTRO)
    permitidos = args.permitir or list(salida.PERMITIDOS_POR_DEFECTO)
    try:
        salida.lista_blanca(permitidos)
        salida.leer_escucha(args.escuchar)
        for reenvio in args.reenviar:
            salida.leer_reenvio(reenvio)
    except ValueError as exc:
        print(f"No se arranca la salida: {exc}", file=sys.stderr)
        return 2
    if args.registro:
        try:
            salida.registrar_en_fichero(args.registro)
        except OSError as exc:
            print(f"No se arranca la salida: no se puede escribir el registro {args.registro}: "
                  f"{exc.strerror or exc}", file=sys.stderr)
            return 2
    salida.servir(args.escuchar, permitidos, args.reenviar)
    return 0


def _cmd_salida_registro(args: argparse.Namespace) -> int:
    from . import salida

    lineas = salida.leer_registro(args.fichero, solo_rechazados=args.rechazados)
    if not Path(args.fichero).is_file():
        print(f"No hay registro en {args.fichero}: la salida aun no ha arrancado con --registro",
              file=sys.stderr)
        return 1
    for linea in lineas:
        print(linea)
    if args.rechazados:
        print(f"{len(lineas)} intentos rechazados", file=sys.stderr)
    return 0


def _cmd_salud(args: argparse.Namespace) -> int:
    from . import salida

    try:
        vivo = salida.comprobar(args.destino)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(f"{args.destino}: {'acepta conexiones' if vivo else 'no contesta'}")
    return 0 if vivo else 1


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
    p_extract.add_argument(
        "--salientes",
        action="store_true",
        help=(
            "la carpeta son facturas emitidas por BM Support BV (ventas): entran por la via "
            "de salida y se guardan en <out>/salientes"
        ),
    )
    p_extract.add_argument("--db", help=_AYUDA_DB)
    p_extract.set_defaults(func=_cmd_extract)

    p_score = sub.add_parser("score", help="compara las extracciones con las respuestas")
    p_score.add_argument("--out", help="carpeta con las extracciones (por defecto: out)")
    p_score.add_argument(
        "--ground-truth",
        default="ground_truth/respuestas.yaml",
        help="fichero de respuestas escritas a mano",
    )
    p_score.add_argument(
        "--comparar-versiones", action="store_true",
        help="la version de config.py contra la anterior, en los mismos documentos: es la "
             "puerta de `reextraer --activar` (sale con 1 si no pasa)")
    p_score.add_argument("--inyeccion", default=INYECCION,
                         help=f"la factura con inyeccion de la puerta (por defecto {INYECCION})")
    p_score.add_argument("--db", help=_AYUDA_DB + "; con --comparar-versiones, se lee de ahi si "
                                                  "existe y no se da --out")
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
    p_export.add_argument(
        "--v2", action="store_true",
        help="el contrato v2 del almacen (panel, facturas, vistas, BTW...; por defecto en "
             "datos-v2.json): docs/integracion-web.md")
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
    p_serve.add_argument(
        "--contenedor", action="store_true",
        help="dentro del contenedor de Docker: escucha en 0.0.0.0 (fuera de un contenedor se "
             "niega) y no lee PDF, que los lee el lector")
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
    p_asegurar = sub_usuario.add_parser(
        "asegurar", help="que exista la persona con ese rol y solo ese (la crea si falta; si ya "
                         "tiene otros roles no toca nada y sale con 3)")
    p_asegurar.add_argument("nombre")
    p_asegurar.add_argument("--rol", required=True,
                            choices=("administrador", "administracion", "consulta"))
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
    opciones_accion = {"--token", "--peticion", "--db"}
    for accion in ACCIONES.values():
        p_una = sub_accion.add_parser(accion.nombre, help=accion.descripcion)
        for parametro in accion.parametros:
            opcion = f"--{parametro.nombre.replace('_', '-')}"
            opciones_accion.add(opcion)
            p_una.add_argument(opcion, dest=parametro.nombre,
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

    p_resumen = sub.add_parser("resumen", help="el panel principal: lo que entra y sale, la "
                                               "caja, las PO, el BTW y lo que pide atencion")
    p_resumen.add_argument("--json", action="store_true", help="el panel entero en JSON")
    p_resumen.add_argument("--db", help=_AYUDA_DB)
    p_resumen.set_defaults(func=_cmd_resumen)

    p_buscar = sub.add_parser("buscar", help="buscar facturas por numero, parte, Objeto, PO, "
                                             "fechas y estados (--filtros los lista)")
    p_buscar.add_argument("--filtro", action="append", metavar="NOMBRE=VALOR",
                          help="un filtro (repetible): numero=4471, estado_pago=vencida,pagada")
    p_buscar.add_argument("--filtros", action="store_true", help="lista los filtros")
    p_buscar.add_argument("--orden", choices=("prioridad", "fecha", "vencimiento", "importe",
                                              "numero"))
    p_buscar.add_argument("--limite", type=int)
    p_buscar.add_argument("--pagina", type=int)
    p_buscar.add_argument("--json", action="store_true", help="el resultado entero en JSON")
    p_buscar.add_argument("--db", help=_AYUDA_DB)
    p_buscar.set_defaults(func=_cmd_buscar)

    p_objetos = sub.add_parser("objetos", help="los Objetos: ingresos, costes y margen, y lo "
                                               "que no es de ninguno")
    p_objetos.add_argument("--json", action="store_true", help="la lista en JSON")
    p_objetos.add_argument("--db", help=_AYUDA_DB)
    p_objetos.set_defaults(func=_cmd_objetos)

    p_historial = sub.add_parser("historial", help="la historia de una factura: original, "
                                                   "cambios, revisiones y avisos")
    p_historial.add_argument("id", type=int)
    p_historial.add_argument("--todo", action="store_true",
                             help="tambien los cambios automaticos campo a campo")
    p_historial.add_argument("--json", action="store_true", help="la historia en JSON")
    p_historial.add_argument("--db", help=_AYUDA_DB)
    p_historial.set_defaults(func=_cmd_historial)

    p_factura = sub.add_parser("factura", help="la ficha de una factura")
    p_factura.add_argument("id", type=int)
    p_factura.add_argument("--json", action="store_true", help="la ficha entera en JSON")
    p_factura.add_argument("--db", help=_AYUDA_DB)
    p_factura.set_defaults(func=_cmd_factura)

    p_relaciones = sub.add_parser(
        "relaciones", help="las relaciones entre facturas propuestas, por confirmar o rechazar")
    p_relaciones.add_argument("--db", help=_AYUDA_DB)
    p_relaciones.set_defaults(func=_cmd_relaciones)

    for nombre, tabla, ayuda in (
            ("proveedores", "proveedor", "los proveedores: lo que se les debe y lo vencido"),
            ("clientes", "cliente", "los clientes: lo que deben y lo vencido")):
        p_lista = sub.add_parser(nombre, help=ayuda)
        p_lista.add_argument("--json", action="store_true", help="la lista en JSON")
        p_lista.add_argument("--db", help=_AYUDA_DB)
        p_lista.set_defaults(func=_cmd_partes, tabla=tabla)
    for nombre, ayuda in (("proveedor", "la vista de un proveedor (§3)"),
                          ("cliente", "la vista de un cliente (§4)")):
        p_vista = sub.add_parser(nombre, help=ayuda)
        p_vista.add_argument("id", type=int)
        p_vista.add_argument("--json", action="store_true", help="la vista entera en JSON")
        p_vista.add_argument("--db", help=_AYUDA_DB)
        p_vista.set_defaults(func=_cmd_parte, tabla=nombre)

    p_ordenes = sub.add_parser("ordenes", help="las ordenes de compra: valor, consumido y "
                                                "lo que queda")
    p_ordenes.add_argument("--json", action="store_true", help="la lista en JSON")
    p_ordenes.add_argument("--db", help=_AYUDA_DB)
    p_ordenes.set_defaults(func=_cmd_ordenes)
    for nombre, ayuda, funcion in (
            ("orden", "una orden de compra: sus facturas, modificaciones y prevision", _cmd_orden),
            ("objeto", "un Objeto y sus ordenes de compra", _cmd_objeto)):
        p_vista = sub.add_parser(nombre, help=ayuda)
        p_vista.add_argument("id", type=int)
        p_vista.add_argument("--json", action="store_true", help="la vista entera en JSON")
        p_vista.add_argument("--db", help=_AYUDA_DB)
        p_vista.set_defaults(func=funcion)

    p_excepciones = sub.add_parser("excepciones", help="las excepciones sin resolver")
    p_excepciones.add_argument("--db", help=_AYUDA_DB)
    p_excepciones.set_defaults(func=_cmd_excepciones)

    p_imp = sub.add_parser(
        "importar", help="importa un fichero de un maestro, del banco, de pagos, de facturas "
                         "de venta de Exact, la hoja de ordenes de compra o el planning")
    p_imp.add_argument("fuente", help="exact, trnsprnt, maestro_csv, banco o po_csv")
    p_imp.add_argument("tipo", help="proveedores, clientes, objetos, recursos, alias, tarifas, "
                                    "ciclos, pagos_exact y facturas_venta (exact), extracto "
                                    "(banco), ordenes_compra y modificaciones_po (po_csv, CSV "
                                    "o YAML; pide cambiar_po) o planning (trnsprnt)")
    p_imp.add_argument("fichero")
    p_imp.add_argument("--mapeo", help="un fichero de mapeo (por defecto, el de "
                                       "config/importacion que reconoce sus columnas); para el "
                                       "banco, tambien camt053, mt940 o mt940:ing|abn|rabobank")
    p_imp.add_argument("--simular", action="store_true",
                       help="dice lo que seria nuevo, cambiaria o se rechazaria, sin escribir")
    p_imp.add_argument("--exportado", help="dia en que se saco del sistema (AAAA-MM-DD); por "
                                           "defecto, el del fichero")
    p_imp.add_argument("--desde", help="el planning: primer dia que cubre la foto (por "
                                       "defecto, el del primer turno)")
    p_imp.add_argument("--hasta", help="el planning: ultimo dia que cubre la foto (por "
                                       "defecto, el del ultimo turno)")
    p_imp.add_argument("--confirmar", action="store_true",
                       help="el planning: importa una foto sin turnos, con semanas enteras sin "
                            "turnos o que deja sin valer muchos turnos del planning de ahora")
    p_imp.add_argument("--token", help=f"token de la persona (o la variable {VARIABLE_TOKEN})")
    p_imp.add_argument("--db", help=_AYUDA_DB)
    p_imp.set_defaults(func=_cmd_importar)

    p_iban = sub.add_parser("iban", help="el registro de cuentas: listar, verificar, rechazar, "
                                         "atestar, telefono")
    sub_iban = p_iban.add_subparsers(dest="accion", required=True)
    p_listar = sub_iban.add_parser("listar", help="las cuentas de los proveedores y su estado")
    p_listar.add_argument("--db", help=_AYUDA_DB)
    for corto, nombre in _IBAN.items():
        accion = ACCIONES[nombre]
        p_una = sub_iban.add_parser(corto, help=accion.descripcion)
        for parametro in accion.parametros:
            p_una.add_argument(f"--{parametro.nombre.replace('_', '-')}", dest=parametro.nombre,
                               required=parametro.obligatorio and parametro.nombre != "motivo",
                               help=parametro.ayuda or parametro.tipo)
        p_una.add_argument("--token", help=f"token de la persona (o la variable {VARIABLE_TOKEN})")
        p_una.add_argument("--peticion", help="identificador de la peticion")
        p_una.add_argument("--db", help=_AYUDA_DB)
    p_iban.set_defaults(func=_cmd_iban)

    p_btw = sub.add_parser("btw", help="el BTW: ver, hoja, listo, reabrir, anotar (no presenta "
                                       "nada)")
    sub_btw = p_btw.add_subparsers(dest="accion", required=True)
    p_ver = sub_btw.add_parser("ver", aliases=["estado"],
                               help="un trimestre, o el resumen sin trimestre (el §6 la llama "
                                    "btw estado)")
    p_ver.add_argument("trimestre", nargs="?", help="2026-T3")
    p_ver.add_argument("--json", action="store_true")
    p_ver.add_argument("--db", help=_AYUDA_DB)
    p_hoja = sub_btw.add_parser("hoja", help="la hoja de trabajo (CSV) y su sha256")
    p_hoja.add_argument("trimestre", help="2026-T3")
    p_hoja.add_argument("--salida", help="fichero donde escribirla (si no, en pantalla)")
    p_hoja.add_argument("--db", help=_AYUDA_DB)
    for corto, nombre in _BTW.items():
        accion = ACCIONES[nombre]
        p_una = sub_btw.add_parser(corto, help=accion.descripcion)
        for parametro in accion.parametros:
            opcion = f"--{parametro.nombre.replace('_', '-')}"
            p_una.add_argument(opcion, dest=parametro.nombre,
                               required=parametro.obligatorio and parametro.nombre != "motivo",
                               help=parametro.ayuda or parametro.tipo)
        p_una.add_argument("--token", help=f"token de la persona (o la variable {VARIABLE_TOKEN})")
        p_una.add_argument("--peticion", help="identificador de la peticion")
        p_una.add_argument("--db", help=_AYUDA_DB)
    p_btw.set_defaults(func=_cmd_btw)

    p_pagos = sub.add_parser("pagos", help="movimientos del banco, lo sin casar y las propuestas")
    p_pagos.add_argument("--sin-casar", action="store_true", help="solo lo que no casa con nada")
    p_pagos.add_argument("--propuestas", action="store_true",
                         help="los pagos propuestos por confirmar")
    p_pagos.add_argument("--factura", type=int, help="lo pagado de una factura, con su saldo")
    p_pagos.add_argument("--limite", type=int, default=200)
    p_pagos.add_argument("--db", help=_AYUDA_DB)
    p_pagos.set_defaults(func=_cmd_pagos)

    p_flujo = sub.add_parser("flujo-caja", help="lo esperado por cobrar y pagar, y lo movido")
    p_flujo.add_argument("--desde", metavar="AAAA-MM-DD", help="un periodo propio, con --hasta")
    p_flujo.add_argument("--hasta", metavar="AAAA-MM-DD")
    p_flujo.add_argument("--hoy", metavar="AAAA-MM-DD", help="otro dia que hoy (Amsterdam)")
    p_flujo.add_argument("--json", action="store_true")
    p_flujo.add_argument("--db", help=_AYUDA_DB)
    p_flujo.set_defaults(func=_cmd_flujo_caja)

    p_fuentes = sub.add_parser("fuentes", help="de cuando es lo ultimo de cada fuente (Z1)")
    p_fuentes.add_argument("--db", help=_AYUDA_DB)
    p_fuentes.set_defaults(func=_cmd_fuentes)

    p_reex = sub.add_parser(
        "reextraer", help="vuelve a leer lo ya leido con la version nueva, con presupuesto")
    p_reex.add_argument("--abiertas", action="store_true",
                        help="facturas en juego (sin pagar ni anular)")
    p_reex.add_argument("--desde", metavar="AAAA-MM-DD", help="con fecha de factura desde ese dia")
    p_reex.add_argument("--proveedor", help="id o nombre del proveedor")
    p_reex.add_argument("--sin-objeto", action="store_true",
                        help="facturas con alguna linea sin Objeto imputado")
    p_reex.add_argument("--reintentos", action="store_true",
                        help="los documentos que quedaron para reintentar en esta version")
    p_reex.add_argument("--limite", type=int, help="como mucho tantos documentos")
    p_reex.add_argument("--presupuesto", metavar="USD",
                        help="dolares que se aceptan gastar; sin el, solo se estima")
    p_reex.add_argument("--lote", action="store_true",
                        help="por la API de Batches: la mitad de precio, en horas")
    p_reex.add_argument("--recoger", type=int, metavar="N",
                        help="lee los resultados del lote de la reextraccion N")
    p_reex.add_argument("--activar", action="store_true",
                        help="pasa a vigentes las candidatas si pasan la puerta (admin)")
    p_reex.add_argument("--ground-truth", default="ground_truth/respuestas.yaml",
                        help="respuestas escritas a mano para la puerta")
    p_reex.add_argument("--inyeccion", default=INYECCION,
                        help=f"la factura con inyeccion de la puerta (por defecto {INYECCION})")
    p_reex.add_argument("--out", default="out",
                        help="carpeta de extracciones; lo leido se exporta en su reextraccion/")
    p_reex.add_argument("--token", help=f"token de la persona (o la variable {VARIABLE_TOKEN})")
    p_reex.add_argument("--db", help=_AYUDA_DB)
    p_reex.set_defaults(func=_cmd_reextraer)

    p_politica = sub.add_parser("politica", help="la politica: prioridad, reglas, empresa y BTW")
    sub_politica = p_politica.add_subparsers(dest="accion", required=True)
    p_cargar = sub_politica.add_parser(
        "cargar", help="apunta prioridad.yaml, reglas.yaml, empresa.yaml o btw.yaml y recalcula")
    p_cargar.add_argument("fichero", nargs="?", default="config/prioridad.yaml")
    p_cargar.add_argument("--db", help=_AYUDA_DB)
    p_cargar.add_argument("--token", help="el token de una persona con admin (o BMS_TOKEN)")
    p_politica.set_defaults(func=_cmd_politica)

    p_demo = sub.add_parser("demo", help="la base de DATOS DE PRUEBA, aparte de la de verdad")
    sub_demo = p_demo.add_subparsers(dest="accion", required=True)
    p_demo_crear = sub_demo.add_parser(
        "crear", help="crea datos/demo.sqlite3 con una empresa ficticia (proveedores, clientes, "
                      "Objetos, facturas, banco, planning y BTW)")
    p_demo_crear.add_argument("--db", help="donde (por defecto, demo.sqlite3 al lado de la base "
                                           "de verdad); tiene que llamarse demo.sqlite3")
    p_demo_crear.add_argument("--rehacer", action="store_true",
                              help="si ya existe, la borra (solo si es de prueba) y la rehace")
    p_demo.set_defaults(func=_cmd_demo)

    p_copia = sub.add_parser("copia", help="copia de seguridad de la base, sus originales y sus "
                                           "anclas en una carpeta nueva, comprobada")
    p_copia.add_argument("destino", help="la carpeta donde dejarla (el disco externo cifrado); "
                                         "con --comprobar, la carpeta de una copia ya hecha")
    p_copia.add_argument("--comprobar", action="store_true",
                         help="no copia: comprueba una copia (sin tocarla)")
    p_copia.add_argument("--db", help=_AYUDA_DB)
    p_copia.set_defaults(func=_cmd_copia)

    p_restaurar = sub.add_parser("restaurar", help="vuelve a poner una copia (comprobada) en su "
                                                   "sitio; lo de antes se guarda primero")
    p_restaurar.add_argument("origen", help="la carpeta de la copia (bms-copia-...)")
    p_restaurar.add_argument("--db", help=_AYUDA_DB)
    p_restaurar.set_defaults(func=_cmd_restaurar)

    p_salida = sub.add_parser(
        "salida", help="el proxy de salida del entorno de Docker: solo CONNECT a la lista "
                       "blanca (por defecto api.anthropic.com:443)")
    p_salida.add_argument("--escuchar", default="0.0.0.0:3128", metavar="HOST:PUERTO",
                          help="donde escucha el proxy (un nombre se resuelve al arrancar: "
                               "el alias de la red del lector)")
    p_salida.add_argument("--permitir", action="append", default=[], metavar="HOST:PUERTO",
                          help="un destino permitido; se puede repetir (por defecto "
                               "api.anthropic.com:443)")
    p_salida.add_argument("--reenviar", action="append", default=[], metavar="ESCUCHA=DESTINO",
                          help="reenvia un puerto tal cual, por ejemplo "
                               "0.0.0.0:8765=consola:8765 (la entrada a la consola)")
    p_salida.add_argument("--registro", metavar="FICHERO",
                          help="apunta cada intento tambien en este fichero, anadiendo al final "
                               "(en Docker, el volumen de la salida: el registro de Docker se "
                               "pierde con el contenedor)")
    p_salida.set_defaults(func=_cmd_salida)

    p_registro = sub.add_parser(
        "salida-registro", help="lo que ha intentado salir a internet, del registro de la salida "
                                "(lo mas viejo primero)")
    p_registro.add_argument("--fichero", default="/registro/salida.log",
                            help="el registro (por defecto, el del entorno de Docker)")
    p_registro.add_argument("--rechazados", action="store_true",
                            help="solo lo que no se dejo salir")
    p_registro.set_defaults(func=_cmd_salida_registro)

    p_salud = sub.add_parser("salud", help="comprobacion de salud de un contenedor: algo acepta "
                                           "conexiones en HOST:PUERTO")
    p_salud.add_argument("destino", metavar="HOST:PUERTO")
    p_salud.set_defaults(func=_cmd_salud)

    argv = sys.argv[1:] if argv is None else list(argv)
    args = parser.parse_args(_unir_valores_de_accion(argv, opciones_accion))
    _aviso_demo(args)
    from .almacen import BaseDePruebaMezclada

    try:
        return args.func(args)
    except BaseDePruebaMezclada as exc:
        print(f"No se abre la base: {exc}", file=sys.stderr)
        return 2
    except config.ClaveNoValida as exc:
        print(f"No se puede usar la clave de la API: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
