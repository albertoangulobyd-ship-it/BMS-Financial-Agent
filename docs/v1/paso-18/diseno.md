# Diseño · paso 18: el correo de facturas, solo

**Microsoft 365 de solo lectura, un buzón dedicado, la lectura automática con tope y el mini PC
que funciona solo.**

Para quien lo construye. Escrito por `correo:disenar` el 23-11-2026 sobre `HEAD 76c3ae3` (rama
`claude/zapier-mcp-setup-rjn0q6`), sin tocar el repositorio. **Revisado** el 23 y el 24-11-2026
por `correo:sintetizar` tras tres críticas (seguridad, operación, viabilidad): cada hallazgo se
comprobó contra el código y las fuentes, y lo que se hizo con cada uno está en **§13 Revisión** (la
versión anterior queda en `scratchpad/correo/diseno-v1.md`). Cada afirmación sobre el código lleva su
`fichero:línea`, comprobada a mano contra el código (no copiada de los mapas). Lo de Microsoft sale de
la investigación (`docs/v1/paso-18/investigacion.md`, con las fuentes markdown de Learn en
`scratchpad/correo/docs-ms/`); lo que solo se puede confirmar contra un inquilino real va marcado
**[comprobar en vivo]**.

Las decisiones del dueño no se reabren: Microsoft 365, un buzón solo para facturas, **solo
lectura**, que funcione solo en el mini PC (Intel N150, 16 GB, Windows 11) y que el dueño solo revise
y apruebe. Las dos variantes (Docker y nativa) quedan cubiertas.

El principio no cambia: **el modelo extrae, el código determinista decide, nada mueve dinero sin una
persona.** Lo único que deja de pedir a una persona en el momento es **gastar dinero de la API en
leer**, y solo dentro de una autorización permanente que una persona firma en la app, con topes.


> Guardado en el repositorio el 24-11-2026 para que no se pierda si se recrea la máquina. Las rutas
> `scratchpad/…` son ficheros de trabajo de la sesión de diseño (críticas, pruebas, copias de las
> fuentes de Microsoft Learn); no están en el repositorio.

---

## 0. Resumen y decisiones

