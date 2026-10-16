# Diseño de la V1

Resumen en castellano de la especificación de trabajo de la V1, pensado para
el dueño del negocio y para quien desarrolla la web. La especificación
completa, con cada tabla, columna y criterio de aceptación, está en
[v1/spec.md](v1/spec.md) (en inglés, porque es lo que siguen los agentes que
construyen). Si este resumen y la especificación no coinciden, manda la
especificación.

> **Principio, igual que en [arquitectura.md](arquitectura.md).** El modelo
> extrae. El código determinista decide. Una persona firma. Un IBAN nunca se
> toma de un documento para pagar. No hay pagos automáticos ni declaración
> automática del BTW.

---

## 1. Qué hace la V1 y qué no hace

La V1 es una herramienta de **vigilancia y control**: lee, compara, avisa y
deja constancia de lo que decide una persona. No emite nada ni mueve dinero.

**Lo que hace**

| Función | Qué significa en la V1 |
| --- | --- |
| Vigilancia de facturas | Facturas de compra y de venta, con su estado (pendiente, vencida, pagada, anulada o abonada) y sus comprobaciones. |
| Vigilancia de pagos | Cruza los extractos del banco y los pagos de Exact con las facturas. Una factura solo cuenta como pagada cuando el saldo pendiente queda dentro de la tolerancia. |
| Conciliación con el planning | Horas, objeto, periodo y tarifa de cada factura contra los turnos aprobados de TRNSPRNT. |
| Imputación a objetos | Cada línea de factura se reparte entre objetos (y recursos), y se puede corregir a mano. |
| Vigilancia de órdenes de compra (PO) | Consumo, valor restante, caducidad y previsión de agotamiento. |
| Visión de caja | Cobros y pagos esperados por fecha de vencimiento, más lo cobrado y pagado de verdad. |
| Visión del IVA / BTW | IVA por trimestre y por rúbrica, facturas que necesitan revisión de IVA y estado de cada trimestre. |
| Conciliación automática | Las comprobaciones del catálogo (sección 4), que el código ejecuta sin intervención. |
| Detección de excepciones y anomalías | Hallazgos con su historia, agrupados en excepciones de trabajo con responsable y fecha de seguimiento. |
| Revisión humana | Una persona marca una factura como revisada o la devuelve. Una factura limpia dice «sin objeciones del sistema», nunca «aprobada». |
| Verificación humana de datos bancarios | Todo IBAN nuevo o cambiado queda bloqueado hasta que alguien lo verifique por teléfono, al número que ya constaba antes del documento. |
| Registro de auditoría | Quién vio, cambió, revisó o resolvió qué, cuándo y por qué, en un registro encadenado que no se puede editar. |
| Solo euros | Cualquier documento en otra moneda se bloquea y queda fuera de todos los totales. |

**Lo que no hace**

- No crea facturas.
- No prepara borradores de factura. La proyección de facturación que ya
  existe se presenta como «facturación esperada» o «trabajo sin facturar», no
  como borradores.
- No gestiona pagos parciales: no hay planes de plazos. Un pago parcial se
  registra por su importe real, la factura sigue pendiente con el resto y
  salta el aviso K2.
- No ejecuta pagos: no genera ficheros SEPA (pain.001) ni guarda credenciales
  del banco.
- No aprueba pagos: resolver un aviso, anularlo o marcar una factura pagada
  nunca equivale a una aprobación de pago.
- No presenta el BTW: el estado «presentado» lo pone una persona, con la
  referencia de la presentación.
- No escribe nada en Exact.

Un conjunto de tests de alcance, activo desde el paso 4 de la construcción,
comprueba que estas exclusiones siguen siendo ciertas.

---

## 2. El modelo de datos en palabras llanas

Todo vive en una base de datos SQLite local (`datos/bms.sqlite3`), con SQL
que se puede llevar a Postgres más adelante. Los originales se guardan aparte,
cada uno con el nombre de su huella (sha256), en modo de solo lectura. La
lista completa de tablas y vistas, tal como quedaron construidas, está en
[modelo-datos.md](modelo-datos.md).

**Cómo se guardan los importes.** Como números enteros, nunca con decimales
flotantes: céntimos de euro, milésimas de hora, diezmilésimas de euro para las
tarifas y puntos básicos para los tipos de IVA. Así las sumas y los filtros
del tipo «importe ≥ 10.000» son exactos. El texto tal como venía impreso
(por ejemplo «8.740,00») se conserva siempre al lado.

**Tres clases de tablas.**

- **Con seguimiento:** cada cambio necesita su fila en el historial de
  cambios, o la propia base de datos lo rechaza. Las filas no se borran: se
  retiran.
- **Solo añadir:** no admiten ni cambios ni borrados (eventos, historial,
  anulaciones, revisiones).
- **Caché:** se reconstruyen en cualquier momento y nunca son la fuente de la
  verdad (estado de cada factura, prioridades).

**Los bloques del modelo**

| Bloque | Qué guarda |
| --- | --- |
| Infraestructura, acceso y auditoría | Versiones de la base de datos, cada versión de la configuración aplicada, usuarios, roles y permisos, el registro de eventos encadenado y el historial campo a campo con el valor anterior, el nuevo y el motivo. |
| Evidencia (inmutable) | Cada documento recibido, cada extracción del modelo (varias por documento, ninguna se sobrescribe), cada importación, los extractos bancarios con sus saldos, los movimientos del banco y cada lote del planning como una foto fija. |
| Datos maestros | Proveedores, clientes, contactos, objetos, recursos, alias de nombres, cuentas bancarias con su historial de verificación, beneficiarios conocidos que no son proveedores (Belastingdienst, nóminas, alquiler), tarifas acordadas, ciclos de facturación y órdenes de compra con sus modificaciones. |
| Facturas | Una sola tabla para compra y venta, con sus líneas tal como están impresas, las imputaciones de cada línea a objetos (de donde salen todos los totales), el desglose de IVA, las referencias impresas, las relaciones entre facturas (abona, anula, corrige, sustituye) y la procedencia de cada campo. |
| Pagos y conciliación | Qué pago o movimiento del banco se aplica a qué factura y por cuánto, y qué turnos del planning respaldan cada línea. |
| Controles | Cada ejecución de las reglas, el último resultado de cada regla, los hallazgos con su historia, las anulaciones, las excepciones, las revisiones, las subidas manuales de prioridad y la caché de estado y prioridad. |
| BTW | Un periodo por trimestre con sus plazos, su estado y, al presentarlo, quién, cuándo, la referencia y la huella de la hoja de cálculo. |

