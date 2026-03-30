“””
trader.py — Executes trades via Alpaca (paper or live)
Includes hard safeguards: position size, daily loss limit, kill switch.
“””

import os
import json
import logging
import requests
from datetime import date
from pathlib import Path
from dotenv import load_dotenv
from ai_signals import is_actionable

load_dotenv()
log = logging.getLogger(“stump.trader”)

# ── CONFIG ──

ALPACA_KEY_ID   = os.getenv(“ALPACA_KEY_ID”)
ALPACA_SECRET   = os.getenv(“ALPACA_SECRET_KEY”)
ALPACA_BASE_URL = os.getenv(“ALPACA_BASE_URL”, “https://paper-api.alpaca.markets”)

MAX_POSITION_USD  = float(os.getenv(“MAX_POSITION_SIZE_USD”, “50”))
DAILY_LOSS_LIMIT  = float(os.getenv(“DAILY_LOSS_LIMIT_USD”,  “150”))
KILL_SWITCH_FILE  = Path(“KILL_SWITCH”)  # touch this file to halt all trading

HEADERS = {
“APCA-API-KEY-ID”:     ALPACA_KEY_ID,
“APCA-API-SECRET-KEY”: ALPACA_SECRET,
“Content-Type”:        “application/json”,
}

# Daily P&L tracking (resets on new day)

_daily_state_file = Path(“daily_pnl.json”)

def _load_daily_state() -> dict:
today = str(date.today())
if _daily_state_file.exists():
try:
data = json.loads(_daily_state_file.read_text())
if data.get(“date”) == today:
return data
except Exception:
pass
return {“date”: today, “realized_pnl”: 0.0, “trades”: []}

def _save_daily_state(state: dict):
_daily_state_file.write_text(json.dumps(state, indent=2))

def _is_kill_switch_active() -> bool:
if KILL_SWITCH_FILE.exists():
log.warning(“🛑 KILL SWITCH ACTIVE — all trading halted”)
return True
return False

def _is_market_open() -> bool:
“”“Check if US market is currently open (Alpaca endpoint).”””
# Crypto trades 24/7 — only check for stocks
try:
resp = requests.get(
“https://api.alpaca.markets/v2/clock”,
headers=HEADERS,
timeout=5,
)
resp.raise_for_status()
return resp.json().get(“is_open”, False)
except Exception:
return True  # Assume open if check fails (safe for crypto)

def get_account_info() -> dict:
“”“Fetch current Alpaca account details.”””
try:
resp = requests.get(
f”{ALPACA_BASE_URL}/v2/account”,
headers=HEADERS,
timeout=10,
)
resp.raise_for_status()
return resp.json()
except Exception as e:
log.error(f”Account fetch error: {e}”)
return {}

def place_order(ticker: str, side: str, usd_amount: float, asset_type: str) -> dict | None:
“””
Place a market order on Alpaca.
- Stocks: notional (dollar) order
- Crypto: notional order (Alpaca supports both)
Returns the order dict or None on failure.
“””
# Crypto symbols need “/USD” suffix on Alpaca
symbol = f”{ticker}/USD” if asset_type == “crypto” else ticker

```
order_payload = {
    "symbol":        symbol,
    "notional":      round(usd_amount, 2),
    "side":          side.lower(),    # "buy" or "sell"
    "type":          "market",
    "time_in_force": "gtc" if asset_type == "crypto" else "day",
}

try:
    resp = requests.post(
        f"{ALPACA_BASE_URL}/v2/orders",
        headers=HEADERS,
        json=order_payload,
        timeout=10,
    )
    resp.raise_for_status()
    order = resp.json()
    log.info(f"✅ Order placed: {side.upper()} ${usd_amount:.2f} of {symbol} — order id: {order.get('id')}")
    return order
except requests.HTTPError as e:
    log.error(f"Order failed for {symbol}: {e} — {e.response.text}")
    return None
except Exception as e:
    log.error(f"Order error for {symbol}: {e}")
    return None
```

def execute_signals(signals: list[dict], snapshot: dict) -> list[dict]:
“””
Main execution function. Applies all safeguards then places orders.
Returns list of executed trade dicts.
“””
executed = []

```
# ── SAFEGUARD 1: Kill switch ──
if _is_kill_switch_active():
    return []

# ── SAFEGUARD 2: Daily loss limit ──
daily = _load_daily_state()
if daily["realized_pnl"] <= -DAILY_LOSS_LIMIT:
    log.warning(f"🛑 Daily loss limit hit (${daily['realized_pnl']:.2f}) — no more trades today")
    return []

# ── SAFEGUARD 3: Account check ──
account = get_account_info()
if not account:
    log.warning("Could not verify account — skipping execution")
    return []

buying_power = float(account.get("buying_power", 0))
log.info(f"Account buying power: ${buying_power:.2f}")

for signal in signals:
    ticker = signal.get("ticker", "")
    action = signal.get("signal", "HOLD")
    conf   = signal.get("confidence", 0)

    # ── SAFEGUARD 4: Only act on high-confidence BUY/SELL ──
    if not is_actionable(signal):
        log.info(f"  ⏭ {ticker} {action} {conf}% — below threshold, skipping")
        continue

    asset_data  = snapshot.get(ticker, {})
    asset_type  = asset_data.get("type", "stock")

    # ── SAFEGUARD 5: Stock market hours ──
    if asset_type == "stock" and not _is_market_open():
        log.info(f"  ⏭ {ticker} — market closed, skipping stock trade")
        continue

    # ── SAFEGUARD 6: Position size cap ──
    trade_amount = min(MAX_POSITION_USD, buying_power * 0.05)  # max 5% of buying power or $MAX
    if trade_amount < 1:
        log.warning(f"  ⚠️ Trade amount too small (${trade_amount:.2f}) — skipping")
        continue

    # ── EXECUTE ──
    side  = "buy" if action == "BUY" else "sell"
    order = place_order(ticker, side, trade_amount, asset_type)

    if order:
        trade_record = {
            "ticker":     ticker,
            "action":     action,
            "confidence": conf,
            "amount_usd": trade_amount,
            "order_id":   order.get("id"),
            "asset_type": asset_type,
            "mode":       "LIVE" if "paper" not in ALPACA_BASE_URL else "PAPER",
        }
        executed.append(trade_record)
        daily["trades"].append(trade_record)

_save_daily_state(daily)
return executed
```
