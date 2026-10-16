# Modelo de datos de la V1

Qué guarda el almacén (`datos/bms.sqlite3`), de qué clase es cada tabla, qué
vistas hay encima y de dónde sale cada estado que enseñan la consola, la CLI y
el contrato v2. Es el mapa para quien lea la base o escriba una consulta nueva;
el porqué de cada decisión está en [diseno-v1.md](diseno-v1.md) y en la
especificación ([v1/spec.md](v1/spec.md), §4 y §5), y lo que cambió al
construirla, en [v1/registro.md](v1/registro.md).

La base la crean las migraciones de `src/bms_agent/almacen/sql/`, de la `0001`
a la `0016`, en orden. Una migración aplicada no se edita nunca: su sha256
queda en la tabla `migracion`, y lo que haga falta después va en la siguiente.

---

## Convenciones

- **SQLite 3.37 o posterior**, con `foreign_keys=ON`, `journal_mode=WAL` y
  `busy_timeout=5000`. Cada orden o importación es una transacción
  `BEGIN IMMEDIATE` con su cambio, sus filas de `cambio_campo`, su `evento` y el
  recálculo entero.
- **Tablas `STRICT`** con `INTEGER PRIMARY KEY`. Las claves naturales son
  `UNIQUE` (sha256, `(fuente, id_externo)`, huella, clave).
- **Importes y cantidades en enteros**, nunca en coma flotante (un test lo
  mira):

  | Sufijo | Qué es |
  | --- | --- |
  | `_cent` | Céntimos de euro, con signo (un abono es negativo) |
  | `_mil` | Milésimas (horas, cantidades) |
  | `_e4` | Diezmilésimas de euro (tarifas por unidad) |
  | `_pb` | Puntos básicos (2100 es el 21 %) |

  No hay columna de moneda: un documento en otra moneda se queda sin importes
  y levanta X1. `almacen/unidades.py` es el único conversor; si perdería
  precisión, deja el valor vacío con Q2 en vez de redondear.
- **Fechas** en texto `AAAA-MM-DD`, con `CHECK (x IS NULL OR date(x) IS x)`.
  Los instantes, en UTC ISO-8601. `semana_iso` se calcula en Python y se
  guarda.
- **Columnas `*_doc`**: texto tal como lo imprime un documento de fuera. Nunca
  se interpreta; se pinta con `textContent` y se neutraliza en un CSV.

## Las clases de tabla

| Clase | Qué garantiza la base | Ejemplos |
| --- | --- | --- |
| **Controlada** (*tracked*) | Lleva `rev`. Un disparador exige `NEW.rev = OLD.rev + 1` y la fila de `cambio_campo` de ese cambio; no se borra (se retira con `retirada_en`) | `factura`, `factura_linea`, `factura_imputacion`, `proveedor`, `orden_compra`, `excepcion`, `aplicacion_pago`, `periodo_btw` |
| **Solo escritura** (*append-only*) | No se actualiza ni se borra | `evento` (salvo el sello de su hash), `cambio_campo`, `nota`, `revision`, `hallazgo_evento`, `anulacion`, `cuenta_evento`, `orden_compra_modificacion`, `politica_version`, `hoja_btw`, `periodo_btw_declarada` |
| **Evidencia** (*immutable*) | Lo que llegó de fuera, tal cual | `documento`, `extraccion`, `movimiento_bancario`, `extracto_bancario`, `planning_turno` |
| **Caché** | Se rehace en cada pasada del motor; nunca es la fuente de la verdad | `evaluacion`, `factura_estado`, `prioridad` |

`cuenta_bancaria` es de solo inserción: una cuenta no cambia, lo que le pasa
va a `cuenta_evento`. **Ningún camino lleva de una extracción a
`cuenta_bancaria`** (un test del grafo de imports y una propiedad lo miran):
un IBAN impreso en una factura es `factura.iban_doc`, lo que el documento dice,
y nunca se usa para pagar.

---

## Las tablas

### Infraestructura, acceso y auditoría

| Tabla | Qué guarda |
| --- | --- |
| `migracion` | Cada migración aplicada, con su sha256 |
| `politica_version` | Cada fichero de configuración tal como se aplicó (reglas, prioridad, BTW, empresa, mapeos), con su sha256 |
| `usuario` | Personas y usuarios de sistema (sistema, extractor, importador, motor), con el hash de su token personal |
| `permiso`, `rol`, `rol_permiso`, `usuario_rol` | Los catorce permisos, los roles (de partida: `administrador`, `administracion`, `consulta`) y quién tiene cuál, con fechas |
| `evento` | Cada orden, importación, pasada, denegación y apertura de un documento, encadenados por hash |
| `cambio_campo` | Cada cambio de cada campo: antes y después, fuente anterior y nueva, motivo (obligatorio en una corrección a mano). Es el historial de cambios |

### Evidencia

