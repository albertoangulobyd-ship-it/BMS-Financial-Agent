"""Semilla de clientes, Objetos y tarifas de venta desde config/tarifas.yaml.

Hasta que lleguen los maestros de Exact y TRNSPRNT (paso 5), la tabla de
tarifas es lo unico que dice que Objetos hay, de que cliente es cada uno y a
cuanto se vende cada trabajo. Sembrarla en el almacen permite imputar ya
cada linea de compra a su Objeto (factura_imputacion.objeto_id), por
coincidencia exacta con el nombre impreso.

- Cada fichero aplicado queda en politica_version con su hash y su texto.
- Los valores entran por campos.py con fuente 'maestro' y la referencia del
  fichero: lo que una persona corrigio despues no se pisa.
- Volver a sembrar el mismo fichero no hace nada. Un fichero cambiado anade
  lo nuevo y actualiza lo que cambio; lo que ya no esta en el fichero no se
  borra (no es una foto completa del maestro).
- margen_por_defecto y no_facturable no se siembran: son la politica de la
  proyeccion de venta, que sigue leyendo el fichero (facturacion.py).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .. import campos
from ..almacen import reloj_de, transaccion, usuario_sistema
from ..almacen.unidades import sha256_texto
from ..auditoria import registrar
from ..campos import Automatico, Leido
from ..dominio import Fuente
from ..identidad import normalizar_nombre, resolver_objeto, resolver_parte
from ..parsing import ParseError, parse_amount
from ..reloj import marca


@dataclass
class ResultadoSemilla:
    fichero: str
    sha256: str
    nueva_politica: bool = False
    clientes_nuevos: int = 0
    objetos_nuevos: int = 0
    tarifas_nuevas: int = 0
    tarifas_cambiadas: int = 0
    imputaciones_resueltas: int = 0
    avisos: list[str] = field(default_factory=list)


def _politica(conn: sqlite3.Connection, nombre: str, texto: str, sha256: str,
              usuario_id: int | None) -> bool:
    """Apunta el fichero en politica_version si ese contenido no estaba ya."""
    if conn.execute("SELECT 1 FROM politica_version WHERE fichero = ? AND sha256 = ?",
                    (nombre, sha256)).fetchone():
        return False
    reloj = reloj_de(conn)
    sistema = usuario_sistema(conn, "sistema")
    fila_id = int(conn.execute(
        "INSERT INTO politica_version (sha256, fichero, contenido, vigente_desde, cargada_en, "
        "cargada_por) VALUES (?, ?, ?, ?, ?, ?)",
        (sha256, nombre, texto, reloj.hoy().isoformat(), marca(reloj.ahora()),
         usuario_id or sistema),
    ).lastrowid)
    registrar(conn, tipo="politica_cargada", actor=sistema, usuario_id=usuario_id,
              tabla="politica_version", fila_id=fila_id,
              datos={"fichero": nombre, "sha256": sha256})
    return True


def _obras(datos: dict[str, Any]) -> list[tuple[str, str | None]]:
    obras = []
    for nombre, cfg in (datos.get("obras") or {}).items():
        cliente = cfg.get("cliente") if isinstance(cfg, dict) else cfg
        obras.append((str(nombre).strip(), str(cliente).strip() if cliente else None))
    return [(o, c) for o, c in obras if o]


def sembrar_tarifas(
    conn: sqlite3.Connection, ruta: str | Path, *, usuario_id: int | None = None,
) -> ResultadoSemilla:
    """Siembra el fichero de tarifas en el almacen. Una transaccion, un evento de datos."""
    ruta = Path(ruta)
    texto = ruta.read_text(encoding="utf-8")
    datos = yaml.safe_load(texto) or {}
    sha256 = sha256_texto(texto)
    resultado = ResultadoSemilla(fichero=ruta.name, sha256=sha256)
    origen = Automatico(Fuente.MAESTRO.value, usuario_sistema(conn, "importador"),
                        ref=f"config:{ruta.name}@{sha256[:12]}", usuario_id=usuario_id)

    with transaccion(conn):
        resultado.nueva_politica = _politica(conn, ruta.name, texto, sha256, usuario_id)
        with campos.orden(conn, origen, tipo="semilla_tarifas",
                          datos={"fichero": ruta.name, "sha256": sha256}) as o:
            clientes: dict[str, int] = {}
            for _obra, cliente in _obras(datos):
                if cliente is None or normalizar_nombre(cliente) in clientes:
                    continue
                encontrado = resolver_parte(conn, "cliente", nombre=cliente).fila_id
                if encontrado is None:
                    encontrado = o.crear("cliente", {"nombre": cliente})
                    o.crear("alias", {"tabla": "cliente", "alias": cliente, "fila_id": encontrado,
                                      "origen": "config", "confirmado": True})
                    resultado.clientes_nuevos += 1
                clientes[normalizar_nombre(cliente)] = encontrado

            objetos: dict[str, int] = {}
            for obra, cliente in _obras(datos):
                cliente_id = clientes.get(normalizar_nombre(cliente)) if cliente else None
                encontrado = resolver_objeto(conn, obra).fila_id
                if encontrado is None:
                    encontrado = o.crear("objeto", {"codigo": obra, "nombre": obra,
                                                     "cliente_id": cliente_id})
                    resultado.objetos_nuevos += 1
                elif cliente_id is not None:
                    o.fijar("objeto", encontrado, {"cliente_id": cliente_id})
                objetos[normalizar_nombre(obra)] = encontrado

            for entrada in datos.get("tarifas") or []:
                if not isinstance(entrada, dict):
                    continue
                trabajo = str(entrada.get("trabajo") or "").strip().lower()
                obra = str(entrada.get("obra") or "").strip()
                try:
                    tarifa = parse_amount(str(entrada.get("tarifa")))
                except ParseError:
                    resultado.avisos.append(f"tarifa ilegible para {obra or '*'}/{trabajo}: "
                                            f"{entrada.get('tarifa')!r}")
                    continue
                if not trabajo:
                    continue
                objeto_id = objetos.get(normalizar_nombre(obra)) if obra else None
                if obra and objeto_id is None:
                    objeto_id = resolver_objeto(conn, obra).fila_id
                    if objeto_id is None:
                        resultado.avisos.append(
                            f"la tarifa de {obra}/{trabajo} es de un Objeto que no esta en obras")
                        continue
                existente = conn.execute(
                    "SELECT id, tarifa_e4 FROM tarifa_acordada WHERE sentido = 'venta' "
                    "AND fuente = 'config' AND objeto_id IS ? AND tipo_servicio = ? "
                    "AND vigente_hasta IS NULL", (objeto_id, trabajo)).fetchone()
                literal = Leido(tarifa, crudo=entrada.get("tarifa"))
                if existente is None:
                    o.crear("tarifa_acordada", {
                        "sentido": "venta", "objeto_id": objeto_id, "tipo_servicio": trabajo,
                        "unidad": "hora", "tarifa_e4": literal, "fuente": "config",
                    })
                    resultado.tarifas_nuevas += 1
                else:
                    antes = existente["tarifa_e4"]
                    o.fijar("tarifa_acordada", existente["id"], {"tarifa_e4": literal})
                    if o.fila("tarifa_acordada", existente["id"])["tarifa_e4"] != antes:
                        resultado.tarifas_cambiadas += 1

        from ..ingesta import reconciliar_referencias

        resultado.imputaciones_resueltas = reconciliar_referencias(conn)
    return resultado
