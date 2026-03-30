“””
🌳 STUMP TRADER BOT — bot.py
Main entry point. Runs on a schedule, fetches prices,
generates AI signals, executes paper trades, sends Telegram alerts.
“””

import os
import time
import schedule
import logging
from datetime import datetime
from dotenv import load_dotenv

from market_data import get_market_snapshot
from ai_signals import generate_signals
from trader import execute_signals
from alerts import send_telegram

load_dotenv()

# ── LOGGING ──

logging.basicConfig(
level=logging.INFO,
format=”%(asctime)s [%(levelname)s] %(message)s”,
datefmt=”%Y-%m-%d %H:%M:%S”
)
log = logging.getLogger(“stump”)

# ── CONFIG ──

STOCK_TICKERS  = os.getenv(“STOCK_TICKERS”,  “AAPL,NVDA,MSFT”).split(”,”)
CRYPTO_TICKERS = os.getenv(“CRYPTO_TICKERS”, “BTC,ETH,SOL”).split(”,”)
INTERVAL_MINS  = int(os.getenv(“ANALYSIS_INTERVAL_MINUTES”, “30”))

def run_cycle():
“”“One full analysis + trade cycle.”””
now = datetime.utcnow().strftime(”%Y-%m-%d %H:%M UTC”)
log.info(f”🌱 Starting analysis cycle — {now}”)

```
# 1. Fetch prices
try:
    snapshot = get_market_snapshot(STOCK_TICKERS, CRYPTO_TICKERS)
    if not snapshot:
        log.warning("Empty snapshot — skipping cycle")
        return
    log.info(f"📊 Got prices for: {list(snapshot.keys())}")
except Exception as e:
    log.error(f"Market data error: {e}")
    return

# 2. Generate AI signals
try:
    signals = generate_signals(snapshot)
    if not signals:
        log.warning("No signals generated")
        return
    log.info(f"🤖 Generated {len(signals)} signals")
except Exception as e:
    log.error(f"AI signal error: {e}")
    return

# 3. Execute (paper or live)
try:
    executed = execute_signals(signals, snapshot)
except Exception as e:
    log.error(f"Trade execution error: {e}")
    executed = []

# 4. Send Telegram alert
try:
    send_telegram(signals, snapshot, executed)
except Exception as e:
    log.error(f"Telegram alert error: {e}")

log.info("✅ Cycle complete\n")
```

def main():
log.info(“🌳 STUMP TRADER starting up…”)
log.info(f”   Stocks:  {STOCK_TICKERS}”)
log.info(f”   Crypto:  {CRYPTO_TICKERS}”)
log.info(f”   Interval: every {INTERVAL_MINS} minutes”)

```
# Send startup ping
try:
    send_telegram([], {}, [], startup=True)
except Exception as e:
    log.warning(f"Startup ping failed: {e}")

# Run immediately on start
run_cycle()

# Schedule recurring runs
schedule.every(INTERVAL_MINS).minutes.do(run_cycle)

log.info(f"⏰ Scheduled — next run in {INTERVAL_MINS} minutes")
while True:
    schedule.run_pending()
    time.sleep(30)
```

if **name** == “**main**”:
main()
