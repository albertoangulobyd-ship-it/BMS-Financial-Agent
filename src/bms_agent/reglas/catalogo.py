"""El catalogo: cada regla del motor con su metadato, tal como lo fija spec.md §7.

Solo estan las reglas que ya se evaluan. Las demas del §7 llegan con su paso
(K y F7 con el banco, P con las ordenes de compra, G y V con el planning...),
y entran aqui cuando su evaluacion existe: una regla listada que no se evalua
daria por bueno lo que nadie ha mirado. El paso 5 trae las del maestro y del
registro de cuentas: A0, A2, A5, A7, A8, E1, E2, F0, F2-F6, F8, F9, U1, Q2,
Q3, Q4, Z1, Z2 y X1 tambien sobre las importaciones de maestros.

M2 tampoco esta en la tabla del §7: es "las ediciones de linea que no se
pueden casar se convierten en hallazgos" del §10 (paso 6), al lado de M1.

El paso 7 trae los pagos (K1-K8) y F7, y X1 tambien sobre los movimientos del
banco.

El paso 8 trae las ventas y las relaciones: V7 (facturacion doble a un
cliente, el caso de B2 y B3 en las ventas, que desde ahora solo miran las
compras), F10 (una venta con un IBAN que no es de BM Support BV), R1-R5 y M3.
M3 tampoco esta en el §7: es "un desacuerdo entre Exact y el PDF es una
discrepancia" de la puerta del paso 8, al lado de M1 y M2.

El paso 9 trae las ordenes de compra (P1-P10), las tarifas pactadas en G3 (que
sigue con el historico cuando no hay pactada, y sube a la version 2), G6 (un
recargo a su propia tarifa) y V4 (la tarifa de venta pactada).

El paso 10 trae el planning: G1, G2, G4, G5 y G7, la parte del planning de G6
(las horas de cada recargo contra las de sus turnos) y de B5 (un turno
conciliado con mas horas de compra de las que tiene), el escalon del planning
de G3 y V4 (la tarifa del turno), V1, V2, V3, V5, V6, V8 y V9, el caso de B5
en V7, y lo planificado de P7, P8 y P10. Sin ningun planning importado dan un
solo sin_datos cada una (turnos.sin_planning), nunca ok.

El paso 11 trae el BTW: C4 (una factura que no es, en un trimestre ya
presentado, lo que se declaro de ella), E0 (falta la informacion del IVA), E5
(lo facturado por un proveedor con KOR se acerca a su umbral) y E7 (un tipo de IVA
que no es de la lista, o una venta sin IVA a un cliente que no puede recibirla).

F0 no esta en la tabla del §7: es la tarea de atestacion de la decision 3
(lo heredado del primer maestro, de nivel atencion), escrita como regla para
que tenga su hallazgo, su excepcion y su prioridad como las demas.

De cada regla: que hace un fallo (B, R o A, y si cambia en las facturas de
venta), si se puede anular, si es pegajosa (su hallazgo no se cierra solo),
si anularla pide segunda firma, que aporta a la prioridad (§8) y que calidad
de dato marca. El orden es el del §7 y es el orden de los resultados.

`NO_ANULABLES` es la lista de la decision 12 (§3): ninguna politica, marca
ni catalogo la puede relajar, y la base la repite en el disparador
anulacion_solo_anulables.
"""

from __future__ import annotations

import hashlib
import json

from ..dominio import AmbitoHallazgo, Calidad, EntradaPrioridad
from . import (
    anomalias,
    aritmetica,
    bancaria,
    calidad,
    fechas,
    identidad,
    iva,
    ordenes,
    pagos,
    planning,
    relaciones,
    unicidad,
    venta,
)
from .base import A, B, LEE_POR_FACTURA, R, Regla, por_factura

_P = EntradaPrioridad
_C = Calidad
_PROVEEDOR = AmbitoHallazgo.PROVEEDOR.value
_IMPORTACION = AmbitoHallazgo.IMPORTACION.value
_MOVIMIENTO = AmbitoHallazgo.MOVIMIENTO.value
_PO = AmbitoHallazgo.ORDEN_COMPRA.value
_CLIENTE = AmbitoHallazgo.CLIENTE.value


def _de_factura(id_: str, funcion, lee: frozenset[str], **metadatos) -> Regla:
    return Regla(id=id_, evaluar=por_factura(id_, funcion), lee=lee | LEE_POR_FACTURA,
                 **metadatos)


