from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Unit = Literal["kg", "g", "l", "ml", "piece", "pack"]
PaymentMode = Literal["cash", "upi", "credit", "unknown"]
PriceBasis = Literal["inclusive", "exclusive", "unknown"]
RunSource = Literal["mock", "live", "cached", "manual"]


def _finite(value: Decimal | None) -> Decimal | None:
    if value is not None and not value.is_finite():
        raise ValueError("decimal values must be finite")
    return value


class ExtractionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    catalog_id: str | None = None
    spoken_name: str = Field(min_length=1, max_length=200)
    search_query: str | None = Field(default=None, max_length=200)
    quantity: Decimal
    unit: Unit
    unit_price: Decimal | None = None

    @field_validator("quantity")
    @classmethod
    def positive_quantity(cls, value: Decimal) -> Decimal:
        _finite(value)
        if value <= 0:
            raise ValueError("quantity must be positive")
        return value

    @field_validator("unit_price")
    @classmethod
    def valid_price(cls, value: Decimal | None) -> Decimal | None:
        _finite(value)
        if value is not None and value < 0:
            raise ValueError("unit_price must not be negative")
        return value


class Correction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_index: int = Field(ge=0)
    field: Literal["quantity", "unit", "unit_price", "item"]
    old_value: str = Field(min_length=1, max_length=200)
    new_value: str = Field(min_length=1, max_length=200)


class InvoiceExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ExtractionItem] = Field(min_length=1, max_length=100)
    customer_name: str | None = Field(default=None, max_length=120)
    payment_mode: PaymentMode = "unknown"
    corrections: list[Correction] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def check_corrections(self) -> "InvoiceExtraction":
        for correction in self.corrections:
            if correction.item_index >= len(self.items):
                raise ValueError("correction item_index is outside items")
        return self


class ReviewedItem(ExtractionItem):
    gst_rate: Decimal | None = None
    price_basis: PriceBasis = "unknown"
    price_offer_id: str | None = None
    tax_candidate_id: str | None = None
    resolved_product_id: str | None = None
    manual_reason: str | None = Field(default=None, max_length=500)
    conditions_confirmed: bool = False
    evidence: list[dict[str, object]] = Field(default_factory=list, max_length=20)
    price_source: str | None = Field(default=None, max_length=100)
    tax_source: str | None = Field(default=None, max_length=100)

    @field_validator("gst_rate")
    @classmethod
    def valid_rate(cls, value: Decimal | None) -> Decimal | None:
        _finite(value)
        if value is not None and value < 0:
            raise ValueError("gst_rate must not be negative")
        return value


class DraftRequest(InvoiceExtraction):
    items: list[ReviewedItem] = Field(min_length=1, max_length=100)


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ReviewedItem] | None = Field(default=None, min_length=1, max_length=100)
    customer_name: str | None = Field(default=None, max_length=120)
    payment_mode: PaymentMode | None = None


class InvoiceLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    catalog_id: str | None
    name: str
    spoken_name: str
    quantity: Decimal
    unit: Unit
    unit_price: Decimal | None
    line_total: Decimal | None
    taxable: Decimal | None
    tax: Decimal | None
    cgst: Decimal | None
    sgst: Decimal | None
    gst_rate: Decimal | None
    price_basis: PriceBasis
    price_offer_id: str | None = None
    tax_candidate_id: str | None = None
    resolved_product_id: str | None = None
    conditions_confirmed: bool = False
    evidence: list[dict[str, object]] = Field(default_factory=list)
    price_source: str | None = None
    tax_source: str | None = None
    source_status: Literal["fixture", "sourced", "user_provided", "unresolved"]
    issues: list[str] = Field(default_factory=list)


class Invoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[InvoiceLine]
    subtotal: Decimal | None
    gst: Decimal | None
    cgst: Decimal | None
    sgst: Decimal | None
    total: Decimal | None
    customer_name: str | None
    payment_mode: PaymentMode
    corrections: list[Correction]
    needs_review: bool
    issues: list[str] = Field(default_factory=list)


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    seq: int
    type: Literal[
        "stage.started", "transcript.ready", "invoice.ready", "ledger.updated",
        "reply.ready", "stage.finished", "run.completed", "run.failed",
        "lookup.started", "lookup.ready",
    ]
    source: RunSource
    payload: dict[str, object] = Field(default_factory=dict)


class LookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=2, max_length=200)
    barcode: str | None = None
    pack_size: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=120)
    as_of_date: date | None = None

    @field_validator("barcode")
    @classmethod
    def barcode_shape(cls, value: str | None) -> str | None:
        if value is not None and (not value.isdecimal() or len(value) not in {8, 12, 13, 14}):
            raise ValueError("barcode must contain 8, 12, 13, or 14 decimal digits")
        return value