| # | Decisión | Por qué (corto) |
| --- | --- | --- |
| D1 | **Un componente nuevo, `correo`**, que solo trae: un papel más en la nativa (`runtime\correo\python.exe`), un servicio más en Docker. Tiene la credencial de Microsoft, sale solo a `login.microsoftonline.com:443` y `graph.microsoft.com:443`, **no abre la base** y **no llega** a `api.anthropic.com`. | `arquitectura.md:236-239`: el proveedor de correo lo alcanza la capa de acción, la extracción no sale a ninguna parte. El lector, que tiene la clave de la API, no puede ver Microsoft. |
| D2 | **Una salida propia para Microsoft.** Docker: un segundo contenedor `salida_correo` (misma imagen, mismo `bms-agent salida`, otra red interna `red_correo`). Nativa: la misma `salida` arrancada en **otra pasada**, con otra lista y otra credencial (`Arrancar-Salida-Correo`), nunca a la vez que la de la API. | La lista blanca es por proxy, no por cliente (`salida.py:623-637`, una sola `Proxy` por `servir`). Juntar las dos listas abriría Microsoft al lector y la API al correo. |
| D3 | **El correo deja los adjuntos en su propia bandeja** (nativa `datos\correo\entrada\`, Docker volumen `correo_entrada`), con nombres que genera él (`pdf/<sha256>.pdf`, `llegadas/<sha256(graph_id\|carpeta)>.json`). **Registra `orden`** (`bms-agent correo registrar`, sin red, actor de sistema `correo`), que valida y mete cada PDF en el almacén de originales con `origen='correo'` y **después lo borra de la bandeja** (acuse: la bandeja solo guarda lo que aún no se ha registrado). **El lector lee los PDF del correo del almacén** (`datos/documentos/…`), no de la bandeja. | El buzón de Docker es de solo lectura en todos los contenedores (`docker-compose.yml:106,124`); el registro previo conserva `mensaje_id` y la fecha de recepción, que después nadie puede añadir (`0001_almacen.sql:259-269`; `documentos.py:198-204`); `arquitectura.md:93-95` pide guardar los adjuntos inmutables con su hash y el id del mensaje. |
| D4 | **Microsoft:** buzón compartido sin licencia; app de Entra de un solo inquilino **sin ningún permiso de API**; **RBAC for Applications** con el rol `Application Mail.Read` y un ámbito de gestión que contiene solo ese buzón; **certificado** (la clave se genera en el mini PC y no sale de él). No se crean Application Access Policies. | Las AAP son legado ("Don't create new App Access Policies", `docs-ms/New-ApplicationAccessPolicy.md`); el consentimiento de Entra suma al de RBAC, así que Entra debe quedar vacío; Microsoft desaconseja secretos en producción (`docs-ms/entra_how-to-add-credentials.md:46`). |
| D5 | **Graph delta** sobre la Bandeja de entrada cada 5 minutos, `Prefer: IdType="ImmutableId"`; idempotencia por **(id inmutable, carpeta) + sha256 del adjunto**. "Correo no deseado": solo se apuntan sus metadatos, no se baja nada; si una persona lo pasa a la Bandeja ("No es correo no deseado"), esa llegada nueva sí se trae. | Solo lectura: la app no puede marcar ni mover; el estado vive en local. El id inmutable no cambia al mover (`docs-ms/concepts_outlook-immutable-id.md:30`): por eso la carpeta entra en la clave. |
| D6 | **Nunca el cuerpo**: no se piden `body`, `bodyPreview`, `uniqueBody`, cabeceras ni el MIME del mensaje, **ni se expanden los `itemAttachment`** (traerían el cuerpo del correo adjunto y adjuntos anidados hasta 30 niveles con su `contentBytes`, `docs-ms/api-reference_v1.0_api_attachment-get.md:20,383-395`). | Lo que no se trae no puede inyectar nada ni filtrar datos personales. |
| D7 | **XML (UBL), lo que no es PDF y los correos adjuntos como elemento**: se apuntan (nombre, tipo declarado, tamaño), **no se bajan ni se leen** en este paso; la app pide reenviar el PDF como adjunto normal. | Un UBL se leería con código determinista, sin modelo: es otro paso. El original sigue en el buzón. |
| D8 | **Lectura automática** solo con una **autorización permanente** que firma en la app una persona con el permiso `admin` (tabla nueva `lectura_automatica`): tope por día (por defecto **2,00 USD**), por mes (**25,00 USD**), facturas por ronda (**20**) y por factura (**0,50 USD**). Apagada hasta que alguien la encienda. Firma las aceptaciones el usuario de sistema nuevo **`automatico`**; `aprobada_via = 'automatica'`. Se **pausa sola** si una persona para una automática ("Stoppen": hasta mañana) o si llega un volumen anormal de correo (hasta que una persona lo mire). | `revision` 8B pedía el sí de una persona (`app-local.md:1484-1487`); la decisión nueva del dueño lo sustituye por un sí permanente, con nombre, versión y topes, auditable. |
| D9 | **Programador de tareas de Windows** con un `ciclo.ps1` por variante. Nativa: al arrancar el equipo y cada 5 min, "se ejecute o no la sesión" (con contraseña guardada: DPAPI la necesita), límite de 4 h por ejecución. Docker: al iniciar sesión, un bucle sin límite de tiempo con un vigilante cada 15 min (Docker Desktop necesita la sesión). En las dos, la cuenta recomendada es un **usuario local estándar aparte** con la contraseña sin caducidad (`instalacion-nativa.md` §12), y **todo script que para o cambia algo pausa antes la automatización**. | Ningún módulo puede lanzar procesos (`nativo.py:313-330`; `test_instalacion_nativa.py:1018-1038`): la programación vive fuera de Python. |
| D10 | HTTP con **`httpx2`** (ya fijado, usa `truststore`, ya probado con la credencial de la salida: `test_instalacion_nativa.py:891-910`); firma del certificado con **`cryptography`** (única dependencia nueva, con `cffi` y `pycparser`; en Windows `scripts/fijar_windows.py` aprende a elegir entre dos ruedas `abi3`, §9 paso 6). **Sin msal.** | msal trae `requests`, `PyJWT`, `urllib3`, `certifi`… (unos 8 paquetes) para unas 60 líneas. |
| D11 | **Contrato 2.6**: lectura nueva `GET /api/v2/correo`; clave nueva `automatica` en `GET /api/v2/lectura`; acciones nuevas `fijar_lectura_automatica`, `reanudar_lectura_automatica`, `excluir_de_lectura_automatica` y `marcar_correo_atendido`. | `consultas.py:1703-1718`: añadir claves sube el menor. |
| D12 | **Lo que la API no acepta no bloquea nada.** Un PDF del correo pesa como mucho **20 MiB** (en base64 ≈ 28 MB, bajo el límite de 32 MB por petición de la API, que además rechaza PDF de más de 600 páginas, o 100 en modelos de 200k); `lectura.estimar` cuenta **cada PDF por separado** y uno que la API rechaza queda "omitido" (y, en la automática, excluido con motivo `rechazado_api`) sin tumbar la cuenta de los demás. Un fallo de la API que no es del documento (clave rechazada, sin saldo, sobrecarga, sin red) **para la pasada sin excluir nada** y la termina `fallida` con su motivo. | Hoy un solo PDF que la API rechaza al contar cierra toda la petición (`lectura.py:530-551` sin captura por PDF; `cli.py:732-737`), y en una pasada todo error es "fallida" del documento (`extract.py:656-666`, `lectura.py:818-819`). |
| D13 | **Variante para el mini PC: Docker, recomendada** para el correo desatendido. La nativa sigue soportada y documentada, pero con el correo leyendo correo de desconocidos cada 5 min un fallo en el proceso `correo` vería la base y la clave de la API (mismo usuario) y podría sacarlas por `graph.microsoft.com` a otro inquilino (§1.5, §1.7). | En Docker el correo no tiene ni el volumen `datos` ni el secreto de la API; en la nativa solo lo separa que el código no lo hace. |

Lo que **no** cambia: el prompt y el esquema (`prompts.py`, `extract.build_request` en `extract.py:164-182`,
sin herramientas), el IBAN solo del maestro, ningún pago, aprobación de factura, BTW ni factura creada
sola, nada sale por correo, la app sin red (`connect-src 'self'`), ningún módulo lanza procesos, la
auditoría solo de escritura.

---

## 1. Componentes y aislamiento

### 1.1 Las piezas

| Pieza | Qué hace | Red | Base de datos | Secreto que ve | Escribe en |
| --- | --- | --- | --- | --- | --- |
| **correo** (nuevo) | `correo traer` (una ronda) y `correo comprobar` (alcance del permiso) | Solo su proxy (`proxy-correo` en Docker; `127.0.0.1:3128` con la credencial de la pasada de correo en la nativa), y por él solo `login.microsoftonline.com:443` y `graph.microsoft.com:443` | **No.** Docker: no tiene el volumen `datos`. Nativa: no la abre (mismo usuario de Windows: ver §1.5) | La clave privada del certificado de Microsoft | Su bandeja (`entrada/`) y su estado (`estado/`) |
| **salida_correo** (nuevo, Docker) / **pasada de correo de `salida`** (nativa) | Proxy CONNECT con la lista `login.microsoftonline.com:443`, `graph.microsoft.com:443` | Fuera, solo 443 | No | Ninguno (nativa: la credencial de la pasada) | Su registro `salida-correo.log` |
| **orden** | Nuevo: `correo registrar` (y el acuse: borra de la bandeja lo registrado), `ciclo latido`, `lectura siguiente`, `lectura tomar --automatica`, `lectura autorizar`, `correo certificado crear\|activar\|volver` (local, sin red) | Ninguna (`network_mode: none`, `docker-compose.yml:126`; regla de bloqueo en la nativa) | Sí | Ninguno (en Docker, solo para `correo certificado …`, la carpeta `docker\secretos\correo\` montada para esa orden) | La base, `datos/documentos` y, para borrar, la bandeja del correo |
| **lector** | Igual que hoy; además lee del almacén de originales los PDF del correo | Solo la salida de la API (`docker-compose.yml:96-99,107-108`) | Sí | La clave de la API | La base, `out/` |
| **salida** | Igual que hoy: solo `api.anthropic.com:443` (`docker-compose.yml:57-66`; `windows/comun.ps1:269-271`) | Fuera, solo 443 | No | (nativa: credencial de la pasada de lectura) | `salida.log` |
| **consola** | Enseña el estado del correo y la autorización (lee la base) | Ninguna | Sí | Ninguno | La base (órdenes de personas) |

### 1.2 El camino de un adjunto

```
Proveedor ──correo──▶ facturen@<dominio> (Exchange Online, buzón compartido)
                               │  GET (solo lectura, RBAC: solo ese buzón)
                               ▼
 [correo] ──CONNECT──▶ [salida de correo: solo login + graph] ──▶ Microsoft
    │ escribe, con nombres que genera él:
    │   entrada/pdf/<sha256>.pdf                     (solo si empieza por %PDF- y pesa ≤ 20 MiB)
    │   entrada/llegadas/<sha256(id|carpeta)>.json   (metadatos del mensaje y de cada adjunto)
    │   estado/estado.json, estado/delta-bandeja.json, estado/intentos.json
    ▼
 [orden: correo registrar]  sin red; valida todo lo de la bandeja como no confiable
    │   documento (origen 'correo', ruta 'entrante', recibido_en = receivedDateTime del servidor,
    │              recibido_fuente 'correo', mensaje_id = internetMessageId) + original en datos/documentos
    │   mensaje_correo, adjunto_correo, estado_correo, ronda_correo   (actor: usuario de sistema 'correo')
    │   y borra de la bandeja el JSON y los PDF que ya están en la base (acuse)
    ▼
 [orden: lectura siguiente]  ¿hay facturas del correo sin leer, autorización encendida y presupuesto?
    ▼
 [orden: lectura tomar --automatica] → [salida de la API] → [lector: lectura contar] (gratis)
    → [orden: lectura autorizar] (la autorización permanente: tope = min(estimación alta, lo que queda
       hoy, lo que queda este mes))
    → [lector: lectura leer] (lee del almacén; para antes de la factura que no cabe)
    ▼
 La app: facturas nuevas en la cola de trabajo de Inicio; la persona revisa como siempre.
```

Nada de la bandeja llega al lector: el lector solo abre originales del almacén
(`almacen/documentos.py:69-74`, `AlmacenDocumentos.ruta`, que solo acepta `<sha[:2]>/<sha256>.<ext>`),
y solo los que `orden` ya registró tras comprobar su hash y su `%PDF-`.

### 1.3 Docker: lo que cambia en `docker/docker-compose.yml` y en `docker/Dockerfile`

Seis servicios (hoy cuatro, `test_entorno_local.py:43,58-62`) y dos redes más:

```yaml
  correo:
    <<: *endurecido
    profiles: ["correo"]            # solo con "docker compose run", como el lector
    command: ["correo", "traer",
              "--ajustes", "/run/secrets/correo_ajustes",
              "--certificado-fichero", "/run/secrets/correo_certificado",
              "--estado", "/correo/estado", "--entrada", "/correo/entrada"]
    environment:
      HTTPS_PROXY: http://proxy-correo:3128
      https_proxy: http://proxy-correo:3128
      NO_PROXY: ""
      no_proxy: ""
    secrets: [correo_ajustes, correo_certificado]
    volumes:
      - correo_estado:/correo/estado
      - correo_entrada:/correo/entrada
    networks: [red_correo]
    healthcheck: {disable: true}    # el de la imagen mira 127.0.0.1:8765 (Dockerfile:52-53)
    mem_limit: 256m
    depends_on:
      salida_correo: {condition: service_healthy}

  salida_correo:
    <<: *endurecido
    command: [salida, --escuchar, proxy-correo:3128,
              --permitir, login.microsoftonline.com:443,
              --permitir, graph.microsoft.com:443,
              --registro, /registro/salida-correo.log]
    volumes: [registro_correo:/registro]
    networks:
      red_correo: {aliases: [proxy-correo]}
      red_exterior_correo: {}       # su propia red con salida: no comparte red_exterior con
                                    # "salida", que escucha ahí la entrada a la consola
    healthcheck:
      test: ["CMD", "python", "-m", "bms_agent.cli", "salud", "proxy-correo:3128"]
      interval: 30s
      timeout: 5s
      start_period: 20s
      retries: 3
    mem_limit: 128m
    restart: unless-stopped

  orden:   # además de lo de hoy (docker-compose.yml:122-125):
    volumes:
      - datos:/datos
      - ../buzon:/buzon:ro
      - registro_salida:/registro:ro
      - correo_entrada:/correo/entrada          # escritura: registrar borra lo registrado (acuse)
      - correo_estado:/correo/estado:ro
      - registro_correo:/registro-correo:ro

networks:
  red_correo: {internal: true}
  red_exterior_correo: {}

volumes:
  correo_estado: {}
  correo_entrada: {}
  registro_correo: {}

secrets:
  correo_ajustes:     {file: ./secretos/correo/correo_ajustes.json}
  correo_certificado: {file: ./secretos/correo/correo_certificado.pem}
```

- **`docker/Dockerfile`**: los dos puntos de montaje nuevos tienen que existir en la imagen y ser de
  `bms`, o Docker crea los volúmenes de `root` y el usuario 10001 no puede escribir (hoy la imagen
  solo crea y da a `bms` `/datos /buzon /registro`, `Dockerfile:44-45`; `USER 10001:10001`, `:47`):
  `mkdir -p /datos /buzon /registro /correo/estado /correo/entrada && chown bms:bms /datos
  /registro /correo/estado /correo/entrada`. Un pin estático nuevo en `test_entorno_local.py`
  comprueba que **cada volumen con nombre que un servicio monta con escritura** tiene su punto de
  montaje en ese `mkdir` y en ese `chown` (aquí no hay demonio de Docker para probarlo de verdad).
- **`red_exterior_correo`**: `salida` escucha la entrada a la consola en su dirección de
  `red_exterior` (`--reenviar entrada:8765=consola:8765`, alias `entrada`, `docker-compose.yml:64,76`;
  `salida.direccion_de_escucha`, `salida.py:593-610`). Un `salida_correo` en esa misma red llegaría a
  la consola; con su propia red, no.
- **Los secretos del correo, en su propia carpeta**: `docker\secretos\correo\` (ya la ignora git:
  `.gitignore:26-27` ignora todo `docker/secretos/*` menos `LEEME.txt`; `.dockerignore` excluye
  `**/secretos/`). El contenedor `correo` solo ve los dos ficheros como secretos de Docker; la
  carpeta entera solo se monta en `orden` y solo para `correo certificado …` (§2.4). **Ningún** script
  monta `docker\secretos` (donde está `anthropic_api_key.txt`, `docker-compose.yml:142-144`) en
  ningún servicio: un pin nuevo de `test_entorno_local.py` lo exige (solo `lector` tiene el secreto
  `anthropic_api_key`; ningún `-v` de los `.ps1` apunta a `secretos` salvo `secretos\correo` en
  `orden`).
- Sin variables de entorno nuevas: las rutas van en `command`. `test_entorno_local.py:146-149` prohíbe
  nombres con `KEY|SECRET|PASSWORD` y `test_alcance_v1.py:240-242` fija el conjunto exacto de variables
  que lee el código: no cambia.
- `salida_correo` escucha solo en la dirección de `red_correo` (`salida.direccion_de_escucha`): el
  lector no lo ve, el correo no ve `proxy` (la salida de la API).
- `correo_ajustes.json` lleva el id del inquilino, el id de la app, la dirección del buzón (dato
  personal) y la huella y caducidad del certificado. `docker/secretos/LEEME.txt` se amplía.
- Todo lo demás de `x-endurecido` (`docker-compose.yml:26-37`) se aplica a los dos servicios nuevos
  (solo lectura, `cap_drop ALL`, `no-new-privileges`, `/tmp` `noexec` de 64 MiB). El correo **no
  descarga en `/tmp`**: escribe por trozos en `/correo/entrada/.parcial-<aleatorio>` y renombra.
- `iniciar.ps1`: `up -d consola salida salida_correo` (el test mira la subcadena
  `up -d consola salida`, `test_entorno_local.py:286`).
- **`depends_on` arranca servicios**: `compose run correo` levanta `salida_correo`, y
  `compose run lector` levanta `salida`, que depende de `consola` (`docker-compose.yml:86-88`). Con la
  automatización encendida, la consola vuelve a los pocos minutos de un `parar.bat`; por eso `parar`
  **pausa** la automatización (§4.4) y lo dice.

### 1.4 Nativa: el papel `correo`

- **Quinto papel.** `$Roles = @("consola", "lector", "salida", "orden", "correo")`
  (`windows/comun.ps1:19`) y `aislamiento.ROLES` (`aislamiento.py:56`), con `_DE["correo"] = "del
  correo"` (`aislamiento.py:79-80`). El instalador ya hace un Python por papel de esa lista
  (`instalar.ps1:420-429`) y `nativo.detectar` reconoce la carpeta (`nativo.py:190`).
- **Cortafuegos**: dos filas nuevas en `Reglas-Del-Cortafuegos` (`windows/comun.ps1:332-345`), iguales
  a las del lector: `correo - sin salida` (Outbound Block) y `correo - sin entrada` (Inbound Block).
  14 reglas. **No** una regla directa al 443: el cortafuegos de Windows no filtra por nombre y las IP
  de Microsoft 365 son compartidas; el correo sale solo por la salida, con su lista y su registro.
- **La pasada de correo de la salida**: función nueva `Arrancar-Salida-Correo([string]$Credencial,
  [int]$Segundos)` en `comun.ps1`, gemela de `Arrancar-Salida` (`comun.ps1:256-282`, que no se toca
  porque está fijada por `test_instalacion_nativa.py:1792-1798,1884-1891`), con
  `"--permitir", $Login, "--permitir", $Graph`, registro `datos\registro-salida\salida-correo.log`,
  `--clave-del-entorno` y `--max-segundos`. Constantes nuevas: `$Login =
  "login.microsoftonline.com:443"`, `$Graph = "graph.microsoft.com:443"`, `$VidaSalidaCorreo = 10 *
  60`. Usa el mismo puerto (`instalacion.json` sigue en versión 1, `nativo.py:203-211`): las dos
  pasadas nunca van a la vez (el cerrojo del ciclo, §4.4). Y como `Parar-Rol "salida"`
  (`comun.ps1:186-191`) mata cualquier salida por la ruta del programa, `Arrancar-Salida-Correo`
  **no arranca nada si `Procesos-De "lector"` no está vacío** (un lector que sobrevivió a un ciclo
  cortado): la ronda se salta con `ocupado` y el ciclo siguiente lo vuelve a intentar.
- **Certificados de Windows**: `Preparar-Certificados-Correo` hace el `HEAD` a los dos hosts de
  Microsoft desde PowerShell, como `Preparar-Certificados` con la API (`comun.ps1:291-305`): el proceso
  `correo` no tiene red y `truststore` usa la cadena de Windows.
- **La puerta**: `nativo.exigir_correo(instalacion)`, gemela de `exigir_lectura` (`nativo.py:264-282`):
  papel `correo`, `HTTPS_PROXY` del proxy de la pasada (`nativo.leer_proxy`, `nativo.py:235-255`) y
  las comprobaciones de aislamiento de `salida` y `correo` de esta misma pasada, de hace menos de 60
  minutos. Para eso `aislamiento.motivo_para_no_leer_de` (`aislamiento.py:492-514`, hoy fijo a
  `("salida", "lector")`) recibe `roles=`; se añade `motivo_para_no_traer(ruta, sesion)` con
  `roles=("salida", "correo")`. `exigir_correo_si_nativa()` no hace nada fuera de la nativa, como
  `exigir_lectura_si_nativa` (`nativo.py:285-289`).
- **El secreto**: `secretos.py` deja de ser solo de la clave de la API (`secretos.py:37-42`): una tabla
  de tipos con su entropía, su cabecera y su fichero. `clave-api` sigue igual (mismos nombres de
  función, mismo fichero `clave-api.dpapi`); `correo-certificado` usa la entropía
  `b"BMS Finanzas - certificado del correo - v1"`, el fichero `datos\secretos\correo-certificado.dpapi`
  y su comprobación de forma (PEM PKCS#8, `-----BEGIN PRIVATE KEY-----`, ≤ 8 KiB). Ámbito del usuario,
  `CRYPTPROTECT_UI_FORBIDDEN`, escritura atómica, sin el contenido en ningún mensaje (como hoy,
  `secretos.py:118-164`). `nativo.certificado_del_correo(instalacion)` lo descifra solo si el papel es
  `correo` (gemela de `clave_del_lector`, `nativo.py:292-303`). `secretos.py` sigue siendo el único
  módulo con `ctypes` (`test_instalacion_nativa.py:979,1036-1038`).
- **Ajustes** (no secretos, pero datos personales): `datos\correo\ajustes.json`.
- **La bandeja y el estado**: `datos\correo\entrada\` y `datos\correo\estado\` (bajo `datos`, que ya es
  escribible: `nativo.ESCRIBIBLES = ("datos", "buzon")`, `nativo.py:81`). No hace falta ninguna
  carpeta nueva en la raíz ni tocar `Poner-Permisos`.
- **Aislamiento probado**: ver §7.4.

### 1.5 Qué aísla cada variante (tabla para `instalacion-nativa.md` §11 y `entorno-local.md`)

Filas nuevas o cambiadas respecto a la tabla de hoy (`docs/instalacion-nativa.md:381-397`):

| | Docker | Nativa |
| --- | --- | --- |
| **El correo, solo a Microsoft** | Red interna `red_correo` con un solo vecino: `salida_correo`, cuya lista es `login.microsoftonline.com:443` y `graph.microsoft.com:443`; `salida_correo` sale por su propia red (`red_exterior_correo`) | Regla del cortafuegos (sin salida); la salida de su pasada, en `127.0.0.1`, con esa lista y una credencial nueva en cada ronda |
| **El correo no llega a la API de Anthropic** | No ve `proxy` (otra red); `salida_correo` contesta 403 a `api.anthropic.com` | La salida de su pasada contesta 403 a `api.anthropic.com`; la de la API no está encendida a la vez |
| **El lector no llega a Microsoft** | No ve `proxy-correo`; `salida` contesta 403 | `salida` de la lectura contesta 403 a los dos hosts de Microsoft (comprobado en cada pasada) |
| **La credencial de Microsoft** | Fichero PEM en `docker\secretos\correo\`, que solo ve el contenedor `correo` (y `orden` solo para `correo certificado …`) | Cifrada con DPAPI; la descifra cualquier programa de tu usuario, y el código solo lo hace en el papel `correo` |
| **El correo y la base de datos** | No tiene el volumen `datos`: no la ve | **La ve** (mismo usuario de Windows): no la abre porque su código no lo hace (prueba en §7) |
| **El correo y la clave de la API** | No ve el secreto `anthropic_api_key` ni la carpeta `docker\secretos` | **Puede descifrarla** (DPAPI, mismo usuario). El código no lo hace, pero un fallo en el proceso `correo` podría, y **podría sacarla, con la base entera, por `graph.microsoft.com`** a un inquilino de Microsoft del atacante: la salida deja pasar por `host:puerto`, no por inquilino (`salida.decidir`, `salida.py:182-215`). Para eso no le hace falta "el hueco" |
| **Lo que escribe el correo** | Solo sus dos volúmenes; `orden` los lee como no confiables y borra lo registrado | `datos\correo\` (y, por ser tu usuario, todo `datos` y `buzon`) |
| **Lo que lee el lector del correo** | Solo originales del almacén ya registrados por `orden` | Igual |
| **Un programa comprometido que arranca otro** | Sigue dentro de la caja | El hueco de siempre (`instalacion-nativa.md` §11, `:399-427`): el correo es un programa más que podría usarlo |
| **Otro programa usando una salida** | No la ve: está en otra red | La ve (127.0.0.1); sin la credencial de esa pasada recibe un no. **Ya no es verdad que "la salida solo está encendida al leer"** (`instalacion-nativa.md:386,423`): la del correo se enciende cada 5 minutos unos segundos y la de la API en cada lectura automática |
| **El registro de lo que sale** | `salida.log` y `salida-correo.log`, cada uno en su volumen | Los dos en `datos\registro-salida\` |
| **Funciona sin nadie** | Necesita una sesión de Windows abierta (Docker Desktop): inicio de sesión automático (§4.2) | Corre sin sesión (tarea con contraseña guardada) |

### 1.6 Quien manda un correo malicioso a `facturen@`

**Puede:**

1. Hacer que se baje y se guarde como evidencia un PDF de hasta 20 MiB por adjunto, hasta los topes
   por ronda y **por día** (§3.5: 150 PDF nuevos y 750 MiB al día; al llegar, el correo se retiene
   hasta el día siguiente y la app lo dice). Los repetidos no ocupan más (nombre por hash, almacén
   por hash). Lo que guarda en el almacén no se borra (es evidencia, `0001_almacen.sql:270`;
   ficheros 0444, `almacen/documentos.py:1-6`): el tope diario es lo que acota cuánto.
2. Hacer que se gaste dinero de la API **hasta el tope del día** (2,00 USD por defecto) y **del mes**
   (25,00 USD), leyendo PDF basura; pero con más de 200 correos en un día la lectura automática **se
   pausa** hasta que una persona lo mire (§5.2), y una persona puede sacar en bloque de la lectura
   automática lo que no es (§5.1). El techo duro sigue siendo el saldo prepagado sin recarga
   automática (`docs/costes.md:16-34`).
3. Poner en la cola de trabajo facturas falsas que esperan revisión: con un proveedor que no está en el
   maestro salen sus avisos (Z2/A0), el IBAN nunca sale del documento (`arquitectura.md:129`), nada se
   paga ni se aprueba solo.
4. Escribir lo que quiera en el remitente, el asunto y el nombre de un adjunto: se guardan como texto
   de terceros (`*_doc`), la app los pinta como texto (nunca `innerHTML`,
   `test_app_local.py:394-411`) y **siempre con la etiqueta "no comprobado"** (el remitente se puede
   falsificar: es el gancho del ataque del cambio de IBAN, `arquitectura.md` §1).
5. Intentar inyectar instrucciones en el PDF: el modelo no tiene herramientas, la regla 1 del prompt
   dice que el documento es dato (`prompts.py:18-24`) y lo inyectado acaba en `document_notes` y en el
   aviso Q3.
6. Mandar un PDF que la API no acepta (más de 600 páginas, cifrado, roto): se queda "omitido" y
   esperando a una persona, sin parar la lectura de los demás (D12, §5.3).
7. Intentar explotar un fallo del análisis de JSON o TLS del proceso `correo` (lo único de nuestro lado
   que procesa lo que él controla, junto con el hash y la comprobación `%PDF-`; nada analiza el PDF ni
   el MIME): ver "si el correo cayera".

**No puede:**

1. Hacer que se envíe, conteste, reenvíe, mueva, marque o borre nada: el rol es `Application
   Mail.Read` y el cliente de Graph solo hace `GET` (más el `POST` del token a
   `login.microsoftonline.com`), comprobado por un test (§7.2).
2. Leer otro buzón del inquilino: el ámbito de RBAC solo contiene `facturen@`, y `correo comprobar` lo
   prueba con un 403 en un buzón de control (§2.3).
3. Llevar al correo a otro host: el proxy solo deja los dos de Microsoft y el cliente comprueba
   esquema, host y puerto de cada `@odata.nextLink`/`@odata.deltaLink` antes de seguirlo (§3.1).
4. Elegir una ruta del disco: los nombres los genera el código (`<sha256>.pdf`, `<sha256>.json`); el
   nombre del adjunto nunca toca el sistema de ficheros.
5. Hacer que el modelo decida algo, cambie un IBAN, apruebe, pague o presente el IVA.
6. Cambiar los topes: solo una persona con `admin`, en la app, con su evento.
7. Colar instrucciones por el cuerpo del correo, ni por el de un correo adjunto: no se piden nunca
   (D6).
8. Hacer que se siga un enlace de OneDrive o SharePoint (`referenceAttachment`): se apunta y ya.
9. Parar el correo con un mensaje raro: cada mensaje tiene su propio límite de errores y de intentos
   (§3.2); al tercero se apunta como `error` y la ronda sigue con el siguiente.

**Si el proceso `correo` cayera** (código del atacante dentro; poco probable: solo analiza JSON de
Microsoft con el `json` de Python, calcula hashes y escribe ficheros con nombres suyos):

- **Docker**: podría escribir lo que quisiera en sus dos volúmenes (`orden` lo valida todo como no
  confiable, §3.8), leer el buzón de facturas (ya es su alcance) y sacar su token o su clave a **otro
  inquilino de Microsoft** por `graph.microsoft.com` (riesgo residual: una lista de hosts no distingue
  inquilinos, igual que la de la API no distingue cuentas). No llegaría a la base, a la clave de la API
  ni a la consola.
- **Nativa**: lo mismo **y además la base entera (IBAN, facturas, personas) y la clave de la API**,
  que podría descifrar con DPAPI y sacar por el mismo `graph.microsoft.com`, sin "el hueco" de
  `instalacion-nativa.md:399-427` (que también tendría). Por eso D13 recomienda Docker para el correo
  desatendido (§1.7).

### 1.7 Qué variante en el mini PC

**Recomendada: Docker.** Es la única en la que un fallo en el proceso que lee correo de desconocidos
cada 5 minutos no alcanza la base ni la clave de la API. Cuesta una sesión de Windows abierta (inicio
de sesión automático con la pantalla bloqueada, §4.2) y Docker Desktop.

**La nativa** sigue soportada (este paso la cubre entera) y funciona sin sesión. Si el dueño la elige
para el correo, lo hace sabiendo la fila "El correo y la clave de la API" de §1.5, que va tal cual a
`instalacion-nativa.md` §11. Lo que la cerraría es un **usuario de Windows aparte solo para el papel
`correo`** (su propio DPAPI, sin lectura en `datos` salvo `datos\correo`), que pide una tarea propia
con su contraseña, permisos nuevos en `Poner-Permisos` (`instalar.ps1:358-380`) y un cerrojo fuera de
`datos`: queda como **paso 19** (§8.1, "lo que deben saber los pasos siguientes"), no en este.

---

## 2. Microsoft 365

### 2.1 Lo que hace el dueño o su informático (una vez)

Va entero en un documento nuevo, `docs/correo-m365.md` (en castellano, con los marcadores
`facturen@<dominio>`, `<id-inquilino>`, nunca datos reales). Requisitos: el rol Exchange Administrator
(o Global Administrator) y el módulo `ExchangeOnlineManagement` v3, desde un PC de administración (no
desde el mini PC). **Tiempo del informático: unos 45 minutos de trabajo**, más la espera del paso 6
(30 minutos a 2 horas) y otros 10 minutos si luego hay que mirar algo; la guía lo dice al principio
para que el dueño lo pida con esa cifra.

1. **El buzón**: compartido, sin licencia, solo para facturas
   (`New-Mailbox -Shared -Name "Facturen" -PrimarySmtpAddress "facturen@<dominio>"`). Sin reglas de
   bandeja. Menos de 50 GB y sin archivo: no necesita licencia (investigación §2). La app no inicia
   sesión en él (solo lee por Graph).
2. **Acceso de una persona, no de la app**: el dueño (o quien revise el correo) recibe acceso completo
   al buzón para verlo en su Outlook, mirar "Correo no deseado" y, si una factura de verdad cayó ahí,
   pulsar **"No es correo no deseado"** (la app la trae en la ronda siguiente, §3.4):
   `Add-MailboxPermission -Identity "facturen@<dominio>" -User "<persona>@<dominio>" -AccessRights FullAccess -AutoMapping $true`.
   Es un permiso de una persona con su propia cuenta y su MFA; la app sigue siendo solo lectura.
3. **El buzón de control**: un segundo buzón compartido sin licencia que **no se usa para nada más**
   y no desaparece cuando alguien deja la empresa
   (`New-Mailbox -Shared -Name "BMS control" -PrimarySmtpAddress "bms-control@<dominio>"`). Sirve
   para que `correo comprobar` vea un 403 fuera del ámbito (§2.3). No debe estar en el ámbito.
4. **La parte pública del certificado**: la genera el mini PC (`correo-configurar.bat`, fase 1,
   §2.6) y deja `correo-certificado.cer`. Nunca se genera fuera ni se sube la clave privada.
5. **Entra → App registrations → New registration**: "Accounts in this organizational directory only",
   sin redirect URI. En *Certificates & secrets* se sube el `.cer`. En *API permissions* **se quita
   `User.Read` y no se añade ni se consiente nada**. Se anotan el *Directory (tenant) ID*, el
   *Application (client) ID* y, en **Enterprise applications** (no en App registrations), el
   *Object ID*. En *Enterprise applications → Permissions* no debe salir nada.
6. **Exchange Online** (`Connect-ExchangeOnline`):
   ```powershell
   New-ServicePrincipal -AppId "<client-id>" -ObjectId "<object-id-enterprise-app>" -DisplayName "BMS lector de facturas"
   New-ManagementScope -Name "BMS-buzon-facturas" -RecipientRestrictionFilter "PrimarySmtpAddress -eq 'facturen@<dominio>'"
   Get-Recipient -RecipientPreviewFilter (Get-ManagementScope "BMS-buzon-facturas").RecipientFilter   # uno, y solo ese
   New-ManagementRoleAssignment -Name "BMS-facturas-MailRead" -App "<object-id-enterprise-app>" `
       -Role "Application Mail.Read" -CustomResourceScope "BMS-buzon-facturas"
   Test-ServicePrincipalAuthorization -Identity "<client-id>" -Resource "facturen@<dominio>"      # InScope True
   Test-ServicePrincipalAuthorization -Identity "<client-id>" -Resource "bms-control@<dominio>"   # InScope False
   Test-ServicePrincipalAuthorization -Identity "<client-id>" | Format-Table                        # una fila: Application Mail.Read
   ```
   (sintaxis en `docs-ms/New-ServicePrincipal.md`, `New-ManagementScope.md:205-216`,
   `New-ManagementRoleAssignment.md:22-24,196-202`, `Test-ServicePrincipalAuthorization.md`).
   `Application Mail.ReadBasic` no sirve (sin adjuntos). **No** se crean Application Access Policies.
   Se esperan entre 30 minutos y 2 horas (caché de permisos de Exchange) antes de la fase 2 de
   `correo-configurar.bat` (§2.6).
7. **Le pasa al dueño** cuatro datos (no secretos, pero sí de la empresa): el id del inquilino, el id
   de la aplicación, la dirección del buzón de facturas y la del buzón de control.
8. Opcional, recomendado: *Set-MailboxJunkEmailConfiguration -Identity facturen -Enabled $false* para
   que nada legítimo se quede en "Correo no deseado" (la cuarentena de EOP para spam de alta confianza
   y phishing sigue) **[comprobar en vivo]**.

### 2.2 Certificado, no secreto

| | Certificado (elegido) | Secreto de cliente |
| --- | --- | --- |
| Lo que dice Microsoft | "the recommended credential type" (`entra_how-to-add-credentials.md:31`) | "should not be used in production" (`:46`); máximo 24 meses, mejor < 12 (`:52-53`) |
| Quién ve la credencial | Nadie: la clave privada se genera en el mini PC y solo sale la parte pública | Una persona la copia del portal y la pega (portapapeles, pantalla) |
| Lo que hay que añadir | `cryptography` (+ `cffi`, `pycparser`), fijados con hash en los dos `requirements` | Nada |
| Vida | La elegimos: 24 meses, con aviso a 30 días | ≤ 24 meses |

La aserción (sin msal, `docs-ms/entra_certificate-credentials.md`): cabecera `alg=PS256`, `typ=JWT`,
`x5t#S256` = base64url(SHA-256 del DER del certificado); claims `aud =
https://login.microsoftonline.com/<inquilino>/oauth2/v2.0/token`, `iss = sub = <client-id>`, `jti` =
UUID nuevo, `nbf = iat = ahora`, `exp = ahora + 5 min`; firma RSA-PSS con SHA-256, MGF1 SHA-256 y sal
de 32 bytes. Se manda como `client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer`
con `scope=https://graph.microsoft.com/.default` y `grant_type=client_credentials`. RSA de 3072 bits.

El token (60-90 min) **vive solo en memoria** de una ronda: se pide uno por ronda (≈ 288 al día,
muy por debajo de cualquier límite). No se guarda nunca en disco: un token guardado sería un secreto
más que proteger.

### 2.3 Cómo comprueba la app que solo puede leer ese buzón

`bms-agent correo comprobar` (papel/servicio `correo`, por su salida). Lo corre `correo-configurar`
al final de su fase 2; después, `correo traer` la repite sola **si la última tiene más de 24 horas**
o **si la ronda anterior terminó en `credencial`, `permiso`, `alcance` o `control_no_existe`** (y el
bucle de Docker, al empezar). Si falla, el correo **no trae nada** (falla cerrado) hasta que vuelva a
pasar, y la app lo dice (§6).

| # | Prueba | Bien si | Si no |
| --- | --- | --- | --- |
| 1 | Pedir el token con la aserción | 200 | `credencial` (400/401 `invalid_client`) o `reloj` (`AADSTS700024`) |
| 2 | Mirar el token (solo la carga útil; viene por TLS del emisor): `tid` = inquilino de los ajustes, `appid` = client id, `aud` = Graph, **`roles` ausente o vacío** | Sin `roles`: ningún permiso de Entra, que valdría para todos los buzones (investigación §1) | `alcance` |
| 3 | `GET /v1.0/users/<buzón>/mailFolders/inbox?$select=id` | 200 | `permiso` (403) |
| 4 | El mismo `GET` contra el **buzón de control** (`bms-control@`, §2.1 paso 3) | **403** | 200: `alcance` (puede leer más que su buzón). 404: `control_no_existe` (el buzón de control ya no existe: se fija otro con `correo ajustes fijar --buzon-control`; no es un fallo de seguridad pero sin la prueba no se trae nada) **[comprobar en vivo qué devuelve Graph para un buzón inexistente fuera del ámbito]**. Otro: `interno` |
| 5 | `GET /v1.0/users?$top=1&$select=id` | 403 (sin permisos de directorio) | `alcance` |

No se prueban escrituras: el cliente no sabe hacer otra cosa que `GET` (y el `POST` del token), y
probarlas pondría un `POST` a Graph en el código. Que el rol es de solo lectura lo dice su definición y
`Test-ServicePrincipalAuthorization` (§2.1, paso 6); que Entra no da nada más lo prueba el punto 2.
Que con cero permisos de Entra el token se emite igual sin `roles` lo confirman blogs, no Learn
**[comprobar en vivo]**: si no se emitiera, el diseño no cambia, solo el texto de ayuda.

El resultado va a `estado.json` (`alcance: {comprobado_en, bien, motivo_codigo}`) y de ahí a la app.

### 2.4 Dónde vive la credencial, cómo se renueva y cuándo avisa

| | Docker | Nativa |
| --- | --- | --- |
| Clave privada | `docker\secretos\correo\correo_certificado.pem` (texto, como la clave de la API hoy, `docker-compose.yml:142-144`, pero en su propia carpeta); secreto de Docker que solo ve `correo` | `datos\secretos\correo-certificado.dpapi` (DPAPI, usuario de la instalación); la descifra solo el papel `correo` |
| Parte pública | `docker\secretos\correo\correo_certificado.cer` (para subir a Entra) | `datos\correo\correo-certificado.cer` |
| La siguiente y la anterior (al renovar) | `docker\secretos\correo\correo_certificado-siguiente.pem/.cer` y `…-anterior.pem` | `datos\secretos\correo-certificado-siguiente.dpapi` y `…-anterior.dpapi` (+ sus `.cer` en `datos\correo\`) |
| Ajustes | `docker\secretos\correo\correo_ajustes.json` | `datos\correo\ajustes.json` |
| Las órdenes locales (`crear`, `activar`, `volver`, `borrar`, `ajustes fijar`) | `docker compose run --rm -T -v "<repo>\docker\secretos\correo:/secretos-correo" orden correo certificado … --carpeta /secretos-correo`: `orden` no tiene red, el montaje es solo para esa orden (como `copia.ps1:24` monta el disco) y **solo esa subcarpeta**, nunca `docker\secretos` | `Orden-De "orden" @("correo", "certificado", …)`: la orden cifra con DPAPI del mismo usuario; el `cryptography` de `runtime\orden` no tiene red |

`ajustes.json` (versión 1): `inquilino` (GUID), `aplicacion` (GUID), `buzon`, `buzon_control`,
`desde` (fecha: lo anterior no se trae la primera vez; por defecto hoy menos 30 días),
`certificado: {huella_sha256, caduca_en}`, `siguiente: {huella_sha256, caduca_en} | null`,
`anterior: {huella_sha256, caduca_en} | null`, `limites: {pdf_dia, mib_dia}` (por defecto 150 y 750,
§3.5). Lo lee y valida `correo/ajustes.py`; nunca entra en `config/` (`test_alcance_v1.py:253-256`
prohíbe claves de credencial allí y la dirección es un dato personal).

**Renovar** (`correo-certificado.bat`, las dos variantes; todo local salvo la comprobación):

1. `correo certificado crear --siguiente`: genera la clave y el certificado nuevos en `…-siguiente`;
   los ajustes guardan su huella en `siguiente`. El script enseña la ruta del `.cer` y la nota para
   el informático.
2. El informático sube el `.cer` nuevo a la misma app de Entra (dos certificados válidos a la vez).
3. `correo-certificado.bat -Activar` (cuando el informático dice que está subido):
   - toma el cerrojo y **pausa la automatización** (§4.4);
   - `correo certificado activar` (local, sin red): actual → `…-anterior`, siguiente → actual, ajustes
     al día;
   - **comprueba con la red de verdad**: nativa, `Arrancar-Salida-Correo` → `Comprobar-Rol "salida"` y
     `Comprobar-Rol "correo"` → `correo comprobar`; Docker, `docker compose run --rm -T correo correo
     comprobar …` (el contenedor de siempre, que solo ve los dos ficheros actuales);
   - si pasa: `correo certificado borrar --anterior`; si da `credencial`: `correo certificado volver`
     (anterior → actual) y lo dice; si falla por otra cosa (sin red), deja las dos y lo dice: el
     siguiente `-Activar` repite la comprobación;
   - reanuda la automatización.
4. El informático quita el certificado viejo de Entra.

**Avisos**: `correo traer` copia `caduca_en` a `estado.json`. La app lo enseña en la tarjeta a 60 días
(ámbar) y con **banda del servidor desde 30 días** y caducado (§6.1): 30 días dan tiempo a pedir al
informático los 10 minutos del paso 2. `comprobar.bat` (nativa) y `automatico.bat -Estado` (las dos)
dicen la fecha; la rutina del mes (§8, `uso-v1.md`) la mira.

### 2.5 Cortar el acceso en un minuto

En `docs/correo-m365.md`: quitar el certificado en Entra, o
`Remove-ManagementRoleAssignment BMS-facturas-MailRead`, o deshabilitar la app empresarial. En el
mini PC: `automatico.bat -Pausar` y borrar la clave (`correo certificado borrar`).

### 2.6 La primera vez: `correo-configurar.bat`, en dos fases

El certificado tiene que existir **antes** que la app de Entra, y los ids solo existen **después**:
por eso hay dos fases, con trabajo en otro PC y una espera entre ellas. El script mira qué hay y
sigue donde quedó.

**Fase 1** (`correo-configurar.bat`, sin nada configurado):

1. Si ya hay un certificado actual, **no lo rehace** (lo invalidaría en Entra y daría `credencial`):
   dice su huella y su caducidad, y que para uno nuevo está `correo-certificado.bat`.
2. Si no, `correo certificado crear`; enseña la ruta del `.cer` y una nota para el informático
   (en castellano y neerlandés, para copiar): "sube este `.cer` a una app de Entra nueva siguiendo
   `docs/correo-m365.md`; tardas unos 45 minutos y luego hay que esperar hasta 2 horas; pásame el id
   del inquilino, el de la aplicación y las dos direcciones".
3. Termina diciendo "cuando tengas los cuatro datos, vuelve a abrir `correo-configurar.bat`".

**Fase 2** (`correo-configurar.bat` con certificado y sin ajustes completos):

1. Pide, uno a uno, y valida antes de guardar nada: id del inquilino (GUID), id de la aplicación
   (GUID), dirección del buzón de facturas, dirección del buzón de control (dos direcciones de correo
   distintas, del mismo dominio, ≤ 320) y `desde` (fecha, por defecto hoy menos 30 días).
2. `correo ajustes fijar …` (local).
3. Pasada de correo y `correo comprobar` (como en el paso 3 de renovar).
4. Si sale `permiso` en las dos primeras horas: "es normal mientras Exchange reparte el permiso;
   vuelve a abrir `correo-configurar.bat` en media hora" (no cambia nada guardado). Si sale `alcance`
   o `credencial`: el texto de §6.4 y la sección de `docs/correo-m365.md` que lo arregla.
5. Si pasa: lo dice, y recuerda `automatico.bat -Instalar` si las tareas no están.

Se puede repetir sin miedo: la fase 2 vuelve a pedir los datos (enseñando los guardados) y nunca toca
el certificado.

---

## 3. Leer el buzón

### 3.1 Delta, no sondeo con `$filter`

Una ronda por ciclo (5 min). La primera vez, y tras perder el enlace:

```
GET https://graph.microsoft.com/v1.0/users/<buzón>/mailFolders/inbox/messages/delta
    ?changeType=created
    &$select=id,internetMessageId,receivedDateTime,hasAttachments,subject,from
    &$filter=receivedDateTime ge <desde o última buena − 3 días>
Prefer: odata.maxpagesize=50, IdType="ImmutableId"
```

Se siguen los `@odata.nextLink` hasta un `@odata.deltaLink`, que se guarda entero en
`estado/delta-bandeja.json` (escritura atómica). La ronda siguiente empieza en él (los parámetros solo
van en la primera petición: `docs-ms/concepts_delta-query-messages.md:20`). Lo mismo para
`mailFolders/junkemail` en `estado/delta-no-deseado.json`, **solo metadatos** (§3.3). Las entradas
`@removed` y los cambios de leído/no leído se ignoran.

- **Delta caducado** (410 con `Location`, o `syncStateNotFound` / `resyncRequired`): ronda de nuevo con
  `$filter=receivedDateTime ge <ultima_buena − 3 días>`; lo repetido lo descarta `registrar` por
  (id inmutable, carpeta). Queda `delta_reiniciado_en` en el estado.
- **Throttling** (429/503/504): se espera `Retry-After` si es ≤ 120 s; si es más, o sin cabecera tras 2
  reintentos (2 s y 8 s), la ronda termina con `limitado` y el ciclo siguiente sigue donde quedó. Una
  petición cada vez (Outlook: 4 concurrentes por buzón, `docs-ms/includes_throttling-outlook.md`).
- **Paginación y cortes**: se procesa página a página y, dentro de cada página, **mensaje a mensaje
  con su propio límite de errores** (§3.2 paso 6); tras cada página **completa** se guarda el
  `nextLink` como punto de reanudación. Si la ronda llega a un límite (§3.5), para tras la página y la
  siguiente ronda sigue ahí.
- **Cada respuesta JSON se lee por trozos con tope**: 4 MiB para una página de delta o una lista de
  adjuntos (con `$select` y 50 por página son unos pocos KiB). Pasar el tope es un fallo de ese
  mensaje (o de la ronda, si es la página), nunca una lectura entera en memoria.
- **Cada URL que se sigue** se comprueba sin depender de la forma de su ruta, que Graph reescribe
  (`…/me/mailfolders('AQMk…')/messages/delta?$skiptoken=…`, `docs-ms/concepts_delta-query-messages.md:151`):
  esquema `https`, host exactamente `graph.microsoft.com`, puerto 443 (o ninguno), sin usuario ni
  contraseña en la URL, ruta que empieza por `/v1.0/` y acaba en `/messages/delta` (sin distinguir
  mayúsculas). Si no, la ronda falla con `interno` y no se sigue. Que no pueda leer otro buzón no lo
  da esta comprobación sino RBAC (§2.3).

¿Por qué no `$filter` cada vez? Sin estado en el servidor haría falta una ventana de solape grande y
volver a listar lo mismo cada 5 min; delta da exactamente lo nuevo y sobrevive a días sin conexión.

### 3.2 Una ronda (`correo traer`), paso a paso

1. **Cerrojo propio** `estado/traer.cerrojo`, tomado con un cerrojo del sistema que se suelta solo si
   el proceso muere (`fcntl.flock` en Linux/Docker, `msvcrt.locking` en Windows; nunca un "crear si no
   existe", que se quedaría tras un corte). Si está tomado: `ocupado` y fin (sin error en la app).
2. Ajustes válidos y certificado legible; si no, `sin_configurar` / `credencial` y fin.
3. **Tamaño de la bandeja**: si `entrada/` pasa de 2 GiB (lo que aún no ha registrado `orden`, que
   borra lo registrado), `disco` y fin. El espacio libre del disco no lo mide el correo sino el ciclo
   (§4.1): en Docker el correo vería el disco virtual de WSL2, no el `C:` de verdad.
4. **Tope diario** (`limites` de los ajustes, §3.5): si hoy ya se bajaron 150 PDF nuevos o 750 MiB,
   la ronda no pide nada a Graph, deja `retenido_hasta` (mañana 00:00, Europe/Amsterdam) en el estado y
   termina **bien** (no es un error: la app dice "retenido hasta mañana" y por qué).
5. Token (§2.2). 400/401 de `invalid_client` o certificado caducado: `credencial`; `AADSTS700024`:
   `reloj`.
6. Si toca (la última comprobación tiene más de 24 h, o la ronda anterior acabó en `credencial`,
   `permiso`, `alcance` o `control_no_existe`, o se pasa `--comprobar`), `correo comprobar`; si falla,
   su código y fin.
7. **Pendientes** (`estado/pendientes.json`): adjuntos que fallaron por red o por Graph en rondas
   anteriores se vuelven a pedir por su id, **durante 24 horas** (como mucho una vez cada 30 minutos);
   pasado eso, `error`.
8. Delta de la bandeja (§3.1). **Por cada mensaje nuevo**, dentro de su propio `try` (un error de ese
   mensaje no para la ronda):
   - antes de tocarlo, suma 1 a su contador en `estado/intentos.json` (escritura atómica, clave
     `sha256(graph_id|carpeta)`); si ya tenía 3 (tres rondas que murieron o fallaron con él, también
     por memoria o un corte), escribe su `llegadas/…json` con cada adjunto `error` ("no se ha podido
     procesar") y sigue con el siguiente;
   - sin adjuntos: solo su `llegadas/<sha256(graph_id|carpeta)>.json`;
   - con adjuntos: `GET …/messages/{id}/attachments?$select=id,name,contentType,size,isInline`
     (`@odata.type` viene siempre; sin `contentBytes` gracias al `$select`, investigación §3
     **[comprobar en vivo]**; si viniera, el tope de 4 MiB lo para) y cada adjunto según §3.3;
   - al terminar bien, borra su contador.
9. Delta de "Correo no deseado": solo `llegadas/…json` con `carpeta: "no_deseado"` y cada adjunto como
   `no_deseado` (sin bajar nada).
10. Limpieza: borra de `entrada/` lo que tiene más de 45 días (huérfanos: `orden` borra lo que
    registra, §3.8) y de `intentos.json` las claves de más de 7 días.
11. `estado/estado.json` (atómico): ronda, resultado, código de error, contadores (también los del
    día: `hoy {fecha, pdf, bytes, mensajes}`), `ultima_buena`, caducidad del certificado, alcance,
    `delta_reiniciado_en`, `retenido_hasta`, `aviso_volumen`.

El proceso no abre la base, no importa `anthropic`, no lee variables de entorno propias (las rutas
llegan por argumentos o desde `nativo.Instalacion`), y su salida por pantalla nunca lleva el token, la
aserción, la cabecera `Authorization` ni `contentBytes`. Los errores de `httpx2` se resumen sin la
consulta de la URL (los `$deltatoken` y `$skiptoken` no salen en el registro).

### 3.3 Qué se hace con cada adjunto

Constante única `correo.MAX_PDF = 20 MiB` (20 971 520 bytes), que usan `traer` y `registrar`: en
base64 son ≈ 27,96 MB y la petición entera de la API (prompt y esquema incluidos) queda bajo su
límite de 32 MB (skill `claude-api`, "Document & File Input": 32 MB por petición, 600 páginas; 100 en
modelos de 200k de contexto). Las páginas no se pueden mirar sin analizar el PDF, y no se analiza:
lo que pase de páginas lo rechaza la API y queda "omitido" (§5.3).

| Tipo (`@odata.type`) / caso | Se hace | `resultado` en `adjunto_correo` |
| --- | --- | --- |
| `fileAttachment`, `isInline` | Se cuenta en el mensaje, no se apunta uno a uno | — |
| `fileAttachment` candidato a PDF: nombre acaba en `.pdf` (sin mayúsculas/minúsculas) **o** tipo declarado `application/pdf`, `application/x-pdf` o `application/octet-stream`; y `size` ≤ 20 MiB | `GET …/attachments/{aid}/$value` por trozos a `entrada/.parcial-<aleatorio>`, cortando si pasa de 20 MiB; si empieza por `%PDF-`: sha256, renombrar a `pdf/<sha256>.pdf` (si ya existe, se borra el parcial) | `documento` (tras registrar) |
| …que no empieza por `%PDF-` | Se borra el parcial | `no_es_pdf` |
| …con `size` > 20 MiB, o que pasa de 20 MiB al bajarlo | No se baja / se corta | `demasiado_grande` |
| `fileAttachment` XML (`.xml`, `application/xml`, `text/xml`) | No se baja (D7) | `xml` |
| `fileAttachment` `message/rfc822`, `.eml`, `.msg` | No se baja (no se analiza MIME) | `reenvio` |
| Cualquier otro `fileAttachment` (imagen, Word, Excel, ZIP…) | No se baja | `no_pdf` |
| `itemAttachment` (un correo reenviado "como adjunto" desde Outlook) | **No se abre** (D6): ni `$expand` ni `$value`. La app pide reenviar el PDF como adjunto normal | `reenvio` |
| `referenceAttachment` (enlace de OneDrive/SharePoint) | No se sigue | `enlace` |
| Cualquier adjunto de un mensaje de "Correo no deseado" | No se baja | `no_deseado` |
| Error de red o de Graph al bajar uno | La ronda sigue con los demás. El delta ya no volverá a dar ese mensaje, así que el correo lo apunta en `estado/pendientes.json` (id del mensaje y del adjunto) y lo vuelve a pedir por su id durante 24 horas (paso 7). Su `llegadas/…json` no se escribe hasta que todos sus adjuntos tienen un resultado final | `error` si sigue fallando a las 24 h |
| PDF con la marca de los datos de prueba (lo detecta `registrar`, `almacen/__init__.py:163-175`) | No entra en la base de verdad | `de_prueba` |

Un correo reenviado normal ("RV:"/"FW:" con los adjuntos) es un mensaje más: sus adjuntos son
`fileAttachment` y se tratan igual; el remitente es quien reenvía. Eso cubre al dueño reenviando
facturas desde su buzón personal.

### 3.4 Idempotencia

- **Mensaje**: la clave es **(id inmutable de Graph, carpeta)** (`Prefer: IdType="ImmutableId"`).
  El id inmutable no cambia al mover el mensaje de carpeta (`docs-ms/concepts_outlook-immutable-id.md:30`):
  si una persona pasa una factura de "Correo no deseado" a la Bandeja ("No es correo no deseado"), el
  delta de la bandeja la da como nueva y, con la carpeta en la clave, **es otra llegada** que sí se
  trae (`mensaje_correo` tiene `UNIQUE (graph_id, carpeta)`, §3.9). `internetMessageId` lo pone el
  remitente: se guarda como dato, no es la clave.
- **Adjunto**: `UNIQUE (mensaje_id, graph_adjunto_id)` y su sha256.
- **Documento**: `documento.sha256 UNIQUE` (`0001_almacen.sql:238`). El mismo PDF en dos correos, o en
  el correo y en `buzon\facturas`, es **un documento** y se paga **una vez** (`extract.Conocido`,
  `extract.py:461-540`). La segunda llegada queda en `adjunto_correo` con el mismo `documento_id`
  (por eso hace falta la tabla: el documento no se puede cambiar, `0001_almacen.sql:259-269`).
- **Bandeja**: `pdf/<sha256>.pdf` (mismo contenido, mismo fichero) y
  `llegadas/<sha256(graph_id|carpeta)>.json` (no se reescribe si ya está). `orden` los borra al
  registrarlos; si el delta se reinicia y vuelve a darlos, se escriben otra vez y `registrar` los
  descarta por las claves de arriba. Perder `correo_estado` solo obliga a reconstruir desde `desde`.

### 3.5 Inundaciones y spam

| Límite | Valor | Al llegar |
| --- | --- | --- |
| Mensajes por ronda | 100 | La ronda para tras la página; sigue en la siguiente |
| Adjuntos tratados por mensaje | 20 (los demás: `no_pdf` con "demasiados adjuntos" en el detalle) | — |
| Tamaño por adjunto | 20 MiB (`correo.MAX_PDF`) | `demasiado_grande` |
| Bytes bajados por ronda | 300 MiB | Para tras la página |
| **PDF nuevos al día** | 150 (ajustes `limites.pdf_dia`) | **Retenido hasta mañana**: no pide nada a Graph (el delta guarda la posición y nada se pierde); la app lo dice |
| **Bytes bajados al día** | 750 MiB (ajustes `limites.mib_dia`) | Igual |
| Bandeja en disco (lo no registrado aún) | 2 GiB | `disco`, no trae más (solo pasa si `orden` no registra) |
| Libre en el disco del equipo | 10 GiB (lo mide el ciclo, §4.1) | El ciclo no trae ni lee; banda en la app |
| Respuesta JSON de Graph | 4 MiB | Fallo de ese mensaje (contador de intentos) o de la ronda |
| Ficheros que mira `registrar` por pasada | 2 000 | Sigue en el ciclo siguiente |
| Mensajes en un día | > 200 | Sigue trayendo (dentro de los topes de arriba), el estado lleva `aviso_volumen` y **la lectura automática se pausa** hasta que una persona lo mire (§5.2) |

Con 150 PDF y 750 MiB al día, lo que un desconocido puede meter en el almacén de evidencia (que no se
borra) queda acotado a eso por día, y siempre visible; el volumen de BMS (unos cientos de facturas al
mes) queda muy por debajo. El dinero no lo protegen estos límites sino los topes de la lectura
automática (§5.2), que valen traiga lo que traiga el buzón. **El remitente no decide nada**: no hay
lista de remitentes conocidos (se descarta en §10) porque el remitente es falsificable y la regla es
que solo se enseña.

### 3.6 Qué se guarda y qué no

| Dato | ¿Se guarda? | Dónde | Para qué |
| --- | --- | --- | --- |
| Fecha de recepción del **servidor** (`receivedDateTime`) | Sí | `documento.recibido_en` (con `recibido_fuente='correo'`) y `mensaje_correo.recibido_en` | `factura.fecha_recepcion` (`ingesta.py:561`) y la llegada de F8 (`reglas/instantanea.py:523-527` toma la mínima, así que no la adelanta) |
| Id inmutable de Graph | Sí | `mensaje_correo.graph_id` | Idempotencia |
| `internetMessageId` | Sí, como dato | `documento.mensaje_id` (columna que ya existe, `0001_almacen.sql:248`) y `mensaje_correo.internet_message_id_doc` | Rastro |
| Remitente (dirección) | Sí, **no verificado** | `mensaje_correo.remitente_doc` (≤ 320) | Solo para enseñarlo, y siempre con la etiqueta "no comprobado" (§6.4). Nunca identifica a un proveedor, nunca va al prompt, nunca decide |
| Nombre del remitente | No | — | — |
| Asunto | Sí, recortado a 200, sin caracteres de control ni de dirección bidi | `mensaje_correo.asunto_doc` | Para que la persona reconozca el correo |
| Destinatarios, CC, cabeceras, MIME | No | — | — |
| **Cuerpo** (`body`, `bodyPreview`, `uniqueBody`), también el de un correo adjunto (`itemAttachment`) | **Nunca se pide** (los `itemAttachment` no se expanden, D6) | — | — |
| Nombre de cada adjunto | Sí, saneado (≤ 255, sin control ni bidi), **nunca como ruta** | `adjunto_correo.nombre_doc`, y en `documento.nombre_original` del primero que lo trae | Para enseñarlo |
| Tipo declarado y tamaño | Sí | `adjunto_correo` | Para enseñarlo y decidir si se baja |
| Bytes de un PDF | Sí | Almacén de originales (como cualquier original) | Evidencia, lectura |
| Bytes de lo que no es PDF | No | Se quedan en el buzón | — |
| Token, aserción, clave privada | Nunca en la base, en un registro ni en un mensaje | — | — |

AVG: el remitente y el asunto son datos personales de terceros; viven solo en la base del mini PC
(y en sus copias cifradas), nunca en el repositorio, en un registro de texto ni en el prompt.

### 3.7 Los ficheros de la bandeja (lo que escribe `correo`)

`entrada/llegadas/<sha256(graph_id|carpeta)>.json`, versión 1, ≤ 64 KiB, UTF-8:

```json
{"version": 1, "carpeta": "bandeja", "graph_id": "AAkALg…", "internet_message_id": "<…@…>",
 "recibido_en": "2026-11-23T08:14:02Z", "remitente": "facturen@proveedor.example",
 "asunto": "Factuur 2026-0412", "en_linea": 2, "traido_en": "2026-11-23T08:15:10Z",
 "adjuntos": [{"id": "AAMk…", "nombre": "factuur-0412.pdf", "tipo": "application/pdf",
               "bytes": 81234, "resultado": "pdf", "sha256": "9f2c…", "detalle": null}]}
```

`resultado` del lado del correo (cerrado): `pdf` (bajado), `no_es_pdf`, `demasiado_grande`, `xml`,
`reenvio`, `no_pdf`, `enlace`, `no_deseado`, `error` (no se pudo bajar en 24 h, o el mensaje falló
tres rondas). `estado/estado.json`, versión 1: `ronda {empezada, terminada, resultado, error_codigo,
mensajes, pdf_nuevos, bytes}`, `hoy {fecha, mensajes, pdf, bytes}`, `ultima_consulta`,
`ultima_buena`, `buzon`, `certificado {caduca_en}`, `alcance {comprobado_en, bien, motivo_codigo}`,
`delta_reiniciado_en`, `retenido_hasta`, `aviso_volumen`.

Códigos de error del correo (`error_codigo`, cerrados, los mismos en `estado.json`, en
`registrar --fallo` y en la API, §6.2): `sin_configurar`, `credencial`, `reloj`, `permiso` (403 en el
propio buzón), `alcance`, `control_no_existe`, `sin_conexion`, `limitado`, `aislamiento`, `salida`,
`disco`, `interno`. (`ocupado` no es un error: la ronda se salta y no se apunta.)

### 3.8 `correo registrar` (en `orden`): todo lo de la bandeja es no confiable

1. **Las carpetas**: solo tres fijas (`entrada/llegadas`, `entrada/pdf`, `estado`). Cada una se
   comprueba con `lstat` antes de abrirla: tiene que ser un directorio de verdad, no un enlace
   simbólico ni (en Windows) un punto de reanálisis (`st_file_attributes &
   FILE_ATTRIBUTE_REPARSE_POINT`). En Linux/Docker se abre con `O_DIRECTORY | O_NOFOLLOW` y todo lo de
   dentro se abre, se mira y se borra **relativo a ese descriptor** (`dir_fd`), así que cambiar la
   carpeta por un enlace a mitad no lleva a otra parte. En Windows (`os.supports_dir_fd` vacío) se
   vuelve a comprobar la carpeta antes de cada fichero; allí el correo comprometido ya tendría todo
   `datos` (§1.5), así que es defensa de más, no la barrera.
2. Solo nombres `^[0-9a-f]{64}\.json$` y `^[0-9a-f]{64}\.pdf$`; cualquier otro se ignora; ninguna
   ruta se forma con texto que no sea ese hexadecimal. **Como mucho 2 000 entradas por pasada** (las
   más antiguas primero): un millón de ficheros diminutos no la cuelgan; lo demás, en el ciclo
   siguiente.
3. Cada fichero: `lstat` primero; si no es un fichero normal (enlace simbólico, punto de reanálisis,
   dispositivo), se rechaza. Se abre con `O_NOFOLLOW` donde exista. ≤ 64 KiB el JSON, ≤ 20 MiB
   (`correo.MAX_PDF`) el PDF.
4. JSON estricto: versión 1, claves exactas, tipos exactos, longitudes máximas (`graph_id` ≤ 512 con
   `[A-Za-z0-9+/=_-]`, `internet_message_id` ≤ 998 ASCII imprimible, `remitente` ≤ 320, `asunto` ≤ 200,
   ≤ 50 adjuntos, `nombre` ≤ 255), `resultado` de la lista cerrada, `sha256` hexadecimal de 64; el
   nombre del fichero tiene que ser `sha256(graph_id|carpeta)`.
   `recibido_en`: ISO-8601 en UTC.
   - **Más de 5 minutos en el futuro** (el reloj de este equipo va atrasado): **no se registra
     todavía**; el fichero se queda, `estado_correo` lleva `reloj` y se vuelve a mirar en el ciclo
     siguiente. Así ninguna factura entra para siempre sin fecha por un reloj mal puesto (el documento
     no se puede corregir después, `0001_almacen.sql:259`).
   - Antes de 2000: el documento entra con `recibido_fuente='desconocido'` y `recibido_en` NULL (lo
     que exige el CHECK de `0001_almacen.sql:256`).
5. Cada PDF: los bytes tienen ese sha256 y empiezan por `%PDF-`; entonces
   `registrar_documento(origen='correo', ruta_declarada='entrante', recibido_en=…,
   recibido_fuente='correo', mensaje_id=internet_message_id, nombre_original=nombre saneado,
   actor=<correo>)` (`almacen/documentos.py:168-236`). Si el sha ya existía, vuelve `ya_estaba` y no
   cambia (`:198-204`): la llegada queda igual en `adjunto_correo`, **y el fichero de la bandeja ya
   no hace falta aunque falte** (otro mensaje con el mismo PDF pudo borrarlo). `DatosDePrueba`
   (`exigir_de_su_base`, `:195`) da `de_prueba`.
6. Un mensaje entero (su `mensaje_correo`, sus `adjunto_correo`, sus documentos y su evento
   `correo_mensaje_registrado`) va en una transacción. Uno malo no para los demás; queda contado en la
   ronda.
7. **Acuse**: tras la transacción, `registrar` borra de la bandeja (con `unlink` relativo al
   descriptor de la carpeta: borra la entrada, nunca sigue un enlace) el `llegadas/…json` del mensaje
   y cada `pdf/<sha>.pdf` cuyo sha ya está en `documento`. Lo rechazado (JSON malo, sha que no casa)
   se borra también y queda contado en la ronda con su motivo. Por eso en Docker `orden` monta
   `correo_entrada` con escritura (§1.3): es la dirección segura (de `orden` hacia el correo, y solo
   para quitar).
8. `estado.json` validado igual; se copia a `estado_correo` (caché) y, si la ronda trajo algo o el
   código de error cambió, una fila en `ronda_correo` con su evento.
9. La base es siempre la de verdad (`bms.sqlite3`): con la de prueba, `registrar` se niega.

### 3.9 Modelo de datos: migración `0019_correo.sql`

Una sola migración (las aplicadas no se editan, `0018_lectura_pedida.sql:3-4`). En este orden:

1. **Usuarios de sistema** `correo` y `automatico` (`INSERT` como en `0001_almacen.sql:60-64`;
   `USUARIOS_SISTEMA` en `almacen/__init__.py:49` pasa a seis, en el mismo orden;
   `test_almacen.py:150` lo compara).
2. **`lectura_automatica`** (evidencia, solo escritura): cada versión de la autorización.
   ```sql
   CREATE TABLE lectura_automatica (
       id                          INTEGER PRIMARY KEY,
       activa                      INTEGER NOT NULL CHECK (activa IN (0, 1)),
       tope_dia_usd_micro          INTEGER NOT NULL CHECK (tope_dia_usd_micro BETWEEN 1 AND 20000000),
       tope_mes_usd_micro          INTEGER NOT NULL CHECK (tope_mes_usd_micro BETWEEN tope_dia_usd_micro AND 200000000),
       max_documentos              INTEGER NOT NULL CHECK (max_documentos BETWEEN 1 AND 100),
       max_por_documento_usd_micro INTEGER NOT NULL CHECK (max_por_documento_usd_micro BETWEEN 1 AND tope_dia_usd_micro),
       fijada_por                  INTEGER NOT NULL REFERENCES usuario(id),
       fijada_en                   TEXT NOT NULL CHECK (datetime(fijada_en) IS NOT NULL),
       motivo                      TEXT
   ) STRICT;
   ```
   Disparadores: `lectura_automatica_personas_alta` (alta solo por una persona, `es_sistema = 0`, como
   `0018:91-96`), `lectura_automatica_sin_update` y `lectura_automatica_sin_delete`. La vigente es la de
   mayor `id`; sin ninguna, apagada. Los techos (20 USD/día, 200 USD/mes) acotan un error o un token de
   administrador robado.
3. **Rehacer `solicitud_lectura` y `pasada_lectura`** (SQLite no cambia un CHECK; precedente:
   `0004_excepciones_revision_prioridad.sql:27-43`). Cambios:
   - `origen IN ('app', 'lector', 'automatica')`;
   - `aprobada_via IN ('app', 'ventana', 'automatica')`;
   - `motivo_codigo` añade `limite_dia`, `limite_mes`, `excluidas`, `sin_autorizacion` (la
     automática) y `saldo`, `clave_rechazada`, `api_no_disponible` (fallos de la API que paran la
     pasada, §5.3; valen también para las de una persona);
   - columna nueva `autorizacion_id INTEGER REFERENCES lectura_automatica(id)` con
     `CHECK ((aprobada_via = 'automatica') = (autorizacion_id IS NOT NULL))`,
     `CHECK (aprobada_via IS NOT 'automatica' OR origen = 'automatica')`,
     `CHECK (origen IS NOT 'automatica' OR aprobada_via IS NULL OR aprobada_via = 'automatica')`;
   - el resto de CHECK, índices y disparadores, iguales; `solicitud_lectura_fija` (`0018:106-121`)
     congela también `autorizacion_id`.

   **El orden exacto** (probado en `scratchpad/correo/viabilidad/prueba_migracion.py` con SQLite
   3.45 y el `executescript("BEGIN IMMEDIATE;" + sql)` de `migrar.py:131`): con `PRAGMA foreign_keys
   = ON` (`almacen/__init__.py:204`) y filas de `pasada_lectura` que apuntan a `solicitud_lectura`,
   1. `PRAGMA defer_foreign_keys = ON;`
   2. `CREATE TABLE solicitud_lectura_nueva (…)` y `INSERT … SELECT` con sus `id`;
   3. `CREATE TABLE pasada_lectura_nueva (… solicitud_id … REFERENCES solicitud_lectura_nueva(id) …)`
      — **a la tabla nueva**, no a `solicitud_lectura`: apuntando al nombre final, el `DROP` de la
      vieja deja la violación diferida y el `COMMIT` falla con `FOREIGN KEY constraint failed`;
   4. `INSERT … SELECT` de `pasada_lectura` con sus `id`;
   5. `DROP TABLE pasada_lectura; DROP TABLE solicitud_lectura;`
   6. `ALTER TABLE solicitud_lectura_nueva RENAME TO solicitud_lectura;` (reescribe la referencia de
      `pasada_lectura_nueva`) y `ALTER TABLE pasada_lectura_nueva RENAME TO pasada_lectura;`
   7. los índices y los disparadores con **sus nombres exactos de 0018**
      (`solicitud_lectura_una_viva`, `solicitud_lectura_estado`, `solicitud_lectura_personas_alta`,
      `solicitud_lectura_personas`, `solicitud_lectura_fija`, `solicitud_lectura_terminada`,
      `solicitud_lectura_sin_delete`, `pasada_lectura_alta`, `pasada_lectura_avanza`,
      `pasada_lectura_sin_delete`).

   La prueba (§7) migra una base con filas en las dos y exige `PRAGMA foreign_key_check` vacío,
   igualdad fila a fila y los mismos nombres en `sqlite_master`. Los literales nuevos no casan con
   `ESTADOS_PROHIBIDOS` (`test_alcance_v1.py:85-87`): la excepción con nombre sigue siendo exactamente
   `{aprobada, esperando_aprobacion}` (`:92-94,121-127`).
4. **`mensaje_correo`** (evidencia, solo escritura): `id`, `graph_id TEXT NOT NULL`,
   `carpeta IN ('bandeja','no_deseado')`, **`UNIQUE (graph_id, carpeta)`** (§3.4: el mismo mensaje
   pasado de "no deseado" a la bandeja es otra llegada), `internet_message_id_doc`, `recibido_en`
   (NOT NULL), `remitente_doc`, `asunto_doc`, `adjuntos` (los no en línea), `en_linea`, `traido_en`,
   `registrado_en`, `registrado_por` (usuario).
5. **`adjunto_correo`** (evidencia): `id`, `mensaje_id → mensaje_correo`, `graph_adjunto_id`,
   `nombre_doc`, `tipo_declarado_doc`, `bytes`, `sha256`, `resultado IN ('documento', 'no_es_pdf',
   'demasiado_grande', 'xml', 'reenvio', 'no_pdf', 'enlace', 'no_deseado', 'de_prueba', 'error')`,
   `documento_id → documento`, `CHECK ((resultado = 'documento') = (documento_id IS NOT NULL))`,
   `UNIQUE (mensaje_id, graph_adjunto_id)`.
6. **`exclusion_automatica`** (evidencia): `documento_id UNIQUE`, `motivo_codigo IN ('grande',
   'fallo', 'rechazado_api', 'persona')`, `solicitud_id → solicitud_lectura` (NULL si la puso una
   persona), `por → usuario`, `en`. "Este documento no se lee solo: espera a una persona."
7. **`pausa_lectura_automatica`** (evidencia): cada pausa y cada reanudación de la lectura
   automática: `id`, `tipo IN ('pausa','reanuda')`, `motivo IN ('persona','volumen')` (NULL al
   reanudar), `solicitud_id` (la automática que una persona paró, si es eso), `por → usuario`
   (persona, o `automatico` para `volumen`), `en`, `hasta` (para `persona`: mañana 00:00 en
   Europe/Amsterdam; NULL para `volumen`). El estado es la última fila (§5.2).
8. **`correo_atendido`** (evidencia): `mensaje_id → mensaje_correo UNIQUE`, `por → usuario`
   (persona), `en`, `nota` (≤ 500). "Una persona ya miró este correo que el programa no podía leer."
9. **`ronda_correo`** (evidencia): solo las rondas que traen algo o cambian de error (no 288 filas al
   día): `empezada_en`, `terminada_en`, `resultado IN ('bien','fallo')`, `error_codigo`, `mensajes`,
   `documentos_nuevos`, `registrada_en`.
10. **`estado_correo`** (CACHÉ, una fila `CHECK (id = 1)`, se reescribe; spec §4): `buzon`,
    `ultima_consulta`, `ultima_buena`, `error_codigo`, `error_desde`, `alcance_comprobado_en`,
    `alcance_bien`, `credencial_caduca_en`, `delta_reiniciado_en`, `retenido_hasta`, `hoy_json`,
    `aviso_volumen`, `actualizado_en`.
11. **`estado_ciclo`** (CACHÉ, una fila): lo escribe `bms-agent ciclo latido` al principio de cada
    ciclo (§4.1): `visto_en`, `variante IN ('nativa','docker')`, `pausado` (0/1), `pausado_desde`,
    `disco_libre_bytes`, `actualizado_en`. Es el latido que enseña la app ("el ciclo automático no
    corre desde…") y el disco de verdad.

Las tablas de evidencia nuevas (`lectura_automatica`, `mensaje_correo`, `adjunto_correo`,
`exclusion_automatica`, `pausa_lectura_automatica`, `correo_atendido`, `ronda_correo`) llevan sus
disparadores `<tabla>_sin_update` y `<tabla>_sin_delete` con el mensaje "`<tabla>` es evidencia: no
se modifica / no se borra" (la prueba exige que case con `solo escritura|evidencia|en curso`,
`test_almacen.py:396`), entran en la tupla `EVIDENCIA` de `test_almacen.py:65-66` (la prueba de
`:406-410` falla si falta una) y `_poblar` les da al menos una fila cada una (también una persona con
`es_sistema = 0` para `lectura_automatica`), porque la de `:383-401` lo exige.

Ninguna es "controlada" (no pasan por `campos.py`): no hacen falta guardas de
`scripts/generar_guardas.py`. `docs/modelo-datos.md` (que aún dice 0001-0016) recoge 0017, 0018 y 0019.

---

## 4. Funcionar solo

### 4.1 El ciclo

Un script por variante, `windows/ciclo.ps1` y `docker/ciclo.ps1`, que lanza el Programador de tareas.
Hace, en este orden y siempre con la base de verdad (nunca `-Demo`):

0. **Pausa**: si existe `datos\automatico.pausa` (nativa) / `docker\estado\automatico.pausa`
   (Docker), termina sin hacer nada (código 0). La ponen y la quitan `Pausar-Automatico` y
   `Reanudar-Automatico` (§4.4); no hace falta el cerrojo para mirarla.
1. **Cerrojo** sin esperar: si otro ciclo, una lectura a mano, `comprobar`, una copia o una
   restauración lo tienen, termina sin hacer nada (código 0). Con el cerrojo en la mano **vuelve a
   mirar la pausa** (la pudo poner `Pausar-Automatico` entre el paso 0 y este).
2. **Latido y disco**: mide el espacio libre de la unidad de la instalación desde PowerShell
   (`Get-PSDrive`, en las dos variantes: en Docker el contenedor solo vería el disco virtual de WSL2)
   y lo apunta con `orden ciclo latido --disco-libre <bytes>` (§3.9, `estado_ciclo`), que también
   escribe `visto_en`; deja además `datos\ciclo.json` / `docker\estado\ciclo.json` con la hora (lo
   leen `automatico.bat -Estado`, `comprobar.bat` e `iniciar.bat` sin abrir la base). **Con menos de
   10 GiB libres** no trae ni lee: `correo registrar --fallo disco` y fin (banda en la app, §6.1).
3. **Correo** (si está configurado): nativa, si `Procesos-De "lector"` no está vacío, se salta
   (`ocupado`, §1.4); si no, la pasada de correo (§1.4), `correo traer`; Docker,
   `docker compose run --rm -T correo` (§1.3). Después `correo registrar` en `orden`, que registra y
   borra de la bandeja lo registrado. Si la salida o el aislamiento fallan, no se trae nada y
   `correo registrar --fallo salida|aislamiento` lo apunta para la app.
4. **La pasada del día** (`orden recalcular --diaria`), la primera vez cada día a partir de las 06:00
   (marca en `ciclo.json`). Hoy solo la hacen `iniciar` e `importar` (`windows/iniciar.ps1:38-40`).
5. **Lectura**: `orden lectura siguiente` dice qué toca:
   - `LECTURA_PEDIDA` (8): una persona pidió una lectura en la app → el camino de `leer-facturas` con
     `lectura tomar --solo-pedida` y `lectura esperar --solo-app` (solo vale el sí de la app; sin
     ventana; 15 minutos, como hoy). Es la decisión 8B (`app-local.md:1484-1487`) hecha: la tarea
     arranca el lector cuando hay una lectura pedida (sin "horario de oficina": una pedida solo existe
     si una persona está en la app y da el sí en 15 minutos; ver la desviación en §8.1).
   - `0`: lectura automática (§5.3).
   - `LECTURA_NADA` (3) o `LECTURA_LIMITE` (9): nada.
6. Suelta el cerrojo y cierra su registro.

Cada paso va en su propio `try`/`catch` de PowerShell: un fallo se apunta en el registro del ciclo y
el ciclo sigue con lo siguiente que no dependa de él (sin correo se puede leer lo que ya hay); el
`finally` de fuera suelta el cerrojo.

`windows/ciclo.ps1`, la parte de la lectura automática (la de la pedida es la de
`leer-facturas.ps1:46-124` con los dos cambios dichos):

```powershell
$tomada = Valor-De "orden" @("lectura", "tomar", "--automatica")
if ($tomada.Codigo -ne 0) { return }                    # ocupada o nada: el ciclo siguiente
$solicitud = ("" + ($tomada.Lineas | Select-Object -Last 1)).Trim()
$credencial = Nueva-Credencial
$salida = Arrancar-Salida $credencial $VidaSalidaLectura
if ($null -eq $salida) { Cerrar-Lectura $solicitud "salida"; return }
try {
    $env:BMS_PROXY_CLAVE = $credencial
    $codigoSalida = Comprobar-Rol "salida"
    Remove-Item Env:\BMS_PROXY_CLAVE -ErrorAction SilentlyContinue
    Preparar-Certificados | Out-Null
    $env:HTTPS_PROXY = "http://bms:" + $credencial + "@127.0.0.1:" + $Inst.PuertoSalida
    Remove-Item Env:\NO_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:\ANTHROPIC_BASE_URL -ErrorAction SilentlyContinue
    $codigoLector = Comprobar-Rol "lector"
    if ($codigoSalida -ne 0 -or $codigoLector -ne 0) {
        Cerrar-Lectura $solicitud "aislamiento"
    } elseif ((Orden-De "lector" @("lectura", "contar", $solicitud, $facturas, "--out", $out)) -eq 0) {
        if ((Orden-De "orden" @("lectura", "autorizar", $solicitud)) -eq 0) {
            Orden-De "lector" @("lectura", "leer", $solicitud, $facturas, "--out", $out) | Out-Null
        }
    }
} finally {
    Remove-Item Env:\HTTPS_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:\BMS_PROXY_CLAVE -ErrorAction SilentlyContinue
    Parar-Salida $salida
    Cerrar-Lectura $solicitud "interrumpida" -SiViva
}
```

En el script de verdad las dos ramas (pedida y automática) comparten una función
`Leer-Con-Salida([string]$Solicitud, [switch]$Automatica)` con la salida, el aislamiento, `contar` y
`leer` **una sola vez** cada uno; entre los dos, `autorizar` (automática) o `esperar --solo-app`
(pedida). El test de pasos lo exige igual que en `leer-facturas` (`test_lectura_lector.py:321-323`).

No hay `lectura esperar` en la rama automática; nunca se escribe "si" en ninguna entrada; nunca se
llama a `extract` (que lee sin petición, sin sí y sin tope, `cli.py:123-149`). En Docker, lo mismo con
`docker compose run --rm -T orden|lector …` como `docker/leer-facturas.ps1:39-94`, y el correo con
`docker compose run --rm -T correo` (su `command` por defecto es `correo traer`).

### 4.2 Arrancar con Windows

**La cuenta (las dos variantes).** Lo desatendido no puede colgar de la contraseña personal del
dueño: si la cambia, o caduca, las tareas con contraseña guardada dejan de arrancar
(`LastTaskResult` 0x8007052E, error de inicio de sesión) y el inicio de sesión automático de Docker
también, y con ellas la consola: nadie podría verlo en la app. Por eso la cuenta recomendada es la de
`instalacion-nativa.md` §12 (`:436-450`): un **usuario local estándar aparte** (p. ej. «bms»), con la
contraseña sin caducidad (`Set-LocalUser -Name bms -PasswordNeverExpires $true`, en un PowerShell de
administrador; `automatico.ps1 -Instalar` lo comprueba con `Get-LocalUser` y avisa si caduca). En la
nativa es el usuario de la instalación (el único con escritura en `datos`, `instalar.ps1:358-380`) y
el de las tareas; en Docker, el que inicia sesión solo y en el grupo `docker-users`. Una cuenta de
Microsoft o de Entra que entra solo con Windows Hello no sirve para "contraseña guardada":
`automatico.ps1` lo detecta y lo dice. El dueño sigue trabajando con su cuenta de siempre y abre la
app en `http://127.0.0.1:8765/app` (la consola escucha en el bucle local del equipo, con su token
personal).

**Nativa** (`windows/automatico.ps1 -Instalar`, con el usuario de la instalación; con otro se niega):

| Tarea (carpeta `\BMS Finanzas\`) | Disparadores | Acción | Ajustes |
| --- | --- | --- | --- |
| `BMS Finanzas - consola` | Al iniciar el equipo (retraso 1 min) y cada 15 min (vigilante) | `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "<Raiz>\windows\iniciar.ps1" -EnSegundoPlano` | Una instancia (`IgnoreNew`), límite 5 min |
| `BMS Finanzas - ciclo` | Al iniciar el equipo (retraso 2 min), repetir cada 5 min sin fin | `… -File "<Raiz>\windows\ciclo.ps1"` | `IgnoreNew`, **límite 4 h** (`$VidaSalidaLectura` = 3 h, `comun.ps1:33`, más los 15 min de `PLAZO_RESPUESTA`, `lectura.py:85`, y margen: una lectura pedida de un lote grande cabe entera), `StartWhenAvailable`, sin despertar el equipo, también con batería |

- "**Ejecutar tanto si el usuario inició sesión como si no**" con **contraseña guardada**
  (`LogonType Password`), nivel limitado. `S4U` ("no guardar la contraseña") **no**: sin la contraseña
  no hay clave maestra de DPAPI y ni la clave de la API ni el certificado se descifran
  (`secretos.py:15-18`) **[comprobar en Windows 11]**. La contraseña la pide `automatico.ps1` con
  `Read-Host -AsSecureString` y solo la pasa a `Register-ScheduledTask`; nunca a un fichero ni a la
  línea de órdenes.
- La acción vive en `<Raiz>\windows`, que es de solo lectura para el usuario (`instalar.ps1:358-380`):
  nadie con el usuario de cada día puede cambiar el script que corre solo.
- **`iniciar.ps1 -EnSegundoPlano`** (el vigilante): con la pausa puesta (§4.4), no hace nada. Si el
  puerto de la consola está abierto, mira **quién escucha**: `(Get-NetTCPConnection -LocalPort
  <puerto> -State Listen).OwningProcess` tiene que estar en `Procesos-De "consola"` (mismo usuario:
  se ve su ruta); si es así, no hace nada; si es **otro programa**, no arranca nada, lo apunta en el
  registro del ciclo y en `datos\ciclo.json` (`puerto_ocupado_por`), y `automatico -Estado`,
  `comprobar.bat` e `iniciar.bat` lo dicen como hoy dice `iniciar.ps1:25-29` (el navegador acabaría en
  ese programa y le daría el token). Si el puerto está libre, arranca la consola oculta, sin abrir Edge
  ni tocar la salida, con `serve --solo-errores` (flag nuevo: `log_message`, `serve.py:1155-1159`,
  solo escribe las peticiones con código ≥ 400; la app consulta cada 2 s en Procesar,
  `processing-workspace.tsx:99`, y la consola ahora vive semanas) y, antes de arrancarla (el fichero
  no está abierto), si `datos\consola.log` pasa de 10 MB lo renombra a `consola.log.1`.
- Si "Iniciar sesión como proceso por lotes" no se concede solo a un usuario estándar al registrar la
  tarea **[comprobar en Windows 11]**, `automatico.ps1` lo dice y la salida de reserva es la de Docker:
  inicio de sesión automático del usuario aparte y tarea "solo con sesión".
- `automatico.ps1 -Quitar | -Pausar | -Reanudar | -Estado`; `desinstalar.ps1` quita las tareas de la
  carpeta `\BMS Finanzas\` junto a `Quitar-Reglas` (`desinstalar.ps1:68-69`). **`-Estado`** dice, sin
  abrir la base: si las tareas existen y están activas, su `LastRunTime` y `LastTaskResult`
  (`Get-ScheduledTaskInfo`; 0x8007052E → "la contraseña guardada ya no vale: vuelve a ponerla con
  `automatico.bat -Instalar`"), la hora de `ciclo.json` (si tiene más de 30 minutos: "el ciclo
  automático no corre desde …"), si está en pausa y desde cuándo, el puerto ocupado si lo está, y la
  caducidad del certificado.

**Docker** (`docker/automatico.ps1 -Instalar`, sin elevar):

| Tarea | Disparadores | Acción | Ajustes |
| --- | --- | --- | --- |
| `BMS Finanzas - ciclo (Docker)` | Al iniciar sesión el usuario (retraso 2 min) y cada 15 min (vigilante) | `powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "<repo>\docker\ciclo.ps1" -Bucle` | `IgnoreNew`, **sin límite de tiempo** (`ExecutionTimeLimit` `PT0S`: el de `New-ScheduledTaskSettingsSet` por defecto es 72 h y cortaría el bucle cada tres días), `RestartCount 3`, `RestartInterval` 5 min |

- `-Bucle`: un solo PowerShell oculto que repite el ciclo cada 5 min (una tarea cada 5 min con sesión
  abierta haría parpadear una ventana cada vez). **Nunca sale por sí mismo**: no llama a `Fallar`
  (que hace `exit 1`, `docker/comun.ps1:14-19`) ni a `Comprobar-Docker` (que lo llama,
  `:21-30`); usa una función nueva `Docker-Listo([int]$Segundos)` que devuelve verdadero o falso y
  espera hasta 10 minutos a `docker info` (en un N150, WSL2 en frío puede tardar más que el retraso de
  2 minutos). Cada vuelta va en `try`/`catch`; con la pausa puesta, duerme y vuelve a mirar. El
  vigilante de cada 15 min solo lo arranca si murió (`IgnoreNew`).
- Docker Desktop solo arranca con la sesión (`docs/entorno-local.md:92-93`): para que funcione solo,
  el mini PC necesita **inicio de sesión automático del usuario aparte, con la pantalla bloqueada**:
  1. Configuración → Cuentas → Opciones de inicio de sesión: desactivar "Para mayor seguridad, permitir
     solo el inicio de sesión de Windows Hello…" (si no, `netplwiz` no enseña la casilla).
  2. `netplwiz` → elegir «bms» → quitar "Los usuarios deben escribir su nombre y contraseña" →
     escribir la contraseña (Windows la guarda como secreto LSA) **[comprobar en Windows 11]**.
  3. `docker/automatico.ps1 -Instalar` registra además `BMS Finanzas - bloquear` (al iniciar sesión
     «bms», sin retraso): `rundll32.exe user32.dll,LockWorkStation`.
  4. Docker Desktop: "Start Docker Desktop when you sign in" (`entorno-local.md:92-93`) y las
     actualizaciones **sin instalar solas** (se aceptan en el mantenimiento del mes con la
     automatización en pausa, §4.4): un diálogo de Docker Desktop detrás de la pantalla bloqueada
     pararía consola y ciclo sin que nadie lo vea.
- `consola`, `salida` y `salida_correo` vuelven solas con `restart: unless-stopped` si existían. Tras
  `parar.bat` o `restaurar.bat` (que hacen `docker compose down`) la automatización queda **en pausa**
  (§4.4) y `iniciar.bat` la reanuda.

### 4.3 Cada cuánto

Cada **5 minutos** (`automatico.ps1 -Minutos 5`, de 5 a 60). Una ronda sin nada nuevo son 2-4
peticiones a Graph; al día ≈ 288 rondas, lejísimos del límite de Outlook (10 000 por 10 min por app y
buzón, `docs-ms/includes_throttling-outlook.md`). La nativa paga además, en cada ronda, la
comprobación de aislamiento de `salida` y `correo` (sus sondas van a la vez; el plazo largo es el del
proxy, 12 s: `aislamiento.py:60-62`).

### 4.4 Una sola cosa a la vez, y la pausa

| Capa | Qué evita |
| --- | --- |
| Tarea con `IgnoreNew` | Dos ciclos solapados |
| **Cerrojo** `datos\ciclo.cerrojo` (nativa) / `docker\estado\ciclo.cerrojo` (Docker): fichero abierto en exclusiva (`[IO.File]::Open(..., FileShare.None)`) mientras dura; si el proceso muere, Windows lo suelta. Funciones `Tomar-Cerrojo [-Esperar <seg>]` y `Soltar-Cerrojo` en los dos `comun.ps1` | Que el ciclo y `leer-facturas`, `comprobar`, `copia`, `restaurar`, `iniciar` o `correo-certificado` se pisen. `leer-facturas`, `comprobar` y `copia` esperan hasta 15 min diciendo "el ciclo automático está trabajando"; el ciclo no espera; `iniciar` sigue la regla de abajo |
| **Pausa** `datos\automatico.pausa` / `docker\estado\automatico.pausa` | Que el ciclo o el vigilante de la consola arranquen algo mientras se para, se instala, se actualiza o se restaura |
| `estado/traer.cerrojo` del correo (cerrojo del sistema, §3.2) | Dos `correo traer` a la vez (también uno a mano) |
| Una sola `solicitud_lectura` viva (`0018:83-86`) | Dos lectores; la pedida de la app y la automática |

**`Pausar-Automatico` / `Reanudar-Automatico`** (en los dos `comun.ps1`):

- **Pausar**: escribe el fichero de pausa (con quién y cuándo); si el `runtime` está entero, `orden
  ciclo latido --pausado` (la app lo enseña); deshabilita las tareas de `\BMS Finanzas\` si puede
  (`Disable-ScheduledTask`: el dueño de la tarea o un administrador; si no, basta el fichero); y
  **toma el cerrojo esperando como mucho 2 minutos**: si un ciclo o una lectura lo tienen, dice "hay
  una lectura en marcha (míralo en Procesar): espera a que termine o párala, y vuelve a probar" y
  devuelve falso; quien llamó no toca nada.
- **Reanudar**: habilita las tareas y borra el fichero de pausa.

| Script | Antes | Después |
| --- | --- | --- |
| `parar.bat` (las dos) | Pausar (y lo dice: "la automatización queda en pausa; para volver, `iniciar.bat` o `automatico.bat -Reanudar`") | — (hoy `parar.ps1:9-12` para y dice "la próxima vez: iniciar.bat"; sin la pausa, el vigilante y el `depends_on` de Docker la volverían a arrancar en minutos) |
| `instalar.bat` (actualizar) | Pausar **antes de** `foreach ($rol in $Roles) { Parar-Rol $rol }` (`instalar.ps1:406`), que va antes de copiar los `runtime` (`:420-425`) | Reanudar, si había tareas |
| `desinstalar.bat` | Pausar antes de `Parar-Rol` (`desinstalar.ps1:68`) | Quita las tareas |
| `restaurar.bat` | Pausar antes de parar la consola (`restaurar.ps1:28-29`) | Reanudar |
| `correo-certificado.bat -Activar` | Pausar | Reanudar |
| Actualizar Docker Desktop (mantenimiento) | `automatico.bat -Pausar` | `automatico.bat -Reanudar` |
| `iniciar.bat` | — | Reanudar (si estaba en pausa) |

**`iniciar.bat`, una regla para las dos variantes** (el botón de cada día no puede quedarse colgado):

1. Si la consola ya contesta en `127.0.0.1:8765/consola` **con la base pedida** (cabecera
   `X-BMS-Entorno: demo` solo con `-Demo`, `serve.py:518-519`) **y es la nuestra** (nativa: quien
   escucha está en `Procesos-De "consola"`; Docker: `docker compose ps` da `consola` y `salida`
   corriendo): reanuda la automatización si estaba en pausa, abre Edge y termina. **Sin parar nada,
   sin `compose down`, sin `recalcular`, sin cerrojo.**
2. Si no (no contesta, otra base, `-Demo` que se rehace): toma el cerrojo esperando **como mucho 1
   minuto**; si no lo consigue, dice "el ciclo automático está leyendo: vuelve a abrir iniciar.bat en
   unos minutos (o mira Procesar si la app está abierta)" y termina sin tocar nada.
3. Con el cerrojo: lo de hoy (`windows/iniciar.ps1:21-29` y siguientes; `docker/iniciar.ps1:20` y
   siguientes), suelta el cerrojo, reanuda y abre Edge. `windows/iniciar.ps1:24` sigue sin parar la
   salida si hay un lector vivo; con el cerrojo en la mano no hay ciclo a la vez.

`Arrancar-Salida` para cualquier salida viva (`comun.ps1:262`) y `comprobar.ps1:50` arranca una sin
mirar: los dos quedan detrás del cerrojo (`comprobar` lo toma).

### 4.5 Suspender, reiniciar, actualizar, apagones, contraseña

- **Suspender/hibernar**: el mini PC es un servidor pequeño: `docs` pide "Suspender: nunca" con
  corriente (Configuración → Sistema → Energía). Si aun así se suspende, las tareas no lo despiertan
  (`WakeToRun` no) y con `StartWhenAvailable` corre un ciclo al volver.
- **Reinicios y Windows Update**: las tareas de la nativa arrancan solas al iniciar el equipo; en
  Docker, con el inicio de sesión automático. **Horas activas de Windows Update = el horario de
  oficina** (p. ej. 07:00-19:00; Configuración → Windows Update → Opciones avanzadas → Horas
  activas): son las horas en que Windows **no** reinicia, así que los reinicios caen de noche (acción
  del dueño). La lista de Windows (§7.4) prueba un reinicio de noche: vuelven las tareas y la consola.
- **Apagón**: en la BIOS/UEFI, "Restore on AC power loss: Power On" (acción del dueño).
- **Contraseña de Windows**: con el usuario aparte y `PasswordNeverExpires` no caduca. Si alguien la
  cambia: en la nativa, `automatico.bat -Instalar` otra vez (vuelve a pedirla); en Docker, `netplwiz`
  otra vez. Lo dicen `automatico.bat -Estado`, `comprobar.bat` e `iniciar.bat` (que leen
  `Get-ScheduledTaskInfo` y `ciclo.json` sin abrir la base) y, mientras la consola corra, la banda
  "el ciclo automático no corre desde…" (§6.1).
- **Ponerse al día**: el `deltaLink` trae todo lo llegado mientras estaba apagado (sin plazo fijo en
  Outlook; si caducó, el reinicio de §3.1 con 3 días de margen sobre la última buena y lo repetido
  descartado). Lo atrasado se lee en varias rondas: 20 facturas por ronda y los topes del día y del
  mes (§5.2).
- **Reloj**: la aserción vale 5 minutos; con el reloj mal, Entra la rechaza (`AADSTS700024`): error
  `reloj` con su texto (Windows sincroniza la hora por defecto). Con un reloj atrasado pocos minutos,
  `registrar` no mete documentos con fecha de recepción "en el futuro": espera (§3.8, paso 4).
- **Lectura cortada** por un reinicio: lo leído queda guardado (una transacción por documento,
  `extract.py:741-746`); la petición termina `interrumpida` en el `finally`, o `abandonada` a los 45
  minutos (`lectura.py:84-97`). Lo que faltaba se lee en la ronda siguiente.

### 4.6 Registros

| Qué | Nativa | Docker | Vida |
| --- | --- | --- | --- |
| Lo que dice cada ciclo (transcripción) | `datos\registro-ciclo\ciclo-AAAA-MM-DD.log` | `docker\estado\registro\ciclo-AAAA-MM-DD.log` (`.gitignore`: `/docker/estado/`) | 30 días (los borra el propio ciclo, por nombre) |
| La consola en segundo plano | `datos\consola.log` con `--solo-errores`; `consola.log.1` al pasar de 10 MB | el de Docker, rotado (`docker-compose.yml:35-37`) | acotado |
| Lo que intentó salir hacia Microsoft | `datos\registro-salida\salida-correo.log` | volumen `registro_correo`, `/registro/salida-correo.log` | 10 × 5 MB (`salida.py:85-90`) |
| Lo que intentó salir hacia la API | como hoy | como hoy | como hoy |
| Lo que pasó con el correo (para la app) | `estado_correo`, `ronda_correo`, `mensaje_correo`, `adjunto_correo` y sus eventos | igual | evidencia: no se borra |

Ningún registro lleva el token, la aserción, la clave, la credencial de la pasada, el cuerpo, el
asunto ni el remitente; `correo traer` dice "el buzón", no su dirección. `ver-salida.bat` enseña los
dos registros de la salida (`windows/ver-salida.ps1:15-18`; `docker/ver-salida.ps1:16-18` con
`--fichero /registro-correo/salida-correo.log`), y su texto de "Solo tiene que salir
api.anthropic.com" (`ver-salida.ps1:8-9`) pasa a decir los tres hosts y a quién corresponde cada uno.

---

## 5. Lectura automática

### 5.1 La autorización: quién la da y qué dice

- Una persona con el permiso **`admin`** (`dominio.py:331`) la enciende, cambia o apaga en la app
  (Instellingen → "Automatisch lezen", §6) con la acción nueva **`fijar_lectura_automatica`**
  (`POST /api/v2/acciones`, `servicios.ACCIONES`, `servicios.py:1677`), con `motivo`. Cada cambio es
  una fila nueva de `lectura_automatica` (§3.9) y un evento `lectura_automatica_fijada` con la persona
  en `usuario_id` y en `actor`. `activa` va como `ENTERO` 0/1 (servicios no tiene tipo booleano:
  `ENTERO, TEXTO, FECHA, VALOR, LISTA, OBJETO`, `servicios.py:84-89`); los topes, `ENTERO` con su rango.
- Mientras no haya ninguna fila, o la vigente tenga `activa = 0`, **no se lee nada solo**: el correo
  trae y registra, y las facturas esperan a que alguien pida una lectura.
- Valores por defecto que la app propone al encenderla: **2,00 USD al día**, **25,00 USD al mes**,
  **20 facturas por ronda**, **0,50 USD como máximo por factura**. Con 0,04-0,09 USD por factura
  (`docs/entorno-local.md:393`), el día cubre 22-50 facturas y el mes 280-600, muy por encima del
  volumen de BMS; una factura que la estimación pone por encima de 0,50 USD (un PDF enorme) no se
  lee sola.
- Tres acciones más, con el permiso de las lecturas (`importar_datos`, como `pedir_lectura`,
  `aprobar_lectura` y `cancelar_lectura`, `servicios.py:1903-1913`), porque solo frenan o quitan
  gasto:
  - **`reanudar_lectura_automatica`** (`motivo`): quita la pausa de "persona" o de "volumen" (§5.2);
    fila `reanuda` en `pausa_lectura_automatica` y su evento.
  - **`excluir_de_lectura_automatica`** (`documento_ids`: `LISTA` de hasta 200, `motivo`): esos
    documentos no se leen solos (`exclusion_automatica`, motivo `persona`). Para sacar en bloque una
    inundación de basura de la cola automática. Leerlos a mano desde Procesar sigue siendo posible.
  - **`marcar_correo_atendido`** (`mensaje_id`, `nota`): un correo que el programa no podía leer
    (§6.2, "esperan a una persona") ya lo miró una persona; fila en `correo_atendido`.
- Ninguna acción se llama `aprobar…` ni lleva "aprob", "programad" ni "enviar"
  (`test_alcance_v1.py:80-87`): la única excepción con nombre sigue siendo `aprobar_lectura`.

### 5.2 Los topes, las pausas y lo que pasa al llegar a ellos

`gastado(día)` y `gastado(mes)` = suma de `pasada_lectura.coste_usd_micro` (`0018:141`) de las
peticiones con `aprobada_via = 'automatica'` cuya pasada empezó ese día / ese mes, en hora de la
empresa (Europe/Amsterdam). Lo que aprueba una persona **no cuenta** contra estos topes: ya tuvo su sí.

`lectura siguiente` solo da `0` (leer) si se cumple todo esto; si no, dice por qué (`parada` en la
API, §6.2):

| Condición | Si no se cumple |
| --- | --- |
| La autorización está encendida | `LECTURA_NADA`; `parada: null`, `activa: false` |
| No hay pausa vigente: ni **`persona`** (alguien paró una automática hoy: dura hasta las 00:00 de mañana o hasta `reanudar_lectura_automatica`) ni **`volumen`** (más de 200 correos hoy: dura hasta que una persona la quite) | `LECTURA_LIMITE`; `parada: 'persona' \| 'volumen'` |
| No hay ninguna petición viva ni pedida | `LECTURA_NADA` |
| Ha pasado el **tiempo de espera tras un fallo técnico**: 1 h tras el primero y el doble tras cada uno seguido (2, 4, 8, 16 h, como mucho 24 h); vuelve a 1 h tras una automática buena. Cuentan `salida`, `aislamiento`, `clave`, `contar`, `sin_tarifa`, `saldo`, `clave_rechazada` y `api_no_disponible` | `LECTURA_LIMITE`; `parada: 'fallo'`, con `motivo_codigo`, `desde` y `proximo_intento` |
| Hay facturas **elegibles** | `LECTURA_NADA` |
| Queda del día **y** del mes al menos `max_por_documento` | `LECTURA_LIMITE`; `parada: 'limite_dia' \| 'limite_mes'` |

- **Elegibles**: documentos con al menos una llegada `documento` desde la **bandeja de entrada** (no
  desde "no deseado"), con original en el almacén, **sin extracción vigente**
  (`ingesta.vigentes_por_documento`, `ingesta.py:276`) y **sin `exclusion_automatica`**; los
  `max_documentos` más antiguos por fecha de llegada.
- **La pausa por volumen** la escribe `correo registrar` (usuario `automatico`) cuando `estado.json`
  trae `aviso_volumen` por primera vez ese día. Un desconocido que manda mil PDF no consume el tope de
  semanas delante de las facturas buenas: la automática para el primer día y una persona decide
  (excluir en bloque lo que no es y reanudar).
- `lectura autorizar`: tope = **mín(extremo alto de la estimación, lo que queda hoy, lo que queda este
  mes)**. Como cada factura no excluida cuesta como mucho `max_por_documento` en su extremo alto y lo
  que queda es al menos eso, la primera siempre cabe. Las que pasan de `max_por_documento` se excluyen
  (`exclusion_automatica`, `grande`) y no se pagan; las que la API no quiso contar (§5.3, paso 4) se
  excluyen con `rechazado_api`.
- **Al llegar al tope** durante la lectura: la de siempre, `_Seguimiento.cabe` para antes de la
  factura que no cabe y la pasada termina en `tope` (`lectura.py:773-793`). Lo que queda, sigue
  pendiente; `siguiente` da `LECTURA_LIMITE` hasta el día (o el mes) siguiente; la app lo dice con lo
  que queda ("Er is vandaag minder dan $0,50 over voor één factuur…", §6.4: con los valores por
  defecto, la automática para al pasar de 1,50 USD en el día, y eso tiene que leerse así) y la
  persona puede leerlo ya desde Procesar con su sí.

### 5.3 Una lectura automática, paso a paso

| # | Paso (dónde corre) | Estado de `solicitud_lectura` | Evento · actor |
| --- | --- | --- | --- |
| 1 | `lectura siguiente` (orden) | — | — |
| 2 | `lectura tomar --automatica` (orden): crea una con `origen='automatica'`, `pedida_por` NULL; si hay **cualquier** viva o pedida, `LECTURA_OCUPADA` y no toca la de la persona | `comprobando` | `lectura_pedida` · `automatico` |
| 3 | Salida de la API + aislamiento de `salida` y `lector` (nativa), como hoy | — | — |
| 4 | `lectura contar` (lector): lo de siempre (`lectura.py:555-595`), sobre las **elegibles**, pero **cada PDF por separado** (D12): uno que la API rechaza al contarlo (400 `invalid_request_error` o 413 `request_too_large`: demasiado grande, demasiadas páginas, cifrado) queda `omitido` con su motivo y los demás siguen; uno de más de `MAX_BYTES_API` ni se manda | `contando` → `esperando_aprobacion` (o `nada_que_leer`) | `lectura_contando`, `lectura_contada` · `extractor` |
| 5 | `lectura autorizar` (orden): comprueba origen, estado, plazo y autorización vigente; calcula el tope; apunta exclusiones (`grande`, `rechazado_api`) | `aprobada` con `aprobada_via='automatica'`, `aprobada_por` NULL, `autorizacion_id`, `tope_usd_micro`, `huella_aprobada = huella_estimacion`; o `nada_que_leer` con `limite_dia`, `limite_mes`, `excluidas` o `sin_autorizacion` | `lectura_aceptada` · `automatico`, `usuario_id` NULL, `datos`: `{via, autorizacion_id, fijada_por, tope_usd_micro, huella, gastado_dia, gastado_mes, tope_dia, tope_mes}`; `lectura_excluida` · `automatico` por cada exclusión |
| 6 | `lectura leer` (lector): lo de siempre (`lectura.py:960-1015`), leyendo del almacén, **con los fallos clasificados** (abajo) | `leyendo` → `hecha`; `fallida` con `saldo`, `clave_rechazada` o `api_no_disponible` si la API falló por algo que no es del documento; `cancelada` si una persona dijo "parar" | `lectura_empezada`, `extraccion_registrada`, `lectura_terminada` · `extractor` |
| 7 | Al terminar: una factura que falló **por el documento** en una automática **por segunda vez** (en dos automáticas distintas) → `exclusion_automatica` (`fallo`); a la primera, se reintenta en la ronda siguiente | — | `lectura_excluida` · `automatico` |

**Los fallos de la API, clasificados** (hoy todo error de un documento es "fallida" y la pasada sigue,
`extract.py:656-666`; `lectura.py:818-819`). En la rama `except` de `extract.py:661`, **antes** de
`avisar` (que llama a `informar` y la marcaría `fallida`, y `_anotar` nunca deshace un `fallida`,
`lectura.py:748-753`), se llama a `seguimiento.fallo(nombre, exc)` (método nuevo de `_Seguimiento`,
opcional en el protocolo `extract.Seguimiento`); si devuelve que es de la API, `extract` cuenta ese
documento en `sin_pagar` (no en `fallidas`) y sigue al siguiente, que `cabe` ya no deja pasar. Mira la
clase y el `status_code` del error del SDK (`anthropic`
1.13.0, `docker/requirements.txt:8`; clases y tipos de la skill `claude-api`, `shared/error-codes.md`).
Clasifica por `status_code` y por el cuerpo del error (`exc.body`: `error.type`,
`error.details.error_code`, el mensaje), leídos con `getattr`, no por la clase sola: el SDK fijado es
el 1.13.0 y el del entorno de aquí el 2.8.0 (§10), y la función es pura y se prueba con excepciones
hechas a mano (`clasificar_error`, §5.7):

| Error | Clase | Qué hace |
| --- | --- | --- |
| 401 `AuthenticationError`, 403 `PermissionDeniedError` | `clave_rechazada` | Para la pasada |
| 402 `billing_error` (sin saldo); 429 con `error.details.error_code = enforced_spend_limit_reached` (el límite de gasto de la cuenta); 400 cuyo mensaje dice que el saldo no llega ("credit balance") | `saldo` | Para la pasada |
| 429 `RateLimitError`, ≥ 500 (`InternalServerError`, 529 `overloaded_error`), `APIConnectionError`, `APITimeoutError` (ya tras los 2 reintentos del SDK) | `api_no_disponible` | Para la pasada |
| 400 / 413 del documento, `Rechazado` y `Cortado` (`extract.py:210-257`), salida que no valida | del documento | Sigue con el siguiente |
| **Dos fallos de documento seguidos con el mismo código, el mismo `error.type` y el mismo mensaje** (algo de la API que no se ha sabido clasificar) | `api_no_disponible` | Para la pasada, sin excluir ninguno de los dos |

"Para la pasada" = `_Seguimiento.parada = "fallida"` con su `motivo_codigo`; el documento que lo
provocó se anota `sin_leer` (no `fallida`: no es culpa suya) y `cabe` devuelve el motivo para los
demás, que quedan `sin_leer` sin pagar (como el tope y el "parar" de hoy, `lectura.py:777-789`).
`terminar` (`lectura.py:921-957`, que hoy solo sabe de `hecha` y `cancelada`) deja la pasada en
`fallida` y la petición `fallida` con ese `motivo_codigo`. **Nada se excluye** y nada se cuenta como
fallo del documento; la espera creciente de §5.2 evita reintentarlo cada 5 minutos. Lo gastado se
cuenta como hoy (un fallo sin uso cuenta su peor caso, `lectura.py:798-809`), pero al parar en el
primero el error ya no se lleva por delante el tope del día. Esto vale igual para las lecturas de una
persona: un saldo agotado deja de verse como veinte facturas "fallidas" con texto del SDK.

**"Stoppen" en una automática** (`cancelar_lectura`, como hoy) **la para y pausa la lectura
automática hasta mañana** (fila `pausa` con motivo `persona` y `hasta` = mañana 00:00 en
Europe/Amsterdam): sin eso, el ciclo siguiente volvería a empezar la misma lectura 5 minutos después.
Procesar lo dice y ofrece "Weer aanzetten" (`reanudar_lectura_automatica`). La persona **no** puede
darle el sí a una automática (`lectura.aprobar` rechaza `origen='automatica'` con `EstadoNoValido`, y
el CHECK de §3.9 tampoco lo deja), y la app no enseña "Empezar" para ellas.

Nadie escribe "sí": el sí es la autorización firmada, y el evento dice cuál y quién la firmó.

Una automática que se queda `esperando_aprobacion` sin señales (el ciclo murió entre 4 y 5) no se
"vuelve a contar" como una de persona (`lectura.py:366-369`): `tomar` la cierra `abandonada`.

### 5.4 La previsión de coste

No cambia en lo que calcula: `contar` cuenta la entrada exacta con `count_tokens` (gratis) y la
salida por la historia (`lectura.estimar`, `lectura.py:510-552`; `coste.py:196-268`); sin tarifa,
falla cerrado (`sin_tarifa`, `lectura.py:580-584`). Cambia en que **cuenta cada PDF por separado**
(paso 4) y en que un PDF de más de `documents.MAX_BYTES_API` (constante nueva, 20 MiB, la misma cifra
que `correo.MAX_PDF`) se omite sin mandarlo, también en `buzon\facturas`. Un fallo que no es del
documento al contar (401/403/402/429/5xx/sin red) sigue cerrando la petición, ahora con
`clave_rechazada`, `saldo` o `api_no_disponible` en vez de `contar`. La estimación, su huella y el
tope quedan en la petición y la app los enseña igual que en una lectura con persona.

### 5.5 Reintentos y fallos

| Fallo | Qué pasa |
| --- | --- |
| Graph (red, 5xx, 429) | La ronda termina con su código; la siguiente sigue donde quedó (§3.1). La app no lo pinta rojo hasta que dura más de 30 minutos (§6.2) |
| Certificado, permiso, alcance, buzón de control | No se trae nada hasta que `correo comprobar` vuelva a pasar; la app lo dice en rojo |
| Un mensaje que falla tres rondas | Se apunta como `error` y la ronda sigue (§3.2) |
| Un adjunto que no baja | Se reintenta 24 h; después, `error` y espera a una persona (§6.2) |
| Salida o aislamiento en la pasada de correo | No se trae nada esa ronda; `registrar --fallo` lo apunta |
| Salida, aislamiento, clave, contar, tarifa en la lectura; o la API sin saldo, con la clave rechazada o no disponible | La petición termina `fallida` con su motivo; nada se excluye; espera creciente (1 h → 24 h) antes de otra automática; la app lo enseña (`parada: 'fallo'`) y, para `saldo` y `clave_rechazada`, banda roja |
| Un PDF que la API no acepta (tamaño, páginas, cifrado) | `omitido` al contar; en la automática, excluido con `rechazado_api`: espera a una persona; los demás se leen |
| Una factura que falla al leerla sola por el documento | A la primera, se reintenta en la ronda siguiente; a la segunda, excluida (`fallo`): espera a una persona |
| Corte a mitad (reinicio, Ctrl+C, límite de la tarea) | Lo leído queda; la petición, `interrumpida`/`abandonada`; lo demás en la ronda siguiente |
| Base ocupada (`database is locked`) | La orden falla y el ciclo siguiente repite; hay que medirlo en el N150 (§10) |

### 5.6 Lo que no cambia

La lectura automática solo **gasta en leer**. Después, lo de siempre: tipar y pasar las reglas en una
transacción (`ingesta.py:1017-1021`), los avisos, la cola de trabajo de Inicio
(`home-panel.tsx:190`), revisar, aprobar pagos (dos personas por encima del umbral), el IBAN del
maestro, el IVA preparado y no presentado. Ninguna factura se aprueba, se paga ni se crea sola; el
modelo sigue sin herramientas; la petición de extracción es la misma (`extract.build_request`,
`extract.py:164-182`), sin remitente, asunto ni cuerpo.

### 5.7 Cambios de código para la lectura

- **`documents.py`**: constante `MAX_BYTES_API = 20 * 1024 * 1024` (la misma cifra que
  `correo.MAX_PDF`; un test lo exige). `load_pdf` (`documents.py:36-52`) no cambia: el tope lo aplica
  `estimar`, para que un PDF grande de `buzon\facturas` también quede "omitido" sin mandarlo.
- **`lectura.py`**:
  - `MOTIVOS` (`lectura.py:103`) + `limite_dia`, `limite_mes`, `excluidas`, `sin_autorizacion`,
    `saldo`, `clave_rechazada`, `api_no_disponible`.
  - **`clasificar_error(exc) -> "documento" | "saldo" | "clave_rechazada" | "api_no_disponible"`**,
    pura, con la tabla de §5.3 (status, `error.type`, `error.details.error_code`, mensaje; `getattr`
    para que valga con el SDK fijado y con el de aquí).
  - **`estimar`** (`lectura.py:510-552`), por PDF: si `doc.byte_size > MAX_BYTES_API`, `Contado(…,
    "omitido", detalle="demasiado grande para la API")` sin llamar a nada; la llamada a
    `coste.contar_entrada` (`lectura.py:547`) va en su propio `try`: si `clasificar_error` dice
    `documento`, `Contado(…, "omitido", detalle=…, rechazado_api=True)` y sigue; si dice otra cosa,
    lanza `ParadaApi(motivo)`. `cli._cmd_lectura_contar` (`cli.py:709-745`) la captura **antes** del
    `except Exception` de `:732` y cierra con ese motivo en vez de `contar`.
  - **`_Seguimiento.fallo(nombre, exc) -> bool`** (§5.3): con `clasificar_error`; si no es del
    documento, `self.parada = "fallida"`, `self.motivo = …`, `_anotar(nombre, "sin_leer")` y devuelve
    `True`; `informar` (`lectura.py:818-821`) no marca `fallida` un nombre parado así; `cabe`
    (`lectura.py:773-793`) devuelve el motivo para los siguientes.
  - **`terminar`** (`lectura.py:921-957`): además de `hecha` y `cancelada`, `fallida` con el motivo
    de la parada. Para una **automática**, por cada nombre `fallida` de esta pasada (los PDF del correo
    se leen como `<sha256>.pdf`) cuenta con `json_each(resultado_json)` (`lectura.py:740-746`) en
    cuántas pasadas de peticiones `origen='automatica'` quedó `fallida`; con **2**,
    `exclusion_automatica('fallo')`.
  - `tomar(conn, *, hay_pdf, automatica=False, solo_pedida=False)` (`lectura.py:354`): con
    `automatica`, crea la petición `origen='automatica'` y, si encuentra una automática colgada en
    `esperando_aprobacion`, la cierra `abandonada` (no la "vuelve a contar" como las de una persona,
    `lectura.py:366-369`).
  - `siguiente(conn, ahora) -> Siguiente(codigo, parada, motivo, desde, proximo_intento, hasta)`:
    la tabla de §5.2, en ese orden.
  - `autorizar(conn, solicitud_id) -> str`: §5.3 paso 5; `_evento(…, sistema="automatico")`.
  - `aprobar` (`lectura.py:280`) rechaza `origen='automatica'`; `cancelar` (`lectura.py:305`) en una
    automática escribe además la pausa `persona` (§5.2).
  - `empezar` pasa a `_Seguimiento` las excluidas (`cabe` devuelve "no se lee sola: espera a una
    persona"); `_resultado` añade `nombre_original`; `_pasada` añade `etiquetas`
    (`{"<sha256>.pdf": nombre original}`, solo para nombres que son un hash del almacén); por dentro
    los nombres siguen siendo los de los ficheros (únicos, y `_pasada`, `lectura.py:1054-1068`,
    compara `documento_actual` con ellos); `para_la_app` añade `autorizacion` y la clave
    `automatica`.
- **`lectura_automatica.py`** (nuevo, sin red): `vigente(conn)`, `fijar(conn, persona, *, activa,
  tope_dia_usd_micro, tope_mes_usd_micro, max_documentos, max_por_documento_usd_micro, motivo)`,
  `gastado(conn, ahora) -> (dia, mes)`, `elegibles(conn, autorizacion, limite)`,
  `pendientes_del_correo(conn)`, `excluir(conn, documento_ids, motivo, por, solicitud_id=None)`,
  `pausar(conn, motivo, por, solicitud_id=None, hasta=None)`, `reanudar(conn, por, motivo)`,
  `pausa_vigente(conn, ahora)`, `espera_tras_fallo(conn, ahora) -> (motivo, desde, proximo)`,
  `esperan_persona(conn, limite)` y `resumen(conn, ahora)` (lo de la app).
- **`extract.py`**: en la rama `except` de `:661`, `seguimiento.fallo(...)` antes de `avisar`; si
  devuelve `True`, `resultado.sin_pagar += 1` y `continue` (§5.3). `Seguimiento` (el protocolo) gana
  `fallo` como opcional (`getattr`), así la extracción sin petición (`extract`, `cli.py:123-149`) no
  cambia.
- **`cli.py`**: `lectura siguiente`, `lectura autorizar SOLICITUD`, `lectura tomar --automatica |
  --solo-pedida`, `lectura esperar --solo-app` (no abre el hilo de la ventana, `cli.py:757-782`),
  `ciclo latido [--disco-libre N] [--pausado | --reanudado] [--variante nativa|docker]`. `_pdfs_de`
  (`cli.py:647-648`) pasa a `_pdfs_a_leer(carpeta, almacen, solicitud)`: para una automática, las
  elegibles (rutas del almacén); para las demás, `buzon/facturas/*.pdf` más los del correo pendientes
  que no vengan solo de "no deseado" y no estén excluidos por una persona. `tomar` mira lo mismo para
  `hay_pdf`. Códigos nuevos `LECTURA_PEDIDA = 8`, `LECTURA_LIMITE = 9`, con su copia en
  `windows/comun.ps1:151-155` y `docker/comun.ps1:103-107` (los tests comparan,
  `test_lectura_lector.py:351-367`).
- **`correo` en la CLI**: `correo traer [--comprobar]`, `correo comprobar`, `correo registrar
  [--fallo CODIGO]`, `correo ver`, `correo certificado crear [--siguiente] | activar | volver | ver |
  borrar [--anterior]`, `correo ajustes fijar | ver`. Códigos `CORREO_SIN_CONFIGURAR = 10`,
  `CORREO_FALLO = 11` (el detalle va en `estado.json`), con su copia en los dos `comun.ps1`.
- **`serve`**: flag `--solo-errores` (§4.2): `log_message` (`serve.py:1155-1159`) solo escribe las
  peticiones con código ≥ 400.

---

## 6. Lo que ve el dueño en la app

### 6.1 Dónde

| Pantalla | Qué |
| --- | --- |
| **Instellingen → Systeem** (`settings-panel.tsx:23-33,136-160`) | Dos filas nuevas: **Facturenmailbox** (estado con `StatusPill`, grupo nuevo `correo`) y **Automatisch lezen** (Aan, Uit, Gepauzeerd, Gestopt na een fout, Dagplafond bereikt, Maandplafond bereikt). Cada una abre su tarjeta (como `IsolationCard`, `:264-283`) |
| Tarjeta **Facturenmailbox** | Estado, última consulta y última buena, el error con su texto, el alcance comprobado (fecha), la caducidad del certificado (ámbar a 60 días), hoy (correos, PDF nuevos, "retenido hasta" si toca), el latido del ciclo (`ciclo.visto_en`, en pausa o no, espacio libre), los últimos 10 correos y la lista **"Wacht op jou"** (abajo). El remitente y el asunto van **siempre** con la etiqueta "niet gecontroleerd" |
| Lista **"Wacht op jou"** (en la tarjeta) | Dos partes, cada una con su número total y hasta 50 filas: (1) **correos que el programa no ha podido leer** y que nadie ha marcado: los de la bandeja sin ningún PDF recibido, y los que tienen algún adjunto `no_deseado`, `enlace`, `xml`, `reenvio`, `demasiado_grande`, `no_es_pdf` o `error` (un `no_deseado` deja de salir cuando la misma llegada aparece después en la bandeja, §3.4); cada uno con su texto de qué hacer y el botón **"Afgehandeld"** (`marcar_correo_atendido`); (2) **facturas que no se leen solas** (excluidas: `grande`, `fallo`, `rechazado_api`, `persona`) y aún sin leer, con enlace a Documentos y a Procesar |
| Tarjeta **Automatisch lezen** | Encendida o no, quién la fijó y cuándo, los cuatro valores, gastado hoy y este mes y lo que queda hoy; si está parada, por qué y hasta cuándo (`parada`, §6.2), con **"Weer aanzetten"** para las pausas `persona` y `volumen`; la lista "Wacht op automatisch lezen" (las elegibles, las más antiguas primero) con casillas y **"Niet vanzelf lezen"** (`excluir_de_lectura_automatica`, hasta 200); con `admin`, el formulario (cuatro números, encender/apagar, motivo, "Opslaan"); sin `admin`, los valores solo para leer |
| **Procesar** (`processing-workspace.tsx`) | Una línea encima de la escena con el estado de la automática y lo gastado (`process.strip`) y, si está parada, el porqué. Una petición `origen='automatica'` dice "Automatisch, uit de facturenmailbox" y quién firmó la autorización, sin botón "Empezar"; "Stoppen" sigue y dice que la pausa dura hasta mañana |
| **Inicio** | Las facturas leídas entran en la cola como hoy (`home-panel.tsx:190`). En «Wat op iemand wacht» (`nl.ts:1254-1258`) una línea más, "{n} mails en facturen wachten op jou", que abre la tarjeta: lee `esperan_persona` de `GET /api/v2/correo` una vez al abrir Inicio (no en bucle) |
| **Banda del servidor** (roja, NL+EN, `app_local.py:205-215`) | Solo lo urgente, una línea cada cosa: certificado caducado o a ≤ 30 días; alcance mal o `control_no_existe`; ninguna ronda buena en 24 h con el correo configurado; **el ciclo automático no corre** (sin pausa y con `estado_ciclo.visto_en` de hace más de 30 minutos, o en pausa desde hace más de 24 h; sale aunque el correo no esté configurado, en cuanto el ciclo ha corrido una vez); **disco** (menos de 10 GiB libres); **`saldo` o `clave_rechazada`** en la última lectura (automática o no); **facturas elegibles esperando más de 4 horas** con la automática encendida, sin pausa ni tope, y sin ninguna automática buena desde entonces |

Isolatie: con el quinto papel, `app_local.PAPELES` (`app_local.py:70-75`) y `settings.roles`
(`nl.ts:875-880` y sus pares en `en.ts` y `es.ts`) ganan `correo`, y "Alle vier de onderdelen"
(`nl.ts:871`; `en.ts:865`; `es.ts:868`) pasa a no contar ("Alle onderdelen…").

### 6.2 La API (contrato 2.6)

`GET /api/v2/correo` (nuevo en `serve.LECTURAS_V2`, `serve.py:120-161`, sin parámetros; en
`_leer_paso_15`, `serve.py:993-1011`), solo lee la base:

```
{"correo": {
  "configurado": bool, "entorno": "nativo" | "contenedor" | "local",
  "estado": "al_dia" | "retrasado" | "retenido" | "error" | "sin_configurar",
  "error_codigo": null | "sin_configurar" | "credencial" | "reloj" | "permiso" | "alcance"
                | "control_no_existe" | "sin_conexion" | "limitado" | "aislamiento" | "salida"
                | "disco" | "interno",                          // la lista cerrada de §3.7
  "error_desde": ts | null, "ultima_consulta": ts | null, "ultima_buena": ts | null,
  "retenido_hasta": ts | null,
  "alcance": {"comprobado_en": ts | null, "bien": bool | null},
  "credencial": {"caduca_en": ts | null, "dias": int | null},
  "aviso_volumen": bool,
  "hoy": {"mensajes": int, "pdf_nuevos": int, "bytes": int},
  "ciclo": {"visto_en": ts | null, "variante": "nativa" | "docker" | null, "pausado": bool,
            "pausado_desde": ts | null, "disco_libre_bytes": int | null, "disco_bajo": bool},
  "recientes": [{"mensaje_id": int, "recibido_en": ts, "carpeta": "bandeja" | "no_deseado",
                 "remitente_doc": str | null, "asunto_doc": str | null,
                 "adjuntos": [{"nombre_doc": str | null, "resultado": str, "bytes": int | null,
                               "documento_id": int | null}]}],          // los 10 últimos
  "esperan_persona": {
     "correos": [ …como "recientes"… ], "correos_total": int,          // ≤ 50, §6.1
     "documentos": [{"documento_id": int, "nombre_original": str | null, "recibido_en": ts | null,
                     "motivo_codigo": "grande" | "fallo" | "rechazado_api" | "persona"}],
     "documentos_total": int},                                         // ≤ 50
  "lectura_automatica": {"activa": bool, "autorizacion_id": int | null,
     "tope_dia_usd_micro": int | null, "tope_mes_usd_micro": int | null,
     "max_documentos": int | null, "max_por_documento_usd_micro": int | null,
     "fijada_por": {"id", "nombre"} | null, "fijada_en": ts | null,
     "gastado_hoy_usd_micro": int, "gastado_mes_usd_micro": int, "queda_hoy_usd_micro": int,
     "parada": null | "limite_dia" | "limite_mes" | "persona" | "volumen" | "fallo",
     "motivo_codigo": str | null,          // con "fallo": salida, aislamiento, clave, contar, sin_tarifa,
                                           //   saldo, clave_rechazada, api_no_disponible
     "desde": ts | null, "proximo_intento": ts | null, "hasta": ts | null,
     "pendientes": int, "elegibles": int, "elegible_mas_antigua": ts | null}}}
```

Reglas del estado: `sin_configurar` si `estado_correo` está vacío; `error` si hay `error_codigo`,
**salvo** `limitado` y `sin_conexion` con `error_desde` de hace menos de 30 minutos (esos son
`retrasado`: "sigue solo"); `retenido` si `retenido_hasta` está en el futuro; `retrasado` si la
última consulta tiene más de 20 minutos; `al_dia` si no. Ninguna cifra con decimales
(`consultas.comprobar_v2`, `consultas.py:3522`). Remitente, asunto y nombres de adjunto salen como
texto, tal cual (saneados al registrar, §3.6).

`GET /api/v2/lectura` (`consultas.lectura_pdf`, `consultas.py:3585-3632`) añade:
`automatica` (= `lectura_automatica` de arriba, sin `fijada_por`), en `solicitud` la clave
`autorizacion` (`{id, fijada_por, fijada_en}` o null), los valores nuevos de `origen`
(`automatica`), `aprobada_via` (`automatica`) y `motivo_codigo` (los siete de §5.7), en cada fila del
resultado `nombre_original`, y en cada pasada (`pasada_en_curso`, `ultima_pasada`) `etiquetas`.

`POST /api/v2/acciones` (`recalcula=False` las cuatro; errores con los códigos que ya existen,
`invalido` fuera de rango y `sin_permiso`, `servicios.py:118-127`):

| Acción | Permiso | Parámetros (tipos de `servicios.py:84-89`) |
| --- | --- | --- |
| `fijar_lectura_automatica` | `admin` | `activa` `ENTERO` 0/1 (no hay tipo booleano), `tope_dia_usd_micro`, `tope_mes_usd_micro`, `max_documentos`, `max_por_documento_usd_micro` (`ENTERO`, con los rangos de §3.9), `motivo` `TEXTO` |
| `reanudar_lectura_automatica` | `importar_datos` | `motivo` `TEXTO` |
| `excluir_de_lectura_automatica` | `importar_datos` | `documento_ids` `LISTA` de `ENTERO` (1-200), `motivo` `TEXTO` |
| `marcar_correo_atendido` | `importar_datos` | `mensaje_id` `ENTERO`, `nota` `TEXTO` (≤ 500) |

`CONTRATO_V2 = "2.6"` (`consultas.py:1718`), con su párrafo "Lo que añadió el 2.6" en
`docs/integracion-web.md` y cada clave en el bloque de su ruta (`test_contrato_v2.py:164-178`). Los
literales "2.5" de `test_cartera.py:576` y `test_lectura.py:871` pasan a "2.6". En el frontend, las
claves nuevas van opcionales con el comentario "Contrato 2.6" (`api-types.ts:605-607`), y las uniones
de `ReadingRequest` (`api-types.ts:629-654`) ganan `'automatica'` y los motivos nuevos.

### 6.3 Ficheros del frontend

`aurora/panels/settings-panel.tsx` (filas `mailbox` y `autoRead`), nuevos
`aurora/panels/mailbox-card.tsx` (con la lista "Wacht op jou"), `aurora/panels/auto-read-card.tsx`
(con el formulario, "Weer aanzetten" y "Niet vanzelf lezen") y `aurora/panels/mailbox-model.ts`
(+ `mailbox-model.test.ts`: estado → tono, días a caducar, qué texto toca a cada correo que espera,
`parada` → texto); `aurora/processing/processing-workspace.tsx` (la línea), `reading-model.ts` (sin
"Empezar" para `automatica`), `process-texts.ts` (`reasonOf`, `:36-52`, con los siete motivos
nuevos); el panel de Inicio («Wat op iemand wacht»); `lib/api-types.ts`, `lib/api.ts`
(`paths.mailbox = '/api/v2/correo'`, `:96-131`), `lib/actions.ts` (las cuatro acciones con su
permiso), `status-pill.tsx` (grupo `correo`); `i18n/nl.ts`, `en.ts`, `es.ts`. Textos del dominio (las
etiquetas de las acciones) en `src/bms_agent/textos/{nl,en,es}.json`. Después, `npm run build` y
`npm run fuente` en el mismo commit (`test_app_local.py:306-326`). Todo con las piezas de
`panels/pieces.tsx` y el texto siempre como texto (nada de `innerHTML` ni
`dangerouslySetInnerHTML`, `test_app_local.py:394-411`).

Las herramientas de vista previa y diseño recorren Instellingen y Procesar
(`frontend/herramientas/vista-previa/comprobar.mjs:190`): tras el cambio se vuelven a grabar y
comprobar (`npm run vista-previa:grabar`, `vista-previa:comprobar`, `diseno:capturar`,
`diseno:comprobar`, `package.json:17-23`).

### 6.4 Textos (NL · ES · EN)

| Clave | NL | ES | EN |
| --- | --- | --- | --- |
| `systemRows.mailbox` | Facturenmailbox | Buzón de facturas | Invoice mailbox |
| `systemNotes.mailbox` | Of de facturen uit de mailbox binnenkomen | Si las facturas del correo están entrando | Whether invoices are coming in from the mailbox |
| `systemRows.autoRead` | Automatisch lezen | Lectura automática | Automatic reading |
| `systemNotes.autoRead` | Hoeveel het programma zelf mag uitgeven aan lezen | Cuánto puede gastar el programa leyendo solo | How much the program may spend reading by itself |
| `mailboxStates.al_dia` | Bijgewerkt | Al día | Up to date |
| `mailboxStates.retrasado` | Al een tijd niet gecontroleerd | Hace rato que no se mira | Not checked for a while |
| `mailboxStates.retenido` | Voor vandaag gepauzeerd | En pausa hasta mañana | Paused until tomorrow |
| `mailboxStates.error` | Werkt niet | No funciona | Not working |
| `mailboxStates.sin_configurar` | Niet ingesteld | Sin configurar | Not set up |
| `mailbox.lastCheck` | Laatst gecontroleerd: {when} | Última consulta: {when} | Last checked: {when} |
| `mailbox.today` | Vandaag: {messages} mails, {pdfs} nieuwe pdf's | Hoy: {messages} correos, {pdfs} PDF nuevos | Today: {messages} emails, {pdfs} new PDFs |
| `mailbox.held` | Vandaag kwamen er ongewoon veel pdf's binnen. De rest wordt vanaf {when} opgehaald; er gaat niets verloren. | Hoy han llegado muchos más PDF de lo normal. Lo demás se trae a partir de {when}; no se pierde nada. | Unusually many PDFs arrived today. The rest is fetched from {when}; nothing is lost. |
| `mailbox.unverified` | niet gecontroleerd | no comprobado | not verified |
| `mailbox.unverifiedHelp` | Afzender en onderwerp kan iedereen invullen. Vertrouw er niet op, zeker niet bij een nieuw rekeningnummer. | El remitente y el asunto los puede poner cualquiera. No te fíes de ellos, y menos con un número de cuenta nuevo. | Anyone can fill in the sender and subject. Do not rely on them, especially with a new account number. |
| `mailbox.certExpires` | Certificaat verloopt over {days} dagen ({date}) | El certificado caduca en {days} días ({date}) | Certificate expires in {days} days ({date}) |
| `mailbox.certExpired` | Het certificaat is verlopen: er komt niets meer binnen | El certificado ha caducado: no entra nada | The certificate has expired: nothing comes in |
| `mailbox.scopeOk` | Alleen deze mailbox is leesbaar (gecontroleerd {when}) | Solo se puede leer este buzón (comprobado {when}) | Only this mailbox can be read (checked {when}) |
| `mailbox.cycle` | Automatisch werk: laatst gezien {when} | Trabajo automático: visto por última vez {when} | Automatic work: last seen {when} |
| `mailbox.cyclePaused` | Automatisch werk staat op pauze sinds {when} (iniciar.bat of automatico.bat -Reanudar zet het weer aan) | El trabajo automático está en pausa desde {when} (iniciar.bat o automatico.bat -Reanudar lo reanudan) | Automatic work is paused since {when} (iniciar.bat or automatico.bat -Reanudar resumes it) |
| `mailbox.waiting` | Wacht op jou | Esperan a una persona | Waiting for you |
| `mailbox.waitingMail` | Mails die het programma niet kon lezen | Correos que el programa no ha podido leer | Emails the program could not read |
| `mailbox.waitingDocs` | Facturen die niet vanzelf gelezen worden | Facturas que no se leen solas | Invoices that are not read automatically |
| `mailbox.handled` | Afgehandeld | Hecho | Handled |
| `mailbox.noPdf` | Geen pdf in deze mail. Staat de factuur op een website of in de tekst, haal hem dan zelf op. | Este correo no trae ningún PDF. Si la factura está en una web o en el texto, tráela tú. | No PDF in this email. If the invoice is on a website or in the text, fetch it yourself. |
| `mailbox.junk` | In ongewenste e-mail: niet opgehaald. Is het een echte factuur? Open de facturenmailbox in Outlook en kies "Geen ongewenste e-mail"; dan wordt hij binnen een paar minuten opgehaald. | En correo no deseado: no se ha traído. ¿Es una factura de verdad? Abre el buzón de facturas en Outlook y elige «No es correo no deseado»; en unos minutos se trae. | In junk email: not fetched. Is it a real invoice? Open the invoice mailbox in Outlook and choose "Not junk"; it is fetched within a few minutes. |
| `mailbox.volume` | Vandaag komen er ongewoon veel mails binnen: automatisch lezen staat op pauze tot iemand de lijst nakijkt. | Hoy llegan muchos más correos de lo normal: la lectura automática está en pausa hasta que alguien mire la lista. | Unusually many emails are arriving today: automatic reading is paused until someone checks the list. |
| `mailboxErrors.credencial` | Microsoft accepteert het certificaat niet. Vraag de beheerder om een nieuw (correo-certificado.bat). | Microsoft no acepta el certificado. Pide uno nuevo a quien mantiene el programa (correo-certificado.bat). | Microsoft does not accept the certificate. Ask the administrator for a new one (correo-certificado.bat). |
| `mailboxErrors.permiso` | Microsoft geeft geen toegang tot de mailbox. De beheerder moet de instelling in Microsoft 365 nakijken. | Microsoft no da acceso al buzón. Quien mantiene el programa tiene que revisar Microsoft 365. | Microsoft refuses access to the mailbox. The administrator needs to check Microsoft 365. |
| `mailboxErrors.alcance` | Het programma kan meer lezen dan alleen de facturenmailbox. Uit veiligheid wordt niets opgehaald tot de beheerder dit herstelt. | El programa puede leer más que el buzón de facturas. Por seguridad no se trae nada hasta que se arregle. | The program can read more than the invoice mailbox. For safety nothing is fetched until this is fixed. |
| `mailboxErrors.control_no_existe` | De controlemailbox bestaat niet meer, dus de veiligheidscontrole kan niet: er wordt niets opgehaald. De beheerder stelt een andere in (correo-configurar.bat). | El buzón de control ya no existe y la comprobación de seguridad no se puede hacer: no se trae nada. Quien mantiene el programa pone otro (correo-configurar.bat). | The control mailbox no longer exists, so the safety check cannot run: nothing is fetched. The administrator sets another one (correo-configurar.bat). |
| `mailboxErrors.sin_conexion` | Geen verbinding met Microsoft. Het wordt over een paar minuten opnieuw geprobeerd. | No hay conexión con Microsoft. Se vuelve a probar en unos minutos. | No connection to Microsoft. It tries again in a few minutes. |
| `mailboxErrors.limitado` | Microsoft vraagt even te wachten. Het gaat vanzelf verder. | Microsoft pide esperar un poco. Sigue solo. | Microsoft asked to wait a moment. It continues by itself. |
| `mailboxErrors.aislamiento` | De afscherming klopt niet: er is niets opgehaald. Voer comprobar.bat uit. | El aislamiento no está bien: no se ha traído nada. Ejecuta comprobar.bat. | The isolation check failed: nothing was fetched. Run comprobar.bat. |
| `mailboxErrors.salida` | De uitgang naar Microsoft is niet gestart: er is niets opgehaald. | La salida hacia Microsoft no ha arrancado: no se ha traído nada. | The exit to Microsoft did not start: nothing was fetched. |
| `mailboxErrors.disco` | De schijf is bijna vol: er wordt niets meer opgehaald of gelezen. | El disco está casi lleno: no se trae ni se lee nada más. | The disk is almost full: nothing more is fetched or read. |
| `mailboxErrors.reloj` | De klok van deze computer loopt verkeerd: Microsoft weigert, en nieuwe mails wachten tot de klok klopt. | El reloj de este ordenador va mal: Microsoft no acepta, y los correos nuevos esperan a que esté bien. | This computer's clock is wrong: Microsoft refuses, and new emails wait until it is right. |
| `mailboxErrors.interno` | Er ging iets mis bij het ophalen. De beheerder kan het logboek bekijken. | Algo ha fallado al traer el correo. Quien mantiene el programa puede mirar el registro. | Something went wrong while fetching. The administrator can check the log. |
| `attachment.documento` | Pdf ontvangen | PDF recibido | PDF received |
| `attachment.no_es_pdf` | Heet pdf, maar is het niet | Dice ser PDF, pero no lo es | Claims to be a PDF but is not |
| `attachment.demasiado_grande` | Te groot (meer dan 20 MB): vraag om een kleinere pdf | Demasiado grande (más de 20 MB): pide un PDF más pequeño | Too large (over 20 MB): ask for a smaller PDF |
| `attachment.xml` | E-factuur (XML): nog niet gelezen | Factura electrónica (XML): aún no se lee | E-invoice (XML): not read yet |
| `attachment.reenvio` | Doorgestuurd als bijlage: stuur de pdf zelf door als gewone bijlage | Reenviado como adjunto: reenvía el PDF como adjunto normal | Forwarded as attachment: forward the PDF itself as a normal attachment |
| `attachment.no_pdf` | Geen pdf: niet gelezen | No es PDF: no se lee | Not a PDF: not read |
| `attachment.enlace` | Link naar OneDrive/SharePoint: niet opgehaald | Enlace a OneDrive/SharePoint: no se trae | Link to OneDrive/SharePoint: not fetched |
| `attachment.no_deseado` | In ongewenste e-mail: niet opgehaald | En correo no deseado: no se trae | In junk email: not fetched |
| `attachment.de_prueba` | Testgegevens: niet toegelaten | Datos de prueba: no entran | Test data: not accepted |
| `attachment.error` | Kon een dag lang niet worden opgehaald | No se ha podido traer en un día | Could not be fetched for a day |
| `excluded.grande` | Te duur om vanzelf te lezen | Demasiado cara para leerla sola | Too expensive to read by itself |
| `excluded.fallo` | Twee keer mislukt bij automatisch lezen | Falló dos veces al leerla sola | Failed twice during automatic reading |
| `excluded.rechazado_api` | De API neemt deze pdf niet aan (te groot, te veel pagina's of beveiligd) | La API no acepta este PDF (demasiado grande, demasiadas páginas o protegido) | The API does not accept this PDF (too large, too many pages or protected) |
| `excluded.persona` | Door iemand apart gezet | Apartada por una persona | Set aside by someone |
| `autoRead.on` | Aan | Encendida | On |
| `autoRead.off` | Uit | Apagada | Off |
| `autoRead.help` | Nieuwe facturen uit de mailbox worden vanzelf gelezen, binnen deze grenzen. Daarna kijk jij ze na, zoals altijd. | Las facturas nuevas del buzón se leen solas, dentro de estos límites. Después las revisas tú, como siempre. | New invoices from the mailbox are read automatically, within these limits. You review them afterwards, as always. |
| `autoRead.capDay` | Plafond per dag | Tope por día | Cap per day |
| `autoRead.capMonth` | Plafond per maand | Tope por mes | Cap per month |
| `autoRead.maxDocs` | Maximaal aantal facturen per ronde | Máximo de facturas por ronda | Maximum invoices per round |
| `autoRead.maxPerDoc` | Maximaal per factuur | Máximo por factura | Maximum per invoice |
| `autoRead.spent` | Vandaag {spent} van {cap} · deze maand {spentMonth} van {capMonth} | Hoy {spent} de {cap} · este mes {spentMonth} de {capMonth} | Today {spent} of {cap} · this month {spentMonth} of {capMonth} |
| `autoRead.setBy` | Ingesteld door {name} op {date} | La fijó {name} el {date} | Set by {name} on {date} |
| `autoRead.limitDay` | Er is vandaag minder dan {max} over voor één factuur: de rest wordt morgen gelezen, of nu via Verwerken. | Hoy queda menos de {max} para una factura: lo demás se lee mañana, o ahora desde Procesar. | Less than {max} is left today for one invoice: the rest is read tomorrow, or now from Process. |
| `autoRead.limitMonth` | Er is deze maand minder dan {max} over voor één factuur: de rest wordt volgende maand gelezen, of nu via Verwerken. | Este mes queda menos de {max} para una factura: lo demás se lee el mes que viene, o ahora desde Procesar. | Less than {max} is left this month for one invoice: the rest is read next month, or now from Process. |
| `autoRead.pausedPerson` | Gepauzeerd tot morgen: {name} heeft een automatische lezing gestopt. | En pausa hasta mañana: {name} paró una lectura automática. | Paused until tomorrow: {name} stopped an automatic reading. |
| `autoRead.pausedVolume` | Gepauzeerd: vandaag kwamen er ongewoon veel mails binnen. Kijk de lijst na, zet apart wat geen factuur is en zet het weer aan. | En pausa: hoy han llegado muchos más correos de lo normal. Mira la lista, aparta lo que no sea factura y vuelve a encenderla. | Paused: unusually many emails arrived today. Check the list, set aside what is not an invoice and turn it back on. |
| `autoRead.failed` | Gestopt na een fout: {reason} Volgende poging om {when}. | Parada tras un fallo: {reason} Próximo intento a las {when}. | Stopped after a failure: {reason} Next try at {when}. |
| `autoRead.resume` | Weer aanzetten | Volver a encender | Turn back on |
| `autoRead.waitingList` | Wacht op automatisch lezen | Esperan a la lectura automática | Waiting for automatic reading |
| `autoRead.exclude` | Niet vanzelf lezen | No leer solas | Do not read automatically |
| `autoRead.onlyAdmin` | Alleen een beheerder kan dit wijzigen. | Solo un administrador puede cambiarlo. | Only an administrator can change this. |
| `autoRead.save` | Opslaan | Guardar | Save |
| `process.origin.automatica` | Automatisch, uit de facturenmailbox | Automática, del buzón de facturas | Automatic, from the invoice mailbox |
| `process.stopAuto` | Stoppen zet automatisch lezen op pauze tot morgen. | Parar deja la lectura automática en pausa hasta mañana. | Stopping pauses automatic reading until tomorrow. |
| `process.strip` | Automatisch lezen: {state} · vandaag {spent} van {cap} · mailbox gecontroleerd om {time} | Lectura automática: {state} · hoy {spent} de {cap} · buzón consultado a las {time} | Automatic reading: {state} · today {spent} of {cap} · mailbox checked at {time} |
| `process.reasons.limite_dia` | Het dagplafond voor automatisch lezen is bereikt. | Se ha llegado al tope del día de la lectura automática. | The daily cap for automatic reading has been reached. |
| `process.reasons.limite_mes` | Het maandplafond voor automatisch lezen is bereikt. | Se ha llegado al tope del mes de la lectura automática. | The monthly cap for automatic reading has been reached. |
| `process.reasons.excluidas` | Deze facturen worden niet vanzelf gelezen: ze wachten op jou. | Estas facturas no se leen solas: esperan a una persona. | These invoices are not read automatically: they wait for you. |
| `process.reasons.sin_autorizacion` | Automatisch lezen staat uit. | La lectura automática está apagada. | Automatic reading is off. |
| `process.reasons.saldo` | Het tegoed voor de API is op (of het bestedingslimiet is bereikt). Vul het aan; daarna gaat het vanzelf verder. | El saldo de la API se ha acabado (o se llegó al límite de gasto). Recárgalo; después sigue solo. | The API credit has run out (or the spending limit was reached). Top it up; it then continues by itself. |
| `process.reasons.clave_rechazada` | De API weigert de sleutel. De beheerder moet hem vervangen (clave.bat). | La API rechaza la clave. Quien mantiene el programa tiene que cambiarla (clave.bat). | The API refuses the key. The administrator needs to replace it (clave.bat). |
| `process.reasons.api_no_disponible` | De API is even niet bereikbaar of overbelast. Er is niets apart gezet; het wordt later vanzelf opnieuw geprobeerd. | La API no está disponible o está saturada. No se ha apartado nada; se vuelve a probar solo más tarde. | The API is unreachable or overloaded. Nothing was set aside; it tries again later by itself. |
| `settings.roles.correo` | De mailophaler | El que trae el correo | The mail fetcher |
| `settings.isolationOk` | Alle onderdelen zijn gecontroleerd en afgeschermd. | Todas las partes están comprobadas y aisladas. | All parts have been checked and isolated. |
| Banda: correo | MAILBOX · Er komen geen facturen meer binnen: {reden} | (las bandas son NL+EN, como las de hoy) | MAILBOX · Invoices are no longer coming in: {reason} |
| Banda: ciclo | AUTOMATISCH · Het automatische werk loopt niet sinds {when}. Zie automatico.bat -Estado. | — | AUTOMATIC · Automatic work has not run since {when}. See automatico.bat -Estado. |
| Banda: disco | SCHIJF · Nog maar {free} vrij: er wordt niets opgehaald of gelezen. | — | DISK · Only {free} free: nothing is fetched or read. |
| Banda: API | LEZEN · {reden} | — | READING · {reason} |
| Banda: wachten | LEZEN · {n} facturen wachten al meer dan 4 uur op automatisch lezen. | — | READING · {n} invoices have waited more than 4 hours for automatic reading. |
| Acciones (`textos/*.json`) | Automatisch lezen instellen · Automatisch lezen weer aanzetten · Niet vanzelf lezen · Mail afgehandeld | Fijar la lectura automática · Volver a encender la lectura automática · No leer solas · Correo atendido | Set automatic reading · Turn automatic reading back on · Do not read automatically · Email handled |

"postbus" ya es la carpeta `buzon` en la app (`nl.ts:1678`); el buzón de correo es "mailbox" para no
confundirlos. Los textos de la API dicen "de API", como hoy (`nl.ts:1680`). El nombre del botón de
Outlook ("Geen ongewenste e-mail" / «No es correo no deseado» / "Not junk") se comprueba en el Outlook
del dueño **[comprobar en vivo]**.

---

## 7. Pruebas

No hay inquilino de Microsoft ni en CI ni aquí: todo lo de Graph se prueba con un doble, y lo que solo
se puede probar contra Microsoft o en Windows va a una lista para el mini PC (§7.4, y como acción del
dueño). Aquí no hay `pwsh` (`which pwsh` no da nada) ni demonio de Docker (`docker info` falla), pero
`docker compose config --quiet` sí funciona sin demonio: §9 paso 0 dice cómo tener `pwsh`.

### 7.1 Los dobles

**`tests/graph_falso.py`** (ayuda de pruebas, no un test): `GraphFalso`, montado con
`httpx2.MockTransport` que el cliente recibe por inyección (`ClienteGraph(…, transporte=…)`; en
producción, `None`). Contesta:

- `POST https://login.microsoftonline.com/<inquilino>/oauth2/v2.0/token`: **verifica de verdad la
  aserción** con la parte pública del certificado de prueba (PS256, `x5t#S256`, `aud`, `iss = sub`,
  `exp − nbf ≤ 10 min`, `jti` nuevo) y da un token falso (un JWT sin firmar con `tid`, `appid`, `aud` y,
  según el caso, `roles`);
- `…/mailFolders/inbox/messages/delta` y `…/junkemail/messages/delta` con páginas de
  `tests/fixtures/correo/*.json`. Los `@odata.nextLink`/`@odata.deltaLink` tienen **las formas de
  Microsoft**, no una propia: con sintaxis de clave y en minúsculas
  (`…/v1.0/users('facturen%40ejemplo.test')/mailfolders('AQMk…')/messages/delta?$skiptoken=…`, como
  `docs-ms/concepts_delta-query-messages.md:151`), con el GUID del buzón
  (`…/v1.0/users/0f1e…/mailFolders/AAMk…/messages/delta?$deltatoken=…`) y la de la primera petición;
- `…/attachments` (lista), `…/attachments/{id}/$value`, `…/mailFolders/inbox?$select=id`,
  `/users?$top=1`; y **falla el test** con cualquier `$expand`, con cualquier `GET` de un
  `itemAttachment` o de un `referenceAttachment`, y con cualquier método que no sea `GET` (salvo el
  `POST` del token);
- casos: 429 con y sin `Retry-After`, 503, 410 con `Location`, `syncStateNotFound`, 401
  `invalid_client`, `AADSTS700024` (reloj), 403, 200 y 404 en el buzón de control (`alcance`,
  `control_no_existe`), un token con `roles: ["Mail.Read"]`, un `nextLink` a otro host, con usuario y
  contraseña, con `http:`, con el puerto 8443; adjuntos `fileAttachment` PDF, PDF con
  `application/octet-stream`, `.PDF` en mayúsculas, uno que se llama `.pdf` y no lo es, uno de 21 MiB
  (más que `MAX_PDF`), XML, `.eml`, imagen en línea, `itemAttachment`, `referenceAttachment`; una lista
  de adjuntos de más de 4 MiB; un mensaje con JSON de forma rara (sin `id`, `receivedDateTime`
  roto) entre dos buenos; el mismo id primero en "no deseado" y después en la bandeja;
- y **apunta cada petición** (método, host, ruta, consulta, cabeceras sin `Authorization`) para que los
  tests comprueben: solo `GET` a Graph, un solo `POST` y solo al token, nunca `body`/`bodyPreview`/
  `uniqueBody` en `$select`, nunca `$expand`, siempre `Prefer: IdType="ImmutableId"`.

**El cliente de la API falso** (como `test_extraccion_pasada.ClienteFalso`): `count_tokens` y
`messages.create` que, según el PDF, devuelven bien o lanzan excepciones **del SDK** hechas a mano: 413
`request_too_large` y 400 `invalid_request_error` para uno (al contar y al leer), 401, 403, 402
`billing_error`, 400 con "credit balance", 429 con `enforced_spend_limit_reached`, 429 normal, 529,
`APIConnectionError`; cuenta llamadas para comprobar que tras una parada no se llama más.

Los datos de las fixtures son inventados, con dominios `example.test` / `ejemplo.test`; ningún dato
real.

| Fichero | Lo que prueba |
| --- | --- |
| `tests/test_lectura.py` (se amplía) | `estimar` por PDF: un PDF de más de `MAX_BYTES_API` queda omitido sin llamar a nada; uno con 413 o 400 al contar queda omitido y los demás se cuentan; 401/402/429/529 al contar cierran con `clave_rechazada`/`saldo`/`api_no_disponible`, no con `contar`; `clasificar_error` caso a caso; en `leer`, un 402 para la pasada en el primer documento (ese queda `sin_leer`, los demás `sin_pagar`, `fallidas` = 0, la petición `fallida` con `saldo`) y vale igual para una lectura de una persona; dos 400 idénticos seguidos paran; un `Rechazado` no para |
| `tests/test_lectura_automatica.py` | La tabla y sus disparadores (solo personas, sin cambios ni borrados, techos); `fijar` solo con `admin` y las otras tres con `importar_datos` (matriz de `test_servicios.py`); `siguiente` en cada fila de §5.2 y en ese orden; la espera tras fallos (1, 2, 4… 24 h; vuelve a 1 h tras una buena); `autorizar` (tope = mínimo; días y meses en Europe/Amsterdam, con el cambio de hora); exclusiones `grande`, `rechazado_api`, `fallo` (a la **segunda** pasada automática fallida, no a la primera; un fallo de la API no cuenta) y `persona` (hasta 200, en bloque); la pausa `persona` al cancelar una automática y su fin a las 00:00; la pausa `volumen` una vez al día; `reanudar`; `aprobar` rechaza una automática; una automática colgada se cierra `abandonada`; elegibles sin las de "no deseado" ni las excluidas; `esperan_persona` (correos y documentos, `correo_atendido`, un `no_deseado` que llegó luego a la bandeja ya no sale); la lectura entera con el cliente falso, leyendo del almacén; `nombre_original` y `etiquetas` |
| `tests/test_migracion_0019.py` | Una base en 0018 con filas en `solicitud_lectura` y `pasada_lectura` migra a 0019 sin perder ni cambiar nada, `PRAGMA foreign_key_check` vacío, los nombres exactos de disparadores e índices de §3.9 en `sqlite_master` |
| `tests/test_almacen.py` (se amplía) | Las siete tablas de evidencia nuevas en `EVIDENCIA` (`:65-66`) y en `_poblar`; `USUARIOS_SISTEMA` con seis (`:150`) |
| `tests/test_correo_certificado.py` | Crear (RSA 3072, autofirmado, 24 meses, PEM PKCS#8), la aserción, la huella; `crear` **no rehace** uno que ya existe (solo `--siguiente`); `activar`, `volver`, `borrar --anterior` (locales); guardar y leer con DPAPI falso (`secretos` con tipos); solo el papel `correo` lo descifra; ningún mensaje ni `caplog` lleva la clave |
| `tests/test_correo_graph.py` | Token, `roles` vacío exigido, `GET` solamente, la comprobación de cada enlace con las formas de Microsoft (pasan) y con otro host, `http:`, usuario en la URL o puerto 8443 (fallan con `interno`), `Retry-After`, reinicio del delta, el tope de 4 MiB leído por trozos, sin token ni consulta en errores ni en `caplog`; y **por una salida de verdad** (`salida.Proxy` local, como `test_instalacion_nativa.py:891-910`): con la credencial pasa a `graph.microsoft.com:443`, a `api.anthropic.com:443` recibe 403, sin credencial 407 |
| `tests/test_correo_traer.py` | Una ronda entera contra `GraphFalso`: nombres de la bandeja (`sha256(graph_id\|carpeta)`), escritura atómica, topes por adjunto, ronda, día (`retenido_hasta`, sin pedir nada a Graph) y bandeja; el mensaje raro entre dos buenos (los buenos se registran; el raro, al tercer intento, `error`); un "corte" simulado a mitad de un mensaje (excepción que no es `Exception`) que sube su contador; `itemAttachment` como `reenvio` sin pedirlo; "no deseado" sin bajar nada y el mismo id luego en la bandeja (se trae); pendientes durante 24 h; el cerrojo: un `traer.cerrojo` que se quedó en disco sin dueño no bloquea, uno tomado por otro proceso da `ocupado`; idempotencia al repetir; `estado.json`; y que `correo traer` **no abre la base** (`sqlite3.connect` parcheado para fallar) **ni importa `anthropic`** |
| `tests/test_correo_registrar.py` | Bandejas malas: nombres con `..`, `\`, `:`, mayúsculas o sin hexadecimal; un fichero o **una carpeta** (`entrada/pdf`, `entrada/llegadas`, `estado`) cambiada por un enlace simbólico (Linux); JSON enorme, roto o con claves de más; sha que no casa; sin `%PDF-`; fecha en el futuro (no se registra, queda el fichero y `reloj`); caracteres de control y bidi; PDF de prueba en la base de verdad; 2 500 ficheros (mira 2 000). Acuse: tras registrar, la bandeja queda vacía de lo registrado y de lo rechazado. Idempotencia: el mismo mensaje dos veces, el mismo PDF en dos mensajes, el mismo PDF ya llegado por `buzon\facturas`. Metadatos: `origen='correo'`, `recibido_fuente='correo'`, `mensaje_id`; y, tras leerla, `factura.fecha_recepcion` = el día de recepción del servidor (`ingesta.py:561`). La pausa `volumen` al ver `aviso_volumen`. Eventos con actor `correo` |
| `tests/test_ciclo_latido.py` | `ciclo latido` escribe `estado_ciclo` (visto, pausado, disco); la banda de §6.1 con cada condición, a partir de una base de prueba |
| `tests/test_simular_correo.py` | El ayudante de e2e, solo con la base de prueba |

### 7.2 Las guardas estructurales que se amplían

| Guarda | Cambio |
| --- | --- |
| `test_alcance_v1.py::test_ningun_modulo_habla_con_la_red_salvo_la_extraccion` (`:270-295`) | `RED_SALIENTE` (`:185-186`) gana `httpx2` y `httpcore2`; los `from X import Y` se miran también como `X.Y` (hoy `from urllib import request` y `from http import client` pasan sin verse, porque solo se compara `X`). Excepción con nombre: `bms_agent.correo.graph` puede importar `httpx2`, y nada más de la lista. `aislamiento.EXTERNOS` (`aislamiento.py:98`) gana los dos hosts de Microsoft; `PERMITIDOS_POR_DEFECTO` **no cambia**; `salida.DESTINOS_CORREO == ("login.microsoftonline.com:443", "graph.microsoft.com:443")` |
| Nueva: el correo no ve la base | Los módulos de `bms_agent.correo` salvo `registrar` no importan (tampoco a través de otros módulos del paquete) `sqlite3`, `bms_agent.almacen`, `lectura`, `extract`, `ingesta`, `serve` ni `anthropic`; `registrar` no importa `graph`, `certificado`, `httpx2` ni `cryptography` |
| Nueva: solo lectura y sin cuerpo | En `correo/graph.py`, las únicas llamadas HTTP son `GET` y un `POST` en la función del token (AST); ningún literal `$expand`, `body`, `bodyPreview`, `uniqueBody`, `/$value` fuera de la función que baja un `fileAttachment`; y `GraphFalso` lo confirma en cada test |
| `test_alcance_v1.py` (variables de entorno, `:240-242`) | Igual: ninguna nueva (las rutas llegan por argumentos) |
| `test_alcance_v1.py` (nombres, `:80-135`) | Siguen pasando sin tocar la excepción: ni las acciones ni los literales nuevos llevan "aprob", "programad", "enviad" ni "enviar" |
| `test_extraction_contract.py:31-40`, `test_extraccion_v2.py:162` | Sin cambios: la petición de extracción es la misma; ni remitente, ni asunto, ni cuerpo |
| `test_instalacion_nativa.py::test_ningun_modulo_lanza_procesos` (`:1018-1038`) | Sin cambios: mira los módulos nuevos sola. Se añade una prueba en un intérprete aparte con `prohibir_procesos` que importa `cryptography`, firma una aserción y habla con `GraphFalso` (como `:1043-1095`) |
| `test_instalacion_nativa.py` (papeles, reglas, scripts) | Cinco papeles, 14 reglas (`:1265-1273`), `SCRIPTS` + `ciclo`, `automatico`, `correo-configurar`, `correo-certificado` (`:1119-1120`); pines nuevos: `Arrancar-Salida-Correo` (sus dos `--permitir`, `--clave-del-entorno`, `--max-segundos`, `$VidaSalidaCorreo`, y que no arranca con `Procesos-De "lector"` no vacío), `Preparar-Certificados-Correo` antes de `Comprobar-Rol "correo"`, `$resultados["correo"]` en `comprobar.ps1`; **`automatico.ps1`**: carpeta `\BMS Finanzas\`, `IgnoreNew`, `LogonType Password`, límite `PT4H` del ciclo y `PT5M` de la consola, acción bajo `<Raiz>\windows`; **la pausa**: `Pausar-Automatico` aparece antes del primer `Parar-Rol` en `parar.ps1`, `instalar.ps1` y `desinstalar.ps1`, y antes de parar la consola en `restaurar.ps1`; `iniciar.ps1 -EnSegundoPlano` mira la pausa y el dueño del puerto y nunca abre Edge; la línea de `iniciar.ps1` (`:1893`) se cambia a propósito |
| `test_entorno_local.py` | Seis servicios (`:43`), `red_correo` interna, `salida_correo` en `red_correo` y `red_exterior_correo` y **no** en `red_exterior` (`:80-92`), su orden exacta con **dos** `--permitir` de Microsoft (gemela de `:103-119`); la de la salida de la API **sigue exigiendo un solo `--permitir`**; **solo `lector` tiene el secreto `anthropic_api_key`**, solo `correo` los dos del correo (`:135-149`); `correo` sin el volumen `datos`; volúmenes nuevos y los de `orden` (`correo_entrada` con escritura, `correo_estado` y `registro_correo` `:ro`) (`:151-162`); perfiles `{lector, ordenes, correo}` (`:172-185`); `SCRIPTS` (`:260`); **el `Dockerfile`**: cada volumen con nombre que algún servicio monta con escritura tiene su punto de montaje en el `mkdir -p` y en el `chown bms:bms` (`Dockerfile:44-45`); **ningún `-v` de un `.ps1` monta `secretos`** salvo `secretos\correo` y solo en `orden`; `docker/automatico.ps1` con `ExecutionTimeLimit` `PT0S` y `docker/ciclo.ps1` sin `Fallar`, `Comprobar-Docker` ni `exit` dentro del bucle |
| `test_entorno_docker.py` (con `BMS_PROBAR_DOCKER=1`, solo donde hay demonio) | Filas nuevas en las matrices (`:124-137`, `:161-173`): `correo` solo llega a `proxy-correo`; `proxy-correo` da 200 solo a los dos de Microsoft; el lector, 403 a los de Microsoft y sin conexión a `proxy-correo`; el correo, sin conexión a `proxy`; **`salida_correo` sin conexión a `salida:8765`** (la entrada a la consola). El montaje de prueba (`:67-75`) gana los dos volúmenes del correo, y un contenedor `correo` escribe en ellos como 10001 |
| `test_lectura_lector.py` (`:286-381`) | `PASOS` de `ciclo.ps1` en las dos variantes: pausa → cerrojo → pausa otra vez → latido → pasada de correo (salida de correo → aislamiento → `traer` → `finally` que la para) → `registrar` → `siguiente`; la rama automática `tomar --automatica` → salida → aislamiento → `contar` → `autorizar` → `leer` → `finally` → `Cerrar-Lectura`; **ningún `esperar` en la rama automática**, `esperar` solo con `--solo-app`, ningún `extract`, ningún `"si"`; códigos nuevos iguales en Python y en los dos `comun.ps1` |
| `test_contrato_v2.py`, `test_codigos_error.py`, `test_textos.py`, `i18n.test.ts`, `codigo-muerto.test.mjs` | Las claves, las acciones y los textos nuevos, en los tres idiomas |

### 7.3 De punta a punta

- **Python, sin red**: `GraphFalso` → `correo traer` → `correo registrar` (la bandeja queda vacía) →
  `lectura siguiente` → `tomar --automatica` → `contar` (cliente falso) → `autorizar` → `leer`
  (cliente falso) → la factura en la cola de `GET /api/v2/facturas`, con su `fecha_recepcion`. Y el
  mismo correo otra vez: nada nuevo, nada pagado. Y con un PDF que la API rechaza en medio: los demás
  se leen y ese sale en `esperan_persona`.
- **Navegador**: `scripts/simular_correo.py` (como `scripts/simular_lector.py`; solo con la base de
  prueba): pone `estado_correo` y `estado_ciclo` en cada estado, mete mensajes y adjuntos de prueba,
  fija una autorización, pausa y reanuda, y da los pasos de una lectura automática con las mismas
  funciones. `frontend/e2e/correo.spec.ts`: las dos filas y tarjetas de Instellingen en cada estado,
  la etiqueta "niet gecontroleerd", "Wacht op jou" con "Afgehandeld", "Niet vanzelf lezen" en bloque,
  el formulario con `admin` y sin él, "Weer aanzetten", la línea de Procesar, una lectura `automatica`
  sin "Empezar" y con "Stoppen" (que deja la pausa), las bandas (certificado, ciclo, saldo). Se corre
  con `procesar.spec.ts`, **`screens.spec.ts`** (Instellingen, `:510-531`) y **`aurora-paridad.spec.ts`**
  (las filas de Systeem, `:209-230`); la suite entera tarda más de una hora
  (`registro.md:11021-11027`): el paso corre esas cuatro.

### 7.4 Lo que solo se comprueba en Windows o con el inquilino

| Qué | Aquí (Linux, sin inquilino) | Solo en el mini PC / el inquilino |
| --- | --- | --- |
| La regla de aislamiento del correo | `aislamiento.evaluar("correo", …)` es una función pura: casos con observaciones falsas | — |
| Sondas de verdad por el proxy | `aislamiento.observar` contra una `salida.Proxy` local con su lista de correo y un resolvedor falso (como `test_salida.py`) | `comprobar.bat`: correo con su programa, 200 a los dos hosts de Microsoft, 4xx a `api.anthropic.com:443`, `graph.microsoft.com:80`, `example.com:443`, `1.1.1.1:443` y `graph.microsoft.com.evil.example:443`, 407 sin credencial; directo a todo, bloqueado; el lector, 403 a los de Microsoft |
| Reglas del cortafuegos | La tabla de `comun.ps1` y sus pines | Las 14 reglas, con el cortafuegos encendido en todos los perfiles |
| DPAPI | Protector falso inyectado | Guardar y descifrar con el usuario de la tarea; con otro usuario, "se guardó con otro usuario" |
| Los `.ps1` | Pines estáticos y `pwsh` los analiza (`test_instalacion_nativa.py:2331-2335,2375-2378`, con el `pwsh` del paso 0) | Que corren en Windows PowerShell 5.1 |
| Tareas (nativa) | Pines de `automatico.ps1` | Arrancan sin sesión tras un **reinicio de noche** (horas activas puestas) y descifran; suspender y volver; una **lectura pedida de más de 1 hora** (un lote de 100) no se corta; la consola que arranca el vigilante sigue viva cuando la tarea termina; **cambiar la contraseña del usuario**: `automatico.bat -Estado` dice 0x8007052E y `-Instalar` lo arregla |
| La pausa | Pines (§7.2) | `parar.bat` y en 20 minutos nada vuelve a arrancar; `iniciar.bat` lo reanuda; `instalar.bat` (actualizar) con las tareas puestas y un ciclo en marcha: espera o lo dice, y no deja `runtime` a medias |
| `iniciar.bat` | Pines | Con la consola ya en marcha abre Edge al momento; con otro programa en el puerto, el vigilante no arranca nada y `-Estado` lo dice |
| Docker: redes | `docker compose config --quiet` y los pines estáticos | `BMS_PROBAR_DOCKER=1 pytest tests/test_entorno_docker.py` (también en un Linux con Docker): las filas nuevas de §7.2 |
| Docker: solo | Pines de `docker/automatico.ps1` y `ciclo.ps1` | Inicio de sesión automático del usuario aparte y la pantalla bloqueada; el bucle sobrevive a un arranque en frío lento de WSL2 y a 3 días; una actualización de Docker Desktop con `automatico.bat -Pausar`; `orden` (uid 10001) escribe en `docker\secretos\correo` montado (renovar el certificado) |
| Disco | `ciclo latido --disco-libre` y la banda, con valores falsos | `Get-PSDrive` da el libre de verdad de la unidad |
| Microsoft de verdad | — | `correo-configurar.bat` fase 2: `correo comprobar` con 200 en el buzón, 403 en el de control y token sin `roles`; qué devuelve un buzón de control que no existe (404 o 403); la primera ronda sigue los `nextLink`/`deltaLink` de verdad; la lista de adjuntos sin `contentBytes`; "Geen ongewenste e-mail" en Outlook y la factura entra en la ronda siguiente; renovar el certificado con `correo-certificado.bat -Activar` en la variante elegida |
| La API de verdad | Cliente falso | Una lectura automática de 2-3 facturas reales; con la clave mala (`clave_rechazada`, banda); `count_tokens` con el saldo a cero **[comprobar]**: el diseño vale tanto si falla al contar como al leer |

---

## 8. Documentos

| Documento | Qué cambia |
| --- | --- |
| **`docs/correo-m365.md`** (nuevo) | La guía del inquilino (§2.1), en castellano, para el dueño o su informático: requisitos, **cuánto tarda** (unos 45 minutos y la espera de hasta 2 horas), los pasos con sus órdenes (el buzón compartido, el acceso completo de **una persona**, el **buzón de control** dedicado, la app sin permisos, RBAC, las pruebas), las dos fases de `correo-configurar.bat`, la renovación del certificado, cómo cortar el acceso, qué hacer con una factura en "Correo no deseado" ("Geen ongewenste e-mail"), lo que la app puede y no puede hacer. Enlaces a Learn (tabla de la investigación). Con marcadores, sin datos reales |
| `docs/arquitectura.md` | §2 (`:92-95`): de lo que llega por correo se guardan **los PDF** inmutables con su hash, el id del mensaje y la fecha del servidor; lo demás (XML, otros adjuntos, el propio mensaje) se apunta y se queda en el buzón (desviación, §8.1). §6 (`:217-223`): RBAC for Applications en vez de "política de acceso de aplicación" (legado), certificado, sin permisos de Entra. Red (`:236-239`): el componente de correo sale solo a los dos hosts de Microsoft por su propia salida. §12 (`:406`): Microsoft 365 y buzón dedicado, decidido. §7: la ingesta de correo, hecha |
| `docs/mcp-setup.md` | El adaptador estrecho del correo ya existe (`:44-46`); Zapier sigue fuera |
| `docs/instalacion-nativa.md` | §1 (cinco programas y el diagrama), §3 (el papel `correo`), §6 (arrancar solo: las tareas, `-EnSegundoPlano`, la pausa), §7 (dónde deja el correo lo suyo), §10 (14 reglas, las sondas del correo; los "12 reglas" de `:358` y `:552`), **§11: la tabla de §1.5 tal cual; se corrigen `:386` y `:423`** ("la salida solo está encendida al leer" deja de ser verdad: la del correo se enciende cada 5 minutos); y el riesgo dicho claro: en la nativa, un fallo en el proceso que lee correo de desconocidos ve la base y la clave de la API y podría sacarlas por `graph.microsoft.com`; para el correo desatendido se recomienda Docker. §12 (el usuario aparte, **recomendado** para el modo desatendido, con la contraseña sin caducidad), §13 (los topes), §14 (los errores del correo y de la lectura), §15 (`ver-salida` con los dos registros; renovar el certificado; actualizar con la pausa), §16 (la primera vez: tareas, correo, `correo comprobar`), §17 (para quien mantiene: papel, reglas, puerta). Se conservan las frases que leen los tests (`test_instalacion_nativa.py:1990-2050`) |
| `docs/entorno-local.md` | La tabla de servicios (`:20-26`) y el diagrama (`:28-43`) con seis servicios; **recomendada para el mini PC con el correo**; arrancar solo (`:92-93`): el usuario aparte, el inicio de sesión automático con sus pasos, la pantalla bloqueada, la tarea del bucle, Docker Desktop sin actualizarse solo; el correo (configurar, renovar); `ver-salida` (`:376`); los costes; "cambiar la lista blanca" (`:455-457`) dice que hay dos; actualizar Docker Desktop (`:415-416`) con `automatico.bat -Pausar` |
| `docs/app-local.md` | Instellingen (las dos filas, "Wacht op jou"), Procesar (origen automático, la línea, la pausa de "Stoppen"), Inicio, §8 (la 8B, `:1484-1487`, sustituida por la decisión del 23-11-2026) |
| `docs/integracion-web.md` | Contrato 2.6: `GET /api/v2/correo`, las claves nuevas de `/api/v2/lectura`, las cuatro acciones, "Lo que añadió el 2.6" |
| `docs/modelo-datos.md` | 0017, 0018 y 0019 (hoy dice 0001-0016, `:10-12`); las tablas nuevas y las reconstruidas |
| `docs/uso-v1.md` | La rutina (`:151-167`): las facturas del correo entran solas; qué mirar cada día (Inicio, «Wat op iemand wacht»). **El mantenimiento del mes**: `automatico.bat -Estado`, la lista "Wacht op jou", la fecha de caducidad del certificado, el saldo de la API, actualizar Windows y Docker Desktop con la automatización en pausa |
| `docs/costes.md` | Los topes de la lectura automática junto al techo prepagado (`:16-34`); qué pasa cuando se acaba el saldo (la lectura para, nada se aparta, banda; tras recargar sigue sola en la hora siguiente) |
| `docs/sistemas.md` | Una sección de Microsoft 365, como la de Exact (`:151-196`) |
| `README.md` | El índice (`:18-36`) con `correo-m365.md` |
| `windows/LEEME.txt`, `docker/secretos/LEEME.txt` | Los ficheros nuevos y qué es cada uno (`docker\secretos\correo\`) |
| `docs/v1/huecos.md`, `docs/fase-0.md` | **No se tocan** (fotos de su momento): el registro cita los huecos que cierra (`huecos.md:1619-1622`, `:1683-1686`, `:54-57`, `:1338-1341`) |
| `docs/v1/registro.md` | La sección del paso 18 (abajo) |

### 8.1 La sección del registro

```
## Paso 18 · el correo de facturas, solo: Microsoft 365 de solo lectura y la lectura automática con tope (petición del dueño del 23-11-2026)

Lo que pidió el dueño (las decisiones, sin reabrir) y lo que cambia del paso 17.

### Lo que hay
| Pieza | Qué es |   ← migración 0019; lectura_automatica.py; lectura.py (estimar por PDF, fallos
                     clasificados, siguiente/autorizar, pausas, exclusiones); correo/ (ajustes,
                     certificado, graph, traer, registrar); secretos.py por tipos; nativo.exigir_correo
                     y certificado_del_correo; aislamiento por papel; salida.DESTINOS_CORREO; CLI correo …,
                     lectura siguiente/autorizar, ciclo latido, serve --solo-errores; cuatro acciones;
                     /api/v2/correo y contrato 2.6; Instellingen, Procesar e Inicio; windows/ y docker/
                     (ciclo, automatico, correo-configurar, correo-certificado, cerrojo, pausa); compose
                     (correo, salida_correo, red_correo, red_exterior_correo, tres volúmenes, dos
                     secretos en secretos/correo); Dockerfile; docs/correo-m365.md
### Puertas
| Lo que se pide | Dónde se comprueba |   ← solo lectura; un buzón; sin cuerpo y sin $expand; el correo
                                            sin base ni API; el lector sin Microsoft; nombres generados;
                                            idempotencia (id, carpeta); topes de dinero y de volumen;
                                            nadie da el sí por una persona; un PDF que la API no quiere
                                            no para nada; ningún proceso; ningún secreto en registros;
                                            ningún servicio salvo el lector ve la clave de la API; la
                                            migración no pierde nada
### Cambios de comportamiento
| # | Antes | Ahora | Por qué |   ← la lectura solo con el sí de una persona → también con la
                                     autorización firmada; leer-facturas lee también las del correo;
                                     contar cuenta cada PDF por separado y omite el que la API no quiere
                                     (también en buzon\facturas, y lo de más de 20 MiB ni se manda); un
                                     fallo de la API (saldo, clave, sobrecarga) para la pasada y ya no
                                     deja veinte "fallidas"; la tarea arranca el lector para una lectura
                                     pedida (8B); recalcular --diaria lo hace el ciclo; parar.bat pausa la
                                     automatización e iniciar.bat la reanuda; iniciar.bat no reinicia una
                                     consola que ya va bien; cinco papeles y 14 reglas; seis servicios;
                                     contrato 2.5 → 2.6; iniciar -EnSegundoPlano
### Desviaciones, y por qué
   1. La 8B (el sí siempre de una persona) cambia por decisión del dueño del 23-11-2026: el sí es una
      autorización permanente, con nombre, versión y topes, firmada en la app por una persona con admin.
      De la 8B se quitan además el "horario de oficina" (una lectura pedida solo existe si una persona
      está en la app y da el sí en 15 minutos) y el "tope al mes" para las pedidas (lo que aprueba una
      persona no cuenta contra los topes de la automática; pregunta abierta 5).
   2. arquitectura.md §2 decía que el correo y sus adjuntos se guardan tal cual: se guardan los PDF (con
      hash, id del mensaje y fecha del servidor) y los metadatos; lo demás se queda en el buzón.
   3. arquitectura.md §6 decía "política de acceso de aplicación": Microsoft la ha dejado como legado;
      RBAC for Applications.
   4. XML/UBL, correos adjuntos como elemento y enlaces se apuntan y no se leen.
   5. "No deseado": solo metadatos; la persona lo pasa a la bandeja en Outlook.
   6. instalacion-nativa.md §11 decía que la salida solo está encendida al leer: ya no.
   7. La nativa no puede impedir que el correo vea la base y la clave de la API (mismo usuario): se
      recomienda Docker para el correo desatendido; el usuario aparte para el correo, paso 19.
   8. Un token por ronda, nunca guardado.
   … (las que salgan al construir)
### Lo que deben saber los pasos siguientes
   UBL determinista; paso 19: un usuario de Windows aparte para el papel correo (tarea propia, permisos,
   cerrojo fuera de datos); notificaciones fuera del camino del dinero; medir los bloqueos de la base en
   el N150; la cuarentena purgable de §13 (S2) si el volumen lo pidiera.
### Resultado
   pytest (pasan/se saltan, Python 3.11 y 3.13 para lo nativo, minutos), typecheck, vitest, build +
   fuente, vista-previa y diseño, e2e (correo, procesar, screens y aurora-paridad, minutos),
   docker compose config, BMS_PROBAR_DOCKER si se corrió, y la lista de §7.4 del mini PC con lo que se
   comprobó y lo que no.
```

---

## 9. Plan de implementación

Cada paso es para un agente, se verifica **aquí** (Linux, sin inquilino, sin Windows) y deja el
repositorio verde. Lo que solo se puede comprobar en el mini PC o contra Microsoft va en la última
columna y se junta en la lista de §7.4: ningún paso espera a eso para darse por hecho. El orden importa:
las guardas primero, la base antes que el código que la usa, la lectura tolerante antes que la
automática, Python antes que scripts y app, los documentos al final. Commits con la forma de siempre:
`tipo(v1-paso-18): frase en castellano en minúscula, sin tildes`.

| # | Paso | Alcance | Verificación aquí | Solo en Windows / inquilino |
| --- | --- | --- | --- | --- |
| 0 | Entorno (sin commit) | `pwsh` 7.4.x descomprimido en el scratchpad, como en el paso 14 (`registro.md:6699`); Python 3.11 (`.venv`) y 3.13 para lo nativo; `BMS_PAQUETES_WINDOWS` si hace falta; anotar la base de la suite | `pwsh -v`; `pytest -q` con los mismos pasan/saltan/fallos de entorno conocidos que antes (el `anthropic` 2.8.0 de aquí, §10) | — |
| 1 | Guardas de red | `test_alcance_v1.py`: `httpx2`, `httpcore2` y el `X.Y` de los `from X import Y`; casos del detector. Ningún código de `src/` cambia | `pytest tests/test_alcance_v1.py`; un módulo de prueba que importa `httpx2` o `from urllib import request` hace fallar el detector | — |
| 2 | Migración 0019 | `0019_correo.sql` entera (§3.9, en el orden exacto del punto 3); `USUARIOS_SISTEMA`; `test_almacen.py` (`EVIDENCIA`, `_poblar`, seis usuarios de sistema); `docs/modelo-datos.md` | `tests/test_migracion_0019.py`; `test_almacen.py`; `test_alcance_v1.py` (literales); `pytest -q` entero | — |
| 3 | La lectura que no se bloquea (sirve ya sin correo) | `documents.MAX_BYTES_API`; `lectura.clasificar_error`; `estimar` por PDF; `_Seguimiento.fallo`, `informar` y `cabe`; `terminar` con `fallida`; `extract.py:661`; `cli._cmd_lectura_contar`; `MOTIVOS` `saldo`, `clave_rechazada`, `api_no_disponible`; sus tres textos en `process-texts.ts` y los i18n; `npm run build` + `npm run fuente` | `test_lectura.py` (los casos de §7.1), `test_extraccion_pasada.py`, `test_lectura_lector.py`; `npm run typecheck`, `npm test`; `test_app_local.py` (fuente al día) | Con la API de verdad: una clave mala da `clave_rechazada` |
| 4 | La autorización, las pausas y las exclusiones | `lectura_automatica.py` (§5.7); `servicios`: las cuatro acciones con sus permisos (`activa` `ENTERO`); etiquetas en `textos/{nl,en,es}.json`; `web/` y `fuente.json` | `test_lectura_automatica.py` (tabla, acciones, gastado con cambio de hora, pausas, exclusiones en bloque, `esperan_persona`); `test_servicios.py` (matriz); `test_textos.py`; `test_app_local.py` | — |
| 5 | La lectura automática | `lectura.py` y `cli.py` (§5.7): `siguiente` con la espera creciente, `tomar --automatica/--solo-pedida`, `autorizar`, la segunda falla → `fallo`, la pausa al cancelar, `esperar --solo-app`, `_pdfs_a_leer`, códigos 8 y 9 y su copia en los dos `comun.ps1` | `test_lectura_automatica.py` (flujo entero con el cliente falso, leyendo del almacén); `test_lectura.py`; `test_lectura_lector.py` (paridad de códigos; `leer-facturas` sigue igual) | — |
| 6 | La dependencia | `scripts/fijar_windows.py`: `elegir_rueda` prefiere, entre varias `abi3` válidas, la de `cp3X` más alto ≤ la versión (hoy se para, `:139-144`), con su prueba; `cryptography`, `cffi`, `pycparser` en `docker/requirements.txt` (x86_64 y aarch64) y `windows/requirements-windows.txt`; `pyproject.toml`; los 17 y el conjunto `binarias` de `test_instalacion_nativa.py:1230,1248` (+ `cryptography`, `cffi`) | `test_entorno_local.py::test_las_dependencias_van_con_version_y_hash`; los de dependencias de `test_instalacion_nativa.py` (con `BMS_PAQUETES_WINDOWS`: las ruedas sin `.data`); `python scripts/fijar_windows.py --comprobar` | Que `instalar.bat` desempaqueta las ruedas nuevas en los cinco `runtime` |
| 7 | Certificado y ajustes | `correo/__init__.py` (`MAX_PDF`), `correo/ajustes.py`, `correo/certificado.py`; `secretos.py` por tipos; `nativo.certificado_del_correo` e `Instalacion.fichero_certificado_correo`; CLI `correo certificado …` (sin rehacer el actual) y `correo ajustes …` | `test_correo_certificado.py`; el intérprete con `prohibir_procesos` firma; `test_instalacion_nativa.py` (`ctypes` solo en `secretos.py`) | DPAPI de verdad con el usuario de la tarea |
| 8 | Cliente de Graph | `correo/graph.py` (token, `GET`, enlaces, tope de 4 MiB por trozos, `Retry-After`); `tests/graph_falso.py` y las fixtures con las formas de Microsoft; la excepción con nombre de `httpx2` | `test_correo_graph.py` (también por una `salida.Proxy` local con la lista de correo); `test_alcance_v1.py`; la guarda "sin `$expand`" | El primer `correo comprobar` y la primera ronda de verdad |
| 9 | La ronda | `correo/traer.py` (cerrojo del sistema, mensaje a mensaje con `intentos.json`, pendientes 24 h, topes por ronda y por día, `retenido_hasta`, "no deseado", la clave (id, carpeta), limpieza) y `correo comprobar` (con `control_no_existe`); CLI `correo traer\|comprobar` | `test_correo_traer.py` (sin base, sin `anthropic`, sin cuerpo) | Qué devuelve Graph para un buzón de control que no existe |
| 10 | Registrar y latido | `correo/registrar.py` (carpetas con `lstat` y `dir_fd`, 2 000 por pasada, acuse, `reloj`, pausa `volumen`); CLI `correo registrar [--fallo]`; `estado_correo`, `ronda_correo`; `ciclo latido` y `estado_ciclo` | `test_correo_registrar.py`; `test_ciclo_latido.py`; el de punta a punta en Python (§7.3) | — |
| 11 | API | `consultas.correo`, `GET /api/v2/correo`, claves nuevas de `/api/v2/lectura`, `CONTRATO_V2 = "2.6"`, `docs/integracion-web.md`, los dos literales "2.5", las bandas del servidor (§6.1) | `test_contrato_v2.py`, `test_lectura.py` (API), `test_cartera.py`, `test_app_local.py`, `test_codigos_error.py`, `test_ciclo_latido.py` (bandas) | — |
| 12 | La app | Instellingen (filas, tarjetas, "Wacht op jou", formulario, "Weer aanzetten", "Niet vanzelf lezen"), Procesar (línea, origen automático sin "Empezar", aviso de "Stoppen"), Inicio (la línea), la etiqueta "niet gecontroleerd", textos NL/ES/EN (§6.4), tipos, rutas, permisos de las acciones; `npm run build` + `npm run fuente`; vista previa y diseño | `npm run typecheck`, `npm test` (con `mailbox-model.test.ts`, `reading-model.test.ts`, `i18n.test.ts`, `codigo-muerto`), `test_app_local.py`; `npm run vista-previa:grabar` + `vista-previa:comprobar`, `diseno:capturar` + `diseno:comprobar` | — |
| 13 | Nativa: el papel | `$Roles`, `aislamiento` por papel (`ROLES`, `EXTERNOS`, `motivo_para_no_traer`), `nativo.exigir_correo`, `comprobar-aislamiento --rol correo`, 2 reglas, `Arrancar-Salida-Correo` (no arranca con un lector vivo), `Preparar-Certificados-Correo`, `comprobar.ps1` con el correo, `app_local.PAPELES`, `settings.roles` | `test_instalacion_nativa.py` (pines nuevos y los cambiados a propósito), `test_alcance_v1.py` (`EXTERNOS`), `aislamiento.evaluar("correo", …)`, `pwsh` los analiza | `comprobar.bat` en verde con cinco papeles |
| 14 | Nativa: solo | `ciclo.ps1` (pausa, cerrojo, latido con `Get-PSDrive`, correo, `recalcular --diaria`, lectura), `automatico.ps1` (`-Instalar` con `PT4H`/`PT5M` y la comprobación del usuario, `-Quitar`, `-Pausar`, `-Reanudar`, `-Estado`), `Pausar-Automatico`/`Reanudar-Automatico`/`Tomar-Cerrojo`/`Soltar-Cerrojo` en `comun.ps1`; la pausa en `parar`, `instalar`, `desinstalar` (y quitar tareas), `restaurar`; `iniciar` (la regla de §4.4 y `-EnSegundoPlano` con el dueño del puerto y la rotación de `consola.log`); `serve --solo-errores`; el cerrojo en `leer-facturas`, `comprobar`, `copia`; `correo-configurar` (dos fases) y `correo-certificado` (`-Activar`) con sus `.bat`; `ver-salida` | `test_instalacion_nativa.py` (`SCRIPTS`, ASCII, PS 5.1, "paso 14", sin `iex`/`curl`, los pines de §7.2); `test_lectura_lector.py` (pasos de `ciclo.ps1`); `pwsh`; una prueba de `serve --solo-errores` | Toda la fila "Tareas (nativa)", "La pausa" e "`iniciar.bat`" de §7.4 |
| 15 | Docker | `docker-compose.yml` (§1.3), **`Dockerfile`** (`mkdir`/`chown` de `/correo/estado` y `/correo/entrada`), `docker/ciclo.ps1 -Bucle` con `Docker-Listo`, `automatico.ps1` (`PT0S`, la tarea de bloquear), pausa y cerrojo en `comun.ps1`, `parar`/`restaurar` con la pausa, `iniciar` (la regla de §4.4; `up -d consola salida salida_correo`), `correo-configurar.ps1`, `correo-certificado.ps1` (montando solo `secretos\correo` en `orden`), `ver-salida`, `.gitignore` (`/docker/estado/`), `secretos/LEEME.txt` | `test_entorno_local.py` (los pines de §7.2); `docker compose -f docker/docker-compose.yml config --quiet` (aquí funciona sin demonio); `pwsh` los analiza | `BMS_PROBAR_DOCKER=1 pytest tests/test_entorno_docker.py`; toda la fila "Docker: solo" de §7.4 |
| 16 | e2e | `scripts/simular_correo.py`, `tests/test_simular_correo.py`, `frontend/e2e/correo.spec.ts` | `pytest tests/test_simular_correo.py`; `npm run e2e -- correo.spec.ts procesar.spec.ts screens.spec.ts aurora-paridad.spec.ts` | — |
| 17 | Documentos | §8 entero y el registro | Las pruebas de documentos (`test_instalacion_nativa.py:1990-2050`, `test_contrato_v2.py`, `test_revision_final.py:1325`, `test_panel_busqueda.py:752`); al final `pytest -q`, `npm run typecheck`, `npm test`, `npm run build`, `npm run fuente` | — |

Fuera del repositorio, después del paso 17: la configuración de Microsoft (§2.1, §2.6) y la lista de
§7.4 en el mini PC (acciones del dueño, §11).

---

## 10. Riesgos y alternativas descartadas

### 10.1 Alternativas descartadas

| Alternativa | Por qué no |
| --- | --- |
| **Zapier MCP** (o Power Automate) leyendo el buzón | Un tercero con acceso al buzón y un camino de datos fuera del equipo; sus permisos no se acotan a un buzón y solo lectura con la misma garantía; el modelo con herramientas (MCP) rompe la regla 6. `docs/mcp-setup.md:27-46` ya lo dejó fuera del camino del dinero |
| **IMAP/POP con OAuth** | Necesita `IMAP.AccessAsApp` y `Add-MailboxPermission -AccessRights FullAccess` para la app: **lectura y escritura**, no se puede dejar en solo lectura; otro host (`outlook.office365.com:993`); MIME a mano; errores opacos. Básico desactivado desde 2022 |
| **EWS** | Se retira entre el 1-10-2026 y el 1-4-2027 (MC1447678) |
| **Acceso delegado con código de dispositivo** | Un usuario con licencia, contraseña y MFA; un token de refresco de 90 días que vale lo que la sesión de ese usuario (todo su correo, no solo facturas); el flujo de código de dispositivo es un vector de phishing y muchas directivas de acceso condicional lo bloquean |
| **Webhooks de Graph** (notificaciones de cambios) | Exigen un punto HTTPS público que conteste en 3 s: una entrada desde internet al mini PC. La variante de Event Hubs necesita Azure. El sondeo con delta cada 5 min basta |
| **Secreto de cliente** | Microsoft no lo quiere en producción; una persona lo ve y lo copia; caduca a los 24 meses como mucho. Se queda como reserva solo si `cryptography` no se pudiera fijar |
| **msal** | Unos 8 paquetes nuevos fijados (`requests`, `urllib3`, `certifi` —que se salta el almacén de Windows—, `PyJWT`…) para unas 60 líneas |
| **Application Access Policies** | Legado: "Don't create new App Access Policies" (`docs-ms/New-ApplicationAccessPolicy.md`) |
| **Añadir los hosts de Microsoft a la salida de hoy** | El lector, que tiene la clave de la API, llegaría a Microsoft, y el correo a la API (`salida.py:182-215`: la lista es por proxy) |
| **Una salida con varias listas** (varios `Proxy` en un `servir`) | Posible, pero más código en un módulo con 522 líneas de pruebas; en Docker dos contenedores dan separación de red sin tocar `salida.py`; en la nativa, dos pasadas seguidas bastan |
| **Regla directa al 443 para el correo en la nativa** | El cortafuegos no filtra por nombre y las IP de Microsoft son compartidas: sería "a cualquier sitio por el 443", sin registro por destino |
| **Que lo haga el lector** (sin papel nuevo) | El lector tiene la clave de la API; juntar las dos credenciales y las dos salidas en un programa es lo que la arquitectura separa (`arquitectura.md:236-239`) |
| **Contenedores residentes con bucle** (correo y lector siempre encendidos) | Deja la clave de la API en un contenedor siempre vivo y contradice "el lector solo arranca a propósito" (`docker-compose.yml:8-11`); ningún contenedor puede lanzar otro (sin `docker.sock`) |
| **Dejar los adjuntos en `buzon\facturas`** | En Docker nadie puede escribir ahí (montado `:ro`); el lector los registraría como `carpeta`/`mtime` y la procedencia del correo se perdería para siempre (`extract.py:758-764`; `0001_almacen.sql:259-269`) |
| **Cuarentena purgable** (registrar en el almacén solo al leer o aceptar) | Quitaría a los desconocidos la escritura en la evidencia, pero la fecha de recepción y el id del mensaje solo se fijan bien al llegar (el documento no se puede cambiar, `0001_almacen.sql:259-269`), el lector tendría que leer de fuera del almacén y `orden` llevaría dos almacenes. Con el acuse, los topes diarios (150 PDF, 750 MiB) y el disco vigilado, lo que entra queda acotado y a la vista. Queda para un paso futuro si el volumen lo pidiera (§13, S2) |
| **Abrir los `itemAttachment`** (`$expand` o `$value`) | `$expand` trae el cuerpo del correo adjunto y adjuntos anidados hasta 30 niveles con su `contentBytes` en una sola respuesta (`docs-ms/api-reference_v1.0_api_attachment-get.md:20,383-395`); `$value` es MIME de terceros que habría que analizar. Se pide reenviar el PDF como adjunto normal |
| **Lista de remitentes conocidos** para decidir qué se lee solo | El remitente es falsificable y la regla es que no decide nada; los topes y la pausa por volumen ya acotan el gasto |
| **Leer primero lo más nuevo** | Tras una inundación, una persona aparta la basura en bloque y lo antiguo legítimo se lee en orden; leyendo lo nuevo primero, una factura antigua podría no leerse nunca sola |
| **Bajar y leer "Correo no deseado"** | Es donde está el spam; se apuntan los metadatos y la persona lo pasa a la bandeja en Outlook |
| **Guardar el token** entre rondas | Un secreto más en disco por ahorrar ~288 peticiones al día |
| **Lotes (mitad de precio)** para las nuevas | Hasta 24 h; el dueño quiere las facturas listas. Queda como palanca futura (`costes.md:220-223`) |
| **Leer UBL ya** | Es código determinista nuevo (sin modelo) con su validación; otro paso |

### 10.2 Riesgos

| Riesgo | Qué se hace | Queda |
| --- | --- | --- |
| **Nativa: un fallo en el proceso `correo` ve la base y la clave de la API** (mismo usuario) y las puede sacar por `graph.microsoft.com` a otro inquilino | Docker recomendado para el correo desatendido (D13, §1.7); el código no las abre (pruebas de §7.2); §11 de `instalacion-nativa.md` lo dice claro | Si el dueño elige la nativa, ese riesgo; el usuario aparte para el correo, paso 19 |
| **Robo de la credencial o del token del correo hacia otro inquilino** por `graph.microsoft.com` | Solo el contenedor/papel `correo` la ve; vida corta del token; acceso cortable en un minuto (§2.5) | Inherente a una lista por nombre de host |
| **Permisos de Entra que suman** al ámbito de RBAC (una app con `Mail.Read` de Entra lee todos los buzones) | La guía lo dice en negrita; `correo comprobar` exige `roles` vacío y un 403 en el buzón de control, y falla cerrado | Que el informático no configure el buzón de control: entonces `comprobar` no pasa |
| **Que el token no se emita sin permisos de Graph** | Lo dicen blogs, no Learn | **[comprobar en vivo]** el primer día |
| **Gasto por inundación** | Topes por día, mes, ronda y factura; pausa por volumen; exclusión en bloque; el saldo prepagado sin recarga | Hasta el tope del día (2 USD por defecto) en basura el día de la inundación |
| **Evidencia que no se borra llenada por desconocidos** | 150 PDF y 750 MiB al día como mucho; acuse; espacio libre vigilado (10 GiB) con banda | Hasta 750 MiB al día de contenido ajeno, a la vista; la cuarentena, descartada por ahora (§10.1) |
| **Un PDF que la API no quiere** | Omitido al contar y excluido de la automática (`rechazado_api`); 20 MiB como mucho; los demás siguen | — |
| **Dos documentos malos seguidos con el mismo error al leer** (el freno de "dos iguales seguidos", §5.3) | Para la pasada como `api_no_disponible`, sin excluir; espera creciente; banda a las 4 h | La automática se queda parada hasta que una persona los aparte (en el uso normal es raro: `contar` ya rechaza los PDF malos) |
| **La contraseña de Windows** de la cuenta de las tareas | Usuario aparte con `PasswordNeverExpires`; `-Estado`, `comprobar.bat`, `iniciar.bat` y la banda del ciclo lo dicen | Si alguien la cambia, nada corre hasta volver a `automatico.bat -Instalar` (o `netplwiz` en Docker) |
| **DPAPI con la tarea** (`S4U` no sirve; derecho de inicio por lotes de un usuario estándar) | Tarea con contraseña guardada; `automatico.ps1` lo comprueba y lo dice | **[comprobar en Windows 11]**; reserva: inicio de sesión automático |
| **Docker necesita una sesión abierta** | Inicio de sesión automático del usuario aparte + pantalla bloqueada; Docker Desktop sin actualizarse solo | La contraseña de ese usuario guardada por Windows (LSA); un diálogo de Docker Desktop que nadie ve (lo dice la banda del ciclo) |
| **La migración que rehace dos tablas con claves foráneas** | El orden exacto probado (§3.9), prueba con filas, `foreign_key_check` | — |
| **Bloqueos de la base** (tipar + reglas en una transacción larga, `busy_timeout` 5 s, `almacen/__init__.py:205`) mientras una persona usa la app | 20 facturas por ronda | Medir en el N150 durante el paso; si pasa, leer en horas tranquilas |
| **Carreras con los scripts de siempre** | El cerrojo y la pausa (§4.4); `iniciar.bat` sin parar nada si la consola va bien | — |
| **Delta caducado tras mucho tiempo apagado** | Reinicio con 3 días de margen sobre la última buena; lo repetido se descarta | Lo que llegó antes de esos 3 días si el enlace caducó y la última buena es más vieja (se ve: `retrasado`) |
| **Facturas en "no deseado"** | En "Wacht op jou" hasta que alguien las marca; la persona con acceso completo las pasa a la bandeja y entran; desactivar el filtro (opcional) | Que nadie mire la lista |
| **Certificado caducado** | Ámbar a 60 días, banda desde 30, el mantenimiento del mes, `correo-certificado.bat` | Si nadie lo renueva, no entra nada (falla cerrado, y se ve) |
| **Reloj del equipo** | Error `reloj`; `registrar` no mete fechas del futuro | — |
| **Ventana que parpadea** (Docker) | Un solo PowerShell oculto en bucle | Un parpadeo al iniciar sesión |
| **Proceso hijo de una tarea** (la consola) que muera al acabar la tarea | Límite de 5 min y el vigilante cada 15 | **[comprobar en Windows 11]** |
| **Textos y cuentas que se quedan viejos** ("cuatro programas", "12 reglas", "Alle vier", `PAPELES`, `ver-salida`, "la salida solo al leer") | Lista en §8 y §6.1 | — |
| **El entorno de desarrollo de aquí** tiene `anthropic` 2.8.0 contra el fijado 1.13.0 | No "arreglar" los pines con este entorno; `clasificar_error` lee con `getattr` y se prueba con excepciones hechas a mano | — |

---

## 11. Lo que solo puede hacer o decidir el dueño

1. **Microsoft 365** (él o su informático, unos 45 minutos y hasta 2 horas de espera,
   `docs/correo-m365.md`): el buzón compartido; **el acceso completo de una persona** a ese buzón (para
   ver "Correo no deseado" y pulsar "Geen ongewenste e-mail"); **un buzón de control dedicado** que no
   desaparezca; la app de Entra sin permisos con el certificado subido; el ámbito y el rol de RBAC; y
   pasarle los cuatro datos (§2.1, §2.6).
2. **Docker o nativa en el mini PC.** La recomendación es **Docker** para el correo desatendido (D13,
   §1.7): un fallo en el proceso que lee correo de desconocidos no alcanza la base ni la clave de la
   API. La nativa funciona sin sesión abierta, pero con ese riesgo dicho en §1.5.
3. **La cuenta de Windows de lo automático**: un usuario local estándar aparte (p. ej. «bms») con la
   contraseña sin caducidad (`Set-LocalUser -PasswordNeverExpires $true`, como administrador). Con
   Docker, además, el inicio de sesión automático de ese usuario con la pantalla bloqueada (§4.2, cuatro
   pasos). El dueño sigue trabajando con su cuenta y abre la app en `http://127.0.0.1:8765/app`.
4. **Los topes**: confirmar o cambiar 2,00 USD/día, 25,00 USD/mes, 20 facturas por ronda y 0,50 USD
   por factura (y, si quiere, 150 PDF y 750 MiB al día del correo), y **encender** la lectura automática
   en la app (con `admin`).
5. **El equipo**: "Suspender: nunca" con corriente; encender tras un apagón (BIOS/UEFI); **horas
   activas de Windows Update = el horario de oficina** (p. ej. 07:00-19:00), para que los reinicios
   caigan de noche; Docker Desktop sin actualizaciones automáticas.
6. **El dinero**: saldo prepagado de la API sin recarga automática y una clave solo para esto
   (`docs/costes.md:16-34`).
7. **La lista de §7.4** en el mini PC, una vez: tareas sin sesión, reinicio de noche, contraseña,
   pausa, lectura larga, `comprobar.bat` en verde con cinco papeles, `correo comprobar` en verde, una
   factura de "no deseado" pasada a la bandeja.
8. **El mantenimiento del mes** (`docs/uso-v1.md`): `automatico.bat -Estado`, la lista "Wacht op
   jou", la caducidad del certificado, el saldo; actualizar Windows y Docker Desktop con
   `automatico.bat -Pausar` antes y `-Reanudar` después.
9. Opcional: desactivar el filtro de correo no deseado del buzón de facturas.

## 12. Preguntas abiertas

1. ¿Emite Entra el token sin ningún permiso de Graph (solo RBAC)? Se ve el primer día con
   `correo comprobar`.
2. ¿Qué devuelve Graph al leer un buzón que no existe y está fuera del ámbito: 404 o 403? Decide si
   `control_no_existe` se puede distinguir; si da 403, un buzón de control borrado pasaría la prueba
   sin probar nada, y la guía insiste en que sea uno dedicado.
3. ¿Un usuario estándar puede registrar la tarea "se ejecute o no la sesión" sin que un administrador
   le dé "Iniciar sesión como proceso por lotes", y descifra DPAPI en ella? (Windows 11, mini PC.)
4. ¿El dueño usará la app en el propio mini PC? La consola solo escucha en `127.0.0.1`; usarla desde
   otro ordenador no está diseñado aquí.
5. ¿Lo que lee una persona con su sí debe contar contra el tope del mes? Este diseño dice que no (la 8B
   pedía un tope al mes para la tarea).
6. ¿Cuántos proveedores mandan solo UBL, sin PDF? Decide cuándo se hace el paso del UBL.
7. ¿`Set-MailboxJunkEmailConfiguration -Enabled $false` vale en un buzón compartido? (Exchange, en vivo.)
8. ¿Falla `count_tokens` con el saldo a cero, o solo la lectura? El diseño cubre los dos casos; cambia
   solo en qué paso se ve `saldo`.

---

## 13. Revisión

Tres críticas (seguridad 12 hallazgos, operación 17, viabilidad 15) sobre la versión anterior
(`scratchpad/correo/diseno-v1.md`). Cada hallazgo se comprobó contra el código de `HEAD 76c3ae3`, las
fuentes de Learn guardadas y la skill `claude-api`; la columna "¿Cierto?" dice lo que salió. Los
bloqueantes y mayores confirmados están todos arreglados; de los menores, se adoptaron todos menos los
que dicen "no" con su porqué.

### 13.1 Seguridad

| # | Hallazgo (gravedad) | ¿Cierto? | Qué se hizo |
| --- | --- | --- | --- |
| S1 | Un PDF venenoso bloquea toda lectura (bloqueante) | Sí: `estimar` no captura por PDF (`lectura.py:530-551`) y un error cierra la petición entera con `contar` (`cli.py:732-737`); 25 MiB en base64 ≈ 34,9 MB > 32 MB por petición (skill `claude-api`) | D12; `MAX_PDF` = `MAX_BYTES_API` = 20 MiB (§3.3); `estimar` por PDF con `clasificar_error` (§5.3 paso 4, §5.4, §5.7); motivo `rechazado_api` en `exclusion_automatica`; vale también para `buzon\facturas` y las lecturas de una persona (allí sale "omitido" con su motivo en Procesar, y la automática siguiente lo aparta a "Wacht op jou"); pruebas en §7.1 |
| S2 | Inundación: la bandeja de 2 GiB con limpieza a 45 días y la evidencia sin tope (mayor) | Sí: `documento_sin_delete` (`0001_almacen.sql:270`), ficheros 0444 (`almacen/documentos.py:1-6`) | Acuse: `registrar` borra de la bandeja lo registrado (§3.8 paso 7; `orden` monta `correo_entrada` con escritura, §1.3); topes diarios 150 PDF y 750 MiB con "retenido hasta mañana" sin perder nada (§3.2 paso 4, §3.5); pausa por volumen. **No adoptado**: la cuarentena purgable (§10.1: la fecha y el id del mensaje solo se fijan bien al llegar, y el lector solo lee del almacén); queda en "lo que deben saber los pasos siguientes" |
| S3 | Un mensaje venenoso para el delta para siempre (mayor) | Sí: el punto de reanudación es por página y no había límite por mensaje | Cada mensaje en su `try` con contador persistente en `estado/intentos.json`: al tercero, `error` y sigue (§3.2 paso 8); respuestas JSON leídas por trozos con tope de 4 MiB (§3.1); los `itemAttachment` ya no se expanden (D6) |
| S4 | Nativa: el canal de exfiltración nuevo está infravalorado; la fila "la clave sin red no sirve" es falsa (mayor) | Sí: la salida decide por `host:puerto` (`salida.decidir`, `salida.py:182-215`); `instalacion-nativa.md:386,423` | Fila de §1.5 corregida; §1.6 y §1.7; D13 recomienda Docker; §8 corrige `instalacion-nativa.md:386,423` y su §11. **En parte**: el usuario de Windows aparte para el papel `correo` (tarea propia, permisos nuevos en `Poner-Permisos`, cerrojo fuera de `datos`) queda como paso 19: cambia la instalación entera y no hace falta con Docker |
| S5 | El ciclo de vida del certificado en Docker expone la clave de la API (mayor) | Sí: `anthropic_api_key.txt` vive en `docker/secretos` (`docker-compose.yml:142-144`) y la receta montaba la carpeta entera | Secretos del correo en `docker\secretos\correo\`; las órdenes locales en `orden` montan solo esa subcarpeta; `activar` es local y la comprobación la hace el contenedor `correo` de siempre (§2.4); pin de `test_entorno_local.py`: solo `lector` tiene `anthropic_api_key` y ningún `-v` monta `secretos` salvo `secretos\correo` en `orden` (§7.2) |
| S6 | El `$expand` de `itemAttachment` trae el cuerpo, contra D6 (menor) | Sí (`attachment-get.md:383-395,508-520`) | No se expande ni se baja: `reenvio` (D6, §3.3); `GraphFalso` falla con cualquier `$expand` y la guarda de §7.2 lo busca en el código |
| S7 | `salida_correo` en `red_exterior` llega a la consola (menor) | Sí: `salida` escucha la entrada en `red_exterior` (`docker-compose.yml:64,76`; `salida.py:593-610`) | Red propia `red_exterior_correo` (§1.3); fila en `test_entorno_docker.py`: `salida_correo` no conecta a `salida:8765` |
| S8 | La bandeja valida ficheros pero no carpetas (menor) | Sí, en el diseño anterior | `lstat` de las tres carpetas, `O_DIRECTORY\|O_NOFOLLOW` y `dir_fd`; 2 000 entradas por pasada (§3.8 pasos 1-3) |
| S9 | "No es correo no deseado" no se trae nunca (menor) | Sí: el id inmutable no cambia al mover (`concepts_outlook-immutable-id.md:30`) | Clave (id, carpeta) en la bandeja, en `intentos.json` y en `mensaje_correo` `UNIQUE (graph_id, carpeta)` (§3.4, §3.9); caso en `GraphFalso` |
| S10 | La comprobación de ruta de `nextLink`/`deltaLink` fallaría en producción (menor) | Sí: Learn devuelve `…/me/mailfolders('AQMk…')/messages/delta` (`concepts_delta-query-messages.md:151`) | Se comprueba esquema, host, puerto, sin usuario, `/v1.0/` y final `/messages/delta` (§3.1); fixtures con las formas de Microsoft (§7.1) |
| S11 | El arranque de la consola en segundo plano acepta cualquier programa en el puerto (menor) | Sí: hoy `iniciar.ps1:25-29` se niega, el vigilante no | `-EnSegundoPlano` mira quién escucha (`Get-NetTCPConnection` + `Procesos-De "consola"`) y, si es otro, no arranca y lo dice (§4.2) |
| S12 | Sin freno ante una inundación; lo antiguo primero; remitente sin "no comprobado" (menor) | Sí | Pausa `volumen` hasta que una persona la quite (§5.2); `excluir_de_lectura_automatica` en bloque (§5.1, §6.1); etiqueta "niet gecontroleerd" en los tres idiomas con su ayuda (§6.4). **No**: leer lo nuevo primero (§10.1) |

### 13.2 Operación

| # | Hallazgo (gravedad) | ¿Cierto? | Qué se hizo |
| --- | --- | --- | --- |
| O1 | Cualquier fallo de la API en una automática excluye las facturas para siempre (mayor) | Sí: todo error es "fallida" y la pasada sigue (`extract.py:656-666`; `lectura.py:818-819`); sin saldo es el techo normal (`docs/costes.md:17-20`) | Fallos clasificados (§5.3): `clave_rechazada`, `saldo` (402, 429 de límite de gasto, 400 "credit balance"), `api_no_disponible`; paran la pasada sin excluir y sin contar como fallo del documento; exclusión `fallo` solo a la segunda falla del documento; textos NL/ES/EN y banda |
| O2 | La app dice "Aan" mientras la automática falla (mayor) | Sí | `parada: 'fallo'` con `motivo_codigo`, `desde` y `proximo_intento` (§5.2, §6.2); espera creciente 1 → 24 h; banda si hay elegibles esperando más de 4 h (§6.1) |
| O3 | Lo desatendido cuelga del inicio de sesión del dueño y nadie se entera (mayor) | Sí; `instalacion-nativa.md:436-450` ya describe el usuario aparte | Usuario aparte con `PasswordNeverExpires` en las dos variantes (§4.2); `-Estado`, `comprobar.bat` e `iniciar.bat` leen `Get-ScheduledTaskInfo` (0x8007052E) y `ciclo.json`; banda si el ciclo no corre desde hace 30 min (`estado_ciclo`, §3.9); pasos del inicio de sesión automático y la tarea de bloquear; cambio de contraseña en §7.4 |
| O4 | Parar, actualizar, desinstalar y restaurar no pausan la automatización (mayor) | Sí (`parar.ps1:9-12`; `instalar.ps1:406,420-425`; `desinstalar.ps1:68`; `restaurar.ps1:28-29`) | `Pausar-Automatico`/`Reanudar-Automatico` (§4.4) llamados antes del primer `Parar-Rol` en cada uno; `parar.bat` lo dice; el vigilante y el ciclo respetan la pausa; actualizar Docker Desktop con `-Pausar` (§4.2, §11); pines (§7.2) |
| O5 | El límite de 1 h de la tarea es menor que una lectura y su corte puede matar la salida de un lector vivo (mayor) | Sí (`$VidaSalidaLectura`, `comun.ps1:33`; `PLAZO_RESPUESTA`, `lectura.py:85`; `Parar-Rol "salida"` en `comun.ps1:262`) | Límite de 4 h (§4.2); `Arrancar-Salida-Correo` no arranca con un lector vivo y la ronda se salta con `ocupado` (§1.4, §4.1); Docker `PT0S`; lectura de más de 1 h en §7.4 |
| O6 | `iniciar.bat` puede colgarse 15 min tras el cerrojo (mayor) | Sí (`windows/iniciar.ps1:21`; `docker/iniciar.ps1:20`) | Una regla para las dos variantes (§4.4): si la consola nuestra ya contesta con la base pedida, solo abre Edge; si no, espera el cerrojo como mucho 1 minuto y lo dice |
| O7 | Lo que necesita a una persona se pierde de vista; el arreglo de "no deseado" no funciona (mayor) | Sí: solo los 10 últimos; nadie tenía acceso al buzón; el id no cambia al mover | `esperan_persona` con correos y documentos, hasta que una persona marque el correo (`correo_atendido`, `marcar_correo_atendido`); número en Inicio (§6.1, §6.2); acceso completo de una persona (§2.1 paso 2); clave (id, carpeta); los adjuntos que fallan se reintentan 24 h (§3.2 paso 7) |
| O8 | Las horas activas de Windows Update, al revés (mayor) | Sí: son las horas en que Windows no reinicia | Horas activas = horario de oficina (§4.5, §11); reinicio de noche en §7.4 |
| O9 | El bucle de Docker sale en vez de esperar; la tarea sin límite fijado (menor) | Sí: `Comprobar-Docker` llama a `Fallar`, que hace `exit 1` (`docker/comun.ps1:14-30`) | `Docker-Listo` que devuelve verdadero/falso y espera 10 min; `try`/`catch` por vuelta; `PT0S`, `RestartCount`, vigilante cada 15 min (§4.2); pin (§7.2) |
| O10 | En Docker el disco se mide mal, y solo se vigila la bandeja (menor) | Sí: el contenedor ve el disco virtual de WSL2 | El ciclo mide con `Get-PSDrive` en las dos variantes, `ciclo latido --disco-libre` (§4.1), `estado_ciclo`, banda `disco`, 10 GiB (§3.5, §6.1) |
| O11 | `reloj` falta en la lista cerrada; una fecha futura pierde la fecha para siempre (menor) | Sí | `reloj` y `control_no_existe` en la lista cerrada (§3.7, §6.2); una fecha más de 5 min en el futuro no se registra todavía (§3.8 paso 4) |
| O12 | Un buzón de control que desaparece parece un fallo de seguridad (menor) | En parte: lo que devuelve Graph es **[comprobar en vivo]** | `control_no_existe` con su texto (§2.3, §6.4); buzón de control dedicado (§2.1 paso 3); pregunta abierta 2 |
| O13 | El aviso del certificado llega tarde y la renovación en Docker no está escrita (menor) | Sí | Ámbar a 60 días, banda desde 30, mantenimiento del mes (§2.4, §6.1); la renovación paso a paso para las dos variantes, con la pasada de correo y el aislamiento en la nativa (§2.4) |
| O14 | `correo-configurar` no está especificado (menor) | Sí | Dos fases, qué pide y cómo lo valida, sin rehacer nunca el certificado, `permiso` normal las dos primeras horas, la nota para el informático y su tiempo (§2.6, §2.1) |
| O15 | Errores breves de Microsoft ponen "Werkt niet" al momento (menor) | Sí | `limitado` y `sin_conexion` son `retrasado` hasta 30 minutos (§6.2) |
| O16 | El tope diario para antes de lo que parece (menor) | Sí | El texto dice lo que pasa ("menos de $0,50 para una factura") y la API da `queda_hoy_usd_micro` (§5.2, §6.4). **No** se cambia la regla: con lo que queda por debajo de `max_por_documento`, `siguiente` contaría gratis cada 5 minutos para no poder leer casi nada, con una petición nueva cada vez |
| O17 | En la nativa, el registro de la consola crece sin límite (menor) | Sí (`serve.py:1155-1159`; `comun.ps1:193-201`) | `serve --solo-errores` y rotación a 10 MB al arrancar desde el vigilante (§4.2, §5.7) |

### 13.3 Viabilidad

| # | Hallazgo (gravedad) | ¿Cierto? | Qué se hizo |
| --- | --- | --- | --- |
| V1 | Docker: `correo` no puede escribir sus volúmenes, que serían de root (bloqueante) | Sí: la imagen solo crea y da a `bms` `/datos /buzon /registro` (`Dockerfile:44-45`), y corre como 10001 (`:47`) | `mkdir`/`chown` de `/correo/estado` y `/correo/entrada` en el `Dockerfile` (§1.3, paso 15); pin estático en `test_entorno_local.py` (§7.2); escritura como 10001 en `test_entorno_docker.py` |
| V2 | Un PDF de 25 MiB o con demasiadas páginas bloquea la automática (mayor) | Sí (como S1) | Como S1 |
| V3 | La expansión de `itemAttachment` trae el cuerpo (mayor) | Sí (como S6) | Como S6 |
| V4 | La comprobación de ruta de los enlaces de Graph (mayor) | Sí (como S10) | Como S10 |
| V5 | "Stoppen" en una automática se deshace a los 5 minutos (mayor) | Sí | "Stoppen" pausa la automática hasta las 00:00 (fila `pausa`, motivo `persona`), con "Weer aanzetten" (§5.3, §5.2, §6.1); pruebas en §7.1 |
| V6 | El límite de 1 h mata las lecturas pedidas que ahora lanza el ciclo; Docker a las 72 h (mayor) | Sí (como O5 y O9) | Como O5 y O9; los dos valores fijados por pines |
| V7 | Docker: `activar` no tiene dónde correr sin exponer la clave de la API (mayor) | Sí (como S5) | Como S5: `activar` local en `orden` con solo `secretos\correo` y comprobación con el `correo` de siempre. **No** se quita la rotación con "siguiente": Entra admite dos certificados a la vez y así se renueva sin un hueco sin correo y con vuelta atrás (`volver`) |
| V8 | El cerrojo de `correo traer` se puede quedar tras un corte (mayor) | Sí: un "crear si no existe" sobrevive al proceso | Cerrojo del sistema (`fcntl.flock` / `msvcrt.locking`) que se suelta solo (§3.2 paso 1); prueba con un fichero que se quedó (§7.1) |
| V9 | Migración 0019: `defer_foreign_keys` solo funciona apuntando a la tabla temporal (menor) | Sí: se volvió a correr `scratchpad/correo/viabilidad/prueba_migracion.py` | El orden exacto, con `REFERENCES solicitud_lectura_nueva(id)` y los nombres de disparadores e índices de 0018 (§3.9 punto 3) |
| V10 | Las tablas nuevas tienen que entrar en `test_almacen` y en `_poblar` (menor) | Sí (`test_almacen.py:61-67,383-410`) | §3.9 (último párrafo) y paso 2 del plan |
| V11 | `fijar_windows.py` no sabe elegir la rueda de `cryptography` (menor) | Sí: dos `abi3` válidas y se para (`scripts/fijar_windows.py:139-144`) | `elegir_rueda` prefiere la `abi3` de `cp3X` más alto ≤ la versión, con su prueba; `binarias` + `cryptography`, `cffi` (paso 6) |
| V12 | `servicios` no tiene tipo booleano (menor) | Sí (`servicios.py:84-89`) | `activa` como `ENTERO` 0/1 (§5.1, §6.2) |
| V13 | Otros scripts paran cosas a espaldas del ciclo (menor) | Sí (`parar.ps1:9-10`; `depends_on`, `docker-compose.yml:86-88`) | Como O4; §1.3 dice que `compose run` levanta servicios y por qué `parar` pausa; `-EnSegundoPlano` mira la pausa sin esperar el cerrojo; la consola no espera 15 min (regla de `iniciar`, §4.4) |
| V14 | Huecos de verificación aquí para los pasos de scripts y app (menor) | Sí: sin `pwsh` ni demonio; `docker compose config --quiet` sí funciona sin demonio | Paso 0 (`pwsh` como en `registro.md:6699`); pines estáticos del `Dockerfile` y de las tareas; vista previa y diseño en el paso 12; `screens.spec.ts` y `aurora-paridad.spec.ts` en el 16; columna "Solo en Windows / inquilino" en el plan |
| V15 | Contradicciones con documentos que no estaban como desviaciones (menor) | Sí (`arquitectura.md:92-95`; `app-local.md:1484-1487`) | Desviaciones 1 y 2 del registro (§8.1) y los cambios de `arquitectura.md` §2 y `app-local.md` (§8); el tope al mes de la 8B se quita a propósito (pregunta abierta 5) |
| — | (en el veredicto) `aurora.settings.roles` no existe: es `settings.roles` | Sí (`nl.ts:856,875`) | Corregido en §6.1 y §6.4 |

### 13.4 Lo que no se tocó

Lo que las críticas dieron por bueno y se volvió a mirar: los topes de gasto son duros
(`lectura.py:773-793` y `salida_que_cabe`); la comprobación de aislamiento va atada a la credencial de
cada pasada (`aislamiento.motivo_para_no_leer_de`, `aislamiento.py:492-514`); las descargas no pueden
meter nada en `Content-Disposition` (`serve._nombre_de_descarga`, `serve.py:436-442`); nada analiza los PDF en local; `tzdata` está
fijado para Windows; los registros de Docker rotan (`docker-compose.yml:35-37`); un corte de internet
no hace fallar el aislamiento; SQLite va en WAL; la carga en el N150 es pequeña.
