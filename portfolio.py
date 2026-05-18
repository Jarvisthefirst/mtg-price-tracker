"""
portfolio.py — Portfolio management and combined reporting for MTG price tracker.
"""

from __future__ import annotations

import io
import json
import base64
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database import PriceDB

PORTFOLIO_PATH = Path(__file__).parent / "portfolios.json"

# ---------------------------------------------------------------------------
# Helpers to convert between old (product_names) and new (products[] w/ qty)
# ---------------------------------------------------------------------------

def _migrate(pf: dict) -> dict:
    """Upgrade old portfolio format to new products+qty format in-place."""
    if "products" in pf:
        return pf  # already new format
    names = pf.pop("product_names", [])
    pf["products"] = [{"name": n, "qty": 1} for n in names]
    return pf


def _ensure_migrated(data: dict) -> dict:
    for pf in data.get("portfolios", []):
        _migrate(pf)
    return data


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def load_portfolios() -> dict:
    if PORTFOLIO_PATH.exists():
        data = json.loads(PORTFOLIO_PATH.read_text())
        return _ensure_migrated(data)
    return {"description": "", "portfolios": []}


def save_portfolios(data: dict):
    # Clean up any remaining old-format keys
    for pf in data.get("portfolios", []):
        pf.pop("product_names", None)
    PORTFOLIO_PATH.write_text(json.dumps(data, indent=4))


def list_portfolios() -> list[dict]:
    return load_portfolios().get("portfolios", [])


def get_portfolio(name: str) -> dict | None:
    for pf in list_portfolios():
        if pf["name"].lower() == name.lower():
            return pf
    return None


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _fmt(v, suffix=""):
    if v is None:
        return "—"
    return f"€{v:,.2f}{suffix}"


def _pct(a, b):
    if a is None or b is None or a == 0:
        return "—"
    d = ((b - a) / a) * 100
    s = "+" if d >= 0 else ""
    cls = "up" if d >= 0 else "down"
    return f'<span class="{cls}">{s}{d:.1f}%</span>'


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

