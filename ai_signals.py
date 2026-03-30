“””
ai_signals.py — Generates BUY/SELL/HOLD signals using Claude
“””

import os
import json
import logging
import anthropic
from dotenv import load_dotenv

load_dotenv()
log    = logging.getLogger(“stump.ai”)
client = anthropic.Anthropic(api_key=os.getenv(“ANTHROPIC_API_KEY”))

MIN_CONFIDENCE = int(os.getenv(“MIN_CONFIDENCE_TO_TRADE”, “75”))

def fmt_price(price: float, asset_type: str) -> str:
if asset_type == “crypto” and price < 1:
return f”${price:.4f}”
if price > 1000:
return f”${price:,.0f}”
return f”${price:.2f}”

def generate_signals(snapshot: dict) -> list[dict]:
“””
Send market snapshot to Claude, get back structured signals.
Returns list of signal dicts.
“””
if not snapshot:
return []

```
# Build snapshot string for the prompt
lines = []
for ticker, d in snapshot.items():
    price_str = fmt_price(d["price"], d["type"])
    lines.append(
        f"{ticker} ({d['type']}): price={price_str}, "
        f"24h={d['change_24h']:+.2f}%, "
        f"vol={d.get('volume', 'N/A')}"
    )
snapshot_str = "\n".join(lines)

prompt = f"""You are a quantitative trading analyst AI named Stump.
```

Analyze the following real-time market snapshot and generate trading signals.

MARKET SNAPSHOT:
{snapshot_str}

MACRO CONTEXT:

- VIX: ~21 (moderate volatility)
- DXY: ~104 (strong dollar)
- Fed: rates on hold
- Gold: ~$3,100
- 10Y yield: ~4.35%

For EACH ticker in the snapshot, generate a signal.
Respond ONLY with a valid JSON array — no markdown, no explanation outside JSON.

Format exactly like this:
[
{{
“ticker”: “BTC”,
“signal”: “BUY”,
“confidence”: 72,
“timeframe”: “4H”,
“reasoning”: “2-3 sentences referencing specific data points from the snapshot.”,
“entry”: 82100,
“target”: 86000,
“stop”: 80200,
“risk_reward”: “1:2.1”
}}
]

Rules:

- signal must be exactly: BUY, SELL, or HOLD
- confidence: integer between 40 and 95
- timeframe: one of 1H, 4H, 1D, 1W
- entry/target/stop: realistic prices based on current price
- Be genuinely analytical — not every signal should be BUY”””
  
  try:
  response = client.messages.create(
  model=“claude-sonnet-4-20250514”,
  max_tokens=1000,
  messages=[{“role”: “user”, “content”: prompt}],
  )
  raw  = response.content[0].text
  clean = raw.replace(”`json", "").replace("`”, “”).strip()
  signals = json.loads(clean)
  log.info(f”Signals: {[(s[‘ticker’], s[‘signal’], s[‘confidence’]) for s in signals]}”)
  return signals
  
  except json.JSONDecodeError as e:
  log.error(f”Failed to parse Claude response as JSON: {e}”)
  log.debug(f”Raw response: {raw}”)
  return []
  except Exception as e:
  log.error(f”Claude API error: {e}”)
  return []

def is_actionable(signal: dict) -> bool:
“”“Returns True if a signal meets the confidence threshold.”””
return (
signal.get(“signal”) in (“BUY”, “SELL”)
and signal.get(“confidence”, 0) >= MIN_CONFIDENCE
)
