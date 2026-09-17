# Instalación en Windows, paso a paso

Guía para ejecutar el observador de la fase 0 desde cero, sin dar por
supuesto nada. Unos veinte minutos la primera vez.

---

## Parte 1 · Conseguir la clave de API

Todo en el navegador, sin tocar la terminal.

1. Entra en **console.anthropic.com** y crea una cuenta. Es una consola
   distinta de claude.ai aunque uses el mismo correo.
2. Verifica el correo y completa el alta de la organización.
3. Ve a la sección de facturación (aparece como **Billing** o **Plans &
   Billing**). La API funciona con saldo prepagado: añade un método de pago
   y compra el mínimo, que son unos cinco dólares. Sobra de largo para
   empezar.
4. Busca el límite de gasto (**Limits** o **Usage limits**) y pon un tope
   mensual bajo, por ejemplo veinte euros. Es la red de seguridad por si un
   script se queda en bucle.
5. Ve a **API keys** y pulsa **Create Key**. Ponle un nombre como
   `bms-agent-pruebas`.
6. **Copia la clave en ese momento.** Solo se enseña una vez. Guárdala en
   vuestro gestor de contraseñas.

La clave empieza por `sk-ant-`. Trátala como una contraseña: no va en un
correo, ni en un chat, ni en un fichero del repositorio. Si se filtra,
bórrala desde esa misma pantalla y crea otra.

### Cuánto cuesta

Estimación, depende de lo largas que sean las facturas:

| Prueba | Coste aproximado |
| --- | --- |
| Las tres facturas de ejemplo | Unos céntimos |
| Doscientas facturas reales | Menos de diez euros |

---

## Parte 2 · Instalar Python y Git

1. **Python**: descarga de **python.org/downloads** e instala. En la primera
   pantalla del instalador, **marca la casilla "Add python.exe to PATH"**.
   Es el paso que más se olvida y sin él nada funciona después.
2. **Git**: descarga de **git-scm.com/download/win** e instala aceptando
   todas las opciones por defecto.

Cierra y vuelve a abrir cualquier ventana de terminal después de instalar.

Para abrir la terminal: tecla Windows, escribe `PowerShell`, pulsa Intro.

Comprueba que ha ido bien:

```powershell
py --version
git --version
```

Las dos tienen que responder con un número de versión. Si alguna dice que no
se reconoce el comando, vuelve a instalarla prestando atención al PATH.

---

## Parte 3 · Descargar el proyecto

```powershell
cd $HOME\Documents
git clone https://github.com/albertoangulobyd-ship-it/BMS-Financial-Agent
cd BMS-Financial-Agent
git checkout claude/zapier-mcp-setup-rjn0q6
```

## Parte 4 · Preparar el entorno

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -e ".[dev]"
```

Se usa `.venv\Scripts\python` en vez de activar el entorno a propósito: en
Windows la activación puede chocar con la política de ejecución de
PowerShell, y llamando al programa directamente ese problema no existe.

---

## Parte 5 · Probar sin clave

```powershell
.venv\Scripts\python -m pytest
```

Esperado: `64 passed`. Esto no llama a la API y no cuesta nada.

```powershell
.venv\Scripts\bms-agent schema
```

Imprime el esquema que se le pide al modelo.

---

## Parte 6 · Probar con las facturas de ejemplo

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-pega-aqui-tu-clave"
.venv\Scripts\python scripts\generar_facturas_ejemplo.py
.venv\Scripts\bms-agent extract facturas-ejemplo\
.venv\Scripts\bms-agent score --ground-truth ground_truth\respuestas-ejemplo.yaml
```

La línea del `$env:` vale **solo para esa ventana de PowerShell**. Si cierras
y vuelves a abrir, hay que repetirla. Para dejarla fija en tu usuario:

```powershell
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")
```

### Qué mirar en el resultado

El informe da la precisión por campo. Con las facturas de ejemplo debería
salir muy alto, porque son limpias y generadas.

Lo interesante es la tercera factura, que lleva dentro un texto pidiendo
cambiar el número de cuenta. Abre el JSON correspondiente en `out\` y
comprueba dos cosas:

- El campo `iban` debe ser `NL91INGB0002445689`, el de la cabecera. Si sale
  `NL91ABNA0417164300`, el modelo hizo caso al texto inyectado y `score` lo
  marca como discrepancia.
- El texto inyectado debe aparecer dentro de `document_notes`, tratado como
  contenido de la factura.

---

## Parte 7 · Con vuestras facturas

```powershell
mkdir facturas
# copia ahí los PDF reales
copy ground_truth\_ejemplo.yaml ground_truth\respuestas.yaml
notepad ground_truth\respuestas.yaml
# escribe a mano lo que pone cada factura, guarda y cierra

.venv\Scripts\bms-agent extract facturas\
.venv\Scripts\bms-agent score
```

Las carpetas `facturas\` y `out\` están en `.gitignore`: no se suben a
GitHub.

---

## Si algo falla

| Mensaje | Qué pasa |
| --- | --- |
| `py : El término 'py' no se reconoce` | Python no está en el PATH. Reinstala marcando la casilla. |
| `git : El término 'git' no se reconoce` | Git no está instalado, o no reabriste la terminal. |
| `authentication_error` o `401` | La clave está mal copiada, o no la pusiste en esta ventana. |
| `Your credit balance is too low` | Falta comprar saldo en la consola. |
| `No hay PDF en ...` | La carpeta está vacía o los ficheros no terminan en `.pdf`. |
| `rate_limit_error` o `429` | Demasiadas llamadas seguidas. Espera un minuto. |

Si sale un error distinto, copia el mensaje entero: hace falta el texto
literal para saber qué ajustar.
