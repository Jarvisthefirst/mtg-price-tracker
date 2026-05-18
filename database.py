"""
database.py — SQLite-backed price history storage.

Structures:
  products (id, name, cardmarket_id, url, created_at)
  price_snapshots (id, product_id, price_avg, price_trend, price_low, 
                   price_30day, listings_count, currency, fetched_at)
"""

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    cardmarket_id INTEGER,
    url         TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER NOT NULL REFERENCES products(id),
    price_avg       REAL,
    price_trend     REAL,
    price_low       REAL,
    price_30day     REAL,
    listings_count  INTEGER,
    currency        TEXT NOT NULL DEFAULT 'EUR',
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
    raw_json        TEXT
);

CREATE INDEX IF NOT EXISTS idx_snapshots_product
    ON price_snapshots(product_id, fetched_at);
"""


class PriceDB:
    def __init__(self, db_path: str | Path):
        self._path = Path(db_path)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)

    # -----------------------------------------------------------------
    # Products
    # -----------------------------------------------------------------

    def upsert_product(self, name: str, cardmarket_id: int | None = None,
                       url: str | None = None) -> int:
        existing = self._conn.execute(
            "SELECT id FROM products WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            self._conn.execute(
                "UPDATE products SET cardmarket_id = COALESCE(?, cardmarket_id), "
                "url = COALESCE(?, url) WHERE id = ?",
                (cardmarket_id, url, existing["id"]),
            )
            return existing["id"]
        cur = self._conn.execute(
            "INSERT INTO products (name, cardmarket_id, url) VALUES (?, ?, ?)",
            (name, cardmarket_id, url),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_products(self):
        return self._conn.execute(
            "SELECT * FROM products ORDER BY name"
        ).fetchall()

    def get_product(self, product_id: int):
        return self._conn.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()

    def delete_product(self, product_id: int):
        self._conn.execute("DELETE FROM price_snapshots WHERE product_id = ?",
                           (product_id,))
        self._conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        self._conn.commit()

    # -----------------------------------------------------------------
    # Snapshots
    # -----------------------------------------------------------------

    def insert_snapshot(self, product_id: int, price_avg: float | None,
                        price_trend: float | None, price_low: float | None,
                        price_30day: float | None,
                        listings_count: int | None,
                        currency: str = "EUR",
                        raw: dict | None = None):
        self._conn.execute(
            """INSERT INTO price_snapshots
               (product_id, price_avg, price_trend, price_low, price_30day,
                listings_count, currency, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (product_id, price_avg, price_trend, price_low, price_30day,
             listings_count, currency,
             json.dumps(raw) if raw else None),
        )
        self._conn.commit()

    def get_latest_snapshot(self, product_id: int):
        return self._conn.execute(
            """SELECT * FROM price_snapshots
               WHERE product_id = ?
               ORDER BY fetched_at DESC LIMIT 1""",
            (product_id,),
        ).fetchone()

    def get_all_latest(self):
        return self._conn.execute(
            """SELECT p.id, p.name, p.cardmarket_id, p.url,
                      s.price_avg, s.price_trend, s.price_low,
                      s.price_30day, s.listings_count, s.currency,
                      s.fetched_at
               FROM products p
               LEFT JOIN price_snapshots s ON s.id = (
                   SELECT s2.id FROM price_snapshots s2
                   WHERE s2.product_id = p.id
                   ORDER BY s2.fetched_at DESC LIMIT 1
               )
               ORDER BY p.name"""
        ).fetchall()

    def get_history(self, product_id: int, days: int | None = None):
        if days:
            return self._conn.execute(
                """SELECT * FROM price_snapshots
                   WHERE product_id = ?
                     AND fetched_at >= datetime('now', ?)
                   ORDER BY fetched_at ASC""",
                (product_id, f"-{days} days"),
            ).fetchall()
        return self._conn.execute(
            """SELECT * FROM price_snapshots
               WHERE product_id = ?
               ORDER BY fetched_at ASC""",
            (product_id,),
        ).fetchall()

    def get_stats(self, product_id: int, days: int = 30):
        """Return min / max / avg / latest over the last N days."""
        row = self._conn.execute(
            """SELECT
                   MIN(price_avg)  AS min_price,
                   MAX(price_avg)  AS max_price,
                   ROUND(AVG(price_avg), 2) AS avg_price,
                   COUNT(*)        AS snapshots
               FROM price_snapshots
               WHERE product_id = ?
                 AND price_avg IS NOT NULL
                 AND fetched_at >= datetime('now', ?)""",
            (product_id, f"-{days} days"),
        ).fetchone()
        latest = self.get_latest_snapshot(product_id)
        first = self._conn.execute(
            """SELECT price_avg, fetched_at FROM price_snapshots
               WHERE product_id = ? AND price_avg IS NOT NULL
                 AND fetched_at >= datetime('now', ?)
               ORDER BY fetched_at ASC LIMIT 1""",
            (product_id, f"-{days} days"),
        ).fetchone()
        return {
            "latest_price": latest["price_avg"] if latest else None,
            "latest_at": latest["fetched_at"] if latest else None,
            "min_price": row["min_price"],
            "max_price": row["max_price"],
            "avg_price": row["avg_price"],
            "snapshots": row["snapshots"],
            "first_price": first["price_avg"] if first else None,
            "first_at": first["fetched_at"] if first else None,
        }

    # -----------------------------------------------------------------
    # Maintenance
    # -----------------------------------------------------------------

    def cleanup_old(self, keep_days: int = 365):
        """Remove snapshots older than keep_days (to save space)."""
        self._conn.execute(
            "DELETE FROM price_snapshots WHERE fetched_at < datetime('now', ?)",
            (f"-{keep_days} days",),
        )
        self._conn.commit()
        return self._conn.total_changes

    def close(self):
        self._conn.close()
