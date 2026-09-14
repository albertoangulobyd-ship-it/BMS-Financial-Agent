# Validación de facturas de zzp'er

Reglas que el núcleo determinista aplica a cada factura de proveedor
autónomo antes de contabilizarla o de incluirla en un lote de pago.

Ver [arquitectura.md](arquitectura.md) para el contexto. Estas reglas viven
en el núcleo determinista: son código con tests, no juicio del modelo. La
única excepción está marcada como tal.

> **Pendiente de confirmación con el contador.** Todo el grupo E (régimen de
> IVA), la regla A5 y el grupo H tocan obligaciones fiscales y laborales.
> El catálogo es un punto de partida técnico, no asesoramiento fiscal.

---

## 1. Tres comprobaciones que no funcionan tal como están escritas

Antes del catálogo, porque si no se corrigen se construyen tres cosas que
generan ruido o falsa confianza.

### Numeración correlativa sin huecos

**No es comprobable, y los huecos son normales.** Un zzp'er factura a varios
clientes con una única serie. Si te llegan la 2026-001, la 2026-007 y la
2026-012, los números que faltan fueron a otros clientes. Marcar eso como
anomalía produce una alerta por factura y acaba ignorándose.

Lo que sí se comprueba es la unicidad **dentro de tus propios registros**:
mismo proveedor y mismo número ya contabilizado es un duplicado exacto. Y
más útil todavía, el duplicado por contenido, que es el que de verdad
cuesta dinero (reglas B2 y B3).

### El umbral de la KOR

**No puedes verificarlo.** La KOR depende de la facturación total del
proveedor en el año natural, con todos sus clientes. Tú solo ves lo que te
factura a ti. Si te factura por debajo del umbral, no sabes nada sobre el
resto.

Lo que sí puedes hacer es vigilar tu propio acumulado con ese proveedor y
avisar cuando se acerque al umbral, porque a partir de ahí es probable que
lo haya superado y tenga que empezar a repercutir IVA (regla E5). Es un
indicio, no una verificación, y así debe presentarse.

### Nombre del titular de la cuenta

**No está en la factura y no se verifica desde el PDF.** La comprobación
real de que el IBAN pertenece a quien dice es la que hace el banco al pagar,
con la verificación de IBAN y nombre. Desde el documento solo puedes
comprobar el IBAN contra tu maestro de proveedores, que es la regla 1 de la
arquitectura y ya bloquea el caso peligroso (reglas F2 y F4).

Ojo además con la tolerancia: un zzp'er puede cobrar legítimamente en una
cuenta a nombre comercial que no coincide literalmente con su nombre
personal. Bloquear por diferencia literal de cadena genera falsos positivos.

---

## 2. Tres resultados posibles

Si todas las reglas bloquean, no se contabiliza nada. La gradación es lo que
hace el sistema usable.

| Resultado | Qué pasa |
| --- | --- |
| **Bloqueo** | No se contabiliza y no entra en ningún lote de pago. Requiere corrección o una factura nueva del proveedor. |
| **Retención** | Queda en borrador o en cuenta de espera y va a la cola de revisión humana. No entra en un lote de pago hasta resolverse. |
| **Aviso** | Se contabiliza y se paga, pero queda en el informe diario y en la lista de excepciones del trimestre. |

Cada evaluación se guarda contra la factura, con la regla, el resultado y
los valores comparados. Es lo que permite responder después por qué una
factura se retuvo.

---

## 3. Catálogo de reglas

Columna **Fuente**: de dónde sale el dato con el que se compara.

- `extracción` · campo leído del PDF
- `maestro` · maestro de proveedores en Exact
- `planning` · programa de planning, solo lectura
- `historial` · tus propias facturas ya contabilizadas
- `registro` · registro externo (KvK, VIES)

### A · Identidad del proveedor

| ID | Comprobación | Fuente | Resultado |
| --- | --- | --- | --- |
| A1 | Nombre completo y dirección presentes | extracción | Retención si falta |
| A2 | Nombre coincide con el maestro, con tolerancia para nombre comercial | maestro | Retención si difiere |
| A3 | Número KvK presente y con formato de ocho dígitos | extracción | Aviso si falta |
| A4 | Número KvK coincide con el registro | registro | Retención si no coincide |
| A5 | btw-id presente y con formato `NL` + nueve dígitos + `B` + dos dígitos | extracción | Bloqueo si falta y no hay mención de KOR |
| A6 | btw-id válido en VIES | registro | Retención si no es válido |