| Tabla | Qué guarda |
| --- | --- |
| `documento` | Cada fichero recibido, por su sha256: nombre, por dónde llegó, cuándo y si el original está en el almacén (`ruta_cas`; sin él, Q4) |
| `extraccion` | Cada lectura de un documento por el modelo, con modelo, versiones de prompt y esquema y su contenido. Ninguna se sobrescribe |
| `importacion` | Cada lote importado (Exact, banco, planning, maestros): fuente, fichero, mapeo, qué cubre, estado y rechazos |
| `extracto_bancario`, `movimiento_bancario` | Los extractos del banco con sus saldos (para K6) y cada movimiento |
| `planning_turno` | Cada turno de cada foto del planning de TRNSPRNT; una foto aceptada no cambia |

### Datos maestros

| Tabla | Qué guarda |
| --- | --- |
| `proveedor`, `cliente`, `contacto` | El maestro (de Exact y TRNSPRNT) y lo local: plazos, BTW-id, KvK, teléfono de verificación |
| `objeto`, `recurso` | Los Objetos (obras, ubicaciones) de cada cliente y las personas o equipos que trabajan |
| `alias` | Otros nombres exactos de un proveedor, cliente, Objeto o recurso. Un IBAN nunca es un alias |
| `cuenta_bancaria`, `cuenta_evento` | El registro de cuentas y todo lo que le pasa a cada una: vista en Exact, en un documento, verificada por teléfono, rechazada… |
| `beneficiario_conocido` | Cobradores que no son proveedores (Belastingdienst, nóminas, alquiler) para que F7 no salte |
| `tarifa_acordada`, `ciclo_facturacion` | Tarifas pactadas de compra y venta y cada cuánto se factura a cada cliente u Objeto |
| `orden_compra`, `orden_compra_objeto`, `orden_compra_modificacion` | Las PO de los dos lados (`cliente`: lo que BMS puede facturar; `proveedor`: lo que le pueden facturar), sus Objetos y sus modificaciones; el valor vigente es el de la última |

### Facturas

| Tabla | Qué guarda |
| --- | --- |
| `factura` | Una tabla para compras (`entrante`) y ventas (`saliente`): número, partes, lo impreso (`*_doc`), fechas, periodo de cabecera, importes, `iban_doc`, y si está anulada o fusionada en otra |
| `factura_linea` | Lo que dice el papel, línea a línea (con la semana impresa, `semana_doc`) |
| `factura_imputacion` | El reparto de cada línea a Objeto, recurso, PO, horas e importe. **Todo total lee de aquí**; dividir una línea es retirar su imputación y crear otras |
| `factura_iva` | El desglose del IVA, con su tratamiento y su rúbrica |
| `factura_referencia` | Las referencias impresas (PO, orden, proyecto…) y la PO con la que casan |
| `factura_cita` | Una factura que un documento nombra, tal como la nombra |
| `factura_relacion` | Abona, anula, corrige, sustituye o relacionada; propuesta, confirmada o rechazada. Solo la confirmada mueve saldos, IVA y totales |
| `procedencia_campo` | Por campo: su valor, su original (también el literal impreso), su fuente (una de las siete), si es dudoso, quién lo cambió y quién lo verificó |
| `nota` | Notas de las personas |

### Pagos y conciliación

| Tabla | Qué guarda |
| --- | --- |
| `aplicacion_pago` | Qué parte de qué movimiento (o de Exact, o a mano) paga qué factura; propuesta, confirmada o retirada. No hay planes de pago ni estado «aprobada para pagar» |
| `conciliacion` | La traza de una línea de factura a los turnos del planning que cubre |

### Controles

| Tabla | Qué guarda |
| --- | --- |
| `ejecucion_reglas` | Cada pasada del motor: por qué, con qué `hoy`, con qué catálogo y qué política |
| `evaluacion` | Caché: el último resultado de cada regla en cada fila (`ok`, `fallo`, `sin_datos`, `no_aplica`) |
| `hallazgo`, `hallazgo_objetivo`, `hallazgo_evento` | Cada aviso, las facturas y campos que toca, y su historia (detectado, cambio de evidencia, cerrado, aceptado, reabierto…) |
| `anulacion` | Las anulaciones de avisos, con su huella y su caducidad; vale solo mientras la evidencia no cambia |
| `excepcion`, `excepcion_hallazgo` | El trabajo: título, responsable, a quién se espera, resolución |
| `revision` | Cada «revisada» o «devuelta», con la huella del contenido que se revisó |
| `prioridad_manual` | Subidas de prioridad a mano (nunca bajadas) |
| `factura_estado`, `prioridad` | Cachés de estado y de prioridad (abajo) |

### Reextracción (paso 6)

| Tabla | Qué guarda |
| --- | --- |
| `reextraccion`, `reextraccion_resultado` | Cada pasada de volver a leer documentos con otro modelo o prompt, su presupuesto y lo que dio cada documento (candidata o reintento) |
| `activacion` | Una candidata que pasa a ser la extracción vigente de su documento; la activa una persona con `admin` después de la comparación |
| `linea_sin_casar` | Una línea que una persona editó y que la lectura nueva ya no trae (M2) |

