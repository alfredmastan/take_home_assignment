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

### Reznar ontology — single `Item` with capability components
A single `Item` class with four optional capability components: `Offense`, `Defense`, `Environment`, `Limitations`. Each component is `None` when the item has nothing in that bucket. All items serialize to one flat `items` table.

**`REGISTRY`:** `{"Item": Item}` — the LLM extracts all fields including `slot` and `form`.

**Schema:**
- **Identity:** `name`, `slot: Slot` (LLM-extracted — where it is worn/carried), `form: Form` (LLM-extracted — what physical object it is), `rarity: Rarity`, `req_attunement: bool`
- **`Offense`** (set only if item improves attacks or is extra effective against creatures): `attack_damage_bonus: int`, `effective_against: list[str]`
- **`Defense`** (set only if item reduces damage, grants immunity, or protects against creatures): `ac_bonus: int`, `condition_immunities: list[Condition]`, `resistances_against: list[str]`
- **`Environment`** (set only if a setting enhances the item): `strong_in: list[str]`
- **`Limitations`** (set only if item has charges, curse, or drawback): `charges: int | None`, `cursed: bool`, `drawback: str | None`
- **Catch-all:** `special_effects: list[str]` — anything not captured structurally

`slot` and `form` are independent — the LLM infers slot from item description semantics (robust to inconsistent naming), and form from the physical object type. `wondrous` covers held/used objects with no wearable slot (horn, drum, pouch, chest, pipe); `other` handles any form not in the enum.

**Enums:**
- `Slot`: head/neck/body/feet/finger/hand/off_hand/none (fixed, exhaustive)
- `Form`: ring/amulet/cloak/gown/boots/helm/mask/crown/headband/armor/shield/weapon/potion/wondrous/other
- `Rarity`: common/uncommon/rare/very_rare/legendary/artifact/varies
- `Condition`: charmed/frightened/stunned/blinded/deafened/paralyzed/petrified/poisoned/exhaustion/lycanthropy/unconscious/other

**Normalizers (`BeforeValidator`):** `_coerce_enum` (lowercase+underscore for enum fields); `_norm_str_list` (slug each element + dedup, used for `ConditionList` and `EnvironmentList`); `_norm_creatures` (strip parentheticals: `fiend (devil)`→fiend + inner term; expand via `CREATURE_TAXONOMY`).

**`CREATURE_TAXONOMY`** tags both specific and parent so either query matches: `vampire` → also `undead`; `devil`/`demon` → also `fiend`; `lycanthrope` → also `shapechanger`; `medusa`/`hydra` → also `monstrosity`; `drow`/`orc` → also `humanoid`.

## Code style

Linting is configured via `ruff` (see `pyproject.toml`). Run: `uv run ruff check .` and `uv run ruff format .`

### Extraction pipeline (two-stage)

**Stage 1 — `reznar/parse_pdf.py`:** PDF is fully image-based. Uses `claude-haiku-4-5-20251001` vision to render each page (via `pypdfium2`) and extract items with verbatim descriptions into `data/items_raw.json`. Fields: `name`, `item_type`, `rarity`, `attunement`, `description`. No semantic analysis — pure OCR + light structure. Pages are processed sequentially so each page can receive a `CONTINUATION_HINT` referencing the carry item from the prior page. When a page may continue a previous item, the hint instructs the model to use a text-only algorithm: ignore all images (decorative illustrations appear anywhere on the page — top, side, bottom — with no fixed position), scan only text top-to-bottom, and classify the first text block as a new item name (ALL-CAPS/bold, 1–5 words, no trailing punctuation) or continuation prose.

**Stage 2 — `reznar/extract.py`:** Reads `data/items_raw.json`. For each item, sends name + description to a text LLM via `ChatAnthropic(...).with_structured_output(Item)` to extract all ontology fields (`slot`, `form`, capability components, etc.), carrying `name`/`rarity`/`req_attunement` through from Stage 1. Writes all items into one flat `items` table via `db.py` (`CREATE TABLE IF NOT EXISTS`, list fields as `text[]`, `ON CONFLICT (name) DO UPDATE`).

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
| `reznar/ontology.py` | Complete — single `Item` class with `Offense`/`Defense`/`Environment`/`Limitations` components + `REGISTRY` |
| `reznar/parse_pdf.py` | Created — Stage 1 PDF parser (generates `data/items_raw.json`) |
| `reznar/extract.py` | Does not exist — Stage 2 DB loader |
| `data/items_raw.json` | Generated — output of Stage 1 |
| `analysis.ipynb` | Does not exist yet |
| `.env` | Created — add real `ANTHROPIC_API_KEY`; model names set via `VISION_MODEL`/`ANALYSIS_MODEL` |
| `.env.example` | Committed — template for new contributors |
| README / `RUN.md` | Needs run instructions added |
