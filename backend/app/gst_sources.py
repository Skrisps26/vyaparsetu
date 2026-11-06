"""Search reviewed legal snapshots. Missing law is unknown, never zero-rated."""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .product_sources import key, now, search_web, source
from starlette.concurrency import run_in_threadpool

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "gst"
OFFICIAL_HOSTS = {"taxinformation.cbic.gov.in", "egazette.gov.in", "gstcouncil.gov.in", "www.gstcouncil.gov.in", "services.gst.gov.in"}


class TaxRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    hsn: str = Field(pattern=r"^\d{2,8}$")
    description: str = Field(min_length=3)
    cgst: Decimal = Field(ge=0, le=100, allow_inf_nan=False)
    sgst: Decimal = Field(ge=0, le=100, allow_inf_nan=False)
    igst: Decimal = Field(ge=0, le=100, allow_inf_nan=False)
    cess: dict | None = None
    conditions: list[str] = Field(default_factory=list)
    valuation_method: str = "ad_valorem"
    effective_from: date
    effective_to: date | None = None
    notification: str
    source_url: str
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    page: str
    excerpt: str = Field(min_length=3)
    reviewed: bool

    @model_validator(mode="after")
    def valid_dates(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to precedes effective_from")
        if self.cgst + self.sgst != self.igst:
            raise ValueError("CGST plus SGST must equal IGST")
        return self


def read_documents(directory: Path = DATA_DIR) -> tuple[list, list, dict]:
    active = directory / "active_snapshot.json"
    if active.exists():
        snapshot = json.loads(active.read_text(encoding="utf8"))
        return snapshot["hsn"], snapshot["rules"], snapshot["manifest"]
    def read_file(name, default):
        path = directory / name
        return json.loads(path.read_text(encoding="utf8")) if path.exists() else default
    hsn = read_file("hsn_directory.json", [])
    rules = read_file("rate_rules.json", [])
    manifest = read_file("source_manifest.json", {})
    return hsn, rules, manifest


def local_tax_candidates(query: str, as_of: date, directory: Path = DATA_DIR) -> tuple[list, list, list]:
    hsn, raw_rules, manifest = read_documents(directory)
    found_codes: set[str] = set()
    # SQLite's maintained FTS tokenizer/search ranks the imported descriptions.
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE VIRTUAL TABLE descriptions USING fts5(code UNINDEXED, description)")
        db.executemany("INSERT INTO descriptions(code,description) VALUES (?,?)", [(str(item["code"]), item["description"]) for item in hsn])
        terms = [f'"{token.replace(chr(34), chr(34)+chr(34))}"' for token in query.split() if token.strip()]
        if terms:
            for row in db.execute("SELECT code FROM descriptions WHERE descriptions MATCH ? ORDER BY rank LIMIT 20", (" OR ".join(terms),)):
                found_codes.add(row[0])
        if query.isdecimal():
            found_codes.update(str(item["code"]) for item in hsn if str(item["code"]).startswith(query))
    candidates, sources, issues = [], [], []
    query_words = set(query.casefold().split())
    for raw in raw_rules:
        try:
            rule = TaxRule.model_validate(raw)
        except ValueError:
            issues.append("An invalid local tax rule was skipped; re-import the official source")
            continue
        if not rule.reviewed or not (rule.effective_from <= as_of and (rule.effective_to is None or as_of <= rule.effective_to)):
            continue
        text_match = any(word in rule.description.casefold() for word in query_words if len(word) >= 3)
        code_match = rule.hsn in found_codes or (query.isdecimal() and rule.hsn.startswith(query))
        if not code_match and not text_match:
            continue
        evidence = source(rule.source_url, rule.notification, "official_tax_snapshot", rule.excerpt, status="snapshot", sha256=rule.sha256, page=rule.page)
        sources.append(evidence)
        candidates.append({"id": key(), "rule_id": rule.id, "hsn": rule.hsn, "description": rule.description, "cgst": str(rule.cgst), "sgst": str(rule.sgst), "igst": str(rule.igst), "cess": rule.cess, "conditions": rule.conditions, "valuation_method": rule.valuation_method, "effective_from": str(rule.effective_from), "effective_to": str(rule.effective_to) if rule.effective_to else None, "source_id": evidence["id"], "status": "snapshot"})
    if not candidates:
        issues.append("GST is unresolved: import an applicable reviewed official rule or enter an explicitly reviewed manual rate")
    if not manifest:
        issues.append("No official GST source snapshot has been imported")
    return candidates, sources, list(dict.fromkeys(issues))


async def official_discovery(query: str) -> list:
    try:
        results = await run_in_threadpool(search_web, f"{query} HSN GST (site:taxinformation.cbic.gov.in OR site:gstcouncil.gov.in)", 3)
    except Exception:
        results = []
    from urllib.parse import urlsplit
    links = [source(result["href"], result.get("title", "Official classification source"), "official_search_link", result.get("body", ""), status="unreviewed") for result in results if urlsplit(result.get("href", "")).hostname in OFFICIAL_HOSTS]
    if not links:
        links = [source("https://services.gst.gov.in/services/searchhsnsac", "GSTN HSN search", "official_search_link", status="unreviewed"), source("https://taxinformation.cbic.gov.in/", "CBIC Tax Information Portal", "official_search_link", status="unreviewed")]
    return links
