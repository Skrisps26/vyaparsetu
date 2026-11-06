import pytest
from pydantic import ValidationError

from app.schemas import InvoiceExtraction


def item(**changes):
    value = {"catalog_id": None, "spoken_name": "arbitrary product", "search_query": "brand pack", "quantity": "1", "unit": "piece", "unit_price": None}
    value.update(changes)
    return value


def test_arbitrary_product_is_valid_without_catalog_membership() -> None:
    extraction = InvoiceExtraction(items=[item()], customer_name=None, payment_mode="cash")
    assert extraction.items[0].catalog_id is None


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "Infinity"])
def test_invalid_quantities_are_rejected(quantity: str) -> None:
    with pytest.raises(ValidationError):
        InvoiceExtraction(items=[item(quantity=quantity)])


def test_invalid_correction_index_is_rejected() -> None:
    with pytest.raises(ValidationError):
        InvoiceExtraction(items=[item()], corrections=[{"item_index": 1, "field": "quantity", "old_value": "1", "new_value": "2"}])


def test_unknown_correction_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        InvoiceExtraction(items=[item()], corrections=[{"item_index": 0, "field": "total", "old_value": "1", "new_value": "2"}])
