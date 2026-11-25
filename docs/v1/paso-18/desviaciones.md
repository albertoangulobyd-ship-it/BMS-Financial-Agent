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

## Paso 10 · registrar y el latido

- **Solo Linux, con `dir_fd`** (la decisión del dueño): sin la nativa no hay camino de Windows
  («se vuelve a comprobar la carpeta antes de cada fichero», §3.8 paso 1). Donde `os.open` u
  `os.unlink` no admiten `dir_fd`, o no hay `O_NOFOLLOW`, `correo registrar` dice que es de
  Docker y no corre (`NoSeRegistra`, salida 2), como `correo traer` sin `flock`. La carpeta de
  la bandeja (`--entrada`) se abre con `O_DIRECTORY | O_NOFOLLOW` y `llegadas` y `pdf` relativas
  a ella (no por su ruta entera), con el mismo `st_dev`/`st_ino` que dio `lstat`.
- **Las rutas, por argumentos** (`--entrada`, `--estado`), como `correo traer`; con `--fallo`
  no hacen falta: **`--fallo` solo apunta** (no registra la bandeja), que es lo que pide §4.1
  («`correo registrar --fallo disco` y fin»). Admite la lista cerrada entera de §3.7. **Sin
  nada del correo en la base (`estado_correo` vacío), `--fallo` no apunta nada** (arreglo tras
  la revisión, abajo).
- **Lo que no casa no se pierde sin decirlo.** Un PDF que no está en `pdf/`, que no tiene el
  sha256 de su nombre, que no empieza por `%PDF-` o que pasa de `MAX_PDF` deja su adjunto como
  `error` y el mensaje se registra igual (espera a una persona en «Wacht op jou»); el fichero
  que no casa se borra y cuenta como rechazado (§3.8 paso 7). Solo una llegada que no vale
  entera (JSON, claves, tipos, el nombre del fichero) se rechaza sin registrar nada. Un PDF de
  los datos de prueba deja `de_prueba` (también en las otras llegadas de la misma pasada que lo
  traen) y se borra.
- **Lo que §3.8 paso 4 no fijaba de la validación**: el `sha256` solo en un `pdf` (en lo demás,
  `null`, como lo escribe `traer`); el `id` de un adjunto no se repite en su mensaje (`UNIQUE
  (mensaje_id, graph_adjunto_id)`); los enteros, de 0 a 2^53; claves repetidas, `NaN` e
  `Infinity` no valen; los instantes, exactamente `AAAA-MM-DDTHH:MM:SSZ` (lo que escribe
  `bandeja.instante`). El remitente, el asunto y los nombres **se vuelven a sanear**
  (`bandeja.sanear`) en vez de rechazar la llegada: un control o un carácter de dirección se
  quita, como al traerlo. El `detalle` de cada adjunto se valida y no se guarda (sin columna,
  paso 2).
- **Las 2 000 por pasada**: primero las llegadas (las más antiguas por `mtime`), y con lo que
  queda, los PDF sueltos de `pdf/` (los que ya están en la base salen; los demás esperan a su
  llegada: un mensaje con otro adjunto pendiente, desviación del paso 9). Lo que no tiene
  nombre de la bandeja no se toca ni cuenta (lo limpia el correo a los 45 días); lo que tiene
  nombre de la bandeja y no es un fichero normal (un enlace, una carpeta, un FIFO) se rechaza y
  se quita la entrada, sin seguirla, aparte y sin ocupar el sitio de lo de verdad (arreglo tras
  la revisión, abajo).
- **Un mensaje que no entra por algo de la base o del almacén** (`IntegrityError`,
  `DocumentoCorrupto`) se queda en la bandeja para la vez siguiente, sin rechazarlo: no es culpa
  de la bandeja. La CLI lo dice y sale con `CORREO_FALLO`.
- **Un mensaje repetido** (la delta que vuelve a empezar, §3.4) sale de la bandeja sin filas ni
  eventos nuevos; su PDF, si ya está en la base. Si la primera vez su PDF no se pudo registrar
  (`error`), esa llegada ya es evidencia y no cambia: el PDF que vuelva no entra por ahí (lo
  limpia el correo a los 45 días).
- **La evidencia** (el hueco que dejó el paso 2): `mensaje_correo` con su evento
  `correo_mensaje_registrado`, que lleva la foto del mensaje y la de cada uno de sus
  `adjunto_correo` (`evidencia.ADJUNTOS`, como los movimientos en el evento de su extracto), y
  `ronda_correo` con `correo_ronda_registrada`, las dos con el usuario `correo`. `db verificar`
  ve una fila de las tres metida o cambiada por detrás. El ayudante `_correo` de
  `test_lectura_automatica.py`, que apunta mensajes a mano, escribe ahora ese evento.
- **`ronda_correo`, «si la ronda trajo algo o el código de error cambió»** (§3.8 paso 8): una
  vez por ronda (su `empezada`) y comparando con el código de la última ronda apuntada, no con
  el de `estado_correo` (que puede llevar lo de un `--fallo` o lo que vio la pasada); si no, en
  un día con el reloj mal cada ronda buena «cambiaría» el código y serían 288 filas.
  `documentos_nuevos` es el `pdf_nuevos` de la ronda (lo bajado, desviación del paso 9). Un
  `--fallo`, y lo que ve la pasada (`reloj`, `interno`), es una fila sin `terminada_en`, solo
  cuando cambia el código.
- **El error de `estado_correo` es el más reciente** entre la ronda de `estado.json` y el último
  `--fallo` (o lo que vio una pasada): un `estado.json` de antes (el correo no corrió porque la
  salida no arrancó) no quita el `salida` que apuntó el ciclo; la ronda siguiente del correo,
  sí. Lo que ve la pasada misma gana siempre: `reloj` (una llegada más de 5 minutos «en el
  futuro») e `interno` (una de las tres carpetas no es una carpeta de verdad, o `estado.json`
  no vale; el resto de `estado_correo` se queda como estaba). Sin `estado.json`, el error que
  ya estaba (cada `--fallo` ya lo escribió en `estado_correo`). `error_desde` es el principio del
  error mientras el código no cambia (la regla de los 30 minutos de §6.2).
