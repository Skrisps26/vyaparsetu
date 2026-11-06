"""Explicit public-source smoke; never invokes speech or GPU providers."""
import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.lookup import LookupQuery, perform_lookup

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--query", required=True)
parser.add_argument("--pack-size")
parser.add_argument("--barcode")
parser.add_argument("--as-of-date", type=date.fromisoformat, default=date.today())
parser.add_argument("--mock", action="store_true", help="Use only explicitly synthetic lookup fixtures")
args = parser.parse_args()
request = LookupQuery(query=args.query, pack_size=args.pack_size, barcode=args.barcode, as_of_date=args.as_of_date)
print(json.dumps(asyncio.run(perform_lookup(request, args.mock)), ensure_ascii=False, indent=2))