**Detalles que importan al negocio**

- **El IBAN de un documento es solo lo que el documento dice.** Se guarda
  para compararlo, nunca para pagar. Ningún camino del código lleva de una
  extracción al registro de cuentas bancarias, y hay tests que lo comprueban.
- **El IBAN completo se ve en la consola interna** y solo se enmascara en la
  proyección del portal, como dice [portal-consulta.md](portal-consulta.md).
- **El valor original nunca se pierde.** Cada campo sabe de dónde viene su
  valor actual (una de siete fuentes: extracción, importación, planning,
  maestro, entrada manual, corrección manual o calculado), cuál era el
  original y cuál dio por última vez la fuente automática. Un valor manual
  gana a uno automático, y deshacer un cambio es otro cambio.
- **Los campos que pertenecen a Exact o TRNSPRNT no se corrigen aquí.** La
  corrección se hace en ese sistema y llega con la siguiente importación.
- **No hay clave única por proveedor y número de factura**, a propósito: así
  el sistema puede ver el duplicado (B2) en lugar de rechazarlo en silencio.
- **Una factura reenviada y fusionada** conserva su fila, pero queda fuera de
  todos los totales.
- **El texto de terceros** (columnas que terminan en `_doc`) se muestra como
  texto, se neutraliza en las exportaciones CSV y nunca se interpreta.

**De dónde sale cada estado**

| Estado o valor | Cómo se calcula |
| --- | --- |
| Pendiente / vencida / pagada / anulada o abonada | Del saldo de la factura y la fecha de hoy. Pagada solo si el saldo pendiente está dentro de la tolerancia (por defecto 0,00). |
| Sin revisar / necesita revisión / revisada | De la última revisión comparada con la huella del contenido actual. Cualquier cambio posterior invalida la revisión. |
| Calidad del dato | Por campo, en este orden: faltante, discrepancia, anomalía, dudoso, verificado. Un campo sin nada de eso se muestra neutro, nunca en verde. |
| Marcas de edición manual | De la procedencia de cada campo. «Sin resolver» es un valor manual distinto del automático y no verificado. |
| Estado del IBAN | Gana el último evento humano; si no hay, «heredada» o «registrada sin verificar». |
| Estado de una excepción y del BTW | Lo pone una persona y queda auditado. |
| Prioridad | La calcula el algoritmo de la sección 5. |

**Permisos.** Los once de la lista de funciones (ver facturas, editar la
extracción, añadir información, cambiar objeto, cambiar PO, marcar pagada,
anular o abonar, resolver aviso, anular aviso, confirmar IBAN, administrar)
más tres propuestos: revisar factura, gestionar BTW e importar datos. Los
usuarios del sistema (extractor, importador, motor) no pueden tener roles.
Cuando hay dos personas con un permiso se exige la separación de funciones;
con una sola persona se permite, pero queda marcado como «autorrevisado».

---

## 3. Qué es un hallazgo, una excepción y una revisión

- **Hallazgo:** el resultado fallido de una regla sobre una factura u otra
  entidad. Tiene una identidad (regla y objetivo) y una evidencia (los valores
  comparados). Si la evidencia cambia, el hallazgo se reabre aunque estuviera
  resuelto o anulado.
- **Hallazgo pegajoso:** no se cierra solo aunque la condición desaparezca.
  Queda como «condición desaparecida» hasta que una persona lo cierra. Son los
  del IBAN, los duplicados, las anomalías de pago, el cambio de régimen de
  IVA, el exceso de PO, R2 y R3. Es lo que evita «editar hasta que se vaya el
  aviso».
- **Anulación:** necesita el permiso de anular avisos y un motivo de al menos
  10 caracteres, solo vale para reglas que lo permiten, queda atada a la
  evidencia que aceptó y puede caducar. Si hay una segunda persona, firma
  también; si no, queda marcada como «autoaprobada».
- **Excepción:** la unidad de trabajo. Una por entidad afectada (factura, PO,
  proveedor, trimestre, movimiento del banco o importación), que agrupa sus
  hallazgos. Tiene responsable, estado (abierta, asignada, esperando a un
  tercero, resuelta) y fecha de seguimiento (como mucho hoy + 14 días por
  defecto). No se puede resolver mientras tenga un bloqueo abierto sin anular.
- **Revisión:** solo una persona con el permiso de revisar puede marcar una
  factura como revisada, y solo si no tiene bloqueos ni retenciones abiertos
  sin anular.
- **«Sin datos» nunca es «correcto».** Una regla que no puede evaluarse (por
  ejemplo, porque aún no hay planning) lo dice así.

---

## 4. Catálogo de comprobaciones

**Cómo leer las tablas**

- **Resultado** si falla, como en [validacion-facturas.md](validacion-facturas.md) §2:
  **Bloquea** (no puede pagarse ni darse por buena), **Retiene** (va a la
  cola de revisión humana y no se paga hasta resolverse) o **Avisa** (sigue
  adelante, pero queda en el informe y en las excepciones).
- **C** es factura de compra (entrante) y **V** es factura de venta
  (saliente), cuando el resultado es distinto en cada sentido.
- **No anulable** significa que nadie puede aceptar el hallazgo sin corregir
  la causa. **Pegajosa** significa que no se cierra sola.
- Las tolerancias y los umbrales están en `config/reglas.yaml`.

### Datos e identidad

