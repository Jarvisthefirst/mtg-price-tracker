# MTG Price Tracker 📊

**Track, visualize, and export your MTG booster display portfolio — in your browser.**

- 🖱️ **Click, don't type** — full web UI at `http://localhost:8080`
- 📦 **Quantity support** — own 3 boxes of MH3 and 2 of Commander Masters? Just say so
- 📄 **Self-contained HTML reports** — open in any browser, no server needed
- 🌐 **Live prices** via Cardmarket API (optional), or enter prices manually

## One-Click Start

### Mac / Linux
```bash
git clone https://github.com/Jarvisthefirst/mtg-price-tracker.git
cd mtg-price-tracker
bash start.sh
```

### Windows
```bash
git clone https://github.com/Jarvisthefirst/mtg-price-tracker.git
cd mtg-price-tracker
double-click start.bat
```

**That's it.** The script creates a virtualenv, installs dependencies, seeds demo data, and opens the browser.

## What It Looks Like

| Tab | What you can do |
|-----|----------------|
| **Dashboard** | See all prices, bar chart overview |
| **Products** | Add/remove products, view price charts, set manual prices |
| **Portfolios** | Create named groups, add products with quantities, edit inline |
| **Report** | Download a self-contained HTML report with charts |

## Browser Features

- **Drag-and-drop portfolio editing** — add/remove products, set quantities, all in the browser
- **Charts** powered by Chart.js
- **One-click HTML report download** — fully self-contained file with base64 charts
- **CSV export** for spreadsheets
- **Manual price entry** when you don't have API access

## Example: Portfolio with Quantities

1. Open `http://localhost:8080`
2. Go to **Portfolios** → **Create** → name it "My Collection"
3. Click the portfolio card to edit
4. Select a product from the dropdown, set quantity, click **Add**
5. Repeat: add MH3×3, Ravnica Remastered×2, Bloomburrow×1
6. Go to **Report**, pick your portfolio, click **Download HTML Report**
7. Open the downloaded file — it has charts, summaries, and per-product detail cards

## Live Prices via Cardmarket API (Optional)

1. Register at https://www.cardmarket.com/en/Developer
2. Create an application → get 4 API credentials
3. In terminal: `python3 tracker.py setup`
4. `python3 tracker.py verify` → confirm it works
5. `python3 tracker.py check` → fetch live prices

Without the API you can enter prices manually in the browser UI.

## CLI Commands (Still Available)

```bash
python3 tracker.py demo                      # Seed demo data
python3 tracker.py list                      # Show all prices
python3 tracker.py portfolio "My Collection" # Console summary
python3 tracker.py portfolio report "Premium" --out report.html
python3 tracker.py export data.csv
python3 tracker.py price "MH3" 195.50
```

## Project Structure

```
mtg-price-tracker/
├── start.sh / start.bat   # One-click launcher
├── web_app.py             # Flask web server
├── index.html             # Browser UI (single page app)
├── tracker.py             # CLI interface
├── database.py            # SQLite storage
├── portfolio.py           # Portfolio management + HTML reports
├── reporter.py            # Tables, charts, CSV export
├── api.py                 # Cardmarket API client (optional)
├── seed_demo.py           # Demo data generator
├── products.json          # Tracked product metadata
├── portfolios.json        # Portfolio definitions
├── config.json            # API credentials
└── requirements.txt       # Python dependencies
```
