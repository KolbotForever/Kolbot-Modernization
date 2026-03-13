"""
Diablo II Lord of Destruction 1.14d Memory Offsets & Addresses.

In 1.14d all DLLs were merged into Game.exe, so every offset is relative
to the Game.exe base address.  The offsets below are derived from publicly
available community research (D2BS source, MapHack projects, Kolbot forums).

IMPORTANT:  These offsets are for the **unpatched** 1.14d Game.exe
(SHA-1 starts with 0x1F...).  If Blizzard ever hot-patches the binary
they may shift — use the pattern-scan fallback in ``memory.py``.
"""

from __future__ import annotations
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Base module name
# ---------------------------------------------------------------------------
GAME_EXE = "Game.exe"

# ---------------------------------------------------------------------------
# Player / Unit pointers
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlayerOffsets:
    """Offsets for the local player unit."""
    # Pointer to the player unit struct (UnitAny*)
    p_player_unit: int = 0x3A6A70
    # Unit hash table for player type (type=0)
    unit_table_player: int = 0x3A5E70
    # Expansion flag
    expansion_flag: int = 0x3A04FC


@dataclass(frozen=True, slots=True)
class UnitOffsets:
    """Offsets within a UnitAny structure."""
    unit_type: int = 0x00        # DWORD  (0=Player, 1=Monster, 2=Object, 4=Item)
    txt_file_no: int = 0x04      # DWORD  class/txtFileNo
    unit_id: int = 0x08          # DWORD  unique unit ID
    mode: int = 0x0C             # DWORD  animation mode
    p_unit_data: int = 0x10      # void*  -> PlayerData / MonsterData / ItemData
    act: int = 0x14              # DWORD  act number (0-4)
    p_act: int = 0x18            # Act*
    seed: int = 0x2C             # DWORD[2]  unit seed
    p_path: int = 0x38           # Path*
    p_stat_list: int = 0x5C      # StatListEx*
    p_inventory: int = 0x60      # Inventory*
    p_skill: int = 0x84          # Skill*
    owner_type: int = 0xA4       # DWORD
    owner_id: int = 0xA8         # DWORD
    p_next_unit: int = 0xE8      # UnitAny*  linked list next


@dataclass(frozen=True, slots=True)
class PathOffsets:
    """Offsets within a Path structure."""
    x_offset: int = 0x00         # WORD  sub-tile X
    x_pos: int = 0x02            # WORD  tile X
    y_offset: int = 0x04         # WORD  sub-tile Y
    y_pos: int = 0x06            # WORD  tile Y
    target_x: int = 0x08         # WORD
    target_y: int = 0x0C         # WORD
    p_room1: int = 0x1C          # Room1*


@dataclass(frozen=True, slots=True)
class StatListOffsets:
    """Offsets within a StatListEx / StatList structure."""
    p_stat: int = 0x48           # Stat*  base stats array
    stat_count: int = 0x4C       # WORD   base stats count
    p_full_stat: int = 0x80      # Stat*  full stats array
    full_stat_count: int = 0x84  # WORD   full stat count


@dataclass(frozen=True, slots=True)
class StatOffsets:
    """Layout of a single Stat entry (layer+id packed DWORD + value DWORD)."""
    stat_id_layer: int = 0x00    # DWORD (lo-word=statId, hi-word=layer)
    value: int = 0x04            # DWORD


# ---------------------------------------------------------------------------
# Item offsets
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ItemOffsets:
    """Offsets for item-specific data (inside UnitData for type=4)."""
    quality: int = 0x00          # DWORD  item quality
    node_page: int = 0x84        # DWORD  0=inv, 1=equip, 2=belt, 3=ground, 5=stash, ...
    item_flags: int = 0x18       # DWORD  identified/ethereal/socketed etc.


@dataclass(frozen=True, slots=True)
class InventoryOffsets:
    """Offsets within the Inventory structure."""
    p_first_item: int = 0x30     # UnitAny*  first item in inventory
    p_owner: int = 0x0C          # UnitAny*  unit that owns this inventory


