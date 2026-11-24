# Paso 18 · desviaciones del diseño al construir

Lo que se hizo distinto de [diseno.md](diseno.md) al construirlo, o lo que el diseño no decía y
hubo que decidir, con su porqué. Una sección por paso de §9. El paso 17 lo recoge en la sección
del paso 18 del registro (§8.1, «Desviaciones, y por qué»).

## Decisión del dueño: solo Docker

El 24-11-2026, con el diseño ya revisado y los pasos 0-5 hechos, el dueño decidió que **el correo
y la lectura automática desatendida se construyen solo para la variante Docker**. La nativa se
queda exactamente como está hoy: sin correo y sin lectura automática desatendida, funcionando y
con sus pruebas en verde. Es lo que ya recomendaba D13 (§1.7): en Docker un fallo en el proceso
que lee correo de desconocidos no alcanza la base ni la clave de la API; en la nativa sí
(§1.5, §1.6). Lo que cambia en cada paso:

- **Paso 6 (la dependencia)**: `cryptography`, `cffi` y `pycparser` solo en la imagen de Docker.
  No se tocan `scripts/fijar_windows.py` (ni su `elegir_rueda`, V11), `windows/requirements-windows.txt`,
  los paquetes de Windows ni los 17 y las `binarias` de `test_instalacion_nativa.py`. Cómo, en la
  sección del paso 6.
