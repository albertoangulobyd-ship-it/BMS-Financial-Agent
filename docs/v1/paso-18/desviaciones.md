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
- **Tras la revisión de los pasos 0-2, la guarda mira también lo que se alcanza sin
  importarlo.** Se saltaba con `import http` y después `http.client.HTTPSConnection(...)`
  (`http.server`, que ya usa `serve.py`, carga `http.client`), con `import urllib.parse` y
  `urllib.request.urlopen(...)`, con `from importlib import import_module as im; im("socket")`
  y con `__import__("urllib", fromlist=["request"])`. Ahora:
  - cada cadena de atributos que sale de un nombre importado cuenta con cada prefijo de lo que
    es entera (`http.client.HTTPSConnection` tras `import http`) y con cada tramo de sus
    atributos (lo que otro módulo deja a mano: `salida.socket`, `server.http.client`,
    `cli.anthropic`); una cadena que sale de una variable no cuenta, para no confundir un
    `socket` local con el módulo;
  - `__import__` e `import_module` se reconocen con el nombre que lleven (`im` tras
    `from importlib import import_module as im`), su `fromlist` cuenta (`urllib.request`), y la
    función usada como valor (`f = importlib.import_module`) no pasa, como un nombre que no es
    un literal;
  - `sys.modules["x"]` y `sys.modules.get("x")` cuentan como `import x` (con algo que no es un
    literal, no pasan); `"site" in sys.modules` (`nativo.py`) no saca nada y pasa.
  Hoy ningún módulo de `src/` usa ninguna de estas formas. Sigue sin verse lo que no está en el
  código como nombre con puntos (`getattr(http, "client")`, `exec`, `eval`, o `sys.modules`
  guardado antes en otra variable): la guarda es una defensa más, y la barrera de verdad sigue
  siendo la lista blanca de la salida y el aislamiento de cada proceso.
- La parte de la fila de §7.2 que toca `src/` (`aislamiento.EXTERNOS` con los dos hosts de
  Microsoft, `salida.DESTINOS_CORREO`) no es de este paso, que no cambia `src/`: la
  aserción `{s.host for s in aislamiento.EXTERNOS} == {"1.1.1.1", "8.8.8.8", "api.anthropic.com"}`
  sigue como estaba y la cambia el paso que los añada (8 o 13), junto con la de
  `DESTINOS_CORREO`. `PERMITIDOS_POR_DEFECTO` no cambia.

## Paso 2 · la migración 0019

- **`CHECK ((aprobada_via IS 'automatica') = (autorizacion_id IS NOT NULL))`, con `IS` y no con
  `=`** como en §3.9: con `=`, una petición sin sí (`aprobada_via` NULL) da NULL y el CHECK
  pasa, así que podía llevar una `autorizacion_id` sin estar aceptada. Con `IS`, sin sí tampoco
  hay autorización (lo prueba `test_una_automatica_solo_la_acepta_su_autorizacion`).
- **Lo que de verdad hace falta en la reconstrucción es el orden, no el `PRAGMA`.** Se comprobó
  cambiando la migración: con `pasada_lectura_nueva` apuntando a `solicitud_lectura_nueva`, la
  migración pasa también sin `PRAGMA defer_foreign_keys = ON` (al borrar la petición vieja ya no
  le apunta nadie); apuntando al nombre final falla con `FOREIGN KEY constraint failed` aunque
  esté el `PRAGMA`. El `PRAGMA` se deja, como dice §3.9, porque no estorba.
