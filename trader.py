import os
import json
import logging
import requests
from datetime import date, datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from ai_signals import is_actionable

load_dotenv()
log = logging.getLogger("stump.trader")
ALPACA_KEY_ID    = os.getenv("ALPACA_KEY_ID")
ALPACA_SECRET    = os.getenv("ALPACA_SECRET_KEY")
ALPACA_BASE_URL  = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
MAX_POSITION_USD = float(os.getenv("MAX_POSITION_SIZE_USD", "50"))
DAILY_LOSS_LIMIT = float(os.getenv("DAILY_LOSS_LIMIT_USD", "150"))
KILL_SWITCH_FILE = Path("KILL_SWITCH")
DAILY_STATE_FILE = Path("daily_pnl.json")
PNL_LOG_FILE     = Path("signal_pnl.json")

HEADERS = {
    "APCA-API-KEY-ID":     ALPACA_KEY_ID,
    "APCA-API-SECRET-KEY": ALPACA_SECRET,
    "Content-Type":        "application/json",
}

# Stop loss tiers
STABLE_STOCKS   = {"AAPL", "MSFT", "AMZN", "SPY", "QQQ", "NVDA", "AMD", "GOOGL", "GLD", "TLT", "IWM", "XLF"}
VOLATILE_STOCKS = {"TSLA", "COIN", "MSTR", "META", "PLTR", "NFLX", "UBER", "ARM", "HOOD", "SMCI", "SOFI", "RKLB"}
CRYPTO          = {"BTC", "ETH", "SOL", "XRP", "DOGE", "AVAX", "LINK", "ADA", "LTC", "MATIC", "UNI", "ATOM", "DOT"}

STOP_LOSS_PCT = {
    "stable":   0.05,
    "volatile": 0.08,
    "crypto":   0.10,
}

# Pyramid rules: buy number -> (min % gain from prev buy, min confidence)
PYRAMID_RULES = {
    1: (0.0, 65),
    2: (1.0, 65),
    3: (2.0, 70),
    4: (3.0, 75),
    5: (4.0, 80),
}
MAX_BUYS_PER_DAY = 5

def get_stop_loss_pct(ticker):
    if ticker in STABLE_STOCKS:   return STOP_LOSS_PCT["stable"]
    if ticker in VOLATILE_STOCKS: return STOP_LOSS_PCT["volatile"]
    if ticker in CRYPTO:          return STOP_LOSS_PCT["crypto"]
    return STOP_LOSS_PCT["volatile"]

def load_daily_state():
    today = str(date.today())
    if DAILY_STATE_FILE.exists():
        try:
            data = json.loads(DAILY_STATE_FILE.read_text())
            if data.get("date") == today:
                return data
        except Exception:
            pass
    return {"date": today, "realized_pnl": 0.0, "trades": []}

def save_daily_state(state):
    DAILY_STATE_FILE.write_text(json.dumps(state, indent=2))

def load_pnl_log():
    if PNL_LOG_FILE.exists():
        try:
            return json.loads(PNL_LOG_FILE.read_text())
        except Exception:
            pass
    return []

def save_pnl_log(log_data):
    PNL_LOG_FILE.write_text(json.dumps(log_data, indent=2))

def log_signal_for_tracking(signal, price, order_id):
    pnl_log = load_pnl_log()
    pnl_log.append({
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "ticker":      signal.get("ticker"),
        "action":      signal.get("signal"),
        "confidence":  signal.get("confidence"),
        "timeframe":   signal.get("timeframe"),
        "entry_price": price,
        "order_id":    order_id,
        "closed":      False,
        "exit_price":  None,
        "pnl":         None,
    })
    save_pnl_log(pnl_log)

def is_kill_switch_active():
    if KILL_SWITCH_FILE.exists():
        log.warning("KILL SWITCH ACTIVE - all trading halted")
        return True
    return False

def is_market_open():
    try:
        resp = requests.get("https://api.alpaca.markets/v2/clock", headers=HEADERS, timeout=5)
        resp.raise_for_status()
        return resp.json().get("is_open", False)
    except Exception:
        return True

