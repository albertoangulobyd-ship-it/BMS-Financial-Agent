# bms-agent en Windows sin Docker, paso a paso

Guía para tener bms-agent funcionando en tu ordenador con Windows, aislado del resto
del ordenador y de internet, **sin Docker Desktop**. Es el mismo programa que el del
entorno de Docker ([entorno-local.md](entorno-local.md)), con las mismas carpetas del
buzón, la misma consola y los mismos datos de prueba; lo que cambia es quién hace de
muro: aquí es el **cortafuegos de Windows**, que ya viene con el ordenador. No hace
falta saber programar: todo se hace con dobles clics y, como mucho, escribiendo una
línea.

Si buscas el día a día de la consola (prioridades, corregir un dato, verificar un
IBAN), está en [uso-v1.md](uso-v1.md). Esta guía es sobre dónde y cómo corre.

---

## 1. Qué es, en dos minutos

bms-agent son cuatro programas, cada uno con su propia copia de Python en
`C:\BMS\runtime\` y sus propias reglas en el cortafuegos de Windows. El cortafuegos
distingue los programas por la carpeta donde están, así que cada uno solo puede hacer
lo que su regla le deja:

| Programa | Qué hace | Qué puede hacer en la red |
| --- | --- | --- |
| **consola** | La consola que abres en el navegador. | **Nada hacia fuera.** Solo contesta a tu navegador, en este ordenador. |
| **lector** | Lee los PDF de facturas con la API de Anthropic. Solo arranca cuando tú lo pides. | **Nada directo.** Solo habla con la **salida**, dentro de este ordenador. |
| **salida** | La única puerta a internet. Deja pasar al lector hacia `api.anthropic.com` y a nada más, y apunta cada intento. **Solo está encendida mientras se leen facturas.** | Solo el puerto 443 (el de las webs cifradas). Lo demás, bloqueado. |
| **orden** | Las órdenes sueltas: importar, crear los datos de prueba, las copias, ver lo que ha salido. | **Nada.** |

```mermaid
flowchart LR
  N["Tu navegador<br/>127.0.0.1:8765"] --> C
  subgraph PC["Tu ordenador (cortafuegos de Windows)"]
    C["consola<br/>sin red"]
    L["lector<br/>la clave cifrada"]
    S["salida<br/>solo al leer"]
    O["orden<br/>sin red"]
    D[("C:\BMS\datos<br/>base y originales")]
  end
  L -->|"127.0.0.1, con la credencial de la pasada"| S
  S -->|"solo esto sale"| A["api.anthropic.com:443"]
  C --- D
  L --- D
  O --- D
```

Lo que esto te garantiza, igual que en Docker:

- **La consola solo se abre desde tu ordenador** (`http://127.0.0.1:8765/consola`).
  Desde otro ordenador de la oficina o de casa no se llega, aunque esté en la misma red.
- **La consola y los datos no tienen internet.** Aunque alguien colara algo raro en una
  factura, el programa que tiene tus datos no puede mandarlos a ninguna parte.
- **Solo el lector sale, solo por la salida y solo a la API de Anthropic.** Cualquier
  otro destino lo rechaza la salida, y queda apuntado. La salida se apaga al acabar.
- **La clave de la API no está escrita en claro en ningún sitio**: va cifrada con la
  protección de datos de Windows (DPAPI), atada a tu usuario y a este ordenador.
- **El programa no se puede cambiar con tu usuario**: solo `datos` y `buzon` se pueden
  escribir.
- **No te fías de que esté bien: lo compruebas.** `comprobar.bat` prueba a salir a
  internet con cada programa y te dice en claro si lo consigue (apartado 10). Si algo
  falla, el lector no lee nada y la consola lo enseña en rojo.
- Siguen valiendo las reglas de siempre: nada paga solo, nada presenta el BTW solo, el
  IBAN de pago nunca sale de una factura y cada cambio lo firma una persona
  ([arquitectura.md](arquitectura.md)).

La diferencia con Docker, sin rodeos, está en el apartado 11.

---

## 2. Lo que necesitas

