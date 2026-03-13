"""
Town manager bot logic.

Coordinates the full town-visit cycle as a bot action: evaluates
when to visit town, performs all tasks, and returns to farming.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from kolbot.core.game_state import GameStateTracker
from kolbot.game.belt import BeltManager
from kolbot.game.inventory import InventoryManager
from kolbot.game.map import get_act, is_town
from kolbot.game.mercenary import Mercenary
from kolbot.game.npcs import NPCManager
from kolbot.game.player import Player
from kolbot.game.town import TownManager
from kolbot.utils.logger import get_logger

log = get_logger("bot.town_manager")


@dataclass(slots=True)
class TownVisitConfig:
    """Configuration for automatic town visits."""
    # Thresholds that trigger a town visit
    min_belt_potions: int = 4       # visit town if total belt potions below this
    min_inventory_free: int = 4     # visit town if free cells below this
    repair_threshold: float = 20.0  # visit town if any item durability below %
    revive_merc: bool = True        # revive merc when dead
    identify_items: bool = True     # identify items at Cain
    stash_items: bool = True        # stash valuable items


class TownVisitManager:
    """
    Decides when to visit town and coordinates the full cycle.

    This wraps TownManager with bot-level decision making:
    checking if a town visit is needed, executing it, and
    returning to the farming location.
    """

    def __init__(
        self,
        player: Player,
        tracker: GameStateTracker,
        town: TownManager,
        inventory: InventoryManager,
        belt: BeltManager,
        merc: Mercenary,
        config: Optional[TownVisitConfig] = None,
    ) -> None:
        self._player = player
        self._tracker = tracker
        self._town = town
        self._inventory = inventory
        self._belt = belt
        self._merc = merc
        self.config = config or TownVisitConfig()
        self._return_area: int = 0
        self._return_pos: Optional[tuple[int, int]] = None

    def needs_town_visit(self) -> bool:
        """Check if any condition requires a town visit."""
        snap = self._tracker.snapshot
        if not snap.in_game:
            return False
        if is_town(snap.area_id):
            return False

        # Belt potions low
        total_potions = (
            self._belt.count_health_potions()
            + self._belt.count_mana_potions()
            + self._belt.count_rejuv_potions()
        )
        if total_potions < self.config.min_belt_potions:
            log.debug("Town needed: low belt potions (%d)", total_potions)
            return True

        # Inventory full
        if self._inventory.inventory_free_cells < self.config.min_inventory_free:
            log.debug("Town needed: inventory almost full (%d free)", self._inventory.inventory_free_cells)
            return True

        # Merc dead
        if self.config.revive_merc and not self._merc.is_alive:
            log.debug("Town needed: merc is dead")
            return True

        return False

    def do_town_visit(self) -> bool:
        """
        Execute a full town visit cycle.

        1. Save current position
        2. Go to town
        3. Do town tasks
        4. Return to saved position
        """
        snap = self._tracker.snapshot
        self._return_area = snap.area_id
        if snap.player:
            self._return_pos = (snap.player.position.x, snap.player.position.y)

        log.info("Starting town visit (from area %d)", self._return_area)

        # Go to town and do tasks
        if not self._town.do_town_tasks():
            log.warning("Town tasks failed")
            return False

        # Return
        if not self._town.return_from_town():
            log.warning("Failed to return from town")
            return False

        log.info("Town visit complete, returned to area %d", self._tracker.snapshot.area_id)
        return True

    def check_and_visit(self) -> bool:
        """
        Check if town visit is needed and do it if so.

        Returns True if a visit was performed (or none was needed).
        Returns False if the visit failed.
        """
        if self.needs_town_visit():
            return self.do_town_visit()
        return True
