# Paso 18 · desviaciones del diseño al construir

Lo que se hizo distinto de [diseno.md](diseno.md) al construirlo, o lo que el diseño no decía y
hubo que decidir, con su porqué. Una sección por paso de §9. El paso 17 lo recoge en la sección
del paso 18 del registro (§8.1, «Desviaciones, y por qué»).

## Paso 0 · el entorno

- **Un fallo de entorno más de los que dice §9.** Además de los dos que da el `anthropic` del
  entorno (más nuevo que el fijado: `test_entorno_local.py::test_las_dependencias_van_con_version_y_hash`
  y `test_extraccion_v2.py::test_la_via_sincrona_y_la_de_lotes_mandan_el_mismo_esquema`), falla
  `test_scoring.py::test_score_no_puntua_en_una_extraccion_v1_lo_que_v1_no_pidio` también con
  el SDK fijado (Python 3.13 y `anthropic` 1.13.0): lee `ground_truth/respuestas-ejemplo.yaml`,
  que no está en git (`.gitignore:7-8` solo deja `_ejemplo.yaml`). No es del código: la base
  de la suite lo cuenta como fallo conocido.
- `pwsh` es el 7.4.13 (el `.tar.gz` de la versión publicada, con su sha256 comprobado contra el
  `hashes.sha256` de esa versión), no el 7.4.21 del paso 14: §9 pide un 7.4.x y es lo que se
  pudo bajar. Los tests de PowerShell de `test_instalacion_nativa.py` pasan con él.

## Paso 1 · las guardas de red

- **`RED_SALIENTE` gana también `httpcore` y `urllib3`**, además de `httpx2` y `httpcore2`: son
  los clientes que van debajo de `httpx` y de `requests`, que ya estaban en la lista. Nada de
  `src/` los importa.
- **También se mira lo que se importa por nombre**: `__import__("x")`, `importlib.import_module("x")`
  e `import_module("x")` cuentan como `import x`, y con algo que no es un literal no pasan (no
  se puede saber qué traen). El diseño solo pedía los `from X import Y`; hoy ningún módulo
  importa por nombre, y sin esto la guarda se saltaba con una línea.
- La comprobación mira **cada prefijo con puntos** de lo importado (`urllib.request.urlopen` es
  de `urllib.request`), no solo el primero y el nombre entero; así `from urllib import request`
  y `from http import client` caen igual que `import urllib.request`.
- La parte de la fila de §7.2 que toca `src/` (`aislamiento.EXTERNOS` con los dos hosts de
  Microsoft, `salida.DESTINOS_CORREO`) no es de este paso, que no cambia `src/`: la
  aserción `{s.host for s in aislamiento.EXTERNOS} == {"1.1.1.1", "8.8.8.8", "api.anthropic.com"}`
  sigue como estaba y la cambia el paso que los añada (8 o 13), junto con la de
  `DESTINOS_CORREO`. `PERMITIDOS_POR_DEFECTO` no cambia.
