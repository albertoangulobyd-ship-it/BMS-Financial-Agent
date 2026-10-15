"""El lector de ficheros CSV, guiado por un mapeo versionado en YAML (spec §9).

Cada formato de CSV tiene su fichero config/importacion/<fuente>-<tipo>-vN.yaml
que dice:

- como leerlo: codificaciones que se prueban por orden (utf-8-sig, cp1252),
  delimitador, separador decimal y de miles, formatos de fecha y la fila de
  la cabecera;
- la huella de la cabecera (`cabecera`): las columnas que tiene que traer;
  `reconoce()` la busca para saber si un fichero es de ese formato;
- que registros canonicos salen de cada fila (`registros`: un mismo fichero
  de acreedores de Exact da proveedores y sus cuentas) y, para cada campo,
  de que columna sale, con que tipo, que mapa de valores y si es derivado
  (`unir` varias columnas, la `primera` que tenga algo);
- si es una foto completa del sistema de origen (`completo`).

Leer es puro: bytes y mapeo en, registros y rechazos fuera. Un mapeo nuevo
es un YAML, un fichero de ejemplo anonimizado y el JSON de lo que tiene que
salir (el test de contrato).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ..almacen.unidades import sha256_bytes, sha256_texto
from ..parsing import detectar_moneda
from ..reglas.normas import normalizar_iban
from .base import LoteLeido, Rechazo
from .canonico import MODELOS

# Los mapeos viven con la configuracion: config/importacion de la carpeta desde
# la que se trabaja o, si no hay, la del repositorio.
DIRECTORIO_MAPEOS = Path(__file__).resolve().parents[3] / "config" / "importacion"
TIPOS_CAMPO = ("texto", "entero", "decimal", "fecha", "bool", "iban")
_BOOL = {"ja": True, "j": True, "yes": True, "y": True, "si": True, "sí": True, "true": True,
         "1": True, "x": True, "nee": False, "n": False, "no": False, "false": False, "0": False}
# Un entero y, si acaso, una unidad sin cifras ni separadores detras.
_ENTERO = re.compile(r"(-?[0-9]+)(?:\s*[^\W\d][^\d]*)?")


class MapeoNoValido(ValueError):
    """Un fichero de mapeo que no tiene la forma que se espera."""


class FicheroIlegible(ValueError):
    """El fichero no se puede leer con ninguna de las codificaciones del mapeo."""


@dataclass(frozen=True)
class Campo:
    """De donde sale un campo canonico de una fila."""

    nombre: str
    columna: str | None = None
    unir: tuple[str, ...] = ()
    primera: tuple[str, ...] = ()
    separador: str = " "
    tipo: str = "texto"
    valores: dict[str, Any] | None = None
    por_defecto: Any = None
    obligatorio: bool = False
    crudo_de: str | None = None        # guarda el literal de otra columna (tarifa_crudo)


@dataclass(frozen=True)
class Registro:
    tipo: str
    campos: tuple[Campo, ...]
    fijos: dict[str, Any] = field(default_factory=dict)
    omitir_si_vacio: tuple[str, ...] = ()


@dataclass(frozen=True)
class Mapeo:
    id: str
    sha256: str
    version: int
    fuente: str
    tipo: str
    formato: str
    codificaciones: tuple[str, ...]
    delimitador: str
    separador_decimal: str
    separador_miles: str | None
    formatos_fecha: tuple[str, ...]
    fila_cabecera: int
    cabecera: tuple[str, ...]
    completo: bool
    registros: tuple[Registro, ...]
    tipo_mime: str = "text/csv"
    texto: str = field(default="", repr=False)     # el YAML tal cual, para politica_version

    def registro(self, tipo: str) -> Registro:
        for registro in self.registros:
            if registro.tipo == tipo:
                return registro
        raise KeyError(f"el mapeo {self.id} no da registros de tipo {tipo}")


def _campo(nombre: str, definicion: Any, donde: str) -> Campo:
    if not isinstance(definicion, dict):
        raise MapeoNoValido(f"{donde}.{nombre}: se espera un mapa")
    conocidas = {"columna", "unir", "primera", "separador", "tipo", "valores", "por_defecto",
                 "obligatorio", "crudo_de"}
    sobran = set(definicion) - conocidas
    if sobran:
        raise MapeoNoValido(f"{donde}.{nombre}: no se entiende {', '.join(sorted(sobran))}")
    tipo = definicion.get("tipo", "texto")
    if tipo not in TIPOS_CAMPO:
        raise MapeoNoValido(f"{donde}.{nombre}: el tipo {tipo!r} no es uno de "
                            f"{', '.join(TIPOS_CAMPO)}")
    origenes = sum(1 for k in ("columna", "unir", "primera") if definicion.get(k))
    if origenes != 1:
        raise MapeoNoValido(f"{donde}.{nombre}: dice de donde sale con columna, unir o primera "
                            "(uno solo)")
    valores = definicion.get("valores")
    return Campo(nombre=nombre, columna=definicion.get("columna"),
                 unir=tuple(definicion.get("unir") or ()),
                 primera=tuple(definicion.get("primera") or ()),
                 separador=str(definicion.get("separador", " ")), tipo=tipo,
                 valores={str(k): v for k, v in valores.items()} if valores else None,
                 por_defecto=definicion.get("por_defecto"),
                 obligatorio=bool(definicion.get("obligatorio", False)),
                 crudo_de=definicion.get("crudo_de"))


def mapeo_de_yaml(texto: str, identificador: str) -> Mapeo:
    """El mapeo de un fichero YAML. Lo que no tiene la forma esperada lanza MapeoNoValido."""
    datos = yaml.safe_load(texto) or {}
    if not isinstance(datos, dict):
        raise MapeoNoValido(f"{identificador}: un mapeo es un mapa")
    for clave in ("version", "fuente", "tipo", "formato", "lectura", "cabecera", "registros"):
        if clave not in datos:
            raise MapeoNoValido(f"{identificador}: falta {clave}")
    lectura = datos["lectura"] or {}
    registros = []
    for tipo, definicion in (datos["registros"] or {}).items():
        if tipo not in MODELOS:
            raise MapeoNoValido(f"{identificador}: no hay registros canonicos de tipo {tipo}")
        definicion = definicion or {}
        campos = tuple(_campo(nombre, d, f"{identificador}.{tipo}")
                       for nombre, d in (definicion.get("campos") or {}).items())
        modelo = MODELOS[tipo]
        fijos = dict(definicion.get("fijos") or {})
        desconocidos = ({c.nombre for c in campos} | set(fijos)) - set(modelo.model_fields)
        if desconocidos:
            raise MapeoNoValido(f"{identificador}.{tipo}: el registro canonico no tiene "
                                f"{', '.join(sorted(desconocidos))}")
        registros.append(Registro(tipo=tipo, campos=campos, fijos=fijos,
                                  omitir_si_vacio=tuple(definicion.get("omitir_si_vacio") or ())))
    if not registros:
        raise MapeoNoValido(f"{identificador}: no da ningun registro")
    return Mapeo(
        id=identificador, sha256=sha256_texto(texto), texto=texto,
        version=int(datos["version"]),
        fuente=str(datos["fuente"]), tipo=str(datos["tipo"]), formato=str(datos["formato"]),
        codificaciones=tuple(lectura.get("codificaciones") or ("utf-8-sig", "cp1252")),
        delimitador=str(lectura.get("delimitador", ";")),
        separador_decimal=str(lectura.get("separador_decimal", ",")),
        separador_miles=lectura.get("separador_miles"),
        formatos_fecha=tuple(lectura.get("formatos_fecha") or ("%d-%m-%Y", "%Y-%m-%d")),
        fila_cabecera=int(lectura.get("fila_cabecera", 1)),
        cabecera=tuple(str(c) for c in datos["cabecera"]), completo=bool(datos.get("completo")),
        registros=tuple(registros), tipo_mime=str(datos.get("tipo_mime", "text/csv")))


def cargar_mapeo(ruta: str | Path) -> Mapeo:
    ruta = Path(ruta)
    return mapeo_de_yaml(ruta.read_text(encoding="utf-8"), ruta.stem)


def directorio_mapeos() -> Path:
    local = Path("config") / "importacion"
    return local if local.is_dir() else DIRECTORIO_MAPEOS


def mapeos(directorio: str | Path | None = None) -> list[Mapeo]:
    """Los mapeos de config/importacion, por nombre."""
    carpeta = Path(directorio) if directorio is not None else directorio_mapeos()
    return [cargar_mapeo(r) for r in sorted(carpeta.glob("*.yaml"))]


# ------------------------------------------------------------ lectura

def decodificar(contenido: bytes, codificaciones: tuple[str, ...]) -> str:
    """El texto del fichero con la primera codificacion que lo lee entero."""
    for codificacion in codificaciones:
        try:
            return contenido.decode(codificacion)
        except UnicodeDecodeError:
            continue
    raise FicheroIlegible(f"no se puede leer con {', '.join(codificaciones)}")


def filas(texto: str, mapeo: Mapeo) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    """La cabecera y cada fila como {columna: texto}, con su numero de linea en el fichero."""
    lector = csv.reader(io.StringIO(texto, newline=""), delimiter=mapeo.delimitador)
    todas = list(lector)
    if len(todas) < mapeo.fila_cabecera:
        return [], []
    cabecera = [c.strip() for c in todas[mapeo.fila_cabecera - 1]]
    salida = []
    for numero, fila in enumerate(todas[mapeo.fila_cabecera:], start=mapeo.fila_cabecera + 1):
        if not any(c.strip() for c in fila):
            continue
        salida.append((numero, {cabecera[i]: fila[i].strip() if i < len(fila) else ""
                                for i in range(len(cabecera))}))
    return cabecera, salida


class ValorNoValido(ValueError):
    def __init__(self, motivo: str, codigo: str = "fila") -> None:
        super().__init__(motivo)
        self.codigo = codigo


def _forma_numero(mapeo: Mapeo) -> re.Pattern[str]:
    """La forma exacta de un numero con los separadores que declara el mapeo.

    Los miles van en grupos de tres cifras detras de uno a tres, y el decimal
    solo una vez y al final: con coma decimal y punto de miles, "42.50" no es
    4250 sino un fichero exportado con otra configuracion regional, y se
    rechaza en vez de leerse cien veces mayor.
    """
    decimal = re.escape(mapeo.separador_decimal)
    entero = r"[0-9]+"
    if mapeo.separador_miles:
        miles = re.escape(mapeo.separador_miles)
        entero = rf"(?:[0-9]{{1,3}}(?:{miles}[0-9]{{3}})+|[0-9]+)"
    return re.compile(rf"[+-]?{entero}(?:{decimal}[0-9]+)?")


def _decimal(texto: str, mapeo: Mapeo) -> Decimal:
    moneda = detectar_moneda(texto)
    if moneda is not None and moneda != "EUR":
        raise ValorNoValido(f"{texto!r} no está en euros ({moneda})", "X1")
    limpio = re.sub(r"(?i)eur|€|\s", "", texto)
    if not _forma_numero(mapeo).fullmatch(limpio):
        raise ValorNoValido(f"{texto!r} no es un importe con decimal "
                            f"{mapeo.separador_decimal!r} y miles "
                            f"{mapeo.separador_miles or 'sin separar'!r}")
    if mapeo.separador_miles:
        limpio = limpio.replace(mapeo.separador_miles, "")
    limpio = limpio.replace(mapeo.separador_decimal, ".")
    try:
        return Decimal(limpio)
    except InvalidOperation:
        raise ValorNoValido(f"{texto!r} no es un importe") from None


def _entero(texto: str, campo: Campo) -> int:
    """Un entero entero, con su unidad detras si la lleva ("30 dagen", "14 dagen netto").

    "2,5" o "1.000" no son un plazo de dias: se rechazan en vez de quedarse
    con la primera cifra (2 o 1).
    """
    numero = _ENTERO.fullmatch(texto.strip())
    if numero is None:
        raise ValorNoValido(f"{campo.nombre}: {texto!r} no es un numero entero")
    return int(numero.group(1))


def _fecha(texto: str, mapeo: Mapeo) -> date:
    for formato in mapeo.formatos_fecha:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValorNoValido(f"{texto!r} no es una fecha ({' o '.join(mapeo.formatos_fecha)})")


def _convertir(texto: str, campo: Campo, mapeo: Mapeo) -> Any:
    if campo.valores is not None:
        if texto in campo.valores:
            return campo.valores[texto]
        if texto.lower() in {k.lower(): v for k, v in campo.valores.items()}:
            return {k.lower(): v for k, v in campo.valores.items()}[texto.lower()]
        raise ValorNoValido(f"{campo.nombre}: {texto!r} no es uno de "
                            f"{', '.join(campo.valores)}")
    if campo.tipo == "texto":
        return texto
    if campo.tipo == "entero":
        return _entero(texto, campo)
    if campo.tipo == "decimal":
        return _decimal(texto, mapeo)
    if campo.tipo == "fecha":
        return _fecha(texto, mapeo)
    if campo.tipo == "bool":
        if texto.strip().lower() in _BOOL:
            return _BOOL[texto.strip().lower()]
        raise ValorNoValido(f"{campo.nombre}: {texto!r} no es si o no")
    if campo.tipo == "iban":
        return normalizar_iban(texto)
    raise AssertionError(campo.tipo)


def _texto_de(campo: Campo, fila: dict[str, str]) -> str:
    if campo.columna is not None:
        return fila.get(campo.columna, "")
    if campo.unir:
        return campo.separador.join(fila.get(c, "") for c in campo.unir if fila.get(c, ""))
    return next((fila.get(c, "") for c in campo.primera if fila.get(c, "")), "")


def valores_de_fila(registro: Registro, fila: dict[str, str], mapeo: Mapeo) -> dict[str, Any]:
    """Los campos canonicos de una fila. Lanza ValorNoValido si uno no se puede leer."""
    salida: dict[str, Any] = dict(registro.fijos)
    for campo in registro.campos:
        texto = _texto_de(campo, fila)
        if not texto:
            if campo.obligatorio:
                raise ValorNoValido(f"falta {campo.nombre}")
            if campo.por_defecto is not None:
                salida[campo.nombre] = campo.por_defecto
            continue
        salida[campo.nombre] = _convertir(texto, campo, mapeo)
        if campo.crudo_de is not None:
            salida[campo.crudo_de] = texto
    return salida


@dataclass(frozen=True)
class LectorTabular:
    """Un lector de CSV para un tipo de registro de un mapeo."""

    mapeo: Mapeo
    tipo: str

    @property
    def fuente(self) -> str:
        return self.mapeo.fuente

    @property
    def formato(self) -> str:
        return self.mapeo.formato

    def reconoce(self, contenido: bytes, nombre: str = "") -> bool:
        """Si el fichero trae todas las columnas de la huella de la cabecera."""
        try:
            texto = decodificar(contenido, self.mapeo.codificaciones)
        except FicheroIlegible:
            return False
        cabecera, _filas = filas(texto, self.mapeo)
        return set(self.mapeo.cabecera) <= set(cabecera)

    def leer(self, contenido: bytes, nombre: str = "", *,
             exportado_en: datetime | None = None) -> LoteLeido:
        texto = decodificar(contenido, self.mapeo.codificaciones)
        cabecera, todas = filas(texto, self.mapeo)
        faltan = [c for c in self.mapeo.cabecera if c not in cabecera]
        if faltan:
            raise FicheroIlegible(f"{nombre or 'el fichero'} no trae las columnas "
                                  f"{', '.join(faltan)} del mapeo {self.mapeo.id}")
        registro = self.mapeo.registro(self.tipo)
        modelo = MODELOS[self.tipo]
        registros, rechazos = [], []
        for numero, fila in todas:
            try:
                valores = valores_de_fila(registro, fila, self.mapeo)
            except ValorNoValido as exc:
                rechazos.append(Rechazo(numero, str(exc), fila, exc.codigo))
                continue
            if any(valores.get(c) in (None, "") for c in registro.omitir_si_vacio):
                continue
            try:
                registros.append(modelo.model_validate({**valores, "fila": numero,
                                                        "crudo": fila}))
            except ValidationError as exc:
                motivo = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                                   for e in exc.errors(include_url=False))
                rechazos.append(Rechazo(numero, motivo, fila))
        return LoteLeido(
            fuente=self.mapeo.fuente, tipo=self.tipo, formato=self.mapeo.formato,
            fichero_sha256=sha256_bytes(contenido), mapeo_id=self.mapeo.id,
            mapeo_sha256=self.mapeo.sha256, exportado_en=exportado_en, cubre_desde=None,
            cubre_hasta=None, completo=self.mapeo.completo, registros=tuple(registros),
            rechazos=tuple(rechazos))


def lectores(mapeo: Mapeo) -> list[LectorTabular]:
    """Un lector por cada tipo de registro del mapeo, en su orden (proveedores, luego cuentas)."""
    return [LectorTabular(mapeo, r.tipo) for r in mapeo.registros]


def elegir_mapeo(fuente: str, tipo: str, contenido: bytes, nombre: str = "", *,
                 directorio: str | Path | None = None) -> Mapeo:
    """El mapeo de esa fuente y tipo que reconoce el fichero: el de version mas alta."""
    candidatos = [m for m in mapeos(directorio) if m.fuente == fuente and m.tipo == tipo]
    if not candidatos:
        raise MapeoNoValido(f"no hay ningun mapeo de {fuente}/{tipo} en config/importacion")
    reconocen = [m for m in candidatos if LectorTabular(m, m.registros[0].tipo).reconoce(
        contenido, nombre)]
    if not reconocen:
        raise MapeoNoValido(f"ningun mapeo de {fuente}/{tipo} reconoce {nombre or 'el fichero'}: "
                            "sus columnas no son las de ninguno (" + ", ".join(
                                m.id for m in candidatos) + ")")
    return max(reconocen, key=lambda m: m.version)


def contrato(mapeo: Mapeo, contenido: bytes) -> dict[str, Any]:
    """Lo que da leer un fichero con un mapeo, en JSON: lo que fija su test de contrato.

    Los registros van con todos sus campos (tambien el crudo de la fila) y
    los rechazos con su fila, su codigo y su motivo: si un mapeo cambia lo
    que lee, el test lo dice campo a campo.
    """
    lotes = []
    for lector in lectores(mapeo):
        lote = lector.leer(contenido)
        lotes.append({
            "tipo": lote.tipo, "formato": lote.formato, "completo": lote.completo,
            "registros": [r.model_dump(mode="json") for r in lote.registros],
            "rechazos": [r.a_dict() for r in lote.rechazos],
        })
    return {"mapeo": mapeo.id, "fuente": mapeo.fuente, "tipo": mapeo.tipo, "lotes": lotes}
