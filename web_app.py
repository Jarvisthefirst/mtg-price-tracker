"""
web_app.py — Browser-based UI for MTG Price Tracker

Run with:
    python3 web_app.py

Or via one-click launcher:
    bash start.sh
"""

from __future__ import annotations

import io
import json
import base64
import csv
from pathlib import Path
from datetime import datetime, timezone

from flask import Flask, request, jsonify, send_file, send_from_directory

from database import PriceDB
from portfolio import (load_portfolios, save_portfolios, get_portfolio,
                        list_portfolios, build_portfolio_html)
from reporter import generate_chart

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

BASE = Path(__file__).parent
DB_PATH = BASE / "price_history.db"
STATIC = BASE / "static"

app = Flask(__name__)


def get_db():
    return PriceDB(str(DB_PATH))


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(str(BASE), "index.html")


# ---------------------------------------------------------------------------
# API — Products
# ---------------------------------------------------------------------------

@app.route("/api/products")
def api_products():
    db = get_db()
    products = db.get_products()
    result = []
    for p in products:
        p = dict(p)
        snap = db.get_latest_snapshot(p["id"])
        s90 = db.get_stats(p["id"], days=90)
        result.append({
            "id": p["id"],
            "name": p["name"],
            "url": p.get("url", ""),
            "latest": s90["latest_price"],
            "avg_90d": s90["avg_price"],
            "min_90d": s90["min_price"],
            "max_90d": s90["max_price"],
            "trend": (snap["price_trend"] if snap else None),
        })
    return jsonify(result)


@app.route("/api/products/<int:pid>")
def api_product_detail(pid):
    db = get_db()
    p = db.get_product(pid)
    if not p:
        return jsonify({"error": "Not found"}), 404
    p = dict(p)
    snap = db.get_latest_snapshot(pid)
    s90 = db.get_stats(pid, days=90)
    s30 = db.get_stats(pid, days=30)
    history = db.get_history(pid, days=90)
    return jsonify({
        "id": p["id"],
        "name": p["name"],
        "url": p.get("url", ""),
        "latest": s90["latest_price"],
        "avg_90d": s90["avg_price"],
        "min_90d": s90["min_price"],
        "max_90d": s90["max_price"],
        "first_90d": s90["first_price"],
        "avg_30d": s30["avg_price"],
        "first_30d": s30["first_price"],
        "trend": (snap["price_trend"] if snap else None),
        "history": [{"date": h["fetched_at"][:10],
                      "avg": h["price_avg"],
                      "low": h["price_low"],
                      "trend": h["price_trend"]}
                     for h in history],
    })


@app.route("/api/products/<int:pid>/chart")
def api_product_chart(pid):
    db = get_db()
    days = request.args.get("days", 90, type=int)
    buf = io.BytesIO()
    success = generate_chart(db, pid, days, buf)
    if not success:
        return jsonify({"error": "No data"}), 404
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/api/products", methods=["POST"])
def api_add_product():
    data = request.get_json()
    name = data.get("name", "").strip()
    pid = data.get("id")
    url = data.get("url", "")
    if not name and not pid:
        return jsonify({"error": "Need name or id"}), 400
    db = get_db()
    products = db.get_products()
    for p in products:
        if p["name"].lower() == name.lower():
            return jsonify({"error": f"'{name}' already exists"}), 409
    db.upsert_product(pid or 0, name, url)
    return jsonify({"ok": True, "name": name})


@app.route("/api/products/<int:pid>", methods=["DELETE"])
def api_delete_product(pid):
    db = get_db()
    db.delete_product(pid)
    return jsonify({"ok": True})


@app.route("/api/products/price", methods=["POST"])
def api_set_price():
    data = request.get_json()
    name = data.get("name", "").strip()
    avg = data.get("avg")
    if not name or avg is None:
        return jsonify({"error": "Need name and avg"}), 400
    db = get_db()
    prods = db.get_products()
    match = None
    for p in prods:
        if name.lower() in p["name"].lower():
            match = p
            break
    if not match:
        return jsonify({"error": f"No product matching '{name}'"}), 404
    db.insert_snapshot(match["id"], float(avg))
    return jsonify({"ok": True, "id": match["id"], "name": match["name"],
                     "price": float(avg)})