**A3 no debe bloquear.** El número KvK es habitual en las facturas
neerlandesas pero el requisito de la ley del IVA es el btw-id. Confirma con
tu contador antes de endurecerlo.

**A4 y A6 se verifican en el alta del proveedor y de forma periódica, no en
cada factura.** Son llamadas externas, con coste y con latencia, y el dato
cambia poco. Guarda el resultado con su fecha y revalida cada trimestre. El
Handelsregister completo de KvK requiere suscripción de pago.

### B · Numeración y unicidad

| ID | Comprobación | Fuente | Resultado |
| --- | --- | --- | --- |
| B1 | Número de factura presente | extracción | Bloqueo si falta |
| B2 | Duplicado exacto: mismo proveedor y mismo número ya contabilizado | historial | Bloqueo |
| B3 | Duplicado probable: mismo proveedor, mismo importe, fecha a menos de catorce días, número distinto | historial | Retención |
| B4 | Periodo ya facturado: el mismo rango de servicio ya cubierto por otra factura del proveedor | historial | Retención |

**B3 y B4 son las que más dinero ahorran.** El duplicado exacto lo pilla
cualquiera. El caso real es la misma semana facturada dos veces con números
distintos, o la factura reenviada un mes después porque el proveedor creyó
que se había perdido.

### C · Fechas

| ID | Comprobación | Fuente | Resultado |
| --- | --- | --- | --- |
| C1 | Fecha de factura presente y no futura | extracción | Retención |
| C2 | Periodo de prestación presente | extracción | Bloqueo si falta |
| C3 | Fecha de factura anterior al fin del periodo facturado | extracción | Aviso |
| C4 | Periodo dentro de un trimestre ya declarado | historial | Aviso, y a la lista de excepciones del IVA |

**C4 alimenta la hoja de trabajo del trimestre.** Una factura que llega
tarde y cae en un periodo ya declarado no es un error, pero el contador
tiene que verla.

### D · Importes y aritmética

| ID | Comprobación | Fuente | Resultado |
| --- | --- | --- | --- |
| D1 | Desglose presente: unidades, tarifa, subtotal, tipo de IVA, importe de IVA y total | extracción | Bloqueo si falta |
| D2 | unidades × tarifa = subtotal, dentro de la tolerancia de redondeo | extracción | Bloqueo |
| D3 | subtotal × tipo = importe de IVA | extracción | Bloqueo |
| D4 | subtotal + IVA = total | extracción | Bloqueo |
| D5 | Descripción suficientemente específica, no "servicios" ni "trabajos" | extracción | Aviso |

**D2, D3 y D4 son aritmética y deben bloquear.** Son baratas y atrapan más
errores de los que parece, sobre todo en facturas hechas a mano.

**D5 es la única regla del catálogo que usa el modelo.** Es un
clasificador sobre el texto de la descripción, no una expresión regular. Y
por eso mismo nunca bloquea: avisa.

### E · Régimen de IVA

| ID | Comprobación | Fuente | Resultado |
| --- | --- | --- | --- |
| E1 | El tipo aplicado coincide con el régimen registrado del proveedor | maestro | Retención si difiere |
| E2 | El régimen cambia respecto a la factura anterior del mismo proveedor | historial | Retención |
| E3 | Con KOR: la factura no repercute IVA y lo menciona expresamente | extracción, maestro | Bloqueo si repercute IVA |
| E4 | Con verleggingsregeling: sin IVA, con la mención de IVA trasladado y vuestro btw-id | extracción | Bloqueo si repercute IVA |
| E5 | Acumulado anual que le habéis pagado, contra el umbral de la KOR | historial | Aviso al acercarse |

**E2 es la regla más valiosa del grupo.** Un proveedor que pasa de KOR a
repercutir IVA, o de IVA normal a IVA trasladado, es casi siempre un cambio
legítimo que hay que registrar en el maestro. Detectarlo en la factura y no
tres meses después en la declaración es la diferencia entre un ajuste y una
corrección.

**E4 depende de vuestro sector.** Si BMS presta o cede personal para obra
de construcción, la regla de traslado de la deuda tributaria aplica y la
factura no debe llevar IVA. Confírmalo con el contador antes de codificar el
comportamiento por defecto, porque equivocarse aquí afecta a todas las
facturas de un proveedor a la vez.

### F · Datos de pago

| ID | Comprobación | Fuente | Resultado |
| --- | --- | --- | --- |
| F1 | IBAN presente y válido con el dígito de control módulo 97 | extracción | Bloqueo |
| F2 | El IBAN de la factura coincide con el del maestro | maestro | Bloqueo |
| F3 | IBAN nuevo o modificado respecto al registrado | maestro | Bloqueo y verificación telefónica al número ya conocido |
| F4 | IBAN de un tercero, factoring o cesión de crédito | extracción, maestro | Bloqueo y escalado |

