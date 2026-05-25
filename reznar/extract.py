"""Stage 2: read items_raw.json, extract ontology fields via LLM, upsert to Postgres."""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

import db
from reznar.config import ANALYSIS_MODEL
from reznar.ontology import Item, _coerce_enum

load_dotenv()

RAW_PATH = Path("data/items_raw.json")

_CREATE = """
CREATE TABLE IF NOT EXISTS items (
    name                          text PRIMARY KEY,
    form                          text,
    slot                          text,
    rarity                        text,
    req_attunement                boolean,
    offense_attack_damage_bonus   int,
    offense_effective_against     text[],
    defense_ac_bonus              int,
    defense_condition_immunities  text[],
    defense_resistances_against   text[],
    defense_damage_resistances    text[],
    environment_strong_in         text[],
    limitations_charges           int,
    limitations_cursed            boolean,
    limitations_drawbacks         text[],
    special_effects               text[]
)
"""

_UPSERT = """
INSERT INTO items (
    name, form, slot, rarity, req_attunement,
    offense_attack_damage_bonus, offense_effective_against,
    defense_ac_bonus, defense_condition_immunities, defense_resistances_against,
    defense_damage_resistances,
    environment_strong_in,
    limitations_charges, limitations_cursed, limitations_drawbacks,
    special_effects
) VALUES (
    %(name)s, %(form)s, %(slot)s, %(rarity)s, %(req_attunement)s,
    %(offense_attack_damage_bonus)s, %(offense_effective_against)s,
    %(defense_ac_bonus)s, %(defense_condition_immunities)s, %(defense_resistances_against)s,
    %(defense_damage_resistances)s,
    %(environment_strong_in)s,
    %(limitations_charges)s, %(limitations_cursed)s, %(limitations_drawbacks)s,
    %(special_effects)s
)
ON CONFLICT (name) DO UPDATE SET
    form                          = EXCLUDED.form,
    slot                          = EXCLUDED.slot,
    rarity                        = EXCLUDED.rarity,
    req_attunement                = EXCLUDED.req_attunement,
    offense_attack_damage_bonus   = EXCLUDED.offense_attack_damage_bonus,
    offense_effective_against     = EXCLUDED.offense_effective_against,
    defense_ac_bonus              = EXCLUDED.defense_ac_bonus,
    defense_condition_immunities  = EXCLUDED.defense_condition_immunities,
    defense_resistances_against   = EXCLUDED.defense_resistances_against,
    defense_damage_resistances    = EXCLUDED.defense_damage_resistances,
    environment_strong_in         = EXCLUDED.environment_strong_in,
    limitations_charges           = EXCLUDED.limitations_charges,
    limitations_cursed            = EXCLUDED.limitations_cursed,
    limitations_drawbacks         = EXCLUDED.limitations_drawbacks,
    special_effects               = EXCLUDED.special_effects
"""

_SYSTEM = (
    "You are extracting structured data from fantasy magic item descriptions for a generic fantasy shop. "
    "Classify the item's physical form, worn slot, and capability components. "
    "'Wondrous item' is a catch-all type and says nothing about physical form — "
    "infer form and slot from the item name and description. "
    "Only set offense/defense/limitations when the item explicitly has those traits. "
    "Do NOT set environment when the item works in any environment or has no environment-specific behavior. "
    "Use special_effects for anything not captured by the four components.\n\n"
    "CREATURE FIELDS (effective_against, resistances_against): "
    "Use ONLY these values: undead/fiend/fey/construct/humanoid/dragon/vampire/medusa/bronze_dragon/other. "
    "Use the broadest applicable family (e.g. a named undead creature → 'undead', a specific dragon species → 'dragon'). "
    "Use 'other' only when no listed family applies. "
    "Non-creature references (e.g. 'armored targets', 'targets using a shield') must NOT appear "
    "in these lists — omit them and describe the mechanic in special_effects instead. "
    "resistances_against must contain ONLY creature/creature-family names — never damage type words "
    "like fire, acid, lightning, necrotic, cold, thunder. Damage type resistances/immunities go in "
    "defense.damage_resistances instead.\n\n"
    "DAMAGE TYPE FIELD (damage_resistances): "
    "Use ONLY these values: acid/bludgeoning/cold/fire/lightning/necrotic/piercing/poison/slashing/sonic/thunder/other. "
    "Never creature names here.\n\n"
    "ENVIRONMENT FIELD (strong_in): "
    "Use ONLY these values: forest/underwater/other. "
    "Leave empty if the item works the same in any environment.\n\n"
    "CHARGES: Set charges only to a count of distinct magical ability uses (small integer, typically "
    "1–20). Capacity measurements — pounds of material, cubic feet, distance, weight — are NOT charges. "
    "For capacity-limited items, describe the limit in drawbacks or special_effects and leave charges null."
)


def _to_row(item: Item) -> dict:
    off = item.offense
    dfn = item.defense
    env = item.environment
    lim = item.limitations
    return {
        "name": item.name,
        "form": item.form,
        "slot": item.slot,
        "rarity": item.rarity,
        "req_attunement": item.req_attunement,
        "offense_attack_damage_bonus": off.attack_damage_bonus if off else 0,
        "offense_effective_against": off.effective_against if off else [],
        "defense_ac_bonus": dfn.ac_bonus if dfn else 0,
        "defense_condition_immunities": dfn.condition_immunities if dfn else [],
        "defense_resistances_against": dfn.resistances_against if dfn else [],
        "defense_damage_resistances": dfn.damage_resistances if dfn else [],
        "environment_strong_in": env.strong_in if env else [],
        "limitations_charges": lim.charges if lim else None,
        "limitations_cursed": lim.cursed if lim else False,
        "limitations_drawbacks": lim.drawbacks if lim else [],
        "special_effects": item.special_effects,
    }


def main() -> None:
    raw_items: list[dict] = json.loads(RAW_PATH.read_text())
    llm = ChatAnthropic(model=ANALYSIS_MODEL).with_structured_output(Item)

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(_CREATE)
        conn.commit()

        total = len(raw_items)
        for i, raw in enumerate(raw_items, 1):
            name = raw["name"]
            print(f"[{i}/{total}] {name}", flush=True)

            user_msg = (
                f"Item name: {name}\n"
                f"D&D item type: {raw.get('item_type', 'wondrous item')}\n"
                f"Rarity: {raw['rarity']}\n"
                f"Attunement required: {raw['attunement']}\n"
                f"Description: {raw['description']}"
            )
            messages = [SystemMessage(_SYSTEM), HumanMessage(user_msg)]
            item = None
            for attempt in range(2):
                try:
                    item = llm.invoke(messages)
                    item = item.model_copy(
                        update={
                            "name": name,
                            "rarity": _coerce_enum(raw["rarity"]),
                            "req_attunement": raw["attunement"],
                        }
                    )
                    break
                except (ValidationError, Exception) as exc:
                    if attempt == 0:
                        print(f"  retrying {name!r} — {exc}")
                        messages.append(
                            HumanMessage(
                                "Your previous response did not parse correctly. "
                                "Return ALL fields as a valid JSON object — "
                                "every component (offense, defense, environment, limitations) "
                                "must be a JSON object or null, never a string."
                            )
                        )
                    else:
                        print(f"  WARNING: skipping {name!r} — {exc}")
            if item is None:
                continue

            cur.execute(_UPSERT, _to_row(item))
            conn.commit()

    print("Done.")


if __name__ == "__main__":
    main()