- **La pausa por volumen, solo con el `aviso_volumen` de hoy**: con el `hoy.fecha` de
  `estado.json` igual al día de Amsterdam. Si no, el `estado.json` de ayer (el correo aún no ha
  corrido hoy) pararía la automática de un día nuevo. La pone `lectura_automatica.pausar`, una
  vez al día (paso 4).
- **`ciclo latido` en un módulo propio, `ciclo.py`** (`latido`, `leer`), sin red ni procesos.
  Sin `--pausado` es que el ciclo corre (`pausado = 0`; `--reanudado` dice lo mismo, para
  `Reanudar-Automatico` si lo quiere usar); con `--pausado`, `pausado_desde` se queda en la
  primera vez. `visto_en` se pone siempre; el disco y la variante, si no se dan, quedan como
  estaban. Un disco libre negativo o de más de 2^62, o otra variante, no se apuntan (salida 2).
  Con menos de 10 GiB lo dice, y no decide nada: el que no trae ni lee es el ciclo (paso 15).
- **Códigos de `correo registrar`**: 0; `CORREO_FALLO` (11) si algo se rechazó, una carpeta no
  valía, un mensaje no entró o algo de la bandeja no se pudo quitar; 2 con la base de prueba, en
  la instalación nativa o sin las carpetas. Lo que dice no copia nunca texto de la bandeja:
  cuentas y motivos fijos. **Lo rechazado se cuenta ahí** (la salida de la orden, que guarda el
  registro del ciclo) y no en `ronda_correo`, que no tiene columna para eso (§3.8 paso 7 decía
  «queda contado en la ronda»; §3.9 no le daba columna, y no se añade: el correo de verdad nunca
  escribe algo que no vale, así que un rechazo es un fallo del programa o un correo
  comprometido, que se ve en el registro del ciclo).
- **De punta a punta (§7.3)** en `test_correo_registrar.py`: `GraphFalso` → `traer` →
  `registrar` → `_ronda` de `test_lectura_automatica.py` (las mismas funciones que las órdenes
  del ciclo) con el cliente falso, la fecha de recepción del servidor en cada factura (también
  una que llegó a las 23:30 UTC, que es el día siguiente en Amsterdam), el mismo correo otra
  vez sin pagar nada, y un PDF que la API no acepta (413) entre dos buenos, en «Wacht op jou».
- **`--fallo` sin el correo no lo da por configurado** (arreglo tras la revisión de los pasos 10
  y 11). Una fila en `estado_correo` es lo que dice a la app que el correo está configurado
  (§6.2: `sin_configurar` si está vacío), y el ciclo apunta `--fallo disco` sin mirar si hay
  correo (§4.1, paso 2). Antes, un Docker sin correo con poco disco una vez quedaba para siempre
  con `configurado` verdadero, `error`/`disco` y la banda roja del buzón: solo lo quitaba un
  `estado.json` de una ronda del correo, que sin correo no llega nunca. Ahora, con
  `estado_correo` vacío, `--fallo` no escribe nada (ni `ronda_correo`) y lo dice; el disco ya lo
  dicen `estado_ciclo` y su banda. Con el correo ya registrado, todo sigue como antes. Lo que
  cuesta: un `--fallo salida|aislamiento` de un correo recién configurado cuyo `estado.json`
  (el de `correo comprobar`) aún no ha pasado por `correo registrar` no se ve hasta el ciclo
  siguiente. **Para el paso 15**: que el ciclo corra `correo registrar` también cuando el correo
  no pudo traer nada (registra lo que ya hubiera), y que `correo-configurar` termine con `correo
  registrar`, para que la app vea el correo configurado y el resultado de la comprobación sin
  esperar al ciclo; si el correo deja de estar configurado, la app sigue con su último estado
  mientras nadie corra `correo traer` (que deja `sin_configurar` en `estado.json`).
- **Lo que no se puede quitar de la bandeja se ve** (arreglo tras la revisión). `_borrar` se
  tragaba cualquier `OSError` y la CLI salía con 0: con el volumen `correo_entrada` de otro dueño
  (lo que aquí no se puede probar, sin demonio de Docker), la bandeja no se vaciaba nunca, cada
  pasada decía «N repetidos» y, con 2 000 así, el correo nuevo no entraba. Ahora, lo que no se
  puede quitar (salvo que ya no esté) se cuenta una vez por pasada, la pasada deja `interno` (la
  app lo dice, como una carpeta que no vale) y la CLI sale con `CORREO_FALLO` diciendo cuántas.
- **Lo que no es un fichero normal no ocupa el sitio de las llegadas** (arreglo tras la
  revisión). Lo raro con nombre de la bandeja se elige aparte (otras 2 000 como mucho por
  carpeta, también las más antiguas) y se quita sin leerlo: un enlace, un FIFO o una carpeta
  vacía (`rmdir` relativo a la carpeta, que no sigue enlaces). Una carpeta con algo dentro no se
  vacía (nunca se borra nada de dentro): queda, cuenta como no quitada y deja `interno`. Antes,
  2 000 carpetas más antiguas con nombre de llegada se rechazaban en cada pasada sin quitarse
  (lo que decía este documento, «se quita la entrada», no era verdad) y no dejaban entrar nada
  más; y un PDF que era una carpeta se contaba como quitado sin estarlo (`pdf_borrados` cuenta
  ahora solo lo que se quitó). **Lo que queda**: una llegada «del futuro» sí ocupa su sitio
  (hay que leerla para saberlo), así que 2 000 así, más antiguas que las demás, las dejarían
  esperando; mientras, la app dice `reloj`. Que se queden así para siempre solo lo consigue un
  correo comprometido (fechas que el reloj no alcanza nunca: el de verdad toma la del servidor
  de Microsoft), que de todas formas puede dejar de traer el correo. No se rechazan, porque con
  el reloj de este equipo muy atrasado (una pila de la placa agotada) las de verdad también son
  «del futuro» y tienen que esperar (§3.8, paso 4).
- **Las comprobaciones que no tenían prueba** (arreglo tras la revisión; cada una falla ahora sin
  su código): el tope de 50 adjuntos (la llegada de 51 llevaba el mismo id repetido, y la
  rechazaba eso) y que 50 entran, la fila de `ronda_correo` de lo que ve la pasada (`reloj`,
  `interno`) solo cuando cambia, el recorte de las más antiguas con más de 4 × 2 000 entradas,
  el `motivo_codigo` del alcance en `estado.json`, y un documento ya apuntado sin su original
  cuyo PDF llega bien (se añade), no casa o no está (el adjunto apunta igual a ese documento).

