@echo off
REM MTG Price Tracker — one-click launcher (Windows)
REM Creates a virtualenv, installs deps, starts web server

echo.
echo  ⚡ MTG Price Tracker — Starting...
echo.

IF NOT EXIST venv (
    echo  📦 Creating virtualenv...
    python -m venv venv
)

echo  📥 Installing dependencies...
call venv\Scripts\activate.bat
pip install -q -r requirements.txt 2>nul || ver
pip install -q flask requests-oauthlib matplotlib 2>nul || ver

IF NOT EXIST price_history.db (
    echo  🌱 Seeding demo data...
    python tracker.py demo
)

echo.
echo  🌐 Opening browser...
echo     http://localhost:8080
echo.
echo     Press Ctrl+C to stop
echo.
python web_app.py
pause
