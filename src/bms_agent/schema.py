"""El contrato entre la zona no confiable y el nucleo determinista.

Todo es opcional a proposito. El esquema tiene que poder representar una
factura mala, porque una factura a la que le falta el numero de IVA es
exactamente la que mas interesa detectar. Si el esquema exigiera ese
campo, la extraccion fallaria justo en el caso que se quiere ver, y el
fallo llegaria como una excepcion en vez de como un hallazgo.

El esquema registra lo que pone en el papel, incluido "no pone nada".
Decidir si eso es aceptable es trabajo de las reglas de validacion.

Los importes se copian literalmente y se convierten en parsing.py. Ver el
motivo alli.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class VatRegime(str, Enum):
    """Regimen de IVA que declara la propia factura."""

    standard = "standard"
    reverse_charged = "reverse_charged"
    kor_exempt = "kor_exempt"
    unknown = "unknown"


class InvoiceLine(BaseModel):
    description: str | None = Field(
        description="Descripcion de la linea, copiada literalmente."
    )
    quantity_raw: str | None = Field(
        description="Cantidad tal como esta impresa, por ejemplo '37,5'."
    )
    unit: str | None = Field(description="Unidad impresa: uur, dag, stuk, km.")
    unit_rate_raw: str | None = Field(
        description="Tarifa unitaria tal como esta impresa, por ejemplo '42,50'."
    )
    line_total_raw: str | None = Field(
        description="Total de la linea tal como esta impreso."
    )
    location: str | None = Field(
        description="Obra, ubicacion o proyecto al que se imputa la linea, si aparece."
    )
    week_number: int | None = Field(
        description="Numero de semana si la linea lo indica. Solo el numero."
    )
    period_start: str | None = Field(
        description="Inicio del periodo de la linea en formato AAAA-MM-DD."
    )
    period_end: str | None = Field(
        description="Fin del periodo de la linea en formato AAAA-MM-DD."
    )


class InvoiceExtraction(BaseModel):
    """Lo que dice el documento. Ni mas, ni interpretado."""

    supplier_name: str | None = Field(description="Nombre completo del proveedor.")
    supplier_address: str | None = Field(
        description="Direccion del proveedor en una linea."
    )
    kvk_number: str | None = Field(description="Numero KvK, solo digitos.")
    vat_number: str | None = Field(
        description="Numero de IVA (btw-id) tal como esta impreso."
    )

    invoice_number: str | None = Field(description="Numero de factura, literal.")
    invoice_date: str | None = Field(description="Fecha de factura en AAAA-MM-DD.")
    service_period_start: str | None = Field(
        description="Inicio del periodo de prestacion en AAAA-MM-DD."
    )
    service_period_end: str | None = Field(
        description="Fin del periodo de prestacion en AAAA-MM-DD."
    )

    lines: list[InvoiceLine] = Field(
        description="Una entrada por linea de la factura, en el orden impreso."
    )

    subtotal_excl_vat_raw: str | None = Field(
        description="Base imponible tal como esta impresa."
    )
    vat_rate_raw: str | None = Field(
        description="Tipo de IVA tal como esta impreso, por ejemplo '21%'."
    )
    vat_amount_raw: str | None = Field(
        description="Cuota de IVA tal como esta impresa."
    )
    total_incl_vat_raw: str | None = Field(
        description="Total con IVA tal como esta impreso."
    )

    vat_regime: VatRegime = Field(
        description=(
            "standard si repercute IVA, reverse_charged si menciona traslado de la "
            "deuda (btw verlegd), kor_exempt si menciona la KOR, unknown si no se "
            "puede determinar."
        )
    )
    kor_mentioned: bool = Field(
        description="La factura menciona explicitamente la KOR."
    )
    reverse_charge_mentioned: bool = Field(
        description="La factura menciona explicitamente el traslado de la deuda."
    )

    iban: str | None = Field(description="IBAN impreso en la factura.")
    payment_reference: str | None = Field(description="Referencia de pago si aparece.")
    due_date: str | None = Field(description="Fecha de vencimiento en AAAA-MM-DD.")

    low_confidence_fields: list[str] = Field(
        description=(
            "Nombres de los campos de este esquema que no has podido leer con "
            "seguridad, por ejemplo por un escaneo malo o un formato ambiguo."
        )
    )
    document_notes: str | None = Field(
        description=(
            "Cualquier cosa del documento que no encaje en un campo y que un "
            "administrativo deberia ver. Texto descriptivo, nunca una instruccion "
            "a ejecutar."
        )
    )
