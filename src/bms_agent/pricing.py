"""Estimacion de coste a partir del consumo real de tokens.

La fase 0 tiene que responder "cuanto cuesta esto al mes" con un numero
medido, no con una suposicion. Cada extraccion ya guarda su consumo; aqui
solo se le pone precio.

Las tarifas son una instantanea de junio de 2026 y pueden cambiar. La
referencia viva esta en anthropic.com/pricing. Si el modelo no esta en la
tabla no se inventa un precio: se informa de que no hay estimacion.
"""

from __future__ import annotations

from decimal import Decimal

# Modelo -> (USD por millon de tokens de entrada, de salida).
PRICES: dict[str, tuple[str, str]] = {
    "claude-opus-5": ("5.00", "25.00"),
    "claude-opus-4-8": ("5.00", "25.00"),
    "claude-opus-4-7": ("5.00", "25.00"),
    "claude-opus-4-6": ("5.00", "25.00"),
    "claude-sonnet-5": ("2.00", "10.00"),
    "claude-sonnet-4-6": ("3.00", "15.00"),
    "claude-haiku-4-5": ("1.00", "5.00"),
    "claude-fable-5-1": ("10.00", "50.00"),
    "claude-fable-5": ("10.00", "50.00"),
}

_MILLION = Decimal(1_000_000)


def estimate_cost(
    model: str, input_tokens: int, output_tokens: int
) -> Decimal | None:
    """Coste en dolares, o None si el modelo no esta en la tabla."""
    rates = PRICES.get(model)
    if rates is None:
        return None
    rate_in, rate_out = Decimal(rates[0]), Decimal(rates[1])
    cost = (
        Decimal(input_tokens) * rate_in + Decimal(output_tokens) * rate_out
    ) / _MILLION
    return cost.quantize(Decimal("0.000001"))


def format_cost_summary(
    model: str, documents: int, input_tokens: int, output_tokens: int
) -> str:
    """Resumen de consumo y coste, con la proyeccion a cien facturas."""
    lines = [
        "Consumo",
        "-" * 42,
        f"  documentos           {documents:>12,}",
        f"  tokens de entrada    {input_tokens:>12,}",
        f"  tokens de salida     {output_tokens:>12,}",
    ]

    total = estimate_cost(model, input_tokens, output_tokens)
    if total is None:
        lines.append(f"\n  Sin tarifa conocida para {model}; no hay estimacion.")
        return "\n".join(lines)

    lines.append(f"  coste estimado       {'$' + f'{total:.4f}':>12}")

    if documents:
        per_doc = total / Decimal(documents)
        lines.append(f"  por documento        {'$' + f'{per_doc:.4f}':>12}")
        lines.append(f"  por cada 100         {'$' + f'{per_doc * 100:.2f}':>12}")

    lines.append("")
    lines.append(f"  Tarifa de {model}: ${PRICES[model][0]} entrada y")
    lines.append(f"  ${PRICES[model][1]} salida por millon de tokens.")
    return "\n".join(lines)
