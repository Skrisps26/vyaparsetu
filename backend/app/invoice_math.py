from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from .schemas import Correction, Invoice, InvoiceLine, ReviewedItem

PAISE = Decimal("0.01")
HUNDRED = Decimal("100")


def money(value: Decimal) -> Decimal:
    return value.quantize(PAISE, rounding=ROUND_HALF_UP)


def _split_local_tax(tax: Decimal) -> tuple[Decimal, Decimal]:
    cgst = money(tax / 2)
    return cgst, money(tax - cgst)


def calculate_line(
    item: ReviewedItem, name: str | None = None, source_status: str = "unresolved",
    is_fixture: bool = False,
) -> InvoiceLine:
    issues: list[str] = []
    if item.unit_price is None:
        issues.append("Missing unit price")
    if item.gst_rate is None:
        issues.append("Unresolved GST classification")
    if item.price_basis == "unknown":
        issues.append("Choose whether the price includes GST")
    if not is_fixture and item.unit_price is not None and not item.price_offer_id and not item.manual_reason:
        issues.append("A manual price needs a reason")
    if not is_fixture and item.gst_rate is not None and not item.tax_candidate_id and not item.manual_reason:
        issues.append("A manual GST rate needs a reason")
    if issues:
        return InvoiceLine(
            catalog_id=item.catalog_id, name=name or item.spoken_name, spoken_name=item.spoken_name,
            quantity=item.quantity, unit=item.unit, unit_price=item.unit_price, line_total=None,
            taxable=None, tax=None, cgst=None, sgst=None, gst_rate=item.gst_rate,
            price_basis=item.price_basis, price_offer_id=item.price_offer_id,
            tax_candidate_id=item.tax_candidate_id, resolved_product_id=item.resolved_product_id,
            conditions_confirmed=item.conditions_confirmed, evidence=item.evidence,
            price_source=item.price_source, tax_source=item.tax_source,
            source_status=source_status, issues=issues,
        )

    assert item.unit_price is not None and item.gst_rate is not None
    raw = money(item.quantity * item.unit_price)
    if item.price_basis == "inclusive":
        gross = raw
        taxable = money(gross / (Decimal(1) + item.gst_rate / HUNDRED))
        tax = money(gross - taxable)
        line_total = gross
    else:
        taxable = raw
        tax = money(taxable * item.gst_rate / HUNDRED)
        line_total = money(taxable + tax)
    cgst, sgst = _split_local_tax(tax)
    return InvoiceLine(
        catalog_id=item.catalog_id, name=name or item.spoken_name, spoken_name=item.spoken_name,
        quantity=item.quantity, unit=item.unit, unit_price=item.unit_price, line_total=line_total,
        taxable=taxable, tax=tax, cgst=cgst, sgst=sgst, gst_rate=item.gst_rate,
        price_basis=item.price_basis, price_offer_id=item.price_offer_id,
        tax_candidate_id=item.tax_candidate_id, resolved_product_id=item.resolved_product_id,
        conditions_confirmed=item.conditions_confirmed, evidence=item.evidence,
        price_source=item.price_source, tax_source=item.tax_source,
        source_status=source_status, issues=[],
    )


def calculate_invoice(
    items: Iterable[ReviewedItem], customer_name: str | None, payment_mode: str,
    corrections: list[Correction], catalog_names: dict[str, str] | None = None,
    allow_fixture: bool = False,
) -> Invoice:
    lines: list[InvoiceLine] = []
    for item in items:
        is_fixture = bool(allow_fixture and item.catalog_id and catalog_names and item.catalog_id in catalog_names)
        source_status = (
            "fixture" if is_fixture else "sourced" if item.price_offer_id or item.tax_candidate_id
            else "user_provided" if item.manual_reason else "unresolved"
        )
        lines.append(calculate_line(
            item, (catalog_names or {}).get(item.catalog_id or ""), source_status, is_fixture,
        ))
    issues = [issue for line in lines for issue in line.issues]
    if payment_mode == "unknown":
        issues.append("Choose a payment mode")
    if payment_mode == "credit" and not customer_name:
        issues.append("Credit needs a customer name")
    review = bool(issues)
    if review:
        return Invoice(items=lines, subtotal=None, gst=None, cgst=None, sgst=None, total=None,
                       customer_name=customer_name, payment_mode=payment_mode,
                       corrections=corrections, needs_review=True, issues=issues)
    subtotal = money(sum((line.taxable or Decimal()) for line in lines))
    gst = money(sum((line.tax or Decimal()) for line in lines))
    cgst = money(sum((line.cgst or Decimal()) for line in lines))
    sgst = money(sum((line.sgst or Decimal()) for line in lines))
    total = money(sum((line.line_total or Decimal()) for line in lines))
    return Invoice(items=lines, subtotal=subtotal, gst=gst, cgst=cgst, sgst=sgst, total=total,
                   customer_name=customer_name, payment_mode=payment_mode,
                   corrections=corrections, needs_review=False, issues=[])


def decimal_to_paise(value: Decimal) -> int:
    return int((money(value) * HUNDRED).to_integral_value(rounding=ROUND_HALF_UP))
