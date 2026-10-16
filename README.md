# BMS Financial Agent

Agente de administración financiera para BMS Support. Automatiza la lectura de
facturas que llegan por correo, su contabilización en Exact, la facturación a
clientes desde el programa de planning, la preparación de ficheros de pago SEPA
y la hoja de trabajo de la declaración trimestral de IVA.

## Principio de diseño

> El modelo extrae y redacta. El código determinista decide y ejecuta.
> Ningún euro se mueve sin una firma humana sobre una pantalla que el modelo
> no ha escrito.

Todo lo demás se deriva de esa frase. Si una decisión la toma el modelo en lugar
del código, o un pago sale sin firma, la arquitectura está rota aunque el
sistema funcione.

## Documentación

| Documento | Contenido |
| --- | --- |
| [docs/arquitectura.md](docs/arquitectura.md) | Zonas de confianza, reglas duras, reparto de responsabilidades, modelo de datos, plan por fases, SEPA, IVA y AVG. |
| [docs/sistemas.md](docs/sistemas.md) | TRNSPRNT y Exact Online: qué se sabe de cada uno, de dónde sale cada dato y qué obliga a cambiar en el diseño. |
| [docs/entorno-local.md](docs/entorno-local.md) | **Para tenerlo en tu ordenador con Windows, sin instalar Python.** Docker Desktop, arrancar y parar, dónde dejar los ficheros, datos de prueba, la clave de la API, copias al disco cifrado y lo que cuesta tenerlo funcionando. |
| [docs/instalacion-nativa.md](docs/instalacion-nativa.md) | **Lo mismo sin Docker**: instalación nativa en Windows con el cortafuegos de Windows por programa, la clave cifrada con DPAPI, la comprobación del aislamiento (`comprobar.bat`), lo que aísla cada variante y lo que cuesta (0 € de software). |
| [docs/instalacion-windows.md](docs/instalacion-windows.md) | Clave de API, instalación con Python y primera prueba en Windows, paso a paso (para desarrollar; para usarlo, mejor el entorno local). |
| [docs/fase-0.md](docs/fase-0.md) | **Empieza aquí.** Puesta en marcha y uso del observador, y las decisiones de diseño del extractor. |
| [docs/uso-v1.md](docs/uso-v1.md) | **Para el día a día.** La rutina diaria, qué quiere decir cada prioridad, cómo corregir un dato, cómo verificar un IBAN por teléfono y cómo cerrar un trimestre del BTW. |
| [docs/diseno-v1.md](docs/diseno-v1.md) | Resumen en castellano de la V1: modelo de datos, comprobaciones, prioridad y orden de construcción. |
| [docs/modelo-datos.md](docs/modelo-datos.md) | El almacén de la V1: cada tabla y su clase (controlada, solo escritura, evidencia, caché), las vistas y de dónde sale cada estado. |
| [docs/validacion-facturas.md](docs/validacion-facturas.md) | Catálogo de reglas de validación de facturas de zzp'er: identidad, numeración, fechas, importes, régimen de IVA, datos de pago, contraste con el planning y riesgo laboral; al final, la tabla de las reglas del motor, generada del código. |
| [docs/integracion-web.md](docs/integracion-web.md) | Cómo conecta un sitio propio con el agente: el contrato de datos v1 (`/api/datos`) y el v2 (`/api/v2`, `export --v2`), servidor local y dónde puede vivir un botón de ejecutar. |
| [docs/portal-consulta.md](docs/portal-consulta.md) | Arquitectura del portal web de consulta: modelo de lectura separado, API de solo lectura y frontend estático sin datos. |
| [docs/costes.md](docs/costes.md) | Por qué la suscripción y la API son carteras distintas, cómo ponerle un techo duro al gasto y las palancas para bajarlo. |
| [docs/mcp-setup.md](docs/mcp-setup.md) | Registro del servidor MCP de Zapier y por qué queda fuera del camino que toca dinero. |

## Puesta en marcha

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest

export ANTHROPIC_API_KEY=sk-ant-...
bms-agent extract facturas/    # deja los PDF ahí primero; lo ya leído no se paga
bms-agent importar-out         # lleva out/ al almacén (datos/) y lo tipa, sin llamar a la API
bms-agent sembrar              # clientes, Objetos y tarifas de venta de config/tarifas.yaml
bms-agent importar exact proveedores acreedores.csv --token ...   # maestros (--simular: qué cambiaría)
bms-agent iban listar          # el registro de cuentas; iban verificar|rechazar|atestar|telefono
bms-agent importar banco extracto extracto.xml --token ...   # CAMT.053, MT940 o CSV del banco
bms-agent pagos --sin-casar    # lo que el banco movió y no casa; --propuestas, --factura N
bms-agent flujo-caja           # lo que se espera cobrar y pagar, y lo que movió el banco
bms-agent extract --salientes ventas/   # facturas emitidas por BMS: entran por la vía de salida
bms-agent importar exact facturas_venta ventas.csv --token ...   # las ventas de Exact, con líneas
bms-agent relaciones           # abonos, correcciones y sustituciones propuestas, por confirmar
bms-agent proveedores          # lo pendiente y lo vencido de cada uno; `proveedor 3`, su vista
bms-agent clientes             # lo mismo de los clientes; `cliente 2`, su vista
bms-agent importar po_csv ordenes_compra pos.csv --token ...   # la hoja de PO (CSV o YAML)
bms-agent importar po_csv modificaciones_po cambios.csv --token ...   # sus modificaciones
bms-agent ordenes              # las PO: valor, consumido sin IVA y lo que queda; `orden 4`, su ficha
bms-agent objetos              # ingresos, costes y margen de cada Objeto, y lo que no es de ninguno
bms-agent objeto 7             # un Objeto: su economía por mes y semana, sus facturas, horas y PO
bms-agent btw ver              # el BTW: el trimestre en curso, los por presentar y el año; `btw ver 2026-T3`
bms-agent btw hoja 2026-T3 --salida hoja.csv   # la hoja de trabajo (CSV) y su sha256
bms-agent btw listo --trimestre 2026-T3 --hoja-sha256 ... --motivo "..." --token ...   # lista para revisar; `btw anotar` (con --rev y --motivo), la presentación hecha a mano
bms-agent fuentes              # de cuándo es lo último de cada fuente (Z1)
bms-agent recalcular --diaria  # reglas y hallazgos al día (--simular: qué cambiaría)
bms-agent usuario crear Ana --rol administracion   # personas y sus permisos
bms-agent usuario token Ana    # su token personal (solo se guarda su hash)
bms-agent resumen              # el panel principal: dinero, caja, facturación, PO, BTW y lo que pide atención
bms-agent buscar --filtro proveedor_id=3 --filtro vencida=si   # búsqueda; `buscar --filtros`, cuáles hay
bms-agent facturas             # la más urgente primero; `factura 12` da la ficha
bms-agent historial 12         # la historia de una factura: quién cambió qué, cuándo y por qué
bms-agent accion marcar_revisada --factura-id 12 --huella ... --token ...   # las órdenes
bms-agent politica cargar config/reglas.yaml --token ...   # admin: pesos, reglas, empresa o btw, con su hash
bms-agent db verificar         # auditoría, anclas, evidencia y hash de cada original
bms-agent extract --estricta facturas/   # releer con otra versión: con almacén, deja candidatas
bms-agent score                # precisión contra respuestas escritas a mano
bms-agent coste                # qué ha costado cada pasada y versión; --estimar, la siguiente
bms-agent reextraer --abiertas --presupuesto 15   # volver a leer con el esquema v2, con techo
bms-agent score --comparar-versiones     # la puerta: la versión nueva contra la anterior
bms-agent reextraer --activar --token ...        # admin: lo releído pasa a vigente si pasa la puerta
bms-agent panel                # panel del historico (del almacén, con lo corregido)
bms-agent simulador            # simulador de tarifas, para decidir el modelo de precios
bms-agent export --tarifas config/tarifas.yaml   # datos en JSON, para un sitio propio (contrato v1)
bms-agent export --v2          # todo lo de /api/v2 en un fichero (contrato v2, sin IBAN)
bms-agent serve                # servidor local en 127.0.0.1; la consola en /consola
bms-agent report               # ficha detallada de cada factura
bms-agent demo crear           # DATOS DE PRUEBA en datos/demo.sqlite3, aparte de la base de verdad
bms-agent copia E:/copias      # copia de seguridad comprobada; `restaurar CARPETA`, la vuelta
bms-agent comprobar-aislamiento --rol consola   # instalación nativa: prueba a salir a internet
bms-agent clave guardar        # instalación nativa: la clave de la API cifrada con DPAPI
```

En el ordenador del dueño todo esto corre en Docker, aislado: la consola y la
base sin internet, el lector de PDF saliendo solo a la API de Anthropic por un
proxy con lista blanca (`bms-agent salida`) y unos scripts de Windows
(`docker/iniciar.bat`, `importar.bat`, `leer-facturas.bat`, `copia.bat`...).
Ver [docs/entorno-local.md](docs/entorno-local.md). Sin Docker, la instalación nativa
(`windows/instalar.bat`) da el mismo aislamiento con un Python para cada papel y el
cortafuegos de Windows: [docs/instalacion-nativa.md](docs/instalacion-nativa.md).

## Estado

Fase 0 en marcha: el observador lee PDFs de una carpeta, los extrae a esquema
y mide la precisión contra respuestas escritas a mano. No tiene credenciales
de ningún sistema de la empresa. Ver [docs/fase-0.md](docs/fase-0.md).

La V1 se construye por pasos según [docs/v1/spec.md](docs/v1/spec.md), con el
resumen en castellano en [docs/diseno-v1.md](docs/diseno-v1.md). Lo hecho en
cada paso, y dónde se apartó de la especificación, está en
[docs/v1/registro.md](docs/v1/registro.md). `pytest` pasa todos los tests sin
llamar a la API. Con el paso 12 la V1 está construida entera; el uso del día
a día está en [docs/uso-v1.md](docs/uso-v1.md). El paso 13 (a petición del
dueño) la deja corriendo en un entorno local aislado con Docker y una base de
datos de prueba: [docs/entorno-local.md](docs/entorno-local.md). El paso 14 (también a
petición del dueño) hace lo mismo sin Docker:
[docs/instalacion-nativa.md](docs/instalacion-nativa.md).