| ID | Qué comprueba | Resultado | Anulación |
| --- | --- | --- | --- |
| Q1 | Falta un campo obligatorio para el sentido de la factura: número, contraparte, fecha, periodo, base, IVA o régimen, total | Retiene (bloquea si falta número, total o contraparte) | No anulable |
| Q2 | Un campo crítico es dudoso (el modelo lo marcó así o no se pudo leer) y nadie lo ha verificado | Retiene | No anulable |
| Q3 | Las notas del documento contienen texto marcado (señal de un intento de inyección) | Avisa y abre excepción | Anulable |
| Q4 | No se conserva el documento original | Avisa | Anulable |
| X1 | No está en euros (campo de moneda, símbolo en los importes o moneda del banco). Queda fuera de todos los totales. | Bloquea | No anulable, pegajosa |
| M1 | Un valor manual difiere del último valor automático y no está verificado (la marca «sin resolver») | Avisa, calidad «discrepancia» | — |
| Z1 | Una fuente es más antigua que su límite de frescura. Las reglas que dependen de ella dan «sin datos». | Avisa y muestra un aviso en pantalla | — |
| Z2 | Filas de una importación rechazadas, o contraparte, objeto o recurso desconocidos | Retiene | No anulable |
| A0 | Contraparte desconocida o ambigua | Retiene | No anulable |
| A1 | Nombre completo y dirección presentes | Retiene | — |
| A2 | El nombre, el KvK o el btw-id impresos difieren del maestro | Retiene | Anulable |
| A3 | Número KvK presente y con formato de ocho dígitos | Avisa | — |
| A5 | btw-id presente y con formato válido | Bloquea si falta y no se menciona la KOR | — |
| A7 | Los datos cambian respecto al historial del propio proveedor (btw-id o KvK: retiene; nombre o dirección: avisa) | Retiene / Avisa | Anulable; pegajosa para btw-id y KvK |
| A8 | La factura no va dirigida a BM Support BV (comparado con `config/empresa.yaml`). En la entrada de ventas, un emisor que no es BMS significa que el documento entró por la vía equivocada. | Retiene (bloquea si entró por la vía equivocada) | Anulable |

A4 y A6 necesitan consultar el KvK y VIES, así que son comprobaciones
periódicas fuera de la V1.

### Duplicados

| ID | Qué comprueba | Resultado | Anulación |
| --- | --- | --- | --- |
| B1 | Número de factura presente | Bloquea | No anulable |
| B2 | Misma contraparte y mismo número normalizado, sin fusionar ni relacionar | Bloquea | Se cierra fusionando o relacionando; anular exige segunda firma; pegajosa |
| B3 | Misma contraparte, total con diferencia de hasta 0,01, como mucho 14 días de distancia, periodos compatibles y número distinto | Retiene | Anulable, pegajosa |
| B4 | Periodos de cargo solapados (por objeto cuando las líneas lo nombran); se excluyen las relaciones confirmadas | Retiene | Anulable, pegajosa |
| B5 | Horas duplicadas: mismo recurso, objeto y fecha en dos líneas sin relación, o un turno conciliado con más horas de compra de las que tiene | Retiene | Anulable, pegajosa |
| V7 | Facturación duplicada: los casos de B2, B3 o B5 en facturas de venta, o un turno facturado por más horas de las que tiene | Retiene | Anulable, pegajosa |

### Fechas

| ID | Qué comprueba | Resultado |
| --- | --- | --- |
| C1 | Fecha de factura presente y no futura | Retiene |
| C2 | Periodo de prestación presente (en la cabecera o en las líneas) | Bloquea |
| C3 | Fecha de factura anterior al fin del periodo | Avisa |
| C4 | Fecha o periodo en un trimestre ya marcado como presentado, o cambiado después de presentarlo | Avisa y se añade a la lista del trimestre |
| C5 | El vencimiento impreso es más corto que el plazo de pago acordado | Avisa |

### Aritmética e IVA

| ID | Qué comprueba | Resultado | Anulación |
| --- | --- | --- | --- |
| D1 | Hay desglose | C: bloquea; V: retiene | No anulable |
| D2 | La suma de las líneas es igual a la base (0,01 por línea más 0,02) | C: bloquea; V: retiene | No anulable |
| D2b | Cantidad por tarifa es igual al importe de la línea (0,01) | C: bloquea; V: retiene | Anulable |
| D3 | Base por tipo es igual al IVA, para cada tipo | Bloquea | No anulable |
| D4 | Base más IVA es igual al total | Bloquea | No anulable |
| D6 | El desglose de IVA cuadra con la cabecera | Bloquea | No anulable |
| I1 | Las imputaciones activas de una línea suman el importe de la línea | Retiene | No anulable |
| E0 | Falta información de IVA (tratamiento desconocido, o IVA general sin tipo o sin importe) | Retiene | No anulable |
| E1 | El tipo difiere del régimen registrado del proveedor | Retiene | Anulable |
| E2 | El régimen ha cambiado respecto a la factura anterior | Retiene | Anulable, pegajosa |
| E3 | Proveedor con KOR que, sin embargo, cobra IVA | Bloquea | No anulable |
| E4 | Inversión del sujeto pasivo con IVA cobrado, o falta el btw-id de BMS | Bloquea | No anulable |
| E5 | El acumulado pagado se acerca al umbral de la KOR | Avisa | — |
| E7 | Tipo o tratamiento inusual: tipo distinto de 0, 9 o 21 (lista configurable); 0 % o inversión del sujeto pasivo en una venta a un cliente no marcado como apto | Retiene | Anulable |

Los identificadores D2 y D2b son los del código actual. El catálogo antiguo
llamaba D2 a la comprobación de cantidad por tarifa; se mantiene la
numeración del código y se corrige la documentación.

### Datos bancarios

Ninguna de estas reglas se puede anular y todas son pegajosas. Solo se cierran
con una verificación, un rechazo o un cambio en los datos.

| ID | Qué comprueba | Resultado |
| --- | --- | --- |
| F1 | El IBAN no supera el dígito de control (mod-97) | Bloquea |
| F2 | El IBAN del documento no es una cuenta pagable de este proveedor | Bloquea |
| F3 | IBAN nuevo o cambiado respecto al registro (venga de un documento, de Exact o de TRNSPRNT); necesita verificación por teléfono | Bloquea |
| F4 | IBAN registrado para otro proveedor, o texto sobre factoring, cessie o G-rekening | Bloquea y escala |
| F5 | IBAN añadido, cambiado o retirado en una importación del maestro posterior a la de referencia | Bloquea |
| F6 | Exact y TRNSPRNT no coinciden en el IBAN de un proveedor | Bloquea |
| F7 | Un cargo del banco asociado a un proveedor fue a un IBAN no pagable para él (y que no es un beneficiario conocido) | Bloquea, y como mínimo Urgente |
| F8 | Verificación sin efecto: el número al que se llamó no es el teléfono del maestro que existía antes del documento, el teléfono cambió dentro del periodo de espera, o la persona no tenía el permiso | Bloquea |
| F9 | Ha cambiado el teléfono de verificación (empieza el periodo de espera) | Avisa |
| F10 | Una factura de venta muestra un IBAN que no es de BMS | Retiene |