| | |
| --- | --- |
| **Ordenador** | Windows 10 u 11 de 64 bits. |
| **Permiso de administrador** | Una vez, al instalar (y al desinstalar). Windows lo pide en una ventana. |
| **Disco** | Unos **300 MB** para el programa, más lo que ocupen tus facturas. |
| **Memoria** | 4 GB bastan: sin Docker no hay máquina virtual. |
| **Internet** | Solo durante la instalación y mientras se leen facturas. |
| **El cortafuegos de Windows** | Encendido (lo está de fábrica). Si un antivirus lo sustituye por el suyo, las reglas no se aplican y `comprobar.bat` sale en rojo: díselo a quien mantiene el programa. |
| **Copias** | Un disco SSD externo, cifrado (apartado 9). |
| **Clave de la API** | La de Anthropic, con crédito prepagado (apartado 4). |

---

## 3. Instalar (una sola vez)

1. Descarga la carpeta del proyecto (el ZIP que te pasa quien mantiene el programa, o
   el de GitHub) y descomprímela, por ejemplo en `Documentos\BMS-Financial-Agent`.
   Si Windows avisa de que los ficheros vienen de internet: clic derecho sobre el ZIP
   → **Propiedades** → marca **Desbloquear** → Aceptar, y descomprímelo otra vez.
2. Entra en la carpeta **`windows`** y haz doble clic en **`instalar.bat`**.
3. Windows pregunta si dejas que haga cambios: **Sí**. Se abre otra ventana que
   instala, en unos minutos:
   - el Python oficial de python.org, comprobado (si lo descargado no es exactamente lo
     esperado, o no lleva la firma de la Python Software Foundation, no instala nada);
   - un Python para cada programa (consola, lector, salida, orden);
   - las dependencias, cada una comprobada igual;
   - las reglas del cortafuegos (todas se llaman **«BMS Finanzas - …»**);
   - los permisos: el programa, de solo lectura para tu usuario; tus datos, solo tuyos.
4. Al acabar, en la primera ventana: crea los accesos del escritorio (**BMS Finanzas -
   Abrir la consola**, **- Datos de prueba**, **- Parar**, **- Importar el buzon**,
   **- Leer facturas**, **- Comprobar aislamiento** y **- Buzon**), te pregunta si
   quieres guardar ya la clave de la API (apartado 4) y hace la comprobación del
   aislamiento. **Tiene que salir todo en verde.**

Queda así:

| Carpeta | Qué hay | ¿Tu usuario puede cambiarlo? |
| --- | --- | --- |
| `C:\BMS\app` | El programa | No |
| `C:\BMS\lib` | Las dependencias | No |
| `C:\BMS\runtime\consola`, `lector`, `salida`, `orden` | Un Python para cada programa | No |
| `C:\BMS\windows` | Los scripts (los de los accesos del escritorio) | No |
| `C:\BMS\datos` | La base, los originales, la clave cifrada, los registros | **Sí** |
| `C:\BMS\buzon` | Donde dejas los ficheros | **Sí** |

Para instalar en otra carpeta, en PowerShell en la carpeta `windows`:
`.\instalar.ps1 -Raiz D:\BMS`.

Si quien mantiene el programa te ha dado una carpeta **`paquetes`**, ponla dentro de
`windows` antes de instalar: el instalador toma de ahí lo que haya (igual de
comprobado) y no lo descarga.

---

## 4. La clave de la API

1. Saca la clave como dice [instalacion-windows.md](instalacion-windows.md), parte 1
   (console.anthropic.com → API keys → Create Key). Empieza por `sk-ant-`.
2. En **Billing**, compra crédito prepagado y **deja apagada la recarga automática**:
   así el gasto nunca pasa del crédito que hayas puesto (apartado 13).
3. Doble clic en **`clave.bat`** (en `C:\BMS\windows`, o desde el instalador). Pega la
   clave con el **botón derecho del ratón** y pulsa Intro. No se ve al escribirla.

La clave queda cifrada en `C:\BMS\datos\secretos\clave-api.dpapi`. Solo **tu usuario
de Windows, en este ordenador**, la puede descifrar, y de los programas de bms-agent
solo el lector la usa. No hay ningún fichero de texto con la clave. En otro ordenador
(o con otro usuario, o desde una copia de seguridad) ese fichero no sirve: allí se
vuelve a guardar con `clave.bat`.