def get_account_info():
    try:
        resp = requests.get(ALPACA_BASE_URL + "/v2/account", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.error("Account fetch error: " + str(e))
        return {}

def get_open_positions():
    try:
        resp = requests.get(ALPACA_BASE_URL + "/v2/positions", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        positions = resp.json()
        held = {}
        for p in positions:
            symbol = p.get("symbol", "").replace("/USD", "").replace("USD", "")
            held[symbol] = {
                "qty":             float(p.get("qty", 0)),
                "avg_entry":       float(p.get("avg_entry_price", 0)),
                "market_value":    float(p.get("market_value", 0)),
                "unrealized_pl":   float(p.get("unrealized_pl", 0)),
                "unrealized_plpc": float(p.get("unrealized_plpc", 0)),
            }
        return held
    except Exception as e:
        log.error("Positions fetch error: " + str(e))
        return {}

def check_pyramid_eligibility(ticker, current_price, daily, conf):
    buys_today = [t for t in daily["trades"] if t.get("ticker") == ticker and t.get("action") == "BUY"]
    buy_count  = len(buys_today)
    if buy_count >= MAX_BUYS_PER_DAY:
        log.info(ticker + " max buys reached (" + str(MAX_BUYS_PER_DAY) + ") - skipping")
        return False
    next_buy_num       = buy_count + 1
    min_gain_pct, min_conf = PYRAMID_RULES.get(next_buy_num, (99.0, 99))
    if conf < min_conf:
        log.info(ticker + " buy #" + str(next_buy_num) + " needs " + str(min_conf) + "% confidence, got " + str(conf) + "% - skipping")
        return False
    if buy_count > 0 and min_gain_pct > 0:
        last_price = buys_today[-1].get("entry_price", 0)
        if last_price > 0:
            gain_pct = ((current_price - last_price) / last_price) * 100
            if gain_pct < min_gain_pct:
                log.info(ticker + " buy #" + str(next_buy_num) + " needs +" + str(min_gain_pct) + "% from last buy, only +" + str(round(gain_pct, 2)) + "% - skipping")
                return False
            log.info(ticker + " buy #" + str(next_buy_num) + " pyramid approved - +" + str(round(gain_pct, 2)) + "% from last buy")
    return True

def check_stop_losses(held_positions, snapshot):
    stop_loss_tickers = []
    for ticker, pos in held_positions.items():
        avg_entry = pos.get("avg_entry", 0)
        if avg_entry <= 0:
            continue
        current_price = snapshot.get(ticker, {}).get("price", 0)
        if current_price <= 0:
            continue
        stop_pct = get_stop_loss_pct(ticker)
        loss_pct = (current_price - avg_entry) / avg_entry
        if loss_pct <= -stop_pct:
            log.warning(ticker + " stop loss triggered: " + str(round(loss_pct * 100, 2)) + "% loss (threshold: -" + str(round(stop_pct * 100, 0)) + "%)")
            stop_loss_tickers.append(ticker)
    return stop_loss_tickers

def place_order(ticker, side, usd_amount, asset_type, qty=None):
    symbol = ticker + "/USD" if asset_type == "crypto" else ticker
    if qty and side == "sell":
        order_payload = {
            "symbol":        symbol,
            "qty":           str(qty),
            "side":          "sell",
            "type":          "market",
            "time_in_force": "gtc" if asset_type == "crypto" else "day",
        }
    else:
        order_payload = {
            "symbol":        symbol,
            "notional":      round(usd_amount, 2),
            "side":          side.lower(),
            "type":          "market",
            "time_in_force": "gtc" if asset_type == "crypto" else "day",
        }
    try:
        resp = requests.post(ALPACA_BASE_URL + "/v2/orders", headers=HEADERS, json=order_payload, timeout=10)
        resp.raise_for_status()
        order = resp.json()
        log.info("Order placed: " + side.upper() + " " + symbol)
        return order
    except requests.HTTPError as e:
        log.error("Order failed for " + symbol + ": " + str(e))
        return None
    except Exception as e:
        log.error("Order error for " + symbol + ": " + str(e))
        return None

def execute_signals(signals, snapshot):
    executed = []
    if is_kill_switch_active():
        return []
    daily = load_daily_state()
    if daily["realized_pnl"] <= -DAILY_LOSS_LIMIT:
        log.warning("Daily loss limit hit - no more trades today")
        return []
    account = get_account_info()
    if not account:
        log.warning("Could not verify account - skipping execution")
        return []
    buying_power   = float(account.get("buying_power", 0))
    held_positions = get_open_positions()
    log.info("Buying power: $" + str(round(buying_power, 2)))
    log.info("Held positions: " + str(list(held_positions.keys())))

    stop_loss_tickers = check_stop_losses(held_positions, snapshot)
    for ticker in stop_loss_tickers:
        pos        = held_positions[ticker]
        asset_type = "crypto" if ticker in CRYPTO else "stock"
        if asset_type == "stock" and not is_market_open():
            log.info(ticker + " stop loss - market closed, will execute at open")
            continue
        qty   = pos.get("qty", 0)
        order = place_order(ticker, "sell", 0, asset_type, qty=qty)
        if order:
            mode     = "PAPER" if "paper" in ALPACA_BASE_URL else "LIVE"
            stop_pct = get_stop_loss_pct(ticker)
            record   = {
                "ticker":      ticker,
                "action":      "SELL",
                "confidence":  100,
                "amount_usd":  pos.get("market_value", 0),
                "order_id":    order.get("id"),
                "asset_type":  asset_type,
                "mode":        mode,
                "reason":      "STOP LOSS -" + str(round(stop_pct * 100, 0)) + "%",
                "entry_price": snapshot.get(ticker, {}).get("price", 0),
            }
            executed.append(record)
            daily["trades"].append(record)

    for signal in signals:
        ticker      = signal.get("ticker", "")
        action      = signal.get("signal", "HOLD")
        conf        = signal.get("confidence", 0)
        if not is_actionable(signal):
            log.info(ticker + " " + action + " " + str(conf) + "% - below threshold, skipping")
            continue
        asset_data  = snapshot.get(ticker, {})
        asset_type  = asset_data.get("type", "stock")
        entry_price = asset_data.get("price", 0)
        if asset_type == "stock" and not is_market_open():
            log.info(ticker + " - market closed, skipping")
            continue
        if action == "SELL":
            if ticker not in held_positions:
                log.info(ticker + " SELL signal but no position held - skipping")
                continue
            if ticker in stop_loss_tickers:
                log.info(ticker + " already sold via stop loss - skipping")
                continue
            qty = held_positions[ticker].get("qty", 0)
            if qty <= 0:
                log.info(ticker + " SELL signal but zero quantity held - skipping")
                continue
        if action == "BUY":
            if not check_pyramid_eligibility(ticker, entry_price, daily, conf):
                continue
        trade_amount = min(MAX_POSITION_USD, buying_power * 0.05)
        if trade_amount < 1:
            log.warning("Trade amount too small - skipping")
            continue
        if action == "SELL":
            qty   = held_positions[ticker].get("qty", 0)
            order = place_order(ticker, "sell", 0, asset_type, qty=qty)
        else:
            order = place_order(ticker, "buy", trade_amount, asset_type)
        if order:
            mode = "PAPER" if "paper" in ALPACA_BASE_URL else "LIVE"
            trade_record = {
                "ticker":      ticker,
                "action":      action,
                "confidence":  conf,
                "amount_usd":  trade_amount,
                "order_id":    order.get("id"),
                "asset_type":  asset_type,
                "mode":        mode,
                "entry_price": entry_price,
            }
            executed.append(trade_record)
            daily["trades"].append(trade_record)
            log_signal_for_tracking(signal, entry_price, order.get("id"))

    save_daily_state(daily)
    return executed

def get_pnl_summary():
    pnl_log = load_pnl_log()
    if not pnl_log:
        return None
    total    = len(pnl_log)
    closed   = [t for t in pnl_log if t.get("closed")]
    winners  = [t for t in closed if (t.get("pnl") or 0) > 0]
    open_pos = total - len(closed)
    return {
        "total_signals": total,
        "open":          open_pos,
        "closed":        len(closed),
        "winners":       len(winners),
        "losers":        len(closed) - len(winners),
        "win_rate":      round(len(winners) / len(closed) * 100, 1) if closed else 0,
        "total_pnl":     round(sum(t.get("pnl") or 0 for t in closed), 2),
    }
