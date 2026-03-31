import os
import json
import logging
import anthropic
import requests
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("stump.ai")
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MIN_CONFIDENCE = int(os.getenv("MIN_CONFIDENCE_TO_TRADE", "75"))
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_alert(text):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage",
            json={"chat_id": CHAT_ID, "text": text},
            timeout=10,
        )
    except Exception:
        pass

def fmt_price(price, asset_type):
    if asset_type == "crypto" and price < 1:
        return "$" + str(round(price, 4))
    if price > 1000:
        return "$" + "{:,.0f}".format(price)
    return "$" + str(round(price, 2))

def generate_signals(snapshot):
    if not snapshot:
        return []
    lines = []
    for ticker, d in snapshot.items():
        lines.append(ticker + "=" + fmt_price(d["price"], d["type"]) + " " + str(d["change_24h"]) + "%")
    snapshot_str = " | ".join(lines)
    prompt = (
        "Market data: " + snapshot_str + "\n"
        "Return ONLY a JSON array, no markdown.\n"
        "Format: [{\"t\":\"BTC\",\"s\":\"BUY\",\"c\":72,\"tf\":\"4H\"}]\n"
        "s=BUY/SELL/HOLD, c=confidence 40-95, tf=1H/4H/1D/1W\n"
        "Be analytical. Not everything is a BUY."
    )
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        clean = raw.replace("```json", "").replace("```", "").strip()
        raw_signals = json.loads(clean)
        signals = []
        for s in raw_signals:
            signals.append({
                "ticker":     s.get("t", "?"),
                "signal":     s.get("s", "HOLD"),
                "confidence": s.get("c", 0),
                "timeframe":  s.get("tf", "4H"),
            })
        log.info("Signals: " + str([(s["ticker"], s["signal"], s["confidence"]) for s in signals]))
        return signals
    except json.JSONDecodeError as e:
        log.error("Failed to parse response: " + str(e))
        return []
    except Exception as e:
        err_str = str(e)
        if "credit balance is too low" in err_str:
            log.error("Out of Anthropic credits")
            send_alert("STUMP: Out of credits. Top up at console.anthropic.com.")
        else:
            log.error("Claude API error: " + err_str)
        return []

def is_actionable(signal):
    return signal.get("signal") in ("BUY", "SELL") and signal.get("confidence", 0) >= MIN_CONFIDENCE
