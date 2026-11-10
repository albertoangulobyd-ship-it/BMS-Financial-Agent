"""Crea una base de DATOS DE PRUEBA nueva en una carpeta y escribe sus tokens en JSON.

Lo usan los tests de la app en el navegador (frontend/e2e/global-setup.ts): cada pasada
empieza con una base de prueba recien hecha en una carpeta temporal, y necesita los
tokens para entrar. `bms-agent demo crear` los escribe para una persona; aqui salen en
JSON, una sola linea, para que un programa los lea sin interpretar texto.

    python scripts/crear_demo_e2e.py --carpeta /tmp/x/datos
    {"db": "/tmp/x/datos/demo.sqlite3", "tokens": {"Ana Demo": "bms_...", ...}, "cifras": {...}}

Solo escribe en un fichero demo.sqlite3 que no exista o que ya sea de prueba (demo.crear
lo exige), y con --rehacer lo vuelve a hacer.

Ademas de las dos personas de la base de prueba (Ana, administradora, y Bram, de
administracion), anade una tercera, "Cas Consulta", con el rol consulta (solo mira): las
pruebas comprueban con ella que quien solo puede leer no ve ningun boton de una orden.

Y deja en la carpeta, junto a la base, los ficheros que la prueba de Importeren sube desde
el navegador (paso 15): la exportacion de clientes de Exact con un cliente nuevo, con la
marca de los datos de prueba (en la base de prueba solo entra lo de la prueba), y un fichero
que no es ninguna exportacion. Van en "ficheros" del JSON.

Paso 16 (Cuentas por cobrar y por pagar): ademas importa un extracto del banco de hoy que
sigue la cadena de los de la base de prueba, con lo que esas pantallas tienen que saber
ensenar y las pruebas hacer de verdad: cobros que el banco casa a medias (propuestas que
esperan a una persona: confirmar, retirar y el conflicto de dos personas a la vez), pagos a
proveedores sin la referencia y un ingreso que no es de ninguna factura (sin casar, para
apuntar un pago con su linea). Entra por el importador de siempre, como desde Importeren.
Solo en la base de las pruebas: `bms-agent demo crear` no cambia, y sus pruebas en Python
tampoco. Lo que entro va en "banco" del JSON.

Paso 17: ese extracto necesita facturas que sigan abiertas, y el escenario va respecto a hoy:
al final de cada mes (del 29 al 31) la factura mensual de la Stichting ya se cobro y no queda
ninguna suya abierta; en los primeros dias del mes, la del gemeentehuis se cobra "hoy" (la
base siempre mueve algo en el mes en curso); y los lunes la factura semanal del puerto aun no
ha salido y la semana olvidada (V6) cae entre las abiertas: quedan dos. Entonces la base se
hace con el reloj de un dia antes, como una base de prueba hecha ese dia y abierta hoy:
"dias_atras" del JSON lo dice. El dia se elige con las facturas que tendria la base
(demo.facturas, puro, sin escribir nada), y la base hecha se comprueba igual. Hasta
DIAS_ATRAS: tests/test_crear_demo_e2e.py demuestra, dia a dia y durante anos, que basta.

Y "numeros" del JSON da el numero de cada factura que las pruebas abren por su papel (la
vieja del gemeentehuis, la repetida de J. Voorbeeld...): los numeros cambian con el dia en
que se hace la base (el mes y el ano van en ellos). Y el ultimo trimestre terminado del BTW
queda listo para revisar y sin presentar aunque su plazo haya pasado (demo.crear con
btw_sin_presentar), para que su prueba lo recorra cualquier dia; su etiqueta va en
"numeros" (vatQuarter). `bms-agent demo crear` no cambia.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


CONSULTA = "Cas Consulta"
# Como mucho, cuantos dias antes de hoy se busca uno en el que la base tenga lo que pide el
# extracto de las pruebas (las facturas abiertas de _facturas_del_extracto). Hace falta irse
# hasta 12 (tests/test_crear_demo_e2e.py lo mide dia a dia de 2026 a 2033).
DIAS_ATRAS = 14


class _FaltaUnaFactura(Exception):
    """La base de prueba de ese dia no tiene una de las facturas abiertas del extracto."""


def _persona_de_consulta(ruta: Path) -> str:
    """Una persona de solo lectura en la base de prueba recien hecha, y su token."""
    from bms_agent import permisos
    from bms_agent.almacen import preparar

    with preparar(ruta) as almacen:
        conn = almacen.conn
        usuario = permisos.crear_usuario(conn, CONSULTA)
        permisos.asignar_rol(conn, usuario, "consulta")
        return permisos.emitir_token(conn, usuario)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--carpeta", required=True, help="donde va demo.sqlite3")
    parser.add_argument("--rehacer", action="store_true", help="si ya existe, se hace de nuevo")
    parser.add_argument("--hoy", metavar="AAAA-MM-DD",
                        help="hacerla como si hoy fuera ese dia (para probar otras fechas; la "
                             "app la abre con el reloj de verdad)")
    args = parser.parse_args(argv)

    from bms_agent import demo
    from bms_agent.almacen import NOMBRE_DEMO
    from bms_agent.reloj import RelojFijo

    ruta = Path(args.carpeta) / NOMBRE_DEMO
    if ruta.exists() and not args.rehacer:
        print(json.dumps({"error": f"{ruta} ya existe: --rehacer para hacerla de nuevo"}),
              file=sys.stderr)
        return 2
    ahora = datetime.now(timezone.utc)
    if args.hoy:
        ahora = datetime.combine(date.fromisoformat(args.hoy), ahora.timetz())
    falta = None
    for atras in dias_posibles(ahora):
        reloj = None if atras == 0 and not args.hoy else RelojFijo(ahora - timedelta(days=atras))
        resumen = demo.crear(ruta, reloj=reloj, rehacer=True, btw_sin_presentar=True)
        # Lo dice el plan; la base hecha lo confirma (si no, el dia siguiente del plan).
        falta = _falta_para_el_extracto(ruta)
        if falta is None:
            break
    else:
        print(json.dumps({"error": f"en ninguno de los {DIAS_ATRAS + 1} ultimos dias tiene la "
                                   f"base lo que pide el extracto de las pruebas: {falta}"}),
              file=sys.stderr)
        return 3
    numeros = numeros_de_las_pruebas(RelojFijo(ahora - timedelta(days=atras)))
    tokens = {**resumen.tokens, CONSULTA: _persona_de_consulta(ruta)}
    ficheros = _ficheros_de_importar(Path(args.carpeta))
    banco = _extracto_de_pagos(ruta, Path(args.carpeta))
    print(json.dumps({"db": str(ruta), "tokens": tokens, "cifras": resumen.cifras,
                      "ficheros": ficheros, "banco": banco, "dias_atras": atras,
                      "numeros": numeros}, ensure_ascii=False))
    return 0


def falta_en_el_plan(reloj) -> str | None:
    """Que le faltaria al extracto en la base hecha con ese reloj, sin hacerla: las mismas
    facturas abiertas que pide _facturas_del_extracto, en demo.facturas (puro)."""
    from bms_agent import demo

    hoy = reloj.hoy()
    compras, ventas = demo.facturas(reloj)

    def abiertas(lista, codigo: str) -> list:
        return [f for f in lista if f.pagar_el is None and f.total > 0
                and f.tipo in ("Factuur", "invoice") and _parte(f) == codigo]

    haven = abiertas(ventas, "10001")
    if len(haven) < 3:
        return f"{len(haven)} facturas abiertas del puerto, y hacen falta tres"
    for nombre, falta in (
            ("la Stichting", abiertas(ventas, "10002")),
            ("el gemeentehuis (pendiente)", [f for f in abiertas(ventas, "10003")
                                             if f.vence >= hoy]),
            ("Oost", abiertas(compras, "30004")),
            ("Voorbeeld ni Noord", _sin_repetir(abiertas(compras, "30002"))
             or abiertas(compras, "30001"))):
        if not falta:
            return f"ninguna factura abierta de {nombre}"
    return None


def _parte(factura) -> str:
    """El codigo del cliente de una venta o del proveedor de una compra del plan."""
    return factura.cliente.codigo if hasattr(factura, "cliente") else factura.proveedor.codigo


def dias_posibles(ahora: datetime) -> list[int]:
    """Los dias atras (de 0 a DIAS_ATRAS) en los que la base tendria lo que pide el extracto,
    del mas cercano a hoy al mas lejano."""
    from bms_agent.reloj import RelojFijo

    return [atras for atras in range(DIAS_ATRAS + 1)
            if falta_en_el_plan(RelojFijo(ahora - timedelta(days=atras))) is None]


def numeros_de_las_pruebas(reloj) -> dict[str, object]:
    """El numero de cada factura que las pruebas abren por su papel en la base de ese dia
    (los numeros llevan el mes y el ano: cambian con el dia en que se hace la base)."""
    from bms_agent import btw, demo

    compras, ventas = demo.facturas(reloj)

    def de(codigo: str, lista=compras) -> list:
        return [f for f in lista if _parte(f) == codigo and getattr(f, "copia", 0) == 0]

    gemeente = sorted((v for v in de("10003", ventas) if v.tipo == "Factuur"),
                      key=lambda v: v.fecha)
    testpersoon = sorted(de("30005"), key=lambda c: c.desde)
    abono = next(c for c in de("30001") if c.tipo == "credit_note")
    voorbeeld = de("30002")
    return {
        # La vieja del gemeentehuis, vencida hace mas de sesenta dias (urgente).
        "municipalOld": gemeente[0].numero,
        # K. Testpersoon: la de hace dos meses (vencida) y la del mes pasado (un dato dudoso).
        "testpersoonOld": testpersoon[0].numero,
        "testpersoonRecent": testpersoon[-1].numero,
        # Noord: la del mes pasado y su abono (R5).
        "noordCredited": abono.citadas[0],
        "noordCredit": abono.numero,
        # Proefwacht: la que trae otro IBAN (F2, F3).
        "proefwachtNewIban": next(c.numero for c in de("30003") if c.iban == demo.IBAN_CAMBIADO),
        # La de otra moneda (X1) y la del texto que pide cambiar el IBAN.
        "otherCurrency": de("30006")[0].numero,
        "oost": de("30004")[0].numero,
        # J. Voorbeeld: la primera, la repetida (la ultima, B2) y las de antes, de la mas
        # reciente a la mas vieja.
        "voorbeeldFirst": voorbeeld[0].numero,
        "voorbeeldTwin": voorbeeld[-1].numero,
        "voorbeeldEarlier": [c.numero for c in reversed(voorbeeld[:-1])],
        # El trimestre del BTW que queda listo para revisar y sin presentar (btw_sin_presentar):
        # el ultimo terminado, como "2026-T3".
        "vatQuarter": btw.etiqueta(*btw.anterior(*btw.trimestre_de(reloj.hoy()))),
    }


def _camt(apuntes: list[tuple], inicial: Decimal, secuencia: int, dia: date) -> bytes:
    """Un CAMT.053 de un dia de la cuenta propia de la base de prueba, con su marca."""
    from bms_agent import demo

    identificador = f"{demo.MARCA_TEXTO}-{dia:%Y%m%d}-PAGOS"
    final = inicial + sum((a[0] for a in apuntes), Decimal(0))

    def saldo(codigo: str, valor: Decimal) -> str:
        return (f"<Bal><Tp><CdOrPrtry><Cd>{codigo}</Cd></CdOrPrtry></Tp>"
                f'<Amt Ccy="EUR">{abs(valor):.2f}</Amt>'
                f"<CdtDbtInd>{'DBIT' if valor < 0 else 'CRDT'}</CdtDbtInd>"
                f"<Dt><Dt>{dia.isoformat()}</Dt></Dt></Bal>")

    entradas = []
    for i, (importe, iban, nombre, concepto) in enumerate(apuntes, start=1):
        cargo = importe < 0
        parte, cuenta = ("Cdtr", "CdtrAcct") if cargo else ("Dbtr", "DbtrAcct")
        entradas.append(
            f'<Ntry><Amt Ccy="EUR">{abs(importe):.2f}</Amt>'
            f"<CdtDbtInd>{'DBIT' if cargo else 'CRDT'}</CdtDbtInd><Sts>BOOK</Sts>"
            f"<BookgDt><Dt>{dia.isoformat()}</Dt></BookgDt>"
            f"<AcctSvcrRef>{identificador}-{i}</AcctSvcrRef>"
            f"<NtryDtls><TxDtls><RltdPties><{parte}><Nm>{nombre}</Nm></{parte}>"
            f"<{cuenta}><Id><IBAN>{iban}</IBAN></Id></{cuenta}></RltdPties>"
            f"<RmtInf><Ustrd>{concepto}</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<!-- {demo.MARCA_TEXTO}: extracto ficticio de las pruebas de la app -->\n"
        '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"><BkToCstmrStmt>'
        f"<GrpHdr><MsgId>{identificador}</MsgId>"
        f"<CreDtTm>{dia.isoformat()}T18:00:00</CreDtTm></GrpHdr>"
        f"<Stmt><Id>{identificador}</Id><ElctrncSeqNb>{secuencia}</ElctrncSeqNb>"
        f"<FrToDt><FrDtTm>{dia.isoformat()}T00:00:00</FrDtTm>"
        f"<ToDtTm>{dia.isoformat()}T23:59:59</ToDtTm></FrToDt>"
        f"<Acct><Id><IBAN>{demo.CUENTA_PROPIA}</IBAN></Id><Ccy>EUR</Ccy></Acct>"
        f"{saldo('OPBD', inicial)}{saldo('CLBD', final)}"
        f"{''.join(entradas)}</Stmt></BkToCstmrStmt></Document>").encode("utf-8")


def _facturas_del_extracto(conn: sqlite3.Connection) -> dict:
    """Las facturas abiertas que usa el extracto: tres del puerto, la ultima de la Stichting,
    la ultima pendiente (no vencida) del gemeentehuis, la ultima de Oost y una de proveedor que
    el banco pueda proponer: la primera de Voorbeeld con un numero que solo lleva ella (la
    repetida, B2, son dos con el mismo importe: el banco no sabria cual y no propone nada), o,
    si no hay, la de Noord. _FaltaUnaFactura si alguna no esta."""

    def abiertas(sentido: str, tabla: str, codigo: str) -> list[sqlite3.Row]:
        columna = "cliente_id" if tabla == "cliente" else "proveedor_id"
        return conn.execute(
            f"SELECT f.numero, e.pendiente_cent, e.estado_pago FROM factura AS f "
            f"JOIN factura_estado AS e ON e.factura_id = f.id "
            f"JOIN {tabla} AS p ON p.id = f.{columna} WHERE f.sentido = ? "
            f"AND p.exact_id = ? AND e.estado_pago IN ('pendiente', 'vencida') "
            f"AND f.total_cent > 0 ORDER BY e.vencimiento, f.id",
            (sentido, codigo)).fetchall()

    def una(nombre: str, filas: list[sqlite3.Row]) -> sqlite3.Row:
        if not filas:
            raise _FaltaUnaFactura(f"ninguna factura abierta de {nombre}")
        return filas[0]

    haven = abiertas("saliente", "cliente", "10001")
    if len(haven) < 3:
        raise _FaltaUnaFactura(f"{len(haven)} facturas abiertas del puerto, y hacen falta tres")
    return {
        "haven": haven,
        "stichting": una("la Stichting", abiertas("saliente", "cliente", "10002")[-1:]),
        "gemeente": una("el gemeentehuis (pendiente)",
                        [f for f in abiertas("saliente", "cliente", "10003")
                         if f["estado_pago"] == "pendiente"][-1:]),
        "oost": una("Oost", abiertas("entrante", "proveedor", "30004")[-1:]),
        "proveedor": una("Voorbeeld ni Noord",
                         _sin_repetir(abiertas("entrante", "proveedor", "30002"))
                         or abiertas("entrante", "proveedor", "30001")),
    }


def _sin_repetir(filas: list) -> list:
    """Las facturas cuyo numero no lleva ninguna otra de la lista (sin la repetida, B2)."""
    numeros = [f["numero"] if isinstance(f, sqlite3.Row) else f.numero for f in filas]
    return [f for f, n in zip(filas, numeros) if numeros.count(n) == 1]


def _falta_para_el_extracto(ruta: Path) -> str | None:
    """Que le falta a la base para el extracto de las pruebas, o None si lo tiene todo."""
    conn = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        _facturas_del_extracto(conn)
    except _FaltaUnaFactura as falta:
        return str(falta)
    finally:
        conn.close()
    return None


def _extracto_de_pagos(ruta: Path, carpeta: Path) -> dict[str, int]:
    """El extracto de hoy de las pruebas de Cuentas por cobrar y por pagar.

    Las facturas se buscan por su cliente o proveedor (sus numeros cambian con el dia en que
    se crea la base). Las propuestas salen de un IBAN que el maestro no tiene (referencia e
    importe: dos de tres) o sin la referencia (importe y cuenta): el banco casa a medias y
    una persona decide. El ingreso sin casar trae el importe de una factura, sin referencia
    y de una cuenta desconocida (uno de tres). Sigue la cadena: el saldo de apertura es el
    ultimo de cierre y el numero el siguiente, asi que no abre K6.
    """
    from bms_agent import demo, permisos
    from bms_agent.almacen import preparar
    from bms_agent.importadores.registrar import importar_fichero

    with preparar(ruta) as almacen:
        conn = almacen.conn
        hoy = date.fromisoformat(conn.execute("SELECT max(hasta) FROM extracto_bancario")
                                 .fetchone()[0])

        def euros(cent: int) -> Decimal:
            return Decimal(cent) / 100

        f = _facturas_del_extracto(conn)
        haven, stichting, gemeente = f["haven"], f["stichting"], f["gemeente"]
        oost, pagada = f["oost"], f["proveedor"]
        # De quien es (Voorbeeld o Noord): por su numero.
        codigo = "30002" if pagada["numero"].startswith("JV-") else "30001"
        proveedor = {p.codigo: p for p in demo.PROVEEDORES}
        apuntes = [
            # Cobros con la referencia y el importe, desde una cuenta que no es la del maestro.
            (euros(stichting["pendiente_cent"]), demo.iban_demo(7000101),
             "Stichting Voorbeeld Zorggroep", f"Betaling factuur {stichting['numero']}"),
            (euros(haven[0]["pendiente_cent"]), demo.iban_demo(7000201), "Demo Havenbedrijf BV",
             f"Betaling factuur {haven[0]['numero']}"),
            (euros(gemeente["pendiente_cent"]), demo.iban_demo(7000301), "Gemeente Demodorp",
             f"Betaling factuur {gemeente['numero']}"),
            (euros(haven[-1]["pendiente_cent"]), demo.iban_demo(7000202),
             "Demo Havenbedrijf BV", f"Betaling factuur {haven[-1]['numero']}"),
            # Un ingreso que no dice de que factura es ni viene de una cuenta conocida.
            (euros(haven[1]["pendiente_cent"]), demo.iban_demo(7000401),
             "Fictief Evenementen BV", "Overboeking"),
            # Pagos a la cuenta del maestro por lo que queda, sin el numero de la factura.
            (-euros(oost["pendiente_cent"]), proveedor["30004"].iban, proveedor["30004"].nombre,
             "Betaling oktober"),
            (-euros(pagada["pendiente_cent"]), proveedor[codigo].iban,
             proveedor[codigo].nombre, "Betaling diensten"),
        ]
        ultimo = conn.execute("SELECT secuencia, saldo_final_cent FROM extracto_bancario "
                              "ORDER BY hasta DESC, secuencia DESC LIMIT 1").fetchone()
        xml = _camt(apuntes, euros(ultimo["saldo_final_cent"]), ultimo["secuencia"] + 1, hoy)
        fichero = carpeta / f"camt053-{hoy:%Y%m%d}-betalingen.xml"
        fichero.write_bytes(xml)
        ana = permisos.usuario_por_nombre(conn, "Ana Demo")
        resultado = importar_fichero(almacen, "banco", "extracto", fichero, lanzado_por=ana,
                                     exportado_en=datetime.now(timezone.utc))
        if any(lote.estado != "aceptada" or lote.rechazos for lote in resultado.lotes):
            raise SystemExit(f"el extracto de las pruebas no entro: {resultado.lotes}")
        propuestas = conn.execute("SELECT count(*) FROM aplicacion_pago WHERE estado = "
                                  "'propuesta'").fetchone()[0]
        return {"movimientos": len(apuntes), "propuestas": propuestas}


def _ficheros_de_importar(carpeta: Path) -> dict[str, str]:
    """Los ficheros que sube la prueba de Importeren: los clientes de Exact de la base de
    prueba mas uno nuevo (con la marca y un IBAN del banco ficticio) y uno que no es nada."""
    from bms_agent import demo

    filas = [[c.codigo, c.nombre, c.kvk or "", c.btw or "", "Normaal", "nee",
              "ja" if c.codigo == "10001" else "nee", f"{c.plazo} dagen", "Actief",
              c.iban or "", c.nombre] for c in demo.CLIENTES]
    filas.append(["10004", "Demo Nieuwbouw BV", "99000204", "NL999000204B01", "Normaal", "nee",
                  "nee", "30 dagen", "Actief", demo.iban_demo(1000401), "Demo Nieuwbouw BV"])
    clientes = carpeta / "exact-debiteuren-nieuw.csv"
    clientes.write_bytes(demo._csv(
        ["Debiteurnummer", "Naam", "KvK-nummer", "Btw-nummer", "Btw-behandeling",
         "Verleggen toegestaan", "PO verplicht", "Betalingsconditie", "Status", "IBAN",
         "Tenaamstelling"], filas))
    raro = carpeta / "notities.txt"
    raro.write_text(f"{demo.MARCA_TEXTO}: dit is geen export van Exact, de bank of TRNSPRNT.\n",
                    encoding="utf-8")
    return {"clientes": str(clientes), "raro": str(raro)}


if __name__ == "__main__":
    raise SystemExit(main())
