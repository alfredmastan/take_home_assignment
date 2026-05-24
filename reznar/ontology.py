"""Reznar's Arcane Oddities — domain ontology.

Per-form Pydantic classes composed from a universal `_Item` base plus two
capability mixins — `_Offense` (offensive improvements) and `_Defense`
(defensive improvements). Each form mixes in only the blocks it can use, so
combat magnitudes never appear on a ring and AC bonuses never appear on a
weapon. Forms pin `slot` and add a `subtype` enum only where one exists
(Weapon, Armor).

All classes serialize into one flat `items` table. The point of the design is
cross-item pattern-finding for Reznar ("which weapons/shields are good vs
vampires?"), which works as a single SQL filter only if values are canonical —
so the normalizers below lowercase + map synonyms, and expand a small taxonomy
(specific -> parent) so a query for `vampire` also matches items tagged `undead`.

See ../stormland/ontology.py for the reference pattern.
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


# ---------------------------------------------------------------------------
# Marker: free-text description for LLM agents, carried as Annotated metadata.
# ---------------------------------------------------------------------------
class Hint:
    __slots__ = ("text",)

    def __init__(self, text: str):
        self.text = text


# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------
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


class WeaponType(StrEnum):
    sword = "sword"
    dagger = "dagger"
    axe = "axe"
    battleaxe = "battleaxe"
    handaxe = "handaxe"
    greatsword = "greatsword"
    longsword = "longsword"
    shortsword = "shortsword"
    rapier = "rapier"
    mace = "mace"
    warhammer = "warhammer"
    war_pick = "war_pick"
    any = "any"


class ArmorType(StrEnum):
    leather = "leather"
    half_plate = "half_plate"
    plate = "plate"
    splint = "splint"
    medium_or_heavy = "medium_or_heavy"
    any = "any"


class DamageType(StrEnum):
    bludgeoning = "bludgeoning"
    piercing = "piercing"
    slashing = "slashing"
    fire = "fire"
    cold = "cold"
    lightning = "lightning"
    thunder = "thunder"
    acid = "acid"
    poison = "poison"
    necrotic = "necrotic"
    radiant = "radiant"
    force = "force"
    psychic = "psychic"


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


class Recharge(StrEnum):
    none = "none"
    short_rest = "short_rest"
    long_rest = "long_rest"
    dawn = "dawn"
    midnight = "midnight"
    daily = "daily"
    finite_uses = "finite_uses"


# ---------------------------------------------------------------------------
# Normalization maps — canonical terms + specific->parent taxonomy
# ---------------------------------------------------------------------------
DAMAGE_SYNONYMS = {
    "electrical": "lightning",
    "electric": "lightning",
    "sonic": "thunder",
}
DAMAGE_UMBRELLAS = {
    "elemental": ["acid", "cold", "fire", "lightning", "thunder"],
    "weapon": ["bludgeoning", "piercing", "slashing"],
    "weapon_damage": ["bludgeoning", "piercing", "slashing"],
    "physical": ["bludgeoning", "piercing", "slashing"],
    "nonmagical": ["bludgeoning", "piercing", "slashing"],
}
CONDITION_SYNONYMS = {
    "charm": "charmed",
    "fear": "frightened",
    "frighten": "frightened",
    "stun": "stunned",
    "blind": "blinded",
    "deafen": "deafened",
    "paralyze": "paralyzed",
    "paralysis": "paralyzed",
    "petrification": "petrified",
    "petrify": "petrified",
    "poison": "poisoned",
}
RECHARGE_SYNONYMS = {
    "day": "daily",
    "daily": "daily",
    "per_day": "daily",
    "24_hours": "daily",
    "short": "short_rest",
    "long": "long_rest",
    "finite": "finite_uses",
}
# specific creature -> broad parent category (tag BOTH so either query matches)
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
ENVIRONMENT_SYNONYMS = {
    "wooded": "forest",
    "woods": "forest",
    "immersed": "underwater",
    "water": "underwater",
    "submerged": "underwater",
    "flying": "airborne",
    "aerial": "airborne",
    "dark": "darkness",
    "sunlight": "daylight",
    "arctic": "cold",
}


# ---------------------------------------------------------------------------
# Helpers + field normalizers
# ---------------------------------------------------------------------------
def _slug(v: str) -> str:
    return v.strip().lower().replace(" ", "_").replace("-", "_")


def _dedup(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for it in items:
        seen.setdefault(it, None)
    return list(seen)


def _coerce_enum(v):
    return _slug(v) if isinstance(v, str) else v


def _norm_damage_list(v):
    if not isinstance(v, list):
        return v
    out: list[str] = []
    for raw in v:
        if not isinstance(raw, str):
            out.append(raw)
            continue
        key = _slug(raw)
        if key in DAMAGE_UMBRELLAS:
            out.extend(DAMAGE_UMBRELLAS[key])
            continue
        mapped = DAMAGE_SYNONYMS.get(key, key)
        if mapped is not None:
            out.append(mapped)
    return _dedup(out)


def _norm_conditions(v):
    if not isinstance(v, list):
        return v
    return _dedup(
        [CONDITION_SYNONYMS.get(_slug(x), _slug(x)) if isinstance(x, str) else x for x in v]
    )


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
            if term in CREATURE_TAXONOMY:  # also tag the broad parent
                out.append(CREATURE_TAXONOMY[term])
    return _dedup(out)


def _norm_environments(v):
    if not isinstance(v, list):
        return v
    return _dedup(
        [ENVIRONMENT_SYNONYMS.get(_slug(x), _slug(x)) if isinstance(x, str) else x for x in v]
    )


def _norm_recharge(v):
    if not isinstance(v, str):
        return v
    s = _slug(v)
    return RECHARGE_SYNONYMS.get(s, s)


# ---------------------------------------------------------------------------
# Annotated field types
# ---------------------------------------------------------------------------
FormField = Annotated[
    Form, BeforeValidator(_coerce_enum), Hint("Object kind, e.g. ring/amulet/helm.")
]
SlotField = Annotated[Slot, BeforeValidator(_coerce_enum), Hint("Where the item is worn/held.")]
RarityField = Annotated[
    Rarity,
    BeforeValidator(_coerce_enum),
    Hint("common|uncommon|rare|very_rare|legendary|artifact|varies; 'very rare' is normalized."),
]
WeaponTypeField = Annotated[
    WeaponType, BeforeValidator(_coerce_enum), Hint("Weapon kind, e.g. dagger.")
]
ArmorTypeField = Annotated[
    ArmorType,
    BeforeValidator(_coerce_enum),
    Hint("Armor kind incl. 'shield'; 'half-plate' is normalized to half_plate."),
]
RechargeField = Annotated[
    Recharge,
    BeforeValidator(_norm_recharge),
    Hint("How the item recharges: short_rest|long_rest|dawn|midnight|daily|finite_uses|none."),
]

DamageList = Annotated[
    list[DamageType],
    BeforeValidator(_norm_damage_list),
    Hint(
        "Damage types; 'elemental' expands to its 5 types, 'weapon' to bludgeoning/piercing/slashing."
    ),
]
ConditionList = Annotated[
    list[Condition],
    BeforeValidator(_norm_conditions),
    Hint("Conditions the item makes you immune to (charmed/frightened/stunned/petrified/...)."),
]
CreatureList = Annotated[
    list[str],
    BeforeValidator(_norm_creatures),
    Hint("Creature types; a specific tag also adds its parent (vampire->undead, devil->fiend)."),
]
EnvironmentList = Annotated[
    list[str],
    BeforeValidator(_norm_environments),
    Hint("Environments: underwater/forest/airborne/darkness/daylight/cold/..."),
]


# ---------------------------------------------------------------------------
# Base + capability mixins. Each form composes only the blocks it can use, so
# combat magnitudes never appear on a ring and AC bonuses never appear on a
# weapon. All forms still serialize into one flat `items` table (union of cols).
# ---------------------------------------------------------------------------
class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class _Item(_Base):
    """Universal fields shared by every form: identity, environments, limits."""

    # Identity
    name: str = Field(min_length=1)
    form: FormField
    slot: SlotField
    rarity: RarityField
    attunement: bool = False

    # Environment (only the "strong in" direction occurs in the data)
    strong_in_environments: EnvironmentList = Field(
        default=[],
        description="Environments where the item is enhanced (underwater/forest/airborne/...).",
    )

    # Limitations — any activated magic item can have these, regardless of form
    charges: int | None = None
    recharge: RechargeField = Recharge.none
    cursed: bool = False
    drawback: str | None = Field(
        default=None, description="One-off drawback not captured structurally."
    )


class _Offense(_Base):
    """Offensive improvements — for forms that deal or boost damage."""

    attack_damage_bonus: int = Field(
        default=0, description="Flat bonus to attack AND damage rolls (always the same value)."
    )
    inflicts_damage_types: DamageList = Field(
        default=[], description="Damage types the item deals/adds on hit."
    )
    effective_against: CreatureList = Field(
        default=[],
        description="Creature types the item is extra effective ATTACKING (extra damage/control).",
    )


class _Defense(_Base):
    """Defensive improvements — for forms that protect the wearer."""

    ac_bonus: int = 0
    resistances: DamageList = Field(
        default=[], description="Damage types taken at half (resistance)."
    )
    damage_immunities: DamageList = Field(
        default=[], description="Damage types taken as zero (immunity)."
    )
    condition_immunities: ConditionList = []
    resistant_against: CreatureList = Field(
        default=[], description="Creature types the item PROTECTS you against."
    )


# ---------------------------------------------------------------------------
# Per-form classes — compose base + the relevant capability blocks, pin slot
# (+ subtype enum where one exists).
# ---------------------------------------------------------------------------
class Weapon(_Item, _Offense):
    form: FormField = Form.weapon
    slot: SlotField = Slot.hand
    subtype: WeaponTypeField = WeaponType.any


class Armor(_Item, _Offense, _Defense):
    form: FormField = Form.armor
    slot: SlotField = Slot.body
    subtype: ArmorTypeField = ArmorType.any


class Shield(_Item, _Defense):
    form: FormField = Form.shield
    slot: SlotField = Slot.off_hand


class Ring(_Item, _Defense):
    form: FormField = Form.ring
    slot: SlotField = Slot.finger


class Amulet(_Item, _Defense):
    form: FormField = Form.amulet
    slot: SlotField = Slot.neck


class Cloak(_Item, _Defense):
    form: FormField = Form.cloak  # cloak or gown
    slot: SlotField = Slot.body


class Footwear(_Item, _Offense):
    form: FormField = Form.boots
    slot: SlotField = Slot.feet


class Headgear(_Item, _Offense, _Defense):
    form: FormField = Form.helm  # helm/mask/crown/headband
    slot: SlotField = Slot.head


class Potion(_Item, _Defense):
    form: FormField = Form.potion
    slot: SlotField = Slot.none


class Wondrous(_Item, _Offense, _Defense):
    form: FormField = Form.wondrous
    slot: SlotField = Slot.none


# ---------------------------------------------------------------------------
# Registry — type-name string -> model class, for generic pipeline discovery.
# ---------------------------------------------------------------------------
REGISTRY: dict[str, type[BaseModel]] = {
    "Weapon": Weapon,
    "Armor": Armor,
    "Shield": Shield,
    "Ring": Ring,
    "Amulet": Amulet,
    "Cloak": Cloak,
    "Footwear": Footwear,
    "Headgear": Headgear,
    "Potion": Potion,
    "Wondrous": Wondrous,
}
