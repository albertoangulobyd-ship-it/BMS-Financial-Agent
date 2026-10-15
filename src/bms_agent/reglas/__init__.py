"""El motor de reglas: funciones puras sobre una instantanea congelada del almacen.

- `base`: que es una regla, la instantanea y sus resultados (ok, fallo,
  sin_datos, no_aplica).
- `catalogo`: cada regla con su metadato del §7 (severidad, si se anula, si
  es pegajosa, que aporta a la prioridad), en el orden de los resultados.
- `motor`: evalua el catalogo, ordena, agrupa los fallos en hallazgos y
  calcula su huella.
- `instantanea`: el unico que lee el almacen, para construir lo que el
  motor evalua.
- Una por familia de reglas: `calidad` (Q, X), `unicidad` (B), `aritmetica`
  (D), `iva` (D3, E), `bancaria` (F) y `planning` (G).

Escribir los hallazgos, su ciclo de vida y las anulaciones es de
hallazgos.py. Las reglas no deciden nada fuera de si mismas: no pagan, no
cambian un dato y no hablan con ningun sistema.
"""
