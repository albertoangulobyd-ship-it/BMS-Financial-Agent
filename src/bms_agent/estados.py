"""Las caches de estado: factura_estado y prioridad, rehechas en cada pasada del motor.

Despues de poner al dia los hallazgos y las excepciones, la pasada
(hallazgos.recalcular) calcula aqui, para cada factura, lo que dicen de ella
los demas modulos y lo deja en una fila que se puede filtrar con SQL:

- su estado de pago (sin pagos importados hasta el paso 7: pendiente o
  vencida por su vencimiento efectivo, anulada si se anulo);
- su estado de revision (revision.py), con la huella de su contenido;
- su calidad de dato, sus marcas de edicion manual, sus campos dudosos y sus
  cambios sin resolver;
- su prioridad (prioridad.py), con la huella de las entradas y el hash de
  los pesos con que se calculo.

Y en la cache prioridad, la de cada excepcion sin resolver y la de cada
proveedor, cliente, Objeto y trimestre (el maximo de sus facturas).

Son caches: se pueden borrar y rehacer, y no son la fuente de nada. Solo se
reescribe lo que cambia, como la cache de evaluaciones: una fila que no
cambia conserva la pasada desde la que vale. Lo que devuelve (`Cambios`) es
lo que una orden ensena: que prioridades se movieron y que revisiones dejaron
de valer.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from . import politica, prioridad, revision
from .almacen import comprobar_entidad, reloj_de
from .auditoria import registrar
from .campos import FaltaMotivo, Persona
from .dominio import (
    ESTADOS_PENDIENTES,
    Calidad,
    EntradaPrioridad,
    EstadoPago,
    EstadoRevision,
    Permiso,
    Sentido,
    Severidad,
)
from .permisos import exigir, orden_auditada
from .prioridad import Entradas, Hallazgo, Hija, Pesos, Subida
from .reglas import catalogo
from .reloj import marca, trimestre_de

_PIDEN_REVISION = frozenset({Severidad.BLOQUEO.value, Severidad.RETENCION.value})
# Como texto: se miran en cada factura de cada pasada, y un Enum.value cuesta.
PENDIENTE = EstadoPago.PENDIENTE.value
VENCIDA = EstadoPago.VENCIDA.value
ANULADA = EstadoPago.ANULADA.value
EN_JUEGO = frozenset({PENDIENTE, VENCIDA})
REVISADA = EstadoRevision.REVISADA.value
ENTRANTE = Sentido.ENTRANTE.value
SALIENTE = Sentido.SALIENTE.value
_ORDEN_CALIDAD = (Calidad.FALTANTE.value, Calidad.DISCREPANCIA.value, Calidad.ANOMALIA.value,
                  Calidad.DUDOSO.value)

_COLUMNAS_ESTADO = (
    "estado_pago", "pendiente_cent", "vencimiento", "dias_vencida", "estado_revision", "calidad",
    "editada", "suplementada", "corregida", "sin_resolver", "dudosos", "pendientes", "sin_datos",
    "excepcion_id", "nivel", "puntos", "suelo", "motivos_json", "huella_contenido",
    "huella_entradas", "politica_sha256",
)
_COLUMNAS_PRIORIDAD = ("nivel", "puntos", "suelo", "motivos_json", "vencimiento", "importe_cent",
                       "huella_entradas", "politica_sha256")


@dataclass(frozen=True)
class CambioPrioridad:
    entidad: str
    entidad_id: int
    antes: str | None
    despues: str | None
    puntos_antes: int | None
    puntos_despues: int | None


@dataclass
class Cambios:
    """Lo que se movio en las caches con esta pasada."""

    prioridades: list[CambioPrioridad] = field(default_factory=list)
    revisiones_invalidadas: list[int] = field(default_factory=list)
    filas_estado: int = 0
    filas_prioridad: int = 0


def _filas(conn: sqlite3.Connection, sql: str, parametros: Sequence[Any] = ()) -> list[tuple]:
    cursor = conn.cursor()
    cursor.row_factory = None
    return cursor.execute(sql, tuple(parametros)).fetchall()


def _motivos(motivos: Sequence[str]) -> str:
    return json.dumps(list(motivos), ensure_ascii=False) if motivos else "[]"


def _fecha(texto: str | None) -> date | None:
    return None if texto is None else date.fromisoformat(texto)


def vencimiento_efectivo(impreso: date | None, fecha_factura: date | None,
                         plazo_dias: int | None) -> date | None:
    """El vencimiento impreso o, si no lo hay, la fecha de la factura mas el plazo de pago."""
    if impreso is not None:
        return impreso
    if fecha_factura is not None and plazo_dias is not None:
        return fecha_factura + timedelta(days=plazo_dias)
    return None


def estado_pago(anulada: bool, fusionada: bool, vencimiento: date | None,
                hoy: date) -> str | None:
    """Sin pagos (hasta el paso 7): anulada, o pendiente/vencida por su vencimiento."""
    if fusionada:
        return None
    if anulada:
        return ANULADA
    if vencimiento is not None and vencimiento < hoy:
        return VENCIDA
    return PENDIENTE


def calidad(calidades: Sequence[str | None], dudosos: int, sin_resolver: int,
            criticos_verificados: bool) -> str | None:
    """La peor calidad de la factura: faltante, discrepancia, anomalia, dudoso.

    Verificado solo si una persona verifico sus campos criticos y no hay nada
    peor. Sin nada de eso, None: neutro, nunca verde.
    """
    vistas = set(c for c in calidades if c)
    if sin_resolver:
        vistas.add(Calidad.DISCREPANCIA.value)
    if dudosos:
        vistas.add(Calidad.DUDOSO.value)
    for nivel in _ORDEN_CALIDAD:
        if nivel in vistas:
            return nivel
    return Calidad.VERIFICADO.value if criticos_verificados else None


def _subidas(conn: sqlite3.Connection) -> dict[tuple[str, int], list[Subida]]:
    salida: dict[tuple[str, int], list[Subida]] = defaultdict(list)
    for entidad, entidad_id, nivel, motivo, quien, hasta in _filas(
            conn, "SELECT p.entidad, p.entidad_id, p.nivel, p.motivo, u.nombre, p.hasta "
                  "FROM prioridad_manual AS p JOIN usuario AS u ON u.id = p.usuario_id "
                  "ORDER BY p.id"):
        salida[(entidad, entidad_id)].append(Subida(nivel, motivo, quien, _fecha(hasta)))
    return salida


def _valor(valores_json: str | None, clave: str) -> int | None:
    try:
        valor = json.loads(valores_json or "{}").get(clave)
    except (json.JSONDecodeError, AttributeError):
        return None
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else None


def _hallazgos(conn: sqlite3.Connection) -> tuple[dict[int, list[Hallazgo]], dict[int, Hallazgo],
                                                  dict[int, list[str | None]]]:
    """Los hallazgos pendientes por factura (la principal y las que cubre), y por id."""
    por_id: dict[int, Hallazgo] = {}
    calidad_de: dict[int, str | None] = {}
    facturas: dict[int, set[int]] = defaultdict(set)
    marcas = ", ".join("?" * len(ESTADOS_PENDIENTES))
    for hallazgo_id, regla, severidad, estado, detalle, valores, factura_id, calidad_ in _filas(
            conn, f"SELECT id, regla, severidad, estado, detalle, valores_json, factura_id, "
                  f"calidad FROM hallazgo WHERE estado IN ({marcas}) ORDER BY id",
            sorted(ESTADOS_PENDIENTES)):
        definicion = catalogo.POR_ID.get(regla)
        entrada = definicion.entrada_prioridad if definicion else EntradaPrioridad.OTRA.value
        por_id[hallazgo_id] = Hallazgo(
            regla=regla, severidad=severidad, estado=estado, entrada=entrada, texto=detalle,
            valor_cent=_valor(valores, "valor_cent"),
            semanas_tras_gracia=_valor(valores, "semanas_tras_gracia"),
            dias_para_caducar=_valor(valores, "dias_para_caducar"))
        calidad_de[hallazgo_id] = calidad_ if estado != "aceptado" else None
        if factura_id is not None:
            facturas[hallazgo_id].add(factura_id)
    if por_id:
        for hallazgo_id, fila_id in _filas(
                conn, "SELECT hallazgo_id, fila_id FROM hallazgo_objetivo WHERE tabla = 'factura'"):
            if hallazgo_id in por_id:
                facturas[hallazgo_id].add(fila_id)
    por_factura: dict[int, list[Hallazgo]] = defaultdict(list)
    calidades: dict[int, list[str | None]] = defaultdict(list)
    for hallazgo_id in sorted(por_id):
        for factura_id in sorted(facturas[hallazgo_id]):
            por_factura[factura_id].append(por_id[hallazgo_id])
            calidades[factura_id].append(calidad_de[hallazgo_id])
    return por_factura, por_id, calidades


@dataclass(frozen=True)
class _Factura:
    id: int
    sentido: str
    numero: str | None
    parte: str | None
    proveedor_id: int | None
    cliente_id: int | None
    fecha_factura: date | None
    vencimiento: date | None
    importe_cent: int | None
    total_cent: int | None
    anulada: bool
    fusionada: bool


def _facturas(conn: sqlite3.Connection) -> list[_Factura]:
    plazos = {("proveedor", i): p for i, p in _filas(
        conn, "SELECT id, plazo_pago_dias FROM proveedor WHERE plazo_pago_dias IS NOT NULL")}
    plazos.update({("cliente", i): p for i, p in _filas(
        conn, "SELECT id, plazo_pago_dias FROM cliente WHERE plazo_pago_dias IS NOT NULL")})
    # El plazo que la ingesta calcula de las condiciones impresas (v2) es lo
    # que dice el proveedor, no lo acordado: solo vale si el maestro no tiene
    # plazo. Si no, un "per omgaande" impreso haria vencer la factura el dia
    # de su fecha. El que fija una persona o una importacion en la factura si
    # manda sobre el maestro.
    del_documento = {f[0] for f in _filas(
        conn, "SELECT fila_id FROM procedencia_campo WHERE tabla = 'factura' "
              "AND campo = 'plazo_pago_dias' AND fuente = 'calculado' "
              "AND fuente_ref = 'condiciones_pago_doc'")}
    salida = []
    for (id_, sentido, numero, emisor, receptor, proveedor_id, cliente_id, fecha, impreso,
         plazo, base, total, anulada, fusionada) in _filas(
            conn, "SELECT id, sentido, numero, emisor_nombre_doc, receptor_nombre_doc, "
                  "proveedor_id, cliente_id, fecha_factura, fecha_vencimiento, plazo_pago_dias, "
                  "base_cent, total_cent, anulada, fusionada_en_id FROM factura ORDER BY id"):
        entrante = sentido == ENTRANTE
        acordado = plazos.get(("proveedor", proveedor_id) if entrante else ("cliente", cliente_id))
        if plazo is None or (id_ in del_documento and acordado is not None):
            plazo = acordado
        fecha_ = _fecha(fecha)
        salida.append(_Factura(
            id=id_, sentido=sentido, numero=numero, parte=emisor if entrante else receptor,
            proveedor_id=proveedor_id, cliente_id=cliente_id, fecha_factura=fecha_,
            vencimiento=vencimiento_efectivo(_fecha(impreso), fecha_, plazo),
            importe_cent=base if base is not None else total, total_cent=total,
            anulada=bool(anulada), fusionada=fusionada is not None))
    return salida


def recalcular(conn: sqlite3.Connection, *, hoy: date, ejecucion_id: int,
               pesos: Pesos | None = None, sin_datos: dict[int, int] | None = None) -> Cambios:
    """Rehace factura_estado y prioridad. Lo llama la pasada del motor, en su transaccion.

    `sin_datos` son las reglas sin datos de cada factura; la pasada ya las
    tiene contadas y se ahorra volver a leer la cache de evaluaciones.
    """
    cambios = Cambios()
    facturas = _facturas(conn)
    # Sin facturas puede haber trabajo: desde el paso 5, excepciones de una
    # importacion o de un proveedor (F0, F5, Z2...), con su prioridad.
    if not facturas and conn.execute("SELECT 1 FROM excepcion WHERE estado <> 'resuelta' "
                                     "LIMIT 1").fetchone() is None:
        return cambios
    # Los pesos con que se calcula quedan siempre en politica_version: si no se
    # cargo ningun fichero, se apuntan los del codigo la primera vez que se usan.
    pesos = pesos or politica.apuntar_pesos_en_uso(conn)
    politica_sha = pesos.sha256()
    hallazgos_de, por_id, calidades = _hallazgos(conn)
    ultimas = revision.ultimas(conn)
    # La huella del contenido solo hace falta donde hay una revision que
    # comprobar: rehacerla para todo el historico en cada pasada costaria mas
    # que todo lo demas. La consola la calcula al abrir una factura.
    huellas = revision.contenidos(conn, [f for f, u in ultimas.items()
                                         if u.resultado == "revisada"])
    de_campos = revision.estado_de_campos(conn)
    vacio = revision.CamposFactura()
    if sin_datos is None:
        sin_datos = dict(_filas(conn, "SELECT fila_id, count(*) FROM evaluacion WHERE tabla = "
                                      "'factura' AND resultado = 'sin_datos' GROUP BY fila_id"))
    excepciones = {f: (e, estado, a, _fecha(s)) for e, f, estado, a, s in _filas(
        conn, "SELECT id, fila_id, estado, esperando_a, fecha_seguimiento FROM excepcion "
              "WHERE tabla = 'factura' AND estado <> 'resuelta'")}
    subidas = _subidas(conn)

    resultados: dict[int, prioridad.Resultado] = {}
    filas_estado: dict[int, tuple] = {}
    for f in facturas:
        lista = hallazgos_de.get(f.id, [])
        pide = any(h.severidad in _PIDEN_REVISION and h.estado != "aceptado" for h in lista)
        campos_ = de_campos.get(f.id, vacio)
        n_sin_resolver = len(campos_.sin_resolver)
        n_dudosos = len(campos_.dudosos)
        ultima = ultimas.get(f.id)
        huella = huellas.get(f.id)
        estado_rev = revision.estado(ultima, huella,
                                     pide or n_sin_resolver > 0 or n_dudosos > 0)
        pago = estado_pago(f.anulada, f.fusionada, f.vencimiento, hoy)
        excepcion = excepciones.get(f.id)
        esperando = excepcion is not None and excepcion[1] == "esperando_externo"
        entradas = Entradas(
            sentido=f.sentido, vencimiento=f.vencimiento,
            en_juego=pago in EN_JUEGO,
            importe_cent=f.importe_cent, fecha_factura=f.fecha_factura, hallazgos=tuple(lista),
            excepcion_abierta=excepcion is not None,
            revisada=estado_rev == REVISADA,
            esperando_a=excepcion[2] if esperando else None,
            fecha_seguimiento=excepcion[3] if esperando else None,
            dudosos=n_dudosos, sin_resolver=n_sin_resolver,
            subidas=tuple(subidas.get(("factura", f.id), ())))
        resultado = prioridad.calcular(entradas, hoy, pesos)
        resultados[f.id] = resultado
        dias = (hoy - f.vencimiento).days if pago == VENCIDA else None
        filas_estado[f.id] = (
            pago,
            f.total_cent if pago in EN_JUEGO else (0 if pago == ANULADA else None),
            f.vencimiento.isoformat() if f.vencimiento else None, dias, estado_rev,
            calidad(calidades.get(f.id, []), n_dudosos, n_sin_resolver,
                    campos_.criticos_verificados),
            int(campos_.editada), int(campos_.suplementada), int(campos_.corregida),
            n_sin_resolver, n_dudosos,
            len(lista), int(sin_datos.get(f.id, 0)),
            excepcion[0] if excepcion else None, resultado.nivel, resultado.puntos,
            resultado.suelo, _motivos(resultado.motivos), huella,
            prioridad.huella_entradas(entradas, hoy, pesos), politica_sha)
    _escribir_estados(conn, filas_estado, ejecucion_id, cambios)
    _escribir_prioridades(conn, _agregados(conn, facturas, resultados, por_id, subidas, hoy,
                                           pesos), ejecucion_id, cambios)
    return cambios


def _escribir_estados(conn: sqlite3.Connection, filas: dict[int, tuple], ejecucion_id: int,
                      cambios: Cambios) -> None:
    columnas = ", ".join(_COLUMNAS_ESTADO)
    anteriores = {f[0]: tuple(f[1:]) for f in _filas(
        conn, f"SELECT factura_id, {columnas} FROM factura_estado")}
    indice_nivel = _COLUMNAS_ESTADO.index("nivel")
    indice_puntos = _COLUMNAS_ESTADO.index("puntos")
    indice_revision = _COLUMNAS_ESTADO.index("estado_revision")
    escribir = []
    for factura_id, fila in filas.items():
        previa = anteriores.get(factura_id)
        if previa == fila:
            continue
        escribir.append((factura_id, *fila, ejecucion_id))
        antes_nivel = previa[indice_nivel] if previa else None
        antes_puntos = previa[indice_puntos] if previa else None
        if (antes_nivel, antes_puntos) != (fila[indice_nivel], fila[indice_puntos]):
            cambios.prioridades.append(CambioPrioridad(
                "factura", factura_id, antes_nivel, fila[indice_nivel], antes_puntos,
                fila[indice_puntos]))
        if (previa is not None and previa[indice_revision] == REVISADA
                and fila[indice_revision] != REVISADA):
            cambios.revisiones_invalidadas.append(factura_id)
    marcas = ", ".join("?" * (len(_COLUMNAS_ESTADO) + 2))
    conn.executemany(
        f"INSERT OR REPLACE INTO factura_estado (factura_id, {columnas}, ejecucion_id) "
        f"VALUES ({marcas})", escribir)
    cambios.filas_estado = len(escribir)


def _hija(f: _Factura, resultado: prioridad.Resultado) -> Hija:
    nombre = f"la factura {f.numero}" if f.numero else f"la factura {f.id}"
    return Hija(f.id, resultado, f.vencimiento, f.importe_cent, nombre)


def _agregados(conn: sqlite3.Connection, facturas: list[_Factura],
               resultados: dict[int, prioridad.Resultado], por_id: dict[int, Hallazgo],
               subidas: dict[tuple[str, int], list[Subida]], hoy: date,
               pesos: Pesos) -> dict[tuple[str, int], tuple]:
    """La prioridad de cada excepcion sin resolver y de lo que tiene facturas."""
    salida: dict[tuple[str, int], tuple] = {}
    por_id_factura = {f.id: f for f in facturas}

    def fila(resultado: prioridad.Resultado, vencimiento: date | None, importe: int | None,
             contenido: Any) -> tuple:
        return (resultado.nivel, resultado.puntos, resultado.suelo,
                json.dumps(list(resultado.motivos), ensure_ascii=False),
                vencimiento.isoformat() if vencimiento else None, importe,
                _huella(contenido, hoy, pesos), pesos.sha256())

    vinculados: dict[int, list[int]] = defaultdict(list)
    for excepcion_id, hallazgo_id in _filas(
            conn, "SELECT eh.excepcion_id, eh.hallazgo_id FROM excepcion_hallazgo AS eh "
                  "JOIN excepcion AS e ON e.id = eh.excepcion_id WHERE e.estado <> 'resuelta' "
                  "ORDER BY eh.hallazgo_id"):
        vinculados[excepcion_id].append(hallazgo_id)
    for excepcion_id, tabla, fila_id in _filas(
            conn, "SELECT id, tabla, fila_id FROM excepcion WHERE estado <> 'resuelta' ORDER BY id"):
        hallazgos = [por_id[h] for h in vinculados.get(excepcion_id, ()) if h in por_id]
        factura = por_id_factura.get(fila_id) if tabla == "factura" else None
        resultado = prioridad.de_excepcion(
            hallazgos, resultados.get(factura.id) if factura else None, hoy,
            subidas.get(("excepcion", excepcion_id), ()))
        salida[("excepcion", excepcion_id)] = fila(
            resultado, factura.vencimiento if factura else None,
            factura.importe_cent if factura else None,
            [excepcion_id, [h.texto for h in hallazgos], resultado.nivel, resultado.puntos])

    # Lo que no esta en juego (anulada, fusionada en otra) no cuenta en su
    # proveedor, cliente, Objeto ni trimestre: no se paga ni se declara. Su
    # trabajo pendiente, si lo tiene, sigue en su excepcion. Paso 7: una pagada
    # tampoco cuenta.
    en_juego = {f.id for f in facturas if not (f.anulada or f.fusionada)}
    hijas: dict[tuple[str, int], list[Hija]] = defaultdict(list)
    for f in facturas:
        if f.id not in en_juego:
            continue
        hija = _hija(f, resultados[f.id])
        if f.sentido == ENTRANTE and f.proveedor_id is not None:
            hijas[("proveedor", f.proveedor_id)].append(hija)
        if f.sentido == SALIENTE and f.cliente_id is not None:
            hijas[("cliente", f.cliente_id)].append(hija)
        if f.fecha_factura is not None:
            ano, trimestre = trimestre_de(f.fecha_factura)
            hijas[("trimestre", ano * 10 + trimestre)].append(hija)
    for factura_id, objeto_id in _filas(
            conn, "SELECT DISTINCT factura_id, objeto_id FROM factura_imputacion "
                  "WHERE objeto_id IS NOT NULL AND retirada_en IS NULL ORDER BY 1, 2"):
        f = por_id_factura.get(factura_id)
        if f is not None and f.id in en_juego:
            hijas[("objeto", objeto_id)].append(_hija(f, resultados[f.id]))
    for entidad, lista in sorted(hijas.items()):
        agregada = prioridad.agregar(lista, hoy, subidas.get(entidad, ()))
        if agregada is None:
            continue
        salida[entidad] = fila(agregada.resultado, agregada.vencimiento,
                               agregada.importe_cent,
                               [[h.id, h.resultado.nivel, h.resultado.puntos] for h in lista]
                               + [agregada.resultado.nivel])
    return salida


def _huella(contenido: Any, hoy: date, pesos: Pesos) -> str:
    """El hash de lo que entro en una prioridad agregada: sus hijas, hoy y los pesos."""
    texto = json.dumps({"contenido": contenido, "hoy": hoy.isoformat(), "pesos": pesos.sha256()},
                       sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _escribir_prioridades(conn: sqlite3.Connection, filas: dict[tuple[str, int], tuple],
                          ejecucion_id: int, cambios: Cambios) -> None:
    columnas = ", ".join(_COLUMNAS_PRIORIDAD)
    anteriores = {(f[1], f[2]): (f[0], tuple(f[3:])) for f in _filas(
        conn, f"SELECT id, entidad, entidad_id, {columnas} FROM prioridad")}
    escribir, borrar = [], []
    for entidad, fila in sorted(filas.items()):
        previa = anteriores.pop(entidad, None)
        if previa is not None and previa[1] == fila:
            continue
        if previa is not None:
            borrar.append((previa[0],))
        escribir.append((*entidad, *fila, ejecucion_id))
        antes = (previa[1][0], previa[1][1]) if previa else (None, None)
        if antes != (fila[0], fila[1]):
            cambios.prioridades.append(CambioPrioridad(entidad[0], entidad[1], antes[0], fila[0],
                                                       antes[1], fila[1]))
    for entidad, (fila_id, previa) in sorted(anteriores.items()):
        borrar.append((fila_id,))
        cambios.prioridades.append(CambioPrioridad(entidad[0], entidad[1], previa[0], None,
                                                   previa[1], None))
    conn.executemany("DELETE FROM prioridad WHERE id = ?", borrar)
    marcas = ", ".join("?" * (len(_COLUMNAS_PRIORIDAD) + 3))
    conn.executemany(
        f"INSERT INTO prioridad (entidad, entidad_id, {columnas}, ejecucion_id) "
        f"VALUES ({marcas})", escribir)
    cambios.filas_prioridad = len(escribir)


# ------------------------------------------------------------ subir a mano

class NoSube(ValueError):
    """Lo pedido no sube nada: la prioridad ya esta por encima, o no es un nivel que se pida."""


_ENTIDADES_A_MANO = ("factura", "excepcion", "proveedor", "cliente", "objeto", "orden_compra",
                     "trimestre")


def nivel_actual(conn: sqlite3.Connection, entidad: str, entidad_id: int) -> str | None:
    """El nivel que se ve ahora en las caches, o None si la entidad no tiene."""
    if entidad == "factura":
        fila = conn.execute("SELECT nivel FROM factura_estado WHERE factura_id = ?",
                            (entidad_id,)).fetchone()
    else:
        fila = conn.execute("SELECT nivel FROM prioridad WHERE entidad = ? AND entidad_id = ?",
                            (entidad, entidad_id)).fetchone()
    return fila[0] if fila else None


def subir_prioridad(conn: sqlite3.Connection, persona: Persona, *, entidad: str,
                    entidad_id: int,
                    nivel: str, hasta: date | str | None = None,
                    datos: dict[str, Any] | None = None) -> int:
    """Una persona con resolver_aviso sube la prioridad de algo. Devuelve el id de la subida.

    Solo se sube: el nivel pedido (atencion o urgente; bloqueada la pone
    siempre una regla) no puede estar por debajo del que ya se ve, y como el
    nivel final es el mayor de todo, ninguna subida baja nada. El motivo (el
    de la persona) es obligatorio, de al menos 10 caracteres, y la subida
    puede vencer.
    """
    motivo = (persona.motivo or "").strip()
    with orden_auditada(conn):
        exigir(conn, persona.usuario_id, Permiso.RESOLVER_AVISO.value,
               accion="subir una prioridad")
        if entidad not in _ENTIDADES_A_MANO:
            raise ValueError(f"se sube la prioridad de {', '.join(_ENTIDADES_A_MANO)}, "
                             f"no de {entidad}")
        # Sin esto, una subida de algo que no existe pasaba: no tiene nivel, asi que
        # tampoco hay nada por encima que la frene.
        comprobar_entidad(conn, entidad, entidad_id)
        texto = str(getattr(nivel, "value", nivel))
        if texto not in prioridad.NIVELES_A_MANO:
            raise NoSube("a mano se sube a atencion o a urgente; bloqueada la pone una regla")
        if len(motivo) < 10:
            raise FaltaMotivo("subir una prioridad pide un motivo de al menos 10 caracteres")
        actual = nivel_actual(conn, entidad, entidad_id)
        if actual is not None and prioridad.RANGO[texto] < prioridad.RANGO[actual]:
            raise NoSube(f"{entidad} {entidad_id} ya esta en {actual}: subirla a {texto} no "
                         "sube nada")
        reloj = reloj_de(conn)
        tope = None
        if hasta is not None:
            tope = hasta if isinstance(hasta, date) else date.fromisoformat(str(hasta))
            if tope < reloj.hoy():
                raise ValueError(f"una subida hasta el {tope.isoformat()} ya habria vencido")
        fila = {"entidad": entidad, "entidad_id": entidad_id, "nivel": texto, "motivo": motivo,
                "usuario_id": persona.usuario_id, "en": marca(reloj.ahora()),
                "hasta": tope.isoformat() if tope else None}
        evento = registrar(conn, tipo="prioridad_subida", actor=persona.usuario_id,
                           usuario_id=persona.usuario_id, tabla=entidad, fila_id=entidad_id,
                           factura_id=entidad_id if entidad == "factura" else None,
                           motivo=motivo, peticion_id=persona.peticion_id,
                           datos={**(datos or {}), "fila": fila})
        return int(conn.execute(
            "INSERT INTO prioridad_manual (entidad, entidad_id, nivel, motivo, usuario_id, en, "
            "hasta, evento_id) VALUES (:entidad, :entidad_id, :nivel, :motivo, :usuario_id, :en, "
            ":hasta, :evento_id)", {**fila, "evento_id": evento}).lastrowid)
