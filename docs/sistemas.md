# Los sistemas de la empresa: TRNSPRNT y Exact Online

Lo que se sabe de los dos programas con los que el agente tiene que hablar, de
dónde sale cada dato y qué cambia en el diseño.

> **Procedencia.** Las páginas de `trnsprnt.nl`, `exact.com` y
> `support.exactonline.com` están bloqueadas por la política de red del
> entorno donde se escribió esto. Lo que sigue sale de resultados de búsqueda,
> no de haber leído las páginas. Cada dato lleva su fuente, y lo marcado
> *por verificar* hay que confirmarlo en cuanto se abra el acceso.

---

## TRNSPRNT: el programa de planificación

**Qué es.** TRNSPRNT B.V. (Leiden, desde 2011) hace un sistema de gestión
para empresas de servicios de *facility*: se presenta para *beveiligers*,
*brandwachten*, instaladores, limpieza, *verkeersregelaars* y *surveillanten*.
Sus módulos, según su propia descripción: **planificación, compras (*inkoop*),
facturación y nóminas (*verloning*)**, automatizados en un flujo de trabajo, y
"fáciles de combinar con vuestros programas de contabilidad".
([Hoe werkt het](https://www.trnsprnt.nl/hoe-werkt-het/),
[trnsprnt.nl](https://trnsprnt.nl/))

Tiene tres aplicaciones: para empleados, para clientes y una **para zzp'ers**,
desde la que reciben encargos, responden con ofertas e informan por objeto.
([TRNSPRNT ZZP en Google Play](https://play.google.com/store/apps/details?id=trnsprnt.TRNSPRNTZZPApp))

Cada empresa cliente tiene su propio subdominio (`mijn<cliente>.trnsprnt.nl`).

**Lo que no se sabe todavía**, y hay que preguntárselo al servicio técnico
(`servicedesk@trnsprnt.nl`) o mirarlo en vuestra cuenta:

- Si vuestra cuenta tiene **API** o solo exportaciones (CSV, Excel).
- Si el módulo de compras **genera las facturas de los zzp'ers** a partir de
  las horas aprobadas (*self-billing*).
- Qué exporta hacia Exact y en qué formato, si es que ya hay una conexión.

### La pregunta que cambia la arquitectura: ¿quién hace la factura del zzp'er?

En *self-billing* la factura no la hace el autónomo: la hace quien le
contrata, a partir de las horas aprobadas, y el autónomo la acepta.
([JEX: selfbilling](https://www.jex.nl/blog/selfbilling))

Si TRNSPRNT ya genera así las facturas de compra, cambian tres cosas:

| Si las facturas… | Entonces |
| --- | --- |
| **las genera TRNSPRNT** desde las horas aprobadas | Los datos ya existen estructurados. Se exportan, no se leen con un modelo: más barato, exacto y sin riesgo de extracción. El cruce contra el planning se cumple por construcción |
| **las manda cada zzp'er** por correo | Es el caso para el que está hecho el extractor, y el cruce contra el planning es imprescindible |
| **hay de las dos** | El agente se concentra en las que llegan **por fuera** de TRNSPRNT, que son justo las de más riesgo |

Dicho de otra forma: el modelo de lenguaje es para lo que no tiene estructura,
no para leer PDF de datos que ya existen en una base de datos.

### Lo que esto dice de los datos de ejemplo

Las facturas de ejemplo con las que se probó el panel tienen oficios de obra
(*montagewerk*, *timmerwerk*, *elektrawerk*) y obras en el puerto. Fue una
suposición para tener datos de prueba. Si la planificación está en TRNSPRNT, lo
probable es que el trabajo sea por **turnos** (*diensten*) en **objetos**,
con tarifas que cambian según la hora y el día (*toeslagen* de noche, fin de
semana y festivos). Eso afecta a:

- **G3, cambio de tarifa**: tiene que comparar por tipo de turno y recargo,
  no por oficio. Un turno de noche más caro que uno de día no es un cambio de
  tarifa.
- **El simulador**: la dimensión *trabajo* pasa a ser tipo de turno.
- **El cruce contra el planning**: por turno y fecha, no por semana.

No se rehacen los ejemplos sobre otra suposición: primero una factura real
anonimizada de cada tipo.

### La exportación del planning que espera el agente (paso 10)

Todavía no hay una exportación real de TRNSPRNT. El mapeo está hecho contra
un fichero **sintético** de turnos de seguridad y *facility* (diensten en
objetos, con recargos de tarde, noche, fin de semana y festivo), y se
enciende de verdad cuando llegue una exportación real: entonces se ajustan
los nombres de las columnas en el YAML del mapeo, no el código. Se importa
con `bms-agent importar trnsprnt planning FICHERO [--desde AAAA-MM-DD --hasta
AAAA-MM-DD]` (por defecto, la foto cubre del primer al último turno que trae).

**Por turnos** (`config/importacion/trnsprnt-planning-v1.yaml`, CSV con `;` y
coma decimal, fechas `dd-mm-aaaa`; ejemplo en
`tests/fixtures/importacion/trnsprnt-planning-v1.csv`):

| Columna | Qué es | Valor obligatorio |
|---|---|---|
| `Dienst-ID` | identificador estable del turno | no (ver abajo) |
| `Datum` | día del turno (el de inicio, si cruza la medianoche) | sí |
| `Begintijd`, `Eindtijd` | hora de inicio y de fin (`7:00` o `07:00`) | no |
| `Pauze (min)` | pausa en minutos | no |
| `Objectcode`, `Objectnaam` | el Objeto (se busca por el código) | no |
| `Opdrachtgever` | el cliente (número de deudor de Exact) | no |
| `Medewerker` | la persona (recurso) | no |
| `Leverancier` | el proveedor (número de acreedor de Exact) | no |
| `Dienstsoort` | tipo de servicio (Objectbeveiliging, Receptie…) | no |
| `Diensttype` | tipo de turno: Dag, Avond, Nacht, Weekend, Feestdag | no |
| `Gepland (u)`, `Gewerkt (u)`, `Goedgekeurd (u)` | horas planificadas, trabajadas y validadas | no; sin planificadas se calculan de las horas menos la pausa; un turno validado lleva las validadas |
| `Status` | Gepland/Ingepland, Uitgevoerd/Gewerkt, Goedgekeurd/Geaccordeerd, Geannuleerd/Vervallen | sí |
| `Factureerbaar` | si se factura al cliente (Ja/Nee) | no |
| `Inkooptarief`, `Verkooptarief` | tarifa de compra y de venta del turno | no |
| `PO-nummer` | la PO del cliente | no |
| `Valuta` | moneda (solo euros) | no |

Las columnas `Datum`, `Begintijd`, `Eindtijd`, `Objectcode`, `Medewerker` y
`Status` tienen que estar en la cabecera: así reconoce el agente el fichero.

**Por semanas** (`config/importacion/trnsprnt-planning-semana-v1.yaml`, la
exportación pivotada *weekoverzicht*): `Jaar`, `Week`, `Objectcode`,
`Opdrachtgever`, `Medewerker`, `Leverancier`, `Dienstsoort`, `Diensttype`,
una columna por día (`Ma` a `Zo`), `Totaal` (obligatorio, y tiene que ser la
suma de los días), `Status` (vacío es validado) y `Factureerbaar`. Una fila
semanal se compara **a nivel de semana**: nunca se parte en días.

Lo que el agente hace con el fichero:

- **Entra entero o no entra.** Una fila que no se lee (una fecha imposible,
  unas horas negativas, un total que no suma, otra moneda, dos turnos con el
  mismo identificador) rechaza la foto entera: medio planning daría por no
  trabajado lo que sí lo está.
- **Cada foto aceptada queda congelada** (evidencia, no se toca) y vale la más
  nueva de cada día (`v_turno_vigente`). Lo ya facturado se concilia con la
  foto de entonces; si una foto nueva cambia una semana facturada, es G7 (compras)
  o V9 (ventas).
- **Sin identificador estable** (`Dienst-ID` vacío), el turno lleva una clave
  sintética (día, Objeto, persona, horas y tipo de turno) marcada como
  **frágil**: si TRNSPRNT le cambia la hora a un turno, la foto siguiente lo ve
  como otro turno. Hay que pedir a TRNSPRNT que exporte su identificador.
- **Lo que no está en el maestro** (un Objeto, una persona, un proveedor o un
  cliente desconocidos) entra con su texto y sin resolver: no se crea nada, y
  Z2 lo dice. Se resuelve en cada pasada en cuanto el maestro lo tenga.

---

## Exact Online: la contabilidad

**API.** REST, con autenticación OAuth 2.0, y cada administración es una
*division* aparte.
([Peliqan: divisions y límites](https://peliqan.io/blog/exact-online-api/),
[Exact: introducción a la REST API](https://support.exactonline.com/community/s/article/All-All-DNO-Content-restintro?language=en_GB))

**Límites de uso** (*por verificar*: dependen del contrato):
**60 llamadas por minuto y 5.000 al día, por administración.**
([Exact: API limits](https://support.exactonline.com/community/s/article/All-All-DNO-Simulation-gen-apilimits?language=en_GB))

**Tokens**: el de acceso dura **10 minutos**; el de refresco vale **hasta el
siguiente refresco**, y no se debe pedir un token nuevo más de una vez cada
10 minutos.
([Exact: API limits](https://support.exactonline.com/community/s/article/All-All-DNO-Simulation-gen-apilimits?language=en_GB),
[n8n: uso del refresh token](https://community.n8n.io/t/refresh-token-usage-for-exact-online/8103))

**Factura de compra con el PDF adjunto**: primero se crea el documento y luego
se vincula al asiento (tipo 20 para compras, 10 para ventas).
([Exact: entry with attachment](https://support.exactonline.com/community/s/article/All-All-DNO-Content-rest-api-business-cases-rest-bsncs--entrattach?language=en_GB))

### Lo que estos datos obligan a hacer

**1. Un espejo de los datos maestros, no una consulta por factura.** Con
5.000 llamadas al día, comprobar cada factura contra Exact en directo (el
proveedor, su IBAN, la cuenta contable, el código de IVA, si ya existe ese
número) se come el presupuesto en cuanto el volumen crece. Lo correcto es
copiar una vez al día proveedores, cuentas bancarias de proveedores, cuentas
contables y códigos de IVA a la base local, y comprobar contra la copia. La
copia es de solo lectura: el agente nunca cambia un dato maestro.

**2. Un único dueño del token.** El token de refresco se renueva en cada uso y
el anterior deja de valer. Si dos procesos refrescan a la vez, uno se queda
fuera y alguien tiene que volver a autorizar a mano. Tiene que haber **un
solo proceso** que guarde y renueve el token, que escriba el nuevo **antes**
de usar el de acceso, y que el resto le pida acceso a él.

**3. El PDF viaja con el asiento.** El flujo de adjuntos permite que el
original quede dentro de Exact junto a la contabilización: cuando el asesor
pregunte por una factura, la tiene ahí sin pedírsela a nadie.

**4. Una sola fuente de verdad para el IBAN.** La regla de que el IBAN sale
del maestro de proveedores y nunca del documento sigue en pie. Pero si
TRNSPRNT y Exact guardan **los dos** la cuenta de cada zzp'er, hay que decidir
cuál manda, y una discrepancia entre ellos es en sí misma una alerta del
mismo tipo que F3.

---

## Pendiente

- [ ] Abrir en la configuración del entorno los dominios `trnsprnt.nl`,
      `www.trnsprnt.nl`, `www.exact.com`, `support.exactonline.com` y
      `start.exactonline.nl`, y verificar lo marcado arriba.
- [ ] Saber si TRNSPRNT genera las facturas de compra, y en qué proporción.
- [ ] Saber si vuestra cuenta de TRNSPRNT tiene API o solo exportaciones.
- [ ] Cuántas administraciones hay en Exact.
- [ ] Una factura real anonimizada de cada tipo.
