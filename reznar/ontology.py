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
    other = "other"


class Rarity(StrEnum):
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
    other = "other"


class CreatureFamily(StrEnum):
    undead = "undead"
    fiend = "fiend"
    fey = "fey"
    construct = "construct"
    humanoid = "humanoid"
    dragon = "dragon"
    vampire = "vampire"
    medusa = "medusa"
    bronze_dragon = "bronze_dragon"
    other = "other"


class DamageType(StrEnum):
    acid = "acid"
    bludgeoning = "bludgeoning"
    cold = "cold"
    fire = "fire"
    lightning = "lightning"
    necrotic = "necrotic"
    piercing = "piercing"
    poison = "poison"
    slashing = "slashing"
    sonic = "sonic"
    thunder = "thunder"
    other = "other"


class EnvironmentType(StrEnum):
    forest = "forest"
    underwater = "underwater"
    other = "other"


# Helpers
def _slug(v: str) -> str:
    return v.strip().lower().replace(" ", "_").replace("-", "_")


def _coerce_enum(v):
    return _slug(v) if isinstance(v, str) else v


def _norm_str_list(v):
    if not isinstance(v, list):
        return v
    seen: dict[str, None] = {}
    for x in v:
        term = _slug(x) if isinstance(x, str) else x
        seen.setdefault(term, None)
    return list(seen)


def _coerce_enum_list(enum_cls):
    def _validate(v):
        if not isinstance(v, list):
            return v
        seen, out = set(), []
        for x in v:
            slug = _slug(x) if isinstance(x, str) else x
            try:
                val = enum_cls(slug)
            except ValueError:
                val = enum_cls.other
            if val not in seen:
                seen.add(val)
                out.append(val)
        return out

    return _validate


# Annotated field types
RarityField = Annotated[
    Rarity,
    BeforeValidator(_coerce_enum),
    Hint(
        "Rarity tier: uncommon|rare|very_rare|legendary|artifact|varies. "
        "Normalize 'very rare' → 'very_rare'. Use 'varies' if rarity depends on variant or roll."
    ),
]
ConditionList = Annotated[
    list[Condition],
    BeforeValidator(_norm_str_list),
    Hint(
        "Conditions this item grants immunity to. "
        "Valid values: charmed/frightened/stunned/blinded/deafened/paralyzed/petrified/"
        "poisoned/exhaustion/lycanthropy/unconscious/other."
    ),
]
CreatureList = Annotated[
    list[CreatureFamily],
    BeforeValidator(_coerce_enum_list(CreatureFamily)),
    Hint(
        "Creature or creature-family names. Use ONLY these values: "
        "undead/fiend/fey/construct/humanoid/dragon/vampire/medusa/bronze_dragon/other. "
        "Use the broadest applicable family (e.g. a named undead creature → 'undead', a specific dragon species → 'dragon'). "
        "Use 'other' only when no listed family applies. "
        "Non-creature references (e.g. 'armored targets') must NOT appear here — put those in special_effects."
    ),
]
DamageTypeList = Annotated[
    list[DamageType],
    BeforeValidator(_coerce_enum_list(DamageType)),
    Hint(
        "Damage types the item grants resistance or immunity to. Use ONLY these values: "
        "acid/bludgeoning/cold/fire/lightning/necrotic/piercing/poison/slashing/sonic/thunder/other. "
        "Never creature names here."
    ),
]
EnvironmentList = Annotated[
    list[EnvironmentType],
    BeforeValidator(_coerce_enum_list(EnvironmentType)),
    Hint(
        "Terrain or location where this item gains bonuses or has altered effects. Use ONLY these values: "
        "forest/underwater/other. "
        "Leave empty if the item works the same in any environment."
    ),
]
SlotField = Annotated[
    Slot,
    BeforeValidator(_coerce_enum),
    Hint(
        "Where on the body this item is worn or carried: "
        "head (hat/helm/mask/face/crown/tiara/circlet/headband/cap — anything worn on the head or face), "
        "neck (amulet/pendant/necklace/collar), "
        "body (cloak/armor/robe/gown/vest/coat), "
        "feet (boots/shoes/sandals/slippers), "
        "finger (ring/band), "
        "hand (weapon/wand/staff/rod/gloves/gauntlets), "
        "off_hand (shield/buckler), "
        "none (potion or consumable with no wearable slot)."
    ),
]
FormField = Annotated[
    Form,
    BeforeValidator(_coerce_enum),
    Hint(
        "Physical form of the item: "
        "ring/amulet/cloak/gown/boots/helm/mask/crown/headband/armor/shield/weapon/potion/wondrous/other. "
        "Use 'wondrous' for held/used objects with no wearable slot (horn, drum, pouch, chest, pipe). "
        "Use 'other' if none of the above forms apply."
    ),
]


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
        default=[],
        description="Creature families this item grants resistance or protection against. ONLY creature names — never damage types.",
    )
    damage_resistances: DamageTypeList = Field(
        default=[],
        description="Damage types (fire, cold, lightning, acid, necrotic, etc.) the item grants resistance or immunity to. ONLY damage type names — never creature names.",
    )


class Environment(_Base):
    """Set if the item has environment-specific behavior — bonuses granted in a setting OR effects that only function in specific environments."""

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
    drawbacks: list[str] = Field(
        default=[],
        description="Penalties not captured by cursed/charges, as short phrases (e.g. 'reduces Strength by 2 while worn', 'causes blindness in sunlight').",
    )


class Item(_Base):
    name: str = Field(min_length=1)
    slot: SlotField
    form: FormField
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


REGISTRY: dict[str, type[BaseModel]] = {
    "Item": Item,
}
