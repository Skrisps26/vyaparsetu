"""Thin adapters over OFF, Open Prices, DDGS and extruct; no generated prices."""
from __future__ import annotations

import asyncio
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4

import extruct
import httpx
from ddgs import DDGS
from starlette.concurrency import run_in_threadpool

from .source_fetch import USER_AGENT, fetch_public_html, public_url

_OFF_LIMIT = asyncio.Lock()
_OFF_LAST = 0.0


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def key() -> str:
    return uuid4().hex


def normalized(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value).casefold())


def source(url: str, title: str, kind: str, excerpt: str = "", **extra) -> dict:
    return {"id": key(), "url": url, "title": title, "publisher": httpx.URL(url).host,
            "retrieved_at": now(), "kind": kind, "excerpt": excerpt[:1500], "status": "observed", **extra}


def search_web(query: str, maximum: int = 5) -> list[dict]:
    return DDGS(timeout=8).text(query, region="in-en", max_results=maximum, backend="auto")


async def barcode_identity(barcode: str) -> tuple[list, list, list, list]:
    """Reads are anonymous; respect OFF's 15 product reads/minute/IP limit."""
    global _OFF_LAST
    products, offers, sources, issues = [], [], [], []
    url = f"https://world.openfoodfacts.org/api/v3.6/product/{barcode}.json"
    try:
        async with _OFF_LIMIT:
            loop = asyncio.get_running_loop()
            if loop.time() - _OFF_LAST < 4:
                return [], [], [], ["Product source rate limit: wait a few seconds before another barcode lookup"]
            _OFF_LAST = loop.time()
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=7) as client:
            response = await client.get(url, params={"fields": "code,product_name,brands,quantity,countries_tags,categories_tags"})
            response.raise_for_status()
            payload = response.json()
            product = payload.get("product") or {}
            if str(product.get("code", payload.get("code", ""))) != barcode or not product.get("product_name"):
                return [], [], [], ["Product not found in Open Food Facts"]
            record = source(url, "Open Food Facts", "open_food_facts", product.get("product_name", ""))
            sources.append(record)
            identity = {"id": key(), "name": product["product_name"], "brand": product.get("brands"),
                        "barcode": barcode, "pack_size": product.get("quantity"), "source_id": record["id"], "match_status": "barcode_match"}
            products.append(identity)
            price_url = "https://prices.openfoodfacts.org/api/v1/prices"
            prices = await client.get(price_url, params={"product_code": barcode, "currency": "INR", "size": 20, "order_by": "-date"})
            prices.raise_for_status()
            for observation in prices.json().get("items", []):
                if observation.get("currency") != "INR":
                    continue
                amount = decimal_price(observation.get("price"))
                if amount is None:
                    continue
                evidence = source(f"{price_url}/{observation['id']}", "Open Prices observation", "open_prices", f"Observed {amount} INR on {observation.get('date', 'unknown date')}")
                sources.append(evidence)
                offers.append({"id": key(), "product_id": identity["id"], "amount": amount, "currency": "INR", "price_kind": "observed", "price_basis": "unknown", "seller": None, "location": None, "observed_at": observation.get("date"), "valid_until": None, "source_id": evidence["id"]})
            if not offers:
                issues.append("No INR price observation found; public coverage is incomplete")
    except (httpx.HTTPError, ValueError, KeyError) as error:
        issues.append(f"Barcode/observed-price source unavailable: {type(error).__name__}")
    return products, offers, sources, issues


def decimal_price(value) -> str | None:
    try:
        amount = Decimal(str(value))
        return str(amount) if amount.is_finite() and amount >= 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _nodes(value):
    if isinstance(value, list):
        for child in value:
            yield from _nodes(child)
    elif isinstance(value, dict):
        yield value
        if "@graph" in value:
            yield from _nodes(value["@graph"])


def structured_products(html: str, url: str, pack_size: str | None = None) -> tuple[list, list, list]:
    """Publisher structured offers only. User still confirms product identity and pack."""
    metadata = extruct.extract(html, base_url=url, syntaxes=["json-ld", "microdata"], uniform=True)
    products, offers, sources = [], [], []
    for node in _nodes([metadata.get("json-ld", []), metadata.get("microdata", [])]):
        kinds = node.get("@type", [])
        kinds = [kinds] if isinstance(kinds, str) else kinds
        if not any(str(kind).rsplit("/", 1)[-1] == "Product" for kind in kinds):
            continue
        name = node.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        brand = node.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name")
        if not isinstance(brand, (str, type(None))):
            brand = None
        size = node.get("size") or node.get("weight")
        if isinstance(size, dict):
            size = f"{size.get('value', '')}{size.get('unitText', size.get('unitCode', ''))}"
        size = size if isinstance(size, str) else None
        # Product name can itself carry a pack size. Never infer price/unit conversion.
        pack_matches = not pack_size or normalized(pack_size) in normalized(f"{name} {size or ''}")
        evidence = source(url, name, "publisher_product", name)
        identity = {"id": key(), "name": name, "brand": brand, "barcode": next((str(node[f]) for f in ["gtin13", "gtin14", "gtin12", "gtin8", "gtin"] if node.get(f)), None), "pack_size": size or (pack_size if pack_matches else None), "source_id": evidence["id"], "match_status": "candidate"}
        products.append(identity)
        sources.append(evidence)
        if not pack_matches:
            continue
        values = node.get("offers", [])
        values = [values] if isinstance(values, dict) else values
        if not isinstance(values, list):
            continue
        for offer in values:
            if not isinstance(offer, dict) or "AggregateOffer" in str(offer.get("@type", "")):
                continue
            amount = decimal_price(offer.get("price"))
            currency = offer.get("priceCurrency")
            if amount is None or currency != "INR":
                continue
            seller = offer.get("seller")
            seller = seller.get("name") if isinstance(seller, dict) else seller
            offers.append({"id": key(), "product_id": identity["id"], "amount": amount, "currency": currency, "price_kind": "selling", "price_basis": "unknown", "seller": seller if isinstance(seller, str) else None, "location": None, "observed_at": None, "valid_until": offer.get("priceValidUntil"), "source_id": evidence["id"]})
    return products, offers, sources


async def discover(query: str, pack_size: str | None, location: str | None) -> tuple[list, list, list, list]:
    products, offers, sources, issues = [], [], [], []
    try:
        results = await run_in_threadpool(search_web, f"{query} {pack_size or ''} price India {location or ''}")
    except Exception as error:
        return [], [], [], [f"Web search unavailable: {type(error).__name__}"]
    for result in results:
        url = result.get("href", "")
        if public_url(url):
            sources.append(source(url, result.get("title", "Product search result"), "search_link", result.get("body", ""), status="unreviewed"))
    semaphore = asyncio.Semaphore(2)

    async def inspect(result):
        url = result.get("href", "")
        if not public_url(url):
            return
        try:
            async with semaphore:
                html = await fetch_public_html(url)
                found, prices, evidence = await run_in_threadpool(structured_products, html, url, pack_size)
                products.extend(found)
                offers.extend(prices)
                sources.extend(evidence)
        except Exception:
            issues.append(f"Could not inspect {httpx.URL(url).host}; open the source link or enter a shop price")
    await asyncio.gather(*(inspect(result) for result in results[:3]))
    if not offers:
        issues.append("No matching structured INR offer found; search links are not verified prices")
    return products, offers, sources, issues
