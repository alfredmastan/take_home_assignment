"""Reznar's Arcane Oddities — domain ontology.

A single `Item` with optional capability components: Offense, Defense, Environment, Limitations.
Each component is None when the item has nothing in that bucket. All items serialize to one flat
`items` table.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

import inflect as _inflect_mod
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
)

_inflect = _inflect_mod.engine()


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
    other = "other"


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


_ENV_BLOCKLIST = {"any_environment", "any", "all_environment", "everywhere", "all", "general"}


def _norm_environments(v):
    if not isinstance(v, list):
        return v
    out: list[str] = []
    for x in v:
        if not isinstance(x, str):
            out.append(x)
            continue
        term = _slug(x)
        if term and term not in _ENV_BLOCKLIST:
            out.append(term)
    return _dedup(out)


_SIZE_KEYWORDS = {
    "size",
    "larger",
    "smaller",
    "bigger",
    "tiny",
    "small",
    "medium",
    "large",
    "huge",
    "gargantuan",
}


def _norm_creatures(v):
    if not isinstance(v, list):
        return v
    out: list[str] = []
    for raw in v:
        if not isinstance(raw, str):
            out.append(raw)
            continue
        # strip parentheticals, keep only the base term
        base_raw = raw.split("(")[0].strip()
        singular = _inflect.singular_noun(base_raw) or base_raw
        term = _slug(singular)
        if term.endswith("_damage"):
            term = term[: -len("_damage")]
        if not term:
            continue
        # size-category phrases (e.g. "creature_at_least_one_size_category_smaller") → "any"
        words = set(term.split("_"))
        if words & _SIZE_KEYWORDS:
            term = "any"
        out.append(term)
    return _dedup(out)


# Annotated field types
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
        "poisoned/exhaustion/lycanthropy/unconscious/other."
    ),
]
CreatureList = Annotated[
    list[str],
    BeforeValidator(_norm_creatures),
    Hint(
        "Creature or creature-family names as lowercase slugs. Use the broadest applicable family, not a specific named creature: "
        "e.g. a named undead creature → 'undead'; a named fiery elemental → 'elemental'; a specific dragon species → 'dragon'. "
        "For size-relative references (e.g. 'creature at least one size smaller') use 'any'. "
        "Non-creature-type strings (e.g. 'armored targets', 'targets using a shield') must NOT appear here — put those in special_effects."
    ),
]
DamageTypeList = Annotated[
    list[str],
    BeforeValidator(_norm_str_list),
    Hint(
        "Damage types the item grants resistance or immunity to, as lowercase slugs. "
        "Examples: fire/cold/lightning/acid/necrotic/radiant/thunder/poison/psychic/bludgeoning/piercing/slashing. "
        "Only physical or elemental damage categories — never creature names here."
    ),
]
EnvironmentList = Annotated[
    list[str],
    BeforeValidator(_norm_environments),
    Hint(
        "Terrain, location, or condition names where this item behaves differently (gains bonuses, only functions, "
        "or has altered effects). Examples: underwater/forest/airborne/darkness/daylight/cold/desert/urban/underground. "
        "Each entry must be a location/terrain/condition noun — NOT a material adjective (wooden, stone, iron, crystal). "
        "If the description says 'in wooden structures', use the terrain type (dungeon, forest) not the material. "
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
