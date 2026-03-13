"""
High-level memory reading layer for Diablo II 1.14d.

Wraps ``ProcessManager`` with game-aware helpers: reading units from hash
tables, resolving stat lists, walking linked lists, etc.
"""

from __future__ import annotations

import time
from typing import Optional

from kolbot.core.offsets import (
    GAME_STATE,
    HASH_TABLE,
    INVENTORY,
    ITEM,
    MAP,
    PATH,
    PLAYER,
    SKILL,
    STAT,
    STAT_LIST,
    UNIT,
)
from kolbot.core.process import ProcessManager
from kolbot.core.structures import (
    AreaInfo,
    Difficulty,
    GameInfo,
    ItemFlag,
    ItemLocation,
    ItemQuality,
    ItemUnit,
    MonsterMode,
    MonsterUnit,
    PlayerClass,
    PlayerUnit,
    Position,
    SkillInfo,
    StatEntry,
    StatID,
    UnitAny,
    UnitType,
)
from kolbot.utils.logger import get_logger

log = get_logger("core.memory")


class GameMemoryReader:
    """
    Reads Diablo II game state from process memory.

    This is the primary interface between raw memory and the rest of the bot.
    All game-state queries should go through this class.

    Usage::

        pm = ProcessManager()
        pm.attach()
        reader = GameMemoryReader(pm)
        player = reader.get_player_unit()
        items = reader.get_ground_items()
    """

    def __init__(self, process: ProcessManager) -> None:
        self._pm = process

    @property
    def pm(self) -> ProcessManager:
        return self._pm

    # ------------------------------------------------------------------
    # Game state
    # ------------------------------------------------------------------

    def is_in_game(self) -> bool:
        """Check if the player is currently in a game (not in lobby/menu)."""
        try:
            val = self._pm.read_game_uint(GAME_STATE.in_game)
            return val != 0
        except OSError:
            return False

    def get_difficulty(self) -> Difficulty:
        try:
            val = self._pm.read_game_uint(GAME_STATE.difficulty)
            return Difficulty(val)
        except (OSError, ValueError):
            return Difficulty.NORMAL

    def get_game_info(self) -> GameInfo:
        """Read current game session info."""
        info = GameInfo()
        info.in_game = self.is_in_game()
        info.difficulty = self.get_difficulty()

        try:
            p_info = self._pm.read_game_pointer(GAME_STATE.p_game_info)
            if p_info:
                info.game_name = self._pm.read_string(p_info + 0x00, 16)
                info.game_password = self._pm.read_string(p_info + 0x18, 16)
                info.server_ip = self._pm.read_string(p_info + 0x30, 16)
        except OSError:
            pass

        return info

    # ------------------------------------------------------------------
    # UI flags
    # ------------------------------------------------------------------

    def is_ui_open(self, flag_index: int) -> bool:
        """Check if a UI panel is open (inventory, stash, etc.)."""
        try:
            addr = self._pm.addr(GAME_STATE.ui_flags) + flag_index * 4
            return self._pm.read_uint(addr) != 0
        except OSError:
            return False

    # ------------------------------------------------------------------
    # Player unit
    # ------------------------------------------------------------------

    def get_player_unit_address(self) -> int:
        """Get the address of the local player's UnitAny struct."""
        try:
            return self._pm.read_game_pointer(PLAYER.p_player_unit)
        except OSError:
            return 0

    def get_player_unit(self) -> Optional[PlayerUnit]:
        """Read the full local player unit."""
        addr = self.get_player_unit_address()
        if not addr:
            return None

        try:
            pu = PlayerUnit()
            pu.address = addr
            pu.unit_type = UnitType.PLAYER
            pu.txt_file_no = self._pm.read_uint(addr + UNIT.txt_file_no)
            pu.unit_id = self._pm.read_uint(addr + UNIT.unit_id)
            pu.mode = self._pm.read_uint(addr + UNIT.mode)
            pu.act = self._pm.read_uint(addr + UNIT.act)

            # Player class
            try:
                pu.player_class = PlayerClass(pu.txt_file_no)
            except ValueError:
                pu.player_class = PlayerClass.AMAZON

            # Name from PlayerData
            p_data = self._pm.read_pointer(addr + UNIT.p_unit_data)
            if p_data:
                pu.name = self._pm.read_string(p_data, 16)

            # Position from Path
            p_path = self._pm.read_pointer(addr + UNIT.p_path)
            if p_path:
                pu.position = Position(
                    x=self._pm.read_word(p_path + PATH.x_pos),
                    y=self._pm.read_word(p_path + PATH.y_pos),
                )

            # Stats
            stats = self._read_stat_list(addr)
            pu.stats = stats
            for s in stats:
                match s.stat_id:
                    case StatID.HP:
                        pu.hp = s.value >> 8  # D2 stores HP * 256
                    case StatID.MAX_HP:
                        pu.max_hp = s.value >> 8
                    case StatID.MANA:
                        pu.mana = s.value >> 8
                    case StatID.MAX_MANA:
                        pu.max_mana = s.value >> 8
                    case StatID.LEVEL:
                        pu.level = s.value
                    case StatID.EXPERIENCE:
                        pu.experience = s.value
                    case StatID.GOLD:
                        pu.gold = s.value
                    case StatID.GOLD_BANK:
                        pu.gold_stash = s.value

            # In town heuristic (mode 5 or 6 = town standing/walking)
            pu.in_town = pu.mode in (5, 6)

            # Skills
            pu.skills = self._read_skills(addr)

            return pu
        except OSError as e:
            log.warning("Failed to read player unit: %s", e)
            return None

    # ------------------------------------------------------------------
    # Monsters
    # ------------------------------------------------------------------

    def get_monsters(self) -> list[MonsterUnit]:
        """Read all monster units from the unit hash table."""
        monsters: list[MonsterUnit] = []
        base = self._pm.addr(HASH_TABLE.monster)

        for i in range(HASH_TABLE.table_size):
            try:
                p_unit = self._pm.read_uint(base + i * 4)
            except OSError:
                continue

            while p_unit:
                try:
                    mu = self._read_monster_unit(p_unit)
                    if mu:
                        monsters.append(mu)
                    p_unit = self._pm.read_uint(p_unit + UNIT.p_next_unit)
                except OSError:
                    break

        return monsters

    def _read_monster_unit(self, addr: int) -> Optional[MonsterUnit]:
        try:
            unit_type = self._pm.read_uint(addr + UNIT.unit_type)
            if unit_type != UnitType.MONSTER:
                return None

            mu = MonsterUnit()
            mu.address = addr
            mu.unit_type = UnitType.MONSTER
            mu.txt_file_no = self._pm.read_uint(addr + UNIT.txt_file_no)
            mu.unit_id = self._pm.read_uint(addr + UNIT.unit_id)
            mu.mode = self._pm.read_uint(addr + UNIT.mode)
            mu.act = self._pm.read_uint(addr + UNIT.act)

            # Position
            p_path = self._pm.read_pointer(addr + UNIT.p_path)
            if p_path:
                mu.position = Position(
                    x=self._pm.read_word(p_path + PATH.x_pos),
                    y=self._pm.read_word(p_path + PATH.y_pos),
                )

            # Dead check
            mu.is_dead = mu.mode in (MonsterMode.DEATH, MonsterMode.DEAD)

            # Monster data flags (unique/champion/minion)
            p_data = self._pm.read_pointer(addr + UNIT.p_unit_data)
            if p_data:
                flags = self._pm.read_uint(p_data + 0x18)
                mu.is_unique = bool(flags & 0x02)
                mu.is_champion = bool(flags & 0x04)
                mu.is_minion = bool(flags & 0x08)

                # Enchantment array (up to 9 enchants at offset 0x1C)
                for j in range(9):
                    ench = self._pm.read_byte(p_data + 0x1C + j)
                    if ench:
                        mu.enchantments.append(ench)

            # HP percent from stats
            stats = self._read_stat_list(addr)
            mu.stats = stats
            hp = 0
            max_hp = 1
            for s in stats:
                if s.stat_id == StatID.HP:
                    hp = s.value >> 8
                elif s.stat_id == StatID.MAX_HP:
                    max_hp = max(s.value >> 8, 1)
            mu.hp_percent = (hp / max_hp) * 100.0

            return mu
        except OSError:
            return None

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------

    def get_ground_items(self) -> list[ItemUnit]:
        """Read all items on the ground from the unit hash table."""
        items: list[ItemUnit] = []
        base = self._pm.addr(HASH_TABLE.item)

        for i in range(HASH_TABLE.table_size):
            try:
                p_unit = self._pm.read_uint(base + i * 4)
            except OSError:
                continue

            while p_unit:
                try:
                    iu = self._read_item_unit(p_unit)
                    if iu and iu.location == ItemLocation.GROUND:
                        items.append(iu)
                    p_unit = self._pm.read_uint(p_unit + UNIT.p_next_unit)
                except OSError:
                    break

        return items

    def get_inventory_items(self) -> list[ItemUnit]:
        """Read all items in the player's inventory/stash/cube."""
        player_addr = self.get_player_unit_address()
        if not player_addr:
            return []

        items: list[ItemUnit] = []
        try:
            p_inv = self._pm.read_pointer(player_addr + UNIT.p_inventory)
            if not p_inv:
                return []

            p_item = self._pm.read_pointer(p_inv + INVENTORY.p_first_item)
            visited: set[int] = set()

            while p_item and p_item not in visited:
                visited.add(p_item)
                iu = self._read_item_unit(p_item)
                if iu:
                    items.append(iu)
                try:
                    p_item = self._pm.read_uint(p_item + UNIT.p_next_unit)
                except OSError:
                    break
        except OSError:
            pass

        return items

    def get_all_items(self) -> list[ItemUnit]:
        """Read every item from the hash table (ground + inventory + all)."""
        items: list[ItemUnit] = []
        base = self._pm.addr(HASH_TABLE.item)

        for i in range(HASH_TABLE.table_size):
            try:
                p_unit = self._pm.read_uint(base + i * 4)
            except OSError:
                continue

            while p_unit:
                try:
                    iu = self._read_item_unit(p_unit)
                    if iu:
                        items.append(iu)
                    p_unit = self._pm.read_uint(p_unit + UNIT.p_next_unit)
                except OSError:
                    break

        return items

    def _read_item_unit(self, addr: int) -> Optional[ItemUnit]:
        try:
            unit_type = self._pm.read_uint(addr + UNIT.unit_type)
            if unit_type != UnitType.ITEM:
                return None

            iu = ItemUnit()
            iu.address = addr
            iu.unit_type = UnitType.ITEM
            iu.txt_file_no = self._pm.read_uint(addr + UNIT.txt_file_no)
            iu.unit_id = self._pm.read_uint(addr + UNIT.unit_id)
            iu.mode = self._pm.read_uint(addr + UNIT.mode)

            # Position
            p_path = self._pm.read_pointer(addr + UNIT.p_path)
            if p_path:
                iu.position = Position(
                    x=self._pm.read_word(p_path + PATH.x_pos),
                    y=self._pm.read_word(p_path + PATH.y_pos),
                )

            # Item data
            p_data = self._pm.read_pointer(addr + UNIT.p_unit_data)
            if p_data:
                quality_raw = self._pm.read_uint(p_data + ITEM.quality)
                try:
                    iu.quality = ItemQuality(quality_raw)
                except ValueError:
                    iu.quality = ItemQuality.NONE

                flags = self._pm.read_uint(p_data + ITEM.item_flags)
                iu.is_identified = bool(flags & ItemFlag.IDENTIFIED)
                iu.is_ethereal = bool(flags & ItemFlag.ETHEREAL)
                iu.is_runeword = bool(flags & ItemFlag.RUNEWORD)

                iu.inv_page = self._pm.read_uint(p_data + ITEM.node_page)

            # Determine location from mode / inv_page
            if iu.mode == 3 or iu.mode == 5:
                iu.location = ItemLocation.GROUND
            elif iu.inv_page == 0:
                iu.location = ItemLocation.INVENTORY
            elif iu.inv_page == 2:
                iu.location = ItemLocation.CUBE
            elif iu.inv_page == 4:
                iu.location = ItemLocation.STASH
            elif iu.inv_page == 1:
                iu.location = ItemLocation.EQUIPPED
            elif iu.inv_page == 3:
                iu.location = ItemLocation.BELT

            # Stats
            stats = self._read_stat_list(addr)
            iu.stats = stats
            for s in stats:
                if s.stat_id == StatID.SOCKETS:
                    iu.sockets = s.value
                elif s.stat_id == StatID.LEVEL:
                    iu.level = s.value

            return iu
        except OSError:
            return None

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def _read_stat_list(self, unit_addr: int) -> list[StatEntry]:
        """Read the stat list from a unit."""
        stats: list[StatEntry] = []
        try:
            p_stat_list = self._pm.read_pointer(unit_addr + UNIT.p_stat_list)
            if not p_stat_list:
                return stats

            # Read full stats (includes bonuses from items/skills)
            p_stats = self._pm.read_pointer(p_stat_list + STAT_LIST.p_full_stat)
            count = self._pm.read_word(p_stat_list + STAT_LIST.full_stat_count)

            if not p_stats or count == 0:
                # Fall back to base stats
                p_stats = self._pm.read_pointer(p_stat_list + STAT_LIST.p_stat)
                count = self._pm.read_word(p_stat_list + STAT_LIST.stat_count)

            if not p_stats or count == 0:
                return stats

            # Each stat entry is 8 bytes: DWORD(layer<<16|statId) + DWORD(value)
            for i in range(min(count, 512)):  # safety cap
                entry_addr = p_stats + i * 8
                id_layer = self._pm.read_uint(entry_addr + STAT.stat_id_layer)
                value = self._pm.read_int(entry_addr + STAT.value)
                stat_id = id_layer & 0xFFFF
                layer = (id_layer >> 16) & 0xFFFF
                stats.append(StatEntry(stat_id=stat_id, layer=layer, value=value))

        except OSError:
            pass
        return stats

    def get_stat(self, unit_addr: int, stat_id: int, layer: int = 0) -> int:
        """Get a specific stat value from a unit. Returns 0 if not found."""
        for s in self._read_stat_list(unit_addr):
            if s.stat_id == stat_id and s.layer == layer:
                return s.value
        return 0

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------

    def _read_skills(self, unit_addr: int) -> list[SkillInfo]:
        """Read all skills from a unit's skill list."""
        skills: list[SkillInfo] = []
        try:
            p_skill_struct = self._pm.read_pointer(unit_addr + UNIT.p_skill)
            if not p_skill_struct:
                return skills

            p_skill = self._pm.read_pointer(p_skill_struct + SKILL.p_first_skill)
            visited: set[int] = set()

            while p_skill and p_skill not in visited:
                visited.add(p_skill)
                p_txt = self._pm.read_pointer(p_skill + SKILL.p_skill_txt)
                if p_txt:
                    skill_id = self._pm.read_word(p_txt)
                    level = self._pm.read_uint(p_skill + SKILL.skill_level)
                    skills.append(SkillInfo(skill_id=skill_id, level=level))
                p_skill = self._pm.read_pointer(p_skill + SKILL.p_next_skill)

        except OSError:
            pass
        return skills

    # ------------------------------------------------------------------
    # Area / Map
    # ------------------------------------------------------------------

    def get_current_area_id(self) -> int:
        """Get the area ID of the player's current location."""
        player_addr = self.get_player_unit_address()
        if not player_addr:
            return 0
        try:
            p_path = self._pm.read_pointer(player_addr + UNIT.p_path)
            if not p_path:
                return 0
            p_room1 = self._pm.read_pointer(p_path + PATH.p_room1)
            if not p_room1:
                return 0
            p_room2 = self._pm.read_pointer(p_room1 + 0x14)  # Room1 -> Room2
            if not p_room2:
                return 0
            p_level = self._pm.read_pointer(p_room2 + 0x90)  # Room2 -> Level
            if not p_level:
                return 0
            return self._pm.read_uint(p_level + MAP.level_id)
        except OSError:
            return 0

    def get_area_info(self, area_id: int) -> Optional[AreaInfo]:
        """Read area info for a specific area ID by walking the level list."""
        player_addr = self.get_player_unit_address()
        if not player_addr:
            return None
        try:
            p_act = self._pm.read_pointer(player_addr + UNIT.p_act)
            if not p_act:
                return None
            p_misc = self._pm.read_pointer(p_act + MAP.p_act_misc)
            if not p_misc:
                return None
            p_level = self._pm.read_pointer(p_misc + MAP.p_level_first)

            visited: set[int] = set()
            while p_level and p_level not in visited:
                visited.add(p_level)
                lid = self._pm.read_uint(p_level + MAP.level_id)
                if lid == area_id:
                    ai = AreaInfo(area_id=lid)
                    ai.x = self._pm.read_uint(p_level + MAP.level_x)
                    ai.y = self._pm.read_uint(p_level + MAP.level_y)
                    ai.size_x = self._pm.read_uint(p_level + MAP.level_sx)
                    ai.size_y = self._pm.read_uint(p_level + MAP.level_sy)
                    return ai
                p_level = self._pm.read_pointer(p_level + MAP.p_level_next)
        except OSError:
            pass
        return None

    # ------------------------------------------------------------------
    # Misc units (objects, tiles)
    # ------------------------------------------------------------------

    def get_objects(self) -> list[UnitAny]:
        """Read all object units (waypoints, shrines, chests, etc.)."""
        objects: list[UnitAny] = []
        base = self._pm.addr(HASH_TABLE.object_)

        for i in range(HASH_TABLE.table_size):
            try:
                p_unit = self._pm.read_uint(base + i * 4)
            except OSError:
                continue

            while p_unit:
                try:
                    unit_type = self._pm.read_uint(p_unit + UNIT.unit_type)
                    if unit_type == UnitType.OBJECT:
                        obj = UnitAny()
                        obj.address = p_unit
                        obj.unit_type = UnitType.OBJECT
                        obj.txt_file_no = self._pm.read_uint(p_unit + UNIT.txt_file_no)
                        obj.unit_id = self._pm.read_uint(p_unit + UNIT.unit_id)
                        obj.mode = self._pm.read_uint(p_unit + UNIT.mode)
                        p_path = self._pm.read_pointer(p_unit + UNIT.p_path)
                        if p_path:
                            obj.position = Position(
                                x=self._pm.read_word(p_path + PATH.x_pos),
                                y=self._pm.read_word(p_path + PATH.y_pos),
                            )
                        objects.append(obj)
                    p_unit = self._pm.read_uint(p_unit + UNIT.p_next_unit)
                except OSError:
                    break

        return objects
