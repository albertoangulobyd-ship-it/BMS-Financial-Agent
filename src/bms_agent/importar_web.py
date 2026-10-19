"""Importar un fichero desde la app local (paso 15): POST /api/v2/importar.

Es la misma orden que `bms-agent importar` (cli._cmd_importar), con las mismas
garantias, porque llama a lo mismo (importadores.registrar.importar_fichero):
la persona y su permiso importar_datos, todo o nada, la auditoria de cada lote,
la pasada del motor de reglas al final y la guarda de los datos de prueba. Lo
unico distinto es de donde llegan los bytes: los sube el navegador dentro de un
JSON, en base64, y no se escriben en ninguna carpeta (ni temporal): el nombre
que trae la peticion es solo un nombre, nunca una ruta que se abra.

Por eso aqui hay tan poco, y todo puro salvo `importar`:

- `leer_peticion`: la forma estricta del cuerpo (claves conocidas, base64 valido,
  tamano maximo, un nombre sin carpetas ni caracteres de control, una fecha).
- `detectar`: que clase de fichero es, mirando lo mismo que mira el importador
  (la huella de las columnas de cada mapeo, CAMT.053, MT940, el YAML de PO). Si
  lo reconocen dos clases, no se elige por la persona: se le pregunta.
- `importar`: primero se simula (simular=True: se hace entero y se deshace) y
  solo despues, con otra peticion, se guarda. La app no deja guardar sin haber
  visto antes la simulacion, pero quien decide que se puede es esta orden.
- `resultado`: lo que hizo o haria, en cuentas y codigos (lo que la app dice en
  neerlandes o en ingles); las frases en espanol del importador (`motivo`,
  `avisos`) siguen ahi para el soporte, como el `error` de los errores.

Ni procesos, ni red: el fichero se lee en memoria y entra por el almacen.
"""

from __future__ import annotations

import base64
import binascii
import re
import sqlite3
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# Un extracto de un ano o un maestro de miles de filas caben de sobra; lo que pasa de
# aqui no es una exportacion normal, y leerlo entero en memoria no es razonable.
MAX_FICHERO = 8 * 1024 * 1024
# El cuerpo lleva el fichero en base64 (4 bytes por cada 3) y unas pocas claves mas.
MAX_CUERPO = (MAX_FICHERO + 2) // 3 * 4 + 16 * 1024
# Cuantos rechazos y avisos van en la respuesta: el resto lo cuenta `rechazadas`.
MAX_RECHAZOS = 100
CLAVES = frozenset({"fichero", "contenido", "fuente", "tipo", "simular", "exportado",
                    "confirmar"})
_SIN_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class PeticionNoValida(ValueError):
    """El cuerpo no tiene la forma de una importacion (un 400 `invalido`)."""

    codigo = "invalido"


class FicheroDemasiadoGrande(ValueError):
    """El fichero pasa de MAX_FICHERO (un 413)."""

    codigo = "fichero_demasiado_grande"


class FicheroNoReconocido(ValueError):
    """Ninguna clase de fichero conocida lo reconoce: la persona tiene que elegirla."""

    codigo = "fichero_no_reconocido"


class TipoAmbiguo(ValueError):
    """Lo reconocen varias clases: la persona elige una (van en `candidatos`)."""

    codigo = "tipo_ambiguo"

    def __init__(self, candidatos: list[tuple[str, str]]) -> None:
        super().__init__("el fichero puede ser " + ", ".join(f"{f}/{t}" for f, t in candidatos)
                         + ": elige cual")
        self.candidatos = candidatos


class FicheroNoValido(ValueError):
    """El fichero no se lee como la clase elegida (columnas, codificacion, XML, YAML)."""

    codigo = "fichero_no_valido"


@dataclass(frozen=True)
class Peticion:
    nombre: str
    contenido: bytes
    fuente: str | None
    tipo: str | None
    simular: bool
    exportado: date | None
    confirmar: bool


