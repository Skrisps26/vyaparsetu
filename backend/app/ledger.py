from __future__ import annotations

import json
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
import sqlite3
from typing import Iterator

from .invoice_math import decimal_to_paise
from .schemas import Invoice


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"cannot serialize {type(value)!r}")


class Ledger:
    def __init__(self, database_path: str) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS invoices (
                    run_id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    invoice_json TEXT NOT NULL,
                    total_paise INTEGER NOT NULL,
                    customer_name TEXT,
                    payment_mode TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS account_openings (
                    scope TEXT NOT NULL,
                    customer_name TEXT NOT NULL,
                    amount_paise INTEGER NOT NULL,
                    PRIMARY KEY(scope, customer_name)
                );
                CREATE TABLE IF NOT EXISTS account_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL UNIQUE,
                    scope TEXT NOT NULL,
                    customer_name TEXT NOT NULL,
                    amount_paise INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(run_id) REFERENCES invoices(run_id)
                );
                CREATE INDEX IF NOT EXISTS account_entries_scope_customer
                    ON account_entries(scope, customer_name);
            """)

    def confirm(self, run_id: str, scope: str, invoice: Invoice) -> tuple[Invoice, int | None, bool]:
        if invoice.needs_review or invoice.total is None:
            raise ValueError("invoice must be resolved before confirmation")
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT invoice_json FROM invoices WHERE run_id = ?", (run_id,)
            ).fetchone()
            if existing:
                saved = Invoice.model_validate(json.loads(existing["invoice_json"]))
                return saved, self._credit_balance(connection, scope, saved.customer_name), True
            invoice_json = json.dumps(invoice.model_dump(mode="json"), default=_json_default)
            total_paise = decimal_to_paise(invoice.total)
            connection.execute(
                "INSERT INTO invoices(run_id, scope, invoice_json, total_paise, customer_name, payment_mode) VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, scope, invoice_json, total_paise, invoice.customer_name, invoice.payment_mode),
            )
            balance: int | None = None
            if invoice.payment_mode == "credit":
                assert invoice.customer_name
                if scope.startswith("demo:"):
                    connection.execute(
                        "INSERT OR IGNORE INTO account_openings(scope, customer_name, amount_paise) VALUES (?, ?, ?)",
                        (scope, invoice.customer_name, 10000),
                    )
                connection.execute(
                    "INSERT INTO account_entries(run_id, scope, customer_name, amount_paise) VALUES (?, ?, ?, ?)",
                    (run_id, scope, invoice.customer_name, total_paise),
                )
                balance = self._credit_balance(connection, scope, invoice.customer_name)
            return invoice, balance, False

    def _credit_balance(self, connection: sqlite3.Connection, scope: str, customer_name: str | None) -> int | None:
        if not customer_name:
            return None
        row = connection.execute(
            """
            SELECT COALESCE((SELECT SUM(amount_paise) FROM account_openings WHERE scope = ? AND customer_name = ?), 0)
                 + COALESCE((SELECT SUM(amount_paise) FROM account_entries WHERE scope = ? AND customer_name = ?), 0)
                 AS balance
            """,
            (scope, customer_name, scope, customer_name),
        ).fetchone()
        return int(row["balance"])

    def snapshot(self) -> dict[str, object]:
        with self._connection() as connection:
            accounts = [
                {"scope": row["scope"], "customer_name": row["customer_name"], "balance": f"{Decimal(row['balance']) / 100:.2f}"}
                for row in connection.execute("""
                    SELECT scope, customer_name, SUM(amount_paise) AS balance
                    FROM (
                        SELECT scope, customer_name, amount_paise FROM account_openings
                        UNION ALL
                        SELECT scope, customer_name, amount_paise FROM account_entries
                    )
                    GROUP BY scope, customer_name
                    ORDER BY scope, customer_name
                """)
            ]
            invoices = [
                {"run_id": row["run_id"], "scope": row["scope"], "invoice": json.loads(row["invoice_json"]),
                 "created_at": row["created_at"]}
                for row in connection.execute("SELECT run_id, scope, invoice_json, created_at FROM invoices ORDER BY created_at DESC")
            ]
        return {"accounts": accounts, "invoices": invoices}
