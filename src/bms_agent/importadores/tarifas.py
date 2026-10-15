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
- La orden termina recalculando las reglas, en la misma transaccion.

Desde el paso 5, leer el fichero (`leer_semilla`) da los mismos registros
canonicos que un mapeo de CSV, con su test de contrato. Escribirlos sigue
siendo cosa de esta orden y no de importadores/registrar.py: la semilla es un
fichero de la politica (vuelve a valer lo que se carga, tambien una version
anterior), no una importacion que se hace una vez por fichero.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .. import campos, politica
from ..almacen import transaccion, usuario_sistema
from ..almacen.unidades import sha256_texto
from ..campos import Automatico, Leido
from ..dominio import Fuente
from ..identidad import normalizar_nombre, resolver_objeto, resolver_parte
from ..parsing import ParseError, parse_amount
from .canonico import ClienteCanonico, ObjetoCanonico, TarifaCanonica


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
    # La pasada del motor de reglas con la que termina la orden (paso 3).
    recalculo: Any = None


def _obras(datos: dict[str, Any]) -> list[tuple[str, str | None]]:
    obras = []
    for nombre, cfg in (datos.get("obras") or {}).items():
        cliente = cfg.get("cliente") if isinstance(cfg, dict) else cfg
        obras.append((str(nombre).strip(), str(cliente).strip() if cliente else None))
    return [(o, c) for o, c in obras if o]


@dataclass(frozen=True)
class Semilla:
    """Lo que dice un tarifas.yaml, en registros canonicos (el mismo marco que un CSV)."""

    clientes: tuple[ClienteCanonico, ...]
    objetos: tuple[ObjetoCanonico, ...]
    tarifas: tuple[TarifaCanonica, ...]
    avisos: tuple[str, ...]


def leer_semilla(texto: str) -> Semilla:
    """Lee un tarifas.yaml sin escribir nada: clientes, Objetos y tarifas de venta.

    Es el lector de la semilla: puro, con su test de contrato
    (tests/fixtures/importacion/config-tarifas.esperado.json) como cada
    mapeo de config/importacion. `fila` es la posicion en su lista del
    fichero (las obras y las tarifas empiezan en 1).
    """
    datos = yaml.safe_load(texto) or {}
    clientes: dict[str, ClienteCanonico] = {}
    objetos = []
    for fila, (obra, cliente) in enumerate(_obras(datos), start=1):
        crudo = {"obra": obra, "cliente": cliente or ""}
        if cliente is not None and normalizar_nombre(cliente) not in clientes:
            clientes[normalizar_nombre(cliente)] = ClienteCanonico(fila=fila, crudo=crudo,
                                                                   nombre=cliente)
        objetos.append(ObjetoCanonico(fila=fila, crudo=crudo, codigo=obra, nombre=obra,
                                      cliente_ref=cliente))
    tarifas, avisos = [], []
    for fila, entrada in enumerate(datos.get("tarifas") or [], start=1):
        if not isinstance(entrada, dict):
            continue
        trabajo = str(entrada.get("trabajo") or "").strip().lower()
        obra = str(entrada.get("obra") or "").strip()
        literal = str(entrada.get("tarifa"))
        try:
            tarifa = parse_amount(literal)
        except ParseError:
            avisos.append(f"tarifa ilegible para {obra or '*'}/{trabajo}: "
                          f"{entrada.get('tarifa')!r}")
            continue
        if not trabajo:
            continue
        # El literal es el texto que leyo parse_amount: un numero YAML
        # (tarifa: 62.5) llega como float, y un float no entra en el JSON
        # canonico.
        tarifas.append(TarifaCanonica(
            fila=fila, crudo={k: str(v) for k, v in entrada.items()}, sentido="venta",
            objeto_ref=obra or None, tipo_servicio=trabajo, unidad="hora", tarifa=tarifa,
            tarifa_crudo=literal))
    return Semilla(tuple(clientes.values()), tuple(objetos), tuple(tarifas), tuple(avisos))


def contrato_semilla(texto: str) -> dict[str, Any]:
    """Lo que da leer un tarifas.yaml, en JSON: lo que fija su test de contrato."""
    semilla = leer_semilla(texto)
    return {"semilla": "config/tarifas.yaml",
            "clientes": [c.model_dump(mode="json") for c in semilla.clientes],
            "objetos": [o.model_dump(mode="json") for o in semilla.objetos],
            "tarifas": [t.model_dump(mode="json") for t in semilla.tarifas],
            "avisos": list(semilla.avisos)}


