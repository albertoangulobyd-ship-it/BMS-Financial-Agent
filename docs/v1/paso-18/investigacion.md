# Correo de facturas desde Microsoft 365: investigación (correo:investigar)

Fecha: 2026-11-23. Solo lectura del repositorio (HEAD 76c3ae3); nada modificado ni commiteado.

## 0. Cómo se ha investigado (y qué no se ha podido abrir)

- `learn.microsoft.com` **no se puede abrir desde esta sesión** (WebFetch: `ENOTFOUND`; curl por el proxy: `CONNECT 403`).
  Tampoco `mikecrowley.us`. Para leer Learn sin abrirlo se han bajado **las fuentes markdown de las mismas páginas**
  desde `raw.githubusercontent.com` (repos públicos de Microsoft de los que se publica Learn). Están en
  `scratchpad/correo/docs-ms/` (carpeta de trabajo de la sesión; no está en el repositorio):
  - cmdlets de Exchange: `MicrosoftDocs/office-docs-powershell/main/exchange/exchange-ps/ExchangePowerShell/*.md`
  - Microsoft Graph: `microsoftgraph/microsoft-graph-docs-contrib/main/...`
  - Entra: `MicrosoftDocs/entra-docs/main/docs/identity-platform/...`
  - Paquetes PyPI (solo leídos con grep, sin ejecutar): msal 1.39.0 y truststore 0.10.5 en `pkg-msal/`, `pkg-truststore/`.
- La página conceptual de Exchange "RBAC for Applications" (`learn.microsoft.com/exchange/permissions-exo/application-rbac`)
  **no tiene fuente pública en GitHub**: lo que se dice de ella viene de los extractos de WebSearch (marcado como tal).
- Si alguien quiere comprobarlo leyendo las páginas: hay que permitir `learn.microsoft.com` en la red de la sesión.

URL de Learn equivalentes a cada fuente (para citar en docs):

| Tema | URL |
|---|---|
| RBAC for Applications | https://learn.microsoft.com/exchange/permissions-exo/application-rbac |
| Application Access Policies (legacy) | https://learn.microsoft.com/exchange/permissions-exo/application-access-policies |
| Graph: limitar acceso a buzones (ahora muestra RBAC for Applications) | https://learn.microsoft.com/graph/auth-limit-mailbox-access |
| Test-ServicePrincipalAuthorization | https://learn.microsoft.com/powershell/module/exchangepowershell/test-serviceprincipalauthorization |
| New-ServicePrincipal | https://learn.microsoft.com/powershell/module/exchangepowershell/new-serviceprincipal |
| New-ManagementScope | https://learn.microsoft.com/powershell/module/exchangepowershell/new-managementscope |
| New-ManagementRoleAssignment | https://learn.microsoft.com/powershell/module/exchangepowershell/new-managementroleassignment |
| New-ApplicationAccessPolicy | https://learn.microsoft.com/powershell/module/exchangepowershell/new-applicationaccesspolicy |
| Credenciales de app (secreto/certificado) | https://learn.microsoft.com/entra/identity-platform/how-to-add-credentials |
| Aserción de certificado (JWT) | https://learn.microsoft.com/entra/identity-platform/certificate-credentials |
| Client credentials grant | https://learn.microsoft.com/entra/identity-platform/v2-oauth2-client-creds-grant-flow |
| Buenas prácticas de registro de apps | https://learn.microsoft.com/entra/identity-platform/security-best-practices-for-app-registration |
| Vida de access tokens | https://learn.microsoft.com/entra/identity-platform/access-tokens |
| Vida de refresh tokens | https://learn.microsoft.com/entra/identity-platform/refresh-tokens |
| message: delta | https://learn.microsoft.com/graph/api/message-delta |
| Delta de mensajes (guía) | https://learn.microsoft.com/graph/delta-query-messages |
| Delta (visión general, caducidad) | https://learn.microsoft.com/graph/delta-query-overview |
| Listar mensajes | https://learn.microsoft.com/graph/api/user-list-messages |
| Listar adjuntos | https://learn.microsoft.com/graph/api/message-list-attachments |
| Obtener adjunto | https://learn.microsoft.com/graph/api/attachment-get |
| fileAttachment / itemAttachment / referenceAttachment | https://learn.microsoft.com/graph/api/resources/fileattachment (…/itemattachment, …/referenceattachment) |
| MIME de un mensaje | https://learn.microsoft.com/graph/outlook-get-mime-message |
| IDs inmutables | https://learn.microsoft.com/graph/outlook-immutable-id |
| Throttling (límites por servicio) | https://learn.microsoft.com/graph/throttling-limits |
| Throttling (Retry-After) | https://learn.microsoft.com/graph/throttling |
| Webhooks de Graph | https://learn.microsoft.com/graph/change-notifications-delivery-webhooks |
| Permisos de Graph | https://learn.microsoft.com/graph/permissions-reference |
| IMAP/POP/SMTP con OAuth | https://learn.microsoft.com/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth |
| Fin de basic auth en EXO | https://learn.microsoft.com/exchange/clients-and-mobile-in-exchange-online/deprecation-of-basic-authentication-exchange-online |
| Límites de Exchange Online (buzón compartido 50 GB) | https://learn.microsoft.com/office365/servicedescriptions/exchange-online-service-description/exchange-online-limits |