**Qué cuenta como cuenta de confianza.** La primera importación del maestro
es la **referencia**: sus cuentas quedan como «heredadas», se aceptan, se
muestran sin verificar y generan una única tarea de atestación de nivel
Atención. Todo lo que se añada, cambie o retire en importaciones posteriores
bloquea (F5) hasta verificarlo por teléfono. Una cuenta es **pagable** si está
verificada, atestada o heredada, **y** aparece en el último lote aceptado de
Exact. La llamada tiene que hacerse al teléfono del maestro que ya existía
antes de que llegara el documento, y un cambio de teléfono abre un periodo de
espera (14 días por defecto). Queda disponible, como opción de política, el
comportamiento más estricto: nada heredado es pagable hasta que se atesta.

### Pagos

| ID | Qué comprueba | Resultado | Anulación |
| --- | --- | --- | --- |
| K1 | Vencida (compra: pasada la fecha; venta: más de N días después) | Avisa y abre excepción | Anulable |
| K2 | Los pagos confirmados no coinciden con el saldo (pago parcial o de más) | C: retiene; V: avisa | No anulable, pegajosa |
| K3 | Marcada pagada a mano y, pasados N días, sin rastro en el banco | Avisa | Anulable |
| K4 | Pago doble: dos cargos para una factura, o misma contraparte, importe y referencia en 30 días | Bloquea | No anulable, pegajosa |
| K5 | Pagada mientras estaba bloqueada | Retiene | No anulable, pegajosa |
| K6 | Salto en la continuidad del extracto: el saldo inicial no coincide con el final anterior, o falta un número de secuencia | Bloquea (todos los estados posteriores al hueco) | No anulable, pegajosa |
| K7 | Movimiento del banco sin casar pasados N días | Avisa | Anulable |
| K8 | El banco y Exact no coinciden en un pago | Retiene | No anulable |

### Planning, facturas de compra

Dan «sin datos» hasta que se importe el planning. G1 pasa a bloquear cuando el
planning se declare obligatorio.

| ID | Qué comprueba | Resultado | Anulación |
| --- | --- | --- | --- |
| G1 | No hay asignación del proveedor o del recurso en el periodo facturado | Bloquea | Exige segunda firma |
| G2 | Horas facturadas contra horas aprobadas, al nivel más fino que tengan los dos lados (recurso y día, luego objeto y día, luego objeto y semana); tolerancia de 0,25 h por día | Retiene | Anulable |
| G3 | Tarifa contra la tarifa acordada (de la más concreta a la más general), si no la del turno en el planning, si no el historial. Si la coincidencia es ambigua da «sin datos» y abre excepción. | Retiene; bloquea por encima del exceso configurado | Anulable (la parte que bloquea exige segunda firma) |
| G4 | Objeto contra el planning | Retiene | Anulable |
| G5 | Periodo y semana ISO contra el planning | Retiene | Anulable |
| G6 | Recargos facturados a su propia tarifa acordada | Retiene | Anulable |
| G7 | Un lote nuevo del planning cambia horas ya conciliadas con esta factura | Avisa | Anulable |

### Facturas de venta

Todas retienen y todas se pueden anular.

| ID | Qué comprueba |
| --- | --- |
| V1 | Horas facturadas contra turnos facturables aprobados |
| V2 | El objeto existe, pertenece al cliente facturado y está activo |
| V3 | Periodo contra el planning |
| V4 | Tarifa de venta contra la tarifa acordada (tanto por encima como por debajo) |
| V5 | Faltan horas facturables aprobadas dentro de un cliente, objeto y periodo que sí se facturó |
| V6 | Posible trabajo sin facturar: el periodo terminó hace más de los días de gracia, hay horas facturables aprobadas y ninguna línea de venta las cubre. Se valora a la tarifa de venta acordada o, si no la hay, se marca «estimado». |
| V8 | Falta un periodo de facturación según el ciclo de facturación |
| V9 | El planning cambió después de facturar |

### Órdenes de compra

El consumo de una PO es la base (sin IVA) de las imputaciones de facturas no
anuladas ni sustituidas, menos los abonos confirmados, ordenadas por fecha de
factura y luego por identificador.

| ID | Qué comprueba | Resultado | Anulación |
| --- | --- | --- | --- |
| P1 | PO válida: existe, es de la misma parte, cubre el objeto, las fechas del trabajo caen dentro de su vigencia y no está cerrada | Retiene | Anulable |
| P2 | Falta la PO donde se exige | Retiene | Anulable |
| P3 | PO desconocida o equivocada (no existe, o es de otra parte u otro objeto) | Retiene | Anulable |
| P4 | La factura supera el valor que le quedaba a la PO | Retiene | Anulable, pegajosa |
| P5 | Consumida al 80 % o más | Avisa | — |
| P6 | Consumida del todo, y se sigue facturando contra ella | Retiene | Anulable |
| P7 | Caduca en 30 días con valor pendiente (retiene si ya caducó y hay trabajo planificado después) | Avisa / Retiene | Anulable |
| P8 | El trabajo planificado por la tarifa de venta supera el valor restante | Avisa | — |
| P9 | La previsión de agotamiento (ritmo de 8 semanas) cae antes de 14 días previos a la fecha de fin | Avisa | — |
| P10 | Lo facturado más lo no facturado más lo planificado supera el valor de la PO | Retiene | Anulable |

### Relaciones entre facturas y anomalías

| ID | Qué comprueba | Resultado | Anulación |
| --- | --- | --- | --- |
| R1 | Un abono o una corrección se refiere a una factura desconocida | Retiene | Anulable |
| R2 | Los abonos superan la factura original | Retiene | No anulable, pegajosa |
| R3 | La original y su sustituta están las dos pendientes, o las dos pagadas | Bloquea | No anulable, pegajosa |
| R4 | Abono sin relación confirmada | Avisa | — |
| R5 | Relación propuesta por la extracción, pendiente de confirmar | Avisa | — |
| U1 | Importe inusual comparado con las bases anteriores de la misma contraparte | Avisa y abre excepción | Anulable |

