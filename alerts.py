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
        send_message("Stump Trader is online.\nBot started. Analysis cycles running.\nNot financial advice.")
        return
    if not signals:
        return
    lines = ["<b>STUMP SIGNALS</b>"]
    for sig in signals:
        ticker = sig.get("ticker", "?")
        action = sig.get("signal", "HOLD")
        conf = sig.get("confidence", 0)
        tf = sig.get("timeframe", "?")
        price = snapshot.get(ticker, {}).get("price", 0)
        chg = snapshot.get(ticker, {}).get("change_24h", 0)
        chg_str = ("+" if chg >= 0 else "") + str(round(chg, 2)) + "%"
        entry = sig.get("entry", "")
        target = sig.get("target", "")
        stop = sig.get("stop", "")
        rr = sig.get("risk_reward", "")
        line = "\n<b>" + ticker + "</b> " + action + " " + str(conf) + "% | " + tf + " | $" + str(round(price, 2)) + " " + chg_str
        if entry:
            line += "\nE:" + str(entry) + " T:" + str(target) + " S:" + str(stop) + " RR:" + rr
        lines.append(line)
    lines.append("\n-----")
    if executed:
        lines.append("<b>EXECUTED</b>")
        for t in executed:
            lines.append("[" + t.get("mode", "PAPER") + "] " + t["action"] + " $" + str(round(t["amount_usd"], 2)) + " " + t["ticker"])
    else:
        lines.append("No trades executed")
    lines.append("\nNot financial advice.")
    send_message("\n".join(lines))
