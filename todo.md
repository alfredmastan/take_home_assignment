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
  - **Identity fields:** `name`, `form: Form`, `slot: Slot` (derived from form via `FORM_SLOT`, never extracted),
    `rarity: Rarity`, `req_attunement: bool`
  - **`Offense`**: `attack_damage_bonus: int`, `effective_against: list[str]`
  - **`Defense`**: `ac_bonus: int`, `condition_immunities: list[Condition]`, `resistances_against: list[str]`
  - **`Environment`**: `strong_in: list[str]`
  - **`Limitations`**: `charges: int | None`, `cursed: bool`, `drawback: str | None`
  - **Catch-all:** `special_effects: list[str]`
  - **Enums:** `Slot`, `Form`, `Rarity`, `Condition`
  - **Normalizers:** `_coerce_enum` (slug for enum fields); `_norm_str_list` (slug + dedup, shared by
    `ConditionList` and `EnvironmentList`); `_norm_creatures` (strip parentheticals + `CREATURE_TAXONOMY` expansion)
  - **`CREATURE_TAXONOMY`:** specific→parent, both tagged — vampire→undead, devil/demon→fiend,
    werewolf→shapechanger, wyrmling/bronze_dragon→dragon, medusa→monstrosity
- [ ] Create `reznar/extract.py` — reads `data/items_raw.json`, populates Postgres via `db.py`
  - Load API key from `.env` via `python-dotenv`; analysis model from `reznar/config.py`
  - **Classify form first** (rule-based): `wondrous item` is D&D's misc bucket, NOT a form — recover
    form from the **name**. Explicit types: `armor (X)`→armor, `weapon (X)`→weapon, `ring`→ring,
    `potion`→potion. Else name keywords: amulet/necklace→amulet, boots→boots, cloak/gown→cloak/gown,
    helm/mask/crown/headband→helm/mask/crown/headband. Fall-through→wondrous.
  - `ChatAnthropic(model=ANALYSIS_MODEL).with_structured_output(Item)` per item; carry `name`/`rarity`/
    `req_attunement`/`form` through, LLM fills capability components. 80 items — simple loop
  - `CREATE TABLE IF NOT EXISTS items (...)`: scalars→text/int/bool, lists→`text[]`, `name` PK,
    capability component fields nullable. Insert via `model_dump()`; `ON CONFLICT (name) DO UPDATE`

## Stage 3 — Analysis

- [ ] Create `analysis.ipynb`
  - Query DB for all items
  - Rarity prediction model
  - Anomaly detection for items whose rarity seems mismatched with their traits
