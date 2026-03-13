"""
Town management: portal logic, town tasks, and waypoint usage.

Coordinates town visits: heal, repair, identify, stash, buy potions,
resurrect merc, then return to the field.
"""

from __future__ import annotations

import time
from typing import Optional

from kolbot.core.game_state import GameStateTracker
from kolbot.core.memory import GameMemoryReader
from kolbot.core.packets import PacketSender
from kolbot.core.structures import Position, UnitType
from kolbot.game.belt import BeltManager
from kolbot.game.inventory import InventoryManager
from kolbot.game.map import Area, get_act, get_town_for_act, is_town
from kolbot.game.mercenary import Mercenary
from kolbot.game.npcs import NPC, NPCManager
from kolbot.utils.helpers import distance
from kolbot.utils.logger import get_logger

log = get_logger("game.town")

# Approximate NPC positions for each town (for walking to them)
# These are rough and may need per-game adjustment via object scanning.
TOWN_NPC_POSITIONS: dict[int, dict[str, Position]] = {
    1: {  # Act 1 - Rogue Encampment
        "stash": Position(x=5118, y=5068),
        "akara": Position(x=5082, y=5051),
        "charsi": Position(x=5141, y=5053),
        "cain": Position(x=5118, y=5059),
        "kashya": Position(x=5100, y=5043),
        "warriv": Position(x=5155, y=5063),
        "waypoint": Position(x=5107, y=5062),
    },
    2: {  # Act 2 - Lut Gholein
        "stash": Position(x=5124, y=5076),
        "fara": Position(x=5116, y=5073),
        "drognan": Position(x=5093, y=5051),
        "lysander": Position(x=5072, y=5083),
        "cain": Position(x=5124, y=5082),
        "greiz": Position(x=5059, y=5038),
        "elzix": Position(x=5039, y=5068),
        "atma": Position(x=5138, y=5060),
        "waypoint": Position(x=5070, y=5083),
    },
    3: {  # Act 3 - Kurast Docks
        "stash": Position(x=5144, y=5059),
        "ormus": Position(x=5129, y=5053),
        "hratli": Position(x=5094, y=5031),
        "alkor": Position(x=5083, y=5059),
        "cain": Position(x=5117, y=5053),
        "asheara": Position(x=5043, y=5093),
        "waypoint": Position(x=5073, y=5058),
    },
    4: {  # Act 4 - Pandemonium Fortress
        "stash": Position(x=5022, y=5040),
        "halbu": Position(x=5015, y=5060),
        "jamella": Position(x=5027, y=5027),
        "cain": Position(x=5027, y=5040),
        "tyrael": Position(x=5017, y=5040),
        "waypoint": Position(x=5043, y=5038),
    },
    5: {  # Act 5 - Harrogath
        "stash": Position(x=5098, y=5019),
        "malah": Position(x=5081, y=5032),
        "larzuk": Position(x=5141, y=5045),
        "qual_kehk": Position(x=5069, y=5026),
        "anya": Position(x=5112, y=5008),
        "cain": Position(x=5119, y=5061),
        "waypoint": Position(x=5113, y=5068),
    },
}