## Paso 11 · la API

- **`GET /api/v2/correo`, lo que §6.2 no fijaba**: `estado` y `configurado` dicen
  `sin_configurar` también cuando el correo corrió sin ajustes (`error_codigo` `sin_configurar`
  en su `estado.json`), no solo sin fila en `estado_correo`: no es un fallo, es que falta
  configurarlo. `retenido_hasta` sale solo mientras dura (el de ayer, `null`). `credencial.dias`
  son los días enteros que quedan (negativo, caducado). `hoy` es el de hoy en Amsterdam: si el
  `estado.json` copiado es de otro día, ceros. `entorno` sale como en `/api/v2/aislamiento`
  (`nativo` con la comprobación de la nativa, `contenedor` en `0.0.0.0`, `local`). `recientes`,
  los 10 más recientes por la hora del servidor de Microsoft, también los de «no deseado».
- **`nombre_original` y `etiquetas` (lo que los pasos 4 y 5 dejaron para aquí)**: `_resultado`
  guarda `nombre_original` en cada fila al terminar (el del documento), y `_pasada` lo pone al
  leer en las filas que no lo llevan (las de antes del 2.6 y las de mientras lee, que solo
  tienen nombre y estado), desde `etiquetas`. `etiquetas` cubre los nombres del resultado y el
  documento en curso que son `<64 hex>.pdf` de un documento con `nombre_original`; un PDF de
  `buzon\facturas` ya se llama como llegó y no lleva etiqueta. `_pasada` necesita la conexión
  (`_pasada(conn, fila)`).
- **`solicitud.omitidos` (nuevo, lo que el paso 3 dejó para los pasos 11 y 12)**: los PDF que la
  cuenta dejó fuera (`clase` `omitido` de `estimacion_json`), con `nombre`, `nombre_original` y
  `rechazado_api`, sin el `detalle` (texto de la API o de una excepción): Procesar dirá cuál y
  por qué con su propio texto (§13 S1, «omitido con su motivo en Procesar»).
- **Las cuatro órdenes de la lectura automática, en `docs/integracion-web.md`** (las añadió el
  paso 4 sin documentarlas: van con el 2.6, §8), con sus errores de verdad (`falta_motivo`,
  `invalido`, `no_existe`, `estado_no_valido`), y los valores nuevos de `origen`,
  `aprobada_via` y `motivo_codigo` (lo que el paso 3 dejó para aquí). Un valor nuevo en una
  lista que ya existía no se cuenta como «cambiar de forma»: sube el menor.
- **Las bandas del servidor (§6.1)** las calcula `consultas.bandas_urgentes` y las pinta
  `app_local.bandas` (`urgentes`), una por cosa, en neerlandés e inglés, solo en `/app` (no en
  la consola vieja), abriendo la base en cada carga de la página; si no se puede leer, sin
  bandas (la página sale igual y la app dice el error al pedir sus datos). Lo que §6.4 no
  fijaba del texto:
  - el certificado que caduca en 30 días o menos no dice «er komen geen facturen meer binnen»
    (aún entran): «Het certificaat verloopt over {n} dagen ({fecha})…»; el caducado, sí;
  - «ninguna ronda buena en 24 h» no sale si ya sale el porqué (el certificado, el alcance o el
    buzón de control), para no decir dos veces lo mismo; sin ninguna buena todavía, las 24 horas
    cuentan desde la primera ronda apuntada (o desde el error), no desde siempre (arreglo tras
    la revisión, abajo);
  - el ciclo en pausa cuenta desde `pausado_desde`; el disco, en GB enteros;
  - la de la API mira la última lectura terminada (de una persona o automática): `fallida` con
    `saldo` o `clave_rechazada`; una lectura posterior que acaba de otra forma la quita;
  - la de las facturas que esperan más de 4 horas sale con la automática encendida y sin pausa
    ni tope (con la espera tras un fallo, sí: es lo que tapaba O2); la espera cuenta desde que
    la factura entró (la registró `correo registrar`) y desde que la automática está encendida
    sin apagarse (cambiar los topes no la apaga), y «sin ninguna automática buena desde
    entonces» es «ninguna `hecha` en esas 4 horas» (arreglo tras la revisión, abajo); cuenta las
    elegibles que entraron hace más de 4 horas.
  Solo números, fechas y textos fijos: nada de lo que trajo el correo. Para no tocar el
  frontend (es del paso 12), la banda usa la clase roja que ya existe (`bms-banda-aislamiento`)
  y además `bms-banda-urgente`, sin estilo propio todavía.
- **El frontend no cambia**: nada fija la versión menor del contrato (`CONTRACT_MAJOR = '2'`,
  `lib/api.ts:17`) y ningún test del frontend la compara. **Para el paso 12**: los tipos de
  `api-types.ts` («Contrato 2.6», opcionales: la respuesta de `GET /api/v2/correo`,
  `automatica`, `solicitud.autorizacion`, `solicitud.omitidos`, `etiquetas`,
  `nombre_original`, y las uniones de `ReadingRequest` con `automatica` y los siete motivos),
  `paths.mailbox`, y, si quiere, un estilo propio para `.bms-banda-urgente`.
- **Las pruebas**: `/api/v2/correo` por el servidor (token, permiso, claves, sin decimales, el
  IBAN de un asunto enmascarado para otro origen, la ruta en `/api/v2/contrato`) y las reglas
  del estado en `test_contrato_v2.py`; las claves nuevas de `/api/v2/lectura` (también las de
  una pasada de antes del 2.6 y los omitidos) en `test_lectura.py`; las bandas, una por
  condición, en `test_ciclo_latido.py`, y en la página de verdad en `test_app_local.py`; los
  códigos de `/api/v2/correo` en `test_codigos_error.py`; los dos literales «2.5»
  (`test_cartera.py`, `test_lectura.py`) pasan a «2.6», y `test_lo_que_lee_la_app` gana la
  clave `automatica`.