- **Paso 7 (certificado y ajustes)**: solo el camino de Docker (los ficheros de
  `docker\secretos\correo\`, §1.3 y §2.4). No se hacen `secretos.py` por tipos, el DPAPI del
  certificado, `nativo.certificado_del_correo` ni `Instalacion.fichero_certificado_correo`; las
  pruebas de §7.1 que los nombran («DPAPI falso», «solo el papel `correo` lo descifra») no van.
- **Paso 13 (nativa: el papel)**: no se hace. Ni el quinto papel `correo`, ni sus reglas del
  cortafuegos, ni `Arrancar-Salida-Correo`, `Preparar-Certificados-Correo`,
  `nativo.exigir_correo`, `aislamiento.motivo_para_no_traer`, `comprobar-aislamiento --rol correo`,
  `app_local.PAPELES` o `settings.roles` con el correo. `aislamiento.EXTERNOS` (la comprobación
  de aislamiento de la nativa) no gana los hosts de Microsoft: la aserción de
  `test_alcance_v1.py` sobre `EXTERNOS` sigue como está; `salida.DESTINOS_CORREO` es del paso 8.
- **Paso 14 (nativa: solo)**: no se hace. Ni `windows\ciclo.ps1` ni `windows\automatico.ps1`, ni la
  pausa y el cerrojo en los scripts de `windows\`, ni `correo-configurar`/`correo-certificado`
  nativos, ni los cambios de `iniciar.ps1 -EnSegundoPlano`. `serve --solo-errores` solo servía
  para el registro de la consola que arranca el vigilante de la nativa (O17; en Docker el registro
  de la consola ya rota, `docker-compose.yml:35-37`): tampoco se hace. Lo que los pasos 4 y 5 ya
  pusieron en `windows\comun.ps1` (los códigos 8 y 9 de la lectura, que `test_lectura_lector.py`
  compara) se queda: no cambia lo que hace la nativa.
- **Paso 15 (Docker)**: se hace entero. Lo que §4.4 pedía «en los dos `comun.ps1`» (la pausa, el
  cerrojo) va solo en `docker\comun.ps1`, y los `PASOS` de `ciclo.ps1` de `test_lectura_lector.py`
  (§7.2) son solo los de `docker\`. Los códigos de `correo` (`CORREO_SIN_CONFIGURAR`,
  `CORREO_FALLO`) se copian solo en `docker\comun.ps1`.
- **Paso 17 (documentos)**: el correo y la lectura automática se documentan solo para Docker:
  `docs/correo-m365.md` con los scripts de `docker\`; `entorno-local.md` con el correo, la
  salida del correo y la lectura automática; en `instalacion-nativa.md`, una línea que diga que la
  nativa no trae correo ni lectura automática desatendida y que para eso está Docker (en vez de
  la columna nativa de §1.5, la renovación nativa de §2.4 y la fila «El correo y la clave de la
  API» en su §11); D13 pasa de «recomendada» a «solo Docker». El registro (§8.1) apunta esta
  decisión entre sus desviaciones, y «lo que deben saber los pasos siguientes» deja el correo en
  la nativa (y con él el usuario de Windows aparte del papel `correo`, el paso 19 de §1.7) como
  trabajo futuro, si el dueño lo pide.
- **La app (pasos 11, 12 y 16)**: en la nativa no hay ciclo que lea solo ni correo que traer. Lo
  que la app enseñe del correo y de la autorización tiene que decirlo sin prometer lo que la
  nativa no hace (la variante llega con `ciclo latido --variante`, §3.9, que en la nativa nunca
  corre): lo decide el paso 12.

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
- **Un buzón con PDF nuevos de los que la API no acepta ninguno termina `fallida` con
  `contar`**, no `nada_que_leer` con `buzon_vacio` o `ya_leidas`, que no serían verdad (lo
  cambió el arreglo tras la revisión del paso 3). Es lo que pasaba antes de D12 con un solo PDF
  malo, pero el motivo dice cuáles (hasta tres) y por qué, y el evento `lectura_fallida` lleva
  `rechazados_api`. Un buzón con solo ficheros que no son PDF sigue en `buzon_vacio`, como
  hoy. La app no enseña los omitidos (no están en `GET /api/v2/lectura`) hasta los pasos 11 y
  12 («omitido con su motivo en Procesar», §13 S1). **Para el paso 5**: así `contar` no llega a
  `esperando_aprobacion` y `autorizar` no corre; una automática cuyas elegibles son todas
  rechazadas no las apartaría con `rechazado_api`, y la espera tras el fallo `contar` repetiría
  la misma cuenta. El paso 5 tiene que apartarlas también en ese caso.
- **Al contar, una contraprueba sin el PDF en vez del freno de «dos iguales seguidos»**
  (arreglo tras la revisión). Un 400 de la configuración (el modelo no admite el esfuerzo o el
  formato de salida, la API no acepta el esquema) llega igual con todos los PDF: sin nada más,
  todos quedaban omitidos con `rechazado_api`, la petición decía «no hay facturas nuevas» y el
  paso 5 las excluiría todas. El freno de §5.3 no sirve al contar: la API da el mismo mensaje a
  cualquier PDF cifrado o con demasiadas páginas, y dos seguidos (un proveedor que siempre manda
  el PDF con contraseña) pararían la cuenta entera en cada ronda sin apartar ninguno, que es S1
  otra vez. Así que, ante el primer 400 o 413 de una cuenta, `estimar` cuenta la misma petición
  sin el PDF (`count_tokens`, que no se cobra; el mismo modelo, prompt, esquema y esfuerzo), salvo
  que la API ya haya contado otro PDF de esa cuenta, que prueba lo mismo y más. Si la API la
  acepta, la culpa es del PDF, y de los 400 que vengan en esa cuenta, sin repetirla.
  Si no la acepta, es `ParadaApi` con el motivo de ese error (`api_no_disponible` si es otro
  400) y no se aparta nada. Un fallo nuestro en la contraprueba sigue cerrando con `contar`. Lo
  que no cubre: una configuración que solo falla con un documento dentro (un modelo que no lea
  PDF). Al leer, el freno de dos iguales sigue como en §5.3.
- **«Parar» gana a un fallo de la API** (arreglo tras la revisión). Si una persona pidió parar
  mientras la llamada en curso falla por algo que no es del documento, la pasada y la petición
  terminan `cancelada`, sin `motivo_codigo`, como con cualquier otro final de ese documento, y
  no `fallida` con `saldo`, `clave_rechazada` o `api_no_disponible`. El documento queda sin
  leer, no fallido; lo que dijo la API sale en la ventana del lector en su línea, y la lectura
  siguiente lo vuelve a ver si sigue. En el paso 5, esa petición no cuenta además como fallo
  técnico para la espera creciente, encima de la pausa `persona`.
- **`docs/integracion-web.md` no cambia aquí**: `motivo_codigo` de `GET /api/v2/lectura` ya
  puede valer `saldo`, `clave_rechazada` o `api_no_disponible` (la app los dice con su texto),
  y la lista de ese documento los añade el paso 11, con el contrato 2.6 (§9).
- Una guarda más, `test_cada_motivo_tiene_su_texto_en_la_app`: cada código de
  `lectura.MOTIVOS` tiene su línea en `reasonOf` (`process-texts.ts`); los pasos 4 y 5, que
  añaden motivos, la tienen que cumplir.

## Paso 4 · la autorización, las pausas y las exclusiones

- **Los eventos que el diseño no nombraba**: `lectura_automatica_pausada` y
  `lectura_automatica_reanudada` (una fila de `pausa_lectura_automatica` cada uno) y
  `correo_atendido`; los de §5.1 y §5.3 (`lectura_automatica_fijada`, `lectura_excluida`), con
  esos nombres. Ninguno casa con lo que `test_alcance_v1.py` prohíbe.
- **`almacen/evidencia.py` gana las cuatro tablas que escribe este paso** (el hueco que dejó
  apuntado el paso 2): `lectura_automatica`, `exclusion_automatica`, `pausa_lectura_automatica`
  y `correo_atendido`, cada fila con su evento de alta y la `foto()` en sus datos, así que
  `db verificar` ve una fila metida por detrás. Como una pausa y una reanudación son filas de la
  misma tabla con eventos distintos, `ALTAS_TAMBIEN` deja que una tabla tenga más de un evento
  de alta. Las tres del correo (`mensaje_correo`, `adjunto_correo`, `ronda_correo`) son del
  paso 10, que las escribe.
- **`excluir_de_lectura_automatica` deja un evento por documento** (la foto de cada fila), y
  solo el primero lleva el `peticion_id` de la orden: `evento.peticion_id` es `UNIQUE`
  (`0001_almacen.sql:170`). Un documento que una persona ya había apartado se deja como estaba
  (para siempre; uno que solo apartó la automática, no: ver «Una persona aparta del todo»,
  abajo); la respuesta dice `excluidos` y `ya_estaban`. Una
  lista con más de 200, vacía, con algo que no es un id o con un documento que no existe no
  aparta ninguno (`invalido` o `no_existe`). La lista se comprueba en
  `lectura_automatica.excluir`: el tipo `LISTA` de `servicios` admite cualquier lista.
- **`fijar_lectura_automatica` pide motivo** (`motivo="obligatorio"`): §5.1 dice «con
  `motivo`» y la columna lo admite vacío; encender o subir lo que el programa gasta solo es
  una decisión que conviene que diga por qué. Las otras tres lo admiten sin pedirlo («Weer
  aanzetten» es un botón). `nota` de `marcar_correo_atendido` es opcional (hasta 500).
- **La pausa vigente no es solo la última fila** (§3.9 punto 7 decía «el estado es la última
  fila»): cuenta todo lo que hay después de la última reanudación, y una de `volumen` gana a
  una de `persona`. Si no, una persona que para una automática con la pausa de volumen puesta
  (no debería pasar, pero nada lo impide en la base) dejaría la de volumen acabada a las 00:00,
  sin que nadie mirara la lista.
- **La pausa por volumen, una vez por día de Amsterdam**: si ese día ya se puso una (aunque una
  persona la haya quitado), `pausar("volumen")` no hace nada. Es lo que pide §5.2 («por primera
  vez ese día») y la prueba de §7.1; si no, `correo registrar` la volvería a poner cada 5
  minutos tras quitarla, porque `estado.json` sigue diciendo `aviso_volumen` todo el día.
- **`reanudar_lectura_automatica` sin ninguna pausa vigente es un 409** (`estado_no_valido`),
  no una fila más.
- **«Sin extracción vigente» con SQL** (`NOT EXISTS` de una extracción que no es una candidata
  sin activar, `extracciones.SIN_CANDIDATAS`), no con `ingesta.vigentes_por_documento`, que
  carga el JSON de cada extracción: `lectura siguiente` corre cada 5 minutos. Es la misma regla
  (un documento con alguna extracción que no es candidata tiene vigente);
  `test_una_extraccion_candidata_no_cuenta_como_leida` lo compara con la función de ingesta.
- **`marcar_correo_atendido` vive en `lectura_automatica.py`**, junto a `esperan_persona`: el
  diseño no la colocaba y el paquete `correo` (paso 7) es de lo que trae, que no abre la base.
  Un correo ya atendido es un 409.
- Lo que §6.1/§6.2 no fijaba y se decidió: la llegada de un documento es la primera vez que
  llegó por la bandeja (las elegibles van por ahí, las más antiguas primero);
  `pendientes_del_correo` (lo que una persona lee desde Procesar) quita lo que apartó una
  persona y lo que la API no acepta (arreglo tras la revisión, abajo), y las elegibles, todo lo
  apartado; en `esperan_persona`, los correos más recientes
  primero y las facturas apartadas por orden inverso de exclusión. En `resumen`,
  `queda_hoy_usd_micro` es lo que queda del día sin pasar de lo que queda del mes, y `parada`
  mira la pausa, la espera tras un fallo y los topes, en ese orden, solo con la automática
  encendida.
- **El tope del mes se mira antes que el del día** (`tope_alcanzado`, para `siguiente`,
  `autorizar` y la app): con el mes acabado, `limite_dia` diría «lo demás se lee mañana», que no
  es verdad.
- `frontend/src/lib/actions.ts` no gana las cuatro acciones todavía: la app no las manda hasta
  el paso 12 (§6.3), y la tabla solo lista lo que la app ofrece. Las etiquetas de
  `textos/*.json` son las de §6.4; las descripciones son nuevas.
- **Una persona aparta del todo lo que ya apartó la automática** (arreglo tras la revisión de
  los pasos 4 y 5). Con `documento_id UNIQUE` (§3.9, punto 6), `excluir_de_lectura_automatica`
  sobre una factura que la automática ya había apartado (`grande`, `fallo`, `rechazado_api`) no
  hacía nada (`ya_estaban`), y esa factura entraba para siempre en cada lectura de una persona:
  una grande que no se quiere pagar, en cada cuenta y en cada sí; una que falla, otra vez
  pagada en cada lectura (si la API cobra el fallo). En `buzon\facturas` se quita el fichero;
  lo del correo no tiene fichero que quitar. La 0019 (aún sin aplicar en ninguna base, como en
  la revisión de los pasos 0-2) cambia el `UNIQUE` por dos índices únicos parciales: **como
  mucho una exclusión del sistema y una de una persona por documento**, para siempre. Una
  persona puede poner la suya sobre la de la automática; la automática no aparta lo que ya está
  apartado. `esperan_persona` da una fila por factura, con su última exclusión (la de la
  persona, si la hay). `docs/modelo-datos.md` lo dice. **Para el paso 12**: la lista «Wacht op
  jou» puede ofrecer «Niet vanzelf lezen» en sus facturas (la acción ya las admite).
- **Lo que lee una persona desde Procesar** (arreglo tras la revisión). §5.1 dice de las
  exclusiones de una persona «leerlos a mano desde Procesar sigue siendo posible»; §5.7, que la
  lectura de una persona lleva lo del correo «que no esté excluido por una persona». Se sigue
  §5.7 (una inundación de basura apartada en bloque no puede entrar en cada lectura de una
  persona, ni pagarse con su sí), y además **lo que la API no acepta (`rechazado_api`) tampoco
  entra**: contarlo otra vez no lo cambia, y solo (sin nada en `buzon\facturas`) dejaba cada
  lectura de una persona, y cada una pedida en la app que lee el ciclo, en `fallida` con
  `contar`, sin salida. Lo grande y lo que falló leyéndose solo sí entran: leerlo es decisión
  de la persona, que si no lo quiere lo aparta del todo (el punto anterior). Es
  `lectura_automatica.FUERA_DE_PROCESAR`; `resumen().pendientes` cuenta lo mismo, y la
  descripción de `excluir_de_lectura_automatica` ya no promete que se lea desde Procesar.
  **Para el paso 12**: una factura apartada por una persona o por la API sigue en «Wacht op
  jou» (lo apartado «y aún sin leer», §6.1) mientras no tenga extracción, que ninguna lectura le
  va a dar; el paso 12 decide cómo sale de la lista (ya pasaba con las de una persona antes de
  este arreglo).

## Paso 5 · la lectura automática

- **`lectura siguiente` mira antes que nada lo que pidió una persona** (`LECTURA_PEDIDA`, 8),
  aunque la automática esté apagada o en pausa: la tabla de §5.2 empieza por la autorización,
  pero §4.1 (paso 5 del ciclo) y la decisión 8B hacen del ciclo el lector de las lecturas
  pedidas, y esas no dependen de la autorización. También es «pedida» la de una persona que
  esperaba el sí y cuyo lector ya no da señales: `tomar --solo-pedida` la vuelve a contar, como
  hacía el lector. Una lectura viva cuyo lector la dejó a medias (`abandonada`) no para el ciclo:
  sin esto, un corte de luz leyendo dejaba la automática parada hasta que alguien pidiera una
  lectura a mano; `tomar --automatica` la cierra (`abandonada`, que no es un fallo técnico).
  `lectura.siguiente` devuelve `leer`, `pedida`, `nada` o `limite`, y `cli.py` lo pasa a 0, 8, 3
  o 9.
- **«No toca la de la persona»** (§5.3, paso 2) se lee como «no se la apropia»: con una viva o
  pedida que su lector atiende, `tomar --automatica` da `LECTURA_OCUPADA`; una que su lector dejó
  a medias se cierra como lo hacen hoy `pedir_lectura` y el lector, salvo la de una persona que
  esperaba el sí, que se queda para el camino de la pedida. Sin nada pedido, `tomar --solo-pedida`
  no crea una del lector: sale con `LECTURA_NADA`. Con `--automatica`, la carpeta sobra (lo que se
  lee sale del almacén) y es opcional.
- **Lo que la API no acepta lo aparta `contar`, no `autorizar`** (§5.2 y §5.3, paso 5). Si la API
  no acepta ninguna de las nuevas, `contar` termina la petición antes de que `autorizar` corra
  (lo dejó apuntado el paso 3), así que tiene que apartarlas él; para que haya un solo sitio, lo
  hace siempre en una automática, con el usuario `automatico`, la petición y lo que dijo la API.
  Y una automática sin ninguna nueva que la API acepte termina en `nada_que_leer` con
  `excluidas`, no `fallida` con `contar`: no es un fallo técnico, y con `contar` la espera
  creciente repetiría la misma cuenta cada vez sin apartar nada. Las de una persona siguen como
  en el paso 3.
- **El tope de `autorizar` es el mínimo de lo que puede costar lo que se va a leer**, lo que
  queda hoy y lo que queda este mes: la suma del extremo alto de las facturas que se leen, no el
  extremo alto de toda la cuenta (§5.2), que incluye las que se apartan por `grande` y no se
  pagan. Es más estrecho y sigue cabiendo la primera. Si entre `contar` y `autorizar` alguien
  baja `max_documentos`, vale el de ahora. Una pausa que aparece entre `siguiente` y `autorizar`
  cierra la petición con `sin_autorizacion` (la lista de `motivo_codigo` de la 0019 no tiene uno
  para las pausas; el motivo en texto lo dice).
- **El máximo por factura y las facturas por ronda son topes duros también al leer**, no solo de
  la cuenta: en una automática, `_Seguimiento` no deja que una llamada pueda costar más que
  `max_por_documento_usd_micro` (su `max_tokens` sale de lo que queda del tope, sin pasar de
  eso) ni paga más de `max_documentos` facturas, y no paga lo apartado (también lo que una
  persona aparte después de contar). Con la cuenta sola, una respuesta más larga que su
  estimación podía costar más del máximo por factura. Lo que cuesta: un fallo sin uso cuenta su
  peor caso, que ahora es como mucho el máximo por factura (paso 3).
- **La segunda falla se cuenta por `documento_id`** en el resultado de las pasadas automáticas
  (`json_each`), no por el nombre: para lo del almacén es lo mismo (`<sha256>.pdf`), y no depende
  de cómo se llame el fichero.
- `lectura esperar` sobre una automática no espera nada: sale con `LECTURA_FALLIDA`. Una persona
  no puede darle el sí ni desde la app (`aprobar_lectura`, 409) ni desde la ventana.
- Los cuatro motivos nuevos (`limite_dia`, `limite_mes`, `excluidas`, `sin_autorizacion`) tienen
  su texto en `process-texts.ts` (la guarda del paso 3), los de §6.4. **Lo demás de la API y de la
  app queda para los pasos 11 y 12**: `autorizacion` y `automatica` en `GET /api/v2/lectura`,
  `nombre_original` en el resultado y `etiquetas` en cada pasada (§5.7) cambian el contrato
  (2.6) y no se añaden aquí; hasta entonces la pasada de una automática enseña los nombres del
  almacén (`<sha256>.pdf`). Ningún script llama todavía a `siguiente`, `tomar --automatica` ni
  `autorizar` (pasos 14 y 15), así que hasta entonces no hay automáticas de verdad.
- **Lo que lee una persona incluye lo del correo** (`_pdfs_a_leer`): `buzon\facturas` más lo que
  el correo dejó en el almacén sin leer, menos lo que una persona apartó y lo que la API no
  acepta (paso 4, arreglo tras la revisión). Con `leer-facturas.bat`
  sin cambios, lo del correo entra en su cuenta y en su lectura, con el sí de siempre. Una
  automática lee solo las elegibles (como mucho las de una ronda de la autorización encendida;
  sin ninguna encendida, nada).
- **Lo que ya está leído en `out/` y falta en la base se guarda antes de contar** (arreglo tras
  la revisión de los pasos 4 y 5; el diseño no lo veía). Las elegibles las decide la base (sin
  extracción vigente), pero la cuenta (`extract.Conocido`) mira también `out/`: una factura del
  correo leída y pagada antes, cuya extracción está en `out/` y no en la base (una base
  restaurada de una copia, que no lleva `out/`, `copia.py`; o un `_al_almacen` que falló, como
  la base ocupada de §5.5), salía «ya leída», la petición terminaba `nada_que_leer` con
  `ya_leidas` sin pasar por `leer` (el único que la guardaba), y seguía elegible: una lectura
  vacía en cada ciclo (288 al día en la auditoría, cada una con la salida y su comprobación) y,
  con ella entre las `max_documentos` más antiguas, lo que llegó después no se leía nunca.
  `lectura.guardar_lo_ya_leido`, que `lectura contar` llama antes de contar, pasa a la base lo
  que ya está en el almacén sin extracción vigente y tiene su lectura en `out/`, como
  `importar-out` y como lo guarda `leer`: la misma pasada (`ingesta.ingestar_pasada`, que lo
  tipa), sin cliente y con un seguimiento que no deja pagar nada. La cuenta lo ve entonces leído
  (vigente) y la ronda siguiente ya no lo elige. Vale para cualquier lectura, pero solo para lo
  que ya está en el almacén: un PDF nuevo de `buzon\facturas` sigue como antes. **En una
  automática, uno que no se puede guardar se aparta a la primera** (`fallo`, con lo que dijo
  la base y «ya estaba leída en out/»): guardar no depende de la API, la vez siguiente fallaría
  igual y, sin apartarlo, el ciclo volvería a por él; espera a una persona (`importar-out` lo
  dice si se puede recuperar). En la de una persona no se aparta nada: la CLI lo dice («sin
  guardar») y la cuenta lo ve como antes. Lo guardado no cambia el motivo de la petición
  (`ya_leidas`, con `pdf_ya_leidos`); lo dicen los eventos `extraccion_registrada` y la salida
  de `lectura contar` («guardada»).
- **`lectura siguiente` sigue el orden de la tabla de §5.2** después de lo pedido por una
  persona (arreglo tras la revisión; el primer punto de esta sección lo decía solo a medias):
  autorización encendida, pausa, otra viva con su lector, espera tras un fallo, elegibles,
  topes. Antes miraba la viva antes que la autorización y la pausa, y con una viva y una pausa
  a la vez salía con 3 en vez de 9.
- Los topes duros de la pasada (las facturas por ronda y lo apartado después de contar, en
  `_Seguimiento.cabe`; `max_documentos` y la pausa en `autorizar`) tienen ahora cada uno una
  prueba que falla sin él (arreglo tras la revisión: las de antes pasaban sin ellos, porque
  `_pdfs_a_leer` ya recortaba la lista).

## Paso 6 · la dependencia

- **Solo Docker, y en su propio fichero: `docker/requirements-correo.txt`**, no en
  `docker/requirements.txt` (la decisión del dueño, arriba). `scripts/fijar_windows.py --comprobar`
  exige que `windows/requirements-windows.txt` tenga exactamente lo de `docker/requirements.txt`
  (más `tzdata`), y lo prueban `test_las_dependencias_de_windows_son_las_de_docker_con_su_hash` y
  `test_fijar_comprobar_sale_con_0_con_lo_que_hay_en_el_repositorio`: con `cryptography` en
  `requirements.txt`, la puerta de la nativa fallaría sin tocar `fijar_windows.py` ni llevarla a
  Windows, que es lo que no se hace. El `Dockerfile` copia los dos ficheros y los instala en la
  misma orden (`pip install --only-binary=:all: --require-hashes -r requirements.txt -r
  requirements-correo.txt`), `.dockerignore` deja entrar el nuevo, y
  `docs/entorno-local.md` §13 lo dice. No cambian `fijar_windows.py` (ni su `elegir_rueda`, V11),
  `requirements-windows.txt`, los paquetes de Windows ni `test_instalacion_nativa.py` (los 17,
  `binarias`).
- **Las versiones**: `cryptography` 50.0.2 (la rueda `cp311-abi3`), `cffi` 2.1.1 (`cp311`) y
  `pycparser` 3.12 (`py3-none-any`), las últimas publicadas, todas de hace más de un mes; las
  ruedas `manylinux_2_17` (manylinux2014) de x86_64 y aarch64, bajadas como dice
  `entorno-local.md` §13 (`pip download --no-deps --only-binary=:all: --python-version 3.11
  --platform manylinux_2_17_…`), con su sha256 comprobado contra el que publica PyPI. La imagen
  (Debian trixie) admite las 2_17; con `--require-hashes`, pip solo elige entre las ruedas cuyo
  hash está fijado.
- **En `pyproject.toml`, un extra `correo = ["cryptography>=50"]`**, no una dependencia del
  paquete: la nativa no la lleva y nada fuera de `bms_agent.correo.certificado` la usa. `dev`
  incluye `bms-agent[correo]`, porque las pruebas del certificado la necesitan. La imagen de
  Docker no instala el paquete con pip (corre de `PYTHONPATH=/app/src`): el extra es lo que
  declara, y `requirements-correo.txt`, lo que se instala.
- **Una prueba nueva**, `test_las_dependencias_del_correo_son_solo_de_docker`
  (`test_entorno_local.py`): las tres, con hash, una rueda por plataforma en las binarias,
  ninguna en `requirements.txt` ni en `requirements-windows.txt`, el extra en `pyproject.toml` y
  las versiones instaladas iguales a las fijadas. Va aparte de
  `test_las_dependencias_van_con_version_y_hash` para que no la tape el fallo de entorno de esa
  prueba en Python 3.11 (el `anthropic` 2.8.0 de aquí, paso 0).
- Los entornos de prueba (el `.venv` 3.11 y el 3.13 del paso 0) llevan las versiones fijadas. Lo
  que la columna «Solo en Windows» de §9 pedía para este paso (que `instalar.bat` desempaquete
  las ruedas nuevas) no aplica; en su lugar, que `docker compose build` instala las tres en la
  imagen se comprueba donde hay demonio de Docker (aquí no lo hay).

## Paso 7 · el certificado y los ajustes

- **Solo el camino de Docker** (la decisión del dueño): `correo/__init__.py` (`MAX_PDF =
  documents.MAX_BYTES_API`), `correo/ajustes.py`, `correo/certificado.py` y la CLI `correo
  certificado crear [--siguiente] | activar | volver | ver | borrar [--anterior | --siguiente]` y
  `correo ajustes fijar | ver`, todas con `--carpeta` obligatoria (la de `docker\secretos\correo`,
  montada en `orden` solo para esa orden, §2.4): sin la nativa no hay sitio por defecto. No se
  hacen `secretos.py` por tipos, el DPAPI del certificado, `nativo.certificado_del_correo` ni
  `Instalacion.fichero_certificado_correo`; `secretos.py` sigue siendo el único con `ctypes`, sin
  cambios. En la instalación nativa, `correo …` dice que es solo de Docker y sale con 2.
- **El `.pem` lleva la clave privada (PKCS#8, sin cifrar, como la clave de la API en
  `docker\secretos`) y, detrás, su certificado**; §2.4 solo decía «clave privada». El contenedor
  `correo` solo ve dos secretos (`correo_certificado` y `correo_ajustes`) y necesita el
  certificado para `x5t#S256` y para saber si ha caducado; tomar la huella de los ajustes podría
  no casar con la clave. Al cargarlo se exige justo eso: un bloque `PRIVATE KEY` y uno
  `CERTIFICATE`, nada más, como mucho 8 KiB, RSA de 3072 bits o más, y que el certificado sea el
  de esa clave. El `.cer` (PEM) se rehace del `.pem` en cada orden que cambia la carpeta; que
  Entra acepta el `.cer` en PEM (Learn: `.cer`, `.pem` o `.crt`) es **[comprobar en vivo]**.
- **El certificado**: autofirmado, `CN=BMS lector de facturas` (nada de la empresa), firmado con
  SHA-256, `BasicConstraints` sin CA y `KeyUsage` de firma (las dos críticas); vale desde 5
  minutos antes de crearlo (un reloj de Microsoft algo atrasado) hasta el mismo día 24 meses
  después (un 29 de febrero, al 28). `asercion` falla en local con `CertificadoCaducado` si ya
  caducó (o aún no vale: la hora del equipo) y exige que el inquilino y la aplicación sean GUID,
  porque el inquilino va en la URL del token. `ver` enseña también la huella SHA-1, la que enseña
  el portal de Entra, para compararla (es pública).
- **Lo que §2.4 no decía de la renovación y se decidió**, para no perder nunca el certificado
  que vale:
  - `volver` deja el actual (el que no valió) como `siguiente`, para activarlo otra vez cuando
    esté bien subido; también termina una activación o una vuelta cortadas a medias (sin actual,
    con anterior). Se guarda también `-anterior.cer`.
  - `activar` no se hace con un anterior aún sin comprobar (la activación anterior no se cerró);
    `crear --siguiente` no se hace si ya hay uno siguiente; `crear` tampoco si el actual existe
    pero no se puede leer, ni con un siguiente o un anterior sin actual.
  - `borrar --siguiente` (nuevo) quita una renovación que no se va a subir; `borrar` sin opciones
    quita las tres claves (cortar el acceso desde el equipo, §2.5), no solo la actual.
- **Lo del certificado en los ajustes** (`certificado`, `siguiente`, `anterior`) sale siempre de
  la carpeta: lo ponen al día las órdenes de `correo certificado` y `correo ajustes fijar`. El
  primer `crear` (fase 1, sin los ids) no crea ajustes; unos ajustes que no valen no paran una
  orden del certificado (lo dice como aviso).
- **Los ajustes, lo que §2.4 no fijaba**: el inquilino y la aplicación, GUID (en minúsculas); los
  buzones, solo letras, cifras y `. _ + -` antes de la `@` y un dominio con punto (van en la URL
  de Graph: nada de `/ ? # %` ni espacios), en minúsculas, como mucho 320, distintos y del mismo
  dominio; los topes, de 1 a 1 000 PDF y de 1 a 4 096 MiB al día; el fichero, como mucho 16 KiB,
  sin claves que sobren, repetidas ni `NaN`. Los errores dicen el campo, nunca lo que pone.
  `ajustes fijar` cambia solo lo que se le da (como el `--buzon-control` de §2.3); la primera vez
  pide los cuatro datos, y unos ajustes guardados que no valen solo se sustituyen enteros.
- **Códigos**: `CORREO_SIN_CONFIGURAR = 10` (`ver` sin certificado o sin ajustes); 1 si la orden
  no se hace, 2 si algo no vale. `CORREO_FALLO = 11` y la copia de los dos en
  `docker\comun.ps1` son de los pasos 9, 10 y 15, que los usan.
- **Las pruebas** (`tests/test_correo_certificado.py`): las de §7.1 sin las de DPAPI y el papel
  `correo`; la firma en un intérprete aparte con `nativo.prohibir_procesos` y `-W error` (§7.2,
  sin `GraphFalso`, que es del paso 8); errores, `repr`, trazas (sin `__cause__` ni
  `__context__`), la salida de la CLI y `caplog` sin nada de la clave (ni su base64 ni sus
  números); una guarda de que solo `correo/certificado.py` importa `cryptography` y nombra
  `_clave`; y la parte de «el correo no ve la base» (§7.2) de estos módulos, mirando lo que
  cargan de verdad. **Para los pasos 8 y 9**: `cryptography.x509` importa `email.utils`, que
  importa `socket` (sin abrir nada); la guarda transitiva que se haga allí no puede exigir que
  `socket` no se cargue.
- **Las comprobaciones que se daban por probadas tienen ahora cada una una prueba que falla sin
  ella** (arreglo tras la revisión de los pasos 6 y 7; el código no cambia). Pasaban también
  sin su código: el mínimo de 3072 bits (la clave de 2048 llevaba el certificado de otra y se
  rechazaba por el par; ahora lleva el suyo, y cada `.pem` que no vale comprueba el motivo que
  da), los GUID en minúsculas (el inquilino de las pruebas no tenía letras; ahora las tiene, y
  el inquilino y la aplicación se pasan en mayúsculas a la aserción, a `ajustes fijar` y en el
  fichero), el tope de 1 000 PDF al día (y que los dos máximos se admiten), las claves
  repetidas, `NaN` e `Infinity` y los 16 KiB (cada uno sobre unos ajustes que, sin eso,
  valdrían), un dominio de nivel superior con cifras (las direcciones que no valen tienen que
  dar el error de su campo, `buzon:`, y no el de `buzon_control` por ser de otro dominio), y que
  se quita el `.cer` que deja sin su `.pem` un `crear --siguiente` cortado.

## Paso 8 · el cliente de Graph

- **`aislamiento.EXTERNOS` no cambia** (§7.2 decía que gana los dos hosts de Microsoft): es la
  comprobación de aislamiento de la nativa (`comprobar-aislamiento`), que no trae el correo
  (decisión del dueño); el camino de Docker no la usa. `salida.DESTINOS_CORREO`
  (`login.microsoftonline.com:443`, `graph.microsoft.com:443`) sí, para `salida_correo` (paso
  15), y `test_alcance_v1.py` lo fija junto a `EXTERNOS`, que sigue como estaba. La excepción
  con nombre de `httpx2` (`PUEDEN_SALIR`, solo `bms_agent.correo.graph`) ya la puso el paso 1.
- **Un módulo que el diseño no nombraba, `correo/bandeja.py`**: los nombres y los formatos de
  la bandeja en un solo sitio (la clave `sha256(graph_id|carpeta)`, los nombres de los
  ficheros, las listas cerradas de resultados y de códigos, los límites de §3.8, el saneado de
  los textos de terceros y la escritura de una vez). Lo usan `graph` y `traer`, y lo usará
  `registrar` (paso 10), que no puede importar `graph` ni `certificado` (§7.2).
- **Los códigos que §2.3 y §3.1 no fijaban**:
  - Graph: 401 → `credencial`; 403 y 404 → `permiso` (también un 404 del propio buzón: §2.3
    solo decía 403); un 5xx que no es de los que limitan (429, 503, 504) → `limitado`; una
    redirección → `interno` (no se sigue ninguna); otro 4xx → `interno`. Un 403 para la ronda
    también cuando es de un mensaje (arreglo tras la revisión, abajo); un 404, no.
  - La red: la salida que no deja pasar (un 403 o 407 del proxy) → `salida`; sin conexión o sin
    respuesta → `sin_conexion`, sin reintentar (lo repite el ciclo siguiente). Los únicos
    reintentos son los de Microsoft que limita.
  - El token: cualquier 400 o 401 con un AADSTS que no es el 700024 → `credencial` (también un
    inquilino que no existe o una aplicación desactivada); un certificado caducado, o que aún
    no vale por la hora del equipo → `credencial` sin pedir nada.
  - `comprobar`: cada código HTTP es un veredicto (los de la tabla de §2.3, e `interno` para
    "otro" también en las pruebas 3 y 5); un token que no se puede leer → `interno`; uno de
    otro inquilino, de otra aplicación o para otra audiencia → `alcance`. Lo que no es un
    veredicto (sin red, Microsoft que limita, la salida) es un error y no cambia el alcance
    guardado.
- **`Retry-After`, acotado**: como mucho dos reintentos por petición, también con la cabecera
  (Learn dice que se repita "hasta que funcione"); una cabecera que no es un número de
  segundos (solo cifras ASCII: arreglo tras la revisión, abajo) cuenta como si no estuviera.
  Las esperas son de cada petición: sin cabecera, la primera es de 2 s y la segunda de 8 s.
- **Un token por cliente (por ronda), que se renueva si le quedan menos de 5 minutos** (una
  ronda larga). El token y la aserción solo en memoria; el token, en un objeto sin `repr` que
  lo enseñe y que no se copia (como la credencial del paso 7). Los errores no se encadenan con
  los de `httpx2`, que llevan la petición entera (con la cabecera `Authorization` o la
  aserción): se lanzan fuera del `except`.
- **Las respuestas sin comprimir** (`Accept-Encoding: identity`), y los topes sobre lo que se
  lee; una respuesta con un `Content-Length` mayor que su tope ni se lee. Sin redirecciones ni
  HTTP/2. `Accept: */*` solo para el `$value` de un adjunto.
- **Los registros de `httpx2` y `httpcore2`, a WARNING en el proceso que importa `graph`**:
  apuntan en INFO cada URL con su consulta (el `$deltatoken`) y en DEBUG las cabeceras de la
  respuesta. `test_correo_graph.py` lo comprueba con `caplog` en DEBUG.
- **Un id de Graph que va en una ruta tiene que ser de `[A-Za-z0-9+/=_-]`** (como el `graph_id`
  de la 0019); `+` y `/` van codificados. **El `Location` de un 410 no se sigue**: la delta
  empieza otra vez con el filtro de fecha (§3.1). La lista de adjuntos sí sigue su
  `@odata.nextLink`, si lo trae (arreglo tras la revisión, abajo).
- **Las pruebas**: la de §7.2 en un intérprete aparte con `nativo.prohibir_procesos`, que firma
  y habla con `GraphFalso`, va en `test_correo_graph.py` y no en `test_instalacion_nativa.py`
  (de la nativa, que no se toca). La de la salida de verdad (`salida.Proxy` con
  `DESTINOS_CORREO` y la credencial de una pasada): el token lo da `GraphFalso` y lo demás va
  por la salida, que deja pasar el CONNECT a los dos hosts y el TLS falla contra el eco local
  (aquí no se puede terminar un TLS de Microsoft); el 403 a `api.anthropic.com:443` (y a
  `graph.microsoft.com:80`) se prueba con `aislamiento.pedir_tunel`, porque el cliente no sabe
  ir allí, y el 407 sin credencial (o con otra), con el cliente (`salida`). `GraphFalso` apunta
  lo que Microsoft no debería ver (un método que no es GET salvo el POST del token, `$expand`,
  el cuerpo en `$select`, una petición sin `IdType="ImmutableId"`, el `$value` de un adjunto
  que no es de fichero, otro host u otro buzón) en `violaciones` en vez de lanzar (el límite
  de errores de cada mensaje se lo tragaría), y cada test falla al final si hay alguna.
- **Un 403 es del buzón, no del mensaje** (arreglo tras la revisión de los pasos 8 y 9).
  `ErrorGraph.para_la_ronda` deja fuera `permiso` con un 404, pero no con un 403: un 403 al
  listar los adjuntos de un mensaje o al bajar uno es `permiso` de la ronda (§3.7: "403 en el
  propio buzón"), no un fallo de ese mensaje. Pasa con el rol `Application Mail.ReadBasic`
  (§2.1, paso 6: deja pasar la delta y la prueba 3 de `correo comprobar`, y no los adjuntos,
  investigacion.md:271-273) o en la media hora a dos horas que tarda Exchange en dar el permiso.
  Antes contaba contra el mensaje: a la cuarta ronda cada factura quedaba como una llegada de
  error sin adjuntos, con la ronda `bien`, sin volver a comprobar, y el paso 10 la registraría
  como evidencia (UNIQUE(graph_id, carpeta)), así que una vuelta buena después se descartaría
  como repetida. Ahora la ronda para con `permiso`, el mensaje no gasta su intento (el PDF que
  no se pudo bajar queda en pendientes, como sin red) y la siguiente vuelve a comprobar. Un 404
  sigue siendo del mensaje (uno que ya no está). Lo que cuesta: un 403 que fuera de un solo
  mensaje (no se conoce ningún caso: el ámbito de RBAC es el buzón entero) dejaría cada ronda en
  `permiso` en ese mensaje, a la vista en la app, en vez de perderlo sin decirlo. Qué contesta
  Graph de verdad a la lista de adjuntos con `Application Mail.ReadBasic` (403 o 404) es
  **[comprobar en vivo]** (§7.4).
- **La lista de adjuntos, por páginas si Graph la pagina** (arreglo tras la revisión). Learn no
  dice si la pagina (`docs-ms/api-reference_v1.0_api_message-list-attachments.md:47`: "supports
  the OData Query Parameters", sin más) y las colecciones de Outlook van de 10 en 10 por defecto
  (`docs-ms/api-reference_v1.0_api_user-list-messages.md:17`); sin seguir el
  `@odata.nextLink`, lo que viniera después de la primera página se perdía sin decirlo. Ahora
  se sigue, comprobado como los de la delta pero con la ruta acabada en `/attachments`
  (`enlace_de_adjuntos_valido`: nunca un `$value`), hasta `PAGINAS_ADJUNTOS` (10) páginas, y el
  tope de 4 MiB es de la lista entera. No se manda `$top`: si Graph no lo admitiera en esta
  lista, fallaría cada mensaje; seguir el enlace vale tanto si pagina como si no. Lo que pasara
  de 10 páginas no se apunta, como lo que pasa de 50 (§3.8). Si Graph la pagina y la forma de su
  `nextLink` son **[comprobar en vivo]** (§7.4, con "la lista de adjuntos sin `contentBytes`").
- **Los números de lo que llega, solo con cifras ASCII** (arreglo tras la revisión):
  `Retry-After`, `Content-Length` y el `expires_in` del token. `str.isdigit()` da por cifras
  `²` o las arábigas, que `int()` no lee (un `ValueError` que salía sin pasar por los códigos
  del correo y, en `correo comprobar`, acababa en una traza), y `int()` no lee un número de
  más de 4 300 cifras. Ahora un número de más de 6 cifras (15 en `Content-Length`) cuenta como
  "demasiado" sin pasarlo entero a `int`: un `Retry-After` así es `limitado`, un
  `Content-Length` así no se lee; uno que no es de cifras ASCII cuenta como si no estuviera, y un
  `expires_in` así da un token sin la forma esperada (`interno`).
- **Las comprobaciones que no tenían prueba** (arreglo tras la revisión; cada una falla ahora
  sin su código): la `aud` y la `appid` del token (y que un token v2, con `azp` y la `aud` del
  id de Graph, vale), `token_type`, `salida` como error de la ronda, `Accept-Encoding:
  identity`, y que una página de la delta con los dos enlaces o sin ninguno no vale.

## Paso 9 · la ronda

- **Una página que no se termina no avanza la delta** (§3.1 solo guardaba el enlace tras cada
  página completa, y §3.2 contaba los intentos por ronda): si un mensaje falla (con menos de
  tres intentos), si un tope llega a mitad o si la ronda para, el enlace se queda en la
  última página completa y la ronda siguiente la repite. Es lo que hace posible "al tercer
  intento": con el `try` de cada mensaje la página seguía y el delta no volvía a dar el
  mensaje.
- **`estado/vistos.json`**, que el diseño no tenía: la clave de cada llegada escrita en los
  últimos 7 días (como mucho 20 000). Una página que se repite no vuelve a traer lo que ya se
  trajo, aunque `orden` ya lo haya registrado y borrado de la bandeja. Sin él, con el tope del
  día a mitad de una página, cada día se volvía a bajar lo ya traído de esa página y el tope se
  gastaba en eso: no se pasaba nunca de ahí. Lo escrito en `llegadas/` que aún no se ha
  registrado también se salta. Tras perder `correo_estado`, o después de 7 días, lo repetido lo
  descarta `registrar` (§3.4).
- **Un error que no es del mensaje no cuenta contra él**: sin red, la salida, la credencial, el
  reloj, Microsoft que limita o un 403 (arreglo tras la revisión, en el paso 8) al listar sus
  adjuntos paran la ronda con ese código y le devuelven el intento (si no, tres cortes de la
  red en el mismo mensaje lo dejaban en `error`). Un corte de verdad (el proceso que muere,
  una excepción que no es `Exception`) sí cuenta, como dice §3.2; también una lista de adjuntos
  de más de 4 MiB, un 404 o un 500 al listarla, un `receivedDateTime` que no se puede leer o un
  adjunto sin id.
- **Un mensaje sin un id que se pueda guardar no tiene llegada** (no hay clave con la que
  contar sus intentos ni registrarlo) y no detiene la página; tampoco las entradas `@removed`.
- **La llegada del tercer intento**: si `receivedDateTime` no se puede leer, `recibido_en` es
  `1970-01-01T00:00:00Z` (antes de 2000: "no se sabe", §3.8 paso 4); sus adjuntos se listan si
  se puede (sin bajar nada) y van todos como `error` con "no se ha podido procesar el mensaje";
  si no se pueden listar, la llegada va sin adjuntos (una de la bandeja sin `documento` ya
  espera a una persona, `lectura_automatica.esperan_persona`).
- **Pendientes también por los topes**: un PDF que no cabe en el tope de la ronda (300 MiB) o
  en el del día a mitad de un mensaje queda en `pendientes.json` con cuándo vuelve a caber (la
  ronda siguiente, o las 00:00 en Amsterdam), y la ronda para tras ese mensaje. Así los topes
  son duros (como mucho un PDF de más, que se empieza a bajar antes de llegar) sin perder
  nada, y el tope de mensajes por ronda sigue siendo "tras la página". Los pendientes van
  primero en cada ronda; a las 24 horas, `error`. Como mucho 500 mensajes en pendientes: con
  más, lo que no se pudo bajar va como `error` (el original sigue en el buzón).
- **Un PDF que no se pudo bajar por la red** (sin red, la salida, Microsoft que limita) o por un
  403 queda pendiente y la ronda para con ese código; uno que falla por algo suyo (un 404, un
  500) queda pendiente y la ronda sigue con los demás.
- **La delta que caduca vuelve a empezar desde la última vez que esa carpeta llegó al final de
  su delta, menos 3 días** (`al_dia_en`, guardado con su enlace en `delta-bandeja.json` y
  `delta-no-deseado.json`), y no desde `ultima_buena`: una ronda puede ir bien sin llegar al
  final (los topes). Nunca antes de `desde` (a las 00:00 en Amsterdam). Un enlace guardado que
  no vale es como uno caducado: no se sigue, se empieza de nuevo y queda `delta_reiniciado_en`.
  **Al empezar de nuevo, el fichero se queda sin enlace pero con `al_dia_en`** (arreglo tras la
  revisión de los pasos 8 y 9): antes se borraba, y `al_dia_en` solo volvía al disco al
  terminar una página; si la primera página de la delta nueva no se terminaba (un mensaje que
  falla, un tope, la ronda que para o muere, otro 410), la ronda siguiente empezaba desde
  `desde` de los ajustes, que puede ser de meses antes, y volvía a bajar lo ya registrado
  (`vistos.json` solo guarda 7 días): se gastaban los topes del día en eso, `hoy.mensajes` podía
  pasar de 200 y poner la pausa por volumen, y con `$filter` Graph da como mucho 5 000 mensajes
  (`docs-ms/concepts_delta-query-messages.md:56`).
- **`ultima_consulta` y `ultima_buena`** son el principio de la última ronda que habló con
  Microsoft y de la última que además fue bien; una ronda retenida (que no pide nada) no cambia
  ninguna. **`hoy.mensajes` cuenta las llegadas escritas de las dos carpetas**, y
  `aviso_volumen` es que pasan de 200. **Un PDF nuevo** es uno bajado que empieza por `%PDF-`
  (aunque `registrar` lo encuentre ya en la base); los bytes del día son todo lo que se bajó.
- **`correo comprobar` deja su resultado como una ronda** en `estado.json` (`ronda` sin
  mensajes, `bien` o `fallo` con su código, y el alcance) y no cambia `hoy`, `retenido_hasta`
  ni la delta: es lo que la app verá tras `correo-configurar`. Con otra ronda en marcha dice
  que está ocupado y sale con 1 (una ronda ocupada sale con 0: no es un error).
- **Códigos de salida**: 0, `CORREO_SIN_CONFIGURAR` (10) y `CORREO_FALLO` (11, nuevo), con el
  código del correo en la salida de errores. La copia de los dos en `docker\comun.ps1` es del
  paso 15, que los usa. Unos ajustes que no valen son `sin_configurar` (hay que fijarlos), y un
  certificado que no se puede usar, `credencial`.
- **El cerrojo, solo `fcntl.flock`**: sin `msvcrt` (la nativa no trae el correo); fuera de
  Linux, `correo traer` lo dice y no corre.
- **Al empezar, la ronda limpia lo que dejó una ronda muerta a medias** (los `.parcial-*` de la
  bandeja y del estado; con el cerrojo en la mano no se está escribiendo nada), además de lo
  de más de 45 días y de los intentos y vistos de más de 7.
- **Lo que §3.3 no decía**: el nombre gana al tipo declarado para decidir si se baja
  (`factura.xml` con `application/octet-stream` es `xml`, y `factura.pdf` con
  `application/xml` se baja: después manda `%PDF-`); un adjunto sin `@odata.type` o de un tipo
  que no se conoce, y los que pasan de los 20 tratados, quedan `no_pdf` con su detalle; los que
  pasan de 50 no se apuntan (el tope de la llegada de §3.8); un tamaño declarado que no es un
  número no impide bajarlo (cuenta lo que llega); un mensaje con `hasAttachments` falso no
  pide la lista (Graph lo da falso también cuando solo hay imágenes en línea: `en_linea` queda
  en 0); un mensaje de "no deseado" sí pide la lista (sin contenido) para apuntar cada adjunto.
  Una llegada de más de 64 KiB acorta sus textos y, si aún no cabe, apunta menos adjuntos.
- **El remitente y el asunto** se guardan saneados (sin controles, sin caracteres de dirección
  ni de anchura cero, los blancos juntos) y recortados a 320 y 200; un `internetMessageId` que
  no es ASCII visible de hasta 998 caracteres va como `null`.
- **Una fecha que se sale del calendario es la de un mensaje raro, no un fallo de cada ronda**
  (arreglo tras la revisión). Un `receivedDateTime` como `0001-01-01T00:00:00+01:00` (el año 0 en
  UTC) hacía saltar un `OverflowError` al pasarlo a UTC: en las tres primeras rondas el mensaje
  fallaba, pero en la cuarta su llegada de error lo volvía a leer fuera de su `try` y cada ronda
  acababa en `interno`, sin pasar nunca de esa página ni llegar a "no deseado". Ahora
  `bandeja.leer_instante` da `None` (no se sabe: `1970-01-01T00:00:00Z` en la llegada), y
  `bandeja.instante` escribe el año siempre con cuatro cifras (`strftime("%Y")` no rellena los
  anteriores al 1000).
- **`correo comprobar` no acaba en una traza** (arreglo tras la revisión): un fallo del programa
  al comprobar es `interno` (sin el texto de la excepción), con su `estado.json` y la salida 11,
  como en una ronda.
- **Las comprobaciones que no tenían prueba** (arreglo tras la revisión; cada una falla sin su
  código): `al_dia_en` con el `nextLink` de la delta nueva, el segundo 410 seguido (sin él, un
  Graph que siempre contesta 410 tenía la ronda pidiendo sin fin), la llegada del tercer
  intento que espera si la ronda no puede listar (sin red, un 403: si no, se escribía sin
  adjuntos), lo que ya está en pendientes o escrito y sin registrar no se vuelve a listar,
  `MAX_PENDIENTES`, la limpieza de `vistos.json` e `intentos.json` (7 días, `MAX_VISTOS`), una
  comprobación con fecha futura o que no salió bien con un código que no está en
  `REPETIR_ALCANCE` (falla cerrado, §2.3), la llegada de más de 64 KiB (los nombres los pone el
  remitente), el `internetMessageId` de 998 y el id de un adjunto que no es ASCII visible.
- **Un tope más, de páginas por ronda (40, las dos carpetas)**: lo ya visto no cuenta como
  mensaje, así que una delta que vuelve a empezar (o que no acaba) pediría páginas sin fin en
  la misma ronda. Tras 40 páginas la ronda para con el enlace guardado y la siguiente sigue.
- **Para el paso 10 (`registrar`)**: los formatos son los de `correo/bandeja.py` (la llegada
  con las claves de §3.7, `resultado` de `bandeja.RESULTADOS`, `recibido_en`
  `1970-01-01T00:00:00Z` cuando no se sabe; `estado.json` con `version`, `ronda`, `hoy`,
  `ultima_consulta`, `ultima_buena`, `buzon`, `certificado`, `alcance`, `delta_reiniciado_en`,
  `retenido_hasta` y `aviso_volumen`). Un PDF puede estar en `pdf/` antes que su llegada (un
  mensaje con otro adjunto pendiente): no es un huérfano mientras no pase de 45 días. El
  correo no escribe nunca un resultado que no sea de la lista (los internos `_bajar` y
  `_pendiente` solo viven en `pendientes.json`).
