"""Reznar's Arcane Oddities — domain ontology.

A single `Item` with optional capability components: Offense, Defense, Environment, Limitations.
Each component is None when the item has nothing in that bucket. All items serialize to one flat
`items` table.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)


# Hint carries field descriptions as Annotated metadata for LLM prompts.
class Hint:
    __slots__ = ("text",)

    def __init__(self, text: str):
        self.text = text


# Controlled vocabularies
class Slot(StrEnum):
    head = "head"
    neck = "neck"
    body = "body"
    hands = "hands"
    feet = "feet"
    finger = "finger"
    hand = "hand"
    off_hand = "off_hand"
    none = "none"


class Form(StrEnum):
    ring = "ring"
    amulet = "amulet"
    cloak = "cloak"
    gown = "gown"
    boots = "boots"
    helm = "helm"
    mask = "mask"
    crown = "crown"
    headband = "headband"
    armor = "armor"
    shield = "shield"
    weapon = "weapon"
    potion = "potion"
    wondrous = "wondrous"


class Rarity(StrEnum):
    common = "common"
    uncommon = "uncommon"
    rare = "rare"
    very_rare = "very_rare"
    legendary = "legendary"
    artifact = "artifact"
    varies = "varies"


class Condition(StrEnum):
    charmed = "charmed"
    frightened = "frightened"
    stunned = "stunned"
    blinded = "blinded"
    deafened = "deafened"
    paralyzed = "paralyzed"
    petrified = "petrified"
    poisoned = "poisoned"
    exhaustion = "exhaustion"
    lycanthropy = "lycanthropy"
    unconscious = "unconscious"


# specific creature -> broad parent; both are tagged so either query matches
CREATURE_TAXONOMY = {
    "vampire": "undead",
    "lich": "undead",
    "zombie": "undead",
    "skeleton": "undead",
    "ghost": "undead",
    "specter": "undead",
    "wraith": "undead",
    "ghoul": "undead",
    "devil": "fiend",
    "demon": "fiend",
    "barlgura": "fiend",
    "werewolf": "shapechanger",
    "lycanthrope": "shapechanger",
    "wyrmling": "dragon",
    "bronze_dragon": "dragon",
    "medusa": "monstrosity",
}


# Helpers
def _slug(v: str) -> str:
    return v.strip().lower().replace(" ", "_").replace("-", "_")


def _dedup(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for it in items:
        seen.setdefault(it, None)
    return list(seen)


def _coerce_enum(v):
    return _slug(v) if isinstance(v, str) else v


def _norm_str_list(v):
    if not isinstance(v, list):
        return v
    return _dedup([_slug(x) if isinstance(x, str) else x for x in v])


def _norm_creatures(v):
    if not isinstance(v, list):
        return v
    out: list[str] = []
    for raw in v:
        if not isinstance(raw, str):
            out.append(raw)
            continue
        # strip parentheticals: "fiend (devil)" -> "fiend"; keep the inner term too
        base = _slug(raw.split("(")[0])
        inner = _slug(raw[raw.find("(") + 1 : raw.find(")")]) if "(" in raw and ")" in raw else None
        for term in (base, inner):
            if not term:
                continue
            out.append(term)
            if term in CREATURE_TAXONOMY:
                out.append(CREATURE_TAXONOMY[term])
    return _dedup(out)


# Annotated field types
FormField = Annotated[
    Form,
    BeforeValidator(_coerce_enum),
    Hint(
        "Physical form of the item: ring/amulet/cloak/gown/boots/helm/mask/crown/headband/"
        "armor/shield/weapon/potion/wondrous. Use 'wondrous' only for items with no wearable "
        "slot (horn, drum, pouch, chest, pipe, etc.)."
    ),
]
RarityField = Annotated[
    Rarity,
    BeforeValidator(_coerce_enum),
    Hint(
        "Rarity tier: common|uncommon|rare|very_rare|legendary|artifact|varies. "
        "Normalize 'very rare' → 'very_rare'. Use 'varies' if rarity depends on variant or roll."
    ),
]
ConditionList = Annotated[
    list[Condition],
    BeforeValidator(_norm_str_list),
    Hint(
        "Conditions this item grants immunity to. "
        "Valid values: charmed/frightened/stunned/blinded/deafened/paralyzed/petrified/"
        "poisoned/exhaustion/lycanthropy/unconscious."
    ),
]
CreatureList = Annotated[
    list[str],
    BeforeValidator(_norm_creatures),
    Hint(
        "Creature types as lowercase slugs. Include both the specific type and its parent category: "
        "vampire/lich/ghoul/zombie/skeleton/ghost/specter/wraith → also undead; "
        "devil/demon → also fiend; werewolf/lycanthrope → also shapechanger; "
        "wyrmling/bronze_dragon → also dragon; medusa → also monstrosity."
    ),
]
EnvironmentList = Annotated[
    list[str],
    BeforeValidator(_norm_str_list),
    Hint(
        "Environments as lowercase slugs where the item is enhanced or relevant. "
        "Examples: underwater/forest/airborne/darkness/daylight/cold/desert/urban/underground."
    ),
]

# slot is derived from form, never extracted by the LLM to avoid hallucination
FORM_SLOT: dict[Form, Slot] = {
    Form.ring: Slot.finger,
    Form.amulet: Slot.neck,
    Form.cloak: Slot.body,
    Form.gown: Slot.body,
    Form.boots: Slot.feet,
    Form.helm: Slot.head,
    Form.mask: Slot.head,
    Form.crown: Slot.head,
    Form.headband: Slot.head,
    Form.armor: Slot.body,
    Form.shield: Slot.off_hand,
    Form.weapon: Slot.hand,
    Form.potion: Slot.none,
    Form.wondrous: Slot.none,
}


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class Offense(_Base):
    """Set only if the item improves attacks or is extra effective against specific creatures."""

    attack_damage_bonus: int = Field(
        default=0, description="Flat bonus applied to both attack rolls and damage rolls."
    )
    effective_against: CreatureList = Field(
        default=[],
        description="Creature types this item deals extra damage or applies extra control effects against.",
    )


class Defense(_Base):
    """Set only if the item reduces damage, grants condition immunity, or protects against creature types."""

    ac_bonus: int = Field(default=0, description="Flat bonus to Armor Class.")
    condition_immunities: ConditionList = Field(
        default=[], description="Conditions the wearer is immune to while using this item."
    )
    resistances_against: CreatureList = Field(
        default=[], description="Creature types this item grants resistance or protection against."
    )


class Environment(_Base):
    """Set only if a specific setting enhances the item's function or grants bonuses."""

    strong_in: EnvironmentList = Field(
        default=[],
        description="Environments where this item grants bonuses or enhanced abilities.",
    )


class Limitations(_Base):
    """Set only if the item has charges, a curse, or a notable drawback."""

    charges: int | None = Field(
        default=None, description="Number of charges the item starts with; None if unlimited use."
    )
    cursed: bool = False
    drawback: str | None = Field(
        default=None,
        description="Freetext penalty not captured by cursed/charges (e.g. 'reduces Strength by 2 while worn').",
    )


class Item(_Base):
    name: str = Field(min_length=1)
    form: FormField
    slot: Slot | None = None
    rarity: RarityField
    req_attunement: bool = False

    offense: Offense | None = None
    defense: Defense | None = None
    environment: Environment | None = None
    limitations: Limitations | None = None

    special_effects: list[str] = Field(
        default=[],
        description="Effects not captured by offense/defense/environment/limitations, as short phrases (e.g. 'grants darkvision 60 ft', 'casts Misty Step once per day').",
    )

    @model_validator(mode="after")
    def _derive_slot(self) -> Item:
        self.slot = FORM_SLOT[Form(self.form)].value
        return self


REGISTRY: dict[str, type[BaseModel]] = {
    "Item": Item,
}