- **Las dos bandas que salían a destiempo** (arreglo tras la revisión de los pasos 10 y 11):
  - «Al meer dan 24 uur geen geslaagde controle» salía en cuanto `ultima_buena` era `NULL`: un
    buzón configurado hace cinco minutos cuya primera ronda falló por la red salía en rojo
    («más de 24 horas») mientras `/api/v2/correo` decía `retrasado` («sigue solo»). Sin ninguna
    buena todavía no hay desde cuándo contar; ahora cuenta desde la primera fila de
    `ronda_correo` (lo primero que se supo del correo) o, sin ninguna, desde `error_desde`.
  - «N facturen wachten al meer dan 4 uur» medía la espera desde `receivedDateTime` (la hora del
    servidor de Microsoft): un correo recibido de noche, lo de antes de configurar el correo
    (`desde`), lo retenido por los topes del día o una delta que vuelve a empezar salían en rojo
    nada más registrarse; y al revés, cualquier automática `hecha` posterior a esa hora vieja
    tapaba la banda aunque después todas fallaran (el caso O2 que la banda tenía que ver).
    Ahora la espera cuenta desde `mensaje_correo.registrado_en` (la primera vez que entró) y
    desde que la automática está encendida (`lectura_automatica.encendida_desde`: la primera
    autorización tras la última apagada; recién encendida con atrasos, no es urgente), y la
    tapa solo una automática `hecha` en las últimas 4 horas. Lo que queda: tras quitar una pausa
    con atrasos de antes, la banda puede salir hasta que termina la primera automática (el
    ciclo siguiente).
- **Las comprobaciones de la API que no tenían prueba** (arreglo tras la revisión; cada una
  falla ahora sin su código): `hoy` solo con el de hoy en Amsterdam, el orden y el tope de
  `recientes` (los 10 más recientes por la hora del servidor, no por el orden de registro), el
  signo de `credencial.dias`, la banda del alcance con `alcance_bien` 0 sin el error `alcance`,
  y la de las facturas que esperan (el umbral, desde cuándo y la automática buena reciente).

## Paso 12 · la app

- **Una factura sale de «Wacht op jou» cuando tiene extracción o cuando una persona la aparta**
  (lo que los pasos 4 y 5 dejaron para aquí). `esperan_persona` ya no da las facturas cuya
  última exclusión es de una persona (`persona`): una persona ya las miró y decidió que no se
  lean (ni solas ni desde Procesar, `FUERA_DE_PROCESAR`), así que no esperan a nadie; si no,
  se quedaban en la lista para siempre, porque ninguna lectura les va a dar una extracción. Lo
  que apartó la automática (`grande`, `fallo`, `rechazado_api`) sigue en la lista hasta que se
  lee desde Procesar (las dos primeras) o hasta que una persona lo aparta también con «Niet
  vanzelf lezen», que la lista ofrece en cada factura (el botón para apartar lo que apartó la
  automática). En la API, `motivo_codigo` de `esperan_persona.documentos` ya no vale `persona`
  (`docs/integracion-web.md` lo dice); la app conserva su texto por si llega.
- **`lectura_automatica.cola` en `GET /api/v2/correo`** (contrato 2.6, sin cambiar de forma: una
  clave más en un objeto). §6.1 pide en la tarjeta «Automatisch lezen» la lista «Wacht op
  automatisch lezen» (las elegibles, las más antiguas primero) con casillas y «Niet vanzelf
  lezen», pero §6.2 solo daba cuántas hay (`elegibles`) y la más antigua: sin los ids no se
  puede apartar nada en bloque (S12, la inundación). La cola son las elegibles, las más
  antiguas primero, con `documento_id`, `nombre_original` (el nombre del adjunto: texto de quien
  lo mandó) y `recibido_en`, como mucho `MAX_EXCLUIR` (200, las que se apartan de una vez). Solo
  en `/api/v2/correo`: `/api/v2/lectura` lleva el resto de `lectura_automatica` y la app lo
  consulta cada 2 segundos.
- **La descripción de `excluir_de_lectura_automatica` en `textos/*.json`** seguía diciendo «je
  kunt ze via Verwerken laten lezen» (lo que el arreglo de los pasos 4 y 5 quitó de
  `servicios.py`): ahora dice lo mismo que `servicios.py` (no se leen, ni solas ni desde
  Procesar; también lo que la automática ya apartó).
- **Solo Docker en la app** (la decisión del dueño; lo que el paso 11 dejó para aquí). La app
  pregunta a `GET /api/v2/correo` (al abrir Systeem, Inicio y Procesar, nunca en bucle) y solo
  enseña el correo y la lectura automática si `entorno` no es `nativo`: en Docker
  (`contenedor`) y en `local` (la base de prueba de las e2e y las herramientas). En la nativa no
  sale nada nuevo: ni las dos filas de Systeem, ni la línea de Procesar, ni la de Inicio; la
  petición se hace y no enseña nada. Tampoco se hace lo de §6.1 para el quinto papel
  (`settings.roles.correo`, «Alle onderdelen»): es del paso 13, que no se hace. Que la nota de
  Instellingen en reposo («Bedrijf, afscherming, personen en back-ups») no nombre el buzón es a
  propósito: en reposo no se sabe la variante sin pedir `/api/v2/correo`.
- **Dónde va cada cosa en Aurora**, que no tiene la pantalla de Instellingen ni el «Wat op
  iemand wacht» que §6.1 citaba (`nl.ts:1254-1258` es hoy `money.notices`, del panel del
  dinero):
  - Systeem pasa a seis filas (con Personen): `GroupView` gana `limit` y Systeem las enseña todas,
    sin el buscador (con cinco como máximo, una quedaba detrás de «En nog 1»). Cada fila abre su
    tarjeta (`mailbox-card.tsx`, `auto-read-card.tsx`), y la fila lleva el estado en su texto y
    su color (`rowTone`), como las demás.
  - En Inicio, «N mails en facturen wachten op jou» es una fila más de «WAT AANDACHT VRAAGT»
    (solo si algo espera) que abre Instellingen › Systeem con la tarjeta del buzón (la vista
    `mailbox` del panel).
  - Las listas de las tarjetas («Wacht op jou», los últimos correos) enseñan 5 y «Alle N tonen»
    (la API da hasta 50; con más, «50 van 61 tonen», abajo); la cola de la automática, entera
    (hasta 200), con «Alles kiezen».
