"""Source-separated discovery and evidence selection; never an autonomous buying agent."""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .gst_sources import local_tax_candidates, official_discovery
from .product_sources import barcode_identity, discover, now

router = APIRouter(prefix="/api", tags=["product evidence"])


class LookupQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=2, max_length=200)
    barcode: str | None = None
    pack_size: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=100)
    as_of_date: date = Field(default_factory=date.today)

    @field_validator("barcode")
    @classmethod
    def barcode_format(cls, value):
        if value and (not value.isascii() or not value.isdecimal() or len(value) not in {8, 12, 13, 14}):
            raise ValueError("Barcode must contain 8, 12, 13 or 14 decimal digits")
        return value or None


class RememberSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: str
    price_offer_id: str | None = None
    tax_candidate_id: str | None = None
    price_basis: Literal["inclusive", "exclusive"]
    conditions_confirmed: bool = False


class EvidenceStore:
    def __init__(self, path: str | Path | None = None):
        self.path = str(path or Path(os.getenv("DATABASE_PATH", "./data/vyaparsetu.sqlite3")).with_name("source-cache.sqlite3"))
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS lookups(id TEXT PRIMARY KEY, query_key TEXT, created REAL, payload TEXT);
            CREATE INDEX IF NOT EXISTS lookup_key ON lookups(query_key,created);
            CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY, kind TEXT, lookup_id TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS shop_selections(query_key TEXT PRIMARY KEY, payload TEXT);""")

    def connect(self):
        return sqlite3.connect(self.path)

    def save(self, query_key: str, payload: dict):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO lookups VALUES (?,?,?,?)", (payload["lookup_id"], query_key, datetime.now(timezone.utc).timestamp(), json.dumps(payload)))
            for kind in ["products", "price_offers", "tax_candidates", "sources"]:
                for record in payload[kind]:
                    db.execute("INSERT OR REPLACE INTO evidence VALUES (?,?,?,?)", (record["id"], kind, payload["lookup_id"], json.dumps(record)))

    def get(self, lookup_id: str):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM lookups WHERE id=?", (lookup_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def cached(self, query_key: str, max_age: int = 1800):
        with self.connect() as db:
            row = db.execute("SELECT payload,created FROM lookups WHERE query_key=? ORDER BY created DESC LIMIT 1", (query_key,)).fetchone()
        if not row:
            return None
        result = json.loads(row[0])
        result["cache_age_seconds"] = int(datetime.now(timezone.utc).timestamp() - row[1])
        result["cache_stale"] = result["cache_age_seconds"] > max_age
        return result

    def evidence(self, identifier: str, kind: str):
        with self.connect() as db:
            row = db.execute("SELECT payload,lookup_id FROM evidence WHERE id=? AND kind=?", (identifier, kind)).fetchone()
        if not row:
            raise ValueError("Selected evidence was not found; search again")
        return json.loads(row[0]), row[1]

    def remember(self, query_key: str, payload: dict):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO shop_selections VALUES (?,?)", (query_key, json.dumps(payload)))

    def remembered(self, query_key: str):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM shop_selections WHERE query_key=?", (query_key,)).fetchone()
        return json.loads(row[0]) if row else None


def mock_lookup(request: LookupQuery) -> dict:
    identifier = uuid4().hex
    product_id, offer_id, tax_id = (uuid4().hex for _ in range(3))
    return {"lookup_id": identifier, "products": [{"id": product_id, "name": f"Demo lookup fixture — {request.query}", "brand": "Fictional Demo Brand", "barcode": request.barcode, "pack_size": request.pack_size or "1 pack", "source_id": "fixture-product", "match_status": "candidate"}],
            "price_offers": [{"id": offer_id, "product_id": product_id, "amount": "42.00", "currency": "INR", "price_kind": "selling", "price_basis": "inclusive", "seller": "Synthetic Demo Shop", "location": "Demo town", "observed_at": None, "valid_until": None, "source_id": "fixture-product"}],
            "tax_candidates": [{"id": tax_id, "hsn": None, "description": "Illustrative fixture GST — not an official classification", "cgst": "2.5", "sgst": "2.5", "igst": "5", "cess": None, "conditions": [], "valuation_method": "ad_valorem", "effective_from": None, "effective_to": None, "source_id": "fixture-tax", "status": "fixture"}],
            "sources": [{"id": "fixture-product", "url": "https://example.invalid/synthetic-product", "title": "Synthetic lookup fixture", "publisher": "VyaparSetu demo", "retrieved_at": now(), "kind": "fixture", "excerpt": "Mock values; not a real market price", "status": "fixture"}, {"id": "fixture-tax", "url": "https://example.invalid/synthetic-tax", "title": "Illustrative GST fixture", "publisher": "VyaparSetu demo", "retrieved_at": now(), "kind": "fixture", "excerpt": "Not an official tax source", "status": "fixture"}],
            "status": "ready", "source": "mock", "issues": ["Synthetic lookup fixture — enable live mode for real public product references"], "as_of_date": str(request.as_of_date)}


async def perform_lookup(request: LookupQuery, use_mocks: bool, store: EvidenceStore | None = None) -> dict:
    store = store or EvidenceStore()
    query_key = json.dumps({**request.model_dump(mode="json"), "mock": use_mocks}, sort_keys=True)
    cached = store.cached(query_key)
    remembered = store.remembered(query_key)
    if cached and not cached["cache_stale"]:
        cached["remembered_selection"] = remembered
        return cached
    if use_mocks:
        result = mock_lookup(request)
        store.save(query_key, result)
        return result
    result = {"lookup_id": uuid4().hex, "products": [], "price_offers": [], "tax_candidates": [], "sources": [], "status": "partial", "source": "live", "issues": [], "as_of_date": str(request.as_of_date)}
    tax, evidence, issues = local_tax_candidates(request.query, request.as_of_date)
    result["tax_candidates"].extend(tax)
    result["sources"].extend(evidence)
    result["issues"].extend(issues)
    try:
        async with asyncio.timeout(15):
            if request.barcode:
                products, offers, evidence, issues = await barcode_identity(request.barcode)
                result["products"].extend(products)
                result["price_offers"].extend(offers)
                result["sources"].extend(evidence)
                result["issues"].extend(issues)
            products, offers, evidence, issues = await discover(request.query, request.pack_size, request.location)
            result["products"].extend(products)
            result["price_offers"].extend(offers)
            result["sources"].extend(evidence)
            result["issues"].extend(issues)
            if not tax:
                result["sources"].extend(await official_discovery(request.query))
    except TimeoutError:
        result["issues"].append("Search deadline reached; keep available evidence or enter a reviewed shop price")
    if not result["sources"]:
        result["sources"] = await official_discovery("")
    if not result["products"] and not result["price_offers"]:
        result["status"] = "source_unavailable" if result["issues"] else "not_found"
        if cached:
            cached["issues"] = list(dict.fromkeys(cached["issues"] + ["Upstream unavailable; showing an older observation, not a current price"]))
            return cached
    elif result["price_offers"] and result["tax_candidates"]:
        result["status"] = "ready"
    result["remembered_selection"] = remembered
    store.save(query_key, result)
    return result


def resolve_review_items(items: list[dict], store: EvidenceStore | None = None, as_of: date | None = None) -> list[dict]:
    """Resolve selected IDs from server snapshots before invoice calculation."""
    store = store or EvidenceStore()
    resolved = []
    for item in items:
        record = dict(item)
        evidence = []
        product_id = record.get("resolved_product_id")
        product = store.evidence(product_id, "products")[0] if product_id else None
        offer_id, tax_id = record.get("price_offer_id"), record.get("tax_candidate_id")
        if offer_id:
            offer, lookup_id = store.evidence(offer_id, "price_offers")
            if not product or offer["product_id"] != product["id"]:
                raise ValueError("Selected price belongs to a different product")
            if offer["currency"] != "INR" or offer["price_kind"] == "mrp":
                raise ValueError("Choose an INR selling/observed price or explicitly enter your shop price")
            record["unit_price"] = offer["amount"]
            record["price_source"] = "observed"
            evidence.append({"kind": "price", "record": offer, "sources": store.get(lookup_id)["sources"], "product": product})
        if tax_id:
            tax, lookup_id = store.evidence(tax_id, "tax_candidates")
            if tax.get("status") not in {"snapshot", "fixture"}:
                raise ValueError("Tax source is not a reviewed rule")
            if tax.get("status") == "fixture" and os.getenv("USE_MOCKS", "true").lower() != "true":
                raise ValueError("Synthetic GST fixtures cannot be used in live invoices")
            if tax.get("conditions") and not record.get("conditions_confirmed"):
                raise ValueError("Confirm the classification conditions before using this tax rule")
            if tax.get("cess") or tax.get("valuation_method") != "ad_valorem":
                raise ValueError("This rule needs specific tax/cess valuation review; ordinary GST calculation is not applicable")
            supply_date = as_of or date.today()
            if (tax.get("effective_from") and date.fromisoformat(tax["effective_from"]) > supply_date) or (tax.get("effective_to") and supply_date > date.fromisoformat(tax["effective_to"])):
                raise ValueError("Selected GST snapshot does not cover the supply date")
            record["gst_rate"] = tax["igst"]
            record["tax_source"] = tax["status"]
            evidence.append({"kind": "tax", "record": tax, "sources": store.get(lookup_id)["sources"]})
        if evidence:
            record["evidence"] = evidence
        resolved.append(record)
    return resolved


@router.post("/lookup")
async def lookup(request: LookupQuery):
    return await perform_lookup(request, os.getenv("USE_MOCKS", "true").lower() == "true")


@router.get("/lookup/{lookup_id}")
async def lookup_snapshot(lookup_id: str):
    result = EvidenceStore().get(lookup_id)
    if not result:
        raise HTTPException(404, "Lookup not found")
    return result


@router.post("/lookup/{lookup_id}/remember")
async def remember_selection(lookup_id: str, selection: RememberSelection):
    store = EvidenceStore()
    snapshot = store.get(lookup_id)
    if not snapshot:
        raise HTTPException(404, "Lookup not found")
    if not any(product["id"] == selection.product_id for product in snapshot["products"]):
        raise HTTPException(422, "Product does not belong to this lookup")
    try:
        resolve_review_items([{"resolved_product_id": selection.product_id, **selection.model_dump(exclude={"product_id"})}], store)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    with store.connect() as db:
        row = db.execute("SELECT query_key FROM lookups WHERE id=?", (lookup_id,)).fetchone()
    store.remember(row[0], selection.model_dump(mode="json"))
    return {"remembered": True, "notice": "A saved observation, not a guarantee of a future price or tax classification"}