- Haz `clave.bat` con tu usuario de siempre, **no** con «Ejecutar como administrador».
- Para cambiarla: `clave.bat` otra vez. Para quitarla: `.\clave.bat -Borrar`.
- Si venías de Docker: copia la clave de `docker\secretos\anthropic_api_key.txt` en
  `clave.bat` y **borra después ese fichero de texto**.
- Si la clave se filtra, bórrala en console.anthropic.com, crea otra y guárdala de nuevo.

---

## 5. La primera vez

En una ventana de PowerShell en `C:\BMS\windows` (en el Explorador, clic derecho sobre
un hueco de la carpeta → **Abrir en Terminal**):

1. **Tu token personal** para entrar en la consola:

   ```powershell
   .\persona.bat -Nombre "Tu nombre" -Rol administrador
   ```

   Sale un token que empieza por `bms_`. **Guárdalo en tu gestor de claves**: se ve
   una sola vez. Para otras personas, lo mismo con `-Rol administracion` o
   `-Rol consulta` (como en [entorno-local.md](entorno-local.md), apartado 5).
2. **La empresa** (sin sus cuentas no entra ningún extracto del banco):

   ```powershell
   .\empresa.bat -Cuentas "NL02ABNA0123456789,NL44RABO0123456789" -BtwId "NL001122334B01" -Kvk "12345678"
   ```

3. **El primer maestro y los trimestres de antes**: importa los acreedores de Exact
   (apartado 7) y haz lo que dice [uso-v1.md](uso-v1.md), «El primer día».

---

## 6. Arrancar y parar

| Para | Haz |
| --- | --- |
| Abrir la consola con tus datos | Doble clic en **BMS Finanzas - Abrir la consola** (`iniciar.bat`) |
| Abrir la consola con DATOS DE PRUEBA | **BMS Finanzas - Datos de prueba** (`iniciar.bat -Demo`, apartado 8) |
| Cerrarla | **BMS Finanzas - Parar** (`parar.bat`) |

Al abrirla, `iniciar.bat` hace **la pasada del día** (lo que depende de la fecha:
vencidas, plazos, órdenes de compra que caducan) y **comprueba que la consola y las
órdenes no tienen salida a internet**. Después arranca la consola sin ventana y abre el
navegador en `http://127.0.0.1:8765/consola`. Entras con tu token.

Parar no borra nada, y apagar el ordenador sin parar tampoco: la base aguanta un corte.

**Si ves una banda roja arriba que dice «AISLAMIENTO SIN COMPROBAR O CON FALLOS»**: la
última comprobación de algún programa ha fallado, falta o tiene más de 90 días. Haz
doble clic en **BMS Finanzas - Comprobar aislamiento** y no trabajes con datos de
verdad hasta que salga todo en verde.

---

## 7. Dónde dejar los ficheros

En **`C:\BMS\buzon`** (el acceso **BMS Finanzas - Buzon** del escritorio), con las
mismas carpetas que el entorno de Docker: la tabla está en
[entorno-local.md](entorno-local.md), apartado 7 (`facturas`, `exact\proveedores`,
`maestro\objetos`, `trnsprnt`, `po`, `banco`…). Se importan en ese orden.

