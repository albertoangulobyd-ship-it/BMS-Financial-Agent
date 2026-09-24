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
