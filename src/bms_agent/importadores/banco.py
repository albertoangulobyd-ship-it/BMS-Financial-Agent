"""Los ficheros del banco: elegir el lector, leer los CSV del banco y la orden de importar.

Un fichero del banco puede ser un CAMT.053 (camt053.py), un MT940
(mt940.py) o el CSV que exporta la banca por internet de un banco, con su
mapeo en config/importacion/banco-extracto-<banco>-vN.yaml. El lector se
elige por lo que trae el fichero (un XML, un :20:, las columnas del CSV), o
se pide (`--formato camt053`, `mt940:ing`, el id de un mapeo).

Los CSV del banco van "sin saldos": no traen un saldo de apertura y de cierre
fiables, asi que con ellos no se comprueba la continuidad de los extractos
(K6). Cada cuenta propia del fichero es un extracto sin saldos.

Lo demas es lo de cualquier importacion (registrar_lote): el fichero entra
entero o nada, la cuenta tiene que ser de BM Support BV, un movimiento que ya
estaba no entra otra vez y la orden termina con la pasada del motor, que
casa los movimientos con las facturas (pagos.py) y evalua las reglas.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from ..almacen import Almacen, exigir_de_su_base, transaccion
from ..dominio import Permiso
from ..permisos import exigir, orden_auditada
from . import camt053, mt940
from .base import LoteLeido, Rechazo
from .camt053 import FicheroNoAdmitido
from .canonico import ExtractoCanonico
from .registrar import ResultadoImportacion, _Simulacion, registrar_lote
from .tabular import LectorTabular, Mapeo, cargar_mapeo, elegir_mapeo, mapeos

FUENTE = "banco"
TIPO = "extracto"


def lote_de_csv(lote: LoteLeido) -> LoteLeido:
    """Los movimientos de un CSV del banco, agrupados en un extracto sin saldos por cuenta."""
    por_cuenta: dict[str, list] = defaultdict(list)
    rechazos = list(lote.rechazos)
    for movimiento in lote.registros:
        if not movimiento.cuenta_propia_iban:
            rechazos.append(Rechazo(movimiento.fila, "la fila no dice de que cuenta es",
                                    dict(movimiento.crudo)))
            continue
        por_cuenta[movimiento.cuenta_propia_iban].append(movimiento)
    extractos = []
    for numero, (cuenta, movimientos) in enumerate(sorted(por_cuenta.items()), start=1):
        fechas = [m.fecha_contable for m in movimientos]
        try:
            extractos.append(ExtractoCanonico(
                fila=numero, crudo={"cuenta": cuenta}, cuenta_propia_iban=cuenta,
                moneda="EUR", desde=min(fechas), hasta=max(fechas), con_saldos=False,
                formato=lote.formato, movimientos=tuple(movimientos)))
        except ValueError as exc:
            rechazos.append(Rechazo(movimientos[0].fila, f"la cuenta {cuenta}: {exc}",
                                    dict(movimientos[0].crudo)))
    desdes = [e.desde for e in extractos if e.desde]
    hastas = [e.hasta for e in extractos if e.hasta]
    exportado = lote.exportado_en
    return replace(lote, tipo=TIPO, registros=tuple(extractos), rechazos=tuple(rechazos),
                   cubre_desde=min(desdes) if desdes else None,
                   cubre_hasta=max(hastas) if hastas else None, exportado_en=exportado)


def mapeos_csv() -> list[Mapeo]:
    return [m for m in mapeos() if m.fuente == FUENTE and m.tipo == TIPO]


def leer(contenido: bytes, nombre: str = "", *, formato: str | None = None,
         exportado_en: datetime | None = None) -> tuple[LoteLeido, Mapeo | None]:
    """El lote de un fichero del banco y, si es un CSV, su mapeo.

    `formato`: camt053, mt940 o mt940:<banco> (ing, abn, rabobank), o el id o
    la ruta de un mapeo de CSV. Sin el, se elige por el contenido.
    """
    if formato == "camt053" or (formato is None and camt053.reconoce(contenido)):
        return camt053.leer(contenido, nombre, exportado_en=exportado_en), None
    if (formato or "").startswith("mt940") or (formato is None and mt940.reconoce(contenido)):
        perfil = formato.split(":", 1)[1] if formato and ":" in formato else None
        return mt940.leer(contenido, nombre, exportado_en=exportado_en, perfil=perfil), None
    if formato is not None:
        candidatos = [m for m in mapeos_csv() if m.id == formato]
        mapeo = candidatos[0] if candidatos else cargar_mapeo(formato)
    else:
        mapeo = elegir_mapeo(FUENTE, TIPO, contenido, nombre)
    lector = LectorTabular(mapeo, "movimientos")
    if not lector.reconoce(contenido, nombre):
        raise FicheroNoAdmitido(f"{nombre or 'el fichero'} no tiene las columnas del mapeo "
                                f"{mapeo.id}")
    return lote_de_csv(lector.leer(contenido, nombre, exportado_en=exportado_en)), mapeo


def importar_extracto(almacen: Almacen, ruta: str | Path, *, lanzado_por: int,
                      formato: str | None = None, exportado_en: datetime | None = None,
                      simular: bool = False) -> ResultadoImportacion:
    """La orden entera de importar un fichero del banco, todo o nada, con su pasada del motor.

    La pasada (hallazgos.recalcular) casa los movimientos nuevos con las
    facturas (pagos.conciliar) y evalua K1-K8 y F7 en la misma transaccion.
    Simulando, se hace todo y se deshace.
    """
    from ..hallazgos import recalcular

    ruta = Path(ruta)
    contenido = ruta.read_bytes()
    conn = almacen.conn
    exigir_de_su_base(conn, contenido, ruta.name)
    lote, mapeo = leer(contenido, ruta.name, formato=formato, exportado_en=exportado_en)
    resultado = ResultadoImportacion(fichero=ruta.name, mapeo=mapeo.id if mapeo else lote.formato,
                                     simulada=simular)

    def hacer() -> ResultadoImportacion:
        resultado.lotes.append(registrar_lote(
            almacen, lote, lanzado_por=lanzado_por, nombre=ruta.name,
            contenido=None if simular else contenido,
            tipo_mime=mapeo.tipo_mime if mapeo else (
                "application/xml" if lote.formato.startswith("camt") else "text/plain")))
        nuevas = [r for r in resultado.lotes if not r.repetida]
        if nuevas and mapeo is not None and mapeo.texto:
            from .. import politica

            politica.registrar(conn, f"importacion/{mapeo.id}.yaml", mapeo.texto, lanzado_por)
        if nuevas:
            causa = max((r.evento_id for r in nuevas if r.evento_id), default=None)
            resultado.recalculo = recalcular(conn, motivo="importacion", usuario_id=lanzado_por,
                                             causa_evento_id=causa)
        return resultado

    with orden_auditada(conn):
        exigir(conn, lanzado_por, Permiso.IMPORTAR_DATOS.value, accion="importar banco/extracto")
        if not simular:
            return hacer()
        try:
            with transaccion(conn):
                raise _Simulacion(hacer())
        except _Simulacion:
            for lote_ in resultado.lotes:
                lote_.simulada = True
            return resultado
