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
| [docs/mcp-setup.md](docs/mcp-setup.md) | Registro del servidor MCP de Zapier y por qué queda fuera del camino que toca dinero. |

## Estado

Propuesta de arquitectura. Sin código todavía. La fase 0 (observador, cero
escrituras) es el siguiente paso.
