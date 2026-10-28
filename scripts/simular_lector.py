"""Hace de lector sobre la base de DATOS DE PRUEBA, sin red ni PDF: para las pruebas de la
app en el navegador (paso 17, especificacion §5.6).

La app no lee: pide una lectura y sigue lo que escribe el lector (leer-facturas.bat). En las
pruebas no hay lector ni API, asi que este ayudante da sus pasos uno a uno, cuando la prueba
lo pide, con las mismas funciones del lector (bms_agent.lectura): el mismo orden de estados,
las mismas fases de la pasada y el mismo tope. No es progreso al azar: es el escenario de la
prueba. Se niega con una base que no sea la de prueba.

    python scripts/simular_lector.py --db DATOS/demo.sqlite3 tomar
    python scripts/simular_lector.py --db ... contar --nuevas 12 --ya-leidas 3
    python scripts/simular_lector.py --db ... leer --pausa 0.4 [--fallidas 1] [--duplicados 2]
    python scripts/simular_lector.py --db ... si | no | caducar | recontar --nuevas 13
    python scripts/simular_lector.py --db ... fallar --motivo aislamiento

Cada orden dice en una linea de JSON como queda la lectura ({"solicitud", "estado"}) y sale
con 0; con 2 si no se puede (otra base, ninguna lectura, un estado que no toca).

- tomar: la pedida desde la app pasa a comprobando (o crea una, como el lector);
- contar: comprobando -> contando -> esperando el si, con una cuenta hecha a mano (`--nuevas`,
  `--ya-leidas`, `--alto` y `--bajo` por factura, en millonesimas de dolar). Sin nuevas, nada
  que leer;
- si / no: lo escrito en la ventana del lector; caducar: nadie dijo que si en el plazo;
- recontar: el lector siguiente vuelve a contar la misma lectura (otra huella: el si que la
  app mande con la de antes es un 409 «conflicto»);
- leer: con el si (de la app o `si`), lee documento a documento con `--pausa` segundos entre
  pasos, y para si se pide parar o si no cabe en el tope, como el lector. Lo que lee son
  documentos que ya estan en la base de prueba (los primeros de la carpeta de facturas
  recibidas): el resultado los nombra, para que Documentos los pinte;
- fallar: termina la lectura fallida con ese motivo (el aislamiento, la salida...). Con
  `--leyendo`, primero lee la mitad, y falla leyendo.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

# Lo que cuesta cada factura leida en la simulacion (6.000 de entrada y 700 de salida con el
# modelo de config.py): solo para que lo gastado suba como sube de verdad.
USO = {"input_tokens": 6000, "output_tokens": 700}


class NoSePuede(Exception):
    """La orden no se puede dar en esta base o en este estado."""


def _estimacion(nuevas: int, ya_leidas: int, alto: int, bajo: int):
    from bms_agent import config, lectura

    documentos = [lectura.Contado(f"factura-{i + 1:02d}.pdf", f"{i + 1:064x}", "nuevo", 4000,
                                  bajo, alto) for i in range(nuevas)]
    documentos += [lectura.Contado(f"ya-leida-{i + 1:02d}.pdf", f"{i + 1001:064x}", "ya_leido")
                   for i in range(ya_leidas)]
    return lectura.Estimacion(config.model_id(), config.PROMPT_VERSION, config.SCHEMA_VERSION,
                              1200, 6400, False, "simulada", documentos)


def _viva(conn):
    from bms_agent import lectura

    fila = lectura.viva(conn)
    if fila is None:
        raise NoSePuede("no hay ninguna lectura viva")
    return fila


def _documentos_de_la_base(conn, cuantos: int) -> list:
    """Los primeros documentos de facturas recibidas de la base de prueba, con su factura."""
    return conn.execute(
        "SELECT d.id, d.nombre_original, d.sha256 FROM documento AS d "
        "JOIN factura AS f ON f.documento_id = d.id WHERE d.ruta_declarada = 'entrante' "
        "GROUP BY d.id ORDER BY d.id LIMIT ?", (cuantos,)).fetchall()


def _leer(conn, args) -> None:
    """Lo que hace lectura.leer, sin PDF ni API: los mismos pasos, fases y tope."""
    from bms_agent import lectura

    fila = _viva(conn)
    if fila["estado"] != "aprobada":
        raise NoSePuede(f"la lectura {fila['id']} esta {fila['estado']}: falta el si")
    estimacion = json.loads(fila["estimacion_json"])
    contados = estimacion["documentos"]
    reales = _documentos_de_la_base(conn, len(contados))
    seguimiento = lectura.empezar(conn, fila["id"], len(contados))
    duplicados = set(range(args.duplicados))
    fallidas = set(range(len(contados) - args.fallidas, len(contados)))
    sha_de, resultado = {}, []
    hasta = len(contados) // 2 if args.leyendo else len(contados)
    for i, contado in enumerate(contados[:hasta]):
        real = reales[i] if i < len(reales) else None
        nombre = real["nombre_original"] if real is not None else contado["nombre"]
        sha_de[nombre] = real["sha256"] if real is not None else contado["sha256"]
        seguimiento.empieza(nombre, "comparando")
        time.sleep(args.pausa)
        if contado["clase"] == "ya_leido":
            seguimiento.informar("cache", nombre, "ya leida")
            continue
        motivo = seguimiento.cabe(SimpleNamespace(sha256=contado["sha256"]))
        if motivo is not None:
            seguimiento.sin_pagar(nombre, motivo)
            continue
        seguimiento.empieza(nombre, "leyendo")
        time.sleep(args.pausa)
        seguimiento.pagado(USO)
        if i in fallidas:
            seguimiento.informar("error", nombre, "simulada: no se pudo leer")
            continue
        seguimiento.empieza(nombre, "guardando")
        time.sleep(args.pausa)
        seguimiento.informar("ok", nombre, "simulada")
    if args.leyendo:
        lectura.cerrar(conn, fila["id"], "lectura", detalle="simulada")
        return
    for fase in ("comparando", "analizando", "organizando"):
        seguimiento.fase(fase)
        time.sleep(args.pausa)
    for i, nombre in enumerate(seguimiento.orden):
        estado = seguimiento.estados[nombre]
        if estado == "sin_leer":
            continue
        real = reales[i] if i < len(reales) else None
        if estado == "leida":
            estado = "posible_duplicado" if i in duplicados else "nueva"
        factura = None
        if real is not None:
            factura = conn.execute(
                "SELECT f.id, f.numero, coalesce(p.nombre, c.nombre) AS empresa FROM factura "
                "AS f LEFT JOIN proveedor AS p ON p.id = f.proveedor_id LEFT JOIN cliente AS c "
                "ON c.id = f.cliente_id WHERE f.documento_id = ? ORDER BY f.id LIMIT 1",
                (real["id"],)).fetchone()
        resultado.append({"documento_id": real["id"] if real is not None else None,
                          "nombre": nombre, "estado": estado,
                          "factura_id": factura["id"] if factura is not None else None,
                          "numero": factura["numero"] if factura is not None else None,
                          "empresa": factura["empresa"] if factura is not None else None})
    lectura.terminar(conn, seguimiento, resultado)


def ejecutar(conn, args) -> int:
    from bms_agent import lectura

    if args.orden == "tomar":
        tomada = lectura.tomar(conn, hay_pdf=True)
        if tomada.solicitud_id is None:
            raise NoSePuede(tomada.detalle)
        return tomada.solicitud_id
    fila = _viva(conn)
    if args.orden == "contar":
        estimacion = _estimacion(args.nuevas, args.ya_leidas, args.alto, args.bajo)
        lectura.contar(conn, fila["id"], lambda _antes: estimacion)
    elif args.orden == "recontar":
        lectura.volver_a_contar(conn, fila["id"])
        estimacion = _estimacion(args.nuevas, args.ya_leidas, args.alto, args.bajo)
        lectura.contar(conn, fila["id"], lambda _antes: estimacion)
    elif args.orden == "si":
        lectura.aprobar_en_ventana(conn, fila["id"])
    elif args.orden == "no":
        if not lectura.cancelar_en_ventana(conn, fila["id"]):
            raise NoSePuede(f"la lectura {fila['id']} esta {fila['estado']}")
    elif args.orden == "caducar":
        if not lectura.caducar(conn, fila["id"]):
            raise NoSePuede(f"la lectura {fila['id']} esta {fila['estado']}")
    elif args.orden == "fallar":
        if args.leyendo:
            args.duplicados, args.fallidas = 0, 0
            _leer(conn, args)
        else:
            lectura.cerrar(conn, fila["id"], args.motivo, detalle="simulado")
    elif args.orden == "leer":
        args.leyendo = False
        _leer(conn, args)
    return fila["id"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--db", required=True, help="la base de prueba (demo.sqlite3)")
    sub = parser.add_subparsers(dest="orden", required=True)
    sub.add_parser("tomar")
    for nombre in ("contar", "recontar"):
        p = sub.add_parser(nombre)
        p.add_argument("--nuevas", type=int, default=3)
        p.add_argument("--ya-leidas", type=int, default=1)
        p.add_argument("--alto", type=int, default=62_000, help="millonesimas de dolar")
        p.add_argument("--bajo", type=int, default=57_000, help="millonesimas de dolar")
    for nombre in ("si", "no", "caducar"):
        sub.add_parser(nombre)
    p = sub.add_parser("leer")
    p.add_argument("--pausa", type=float, default=0.3, help="segundos entre pasos")
    p.add_argument("--duplicados", type=int, default=0, help="las primeras N, duplicados")
    p.add_argument("--fallidas", type=int, default=0, help="las ultimas N no se pueden leer")
    p = sub.add_parser("fallar")
    p.add_argument("--motivo", default="aislamiento")
    p.add_argument("--leyendo", action="store_true", help="lee la mitad y falla leyendo")
    p.add_argument("--pausa", type=float, default=0.3)
    args = parser.parse_args(argv)

    from bms_agent import lectura
    from bms_agent.almacen import es_base_demo, preparar

    ruta = Path(args.db)
    if not ruta.is_file():
        print(json.dumps({"error": f"no existe {ruta}"}), file=sys.stderr)
        return 2
    with preparar(ruta) as almacen:
        conn = almacen.conn
        if not es_base_demo(conn):
            print(json.dumps({"error": "solo con la base de DATOS DE PRUEBA: esta es de verdad"}),
                  file=sys.stderr)
            return 2
        try:
            solicitud = ejecutar(conn, args)
        except (NoSePuede, lectura.EstadoNoValido, lectura.Parada) as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 2
        estado = conn.execute("SELECT estado FROM solicitud_lectura WHERE id = ?",
                              (solicitud,)).fetchone()[0]
    print(json.dumps({"solicitud": solicitud, "estado": estado}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
