from decimal import Decimal

from app.invoice_math import calculate_invoice
from app.providers.mock import mock_extraction
from app.schemas import ReviewedItem


def test_canonical_mock_oracle_and_correction() -> None:
    items, customer, payment, corrections = mock_extraction()
    invoice = calculate_invoice(items, customer, payment, corrections, {"demo-rice": "ഡെമോ അരി", "demo-soap": "ഡെമോ സോപ്പ്"}, allow_fixture=True)
    assert invoice.needs_review is False
    assert invoice.subtotal == Decimal("140.00")
    assert invoice.gst == Decimal("9.60")
    assert invoice.cgst == invoice.sgst == Decimal("4.80")
    assert invoice.total == Decimal("149.60")
    assert invoice.corrections[0].old_value == "2"
    assert invoice.corrections[0].new_value == "3"


def test_exclusive_and_inclusive_prices_do_not_double_count_tax() -> None:
    exclusive = ReviewedItem(spoken_name="manual", quantity="1", unit="piece", unit_price="100", gst_rate="5", price_basis="exclusive", manual_reason="shop quote")
    inclusive = ReviewedItem(spoken_name="manual", quantity="1", unit="piece", unit_price="105", gst_rate="5", price_basis="inclusive", manual_reason="shop quote")
    exclusive_bill = calculate_invoice([exclusive], None, "cash", [], {})
    inclusive_bill = calculate_invoice([inclusive], None, "cash", [], {})
    assert (exclusive_bill.subtotal, exclusive_bill.gst, exclusive_bill.total) == (Decimal("100.00"), Decimal("5.00"), Decimal("105.00"))
    assert (inclusive_bill.subtotal, inclusive_bill.gst, inclusive_bill.total) == (Decimal("100.00"), Decimal("5.00"), Decimal("105.00"))


def test_half_quantity_rounding_is_at_line_boundary() -> None:
    item = ReviewedItem(spoken_name="manual", quantity="0.5", unit="kg", unit_price="19.99", gst_rate="5", price_basis="exclusive", manual_reason="shop quote")
    invoice = calculate_invoice([item], None, "cash", [], {})
    assert (invoice.subtotal, invoice.gst, invoice.total) == (Decimal("10.00"), Decimal("0.50"), Decimal("10.50"))


def test_arbitrary_manual_rate_needs_reason_but_fixture_rate_does_not() -> None:
    arbitrary = ReviewedItem(spoken_name="new product", quantity="1", unit="piece", unit_price="10", gst_rate="5", price_basis="exclusive")
    fixture = ReviewedItem(catalog_id="demo-rice", spoken_name="rice", quantity="1", unit="kg", unit_price="40", gst_rate="5", price_basis="exclusive")
    assert calculate_invoice([arbitrary], None, "cash", [], {}).needs_review is True
    assert calculate_invoice([fixture], None, "cash", [], {"demo-rice": "ഡെമോ അരി"}).needs_review is True
    assert calculate_invoice([fixture], None, "cash", [], {"demo-rice": "ഡെമോ അരി"}, allow_fixture=True).needs_review is False