---

## 1. Acceso app-only a UN buzón: RBAC for Applications (recomendado) frente a Application Access Policies

### Qué recomienda Microsoft hoy

- **RBAC for Applications** es el mecanismo vigente. La página de Learn dice que "extiende el modelo RBAC de Exchange Online y
  **reemplaza** a las Application Access Policies" (extracto de WebSearch de application-rbac).
- **Application Access Policies (AAP)**: ya **legacy**. La ayuda del cmdlet dice literalmente:
  > "App Access Policies are replaced by Role Based Access Control for Applications. [...] **Don't create new App Access
  > Policies** as these policies will eventually require migration to Role Based Access Control for Applications."
  (`docs-ms/New-ApplicationAccessPolicy.md`, sección SYNOPSIS, bloque IMPORTANT).
  La página conceptual se titula ahora "Application Access Policies (legacy)" y dice que "se anunciará la deprecación en el
  futuro". **No hay fecha de retirada anunciada** (a septiembre de 2026, según un blog de migración de julio-2026 y un toolkit
  de GitHub; no he encontrado ningún aviso de Message Center con fecha en oct-nov 2026). El cambio a "replaced / no crear
  nuevas" se publicó en la documentación hacia **agosto de 2025** (blog Icewolf, 2025-12-03). Cronología: vista previa de RBAC
  for Applications en dic-2022 (Tech Community), con el plan declarado de deprecar AAP tras la GA.
- La propia página de Graph `graph/auth-limit-mailbox-access` (que antes explicaba AAP) hoy se titula "Role Based Access
  Control for Applications in Exchange Online".
- Única excepción documentada a favor de AAP: **AutoDiscover** no funciona con roles RBAC de aplicación. No nos afecta (Graph
  no usa AutoDiscover).
- Diferencias conocidas al migrar (blogs, no Microsoft): AAP tenía `DenyAccess`, RBAC no; los ámbitos por grupo no siguen
  grupos anidados. Para un único buzón no importa.

### El punto crítico: el consentimiento en Entra suma, no se recorta

- RBAC for Applications y los permisos de aplicación consentidos en Entra **se suman** (unión). Learn: si el service
  principal tiene `Mail.Read` concedido en Entra ID y además un `Mail.Read` con ámbito en RBAC, "es importante que **quite la
  asignación de Mail.Read de Microsoft Entra ID**"; el ejemplo de Learn muestra el permiso de Entra llegando a un buzón que el
  ámbito RBAC excluye (extracto de WebSearch de application-rbac).
- Por tanto: **la app de Entra NO debe tener ningún permiso de aplicación `Mail.*` (ni `Mail.ReadBasic.All`, ni `Mail.ReadWrite`,
  ni `Mail.Send`, ni `full_access_as_app`) consentido.** El permiso de Graph `Mail.Read` de aplicación es literalmente "Read mail
  in **all mailboxes**" (`docs-ms/concepts_permissions-reference.md:4862-4869`).
- Con cero permisos de Graph, el token `client_credentials` con `scope=https://graph.microsoft.com/.default` se emite igual (sin
  claim `roles`) y Exchange autoriza por RBAC. Varios blogs (Practical365, Cronofy "RBAC without tenant-wide permissions") lo
  confirman; **no lo he podido leer en Learn**: confianza media-alta, se valida con la prueba de la sección "Probar".
- Quitar también el permiso delegado `User.Read` que el portal añade por defecto: no hace falta.

### Roles de aplicación relevantes (Exchange)

`Application Mail.Read` (cubre mensajes y adjuntos en Graph), `Application Mail.ReadBasic` (sin cuerpo ni **adjuntos**: no
sirve), `Application Mail.ReadWrite`, `Application Mail.Send`, `Application MailboxSettings.Read`, `Application Exchange Full
Access`, `Application EWS.AccessAsApp`… Cubren **Graph y EWS**; **no IMAP/POP** (esos van por `Add-MailboxPermission`).
Para este proyecto: **solo `Application Mail.Read`**.

### Pasos exactos (una vez, desde un PC de administración, no desde la app)

Requisitos: rol Exchange Administrator (o Global Admin) y el módulo `ExchangeOnlineManagement` v3.

