"""
Script API — Kolbot-compatible function library.

Exposes a set of global functions and objects that mirror the original
Kolbot/D2BS scripting API.  Both native Python scripts and transpiled
.dbj scripts call through this layer.

The API object is injected into script namespaces so scripts can call
e.g. ``me.x``, ``getUnit()``, ``clickItem()``, etc.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Optional

from kolbot.core.structures import (
    ItemQuality,
    ItemUnit,
    MonsterUnit,
    PlayerUnit,
    Position,
    StatID,
    UnitType,
)
from kolbot.game.items import ItemClassifier as IC, get_item_name
from kolbot.game.map import Area, get_area_name, is_town
from kolbot.game.skills import SkillID, get_skill_name
from kolbot.utils.logger import get_logger

if TYPE_CHECKING:
    from kolbot.core.game_state import GameStateTracker
    from kolbot.core.memory import GameMemoryReader
    from kolbot.core.packets import PacketSender
    from kolbot.game.belt import BeltManager
    from kolbot.game.inventory import InventoryManager
    from kolbot.game.player import Player
    from kolbot.game.mercenary import Mercenary
    from kolbot.game.monsters import MonsterTracker
    from kolbot.game.npcs import NPCManager
    from kolbot.bot.pickit import PickitEngine

log = get_logger("scripts.api")


# ===================================================================
# "me" object — mirrors D2BS `me` global
# ===================================================================

class MeProxy:
    """
    Proxy for the local player, compatible with D2BS ``me`` object.

    Attributes like ``me.x``, ``me.hp``, ``me.charlvl`` etc. are
    resolved dynamically from the game state snapshot.
    """

    def __init__(self, tracker: "GameStateTracker", player: "Player") -> None:
        self._tracker = tracker
        self._player = player

    def _pu(self) -> Optional[PlayerUnit]:
        return self._tracker.snapshot.player

    @property
    def x(self) -> int:
        pu = self._pu()
        return pu.position.x if pu else 0

    @property
    def y(self) -> int:
        pu = self._pu()
        return pu.position.y if pu else 0

    @property
    def area(self) -> int:
        return self._tracker.snapshot.area_id

    @property
    def hp(self) -> int:
        pu = self._pu()
        return pu.hp if pu else 0

    @property
    def hpmax(self) -> int:
        pu = self._pu()
        return pu.max_hp if pu else 1

    @property
    def mp(self) -> int:
        pu = self._pu()
        return pu.mana if pu else 0

    @property
    def mpmax(self) -> int:
        pu = self._pu()
        return pu.max_mana if pu else 1

    @property
    def charlvl(self) -> int:
        pu = self._pu()
        return pu.level if pu else 0

    @property
    def classid(self) -> int:
        pu = self._pu()
        return pu.player_class.value if pu else 0

    @property
    def name(self) -> str:
        pu = self._pu()
        return pu.name if pu else ""

    @property
    def gold(self) -> int:
        pu = self._pu()
        return pu.gold if pu else 0

    @property
    def goldbank(self) -> int:
        pu = self._pu()
        return pu.gold_stash if pu else 0

    @property
    def intown(self) -> bool:
        return is_town(self.area)

    @property
    def dead(self) -> bool:
        return self._player.is_dead

    @property
    def act(self) -> int:
        from kolbot.game.map import get_act
        return get_act(self.area)

    @property
    def diff(self) -> int:
        return self._tracker.snapshot.difficulty.value

    @property
    def mode(self) -> int:
        pu = self._pu()
        return pu.mode if pu else 0

    def getSkill(self, skill_id: int) -> int:
        """Get skill level by ID (mirrors me.getSkill in D2BS)."""
        return self._player.get_skill_level(skill_id)

    def getStat(self, stat_id: int) -> int:
        """Get a player stat (mirrors me.getStat in D2BS)."""
        pu = self._pu()
        if not pu:
            return 0
        for s in pu.stats:
            if s.stat_id == stat_id:
                # HP/Mana are stored *256 in D2
                if stat_id in (StatID.HP, StatID.MAX_HP, StatID.MANA, StatID.MAX_MANA):
                    return s.value >> 8
                return s.value
        return 0

    def overhead(self, msg: str) -> None:
        """Display overhead message (not implemented — log only)."""
        log.info("[overhead] %s", msg)


# ===================================================================
# Script API context
# ===================================================================

class ScriptAPI:
    """
    The full scripting API injected into script execution contexts.

    Provides all top-level functions that Kolbot scripts expect:
    ``getUnit``, ``clickMap``, ``delay``, ``print``, ``say``, etc.
    """

    def __init__(
        self,
        tracker: "GameStateTracker",
        reader: "GameMemoryReader",
        sender: "PacketSender",
        player: "Player",
        inventory: "InventoryManager",
        belt: "BeltManager",
        merc: "Mercenary",
        npcs: "NPCManager",
        monster_tracker: "MonsterTracker",
        pickit: "PickitEngine",
    ) -> None:
        self._tracker = tracker
        self._reader = reader
        self._sender = sender
        self._player = player
        self._inventory = inventory
        self._belt = belt
        self._merc = merc
        self._npcs = npcs
        self._monsters = monster_tracker
        self._pickit = pickit

        # The `me` proxy
        self.me = MeProxy(tracker, player)

    # ------------------------------------------------------------------
    # Unit discovery (mirrors D2BS getUnit)
    # ------------------------------------------------------------------

    def getUnit(self, unit_type: int = -1, name_or_id: Any = None) -> Optional[Any]:
        """
        Find a unit by type and name/classId.

        unit_type: 0=player, 1=monster, 2=object, 4=item, -1=any
        name_or_id: txtFileNo (int) or name (str)
        """
        snap = self._tracker.snapshot

        if unit_type in (0, -1) and snap.player:
            if name_or_id is None or snap.player.name == name_or_id:
                return snap.player

        if unit_type in (1, -1):
            for m in snap.monsters:
                if name_or_id is None:
                    return m
                if isinstance(name_or_id, int) and m.txt_file_no == name_or_id:
                    return m

        if unit_type in (4, -1):
            for item in snap.ground_items + snap.inventory_items:
                if name_or_id is None:
                    return item
                if isinstance(name_or_id, int) and item.txt_file_no == name_or_id:
                    return item

        if unit_type in (2, -1):
            for obj in snap.objects:
                if name_or_id is None:
                    return obj
                if isinstance(name_or_id, int) and obj.txt_file_no == name_or_id:
                    return obj

        return None

    def getUnits(self, unit_type: int = -1) -> list:
        """Get all units of a type."""
        snap = self._tracker.snapshot
        result: list = []
        if unit_type in (0, -1) and snap.player:
            result.append(snap.player)
        if unit_type in (1, -1):
            result.extend(snap.monsters)
        if unit_type in (4, -1):
            result.extend(snap.ground_items)
            result.extend(snap.inventory_items)
        if unit_type in (2, -1):
            result.extend(snap.objects)
        return result

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------

    def clickMap(self, click_type: int, shift: int, x: int, y: int) -> bool:
        """
        Simulate a map click (mirrors D2BS clickMap).

        click_type: 0=left, 1=right
        shift: 0=normal, 1=shift-held
        """
        if click_type == 0:
            self._sender.send_raw(self._sender.builder.cast_left_on_location(x, y))
        else:
            self._sender.cast_right_at(x, y)
        return True

    def moveTo(self, x: int, y: int) -> bool:
        """Move the player to coordinates."""
        return self._player.move_to(x, y)

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------

    def setSkill(self, skill_id: int, hand: int = 1) -> bool:
        """
        Set active skill.

        hand: 0=left, 1=right
        """
        if hand == 0:
            return self._sender.set_left_skill(skill_id)
        return self._sender.set_right_skill(skill_id)

    def castSkill(self, skill_id: int, x: int, y: int) -> bool:
        """Cast a skill at a location."""
        return self._player.cast_right(skill_id, x, y)

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------

    def pickUpItem(self, item: ItemUnit) -> bool:
        return self._inventory.pick_item(item)

    def dropItem(self, item: ItemUnit) -> bool:
        return self._inventory.drop_item(item)

    def identifyItem(self, item: ItemUnit) -> bool:
        return self._inventory.identify_item(item)

    def getItemName(self, item: ItemUnit) -> str:
        return get_item_name(item.txt_file_no)

    # ------------------------------------------------------------------
    # NPC / Town
    # ------------------------------------------------------------------

    def openNPC(self, npc_id: int) -> bool:
        return self._npcs.interact_npc(npc_id)

    def closeNPC(self) -> bool:
        return self._npcs.close_npc()

    def usePortal(self) -> bool:
        return self._player.use_town_portal()

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def delay(self, ms: int) -> None:
        """Sleep for *ms* milliseconds."""
        time.sleep(ms / 1000.0)

    def print(self, *args: Any) -> None:
        """Print to bot console."""
        msg = " ".join(str(a) for a in args)
        log.info("[script] %s", msg)

    def say(self, msg: str) -> None:
        """Send a chat message in-game."""
        self._sender.send_raw(self._sender.builder.chat_message(msg))

    def quit(self) -> None:
        """Leave the current game."""
        self._sender.leave_game()

    def getDistance(self, x1: int, y1: int, x2: int = 0, y2: int = 0) -> float:
        """Get distance. If only 2 args, distance from player to (x1,y1)."""
        from kolbot.utils.helpers import distance
        if x2 == 0 and y2 == 0:
            pos = self._player.position
            return distance(pos.x, pos.y, x1, y1)
        return distance(x1, y1, x2, y2)

    def getAreaName(self, area_id: int) -> str:
        return get_area_name(area_id)

    def getSkillName(self, skill_id: int) -> str:
        return get_skill_name(skill_id)

    # ------------------------------------------------------------------
    # Build namespace dict for script execution
    # ------------------------------------------------------------------

    def build_namespace(self) -> dict[str, Any]:
        """
        Build the global namespace dict injected into scripts.

        This provides all the functions and objects scripts need.
        """
        ns: dict[str, Any] = {
            # Core objects
            "me": self.me,
            "api": self,
            # Unit functions
            "getUnit": self.getUnit,
            "getUnits": self.getUnits,
            # Movement
            "clickMap": self.clickMap,
            "moveTo": self.moveTo,
            # Skills
            "setSkill": self.setSkill,
            "castSkill": self.castSkill,
            # Items
            "pickUpItem": self.pickUpItem,
            "dropItem": self.dropItem,
            "identifyItem": self.identifyItem,
            "getItemName": self.getItemName,
            # NPC
            "openNPC": self.openNPC,
            "closeNPC": self.closeNPC,
            "usePortal": self.usePortal,
            # Misc
            "delay": self.delay,
            "print": self.print,
            "say": self.say,
            "quit": self.quit,
            "getDistance": self.getDistance,
            "getAreaName": self.getAreaName,
            "getSkillName": self.getSkillName,
            # Constants
            "Area": Area,
            "SkillID": SkillID,
            "StatID": StatID,
            "ItemQuality": ItemQuality,
            "UnitType": UnitType,
        }
        return ns
