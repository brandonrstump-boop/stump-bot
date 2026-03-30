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
logging.basicConfig(level=logging.INFO, format=”%(asctime)s [%(levelname)s] %(message)s”, datefmt=”%Y-%m-%d %H:%M:%S”)
log = logging.getLogger(“stump”)
STOCK_TICKERS = os.getenv(“STOCK_TICKERS”, “AAPL,NVDA,MSFT”).split(”,”)
CRYPTO_TICKERS = os.getenv(“CRYPTO_TICKERS”, “BTC,ETH,SOL”).split(”,”)
INTERVAL_MINS = int(os.getenv(“ANALYSIS_INTERVAL_MINUTES”, “30”))

def run_cycle():
now = datetime.utcnow().strftime(”%Y-%m-%d %H:%M UTC”)
log.info(“Starting analysis cycle - “ + now)
try:
snapshot = get_market_snapshot(STOCK_TICKERS, CRYPTO_TICKERS)
if not snapshot:
log.warning(“Empty snapshot - skipping cycle”)
return
log.info(“Got prices for: “ + str(list(snapshot.keys())))
except Exception as e:
log.error(“Market data error: “ + str(e))
return
try:
signals = generate_signals(snapshot)
if not signals:
log.warning(“No signals generated”)
return
log.info(“Generated “ + str(len(signals)) + “ signals”)
except Exception as e:
log.error(“AI signal error: “ + str(e))
return
try:
executed = execute_signals(signals, snapshot)
except Exception as e:
log.error(“Trade execution error: “ + str(e))
executed = []
try:
send_telegram(signals, snapshot, executed)
except Exception as e:
log.error(“Telegram alert error: “ + str(e))
log.info(“Cycle complete”)

def main():
log.info(“STUMP TRADER starting up…”)
log.info(“Stocks: “ + str(STOCK_TICKERS))
log.info(“Crypto: “ + str(CRYPTO_TICKERS))
log.info(“Interval: every “ + str(INTERVAL_MINS) + “ minutes”)
try:
send_telegram([], {}, [], startup=True)
except Exception as e:
log.warning(“Startup ping failed: “ + str(e))
run_cycle()
schedule.every(INTERVAL_MINS).minutes.do(run_cycle)
log.info(“Scheduled - next run in “ + str(INTERVAL_MINS) + “ minutes”)
while True:
schedule.run_pending()
time.sleep(30)

if **name** == “**main**”:
main() 