class TownManager:
    """
    Orchestrates town visits.

    Handles the full sequence: enter town, heal, identify, stash, repair,
    buy potions, fill belt, resurrect merc, then return via portal/waypoint.
    """

    def __init__(
        self,
        reader: GameMemoryReader,
        sender: PacketSender,
        tracker: GameStateTracker,
        player,  # Player instance (circular import avoidance)
        inventory: InventoryManager,
        belt: BeltManager,
        merc: Mercenary,
        npcs: NPCManager,
    ) -> None:
        self._reader = reader
        self._sender = sender
        self._tracker = tracker
        self._player = player
        self._inventory = inventory
        self._belt = belt
        self._merc = merc
        self._npcs = npcs

    @property
    def current_act(self) -> int:
        return get_act(self._tracker.snapshot.area_id)

    @property
    def in_town(self) -> bool:
        return is_town(self._tracker.snapshot.area_id)

    def go_to_town(self) -> bool:
        """
        Enter town using a town portal.

        If already in town, returns True immediately.
        """
        if self.in_town:
            return True

        log.info("Casting town portal")
        self._sender.town_portal()
        time.sleep(1.0)

        # Wait for town portal to appear and enter it
        # Look for portal object in the objects list
        deadline = time.time() + 5.0
        while time.time() < deadline:
            snap = self._tracker.snapshot
            for obj in snap.objects:
                # Town portal object ID = 59
                if obj.txt_file_no == 59:
                    self._sender.interact(UnitType.OBJECT, obj.unit_id)
                    time.sleep(1.5)
                    if self.in_town:
                        log.info("Entered town")
                        return True
            time.sleep(0.2)

        log.warning("Failed to enter town via portal")
        return False

    def return_from_town(self) -> bool:
        """
        Return to the field through the town portal.
        """
        if not self.in_town:
            return True

        # Find our portal in town
        snap = self._tracker.snapshot
        for obj in snap.objects:
            if obj.txt_file_no == 59:  # Town portal
                self._sender.interact(UnitType.OBJECT, obj.unit_id)
                time.sleep(1.5)
                if not self.in_town:
                    log.info("Returned from town")
                    return True

        log.warning("No return portal found in town")
        return False

    def use_waypoint(self, target_area: int) -> bool:
        """Use a town waypoint to travel to a target area."""
        act = self.current_act
        wp_pos = TOWN_NPC_POSITIONS.get(act, {}).get("waypoint")
        if not wp_pos:
            return False

        # Walk to waypoint
        self._player.move_to(wp_pos.x, wp_pos.y)
        time.sleep(0.3)

        # Find waypoint object
        snap = self._tracker.snapshot
        for obj in snap.objects:
            # Waypoint object IDs: 119, 145, 156, 157, 237, 238, ...
            if obj.txt_file_no in (119, 145, 156, 157, 237, 238, 288, 323, 324, 398, 402, 429, 494, 496, 511, 539):
                self._sender.open_waypoint(obj.unit_id, target_area)
                time.sleep(1.0)
                return True

        log.warning("Waypoint object not found")
        return False

    # ------------------------------------------------------------------
    # Full town routine
    # ------------------------------------------------------------------

    def do_town_tasks(self) -> bool:
        """
        Execute the full town routine:
        1. Heal at healer NPC
        2. Identify items at Cain
        3. Stash valuable items
        4. Repair equipment
        5. Buy/refill potions
        6. Fill belt
        7. Resurrect merc if dead
        """
        if not self.in_town:
            if not self.go_to_town():
                return False

        act = self.current_act
        log.info("Starting town tasks in Act %d", act)

        # 1. Heal
        self._heal(act)

        # 2. Identify at Cain
        self._identify(act)

        # 3. Stash items
        self._stash_items(act)

        # 4. Repair
        self._repair(act)

        # 5. Buy potions
        self._buy_potions(act)

        # 6. Fill belt
        self._belt.fill_belt()

        # 7. Resurrect merc
        if not self._merc.is_alive:
            self._resurrect_merc(act)

        log.info("Town tasks complete")
        return True

    def _heal(self, act: int) -> None:
        """Heal at the act's healing NPC."""
        healer_id = self._npcs.get_healer_id(act)
        if not healer_id:
            return
        npc_pos = self._get_npc_position(act, "akara" if act == 1 else
                                          "fara" if act == 2 else
                                          "ormus" if act == 3 else
                                          "jamella" if act == 4 else "malah")
        if npc_pos:
            self._player.move_to(npc_pos.x, npc_pos.y)
        self._npcs.interact_npc(healer_id)
        time.sleep(0.3)

    def _identify(self, act: int) -> None:
        """Identify items at Cain."""
        cain_pos = self._get_npc_position(act, "cain")
        if cain_pos:
            self._player.move_to(cain_pos.x, cain_pos.y)
        self._npcs.identify_at_cain(act)
        time.sleep(0.3)

    def _stash_items(self, act: int) -> None:
        """Open stash and store valuable items."""
        stash_pos = self._get_npc_position(act, "stash")
        if stash_pos:
            self._player.move_to(stash_pos.x, stash_pos.y)
        # Interact with stash object
        snap = self._tracker.snapshot
        for obj in snap.objects:
            # Stash object IDs: 267 (personal stash), 268 (shared stash concept)
            if obj.txt_file_no in (267, 268, 580, 581):
                self._sender.interact(UnitType.OBJECT, obj.unit_id)
                time.sleep(0.5)
                break
        # TODO: implement item evaluation and stashing logic

    def _repair(self, act: int) -> None:
        """Repair at the act's repair NPC."""
        repair_id = self._npcs.get_repair_id(act)
        if not repair_id:
            return
        npc_pos = self._get_npc_position(act, "charsi" if act == 1 else
                                          "fara" if act == 2 else
                                          "hratli" if act == 3 else
                                          "halbu" if act == 4 else "larzuk")
        if npc_pos:
            self._player.move_to(npc_pos.x, npc_pos.y)
        self._npcs.repair_all(repair_id)

    def _buy_potions(self, act: int) -> None:
        """Buy potions from the vendor."""
        vendor_id = self._npcs.get_potion_vendor_id(act)
        if not vendor_id:
            return
        # Determine how many potions we need
        hp_need = max(0, 8 - self._belt.count_health_potions())
        mp_need = max(0, 8 - self._belt.count_mana_potions())
        if hp_need > 0 or mp_need > 0:
            self._npcs.buy_potions(vendor_id, hp_need, mp_need)

    def _resurrect_merc(self, act: int) -> None:
        """Resurrect the mercenary."""
        self._npcs.resurrect_merc(act)

    def _get_npc_position(self, act: int, name: str) -> Optional[Position]:
        """Get a known NPC/stash position for the current act."""
        positions = TOWN_NPC_POSITIONS.get(act, {})
        return positions.get(name)
