from decimal import Decimal

from app.invoice_math import calculate_invoice
from app.ledger import Ledger
from app.providers.mock import mock_extraction


def canonical_invoice():
    items, customer, payment, corrections = mock_extraction()
    return calculate_invoice(items, customer, payment, corrections, {"demo-rice": "ഡെമോ അരി", "demo-soap": "ഡെമോ സോപ്പ്"}, allow_fixture=True)


def test_confirmation_is_idempotent_and_demo_credit_starts_at_one_hundred(tmp_path) -> None:
    ledger = Ledger(str(tmp_path / "ledger.sqlite3"))
    invoice = canonical_invoice()
    saved, balance, repeated = ledger.confirm("run-one", "demo:run-one", invoice)
    again, same_balance, repeated_again = ledger.confirm("run-one", "demo:run-one", invoice)
    assert saved.total == again.total == Decimal("149.60")
    assert balance == same_balance == 24960
    assert repeated is False
    assert repeated_again is True
    snapshot = ledger.snapshot()
    assert snapshot["accounts"] == [{"scope": "demo:run-one", "customer_name": "Demo Kili", "balance": "249.60"}]


def test_cash_and_upi_never_post_a_credit_balance(tmp_path) -> None:
    ledger = Ledger(str(tmp_path / "ledger.sqlite3"))
    invoice = canonical_invoice().model_copy(update={"payment_mode": "cash", "customer_name": None})
    ledger.confirm("cash-run", "live", invoice)
    assert ledger.snapshot()["accounts"] == []