def nombre_de_fichero(texto: Any) -> str:
    """El nombre que se guarda con el documento: lo ultimo tras una barra, sin caracteres de
    control y de 200 caracteres como mucho. Nunca se abre como ruta."""
    if not isinstance(texto, str):
        raise PeticionNoValida("fichero: el nombre del fichero es un texto")
    nombre = unicodedata.normalize("NFC", texto).replace("\\", "/").rsplit("/", 1)[-1]
    nombre = _SIN_CONTROL.sub("", nombre).strip()
    if not nombre or nombre in (".", "..") or len(nombre) > 200:
        raise PeticionNoValida("fichero: un nombre de fichero de 1 a 200 caracteres")
    return nombre


def _booleano(cuerpo: dict[str, Any], clave: str) -> bool:
    valor = cuerpo.get(clave, False)
    if not isinstance(valor, bool):
        raise PeticionNoValida(f"{clave}: true o false")
    return valor


def _texto_o_nada(cuerpo: dict[str, Any], clave: str) -> str | None:
    valor = cuerpo.get(clave)
    if valor is None or valor == "":
        return None
    if not isinstance(valor, str) or not re.fullmatch(r"[a-z0-9_]{1,40}", valor):
        raise PeticionNoValida(f"{clave}: un nombre en minusculas, como los de la CLI")
    return valor


def leer_peticion(cuerpo: dict[str, Any], *, maximo: int | None = None) -> Peticion:
    """El cuerpo de POST /api/v2/importar, comprobado. Funcion pura.

    {fichero, contenido (base64), fuente, tipo, simular, exportado (AAAA-MM-DD), confirmar}:
    fuente y tipo van juntos o ninguno (se detecta); `simular` por defecto es False, pero
    la app siempre simula primero.
    """
    maximo = MAX_FICHERO if maximo is None else maximo
    sobran = sorted(set(cuerpo) - CLAVES)
    if sobran:
        raise PeticionNoValida(f"una importacion no lleva {', '.join(sobran)}")
    nombre = nombre_de_fichero(cuerpo.get("fichero"))
    crudo = cuerpo.get("contenido")
    if not isinstance(crudo, str) or not crudo:
        raise PeticionNoValida("contenido: los bytes del fichero en base64")
    if len(crudo) > (maximo + 2) // 3 * 4 + 4:
        raise FicheroDemasiadoGrande(f"el fichero pasa de {maximo // (1024 * 1024)} MB")
    try:
        contenido = base64.b64decode(crudo, validate=True)
    except (binascii.Error, ValueError):
        raise PeticionNoValida("contenido: no es base64") from None
    if not contenido:
        raise PeticionNoValida("contenido: el fichero esta vacio")
    if len(contenido) > maximo:
        raise FicheroDemasiadoGrande(f"el fichero pasa de {maximo // (1024 * 1024)} MB")
    fuente, tipo = _texto_o_nada(cuerpo, "fuente"), _texto_o_nada(cuerpo, "tipo")
    if (fuente is None) != (tipo is None):
        raise PeticionNoValida("fuente y tipo van juntos (o ninguno: se detecta)")
    exportado = None
    if cuerpo.get("exportado") not in (None, ""):
        texto = cuerpo["exportado"]
        try:
            if not isinstance(texto, str):
                raise ValueError
            exportado = date.fromisoformat(texto)
        except ValueError:
            raise PeticionNoValida("exportado: una fecha AAAA-MM-DD") from None
    return Peticion(nombre=nombre, contenido=contenido, fuente=fuente, tipo=tipo,
                    simular=_booleano(cuerpo, "simular"), exportado=exportado,
                    confirmar=_booleano(cuerpo, "confirmar"))


# ------------------------------------------------------------ las clases de fichero

def tipos() -> list[tuple[str, str]]:
    """Lo que se puede importar: cada fuente y tipo con un mapeo en config/importacion, y el
    banco (CAMT.053, MT940 o un CSV del banco). Las mismas que `bms-agent importar`."""
    from .importadores.tabular import mapeos

    salida: list[tuple[str, str]] = []
    for m in mapeos():
        if (m.fuente, m.tipo) not in salida:
            salida.append((m.fuente, m.tipo))
    if ("banco", "extracto") not in salida:
        salida.append(("banco", "extracto"))
    return salida


