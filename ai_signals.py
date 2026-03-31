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
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

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

def analyze_batch(batch):
    if not batch:
        return []
    lines = []
    for ticker, d in batch.items():
        lines.append(ticker + "=" + fmt_price(d["price"], d["type"]) + " " + str(d["change_24h"]) + "%")
    snapshot_str = " | ".join(lines)
    prompt = (
        "Market data: " + snapshot_str + "\n"
        "Return ONLY a JSON array, no markdown.\n"
        "Format: [{\"t\":\"BTC\",\"s\":\"BUY\",\"c\":72,\"tf\":\"4H\"}]\n"
        "s=BUY/SELL/HOLD, c=confidence 40-95, tf=1H/4H/1D/1W\n"
        "Be analytical. Not everything is a BUY."
    )
    models = ["claude-sonnet-4-6", "claude-haiku-4-5-20251001"]
    for model in models:
        try:
            if model != models[0]:
                log.warning("Sonnet unavailable - falling back to Haiku")
            response = client.messages.create(
                model=model,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            raw   = response.content[0].text
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
            if model != models[0]:
                log.info("Haiku fallback succeeded")
            return signals
        except json.JSONDecodeError as e:
            log.error("Failed to parse batch response: " + str(e))
            return []
        except Exception as e:
            err_str = str(e)
            if "credit balance is too low" in err_str:
                log.error("Out of Anthropic credits")
                send_alert("STUMP: Out of credits. Top up at console.anthropic.com.")
                return []
            if "overloaded" in err_str.lower() or "529" in err_str:
                log.warning("Model " + model + " overloaded - trying next")
                continue
            log.error("Claude API error: " + err_str)
            return []
    log.error("All models overloaded - skipping batch")
    return []

def generate_signals(snapshot):
    if not snapshot:
        return []

    tickers = list(snapshot.keys())
    batch_size = 5
    batches = []
    for i in range(0, len(tickers), batch_size):
        batch_tickers = tickers[i:i + batch_size]
        batch = {t: snapshot[t] for t in batch_tickers}
        batches.append(batch)

    log.info("Running " + str(len(batches)) + " batch(es) of up to " + str(batch_size) + " assets each")

    all_signals = []
    for i, batch in enumerate(batches):
        log.info("Batch " + str(i + 1) + ": " + str(list(batch.keys())))
        signals = analyze_batch(batch)
        all_signals.extend(signals)

    log.info("Signals: " + str([(s["ticker"], s["signal"], s["confidence"]) for s in all_signals]))
    return all_signals

def is_actionable(signal):
    return signal.get("signal") in ("BUY", "SELL") and signal.get("confidence", 0) >= MIN_CONFIDENCE