```powershell
# 0. El buzón (compartido, sin licencia; ver sección 2). Placeholder: facturen@<dominio>
New-Mailbox -Shared -Name "Facturen" -DisplayName "Facturen" -PrimarySmtpAddress "facturen@<dominio>"

# 1. Entra (portal): App registrations > New registration, "Accounts in this organizational directory only",
#    sin redirect URI. En "Certificates & secrets" subir el .cer (parte pública). En "API permissions":
#    quitar User.Read y NO añadir ni consentir nada.
#    Anotar: Application (client) ID  y, en Enterprise applications (¡no en App registrations!), el Object ID.

Connect-ExchangeOnline

# 2. Puntero al service principal en Exchange (AppId = client id; ObjectId = Object ID de *Enterprise applications*)
New-ServicePrincipal -AppId "<client-id>" -ObjectId "<enterprise-app-object-id>" -DisplayName "BMS lector de facturas"

# 3. Ámbito que contiene exactamente ese buzón
New-ManagementScope -Name "BMS-buzon-facturas" -RecipientRestrictionFilter "PrimarySmtpAddress -eq 'facturen@<dominio>'"
#    Comprobar que el filtro da UNO y solo uno:
Get-Recipient -RecipientPreviewFilter (Get-ManagementScope "BMS-buzon-facturas").RecipientFilter

# 4. Asignar el rol de solo lectura con ese ámbito
New-ManagementRoleAssignment -Name "BMS-facturas-MailRead" -App "<enterprise-app-object-id>" `
    -Role "Application Mail.Read" -CustomResourceScope "BMS-buzon-facturas"

# 5. Probar (el test se salta la caché)
Test-ServicePrincipalAuthorization -Identity "<client-id>" -Resource "facturen@<dominio>"   # InScope = True
Test-ServicePrincipalAuthorization -Identity "<client-id>" -Resource "<otro buzón>"          # InScope = False
Test-ServicePrincipalAuthorization -Identity "<client-id>" | Format-Table                     # solo 1 fila: Application Mail.Read
```

Fuentes de la sintaxis: `New-ServicePrincipal -AppId <String> -ObjectId <String>` (`docs-ms/New-ServicePrincipal.md`, SYNTAX;
`-ServiceId` "is being deprecated. Use the ObjectId parameter instead"; el ObjectId es "The Object ID property from Enterprise
applications"); `New-ManagementRoleAssignment ... -App <ServicePrincipalIdParameter> [-CustomResourceScope ...]`
(`docs-ms/New-ManagementRoleAssignment.md:22-24`, `-App` en :196-202: "the ObjectId GUID value from the output of the
Get-ServicePrincipal cmdlet"; con `-App` solo roles de aplicación, :276); `-RecipientRestrictionFilter` en OPATH
(`docs-ms/New-ManagementScope.md:205-216`). Alternativa al filtro: `-RecipientAdministrativeUnitScope` con una unidad
administrativa de Entra que solo contenga ese buzón (más piezas; el filtro basta).

`Test-ServicePrincipalAuthorization -Identity <sp> [-Resource <buzón>]`: devuelve RoleName / GrantedPermissions /
AllowedResourceScope / ScopeType / **InScope** (True/False; "Not Run" sin `-Resource`) (`docs-ms/Test-ServicePrincipalAuthorization.md`,
ejemplos 1 y 2). **Ojo: solo ve lo concedido en Exchange RBAC, no lo consentido en Entra**; lo de Entra se mira en Enterprise
applications > Permissions (o `Get-MgServicePrincipalAppRoleAssignment`): debe salir vacío.

### Caché

Learn: los cambios de permisos de app tardan **entre 30 minutos y 2 horas** (30 min si la app no ha llamado; hasta 2 h si está
activa); "the test command bypasses this cache" (extractos de WebSearch de application-rbac / auth-limit-mailbox-access).

### Probar de verdad (además del cmdlet), tras la caché

1. `GET https://graph.microsoft.com/v1.0/users/facturen@<dominio>/mailFolders/inbox/messages?$top=1&$select=id` → 200.
2. Mismo GET contra otro buzón del tenant → **403** (ErrorAccessDenied).
3. `POST /users/facturen@<dominio>/sendMail`, `PATCH /users/.../messages/{id}` (`isRead`), `POST .../move`, `DELETE` → **403**
   (prueba de que es solo lectura).
4. `GET /users` → 403 (sin permisos de directorio).
Estas pruebas encajan como "comprobar" del instalador (patrón de `src/bms_agent/aislamiento.py`, que ya prueba que lo prohibido
recibe un no: `PROHIBIDOS_POR_EL_PROXY` en :108).

---

## 2. Buzón compartido sin licencia

- **Funciona** con Graph app-only: un buzón compartido se direcciona como cualquier usuario,
  `/users/{upn-o-id}/mailFolders/inbox/messages`, `/users/{id}/messages/{id}/attachments` (Microsoft Q&A
  1406369/1411017; la respuesta de Q&A recomienda justo RBAC for Applications con ámbito al buzón compartido).
