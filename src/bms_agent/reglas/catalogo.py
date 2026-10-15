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
from . import aritmetica, anomalias, bancaria, calidad, identidad, iva, pagos, planning, unicidad
from .base import A, B, LEE_POR_FACTURA, R, Regla, por_factura

_P = EntradaPrioridad
_C = Calidad
_PROVEEDOR = AmbitoHallazgo.PROVEEDOR.value
_IMPORTACION = AmbitoHallazgo.IMPORTACION.value
_MOVIMIENTO = AmbitoHallazgo.MOVIMIENTO.value


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
    Regla("Z1", "Fuente pasada de frescura", "calidad", calidad.z1, calidad.LEE_Z1,
          severidad=A, calidad=_C.ANOMALIA.value, ambito=_IMPORTACION,
          descripcion="Lo último de una fuente es más viejo que su límite (banco 3 días "
                      "laborables, Exact y TRNSPRNT 7 días): lo que depende de ella queda sin "
                      "datos."),
    Regla("Z2", "Filas de importación rechazadas", "calidad", calidad.z2, calidad.LEE_Z2,
          severidad=R, calidad=_C.FALTANTE.value, ambito=_IMPORTACION,
          descripcion="La última importación de una fuente rechazó filas (o entera), o trae "
                      "una parte, un Objeto o un recurso que no existe: nada se crea solo."),
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
    Regla("G3", "Tarifa distinta por el mismo trabajo", "planning", planning.g3,
          planning.LEE_G3, solo_texto=planning.SOLO_TEXTO_G3, severidad=R, anulable=True,
          entrada_prioridad=_P.PLANNING.value,
          calidad=_C.ANOMALIA.value,
          descripcion="Sin tarifa pactada ni planning, contra el histórico: la misma "
                      "contraparte cobra otra tarifa por el mismo trabajo en el mismo Objeto."),
    # Relaciones y anomalias
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
