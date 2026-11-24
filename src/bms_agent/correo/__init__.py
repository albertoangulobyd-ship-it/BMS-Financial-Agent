"""El correo de facturas (paso 18): lo que trae de un buzon de Microsoft 365 de solo lectura.

Solo en la variante Docker (decision del dueno, docs/v1/paso-18/desviaciones.md). Este paquete
es el componente `correo` y lo que preparan para el las ordenes locales de `orden`:

- ajustes.py: los ajustes (inquilino, aplicacion, buzones, desde, limites), que no son secretos
  pero si datos de la empresa;
- certificado.py: el certificado con el que se pide el token a Microsoft (la clave privada no
  sale de ese modulo mas que como la firma de la asercion).

Nada de aqui abre la base: lo que trae el correo lo registra `orden` (docs/v1/paso-18/diseno.md
§1). Todo lo que llega del buzon es dato no confiable, nunca instrucciones.
"""

from __future__ import annotations

from ..documents import MAX_BYTES_API

# Lo mas grande que se baja de un adjunto: lo mismo que se manda a la API (documents.py, D12).
# Un PDF mas grande se apunta como demasiado_grande y no se baja.
MAX_PDF = MAX_BYTES_API