- **Licencia**: no necesita mientras ocupe **≤ 50 GB** y no tenga archivo/retención (Exchange Online limits). Para facturas
  PDF sobra (50 GB ≈ cientos de miles de facturas). Nadie inicia sesión en él (la cuenta queda deshabilitada para sign-in), lo
  que elimina el flujo delegado y su contraseña.
- Los cambios de licencias de 2026 son de **EWS** (bloqueo de EWS por licencia desde 1-mar-2026, retirada de EWS desde
  1-oct-2026, MC1447678), **no de Graph** ni del buzón compartido.
- Quien lo administre desde Outlook necesita su propia licencia y permiso FullAccess sobre el buzón (eso es de la persona, no de
  la app).
- Práctico: sin reglas de bandeja en ese buzón (para que todo caiga en Inbox) y mirar de vez en cuando "Correo no deseado"
  (la app no puede mover nada; ver 4).

---

## 3. Credenciales de cliente: certificado frente a secreto; hosts

### Qué dice Microsoft

- Secreto: "Client secret lifetime is limited to two years (**24 months**) or less. You can't specify a custom lifetime longer
  than 24 months." "Microsoft recommends that you set an expiration value of **less than 12 months**."
  (`docs-ms/entra_how-to-add-credentials.md:52-53`).
- "Client secrets are less secure than certificate or federated credentials and therefore **should not be used in production**"
  (`docs-ms/entra_how-to-add-credentials.md:46`); certificado = "the recommended credential type" (:31).
- Buenas prácticas: managed identity o federación si se puede; si no, **certificado**; "Don't use password credentials";
  certificado de CA mejor que autofirmado, pero "self-signed certificates are still preferred over passwords"
  (`docs-ms/entra_security-best-practices-for-app-registration.md:55-58`).
- Managed identity / workload identity federation no aplican a un mini PC sin Azure (Azure Arc sería meter un agente que lanza
  procesos y habla con muchos endpoints: descartado).
- El certificado se sube como `.cer/.pem/.crt` (solo parte pública); el portal **no** limita su validez (sí puede limitarla una
  "application management policy" del tenant si se configura).

### Aserción JWT (sin MSAL)

Formato actual en Learn (`docs-ms/entra_certificate-credentials.md`, "Assertion format"):
- Cabecera: `alg` = **PS256**, `typ` = JWT, `x5t#S256` = base64url del SHA-256 del DER del certificado.
- Claims: `aud` = `https://login.microsoftonline.com/{tenantId}/oauth2/v2.0/token`, `iss` = `sub` = client id, `jti` = GUID
  nuevo, `nbf`/`iat` = ahora, `exp` = 5-10 min después.
- Firma con **PSS padding**. Se manda como `client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer` +
  `client_assertion=<JWT>` en lugar de `client_secret` (`docs-ms/entra_v2-oauth2-client-creds-grant-flow.md:173-204`).
- RS256 con `x5t` (SHA-1) sigue funcionando: MSAL 1.39.0 usa PS256+x5t#S256 y solo cae a RS256+x5t para ADFS
  (`pkg-msal/x/msal/application.py:980-990`).

Dificultad en Python: la **biblioteca estándar no firma RSA**. Hace falta `cryptography` (RSA-PSS SHA-256, MGF1 SHA-256, sal
de 32 bytes = longitud del hash, que es lo que pide JWS PS256). Con `cryptography` el JWT se arma a mano en ~30 líneas
(base64url + json + `private_key.sign(..., padding.PSS(...), hashes.SHA256())`); PyJWT no es necesario. `cryptography` 50.0.2
trae ruedas abi3 para Windows x64 y manylinux y depende de `cffi` → `pycparser`. Ninguno de los tres está hoy en los
requisitos fijados (`docker/requirements.txt:8-41`, `windows/requirements-windows.txt:18-50`): habría que añadirlos con hash.
Alternativa en la variante nativa: clave no exportable en el almacén de certificados de Windows y firma con CNG
(`NCryptSignHash`, `BCRYPT_PAD_PSS`) vía ctypes; más fuerte (la clave nunca está en un fichero) pero mucho más código y no sirve
para Docker. Recomendación: `cryptography` y la clave privada PEM guardada como ya se guarda la de Anthropic (DPAPI en nativo,
`windows/clave.ps1:7`; Docker secret en Docker, `docker/docker-compose.yml:101-103`).

Si se elige secreto (más simple, sin dependencias): caduca como máximo a 24 meses (recomendado <12), y viaja en cada petición
de token. Microsoft lo desaconseja para producción. Para un buzón solo-lectura con ámbito a un buzón el riesgo es limitado,
pero el proyecto ya cuida secretos con DPAPI/Docker secrets y el coste del certificado es una dependencia; mi recomendación es
**certificado** (2 años de validez autofirmado, renovación con aviso en la app 30 días antes).

