"""Synthetic rules exercise date/condition behavior, never represent operative law."""
import json
from datetime import date

from app.gst_sources import local_tax_candidates, read_documents


def rule(identifier, rate, start, end=None, conditions=None):
    return {"id": identifier, "hsn": "1006", "description": "Synthetic test grain",
            "cgst": str(rate / 2), "sgst": str(rate / 2), "igst": str(rate),
            "cess": None, "conditions": conditions or [], "valuation_method": "ad_valorem",
            "effective_from": start, "effective_to": end, "notification": "SYNTHETIC TEST ONLY",
            "source_url": "https://taxinformation.cbic.gov.in/test-fixture-not-real",
            "sha256": "0" * 64, "page": "1", "excerpt": "Synthetic tax fixture",
            "reviewed": True}


def write_snapshot(directory, rules):
    (directory / "active_snapshot.json").write_text(json.dumps({"hsn": [{"code": "1006", "description": "Synthetic test grain"}], "rules": rules, "manifest": {"fixture_only": True}}))


def test_supply_date_selects_applicable_rule_without_latest_wins_guess(tmp_path):
    write_snapshot(tmp_path, [rule("before", 5, "2025-01-01", "2025-12-31"), rule("after", 18, "2026-01-01")])
    before, _, _ = local_tax_candidates("1006", date(2025, 12, 31), tmp_path)
    after, _, _ = local_tax_candidates("1006", date(2026, 1, 1), tmp_path)
    assert [(r["rule_id"], r["igst"]) for r in before] == [("before", "5")]
    assert [(r["rule_id"], r["igst"]) for r in after] == [("after", "18")]


def test_overlapping_packaging_rules_remain_distinct_review_choices(tmp_path):
    write_snapshot(tmp_path, [rule("loose", 0, "2025-01-01", conditions=["Loose unpackaged goods"]), rule("packed", 5, "2025-01-01", conditions=["Pre-packaged and labelled"])])
    candidates, _, _ = local_tax_candidates("test grain", date(2026, 1, 1), tmp_path)
    assert {r["rule_id"] for r in candidates} == {"loose", "packed"}
    assert all(r["conditions"] for r in candidates)


def test_unknown_classification_does_not_default_to_exempt(tmp_path):
    write_snapshot(tmp_path, [rule("grain", 5, "2025-01-01")])
    candidates, _, issues = local_tax_candidates("stainless spoon", date(2026, 1, 1), tmp_path)
    assert candidates == []
    assert any("unresolved" in issue for issue in issues)


def test_malformed_rule_is_not_activated_as_valid_rate(tmp_path):
    invalid = rule("bad", 5, "2025-01-01")
    invalid["igst"] = "NaN"
    write_snapshot(tmp_path, [invalid])
    candidates, _, issues = local_tax_candidates("1006", date(2026, 1, 1), tmp_path)
    assert candidates == []
    assert any("invalid" in issue for issue in issues)


def test_active_import_is_read_as_one_coherent_snapshot(tmp_path):
    write_snapshot(tmp_path, [rule("active", 5, "2025-01-01")])
    (tmp_path / "rate_rules.json").write_text("[]")
    _, rules, _ = read_documents(tmp_path)
    assert rules[0]["id"] == "active"
