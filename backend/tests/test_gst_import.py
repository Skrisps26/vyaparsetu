"""Synthetic workbooks test import failure atomicity, not tax-law correctness."""
import argparse
import json

import pytest
from openpyxl import Workbook

from app.gst_sources import read_documents
from scripts.import_gst import activate, import_hsn


def workbook(path, rows):
    book = Workbook()
    sheet = book.active
    sheet.append(["HSN", "Description"])
    for row in rows:
        sheet.append(row)
    book.save(path)


def arguments(path, output, columns=True):
    return argparse.Namespace(input=str(path), output=str(output), sheet=None,
                              code_column="HSN" if columns else None,
                              description_column="Description" if columns else None,
                              source_url="https://services.gst.gov.in/services/searchhsnsac", retrieved_at="2026-01-01")


def test_workbook_inspection_does_not_activate_unreviewed_columns(tmp_path, capsys):
    path = tmp_path / "synthetic.xlsx"
    workbook(path, [("1006", "Synthetic grain")])
    output = tmp_path / "index"
    import_hsn(arguments(path, output, columns=False))
    assert json.loads(capsys.readouterr().out)["headers"] == ["HSN", "Description"]
    assert not output.exists()


def test_explicit_column_import_keeps_hsn_and_source_hash(tmp_path):
    path, output = tmp_path / "synthetic.xlsx", tmp_path / "index"
    workbook(path, [("0101", "Synthetic leading zero category"), ("1006", "Synthetic grain")])
    import_hsn(arguments(path, output))
    entries, _, manifest = read_documents(output)
    assert entries[0]["code"] == "0101"
    assert entries[1]["description"] == "Synthetic grain"
    assert manifest["hsn_source"]["url"].endswith("searchhsnsac")
    assert manifest["hsn_source"]["filename"] == "synthetic.xlsx"


def test_bad_row_leaves_previous_active_index_unchanged(tmp_path):
    path, output = tmp_path / "invalid.xlsx", tmp_path / "index"
    activate(output, [{"code": "1006", "description": "Previously activated synthetic grain"}], [], {"fixture_only": True})
    before = (output / "active_snapshot.json").read_bytes()
    workbook(path, [("1006", "Valid first row"), ("not-hsn", "Invalid second row")])
    with pytest.raises(ValueError, match="no import activated"):
        import_hsn(arguments(path, output))
    assert (output / "active_snapshot.json").read_bytes() == before
