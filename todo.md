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

- [x] Design `reznar/ontology.py` — per-form Pydantic classes composed from a base + capability mixins
  - Follow `stormland/ontology.py` pattern: `_Base` (`extra="forbid"`), `Hint` class,
    `Annotated[type, BeforeValidator(...), Hint(...)]` field types, `REGISTRY`
  - **Universal base `_Item(_Base)`** + two capability mixins: **`_Offense`** (offensive improvements)
    and **`_Defense`** (defensive improvements). Each form composes only the blocks it can use, so combat
    magnitudes never appear on a ring and AC bonuses never appear on a weapon. Forms pin `slot` and add a
    form-specific `subtype` enum where one exists. All serialize into one flat `items` table (union of cols).
  - **Classes / `REGISTRY`** (mixins in parens): `Weapon` (`_Item,_Offense`; slot=hand, `subtype: WeaponType`),
    `Armor` (`_Item,_Offense,_Defense`; slot=body, `subtype: ArmorType`), `Shield` (`_Item,_Defense`; slot=off_hand — its
    own class, no subtype), `Ring` (`_Item,_Defense`; finger), `Amulet` (`_Item,_Defense`; neck),
    `Cloak` (`_Item,_Defense`; body, cloak/gown), `Footwear` (`_Item,_Offense`; feet, boots),
    `Headgear` (`_Item,_Offense,_Defense`; head, helm/mask/crown/headband),
    `Potion` (`_Item,_Defense`; none), `Wondrous` (`_Item,_Offense,_Defense`; none, residual)
  - **Controlled vocabularies (`Literal`/`Enum` + `Hint`)**:
    - `Slot`: head | neck | body | hands | feet | finger | hand | off_hand | none
    - `Form`: ring | amulet | cloak | gown | boots | helm | mask | crown | headband | armor | shield | weapon | potion | wondrous
    - `Rarity`: common | uncommon | rare | very_rare | legendary | artifact | varies
    - `WeaponType`: sword | dagger | axe | battleaxe | handaxe | greatsword | longsword | shortsword | rapier | mace | warhammer | war_pick | any
    - `ArmorType`: leather | half_plate | plate | splint | medium_or_heavy | any (shield is now its own `Shield` class, not a subtype)
    - `DamageType`: bludgeoning | piercing | slashing | fire | cold | lightning | thunder | acid | poison | necrotic | radiant | force | psychic
    - `Condition`: charmed | frightened | stunned | blinded | deafened | paralyzed | petrified | poisoned | exhaustion | lycanthropy | unconscious
    - `Recharge`: none | short_rest | long_rest | dawn | midnight | daily | finite_uses
  - **Fields (simplified to five buckets — see `reznar/deferred_fields.md` for what was dropped)**:
    - `_Item` (universal): Identity `name`, `form: Form`, `slot: Slot`, `rarity: Rarity`, `attunement: bool`;
      Environments `strong_in_environments` (permissive strings); Limitations `charges: Optional[int]`,
      `recharge: Recharge="none"`, `cursed: bool=False`, `drawback: Optional[str]`
    - `_Offense`: `attack_damage_bonus: int=0` (single bonus — "+N to attack AND damage" is always one value);
      `inflicts_damage_types: list[DamageType]`; `effective_against: list[str]` (creatures it's extra effective attacking)
    - `_Defense`: `ac_bonus: int=0`; `resistances`, `damage_immunities` (each `list[DamageType]`);
      `condition_immunities: list[Condition]`; `resistant_against: list[str]` (creatures it protects against)
    - Creature fields are permissive normalized strings (not strict enum — keep specifics like medusa/vampire)
    - `subtype` only on `Weapon`/`Armor`
    - **Deferred** (in `reznar/deferred_fields.md`, not on any class): `grants_abilities`+`Ability` enum,
      `special_effects`; **dropped** (zero data): `vulnerabilities`, `weak_vs_creatures`, `weak_in_environments`,
      `raw_description`
  - **Normalizers (`BeforeValidator`)**: `_damage_type` (lowercase; electrical→lightning, sonic→thunder);
    `_creature` (lowercase, strip parentheticals: `fiend (devil)`→fiend); `_environment` (wooded→forest,
    immersed→underwater, flying→airborne); enum coercion (lowercase+underscore: `very rare`→very_rare)
  - **Value normalization is the key lever for Reznar's pattern-finding** (NOT extra tables — storage
    stays one wide `items` table; the 9 classes are modeling convenience and all serialize into it).
    Reznar's job is cross-item queries ("which weapons/shields are good vs vampires?") — easy as a single
    `WHERE form IN (...) AND 'vampire' = ANY(effective_against)` only if the *values* are canonical.
    Two parts:
    - **Canonical terms**: lowercase + map synonyms so the same concept is one token (electrical→lightning,
      sonic→thunder, wooded→forest, immersed/water→underwater, flying/airborne→airborne, `very rare`→very_rare).
    - **Category taxonomy (specific → parent), tag BOTH at extraction time** so a query for either matches:
      - Creatures: `vampire`→also `undead`; `devil`/`demon`→also `fiend`; `bronze dragon`/`wyrmling`→also `dragon`;
        `werewolf`/`lycanthrope`→also `shapechanger`. Without this, querying `vampire` misses Sword of the Lion
        Emperor / Cold Iron Weapon / Amulet of Undead Control (tagged `undead`).
      - Damage: expand umbrella terms — `elemental`→`acid,cold,fire,lightning,thunder` (e.g. Elixir of the
        Elements); `weapon damage`→`bludgeoning,piercing,slashing`.
    - Store the specific AND the parent in the same array (e.g. `effective_against = {vampire, undead}`) so
      both precise and broad customer queries work in plain SQL. Keep a small taxonomy dict in `ontology.py`.
- [ ] Create `reznar/extract.py` — reads `data/items_raw.json`, populates Postgres via `db.py`
  - Load API key from `.env` via `python-dotenv`; analysis model from `reznar/config.py`
  - **Classify form first** (rule-based): `wondrous item` is D&D's misc bucket, NOT a form — recover
    form from the **name**. Explicit types: `armor (shield)`→Shield, other `armor (X)`→Armor,
    `weapon (X)`→Weapon, `ring`→Ring, `potion`→Potion. Else name keywords (priority): ring→Ring,
    amulet/necklace→Amulet, boots→Footwear,
    cloak/gown→Cloak, helm/mask/crown/headband→Headgear. Fall-through (caltrops/horn/pipe/chest/drum/
    backpack/compass/canteen/pouch/shovel/scroll)→Wondrous, slot=none. Look up class in `REGISTRY`
  - `ChatAnthropic(model=ANALYSIS_MODEL).with_structured_output(cls)` per item; carry name/rarity/
    attunement through, LLM fills semantic fields. 80 items — simple loop (optional
    `ThreadPoolExecutor`)
  - `CREATE TABLE IF NOT EXISTS items (...)` = UNION of subclass fields (effect cols nullable;
    `class_type` + `form` + `subtype` columns). Scalars→text/int/bool, lists→`text[]`, `name` PK.
    Insert via `model_dump()`; `ON CONFLICT (name) DO UPDATE` for idempotent re-runs; `conn.commit()`

## Stage 3 — Analysis

- [ ] Create `analysis.ipynb`
  - Query DB for all items
  - Rarity prediction model
  - Anomaly detection for items whose rarity seems mismatched with their traits
