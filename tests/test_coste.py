"""Cuanto cuesta cada pasada.

Lo que se fija aqui es sobre todo que el numero sea HONESTO: lo medido se
presenta como medido, lo estimado como horquilla, y un modelo sin tarifa no
se rellena con un precio inventado.
"""

from __future__ import annotations

from decimal import Decimal

from bms_agent.coste import (
    Documento,
    Estimacion,
    SALIDA_POR_DEFECTO,
    agrupar_en_pasadas,
    contar_entrada,
    formatear_estimacion,
    formatear_gastado,
    horquilla_de_salida,
    leer_documentos,
)


def registro(nombre, entrada=6000, salida=800, modelo="claude-opus-5", cuando=None):
    r = {
        "source_name": nombre,
        "model": modelo,
        "usage": {"input_tokens": entrada, "output_tokens": salida},
    }
    if cuando:
        r["extracted_at"] = cuando
    return r


def test_el_coste_sale_del_consumo_guardado() -> None:
    """6000 de entrada a $5 el millon y 800 de salida a $25 son $0,05."""
    d = leer_documentos([registro("a.pdf")])[0]
    assert d.coste == Decimal("0.050000")


def test_un_modelo_sin_tarifa_no_se_inventa() -> None:
    docs = leer_documentos([registro("a.pdf", modelo="modelo-que-no-existe")])
    assert docs[0].coste is None
    assert "Sin tarifa conocida" in formatear_gastado(docs)


def test_sin_extracciones_lo_dice_en_vez_de_ensenar_ceros() -> None:
    assert "No hay ninguna extraccion" in formatear_gastado([])


def test_dos_ejecuciones_separadas_son_dos_pasadas() -> None:
    docs = leer_documentos([
        registro("a.pdf", cuando="2026-09-20T10:00:00+00:00"),
        registro("b.pdf", cuando="2026-09-20T10:02:00+00:00"),
        registro("c.pdf", cuando="2026-09-21T09:00:00+00:00"),
    ])
    pasadas = agrupar_en_pasadas(docs)

    assert len(pasadas) == 2
    assert [len(p.documentos) for p in pasadas] == [1, 2]   # la mas reciente primero
    assert pasadas[0].desde.day == 21


def test_las_extracciones_seguidas_son_una_sola_pasada() -> None:
    docs = leer_documentos([
        registro(f"{i}.pdf", cuando=f"2026-09-20T10:0{i}:00+00:00") for i in range(5)
    ])
    pasadas = agrupar_en_pasadas(docs)

    assert len(pasadas) == 1
    assert pasadas[0].entrada == 30000
    assert pasadas[0].coste == Decimal("0.250000")


def test_lo_que_no_tiene_hora_va_aparte_y_al_final() -> None:
    """No se le inventa un hueco ni se mete en la pasada de otro dia."""
    docs = leer_documentos([
        registro("con.pdf", cuando="2026-09-20T10:00:00+00:00"),
        registro("sin.pdf"),
    ])
    pasadas = agrupar_en_pasadas(docs)

    assert len(pasadas) == 2
    assert pasadas[-1].desde is None
    assert [d.nombre for d in pasadas[-1].documentos] == ["sin.pdf"]


def test_una_pasada_con_un_modelo_sin_tarifa_no_suma_a_medias() -> None:
    docs = leer_documentos([
        registro("a.pdf", cuando="2026-09-20T10:00:00+00:00"),
        registro("b.pdf", cuando="2026-09-20T10:01:00+00:00", modelo="otro"),
    ])
    assert agrupar_en_pasadas(docs)[0].coste is None


def test_sin_historico_la_salida_es_un_punto_de_partida_declarado() -> None:
    bajo, alto, medida = horquilla_de_salida([])
    assert (bajo, alto) == SALIDA_POR_DEFECTO
    assert medida is False


def test_con_historico_la_salida_sale_de_vuestras_propias_facturas() -> None:
    docs = leer_documentos([registro(f"{i}.pdf", salida=s)
                            for i, s in enumerate([700, 800, 900, 1000, 5000])])
    bajo, alto, medida = horquilla_de_salida(docs)

    assert medida is True
    assert bajo <= 900 <= alto            # la mediana queda dentro
    assert alto < 5000                    # el documento raro no manda


class ClienteFalso:
    """Cuenta tokens sin llamar a nadie, y guarda lo que le pidieron."""

    def __init__(self, tokens: int = 4321) -> None:
        self.tokens = tokens
        self.peticiones: list[dict] = []
        self.messages = self

    def count_tokens(self, **kwargs):
        self.peticiones.append(kwargs)
        return type("R", (), {"input_tokens": self.tokens})()


def test_contar_la_entrada_manda_la_misma_peticion_sin_max_tokens() -> None:
    """Si se contara otra peticion, la cifra no valdria para nada."""
    cliente = ClienteFalso()
    peticion = {
        "model": "claude-opus-5", "max_tokens": 16000, "system": "...",
        "messages": [{"role": "user", "content": []}], "output_format": object,
    }
    assert contar_entrada(cliente, peticion) == 4321

    enviado = cliente.peticiones[0]
    assert "max_tokens" not in enviado           # no es parte de la entrada
    assert enviado["output_format"] is peticion["output_format"]  # el esquema ocupa
    assert enviado["system"] == "..."


def test_si_no_hay_nada_nuevo_la_proxima_pasada_cuesta_cero() -> None:
    texto = formatear_estimacion(Estimacion(
        modelo="claude-opus-5", en_cache=12, nuevos=0, entrada=0,
        salida_baja=0, salida_alta=0, salida_medida=True,
    ))
    assert "cuesta cero" in texto


def test_la_estimacion_se_da_en_horquilla_y_dice_que_es_exacto() -> None:
    est = Estimacion(
        modelo="claude-opus-5", en_cache=0, nuevos=3, entrada=21000,
        salida_baja=1800, salida_alta=4800, salida_medida=True,
    )
    assert est.coste_bajo < est.coste_alto

    texto = formatear_estimacion(est)
    assert "contados, exacto" in texto
    assert "horquilla" in texto
    assert "mediana de vuestro historico" in texto


def test_una_estimacion_sin_tarifa_no_da_un_numero() -> None:
    texto = formatear_estimacion(Estimacion(
        modelo="modelo-que-no-existe", en_cache=0, nuevos=2, entrada=1000,
        salida_baja=100, salida_alta=200, salida_medida=False,
    ))
    assert "no hay estimacion" in texto