**El pago se construye siempre con el IBAN del maestro, nunca con el del
documento.** F1 y F2 no eligen el número, solo detectan la discrepancia. Es
la regla 1 de la arquitectura y no admite excepción operativa.

### G · Contraste con el planning

Este es el núcleo del sistema y la razón por la que existe el proyecto.

| ID | Comprobación | Fuente | Resultado |
| --- | --- | --- | --- |
| G1 | El proveedor tiene una asignación activa en el periodo facturado | planning | Bloqueo si no la tiene |
| G2 | Horas facturadas por ubicación y asignación = horas registradas, dentro de tolerancia | planning | Retención si se sale |
| G3 | La tarifa coincide con la de esa asignación concreta | planning | Retención, y bloqueo por encima del exceso configurado |
| G4 | La ubicación facturada existe y coincide con la del registro | planning | Retención |
| G5 | La semana facturada coincide con la semana ISO del planning | planning | Retención |
| G6 | Los recargos de horas extra, nocturnidad o festivo tienen su propia tarifa y su propia regla | planning | Retención |

**G3 no asume tarifa plana.** La tarifa se busca por asignación, no por
proveedor. Un mismo autónomo puede tener tarifas distintas en dos obras a la
vez, y una tarifa media o heredada del contrato marco es exactamente el
error que esta regla existe para evitar.

**G2 necesita una política de tolerancia explícita**, versionada como
configuración y no escrita en el código. Qué se hace con las pausas, con el
tiempo de desplazamiento y con el redondeo al cuarto de hora tiene que estar
decidido antes de escribir la comparación, o la regla saltará constantemente.

### H · Riesgo laboral y de cadena

No estaba en la lista original y conviene que esté, porque en los Países
Bajos es donde más ha cambiado la exposición de una empresa que trabaja con
autónomos.

| ID | Comprobación | Fuente | Resultado |
| --- | --- | --- | --- |
| H1 | Patrón de dependencia: muchas horas semanales y continuidad prolongada con un solo cliente | planning, historial | Aviso |
| H2 | Modelovereenkomst vigente en el expediente del proveedor | maestro | Aviso si falta o está caducado |
| H3 | Con traslado de la deuda en construcción: responsabilidad en cadena y, en su caso, cuenta bloqueada | maestro | Aviso |

**H1 es un indicio, no un veredicto.** La fiscalidad neerlandesa reanudó la
fiscalización del falso autónomo, y el patrón que la levanta es exactamente
el que tu planning ya registra: un autónomo con jornada completa, de forma
continuada, para un solo cliente y a tarifa fija. El sistema puede verlo
antes que una inspección. Qué se hace con el aviso es una decisión de
negocio y de vuestro asesor, no del agente.

---

## 4. Tolerancias

Toda comparación numérica necesita una tolerancia explícita. Van como
configuración versionada, con fecha de vigencia, no como constantes en el
código.

| Parámetro | Punto de partida sugerido |
| --- | --- |
| Redondeo en la aritmética de importes | Un céntimo por línea, dos por factura |
| Diferencia de horas antes de retener (G2) | Un cuarto de hora por jornada |
| Diferencia de tarifa antes de retener (G3) | Cualquier diferencia |
| Exceso de tarifa que bloquea en vez de retener (G3) | Por decidir con vosotros |
| Ventana del duplicado por contenido (B3) | Catorce días |
| Margen de aviso del umbral KOR (E5) | El último diez por ciento |

Empieza con tolerancias generosas y ve apretándolas con los datos de la
fase 0. Una regla que salta demasiado se desactiva de hecho aunque siga
activa en el código.

---

## 5. Lo que hay que confirmar con el contador

| Punto | Por qué |
| --- | --- |
| Si el número KvK se exige en factura o basta el btw-id | Decide si A3 avisa o bloquea |
| Si aplica la regla de traslado de la deuda a vuestra actividad | E4 afecta a todas las facturas de un proveedor a la vez |
| Mapeo de rúbricas de la declaración trimestral | Ya recogido en la arquitectura, se cruza con C4 |
| Tratamiento de las facturas que llegan tras el cierre del trimestre | Define qué hace C4 además de avisar |
| Umbral de exceso de tarifa que justifica bloquear un pago | Única cifra del catálogo que es decisión de negocio pura |
