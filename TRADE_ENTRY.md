# 📋 PraxiAlpha — Trade Entry Templates

> **Purpose:** Copy-paste templates for rapid trade logging via Copilot Chat.
> Paste a filled-in template into chat and say **"Log this trade"** —
> Copilot will handle Docker checks, API calls, and verification.
>
> See **WORKFLOW.md § Quick Command: Log Trade** for the full workflow.

---

## New Trade Entry

```
ACTION: NEW_TRADE
TICKER: <e.g. AAPL>
DIRECTION: <long | short>
ASSET_TYPE: <shares | options>
TRADE_TYPE: <single_leg | multi_leg>
TIMEFRAME: <daily | weekly | monthly | quarterly>
ENTRY_DATE: <YYYY-MM-DD>
ENTRY_PRICE: <e.g. 185.50>
QUANTITY: <e.g. 100>
STOP_LOSS: <e.g. 180.00 | NONE>
TAKE_PROFIT: <e.g. 200.00 | NONE>
TAGS: <comma-separated | NONE>
COMMENTS: <free text | NONE>
```

### Example — Long shares entry

```
ACTION: NEW_TRADE
TICKER: NVDA
DIRECTION: long
ASSET_TYPE: shares
TRADE_TYPE: single_leg
TIMEFRAME: daily
ENTRY_DATE: 2026-03-26
ENTRY_PRICE: 950.00
QUANTITY: 10
STOP_LOSS: 920.00
TAKE_PROFIT: 1050.00
TAGS: momentum, AI-sector
COMMENTS: Breakout above 945 resistance on heavy volume
```

---

## Add Exit (Partial or Full Close)

```
ACTION: ADD_EXIT
TRADE_ID: <uuid of the open trade>
EXIT_DATE: <YYYY-MM-DD>
EXIT_PRICE: <e.g. 200.50>
QUANTITY: <e.g. 50>
COMMENTS: <free text | NONE>
```

### Example — Partial exit

```
ACTION: ADD_EXIT
TRADE_ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
EXIT_DATE: 2026-04-02
EXIT_PRICE: 1020.00
QUANTITY: 5
COMMENTS: Taking half off at +7.4%
```

---

## Quick Reference — Field Values

| Field | Allowed Values |
|-------|---------------|
| `DIRECTION` | `long`, `short` |
| `ASSET_TYPE` | `shares`, `options` |
| `TRADE_TYPE` | `single_leg`, `multi_leg` |
| `TIMEFRAME` | `daily`, `weekly`, `monthly`, `quarterly` |
| `ENTRY_DATE` / `EXIT_DATE` | ISO format: `YYYY-MM-DD` |
| `STOP_LOSS`, `TAKE_PROFIT` | Positive number or `NONE` |
| `TAGS` | Comma-separated strings or `NONE` |
| `COMMENTS` | Free text or `NONE` |

---

## How It Works

1. **You paste** a filled-in template into Copilot Chat
2. **You say** "Log this trade" (or "Add this exit")
3. **Copilot runs** the Quick Command workflow from `WORKFLOW.md`:
   - ✅ Checks Docker containers are running (`db`, `app`)
   - ✅ Hits `/health` to confirm the API is alive
   - ✅ Sends the `POST` request to `/api/v1/journal/` (or `/{id}/exits`)
   - ✅ Prints the API response (trade ID, status, computed fields)
   - ✅ Tells you how to verify in the Streamlit Journal UI
