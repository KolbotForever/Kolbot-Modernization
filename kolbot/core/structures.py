"""
Diablo II 1.14d in-memory data structures represented as Python dataclasses.

These mirror the C structs that the game uses internally.  They are populated
by the memory-reading layer and consumed by higher-level game modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, IntFlag


# ===================================================================
# Enums
# ===================================================================

class UnitType(IntEnum):
    PLAYER = 0
    MONSTER = 1
    OBJECT = 2
    MISSILE = 3
    ITEM = 4
    TILE = 5


class PlayerClass(IntEnum):
    AMAZON = 0
    SORCERESS = 1
    NECROMANCER = 2
    PALADIN = 3
    BARBARIAN = 4
    DRUID = 5
    ASSASSIN = 6


class Difficulty(IntEnum):
    NORMAL = 0
    NIGHTMARE = 1
    HELL = 2


class ItemQuality(IntEnum):
    NONE = 0
    INFERIOR = 1
    NORMAL = 2
    SUPERIOR = 3
    MAGIC = 4
    SET = 5
    RARE = 6
    UNIQUE = 7
    CRAFTED = 8


class ItemLocation(IntEnum):
    GROUND = 0
    INVENTORY = 1
    EQUIPPED = 2
    BELT = 3
    CURSOR = 4
    STASH = 5
    CUBE = 6
    SHOP = 7


class ItemFlag(IntFlag):
    IDENTIFIED = 0x00000010
    SOCKETED = 0x00000800
    ETHEREAL = 0x00400000
    RUNEWORD = 0x04000000
    PERSONALIZED = 0x01000000


class PlayerMode(IntEnum):
    DEATH = 0
    STANDING = 1
    WALKING = 2
    RUNNING = 3
    GETTING_HIT = 4
    TOWN_STANDING = 5
    TOWN_WALKING = 6
    ATTACKING1 = 7
    ATTACKING2 = 8
    BLOCKING = 9
    CASTING = 10
    THROWING = 11
    KICKING = 12
    SKILL1 = 13
    SKILL2 = 14
    SKILL3 = 15
    SKILL4 = 16
    DEAD = 17
    SEQUENCE = 18
    KNOCK_BACK = 19


class MonsterMode(IntEnum):
    DEATH = 0
    STANDING = 1
    WALKING = 2
    GETTING_HIT = 3
    ATTACKING1 = 4
    ATTACKING2 = 5
    BLOCKING = 6
    CASTING = 7
    SKILL1 = 8
    SKILL2 = 9
    SKILL3 = 10
    SKILL4 = 11
    DEAD = 12
    KNOCK_BACK = 13
    SEQUENCE = 14
    RUN = 15


# ===================================================================
# Stat IDs (most commonly used)
# ===================================================================

class StatID(IntEnum):
    STRENGTH = 0
    ENERGY = 1
    DEXTERITY = 2
    VITALITY = 3
    STAT_POINTS = 4
    SKILL_POINTS = 5
    HP = 6
    MAX_HP = 7
    MANA = 8
    MAX_MANA = 9
    STAMINA = 10
    MAX_STAMINA = 11
    LEVEL = 12
    EXPERIENCE = 13
    GOLD = 14
    GOLD_BANK = 15  # stash gold
    ENHANCED_DAMAGE = 17
    ENHANCED_DEFENSE = 31
    ATTACK_RATING = 19
    TO_BLOCK = 20
    MIN_DAMAGE = 21
    MAX_DAMAGE = 22
    DEFENSE = 31
    MAGIC_FIND = 80
    GOLD_FIND = 79
    FIRE_RESIST = 39
    COLD_RESIST = 43
    LIGHTNING_RESIST = 41
    POISON_RESIST = 45
    FASTER_CAST_RATE = 105
    FASTER_HIT_RECOVERY = 99
    FASTER_RUN_WALK = 96
    INCREASED_ATTACK_SPEED = 93
    LIFE_LEECH = 60
    MANA_LEECH = 62
    SOCKETS = 194
    SKILL_TAB = 188
    ITEM_ALL_SKILLS = 127
    ITEM_CLASS_SKILLS = 83
    CRUSHING_BLOW = 136
    DEADLY_STRIKE = 141
    OPEN_WOUNDS = 135
    CANNOT_BE_FROZEN = 153


# ===================================================================
# Data structures
# ===================================================================

@dataclass(slots=True)
class Position:
    """Map tile position."""
    x: int = 0
    y: int = 0


@dataclass(slots=True)
class StatEntry:
    """A single stat on a unit."""
    stat_id: int = 0
    layer: int = 0
    value: int = 0


@dataclass(slots=True)
class SkillInfo:
    """Info about one skill on a unit."""
    skill_id: int = 0
    level: int = 0
    charges: int = 0  # -1 if not a charge skill


@dataclass(slots=True)
class UnitAny:
    """Generic representation of any D2 unit (player, monster, item, etc.)."""
    address: int = 0              # memory address of this struct
    unit_type: UnitType = UnitType.PLAYER
    txt_file_no: int = 0          # class id / item code index
    unit_id: int = 0
    mode: int = 0
    act: int = 0
    position: Position = field(default_factory=Position)
    owner_type: int = 0
    owner_id: int = 0
    # Populated lazily depending on unit type:
    stats: list[StatEntry] = field(default_factory=list)
    skills: list[SkillInfo] = field(default_factory=list)
    name: str = ""


@dataclass(slots=True)
class PlayerUnit(UnitAny):
    """Extended player-specific data."""
    player_class: PlayerClass = PlayerClass.AMAZON
    level: int = 1
    hp: int = 0
    max_hp: int = 0
    mana: int = 0
    max_mana: int = 0
    gold: int = 0
    gold_stash: int = 0
    experience: int = 0
    in_town: bool = False


@dataclass(slots=True)
class MonsterUnit(UnitAny):
    """Extended monster-specific data."""
    hp_percent: float = 100.0
    is_unique: bool = False
    is_champion: bool = False
    is_minion: bool = False
    is_dead: bool = False
    enchantments: list[int] = field(default_factory=list)


@dataclass(slots=True)
class ItemUnit(UnitAny):
    """Extended item-specific data."""
    quality: ItemQuality = ItemQuality.NONE
    location: ItemLocation = ItemLocation.GROUND
    level: int = 0  # item level
    item_code: str = ""  # 3-4 char code (e.g. "rin", "amu", "jah")
    sockets: int = 0
    is_identified: bool = False
    is_ethereal: bool = False
    is_runeword: bool = False
    inv_page: int = 0  # 0=inv, 2=cube, 4=stash
    inv_x: int = 0
    inv_y: int = 0


@dataclass(slots=True)
class GameInfo:
    """Current game session info."""
    game_name: str = ""
    game_password: str = ""
    server_ip: str = ""
    difficulty: Difficulty = Difficulty.NORMAL
    area_id: int = 0
    in_game: bool = False
    map_seed: int = 0


@dataclass(slots=True)
class AreaInfo:
    """Info about a game area / level."""
    area_id: int = 0
    name: str = ""
    act: int = 0
    x: int = 0
    y: int = 0
    size_x: int = 0
    size_y: int = 0
    waypoint: bool = False


# ===================================================================
# Packet structures
# ===================================================================

@dataclass(slots=True)
class GamePacket:
    """Raw game packet (client <-> server)."""
    direction: str = "send"    # "send" or "recv"
    packet_id: int = 0
    data: bytes = b""
    timestamp: float = 0.0
