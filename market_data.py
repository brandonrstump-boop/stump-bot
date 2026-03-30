“””
market_data.py — Fetches real-time prices
Stocks:  Alpaca Markets API
Crypto:  Twelve Data API
“””

import os
import requests
import logging
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(“stump.data”)

ALPACA_KEY_ID    = os.getenv(“ALPACA_KEY_ID”)
ALPACA_SECRET    = os.getenv(“ALPACA_SECRET_KEY”)
TWELVE_DATA_KEY  = os.getenv(“TWELVE_DATA_KEY”)

# ─────────────────────────────────────────

# STOCKS via Alpaca

# ─────────────────────────────────────────

def get_stock_prices(tickers: list[str]) -> dict:
if not tickers:
return {}

```
headers = {
    "APCA-API-KEY-ID":     ALPACA_KEY_ID,
    "APCA-API-SECRET-KEY": ALPACA_SECRET,
}
symbols = ",".join(tickers)
result  = {}

# Latest trade price
try:
    resp = requests.get(
        "https://data.alpaca.markets/v2/stocks/trades/latest",
        headers=headers,
        params={"symbols": symbols},
        timeout=10,
    )
    resp.raise_for_status()
    trades = resp.json().get("trades", {})
except Exception as e:
    log.error(f"Alpaca trades error: {e}")
    return {}

# Daily bars for % change
try:
    resp2 = requests.get(
        "https://data.alpaca.markets/v2/stocks/bars",
        headers=headers,
        params={"symbols": symbols, "timeframe": "1Day", "limit": 2},
        timeout=10,
    )
    resp2.raise_for_status()
    bars_data = resp2.json().get("bars", {})
except Exception as e:
    log.warning(f"Alpaca bars error (using 0% change): {e}")
    bars_data = {}

for ticker in tickers:
    trade = trades.get(ticker, {})
    price = trade.get("p", 0)
    if not price:
        continue

    bars       = bars_data.get(ticker, [])
    change_24h = 0.0
    volume     = 0

    if len(bars) >= 2:
        prev_close = bars[-2].get("c", price)
        change_24h = round(((price - prev_close) / prev_close) * 100, 2) if prev_close else 0
        volume     = bars[-1].get("v", 0)
    elif len(bars) == 1:
        volume = bars[0].get("v", 0)

    result[ticker] = {
        "price":     price,
        "change_24h": change_24h,
        "volume":    volume,
        "type":      "stock",
    }
    log.info(f"  {ticker}: ${price:.2f} ({change_24h:+.2f}%)")

return result
```

# ─────────────────────────────────────────

# CRYPTO via Twelve Data

# ─────────────────────────────────────────

TWELVE_CRYPTO_MAP = {
“BTC”:  “BTC/USD”,
“ETH”:  “ETH/USD”,
“SOL”:  “SOL/USD”,
“XRP”:  “XRP/USD”,
“ADA”:  “ADA/USD”,
“DOGE”: “DOGE/USD”,
“AVAX”: “AVAX/USD”,
“LINK”: “LINK/USD”,
“DOT”:  “DOT/USD”,
“LTC”:  “LTC/USD”,
}

def get_crypto_prices(tickers: list[str]) -> dict:
if not tickers:
return {}

```
result = {}
for ticker in tickers:
    symbol = TWELVE_CRYPTO_MAP.get(ticker)
    if not symbol:
        log.warning(f"No Twelve Data mapping for {ticker} — skipping")
        continue
    try:
        # Current price
        resp = requests.get(
            "https://api.twelvedata.com/price",
            params={"symbol": symbol, "apikey": TWELVE_DATA_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        price_data = resp.json()
        price = float(price_data.get("price", 0))
        if not price:
            continue

        # 24h change via quote endpoint
        resp2 = requests.get(
            "https://api.twelvedata.com/quote",
            params={"symbol": symbol, "apikey": TWELVE_DATA_KEY},
            timeout=10,
        )
        resp2.raise_for_status()
        quote = resp2.json()
        change_24h = float(quote.get("percent_change", 0))
        volume     = float(quote.get("volume", 0))

        result[ticker] = {
            "price":      price,
            "change_24h": round(change_24h, 2),
            "volume":     volume,
            "type":       "crypto",
        }
        log.info(f"  {ticker}: ${price:.4f} ({change_24h:+.2f}%)")

    except Exception as e:
        log.error(f"Twelve Data error for {ticker}: {e}")

return result
```

# ─────────────────────────────────────────

# COMBINED SNAPSHOT

# ─────────────────────────────────────────

def get_market_snapshot(stock_tickers: list[str], crypto_tickers: list[str]) -> dict:
log.info(“Fetching market snapshot…”)
snapshot = {}
if stock_tickers:
snapshot.update(get_stock_prices(stock_tickers))
if crypto_tickers:
snapshot.update(get_crypto_prices(crypto_tickers))
return snapshot
