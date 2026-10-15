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
| [docs/instalacion-windows.md](docs/instalacion-windows.md) | **Si no has ejecutado esto nunca, empieza aquí.** Clave de API, instalación y primera prueba en Windows, paso a paso. |
| [docs/fase-0.md](docs/fase-0.md) | **Empieza aquí.** Puesta en marcha y uso del observador, y las decisiones de diseño del extractor. |
| [docs/validacion-facturas.md](docs/validacion-facturas.md) | Catálogo de reglas de validación de facturas de zzp'er: identidad, numeración, fechas, importes, régimen de IVA, datos de pago, contraste con el planning y riesgo laboral. |
| [docs/integracion-web.md](docs/integracion-web.md) | Cómo conecta un sitio propio con el agente: contrato de datos, servidor local y dónde puede vivir un botón de ejecutar. |
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
bms-agent objeto 7             # un Objeto y sus PO
bms-agent fuentes              # de cuándo es lo último de cada fuente (Z1)
bms-agent recalcular --diaria  # reglas y hallazgos al día (--simular: qué cambiaría)
bms-agent usuario crear Ana --rol administracion   # personas y sus permisos
bms-agent usuario token Ana    # su token personal (solo se guarda su hash)
bms-agent facturas             # la más urgente primero; `factura 12` da la ficha
bms-agent accion marcar_revisada --factura-id 12 --huella ... --token ...   # las órdenes
bms-agent politica cargar config/reglas.yaml --token ...   # admin: pesos, reglas o empresa, con su hash
bms-agent db verificar         # auditoría, anclas, evidencia y hash de cada original
bms-agent extract --estricta facturas/   # releer con otra versión: con almacén, deja candidatas
bms-agent score                # precisión contra respuestas escritas a mano
bms-agent coste                # qué ha costado cada pasada y versión; --estimar, la siguiente
bms-agent reextraer --abiertas --presupuesto 15   # volver a leer con el esquema v2, con techo
bms-agent score --comparar-versiones     # la puerta: la versión nueva contra la anterior
bms-agent reextraer --activar --token ...        # admin: lo releído pasa a vigente si pasa la puerta
bms-agent panel                # panel del historico (del almacén, con lo corregido)
bms-agent simulador            # simulador de tarifas, para decidir el modelo de precios
bms-agent export --tarifas config/tarifas.yaml   # datos en JSON, para un sitio propio
bms-agent serve                # servidor local en 127.0.0.1; la consola en /consola
bms-agent report               # ficha detallada de cada factura
```

## Estado

Fase 0 en marcha: el observador lee PDFs de una carpeta, los extrae a esquema
y mide la precisión contra respuestas escritas a mano. No tiene credenciales
de ningún sistema de la empresa. Ver [docs/fase-0.md](docs/fase-0.md).

La V1 se construye por pasos según [docs/v1/spec.md](docs/v1/spec.md), con el
resumen en castellano en [docs/diseno-v1.md](docs/diseno-v1.md). Lo hecho en
cada paso, y dónde se apartó de la especificación, está en
[docs/v1/registro.md](docs/v1/registro.md). `pytest` pasa 1630 tests sin
llamar a la API.
