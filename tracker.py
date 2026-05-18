#!/usr/bin/env python3
"""
MTG Price Tracker — Track Cardmarket prices for booster displays over time.

Usage:
    python tracker.py setup             — Configure API credentials
    python tracker.py verify            — Test API credentials
    python tracker.py check             — Fetch latest prices for all products
    python tracker.py list              — Show latest prices (table)
    python tracker.py info <id/name>    — Detailed view with history
    python tracker.py chart <id/name>   — Generate a price chart
    python tracker.py add <name> <url_or_id>  — Add a product
    python tracker.py remove <id>       — Remove a product
    python tracker.py export [path]     — Export all data as CSV
    python tracker.py find <query>      — Search Cardmarket for product IDs
    python tracker.py price <id> <avg>  — Manually record a price
    python tracker.py portfolio list    — Show all portfolios
    python tracker.py portfolio <name>  — Console portfolio summary
    python tracker.py portfolio report <name> [--out file.html] [--days 90]
                                      — Self-contained HTML report
    python tracker.py portfolio create <name> [products...]
                                      — Create a custom portfolio
    python tracker.py portfolio add <name> <product1 product2...>
                                      — Add products to a portfolio

Setup:
    1. Go to https://www.cardmarket.com/en/Developer
    2. Create an app to get 4 API credentials
    3. Run: python tracker.py setup
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from database import PriceDB
from api import CardmarketAPI
from reporter import summary_table, product_detail, export_csv, generate_chart
from portfolio import (list_portfolios, get_portfolio, build_portfolio_html,
                        PORTFOLIO_PATH, save_portfolios, load_portfolios)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
PRODUCTS_PATH = SCRIPT_DIR / "products.json"
DB_PATH = SCRIPT_DIR / "price_history.db"

logging.basicConfig(level=logging.INFO, format="%(levelname).1s %(message)s")
logger = logging.getLogger("tracker")


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {
        "cardmarket_api": {"app_token": "", "app_secret": "",
                           "access_token": "", "access_secret": ""},
        "database": str(DB_PATH), "products_file": str(PRODUCTS_PATH),
        "fetch_method": "api", "request_delay_seconds": 1.0,
    }


def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=4))


def load_products() -> list[dict]:
    if PRODUCTS_PATH.exists():
        return json.loads(PRODUCTS_PATH.read_text()).get("products", [])
    return []


def save_products(products: list[dict]):
    PRODUCTS_PATH.write_text(json.dumps(
        {"description": "Products to track (editable)", "products": products},
        indent=4,
    ))


# ---------------------------------------------------------------------------
# API & DB
# ---------------------------------------------------------------------------

def get_api(cfg: dict) -> CardmarketAPI | None:
    creds = cfg.get("cardmarket_api", {})
    if not creds.get("app_token"):
        return None
    return CardmarketAPI(creds["app_token"], creds["app_secret"],
                         creds["access_token"], creds["access_secret"],
                         cfg.get("request_delay_seconds", 1.0))


def get_db() -> PriceDB:
    return PriceDB(load_config().get("database", str(DB_PATH)))


def resolve_product(db: PriceDB, ident: str) -> dict | None:
    """Resolve an identifier to a product row.

    Accepts: numeric ID, #id, name fragment, name initialism (MH3 → Modern Horizons 3).
    """
    ident = ident.strip()
    # Numeric ID
    if ident.isdigit():
        p = db.get_product(int(ident))
        if p: return p
    # #id
    if ident.startswith("#") and ident[1:].isdigit():
        p = db.get_product(int(ident[1:]))
        if p: return p
    # Name fragment (case-insensitive)
    low = ident.lower()
    for p in db.get_products():
        if low in p["name"].lower():
            return p
    # URL fragment
    for p in db.get_products():
        if p["url"] and low in p["url"].lower():
            return p
    # Initialism matching: "MH3" → split name into words, match first letters
    if len(ident) >= 2:
        for p in db.get_products():
            initials = "".join(w[0] for w in p["name"].split() if w)
            if initials.lower() == low:
                return p
            # Support partial initials too: "MHM3"→"Modern Horizons ... 3"
            words = p["name"].split()
            alt = "".join(w[0] if i < 2 else w[0] if w.isdigit() else ""
                         for i, w in enumerate(words) if w)
            if alt.lower() == low:
                return p
    return None


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_demo(_args):
    """Seed the DB with 91 days of realistic demo data (no API needed)."""
    from seed_demo import seed_demo
    seed_demo(get_db())
    print("   Run: python tracker.py list\n")


def cmd_setup(_args):
    cfg = load_config()
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║   Cardmarket API Setup                              ║")
    print("╠══════════════════════════════════════════════════════╣")
    print("║  1. Go to https://www.cardmarket.com/en/Developer   ║")
    print("║  2. Create an application (free)                    ║")
    print("║  3. Copy the 4 credentials below                    ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()
    creds = cfg.setdefault("cardmarket_api", {})
    for key, label in [("app_token","App Token"),("app_secret","App Secret"),
                       ("access_token","Access Token"),("access_secret","Access Secret")]:
        cur = creds.get(key, "")
        hint = f" [{cur[:16]}...]" if cur and len(cur) > 16 else ""
        val = input(f"  {label}{hint}: ").strip()
        if val:
            creds[key] = val
    if any(creds.values()):
        save_config(cfg)
        print("\n✅ Saved. Run: python tracker.py verify\n")
    else:
        print("\n⚠️  Nothing saved.\n")


def cmd_verify(_args):
    cfg = load_config()
    api = get_api(cfg)
    if not api:
        print("❌ No API credentials. Run: python tracker.py setup")
        return
    print("🔍 Verifying API credentials...")
    print("✅ Valid!" if api.verify_credentials() else "❌ Failed — check keys in config.json")
    print()


def cmd_find(args):
    cfg = load_config()
    api = get_api(cfg)
    if not api:
        print("❌ API not configured. Run: python tracker.py setup\n")
        return
    query = " ".join(args.query)
    print(f"🔍 Searching '{query}'...\n")
    results = api.find_product(query)
    if not results:
        print("No results.\n")
        return
    for p in results:
        print(f"  {p.get('idProduct','?'):>8}  {(p.get('enName') or '?')[:60]:60s}  "
              f"{(p.get('expansionName') or p.get('categoryName') or '?')[:30]}")
    print()


def cmd_add(args):
    name, ident = args.name, args.identifier
    pid, url = None, None
    if ident.startswith("http"):
        url = ident
    elif ident.isdigit():
        pid = int(ident)
    else:
        print("❌ Must be a URL or numeric product ID.\n")
        return
    db = get_db()
    db_id = db.upsert_product(name, cardmarket_id=pid, url=url)
    products = load_products()
    products.append({"name": name, "cardmarket_id": pid, "url": url})
    save_products(products)
    print(f"✅ Added '{name}' (db id={db_id})\n")


def cmd_remove(args):
    db = get_db()
    prod = resolve_product(db, args.ident)
    if not prod:
        print(f"❌ No match for '{args.ident}'\n")
        return
    db.delete_product(prod["id"])
    products = [p for p in load_products() if p["name"] != prod["name"]]
    save_products(products)
    print(f"🗑️  Removed '{prod['name']}'\n")


def cmd_check(_args):
    cfg = load_config()
    api = get_api(cfg)
    if not api:
        print("❌ Cardmarket API not configured.\n")
        print("   Steps:")
        print("     1. Go to https://www.cardmarket.com/en/Developer")
        print("     2. Create an app → get 4 API keys")
        print("     3. python tracker.py setup\n")
        return
    products = load_products()
    if not products:
        print("📭 No products. Add: python tracker.py add \"Name\" <url_or_id>\n")
        return
    db = get_db()
    ok, fail = 0, 0
    print(f"📡 Fetching {len(products)} products...\n")
    for p in products:
        name = p["name"]
        print(f"  ⏳ {name} ... ", end="", flush=True)
        try:
            pid = p.get("cardmarket_id")
            if not pid:
                res = api.find_product(name)
                if not res:
                    print("⚠️  not found"); fail += 1; continue
                pid = res[0]["idProduct"]
            prices = api.get_product_prices(pid)
            if prices:
                db.upsert_product(name, cardmarket_id=pid, url=p.get("url"))
                rows = db.upsert_product(name)
                db.insert_snapshot(rows, prices.get("price_avg"),
                                   prices.get("price_trend"), prices.get("price_low"),
                                   prices.get("price_30day"),
                                   prices.get("listings_count"),
                                   prices.get("currency", "EUR"), raw=prices)
                print(f"✅ €{prices.get('price_avg', '?')}")
                ok += 1
            else:
                print("⚠️  no data"); fail += 1
        except Exception as e:
            print(f"❌ {e}"); fail += 1
    print(f"\n📊 {ok} ok, {fail} failed\n")


def cmd_list(_args):
    print(summary_table(get_db()))
    print()


def cmd_info(args):
    db = get_db()
    prod = resolve_product(db, args.ident)
    if not prod:
        print(f"❌ No match for '{args.ident}'\n"); return
    print(product_detail(db, prod["id"], days=args.days))


def cmd_chart(args):
    db = get_db()
    prod = resolve_product(db, args.ident)
    if not prod:
        print(f"❌ No match for '{args.ident}'\n"); return
    print(generate_chart(db, prod["id"], days=args.days, out_path=args.output))
    print()


def cmd_export(args):
    result = export_csv(get_db(), args.path)
    print(result)
    if args.path: print()


def cmd_price(args):
    """Manually record a price snapshot."""
    db = get_db()
    prod = resolve_product(db, args.ident)
    if not prod:
        print(f"❌ No match for '{args.ident}'\n"); return
    db.insert_snapshot(prod["id"], float(args.avg), None, None, None, None)
    print(f"✅ Recorded €{args.avg} for {prod['name']}\n")


def _get_portfolio_from(name, portfolios):
    """Find portfolio by name in a pre-loaded list."""
    for pf in portfolios:
        if pf["name"].lower() == name.lower():
            return pf
    return None


def cmd_portfolio(args):
    """Portfolio management — supports qty for multiple units of the same product.

    Add/remove syntax: "Product Name" or "Product Name:N" (where N is quantity)
    """
    db = get_db()
    portfolios_data = load_portfolios()
    portfolios = portfolios_data.setdefault("portfolios", [])

    # --- Helper: resolve product names from DB ---
    def _resolve(raw):
        qty = 1
        if ":" in raw:
            raw_name, qs = raw.rsplit(":", 1)
            try:
                qty = int(qs)
            except ValueError:
                qty = 1
        else:
            raw_name = raw
        low = raw_name.lower()
        all_p = {p["name"].lower(): p["name"] for p in db.get_products()}
        if low in all_p:
            return all_p[low], qty, None
        matches = [n for n in all_p.values() if low in n.lower()]
        if len(matches) == 1:
            return matches[0], qty, None
        # Try initialism: "MH3" → match "Modern Horizons 3 Play Booster Box"
        for n in all_p.values():
            words = n.split()
            # Full initialism: "MH3PB" (all first letters)
            initials = "".join(w[0] for w in words if w).lower()
            if initials == low:
                return n, qty, None
            # Smart: product initials + digits: "MH3" = M(odern) H(3)orizons 3
            alt = "".join(w[0] if i < 2 else (w[0] if w.isdigit() else "")
                         for i, w in enumerate(words) if w).lower()
            if alt == low:
                return n, qty, None
        return None, qty, raw_name

    # --- List ---
    if args.action == "list" or (not args.action or args.action == "list"):
        if not portfolios:
            print("📭 No portfolios. Create one:\n")
            print("   python tracker.py portfolio create MyPortfolio 'Product1' 'Product2'\n")
            return
        print("\n📂 Portfolios:\n")
        for pf in portfolios:
            prods = pf.get("products", [])
            total_qty = sum(p.get("qty", 1) for p in prods)
            preview = ", ".join(
                (p["name"][:24] + (f"×{p['qty']}" if p.get("qty", 1) > 1 else ""))
                for p in prods[:4]
            )
            if len(prods) > 4:
                preview += "..."
            desc = pf.get("description", "")
            print(f"  📊 {pf['name']}{" — " + desc if desc else ""}")
            print(f"     {total_qty} units across {len(prods)} products: {preview}")
            print()
        print(f"   Total: {len(portfolios)} portfolios\n")
        return

    # --- Create ---
    if args.action == "create":
        name = args.portfolio_name
        if not name:
            print("❌ Usage: python tracker.py portfolio create <name> [Product1 Product2 ...]\n")
            return
        if _get_portfolio_from(name, portfolios):
            print(f"❌ Portfolio '{name}' already exists.\n")
            return
        prods = []
        for a in args.products:
            resolved_name, qty, _ = _resolve(a)
            if resolved_name:
                prods.append({"name": resolved_name, "qty": qty})
        new_pf = {"name": name, "description": "", "products": prods}
        portfolios.append(new_pf)
        save_portfolios(portfolios_data)
        print(f"✅ Created '{name}' with {len(prods)} product(s) ({sum(p['qty'] for p in prods)} units)\n")
        return

    # --- Add products ---
    if args.action == "add":
        name = args.portfolio_name
        if not name:
            print("❌ Usage: python tracker.py portfolio add <name> [Product1 Product2 ...]\n")
            return
        pf = _get_portfolio_from(name, portfolios)
        if not pf:
            print(f"❌ Portfolio '{name}' not found.\n")
            return
        added = []
        for a in args.products:
            resolved_name, qty, orig = _resolve(a)
            if resolved_name:
                existing = next((p for p in pf["products"] if p["name"] == resolved_name), None)
                if existing:
                    existing["qty"] += qty
                else:
                    pf["products"].append({"name": resolved_name, "qty": qty})
                added.append(f"{resolved_name}×{qty}" if qty > 1 else resolved_name)
        save_portfolios(portfolios_data)
        if added:
            print(f"✅ Added to '{name}': {", ".join(added)}")
        print()
        return

    # --- Remove products ---
    if args.action == "remove":
        name = args.portfolio_name
        if not name:
            print("❌ Usage: python tracker.py portfolio remove <name> [Product1 Product2 ...]\n")
            return
        pf = _get_portfolio_from(name, portfolios)
        if not pf:
            print(f"❌ Portfolio '{name}' not found.\n")
            return
        removed = []
        for a in args.products:
            resolved_name, qty, _ = _resolve(a)
            if resolved_name:
                existing = next((p for p in pf["products"] if p["name"] == resolved_name), None)
                if existing:
                    if qty >= existing["qty"]:
                        pf["products"].remove(existing)
                        removed.append(existing["name"])
                    else:
                        existing["qty"] -= qty
                        removed.append(f"{existing['name']}×{qty}")
                    save_portfolios(portfolios_data)
        if removed:
            print(f"🗑️  Removed from '{name}': {", ".join(removed)}")
        else:
            print(f"⚠️  Nothing matched.\n")
        print()
        return

    # --- Report (HTML) ---
    if args.action == "report":
        pf = _get_portfolio_from(args.portfolio_name, portfolios)
        if not pf:
            print(f"❌ Portfolio '{args.portfolio_name}' not found.\n")
            return
        html = build_portfolio_html(db, args.portfolio_name, days=args.days)
        out = args.output or f"portfolio_{pf['name'].lower().replace(' ', '_')}.html"
        Path(out).write_text(html)
        print(f"✅ Generated: {out} ({len(html)/1024:.0f} KB)\n")
        return

    # --- Console summary ---
    pf_name = args.action
    pf = _get_portfolio_from(pf_name, portfolios)
    if not pf:
        avail = ", ".join(p["name"] for p in portfolios)
        print(f"❌ Portfolio '{pf_name}' not found. Available: {avail}\n")
        return
    prods = pf.get("products", [])
    total_units = sum(p["qty"] for p in prods)
    total_value = 0.0
    print(f"\n📊 {pf['name']}")
    if pf.get("description"):
        print(f"   {pf['description']}")
    print()
    for pc in prods:
        p = next((x for x in db.get_products() if x["name"] == pc["name"]), None)
        if p:
            snap = db.get_latest_snapshot(p["id"])
            price = snap["price_avg"] if snap and snap["price_avg"] else None
            if price:
                subtotal = price * pc["qty"]
                total_value += subtotal
                qty_tag = f" ×{pc['qty']}" if pc["qty"] > 1 else ""
                print(f"   ✓ {pc['name'][:44]:44s}  €{price:>7.2f}{qty_tag}  (€{subtotal:>7.2f})")
            else:
                print(f"   ○ {pc['name'][:44]:44s}  —")
    print()
    print(f"   Value: €{total_value:,.2f}  |  {total_units} units, {len(prods)} products")
    print()
    print(f"   📄 Full HTML → portfolio report \"{pf_name}\" -o report.html")
    print()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(prog="tracker",
        description="Track MTG booster display prices on Cardmarket 📊")
    s = p.add_subparsers(dest="command", required=True)

    s.add_parser("demo", help="Seed database with 91 days of demo data")
    s.add_parser("setup", help="Configure Cardmarket API credentials")
    s.add_parser("verify", help="Test API credentials")
    f = s.add_parser("find", help="Search Cardmarket products")
    f.add_argument("query", nargs="+")

    a = s.add_parser("add", help="Add product")
    a.add_argument("name"); a.add_argument("identifier")

    r = s.add_parser("remove", help="Remove product")
    r.add_argument("ident")

    s.add_parser("check", help="Fetch latest prices")
    s.add_parser("list", help="Show latest prices")

    i = s.add_parser("info", help="Product detail + history")
    i.add_argument("ident"); i.add_argument("--days", type=int, default=30)

    c = s.add_parser("chart", help="Generate price chart")
    c.add_argument("ident"); c.add_argument("--days", type=int, default=90)
    c.add_argument("--output", "-o", default=None)

    e = s.add_parser("export", help="Export as CSV")
    e.add_argument("path", nargs="?", default=None)

    pr = s.add_parser("price", help="Manually record a price")
    pr.add_argument("ident"); pr.add_argument("avg", type=float)

    pf = s.add_parser("portfolio", help="Portfolio management")
    pf.add_argument("action", nargs="?", default="list",
                    help="'list','create','report','add','remove', or a portfolio name")
    pf.add_argument("portfolio_name", nargs="?", help="Portfolio name")
    pf.add_argument("products", nargs="*", help="Product names")
    pf.add_argument("--output", "-o", default=None, help="Output HTML path")
    pf.add_argument("--days", type=int, default=90, help="Lookback days (default: 90)")

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    {"demo": cmd_demo, "setup": cmd_setup, "verify": cmd_verify, "find": cmd_find,
     "add": cmd_add, "remove": cmd_remove, "check": cmd_check,
     "list": cmd_list, "info": cmd_info, "chart": cmd_chart,
     "export": cmd_export, "price": cmd_price,
     "portfolio": cmd_portfolio}.get(args.command)(args)


if __name__ == "__main__":
    main()