- **Lo que §3.9 no fijaba y se decidió** (todo con CHECK o disparador, para que la base lo
  sostenga aunque falle el código):
  - `mensaje_correo`: los límites de §3.8 paso 4 (`graph_id` de 1 a 512 caracteres de
    `[A-Za-z0-9+/=_-]`, `internet_message_id_doc` ≤ 998, `remitente_doc` ≤ 320, `asunto_doc` ≤ 200),
    `adjuntos` y `en_linea` ≥ 0, `traido_en` y `registrado_en` obligatorios, y un índice por
    `recibido_en` (lo más reciente y lo que espera a una persona).
  - `adjunto_correo`: `sha256` en hexadecimal de 64 en minúsculas; `documento` exige `sha256`;
    el disparador `adjunto_correo_su_documento` exige que el documento sea el de ese sha256; un
    índice parcial por `documento_id` (las elegibles). Sin columna `detalle`: la API de §6.2 no
    lo enseña y se queda en el JSON de la bandeja.
  - `exclusion_automatica`: `persona` si y solo si no hay `solicitud_id`; el disparador
    `exclusion_automatica_quien`: la de `persona` la pone una persona y las demás un usuario de
    sistema. Sin columna de motivo en texto: va en el evento, como el de las acciones.
  - `pausa_lectura_automatica`: una `pausa` lleva `motivo` y una `reanuda` no; `persona` lleva
    `hasta` (posterior a `en`) y `volumen` no; `solicitud_id` solo en una de `persona`; el
    disparador `pausa_lectura_automatica_quien`: la de `volumen` la pone un usuario de sistema, y
    parar y reanudar, una persona.
  - `correo_atendido`: el disparador `correo_atendido_personas_alta` (solo una persona).
  - `ronda_correo`: `fallo` si y solo si hay `error_codigo`, de la lista cerrada de §3.7;
    `terminada_en` puede faltar (un `registrar --fallo` no es una ronda entera).
  - `estado_correo`: `error_codigo` con `error_desde` y `alcance_comprobado_en` con
    `alcance_bien`, juntos o ninguno; `hoy_json` JSON (por defecto `{}`); `aviso_volumen` 0/1.
  - `estado_ciclo`: `variante` puede ser NULL (la API de §6.2 lo admite y `--variante` es
    opcional); `pausado_desde` solo con `pausado = 1`.
- **Un disparador más sobre `solicitud_lectura`, `solicitud_lectura_automatica_vigente`**
  (revisión de los pasos 0-2; §3.9 decía «el resto de CHECK, índices y disparadores, iguales»).
  Los techos de `lectura_automatica` solo acotaban lo que se podía escribir en la autorización,
  no lo que una automática podía gastar: la base aceptaba una automática con una autorización
  ya superada por otra apagada y con un tope de 150 USD. Ahora, al aceptar una automática
  (`aprobada_via = 'automatica'` cuando aún no tenía sí), la base exige que `autorizacion_id`
  sea la vigente (la de mayor `id`), que esté encendida (`activa = 1`) y que `tope_usd_micro`
  no pase de su `tope_dia_usd_micro`. Las tres cosas salen del diseño (§5.1, §5.2: la vigente
  es la de mayor `id`; apagada, no se lee nada solo; el tope es el mínimo de lo estimado, lo que
  queda hoy y lo que queda este mes, y lo que queda hoy nunca pasa del tope del día), así que
  el `lectura autorizar` del paso 5 no tiene que hacer nada distinto: esto es para que un error
  suyo tampoco gaste. No mira lo gastado ya hoy ni este mes (el día es el de Europe/Amsterdam,
  que SQLite no sabe calcular, y lo gastado de verdad puede pasar un poco del tope), ni las
  pausas (una pausa por volumen que llega entre `tomar` y `autorizar` la tiene que ver
  `autorizar` y cerrar la petición limpia, no una excepción de la base). Solo mira el momento
  de aceptar: una lectura ya aceptada no la para la base si después apagan la autorización (el
  diseño no dice qué pasa entonces; hoy pararla es `cancelar_lectura`). La prueba
  `test_una_automatica_la_acepta_la_vigente_encendida_y_dentro_de_su_dia` falla si se quita
  cualquiera de las tres condiciones.
