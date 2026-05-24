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

### Reznar ontology — per-form classes over a shared base
A single god-class is avoided. A shared base **`_Item(_Base)`** holds all *cross-cutting* fields (effects appear on every form — helms deal damage, potions grant resistances), and **thin per-form subclasses** pin `slot` and add a form-specific `subtype` enum only where one exists. All subclasses serialize into one flat `items` table.

**Classes / `REGISTRY`:** `Weapon` (slot=hand, `subtype: WeaponType`), `Armor` (`subtype: ArmorType` incl. `shield`; slot derived: shield→off_hand, else body), `Ring` (finger), `Amulet` (neck), `Cloak` (body), `Footwear` (feet), `Headgear` (head; helm/mask/crown/headband), `Potion` (none), `Wondrous` (none — residual).

**Key normalization rule:** the raw `item_type` `"wondrous item"` is D&D's miscellaneous bucket — NOT a form. The real form is recovered from the item **name** (amulets, boots, cloaks, helms are all typed "wondrous item"); `Wondrous` is reserved only for held/used objects with no wearable slot (horns, drums, chests, pipes, pouches…).

**Effect schema (the design rule):** keep genuine common ground concrete; model high-variance dimensions as Pokemon-style matchup grids; never drop a description detail.
- **Combat magnitudes** (concrete ints): `ac_bonus`, `attack_bonus`, `damage_bonus`
- **Damage-type grid** (`list[DamageType]`): `inflicts_damage_types` (offense) · `resistances` + `immunities` (defense, kept separate — the data uses both terms) · `vulnerabilities` (weakness)
- **Conditions:** `condition_immunities: list[Condition]` (charmed/frightened/stunned/petrified/lycanthropy…) — separate axis from damage types
- **Creature grid** (permissive normalized strings — keep specifics like medusa/vampire): `offensive_vs_creatures` · `defensive_vs_creatures` · `weak_vs_creatures`. An item can appear in offensive AND defensive vs the same creature (e.g. Armor of Daylight's Embrace vs vampire)
- **Environment grid** (permissive strings): `strong_in_environments` · `weak_in_environments`
- **Utility:** `grants_abilities: list[Ability]` (control/summon/flight/invisibility/teleport/shapeshift/spellcasting…)
- **Limitations:** `charges: int?` · `recharge: Recharge` (short_rest/long_rest/dawn/midnight/daily/finite_uses/none) · `cursed: bool` · `drawback: str?` (one-off drawbacks)
- **Catch-all:** `special_effects: list[str]` — anything not captured structurally, so nothing in a description is lost
- Identity carried through: `name`, `raw_description` (verbatim), `form`, `slot`, `rarity`, `attunement`

**Enums:** `Rarity` (common→artifact + `varies`), `Slot`, `Form`, `WeaponType`, `ArmorType`, `DamageType` (incl. bludgeoning/piercing/slashing + fire/cold/lightning/thunder/acid/poison/necrotic/radiant/force/psychic), `Condition`, `Ability`, `Recharge`. **Normalizers** (`BeforeValidator`): damage types (electrical→lightning, sonic→thunder), creatures (strip parentheticals: `fiend (devil)`→fiend), environments (wooded→forest, immersed→underwater, flying→airborne), enum coercion (`very rare`→very_rare).

**Value normalization is the key lever for Reznar's pattern-finding** — not extra tables. Storage stays one wide `items` table; the 9 classes are modeling convenience and all serialize into it. Reznar's job is cross-item queries ("which weapons/shields are good vs vampires?"), which work as a single `WHERE form IN (...) AND 'vampire' = ANY(offensive_vs_creatures)` only if values are canonical. Two parts:
- **Canonical terms**: lowercase + synonym mapping (see Normalizers above) so one concept = one token.
- **Category taxonomy (specific → parent), tag BOTH at extraction time** so precise and broad queries both match: `vampire`→also `undead`; `devil`/`demon`→also `fiend`; `bronze dragon`→also `dragon`. Expand damage umbrellas too: `elemental`→acid/cold/fire/lightning/thunder; `weapon damage`→bludgeoning/piercing/slashing. Store specific + parent in the same array (`offensive_vs_creatures = {vampire, undead}`); keep a small taxonomy dict in `ontology.py`. Without this, a `vampire` query misses items tagged only `undead`.

**Domain facts:** rarity tiers common → artifact (+ `varies`); attunement is a bool (limited slots per user); one item per equipment slot.

## Code style

Linting is configured via `ruff` (see `pyproject.toml`). Run: `uv run ruff check .` and `uv run ruff format .`

### Extraction pipeline (two-stage)

**Stage 1 — `reznar/parse_pdf.py`:** PDF is fully image-based. Uses `claude-haiku-4-5-20251001` vision to render each page (via `pypdfium2`) and extract items with verbatim descriptions into `data/items_raw.json`. Fields: `name`, `item_type`, `rarity`, `attunement`, `description`. No semantic analysis — pure OCR + light structure. Pages are processed sequentially so each page can receive a `CONTINUATION_HINT` referencing the carry item from the prior page. When a page may continue a previous item, the hint instructs the model to use a text-only algorithm: ignore all images (decorative illustrations appear anywhere on the page — top, side, bottom — with no fixed position), scan only text top-to-bottom, and classify the first text block as a new item name (ALL-CAPS/bold, 1–5 words, no trailing punctuation) or continuation prose.

**Stage 2 — `reznar/extract.py`:** Reads `data/items_raw.json`. For each item, first **classifies the form** rule-based (explicit `armor (X)`/`weapon (X)`/`ring`/`potion`, else recover from the name — `wondrous item` is not a form), looks up the class in `REGISTRY`, then sends the description to a text LLM via `ChatAnthropic(...).with_structured_output(cls)` to extract ontology fields (carrying name/rarity/attunement/raw_description through). Writes all forms into one flat `items` table via `db.py` (`CREATE TABLE IF NOT EXISTS`, list fields as `text[]`, `ON CONFLICT (name) DO UPDATE`).

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
| `reznar/ontology.py` | Stub — needs per-form classes (`_Item` base + `Weapon`/`Armor`/`Ring`/`Amulet`/`Cloak`/`Footwear`/`Headgear`/`Potion`/`Wondrous`) + `REGISTRY` |
| `reznar/parse_pdf.py` | Created — Stage 1 PDF parser (generates `data/items_raw.json`) |
| `reznar/extract.py` | Does not exist — Stage 2 DB loader |
| `data/items_raw.json` | Generated — output of Stage 1 |
| `analysis.ipynb` | Does not exist yet |
| `.env` | Created — add real `ANTHROPIC_API_KEY`; model names set via `VISION_MODEL`/`ANALYSIS_MODEL` |
| `.env.example` | Committed — template for new contributors |
| README / `RUN.md` | Needs run instructions added |
