# Key Decisions

## Stack
- Python 3.12 managed by `uv`; venv at `~/Library/Application Support/grocery-agent/.venv`
- Retail plumbing: `open-supermarkets@3.0.0` CLI (installed into `node/` outside OneDrive)
- Orchestration: `langgraph` state graph (deterministic nodes, LLM only for language tasks)
- LLM: local Ollama `qwen3:4b-instruct-2507-q4_K_M`; OpenAI-compatible endpoint configurable
- Storage: SQLite at `~/Library/Application Support/grocery-agent/grocery.sqlite3`; config at same dir
- No local LLM API keys required; no cloud credentials stored

## Data boundaries
- Retailer session cookies owned by `open-supermarkets` at `~/.sainsburys`, `~/.tesco`, `~/.ocado` — agent never reads them
- HMAC key for order reference hashing at `~/Library/Application Support/grocery-agent/order-id.key`
- Order IDs hashed before storage; postcodes redacted in logs; no payment data ever captured
- Agent writes only to `10 Projects/Grocery Agent/` in the Obsidian vault; never touches imported notes or templates

## Retailer scope
- Live: Sainsbury's, Tesco, Ocado (search, basket, slots, orders)
- Tesco: opt-in via cookie import (scripted login often bot-blocked); read-only search works anonymously
- Ocado: slots readable; booking/checkout blocked upstream — agent never calls them
- Aldi/Lidl: no UK online API integration; manual/in-store benchmark only
- Checkout/payment: never exposed; `--confirm` path disabled; `book_slot` not implemented

## Pricing model
- Prices stored as minor units (pence); `null` means unknown, never `0`
- Member prices flagged with `requires_loyalty`; never presented as universal shelf price
- Pack size resolution via `packs_needed()`; unknown prices flagged in proposal

## Obsidian integration
- Read-only indexer with FTS5 search over markdown chunks
- Output templates: `Meal Plans/`, `Shopping Lists/`, `Recipes/` under `10 Projects/Grocery Agent/`
- Agent-owned notes carry `agent: grocery-agent` frontmatter marker; non-agent notes never overwritten

## What was explicitly rejected
- Custom retailer scrapers bypassing bot protection (fail closed instead)
- Storing retailer credentials or session cookies in agent data dir
- Multi-agent swarm — single LangGraph graph with deterministic nodes
- Writing checkout/payment code of any kind

## Visual design
- CLI: Ives minimalism (heavy borders, whitespace, clean typography) + Lichtenstein accents (red `#ff0033`, blue `#0033ff`, yellow `#ffcc00`, heavy borders)
- Dashboard: Apple-style minimal surface cards + Lichtenstein bold accent colors for prices/status
- No comments in source code (documentation in key_decisions.md instead)

