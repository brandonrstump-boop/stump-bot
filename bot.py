import os
import time
import schedule
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv
from market_data import get_market_snapshot
from ai_signals import generate_signals
from trader import execute_signals
from alerts import send_telegram, send_daily_summary

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("stump")

ALL_STOCK_TICKERS  = os.getenv("STOCK_TICKERS",  "AAPL,NVDA,MSFT,TSLA,AMD,AMZN,SPY,QQQ,COIN,MSTR,META,GOOGL,PLTR,NFLX,UBER,ARM,HOOD,SMCI,GLD,TLT,IWM,XLF,SOFI,RKLB,SPY").split(",")
ALL_CRYPTO_TICKERS = os.getenv("CRYPTO_TICKERS", "BTC,ETH,SOL,XRP,DOGE,AVAX,LINK,LTC,ADA,MATIC,UNI,ATOM").split(",")
INTERVAL_MINS      = int(os.getenv("ANALYSIS_INTERVAL_MINUTES", "30"))

def is_stock_market_open():
    now          = datetime.now(timezone.utc)
    et_mins      = (now.hour * 60 + now.minute) - (4 * 60)
    if et_mins < 0:
        et_mins += 24 * 60
    weekday      = now.weekday()
    if now.hour < 4:
        weekday  = (weekday - 1) % 7
    is_weekday   = weekday < 5
    market_open  = 9 * 60 + 30
    market_close = 16 * 60
    return is_weekday and (market_open <= et_mins < market_close)

def run_cycle():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    log.info("Starting analysis cycle - " + now)
    market_open    = is_stock_market_open()
    log.info("Stock market open: " + str(market_open))
    stock_tickers  = ALL_STOCK_TICKERS if market_open else []
    crypto_tickers = ALL_CRYPTO_TICKERS
    try:
        snapshot = get_market_snapshot(stock_tickers, crypto_tickers)
        if not snapshot:
            log.warning("Empty snapshot - skipping cycle")
            return
        log.info("Got prices for: " + str(list(snapshot.keys())))
    except Exception as e:
        log.error("Market data error: " + str(e))
        return
    try:
        signals = generate_signals(snapshot)
        if not signals:
            log.warning("No signals generated")
            return
        log.info("Generated " + str(len(signals)) + " signals")
    except Exception as e:
        log.error("AI signal error: " + str(e))
        return
    try:
        executed = execute_signals(signals, snapshot)
    except Exception as e:
        log.error("Trade execution error: " + str(e))
        executed = []
    try:
        send_telegram(signals, snapshot, executed)
    except Exception as e:
        log.error("Telegram alert error: " + str(e))
    log.info("Cycle complete")

def run_daily_summary():
    log.info("Sending daily summary...")
    try:
        send_daily_summary()
    except Exception as e:
        log.error("Daily summary error: " + str(e))

def main():
    log.info("STUMP TRADER starting up...")
    log.info("Stocks (market hours): " + str(ALL_STOCK_TICKERS))
    log.info("Crypto (24/7): " + str(ALL_CRYPTO_TICKERS))
    log.info("Interval: every " + str(INTERVAL_MINS) + " minutes")
    log.info("Daily summary: 9:00 AM ET")
    try:
        send_telegram([], {}, [], startup=True)
    except Exception as e:
        log.warning("Startup ping failed: " + str(e))
    run_cycle()
    schedule.every(INTERVAL_MINS).minutes.do(run_cycle)
    schedule.every().day.at("13:00").do(run_daily_summary)
    log.info("Scheduled. Next signal cycle in " + str(INTERVAL_MINS) + " minutes.")
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    main()
