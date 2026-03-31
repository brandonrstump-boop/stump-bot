import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("stump.alerts")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

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

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")

    lines = ["<b>STUMP</b> " + now]

    for sig in signals:
        ticker = sig.get("ticker", "?")
        action = sig.get("signal", "HOLD")
        conf = sig.get("confidence", 0)
        tf = sig.get("timeframe", "?")
        chg = snapshot.get(ticker, {}).get("change_24h", 0)
        chg_str = ("+" if chg >= 0 else "") + str(round(chg, 2)) + "%"

        if action == "BUY":
            icon = "+"
        elif action == "SELL":
            icon = "-"
        else:
            icon = "~"

        lines.append(icon + " <b>" + ticker + "</b> " + action + " " + str(conf) + "% | " + tf + " | " + chg_str)

    if executed:
        lines.append("")
        lines.append("<b>TRADED:</b>")
        for t in executed:
            lines.append("[" + t.get("mode", "PAPER") + "] " + t["action"] + " $" + str(round(t["amount_usd"], 2)) + " " + t["ticker"])
    else:
        lines.append("")
        lines.append("No trades this run.")

    send_message("\n".join(lines))
