"""
reporter.py — Formatting, summary tables, and optional charting.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database import PriceDB


def _fmt(price: float | None, currency: str = "€") -> str:
    if price is None:
        return "  —  "
    return f"{currency}{price:,.2f}"


def _pct_change(old: float | None, new: float | None) -> str:
    if old is None or new is None or old == 0:
        return "  —  "
    change = ((new - old) / old) * 100
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.1f}%"


# -----------------------------------------------------------------
# Report builders
# -----------------------------------------------------------------

def summary_table(db: "PriceDB") -> str:
    """Return a formatted overview of all tracked products (latest snapshot)."""
    rows = db.get_all_latest()
    if not rows:
        return "No products configured yet. Add some with: python tracker.py add <name> <url>"

    lines = [
        "╔══════════════════════════════════════════════════════════════════════════════════╗",
        "║                     MTG Booster Display — Price Overview                       ║",
        "╚══════════════════════════════════════════════════════════════════════════════════╝",
        "",
        f"{'Product':45s} {'Avg':>10s} {'Trend':>10s} {'Low':>10s} {'30d Avg':>10s}  {'Listings':>8s}",
        "─" * 100,
    ]

    for r in rows:
        name = r["name"][:44]
        lines.append(
            f"{name:45s} {_fmt(r['price_avg']):>10s} {_fmt(r['price_trend']):>10s} "
            f"{_fmt(r['price_low']):>10s} {_fmt(r['price_30day']):>10s}  "
            f"{str(r['listings_count'] or '—'):>8s}"
        )

    lines += [
        "",
        f"Last updated: {rows[0]['fetched_at'] if rows else 'never'} UTC",
    ]
    return "\n".join(lines)


def product_detail(db: "PriceDB", product_id: int, days: int = 30) -> str:
    """Show stats + recent history for a single product."""
    prod = db.get_product(product_id)
    if not prod:
        return f"Product #{product_id} not found."

    stats = db.get_stats(product_id, days=days)
    history = db.get_history(product_id, days=days)

    lines = [
        f"📦 {prod['name']}",
        f"   Cardmarket ID: {prod['cardmarket_id'] or 'N/A'}",
        f"   URL: {prod['url'] or 'N/A'}",
        "",
        f"   ── Last {days} days ──",
        f"   Latest:       {_fmt(stats['latest_price'])}  ({stats['latest_at'] or 'N/A'})",
        f"   First:        {_fmt(stats['first_price'])}  ({stats['first_at'] or 'N/A'})",
        f"   Change:       {_pct_change(stats['first_price'], stats['latest_price'])}",
        f"   Min:          {_fmt(stats['min_price'])}",
        f"   Max:          {_fmt(stats['max_price'])}",
        f"   Average:      {_fmt(stats['avg_price'])}",
        f"   Snapshots:    {stats['snapshots']}",
        "",
    ]

    if history:
        lines.append("   Recent samples (last 10):")
        lines.append(f"   {'Date':22s} {'Avg':>10s} {'Trend':>10s} {'Low':>10s}")
        lines.append("   " + "─" * 55)
        for snap in history[-10:]:
            lines.append(
                f"   {snap['fetched_at'][:19]:22s} "
                f"{_fmt(snap['price_avg']):>10s} "
                f"{_fmt(snap['price_trend']):>10s} "
                f"{_fmt(snap['price_low']):>10s}"
            )

    return "\n".join(lines)


def export_csv(db: "PriceDB", out_path: str | Path | None = None) -> str:
    """Export all history as CSV. Returns the CSV text if no path given."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "product_id", "product_name", "fetched_at",
        "price_avg", "price_trend", "price_low", "price_30day",
        "listings_count", "currency",
    ])

    products = db.get_products()
    for prod in products:
        snaps = db.get_history(prod["id"])
        for s in snaps:
            writer.writerow([
                prod["id"], prod["name"], s["fetched_at"],
                s["price_avg"], s["price_trend"], s["price_low"],
                s["price_30day"], s["listings_count"], s["currency"],
            ])

    csv_text = output.getvalue()
    if out_path:
        Path(out_path).write_text(csv_text)
        return f"Exported {len(csv_text):,} bytes → {out_path}"
    return csv_text


def generate_chart(db: "PriceDB", product_id: int, days: int = 90,
                   out_path: str | None = None) -> str | None:
    """
    Generate a matplotlib chart for a product's price history.
    Returns the file path of the saved chart, or a message on failure.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        return "matplotlib not installed. Run: pip install matplotlib"

    from datetime import datetime as dt

    prod = db.get_product(product_id)
    if not prod:
        return f"Product #{product_id} not found."

    snaps = db.get_history(product_id, days=days)
    if not snaps:
        return f"No data in the last {days} days for {prod['name']}."

    dates = [dt.fromisoformat(s["fetched_at"]) for s in snaps]
    avgs = [s["price_avg"] for s in snaps]
    trends = [s["price_trend"] for s in snaps]
    lows = [s["price_low"] for s in snaps]

    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    if any(avgs):
        ax.plot(dates, avgs, label="Avg Price", color="#00d4aa", linewidth=2)
    if any(trends):
        ax.plot(dates, trends, label="Trend", color="#ff6b6b", linewidth=1.5,
                linestyle="--")
    if any(lows):
        ax.plot(dates, lows, label="Low", color="#ffd93d", linewidth=1,
                linestyle=":")

    ax.set_title(f"{prod['name']} — Price History ({days}d)",
                 color="white", fontsize=14, pad=15)
    ax.set_ylabel("Price (EUR)", color="white")
    ax.tick_params(colors="white")
    ax.legend(facecolor="#2d2d44", edgecolor="none", labelcolor="white")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.grid(alpha=0.15, color="white")
    fig.autofmt_xdate()

    if out_path is None:
        name_slug = prod["name"].lower().replace(" ", "_").replace("-", "_")[:40]
        out_path = f"chart_{name_slug}_{days}d.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