- **«Con enlace a Documentos y a Procesar»** (§6.1, las facturas de «Wacht op jou»): una
  factura que no se ha leído no tiene empresa ni hoja en Documenten, así que no hay sitio al que
  enlazar. Cada una ofrece «Origineel downloaden» (la descarga auditada de siempre, con un nombre
  generado, nunca el del adjunto), «Lezen via Verwerken» solo para `grande` y `fallo` (lo que
  Procesar lee con el sí de una persona) y «Niet vanzelf lezen».
- **Procesar**: la línea (`process.strip`) sale encima de la escena con la `automatica` de
  `/api/v2/lectura` (cada 2 s) y la última consulta del buzón de `/api/v2/correo` (al abrir y
  tras cada orden); sin correo configurado y con la automática apagada no sale (no diría nada).
  Si está parada, el porqué debajo y «Weer aanzetten» para las dos pausas (`persona` y
  `volumen`, como en la tarjeta). Una automática no tiene «Empezar» y, si se ve esperando su sí,
  no dice «Je hebt tot … om te beslissen» sino de dónde viene y quién firmó la autorización. Una
  automática terminada sin leer que la visita no siguió es P0 (la nota y la línea dicen cómo
  acabó): si no, Procesar se abría con «Geen nieuwe facturen» de una lectura que nadie pidió. Lo
  que la cuenta dejó fuera (`omitidos`) sale con su porqué y el nombre con que llegó (§13 S1), y
  los PDF del correo se nombran por `etiquetas`/`nombre_original`, no por su `<sha256>.pdf`.
- **La segunda frase de `saldo` y `api_no_disponible` según el origen** (lo que el paso 3 dejó
  para aquí): «daarna gaat het vanzelf verder» / «het wordt later vanzelf opnieuw geprobeerd» solo
  en una automática; la de una persona (o del lector) no sigue sola y dice que la vuelva a pedir
  (`process.reasonsByHand`). `reasonOf` recibe el `origen`. Las bandas del servidor (paso 11)
  siguen con la frase de la automática.
- **Los textos de §6.4, con estos cambios**: van en `aurora.mailbox`, `aurora.autoRead`,
  `aurora.process` y `status.{mailbox,autoRead,certificate}` (las claves de la tabla eran
  orientativas); los nombres de los scripts, como huecos de `WithScriptNames`
  (`correo-configurar.bat`, `correo-certificado.bat`, `iniciar.bat`, `automatico.bat`, los de
  Docker del paso 15). `autoRead.pausedPerson` va sin `{name}`: la API no dice quién paró la
  automática (la pausa sí lo guarda, pero `parada` no lo trae), y «iemand» dice lo mismo sin otra
  clave. `autoRead.failed` dice «Volgende poging {when}» con «vandaag om 12:00» o la fecha: el
  próximo intento puede ser otro día (hasta 24 h). Nuevos, porque la tarjeta los necesita:
  la última buena (solo si no es la última consulta), «nog nooit», el certificado a 1 día y hoy,
  qué hacer con él (≤ 60 días), el alcance aún sin comprobar, el ciclo que no ha corrido nunca,
  el disco libre, los últimos correos, la frase de «Afgehandeld» y de apartar, lo que queda hoy,
  nunca encendida y apagada, elegir en la cola, los errores del formulario, quién firmó (en
  Procesar), la línea con la automática apagada, los omitidos y la fila de Inicio (con su
  singular). El formulario pide los importes en dólares con la notación de la app (`2,00`) en los
  tres idiomas, y comprueba lo mismo que `lectura_automatica.validar` antes de mandarlo (el
  servidor lo vuelve a mirar). Una fecha de recepción que no se sabe (`1970-01-01`, §3.8 paso 4)
  no se enseña.
- **Las pastillas**: tres grupos nuevos en `status-pill.tsx`: `correo` (el estado de la API),
  `lectura_automatica` y `certificado` (derivados). Laten un buzón que no funciona y un
  certificado caducado (no entra ninguna factura); lo demás, quieto.
- **La banda `.bms-banda-urgente`** (lo que el paso 11 dejó para aquí) tiene estilo propio en
  `index.css`: el rojo un poco más oscuro, la línea de abajo marcada para que dos seguidas se lean
  como dos y su peso normal (son frases); igual en los dos temas, como las demás bandas.
- **Las herramientas de diseño** ganan dos estados (`instellingen-mailbox`,
  `instellingen-automatisch`): con la base de prueba de las e2e, el buzón sale sin configurar y
  la automática apagada (con el formulario). Los estados con correo de verdad (los que esperan,
  una pausa, un fallo) necesitan el simulador del paso 16 (`scripts/simular_correo.py`); aquí se
  miraron a mano sobre una base de prueba sembrada (las cuatro órdenes en el navegador, los dos
  temas, 1440 y 400 px).
- **Lo que una persona aparta se sigue viendo: «Apart gezet»** (arreglo tras la revisión del paso
  12). Con la primera desviación de esta sección, una factura apartada con «Niet vanzelf lezen»
  (también con «Alles kiezen», 200 de una vez, en una inundación) salía de la cola y de «Wacht op
  jou» y, sin extracción, tampoco estaba en Documenten: desaparecía de la app, y la exclusión no
  se quita nunca. Ahora `GET /api/v2/correo` lleva `lectura_automatica.apartadas` (solo ahí, como
  `cola`): lo que una persona apartó y sigue sin leer, las últimas primero, como mucho 50, con su
  total, quién y cuándo (`lectura_automatica.apartadas_por_persona`). La tarjeta «Automatisch
  lezen» lo enseña debajo de la cola, solo para verlo y bajar el original (con un nombre
  generado), sin ninguna orden. El camino de vuelta, que ya existía y ahora tiene su prueba
  (`test_lo_que_aparto_una_persona_se_lee_si_su_pdf_vuelve_a_buzon_facturas`): el PDF dejado en
  `buzon\facturas` se lee con el sí de siempre (las exclusiones solo quitan lo del correo), y
  leído sale de «Apart gezet». La tarjeta lo dice, y los dos textos de apartar («Niet vanzelf
  lezen» en «Wacht op jou» y en la cola) dicen dónde se encuentra después. §6.1 dejaba lo apartado
  por una persona en «Wacht op jou»; no se vuelve a eso porque no espera a nadie (la lista no se
  vaciaría nunca), y la lista aparte enseña lo mismo sin pedir nada.
