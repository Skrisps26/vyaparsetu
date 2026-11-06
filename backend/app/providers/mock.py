from __future__ import annotations

from .types import SpeechResult
from ..schemas import Correction, InvoiceExtraction, ReviewedItem

CANONICAL_TRANSCRIPT = "ഡെമോ അരി two kilo, അല്ല three kilo, കിലോയ്ക്ക് forty rupees; ഡെമോ സോപ്പ് one piece twenty rupees; ഡെമോ കിളിയുടെ അക്കൗണ്ടിൽ കടമായി ഇടൂ."
MOCK_REPLY = "ബിൽ തുക നൂറ്റി നാൽപ്പത്തൊമ്പത് രൂപ അറുപത് പൈസ. ഡെമോ അക്കൗണ്ടിൽ ചേർത്തു. ആകെ ബാക്കി ഇരുന്നൂറ്റി നാൽപ്പത്തൊമ്പത് രൂപ അറുപത് പൈസ."


def mock_speech() -> SpeechResult:
    return SpeechResult(transcript=CANONICAL_TRANSCRIPT, detected_language_code="ml-IN", provider_elapsed_ms=None)


def mock_extraction() -> tuple[list[ReviewedItem], str, str, list[Correction]]:
    return (
        [
            ReviewedItem(catalog_id="demo-rice", spoken_name="ഡെമോ അരി", search_query=None,
                         quantity="3", unit="kg", unit_price="40", gst_rate="5", price_basis="exclusive"),
            ReviewedItem(catalog_id="demo-soap", spoken_name="ഡെമോ സോപ്പ്", search_query=None,
                         quantity="1", unit="piece", unit_price="20", gst_rate="18", price_basis="exclusive"),
        ],
        "Demo Kili",
        "credit",
        [Correction(item_index=0, field="quantity", old_value="2", new_value="3")],
    )


def mock_extraction_schema() -> InvoiceExtraction:
    items, customer_name, payment_mode, corrections = mock_extraction()
    return InvoiceExtraction(items=items, customer_name=customer_name, payment_mode=payment_mode, corrections=corrections)
