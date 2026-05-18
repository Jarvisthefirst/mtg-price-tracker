# MTG Price Tracker 📊

Track the price development of Magic: The Gathering booster displays on Cardmarket — with portfolio grouping and self-contained HTML reports.

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt requests-oauthlib matplotlib

# 2. Seed demo data (try it immediately)
python tracker.py demo
python tracker.py list

# 3. View a portfolio
python tracker.py portfolio "Premium"

# 4. Generate a self-contained HTML report
python tracker.py portfolio report "Premium" --out premium_report.html
# → Open premium_report.html in any browser
```

## All Commands

| Command | What it does |
|---------|-------------|
| `demo` | Seed 91 days of realistic demo data |
| `list` | Latest prices — all products |
| `info <name>` | Detailed price history |
| `chart <name>` | Generate a price chart (PNG) |
| `add <name> <url/id>` | Add a product to track |
| `remove <name>` | Remove a product |
| `price <name> <€>` | Manually record a price |
| `export [file.csv]` | Export all history as CSV |
| `check` | Fetch live prices from the API |
| `setup` | Enter Cardmarket API credentials |
| `verify` | Test API credentials |
| `find <query>` | Search Cardmarket for IDs |

## Portfolios 📂

Group products into portfolios to see **combined price development**:

```bash
# Create a portfolio
python tracker.py portfolio create "My Collection" \
  "Modern Horizons 2" "Commander Masters" "Ravnica Remastered"

# Console summary
python tracker.py portfolio "My Collection"

# Add/remove products
python tracker.py portfolio add "My Collection" "MH3"
python tracker.py portfolio remove "My Collection" "Ravnica"

# Generate a self-contained HTML report (with inline chart!)
python tracker.py portfolio report "Premium" \
  --out premium_report.html --days 90
```

The HTML report is a single file with:
- Embedded base64 chart (no server needed)
- Product cards with 90d history
- Combined portfolio value chart
- Summary stats & CSV data

### Pre-built portfolios

| Portfolio | Products | Description |
|-----------|----------|-------------|
| **Premium** | Commander Masters, Double Masters 2022 | High-end reprint sets |
| **Modern Horizons** | MH3, MH2 | Horizontal cycle evolution |
| **Standard Rotating** | Bloomburrow, Tarkir: Dragonstorm | Recent standard sets |

## Live Prices

The Cardmarket API is free but requires one-time setup:

1. Go to [cardmarket.com/en/Developer](https://www.cardmarket.com/en/Developer)
2. Create an application → get 4 credentials
3. `python tracker.py setup` → paste them in
4. `python tracker.py verify` → confirm it works
5. `python tracker.py check` → fetch live prices

Without the API, you can still manually enter prices:
```bash
python tracker.py price "MH3 Play Box" 198
```

## Project Files

```
mtg-price-tracker/
├── tracker.py          # Main CLI (368 lines)
├── database.py         # SQLite storage
├── api.py              # Cardmarket API client
├── reporter.py         # Table formatting, charts
├── portfolio.py        # Portfolio management + HTML reports
├── seed_demo.py        # Demo data generator
├── products.json       # Tracked products
├── portfolios.json     # Portfolio groups
├── config.json         # API credentials
├── price_history.db    # SQLite database (auto-created)
└── README.md           # This file
```
