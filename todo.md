# Todo

## Setup

- [x] Add dependencies to `pyproject.toml` and run `uv sync`
  - `langchain`, `langchain-anthropic` for LLM workflow
  - `pypdfium2` for PDF rendering
  - `python-dotenv` for `.env` loading
- [x] Copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY` (model names already set)

## Stage 1 — PDF → `data/items_raw.json`

- [x] Create `reznar/parse_pdf.py`
  - Load API key from `.env` via `python-dotenv`
  - Load vision model name from `.env` via `reznar/config.py`
  - Render each of the 39 PDF pages to a base64 PNG via `pypdfium2` (scale=2)
  - Send each page image to the vision model via LangChain (`ChatAnthropic`)
  - Prompt: extract items with verbatim description — fields: `name`, `item_type`, `rarity`, `attunement` (bool), `description`
  - Collect all items across pages, save to `data/items_raw.json`
  - Idempotent: skip if output exists unless `--force` passed
  - Progress: print `Page N/39 → M items` per page

## Stage 2 — Ontology + DB

- [ ] Design `reznar/ontology.py` — Pydantic models for `MagicItem` and related entities
  - Fields: name, item_type, rarity, attunement, equipment_slot, offensive traits, defensive traits, creature/environment targeting, use limitations
  - Follow `stormland/ontology.py` pattern: `_Base`, `Hint`, `BeforeValidator`, `REGISTRY`
- [ ] Create `reznar/extract.py` — reads `data/items_raw.json`, analyzes each item description one at a time with a text LLM via LangChain, populates Postgres via `db.py`
  - Load API key from `.env` via `python-dotenv`
  - Load analysis model name from `.env` via `reznar/config.py`

## Stage 3 — Analysis

- [ ] Create `analysis.ipynb`
  - Query DB for all items
  - Rarity prediction model
  - Anomaly detection for items whose rarity seems mismatched with their traits
