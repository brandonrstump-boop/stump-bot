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
ALPACA_KEY_ID = os.getenv(“ALPACA_KEY_ID”)
ALPACA_SECRET = os.getenv(“ALPACA_SECRET_KEY”)
ALPACA_BASE_URL = os.getenv(“ALPACA_BASE_URL”, “https://paper-api.alpaca.markets”)
MAX_POSITION_USD = float(os.getenv(“MAX_POSITION_SIZE_USD”, “50”))
DAILY_LOSS_LIMIT = float(os.getenv(“DAILY_LOSS_LIMIT_USD”, “150”))
KILL_SWITCH_FILE = Path(“KILL_SWITCH”)
DAILY_STATE_FILE = Path(“daily_pnl.json”)
HEADERS = {
“APCA-API-KEY-ID”: ALPACA_KEY_ID,
“APCA-API-SECRET-KEY”: ALPACA_SECRET,
“Content-Type”: “application/json”,
}

def load_daily_state():
today = str(date.today())
if DAILY_STATE_FILE.exists():
try:
data = json.loads(DAILY_STATE_FILE.read_text())
if data.get(“date”) == today:
return data
except Exception:
pass
return {“date”: today, “realized_pnl”: 0.0, “trades”: []}

def save_daily_state(state):
DAILY_STATE_FILE.write_text(json.dumps(state, indent=2))

def is_kill_switch_active():
if KILL_SWITCH_FILE.exists():
log.warning(“KILL SWITCH ACTIVE - all trading halted”)
return True
return False

def is_market_open():
try:
resp = requests.get(“https://api.alpaca.markets/v2/clock”, headers=HEADERS, timeout=5)
resp.raise_for_status()
return resp.json().get(“is_open”, False)
except Exception:
return True

def get_account_info():
try:
resp = requests.get(ALPACA_BASE_URL + “/v2/account”, headers=HEADERS, timeout=10)
resp.raise_for_status()
return resp.json()
except Exception as e:
log.error(“Account fetch error: “ + str(e))
return {}

def place_order(ticker, side, usd_amount, asset_type):
symbol = ticker + “/USD” if asset_type == “crypto” else ticker
order_payload = {
“symbol”: symbol,
“notional”: round(usd_amount, 2),
“side”: side.lower(),
“type”: “market”,
“time_in_force”: “gtc” if asset_type == “crypto” else “day”,
}
try:
resp = requests.post(ALPACA_BASE_URL + “/v2/orders”, headers=HEADERS, json=order_payload, timeout=10)
resp.raise_for_status()
order = resp.json()
log.info(“Order placed: “ + side.upper() + “ $” + str(usd_amount) + “ of “ + symbol)
return order
except requests.HTTPError as e:
log.error(“Order failed for “ + symbol + “: “ + str(e))
return None
except Exception as e:
log.error(“Order error for “ + symbol + “: “ + str(e))
return None

def execute_signals(signals, snapshot):
executed = []
if is_kill_switch_active():
return []
daily = load_daily_state()
if daily[“realized_pnl”] <= -DAILY_LOSS_LIMIT:
log.warning(“Daily loss limit hit - no more trades today”)
return []
account = get_account_info()
if not account:
log.warning(“Could not verify account - skipping execution”)
return []
buying_power = float(account.get(“buying_power”, 0))
log.info(“Buying power: $” + str(round(buying_power, 2)))
for signal in signals:
ticker = signal.get(“ticker”, “”)
action = signal.get(“signal”, “HOLD”)
conf = signal.get(“confidence”, 0)
if not is_actionable(signal):
log.info(ticker + “ “ + action + “ “ + str(conf) + “% - below threshold, skipping”)
continue
asset_data = snapshot.get(ticker, {})
asset_type = asset_data.get(“type”, “stock”)
if asset_type == “stock” and not is_market_open():
log.info(ticker + “ - market closed, skipping”)
continue
trade_amount = min(MAX_POSITION_USD, buying_power * 0.05)
if trade_amount < 1:
log.warning(“Trade amount too small - skipping”)
continue
side = “buy” if action == “BUY” else “sell”
order = place_order(ticker, side, trade_amount, asset_type)
if order:
mode = “PAPER” if “paper” in ALPACA_BASE_URL else “LIVE”
trade_record = {
“ticker”: ticker,
“action”: action,
“confidence”: conf,
“amount_usd”: trade_amount,
“order_id”: order.get(“id”),
“asset_type”: asset_type,
“mode”: mode,
}
executed.append(trade_record)
daily[“trades”].append(trade_record)
save_daily_state(daily)
return executed 