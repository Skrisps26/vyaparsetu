"""Import explicitly reviewed official files. No undocumented GSTN endpoints."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.gst_sources import DATA_DIR, OFFICIAL_HOSTS, TaxRule, read_documents
from openpyxl import load_workbook
from pypdf import PdfReader


def sha256(path: Path) -> str:
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def official(url: str):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS or parsed.username:
        raise ValueError("Source must be an official HTTPS GSTN, CBIC, Gazette or GST Council URL")


def activate(directory: Path, hsn, rules, manifest):
    """One atomic activation: readers never observe a half-imported index."""
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"hsn": hsn, "rules": rules, "manifest": manifest}
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf8", dir=directory, delete=False, suffix=".staging") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    try:
        os.replace(temporary, directory / "active_snapshot.json")
    finally:
        temporary.unlink(missing_ok=True)


def import_hsn(args):
    path = Path(args.input)
    if path.suffix.lower() != ".xlsx":
        raise ValueError("Use an official .xlsx file; convert legacy .xls preserving provenance first")
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook[args.sheet] if args.sheet else workbook.worksheets[0]
        rows = sheet.iter_rows(values_only=True)
        headers = [str(value).strip() if value is not None else "" for value in next(rows)]
        if not args.code_column or not args.description_column:
            print(json.dumps({"sheets": workbook.sheetnames, "sheet": sheet.title, "headers": headers, "action": "Re-run with --code-column and --description-column; nothing imported"}, ensure_ascii=False))
            return
        if not args.source_url or not args.retrieved_at:
            raise ValueError("--source-url and --retrieved-at are required to activate an HSN import")
        official(args.source_url)
        date.fromisoformat(args.retrieved_at)
        if args.code_column not in headers or args.description_column not in headers:
            raise ValueError("Explicit column names must match the displayed workbook headers")
        ci, di = headers.index(args.code_column), headers.index(args.description_column)
        entries = []
        for number, row in enumerate(rows, 2):
            code, description = row[ci], row[di]
            if code is None and description is None:
                continue
            code = str(code).strip()
            if not code.isdecimal() or len(code) not in {2, 4, 6, 8} or not isinstance(description, str) or not description.strip():
                raise ValueError(f"Invalid code/description at Excel row {number}; no import activated")
            entries.append({"code": code, "description": description.strip()})
        if not entries:
            raise ValueError("The selected sheet has no valid HSN entries")
        _, rules, manifest = read_documents(Path(args.output))
        manifest["hsn_source"] = {"url": args.source_url, "retrieved_at": args.retrieved_at, "filename": path.name, "sha256": sha256(path), "sheet": sheet.title, "status": "reviewed", "import_version": 1}
        activate(Path(args.output), entries, rules, manifest)
        print(json.dumps({"activated": True, "hsn_records": len(entries), "source_sha256": manifest["hsn_source"]["sha256"]}))
    finally:
        workbook.close()


def import_rates(args):
    rules_file, manifest_file = Path(args.rules), Path(args.manifest)
    values = json.loads(rules_file.read_text(encoding="utf8"))
    manifest = json.loads(manifest_file.read_text(encoding="utf8"))
    if not isinstance(values, list) or not values:
        raise ValueError("Rules must be a non-empty JSON list of reviewed records")
    sources = manifest.get("rate_sources", [])
    if not sources:
        raise ValueError("Manifest must identify rate_sources with local_file, url and sha256")
    documents = {}
    for item in sources:
        official(item["url"])
        document = (manifest_file.parent / item["local_file"]).resolve()
        digest = sha256(document)
        if digest.lower() != item["sha256"].lower():
            raise ValueError(f"Source checksum mismatch: {document.name}")
        reader = PdfReader(document)
        documents[(item["url"], digest.lower())] = reader
    parsed = [TaxRule.model_validate(value) for value in values]
    if len({rule.id for rule in parsed}) != len(parsed):
        raise ValueError("Rule IDs must be unique")
    for rule in parsed:
        official(rule.source_url)
        if not rule.reviewed:
            raise ValueError(f"Rule {rule.id} requires human review before activation")
        reader = documents.get((rule.source_url, rule.sha256.lower()))
        if reader is None:
            raise ValueError(f"Rule {rule.id} has no matching source PDF")
        try:
            page = reader.pages[int(rule.page) - 1]
        except (ValueError, IndexError):
            raise ValueError(f"Rule {rule.id} must reference an existing one-based PDF page") from None
        text = " ".join((page.extract_text() or "").split()).casefold()
        if " ".join(rule.excerpt.split()).casefold() not in text:
            raise ValueError(f"Rule {rule.id} excerpt was not found on its source page")
    hsn, _, previous = read_documents(Path(args.output))
    previous.update(manifest)
    activate(Path(args.output), hsn, [rule.model_dump(mode="json") for rule in parsed], previous)
    print(json.dumps({"activated": True, "reviewed_rules": len(parsed), "notice": "Snapshot coverage only; this does not certify no later amendments exist"}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DATA_DIR), help="Local activated source directory")
    commands = parser.add_subparsers(dest="command", required=True)
    hsn = commands.add_parser("hsn", help="Inspect workbook headers, or import with explicit columns and provenance")
    hsn.add_argument("--input", required=True)
    for name in ["sheet", "code-column", "description-column", "source-url", "retrieved-at"]:
        hsn.add_argument(f"--{name}")
    hsn.set_defaults(action=import_hsn)
    rates = commands.add_parser("rates", help="Validate reviewed rules against official PDF files and atomically activate")
    rates.add_argument("--rules", required=True)
    rates.add_argument("--manifest", required=True)
    rates.set_defaults(action=import_rates)
    args = parser.parse_args()
    try:
        args.action(args)
    except (ValueError, OSError, KeyError, StopIteration) as error:
        parser.exit(2, f"Import rejected: {error}\n")


if __name__ == "__main__":
    main()
