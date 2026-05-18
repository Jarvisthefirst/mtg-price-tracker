#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# MTG Price Tracker — one-click launcher
# Creates a virtualenv, installs deps, starts web server
# ──────────────────────────────────────────────────────────
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo ""
echo "  ⚡ MTG Price Tracker — Starting..."
echo ""

# 1. Create virtualenv if needed
if [ ! -d venv ]; then
    echo "  📦 Creating virtualenv..."
    python3 -m venv venv
fi

# 2. Activate
source venv/bin/activate

# 3. Install dependencies
echo "  📥 Installing dependencies..."
pip install -q -r requirements.txt 2>/dev/null || true
pip install -q flask requests-oauthlib matplotlib 2>/dev/null || true

# 4. Seed demo data if DB doesn't exist
if [ ! -f price_history.db ]; then
    echo "  🌱 Seeding demo data..."
    python3 tracker.py demo
fi

# 5. Start web server
echo ""
echo "  🌐 Opening browser..."
echo "     http://localhost:8080"
echo ""
echo "     Press Ctrl+C to stop"
echo ""
python3 web_app.py