- **Las clases de las siete tablas nuevas, como en `docs/modelo-datos.md` y no como en §3.9**
  (revisión de los pasos 0-2). §3.9 las llamaba evidencia a todas (y a `lectura_automatica`,
  «evidencia, solo escritura»); el modelo de datos y la clase de spec.md §4 («lo que llegó de
  fuera») dicen otra cosa, y la cabecera de la 0019 y el modelo de datos no casaban. Quedan:
  `lectura_automatica`, `exclusion_automatica`, `pausa_lectura_automatica` y `correo_atendido`,
  **de solo escritura** (lo que deciden las personas, o el sistema en nombre de la autorización,
  como una anulación o una nota), con el mensaje «`<tabla>` es de solo escritura: no se
  modifica / no se borra» en sus disparadores; `mensaje_correo`, `adjunto_correo` y
  `ronda_correo`, **evidencia** (lo que llegó del buzón y lo que contó el componente de
  correo), con el mensaje «es evidencia» de §3.9. Lo que la base hace es lo mismo en las siete
  (`_sin_update` y `_sin_delete` abortan siempre); cambian la cabecera, los mensajes y en qué
  tupla de `test_almacen.py` está cada una. `test_cada_tabla_nueva_es_de_la_clase_que_dice_el_modelo_de_datos`
  comprueba que los disparadores y `docs/modelo-datos.md` dicen lo mismo.
- **Una persona que ya se llamara `correo` o `automatico`** (en minúsculas: antes del paso 18 el
  nombre no estaba reservado) hace parar la 0019 por el `UNIQUE` del nombre, y la base se queda
  en 0018 entera (lo prueba `test_una_0019_que_falla_deja_la_base_en_0018_entera`). No se
  renombra a nadie en una migración: si pasara, se ve al arrancar y lo arregla una persona.
- **`test_almacen.py`**: además de `EVIDENCIA`, `_poblar` y los seis usuarios de sistema,
  `test_una_persona_tiene_roles_que_solo_se_cierran` daba por hecho que la primera persona es la
  5; ahora es la siguiente a los usuarios de sistema (la 7 en una base nueva).
- **Hueco del diseño, para los pasos 4, 5 y 10**: `almacen/evidencia.py` (lo que comprueba
  `db verificar`: cada fila de evidencia con la foto de su evento, `COLUMNAS` y `EVENTOS`) no sale
  en el diseño. Su regla dice que una tabla nueva de evidencia se apunta allí con sus columnas y
  sus tipos de evento, y que su escritor pone `foto()` en el evento. La migración no escribe filas
  y no hay escritores todavía: quien escriba `lectura_automatica`, `exclusion_automatica` y
  `pausa_lectura_automatica` (pasos 4 y 5), y `mensaje_correo`, `adjunto_correo`,
  `ronda_correo` y `correo_atendido` (pasos 4 y 10), decide con eso delante (los mensajes y sus
  adjuntos irían en el evento de su mensaje, como los movimientos en el de su extracto).

## Paso 3 · la lectura que no se bloquea

- **`clasificar_error` solo da «documento» a un 400 o un 413** (y a lo que no es un error de la
  API: un rechazo del modelo, una respuesta cortada o que no valida). Lo que la tabla de §5.3
  no nombra (un 404 porque el modelo no existe, 408, 409, 422, 503…) es `api_no_disponible`, no
  «documento»: al contar, un «documento» queda omitido y el paso 5 lo excluye con
  `rechazado_api`, así que un 404 de configuración apartaría todas las facturas a «Wacht op
  jou». El freno de «dos iguales seguidos» sigue para los 400 al leer.
- **Al contar, una excepción que no es de la API** (un fallo del programa, sin código HTTP)
  sigue cerrando la petición con `contar`, como antes, en vez de dejar ese PDF omitido con
  `rechazado_api`: un fallo nuestro no se toma por un PDF malo.