- **BMS Finanzas - Importar el buzon** (`importar.bat`) para todo lo que no son PDF.
  No cuesta nada: no llama a ninguna API y el programa que importa no tiene red. Te pide
  tu token. Lo que entra se mueve a `buzon\hecho\<fecha>\`; lo que entra con filas
  rechazadas también, y lo dice en amarillo; lo que no entra se queda y dice por qué.
- **BMS Finanzas - Leer facturas** (`leer-facturas.bat`) para los PDF. **Esto sí cuesta
  dinero** (unos céntimos por factura). Lo que hace, en orden:
  1. enciende la salida, solo en este ordenador y con una credencial nueva para esta
     lectura, que solo conocen la salida y el lector;
  2. comprueba el aislamiento de la salida y del lector: si el lector puede llegar a
     internet por su cuenta, o la salida deja pasar algo que no sea la API, **no lee
     nada ni paga nada**, y lo dice en rojo. No hay forma de saltarse esto;
  3. cuenta lo que va a mandar (gratis), te enseña el coste y solo sigue si escribes
     `si`;
  4. lee, y apaga la salida al acabar (también si algo falla o cierras la ventana).

  Un PDF que ya se leyó no se vuelve a pagar.

### Las órdenes sueltas (`orden.bat`)

Lo que [uso-v1.md](uso-v1.md) escribe como `bms-agent ...` aquí se escribe con
**`orden.bat`** delante, en PowerShell en `C:\BMS\windows`, igual que en Docker:

```powershell
.\orden.bat iban listar
.\orden.bat btw ver 2026-T3
.\orden.bat historial 12
```

Te pide el token (no se ve), lo pasa por dentro y lo olvida al acabar. La orden corre
con el programa **orden**, sin red, siempre sobre tus datos de verdad. Lo que tiene su
script (`iniciar`, `importar`, `leer-facturas`, `persona`, `empresa`, `copia`,
`restaurar`, `clave`) no va por `orden.bat`.

---

## 8. Datos de prueba y datos de verdad

Exactamente como en Docker ([entorno-local.md](entorno-local.md), apartado 8):

- **BMS Finanzas - Datos de prueba** (`iniciar.bat -Demo`) crea **otra base**,
  `C:\BMS\datos\demo.sqlite3`, con una empresa de seguridad ficticia y los casos que la
  consola tiene que saber enseñar. Se crea de nuevo cada vez, con la fecha de hoy, y
  salen dos tokens («Ana Demo» y «Bram Demo») que solo valen ahí.
- En cada página hay una **banda roja fija: DATOS DE PRUEBA**.
- Para volver a tus datos: **Parar** y **Abrir la consola**.
- Lo de prueba nunca pasa a tus datos de verdad, y lo de verdad no entra en la prueba:
  `importar.bat -Demo` con un fichero de verdad lo deja en el buzón, y
  `leer-facturas.bat -Demo` no lee ni paga nada.

---

## 9. Copias de seguridad

Aquí tus datos son una carpeta normal (`C:\BMS\datos`), pero **la copia se hace con su
script**: una base copiada a medias no sirve, y el script la comprueba.

**Una vez: cifrar el disco externo** con BitLocker (Windows Pro) o VeraCrypt (gratis),
como dice [entorno-local.md](entorno-local.md), apartado 9.

**Cada semana**, en PowerShell en `C:\BMS\windows`:

```powershell
.\copia.bat -Destino E:\BMS-copias
.\copia.bat -Comprobar E:\BMS-copias\bms-copia-bms-AAAAMMDD-HHMMSS
```

Se puede hacer con la consola abierta. Cada copia va en su carpeta con fecha y hora y
nunca pisa otra.

**Recuperar una copia**:

```powershell
.\restaurar.bat -Origen E:\BMS-copias\bms-copia-bms-AAAAMMDD-HHMMSS
```

Pregunta antes, para la consola, comprueba la copia, la pone en su sitio y la verifica.
Lo de antes queda guardado en `datos\antes-de-restaurar`, y la vuelta atrás queda
dicha en la auditoría. **La clave de la API no va en la copia** (en otro ordenador no
serviría): después de restaurar en un ordenador nuevo, `clave.bat`.

---

## 10. Lo que prueba la comprobación (`comprobar.bat`)

No se fía de la configuración: **cada programa lo intenta, con su propio Python**, y se
mira lo que pasa. Tarda unos segundos.

| Programa | Lo que prueba | Lo que tiene que pasar |
| --- | --- | --- |
| consola, orden | Conectar con `1.1.1.1:443`, `8.8.8.8:53` (TCP y una consulta DNS por UDP), `1.1.1.1:80` y `api.anthropic.com:443` | Ninguna llega |
| consola, orden | Pasar por la salida sin la credencial de la lectura | La salida dice que no (407) |
| salida | Los mismos destinos | Solo el puerto 443; `8.8.8.8:53` y el puerto 80, bloqueados |
| lector | Los mismos destinos, directamente | Ninguno llega |
| lector | Llegar a la salida (en este ordenador) | Llega |
| lector | Por la salida, con la credencial: `api.anthropic.com:443` | Sí (200) |
| lector | Por la salida: `example.com:443`, `api.anthropic.com:80`, `1.1.1.1:443` y `api.anthropic.com.evil.example:443` | No (403) |
| lector | Por la salida, sin la credencial | No (407) |
| todos | Escribir en `app`, `lib` y su carpeta de `runtime` | No pueden |
| todos | Escribir en `datos` y `buzon` | Pueden |

Además dice si el cortafuegos está encendido en todos sus perfiles, si están sus 12
reglas y si la clave guardada se puede descifrar.

El resultado de cada programa queda en `C:\BMS\datos\aislamiento.json`, con la hora.
Con él:

- **la consola pinta la banda roja** si alguno falla, falta o tiene más de 90 días;
- **una lectura no se hace** si la comprobación del lector y la de la salida no son de
  esa misma lectura (la de su credencial), de hace menos de una hora y en verde. Lo
  mira el propio lector antes de llamar a la API, además del script: no hay opción para
  saltárselo.

Lo que **no** puede probar está en el apartado siguiente.

---

## 11. Docker o nativa: qué aísla cada una

Las dos variantes son el mismo programa con las mismas reglas de dinero. Lo que cambia
es el muro:

| | Docker ([entorno-local.md](entorno-local.md)) | Nativa (esta guía) |
| --- | --- | --- |
| La consola y los datos, sin internet | Red interna de Docker: no hay ruta | Regla del cortafuegos por programa |
| El lector, solo por la salida | Red interna con un solo vecino: la salida | Regla del cortafuegos; la salida, en 127.0.0.1 |
| La salida, solo a `api.anthropic.com:443` | Lista blanca del proxy | Lista blanca del proxy **y** regla del cortafuegos (solo 443) |
| Otro programa usando la salida | No la ve: está en otra red | La ve (127.0.0.1 no se filtra), pero sin la credencial de la lectura recibe un no; y la salida solo está encendida al leer |
| La consola, solo desde tu ordenador | Puerto publicado en 127.0.0.1 | Escucha solo en 127.0.0.1 y regla de entrada bloqueada |
| La clave de la API | Fichero de texto en `docker\secretos`, que solo ve el lector | Cifrada con DPAPI; la descifra cualquier programa de tu usuario, y el código solo lo hace en el lector |
| El código, sin cambios | Imagen de solo lectura | Permisos de Windows: solo lectura para tu usuario |
| Lo que ve cada programa del disco | Cada caja solo sus volúmenes (la salida no ve tus datos) | Los cuatro corren con tu usuario y ven lo mismo (también la salida) |
| **Un programa comprometido que arranca otro programa** | El otro sigue dentro de la caja, sin red | **El otro no tiene reglas: podría salir** (ver abajo) |
| Consultas de nombres (DNS) | Las de la red interna no salen | Las hace un servicio de Windows, no el programa: el cortafuegos del programa no las para |
| Lo que hay que instalar | Docker Desktop (y WSL2) | Nada: Python va dentro, el cortafuegos ya está |
| Memoria y disco | 8-16 GB, unos 2 GB | 4 GB, unos 300 MB |
| Coste del software | 0 € para empresas pequeñas (licencia de Docker Desktop) | **0 €** |

**El hueco, dicho claro.** Las reglas del cortafuegos son por programa. Si alguien
consiguiera que uno de los programas de bms-agent ejecutara código suyo (por ejemplo,
con un fallo en una biblioteca al leer un fichero), ese código podría arrancar otro
programa del ordenador que no tiene reglas (PowerShell, un navegador) y salir por él.
También podría codificar datos en consultas de nombres, que en Windows hace un servicio
del sistema. Docker no tiene ese hueco: lo que se arranca dentro de una caja sigue en
la caja.

Lo que se hace contra eso, por capas:

- **El código de bms-agent no arranca ningún programa**, nunca: un test lo vigila en
  cada módulo (ni `subprocess`, ni `os.system`, ni `ShellExecute`…). Un atacante
  tendría que traer su propio camino.
- **La salida solo está encendida mientras lees**, y solo deja pasar a quien trae la
  credencial de esa lectura.
- **Lo que entra de fuera** (los PDF y los CSV) no lo interpreta como instrucciones
  nadie: el modelo solo extrae, y el lector no tiene herramientas.
- Si quieres más: **un usuario de Windows aparte** (apartado 12), que separa tus
  ficheros personales de los de bms-agent; o **la variante de Docker**, que no tiene
  este hueco. Encerrar cada programa en un AppContainer de Windows (lo que hacen las
  apps de la tienda) también lo cerraría, pero necesita un lanzador propio que esta
  versión no trae.

---

## 12. Un usuario de Windows aparte (opcional)

Para separar más: crea un usuario **estándar** (no administrador) solo para bms-agent,
por ejemplo «bms»: **Configuración → Cuentas → Otros usuarios → Agregar cuenta → No
tengo los datos de inicio de sesión de esta persona → Agregar un usuario sin cuenta
Microsoft**. Entra con ese usuario e instala desde ahí (`instalar.bat`; cuando Windows
pida permiso de administrador, escribe la contraseña de tu usuario de siempre). Así:

- los permisos de `C:\BMS\datos` son solo de ese usuario: tus programas de cada día no
  los ven, y bms-agent no ve tus documentos ni tu navegador;
- la clave de la API se cifra para ese usuario: tus programas no la pueden descifrar.

Para usarlo, **Cambiar de usuario** en el menú Inicio. Lo demás es igual.

---

## 13. Lo que cuesta tenerlo funcionando

**Son estimaciones**, hechas con facturas de una o dos páginas. La cifra exacta de lo
que se va a mandar la da gratis `leer-facturas.bat` antes de leer.

| Partida | Coste | Nota |
| --- | --- | --- |
| Software | **0 €** | Sin Docker Desktop ni su licencia. Python y el cortafuegos de Windows son gratis. |
| El ordenador que ya tienes | **0 €** | Windows 10/11 de 64 bits; 4 GB de memoria bastan. |
| Mini PC dedicado (opcional) | **250-450 €** una vez, y unos **2 €/mes** de luz | Solo si prefieres no usar tu ordenador de trabajo. |
| SSD externo cifrado | **70-100 €** una vez | Para las copias (apartado 9). |
| API de Claude, modelo claude-opus-5-5 | 4 USD por millón de tokens de entrada y 20 USD por millón de salida | Unos **0,04-0,09 USD por factura**; la mitad por la vía de lotes (más lenta: hasta 24 horas). |
| Reenviar un PDF ya leído | **0** | Lo ya leído en la base no se vuelve a mandar. |
| Importar de Exact, el banco o TRNSPRNT | **0** | No usa la API. |
| Mantenimiento | **1 hora al mes** | La copia semanal, `comprobar.bat` y mirar lo que ha salido. |

Lo que sale al mes en la API, según cuántas facturas leas (lo mismo que con Docker):

| Facturas al mes | Normal | Por lotes |
| --- | --- | --- |
| 100 | 4-9 USD | 2-5 USD |
| 300 | 12-28 USD | 6-14 USD |
| 1.000 | 40-92 USD | 20-46 USD |

**El techo duro** es el crédito prepagado con la recarga automática apagada: si se
acaba, la API deja de leer y no se cobra nada más. La consola, las importaciones y las
copias siguen funcionando sin crédito.

---

## 14. Si algo no va

| Lo que ves | Qué hacer |
| --- | --- |
| «Falta el sha256 fijado del Python embebible» o «Faltan los sha256 de …» al instalar | La versión que tienes no trae fijado lo que se descarga, y el instalador no baja nada sin comprobar. Pide a quien mantiene el programa una versión con eso hecho (apartado 17). |
| «no lleva una firma valida de Python Software Foundation» | Lo descargado no es el Python oficial. No sigas y avisa. |
| Banda roja «AISLAMIENTO SIN COMPROBAR O CON FALLOS» | `comprobar.bat`. Si sale en rojo, manda la ventana a quien mantiene el programa y no trabajes con datos de verdad. |
| «El aislamiento no esta bien … no se lee nada ni se paga nada» | Lo mismo: `comprobar.bat`. No se ha gastado nada. |
| «el perfil … del cortafuegos esta apagado» | Seguridad de Windows → Firewall y protección de red → enciéndelo en los tres perfiles. |
| «falta la regla …» | Vuelve a abrir `instalar.bat` desde la carpeta del proyecto: rehace las reglas sin tocar tus datos. |
| «Falta la clave de la API» | `clave.bat` (apartado 4). |
| «se guardo con otro usuario de Windows o en otro ordenador» | Vuelve a guardarla con `clave.bat`, con el usuario con el que usas bms-agent. |
| «El puerto 3128 de este ordenador lo usa otro programa» | Otro programa ocupa el puerto de la salida. Reinicia el ordenador; si sigue, avisa. |
| La consola no abre | `parar.bat` y otra vez **Abrir la consola**. Si sigue: manda `C:\BMS\datos\consola-errores.log`. |
| Un fichero no se importa, «es de los DATOS DE PRUEBA», «la base está abierta» al restaurar… | Igual que en Docker: [entorno-local.md](entorno-local.md), apartado 10. |
| Quieres ver qué ha salido a internet | `.\ver-salida.bat` (o `-Rechazados`). Solo tiene que aparecer `api.anthropic.com`. |

---

## 15. El mantenimiento de cada mes

1. **La copia semanal** al disco cifrado, y una vez al mes `copia.bat -Comprobar` de la
   última.
2. **`comprobar.bat`**: todo en verde. Las actualizaciones de Windows o de un antivirus
   pueden cambiar el cortafuegos; esta es la forma de saberlo.
3. **Mira la salida**: `.\ver-salida.bat -Rechazados`. Lo normal es que no salga nada;
   un intento rechazado (o uno sin la credencial, 407) es un aviso para quien mantiene
   el programa.
4. **El crédito de la API**, en console.anthropic.com → Billing.
5. **Una versión nueva** del programa: `parar.bat`, pon la carpeta nueva del proyecto y
   vuelve a abrir `instalar.bat` desde su carpeta `windows`. Cambia `app`, `lib`,
   `runtime` y las reglas; **tus datos, el buzón y la clave se quedan**.
6. **Desinstalar**: `desinstalar.bat`. Quita el programa, sus reglas (exactamente las
   «BMS Finanzas - …») y los accesos del escritorio. Tus datos se quedan en `C:\BMS\datos`
   y `C:\BMS\buzon` salvo que escribas `SI`, en mayúsculas, cuando te lo pregunte (haz
   antes una copia).

---

## 16. La primera vez en tu ordenador: lo que hay que mirar

Esta variante se ha construido y probado en un ordenador sin Windows: lo que es Python
(la comprobación del aislamiento, la puerta de la lectura, la clave cifrada con un
DPAPI de mentira, la consola) tiene sus tests, y los scripts pasan el analizador de
PowerShell 7. Lo que solo existe en Windows (el cortafuegos, DPAPI de verdad, los
permisos, Windows PowerShell 5.1, la ventana de permiso de administrador) **se mira la
primera vez en tu ordenador**, con datos de prueba, antes de meter nada de verdad:

1. `instalar.bat` termina sin rojo y deja los siete accesos en el escritorio.
2. En **Firewall de Windows Defender con seguridad avanzada** (`wf.msc`), en reglas de
   entrada y de salida, aparecen las 12 reglas «BMS Finanzas - …».
3. `comprobar.bat` sale **todo en verde** (los cuatro programas, el cortafuegos y la
   clave). **Sin esto, no se usan datos de verdad.**
4. **Datos de prueba**: la consola se abre en `http://127.0.0.1:8765/consola` con la
   banda de DATOS DE PRUEBA y sin la banda roja del aislamiento.
