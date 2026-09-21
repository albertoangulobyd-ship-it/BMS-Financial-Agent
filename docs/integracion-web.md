# Conectar el agente con un sitio web propio

## Sobre el botón de "ejecutar el agente"

El instinto es correcto: administración tiene que poder lanzar una pasada sin
abrir una terminal. Pero hay dos cosas que decidir antes, y una tiene
consecuencias de seguridad.

### Dónde vive el botón

| Dónde | ¿Vale? | Por qué |
| --- | --- | --- |
| Herramienta interna, en el ordenador de administración o dentro de la red, detrás de autenticación | **Sí** | Es una consola de operación. Es su sitio natural |
| Portal público de consulta (clientes, trabajadores, asesor) | **No** | Cada pulsación cuesta dinero real. Un endpoint público que lanza trabajo es una forma de vaciar el saldo de la API: basta con encontrar la URL y pulsarlo en bucle. Y rompe la garantía de solo lectura sobre la que se apoya toda la arquitectura del portal |

Esto no contradice la regla de que *el portal nunca gana un botón*: la consola
interna y el portal son dos aplicaciones distintas, con dos audiencias y dos
niveles de acceso distintos. Lo que no puede pasar es que sean la misma página.

### Qué forma tiene el botón

**No puede ser una llamada síncrona.** Leer cincuenta facturas tarda minutos.
Un botón que se queda girando, o que agota el tiempo de espera del navegador,
o que se dispara dos veces porque el usuario creyó que no había pasado nada,
es el diseño equivocado.

La forma correcta es un **trabajo**:

1. `POST /api/ejecutar` lanza y devuelve enseguida.
2. El navegador consulta `GET /api/ejecucion` cada pocos segundos.
3. Cuando el estado pasa a `terminado`, el sitio recarga los datos.

Tres detalles que hay que resolver sí o sí:

- **Un solo trabajo a la vez.** Dos clics seguidos son dos extracciones
  concurrentes sobre la misma carpeta: el doble de gasto para nada. Cerrojo.
- **Progreso visible.** Sin él, el usuario vuelve a pulsar.
- **El coste de la pasada, al terminar.** Es la cifra que evita que alguien se
  acostumbre a pulsar el botón por costumbre.

---

## Los tres niveles de conexión

Van en orden. Cada uno sirve para una fase distinta del proyecto.

### Nivel 1 · Un fichero JSON (funciona hoy)

```bash
bms-agent export --file datos.json
```

Escribe todo lo que el panel necesita. El sitio lo lee con un `fetch`. Sin
servidor, sin base de datos, sin nada que desplegar. Es el camino más rápido
para tener un sitio funcionando, y sirve mientras el agente se ejecute a mano.

### Nivel 2 · Servidor local de desarrollo (funciona hoy)

```bash
bms-agent serve
```

Levanta en `http://127.0.0.1:8765`:

| Endpoint | Qué hace |
| --- | --- |
| `GET /api/datos` | Los mismos datos que el export, siempre frescos |
| `GET /api/ejecucion` | Estado de la última pasada |
| `POST /api/ejecutar` | Lanza una pasada. Devuelve `409` si ya hay una |

**Escucha solo en `127.0.0.1`, a propósito.** No acepta una IP de red. Es un
servidor de desarrollo para construir el sitio contra datos reales, no un paso
hacia producción.

Acepta peticiones desde `localhost` y `127.0.0.1` en cualquier puerto, así que
un sitio servido con Vite, Next o lo que uses puede consumirlo directamente.

Ejemplo de uso desde el sitio:

```js
const datos = await (await fetch('http://127.0.0.1:8765/api/datos')).json()

async function ejecutar() {
  const r = await fetch('http://127.0.0.1:8765/api/ejecutar', {method: 'POST'})
  if (r.status === 409) return   // ya hay una en curso
  const timer = setInterval(async () => {
    const e = await (await fetch('http://127.0.0.1:8765/api/ejecucion')).json()
    pintarProgreso(e)                       // e.procesadas de e.total
    if (e.estado === 'terminado' || e.estado === 'error') {
      clearInterval(timer)
      recargarDatos()                       // e.coste dice lo que costó
    }
  }, 2000)
}
```

### Nivel 3 · API de verdad (cuando toque desplegar)

Base de datos, API autenticada por rol y modelo de lectura separado. Ver
[portal-consulta.md](portal-consulta.md): ahí está la razón por la que la API
del portal no puede ser esta misma en otro puerto.

---

## El contrato de datos

Lo que devuelven `bms-agent export` y `GET /api/datos`. Es estable: si cambia,
cambia con una nota en este fichero.

