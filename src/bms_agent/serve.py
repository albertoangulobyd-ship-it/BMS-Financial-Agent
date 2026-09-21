"""Servidor local de desarrollo: datos del panel y ejecucion bajo demanda.

Existe para que un sitio web propio pueda desarrollarse contra datos reales
sin esperar a que haya base de datos ni API desplegada.

DOS COSAS QUE NO SON NEGOCIABLES EN ESTE FICHERO:

1. Escucha SOLO en 127.0.0.1. No acepta 0.0.0.0 ni una IP de red. Un
   endpoint que lanza al agente cuesta dinero en cada llamada: expuesto a
   una red, cualquiera que encuentre la URL puede vaciar el saldo de la API
   pulsando un boton en bucle. Esto es un servidor de desarrollo, no el
   camino a produccion.

2. La ejecucion es un TRABAJO, no una llamada sincrona. Extraer cincuenta
   facturas tarda minutos: el navegador no espera, pregunta. Se lanza, se
   devuelve un identificador y se consulta el estado. Y solo una a la vez:
   dos clics seguidos serian dos extracciones concurrentes sobre la misma
   carpeta, o sea el doble de gasto por nada.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import config
from .cache import build_index
from .dashboard import construir_datos
from .documents import UnsupportedDocument, iter_pdfs, load_pdf
from .extract import extract_invoice
from .pricing import estimate_cost
from .report import load_records

ORIGENES_PERMITIDOS = ("http://localhost", "http://127.0.0.1")


@dataclass
class Ejecucion:
    """Estado de una pasada del agente. Lo consulta el navegador."""

    estado: str = "inactivo"  # inactivo | corriendo | terminado | error
    total: int = 0
    procesadas: int = 0
    reutilizadas: int = 0
    fallidas: int = 0
    tokens_entrada: int = 0
    tokens_salida: int = 0
    mensaje: str = ""
    iniciada: str | None = None
    terminada: str | None = None
    errores: list[str] = field(default_factory=list)

    def a_dict(self) -> dict[str, Any]:
        coste = estimate_cost(config.model_id(), self.tokens_entrada, self.tokens_salida)
        return {
            "estado": self.estado,
            "total": self.total,
            "procesadas": self.procesadas,
            "reutilizadas": self.reutilizadas,
            "fallidas": self.fallidas,
            "coste": float(coste) if coste is not None else None,
            "mensaje": self.mensaje,
            "iniciada": self.iniciada,
            "terminada": self.terminada,
            "errores": self.errores[-10:],
        }


class Agente:
    """Encapsula la ejecucion, con cerrojo para que no haya dos a la vez."""

    def __init__(self, carpeta_pdf: Path, carpeta_salida: Path) -> None:
        self.carpeta_pdf = carpeta_pdf
        self.carpeta_salida = carpeta_salida
        self._cerrojo = threading.Lock()
        self._estado = Ejecucion()

    @property
    def estado(self) -> dict[str, Any]:
        return self._estado.a_dict()

    def lanzar(self) -> tuple[bool, str]:
        """Arranca una pasada si no hay otra en curso."""
        if not self._cerrojo.acquire(blocking=False):
            return False, "Ya hay una ejecucion en curso."
        hilo = threading.Thread(target=self._correr, daemon=True)
        hilo.start()
        return True, "Ejecucion lanzada."

    def _correr(self) -> None:
        try:
            self._ejecutar()
        except Exception as exc:  # una pasada que falla no tumba el servidor
            self._estado.estado = "error"
            self._estado.mensaje = f"{type(exc).__name__}: {exc}"
            self._estado.terminada = _ahora()
        finally:
            self._cerrojo.release()

    def _ejecutar(self) -> None:
        import anthropic

        pdfs = list(iter_pdfs(self.carpeta_pdf))
        self._estado = Ejecucion(
            estado="corriendo", total=len(pdfs), iniciada=_ahora(),
            mensaje=f"Leyendo {len(pdfs)} documentos con {config.model_id()}",
        )
        if not pdfs:
            self._estado.estado = "terminado"
            self._estado.mensaje = f"No hay PDF en {self.carpeta_pdf}/"
            self._estado.terminada = _ahora()
            return

        cliente = anthropic.Anthropic()
        cache = build_index(self.carpeta_salida)
        modelo = config.model_id()

        for ruta in pdfs:
            try:
                doc = load_pdf(ruta)
            except UnsupportedDocument as exc:
                self._estado.fallidas += 1
                self._estado.errores.append(f"{ruta.name}: {exc}")
                continue

            guardada = cache.get(doc.sha256)
            if guardada is not None and guardada.matches(
                modelo, config.PROMPT_VERSION, config.SCHEMA_VERSION
            ):
                self._estado.reutilizadas += 1
                continue

            try:
                registro = extract_invoice(cliente, doc, model=modelo)
            except Exception as exc:
                self._estado.fallidas += 1
                self._estado.errores.append(f"{ruta.name}: {type(exc).__name__}: {exc}")
                continue

            registro.write_json(self.carpeta_salida)
            self._estado.procesadas += 1
            self._estado.tokens_entrada += registro.usage.get("input_tokens") or 0
            self._estado.tokens_salida += registro.usage.get("output_tokens") or 0
            self._estado.mensaje = f"{self._estado.procesadas + self._estado.reutilizadas} de {len(pdfs)}"

        self._estado.estado = "terminado"
        self._estado.terminada = _ahora()
        self._estado.mensaje = (
            f"{self._estado.procesadas} leidas, {self._estado.reutilizadas} reutilizadas, "
            f"{self._estado.fallidas} con problemas"
        )


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Manejador(BaseHTTPRequestHandler):
    agente: Agente
    carpeta_salida: Path

    def _cors(self) -> None:
        origen = self.headers.get("Origin", "")
        if origen.startswith(ORIGENES_PERMITIDOS):
            self.send_header("Access-Control-Allow-Origin", origen)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, codigo: int, cuerpo: dict[str, Any]) -> None:
        datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(datos)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/api/datos":
            registros = load_records(self.carpeta_salida)
            self._json(200, construir_datos(registros))
        elif self.path.rstrip("/") == "/api/ejecucion":
            self._json(200, self.agente.estado)
        else:
            self._json(404, {"error": "no existe"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/api/ejecutar":
            self._json(404, {"error": "no existe"})
            return
        lanzada, mensaje = self.agente.lanzar()
        self._json(202 if lanzada else 409, {"lanzada": lanzada, "mensaje": mensaje})

    def log_message(self, formato: str, *args: Any) -> None:
        print(f"  {self.address_string()} {formato % args}")


def servir(
    carpeta_pdf: str | Path = "facturas",
    carpeta_salida: str | Path = "out",
    puerto: int = 8765,
) -> None:
    """Arranca el servidor local. Solo 127.0.0.1, a proposito."""
    agente = Agente(Path(carpeta_pdf), Path(carpeta_salida))

    manejador = type("ManejadorConfigurado", (Manejador,), {
        "agente": agente, "carpeta_salida": Path(carpeta_salida),
    })

    servidor = ThreadingHTTPServer(("127.0.0.1", puerto), manejador)
    print(f"Servidor de desarrollo en http://127.0.0.1:{puerto}")
    print(f"  GET  /api/datos       datos del panel")
    print(f"  GET  /api/ejecucion   estado de la ultima pasada")
    print(f"  POST /api/ejecutar    lanza una pasada del agente")
    print(f"\nLee PDF de {carpeta_pdf}/ y guarda extracciones en {carpeta_salida}/")
    print("Solo escucha en 127.0.0.1. No es un servidor de produccion.\n")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nParado.")
        servidor.shutdown()
