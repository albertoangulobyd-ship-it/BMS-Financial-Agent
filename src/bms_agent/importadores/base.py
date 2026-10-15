"""El marco de los importadores (spec §9): lectores puros y un lote leido.

Un lector convierte bytes en registros canonicos y no escribe nada: lo que
entra en el almacen lo decide registrar.py (`registrar_lote`, el unico que
escribe), con la misma auditoria y las mismas reglas para toda fuente. Asi
un formato nuevo (un CSV de otro sistema, una API mas adelante) es solo un
lector mas que da los mismos registros.

- `Lector`: fuente, tipo y formato; `reconoce()` mira si unos bytes son de
  su formato (la huella de la cabecera); `leer()` da un `LoteLeido`.
- `LoteLeido`: los registros canonicos (modelos de canonico.py), las filas
  rechazadas con su motivo y su contenido crudo, y lo que se sabe del
  fichero (su hash, de cuando es, si es una foto completa).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from pydantic import BaseModel

# Las importaciones que entran todo o nada (decision 6): un fichero a medias
# crearia estados falsos de "sin pagar" o "sin facturar", o una cuenta
# bancaria a medio registrar. El resto de los maestros entra fila a fila, y
# lo rechazado queda como Z2.
ATOMICOS = frozenset({"cuentas", "extracto", "planning", "facturas_venta", "facturas_compra",
                      "pagos_exact"})


@dataclass(frozen=True)
class Rechazo:
    """Una fila que no entra. `codigo`: fila (no se pudo leer), referencia (apunta a algo que no
    existe), X1 (un importe en otra moneda), duplicada, sistema (es de otro sistema)."""

    fila: int
    motivo: str
    crudo: dict[str, Any] | None = None
    codigo: str = "fila"

    def a_dict(self) -> dict[str, Any]:
        return {"fila": self.fila, "codigo": self.codigo, "motivo": self.motivo,
                "crudo": self.crudo}


@dataclass(frozen=True)
class LoteLeido:
    """Lo que un lector saca de un fichero, sin haber escrito nada.

    `completo`: es una foto entera (lo que falta en ella cuenta como
    retirado); `exportado_en`: cuando se saco del sistema de origen, que es
    lo que mide la frescura (Z1).
    """

    fuente: str
    tipo: str
    formato: str
    fichero_sha256: str
    mapeo_id: str | None
    mapeo_sha256: str | None
    exportado_en: datetime | None
    cubre_desde: date | None
    cubre_hasta: date | None
    completo: bool
    registros: tuple[BaseModel, ...]
    rechazos: tuple[Rechazo, ...]
    avisos: tuple[str, ...] = ()

    @property
    def filas_leidas(self) -> int:
        return len(self.registros) + len(self.rechazos)


class Lector(Protocol):
    """Puro: bytes en, registros canonicos fuera."""

    fuente: str
    tipo: str
    formato: str

    def reconoce(self, contenido: bytes, nombre: str) -> bool: ...

    def leer(self, contenido: bytes, nombre: str, *,
             exportado_en: datetime | None = None) -> LoteLeido: ...
