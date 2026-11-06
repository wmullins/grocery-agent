# Next Steps

## Loyalty program data — UK reality

There are **no official public APIs** for Tesco Clubcard, Sainsbury's Nectar, or Lidl Plus. `open-supermarkets` (v3.0.0) uses unofficial, unofficial reverse-engineered endpoints that require logged-in browser sessions.

| Retailer | API | Login method | Session expiry | Cookie import path |
|----------|-----|-------------|----------------|-------------------|
| Tesco | No official API | Session-cookie only | Periodic (bot-blocked scripted login) | `grocery auth tesco --cookie-file <cookies.json>` |
| Sainsbury's | No official API | Scripted login + SMS MFA | ~20 minutes | `grocery auth sainsburys` |
| Ocado | No official API | Scripted login | Periodic | `grocery auth ocado` |
| Aldi/Lidl UK | No online API | N/A | N/A | Manual/in-store only |

### What works today
- **Read-only search** — Tesco/Sainsbury's/Ocado product search may work without a session (CLI does not pre-enforce session for search)
- **Basket/slots/orders** — Require valid session cookie
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

## WhichGrocer (Australian — not applicable)

https://www.whichgrocer.com/ covers Woolworths, Coles, ALDI Australia, Chemist Warehouse, Priceline — **Australian retailers only**. Not relevant for UK Tesco/Sainsbury's/Ocado. It does have an MCP connector (`https://mcp.whichgrocer.com/mcp`) but that's AU-only.

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
