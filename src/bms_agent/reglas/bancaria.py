"""Reglas de datos de pago: F1 (el digito de control) y, desde el paso 5, el registro de cuentas.

El pago se construye siempre con el IBAN del maestro, nunca con el del
documento (regla 1 de arquitectura.md): estas reglas no eligen el numero,
solo detectan la discrepancia. Ninguna se puede anular y todas son
pegajosas: un IBAN raro que deja de verse no es un problema resuelto.

Paso 5: F0 (lo heredado sin atestar), F2 (el IBAN de la factura no es
pagable), F3 (es nuevo o esta rechazado), F4 (es de otro, o hay factoring),
F5 (el maestro cambio una cuenta despues del primero), F6 (Exact y TRNSPRNT
no coinciden), F8 (una verificacion que no cuenta) y F9 (el telefono de
verificacion acaba de cambiar). F7 y F10 llegan con el banco (paso 7) y las
ventas (paso 8).
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .base import (
    ENTRANTE,
    FALLO,
    LEE_CADUCIDAD,
    LEE_EN_JUEGO,
    LEE_LOTES,
    OK,
    SIN_DATOS,
    CambioTelefono,
    Comprobacion,
    Cuenta,
    EventoCuenta,
    Factura,
    Instantanea,
    Objetivo,
    Politica,
    Resultado,
    caducada,
    fallo,
    importado,
    resultado_de,
    sin_datos,
    solo_objeciones,
)
from .normas import normalizar_iban


# A=10 ... Z=35 (ISO 13616), como tabla de str.translate: una por IBAN y
# no una conversion por letra, que en cinco mil facturas se notaba.
_LETRAS_A_CIFRAS = {ord(c): str(int(c, 36)) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}


def validar_iban(iban: str | None) -> bool:
    """Digito de control modulo 97 (ISO 13616).

    Aritmetica pura, sin sistemas externos. Un IBAN que no pasa esta
    comprobacion esta mal transcrito o es inventado, y en los dos casos el
    pago no puede salir.
    """
    texto = "".join(str(iban or "").split()).upper()
    if not (15 <= len(texto) <= 34) or not texto[:2].isalpha() or not texto[2:4].isdigit():
        return False
    if not (texto.isascii() and texto.isalnum()):      # una "Ñ" es alfanumerica, no de un IBAN
        return False
    movido = texto[4:] + texto[:4]
    return int(movido.translate(_LETRAS_A_CIFRAS)) % 97 == 1


def iban(texto: str | None) -> Comprobacion:
    """F1: el IBAN impreso es sintacticamente valido."""
    if not texto:
        return Comprobacion(SIN_DATOS, "La factura no lleva IBAN.")
    limpio = "".join(str(texto).split()).upper()
    if validar_iban(limpio):
        return Comprobacion(OK, f"{limpio} pasa el digito de control.")
    return Comprobacion(FALLO, f"{limpio} no pasa el digito de control modulo 97.")


def f1(factura: Factura, _politica: Politica) -> list[Resultado]:
    comprobacion = iban(factura.iban_doc)
    objetivos = ((Objetivo("factura", factura.id, "iban_doc"),)
                 if comprobacion.resultado == FALLO else ())
    limpio = "".join(str(factura.iban_doc or "").split()).upper() or None
    return [resultado_de("F1", factura, comprobacion, valores={"iban": limpio},
                         objetivos=objetivos)]


LEE_F1 = frozenset({"factura.iban_doc"})


# ------------------------------------------------------------ el registro de cuentas
#
# El estado de una cuenta no esta en su fila: lo dicen sus eventos (el
# maestro que la trae o deja de traerla, y lo que decide una persona). Estas
# funciones lo leen de la instantanea, sin la base, y las usan las reglas F y
# las ordenes de IBAN (para decir en el momento si una verificacion cuenta).

DECISIONES = frozenset({"verificada", "rechazada", "atestada", "retirada"})
VISTO_EXACT = "visto_en_exact"
AUSENTE_EXACT = "ausente_en_exact"
HEREDADA = "heredada"
REGISTRADA = "registrada"


def _instante(texto: str) -> datetime:
    return datetime.fromisoformat(texto)


def telefono_antes_de(telefonos: Sequence[CambioTelefono], instante: str) -> CambioTelefono | None:
    """El valor del telefono de verificacion que tenia el maestro justo antes de un instante."""
    anteriores = [t for t in telefonos if t.en < instante]
    return anteriores[-1] if anteriores else None


def cambio_reciente(telefonos: Sequence[CambioTelefono], instante: str,
                    dias: int) -> CambioTelefono | None:
    """El ultimo cambio de telefono (no el alta) en los `dias` anteriores a un instante."""
    limite = _instante(instante) - timedelta(days=dias)
    recientes = [t for t in telefonos if not t.alta and t.en <= instante
                 and _instante(t.en) > limite]
    return recientes[-1] if recientes else None


def eficacia(evento: EventoCuenta, telefonos: Sequence[CambioTelefono],
             politica: Politica) -> str | None:
    """Por que una verificacion por telefono no cuenta (F8), o None si cuenta.

    El numero llamado tiene que ser el que tenia el maestro antes de que
    llegara lo que motivo la verificacion (el documento con el IBAN nuevo, o
    la importacion que lo cambio): un estafador que cambia el IBAN y el
    telefono a la vez no puede hacer que se le llame a el. Y tras un cambio
    del telefono hay un enfriamiento: ninguna verificacion por telefono vale
    hasta que pasa.
    """
    if not evento.con_permiso:
        return "quien la hizo no tenia confirmar_iban"
    referencia = evento.llegada or evento.en
    antes = telefono_antes_de(telefonos, referencia)
    if antes is None or antes.valor is None:
        return "el maestro no tenia telefono de verificacion antes del documento que la motivo"
    if evento.telefono_usado != antes.valor:
        return ("el numero llamado no es el que tenia el maestro antes del documento que la "
                "motivo")
    reciente = cambio_reciente(telefonos, evento.en, politica.enfriamiento_telefono_dias)
    if reciente is not None:
        dias = (_instante(evento.en) - _instante(reciente.en)).days
        return (f"el telefono de verificacion cambio hace {dias} días: no vale ninguna "
                f"verificacion hasta {politica.enfriamiento_telefono_dias} días despues")
    return None


@dataclass(frozen=True)
class EstadoCuenta:
    """Lo que dicen los eventos de una cuenta, con la politica de hoy.

    `estado`: la ultima decision que cuenta de una persona (verificada,
    atestada, rechazada, retirada) o, sin ninguna, heredada (llego con el
    primer maestro) o registrada (sin verificar). `en_exact`: si la trae la
    ultima importacion de Exact que la miro (None si nunca la miro ninguna).
    `cambios`: lo que cambio en el maestro despues del primero y nadie ha
    verificado ni rechazado (F5), como (tipo, id del evento, importacion).
    `ineficaz`: la ultima verificacion, si no cuenta y no hay otra decision
    despues (F8), con el motivo.
    """

    estado: str
    en_exact: bool | None
    cambios: tuple[tuple[str, int, int | None], ...]
    ineficaz: tuple[EventoCuenta, str] | None
    baseline: int | None
    pagable: bool


def estado_cuenta(cuenta: Cuenta, telefonos: Sequence[CambioTelefono],
                  politica: Politica) -> EstadoCuenta:
    """El estado de una cuenta (decision 3): heredada, verificada, atestada, rechazada...

    Pagable es: verificada, atestada o heredada (heredada no, con
    iban_solo_verificadas), presente en la ultima importacion de Exact que la
    miro y sin un cambio del maestro pendiente de verificar.
    """
    baseline = next((e.importacion_id for e in cuenta.eventos if e.tipo == "baseline"), None)
    decision: str | None = None
    en_exact: bool | None = None
    cambios: list[tuple[str, int, int | None]] = []
    ineficaz: tuple[EventoCuenta, str] | None = None
    vista_antes = False
    for evento in cuenta.eventos:
        if evento.tipo in DECISIONES:
            # Una verificacion que no cuenta (tambien la de quien no tenia el
            # permiso) es F8; cualquier otra decision sin permiso no existe.
            if evento.tipo == "verificada":
                motivo = eficacia(evento, telefonos, politica)
                if motivo is not None:
                    ineficaz = (evento, motivo)
                    continue
            elif not evento.con_permiso:
                continue
            decision, ineficaz = evento.tipo, None
            if evento.tipo in ("verificada", "rechazada"):
                cambios = []
        elif evento.tipo in (VISTO_EXACT, AUSENTE_EXACT):
            if evento.tipo == AUSENTE_EXACT:
                cambios.append(("retirada_del_maestro", evento.id, evento.importacion_id))
            elif not vista_antes and evento.importacion_id != baseline and decision != "verificada":
                cambios.append(("anadida_al_maestro", evento.id, evento.importacion_id))
            elif en_exact is False and decision != "verificada":
                cambios.append(("vuelve_al_maestro", evento.id, evento.importacion_id))
            vista_antes = vista_antes or evento.tipo == VISTO_EXACT
            en_exact = evento.tipo == VISTO_EXACT
    estado = decision or (HEREDADA if baseline is not None else REGISTRADA)
    aceptado = {"verificada", "atestada"} | (
        set() if politica.iban_solo_verificadas else {HEREDADA})
    pagable = bool(en_exact) and not cambios and estado in aceptado
    return EstadoCuenta(estado, en_exact, tuple(cambios), ineficaz, baseline, pagable)


# ------------------------------------------------------------ F0, F2-F6, F8, F9 (paso 5)
#
# Ninguna se anula y todas son pegajosas (spec §7): se cierran con una
# verificacion, un rechazo o un cambio en los datos, y la orden de IBAN que
# la hace desaparecer la resuelve (servicios.py). Solo miran las cuentas de
# proveedor: son las que se pagan; las de cliente se registran para el
# cruce con el banco (paso 7).

# Se busca sobre el texto ya en minusculas: sin IGNORECASE la busqueda es
# tres veces mas rapida, y se hace en cada compra de cada pasada.
_FACTORING = re.compile(
    r"factoring|factormaatschappij|\bcessie\b|gecedeerd|cesi[oó]n de (?:cr[eé]dito|la factura)"
    r"|\bg[-\s]?rekening\b|vrijwaringsrekening|debt purchase|assignment of (?:the )?receivable")


@dataclass(frozen=True)
class Registro:
    """Lo que las reglas F necesitan del registro de cuentas, calculado una vez por pasada."""

    estados: dict[int, EstadoCuenta]
    por_proveedor: dict[int, list[Cuenta]]
    por_iban: dict[str, list[Cuenta]]
    hay_maestro: bool                    # alguna cuenta de proveedor llego de Exact
    proveedores_importados: bool         # ya entro algun maestro de proveedores
    caducada: bool                       # Exact esta pasado de su limite de frescura


def registro(instantanea: Instantanea) -> Registro:
    telefonos: dict[int, list[CambioTelefono]] = defaultdict(list)
    for t in instantanea.telefonos:
        telefonos[t.proveedor_id].append(t)
    estados: dict[int, EstadoCuenta] = {}
    por_proveedor: dict[int, list[Cuenta]] = defaultdict(list)
    por_iban: dict[str, list[Cuenta]] = defaultdict(list)
    hay_maestro = False
    for cuenta in instantanea.cuentas:
        por_iban[cuenta.iban].append(cuenta)
        if cuenta.titular != "proveedor":
            continue
        por_proveedor[cuenta.parte_id].append(cuenta)
        estados[cuenta.id] = estado_cuenta(cuenta, telefonos.get(cuenta.parte_id, ()),
                                           instantanea.politica)
        hay_maestro = hay_maestro or any(e.tipo in (VISTO_EXACT, AUSENTE_EXACT)
                                         for e in cuenta.eventos)
    return Registro(estados, por_proveedor, por_iban, hay_maestro,
                    importado(instantanea, "proveedores"), bool(caducada(instantanea, "exact")))


def _rechazada_para(cuenta: Cuenta | None, factura: Factura) -> bool:
    """Si una persona rechazo esta cuenta por esta factura y dijo pagar a la verificada."""
    if cuenta is None or factura.documento_id is None:
        return False
    return any(e.tipo == "rechazada" and e.con_permiso and e.documento_id == factura.documento_id
               and e.decision_facturas == "pagar_a_verificada" for e in cuenta.eventos)


def _del_proveedor(r: Registro, factura: Factura, iban: str) -> Cuenta | None:
    return next((c for c in r.por_proveedor.get(factura.proveedor_id, ()) if c.iban == iban),
                None)


def _objetivo_iban(factura: Factura) -> tuple[Objetivo, ...]:
    return (Objetivo("factura", factura.id, "iban_doc"),)


def f2(factura: Factura, r: Registro) -> list[Resultado]:
    """F2: el IBAN de la factura no es una cuenta pagable de su proveedor (bloquea).

    Pagable (decision 3): verificada, atestada o heredada, presente en la
    ultima importacion de Exact que la miro y sin un cambio del maestro por
    verificar. Una cuenta rechazada para esta factura con "pagar a la
    verificada" deja de bloquearla si el proveedor tiene alguna pagable: el
    pago sale a esa, nunca al IBAN del documento.
    """
    if factura.sentido != ENTRANTE or not factura.iban_doc:
        return []
    if factura.proveedor_id is None and not r.proveedores_importados:
        return []
    iban = normalizar_iban(factura.iban_doc)
    if iban is None:
        return []
    if factura.proveedor_id is None:
        return [fallo("F2", factura, "Sin proveedor resuelto ninguna cuenta es pagable: el IBAN "
                                     "de la factura no se puede comprobar contra el registro.",
                      valores={"iban": iban, "estado": None}, objetivos=_objetivo_iban(factura))]
    if not r.hay_maestro:
        return [sin_datos("F2", factura, "Todavía no ha entrado ninguna cuenta del maestro de "
                                         "Exact: no se sabe qué cuenta es pagable.")]
    cuenta = _del_proveedor(r, factura, iban)
    estado = r.estados[cuenta.id] if cuenta is not None else None
    pagables = [c for c in r.por_proveedor.get(factura.proveedor_id, ()) if r.estados[c.id].pagable]
    if estado is not None and estado.pagable:
        if r.caducada:
            return [sin_datos("F2", factura, "El maestro de Exact está pasado de su límite de "
                                             "frescura: no se sabe si la cuenta sigue en él.")]
        return []
    if pagables and _rechazada_para(cuenta, factura):
        return []
    if estado is None:
        motivo = "no está en el registro de cuentas de este proveedor"
    elif estado.estado == "rechazada":
        motivo = "una persona la rechazó"
    elif estado.cambios:
        motivo = "tiene un cambio del maestro sin verificar"
    elif not estado.en_exact:
        motivo = "no está en el último maestro de Exact"
    else:
        motivo = f"está {estado.estado}, sin verificar ni atestar"
    return [fallo("F2", factura, f"El IBAN {iban} de la factura no es pagable: {motivo}. Se paga "
                                 "siempre a una cuenta del maestro, nunca al IBAN del documento.",
                  valores={"iban": iban, "estado": estado.estado if estado else None,
                           "pagables": len(pagables)},
                  objetivos=_objetivo_iban(factura))]


LEE_REGISTRO = LEE_LOTES | LEE_CADUCIDAD | frozenset({
    "instantanea.cuentas", "instantanea.telefonos", "instantanea.politica",
    "cuenta.id", "cuenta.titular", "cuenta.parte_id", "cuenta.iban", "cuenta.eventos",
    "evento_cuenta.id", "evento_cuenta.tipo", "evento_cuenta.en",
    "evento_cuenta.importacion_id", "evento_cuenta.con_permiso",
    "evento_cuenta.telefono_usado", "evento_cuenta.llegada",
    "cambio_telefono.proveedor_id", "cambio_telefono.valor", "cambio_telefono.en",
    "cambio_telefono.alta", "politica.iban_solo_verificadas",
    "politica.enfriamiento_telefono_dias",
})
LEE_F2 = LEE_EN_JUEGO | LEE_REGISTRO | frozenset({
    "factura.id", "factura.sentido", "factura.iban_doc", "factura.proveedor_id",
    "factura.documento_id", "evento_cuenta.documento_id", "evento_cuenta.decision_facturas",
})


def f3(factura: Factura, r: Registro) -> list[Resultado]:
    """F3: el IBAN de la factura es nuevo para su proveedor, o esta rechazado (bloquea).

    Necesita la llamada al telefono del maestro de antes del documento. Sin
    proveedor resuelto no se mira (ya bloquea F2); sin cuentas del maestro,
    tampoco (F2 da sin_datos).
    """
    if (factura.sentido != ENTRANTE or not factura.iban_doc or factura.proveedor_id is None
            or not r.hay_maestro):
        return []
    iban = normalizar_iban(factura.iban_doc)
    if iban is None:
        return []
    cuenta = _del_proveedor(r, factura, iban)
    if cuenta is not None and r.estados[cuenta.id].estado != "rechazada":
        if r.caducada:
            return [sin_datos("F3", factura, "El maestro de Exact está pasado de su límite de "
                                             "frescura: no se compara con él.")]
        return []
    if _rechazada_para(cuenta, factura):
        return []
    motivo = ("está rechazada para este proveedor" if cuenta is not None
              else "es nueva para este proveedor")
    return [fallo("F3", factura, f"La cuenta {iban} {motivo}: verificar por teléfono al número "
                                 "que tenía el maestro antes de esta factura, nunca al que trae.",
                  valores={"iban": iban, "registrada": cuenta is not None},
                  objetivos=_objetivo_iban(factura))]


LEE_F3 = LEE_F2


def _preparar_f4(instantanea: Instantanea) -> tuple[Registro, dict[str, bool]]:
    """El registro, y una memoria de los textos ya mirados en esta pasada (se repiten mucho)."""
    return registro(instantanea), {}


def f4(factura: Factura, contexto: tuple[Registro, dict[str, bool]]) -> list[Resultado]:
    """F4: el IBAN es de otro (proveedor o cliente) o la factura habla de factoring o cesion."""
    if factura.sentido != ENTRANTE:
        return []
    r, mirados = contexto
    motivos = []
    texto = " ".join(t for t in (factura.notas_doc, *(l.descripcion_doc for l in factura.lineas))
                     if t)
    factoring = mirados.get(texto)
    if factoring is None:
        factoring = mirados[texto] = bool(texto and _FACTORING.search(texto.lower()))
    if factoring:
        motivos.append("habla de factoring, cesión o G-rekening")
    # Sin cuentas registradas no hay de quien mas sea: el IBAN solo se normaliza si hace falta.
    iban = normalizar_iban(factura.iban_doc) if (r.por_iban or factoring) else None
    ajenas = [c for c in r.por_iban.get(iban, ()) if iban is not None and not (
        c.titular == "proveedor" and c.parte_id == factura.proveedor_id)]
    if ajenas:
        motivos.append(f"el IBAN {iban} está registrado para otro titular")
    if not motivos:
        return []
    return [fallo("F4", factura, "Pago a un tercero: " + "; ".join(motivos)
                  + ". Bloquea y se escala.",
                  valores={"iban": iban, "ajenas": [[c.titular, c.parte_id] for c in ajenas],
                           "factoring": factoring},
                  objetivos=_objetivo_iban(factura))]


LEE_F4 = LEE_EN_JUEGO | LEE_REGISTRO | frozenset({
    "factura.id", "factura.sentido", "factura.iban_doc", "factura.proveedor_id",
    "factura.notas_doc", "factura.lineas", "linea.descripcion_doc",
})


def _de_proveedor(regla: str, proveedor_id: int, resultado: str, detalle: str, *,
                  clave: str, valores: dict[str, Any]) -> Resultado:
    return Resultado(regla, "proveedor", proveedor_id, resultado, detalle, valores, clave, None,
                     None, (Objetivo("proveedor", proveedor_id),))


def f0(instantanea: Instantanea) -> list[Resultado]:
    """F0: cuentas heredadas del primer maestro que nadie ha atestado (retiene; es la tarea).

    El primer maestro se acepta como referencia para no bloquear nada el
    primer dia (decision 3), pero esas cuentas se ensenan sin verificar y
    queda una sola tarea, de nivel atencion, para atestarlas. Va sobre la
    importacion de partida.
    """
    r = registro(instantanea)
    pendientes: dict[int, list[Cuenta]] = defaultdict(list)
    for proveedor in r.por_proveedor.values():
        for cuenta in proveedor:
            estado = r.estados[cuenta.id]
            if (estado.baseline is not None and estado.estado == HEREDADA and estado.en_exact
                    and not estado.cambios):
                pendientes[estado.baseline].append(cuenta)
    salida = []
    for importacion_id, cuentas_ in sorted(pendientes.items()):
        n = len(cuentas_)
        salida.append(Resultado(
            "F0", "importacion", importacion_id, FALLO,
            f"{n} cuenta{'s' if n != 1 else ''} heredada{'s' if n != 1 else ''} del primer "
            "maestro sin atestar: se aceptan como referencia, pero nadie las ha comprobado.",
            {"cuentas": sorted(c.id for c in cuentas_)}, "", None, None,
            (Objetivo("importacion", importacion_id),)))
    return salida


def f5(instantanea: Instantanea) -> list[Resultado]:
    """F5: una cuenta anadida, cambiada o quitada en un maestro posterior al primero (bloquea).

    Hasta que una persona la verifica por telefono (o la rechaza). No se
    cierra porque otro maestro la vuelva a dejar como estaba: lo que se
    cambio en el maestro sin que nadie llamara sigue sin verificar.
    """
    r = registro(instantanea)
    salida = []
    textos = {"anadida_al_maestro": "se añadió", "retirada_del_maestro": "desapareció",
              "vuelve_al_maestro": "volvió"}
    for proveedor_id, cuentas_ in sorted(r.por_proveedor.items()):
        for cuenta in cuentas_:
            cambios = r.estados[cuenta.id].cambios
            if not cambios:
                continue
            que = ", ".join(f"{textos[t]} (importación {i})" for t, _e, i in cambios)
            salida.append(_de_proveedor(
                "F5", proveedor_id, FALLO,
                f"La cuenta {cuenta.iban} cambió en el maestro: {que}. Bloqueada hasta "
                "verificarla por teléfono al número de antes del cambio.",
                clave=f"cuenta:{cuenta.id}",
                valores={"cuenta": cuenta.id, "iban": cuenta.iban,
                         "cambios": [[t, e, i] for t, e, i in cambios]}))
    return salida


def f6(instantanea: Instantanea) -> list[Resultado]:
    """F6: Exact y TRNSPRNT no dicen las mismas cuentas de un proveedor (bloquea)."""
    salida = []
    por_proveedor: dict[int, dict[str, set[str]]] = defaultdict(lambda: {"exact": set(),
                                                                         "trnsprnt": set()})
    con_datos: dict[int, set[str]] = defaultdict(set)
    for cuenta in instantanea.cuentas:
        if cuenta.titular != "proveedor":
            continue
        for fuente in ("exact", "trnsprnt"):
            ultimos = [e.tipo for e in cuenta.eventos
                       if e.tipo in (f"visto_en_{fuente}", f"ausente_en_{fuente}")]
            if ultimos:
                con_datos[cuenta.parte_id].add(fuente)
                if ultimos[-1].startswith("visto"):
                    por_proveedor[cuenta.parte_id][fuente].add(cuenta.iban)
    for proveedor_id, fuentes in sorted(con_datos.items()):
        if fuentes != {"exact", "trnsprnt"}:
            continue
        exact, trnsprnt = (sorted(por_proveedor[proveedor_id][f]) for f in ("exact", "trnsprnt"))
        if exact != trnsprnt:
            salida.append(_de_proveedor(
                "F6", proveedor_id, FALLO,
                f"Exact dice {', '.join(exact) or 'ninguna'} y TRNSPRNT "
                f"{', '.join(trnsprnt) or 'ninguna'}.", clave="exact_trnsprnt",
                valores={"exact": exact, "trnsprnt": trnsprnt}))
    return salida


def f8(instantanea: Instantanea) -> list[Resultado]:
    """F8: la ultima verificacion de una cuenta no cuenta (bloquea).

    El numero llamado no era el del maestro de antes del documento, el
    telefono habia cambiado dentro del enfriamiento, o quien verifico no
    tenia confirmar_iban. La cuenta sigue como estaba antes de esa llamada.
    """
    r = registro(instantanea)
    salida = []
    for proveedor_id, cuentas_ in sorted(r.por_proveedor.items()):
        for cuenta in cuentas_:
            ineficaz = r.estados[cuenta.id].ineficaz
            if ineficaz is None:
                continue
            evento, motivo = ineficaz
            salida.append(_de_proveedor(
                "F8", proveedor_id, FALLO,
                f"La verificación de {cuenta.iban} del {evento.en[:10]} no vale: {motivo}.",
                clave=f"cuenta:{cuenta.id}",
                valores={"cuenta": cuenta.id, "iban": cuenta.iban, "evento": evento.id,
                         "motivo": motivo}))
    return salida


def f9(instantanea: Instantanea) -> list[Resultado]:
    """F9: el telefono de verificacion cambio hace menos que el enfriamiento (aviso)."""
    dias = instantanea.politica.enfriamiento_telefono_dias
    ultimos: dict[int, CambioTelefono] = {}
    for t in instantanea.telefonos:
        if not t.alta:
            ultimos[t.proveedor_id] = t
    salida = []
    for proveedor_id, cambio in sorted(ultimos.items()):
        transcurridos = (instantanea.hoy - cambio.dia).days
        if transcurridos >= dias:
            continue
        hasta = cambio.dia + timedelta(days=dias)
        salida.append(_de_proveedor(
            "F9", proveedor_id, FALLO,
            f"El teléfono de verificación cambió el {cambio.dia.isoformat()}: hasta el "
            f"{hasta.isoformat()} no vale ninguna verificación por teléfono de este proveedor.",
            clave="telefono", valores={"cambio": cambio.cambio_id, "dia": cambio.dia.isoformat(),
                                       "hasta": hasta.isoformat()}))
    return salida


LEE_F0 = LEE_REGISTRO
LEE_F5 = LEE_REGISTRO
LEE_F8 = LEE_REGISTRO
LEE_F6 = frozenset({"instantanea.cuentas", "cuenta.titular", "cuenta.eventos", "cuenta.parte_id",
                    "cuenta.iban", "evento_cuenta.tipo"})
LEE_F9 = frozenset({"instantanea.telefonos", "instantanea.politica", "instantanea.hoy",
                    "politica.enfriamiento_telefono_dias", "cambio_telefono.alta",
                    "cambio_telefono.proveedor_id", "cambio_telefono.dia",
                    "cambio_telefono.cambio_id"})

EVALUAR = {
    "F2": solo_objeciones(f2, registro),
    "F3": solo_objeciones(f3, registro),
    "F4": solo_objeciones(f4, _preparar_f4),
}
