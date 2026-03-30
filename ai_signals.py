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
        price_str = fmt_price(d["price"], d["type"])
        lines.append(ticker + " (" + d["type"] + "): price=" + price_str + ", 24h=" + str(d["change_24h"]) + "%, vol=" + str(d.get("volume", "N/A")))
    snapshot_str = "\n".join(lines)
    prompt = (
        "You are a quantitative trading analyst AI named Stump.\n"
        "Analyze the following real-time market snapshot and generate trading signals.\n\n"
        "MARKET SNAPSHOT:\n" + snapshot_str + "\n\n"
        "MACRO CONTEXT:\n"
        "- VIX: ~21 (moderate volatility)\n"
        "- DXY: ~104 (strong dollar)\n"
        "- Fed: rates on hold\n"
        "- Gold: ~$3,100\n"
        "- 10Y yield: ~4.35%\n\n"
        "For EACH ticker in the snapshot, generate a signal.\n"
        "Respond ONLY with a valid JSON array, no markdown, no explanation outside JSON.\n\n"
        "Format exactly like this:\n"
        "[{\"ticker\":\"BTC\",\"signal\":\"BUY\",\"confidence\":72,\"timeframe\":\"4H\",\"reasoning\":\"2-3 sentences.\",\"entry\":82100,\"target\":86000,\"stop\":80200,\"risk_reward\":\"1:2.1\"}]\n\n"
        "Rules:\n"
        "- signal must be exactly: BUY, SELL, or HOLD\n"
        "- confidence: integer between 40 and 95\n"
        "- timeframe: one of 1H, 4H, 1D, 1W\n"
        "- entry/target/stop: realistic prices based on current price\n"
        "- Not every signal should be BUY"
    )
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        clean = raw.replace("```json", "").replace("```", "").strip()
        signals = json.loads(clean)
        log.info("Signals: " + str([(s["ticker"], s["signal"], s["confidence"]) for s in signals]))
        return signals
    except json.JSONDecodeError as e:
        log.error("Failed to parse Claude response as JSON: " + str(e))
        return []
    except Exception as e:
        err_str = str(e)
        if "credit balance is too low" in err_str:
            log.error("Out of Anthropic credits")
            send_alert("STUMP: Out of Anthropic credits. Bot has paused. Top up at console.anthropic.com to resume.")
        else:
            log.error("Claude API error: " + err_str)
        return []

def is_actionable(signal):
    return signal.get("signal") in ("BUY", "SELL") and signal.get("confidence", 0) >= MIN_CONFIDENCE
