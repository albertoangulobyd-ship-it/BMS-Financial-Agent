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

**Qué evalúa ya el motor de reglas.** Desde el paso 3 de la V1, el código
evalúa sobre el almacén Q1 (campos obligatorios), X1, B2, B3, B4, D1, D2,
D2b, D3, D4, E3, E4, F1 y G3 contra el histórico (sin tarifa pactada ni
planning). Desde el paso 5, con los maestros importados y el registro de
cuentas: Q2, Q3, Q4, Z1, Z2, A0, A2, A5, A7, A8, E1, E2, U1, F0, F2, F3,
F4, F5, F6, F8 y F9 (y X1 también sobre las importaciones). Desde el paso
6, M2: la edición manual de una línea que una extracción nueva no trae (ver
la sección M). Desde el paso 7, con el banco y los pagos: K1-K8 y F7. Desde
el paso 8, con las ventas y las relaciones entre facturas: V7, F10, M3 y
R1-R5 (sección R), y D1, D2 y D2b retienen en una venta en vez de bloquear.
Desde el paso 9, con las órdenes de compra y las tarifas pactadas: P1-P10
(sección P; P8, P10 y la PO ya caducada de P7 dan sin datos hasta el
planning), G3 contra la tarifa pactada con el histórico donde no hay
ninguna, G6 y V4 (sección G). Desde el paso 10, con el planning de TRNSPRNT:
G1, G2, G4, G5 y G7, la parte del planning de G6, el escalón del planning de
G3 y V4, V1-V3, V5, V6, V8 y V9 (sección V), B5 (horas cobradas dos veces) y
el caso de las horas en V7, y P7, P8 y P10 con el trabajo del planning. Sin
ningún planning importado, cada una da un solo «sin datos», nunca «ok». Desde
el paso 11, con el BTW: C4 contra los trimestres presentados, E0, E5 y E7
(sección E, y `config/btw.yaml` para la lista de tipos y el umbral). Desde el
paso 12, la tabla del [apartado 6](#6-el-catálogo-del-motor-regla-a-regla)
sale entera del catálogo del código y un test comprueba que es la misma: si
este texto y esa tabla no dicen lo mismo, manda la tabla. Su metadato
(qué hace un fallo, si se puede anular, si el hallazgo es pegajoso) está en
`src/bms_agent/reglas/catalogo.py`, que sigue la tabla del §7 de la
[especificación](v1/spec.md); las tolerancias, en `reglas.base.Politica`,
con los valores del apartado 4 (y los de `config/reglas.yaml`). Las demás
reglas entran en el motor con el paso que trae sus datos.

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
| B5 | Un turno del planning conciliado con más horas de compra de las que tiene, desde dos o más facturas que no se explican entre sí | planning, conciliación | Retención; pegajosa |
| V7 | En las ventas, el caso de B2, el de B3 o el de B5: se ha facturado dos veces a un cliente | historial, conciliación | Retención |

B2 y B3 miran las compras, donde un duplicado se pagaría dos veces; en una
venta lo mismo es V7. Un abono, una corrección o una sustitución confirmada
entre dos facturas explica que se parezcan y calla B2, B3, B4 y V7; una
relación «relacionada» no.

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
| C4 | Fecha de factura en un trimestre ya presentado sin estar en lo declarado, o que cambió después de presentarlo | historial | Aviso, y a la lista de excepciones del IVA |

**C4 alimenta la hoja de trabajo del trimestre.** Una factura que llega
tarde y cae en un periodo ya declarado no es un error, pero el contador
tiene que verla.

Desde el paso 11 de la V1, C4 compara cada trimestre presentado con lo que
se declaró de cada factura al anotar la presentación (su huella de IVA:
tratamiento, tipo, base y cuota de cada línea). Avisa de tres cosas: la
factura llegó después («tarde»), cambió después («cambio») o ya no cuenta en
ese trimestre porque se anuló, se sustituyó o cambió de fecha («fuera»). La
factura cuenta en el trimestre de su fecha de factura (factuurstelsel), no en
el de su periodo de prestación: una factura de octubre por trabajo de
septiembre se declara en el cuarto trimestre, y mirar el periodo marcaría
casi todas las de las primeras semanas tras cada presentación. Un abono va
en su propio trimestre: no reabre el que acredita.

### D · Importes y aritmética

| ID | Comprobación | Fuente | Resultado |
| --- | --- | --- | --- |
| D1 | Desglose presente: unidades, tarifa, subtotal, tipo de IVA, importe de IVA y total | extracción | Bloqueo si falta |
| D2 | La suma de las líneas = subtotal, dentro de la tolerancia de redondeo (0,01 por línea más 0,02) | extracción | Bloqueo |
| D2b | En cada línea, unidades × tarifa = importe de la línea (0,01) | extracción | Bloqueo |
| D3 | subtotal × tipo = importe de IVA | extracción | Bloqueo |
| D4 | subtotal + IVA = total | extracción | Bloqueo |
| D5 | Descripción suficientemente específica, no "servicios" ni "trabajos" | extracción | Aviso |

En una factura de venta, D1, D2 y D2b retienen en vez de bloquear: la
factura ya salió de BM Support BV y no se paga desde aquí, pero hay que
mirarla. D3 y D4 bloquean en las dos.

**D2, D2b, D3 y D4 son aritmética y deben bloquear.** Son baratas y atrapan
más errores de los que parece, sobre todo en facturas hechas a mano. Los
identificadores son los del código: el catálogo llamaba antes D2 a la
comprobación de unidades por tarifa, que en el código es D2b.

**D5 es la única regla del catálogo que usa el modelo.** Es un
clasificador sobre el texto de la descripción, no una expresión regular. Y
por eso mismo nunca bloquea: avisa.

### X · Moneda

| ID | Comprobación | Fuente | Resultado |
| --- | --- | --- | --- |
| X1 | Los importes están en euros: ninguno lleva otra moneda (`$`, `£`, `USD`…) | extracción | Bloqueo; la factura queda fuera de todos los totales |

**X1 existe porque antes el símbolo del dólar se quitaba igual que el del
euro**, y una factura en dólares sumaba como si estuviera en euros. Desde el
esquema v2 la extracción trae la moneda impresa (`currency_raw`) y manda
ella; con una extracción v1, que no la pedía, se mira el literal de cada
importe, pero la decisión es de la factura entera: un modelo copia el `$` en
unos campos y lo pierde en otros, y el importe que lo perdió no son euros. Si
ningún importe se puede leer y ninguno lleva marcador, X1 queda sin datos en
vez de dar por buenos unos euros que nadie ha visto.

### M · Lo que una persona cambió

| ID | Comprobación | Fuente | Resultado |
| --- | --- | --- | --- |
| M1 | Un valor manual distinto del último valor automático, sin verificar | procedencia | Atención (campo sin resolver); no es una regla del catálogo, sale de la procedencia de cada campo |
| M2 | Una línea que una persona editó o excluyó no aparece en la extracción vigente: no se pudo casar por su huella con ninguna línea nueva | procedencia, extracción | Retención; se anula con motivo o se cierra excluyendo la línea |
| M3 | Una venta de Exact y su PDF no dicen lo mismo (fecha, base, IVA, total, tipo o periodo), o tienen el mismo número y no se pudieron unir (otro cliente o sin resolver, el PDF ya lleva un pago o una relación confirmada, o no lo emite BM Support BV), y dice por qué | Exact, extracción | Retención, calidad «discrepancia»; cuenta la de Exact y una persona mira la diferencia |

**M2 existe porque una lectura nueva no puede llevarse por delante lo que
escribió una persona.** Al activar una reextracción (paso 6), las ediciones
de cada línea van a la línea nueva que dice lo mismo (descripción,
cantidad, unidad, tarifa e importe), no a la que está en la misma posición.
Si no hay ninguna, la línea se conserva tal cual con su edición, y M2 lo
dice para que una persona decida.

### E · Régimen de IVA

| ID | Comprobación | Fuente | Resultado |
| --- | --- | --- | --- |
| E0 | Falta la información del IVA: el tratamiento no se sabe o, con IVA normal, falta el tipo o la cuota | extracción | Retención, no se anula |
| E1 | El tipo aplicado coincide con el régimen registrado del proveedor | maestro | Retención si difiere |
| E2 | El régimen cambia respecto a la factura anterior del mismo proveedor | historial | Retención |
| E3 | Con KOR: la factura no repercute IVA y lo menciona expresamente | extracción, maestro | Bloqueo si repercute IVA |
| E4 | Con verleggingsregeling: sin IVA, con la mención de IVA trasladado y vuestro btw-id | extracción | Bloqueo si repercute IVA |
| E5 | Acumulado anual que os ha facturado, contra el umbral de la KOR | historial | Aviso al acercarse |
| E7 | Tipo poco habitual (no es 0, 9 ni 21 %), o una venta al 0 % o con IVA trasladado a un cliente que el maestro no tiene marcado para ello | extracción, maestro | Retención |

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

**E5 cuenta lo facturado, no lo pagado.** El umbral de la KOR es sobre la
facturación del proveedor en el año natural, y lo que os factura es la parte
que veis de ella aunque no la hayáis pagado todavía. Suma la base de sus
facturas del año (los abonos restan), si sigue facturando con KOR, y avisa
desde el porcentaje de `config/btw.yaml`. El hallazgo es del proveedor, no
de cada factura.

**E7 mira dos cosas distintas.** Un tipo que no está en la lista de
`config/btw.yaml` (0, 9 y 21 %), en cualquier factura; y una venta sin IVA
(al 0 % o con IVA trasladado) a un cliente que el maestro de Exact no tiene
marcado como «verleggen toegestaan». Sin el cliente resuelto, la segunda da
«sin datos».

### F · Datos de pago

| ID | Comprobación | Fuente | Resultado |
| --- | --- | --- | --- |
| F1 | IBAN presente y válido con el dígito de control módulo 97 | extracción | Bloqueo |
| F2 | El IBAN de la factura coincide con el del maestro | maestro | Bloqueo |
| F3 | IBAN nuevo o modificado respecto al registrado | maestro | Bloqueo y verificación telefónica al número ya conocido |
| F4 | IBAN de un tercero, factoring o cesión de crédito | extracción, maestro | Bloqueo y escalado |
| F10 | Una factura de venta lleva un IBAN que no es una cuenta de BM Support BV | extracción, `config/empresa.yaml` | Retención; no se anula |

**El pago se construye siempre con el IBAN del maestro, nunca con el del
documento.** F1 y F2 no eligen el número, solo detectan la discrepancia. Es
la regla 1 de la arquitectura y no admite excepción operativa.

### R · Relaciones entre facturas

Un abono, una corrección o una sustitución se relaciona con su original. La
relación la propone la extracción (las facturas que nombra el documento) o
Exact (la factura relacionada de un abono de venta), y la confirma o la
rechaza una persona con `anular_acreditar`; también la puede enlazar a mano.
**Lo propuesto no mueve nada.** Lo confirmado sí: un abono que cubre la
original la deja acreditada, uno parcial le baja lo pendiente, y una factura
sustituida o corregida sale de los totales, de la caja y del IVA.

| ID | Comprobación | Fuente | Resultado |
| --- | --- | --- | --- |
| R1 | Un abono o una corrección nombra una factura de la misma contraparte que no está (o que está repetida) | extracción, historial | Retención |
| R2 | Los abonos confirmados le quitan a una factura más de lo que vale, o un abono se aplica por más de lo que vale | relaciones | Retención; pegajosa, no se anula |
| R3 | La original y la que la sustituye (o corrige) están las dos pendientes, las dos pagadas, o la original pagada y la nueva pendiente (lo pagado no se descuenta de la nueva) | relaciones, pagos | Bloqueo; pegajosa, no se anula. Se resuelve anulando o abonando la original (o pagando solo la diferencia) |
| R4 | Un abono sin ninguna relación confirmada que diga a qué factura abona | relaciones | Aviso |
| R5 | Una relación propuesta espera a una persona | relaciones | Aviso |

### G · Contraste con el planning

Este es el núcleo del sistema y la razón por la que existe el proyecto.

| ID | Comprobación | Fuente | Resultado |
| --- | --- | --- | --- |
| G1 | El proveedor (o una persona de la factura) tiene turnos en el planning del periodo facturado | planning | Retención; bloqueo con el planning declarado obligatorio (`planning.obligatorio`). Se anula con segunda firma |
| G2 | Horas facturadas = horas validadas del planning, en la celda más fina que llevan los dos lados (persona y día, Objeto y día, persona u Objeto y semana, periodo), con 0,25 h por día con turnos de tolerancia (0,25 pasa, 0,26 no) | planning | Retención. Un turno sin validar en la celda, una fila semanal que no cabe entera o días que el planning no cubre: sin datos |
| G3 | La tarifa de una línea de compra coincide con la pactada (de lo más concreto a lo general: recurso y Objeto, Objeto, recurso, proveedor, general; el turno es condición de todos). Sin pactada ni planning, contra el histórico | tarifas pactadas, planning, historial | Retención por encima de la pactada, y bloqueo (se anula con segunda firma) por encima del exceso configurado (10 %). Dos pactadas igual de concretas con precios distintos: sin datos en la línea y la factura retenida (`ambigua`). Pactadas para la línea pero ninguna de su unidad o su día: sin datos y la factura retenida (`no_casa`), nunca el histórico |
| G4 | El Objeto de la línea es donde el planning tiene a la persona (o al proveedor) esos días. Una línea sin Objeto recibe la propuesta del planning, que confirma una persona con `cambiar_objeto` | planning | Retención |
| G5 | La semana impresa es la de las fechas de la línea (el año lo da la fecha de la factura: la semana 52 de una factura del 6 de enero es la del año anterior), y lo facturado en días sin turnos no es trabajo de otras fechas sin facturar (cuatro semanas antes o después) | planning | Retención |
| G6 | Una línea de un recargo (horas extra, noche, festivo) se cobra a su propia tarifa pactada, y solo por las horas que el planning tiene de ese recargo en su celda | tarifas pactadas, planning | Retención por encima. Sin tarifa propia pero con otras pactadas para la línea: sin datos y la factura retenida (`no_casa`), para que una persona confirme el recargo. Sin ninguna pactada, no aplica y la mira G3 |
| G7 | El planning de lo facturado (la celda tal como se concilió) no ha cambiado en una foto más nueva | planning, conciliación | Aviso |
| V4 | La tarifa de una línea de venta es la de venta pactada o, sin pactada, la del turno en el planning, ni por encima ni por debajo | tarifas pactadas, planning | Retención. Sin ninguna de las dos, sin datos |

**La celda.** Una línea se compara con el planning al nivel más fino que
llevan los dos lados: la persona si la línea la nombra y el planning tiene sus
turnos, si no el Objeto; un día si la línea es de un día, una semana si es de
una semana entera (o si el planning de esa semana solo tiene la fila semanal
de la exportación pivotada) y el periodo en lo demás. En una compra cuentan
los turnos de su proveedor; en una venta, los facturables de su cliente. Un
turno cancelado no cuenta nunca. Lo facturado queda conciliado con los turnos
de su celda tal como eran (la traza de la ficha de la factura); si una foto
más nueva los cambia, es G7 o V9.

### V · Facturas de venta contra el planning

| ID | Comprobación | Fuente | Resultado |
| --- | --- | --- | --- |
| V1 | Horas facturadas = horas validadas facturables del planning, en la misma celda que G2 | planning | Retención |
| V2 | El Objeto de cada línea existe, es del cliente facturado y estaba activo esos días; una línea sin Objeto retiene y recibe la propuesta del planning | maestro, planning | Retención |
| V3 | La semana y el periodo facturados contra el planning (como G5) | planning | Retención |
| V5 | Dentro del Objeto y el periodo que cobra una factura, turnos validados facturables que ninguna línea cubre | planning | Retención; valorado a la tarifa de venta pactada o, si no, estimado |
| V6 | Trabajo validado facturable que ninguna venta cubre, pasado el fin de su periodo de facturación (el de su ciclo, o el mes) más sus días de gracia (los del ciclo, o 14) | planning, ciclos | Retención del cliente; valorado a la tarifa de venta pactada o marcado estimado |
| V8 | Un periodo de un ciclo de facturación, pasado con su gracia, con trabajo en el planning y sin ninguna factura | planning, ciclos | Retención del cliente |
| V9 | El planning de lo facturado cambió en una foto más nueva (como G7) | planning, conciliación | Retención: hace falta una corrección o un abono |

**El turno, la unidad y el día los imprime el proveedor.** Si bastara con
imprimir «Nacht», «stuk» o una fecha fuera de la vigencia para que la línea
no casara con nada y volviera al histórico (donde una primera factura es
siempre «la de siempre»), el control de la tarifa pactada, y su bloqueo,
dependería de un texto del proveedor. Por eso una línea con tarifas pactadas
para ella que no casa con ninguna retiene. La unidad se compara en un
vocabulario común (hora, día, stuk): «dag» en la hoja de tarifas y «dag» en
la línea son lo mismo.

**G3 no asume tarifa plana.** La tarifa se busca por asignación, no por
proveedor. Un mismo autónomo puede tener tarifas distintas en dos obras a la
vez, y una tarifa media o heredada del contrato marco es exactamente el
error que esta regla existe para evitar.

**G2 necesita una política de tolerancia explícita**, versionada como
configuración y no escrita en el código. Qué se hace con las pausas, con el
tiempo de desplazamiento y con el redondeo al cuarto de hora tiene que estar
decidido antes de escribir la comparación, o la regla saltará constantemente.

### P · Órdenes de compra

Una PO es de un lado: la que un cliente da a BM Support BV (la consumen las
ventas a ese cliente) o la que BM Support BV da a un proveedor (la consumen
sus compras). Lo consumido es la base sin IVA de las imputaciones de las
facturas que cuentan (ni anuladas, ni fusionadas, ni sustituidas), menos los
abonos con su relación confirmada mientras la factura que abonan cuenta. Qué
referencia impresa es una PO lo decide el código casando con la lista de PO,
nunca el modelo. El valor y el fin vigentes son los de la última
modificación, que no puede tener una fecha posterior a hoy.

| ID | Comprobación | Fuente | Resultado |
| --- | --- | --- | --- |
| P1 | La PO imputada está abierta y su vigencia cubre los días del trabajo | órdenes de compra | Retención; se anula. Sin ningún día, sin datos |
| P2 | Una venta sin PO donde el Objeto (o, si no lo dice, el cliente) la pide. Un abono no: toma la de la factura que abona | maestro | Retención; se anula |
| P3 | La PO impresa está registrada y es de su parte; la imputada es de su parte y cubre el Objeto de la línea; una factura que imprime varias PO no deja una imputación sin ninguna | órdenes de compra | Retención; se anula. Sin ninguna PO de ese lado, sin datos |
| P4 | La factura carga a la PO más de lo que quedaba antes de ella, por fecha de factura y por id o por orden de llegada (una fecha atrasada no la libra) | órdenes de compra | Retención; se anula; pegajosa; suelo urgente |
| P5 | La PO lleva consumido el umbral de la política (80 %, entre 50 y 100) o más | órdenes de compra | Aviso de la PO |
| P6 | La PO ya estaba consumida entera antes de la factura y la factura le carga más | órdenes de compra | Retención; se anula; suelo urgente |
| P7 | La PO caduca dentro de los días de la política (30) con valor por consumir. Los días se cuentan desde el fin fijo al calcular la prioridad: un P7 aceptado no se reabre al día siguiente. Ya caducada con valor por consumir y con turnos en el planning después de su fin, retiene | órdenes de compra, planning | Aviso de la PO; se anula; puntos de caducidad |
| P8 | El trabajo planificado (después de hoy) por la tarifa de su lado pasa lo que queda | planning | Aviso de la PO. Sin planning, sin datos |
| P9 | Al ritmo de las últimas 8 semanas la PO se agota más de 14 días antes de su fin | órdenes de compra | Aviso de la PO |
| P10 | Lo facturado más lo trabajado sin facturar más lo planificado pasa el valor | planning, conciliación | Retención de la PO y de las facturas desde el punto en que se pasa. Sin planning, sin datos |

P5 y P7-P10 son de la PO entera, no de una factura: dan la prioridad de la
PO y no suben la de las facturas que le cargan (ver el registro del paso 9).

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
| Exceso de tarifa que bloquea en vez de retener (G3) | 10 % sobre la pactada (`config/reglas.yaml`, entre 1 y 100) |
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
| Mapeo de rúbricas de la declaración trimestral | Ya recogido en la arquitectura, se cruza con C4. Desde el paso 11 está en `config/btw.yaml`, marcado por confirmar: cada hoja de trabajo lo dice hasta que se confirme |
| Tratamiento de las facturas que llegan tras el cierre del trimestre | Define qué hace C4 además de avisar |
| Umbral de exceso de tarifa que justifica bloquear un pago | Única cifra del catálogo que es decisión de negocio pura |

---

## 6. El catálogo del motor, regla a regla

Lo que el motor evalúa hoy, regla a regla, tal como lo dice el código: qué
mira, qué hace un fallo en una factura de compra y en una de venta
(**Bloqueo**, **Retención** o **Aviso**, como en el apartado 2), si se puede
anular (con la lista dura de la decisión 12: la familia F, X1, E3, E4, K2, K4,
K6, R2, R3 y, en las compras, D2, D3, D4 y D6 no se anulan nunca), si es
pegajosa (su aviso no se cierra solo aunque desaparezca la condición), si
anularla pide la firma de una segunda persona, si abre una excepción (lo que
bloquea o retiene la abre siempre), qué aporta a la prioridad y de qué es el
aviso (una factura, un proveedor, un cliente, una PO, una importación o un
movimiento del banco).

<!-- catalogo:inicio -->

_Generado de `src/bms_agent/reglas/catalogo.py` con `python scripts/generar_catalogo_doc.py`: no se edita a mano. 82 reglas._

| Regla | Qué mira | Compra | Venta | Anulable (compra / venta) | Pegajosa | Segunda firma | Abre excepción | Prioridad | De qué |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Q1 | **Campos obligatorios**. Falta un campo obligatorio para el sentido de la factura: número, contraparte, fecha, periodo, base, IVA o régimen, total. Bloquea si falta el número, el total o la contraparte. | Retención | Retención | no / no | no | no | sí | otra | factura |
| Q2 | **Lectura dudosa sin verificar**. Un campo crítico se leyó con duda (low_confidence_fields o un literal que no se pudo leer) y nadie lo ha verificado. | Retención | Retención | no / no | no | no | sí | otra | factura |
| Q3 | **Texto sospechoso en el documento**. Las notas del documento traen texto dirigido a quien lo procesa (un IBAN, cambiar datos, llamar): señal de un intento de inyección. | Aviso | Aviso | sí / sí | no | no | sí | otra | factura |
| Q4 | **Original no guardado**. El original del documento no está en el almacén. | Aviso | Aviso | sí / sí | no | no | no | otra | factura |
| X1 | **Moneda**. La factura no está en euros: queda fuera de todos los totales. En un maestro, una fila con un importe en otra moneda no entra y bloquea su importación. | Bloqueo | Bloqueo | no / no | sí | no | sí | otra | factura |
| M2 | **Edición manual sin casar**. Una línea que una persona editó o excluyó no aparece en la extracción vigente (no se pudo casar por su huella): se conserva tal cual y una persona decide si sigue. | Retención | Retención | sí / sí | no | no | sí | otra | factura |
| M3 | **Exact y el documento no coinciden**. Una venta de Exact (o TRNSPRNT) y su PDF no dicen lo mismo (fecha, base, IVA, total, tipo o periodo), o tienen el mismo número y no se pudieron unir: cuenta la de Exact, y una persona mira la diferencia. | Retención | Retención | sí / sí | no | no | sí | otra | factura |
| Z1 | **Fuente pasada de frescura**. Lo último de una fuente es más viejo que su límite (banco 3 días laborables, Exact y TRNSPRNT 7 días): lo que depende de ella queda sin datos. | Aviso | Aviso | no / no | no | no | no | otra | importacion |
| Z2 | **Filas de importación rechazadas**. La última importación de una fuente rechazó filas (o entera), o trae una parte, un Objeto o un recurso que no existe (el planning los deja entrar sin resolver): nada se crea solo. | Retención | Retención | no / no | no | no | sí | otra | importacion |
| A0 | **Contraparte desconocida**. Ningún proveedor o cliente del maestro coincide exactamente (btw-id, KvK o alias confirmado), o coincide más de uno. | Retención | Retención | no / no | no | no | sí | otra | factura |
| A2 | **Distinto del maestro**. El nombre, el KvK o el btw-id impresos no dicen lo mismo que el maestro de la contraparte (un alias confirmado cuenta como su nombre). | Retención | Retención | sí / sí | no | no | sí | otra | factura |
| A5 | **btw-id**. Una compra sin btw-id que no dice KOR bloquea; un btw-id neerlandés que no es NL + nueve cifras + B + dos cifras retiene. | Bloqueo | Bloqueo | no / no | no | no | sí | otra | factura |
| A7 | **Datos cambiados respecto a su historia**. Lo que imprime un proveedor cambia respecto a su factura anterior: btw-id o KvK retienen, nombre o dirección avisan. | Retención | Retención | sí / sí | sí | no | sí | otra | factura |
| A8 | **Destinatario**. La factura no va dirigida a BM Support BV (config/empresa.yaml); una que llega por la vía de salida y no emite BM Support BV está mal encaminada y bloquea. | Retención | Retención | sí / sí | no | no | sí | otra | factura |
| B2 | **Número de factura repetido**. La misma contraparte con el mismo número normalizado, sin fusionar ni enlazar. Se cierra fusionando o enlazando. | Bloqueo | Bloqueo | sí / sí | sí | sí | sí | duplicado exacto | factura |
| B3 | **Posible duplicado por contenido**. Misma contraparte, el mismo total (0,01), como mucho 14 días entre las dos, periodos compatibles y número distinto. | Retención | Retención | sí / sí | sí | no | sí | duplicado | factura |
| B4 | **Periodo facturado dos veces**. Periodos de cobro que se pisan, por Objeto cuando las líneas lo nombran; sin las relaciones confirmadas ni los abonos. | Retención | Retención | sí / sí | sí | no | sí | duplicado | factura |
| B5 | **Horas cobradas dos veces**. Un turno del planning conciliado con más horas de compra de las que tiene, desde dos o más facturas que no se explican entre sí (la parte del planning de B5). | Retención | Retención | sí / sí | sí | no | sí | duplicado | factura |
| V7 | **Facturación doble**. En las ventas, el caso de B2 (el mismo número a la misma contraparte), el de B3 (el mismo importe a pocos días, periodos compatibles y otro número) o el de B5 (las horas de un turno cobradas desde dos facturas): se le ha facturado dos veces. | Retención | Retención | sí / sí | sí | no | sí | duplicado | factura |
| C4 | **Trimestre del BTW ya presentado**. La factura cae en un trimestre del BTW ya presentado y no es lo que se declaró de ella: llegó después, cambió después o ya no cuenta allí. Va a la lista del trimestre para el contable. | Aviso | Aviso | sí / sí | no | no | no | IVA blando | factura |
| D1 | **Desglose**. El desglose está: líneas con cantidad, tarifa e importe, base, total y, si se repercute IVA, tipo y cuota. | Bloqueo | Retención | no / no | no | no | sí | otra | factura |
| D2 | **Suma de líneas**. La suma de las líneas es la base (0,01 por línea más 0,02). | Bloqueo | Retención | no / no | no | no | sí | otra | factura |
| D2b | **Aritmética de línea**. Cantidad por tarifa es el importe de cada línea (0,01). | Bloqueo | Retención | sí / sí | no | no | sí | otra | factura |
| D3 | **Cuota de IVA**. La base por el tipo es la cuota, tipo a tipo (0,02). | Bloqueo | Bloqueo | no / no | no | no | sí | IVA duro | factura |
| D4 | **Total**. La base más la cuota es el total (0,02). | Bloqueo | Bloqueo | no / no | no | no | sí | otra | factura |
| E0 | **Falta información del IVA**. No se sabe cómo trata el IVA la factura, o con IVA normal le falta el tipo o la cuota (en la cabecera o en una fila del desglose). | Retención | Retención | no / no | no | no | sí | IVA blando | factura |
| E1 | **Régimen distinto del maestro**. El régimen de IVA de la factura no es el que el maestro tiene registrado del proveedor. | Retención | Retención | sí / sí | no | no | sí | IVA blando | factura |
| E2 | **Cambio de régimen**. El régimen cambia respecto a la factura anterior del mismo proveedor. | Retención | Retención | sí / sí | sí | no | sí | IVA blando | factura |
| E3 | **IVA con KOR**. Con KOR la factura no repercute IVA. | Bloqueo | Bloqueo | no / no | no | no | sí | IVA duro | factura |
| E4 | **IVA trasladado**. Con IVA trasladado no hay cuota y figura el btw-id del receptor. | Bloqueo | Bloqueo | no / no | no | no | sí | IVA duro | factura |
| E5 | **Cerca del umbral de la KOR**. Lo que un proveedor con KOR ha facturado este año a BM Support BV llega al porcentaje de la política del umbral de la KOR (un indicio: el umbral es de todo lo que factura). | Aviso | Aviso | sí / sí | no | no | no | IVA blando | proveedor |
| E7 | **Tipo o tratamiento de IVA raro**. Un tipo de IVA que no es de la lista de la política (0, 9 y 21), o una venta con IVA trasladado o al 0 % a un cliente que el maestro no tiene marcado para facturarle así. | Retención | Retención | sí / sí | no | no | sí | IVA blando | factura |
| F0 | **Cuentas heredadas sin atestar**. Las cuentas del primer maestro se aceptan como referencia pero nadie las ha comprobado: una tarea, de nivel atención, para atestarlas. | Retención | Retención | no / no | sí | no | sí | IBAN | importacion |
| F1 | **IBAN**. El IBAN impreso pasa el dígito de control módulo 97. | Bloqueo | Bloqueo | no / no | sí | no | sí | IBAN | factura |
| F2 | **IBAN no pagable**. El IBAN de la factura no es una cuenta pagable de su proveedor: verificada, atestada o heredada, en el último maestro de Exact y sin un cambio por verificar. | Bloqueo | Bloqueo | no / no | sí | no | sí | IBAN | factura |
| F3 | **IBAN nuevo o cambiado**. El IBAN de la factura es nuevo para el proveedor, o está rechazado: verificación telefónica al número del maestro de antes del documento. | Bloqueo | Bloqueo | no / no | sí | no | sí | IBAN | factura |
| F4 | **IBAN de un tercero o factoring**. El IBAN está registrado para otro titular, o la factura habla de factoring, cesión o G-rekening. Bloquea y se escala. | Bloqueo | Bloqueo | no / no | sí | no | sí | IBAN | factura |
| F5 | **Cuenta cambiada en el maestro**. Una cuenta añadida, cambiada o quitada en un maestro posterior al primero, sin verificar por teléfono. | Bloqueo | Bloqueo | no / no | sí | no | sí | IBAN | proveedor |
| F6 | **Exact y TRNSPRNT no coinciden**. Exact y TRNSPRNT dicen cuentas distintas del mismo proveedor. | Bloqueo | Bloqueo | no / no | sí | no | sí | IBAN | proveedor |
| F7 | **Cargo a una cuenta no pagable**. Un cargo del banco a un proveedor (casado con una factura suya, o a una cuenta registrada para él) fue a una cuenta que no es pagable para él, y no es un beneficiario conocido ni una cuenta propia. | Bloqueo | Bloqueo | no / no | sí | no | sí | IBAN | movimiento |
| F8 | **Verificación que no vale**. La llamada no fue al teléfono del maestro de antes del documento, el teléfono cambió dentro del enfriamiento o quien verificó no tenía el permiso. | Bloqueo | Bloqueo | no / no | sí | no | sí | IBAN | proveedor |
| F9 | **Teléfono de verificación cambiado**. El teléfono de verificación de un proveedor acaba de cambiar: empieza el enfriamiento. | Aviso | Aviso | no / no | sí | no | no | IBAN | proveedor |
| F10 | **IBAN ajeno en una venta**. Una factura de venta lleva un IBAN que no es una cuenta de BM Support BV (config/empresa.yaml): el cliente pagaría a otra cuenta. | Retención | Retención | no / no | sí | no | sí | IBAN | factura |
| K1 | **Vencida**. Sin pagar pasado su vencimiento: una compra desde el día siguiente, una venta pasados los días de la política. Sin extractos que cubran desde su fecha, sin datos. | Aviso | Aviso | sí / sí | no | no | sí | días vencida | factura |
| K2 | **Pagado distinto del saldo**. Lo confirmado no deja el saldo a cero: un pago parcial (la factura sigue pendiente o vencida con lo que queda) o de más. | Retención | Aviso | no / no | sí | no | sí | otra | factura |
| K3 | **Pagada a mano sin rastro en el banco**. Marcada pagada a mano y, pasados los días de la política, ningún extracto trae el pago. | Aviso | Aviso | sí / sí | no | no | no | otra | factura |
| K4 | **Pago doble**. Dos cargos a la misma cuenta, por el mismo importe y con la misma referencia en pocos días, o una factura pagada de más con dos cargos. | Bloqueo | Bloqueo | no / no | sí | no | sí | duplicado | factura |
| K5 | **Pagada estando Bloqueada**. Se pagó un día en que la factura tenía un hallazgo que bloquea, pendiente y sin anular. | Retención | Retención | no / no | sí | no | sí | otra | factura |
| K6 | **Extractos que no encadenan**. El saldo de apertura de un extracto no es el de cierre del anterior, o falta un número: lo pagado desde ahí no se da por bueno. | Bloqueo | Bloqueo | no / no | sí | no | sí | otra | importacion |
| K7 | **Movimiento sin casar**. Un movimiento del banco que, pasados los días de la política, no está casado con ninguna factura. | Aviso | Aviso | sí / sí | no | no | no | otra | movimiento |
| K8 | **Banco y Exact no coinciden**. El banco y Exact dicen importes pagados distintos de la misma factura. | Retención | Retención | no / no | no | no | sí | otra | factura |
| G1 | **Sin turnos en el planning**. Una compra sin ningún turno de su proveedor ni de sus personas en el periodo facturado. Retiene; bloquea si el planning es obligatorio (config/reglas.yaml). Anularla pide segunda firma. | Retención | Retención | sí / sí | no | sí | sí | planning | factura |
| G2 | **Horas distintas de las validadas**. Las horas facturadas contra las validadas del planning, en la celda más fina que llevan los dos lados (persona y día, Objeto y día, Objeto y semana, periodo), con 0,25 h por día de tolerancia. Turnos sin validar, filas semanales que no se pueden partir o días que el planning no cubre: sin datos. | Retención | Retención | sí / sí | no | no | sí | planning | factura |
| G3 | **Tarifa distinta de la pactada**. La tarifa de una línea de compra contra la pactada (de lo más concreto a lo general: recurso y Objeto, Objeto, recurso, proveedor; el turno tiene que ser el mismo): por encima retiene, y por encima del porcentaje de la política bloquea. Sin pactada ni planning, contra el histórico: la misma contraparte cobra otra tarifa por el mismo trabajo en el mismo Objeto. Dos pactadas igual de concretas con precios distintos: sin datos en la línea y la factura retenida, con su excepción. Con pactadas para la línea pero ninguna de su unidad o su día (los imprime el proveedor): sin datos y la factura retenida, no el histórico. Sin pactada, la tarifa del turno en el planning, si todos los de su celda dicen la misma. | Retención | Retención | sí / sí | no | no | sí | planning | factura |
| G4 | **Objeto distinto del planning**. El Objeto de una línea de compra contra el planning: la persona o el proveedor tienen esos días turnos en otro Objeto. Una línea sin Objeto recibe la propuesta del planning, que confirma una persona. | Retención | Retención | sí / sí | no | no | sí | planning | factura |
| G5 | **Periodo distinto del planning**. El periodo y la semana ISO de una compra contra el planning: la semana impresa no es la de sus fechas, o lo facturado cae en días sin turnos y ese trabajo está sin facturar en otra semana. | Retención | Retención | sí / sí | no | no | sí | planning | factura |
| G6 | **Recargo a otra tarifa que la suya**. Una línea de un recargo (noche, fin de semana, festivo) se cobra a su propia tarifa pactada. Sin tarifa propia pero con otras pactadas para la línea (la de día), sin datos y la factura retenida para que una persona confirme el recargo; sin ninguna pactada, la mira G3 con el histórico. Con el planning, las horas de cada recargo no pasan las de los turnos de ese recargo. | Retención | Retención | sí / sí | no | no | sí | planning | factura |
| G7 | **El planning cambió tras conciliar**. Una foto más nueva del planning cambia las horas ya conciliadas con una compra (otras horas, turnos que ya no están o se cancelaron, turnos nuevos). | Aviso | Aviso | sí / sí | no | no | no | planning | factura |
| V1 | **Horas facturadas distintas de las validadas**. Las horas de una venta contra las validadas facturables del planning, en la celda más fina de los dos lados (como G2). | Retención | Retención | sí / sí | no | no | sí | planning | factura |
| V2 | **Objeto de la venta**. El Objeto de cada línea de venta existe, es del cliente facturado y estaba activo; una línea sin Objeto retiene, con la propuesta del planning si la hay. | Retención | Retención | sí / sí | no | no | sí | planning | factura |
| V3 | **Periodo de la venta distinto del planning**. El periodo y la semana de lo facturado contra el planning (como G5). | Retención | Retención | sí / sí | no | no | sí | planning | factura |
| V4 | **Tarifa de venta distinta de la pactada**. La tarifa de una línea de venta no es la de venta pactada (ni por encima ni por debajo). Sin tarifa pactada, la del turno en el planning; sin ninguna, sin datos. | Retención | Retención | sí / sí | no | no | sí | planning | factura |
| V5 | **Horas validadas sin facturar en lo facturado**. Dentro del Objeto y el periodo que cobra una venta, turnos validados facturables que ninguna línea de venta cubre. | Retención | Retención | sí / sí | no | no | sí | facturación ausente | factura |
| V6 | **Trabajo sin facturar**. Turnos validados facturables que ninguna venta cubre, pasado el fin de su periodo de facturación más sus días de gracia. Valorado a la tarifa de venta pactada o, si no, marcado como estimado. | Retención | Retención | sí / sí | no | no | sí | trabajo sin facturar | cliente |
| V8 | **Periodo de facturación sin factura**. Un periodo del ciclo de facturación de un cliente u Objeto, con trabajo en el planning, ya pasado con su gracia y sin ninguna factura. | Retención | Retención | sí / sí | no | no | sí | facturación ausente | cliente |
| V9 | **El planning cambió tras facturar**. Una foto más nueva del planning cambia lo que se facturó (regla 9 de arquitectura.md): hace falta una corrección o un abono. | Retención | Retención | sí / sí | no | no | sí | planning | factura |
| P1 | **PO no válida**. La PO a la que se imputa la factura está cerrada, o el trabajo cae fuera de su vigencia (que sea de la parte y cubra el Objeto lo mira P3). | Retención | Retención | sí / sí | no | no | sí | límite de PO | factura |
| P2 | **Falta la PO**. Una venta sin PO donde el Objeto (o, si no lo dice, el cliente) la pide. Un abono no: toma la PO de la factura que abona. | Retención | Retención | sí / sí | no | no | sí | límite de PO | factura |
| P3 | **PO desconocida o de otro**. La PO que dice la factura no está registrada, es de otra parte o no cubre el Objeto de la línea; o la factura imprime varias PO y una imputación no va a ninguna (una persona decide con imputar_po). | Retención | Retención | sí / sí | no | no | sí | límite de PO | factura |
| P4 | **Factura por encima de lo que queda**. La factura carga a la PO más de lo que le quedaba antes de ella, sin IVA: por fecha de factura y por id, o por orden de llegada (una fecha atrasada no la libra). | Retención | Retención | sí / sí | sí | no | sí | límite de PO duro | factura |
| P5 | **PO casi consumida**. La PO lleva consumido el porcentaje de la política (80 %) o más. | Aviso | Aviso | no / no | no | no | no | límite de PO | orden_compra |
| P6 | **PO consumida y se sigue facturando**. La PO ya estaba consumida entera antes de la factura (por fecha o por llegada), y la factura le carga más. | Retención | Retención | sí / sí | no | no | sí | límite de PO duro | factura |
| P7 | **PO a punto de caducar**. La PO caduca dentro de los días de la política (30) con valor por consumir. Ya caducada, retiene si el planning tiene trabajo después de su fin. | Aviso | Aviso | sí / sí | no | no | no | caducidad de PO | orden_compra |
| P8 | **Planificado por encima de lo que queda**. El trabajo planificado (después de hoy) por la tarifa pactada, o la del turno, pasa lo que queda de la PO. | Aviso | Aviso | no / no | no | no | no | límite de PO | orden_compra |
| P9 | **PO que se agota antes de tiempo**. Al ritmo de las últimas semanas (8), la PO se agota antes de los días de margen (14) de su fin. | Aviso | Aviso | no / no | no | no | no | límite de PO | orden_compra |
| P10 | **Esperado por encima de la PO**. Lo facturado más lo trabajado sin facturar más lo planificado pasa el valor de la PO; retiene también las facturas que le cargan desde ahí. | Retención | Retención | sí / sí | no | no | sí | límite de PO duro | orden_compra |
| R1 | **Factura nombrada que no está**. Un abono o una corrección nombra una factura de la misma contraparte que no está en el almacén (o que está repetida). | Retención | Retención | sí / sí | no | no | sí | otra | factura |
| R2 | **Abonos por encima de la original**. Los abonos confirmados le quitan a una factura más de lo que vale, o un abono se aplica por más de lo que vale. | Retención | Retención | no / no | sí | no | sí | otra | factura |
| R3 | **Original y sustituta a la vez**. La original y la que la sustituye (o corrige) están las dos pendientes (se pagaría el mismo trabajo dos veces) o las dos pagadas. | Bloqueo | Bloqueo | no / no | sí | no | sí | duplicado | factura |
| R4 | **Abono sin relación**. Un abono sin ninguna relación confirmada que diga a qué factura abona. | Aviso | Aviso | no / no | no | no | no | otra | factura |
| R5 | **Relación por confirmar**. La extracción o Exact proponen una relación entre dos facturas: hasta que una persona la confirma no mueve saldos, IVA ni duplicados. | Aviso | Aviso | no / no | no | no | no | otra | factura |
| U1 | **Importe inusual**. La base se sale de lo habitual de la contraparte (mediana y MAD de sus facturas anteriores; con menos de tres, sin datos). | Aviso | Aviso | sí / sí | no | no | sí | otra | factura |

<!-- catalogo:fin -->
