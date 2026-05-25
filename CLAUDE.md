# CLAUDE.md

## Goal

Take-home for MulhollandAI: design an ontology for Reznar's Arcane Oddities (fantasy magic item shop), extract items from `data/items_combined.pdf` into local Postgres, then analyze rarity anomalies in a Jupyter notebook.

**Deliverables:**
1. `reznar/ontology.py` + extraction pipeline → populated `items` table
2. `analysis.ipynb` → rarity prediction and anomaly detection

## Status

| File | Status |
|------|--------|
| `stormland/ontology.py` | Complete — reference implementation |
| `reznar/config.py` | Complete — loads `VISION_MODEL`/`ANALYSIS_MODEL` from `.env` |
| `reznar/ontology.py` | Complete — `Item` + components + `REGISTRY` |
| `reznar/parser.py` | Complete — Stage 1 PDF → `data/items_raw.json` (80 items) |
| `reznar/extract.py` | Complete — Stage 2 → `items` table in Postgres |
| `data/items_raw.json` | Generated — 80 items |
| `analysis.ipynb` | **Not built yet** |

## Commands

```bash
uv sync                          # install deps
uv run python verify.py          # check Postgres
uv run python reznar/parser.py     # Stage 1
uv run python reznar/extract.py    # Stage 2
uv run ruff check . && uv run ruff format .
```

Reset DB: `rm -rf data/.pg/`

## Architecture

**DB (`db.py`):** Embedded Postgres via `pgserver` in `data/.pg/`. Auto-starts on first connect.
```python
import db
with db.connect() as conn, conn.cursor() as cur:
    cur.execute("...")
```

**AI:** LangChain (`ChatAnthropic` from `langchain_anthropic`) — never raw Anthropic SDK. Keys/model names in `.env`.

**All pipeline code lives in `reznar/`.**

## Ontology — `Item`

Single flat `items` table. One `Item` class with four optional capability components (each `None` if unused):

- **Identity:** `name`, `slot: Slot`, `form: Form`, `rarity: Rarity`, `req_attunement: bool`
- **`Offense`** (attacks/effectiveness): `attack_damage_bonus: int`, `effective_against: list[CreatureFamily]`
- **`Defense`** (damage reduction/immunity): `ac_bonus: int`, `condition_immunities: list[Condition]`, `resistances_against: list[CreatureFamily]`, `damage_resistances: list[DamageType]`
- **`Environment`** (situational boosts): `strong_in: list[EnvironmentType]`
- **`Limitations`** (charges/curse/drawbacks): `charges: int | None`, `cursed: bool`, `drawbacks: list[str]`
- **`special_effects: list[str]`** — catch-all for anything unstructured

**Enums:**
- `Slot`: head/neck/body/feet/finger/hand/off_hand/none
- `Form`: ring/amulet/cloak/gown/boots/helm/mask/crown/headband/armor/shield/weapon/potion/wondrous/other
- `Rarity`: common/uncommon/rare/very_rare/legendary/artifact/varies
- `Condition`: charmed/frightened/stunned/blinded/deafened/paralyzed/petrified/poisoned/exhaustion/lycanthropy/unconscious/other
- `CreatureFamily`: undead/fiend/fey/construct/humanoid/dragon/vampire/medusa/bronze_dragon/other
- `DamageType`: acid/bludgeoning/cold/fire/lightning/necrotic/piercing/poison/slashing/sonic/thunder/other
- `EnvironmentType`: forest/underwater/other

`slot` and `form` are LLM-inferred independently. `wondrous` = held/used with no wearable slot. All enum lists use `other` to gracefully handle values outside the known vocabulary.

## Pipeline

**Stage 1 (`parser.py`):** Vision model (`claude-haiku-4-5-20251001`) renders each PDF page → extracts `name/item_type/rarity/attunement/description` into `data/items_raw.json`. Sequential pages share a `CONTINUATION_HINT` for cross-page items. Model ignores decorative images; classifies first text block as new item (ALL-CAPS, 1–5 words) or continuation.

**Stage 2 (`extract.py`):** Reads `items_raw.json` → text LLM via `.with_structured_output(Item)` → writes to `items` table (`ON CONFLICT (name) DO UPDATE`). System prompt enumerates valid values for `CreatureFamily`, `DamageType`, and `EnvironmentType` so the LLM picks canonical terms; unknown values fall to `other` via `_coerce_enum_list`. Enforces: creature fields = `CreatureFamily` only; `damage_resistances` = `DamageType` only; `charges` = use count (1–20).
