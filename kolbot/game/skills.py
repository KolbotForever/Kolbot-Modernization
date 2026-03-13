"""
Skill database and management.

Maps skill IDs to names, provides skill tree lookups, and manages
the player's active skill selection.
"""

from __future__ import annotations

import json
from enum import IntEnum
from pathlib import Path
from typing import Optional

from kolbot.utils.logger import get_logger

log = get_logger("game.skills")


# ===================================================================
# Common skill IDs (most frequently used by bots)
# ===================================================================

class SkillID(IntEnum):
    """Well-known skill identifiers."""
    # --- Amazon ---
    MAGIC_ARROW = 6
    MULTIPLE_SHOT = 12
    GUIDED_ARROW = 22
    STRAFE = 26
    LIGHTNING_FURY = 35
    VALKYRIE = 32

    # --- Sorceress ---
    FIRE_BOLT = 36
    WARMTH = 37
    INFERNO = 39
    BLAZE = 43
    FIRE_BALL = 47
    FIRE_WALL = 51
    ENCHANT = 52
    METEOR = 56
    FIRE_MASTERY = 61
    HYDRA = 62
    ICE_BOLT = 39
    FROZEN_ARMOR = 40
    FROST_NOVA = 44
    ICE_BLAST = 45
    SHIVER_ARMOR = 48
    GLACIAL_SPIKE = 49
    BLIZZARD = 59
    CHILLING_ARMOR = 55
    FROZEN_ORB = 64
    COLD_MASTERY = 63
    CHARGED_BOLT = 38
    STATIC_FIELD = 42
    TELEKINESIS = 43
    NOVA = 48
    LIGHTNING = 53
    CHAIN_LIGHTNING = 49
    TELEPORT = 54
    THUNDER_STORM = 57
    ENERGY_SHIELD = 58
    LIGHTNING_MASTERY = 60

    # --- Necromancer ---
    TEETH = 67
    BONE_ARMOR = 68
    BONE_SPEAR = 84
    BONE_SPIRIT = 93
    BONE_WALL = 74
    BONE_PRISON = 90
    CORPSE_EXPLOSION = 74
    POISON_NOVA = 92
    LOWER_RESIST = 91
    AMPLIFY_DAMAGE = 66
    DECREPIFY = 87
    LIFE_TAP = 82
    ATTRACT = 89
    DIM_VISION = 72
    CONFUSE = 88
    RAISE_SKELETON = 70
    SKELETON_MASTERY = 69
    CLAY_GOLEM = 75
    GOLEM_MASTERY = 81
    SUMMON_RESIST = 85
    RAISE_SKELETAL_MAGE = 80
    BLOOD_GOLEM = 77
    IRON_GOLEM = 86
    FIRE_GOLEM = 94
    REVIVE = 95

    # --- Paladin ---
    SACRIFICE = 96
    SMITE = 97
    HOLY_BOLT = 101
    ZEAL = 106
    CHARGE = 107
    VENGEANCE = 112
    BLESSED_HAMMER = 112
    HOLY_SHIELD = 117
    FIST_OF_THE_HEAVENS = 121
    MIGHT = 98
    HOLY_FIRE = 102
    THORNS = 99
    DEFIANCE = 104
    BLESSED_AIM = 108
    CLEANSING = 109
    HOLY_FREEZE = 114
    HOLY_SHOCK = 118
    SANCTUARY = 119
    FANATICISM = 122
    CONVICTION = 123
    REDEMPTION = 124
    SALVATION = 125
    MEDITATION = 120

    # --- Barbarian ---
    BASH = 126
    LEAP = 132
    DOUBLE_SWING = 127
    STUN = 128
    DOUBLE_THROW = 133
    LEAP_ATTACK = 138
    CONCENTRATE = 131
    FRENZY = 147
    WHIRLWIND = 151
    BERSERK = 152
    HOWL = 130
    FIND_POTION = 134
    TAUNT = 129
    SHOUT = 138
    FIND_ITEM = 142
    BATTLE_CRY = 146
    BATTLE_ORDERS = 149
    GRIM_WARD = 148
    WAR_CRY = 150
    BATTLE_COMMAND = 155

    # --- Druid ---
    FIRESTORM = 225
    MOLTEN_BOULDER = 226
    FISSURE = 228
    VOLCANO = 230
    ARMAGEDDON = 232
    ARCTIC_BLAST = 233
    CYCLONE_ARMOR = 235
    TWISTER = 234
    TORNADO = 240
    HURRICANE = 245
    OAK_SAGE = 226
    HEART_OF_WOLVERINE = 236
    SPIRIT_OF_BARBS = 246

    # --- Assassin ---
    FIRE_BLAST = 251
    SHOCK_WEB = 256
    BLADE_SENTINEL = 252
    CHARGED_BOLT_SENTRY = 261
    WAKE_OF_FIRE = 258
    LIGHTNING_SENTRY = 271
    DEATH_SENTRY = 276
    BLADE_FURY = 272
    BLADE_SHIELD = 277
    BURST_OF_SPEED = 258
    CLOAK_OF_SHADOWS = 264
    FADE = 267
    SHADOW_WARRIOR = 268
    SHADOW_MASTER = 279
    MIND_BLAST = 273
    DRAGON_TALON = 252
    DRAGON_CLAW = 259
    DRAGON_TAIL = 270
    DRAGON_FLIGHT = 278


# ===================================================================
# Skill database
# ===================================================================

_SKILL_DB: dict[int, dict] = {}
_DB_LOADED = False


def _load_skill_db() -> None:
    global _SKILL_DB, _DB_LOADED
    if _DB_LOADED:
        return
    db_path = Path(__file__).resolve().parents[2] / "data" / "skills.json"
    if db_path.exists():
        with open(db_path, encoding="utf-8") as f:
            raw = json.load(f)
        for entry in raw:
            _SKILL_DB[entry["id"]] = entry
    _DB_LOADED = True


def get_skill_name(skill_id: int) -> str:
    _load_skill_db()
    info = _SKILL_DB.get(skill_id, {})
    return info.get("name", f"Skill({skill_id})")


def get_skill_info(skill_id: int) -> dict:
    _load_skill_db()
    return _SKILL_DB.get(skill_id, {})


def is_attack_skill(skill_id: int) -> bool:
    _load_skill_db()
    info = _SKILL_DB.get(skill_id, {})
    return info.get("is_attack", False)


def get_skill_mana_cost(skill_id: int, level: int) -> int:
    """Approximate mana cost for a skill at a given level."""
    _load_skill_db()
    info = _SKILL_DB.get(skill_id, {})
    base = info.get("mana_cost", 0)
    per_level = info.get("mana_per_level", 0)
    return max(0, base + per_level * (level - 1))