def detectar(contenido: bytes, nombre: str) -> list[tuple[str, str]]:
    """Las clases que reconocen el fichero, sin escribir nada (lo que mira el importador)."""
    from .importadores import camt053, mt940, ordenes
    from .importadores.tabular import LectorTabular, mapeos

    if Path(nombre).suffix.lower() in (".yaml", ".yml"):
        try:
            datos = ordenes._cargar(contenido)
        except ordenes.YamlNoValido:
            return []
        return [("po_csv", "ordenes_compra" if datos.get("ordenes") else "modificaciones_po")]
    if camt053.reconoce(contenido) or mt940.reconoce(contenido):
        return [("banco", "extracto")]
    vistos: list[tuple[str, str]] = []
    for m in mapeos():
        if (m.fuente, m.tipo) in vistos:
            continue
        if LectorTabular(m, m.registros[0].tipo).reconoce(contenido, nombre):
            vistos.append((m.fuente, m.tipo))
    return vistos


def elegir(peticion: Peticion) -> tuple[str, str]:
    """La clase de la importacion: la pedida, o la unica que reconoce el fichero."""
    if peticion.fuente is not None and peticion.tipo is not None:
        if (peticion.fuente, peticion.tipo) not in tipos():
            raise PeticionNoValida(f"no se importa {peticion.fuente}/{peticion.tipo}")
        return peticion.fuente, peticion.tipo
    candidatos = detectar(peticion.contenido, peticion.nombre)
    if not candidatos:
        raise FicheroNoReconocido(f"{peticion.nombre} no es ninguna de las exportaciones que se "
                                  "conocen: elige que es")
    if len(candidatos) > 1:
        raise TipoAmbiguo(candidatos)
    return candidatos[0]


def exportado_en(dia: date | None, ahora: datetime | None = None) -> datetime:
    """Cuando se saco el fichero de su sistema (lo que mide la frescura, Z1): el dia dicho a
    mediodia UTC, como `--exportado` de la CLI; sin el, ahora."""
    if dia is None:
        return ahora or datetime.now(timezone.utc)
    return datetime(dia.year, dia.month, dia.day, 12, tzinfo=timezone.utc)


# ------------------------------------------------------------ la orden

def importar(almacen: Any, usuario_id: int, peticion: Peticion) -> dict[str, Any]:
    """Simula o importa el fichero, como `bms-agent importar` (con --simular si se pide).

    Los errores de lectura salen como FicheroNoValido; el permiso, los datos de prueba y la
    confirmacion del planning, con sus propias excepciones (cada una con su codigo).
    """
    from .almacen import DatosDePrueba
    from .importadores.planning import PideConfirmacion
    from .importadores.registrar import importar_fichero

    fuente, tipo = elegir(peticion)
    if peticion.confirmar and (fuente, tipo) != ("trnsprnt", "planning"):
        raise PeticionNoValida("confirmar solo vale para el planning (trnsprnt planning)")
    try:
        r = importar_fichero(almacen, fuente, tipo, Path(peticion.nombre),
                             lanzado_por=usuario_id, exportado_en=exportado_en(peticion.exportado),
                             simular=peticion.simular, confirmar=peticion.confirmar,
                             contenido=peticion.contenido)
    except (PideConfirmacion, DatosDePrueba):
        raise
    except ValueError as exc:
        # Lo mismo que la CLI dice "No se importa: ..." (MapeoNoValido, FicheroIlegible, un
        # XML o un YAML que no se leen, columnas que no son las del mapeo, una fecha futura).
        raise FicheroNoValido(str(exc)) from None
    return resultado(r, fuente, tipo)


