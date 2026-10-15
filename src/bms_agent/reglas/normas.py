"""Como se escriben igual dos cosas que son la misma: btw-id, KvK, nombres, IBAN y telefonos.

Funciones puras, sin la base ni nada de fuera, para que las usen igual las
reglas (que no pueden importar nada mas que reglas/ y dominio) e identidad.py
(que las reexporta): un documento y el maestro se comparan con la misma
normalizacion, y la coincidencia sigue siendo exacta despues de ella.
"""

from __future__ import annotations

import re
from typing import Any

_NO_ALFANUMERICO = re.compile(r"[^0-9A-Za-z]")
_SIN_PUNTUACION = re.compile(r"[^\w\s]")
_NO_DIGITO = re.compile(r"\D")
_CERO_ENTRE_PARENTESIS = re.compile(r"\(\s*0\s*\)")      # +31 (0)10 ...


def normalizar_btw(texto: Any) -> str | None:
    """'NL 0012.34567.B01' es 'NL001234567B01'."""
    limpio = _NO_ALFANUMERICO.sub("", str(texto or "")).upper()
    return limpio or None


def normalizar_kvk(texto: Any) -> str | None:
    """Solo los digitos: 'KvK 8765 4321' es '87654321'."""
    limpio = _NO_DIGITO.sub("", str(texto or ""))
    return limpio or None


def normalizar_nombre(texto: Any) -> str | None:
    """Sin mayusculas, sin puntuacion y con un espacio entre palabras.

    "Van Dijk B.V." y "van dijk bv" son el mismo nombre escrito de dos
    formas; "Van Dijk Bouw" es otro. Es la misma normalizacion que agrupa los
    pagos del panel (dashboard._nombre_normalizado).
    """
    sin_puntos = _SIN_PUNTUACION.sub("", str(texto or "").lower())
    limpio = " ".join(sin_puntos.split())
    return limpio or None


def normalizar_iban(texto: Any) -> str | None:
    """Sin espacios y en mayusculas: 'NL02 ABNA 0123 4567 89' es 'NL02ABNA0123456789'."""
    limpio = "".join(str(texto or "").split()).upper()
    return limpio or None


def parece_iban(texto: Any) -> bool:
    """La forma de un IBAN: dos letras, dos digitos y de 15 a 34 caracteres alfanumericos."""
    compacto = normalizar_iban(texto) or ""
    return (15 <= len(compacto) <= 34 and compacto[:2].isalpha() and compacto[2:4].isdigit()
            and compacto.isalnum())


def normalizar_telefono(texto: Any) -> str | None:
    """Los digitos de un numero neerlandes, con el prefijo de pais como un 0.

    '+31 6 1234 5678', '0031-6-12345678', '+31 (0)6 1234 5678' y '06 12345678'
    son el mismo numero: la verificacion compara el numero llamado con el del
    maestro, y no puede depender de como se escribio. El "(0)" es el cero del
    prefijo que no se marca desde fuera: se quita antes de contar las cifras.
    """
    texto = _CERO_ENTRE_PARENTESIS.sub("", str(texto or "")).strip()
    digitos = _NO_DIGITO.sub("", texto)
    if not digitos:
        return None
    if digitos.startswith("0031"):
        return "0" + digitos[4:]
    if texto.startswith("+31") or (digitos.startswith("31") and len(digitos) == 11):
        return "0" + digitos[2:]
    return digitos