- **Lo que la cuenta dejó fuera, también cuando la petición acaba al contar** (§13 S1; arreglo tras
  la revisión). `solicitud.omitidos` sale de `estimacion_json`, y solo la petición que esperaba el
  sí la guardaba: la de una persona en la que la API no acepta ninguno de los PDF nuevos (`fallida`
  con `contar`, el caso para el que estaba S1) y la que no tiene nada que leer no decían cuál, y
  Procesar solo decía «Kon niet uitrekenen wat het kost». Ahora `lectura.contar` guarda la cuenta
  (sin huella: no hay nada que aprobar) también en sus finales sin sí (`nada_que_leer`, `fallida`
  con `contar` o `sin_tarifa`) cuando dejó algo fuera; sin nada fuera, como antes
  (`test_lectura.py` pasa de pedir `estimacion_json` nulo a pedir los omitidos en la API).
  Procesar los enseña también en la pantalla de error y, para quien llega después, en P0 junto a
  «Laatste leesronde niet afgemaakt» (`omittedShown`), con el nombre con que llegaron. La lectura de una persona sigue sin apartar nada de lo del correo que la API no
  acepta (lo hace solo la automática, paso 5); con el nombre a la vista, una persona lo aparta
  desde la cola, o quita el fichero de `buzon\facturas`.
- **En Docker no se nombra ningún script de la nativa** (arreglo tras la revisión). El correo y la
  automática solo existen en Docker, que no tiene `clave.bat` ni `comprobar.bat` (la clave es
  `docker\secretos\anthropic_api_key.txt`, `entorno-local.md` §4), y la tarjeta y la línea de
  Procesar decían «Voer comprobar.bat uit» (`mailboxErrors.aislamiento` de §6.4) o, en el fallo de
  la automática, los porqués de la lectura con `clave.bat` y `comprobar.bat`. Ahora:
  - el error `aislamiento` del buzón dice que no se trae nada hasta que la persona que mantiene
    el programa revise la instalación (sin script: Docker no tiene uno que compruebe el
    aislamiento, y `automatico.bat -Estado` del paso 15 no lo mira);
  - `reasonOf` tiene los porqués de Docker (`process.reasonsDocker`: `clave`, `clave_rechazada`
    con el fichero de `docker\secretos`; `aislamiento`, que revise la instalación) para una
    automática siempre y, en Docker, también para la de una persona: Procesar sabe la variante
    por `GET /api/v2/correo` (`entorno` `contenedor`), que ya pedía. Con `leer-facturas.bat` de
    Docker sin la clave, la petición acaba con `clave` y Procesar decía `clave.bat` desde el paso
    17; en la nativa (y en `local`) todo sigue igual;
  - la banda roja de la clave rechazada (paso 11) lo mismo: `consultas.bandas_urgentes` recibe el
    entorno del servidor y en `contenedor` nombra el fichero.
  `{invoiceFolder}` (`buzon\facturas`) entra en `SCRIPT_NAMES` como nombre propio, como los de
  los `.bat`: es como se llama en el disco.
- **La espera de una automática dice lo que la pantalla ofrece** (arreglo tras la revisión). La
  tarjeta decía «Het nakijken begint als je op Beginnen drukt» sin «Beginnen»; el origen salía dos
  veces (la línea y la nota); y junto a «Niet lezen» decía «Stoppen zet automatisch lezen op pauze
  tot morgen». Ahora la tarjeta dice que empieza sola (`card.startAutoNote`), la línea dice que
  cabe en los límites de la automática (`waiting.automatic`) y la nota, de dónde viene y quién
  firmó; `stopAuto` no nombra ningún botón («Automatisch lezen pauzeert dan tot morgen»), porque
  sale junto a «Niet lezen» (esperando) y junto a «Lezen stoppen» (leyendo).
- **«Alle 50 tonen» con 61 esperando** (arreglo tras la revisión). Las listas de la tarjeta del
  buzón (y «Apart gezet») tienen su total: si la API no las trae todas (50), el botón dice «50 van
  61 tonen» y, abierta, «en nog 11», como la cola (`foldedText`).
- **Las reglas que solo sostenía el componente, al modelo, con su prueba** (arreglo tras la
  revisión: quitar la regla de la nativa en Systeem o en Inicio, enseñar «Beginnen» a una
  automática o la etiqueta «niet gecontroleerd» pasaba todas las pruebas). `systemRowsOf` (las
  filas de Systeem y el buzón que se enseña, sin nada en la nativa), `waitingCount` (0 en la
  nativa) e `introButtonHidden` (el botón de la intro de Procesar) deciden lo que antes decía el
  componente, y `mailbox-card.test.ts` pinta un correo con `react-dom/server` (como
  `status-pill.test.ts`) y exige las dos etiquetas y el texto de fuera como texto. **Para el paso
  16**: `correo.spec.ts` corre sobre la base de las e2e (`entorno` `local`); el caso de la nativa
  necesita un `page.route` que devuelva `entorno: 'nativo'` en `/api/v2/correo` (Systeem con sus
  cuatro filas, Inicio sin la fila, Procesar sin la línea), como hizo la revisión a mano.


## Paso 15 · Docker

Lo de §1.3 (`docker-compose.yml`, el `Dockerfile`), §4.1-§4.6 (el ciclo, las tareas, la pausa y
el cerrojo), §2.4 y §2.6 (el certificado y la primera vez) para la variante Docker. Por la
decisión del dueño, nada de esto va en la nativa: ni `windows\ciclo.ps1`, ni `automatico`, ni la
pausa o el cerrojo en `windows\comun.ps1`, ni los códigos del correo allí
(`test_los_codigos_del_correo_son_los_de_la_cli_y_solo_de_docker` lo exige).