### BTW

| Tabla | Qué guarda |
| --- | --- |
| `periodo_btw` | El estado de cada trimestre (abierto, listo para revisión, presentado) y la referencia de la presentación. Lo pone una persona; el agente no presenta nada |
| `hoja_btw` | Cada hoja de trabajo que se marcó lista o se presentó, con su sha256 |
| `periodo_btw_declarada` | Lo que se declaró de cada factura al presentar (contra lo que compara C4) |

---

## Las vistas

Ninguna depende de la fecha de hoy y todas suman enteros. Lo que depende de
hoy (vencida, esta semana, el año hasta hoy) lo calcula Python con el `hoy` del
reloj del almacén y, cuando hace falta en SQL, lo deja en una caché.

| Vista | Para qué |
| --- | --- |
| `v_extraccion_vigente` | La extracción vigente de cada documento |
| `v_cuenta_estado` | El estado de cada cuenta bancaria |
| `v_factura_relaciones` | Lo que mueven las relaciones confirmadas de cada factura (acreditado, sustituida por, anulada por un abono) |
| `v_factura_saldo` | Total, acreditado, pagado, saldo y el estado de pago sin `hoy` |
| `v_imputacion_vigente` | Las imputaciones activas de las facturas que cuentan (ni anuladas, ni fusionadas, ni sustituidas) |
| `v_iva_vigente`, `v_btw_linea` | Las líneas de IVA que cuentan y su trimestre |
| `v_proveedor_totales`, `v_cliente_totales` | Lo facturado de siempre por proveedor y por cliente |
| `v_po_vigente`, `v_po_consumo` | El valor vigente de cada PO y lo consumido |
| `v_turno_vigente`, `v_planning_estado` | La última foto aceptada del planning por día, y por turno las horas conciliadas con compras y ventas |
| `v_factura_ediciones` | Las marcas de edición a mano por factura |
| `v_factura_listado` | Una fila por factura para la búsqueda (§18): la contraparte impresa, el periodo de prestación, importes, si cuenta, y lo que dice la caché `factura_estado` |
| `v_objeto_periodo` | Por Objeto y mes de la fecha de factura: ingresos, costes, margen y horas |

Diferencias con la especificación: no hay `v_campo_calidad` (la calidad de un
campo depende de sus avisos y la calcula `consultas.py`), ni `v_cliente_cobro`
(los plazos de cobro los calcula la vista del cliente). `v_objeto_periodo` va
solo por mes: la semana ISO reparte una línea de un mes entre sus semanas por
sus días y eso se hace en Python (`trabajo.importes_por_semana`).

---

## Dónde vive cada estado

| Estado o valor | De dónde sale |
| --- | --- |
| **Pendiente, vencida, pagada, anulada, acreditada** | `v_factura_saldo` más el `hoy` del motor, en la caché `factura_estado`. Pagada es saldo dentro de la tolerancia; un pago parcial sigue pendiente o vencida con lo que queda. El vencimiento efectivo (el impreso o la fecha más el plazo) también está en la caché |
| **Sin revisar, necesita revisión, revisada** | La última `revision` comparada con la huella del contenido de hoy, en `factura_estado` |
| **Calidad del dato** | Por campo, de sus avisos y sus marcas, en el orden faltante, discrepancia, anomalía, dudoso, verificado; sin ninguna, neutra (nunca verde). La de la factura, en `factura_estado` |
| **Marcas de edición** (editada, suplementada, corregida, sin resolver) | `procedencia_campo`, resumidas en `v_factura_ediciones` y en `factura_estado` |
| **Periodo de prestación** | El de la cabecera o, si no lo imprime, el de sus imputaciones con la misma cuenta que las horas (fechas de la imputación o de la línea, la semana impresa con el año de la fecha de la factura). Lo escribe el motor en `factura_estado` (migración 0016) y lo lee `v_factura_listado` |
| **Prioridad** (normal, atención, urgente, bloqueada) | `prioridad.py`, en `factura_estado` (facturas) y en `prioridad` (excepciones, PO, proveedores, clientes, Objetos, trimestres) |
| **Estado de una cuenta bancaria** | `v_cuenta_estado`: manda el último evento de una persona; si no, heredada o registrada sin verificar |
| **Estado de una excepción, del BTW** | Lo pone una persona, con su evento |
| **Si una factura cuenta en los totales** | `v_factura_listado.cuenta`: ni anulada, ni copia fusionada, ni sustituida o corregida por otra. La búsqueda, las vistas de las partes, los Objetos y el BTW usan la misma regla |

La búsqueda y el panel leen las cachés: dicen de qué día es su estado
(`estado_del`) y si es el de hoy (`al_dia`). Si no lo es, falta
`bms-agent recalcular --diaria`.