def _cuentas(lote: Any) -> dict[str, Any] | None:
    if not lote.cuentas:
        return None
    return {"vistas": sum(c.vistas for c in lote.cuentas),
            "nuevas": sum(len(c.nuevas) for c in lote.cuentas),
            "ausentes": sum(len(c.ausentes) for c in lote.cuentas),
            "primer_maestro": any(c.baseline for c in lote.cuentas)}


# La tabla de lo que trae cada clase de lote: "1 nuevo" en un maestro de clientes es un
# cliente, no el cliente y su alias. Una que no esta aqui cuenta todas sus filas nuevas.
PRINCIPAL = {"proveedores": "proveedor", "clientes": "cliente", "contactos": "contacto",
             "objetos": "objeto", "recursos": "recurso", "alias": "alias",
             "cuentas": "cuenta_bancaria", "tarifas": "tarifa_acordada",
             "ciclos": "ciclo_facturacion", "ordenes_compra": "orden_compra",
             "modificaciones_po": "orden_compra_modificacion", "facturas_venta": "factura",
             "extracto": "movimiento_bancario", "planning": "planning_turno"}


def _nuevos(lote: Any) -> int:
    principal = PRINCIPAL.get(lote.tipo)
    if principal is None:
        return len(lote.nuevos)
    return sum(1 for tabla, _id in lote.nuevos if tabla == principal)


def _lote(lote: Any) -> dict[str, Any]:
    return {
        "tipo": lote.tipo, "estado": lote.estado, "repetida": lote.repetida,
        # Simulando, el numero es el de una importacion que se deshizo: no existe.
        "importacion_id": None if lote.simulada else lote.importacion_id,
        "filas_leidas": lote.filas_leidas, "aceptadas": lote.aceptadas,
        "rechazadas": len(lote.rechazos),
        "rechazos": [{"fila": x.fila, "codigo": x.codigo, "motivo": x.motivo}
                     for x in lote.rechazos[:MAX_RECHAZOS]],
        "nuevos": _nuevos(lote),
        "nuevos_por_tabla": dict(sorted(Counter(tabla for tabla, _id in lote.nuevos).items())),
        "cambiados": len(lote.cambiados),
        "sin_resolver": len(lote.sin_resolver), "retirados": len(lote.retirados),
        "cuentas": _cuentas(lote), "avisos": list(lote.avisos[:MAX_RECHAZOS]),
    }


def resultado(r: Any, fuente: str, tipo: str) -> dict[str, Any]:
    """Lo que hizo (o haria) la importacion, en cuentas y codigos."""
    recalculo = r.recalculo
    conciliacion = getattr(recalculo, "conciliacion", None) if recalculo is not None else None
    return {
        "fichero": r.fichero, "mapeo": r.mapeo, "fuente": fuente, "tipo": tipo,
        "simulada": r.simulada, "lotes": [_lote(lote) for lote in r.lotes],
        # Lo que la pasada del motor movio: nuevos (detectado), cerrados solos, reabiertos...
        "hallazgos": dict(sorted(Counter(t.tipo for t in recalculo.transiciones).items()))
        if recalculo is not None else {},
        "pagos": {"casados": len(conciliacion.automaticas),
                  "propuestas": len(conciliacion.propuestas)}
        if conciliacion is not None else None,
    }


# ------------------------------------------------------------ la historia

def historial(conn: sqlite3.Connection, limite: int = 30) -> list[dict[str, Any]]:
    """Las ultimas importaciones, la mas reciente primero: que, cuando, quien y como acabo."""
    filas = conn.execute(
        "SELECT i.id, i.fuente, i.tipo, i.formato, i.estado, i.filas_leidas, "
        "i.filas_aceptadas, i.filas_rechazadas, i.exportado_en, i.iniciada_en, "
        "i.terminada_en, u.nombre AS persona, d.nombre_original AS fichero "
        "FROM importacion AS i LEFT JOIN usuario AS u ON u.id = i.iniciada_por "
        "LEFT JOIN documento AS d ON d.id = i.documento_id "
        "ORDER BY i.iniciada_en DESC, i.id DESC LIMIT ?", (limite,)).fetchall()
    return [dict(f) for f in filas]
