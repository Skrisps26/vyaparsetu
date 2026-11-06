import asyncio
from decimal import Decimal

from app.config import Settings
from app.ledger import Ledger
from app.pipeline import Pipeline
from app.schemas import ConfirmRequest, ReviewedItem


def test_reviewed_mock_invoice_can_be_confirmed_without_becoming_unresolved(tmp_path):
    async def scenario():
        pipeline = Pipeline(Settings(use_mocks=True), Ledger(str(tmp_path / "ledger.sqlite3")))
        record = await pipeline.create_mock()
        while record.invoice is None:
            await asyncio.sleep(0)
        allowed = set(ReviewedItem.model_fields)
        reviewed = [{key: value for key, value in line.model_dump().items() if key in allowed} for line in record.invoice.items]
        request = ConfirmRequest(items=reviewed, customer_name="Demo Kili", payment_mode="credit")
        saved = await pipeline.confirm(record.run_id, request)
        assert saved.invoice.total == Decimal("149.60")
        assert saved.balance_paise == 24960
        assert not saved.invoice.needs_review
        await pipeline.confirm(record.run_id, request)
        assert pipeline.ledger.snapshot()["accounts"][0]["balance"] == "249.60"
    asyncio.run(asyncio.wait_for(scenario(), timeout=3))
