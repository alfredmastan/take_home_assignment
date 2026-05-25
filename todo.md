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
  - Render each of the 39 PDF pages to a base64 JPEG via `pypdfium2` (scale=3)
  - Send each page image to the vision model via LangChain (`ChatAnthropic`)
  - Prompt: extract items with verbatim description — fields: `name`, `item_type`, `rarity`, `attunement` (bool), `description`
  - Pages processed sequentially; `CONTINUATION_HINT` passes carry item name + tail text to next page
  - Continuation detection uses text-only algorithm: ignore images (unstructured placement), classify first text block as new item name (ALL-CAPS/bold, 1–5 words) or continuation prose
  - Progress: print `Page N/39: M items` (with `(continuation)` tag) as each page completes
  - Output: 80 items → `data/items_raw.json`

## Stage 2 — Ontology + DB

- [x] Design `reznar/ontology.py` — single `Item` class with optional capability components
  - Follow `stormland/ontology.py` pattern: `_Base` (`extra="forbid"`), `Hint` class,
    `Annotated[type, BeforeValidator(...), Hint(...)]` field types, `REGISTRY`
  - **Single `Item(_Base)`** with four optional components: `Offense`, `Defense`, `Environment`, `Limitations`
  - **Identity fields:** `name`, `slot: Slot` (LLM-extracted — where worn/carried), `form: Form`
    (LLM-extracted — physical object type), `rarity: Rarity`, `req_attunement: bool`
  - `slot` and `form` are independent; LLM extracts both from item name + description
  - **`Offense`**: `attack_damage_bonus: int`, `effective_against: list[str]`
  - **`Defense`**: `ac_bonus: int`, `condition_immunities: list[Condition]`, `resistances_against: list[str]` (creature families only), `damage_resistances: list[str]` (damage types only)
  - **`Environment`**: `strong_in: list[str]`
  - **`Limitations`**: `charges: int | None`, `cursed: bool`, `drawbacks: list[str]`
  - **Catch-all:** `special_effects: list[str]`
  - **Enums:** `Slot` (head/neck/body/feet/finger/hand/off_hand/none — fixed, exhaustive),
    `Form` (…/wondrous/other), `Rarity`, `Condition` (…/other)
  - **Normalizers:** `_coerce_enum`; `_norm_str_list`; `_norm_creatures` (strip parentheticals, singularize,
    filter size-category phrases → `"any"`); `_norm_environments` (slug-only — no lemmatization, avoids
    spaCy corruption of adjectives like "wooden"). Creature family generalization handled by LLM prompt, not a
    hardcoded taxonomy — shop is a generic fantasy setting, not a specific game system
- [x] Create `reznar/extract.py` — reads `data/items_raw.json`, populates Postgres via `db.py`
  - Load API key from `.env` via `python-dotenv`; analysis model from `reznar/config.py`
  - `ChatAnthropic(model=ANALYSIS_MODEL).with_structured_output(Item)` per item; carry `name`/`rarity`/
    `req_attunement` through, LLM extracts `slot`/`form` and capability components. 80 items — simple loop
  - `CREATE TABLE IF NOT EXISTS items (...)`: scalars→text/int/bool, lists→`text[]`, `name` PK,
    capability component fields nullable. Insert via `model_dump()`; `ON CONFLICT (name) DO UPDATE`
  - System prompt enforces: creature fields = creature/family names only; `damage_resistances` = damage
    type names only; `charges` = use count (1–20), not capacity measurements; `strong_in` = terrain/location/
    condition nouns only, never material adjectives (wooden, stone, iron)
  - System prompt notes `wondrous item` is a D&D catch-all (not a physical form) — LLM must infer `slot`/`form` from item name and description
  - Retry on `ValidationError`: up to 2 attempts, sending parse error back as correction prompt

## Stage 3 — Analysis

- [ ] Create `analysis.ipynb`
  - Query DB for all items
  - Rarity prediction model
  - Anomaly detection for items whose rarity seems mismatched with their traits
