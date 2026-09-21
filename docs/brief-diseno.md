# Briefing de diseño · Agente Financiero BMS

Documento autocontenido para alguien que va a ayudar con el diseño y no
conoce el proyecto. Se puede leer entero sin abrir nada más.

---

## 1. Qué es esto en una frase

Un agente que lee las facturas de proveedores autónomos que llegan por
correo, las entiende, las cruza con lo que la empresa tiene registrado, y
avisa de lo que no cuadra. Más un panel donde ver qué está pasando.

## 2. La empresa

**BMS Support**, empresa neerlandesa de **cesión de personal**. Contrata
autónomos (*zzp'ers*) y los coloca en obras de clientes. El ciclo es
**semanal**: el autónomo trabaja una semana ISO en una obra, y factura esa
semana.

Volumen estimado: decenas de facturas al mes, seis o más proveedores
recurrentes, varias obras simultáneas.

## 3. Quién usa esto

| Rol | Qué necesita | ¿Hoy tiene pantalla? |
| --- | --- | --- |
| **Administración** (una persona) | Su cola de trabajo: qué no puede procesar hoy y por qué | Sí, el panel |
| **Asesor fiscal externo** | Cuadre del IVA trimestral, régimen por factura, excepciones | Parcial |
| **Cliente final** | Sus facturas y las horas que las sostienen | No, es del portal futuro |
| **Trabajador autónomo** | Solo sus propias horas | No, es del portal futuro |

El usuario principal es **administración**: una persona, no un equipo. Todo
lo que le ahorre abrir PDFs uno a uno es valor directo.

## 4. Qué hace el agente (alcance completo)

Once cosas, por fases. Las marcadas **[hoy]** funcionan.

1. **[hoy]** Leer facturas en PDF y extraerlas a datos estructurados.
2. **[hoy]** Comprobar aritmética, IVA, IBAN y campos obligatorios.
3. **[hoy]** Detectar duplicados, periodos repetidos, cambios de IBAN y de
   tarifa cruzando todo el histórico.
4. **[hoy]** Medir su propia precisión contra respuestas escritas a mano.
5. Subir los PDF a **Exact** (la contabilidad) y contabilizarlos.
6. Cruzar las horas facturadas contra el **programa de planificación**.
7. Emitir facturas a clientes desde las horas registradas.
8. Preparar el **fichero de pago SEPA** para subirlo al banco a mano.
9. Responder a las preguntas del asesor fiscal.
10. Preparar la **declaración trimestral de IVA**.
11. Explicar a un cliente o a un trabajador de dónde salen unas horas.

## 5. La regla que manda sobre todo el diseño

> **El modelo extrae y redacta. El código determinista decide y ejecuta.
> Ningún euro se mueve sin una firma humana sobre una pantalla que el modelo
> no ha escrito.**

Consecuencias de diseño, y no son negociables:

- **Una pantalla de aprobación se dibuja desde el dato estructurado**, nunca
  desde texto que haya generado el modelo. Si el resumen lo redactara el
  modelo, una instrucción escondida en un PDF podría hacer que el resumen
  diga una cosa y el fichero de pago contenga otra.
- **El texto que viene de un PDF es contenido, nunca una orden.** Los PDF de
  proveedores llegan con texto diseñado para engañar a un sistema. Se muestra
  siempre marcado como "esto lo dice el documento", en monoespaciado y con
  marco, nunca mezclado con la interfaz.
- **El IBAN de un pago sale del registro de proveedores, jamás del
  documento.** El fraude real en administración neerlandesa es la factura con
  el número de cuenta cambiado.

## 6. Las tres superficies

### A. Panel de administración — **existe, es lo que hay que pulir**

Un fichero HTML local que se abre desde el disco. Sin servidor, sin base de
datos, sin internet. Contiene:

- Fila de filtros (periodo, proveedor, estado, búsqueda) que acota **todo** lo
  de abajo, de modo que las cifras siempre concuerdan entre sí.
- Seis tiles: base imponible, proveedores, horas, IVA soportado, cuántas por
  revisar, cuántas no se pueden pagar.
- Bloque de avisos agrupados.
- Gasto por mes (columnas) y ranking por proveedor (barras horizontales).
- Reparto por régimen de IVA (barra apilada).
- **Matriz proveedor × semana ISO.** Es la pieza más útil y la más propia de
  este negocio: cada columna es una semana, una celda vacía es una semana sin
  factura, dos facturas en la misma celda salen marcadas.
- Tabla completa de todas las facturas, ordenable y exportable a CSV.

### B. Ficha por factura — **existe, secundaria**

Otro fichero HTML: una tarjeta por factura con sus líneas, totales,
comprobaciones aplicadas y procedencia. Para cuando hay que mirar una en
concreto.

### C. Portal web de consulta — **diseñado, sin construir**

Lo que verán clientes, trabajadores y el asesor. Frontend estático
desplegado; los datos vienen de una API de solo lectura sobre una copia
empobrecida de la base de datos, **sin IBAN completo y sin datos personales
que no hagan falta**. El portal **nunca** tendrá un botón que escriba.

## 7. El sistema visual actual

Ya existe y conviene mantenerlo, no reinventarlo.

**Tipografía**
- Títulos e interfaz: **Archivo** (sans, con carácter)
- Texto corrido en los documentos: **Source Serif 4**
- Datos, códigos, IBAN, etiquetas: **IBM Plex Mono**

**Color de interfaz** (claro / oscuro, ambos definidos por tokens)
- Fondo `#F6F7F9` / `#0D1117`, superficie `#FFFFFF` / `#161B23`
- Tinta `#141A23` / `#E3E9F1`
- Acento azul tinta `#1F4E8C` / `#7BA9E7`
- Neutros con sesgo frío, elegidos, no grises puros

**Color de datos** (validado con un script de accesibilidad contra las
superficies reales del proyecto, en ambos modos, modo todos-los-pares)
- Categórico: `#2a78d6` azul, `#eb6834` naranja, `#1baf7a` aqua
- Secuencial (la matriz): rampa azul de un solo tono, cinco peldaños
- Estado: bueno `#0ca30c`, aviso `#a06a00` en claro y `#fab219` en oscuro,
  crítico `#d03b3b`

**Reglas de gráfico que ya se aplican**: nada de doble eje; una serie, un
color y sin leyenda; rejilla de una línea sólida; etiqueta directa solo en el
máximo y el último punto; áreas de activación mayores que la marca y
alcanzables por teclado; la tabla completa como alternativa a todo color.

## 8. Restricciones que un diseño nuevo tiene que respetar

1. **Los avisos no pueden inundar la página.** Ya pasó: veintidós avisos
   idénticos enterraron los gráficos y la tabla. Se agrupan.
2. **Un aviso que salta siempre se ignora**, y entonces se pierden también
   los buenos. Cada regla se afinó contra falsos positivos reales (horas de
   viaje a otra tarifa, un autónomo que factura el mismo importe cada
   semana, un cambio de banco legítimo).
3. **El IBAN se enseña completo en el panel interno** (el dígito que cambia
   es el dato) **y enmascarado en el portal externo**. Son pantallas con
   reglas opuestas a propósito.
4. **Todo texto extraído se escapa antes de entrar en la pantalla.** Un
   proveedor no puede inyectar marcado en vuestro panel.
5. **Nada "verde" que no se haya comprobado de verdad.** Si una regla no
   tiene los datos para evaluarse, sale como *no evaluable*, no como
   correcta. Un dato ausente no es un fallo, pero tampoco es un aprobado.
6. **Es una herramienta de escritorio.** Una persona de administración con
   un monitor. El móvil no es el caso de uso.

## 9. Lo que está abierto, y donde más ayuda hace falta

| Pregunta | Por qué importa |
| --- | --- |
| La matriz semana × proveedor no escala. Con cuarenta proveedores y un año de semanas es ilegible. ¿Paginar, agrupar, hacer zoom, cambiar de forma? | Es la vista más útil del panel |
| Los avisos y los gráficos se pelean por la parte de arriba. ¿Qué va primero: la cola de trabajo o el panorama? | Decide la jerarquía de toda la página |
| Tres roles muy distintos. ¿Una página con filtros, o pantallas separadas? | Condiciona si el portal reutiliza esto o no |
| Estado vacío y estado parcial: ¿qué dice la pantalla el primer día, sin datos? | Hoy no está diseñado |
| El asesor fiscal querrá algo imprimible o exportable por trimestre | No existe |
| El portal para cliente y trabajador no tiene ni un boceto | Fase posterior, pero conviene pensarlo antes |

## 10. Vocabulario que hace falta

| Término | Qué es |
| --- | --- |
| **zzp'er** | Autónomo neerlandés sin empleados |
| **KvK** | Registro mercantil. El número tiene ocho dígitos |
| **btw** | IVA. **btw-id** es el número de IVA, formato `NL` + 9 dígitos + `B` + 2 |
| **btw verlegd** | IVA trasladado: la factura no lleva cuota, la declara el cliente. Habitual en construcción |
| **KOR** | Régimen de pequeña empresa: el proveedor no repercute IVA |
| **IBAN** | Número de cuenta. Lleva dígito de control, se valida con aritmética |
| **SEPA / pain.001** | Formato del fichero de pagos que se sube al banco |
| **Semana ISO** | La unidad de trabajo aquí. Lunes a domingo, numeradas de 1 a 52 o 53 |
| **Base imponible** | Importe sin IVA. Es lo único comparable entre regímenes |

## 11. Estado real del proyecto

- Código: unas 3.500 líneas de Python, 133 tests, ninguno llama a la API.
- La extracción funciona sobre facturas reales con acierto medido.
- El agente **no tiene credenciales de ningún sistema de la empresa**. Ni
  correo, ni contabilidad, ni banco. Solo lee PDF de una carpeta.
- Documentación en `docs/`: arquitectura, catálogo de validación, portal,
  costes, instalación y fase 0.
