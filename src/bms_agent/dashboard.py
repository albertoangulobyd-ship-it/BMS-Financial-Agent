"""Agregacion del historico de facturas para el panel.

El informe por fichas contesta "que dice esta factura". Esto contesta "que
esta pasando": cuanto se gasta, con quien, como evoluciona, y que hay raro.

Todas las deteccion de anomalias de aqui son deterministas y cruzan el
historico completo, que es lo que una factura mirada de una en una no puede
ver: un duplicado, un periodo repetido o una tarifa que cambio.

Desde el paso 3, B2, B3, B4 y G3 no se calculan aqui: los detectores
construyen sus candidatas desde las filas del panel y llaman a las
comprobaciones de fondo de reglas/unicidad.py y reglas/planning.py, las
mismas que el motor evalua sobre el almacen. Lo que sigue aqui es el
contrato v1 (sus textos, su orden, su severidad critico/revisar), que la
foto de referencia y /api/datos fijan byte a byte.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from .checks import POLITICA_V1, _euros, en_euros, run_checks
from .facturacion import cargar_tarifas, proyectar
from .parsing import ParseError, es_unidad_hora, parse_amount, parse_iso_date
from .reglas.planning import Observacion, cambios_de_tarifa, tipo_de_trabajo
from .reglas.unicidad import Candidata, importes_repetidos, numeros_repetidos, periodos_solapados

VENTANA_DUPLICADO = timedelta(days=POLITICA_V1.ventana_duplicado_dias)

SEVERIDAD_ORDEN = {"critico": 0, "revisar": 1, "aviso": 2}


@dataclass
class Alerta:
    severidad: str  # critico | revisar | aviso
    regla: str
    titulo: str
    detalle: str
    facturas: list[str] = field(default_factory=list)
    # Las posiciones en `registros` de las facturas, para marcar sus filas:
    # dos PDF con el mismo nombre en dos carpetas no son la misma factura.
    # No va en el contrato v1.
    indices: list[int] = field(default_factory=list, compare=False, repr=False)


@dataclass
class Fila:
    """Una factura, aplanada para la tabla."""

    fichero: str
    proveedor: str
    numero: str
    fecha: str
    fecha_orden: str
    identidad: str
    periodo: str
    periodo_ini: str
    periodo_fin: str
    ubicaciones: str
    semanas: str
    horas: Decimal | None
    otras_unidades: list[str]
    base: Decimal | None
    iva: Decimal | None
    total: Decimal | None
    regimen: str
    iban: str
    vencimiento: str
    estado: str  # ok | revisar | critico
    fallos: list[str]   # reglas incumplidas: no se paga sin resolver
    avisos: list[str]   # cosas que mirar, pero no bloquean
    # X1: la factura no esta en euros. Sale en la tabla y en las alertas, pero
    # ningun agregado la suma (ni importes ni horas): ver _sumables.
    en_euros: bool = True
    # La posicion del registro de esta fila en la lista de entrada.
    indice: int = -1

    @property
    def motivos(self) -> list[str]:
        return self.fallos + self.avisos


def _dec(raw: Any) -> Decimal | None:
    if raw in (None, ""):
        return None
    try:
        return parse_amount(str(raw))
    except ParseError:
        return None


def _fecha(raw: Any) -> date | None:
    if raw in (None, ""):
        return None
    try:
        return parse_iso_date(str(raw))
    except ParseError:
        return None


def _horas(extraction: dict[str, Any]) -> Decimal | None:
    """Suma solo las lineas facturadas en horas.

    Lo facturado en dias, piezas o kilometros no son horas y sumarlo daria un
    numero sin sentido. Lo que queda fuera se declara en _otras_unidades para
    que no desaparezca en silencio. Que es una hora lo decide es_unidad_hora:
    "uren" o "hours" tambien lo son.
    """
    total = Decimal(0)
    visto = False
    for linea in extraction.get("lines") or []:
        if es_unidad_hora(linea.get("unit")):
            cantidad = _dec(linea.get("quantity_raw"))
            if cantidad is not None:
                total += cantidad
                visto = True
    return total if visto else None


def _otras_unidades(extraction: dict[str, Any]) -> list[str]:
    """Unidades distintas de la hora presentes en la factura."""
    unidades: list[str] = []
    for linea in extraction.get("lines") or []:
        unidad = (linea.get("unit") or "").strip().lower()
        if unidad and not es_unidad_hora(unidad) and unidad not in unidades:
            unidades.append(unidad)
    return unidades


def _identidad(extraction: dict[str, Any]) -> str:
    """Clave canonica del proveedor.

    El nombre impreso cambia entre facturas del mismo autonomo ("J. de Vries",
    "De Vries Montage"). El btw-id no. Agrupar por nombre haria que un cambio
    de IBAN acompanado de un cambio de nombre pasara desapercibido, que es
    justo la forma que toma el fraude cuando alguien se esfuerza.
    """
    btw = (extraction.get("vat_number") or "").replace(" ", "").upper()
    if btw:
        return "btw:" + btw
    kvk = (extraction.get("kvk_number") or "").strip()
    if kvk:
        return "kvk:" + kvk
    return "nom:" + (extraction.get("supplier_name") or "").strip().lower()


def _unicos(valores: list[Any]) -> str:
    vistos: list[str] = []
    for v in valores:
        if v in (None, "") or str(v) in vistos:
            continue
        vistos.append(str(v))
    return " · ".join(vistos) if vistos else "—"


def _periodo_de(extraction: dict[str, Any]) -> tuple[str | None, str | None]:
    """Periodo de prestacion, de la cabecera o deducido de las lineas.

    Muchas facturas no llevan el periodo arriba y solo lo declaran linea a
    linea. Sin mirar ahi, la regla del periodo repetido no ve nada en esas
    facturas, que es justo donde un duplicado pasa mas desapercibido.
    """
    inicio = extraction.get("service_period_start")
    fin = extraction.get("service_period_end")
    if inicio and fin:
        return inicio, fin

    inicios = [l.get("period_start") for l in extraction.get("lines") or []]
    fines = [l.get("period_end") for l in extraction.get("lines") or []]
    validos_i = sorted(d for d in inicios if d)
    validos_f = sorted(d for d in fines if d)
    return (inicio or (validos_i[0] if validos_i else None),
            fin or (validos_f[-1] if validos_f else None))

def construir_filas(registros: list[dict[str, Any]]) -> list[Fila]:
    filas: list[Fila] = []
    for indice, registro in enumerate(registros):
        x = registro.get("extraction") or {}
        comprobaciones = run_checks(x)
        fallos = [f"{c.label}: {c.detail}" for c in comprobaciones if c.failed]
        # La moneda se decide una vez por factura. Un literal sin marcador en
        # una factura con "$" en el total no son euros, aunque parse_amount,
        # que solo ve ese literal, lo lea como tales.
        euros = not any(c.rule == "X1" and c.failed for c in comprobaciones)

        avisos: list[str] = []
        dudosos = x.get("low_confidence_fields") or []
        if dudosos:
            avisos.append("Lectura dudosa en " + ", ".join(dudosos))
        if x.get("document_notes"):
            avisos.append("El documento lleva texto marcado para revisar")

        estado = "critico" if fallos else ("revisar" if avisos else "ok")

        inicio, fin = _periodo_de(x)
        periodo = f"{inicio or '?'} a {fin or '?'}" if (inicio or fin) else "—"

        lineas = x.get("lines") or []
        fecha_cruda = x.get("invoice_date")
        fecha_norm = _fecha(fecha_cruda)
        filas.append(
            Fila(
                fichero=registro.get("source_name", "—"),
                proveedor=x.get("supplier_name") or "(sin nombre)",
                numero=x.get("invoice_number") or "—",
                fecha=fecha_cruda or "—",
                # Normalizada a ISO: el resto del modulo trocea esta cadena
                # (fecha_orden[:7], [:4]) y un "13-09-2026" daria int("13-0").
                fecha_orden=fecha_norm.isoformat() if fecha_norm else "0000-00-00",
                identidad=_identidad(x),
                periodo=periodo,
                periodo_ini=inicio or "",
                periodo_fin=fin or inicio or "",
                ubicaciones=_unicos([l.get("location") for l in lineas]),
                semanas=_unicos([l.get("week_number") for l in lineas]),
                horas=_horas(x),
                otras_unidades=_otras_unidades(x),
                base=_dec(x.get("subtotal_excl_vat_raw")) if euros else None,
                iva=_dec(x.get("vat_amount_raw")) if euros else None,
                total=_dec(x.get("total_incl_vat_raw")) if euros else None,
                regimen=x.get("vat_regime") or "unknown",
                iban=(x.get("iban") or "—"),
                vencimiento=x.get("due_date") or "—",
                estado=estado,
                fallos=fallos,
                avisos=avisos,
                en_euros=euros,
                indice=indice,
            )
        )
    filas.sort(key=lambda f: f.fecha_orden, reverse=True)
    return filas


def _sumables(filas: list[Fila]) -> list[Fila]:
    """Las filas que entran en los agregados: las que estan en euros.

    Una factura que no esta en euros queda fuera de todos, tambien de las
    horas y de los recuentos por mes, proveedor, regimen y semana. Dejarla en
    unos y no en otros daba un panel que la contaba en las horas de un
    proveedor con 0,00 EUR de importe, como si hubiera trabajado gratis.
    """
    return [f for f in filas if f.en_euros]


def por_mes(filas: list[Fila]) -> list[dict[str, Any]]:
    """Serie temporal de gasto, en BASE IMPONIBLE.

    No en total con IVA: una factura con el IVA trasladado no lleva cuota y
    otra al 21% si, asi que compararlas por el total premia al regimen, no al
    gasto. La base es lo unico comparable entre regimenes.
    """
    acumulado: dict[str, list[Any]] = defaultdict(lambda: [0, Decimal(0)])
    for fila in _sumables(filas):
        importe = fila.base if fila.base is not None else fila.total
        if fila.fecha_orden == "0000-00-00" or importe is None:
            continue
        clave = fila.fecha_orden[:7]
        acumulado[clave][0] += 1
        acumulado[clave][1] += importe

    if not acumulado:
        return []

    meses = sorted(acumulado)
    salida: list[dict[str, Any]] = []
    ano, mes = int(meses[0][:4]), int(meses[0][5:7])
    fin_ano, fin_mes = int(meses[-1][:4]), int(meses[-1][5:7])
    while (ano, mes) <= (fin_ano, fin_mes):
        clave = f"{ano:04d}-{mes:02d}"
        cuenta, total = acumulado.get(clave, [0, Decimal(0)])
        salida.append({"mes": clave, "facturas": cuenta, "total": total})
        mes += 1
        if mes == 13:
            ano, mes = ano + 1, 1
    return salida


def por_proveedor(filas: list[Fila]) -> list[dict[str, Any]]:
    acumulado: dict[str, dict[str, Any]] = {}
    for fila in _sumables(filas):
        entrada = acumulado.setdefault(
            fila.proveedor,
            {"proveedor": fila.proveedor, "facturas": 0, "total": Decimal(0),
             "horas": Decimal(0), "primera": None, "ultima": None, "avisos": 0},
        )
        entrada["facturas"] += 1
        importe = fila.base if fila.base is not None else fila.total
        if importe is not None:
            entrada["total"] += importe
        if fila.horas is not None:
            entrada["horas"] += fila.horas
        if fila.estado != "ok":
            entrada["avisos"] += 1
        if fila.fecha_orden != "0000-00-00":
            if entrada["primera"] is None or fila.fecha_orden < entrada["primera"]:
                entrada["primera"] = fila.fecha_orden
            if entrada["ultima"] is None or fila.fecha_orden > entrada["ultima"]:
                entrada["ultima"] = fila.fecha_orden
    return sorted(acumulado.values(), key=lambda e: e["total"], reverse=True)


def por_regimen(filas: list[Fila]) -> list[dict[str, Any]]:
    etiquetas = {
        "standard": "IVA repercutido",
        "reverse_charged": "IVA trasladado",
        "kor_exempt": "Exenta por KOR",
        "unknown": "Sin determinar",
    }
    acumulado: dict[str, dict[str, Any]] = {}
    for fila in _sumables(filas):
        entrada = acumulado.setdefault(
            fila.regimen,
            {"clave": fila.regimen, "etiqueta": etiquetas.get(fila.regimen, fila.regimen),
             "facturas": 0, "total": Decimal(0)},
        )
        entrada["facturas"] += 1
        importe = fila.base if fila.base is not None else fila.total
        if importe is not None:
            entrada["total"] += importe
    return sorted(acumulado.values(), key=lambda e: e["total"], reverse=True)


def _candidatas(filas: list[Fila]) -> list[Candidata]:
    """Las filas como las ven las reglas de duplicados, en el orden del panel.

    `orden` es la posicion de la fila: a igual fecha o periodo, manda el
    orden en que el panel las tiene, como antes. Una fila sin nombre, btw-id
    ni KvK no tiene contraparte y no se agrupa con nadie (antes la guarda
    `nom:(sin` no cazaba nada y las juntaba).
    """
    return [
        Candidata(
            ref=posicion,
            grupo=None if fila.identidad == "nom:" else fila.identidad,
            numero=None if fila.numero == "—" else fila.numero,
            fecha=None if fila.fecha_orden == "0000-00-00" else _fecha(fila.fecha_orden),
            total=fila.total,
            inicio=_fecha(fila.periodo_ini),
            fin=_fecha(fila.periodo_fin),
            orden=posicion,
        )
        for posicion, fila in enumerate(filas)
    ]


def _es_correccion(a: Fila, b: Fila) -> bool:
    """Una nota de credito o una rectificativa contra la factura que corrige."""
    if a.total is None or b.total is None:
        return False
    return a.total < 0 or b.total < 0 or a.total == -b.total


def detectar_duplicados(filas: list[Fila]) -> list[Alerta]:
    """Reglas B2 y B3: lo que solo se ve cruzando el historico (reglas/unicidad.py)."""
    alertas: list[Alerta] = []
    candidatas = _candidatas(filas)

    # B2: mismo proveedor y mismo numero.
    for (_clave, numero), grupo in numeros_repetidos(candidatas):
        miembros = [filas[c.ref] for c in grupo]
        alertas.append(Alerta(
            "critico", "B2", "Numero de factura repetido",
            f"{miembros[0].proveedor} tiene {len(miembros)} facturas con el numero {numero}.",
            [f.fichero for f in miembros], [f.indice for f in miembros],
        ))

    # B3: mismo proveedor, mismo importe, pocos dias de diferencia, numero distinto.
    for a, b, dias in importes_repetidos(candidatas, POLITICA_V1):
        fa, fb = filas[a.ref], filas[b.ref]
        alertas.append(Alerta(
            "revisar", "B3", "Posible duplicado por contenido",
            f"{fa.proveedor}: {fa.numero} y {fb.numero} suman lo mismo "
            f"({_euros(fb.total)}) con {dias} dias de diferencia "
            f"y periodos que se pisan.",
            [fa.fichero, fb.fichero], [fa.indice, fb.indice],
        ))
    return alertas


def detectar_periodos_repetidos(filas: list[Fila]) -> list[Alerta]:
    """Regla B4: el mismo periodo facturado dos veces (reglas/unicidad.py).

    Se comparan rangos de fechas, no cadenas. Un periodo del 7 al 13 solapa
    con otro del 1 al 10 aunque los textos no se parezcan en nada, y ese es
    precisamente el caso que hay que cazar. Una nota de credito o una
    rectificativa cubren a proposito el mismo periodo que corrigen: eso no
    es facturar dos veces. En el contrato v1 no se separa por Objeto; el
    motor de reglas si lo hace.
    """
    alertas: list[Alerta] = []

    def excluir(a: Candidata, b: Candidata) -> bool:
        return _es_correccion(filas[a.ref], filas[b.ref])

    for a, b, dias in periodos_solapados(_candidatas(filas), excluir):
        fila_a, fila_b = filas[a.ref], filas[b.ref]
        # Retencion, no bloqueo, como dice el catalogo: dos periodos que se
        # pisan son a menudo dos obras o una sustitucion, y eso lo decide una
        # persona, no la aritmetica.
        alertas.append(Alerta(
            "revisar", "B4", "Periodo facturado dos veces",
            f"{fila_a.proveedor}: {fila_a.numero} ({fila_a.periodo}) y "
            f"{fila_b.numero} ({fila_b.periodo}) solapan {dias} dia(s).",
            [fila_a.fichero, fila_b.fichero], [fila_a.indice, fila_b.indice],
        ))
    return alertas


_tipo_de_trabajo = tipo_de_trabajo


def detectar_cambios_de_tarifa(registros: list[dict[str, Any]]) -> list[Alerta]:
    """Regla G3 en su version disponible hoy: la tarifa cambia sin el planning.

    Sin el programa de planificacion no se puede comprobar contra la tarifa
    pactada, pero si se puede ver que un proveedor cobra dos tarifas distintas
    por el mismo trabajo en la misma ubicacion, en facturas distintas
    (reglas.planning.cambios_de_tarifa).

    Solo se compara entre facturas: dos tarifas dentro de una misma factura
    son normalmente dos conceptos, no un cambio.
    """
    observaciones: list[Observacion] = []
    nombres: dict[str, list[str]] = defaultdict(list)
    ficheros: dict[int, str] = {}
    for indice, registro in enumerate(registros):
        x = registro.get("extraction") or {}
        if not en_euros(x):
            # X1: una tarifa sin marcador en una factura en dolares no es una
            # tarifa en euros, y compararla con las otras daria un G3 falso.
            continue
        # Se agrupa por la identidad del proveedor, no por el nombre impreso:
        # quien cambia de nombre seguia cobrando otra tarifa sin que saltara
        # nada, y dos proveedores que se llaman igual se mezclaban.
        identidad = _identidad(x)
        nombre = x.get("supplier_name") or "(sin nombre)"
        if nombre not in nombres[identidad]:
            nombres[identidad].append(nombre)
        fecha = x.get("invoice_date") or "0000-00-00"
        ficheros[indice] = registro.get("source_name", "—")
        for linea in x.get("lines") or []:
            tarifa = _dec(linea.get("unit_rate_raw"))
            if tarifa is None:
                continue
            # Una linea sin obra no se descarta: se agrupa aparte. Descartarla
            # dejaba sin vigilancia a los proveedores que no desglosan por obra.
            ubicacion = str(linea.get("location") or "(sin obra)")
            grupo = (identidad, ubicacion, _tipo_de_trabajo(linea.get("description")))
            observaciones.append(Observacion(grupo, tarifa, fecha, (ficheros[indice], indice)))

    encontradas: list[tuple[tuple[str, str, str, str], Alerta]] = []
    for cambio in cambios_de_tarifa(observaciones):
        identidad, ubicacion, trabajo = cambio.grupo
        proveedor = _nombre_de(nombres[identidad])
        # Las desviadas salen por el nombre del fichero, como antes.
        desviadas = list(cambio.desviadas)
        encontradas.append(((proveedor, ubicacion, trabajo, identidad), Alerta(
            "revisar", "G3", "Tarifa distinta por el mismo trabajo",
            f"{proveedor}, {trabajo} en {ubicacion}: venia a "
            f"{_euros(cambio.anterior)} y despues a " +
            " y ".join(_euros(t) for t in cambio.posteriores) +
            f", entre {cambio.primera_fecha} y {cambio.ultima_fecha}.",
            [f for f, _i in desviadas], [i for _f, i in desviadas],
        )))
    # Orden por el nombre que se ensena, como antes de agrupar por identidad,
    # para que el panel no cambie de orden sin motivo.
    return [alerta for _clave, alerta in sorted(encontradas, key=lambda e: e[0])]


def _nombre_de(nombres: list[str]) -> str:
    """Nombre que se ensena de un proveedor que ha firmado de varias formas."""
    return " / ".join(sorted(nombres)) if nombres else "(sin nombre)"


def _nombre_normalizado(nombre: Any) -> str:
    """Nombre impreso sin mayusculas, puntos ni espacios de mas.

    "Van Dijk B.V." y "van dijk bv" son el mismo nombre para quien copia una
    factura ajena, y tienen que serlo tambien para F3.
    """
    sin_puntos = re.sub(r"[^\w\s]", "", str(nombre or "").lower())
    return " ".join(sin_puntos.split())


def _grupos_de_pago(registros: list[dict[str, Any]]) -> list[int]:
    """Grupo de proveedor de cada registro para las reglas de pago (F).

    _identidad toma la primera clave que hay (btw-id, KvK o nombre), y eso
    basta para agrupar el gasto, pero no para una parada de pago: un
    documento que copia el nombre y el KvK de un proveedor conocido y quita o
    cambia el btw-id tenia otra identidad, y su IBAN nuevo no paraba nada.
    Aqui dos registros son del mismo grupo si comparten CUALQUIERA de las tres
    claves (union de conjuntos). Juntar de mas cuesta una llamada; juntar de
    menos, un pago a una cuenta ajena.

    Un nombre vacio no une nada: "(sin nombre)" no es un proveedor.
    """
    padre = list(range(len(registros)))

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    primero_con: dict[str, int] = {}
    for i, registro in enumerate(registros):
        x = registro.get("extraction") or {}
        claves = [
            "btw:" + (x.get("vat_number") or "").replace(" ", "").upper(),
            "kvk:" + (x.get("kvk_number") or "").strip(),
            "nom:" + _nombre_normalizado(x.get("supplier_name")),
        ]
        for clave in claves:
            if clave.endswith(":"):
                continue
            if clave in primero_con:
                padre[raiz(i)] = raiz(primero_con[clave])
            else:
                primero_con[clave] = i
    return [raiz(i) for i in range(len(registros))]


def detectar_ibanes(registros: list[dict[str, Any]]) -> list[Alerta]:
    """Un proveedor con mas de un IBAN en sus documentos. Parada dura F3.

    Ninguna de las cuentas impresas es la de referencia. Antes lo era la que
    se vio primero, y eso convertia una primera factura fraudulenta en la
    cuenta "habitual" y acusaba a las buenas que llegaban despues. Una cuenta
    solo vale cuando esta verificada fuera del documento (el registro de
    cuentas llega con el maestro); mientras tanto, todas las facturas del
    proveedor que traen alguno de esos IBAN se paran hasta la llamada.

    El proveedor es el grupo de _grupos_de_pago: comparte btw-id, KvK o
    nombre con otra factura. Asi no se escapa quien copia el nombre y el KvK
    de un proveedor y cambia o quita el btw-id.

    Las cuentas se listan por la fecha en que aparecieron, porque eso ayuda a
    la llamada, pero el orden no hace buena a ninguna.
    """
    ibanes: dict[int, dict[str, list[tuple[str, int]]]] = defaultdict(lambda: defaultdict(list))
    nombres: dict[int, list[str]] = defaultdict(list)
    fechas: dict[int, str] = {}
    for indice, (registro, clave) in enumerate(zip(registros, _grupos_de_pago(registros))):
        x = registro.get("extraction") or {}
        nombre = x.get("supplier_name") or "(sin nombre)"
        if nombre not in nombres[clave]:
            nombres[clave].append(nombre)
        fichero = registro.get("source_name", "—")
        parseada = _fecha(x.get("invoice_date"))
        fechas[indice] = parseada.isoformat() if parseada else "9999-99-99"
        iban = (x.get("iban") or "").replace(" ", "").upper()
        if iban:
            ibanes[clave][iban].append((fichero, indice))

    encontradas: list[tuple[tuple[str, list[str]], Alerta]] = []
    for clave, cuentas in ibanes.items():
        if len(cuentas) < 2:
            continue
        proveedor = _nombre_de(nombres[clave])
        primera_de = {
            cuenta: min(fechas.get(i, "9999-99-99") for _f, i in lista)
            for cuenta, lista in cuentas.items()
        }
        orden = sorted(cuentas, key=lambda c: (primera_de[c], c))
        resumen = "; ".join(
            f"{c} en {len(cuentas[c])} factura(s) "
            + ("de fecha desconocida" if primera_de[c] == "9999-99-99"
               else f"desde {primera_de[c]}")
            for c in orden
        )
        afectadas = sorted(par for lista in cuentas.values() for par in lista)
        nombres_afectadas = [f for f, _i in afectadas]
        encontradas.append(((proveedor, nombres_afectadas), Alerta(
            "critico", "F3", "Mas de un IBAN para el mismo proveedor",
            f"{proveedor} trae {len(cuentas)} IBAN distintos en sus facturas: "
            f"{resumen}. Ninguno vale de referencia por haberse visto antes: "
            "verificacion telefonica al numero ya conocido antes de pagar "
            "cualquiera de ellas.",
            nombres_afectadas, [i for _f, i in afectadas],
        )))
    return [alerta for _clave, alerta in sorted(encontradas, key=lambda e: e[0])]


def construir_alertas(
    filas: list[Fila], registros: list[dict[str, Any]]
) -> list[Alerta]:
    alertas: list[Alerta] = []
    alertas += detectar_ibanes(registros)
    alertas += detectar_duplicados(filas)
    alertas += detectar_periodos_repetidos(filas)
    alertas += detectar_cambios_de_tarifa(registros)

    # Los motivos que se repiten se agrupan. Veintidos avisos identicos de
    # "lectura dudosa" no son veintidos hallazgos: son uno, con veintidos
    # facturas detras, y listarlos por separado entierra todo lo demas.
    grupos: dict[tuple[str, str], dict[str, Any]] = {}
    for fila in filas:
        for severidad, regla, motivo in (
            [("critico", "D", m) for m in fila.fallos]
            + [("revisar", "—", m) for m in fila.avisos]
        ):
            titulo = motivo.split(":")[0]
            clave = (severidad, titulo)
            entrada = grupos.setdefault(clave, {
                "severidad": severidad, "regla": regla, "titulo": titulo,
                "detalles": [], "facturas": [], "proveedores": set(),
            })
            entrada["detalles"].append(f"{fila.proveedor} {fila.numero}: {motivo}")
            entrada["facturas"].append(fila.fichero)
            entrada["proveedores"].add(fila.proveedor)

    for entrada in grupos.values():
        cuantas = len(entrada["facturas"])
        if cuantas == 1:
            detalle = entrada["detalles"][0]
        else:
            proveedores = sorted(entrada["proveedores"])
            de_quien = (
                proveedores[0] if len(proveedores) == 1
                else f"{len(proveedores)} proveedores"
            )
            detalle = f"{cuantas} facturas de {de_quien}. " + entrada["detalles"][0]
        alertas.append(Alerta(
            entrada["severidad"], entrada["regla"], entrada["titulo"],
            detalle, entrada["facturas"],
        ))

    alertas.sort(key=lambda a: (
        SEVERIDAD_ORDEN.get(a.severidad, 9), a.regla, -len(a.facturas), a.titulo))
    return alertas


def _num(value: Decimal | None) -> float | None:
    """Decimal a float solo en la frontera de serializacion.

    Los calculos van en Decimal. El JSON que consume el navegador necesita
    numeros, y a estas alturas ya no se opera con ellos: solo se pintan.
    """
    return None if value is None else float(value)


def _propagar_alertas_a_filas(filas: list[Fila], alertas: list[Alerta]) -> None:
    """Una factura involucrada en un duplicado o un cambio de IBAN no esta "ok".

    Las reglas que cruzan el historico (B2, B3, B4, F3, G3) no las ve una
    factura sola, asi que su estado hay que propagarlo hacia atras. Sin esto,
    una factura duplicada aparece verde en la tabla mientras la alerta de
    arriba dice que es critica, y el panel se contradice a si mismo.

    Se une por la posicion del registro (`Alerta.indices`), no por el nombre
    del fichero: dos PDF que se llaman igual en dos carpetas son dos
    facturas, y antes la alerta de uno marcaba la fila del otro. Una alerta
    sin posiciones (hecha a mano) se une por el nombre, como antes.
    """
    por_fichero = {f.fichero: f for f in filas}
    por_indice = {f.indice: f for f in filas}
    for alerta in alertas:
        if alerta.regla in ("—", "D"):
            continue
        afectadas = ([por_indice.get(i) for i in alerta.indices] if alerta.indices
                     else [por_fichero.get(f) for f in alerta.facturas])
        for fila in afectadas:
            if fila is None:
                continue
            texto = f"{alerta.titulo} (regla {alerta.regla})"
            if alerta.severidad == "critico":
                if texto not in fila.fallos:
                    fila.fallos.append(texto)
                fila.estado = "critico"
            else:
                if texto not in fila.avisos:
                    fila.avisos.append(texto)
                if fila.estado == "ok":
                    fila.estado = "revisar"


def _lunes(semana: str) -> date:
    """Lunes de una semana ISO escrita como 2026-W37."""
    ano, num = int(semana[:4]), int(semana[6:])
    return date.fromisocalendar(ano, num, 1)


def _rango_de_semanas(primera: str, ultima: str) -> list[str]:
    """Todas las semanas ISO entre dos, ambas incluidas."""
    dia, fin = _lunes(primera), _lunes(ultima)
    salida: list[str] = []
    while dia <= fin:
        iso = dia.isocalendar()
        salida.append(f"{iso.year}-W{iso.week:02d}")
        dia += timedelta(days=7)
    return salida


def _semanas_del_ano(ano: int) -> int:
    """52 o 53, segun el ano ISO."""
    return date(ano, 12, 28).isocalendar().week


def _ano_de_semana(declarada: int, referencia: date) -> int:
    """Ano ISO al que pertenece una semana declarada.

    Una factura emitida el 6 de enero por la semana 52 es de la semana 52 del
    ano ANTERIOR. Tomar el ano de la fecha de emision la mandaria a diciembre
    del ano en curso, y esa factura desaparece de la rejilla.
    """
    iso = referencia.isocalendar()
    if declarada >= 52 and iso.week <= 2:
        return iso.year - 1
    if declarada <= 2 and iso.week >= 52:
        return iso.year + 1
    return iso.year


def _semanas_de(fila: Fila) -> list[str]:
    """Semanas ISO que cubre una factura.

    Se usa la semana que declara la propia factura cuando esta; si no, la
    semana ISO del fin del periodo. Un zzp'er factura por semana, asi que
    esta es la unidad en la que se ve si falta una o si hay dos.

    Una semana ilegible o fuera de rango se descarta: un 53 en un ano de 52
    semanas hacia estallar date.fromisocalendar y con el la generacion entera
    del panel.
    """
    fin = _fecha(fila.periodo_fin) or _fecha(fila.fecha_orden)
    if not fin:
        return []

    salida: list[str] = []
    for texto in fila.semanas.split(" · "):
        if not texto.strip().isdigit():
            continue
        numero = int(texto)
        if not 1 <= numero <= 53:
            continue
        ano = _ano_de_semana(numero, fin)
        if numero > _semanas_del_ano(ano):
            continue
        salida.append(f"{ano}-W{numero:02d}")

    if salida:
        return salida
    iso = fin.isocalendar()
    return [f"{iso.year}-W{iso.week:02d}"]


def matriz_semanal(filas: list[Fila], maximo: int = 18) -> dict[str, Any]:
    """Rejilla proveedor por semana ISO.

    Una celda vacia es una semana sin factura de ese proveedor; dos o mas
    facturas en la misma celda es lo que hay que mirar. Sin el programa de
    planificacion no se puede saber si un hueco es que no trabajo o que no ha
    facturado, pero si se sabe a quien hay que llamar.
    """
    celdas: dict[tuple[str, str], dict[str, Any]] = {}
    semanas: set[str] = set()
    totales_por_proveedor: dict[str, Decimal] = defaultdict(Decimal)
    for fila in _sumables(filas):
        importe = fila.base if fila.base is not None else fila.total
        suyas = _semanas_de(fila)
        if not suyas:
            continue
        totales_por_proveedor[fila.proveedor] += importe or Decimal(0)
        # Una factura que cubre dos semanas se reparte entre ellas. Sumar el
        # importe entero en cada celda multiplicaba el gasto por el numero de
        # semanas y rompia la escala de la rampa.
        trozo = (importe or Decimal(0)) / Decimal(len(suyas))
        for semana in suyas:
            semanas.add(semana)
            celda = celdas.setdefault((fila.proveedor, semana),
                                      {"importe": Decimal(0), "n": 0, "estados": []})
            celda["importe"] += trozo
            celda["n"] += 1
            celda["estados"].append(fila.estado)

    if not semanas:
        return {"semanas": [], "proveedores": [], "maximo": 0}

    # Rango continuo: una semana sin facturas tiene que verse como hueco.
    # Es precisamente el dato que hace util esta rejilla.
    orden = _rango_de_semanas(min(semanas), max(semanas))[-maximo:]
    visibles = set(orden)
    proveedores: dict[str, dict[str, Any]] = {}
    for (proveedor, semana), celda in celdas.items():
        if semana not in visibles:
            continue
        entrada = proveedores.setdefault(proveedor, {"proveedor": proveedor, "celdas": {}, "total": Decimal(0)})
        estado = ("critico" if "critico" in celda["estados"]
                  else "revisar" if "revisar" in celda["estados"] else "ok")
        entrada["celdas"][semana] = {
            "importe": _num(celda["importe"]), "n": celda["n"], "estado": estado,
        }

    for nombre, entrada in proveedores.items():
        entrada["total"] = totales_por_proveedor.get(nombre, Decimal(0))
    lista = sorted(proveedores.values(), key=lambda e: e["total"], reverse=True)
    tope = max((c["importe"] or 0) for e in lista for c in e["celdas"].values())
    return {
        "semanas": orden,
        "proveedores": [{"proveedor": e["proveedor"], "celdas": e["celdas"],
                         "total": _num(e["total"])} for e in lista],
        "maximo": tope,
    }


def construir_datos(
    registros: list[dict[str, Any]], tarifas_path: str | None = "config/tarifas.yaml"
) -> dict[str, Any]:
    """Todo lo que el panel necesita, listo para serializar a JSON."""
    filas = construir_filas(registros)
    alertas = construir_alertas(filas, registros)
    _propagar_alertas_a_filas(filas, alertas)

    coste = Decimal(0)
    for registro in registros:
        uso = registro.get("usage") or {}
        from .pricing import estimate_cost

        estimado = estimate_cost(
            registro.get("model", ""),
            uso.get("input_tokens") or 0,
            uso.get("output_tokens") or 0,
        )
        if estimado is not None:
            coste += estimado

    # Los recuentos de abajo (facturas, proveedores, criticas) son de la
    # tabla, y la factura que no esta en euros esta en la tabla. Las sumas no.
    sumables = _sumables(filas)
    total = sum((f.total for f in sumables if f.total is not None), Decimal(0))
    horas = sum((f.horas for f in sumables if f.horas is not None), Decimal(0))
    iva = sum((f.iva for f in sumables if f.iva is not None), Decimal(0))

    return {
        "filas": [
            {
                "fichero": f.fichero, "proveedor": f.proveedor, "numero": f.numero,
                "fecha": f.fecha, "orden": f.fecha_orden, "periodo": f.periodo,
                "ubicaciones": f.ubicaciones, "semanas": f.semanas,
                "horas": _num(f.horas), "base": _num(f.base), "iva": _num(f.iva),
                "total": _num(f.total), "regimen": f.regimen, "iban": f.iban,
                "vencimiento": f.vencimiento, "estado": f.estado, "motivos": f.motivos,
                "otras_unidades": f.otras_unidades,
                "semanas_iso": _semanas_de(f),
            }
            for f in filas
        ],
        "por_mes": [
            {"mes": m["mes"], "facturas": m["facturas"], "total": _num(m["total"])}
            for m in por_mes(filas)
        ],
        "por_proveedor": [
            {
                "proveedor": p["proveedor"], "facturas": p["facturas"],
                "total": _num(p["total"]), "horas": _num(p["horas"]),
                "primera": p["primera"], "ultima": p["ultima"], "avisos": p["avisos"],
            }
            for p in por_proveedor(filas)
        ],
        "matriz": matriz_semanal(filas),
        "facturacion": proyectar(registros, cargar_tarifas(tarifas_path)),
        "por_regimen": [
            {"clave": r["clave"], "etiqueta": r["etiqueta"],
             "facturas": r["facturas"], "total": _num(r["total"])}
            for r in por_regimen(filas)
        ],
        "alertas": [
            {"severidad": a.severidad, "regla": a.regla, "titulo": a.titulo,
             "detalle": a.detalle, "facturas": a.facturas}
            for a in alertas
        ],
        "totales": {
            "facturas": len(filas),
            "importe": _num(total),
            "iva": _num(iva),
            "horas": _num(horas),
            "proveedores": len({f.proveedor for f in filas}),
            "criticas": sum(1 for f in filas if f.estado == "critico"),
            "por_revisar": sum(1 for f in filas if f.estado != "ok"),
            "coste_lectura": _num(coste),
            "desde": min((f.fecha_orden for f in filas if f.fecha_orden != "0000-00-00"), default=None),
            "hasta": max((f.fecha_orden for f in filas if f.fecha_orden != "0000-00-00"), default=None),
        },
    }
