# Next Steps

## Loyalty program data — UK reality

There are **no official public APIs** for Tesco Clubcard, Sainsbury's Nectar, or Lidl Plus. `open-supermarkets` (v3.0.0) uses unofficial, unofficial reverse-engineered endpoints that require logged-in browser sessions.

| Retailer | API | Login method | Session expiry | Loyalty pricing captured? |
|----------|-----|-------------|----------------|---------------------------|
| Tesco | No official API | Session-cookie only | Periodic (bot-blocked scripted login) | **Yes** — Clubcard prices in `promotions` when logged in |
| Sainsbury's | No official API | Scripted login + SMS MFA | ~20 minutes | **No** — only shelf `retail_price`, no Nectar |
| Ocado | No official API | Scripted login | Periodic | N/A — no loyalty program |
| Aldi/Lidl UK | No online API | N/A | N/A | Manual/in-store only |

### What works today
- **Read-only search** — Tesco/Sainsbury's/Ocado product search may work without a session (CLI does not pre-enforce session for search)
- **Basket/slots/orders** — Require valid session cookie
- **Tesco Clubcard pricing** — Captured in `promotions` (with `requires_loyalty=true`) when logged in with valid session
- **Sainsbury's Nectar pricing** — NOT captured (only shelf `retail_price`; open-supermarkets doesn't expose Nectar prices)
- **Price history** — Forward recording only (import your own CSVs)

### What does NOT work
- Tesco scripted login (bot-blocked)
- Sainsbury's headless login without SMS MFA
- Ocado slot booking/checkout (AWS WAF blocked)
- Aldi/Lidl UK online data

## Your options for live loyalty data

### Option 1: Session refresh (ongoing, manual)
When `grocery doctor` shows `authenticated: false`:
1. Log in to Tesco.com / Sainsbury's.co.uk / Ocado.com in your browser
2. Export cookies (browser extension or DevTools)
3. Run `grocery auth <retailer> --cookie-file <cookies.json>`
4. Run `grocery history-import` to pull recent orders
   - Tesco Clubcard prices appear in `promotions` with `requires_loyalty=true`
   - Sainsbury's shows shelf prices only (no Nectar pricing captured)

### Option 2: SAR/DSAR (one-time, legal right)
Request your full purchase data under UK GDPR:
- Tesco: Privacy Centre → Data request
- Sainsbury's: Nectar account → Data request
- Lidl Plus: Customer service → Data request

This gives historical data, not ongoing live data.

### Option 3: Forward recording (ongoing, manual)
After each shop, save your receipt/CSV and import:
```
grocery history-import-csv <receipt.csv> --retailer tesco
```
You can manually record member prices paid at checkout — this is the only way to build a complete loyalty price history for Tesco Clubcard and Sainsbury's Nectar.

## What would be needed for ongoing live loyalty data

**Tesco Clubcard:** open-supermarkets captures Clubcard prices in `promotions` when logged in, but sessions expire and there's no API to automate re-login. Requires manual cookie re-import.

**Sainsbury's Nectar:** open-supermarkets does NOT capture Nectar pricing at all — only shelf `retail_price`. This would require provider-level changes to open-supermarkets to parse Nectar-specific fields from Sainsbury's API responses.

**No official APIs exist** for any UK supermarket loyalty program. All access is unofficial scraping that may violate retailer terms and can break at any time.


## WhichGrocer (Australian — not applicable)

https://www.whichgrocer.com/ covers Woolworths, Coles, ALDI Australia, Chemist Warehouse, Priceline — **Australian retailers only**. Not relevant for UK Tesco/Sainsbury's/Ocado. It does have an MCP connector (`https://mcp.whichgrocer.com/mcp`) but that's AU-only.

## UK comparison sites — checked, no APIs

| Site | Coverage | API? | Personal data? |
|------|----------|------|----------------|
| **Trolley.co.uk** | UK (Tesco, Sainsbury's, Morrisons, Asda, Amazon, etc.) | No public API | Consumer comparison only |
| **Grocefully** | UK (Tesco, Asda, Sainsbury's, Morrisons, Ocado, Iceland) | No public API | Consumer comparison only |
| **GroceryCompare.co.uk** | UK | Site unreachable | Unknown |
| **Which?** | UK editorial reviews | No | Editorial content only |

All four are consumer-facing comparison websites that aggregate publicly available shelf prices — none offer public APIs, access to personal loyalty pricing, or purchase history. `open-supermarkets` remains the most direct route for UK live grocery data, but it requires manual session cookie imports since there are no official APIs.

## Recommended next steps

1. **Clear bad recipe data** — `grocery recipes-extract` already clears and re-extracts from `10 Projects/Grocery Agent/Recipes/` only (40 recipes from your 2 recipe notes)
2. **Import your purchase history** — `grocery history-import-csv <file> --retailer <name>`
3. **Set up session refresh** — Import Tesco/Sainsbury's cookies when `grocery doctor` shows auth expired
4. **Dashboard** — `grocery serve` → `http://127.0.0.1:8789` for browsing orders, recipes, prices
5. **CLI** — `grocery compare <retailer> <product>` for live price checks

## Not building
- Anti-bot bypasses or CAPTCHA solving
- Credential storage in agent data dir
- Checkout/payment automation
- Multi-agent swarms
