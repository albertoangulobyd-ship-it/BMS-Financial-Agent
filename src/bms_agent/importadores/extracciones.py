"""Migracion de out/ al almacen, sin una sola llamada a la API.

Cada fichero de out/*.json es una extraccion ya pagada. `importar_out` la
guarda tal cual (el texto exacto del fichero), ata cada una a su documento
por el hash de los bytes, y si encuentra el PDF con ese hash en la carpeta
de facturas lo copia al almacen de documentos. Si no lo encuentra, el
documento queda apuntado sin original (ruta_cas NULL): la extraccion sigue
valiendo, y el original se puede anadir despues con otra pasada.

Volver a importar la misma carpeta no hace nada: cada fichero importado
queda en la tabla importacion por su hash, y cada extraccion es unica por
documento, modelo, versiones y contenido. Lo que esta mal (no es JSON, no
dice de que documento es) se rechaza y queda apuntado, tambien una sola vez.

La direccion la pone esta via de entrada, no el modelo: todo lo que leyo el
extractor v1 son facturas recibidas (ruta_declarada 'entrante').
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..almacen import Almacen, reloj_de, transaccion, usuario_sistema
from ..almacen.documentos import instante_de_fichero, registrar_documento
from ..almacen.extracciones import RegistroInvalido, leer_registro, registrar_extraccion
from ..almacen.unidades import json_canonico, sha256_bytes
from ..auditoria import registrar
from ..documents import PDF_MAGIC
from ..reloj import marca

FUENTE = "extracciones"
TIPO = "extraccion"
TIPO_MIME = "application/pdf"


@dataclass
class ResultadoImportacion:
    ficheros: int = 0
    importadas: int = 0
    ya_estaban: int = 0
    rechazadas: int = 0
    documentos_nuevos: int = 0
    originales_guardados: int = 0
    sin_original: int = 0
    rechazos: list[tuple[str, str]] = field(default_factory=list)


def indexar_pdfs(carpeta: str | Path | None) -> dict[str, Path]:
    """Cada PDF de la carpeta (y sus subcarpetas) por el hash de sus bytes.

    Lo que no empieza por %PDF- no es un original de factura y no se mira,
    igual que en la extraccion. Si el mismo PDF esta dos veces, vale el
    primero en orden de ruta.
    """
    if carpeta is None or not Path(carpeta).is_dir():
        return {}
    indice: dict[str, Path] = {}
    for ruta in sorted(Path(carpeta).rglob("*")):
        if not ruta.is_file() or ruta.suffix.lower() != ".pdf":
            continue
        contenido = ruta.read_bytes()
        if contenido.startswith(PDF_MAGIC):
            indice.setdefault(sha256_bytes(contenido), ruta)
    return indice


def _importacion_previa(almacen: Almacen, fichero_sha256: str):
    return almacen.conn.execute(
        "SELECT id, estado FROM importacion WHERE fuente = ? AND tipo = ? AND fichero_sha256 = ?",
        (FUENTE, TIPO, fichero_sha256),
    ).fetchone()


def _rechazar(
    almacen: Almacen, nombre: str, fichero_sha256: str, motivo: str,
    actor: int, usuario_id: int | None,
) -> None:
    conn = almacen.conn
    ahora = marca(reloj_de(conn).ahora())
    cursor = conn.execute(
        "INSERT INTO importacion (fuente, tipo, formato, fichero_sha256, estado, filas_leidas, "
        "filas_rechazadas, rechazos_json, iniciada_en, terminada_en, iniciada_por, actor) "
        "VALUES (?, ?, 'json:desconocido', ?, 'rechazada', 1, 1, ?, ?, ?, ?, ?)",
        (FUENTE, TIPO, fichero_sha256,
         json_canonico([{"fila": 1, "motivo": motivo, "crudo": None}]),
         ahora, ahora, usuario_id, actor),
    )
    registrar(
        conn, tipo="importacion", actor=actor, usuario_id=usuario_id, resultado="error",
        tabla="importacion", fila_id=int(cursor.lastrowid), motivo=motivo,
        datos={"fichero": nombre, "estado": "rechazada"},
    )


def _aceptar(
    almacen: Almacen, nombre: str, registro, documento_id: int,
    actor: int, usuario_id: int | None,
) -> int:
    """La importacion de un fichero bueno: abierta, con su extraccion, y cerrada."""
    conn = almacen.conn
    cursor = conn.execute(
        "INSERT INTO importacion (fuente, tipo, formato, documento_id, fichero_sha256, "
        "filas_leidas, iniciada_en, iniciada_por, actor) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)",
        (FUENTE, TIPO, f"json:extraccion-s{registro.schema_version}", documento_id,
         registro.contenido_sha256, marca(reloj_de(conn).ahora()), usuario_id, actor),
    )
    importacion_id = int(cursor.lastrowid)
    extraccion = registrar_extraccion(
        conn, registro, documento_id=documento_id, via="out_v1",
        actor=actor, usuario_id=usuario_id,
    )
    conn.execute(
        "UPDATE importacion SET estado = 'aceptada', filas_aceptadas = 1, terminada_en = ? "
        "WHERE id = ?",
        (marca(reloj_de(conn).ahora()), importacion_id),
    )
    registrar(
        conn, tipo="importacion", actor=actor, usuario_id=usuario_id,
        tabla="importacion", fila_id=importacion_id,
        datos={"fichero": nombre, "estado": "aceptada", "documento_id": documento_id,
               "extraccion_id": extraccion.id},
    )
    return extraccion.id


def importar_out(
    almacen: Almacen,
    out_dir: str | Path,
    carpeta_pdfs: str | Path | None = None,
    *,
    usuario_id: int | None = None,
) -> ResultadoImportacion:
    """Importa cada out/*.json al almacen. Toda la orden es una transaccion.

    `usuario_id` es la persona que la lanza, si la hay; la ejecuta el usuario
    de sistema importador.
    """
    out_dir = Path(out_dir)
    if not out_dir.is_dir():
        raise FileNotFoundError(f"no existe la carpeta {out_dir}")
    pdfs = indexar_pdfs(carpeta_pdfs)
    conn = almacen.conn
    resultado = ResultadoImportacion()
    original_de: dict[int, str] = {}

    with transaccion(conn):
        actor = usuario_sistema(conn, "importador")
        for ruta in sorted(out_dir.glob("*.json")):
            resultado.ficheros += 1
            crudo = ruta.read_bytes()
            fichero_sha256 = sha256_bytes(crudo)
            previa = _importacion_previa(almacen, fichero_sha256)
            try:
                registro = leer_registro(crudo.decode("utf-8"))
            except UnicodeDecodeError:
                registro, motivo = None, "no es texto UTF-8"
            except RegistroInvalido as exc:
                registro, motivo = None, str(exc)
            if registro is None:
                resultado.rechazadas += 1
                resultado.rechazos.append((ruta.name, motivo))
                if previa is None:
                    _rechazar(almacen, ruta.name, fichero_sha256, motivo, actor, usuario_id)
                continue

            pdf = pdfs.get(registro.source_sha256)
            contenido_pdf = pdf.read_bytes() if pdf is not None else None
            if contenido_pdf is not None and sha256_bytes(contenido_pdf) != registro.source_sha256:
                pdf, contenido_pdf = None, None        # cambio mientras se importaba
            documento = registrar_documento(
                almacen, sha256=registro.source_sha256, contenido=contenido_pdf,
                nombre_original=registro.source_name or (pdf.name if pdf else None),
                tipo_mime=TIPO_MIME, origen="out_v1", ruta_declarada="entrante",
                recibido_en=instante_de_fichero(pdf) if pdf is not None else None,
                recibido_fuente="mtime" if pdf is not None else "desconocido",
                actor=actor, usuario_id=usuario_id,
            )
            original_de[documento.id] = documento.original
            resultado.documentos_nuevos += documento.nuevo
            resultado.originales_guardados += documento.original in ("guardado", "anadido")

            ya_esta = previa is not None or conn.execute(
                "SELECT 1 FROM extraccion WHERE documento_id = ? AND modelo = ? "
                "AND prompt_version = ? AND schema_version = ? AND contenido_sha256 = ?",
                (documento.id, registro.modelo, registro.prompt_version,
                 registro.schema_version, registro.contenido_sha256),
            ).fetchone() is not None
            if ya_esta:
                resultado.ya_estaban += 1
                continue
            _aceptar(almacen, ruta.name, registro, documento.id, actor, usuario_id)
            resultado.importadas += 1

    resultado.sin_original = sum(1 for estado in original_de.values() if estado == "falta")
    return resultado
