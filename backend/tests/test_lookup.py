"""Consumer-visible identity/price boundaries; all page contents are synthetic fixtures."""
import json
from datetime import date

import pytest

from app.lookup import EvidenceStore, LookupQuery, mock_lookup, resolve_review_items
from app.product_sources import structured_products
from app.source_fetch import public_url


def page(name="Demo grain 100g", price="42", currency="INR", kind="Offer"):
    data = {"@context": "https://schema.org", "@type": "Product", "name": name,
            "offers": {"@type": kind, "price": price, "priceCurrency": currency}}
    return '<script type="application/ld+json">' + json.dumps(data) + '</script>'


def test_same_name_different_pack_does_not_supply_requested_pack_price():
    products, offers, _ = structured_products(page(), "https://example.test/product", "500 g")
    assert products[0]["name"] == "Demo grain 100g"
    assert offers == []


def test_exact_pack_offer_has_explicit_currency_and_unknown_tax_inclusion():
    products, offers, _ = structured_products(page(), "https://example.test/product", "100 g")
    assert offers[0]["amount"] == "42"
    assert offers[0]["product_id"] == products[0]["id"]
    assert offers[0]["price_basis"] == "unknown"


@pytest.mark.parametrize("options", [{"currency": ""}, {"currency": "USD"}, {"price": "NaN"}, {"price": "-1"}, {"kind": "AggregateOffer"}])
def test_non_billable_publisher_offer_never_becomes_a_price(options):
    _, offers, _ = structured_products(page(**options), "https://example.test/product")
    assert offers == []


def fixture_store(tmp_path):
    store = EvidenceStore(tmp_path / "evidence.sqlite3")
    snapshot = mock_lookup(LookupQuery(query="Outside catalog product"))
    store.save("fixture", snapshot)
    return store, snapshot


def selection(snapshot):
    return {"resolved_product_id": snapshot["products"][0]["id"],
            "price_offer_id": snapshot["price_offers"][0]["id"], "price_basis": "inclusive"}


def test_evidence_selection_uses_server_price_not_edited_client_price(tmp_path):
    store, snapshot = fixture_store(tmp_path)
    reviewed = resolve_review_items([{**selection(snapshot), "unit_price": "0.01"}], store)
    assert reviewed[0]["unit_price"] == "42.00"
    assert reviewed[0]["evidence"][0]["product"]["name"].startswith("Demo lookup fixture")


def test_mismatched_product_cannot_borrow_another_products_offer(tmp_path):
    store, first = fixture_store(tmp_path)
    second = mock_lookup(LookupQuery(query="Different pack"))
    store.save("second", second)
    with pytest.raises(ValueError, match="different product"):
        resolve_review_items([{**selection(first), "resolved_product_id": second["products"][0]["id"]}], store)


def test_fixture_tax_cannot_cross_into_live_billing(tmp_path, monkeypatch):
    store, snapshot = fixture_store(tmp_path)
    monkeypatch.setenv("USE_MOCKS", "false")
    with pytest.raises(ValueError, match="Synthetic GST"):
        resolve_review_items([{**selection(snapshot), "tax_candidate_id": snapshot["tax_candidates"][0]["id"]}], store)


def test_unknown_evidence_requires_new_search(tmp_path):
    store = EvidenceStore(tmp_path / "empty.sqlite3")
    with pytest.raises(ValueError, match="not found"):
        resolve_review_items([{"resolved_product_id": "not-present"}], store)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:pass@example.org", "https://example.org:8080/x", "javascript:alert(1)"])
def test_only_normal_public_http_links_enter_fetch_path(url):
    assert not public_url(url)


def test_invalid_barcode_is_not_silently_changed():
    with pytest.raises(ValueError):
        LookupQuery(query="Demo", barcode="123-not-a-code")
