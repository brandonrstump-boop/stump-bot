“””
alerts.py — Sends Telegram messages for signals and trades
“””

import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(“stump.alerts”)

BOT_TOKEN = os.getenv(“TELEGRAM_BOT_TOKEN”)
CHAT_ID   = os.getenv(“TELEGRAM_CHAT_ID”)

def _send(message: str):
if not BOT_TOKEN or not CHAT_ID:
log.warning(“Telegram not configured — skipping alert”)
return
try:
resp = requests.post(
f”https://api.telegram.org/bot{BOT_TOKEN}/sendMessage”,
json={
“chat_id”:    CHAT_ID,
“text”:       message,
“parse_mode”: “HTML”,
},
timeout=10,
)
resp.raise_for_status()
except Exception as e:
log.error(f”Telegram send error: {e}”)

def send_telegram(
signals:  list[dict],
snapshot: dict,
executed: list[dict],
startup:  bool = False,
):
“”“Build and send a Telegram summary message.”””

```
if startup:
    _send(
        "🌳 <b>Stump Trader is online</b>\n"
        "Bot started successfully. Analysis cycles running.\n"
        "——————————————\n"
        "<i>Paper trading mode. Not financial advice.</i>"
    )
    return

if not signals:
    return

# ── BUILD MESSAGE ──
lines = ["🌱 <b>STUMP SIGNAL REPORT</b>"]

signal_emojis = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}

for sig in signals:
    ticker = sig.get("ticker", "?")
    action = sig.get("signal", "HOLD")
    conf   = sig.get("confidence", 0)
    tf     = sig.get("timeframe", "?")
    reason = sig.get("reasoning", "")
    price  = snapshot.get(ticker, {}).get("price", 0)
    chg    = snapshot.get(ticker, {}).get("change_24h", 0)

    emoji  = signal_emojis.get(action, "⚪")
    chg_str = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"

    lines.append(
        f"\n{emoji} <b>{ticker}</b> — {action}  ({conf}% conf, {tf})\n"
        f"   Price: ${price:,.4f}  {chg_str} 24h\n"
        f"   {reason[:120]}{'…' if len(reason)>120 else ''}"
    )

    # Entry/target/stop if present
    if sig.get("entry"):
        lines.append(
            f"   Entry ${sig['entry']:,} → Target ${sig['target']:,} | Stop ${sig['stop']:,}"
        )

# ── EXECUTED TRADES ──
if executed:
    lines.append("\n——————————————")
    lines.append("⚡ <b>TRADES EXECUTED</b>")
    for t in executed:
        mode = t.get("mode", "PAPER")
        lines.append(
            f"  [{mode}] {t['action']} ${t['amount_usd']:.2f} of {t['ticker']}"
        )
else:
    lines.append("\n——————————————")
    lines.append("⏭ No trades executed this cycle")

lines.append("\n<i>Not financial advice. Trade at your own risk.</i>")

_send("\n".join(lines))
```