### Tokens

- Token app-only: vida aleatoria de **60-90 min** (media 75) (`docs-ms/entra_access-tokens.md:54`). Cachearlo en memoria hasta
  `expires_in` menos un margen; no pedir uno por ciclo de sondeo.
- Autoridad **del tenant** (`/{tenant-id}/oauth2/v2.0/token`), no `/common`.
- El cuerpo de la petición de token (secreto o aserción) y el `Authorization: Bearer` nunca a un log ni a un mensaje de error
  (regla 11, `docs/arquitectura.md:139`). Los errores de Entra (`AADSTS...`) se pueden registrar: no llevan el secreto.

### Hosts para la lista blanca de la salida

- `login.microsoftonline.com:443` (token; MSAL también hace ahí su "instance discovery").
- `graph.microsoft.com:443` (API; los `@odata.nextLink`/`@odata.deltaLink` son de este mismo host; aun así validar el host
  antes de seguirlos).
- **Nada más** en el camino normal. Revocación (CRL/OCSP: `crl.microsoft.com`, `oneocsp.microsoft.com`, `ocsp.digicert.com`…):
  Python/OpenSSL **no comprueba revocación** por defecto y `truststore` en Windows solo la pide si el contexto SSL lleva
  `VERIFY_CRL_CHECK_*` (`pkg-truststore/x/truststore/_windows.py:366-369`), así que no hace falta abrirlos. Riesgo residual: si
  Windows tuviera que descargar un intermedio/raíz que falte (AIA, `ctldl.windowsupdate.com`), fallaría el TLS; los servidores
  de Microsoft mandan la cadena completa y las raíces (DigiCert G2 / Microsoft RSA 2017) vienen en Windows.
- No hacen falta `outlook.office365.com` (eso es EWS/IMAP) ni `*.sharepoint.com` (solo para seguir referencias a OneDrive, que
  no se siguen).

Implicación para el diseño (no es de esta tarea, solo aviso): hoy la salida tiene **una** lista para un solo escuchador
(`src/bms_agent/salida.py:65` `PERMITIDOS_POR_DEFECTO = ("api.anthropic.com:443",)`; `--escuchar`/`--permitir` en
`src/bms_agent/cli.py:3445-3450`; en Docker `--permitir api.anthropic.com:443` en `docker/docker-compose.yml:62`). Añadir ahí
Graph dejaría al lector (que tiene la clave de Anthropic) llegar a Graph, y al lector de correo llegar a Anthropic. Lo limpio
es una segunda salida (otro escuchador/puerto con su propia lista: login+graph) solo para el componente de correo. En nativo,
la salida solo vive durante una pasada y con credencial al azar (`salida.py:35-45`, `windows/leer-facturas.ps1:81`); un sondeo
cada pocos minutos pide una salida de vida larga o una por ciclo.

---

## 4. Leer lo nuevo, solo lectura, y sacar los PDF

### Delta sobre la carpeta (recomendado)

```
GET https://graph.microsoft.com/v1.0/users/{id}/mailFolders/inbox/messages/delta
    ?changeType=created
    &$select=id,internetMessageId,receivedDateTime,hasAttachments,subject,from
Prefer: odata.maxpagesize=50, IdType="ImmutableId"
```
- Ronda: seguir `@odata.nextLink` hasta recibir `@odata.deltaLink`; guardar **la URL entera** del deltaLink; la siguiente ronda
  empieza por ella (`docs-ms/api-reference_v1.0_api_message-delta.md`, Query parameters). Los parámetros solo se ponen en la
  primera petición; van codificados en el token.
- Soporta `$select`, `$top`, `$expand`; `$filter` solo `receivedDateTime ge|gt {v}` (y con `$filter` devuelve **como mucho
  5.000** mensajes); `$orderby` solo `receivedDateTime desc`; sin `$search` (`docs-ms/concepts_delta-query-messages.md`,
  "Use query parameters").
- `changeType=created|updated|deleted` filtra el tipo de cambio. Aun así puede llegar `@removed` y cambios de leído/no leído:
  hay que tolerarlos (nota del mismo fichero).
- Permisos: mínimo `Mail.ReadBasic.All` (app) para la delta (`docs-ms/perm_message-delta.md`), pero **los adjuntos exigen
  `Mail.Read`** (`docs-ms/api-reference_v1.0_api_message-list-attachments.md`, tabla de permisos). Con RBAC:
  `Application Mail.Read`.
- Primera sincronización: devuelve todo lo que haya en la carpeta. Para no leer el histórico, en la primera petición
  `$filter=receivedDateTime ge {fecha de alta}` (límite 5.000).