CATALOGO: tuple[Regla, ...] = (
    # Datos e identidad
    _de_factura("Q1", calidad.q1, calidad.LEE_Q1,
                titulo="Campos obligatorios", familia="calidad", severidad=R,
                calidad=_C.FALTANTE.value,
                descripcion="Falta un campo obligatorio para el sentido de la factura: número, "
                            "contraparte, fecha, periodo, base, IVA o régimen, total. Bloquea "
                            "si falta el número, el total o la contraparte."),
    Regla("Q2", "Lectura dudosa sin verificar", "calidad", calidad.EVALUAR_Q["Q2"],
          calidad.LEE_Q2, severidad=R, calidad=_C.DUDOSO.value,
          descripcion="Un campo crítico se leyó con duda (low_confidence_fields o un literal "
                      "que no se pudo leer) y nadie lo ha verificado."),
    Regla("Q3", "Texto sospechoso en el documento", "calidad", calidad.EVALUAR_Q["Q3"],
          calidad.LEE_Q3, severidad=A, anulable=True, crea_excepcion=True,
          calidad=_C.ANOMALIA.value,
          descripcion="Las notas del documento traen texto dirigido a quien lo procesa (un "
                      "IBAN, cambiar datos, llamar): señal de un intento de inyección."),
    Regla("Q4", "Original no guardado", "calidad", calidad.EVALUAR_Q["Q4"], calidad.LEE_Q4,
          severidad=A, anulable=True, calidad=_C.FALTANTE.value,
          descripcion="El original del documento no está en el almacén."),
    Regla("X1", "Moneda", "calidad", calidad.x1_todo,
          calidad.LEE_X1 | LEE_POR_FACTURA | calidad.LEE_X1_IMPORTACIONES,
          severidad=B, pegajosa=True, calidad=_C.ANOMALIA.value,
          descripcion="La factura no está en euros: queda fuera de todos los totales. En un "
                      "maestro, una fila con un importe en otra moneda no entra y bloquea su "
                      "importación."),
    Regla("M2", "Edición manual sin casar", "calidad", calidad.EVALUAR_M2, calidad.LEE_M2,
          severidad=R, anulable=True, calidad=_C.DISCREPANCIA.value,
          descripcion="Una línea que una persona editó o excluyó no aparece en la extracción "
                      "vigente (no se pudo casar por su huella): se conserva tal cual y una "
                      "persona decide si sigue."),
    Regla("M3", "Exact y el documento no coinciden", "calidad", calidad.m3, calidad.LEE_M3,
          solo_texto=calidad.SOLO_TEXTO_M3, severidad=R, anulable=True,
          calidad=_C.DISCREPANCIA.value,
          descripcion="Una venta de Exact (o TRNSPRNT) y su PDF no dicen lo mismo (fecha, "
                      "base, IVA, total, tipo o periodo), o tienen el mismo número y no se "
                      "pudieron unir: cuenta la de Exact, y una persona mira la diferencia."),
    Regla("Z1", "Fuente pasada de frescura", "calidad", calidad.z1, calidad.LEE_Z1,
          severidad=A, calidad=_C.ANOMALIA.value, ambito=_IMPORTACION,
          descripcion="Lo último de una fuente es más viejo que su límite (banco 3 días "
                      "laborables, Exact y TRNSPRNT 7 días): lo que depende de ella queda sin "
                      "datos."),
    Regla("Z2", "Filas de importación rechazadas", "calidad", calidad.z2, calidad.LEE_Z2,
          severidad=R, calidad=_C.FALTANTE.value, ambito=_IMPORTACION,
          descripcion="La última importación de una fuente rechazó filas (o entera), o trae "
                      "una parte, un Objeto o un recurso que no existe (el planning los deja "
                      "entrar sin resolver): nada se crea solo."),
    Regla("A0", "Contraparte desconocida", "identidad", identidad.EVALUAR["A0"],
          identidad.LEE_A0, severidad=R, calidad=_C.FALTANTE.value,
          descripcion="Ningún proveedor o cliente del maestro coincide exactamente (btw-id, "
                      "KvK o alias confirmado), o coincide más de uno."),
    Regla("A2", "Distinto del maestro", "identidad", identidad.EVALUAR["A2"],
          identidad.LEE_A2 | identidad.SOLO_TEXTO_A2, solo_texto=identidad.SOLO_TEXTO_A2,
          severidad=R, anulable=True, calidad=_C.DISCREPANCIA.value,
          descripcion="El nombre, el KvK o el btw-id impresos no dicen lo mismo que el maestro "
                      "de la contraparte (un alias confirmado cuenta como su nombre)."),
    Regla("A5", "btw-id", "identidad", identidad.EVALUAR["A5"], identidad.LEE_A5,
          severidad=B, calidad=_C.FALTANTE.value,
          descripcion="Una compra sin btw-id que no dice KOR bloquea; un btw-id neerlandés que "
                      "no es NL + nueve cifras + B + dos cifras retiene."),
    Regla("A7", "Datos cambiados respecto a su historia", "identidad", identidad.EVALUAR["A7"],
          identidad.LEE_A7, severidad=R, anulable=True, pegajosa=True,
          calidad=_C.ANOMALIA.value,
          descripcion="Lo que imprime un proveedor cambia respecto a su factura anterior: "
                      "btw-id o KvK retienen, nombre o dirección avisan."),
    Regla("A8", "Destinatario", "identidad", identidad.EVALUAR["A8"], identidad.LEE_A8,
          severidad=R, anulable=True, calidad=_C.DISCREPANCIA.value,
          descripcion="La factura no va dirigida a BM Support BV (config/empresa.yaml); una "
                      "que llega por la vía de salida y no emite BM Support BV está mal "
                      "encaminada y bloquea."),
    # Duplicados
    Regla("B2", "Número de factura repetido", "unicidad", unicidad.b2, unicidad.LEE_B2,
          solo_texto=unicidad.SOLO_TEXTO,
          severidad=B, anulable=True, pegajosa=True, segunda_firma=True,
          entrada_prioridad=_P.DUPLICADO_EXACTO.value, calidad=_C.ANOMALIA.value,
          descripcion="La misma contraparte con el mismo número normalizado, sin fusionar "
                      "ni enlazar. Se cierra fusionando o enlazando."),
    Regla("B3", "Posible duplicado por contenido", "unicidad", unicidad.b3, unicidad.LEE_B3,
          solo_texto=unicidad.SOLO_TEXTO,
          severidad=R, anulable=True, pegajosa=True, entrada_prioridad=_P.DUPLICADO.value,
          calidad=_C.ANOMALIA.value,
          descripcion="Misma contraparte, el mismo total (0,01), como mucho 14 días entre "
                      "las dos, periodos compatibles y número distinto."),
    Regla("B4", "Periodo facturado dos veces", "unicidad", unicidad.b4, unicidad.LEE_B4,
          solo_texto=unicidad.SOLO_TEXTO,
          severidad=R, anulable=True, pegajosa=True, entrada_prioridad=_P.DUPLICADO.value,
          calidad=_C.ANOMALIA.value,
          descripcion="Periodos de cobro que se pisan, por Objeto cuando las líneas lo "
                      "nombran; sin las relaciones confirmadas ni los abonos."),
    Regla("B5", "Horas cobradas dos veces", "unicidad", unicidad.b5, unicidad.LEE_B5,
          severidad=R, anulable=True, pegajosa=True, entrada_prioridad=_P.DUPLICADO.value,
          calidad=_C.ANOMALIA.value,
          descripcion="Un turno del planning conciliado con más horas de compra de las que "
                      "tiene, desde dos o más facturas que no se explican entre sí (la parte "
                      "del planning de B5)."),
    Regla("V7", "Facturación doble", "unicidad", unicidad.v7,
          unicidad.LEE_V7 | unicidad.LEE_TURNOS_DE_MAS,
          solo_texto=unicidad.SOLO_TEXTO,
          severidad=R, anulable=True, pegajosa=True, entrada_prioridad=_P.DUPLICADO.value,
          calidad=_C.ANOMALIA.value,
          descripcion="En las ventas, el caso de B2 (el mismo número a la misma contraparte), "
                      "el de B3 (el mismo importe a pocos días, periodos compatibles y otro "
                      "número) o el de B5 (las horas de un turno cobradas desde dos facturas): "
                      "se le ha facturado dos veces."),
    # Fechas (paso 11)
    Regla("C4", "Trimestre del BTW ya presentado", "fechas", fechas.c4,
          fechas.LEE_C4 | fechas.SOLO_TEXTO_C4, solo_texto=fechas.SOLO_TEXTO_C4,
          severidad=A, anulable=True, entrada_prioridad=_P.IVA_BLANDA.value,
          calidad=_C.ANOMALIA.value,
          descripcion="La factura cae en un trimestre del BTW ya presentado y no es lo que se "
                      "declaró de ella: llegó después, cambió después o ya no cuenta allí. Va "
                      "a la lista del trimestre para el contable."),
    # Aritmetica e IVA
    _de_factura("D1", aritmetica.d1, aritmetica.LEE_D1,
                titulo="Desglose", familia="aritmetica", severidad=B, severidad_saliente=R,
                calidad=_C.FALTANTE.value,
                descripcion="El desglose está: líneas con cantidad, tarifa e importe, base, "
                            "total y, si se repercute IVA, tipo y cuota."),
    _de_factura("D2", aritmetica.d2, aritmetica.LEE_D2,
                titulo="Suma de líneas", familia="aritmetica", severidad=B, severidad_saliente=R,
                calidad=_C.DISCREPANCIA.value,
                descripcion="La suma de las líneas es la base (0,01 por línea más 0,02)."),
    _de_factura("D2b", aritmetica.d2b, aritmetica.LEE_D2B,
                titulo="Aritmética de línea", familia="aritmetica", severidad=B,
                severidad_saliente=R, anulable=True, calidad=_C.DISCREPANCIA.value,
                descripcion="Cantidad por tarifa es el importe de cada línea (0,01)."),
    _de_factura("D3", iva.d3, iva.LEE_D3,
                titulo="Cuota de IVA", familia="iva", severidad=B,
                entrada_prioridad=_P.IVA_DURA.value, calidad=_C.DISCREPANCIA.value,
                descripcion="La base por el tipo es la cuota, tipo a tipo (0,02)."),
    _de_factura("D4", aritmetica.d4, aritmetica.LEE_D4,
                titulo="Total", familia="aritmetica", severidad=B,
                calidad=_C.DISCREPANCIA.value,
                descripcion="La base más la cuota es el total (0,02)."),
    Regla("E0", "Falta información del IVA", "iva", iva.EVALUAR_E["E0"], iva.LEE_E0,
          severidad=R, entrada_prioridad=_P.IVA_BLANDA.value, calidad=_C.FALTANTE.value,
          descripcion="No se sabe cómo trata el IVA la factura, o con IVA normal le falta el "
                      "tipo o la cuota (en la cabecera o en una fila del desglose)."),
    Regla("E1", "Régimen distinto del maestro", "iva", iva.EVALUAR_E["E1"],
          iva.LEE_E1, severidad=R, anulable=True, entrada_prioridad=_P.IVA_BLANDA.value,
          calidad=_C.DISCREPANCIA.value,
          descripcion="El régimen de IVA de la factura no es el que el maestro tiene "
                      "registrado del proveedor."),
    Regla("E2", "Cambio de régimen", "iva", iva.EVALUAR_E["E2"],
          iva.LEE_E2, severidad=R, anulable=True, pegajosa=True,
          entrada_prioridad=_P.IVA_BLANDA.value, calidad=_C.ANOMALIA.value,
          descripcion="El régimen cambia respecto a la factura anterior del mismo proveedor."),
    _de_factura("E3", iva.e3, iva.LEE_E3,
                titulo="IVA con KOR", familia="iva", severidad=B,
                entrada_prioridad=_P.IVA_DURA.value, calidad=_C.DISCREPANCIA.value,
                descripcion="Con KOR la factura no repercute IVA."),
    _de_factura("E4", iva.e4, iva.LEE_E4,
                titulo="IVA trasladado", familia="iva", severidad=B,
                entrada_prioridad=_P.IVA_DURA.value, calidad=_C.DISCREPANCIA.value,
                descripcion="Con IVA trasladado no hay cuota y figura el btw-id del receptor."),
    Regla("E5", "Cerca del umbral de la KOR", "iva", iva.e5, iva.LEE_E5, severidad=A,
          anulable=True, entrada_prioridad=_P.IVA_BLANDA.value, calidad=_C.ANOMALIA.value,
          ambito=_PROVEEDOR,
          descripcion="Lo que un proveedor con KOR ha facturado este año a BM Support BV llega "
                      "al porcentaje de la política del umbral de la KOR (un indicio: el umbral "
                      "es de todo lo que factura)."),
    Regla("E7", "Tipo o tratamiento de IVA raro", "iva", iva.EVALUAR_E["E7"], iva.LEE_E7,
          severidad=R, anulable=True, entrada_prioridad=_P.IVA_BLANDA.value,
          calidad=_C.ANOMALIA.value,
          descripcion="Un tipo de IVA que no es de la lista de la política (0, 9 y 21), o una "
                      "venta con IVA trasladado o al 0 % a un cliente que el maestro no tiene "
                      "marcado para facturarle así."),
    # Datos de pago
    Regla("F0", "Cuentas heredadas sin atestar", "bancaria", bancaria.f0, bancaria.LEE_F0,
          severidad=R, pegajosa=True, entrada_prioridad=_P.IBAN.value, calidad=_C.DUDOSO.value,
          ambito=_IMPORTACION,
          descripcion="Las cuentas del primer maestro se aceptan como referencia pero nadie "
                      "las ha comprobado: una tarea, de nivel atención, para atestarlas."),
    _de_factura("F1", bancaria.f1, bancaria.LEE_F1,
                titulo="IBAN", familia="bancaria", severidad=B, pegajosa=True,
                entrada_prioridad=_P.IBAN.value, calidad=_C.DISCREPANCIA.value,
                descripcion="El IBAN impreso pasa el dígito de control módulo 97."),
    Regla("F2", "IBAN no pagable", "bancaria", bancaria.EVALUAR["F2"], bancaria.LEE_F2,
          severidad=B, pegajosa=True, entrada_prioridad=_P.IBAN.value,
          calidad=_C.DISCREPANCIA.value,
          descripcion="El IBAN de la factura no es una cuenta pagable de su proveedor: "
                      "verificada, atestada o heredada, en el último maestro de Exact y sin un "
                      "cambio por verificar."),
    Regla("F3", "IBAN nuevo o cambiado", "bancaria", bancaria.EVALUAR["F3"], bancaria.LEE_F3,
          severidad=B, pegajosa=True, entrada_prioridad=_P.IBAN.value,
          calidad=_C.DISCREPANCIA.value,
          descripcion="El IBAN de la factura es nuevo para el proveedor, o está rechazado: "
                      "verificación telefónica al número del maestro de antes del documento."),
    Regla("F4", "IBAN de un tercero o factoring", "bancaria", bancaria.EVALUAR["F4"],
          bancaria.LEE_F4, severidad=B, pegajosa=True, crea_excepcion=True,
          entrada_prioridad=_P.IBAN.value, calidad=_C.DISCREPANCIA.value,
          descripcion="El IBAN está registrado para otro titular, o la factura habla de "
                      "factoring, cesión o G-rekening. Bloquea y se escala."),
    Regla("F5", "Cuenta cambiada en el maestro", "bancaria", bancaria.f5, bancaria.LEE_F5,
          severidad=B, pegajosa=True, entrada_prioridad=_P.IBAN.value,
          calidad=_C.DISCREPANCIA.value, ambito=_PROVEEDOR,
          descripcion="Una cuenta añadida, cambiada o quitada en un maestro posterior al "
                      "primero, sin verificar por teléfono."),
    Regla("F6", "Exact y TRNSPRNT no coinciden", "bancaria", bancaria.f6, bancaria.LEE_F6,
          severidad=B, pegajosa=True, entrada_prioridad=_P.IBAN.value,
          calidad=_C.DISCREPANCIA.value, ambito=_PROVEEDOR,
          descripcion="Exact y TRNSPRNT dicen cuentas distintas del mismo proveedor."),
    Regla("F7", "Cargo a una cuenta no pagable", "bancaria", bancaria.f7, bancaria.LEE_F7,
          severidad=B, pegajosa=True, entrada_prioridad=_P.IBAN.value,
          calidad=_C.DISCREPANCIA.value, ambito=_MOVIMIENTO,
          descripcion="Un cargo del banco a un proveedor (casado con una factura suya, o a una "
                      "cuenta registrada para él) fue a una cuenta que no es pagable para él, "
                      "y no es un beneficiario conocido ni una cuenta propia."),
    Regla("F8", "Verificación que no vale", "bancaria", bancaria.f8, bancaria.LEE_F8,
          severidad=B, pegajosa=True, entrada_prioridad=_P.IBAN.value,
          calidad=_C.DISCREPANCIA.value, ambito=_PROVEEDOR,
          descripcion="La llamada no fue al teléfono del maestro de antes del documento, el "
                      "teléfono cambió dentro del enfriamiento o quien verificó no tenía el "
                      "permiso."),
    Regla("F9", "Teléfono de verificación cambiado", "bancaria", bancaria.f9, bancaria.LEE_F9,
          severidad=A, pegajosa=True, entrada_prioridad=_P.IBAN.value,
          calidad=_C.ANOMALIA.value, ambito=_PROVEEDOR,
          descripcion="El teléfono de verificación de un proveedor acaba de cambiar: empieza "
                      "el enfriamiento."),
    Regla("F10", "IBAN ajeno en una venta", "bancaria", bancaria.f10, bancaria.LEE_F10,
          severidad=R, pegajosa=True, entrada_prioridad=_P.IBAN.value,
          calidad=_C.DISCREPANCIA.value,
          descripcion="Una factura de venta lleva un IBAN que no es una cuenta de BM Support BV "
                      "(config/empresa.yaml): el cliente pagaría a otra cuenta."),
    # Pagos (paso 7)
    Regla("K1", "Vencida", "pagos", pagos.EVALUAR["K1"], pagos.LEE_K1, severidad=A,
          anulable=True, crea_excepcion=True, entrada_prioridad=_P.DIAS_VENCIDA.value,
          calidad=_C.ANOMALIA.value,
          descripcion="Sin pagar pasado su vencimiento: una compra desde el día siguiente, una "
                      "venta pasados los días de la política. Sin extractos que cubran desde su "
                      "fecha, sin datos."),
    Regla("K2", "Pagado distinto del saldo", "pagos", pagos.EVALUAR["K2"], pagos.LEE_K2,
          severidad=R, severidad_saliente=A, pegajosa=True, calidad=_C.DISCREPANCIA.value,
          descripcion="Lo confirmado no deja el saldo a cero: un pago parcial (la factura sigue "
                      "pendiente o vencida con lo que queda) o de más."),
    Regla("K3", "Pagada a mano sin rastro en el banco", "pagos", pagos.EVALUAR["K3"],
          pagos.LEE_K3, severidad=A, anulable=True, calidad=_C.FALTANTE.value,
          descripcion="Marcada pagada a mano y, pasados los días de la política, ningún "
                      "extracto trae el pago."),
    Regla("K4", "Pago doble", "pagos", pagos.k4, pagos.LEE_K4, severidad=B, pegajosa=True,
          entrada_prioridad=_P.DUPLICADO.value, calidad=_C.ANOMALIA.value,
          descripcion="Dos cargos a la misma cuenta, por el mismo importe y con la misma "
                      "referencia en pocos días, o una factura pagada de más con dos cargos."),
    Regla("K5", "Pagada estando Bloqueada", "pagos", pagos.EVALUAR["K5"], pagos.LEE_K5,
          severidad=R, pegajosa=True, calidad=_C.ANOMALIA.value,
          descripcion="Se pagó un día en que la factura tenía un hallazgo que bloquea, "
                      "pendiente y sin anular."),
    Regla("K6", "Extractos que no encadenan", "pagos", pagos.k6, pagos.LEE_K6, severidad=B,
          pegajosa=True, calidad=_C.FALTANTE.value, ambito=_IMPORTACION,
          descripcion="El saldo de apertura de un extracto no es el de cierre del anterior, o "
                      "falta un número: lo pagado desde ahí no se da por bueno."),
    Regla("K7", "Movimiento sin casar", "pagos", pagos.k7, pagos.LEE_K7, severidad=A,
          anulable=True, calidad=_C.FALTANTE.value, ambito=_MOVIMIENTO,
          descripcion="Un movimiento del banco que, pasados los días de la política, no está "
                      "casado con ninguna factura."),
    Regla("K8", "Banco y Exact no coinciden", "pagos", pagos.EVALUAR["K8"], pagos.LEE_K8,
          severidad=R, calidad=_C.DISCREPANCIA.value,
          descripcion="El banco y Exact dicen importes pagados distintos de la misma factura."),
    # Planning
    Regla("G1", "Sin turnos en el planning", "planning", planning.g1, planning.LEE_G1,
          severidad=R, anulable=True, segunda_firma=True, entrada_prioridad=_P.PLANNING.value,
          calidad=_C.FALTANTE.value,
          descripcion="Una compra sin ningún turno de su proveedor ni de sus personas en el "
                      "periodo facturado. Retiene; bloquea si el planning es obligatorio "
                      "(config/reglas.yaml). Anularla pide segunda firma."),
    Regla("G2", "Horas distintas de las validadas", "planning", planning.g2,
          planning.LEE_G2, severidad=R, anulable=True,
          entrada_prioridad=_P.PLANNING.value, calidad=_C.DISCREPANCIA.value,
          descripcion="Las horas facturadas contra las validadas del planning, en la celda más "
                      "fina que llevan los dos lados (persona y día, Objeto y día, Objeto y "
                      "semana, periodo), con 0,25 h por día de tolerancia. Turnos sin validar, "
                      "filas semanales que no se pueden partir o días que el planning no cubre: "
                      "sin datos."),
    Regla("G3", "Tarifa distinta de la pactada", "planning", planning.g3,
          planning.LEE_G3 | planning.LEE_TURNO_TARIFA,
          solo_texto=planning.SOLO_TEXTO_G3 | (planning.NO_EVIDENCIA_PACTADA & planning.LEE_G3),
          severidad=R, anulable=True, entrada_prioridad=_P.PLANNING.value,
          calidad=_C.ANOMALIA.value, version=2,
          descripcion="La tarifa de una línea de compra contra la pactada (de lo más concreto "
                      "a lo general: recurso y Objeto, Objeto, recurso, proveedor; el turno "
                      "tiene que ser el mismo): por encima retiene, y por encima del porcentaje "
                      "de la política bloquea. Sin pactada ni planning, contra el histórico: la "
                      "misma contraparte cobra otra tarifa por el mismo trabajo en el mismo "
                      "Objeto. Dos pactadas igual de concretas con precios distintos: sin datos "
                      "en la línea y la factura retenida, con su excepción. Con pactadas para "
                      "la línea pero ninguna de su unidad o su día (los imprime el proveedor): "
                      "sin datos y la factura retenida, no el histórico. Sin pactada, la tarifa "
                      "del turno en el planning, si todos los de su celda dicen la misma."),
    Regla("G4", "Objeto distinto del planning", "planning", planning.g4, planning.LEE_G4,
          solo_texto=planning.SOLO_TEXTO_G4, severidad=R, anulable=True,
          entrada_prioridad=_P.PLANNING.value, calidad=_C.DISCREPANCIA.value,
          descripcion="El Objeto de una línea de compra contra el planning: la persona o el "
                      "proveedor tienen esos días turnos en otro Objeto. Una línea sin Objeto "
                      "recibe la propuesta del planning, que confirma una persona."),
    Regla("G5", "Periodo distinto del planning", "planning", planning.g5, planning.LEE_G5,
          solo_texto=frozenset({"linea.orden"}), severidad=R, anulable=True,
          entrada_prioridad=_P.PLANNING.value, calidad=_C.DISCREPANCIA.value,
          descripcion="El periodo y la semana ISO de una compra contra el planning: la semana "
                      "impresa no es la de sus fechas, o lo facturado cae en días sin turnos y "
                      "ese trabajo está sin facturar en otra semana."),
    Regla("G6", "Recargo a otra tarifa que la suya", "planning", planning.g6, planning.LEE_G6,
          solo_texto=planning.SOLO_TEXTO_G6, severidad=R, anulable=True,
          entrada_prioridad=_P.PLANNING.value,
          calidad=_C.ANOMALIA.value,
          descripcion="Una línea de un recargo (noche, fin de semana, festivo) se cobra a su "
                      "propia tarifa pactada. Sin tarifa propia pero con otras pactadas para la "
                      "línea (la de día), sin datos y la factura retenida para que una persona "
                      "confirme el recargo; sin ninguna pactada, la mira G3 con el histórico. "
                      "Con el planning, las horas de cada recargo no pasan las de los turnos de "
                      "ese recargo."),
    Regla("G7", "El planning cambió tras conciliar", "planning", planning.g7,
          planning.LEE_G7, solo_texto=frozenset({"linea.orden"}), severidad=A,
          anulable=True, entrada_prioridad=_P.PLANNING.value, calidad=_C.ANOMALIA.value,
          descripcion="Una foto más nueva del planning cambia las horas ya conciliadas con "
                      "una compra (otras horas, turnos que ya no están o se cancelaron, turnos "
                      "nuevos)."),
    # Facturas de venta
    Regla("V1", "Horas facturadas distintas de las validadas", "venta", venta.v1, venta.LEE_V1,
          severidad=R, anulable=True, entrada_prioridad=_P.PLANNING.value,
          calidad=_C.DISCREPANCIA.value,
          descripcion="Las horas de una venta contra las validadas facturables del planning, "
                      "en la celda más fina de los dos lados (como G2)."),
    Regla("V2", "Objeto de la venta", "venta", venta.v2, venta.LEE_V2,
          solo_texto=venta.SOLO_TEXTO_V2, severidad=R, anulable=True,
          entrada_prioridad=_P.PLANNING.value, calidad=_C.DISCREPANCIA.value,
          descripcion="El Objeto de cada línea de venta existe, es del cliente facturado y "
                      "estaba activo; una línea sin Objeto retiene, con la propuesta del "
                      "planning si la hay."),
    Regla("V3", "Periodo de la venta distinto del planning", "venta", venta.v3, venta.LEE_V3,
          solo_texto=frozenset({"linea.orden"}), severidad=R, anulable=True,
          entrada_prioridad=_P.PLANNING.value, calidad=_C.DISCREPANCIA.value,
          descripcion="El periodo y la semana de lo facturado contra el planning (como G5)."),
    Regla("V4", "Tarifa de venta distinta de la pactada", "venta", venta.v4, venta.LEE_V4,
          solo_texto=venta.SOLO_TEXTO_V4, severidad=R, anulable=True,
          entrada_prioridad=_P.PLANNING.value,
          calidad=_C.DISCREPANCIA.value,
          descripcion="La tarifa de una línea de venta no es la de venta pactada (ni por encima "
                      "ni por debajo). Sin tarifa pactada, la del turno en el planning; sin "
                      "ninguna, sin datos."),
    Regla("V5", "Horas validadas sin facturar en lo facturado", "venta", venta.v5, venta.LEE_V5,
          severidad=R, anulable=True, entrada_prioridad=_P.FACTURACION_AUSENTE.value,
          calidad=_C.FALTANTE.value,
          descripcion="Dentro del Objeto y el periodo que cobra una venta, turnos validados "
                      "facturables que ninguna línea de venta cubre."),
    Regla("V6", "Trabajo sin facturar", "venta", venta.v6, venta.LEE_V6, severidad=R,
          anulable=True, entrada_prioridad=_P.TRABAJO_SIN_FACTURAR.value,
          calidad=_C.FALTANTE.value, ambito=_CLIENTE,
          descripcion="Turnos validados facturables que ninguna venta cubre, pasado el fin de "
                      "su periodo de facturación más sus días de gracia. Valorado a la tarifa "
                      "de venta pactada o, si no, marcado como estimado."),
    Regla("V8", "Periodo de facturación sin factura", "venta", venta.v8, venta.LEE_V8,
          severidad=R, anulable=True, entrada_prioridad=_P.FACTURACION_AUSENTE.value,
          calidad=_C.FALTANTE.value, ambito=_CLIENTE,
          descripcion="Un periodo del ciclo de facturación de un cliente u Objeto, con trabajo "
                      "en el planning, ya pasado con su gracia y sin ninguna factura."),
    Regla("V9", "El planning cambió tras facturar", "venta", venta.v9, venta.LEE_V9,
          solo_texto=frozenset({"linea.orden"}), severidad=R, anulable=True,
          entrada_prioridad=_P.PLANNING.value, calidad=_C.ANOMALIA.value,
          descripcion="Una foto más nueva del planning cambia lo que se facturó (regla 9 de "
                      "arquitectura.md): hace falta una corrección o un abono."),
    # Ordenes de compra (paso 9)
    Regla("P1", "PO no válida", "ordenes", ordenes.p1, ordenes.LEE_P1,
          solo_texto=ordenes.SOLO_TEXTO, severidad=R, anulable=True,
          entrada_prioridad=_P.LIMITE_PO.value, calidad=_C.DISCREPANCIA.value,
          descripcion="La PO a la que se imputa la factura está cerrada, o el trabajo cae fuera "
                      "de su vigencia (que sea de la parte y cubra el Objeto lo mira P3)."),
    Regla("P2", "Falta la PO", "ordenes", ordenes.p2, ordenes.LEE_P2, severidad=R, anulable=True,
          entrada_prioridad=_P.LIMITE_PO.value, calidad=_C.FALTANTE.value,
          descripcion="Una venta sin PO donde el Objeto (o, si no lo dice, el cliente) la pide. "
                      "Un abono no: toma la PO de la factura que abona."),
    Regla("P3", "PO desconocida o de otro", "ordenes", ordenes.p3, ordenes.LEE_P3,
          solo_texto=ordenes.SOLO_TEXTO, severidad=R, anulable=True,
          entrada_prioridad=_P.LIMITE_PO.value, calidad=_C.DISCREPANCIA.value,
          descripcion="La PO que dice la factura no está registrada, es de otra parte o no "
                      "cubre el Objeto de la línea; o la factura imprime varias PO y una "
                      "imputación no va a ninguna (una persona decide con imputar_po)."),
    Regla("P4", "Factura por encima de lo que queda", "ordenes", ordenes.p4, ordenes.LEE_CARGOS,
          solo_texto=ordenes.SOLO_TEXTO, severidad=R, anulable=True, pegajosa=True,
          entrada_prioridad=_P.LIMITE_PO_DURO.value, calidad=_C.ANOMALIA.value,
          descripcion="La factura carga a la PO más de lo que le quedaba antes de ella, sin IVA: "
                      "por fecha de factura y por id, o por orden de llegada (una fecha "
                      "atrasada no la libra)."),
    Regla("P5", "PO casi consumida", "ordenes", ordenes.p5, ordenes.LEE_P5,
          solo_texto=ordenes.SOLO_TEXTO, severidad=A, entrada_prioridad=_P.LIMITE_PO.value,
          calidad=_C.ANOMALIA.value, ambito=_PO,
          descripcion="La PO lleva consumido el porcentaje de la política (80 %) o más."),
    Regla("P6", "PO consumida y se sigue facturando", "ordenes", ordenes.p6, ordenes.LEE_CARGOS,
          solo_texto=ordenes.SOLO_TEXTO, severidad=R, anulable=True,
          entrada_prioridad=_P.LIMITE_PO_DURO.value, calidad=_C.ANOMALIA.value,
          descripcion="La PO ya estaba consumida entera antes de la factura (por fecha o por "
                      "llegada), y la factura le carga más."),
    Regla("P7", "PO a punto de caducar", "ordenes", ordenes.p7, ordenes.LEE_P7,
          solo_texto=ordenes.SOLO_TEXTO, severidad=A, anulable=True,
          entrada_prioridad=_P.CADUCIDAD_PO.value, calidad=_C.ANOMALIA.value, ambito=_PO,
          descripcion="La PO caduca dentro de los días de la política (30) con valor por "
                      "consumir. Ya caducada, retiene si el planning tiene trabajo después de "
                      "su fin."),
    Regla("P8", "Planificado por encima de lo que queda", "ordenes", ordenes.p8, ordenes.LEE_P8,
          solo_texto=ordenes.SOLO_TEXTO, severidad=A, entrada_prioridad=_P.LIMITE_PO.value,
          calidad=_C.ANOMALIA.value, ambito=_PO,
          descripcion="El trabajo planificado (después de hoy) por la tarifa pactada, o la del "
                      "turno, pasa lo que queda de la PO."),
    Regla("P9", "PO que se agota antes de tiempo", "ordenes", ordenes.p9, ordenes.LEE_P9,
          solo_texto=ordenes.SOLO_TEXTO, severidad=A, entrada_prioridad=_P.LIMITE_PO.value,
          calidad=_C.ANOMALIA.value, ambito=_PO,
          descripcion="Al ritmo de las últimas semanas (8), la PO se agota antes de los días de "
                      "margen (14) de su fin."),
    Regla("P10", "Esperado por encima de la PO", "ordenes", ordenes.p10, ordenes.LEE_P10,
          solo_texto=ordenes.SOLO_TEXTO, severidad=R, anulable=True,
          entrada_prioridad=_P.LIMITE_PO_DURO.value, calidad=_C.ANOMALIA.value, ambito=_PO,
          descripcion="Lo facturado más lo trabajado sin facturar más lo planificado pasa el "
                      "valor de la PO; retiene también las facturas que le cargan desde ahí."),
    # Relaciones y anomalias
    Regla("R1", "Factura nombrada que no está", "relaciones", relaciones.EVALUAR["R1"],
          relaciones.LEE_R1, severidad=R, anulable=True, calidad=_C.FALTANTE.value,
          descripcion="Un abono o una corrección nombra una factura de la misma contraparte que "
                      "no está en el almacén (o que está repetida)."),
    Regla("R2", "Abonos por encima de la original", "relaciones", relaciones.EVALUAR["R2"],
          relaciones.LEE_R2, solo_texto=relaciones.SOLO_TEXTO, severidad=R, pegajosa=True,
          calidad=_C.ANOMALIA.value,
          descripcion="Los abonos confirmados le quitan a una factura más de lo que vale, o un "
                      "abono se aplica por más de lo que vale."),
    Regla("R3", "Original y sustituta a la vez", "relaciones", relaciones.EVALUAR["R3"],
          relaciones.LEE_R3, solo_texto=relaciones.SOLO_TEXTO, severidad=B, pegajosa=True,
          entrada_prioridad=_P.DUPLICADO.value, calidad=_C.ANOMALIA.value,
          descripcion="La original y la que la sustituye (o corrige) están las dos pendientes "
                      "(se pagaría el mismo trabajo dos veces) o las dos pagadas."),
    Regla("R4", "Abono sin relación", "relaciones", relaciones.EVALUAR["R4"], relaciones.LEE_R4,
          severidad=A, calidad=_C.FALTANTE.value,
          descripcion="Un abono sin ninguna relación confirmada que diga a qué factura abona."),
    Regla("R5", "Relación por confirmar", "relaciones", relaciones.EVALUAR["R5"],
          relaciones.LEE_R5, solo_texto=relaciones.SOLO_TEXTO, severidad=A,
          calidad=_C.DUDOSO.value,
          descripcion="La extracción o Exact proponen una relación entre dos facturas: hasta "
                      "que una persona la confirma no mueve saldos, IVA ni duplicados."),
    Regla("U1", "Importe inusual", "anomalias", anomalias.EVALUAR_U1, anomalias.LEE_U1,
          severidad=A, anulable=True, crea_excepcion=True, calidad=_C.ANOMALIA.value,
          descripcion="La base se sale de lo habitual de la contraparte (mediana y MAD de sus "
                      "facturas anteriores; con menos de tres, sin datos)."),
)

POR_ID: dict[str, Regla] = {regla.id: regla for regla in CATALOGO}

# Decision 12 (§3): lo que no se anula nunca. Las D, solo en las entrantes.
NO_ANULABLES = frozenset({"X1", "E3", "E4", "K2", "K4", "K6", "R2", "R3"})
NO_ANULABLES_ENTRANTES = frozenset({"D2", "D3", "D4", "D6"})
FAMILIAS_NO_ANULABLES = ("F",)


def nunca_anulable(regla_id: str, sentido: str | None) -> bool:
    """La lista dura de la decision 12, que ningun catalogo ni politica relaja."""
    if regla_id in NO_ANULABLES or regla_id.startswith(FAMILIAS_NO_ANULABLES):
        return True
    return regla_id in NO_ANULABLES_ENTRANTES and sentido != "saliente"


def regla(regla_id: str) -> Regla:
    try:
        return POR_ID[regla_id]
    except KeyError:
        raise KeyError(f"{regla_id} no es una regla del catalogo") from None


def sha256(reglas: tuple[Regla, ...] = CATALOGO) -> str:
    """El hash del catalogo que se evaluo (va en ejecucion_reglas)."""
    texto = json.dumps([r.metadatos() for r in reglas], sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()