5. Desde otro ordenador o el móvil, en la misma red, `http://<la IP de tu PC>:8765` no
   abre nada.
6. `clave.bat`, y después `leer-facturas.bat` con **una** factura de verdad: cuenta,
   pregunta, lee. Luego `ver-salida.bat`: solo `api.anthropic.com`, permitido.
7. `parar.bat`, y en el Administrador de tareas no queda ningún `python.exe` de
   `C:\BMS`.
8. `copia.bat -Destino` al disco cifrado y `copia.bat -Comprobar` de esa copia.

Si algo de esto no sale como dice, para y avisa a quien mantiene el programa con la
ventana tal cual.

---

## 17. Para quien mantiene el programa

- **Lo que se instala.** `instalar.ps1` (Windows PowerShell 5.1 y PowerShell 7) baja el
  Python embebible de python.org (`windows/fijado.json`: versión, URL, sha256 y
  firmante), lo comprueba por sha256 y por su firma Authenticode, y lo copia en
  `runtime\<papel>` con un `python311._pth` (`python311.zip`, `.`, `..\..\lib`,
  `..\..\app\src`; `nativo.RUTAS_PTH`) y sin `pythonw.exe`. Las ruedas de
  `windows/requirements-windows.txt` (formato de pip, con `--hash`) se buscan en PyPI por
  su sha256, se comprueban y se abren en `lib\` (lo que haría `pip --target`): el
  embebible no trae pip. Con `windows\paquetes\` se toman de ahí. Nada se usa sin su
  hash.
- **Fijar los hashes.** Las ruedas py3-none-any tienen el hash de
  `docker/requirements.txt` (el mismo fichero). Las de Windows (`jiter`, `pydantic_core`,
  `PyYAML`), `tzdata` y el Python embebible se fijan con
  `python scripts/fijar_windows.py` (necesita internet; `--comprobar` dice qué falta).
  Antes de subir el sha256 del embebible, comprueba su firma de Sigstore:
  `python -m sigstore verify identity --bundle python-3.11.9-embed-amd64.zip.sigstore
  --cert-identity pablogsal@python.org --cert-oidc-issuer https://accounts.google.com
  python-3.11.9-embed-amd64.zip` (el .sigstore está junto al zip en python.org, y quién
  firma cada versión, en python.org/downloads/metadata/sigstore). Mientras falte alguno,
  el instalador para y lo dice.
- **Por qué Python 3.11.9.** Es la misma versión menor que el desarrollo y la imagen de
  Docker, y la última 3.11 con binarios para Windows: desde la 3.11.10 solo hay código
  fuente. La imagen de Docker lleva la 3.11.17, con las correcciones de seguridad de
  después; la nativa no las tiene (por ejemplo, la de `ipaddress` sobre qué direcciones
  son privadas, que la salida usa para no dejar ir a la red de casa, aunque solo resuelve
  `api.anthropic.com`; y varias de `tarfile`, `zipfile` y `email`, que bms-agent no usa). El paso siguiente es pasar el
  desarrollo a 3.13 o 3.14 y fijar ese embebible.
- **Las reglas** están en `comun.ps1` (`Reglas-Del-Cortafuegos`), todas con el prefijo
  «BMS Finanzas - » y el grupo «BMS Finanzas»; el desinstalador quita exactamente las del
  prefijo. En Windows un bloqueo gana a un permiso: la salida lleva el permiso del TCP
  443 y bloqueos del TCP 1-442 y 444-65535, del UDP y del ICMP. Un destino nuevo para la
  salida es un `--permitir` en `Arrancar-Salida` y el test estático.
- **La puerta de la lectura** (`nativo.exigir_lectura`, en cada cliente de la API): solo
  el programa del lector, por el proxy de `HTTPS_PROXY` (`http://bms:CREDENCIAL@127.0.0.1:3128`)
  y con la comprobación del lector y de la salida de esa misma credencial (su sha256
  está en `aislamiento.json`, la credencial no) de hace menos de 60 minutos. La salida
  recibe la credencial por `BMS_PROXY_CLAVE` (`bms-agent salida --clave-del-entorno`) y
  contesta 407 sin ella.
- **La instalación se reconoce** por `instalacion.json` en la raíz y por la carpeta del
  intérprete (`runtime\<papel>\python.exe`): `nativo.detectar`. Fuera de ella (el
  desarrollo, Docker) nada de esto se aplica.
- **Ningún módulo lanza procesos**: `tests/test_instalacion_nativa.py`
  (`test_ningun_modulo_lanza_procesos`). Si alguno lo necesitara, va en `PUEDEN_LANZAR`
  con su porqué, y es un hueco más de esta variante.
- **Los tests**: `pytest tests/test_instalacion_nativa.py`. Con `pwsh` en el PATH, o con
  `BMS_PROBAR_PWSH=1` y Docker (la imagen `mcr.microsoft.com/powershell`, sin red),
  además cada `.ps1` pasa el analizador de PowerShell y se ejecutan de verdad la
  lectura de los hashes, el `._pth`, la descarga comprobada y la tabla de reglas.