# ---------------------------------------------------------------------------
# API — Portfolios
# ---------------------------------------------------------------------------

@app.route("/api/portfolios")
def api_portfolios():
    data = load_portfolios()
    return jsonify(data.get("portfolios", []))


@app.route("/api/portfolios", methods=["POST"])
def api_create_portfolio():
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Need name"}), 400
    if get_portfolio(name):
        return jsonify({"error": f"'{name}' already exists"}), 409
    portfolios_data = load_portfolios()
    pf = {"name": name, "description": data.get("description", ""), "products": []}
    portfolios_data.setdefault("portfolios", []).append(pf)
    save_portfolios(portfolios_data)
    return jsonify({"ok": True, "name": name})


@app.route("/api/portfolios/<pname>", methods=["PUT"])
def api_update_portfolio(pname):
    data = request.get_json()
    portfolios_data = load_portfolios()
    pf = _find_portfolio(portfolios_data, pname)
    if not pf:
        return jsonify({"error": "Not found"}), 404
    if "description" in data:
        pf["description"] = data["description"]
    if "products" in data:
        pf["products"] = data["products"]
    save_portfolios(portfolios_data)
    return jsonify({"ok": True})


@app.route("/api/portfolios/<pname>", methods=["DELETE"])
def api_delete_portfolio(pname):
    portfolios_data = load_portfolios()
    portfolios_data["portfolios"] = [
        p for p in portfolios_data.get("portfolios", [])
        if p["name"].lower() != pname.lower()
    ]
    save_portfolios(portfolios_data)
    return jsonify({"ok": True})


@app.route("/api/portfolios/<pname>/report")
def api_portfolio_report(pname):
    db = get_db()
    days = request.args.get("days", 90, type=int)
    html = build_portfolio_html(db, pname, days=days)
    if html.startswith("<p"):
        return jsonify({"error": html}), 404
    return send_file(
        io.BytesIO(html.encode("utf-8")),
        mimetype="text/html",
        as_attachment=True,
        download_name=f"portfolio_{pname.lower().replace(' ','_')}.html",
    )


@app.route("/api/portfolios/<pname>/data")
def api_portfolio_data(pname):
    db = get_db()
    pf = get_portfolio(pname)
    if not pf:
        return jsonify({"error": "Not found"}), 404
    days = request.args.get("days", 90, type=int)
    all_prods = {p["name"]: p for p in db.get_products()}
    result = []
    for pc in pf.get("products", []):
        prod = all_prods.get(pc["name"])
        if prod:
            s90 = db.get_stats(prod["id"], days=days)
            result.append({
                "name": prod["name"],
                "qty": pc["qty"],
                "latest": s90["latest_price"],
                "avg_90d": s90["avg_price"],
                "first_90d": s90["first_price"],
            })
    return jsonify(result)


def _find_portfolio(data, name):
    for p in data.get("portfolios", []):
        if p["name"].lower() == name.lower():
            return p
    return None


# ---------------------------------------------------------------------------
# API — Export / Import
# ---------------------------------------------------------------------------

@app.route("/api/export")
def api_export_csv():
    db = get_db()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Date", "Product", "AvgPrice", "LowPrice", "Trend"])
    for p in db.get_products():
        for snap in db.get_history(p["id"], days=9999):
            w.writerow([
                snap["fetched_at"][:10],
                p["name"],
                snap["price_avg"],
                snap["price_low"],
                snap["price_trend"],
            ])
    out.seek(0)
    return send_file(
        io.BytesIO(out.getvalue().encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name="price_history.csv",
    )


@app.route("/api/seed")
def api_seed():
    from seed_demo import seed_demo
    db = get_db()
    seed_demo(db)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os, webbrowser
    port = int(os.environ.get("PORT", 8080))
    url = f"http://localhost:{port}"
    print(f"\n  🌐 MTG Price Tracker — Web UI\n")
    print(f"     Open: {url}")
    print(f"\n     Press Ctrl+C to stop\n")
    webbrowser.open(url)
    app.run(host="0.0.0.0", port=port, debug=False)