U1 compara con las facturas anteriores no anuladas de esa contraparte: con 6 o
más, usa la mediana y la desviación absoluta mediana (umbral 3,5); con 3 a 5,
avisa si el importe es más del doble o menos de la mitad de la mediana; con
menos de 3, da «sin datos».

Las relaciones que propone el modelo (abonos, correcciones, sustituciones) son
siempre **propuestas**: solo cuentan en saldos, IVA y B4 cuando una persona
las confirma. Un enlace equivocado marcaría en silencio una factura como
abonada.

### Correspondencia con la lista de funciones

| Comprobación de la lista | Reglas |
| --- | --- |
| Compra: horas, objeto y periodo contra el planning | G2, G4, G5 (más G1) |
| Compra: tarifa contra la acordada | G3 |
| Total contra líneas | D2, D2b, D4 (más I1) |
| Cálculo del IVA | D3, D6, E3, E4 |
| Factura duplicada | B2, B3 |
| Horas duplicadas | B5 |
| Periodos solapados | B4 |
| Datos del proveedor contra el historial | A2, A7 |
| IBAN contra el IBAN verificado | F2 |
| IBAN cambiado | F3, F5, F6 |
| Importe inusual | U1 |
| Venta: horas, objeto y periodo contra el planning | V1, V2, V3 |
| Venta: tarifa contra la acordada | V4 |
| Horas facturables que faltan | V5 |
| Posible trabajo sin facturar | V6 |
| Facturación duplicada | V7 |
| Periodo de facturación que falta | V8 |
| Alertas de PO (límite, consumida, exceso, falta, desconocida, caducidad, planificado, previsión, esperado) | P5, P6, P4, P2, P3, P7, P8, P9, P10 |
| IVA: información que falta / cálculo incorrecto / tratamiento inusual | E0 / D3, D6 / E1, E2, E7 |

Las «facturas que requieren revisión de IVA» son las del trimestre con
hallazgos de IVA abiertos, más C4. Se añaden más allá de la lista: Q1–Q4, X1,
M1, Z1–Z2, A0, A8, C5, F1, F4, F7–F10, K1–K8, G6, G7, V9, R1–R5 e I1.

**Cómo funciona el motor.** Cada regla es una función pura sobre una foto fija
de los datos: no toca la base de datos, el reloj, el entorno ni la red, y un
test lo comprueba. Cada orden y cada importación terminan con un recálculo
completo en la misma transacción, y además se recalcula una vez al día.

---

## 5. Algoritmo de prioridad

La prioridad es una función pura con cuatro niveles: **Normal**, **Atención**,
**Urgente** y **Bloqueada**. Los pesos están en `config/prioridad.yaml` y cada
versión queda registrada.

**Capa 1: suelos.** Un suelo es el nivel mínimo que impone un hallazgo abierto
y no anulado.

| Suelo | Lo provocan |
| --- | --- |
| **Bloqueada** | Cualquier hallazgo que bloquea: B1, B2, C2, A5, X1, K4, K6, R3; D1, D2 y D2b en compras; D3, D4, D6, E3, E4; la familia F (salvo F10, que solo retiene); G1 cuando el planning sea obligatorio; Q1 por número, total o contraparte; A8 cuando el documento entró por la vía equivocada. |
| **Urgente** | B3, B4, B5, V7, F7, P4, P6, P10, K5; cualquier hallazgo de IVA a 7 días o menos del plazo del BTW; una compra vencida hace más de 30 días que necesita acción; una venta vencida hace más de 60 días. |
| **Atención** | Cualquier retención abierta, cualquier excepción abierta, un campo dudoso sin verificar (Q2) o un cambio manual sin resolver (M1). Incluye los hallazgos pegajosos cuya condición desapareció y que nadie ha cerrado. |

**Capa 2: puntos.** Los puntos por plazo, vencimiento e importe solo cuentan
si la factura necesita acción (tiene una excepción abierta o no está revisada).

| Entrada | Puntos |
| --- | --- |
| Plazo de pago (compra) | vence en 0–3 días: 20; en 4–7 días: 10 |
| Días vencida, compra | 1–14: 15; 15–30: 25; más de 30: 35 |
| Días vencida, venta | 1–14: 10; 15–30: 20; 31–60: 30 |
| Importe | 2.500 o más: 5; 10.000 o más: 10; 25.000 o más: 20 |
| Discrepancia con el planning | 15; más 10 si vale 500 € o más; más otros 10 si vale 2.500 € o más |
| Facturación que falta (V5, V8) | 20 |
| Trabajo sin facturar (V6) | menos de 1.000 €: 15; si no, 25; más 5 por semana completa pasada la gracia, como mucho 20 extra |
| Límite blando de PO | 10 |
| Caducidad de PO (P7) | en 30 días: 10; en 7 días: 20 |
| Hallazgo blando de IVA | 20; más 15 si el plazo del BTW está a 14 días o menos |
| Otra anomalía | 10 por regla distinta, como mucho 20 |
| Esperando a un tercero, seguimiento en el futuro | puntos de plazo y vencimiento a la mitad |
| Esperando a un tercero, seguimiento ya pasado | 10 |

De 0 a 19 puntos es Normal, de 20 a 39 es Atención y 40 o más es Urgente. Los
puntos nunca llevan a Bloqueada: detrás de una Bloqueada siempre hay una regla
con nombre.

**Nivel final.** El mayor entre el suelo, el nivel por puntos y cualquier
subida manual activa. Una persona puede **subir** una prioridad con un motivo
(queda auditado y puede caducar). **Nadie puede bajarla.**

**El motivo se explica.** Primero el del suelo y luego cada aportación, por
ejemplo: «Bloqueada: IBAN NL..4300 no verificado para Van Dijk BV (F3) · vence
en 2 días +20 · importe 12.400,00 ≥ 10.000 +10».

**Agregación y orden.** Una excepción toma el máximo entre los suelos de sus
hallazgos y el nivel de su factura. Un proveedor, cliente, objeto, PO o
trimestre toma el máximo de sus hijos. El orden es: nivel, puntos, fecha de
vencimiento (las vacías al final), importe absoluto e identificador.

---

## 6. De dónde entra cada dato