- **El PDF de más de `MAX_BYTES_API` también lleva `rechazado_api`.** §5.7 solo se lo ponía al
  que la API rechaza al contar, pero §5.5 («tamaño, páginas, cifrado») dice que en la
  automática se excluye con ese motivo; sin él, el paso 5 lo dejaría elegible para siempre, el
  más antiguo de la cola, contado y omitido cada ronda. El tope se mira después de saber si ya
  está leído: un PDF grande ya leído sigue siendo «ya leído». Otra copia de un PDF rechazado
  (el mismo hash, con otro nombre) queda omitida igual, sin volver a mandarla.
- **La cuenta guardada (`estimacion_json`, y por tanto su huella) lleva `rechazado_api: true` y
  su `detalle` solo en los documentos rechazados.** La de una cuenta sin rechazados queda igual
  que antes (la misma huella para lo mismo). El paso 5 (`autorizar`) lee de ahí qué excluir.
  `leer` no elige los rechazados: ni se mandan ni salen en el progreso (antes, un omitido con
  hash se elegía y `cabe` lo dejaba «sin leer» con un motivo que no era el suyo).
- **Lo gastado por un fallo sin uso sigue siendo lo peor que podía costar** (§5.3: «como hoy»),
  también para un error HTTP de la API, que no se cobra. Con el `max_tokens` de la
  configuración, el primer fallo de una lectura corta se lleva casi todo su tope y el segundo
  documento ya no cabe (`tope`), así que el freno de «dos iguales seguidos» solo se ve con
  varias facturas por delante; las pruebas bajan `BMS_EXTRACT_MAX_TOKENS` para verlo. Contar a
  0 un error HTTP sería otra decisión, que no se tomó.
- **El primero de «dos iguales seguidos», que ya había quedado fallido, pasa a «sin leer» al
  llegar el segundo**: así ninguno de los dos cuenta como fallo del documento (§5.3) ni, en el
  paso 5, para la exclusión `fallo`. Un rechazo del modelo, una respuesta cortada o una lectura
  buena en medio cortan la cadena. El `ResultadoPasada.fallidas` de `extract` sigue contando el
  primero; la lectura pedida no lo usa (la pasada y la petición cuentan con el seguimiento).
- **`terminar` cierra la fallida con el evento `lectura_terminada`** (la fila 6 de la tabla de
  §5.3), con `fase` y `motivo_codigo` en sus datos; `lectura_fallida` sigue siendo el de
  `cerrar`. `lectura leer` sale entonces con `LECTURA_FALLIDA` (7) y no con 1; los dos
  `leer-facturas.ps1` tratan igual cualquier código que no es 0 ni 5, así que no cambian.
- **Los textos, los de §6.4 tal cual**, pero su segunda frase («daarna gaat het vanzelf
  verder», «después sigue solo», «se vuelve a probar solo más tarde») es la de la lectura
  automática: en una lectura de una persona sobre `buzon\facturas` no sigue sola. Hasta el paso
  5 solo hay lecturas de una persona. Para el paso 12 (Procesar sabe el origen de la petición):
  decidir si la frase cambia con el origen.
- **Un buzón con solo PDF rechazados termina `nada_que_leer`** con `buzon_vacio` (o
  `ya_leidas`), como hoy uno con un fichero que no es un PDF: la ventana del lector dice
  «omitido … la API no lo acepta: …», pero la app no enseña los omitidos (no están en
  `GET /api/v2/lectura`) hasta los pasos 11 y 12 («omitido con su motivo en Procesar», §13 S1).
- **`docs/integracion-web.md` no cambia aquí**: `motivo_codigo` de `GET /api/v2/lectura` ya
  puede valer `saldo`, `clave_rechazada` o `api_no_disponible` (la app los dice con su texto),
  y la lista de ese documento los añade el paso 11, con el contrato 2.6 (§9).
- Una guarda más, `test_cada_motivo_tiene_su_texto_en_la_app`: cada código de
  `lectura.MOTIVOS` tiene su línea en `reasonOf` (`process-texts.ts`); los pasos 4 y 5, que
  añaden motivos, la tienen que cumplir.
