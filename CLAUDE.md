# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a take-home assignment for MulhollandAI. The task: design an ontology for Reznar's Arcane Oddities (a fantasy magic item shop), build an extraction pipeline that populates a local Postgres database from `data/items_combined.pdf`, then analyze rarity anomalies in a Jupyter notebook.

**Two deliverables:**
1. `reznar/ontology.py` + extraction pipeline → populated local Postgres
2. `analysis.ipynb` → rarity prediction and anomaly detection

## Commands

```bash
# Install dependencies (includes langchain, langchain-anthropic, python-dotenv)
uv sync

# Verify Postgres is running
uv run python verify.py

# Browse the database in a web UI (requires: brew install pgweb)
uv run python web.py
```

Run any script with `uv run python <script.py>` or activate the venv once with `source .venv/bin/activate`.

Reset the database: `rm -rf data/.pg/`

## Architecture

### Database (`db.py`)
`db.connect()` returns a `psycopg` connection to an embedded Postgres instance (via `pgserver`) whose data lives in `data/.pg/`. The server auto-starts on first connect. No external Postgres installation needed.

```python
import db
with db.connect() as conn, conn.cursor() as cur:
    cur.execute("...")
```

### Ontology pattern (`stormland/ontology.py` → reference; `reznar/ontology.py` → implement)
Entities are Pydantic `BaseModel` subclasses sharing a `_Base` with `extra="forbid"`. Field types use `Annotated[base_type, BeforeValidator(...), Hint(...)]`:
- `BeforeValidator` normalizes messy LLM output into a canonical form
- `Hint` carries a free-text description used to prompt LLMs (fewer validation round-trips)

Each ontology module exports a `REGISTRY: dict[str, type[BaseModel]]` mapping type-name strings to model classes for generic pipeline discovery.

### Key design constraints from the domain
- Rarity tiers: common → artifact
- Attunement: items may require attunement (limited slots per user)
- Equipment slots: head/hands/feet/body/ring/neck/etc. — one item per slot
- Pattern dimensions Reznar cares about: offensive, defensive, creature/environment targeting, use limitations

## Code style

Linting is configured via `ruff` (see `pyproject.toml`). Run: `uv run ruff check .` and `uv run ruff format .`

### Extraction pipeline (two-stage)

**Stage 1 — `reznar/parse_pdf.py`:** PDF is fully image-based. Uses `claude-haiku-4-5-20251001` vision to render each page (via `pypdfium2`) and extract items with verbatim descriptions into `data/items_raw.json`. Fields: `name`, `item_type`, `rarity`, `attunement`, `description`. No semantic analysis — pure OCR + light structure. Pages are processed in parallel via `ThreadPoolExecutor(max_workers=5)`; each worker returns `(page_index, items)` with no shared state, results are sorted by page index and written once at the end.

**Stage 2 — `reznar/extract.py`:** Reads `data/items_raw.json`, sends each item's description to a text LLM one at a time to extract ontology fields (equipment slot, offensive/defensive traits, targeting, limitations), then writes to Postgres via `db.py`.

### AI workflow (LangChain)
Both pipeline stages use **LangChain** (`langchain`, `langchain-anthropic`) rather than the raw Anthropic SDK. Use `ChatAnthropic` from `langchain_anthropic` for all LLM calls.

### Configuration (`.env`)
All configuration — API keys and model names — lives in `.env` at the project root. Load with `python-dotenv`:

```python
from dotenv import load_dotenv
load_dotenv()
```

`.env` is not committed — fill in your key before running anything.

Run Stage 1: `uv run python reznar/parse_pdf.py`

## All pipeline code lives in `reznar/`
All new files (`parse_pdf.py`, `extract.py`, `config.py`, `ontology.py`) go inside `reznar/`. Do not create pipeline scripts at the project root.

## What exists vs. what needs building

| File | Status |
|------|--------|
| `stormland/ontology.py` | Complete — reference implementation |
| `reznar/config.py` | Created — loads `VISION_MODEL` and `ANALYSIS_MODEL` from `.env` |
| `reznar/ontology.py` | Stub — needs entity models |
| `reznar/parse_pdf.py` | Created — Stage 1 PDF parser (generates `data/items_raw.json`) |
| `reznar/extract.py` | Does not exist — Stage 2 DB loader |
| `data/items_raw.json` | Generated — output of Stage 1 |
| `analysis.ipynb` | Does not exist yet |
| `.env` | Created — add real `ANTHROPIC_API_KEY`; model names set via `VISION_MODEL`/`ANALYSIS_MODEL` |
| `.env.example` | Committed — template for new contributors |
| README / `RUN.md` | Needs run instructions added |