# ---------------------------------------------------------------------------
# Game state / UI
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class GameStateOffsets:
    """Global game state pointers."""
    # In-game flag (DWORD, non-zero when inside a game)
    in_game: int = 0x3A27E8
    # Game info struct pointer (contains game name, password, ip)
    p_game_info: int = 0x3A0438
    # UI flags array (each DWORD is a UI panel open/closed flag)
    ui_flags: int = 0x3A6BE0
    # Automap flag
    automap_on: int = 0x3A27EC
    # Difficulty (0=Normal, 1=NM, 2=Hell)
    difficulty: int = 0x3A04CC
    # FPS target
    fps: int = 0x3BB390


@dataclass(frozen=True, slots=True)
class UIFlagIndex:
    """Indices into the UI flags array."""
    inventory: int = 0x01
    character: int = 0x02
    skill_tree: int = 0x04
    quest_log: int = 0x08
    waypoint: int = 0x09
    stash: int = 0x0C
    chat: int = 0x11
    npc_menu: int = 0x12
    npc_shop: int = 0x14
    esc_menu: int = 0x17
    automap: int = 0x19
    cube: int = 0x1A
    belt: int = 0x1F


# ---------------------------------------------------------------------------
# Map / Area
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MapOffsets:
    """Offsets for map/area data."""
    p_act_misc: int = 0x78       # offset within Act struct -> ActMisc*
    p_level_first: int = 0x78    # ActMisc -> Level* linked list
    # Level struct offsets
    level_id: int = 0x1D0        # DWORD area id
    level_x: int = 0x1D4         # DWORD
    level_y: int = 0x1D8         # DWORD
    level_sx: int = 0x1DC        # DWORD  size x
    level_sy: int = 0x1E0        # DWORD  size y
    p_room2_first: int = 0x1F8   # Room2* linked list
    p_level_next: int = 0x230    # Level*


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SkillOffsets:
    """Offsets within the Skill/SkillInfo structures."""
    p_first_skill: int = 0x00    # Skill* inside SkillList
    skill_id: int = 0x08         # WORD in Skill -> SkillTxt -> skillId
    p_skill_txt: int = 0x04      # SkillTxt*
    skill_level: int = 0x24      # DWORD
    p_next_skill: int = 0x28     # Skill*  linked list


# ---------------------------------------------------------------------------
# Network / Packets
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PacketOffsets:
    """Addresses for packet send/receive hooks."""
    # SendPacket function address (client -> server)
    send_packet: int = 0x12AE62
    # RecvPacket handler table (server -> client)
    recv_handler_table: int = 0x3C0728
    # Game socket pointer
    p_game_socket: int = 0x3A0490


# ---------------------------------------------------------------------------
# Unit hash tables (one per unit type, 128 entries each)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class UnitHashTableOffsets:
    """Base addresses of the 128-entry unit hash tables per type."""
    table_size: int = 128
    player: int = 0x3A5E70       # type 0
    monster: int = 0x3A5E70 + 0x200   # type 1  (offset by 128*4)
    object_: int = 0x3A5E70 + 0x400   # type 2
    missile: int = 0x3A5E70 + 0x600   # type 3
    item: int = 0x3A5E70 + 0x800     # type 4


# ---------------------------------------------------------------------------
# Singleton offset collections
# ---------------------------------------------------------------------------

PLAYER = PlayerOffsets()
UNIT = UnitOffsets()
PATH = PathOffsets()
STAT_LIST = StatListOffsets()
STAT = StatOffsets()
ITEM = ItemOffsets()
INVENTORY = InventoryOffsets()
GAME_STATE = GameStateOffsets()
UI_FLAG = UIFlagIndex()
MAP = MapOffsets()
SKILL = SkillOffsets()
PACKET = PacketOffsets()
HASH_TABLE = UnitHashTableOffsets()
