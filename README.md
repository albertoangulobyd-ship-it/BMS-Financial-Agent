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
| [docs/fase-0.md](docs/fase-0.md) | **Empieza aquí.** Puesta en marcha y uso del observador, y las decisiones de diseño del extractor. |
| [docs/validacion-facturas.md](docs/validacion-facturas.md) | Catálogo de reglas de validación de facturas de zzp'er: identidad, numeración, fechas, importes, régimen de IVA, datos de pago, contraste con el planning y riesgo laboral. |
| [docs/mcp-setup.md](docs/mcp-setup.md) | Registro del servidor MCP de Zapier y por qué queda fuera del camino que toca dinero. |

## Puesta en marcha

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest

export ANTHROPIC_API_KEY=sk-ant-...
bms-agent extract facturas/    # deja los PDF ahí primero
bms-agent score
```

## Estado

Fase 0 en marcha: el observador lee PDFs de una carpeta, los extrae a esquema
y mide la precisión contra respuestas escritas a mano. No tiene credenciales
de ningún sistema de la empresa. Ver [docs/fase-0.md](docs/fase-0.md).
