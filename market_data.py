import os
import time
import requests
import logging
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("stump.data")
ALPACA_KEY_ID   = os.getenv("ALPACA_KEY_ID")
ALPACA_SECRET   = os.getenv("ALPACA_SECRET_KEY")
TWELVE_DATA_KEY = os.getenv("TWELVE_DATA_KEY")

TWELVE_CRYPTO_MAP = {
    "BTC":   "BTC/USD",
    "ETH":   "ETH/USD",
    "SOL":   "SOL/USD",
    "XRP":   "XRP/USD",
    "ADA":   "ADA/USD",
    "DOGE":  "DOGE/USD",
    "AVAX":  "AVAX/USD",
    "LINK":  "LINK/USD",
    "DOT":   "DOT/USD",
    "LTC":   "LTC/USD",
    "MATIC": "MATIC/USD",
    "UNI":   "UNI/USD",
    "ATOM":  "ATOM/USD",
}

def get_stock_prices(tickers):
    if not tickers:
        return {}
    headers = {
        "APCA-API-KEY-ID":     ALPACA_KEY_ID,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
    }
    symbols = ",".join(tickers)
    result  = {}
    try:
        resp = requests.get("https://data.alpaca.markets/v2/stocks/trades/latest", headers=headers, params={"symbols": symbols}, timeout=10)
        resp.raise_for_status()
        trades = resp.json().get("trades", {})
    except Exception as e:
        log.error("Alpaca trades error: " + str(e))
        return {}
    try:
        resp2 = requests.get("https://data.alpaca.markets/v2/stocks/bars", headers=headers, params={"symbols": symbols, "timeframe": "1Day", "limit": 2}, timeout=10)
        resp2.raise_for_status()
        bars_data = resp2.json().get("bars", {})
    except Exception as e:
        log.warning("Alpaca bars error: " + str(e))
        bars_data = {}
    for ticker in tickers:
        trade = trades.get(ticker, {})
        price = trade.get("p", 0)
        if not price:
            continue
        bars       = bars_data.get(ticker, [])
        change_24h = 0.0
        change_1h  = 0.0
        volume     = 0
        if len(bars) >= 2:
            prev_close = bars[-2].get("c", 0)
            change_24h = round(((price - prev_close) / prev_close) * 100, 2) if prev_close else 0
            volume     = bars[-1].get("v", 0)
            open_price = bars[-1].get("o", price)
            change_1h  = round(((price - open_price) / open_price) * 100, 2) if open_price else 0
        elif len(bars) == 1:
            prev_close = bars[0].get("o", price)
            change_24h = round(((price - prev_close) / prev_close) * 100, 2) if prev_close else 0
            volume     = bars[0].get("v", 0)
        result[ticker] = {"price": price, "change_24h": change_24h, "change_1h": change_1h, "volume": volume, "type": "stock"}
        log.info(ticker + ": $" + str(round(price, 2)) + " 24h=" + str(change_24h) + "% 1h=" + str(change_1h) + "%")
    return result

def get_crypto_price(ticker, retries=3):
    symbol = TWELVE_CRYPTO_MAP.get(ticker)
    if not symbol:
        log.warning("No mapping for " + ticker)
        return None
    for attempt in range(retries):
        try:
            resp = requests.get("https://api.twelvedata.com/price", params={"symbol": symbol, "apikey": TWELVE_DATA_KEY}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if "price" not in data:
                log.warning(ticker + " price missing - attempt " + str(attempt + 1))
                time.sleep(2)
                continue
            price = float(data["price"])
            if not price:
                continue
            resp2 = requests.get("https://api.twelvedata.com/quote", params={"symbol": symbol, "apikey": TWELVE_DATA_KEY}, timeout=10)
            resp2.raise_for_status()
            quote      = resp2.json()
            change_24h = round(float(quote.get("percent_change", 0)), 2)
            volume     = float(quote.get("volume", 0))
            change_1h  = 0.0
            try:
                resp3 = requests.get(
                    "https://api.twelvedata.com/time_series",
                    params={"symbol": symbol, "interval": "1h", "outputsize": 2, "apikey": TWELVE_DATA_KEY},
                    timeout=10,
                )
                resp3.raise_for_status()
                values = resp3.json().get("values", [])
                if len(values) >= 2:
                    curr_close = float(values[0].get("close", price))
                    prev_close = float(values[1].get("close", curr_close))
                    change_1h  = round(((curr_close - prev_close) / prev_close) * 100, 2) if prev_close else 0.0
            except Exception:
                change_1h = 0.0
            log.info(ticker + ": $" + str(round(price, 4)) + " 24h=" + str(change_24h) + "% 1h=" + str(change_1h) + "%")
            return {"price": price, "change_24h": change_24h, "change_1h": change_1h, "volume": volume, "type": "crypto"}
        except Exception as e:
            log.error("Twelve Data error for " + ticker + " attempt " + str(attempt + 1) + ": " + str(e))
            if attempt < retries - 1:
                time.sleep(2)
    return None

def get_crypto_prices(tickers):
    if not tickers:
        return {}
    result = {}
    for ticker in tickers:
        data = get_crypto_price(ticker)
        if data:
            result[ticker] = data
        else:
            log.warning(ticker + " failed after retries - skipping")
    return result

def get_market_snapshot(stock_tickers, crypto_tickers):
    log.info("Fetching market snapshot...")
    snapshot = {}
    if stock_tickers:
        snapshot.update(get_stock_prices(stock_tickers))
    if crypto_tickers:
        snapshot.update(get_crypto_prices(crypto_tickers))
    return snapshot