def sembrar_tarifas(
    conn: sqlite3.Connection, ruta: str | Path, *, usuario_id: int | None = None,
) -> ResultadoSemilla:
    """Siembra el fichero de tarifas en el almacen. Una transaccion, un evento de datos."""
    ruta = Path(ruta)
    texto = ruta.read_text(encoding="utf-8")
    semilla = leer_semilla(texto)
    sha256 = sha256_texto(texto)
    resultado = ResultadoSemilla(fichero=ruta.name, sha256=sha256, avisos=list(semilla.avisos))
    origen = Automatico(Fuente.MAESTRO.value, usuario_sistema(conn, "importador"),
                        ref=f"config:{ruta.name}@{sha256[:12]}", usuario_id=usuario_id)

    with transaccion(conn):
        resultado.nueva_politica = politica.registrar(conn, ruta.name, texto, usuario_id)
        with campos.orden(conn, origen, tipo="semilla_tarifas",
                          datos={"fichero": ruta.name, "sha256": sha256}) as o:
            clientes: dict[str, int] = {}
            for cliente in semilla.clientes:
                encontrado = resolver_parte(conn, "cliente", nombre=cliente.nombre).fila_id
                if encontrado is None:
                    encontrado = o.crear("cliente", {"nombre": cliente.nombre})
                    o.crear("alias", {"tabla": "cliente", "alias": cliente.nombre,
                                      "fila_id": encontrado, "origen": "config",
                                      "confirmado": True})
                    resultado.clientes_nuevos += 1
                clientes[normalizar_nombre(cliente.nombre)] = encontrado

            objetos: dict[str, int] = {}
            for objeto in semilla.objetos:
                cliente_id = (clientes.get(normalizar_nombre(objeto.cliente_ref))
                              if objeto.cliente_ref else None)
                encontrado = resolver_objeto(conn, objeto.codigo).fila_id
                if encontrado is None:
                    encontrado = o.crear("objeto", {"codigo": objeto.codigo,
                                                     "nombre": objeto.nombre,
                                                     "cliente_id": cliente_id})
                    resultado.objetos_nuevos += 1
                elif cliente_id is not None:
                    o.fijar("objeto", encontrado, {"cliente_id": cliente_id})
                objetos[normalizar_nombre(objeto.codigo)] = encontrado

            for tarifa in semilla.tarifas:
                obra = tarifa.objeto_ref
                objeto_id = objetos.get(normalizar_nombre(obra)) if obra else None
                if obra and objeto_id is None:
                    objeto_id = resolver_objeto(conn, obra).fila_id
                    if objeto_id is None:
                        resultado.avisos.append(
                            f"la tarifa de {obra}/{tarifa.tipo_servicio} es de un Objeto que no "
                            "esta en obras")
                        continue
                existente = conn.execute(
                    "SELECT id, tarifa_e4 FROM tarifa_acordada WHERE sentido = 'venta' "
                    "AND fuente = 'config' AND objeto_id IS ? AND tipo_servicio = ? "
                    "AND vigente_hasta IS NULL", (objeto_id, tarifa.tipo_servicio)).fetchone()
                literal = Leido(tarifa.tarifa, crudo=tarifa.tarifa_crudo)
                if existente is None:
                    o.crear("tarifa_acordada", {
                        "sentido": "venta", "objeto_id": objeto_id,
                        "tipo_servicio": tarifa.tipo_servicio, "unidad": "hora",
                        "tarifa_e4": literal, "fuente": "config",
                    })
                    resultado.tarifas_nuevas += 1
                else:
                    antes = existente["tarifa_e4"]
                    o.fijar("tarifa_acordada", existente["id"], {"tarifa_e4": literal})
                    if o.fila("tarifa_acordada", existente["id"])["tarifa_e4"] != antes:
                        resultado.tarifas_cambiadas += 1

        from ..hallazgos import recalcular
        from ..identidad import reconciliar_referencias

        resultado.imputaciones_resueltas = reconciliar_referencias(conn)
        # Un Objeto que ahora se resuelve cambia lo que leen las reglas (B4 por
        # Objeto, G3): la orden acaba con su recalculo, en su transaccion.
        resultado.recalculo = recalcular(conn, motivo="importacion", usuario_id=usuario_id)
    return resultado