Todas las importaciones pasan por un único escritor que garantiza lo mismo
para cualquier fuente:

- **Repetir es seguro:** importar dos veces el mismo fichero no hace nada. El
  fichero original se guarda en el almacén de documentos.
- **Todo o nada donde importa:** extractos del banco, planning, cuentas
  bancarias, facturas y pagos se cargan enteros o no se cargan, porque medio
  fichero crearía falsos «sin pagar» o «sin facturar». El resto del maestro se
  carga fila a fila y las filas rechazadas generan Z2.
- **Lo que una importación nunca puede hacer:** sobrescribir un valor manual
  (si discrepa, salta M1), editar un campo que pertenece a Exact o TRNSPRNT,
  escribir un estado «verificado» o meter un IBAN por otro camino que el
  registro de cuentas con su evento.
- **Nada se crea solo:** una parte, objeto o recurso desconocido genera un
  hallazgo. La identificación es exacta: btw-id, luego KvK, luego alias
  confirmado. Nunca por IBAN y nunca aproximada.
- **Prueba en seco:** `--simular` enseña lo que sería nuevo, cambiado o
  rechazado sin escribir nada.
- **Frescura:** la fecha de exportación de cada fichero dice lo fresca que es
  la fuente. Límites por defecto pensados para exportaciones manuales: banco 3
  días laborables, Exact 7 días, TRNSPRNT 7 días. Pasado el límite sale un
  aviso en pantalla (Z1) y las reglas dependientes dan «sin datos».

| Fuente | Cuándo | Qué aporta |
| --- | --- | --- |
| Extracciones existentes (`out/*.json`, v1 y v2) | Ya | Localiza cada PDF por su huella, lo copia al almacén y guarda la extracción tal cual. **Cero llamadas a la API.** |
| Datos maestros (exportaciones CSV de Exact, o una hoja rellenada a mano) | Ya | Proveedores y clientes con cuentas bancarias, condiciones de pago, código de IVA y el teléfono designado para verificar; objetos, recursos y alias; tarifas acordadas; ciclos de facturación. Una carga inicial única desde `config/tarifas.yaml`. |
| Exact | CSV ya; API REST más adelante | Facturas de venta y sus líneas (centro de coste o proyecto como objeto), partidas abiertas y pagos. Precedencia: banco, luego Exact, luego manual. La API REST irá por el único proceso dueño del token ([sistemas.md](sistemas.md)). Nunca se escribe en Exact. |
| Banco | Ya | CAMT.053 (versiones .001.02 y .001.08), con saldos y número de secuencia para K6. MT940 con perfiles por banco (ING, ABN AMRO, Rabobank). CSV del banco marcado «sin saldos», así que K6 no se evalúa. La cuenta del extracto tiene que ser de BMS; una fila que no está en euros da X1. |
| TRNSPRNT | Mapeo ya; en vivo cuando se conozca el formato | Un mapeo CSV construido contra un ejemplo sintético; más adelante un lector de API que produce los mismos registros. Cada importación es una foto fija. Las autofacturas de compra entran estructuradas, sin pasar por el modelo. |
| Órdenes de compra | Ya | CSV o YAML que escribe una persona con el permiso de cambiar PO. Las modificaciones son filas aparte. |

**Mapeos.** Cada formato de CSV tiene su fichero YAML versionado
(separador, codificación, separador decimal, formatos de fecha, qué columna
alimenta qué campo, campos derivados como horas = fin − inicio − pausa, reglas
de signo y una huella de la cabecera para reconocer el formato). Añadir un
formato nuevo es escribir un YAML, un ejemplo anonimizado y el resultado
esperado. Para XLSX, de momento, se exporta a CSV.

---

## 7. Cambios en el extractor y lo que cuestan

**Lo que no cambia, a propósito.** El modelo sigue sin herramientas ni red, la
salida sigue forzada al esquema, los importes se copian literalmente, el texto
inyectado sigue yendo a `document_notes`, y nada de la base de datos entra en
el prompt (ni maestro, ni lista de IBAN, ni lista de PO).

**Esquema v2.** Todos los campos nuevos son obligatorios pero admiten vacío,
como ahora.

| Dónde | Campos nuevos |
| --- | --- |
| Cabecera | Tipo de documento tal como se declara (factura, abono, factura corregida, sustitutiva, anulación o desconocido); facturas relacionadas con la frase literal; moneda tal como aparece; persona de contacto del emisor; nombre, btw-id y «t.a.v.» del destinatario; todas las referencias impresas con su etiqueta; condiciones de pago literales; desglose de IVA por tipo. |
| Líneas | Nombre del trabajador, fecha de trabajo, referencia de pedido, tipo de turno o recargo literal (dag, avond, nacht, weekend, feestdag, toeslag), tipo de IVA. El campo de ubicación pasa a ser «objeto, ubicación o proyecto tal como está impreso». |
| No se extrae | Teléfonos, correos ni identificadores personales. Un test comprueba que el esquema no tiene ningún campo con pinta de teléfono. |

**El modelo transcribe, el código decide.** El modelo copia todas las
referencias con su etiqueta, y es el código el que decide cuál es una PO
comparándola con la lista de PO. El vencimiento solo se copia si está impreso;
si no, lo calcula el código como valor «calculado». El sentido de la factura
(compra o venta) lo decide la vía por la que entró el documento, nunca el
modelo. El prompt pasa a ser neutral respecto al sentido y la regla 1 se
mantiene palabra por palabra.

**Moneda.** El lector de importes devuelve el importe y su moneda, de modo que
cualquier moneda que no sea el euro da X1 en lugar de sumarse como euros.

**Compatibilidad con lo ya extraído.** Las extracciones v1 se leen adaptadas a
la forma v2 sin reescribirse. Los campos que v1 nunca pidió se marcan
«faltante: no solicitado en v1», nunca «no está en el documento», y las reglas
que los necesitan dan «sin datos».

**Caché y coste.**

- **Por defecto se conserva:** cualquier extracción guardada de los mismos
  bytes se reutiliza, sea de la versión que sea. Así subir de versión el
  esquema no vuelve a pagar en silencio toda la carpeta ni destruye la
  evidencia v1. `--estricta` mantiene el comportamiento actual para las
  mediciones.