def build_portfolio_html(db: PriceDB, portfolio_name: str,
                          days: int = 90) -> str:
    """Generate a standalone HTML report for a named portfolio.

    Handles quantities — each product in the portfolio can have qty > 1.
    Per-product values are multiplied by qty for portfolio totals.
    """
    pf = get_portfolio(portfolio_name)
    if not pf:
        return f"<p>Portfolio '{portfolio_name}' not found.</p>"

    products_cfg = pf.get("products", [])
    if not products_cfg:
        return f"<p>Portfolio '{portfolio_name}' is empty.</p>"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Resolve product names to DB rows
    all_products = {p["name"]: p for p in db.get_products()}
    resolved = []
    for pc in products_cfg:
        prod = all_products.get(pc["name"])
        if prod:
            resolved.append((prod, pc["qty"]))

    if not resolved:
        return f"<p>No tracked products found for '{portfolio_name}'.</p>"

    # -------------------------------------------------------------------
    # Per-product stats (quantity-aware)
    # -------------------------------------------------------------------
    rows_html = ""
    total_value = 0.0
    n_with_change = 0
    sum_change_90 = 0.0

    for prod, qty in resolved:
        s90 = db.get_stats(prod["id"], days=90)
        s30 = db.get_stats(prod["id"], days=30)
        latest = s90["latest_price"]
        f90 = s90["first_price"]
        f30 = s30["first_price"]
        c90 = ((latest - f90) / f90 * 100) if (latest and f90 and f90 != 0) else None
        c30 = ((latest - f30) / f30 * 100) if (latest and f30 and f30 != 0) else None
        low = db.get_latest_snapshot(prod["id"])
        low_p = low["price_low"] if low else None

        prod_value = (latest * qty) if latest else 0
        total_value += prod_value

        if c90 is not None:
            sum_change_90 += c90
            n_with_change += 1

        qty_label = f" ×{qty}" if qty > 1 else ""
        rows_html += f"""
        <tr>
          <td>{prod['name'][:45]}{qty_label}</td>
          <td><strong>{_fmt(latest)}</strong></td>
          <td>{_fmt(low_p)}</td>
          <td>{_fmt(s90['avg_price'])}</td>
          <td>{_fmt(prod_value)}</td>
          <td>{_pct(f30, latest)}</td>
          <td>{_pct(f90, latest)}</td>
        </tr>"""

    avg_change_90 = (sum_change_90 / n_with_change) if n_with_change else None

    # -------------------------------------------------------------------
    # Combined value-over-time (quantity-aware)
    # -------------------------------------------------------------------
    series_by_product = []
    for prod, qty in resolved:
        snaps = db.get_history(prod["id"], days=days)
        pts = [(snap["fetched_at"][:10],
                (snap["price_avg"] or 0) * qty)
               for snap in snaps if snap["price_avg"] is not None]
        series_by_product.append(pts)

    all_dates_set = set()
    for pts in series_by_product:
        for d, _ in pts:
            all_dates_set.add(d)
    all_dates = sorted(all_dates_set)

    combined = []
    for date_str in all_dates:
        total = 0.0
        for pts in series_by_product:
            val = next((v for d, v in reversed(pts) if d <= date_str), 0)
            total += val
        combined.append((date_str, f"{total:.2f}"))

    chart_csv = "\n".join(f"{d},{v}" for d, v in combined)
    chart_img = _chart_to_base64(series_by_product, all_dates,
                                 [(p[0]["name"], p[1]) for p in resolved])

    # -------------------------------------------------------------------
    # Product detail cards
    # -------------------------------------------------------------------
    detail_cards = ""
    for prod, qty in resolved:
        s90 = db.get_stats(prod["id"], days=90)
        snaps = db.get_history(prod["id"], days=days)
        hist = ""
        for s in snaps[-15:]:
            hist += f"""<tr><td>{s['fetched_at'][:10]}</td>
                        <td>{_fmt(s['price_avg'])}</td>
                        <td>{_fmt(s['price_trend'])}</td>
                        <td>{_fmt(s['price_low'])}</td></tr>"""

        qty_tag = f" ×{qty} — <span style='color:#00d4aa'>€{s90['latest_price']*qty:,.2f}</span>" if qty > 1 else ""
        detail_cards += f"""
        <div class="pcard" id="p-{prod['id']}">
          <h3>📦 {prod['name']}{qty_tag}</h3>
          <table class="data-table compact">
            <tr><td width="120">90d Start</td><td>{_fmt(s90['first_price'])}</td>
                <td width="120">Latest</td><td><strong>{_fmt(s90['latest_price'])}</strong></td></tr>
            <tr><td>90d Min / Max</td><td>{_fmt(s90['min_price'])} / {_fmt(s90['max_price'])}</td>
                <td>90d Change</td><td>{_pct(s90['first_price'], s90['latest_price'])}</td></tr>
            <tr><td>Qty</td><td>{qty}</td>
                <td>Subtotal</td><td>{_fmt(s90['latest_price'] * qty if s90['latest_price'] else 0)}</td></tr>
          </table>
          {f'<table class="data-table compact hist"><tr><th>Date</th><th>Avg</th><th>Trend</th><th>Low</th></tr>{hist}</table>' if hist else ''}
        </div>"""

    # -------------------------------------------------------------------
    # Assemble HTML
    # -------------------------------------------------------------------
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MTG Portfolio — {pf['name']}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:#0f0f1a; color:#e0e0e0; padding:2rem; }}
.container {{ max-width:1100px; margin:0 auto; }}
h1 {{ font-size:1.8rem; margin-bottom:0.3rem; }}
h2 {{ font-size:1.3rem; margin:1.5rem 0 1rem; color:#00d4aa; }}
h3 {{ font-size:1.1rem; margin:0 0 0.5rem; color:#ffd93d; }}
.subtitle {{ color:#888; margin-bottom:1.5rem; }}
.summary {{ display:flex; gap:1rem; margin:1.5rem 0; flex-wrap:wrap; }}
.card {{ background:#1a1a2e; border-radius:12px; padding:1.2rem 1.5rem; flex:1; min-width:160px; }}
.card .lbl {{ font-size:0.8rem; color:#888; text-transform:uppercase; letter-spacing:1px; }}
.card .val {{ font-size:1.6rem; font-weight:700; margin-top:0.3rem; }}
.card .val.up {{ color:#00d4aa; }} .card .val.down {{ color:#ff6b6b; }}
table {{ width:100%; border-collapse:collapse; margin:0.5rem 0 1.5rem; }}
th {{ text-align:left; padding:0.6rem 0.8rem; background:#1a1a2e;
     font-size:0.8rem; text-transform:uppercase; letter-spacing:0.5px; color:#888; border-bottom:2px solid #2d2d44; }}
td {{ padding:0.6rem 0.8rem; border-bottom:1px solid #1e1e30; }}
tr:hover td {{ background:#1a1a2e; }}
.compact td {{ padding:0.4rem 0.8rem; }}
.hist {{ font-size:0.85rem; }}
span.up {{ color:#00d4aa; }} span.down {{ color:#ff6b6b; }}
.chart-box {{ background:#1a1a2e; border-radius:12px; padding:1rem; margin:1.5rem 0; text-align:center; }}
.chart-box img {{ max-width:100%; height:auto; border-radius:8px; }}
.pcard {{ background:#1a1a2e; border-radius:12px; padding:1.2rem; margin:1rem 0; }}
.footer {{ text-align:center; color:#555; font-size:0.8rem; margin-top:3rem; }}
pre {{ max-height:120px; overflow-y:auto; font-size:0.75rem; color:#666; margin-top:0.3rem; }}
</style>
</head>
<body>
<div class="container">
  <h1>📊 {pf['name']}</h1>
  <p class="subtitle">{pf.get('description','')} · {now} · {len(resolved)} products, {sum(q for _, q in resolved)} total units</p>

  <div class="summary">
    <div class="card"><div class="lbl">Portfolio Value</div>
      <div class="val">{_fmt(total_value)}</div></div>
    <div class="card"><div class="lbl">Avg 90d Change</div>
      <div class="val {'up' if avg_change_90 and avg_change_90>=0 else 'down'}">
        {avg_change_90:+.1f}%</div></div>
    <div class="card"><div class="lbl">Units / Products</div>
      <div class="val">{sum(q for _, q in resolved)} / {len(resolved)}</div></div>
  </div>

  <div class="chart-box">
    <h2 style="margin:0 0 0.5rem">Portfolio Value Over Time ({days}d) — quantity weighted</h2>
    {chart_img}
  </div>

  <h2>Individual Breakdown</h2>
  <table>
    <thead><tr><th>Product</th><th>Latest</th><th>Low</th><th>90d Avg</th><th>Subtotal</th><th>30d Δ</th><th>90d Δ</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>

  <h2>Product Details</h2>
  {detail_cards}

  <div class="footer">
    <p>MTG Price Tracker · All values quantity-weighted</p>
    <p>Combined value (date, total):</p>
    <pre>{chart_csv[:2000]}</pre>
  </div>
</div>
</body>
</html>"""
    return html


def _chart_to_base64(series_by_product, all_dates, product_labels):
    """Generate a matplotlib chart with individual lines + stacked portfolio."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        return '<p style="color:#888">Install matplotlib for charts.</p>'

    if not all_dates:
        return '<p style="color:#888">No data for chart.</p>'

    date_objs = [datetime.strptime(d, "%Y-%m-%d") for d in all_dates]
    x_idx = range(len(all_dates))

    # Build per-date values for each product
    per_date_values = []
    for date_str in all_dates:
        row = []
        for pts in series_by_product:
            val = next((v for d, v in reversed(pts) if d <= date_str), 0)
            row.append(val)
        per_date_values.append(row)

    colors = ["#00d4aa", "#ff6b6b", "#ffd93d", "#6c5ce7", "#00b894",
              "#e17055", "#0984e3", "#fdcb6e"]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 8.5),
                                    height_ratios=[3, 1])
    fig.patch.set_facecolor("#1a1a2e")
    for ax in (ax1, ax2):
        ax.set_facecolor("#1a1a2e")
        ax.tick_params(colors="#888")
        ax.grid(alpha=0.08, color="white")
        ax.spines["bottom"].set_color("#2d2d44")
        ax.spines["left"].set_color("#2d2d44")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    for i, pts in enumerate(series_by_product):
        if not pts:
            continue
        x, y = [], []
        for pos, date_str in enumerate(all_dates):
            v = next((v for d, v in reversed(pts) if d <= date_str), None)
            if v is not None:
                x.append(pos)
                y.append(v)
        if not x:
            continue
        c = colors[i % len(colors)]
        label = product_labels[i] if i < len(product_labels) else f"P{i}"
        # Truncate name in legend
        lbl = label[0] if isinstance(label, tuple) else label[:32]
        ax1.plot(x, y, label=str(lbl), color=c, linewidth=1.6)

    ax1.set_title("Individual Products (quantity-weighted)", color="white",
                  fontsize=13, pad=10)
    ax1.set_xticks(x_idx)
    ax1.set_xticklabels([d.strftime("%b %d") for d in date_objs],
                         rotation=30, ha="right", fontsize=7)
    step = max(1, len(date_objs) // 10)
    for idx, label in enumerate(ax1.get_xticklabels()):
        if idx % step != 0:
            label.set_visible(False)
    ax1.legend(facecolor="#2d2d44", edgecolor="none", labelcolor="white",
               fontsize=7.5, ncol=2)

    totals = [sum(row) for row in per_date_values]
    ax2.fill_between(x_idx, 0, totals, color="#00d4aa", alpha=0.25)
    ax2.plot(x_idx, totals, color="#00d4aa", linewidth=2)

    bottoms = [0.0] * len(totals)
    for i, pts in enumerate(series_by_product):
        if not pts:
            continue
        c = colors[i % len(colors)]
        vals = [row[i] if i < len(row) else 0.0 for row in per_date_values]
        ax2.bar(x_idx, vals, bottom=bottoms, width=0.8, color=c, alpha=0.3)

    ax2.set_title(f"Combined Portfolio Value: {_fmt(totals[-1] if totals else 0)}",
                  color="white", fontsize=13, pad=10)
    ax2.set_ylabel("Total (EUR)", color="#888")
    ax2.set_xticks(x_idx)
    ax2.set_xticklabels([d.strftime("%b %d") for d in date_objs],
                         rotation=30, ha="right", fontsize=7)
    for idx, label in enumerate(ax2.get_xticklabels()):
        if idx % step != 0:
            label.set_visible(False)

    fig.tight_layout(pad=2)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor="#1a1a2e")
    plt.close(fig)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode()
    return f'<img src="data:image/png;base64,{b64}" alt="Portfolio chart" />'