- **Caducidad del deltaLink**: para Outlook "el límite superior no es fijo; depende del tamaño de la caché interna de tokens";
  los viejos se borran cuando se llena. Al caducar: un 4xx con código tipo **`syncStateNotFound`**; además Graph puede devolver
  **`410 Gone`** con `Location` a una delta vacía (reinicio por mantenimiento/migración del tenant)
  (`docs-ms/concepts_delta-query-overview.md:190-202`). Tratamiento: nueva ronda completa con `$filter=receivedDateTime ge
  {último recibido − margen}` y deduplicar. Con sondeo cada pocos minutos el token se usa continuamente.
- Tamaño de página: `Prefer: odata.maxpagesize={x}`. (Listado normal: 10 por defecto, `$top` 1-1000; páginas grandes con
  cuerpos completos pueden dar 504: `docs-ms/api-reference_v1.0_api_user-list-messages.md:17-19`.)

### Alternativa: sondeo con $filter

```
GET /users/{id}/mailFolders/inbox/messages?$filter=receivedDateTime ge {marca−margen}
    &$orderby=receivedDateTime asc&$select=...&$top=50
```
Sin estado del servidor (no caduca), pero: `receivedDateTime` es la hora de recepción del servidor y un mensaje puede aparecer
con una hora anterior a la marca (retrasos de transporte), así que hace falta solape + deduplicado; y `$filter` con `$orderby`
exige que las propiedades del orden estén en el filtro, en el mismo orden y primero
(`docs-ms/api-reference_v1.0_api_user-list-messages.md:61-66`). Buena **red de seguridad** cuando la delta caduca; como vía
principal, delta.

### Solo lectura: consecuencias

La app no puede marcar como leído, mover ni etiquetar. "Lo nuevo" lo decide el estado local (deltaLink + tabla de mensajes
vistos con su ID inmutable e `internetMessageId`), no `isRead`. Si alguien abre el buzón en Outlook, los cambios de leído llegan
como `updated` y con `changeType=created` no molestan.

### Adjuntos

1. Listar sin traer contenido:
   `GET /users/{id}/messages/{mid}/attachments?$select=id,name,contentType,size,isInline`
   (`@odata.type` viene siempre: `#microsoft.graph.fileAttachment` / `itemAttachment` / `referenceAttachment`). Sin `$select`,
   la lista incluye `contentBytes` (base64) de cada fichero.
2. **fileAttachment** (`docs-ms/api-reference_v1.0_resources_fileattachment.md`): `contentBytes` base64, `size` Int32,
   `isInline`, `name` (texto mostrado, "doesn't need to be the actual file name": no fiarse), `contentType` (lo pone el
   remitente: no fiarse). Bajar en bruto con `GET .../attachments/{aid}/$value` (`docs-ms/api-reference_v1.0_api_attachment-get.md`,
   "Get the raw contents"). Comprobar que empieza por `%PDF-`, tope de tamaño propio antes de leer (p. ej. 25 MB; Exchange
   Online recibe por defecto mensajes de hasta ~36 MB y se puede subir a 150 MB; los límites de 3 MB / 150 MB de la doc son de
   **subida**, no de lectura), nombre generado y SHA-256.
3. **itemAttachment** (reenvío "como datos adjuntos" desde Outlook: muy común): `GET .../attachments/{aid}?$expand=microsoft.graph.itemattachment/item`
   devuelve el mensaje adjunto **con sus propios adjuntos y su `contentBytes`**, anidados hasta **30 niveles**
   (attachment-get.md:20 y ejemplo 4: el PDF anidado sale como `fileAttachment` con `contentBytes`). Alternativa:
   `.../attachments/{aid}/$value` da el mensaje adjunto en **MIME** y se recorre con `email` de la biblioteca estándar
   (`policy=email.policy.default`), sacando partes `application/pdf` (o `application/octet-stream` con nombre `.pdf` y cabecera
   `%PDF-`). Poner tope de profundidad (p. ej. 3) y de tamaño.
4. Reenvío desde clientes no-Outlook: el original llega como **fileAttachment** `message/rfc822` (`.eml`) → mismo tratamiento
   MIME. Un `.msg` adjunto como fichero (formato OLE) no se abre: se marca para revisión manual.
5. **Inline** (`isInline: true`, logos de firma): ignorar salvo que sea PDF (raro).
6. **referenceAttachment** (enlace a OneDrive/SharePoint): en v1.0 no expone URL descargable; `$value` → **405**
   (attachment-get.md, "Attempting to get the $value of a reference attachment returns HTTP 405"); `size` es el de los metadatos,
   no del fichero (referenceattachment.md). **No seguir enlaces**: marcar "factura por enlace, descargar a mano".
7. Alternativa global: `GET /users/{id}/messages/{mid}/$value` = mensaje completo en MIME (`docs-ms/concepts_outlook-get-mime-message.md`).
   Útil como archivo de auditoría (hash del .eml), pero mete el cuerpo entero; con la API estructurada se trae menos texto no
   fiable.