- **Nada se sobrescribe:** las extracciones se añaden.
- **Reextracción con presupuesto:** una orden aparte (`reextraer`) que elige
  qué documentos (abiertos, desde una fecha, de un proveedor, sin objeto),
  cuenta exactamente los tokens de entrada, estima los de salida y **se niega
  a ejecutar si la estimación alta supera el presupuesto**.
- **Activación con puerta de calidad:** una extracción nueva solo pasa a ser
  la vigente si la v2 puntúa al menos igual que la v1 y al menos un 98 % en
  los campos críticos del conjunto real, y si el PDF con inyección sigue dando
  el IBAN de la cabecera. Al activarla, cada valor manual que la nueva
  extracción contradiga genera M1.
- **El histórico puede quedarse en v1.** Lo cerrado y pagado no necesita
  reextraerse; los campos que falten se pueden rellenar a mano.

**Cuánto cuesta.**

| Concepto | Dato |
| --- | --- |
| Precio claude-opus-5 | 5 $ por millón de tokens de entrada, 25 $ de salida |
| Precio claude-opus-5-5 | 4 $ de entrada, 20 $ de salida (se añade a `pricing.py`, que no lo tenía) |
| Lotes (Batches) | 50 % del precio normal |
| Pasada v2, estimación | unos 6–7 $ por cada 100 documentos en modo síncrono; 3–3,5 $ en lote |

Si se cambia de modelo, se hace en la misma pasada que el cambio de esquema,
para pagar cada documento una sola vez. Con Opus 5.5 el razonamiento no se
puede desactivar y el esfuerzo por defecto es medio, así que se fija de forma
explícita y se vuelve a puntuar. La elección se decide midiendo, como ya hace
[fase-0.md](fase-0.md). Ver también [costes.md](costes.md).

**Facturas de venta en PDF.** Solo se leen cuando no hay fuente estructurada
(Exact o TRNSPRNT).

---

## 8. Orden de construcción

Cada paso tiene una puerta que debe pasarse antes de empezar el siguiente.
El avance real de cada paso se apunta en [v1/registro.md](v1/registro.md).

| Paso | Qué se construye | Puerta (resumen) |
| --- | --- | --- |
| **0. Base y correcciones** (sin base de datos, sin gasto de API) | Ejemplos v1 (las 3 facturas, un abono, una línea en «uren», una fecha dd-mm-aaaa, la factura con inyección y una en dólares) y una foto de referencia de `construir_datos`. Correcciones: las líneas en «uren» que hoy se pierden, los dólares que hoy se leen como euros, B4 como retención, la etiqueta de E3, G3 agrupado por identidad del proveedor, el IBAN más antiguo que ya no se toma como referencia, el precio de claude-opus-5-5. Endurecer `serve.py` (origen exacto, lista de Host, token en cabecera, POST solo JSON). La caché conserva por defecto y nunca sobrescribe. | Los tests existentes pasan; un POST desde otra web recibe 403; un Host ajeno, 403 o 421; `http://localhost.attacker.example` no recibe cabecera CORS; cambiar solo la versión hace 0 llamadas. |
| **1. Almacén, evidencia y auditoría** | La base de datos, el almacén de documentos, el registro encadenado y la migración de `out/` **con cero llamadas a la API**. `extract` y `serve` escriben en los dos sitios. | Las tablas de solo añadir rechazan cambios; la cadena detecta una fila editada a mano; importar dos veces da lo mismo; el panel sale igual desde la base de datos que desde `out/`. |
| **2. Núcleo tipado y una sola vía de escritura** | Maestro (sin cuentas bancarias), facturas, líneas, imputaciones, IVA, referencias, relaciones y procedencia; permisos e identidad; carga inicial de objetos, clientes y tarifas desde `config/tarifas.yaml`. Panel, informe y exportación leen de la base de datos. | El original sobrevive a dos correcciones; el sistema decide entre «completado» y «corregido»; lo automático nunca pisa lo manual; una corrección sin motivo se rechaza. |
| **3. Motor de reglas y hallazgos** | Se portan las reglas actuales (Q1, D1–D4, D2b, E3/E4, F1, B2–B4 y G3 por historial) y el recálculo diario. | Reglas puras comprobadas por test; resultados idénticos con datos desordenados; lo pegajoso no se cierra solo; 5.000 facturas se recalculan en menos de 2 segundos. |
| **4. Excepciones, revisión, prioridad, órdenes y consola** | Las órdenes de edición, la CLI, `POST /api/v2/acciones` y una consola mínima. Empiezan los tests de alcance. | Cada orden es una transacción; cualquier cambio invalida la revisión; tests de prioridad para cada suelo y cada umbral; matriz de permisos; el texto de los documentos se muestra como texto. |
| **5. Maestro y registro de IBAN** | Cuentas bancarias, beneficiarios conocidos, tarifas acordadas, ciclos; importadores del maestro; referencia, atestación y verificación; reglas A, F, E1, E2, U1, Q2–Q4, X1, Z1, Z2. | Ninguna extracción crea ni cambia una cuenta bancaria; la factura con inyección queda bloqueada (F2/F3) y da Q3; un cambio de IBAN en Exact bloquea (F5); una verificación con teléfono cambiado hace 3 días no vale (F8). |
| **6. Extracción v2** (el único paso que gasta en la API, y solo cuando se lanza a propósito) | Esquema y prompt v2, adaptación de v1, puntuación, estimación de coste, `reextraer` y lotes. | Comprobaciones automáticas del esquema; antes de activar, a mano: dentro de presupuesto, v2 al menos igual que v1 y ≥ 98 % en campos críticos, y el PDF con inyección sigue bien. |
| **7. Banco, pagos y caja** | Lectores CAMT.053, MT940 y CSV del banco; aplicación de pagos; partidas abiertas de Exact; visión de caja; reglas K1–K8 y F7. | Un salto de continuidad bloquea (K6); un cargo doble da K4; un pago parcial deja la factura pendiente con su saldo y K2; la caja se prueba con fecha fija entre domingo y lunes y a fin de mes. |
| **8. Facturas de venta, relaciones y visiones de proveedor y cliente** | Mapeo de ventas de Exact y vía de PDF de venta; propuestas y confirmación de relaciones; reglas R1–R5, V7, F10 y la aritmética como retención en ventas. | La vía decide el sentido; un abono total marca la original como abonada; las sustituidas quedan fuera de totales, caja e IVA. |
| **9. Órdenes de compra y tarifas acordadas** | Importación y órdenes de PO, consumo y previsión, reglas P1–P10; G3 y V4 contra tarifas acordadas. | Consumo sin IVA, con abonos restados y sin anuladas ni sustituidas; caducidad con fecha fija; previsión determinista. |
| **10. Planning** (mapeo contra un ejemplo sintético, se activa con la primera exportación real) | Turnos y conciliación; reglas G1–G7, V1–V6, V8, V9 y la parte de planning de B5, P8 y P10; horas en la visión por objeto. | Nivel de comparación correcto; frontera del año ISO; 0,25 h pasa y 0,26 h falla; un nuevo lote que cambia una semana facturada da V9. |
| **11. BTW** | Periodos, `config/btw.yaml` confirmado con el contador, autoliquidación de la inversión del sujeto pasivo, reglas C4, E0, E7. | Rúbricas 2a y 5b que se compensan; plazo del Q4 el 31 de enero; presentar es irreversible y queda con huella. |
| **12. Panel principal, búsqueda, contrato v2 y documentación** | Bloques del panel y filtros de búsqueda, `/api/v2`, `export --v2`, consola con procedencia y marcas de edición. | Los totales cuadran entre vistas; un test por filtro; `/api/datos` sigue idéntico byte a byte. |
| **13. Entorno local con Docker y datos de prueba** (a petición del dueño) | Imagen y `docker-compose.yml` (consola y base sin red, el lector saliendo solo a la API por el proxy `bms-agent salida`), scripts de Windows, `demo crear` con una base de prueba aparte, copias comprobadas. | El proxy solo deja ir a `api.anthropic.com:443`; la configuración aísla cada contenedor; cada bloque del panel tiene algo con los datos de prueba, la consola lleva la banda y nada de la prueba entra en la base de verdad. |