```
{
  "totales": {
    "facturas", "importe", "iva", "horas", "proveedores",
    "criticas", "por_revisar", "coste_lectura", "desde", "hasta"
  },
  "filas": [ {                          // una por factura
    "fichero", "proveedor", "numero",
    "fecha",                            // como la imprime la factura
    "orden",                            // AAAA-MM-DD normalizado, para ordenar
    "periodo", "ubicaciones", "semanas",
    "semanas_iso": ["2026-W37"],        // ya resueltas al año ISO correcto
    "horas", "base", "iva", "total",    // números, no cadenas
    "regimen",                          // standard | reverse_charged | kor_exempt | unknown
    "iban", "vencimiento",
    "estado",                           // ok | revisar | critico
    "motivos": [],                      // por qué no está en ok
    "otras_unidades": []                // unidades distintas de la hora
  } ],
  "por_mes":       [ {"mes": "2026-09", "facturas", "total"} ],
  "por_proveedor": [ {"proveedor", "facturas", "total", "horas", "primera", "ultima", "avisos"} ],
  "por_regimen":   [ {"clave", "etiqueta", "facturas", "total"} ],
  "matriz": {
    "semanas": ["2026-W21", ...],       // rango continuo, con los huecos
    "proveedores": [ {"proveedor", "total",
                      "celdas": {"2026-W21": {"importe", "n", "estado"}}} ],
    "maximo"                            // para escalar la rampa de color
  },
  "alertas": [ {"severidad", "regla", "titulo", "detalle", "facturas": []} ],

  "facturacion": {                      // proyeccion de venta, NO facturas emitidas
    "configurada",                      // false si no hay tabla de tarifas
    "margen_por_defecto",
    "propuestas": [ {
      "cliente", "obra", "semana",      // agrupado por los tres
      "lineas": [ {"trabajo", "horas", "coste", "venta",
                   "tarifa_venta", "origen_tarifa"} ],   // tabla | margen
      "horas", "coste", "venta", "margen", "margen_pct",
      "facturas_origen": [], "proveedores": [],
      "avisos": []                      // obra sin cliente, coste que varia...
    } ],
    "sin_mapear": [],                   // obras sin cliente en la tabla
    "no_facturable": [ {"trabajo", "horas"} ],           // horas que no se refacturan
    "totales": {"propuestas", "clientes", "horas", "coste", "venta", "margen", "margen_pct"}
  }
}
```

### Sobre `facturacion`: es una proyección, no una factura

Se calcula desde lo que **los autónomos os han facturado**, no desde las horas
registradas en el planning. Tres cosas que la pantalla tiene que dejar claras:

- Si un autónomo facturó de más o de menos, la proyección hereda el error. El
  cruce contra el planning es lo que lo corrige, y llega en la fase 2.
- Las horas que se pagan no son las que se facturan. Las de viaje son el caso
  típico: van en `no_facturable`.
- **Una obra no es un cliente.** Las facturas de compra dicen "Rijnhaven", no
  de quién es. Ese mapeo está en `config/tarifas.yaml`, y lo que falte sale en
  `sin_mapear` en vez de inventarse.

`origen_tarifa` dice de dónde salió cada precio: `tabla` si estaba pactado,
`margen` si se aplicó el porcentaje sobre el coste. Conviene que se vea en la
pantalla, porque son dos niveles de confianza distintos.

Con `configurada: false` no hay tabla puesta y todo sale sin mapear: es el
estado por defecto y la pantalla debería invitar a rellenarla, no mostrar
ceros.

### Tres cosas que conviene saber al construir contra esto

**Todos los importes agregados van en BASE IMPONIBLE**: `por_mes`,
`por_proveedor`, `por_regimen` y las celdas de la matriz. Comparar regímenes
por el total con IVA premia al régimen y no al gasto, porque una factura con
el IVA trasladado no lleva cuota y otra al 21% sí. El total con IVA está en
cada fila, para cuando lo que interesa es lo que sale del banco.

**Todo el texto de `filas` y de `alertas` viene de PDF de terceros.** Llega sin
escapar, tal como lo dice el documento, y algunos documentos traen texto
diseñado para que un sistema lo obedezca. En el navegador va al DOM con
`textContent`, nunca con `innerHTML`. Si lo exportas a CSV, neutraliza las
celdas que empiezan por `=`, `+`, `-` o `@`, que Excel las ejecuta.

**`estado` ya viene cruzado con todo el histórico.** Una factura señalada por
un duplicado o por un cambio de IBAN sale como `critico` aunque ella sola
parezca correcta. No hay que recalcularlo en el cliente.