### IDs

- **`Prefer: IdType="ImmutableId"`** en *cada* petición: el id no cambia aunque el mensaje se mueva de carpeta dentro del
  buzón; cambia si va a archivo o se exporta/reimporta. También vale en delta, y los deltaLink sirven con ambos formatos.
  Son **sensibles a mayúsculas** (`docs-ms/concepts_outlook-immutable-id.md`).
- **`internetMessageId`** (cabecera Message-ID): estable entre buzones y reenvíos, pero lo fija el remitente (no fiable como
  única clave). Clave de idempotencia sugerida: ID inmutable del mensaje + SHA-256 del PDF (el hash del PDF ya es la clave
  natural del proyecto, regla 8 `docs/arquitectura.md:136`).
- Cuerpo y asunto: no pedirlos salvo para mostrar (`$select` sin `body`); son datos no fiables, nunca instrucciones (regla 6,
  `docs/arquitectura.md:134`). `from` es falsificable.

---

## 5. Throttling y frecuencia de sondeo

- Límites de Outlook **por app y por buzón**: **10.000 peticiones en 10 minutos**, **4 peticiones concurrentes**, 150 MB de
  subida en 5 min (`docs-ms/includes_throttling-outlook.md`, "Limits per mailbox"). Global por app: 130.000 peticiones / 10 s
  (`docs-ms/concepts_throttling-limits.md:20-24`).
- Al pasarse: **429** con `Retry-After` (segundos). Esperar exactamente eso y reintentar; sin `Retry-After`, backoff
  exponencial (`docs-ms/concepts_throttling.md:82-95`). Tratar igual 503/504 transitorios. Peticiones **en serie** (una a la
  vez) para no rozar las 4 concurrentes.
- Microsoft no publica un intervalo de sondeo "recomendado"; su recomendación general es delta (+ notificaciones). Un ciclo =
  1 petición delta (+1 token cada ~hora +2-3 por factura). Sondeo cada **5 minutos** = 288 peticiones/día; cada 2 min = 720:
  órdenes de magnitud por debajo del límite. Recomendación: 5 min (configurable 2-15), con jitter de unos segundos.
- Entra también limita la emisión de tokens: reutilizar el token hasta su caducidad.

---

## 6. Alternativas

| Alternativa | Veredicto | Por qué |
|---|---|---|
| **Delegado + device code** con un usuario dedicado | Rechazar | Necesita un buzón de usuario con licencia y contraseña/MFA, y guardar un **refresh token** (90 días deslizantes, `docs-ms/entra_refresh-tokens.md:23-25`) que vale lo que la sesión del usuario. Device code es vector de phishing: Microsoft creó en **mayo 2025** una directiva de Acceso Condicional gestionada "Block device code flow"; si está activa, también bloquea los refresh. Delegado `Mail.Read` no se puede recortar más que "su buzón". Requiere intervención humana para re-consentir. |
| **IMAP/POP con OAuth** (client credentials) | Rechazar | Exige `IMAP.AccessAsApp` + `New-ServicePrincipal` + **`Add-MailboxPermission -AccessRights FullAccess`**: FullAccess es lectura-**escritura** (IMAP puede borrar/mover/marcar), contradice "solo lectura". Errores opacos ("AUTHENTICATE failed"). Otro host/puerto (`outlook.office365.com:993`), MIME a mano. Basic auth para IMAP/POP/EWS/EAS desactivada **definitivamente desde el 1-oct-2022**; SMTP AUTH basic se desactiva por defecto a final de **dic-2026** y se retira en 2027 (irrelevante: no enviamos). |
| **EWS** | Rechazar | Retirada en Exchange Online desde **1-oct-2026**, completa **1-abr-2027** (MC1447678, lista `EWSAllowedAppIDs`). |
| **Graph change notifications (webhooks)** | Rechazar | Exigen "a **publicly accessible, HTTPS-secured endpoint**"; si no es público, Graph no manda nada; validación del endpoint, respuesta en 3 s, reintentos 4 h (`docs-ms/concepts_change-notifications-delivery-webhooks.md:17,27,34`). Abriría una entrada desde internet al mini PC. La variante con Event Hubs exige suscripción de Azure y otro host/protocolo. El sondeo cada pocos minutos basta. |
| **Zapier / Power Automate** | Rechazar | Credenciales del buzón en un tercero y catálogo de acciones amplio (`docs/mcp-setup.md:27-46`). |
| **Application Access Policy** | Rechazar | Legacy, "don't create new" (sección 1). |
| **Graph app-only + RBAC for Applications + certificado** | **Aceptar** | Sin usuario ni contraseña, sin refresh tokens, sin intervención humana, ámbito a un buzón y a solo lectura verificable con `Test-ServicePrincipalAuthorization` y con 403 en lo demás; solo dos hosts HTTPS. |

