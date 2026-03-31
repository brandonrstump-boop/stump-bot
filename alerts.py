import os
import logging
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("stump.alerts")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

def send_message(text):
    if not BOT_TOKEN or not CHAT_ID:
        log.warning("Telegram not configured - skipping alert")
        return
    try:
        resp = requests.post(
            "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        log.error("Telegram send error: " + str(e))

def send_telegram(signals, snapshot, executed, startup=False):
    if startup:
        send_message("Stump is online. Running every 30 min.")
        return
    if not signals:
        return

    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    lines = ["<b>STUMP</b> " + now]

    for sig in signals:
        ticker  = sig.get("ticker", "?")
        action  = sig.get("signal", "HOLD")
        conf    = sig.get("confidence", 0)
        tf      = sig.get("timeframe", "?")
        chg     = snapshot.get(ticker, {}).get("change_24h", 0)
        chg_str = ("+" if chg >= 0 else "") + str(round(chg, 2)) + "%"
        icon    = "+" if action == "BUY" else ("-" if action == "SELL" else "~")
        lines.append(icon + " <b>" + ticker + "</b> " + action + " " + str(conf) + "% | " + tf + " | " + chg_str)

    lines.append("")

    if executed:
        stop_losses = [t for t in executed if t.get("reason", "").startswith("STOP LOSS")]
        normal      = [t for t in executed if not t.get("reason", "").startswith("STOP LOSS")]

        if stop_losses:
            lines.append("<b>STOP LOSS TRIGGERED:</b>")
            for t in stop_losses:
                lines.append("  " + t["ticker"] + " sold - " + t.get("reason", ""))

        if normal:
            lines.append("<b>TRADED:</b>")
            for t in normal:
                lines.append("  [" + t.get("mode", "PAPER") + "] " + t["action"] + " $" + str(round(t["amount_usd"], 2)) + " " + t["ticker"])
    else:
        lines.append("No trades this run.")

    send_message("\n".join(lines))

def send_daily_summary():
    from trader import get_pnl_summary

    ALPACA_KEY_ID = os.getenv("ALPACA_KEY_ID")
    ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY")
    ALPACA_BASE   = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    HEADERS = {
        "APCA-API-KEY-ID":     ALPACA_KEY_ID,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
    }

    lines = ["<b>STUMP DAILY SUMMARY</b>"]
    lines.append(datetime.now(timezone.utc).strftime("%A %b %d, %Y"))
    lines.append("")

    try:
        resp = requests.get(ALPACA_BASE + "/v2/account", headers=HEADERS, timeout=10)
        a = resp.json()
        equity  = float(a.get("equity", 0))
        last_eq = float(a.get("last_equity", equity))
        day_pl  = equity - last_eq
        day_pct = ((day_pl / last_eq) * 100) if last_eq else 0
        lines.append("<b>Portfolio:</b> $" + "{:,.2f}".format(equity))
        lines.append("<b>Today P&L:</b> " + ("+" if day_pl >= 0 else "") + "$" + "{:,.2f}".format(day_pl) + " (" + ("+" if day_pct >= 0 else "") + str(round(day_pct, 2)) + "%)")
    except Exception:
        lines.append("Portfolio: unavailable")

    lines.append("")

    try:
        resp2 = requests.get(ALPACA_BASE + "/v2/positions", headers=HEADERS, timeout=10)
        positions = resp2.json()
        if positions:
            lines.append("<b>Open Positions (" + str(len(positions)) + "):</b>")
            for p in positions:
                sym  = p["symbol"].replace("/USD", "")
                pl   = float(p.get("unrealized_pl", 0))
                plpc = float(p.get("unrealized_plpc", 0)) * 100
                lines.append("  " + sym + " " + ("+" if pl >= 0 else "") + "$" + str(round(pl, 2)) + " (" + ("+" if plpc >= 0 else "") + str(round(plpc, 2)) + "%)")
        else:
            lines.append("<b>Open Positions:</b> None")
    except Exception:
        lines.append("Positions: unavailable")

    lines.append("")

    pnl = get_pnl_summary()
    if pnl and pnl["total_signals"] > 0:
        lines.append("<b>Signal Accuracy:</b>")
        lines.append("  Signals traded: " + str(pnl["total_signals"]))
        lines.append("  Open: " + str(pnl["open"]) + " | Closed: " + str(pnl["closed"]))
        if pnl["closed"] > 0:
            lines.append("  Win rate: " + str(pnl["win_rate"]) + "%")
            lines.append("  Total P&L: " + ("+" if pnl["total_pnl"] >= 0 else "") + "$" + str(pnl["total_pnl"]))
    else:
        lines.append("<b>Signal Accuracy:</b> No closed trades yet")

    lines.append("")
    lines.append("Stop losses: Stable 5% | Volatile 8% | Crypto 10%")
    lines.append("Not financial advice.")

    send_message("\n".join(lines))
