#!/usr/bin/env python3
"""Seed the database with realistic demo data for 8 MTG booster displays."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from database import PriceDB
from datetime import datetime, timedelta
from random import seed, uniform, gauss

seed(42)
db = PriceDB(Path(__file__).parent / "price_history.db")

products = [
    ("Modern Horizons 3 Play Booster Box",       210, -0.08),
    ("Modern Horizons 2 Draft Booster Box",      275, +0.12),
    ("Commander Masters Draft Booster Box",      340, -0.05),
    ("Double Masters 2022 Draft Booster Box",    320, -0.03),
    ("Ravnica Remastered Draft Booster Box",     155, +0.06),
    ("Tarkir: Dragonstorm Play Booster Box",      95, -0.15),
    ("Innistrad Remastered Play Booster Box",    140, +0.04),
    ("Bloomburrow Play Booster Box",             110, -0.10),
]

today = datetime.now()
for name, base, trend_pct in products:
    pid = db.upsert_product(name)
    for d in range(90, -1, -1):
        dt = today - timedelta(days=d)
        drift = trend_pct * (90 - d) / 90 * base
        avg = round(max(1, base + drift + gauss(0, 4)), 2)
        tr = round(avg + uniform(-5, 5), 2)
        low = round(avg * uniform(0.92, 0.97), 2)
        avg30 = round(avg * uniform(0.97, 1.03), 2)
        listings = int(uniform(5, 40))
        db._conn.execute(
            """INSERT INTO price_snapshots
               (product_id, price_avg, price_trend, price_low, price_30day,
                listings_count, currency, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, 'EUR', ?)""",
            (pid, avg, tr, low, avg30, listings, dt.strftime("%Y-%m-%d %H:%M:%S")))
    db._conn.commit()

print(f"✅ Demo data: {len(products)} products × 91 days")