---

## 7. Python: HTTPS a mano frente a msal

### Sin msal (recomendado)

- Todo cabe en la biblioteca estándar salvo la firma del certificado:
  - Token: `POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`, `application/x-www-form-urlencoded`,
    `client_id`, `scope=https://graph.microsoft.com/.default`, `grant_type=client_credentials` y `client_assertion_type` +
    `client_assertion` (o `client_secret`) (`docs-ms/entra_v2-oauth2-client-creds-grant-flow.md:147-204`).
  - Graph: `GET` con `Authorization: Bearer`, `Prefer`, JSON con `json`.
- **Proxy CONNECT**: `urllib.request` con `ProxyHandler({"https": "http://bms:<clave>@127.0.0.1:<puerto>"})` hace túnel CONNECT
  y mueve `Proxy-Authorization` a las cabeceras del túnel (no viaja al servidor final; comprobado en CPython 3.11,
  `urllib.request.AbstractHTTPHandler.do_open`: "Proxy-Authorization should not be sent to origin server"); o explícito con
  `http.client.HTTPSConnection(proxy_host, proxy_port)` + `set_tunnel("graph.microsoft.com", 443, headers={"Proxy-Authorization": ...})`.
  Es el mismo esquema que ya usa el proyecto (`HTTPS_PROXY` con credencial: `windows/leer-facturas.ps1:81`; sin credencial en
  Docker: `docker/docker-compose.yml:96-97`; CONNECT a mano en `src/bms_agent/aislamiento.py:200-207`).
- TLS: `ssl.create_default_context()`; en Windows conviene `truststore` (ya fijado: `windows/requirements-windows.txt:44`) para
  usar el almacén del sistema.
- `httpx2` ya está instalado como dependencia del SDK de Anthropic (`docker/requirements.txt:20`) y también soporta proxy, pero
  acoplar el lector de correo a la pila del SDK no aporta; `urllib` basta y no añade nada.
- Dependencias nuevas: solo `cryptography` (+`cffi`, `pycparser`) si se usa certificado; ninguna con secreto.
- No lanza procesos: compatible con el gancho de auditoría de la variante nativa (`src/bms_agent/nativo.py:123-125`
  `SUCESOS_DE_PROCESO`, instalado en :322).

### Con msal

- msal **1.39.0** (2026-09-17) requiere `requests<3`, `PyJWT[crypto]<3`, `cryptography<51` (PyPI). Transitivo: `requests` →
  `urllib3`, `certifi`, `charset-normalizer`, `idna`; `cryptography` → `cffi` → `pycparser`. Unos **8 paquetes nuevos** que fijar
  con hash, para hacer lo que son ~60 líneas.
- Aporta: caché de token, aserción PS256 hecha, reintentos. `requests` respeta `HTTPS_PROXY` con credencial.
- Incluye código que lanza procesos (`subprocess.call(['wslview'|'explorer.exe', ...])` y `webbrowser`) **solo** en el flujo
  interactivo (`pkg-msal/x/msal/oauth2cli/authcode.py:94-114`); el confidential client no lo toca, y en nativo el gancho lo
  pararía igualmente. Hace "instance discovery" contra `login.microsoftonline.com` (mismo host).
- `requests` usa `certifi` (su propio almacén de CA), no el de Windows, salvo que se inyecte `truststore`.

Veredicto: **sin msal**; `cryptography` como única dependencia nueva (o ninguna si se acepta secreto).

---

## 8. Resumen de la receta recomendada

1. Buzón **compartido** `facturen@<dominio>` sin licencia; sin reglas; nadie inicia sesión en él.
2. App de Entra de un solo tenant, **sin permisos de API consentidos**, credencial **certificado** (autofirmado 2 años; la clave
   privada solo en el PC, cifrada con DPAPI en nativo / Docker secret en Docker).
3. Exchange: `New-ServicePrincipal` → `New-ManagementScope` (filtro al buzón, comprobado con `-RecipientPreviewFilter`) →
   `New-ManagementRoleAssignment -Role "Application Mail.Read" -CustomResourceScope` → `Test-ServicePrincipalAuthorization`
   (True en el buzón, False en otro) → esperar 30 min-2 h → pruebas 200/403 reales (incluidas escritura y envío).
4. Lector de correo: token client-credentials (cacheado 60-90 min), delta de `inbox` con `changeType=created`, IDs inmutables,
   adjuntos con `$select` y `$value`, item attachments con `$expand` o MIME, referencias a OneDrive marcadas para mano, PDFs a su
   directorio vacío con nombre generado y SHA-256; 429 → `Retry-After`; sondeo 5 min.
5. Red: solo `login.microsoftonline.com:443` y `graph.microsoft.com:443`, por una salida **propia** del lector de correo.
