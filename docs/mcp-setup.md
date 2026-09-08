# Servidor MCP de Zapier

## Registro

Zapier expone un servidor MCP por HTTP. Para registrarlo en Claude Code a nivel
de usuario, disponible en todos los proyectos:

```bash
claude mcp add --scope user --transport http "Zapier-MCP" https://mcp.zapier.com/api/v1/connect
```

Después hay que reiniciar Claude Code, porque los servidores MCP se cargan al
arrancar. Comprobación y autenticación:

```bash
claude mcp get Zapier-MCP     # muestra la configuración y el estado
claude mcp list               # comprueba la salud de todos los servidores
```

Dentro de una sesión, `/mcp` abre el panel donde se autentica el servidor. Abre
una pestaña de Zapier para iniciar sesión y aprobar el acceso.

En la web de Claude el registro es distinto: Ajustes, Conectores, Añadir
conector personalizado, con la misma URL. Un `claude mcp add` ejecutado dentro de
una sesión remota solo afecta al contenedor de esa sesión, que es efímero.

## Por qué queda fuera del camino del dinero

Zapier MCP sirve bien para el pegamento de bajo riesgo: avisar en Teams o Slack,
crear una tarea, mandar un recordatorio. Para la lectura del buzón, la escritura
en Exact o la generación de ficheros de pago es una mala elección, por tres
razones:

1. **Concentra credenciales en un tercero.** Los tokens del buzón de
   administración y de Exact quedan en manos de un proveedor externo, con un
   alcance que no se controla campo a campo.
2. **La superficie de acciones es amplia y cambiante.** Al modelo se le expone
   un catálogo de miles de acciones posibles. Lo que necesita este sistema es lo
   contrario: un conjunto pequeño, tipado y auditable de operaciones permitidas.
3. **No aporta lo que hace defendible el sistema.** Sin validación tipada, sin
   idempotencia por hash y sin registro inmutable, no se puede justificar un
   asiento ni un pago ante el contador ni ante el fisco.

La decisión, recogida en [arquitectura.md](arquitectura.md): adaptadores propios
y estrechos para correo, Exact, planning y SEPA. Zapier, si se mantiene, solo
para notificaciones, fuera del camino que toca dinero.