**Estado de la construcción (octubre de 2026).** Los doce pasos están
construidos y la puerta de cada uno pasa; el detalle, con cada desviación, está
en [v1/registro.md](v1/registro.md). El paso 12 cerró la V1 con el panel
principal de siete bloques, la búsqueda con todos los filtros del §18, la
vista económica de cada Objeto, la historia de cada factura, el contrato v2
(`/api/v2` y `export --v2`, en [integracion-web.md](integracion-web.md)) y la
guía de uso diario ([uso-v1.md](uso-v1.md)). Lo que queda no es código:
confirmar `config/btw.yaml` con el asesor, mapear el planning con la primera
exportación real de TRNSPRNT, medir la extracción v2 con facturas reales antes
de activarla, y las respuestas del apartado 9. El paso 13, a petición del
dueño, la deja corriendo en su ordenador en un entorno aislado con Docker y con
una base de datos de prueba ([entorno-local.md](entorno-local.md)).

**Tests de alcance, desde el paso 4.** Comprueban que nada crea ni prepara
facturas, paga, aprueba pagos o presenta el BTW; que no hay generador SEPA ni
credenciales del banco; que no hay planes de plazos; que lo que no está en
euros siempre se bloquea; que ninguna extracción llega al registro de cuentas;
y que las peticiones al modelo no llevan herramientas.

---

## 9. Preguntas abiertas para el responsable del producto

Cada respuesta cambia el diseño. Hasta tenerlas, se aplican los valores por
defecto descritos arriba.

- [ ] **Referencia de IBAN y doble firma.** ¿La primera importación de Exact
      cuenta como referencia (marcada sin verificar), o nada debe quedar «sin
      objeciones» hasta que se ateste o se llame? ¿Hay una segunda persona
      para la doble firma, y a partir de qué importe?
- [ ] **Datos de pago.** ¿Qué banco o bancos, qué formato (se prefiere
      CAMT.053) y cada cuánto se exporta? ¿Se usa también el estado de pago de
      Exact, y qué fuente manda? ¿Hay tolerancia para los gastos bancarios?
- [ ] **TRNSPRNT.** ¿Tiene API o solo exportaciones? ¿Cada turno lleva un
      identificador estable, horas aprobadas y el proveedor? ¿Qué tarifas
      guarda? ¿Qué parte de las facturas de compra autofactura? Si es alta,
      hay que replantear el gasto del paso 6.
- [ ] **Facturas de venta.** ¿Salen de Exact o de TRNSPRNT? ¿Sus líneas llevan
      objeto, recurso y periodo de trabajo? ¿Cuántas administraciones
      (divisiones) de Exact hay?
- [ ] **Órdenes de compra.** ¿Quién las emite y a quién? ¿Los valores son sin
      IVA? ¿Qué clientes u objetos las exigen, y quién mantiene la lista?
- [ ] **Tarifas y ciclos de facturación.** ¿De dónde salen las tarifas
      acordadas, y los recargos son tarifas propias o porcentajes? ¿Cuál es el
      ciclo de facturación y el periodo de gracia por cliente u objeto?
- [ ] **Umbrales y pesos.** U1, el porcentaje de aviso y la ventana de
      caducidad de las PO, los tramos de prioridad, el exceso de tarifa en G3
      que bloquea en lugar de retener, los límites de frescura y el periodo de
      espera tras un cambio de teléfono.
- [ ] **IVA, para el contador.** ¿Se aplica la inversión del sujeto pasivo al
      trabajo de BMS? ¿Cuál es la correspondencia con las rúbricas?
      ¿Factuurstelsel o kasstelsel, declaración trimestral, y qué se hace con
      las facturas que llegan después de presentar un trimestre?
- [ ] **Usuarios y roles.** ¿Quién tiene cada permiso? ¿Vale para la V1
      identificar a cada persona con un token local hasta que llegue Entra ID
      con el despliegue? ¿Se añaden a la lista los permisos de revisar
      factura, gestionar BTW e importar datos?
- [ ] **Atribución y motivos.** ¿Los márgenes por objeto y las cifras del año
      se atribuyen por periodo de trabajo o por fecha de factura? ¿El motivo es
      obligatorio en toda edición manual o solo en las correcciones?
      Mientras tanto (paso 12): por mes y por año cuenta la fecha de factura;
      por semana, los días trabajados de su periodo, igual que las horas.