- **Las tareas, en la carpeta raíz del Programador de tareas** (`\`), no en `\BMS Finanzas\`:
  `automatico.ps1 -Instalar` corre sin elevar, con la cuenta que se queda con la sesión, y una
  cuenta estándar puede no poder crear una carpeta de tareas **[comprobar en Windows 11]**. Se
  llaman `BMS Finanzas - ciclo (Docker)` y `BMS Finanzas - bloquear (Docker)` (las dos con
  «(Docker)»). Con `-SinBloquear` no se pone la de bloquear la pantalla (quien use su propia
  cuenta y no el usuario aparte). Repetir `-Instalar` (otros `-Minutos`) para el bucle de antes
  con el cerrojo en la mano, para no cortar una lectura. La repetición del vigilante (15 min) se
  pone sin `-RepetitionDuration` (sin fin) y `ExecutionTimeLimit` como `"PT0S"` literal, que es
  lo que fija la prueba **[comprobar en Windows 11 que se registra así]**.
- **`Pausar-Automatico` no apaga la tarea en Docker** (§4.4 decía «deshabilita las tareas si
  puede»). La tarea solo arranca `ciclo.ps1 -Bucle`, que no hace nada con la pausa puesta; apagarla
  no añade nada y deja una trampa: `parar.bat` o `restaurar.bat` los abre el dueño con su cuenta,
  que no es la dueña de la tarea, y una tarea apagada por «bms» (`automatico.bat -Pausar`) que el
  dueño no puede volver a encender (`iniciar.bat`) se quedaría apagada y, tras el siguiente
  reinicio, nada arrancaría solo sin que nadie lo viera. `Reanudar-Automatico` sí la enciende si
  alguien la apagó y esa cuenta puede; si no, lo dice. `-Estado` dice si está apagada.
- **La pausa se dice a la app con el cerrojo en la mano y solo con la automatización puesta.**
  `Pausar-Automatico` escribe el fichero, toma el cerrojo (2 minutos) y solo entonces `ciclo
  latido --pausado`, y solo si la tarea está (si esa cuenta la ve) o el ciclo ya corrió aquí
  (`docker\estado\ciclo.json`): si no, un Docker sin automatización que pasa por `parar.bat`
  quedaba para siempre «en pausa» en la app (y con la banda de las 24 horas). Antes del cerrojo
  podía pisarlo el latido de un ciclo en marcha. Si no consigue el cerrojo (una lectura larga), la
  pausa se queda puesta y lo apunta el propio bucle en cuanto el cerrojo queda libre (una vez por
  pausa, también con el cerrojo: así no abre la base en medio de una restauración). El latido va
  siempre a la base de verdad (`BMS_BASE=bms` solo para esa orden).
- **`Reanudar-Automatico` no escribe en la base**: el bucle mira la pausa cada 30 segundos y, al
  quitarla, corre un ciclo enseguida, cuyo latido lo dice. Así `iniciar.bat` reanuda sin esperar a
  Docker. **`-SiLaPuseYo`** (nuevo): `restaurar.bat` y `correo-certificado.bat -Activar` solo
  reanudan si la pausa la pusieron ellos; una de antes (`automatico.bat -Pausar` para el
  mantenimiento) se respeta. `iniciar.bat` reanuda siempre, como dice §4.4.
- **La salida, antes del lector y del correo, con `docker compose up -d --wait`.** En Docker no
  hay comprobación de aislamiento (la hace la red), pero una salida que no arranca tiene que dar
  su motivo: la lectura se cierra con `salida` (y cuenta para la espera creciente de §5.2) y el
  correo apunta `correo registrar --fallo salida`. Sin esto, `compose run lector` fallaba sin
  decir por qué y la petición acababa `interrumpida`. Un `correo traer` que no dice cómo acabó
  (ni 0, ni 10, ni 11: su contenedor no arrancó o un fallo del programa) apunta `--fallo
  interno`. `correo registrar` corre siempre después (lo que dejó el paso 10).
- **El correo «configurado» es que estén los dos ficheros** (`correo_ajustes.json` y
  `correo_certificado.pem`): sin ellos `compose run correo` ni arranca (son sus secretos), así que
  `correo traer` no puede dejar `sin_configurar` en su `estado.json`. Con la carpeta
  `docker\secretos\correo` y alguno de los dos sin estar (la fase 1 de `correo-configurar`, o
  `correo-certificado -Borrar`), el ciclo apunta `--fallo sin_configurar`, que no escribe nada si
  el correo nunca llegó a la base (paso 10) y, si llegó, deja de enseñar el último estado bueno
  (lo que el paso 10 dejaba como «lo que cuesta»). Sin la carpeta, nada.
- **Con la consola en DATOS DE PRUEBA, el ciclo no lee** (el diseño no lo decía). `compose up
  salida` y `compose run lector` arrancan sus dependencias, y compose vuelve a crear la consola si
  su configuración cambió (`BMS_DB`): una lectura del ciclo pasaba la consola de `iniciar.bat
  -Demo` a la base de verdad en medio de una demostración. El ciclo mira la cabecera
  `X-BMS-Entorno: demo` de `127.0.0.1:8765/consola` antes de `lectura siguiente`; el correo se
  sigue trayendo y registrando (no toca la consola).
- **El disco libre es el menor de dos unidades**: la del proyecto y la de `%LOCALAPPDATA%`, donde
  Docker Desktop guarda por defecto su disco de WSL2 (que es donde crecen la base y los
  originales). §4.1 decía «la unidad de la instalación», que en Docker no es la de los datos.
- **El registro del ciclo no es una transcripción** (`Start-Transcript`, §4.6): en Windows
  PowerShell 5.1 no recoge lo que un programa escribe directamente en la consola, que es todo lo
  de `docker compose`. `Anotar` y `Compose-Anotado` (en `comun.ps1`) escriben cada línea de las
  dos salidas de cada orden, con su hora, en `docker\estado\registro\ciclo-AAAA-MM-DD.log` (30
  días, por el nombre). `Cerrar-Lectura` pasa por `Anotar` (lo mismo en pantalla para
  `leer-facturas`). Lo que dicen las órdenes no lleva secretos (pasos 8-10).
- **`ciclo.bat`** (nuevo): un ciclo a mano, a la vista, para probarlo en el mini PC; `ciclo.ps1`
  sin `-Bucle` es eso. El bucle pide `correo traer --comprobar` en su primera ronda (§2.3: «y el
  bucle de Docker, al empezar») hasta que una ronda acaba bien. Los cuatro `.bat` nuevos
  (`ciclo`, `automatico`, `correo-configurar`, `correo-certificado`) dejan la ventana abierta al
  acabar también si todo fue bien, como `comprobar.bat` de la nativa: lo que dicen (la nota y el
  `.cer` para el informático, el estado de lo automático) hay que leerlo; los de antes de Docker,
  solo si algo falla.
- **`iniciar.bat` rápido hace la pasada del día si el ciclo no la ha hecho hoy** (§4.4 decía «sin
  recalcular»): sin la automatización puesta, una consola que lleva días en marcha ya no tendría
  nunca su pasada del día, que antes hacía cada `iniciar.bat`. Se mira en `ciclo.json` (sin abrir
  la base) y no para nada. **Solo con el cerrojo libre, sin esperarlo** (§4.4 decía «sin
  cerrojo»: lo que no se quiere es que `iniciar.bat` espere): con un ciclo leyendo, la pasada la
  hace él, y dos transacciones largas a la vez en la base se pisarían (§10.2, `busy_timeout` de 5
  s). También dice si el ciclo no pasa desde hace más de 30 minutos (§4.5).
- **`leer-facturas.bat` y `copia.bat` esperan el cerrojo** (hasta 15 minutos, §4.4; la fila de §9
  no los nombraba); `copia.bat -Comprobar` no (solo lee la copia). **`correo-configurar.bat`
  también** para la comprobación y `correo registrar` (con una ronda en marcha, `correo
  comprobar` dice que está ocupado y sale con 1).
- **`correo-configurar.bat`**, lo que §2.6 no fijaba: la fase 2 empieza preguntando si ya hay los
  cuatro datos (si no, vuelve a enseñar el `.cer` y la nota); los guardados salen de
  `correo_ajustes.json` (en el equipo, sin Docker) entre corchetes y con Intro se dejan; lo que
  se escribe se mira antes (GUID, dirección, distintas y del mismo dominio, la fecha) y `correo
  ajustes fijar` lo vuelve a validar entero antes de guardar nada. Termina siempre con `correo
  registrar` (lo que dejó el paso 10), y dice `automatico.bat -Instalar` si las tareas no están.
- **`correo-certificado.bat`**: sin nada crea el siguiente (§2.4, paso 1); además `-Ver`,
  `-Descartar` (`borrar --siguiente`) y `-Borrar` (todos, §2.5), con «si». `-Activar` con un
  anterior aún sin comprobar (una activación cortada sin red) no vuelve a activar: solo repite la
  comprobación. Tras `volver` (Microsoft no acepta el nuevo) se comprueba otra vez con el de
  antes, para que la app no se quede en `credencial` hasta la ronda siguiente.
- **`automatico.ps1 -Instalar` avisa y pregunta, no se niega**: una cuenta que no es local
  (`Get-LocalUser` no la encuentra: de la empresa o de un dominio), una de Microsoft
  (`PrincipalSource`), una contraseña que caduca (con la orden de `Set-LocalUser`), una cuenta
  administradora o fuera de `docker-users` (`whoami /groups`, por el SID de Administradores y el
  nombre del grupo). Con todo dicho, quien la usa con su propia cuenta puede seguir. En Docker
  las tareas son «solo con la sesión iniciada»: no guardan contraseña, y un 0x8007052E solo
  saldría del inicio de sesión automático.
- **Las pruebas**: los pines de §7.2 en `test_entorno_local.py` (seis servicios, las redes y sus
  vecinos, las dos salidas, los secretos, los volúmenes, los perfiles, el `mkdir`/`chown`, los
  `-v` de `secretos`, `SCRIPTS`, la pausa, el cerrojo, las tareas, el ciclo, el correo, PowerShell
  5.1, y `pwsh` analiza cada `.ps1` de `docker/`); los pasos de la lectura del ciclo y sus motivos,
  en `test_lectura_lector.py`; y uno nuevo, **`tests/test_ciclo_docker.py`**: `ciclo.ps1` y
  `comun.ps1` de verdad con `pwsh` y un `docker` falso delante en el PATH (cada orden, en su orden,
  con cada código de salida; la pausa; el cerrojo de otro proceso; los DATOS DE PRUEBA; el bucle
  que no sale con todo fallando, la pausa una vez, la vuelta tras quitarla y `--comprobar` hasta
  la primera ronda buena). Las 24 mutaciones que se probaron (quitar la pausa de `parar`, el
  cerrojo exclusivo, `PT0S`, `IgnoreNew`, `registrar` al final, `--solo-app`, el `-v` solo de
  `secretos\correo`, el `chown` de un volumen, la red propia de la salida del correo…) hacen
  fallar alguna prueba. `test_app_local.py` (el lanzador espera a `/consola`) admite que
  `$consola_url` se defina antes de esperar: el camino rápido de `iniciar` también la usa.
  `test_entorno_docker.py` (con `BMS_PROBAR_DOCKER=1`) gana las filas de §7.2, coherentes con el
  `compose` nuevo, pero aquí no hay demonio: **va a la lista del mini PC**.
- **Lo que queda para el mini PC (§7.4, «Docker: solo»)**: `BMS_PROBAR_DOCKER=1 pytest
  tests/test_entorno_docker.py` (las redes del correo, los 200 a Microsoft por `proxy-correo`, y que
  el correo, uid 10001, escribe en sus volúmenes; también si un volumen que crea primero un
  montaje `:ro` toma el dueño de la imagen); `automatico.bat -Instalar` con una cuenta estándar
  (la carpeta raíz, el disparador al iniciar sesión con su retraso y su repetición, `PT0S`, la
  tarea de bloquear) y `-Estado`; el bucle oculto en Windows PowerShell 5.1 tras un arranque en
  frío de WSL2 y tres días; `docker compose up --wait` con el compose de Docker Desktop; el
  cerrojo entre la cuenta «bms» y la del dueño (los permisos de `docker\estado`, que pone el
  `proteger.bat` del paso 15b); las órdenes de Docker desde la cuenta del dueño con Docker Desktop
  en la sesión de «bms» (`docker-users`); `Get-PSDrive` y `%LOCALAPPDATA%`; los secretos del correo
  como ficheros montados que lee el usuario 10001; `iniciar.bat` sin `docker\secretos\correo` (los
  dos secretos del correo, declarados y sin sus ficheros, no tienen que impedir que arranquen la
  consola y las dos salidas, que no los usan); y `orden` escribiendo en `docker\secretos\correo`
  montado (renovar el certificado).
