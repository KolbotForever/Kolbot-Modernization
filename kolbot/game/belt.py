"""
Belt management.

Tracks potion slots in the belt, auto-fills from inventory, and provides
quick-use methods for health/mana/rejuv potions during combat.
"""

from __future__ import annotations

import time
from typing import Optional

from kolbot.core.game_state import GameStateTracker
from kolbot.core.memory import GameMemoryReader
from kolbot.core.packets import PacketSender
from kolbot.core.structures import ItemLocation, ItemUnit
from kolbot.game.items import ItemClassifier as IC
from kolbot.utils.logger import get_logger

log = get_logger("game.belt")

# Belt column assignments (standard Kolbot convention):
#   Column 0: Health potions
#   Column 1: Mana potions
#   Column 2: Rejuvenation potions
#   Column 3: Rejuvenation potions (or thawing/antidote)

# Belt sizes by belt type (rows)
BELT_SIZES = {
    "none": 1,
    "sash": 2,
    "light_belt": 2,
    "belt": 3,
    "heavy_belt": 3,
    "plated_belt": 4,
    "war_belt": 4,
    "mithril_coil": 4,
    "troll_belt": 4,
    "colossus_girdle": 4,
    "vampirefang_belt": 4,
    "spiderweb_sash": 4,
}

BELT_COLS = 4  # always 4 columns


class BeltManager:
    """
    Manages the 4-column potion belt.

    Provides methods to:
    - Use potions by column (health / mana / rejuv)
    - Auto-fill belt from inventory potions
    - Track belt contents
    """

    def __init__(
        self,
        reader: GameMemoryReader,
        sender: PacketSender,
        tracker: GameStateTracker,
    ) -> None:
        self._reader = reader
        self._sender = sender
        self._tracker = tracker
        self._belt_rows = 4  # assume 4-row belt by default

    @property
    def belt_rows(self) -> int:
        return self._belt_rows

    @belt_rows.setter
    def belt_rows(self, value: int) -> None:
        self._belt_rows = max(1, min(4, value))

    @property
    def max_potions(self) -> int:
        return self._belt_rows * BELT_COLS

    def get_belt_items(self) -> list[ItemUnit]:
        """Get all items currently in the belt."""
        return [
            i for i in self._tracker.snapshot.inventory_items
            if i.location == ItemLocation.BELT
        ]

    def count_health_potions(self) -> int:
        return sum(1 for i in self.get_belt_items() if IC.is_health_potion(i))

    def count_mana_potions(self) -> int:
        return sum(1 for i in self.get_belt_items() if IC.is_mana_potion(i))

    def count_rejuv_potions(self) -> int:
        return sum(1 for i in self.get_belt_items() if IC.is_rejuv_potion(i))

    def get_column_count(self, col: int) -> int:
        """Count potions in a specific column (0-3)."""
        return sum(
            1 for i in self.get_belt_items()
            if i.inv_x == col
        )

    def is_column_full(self, col: int) -> bool:
        return self.get_column_count(col) >= self._belt_rows

    def is_belt_full(self) -> bool:
        return all(self.is_column_full(c) for c in range(BELT_COLS))

    # ------------------------------------------------------------------
    # Potion usage
    # ------------------------------------------------------------------

    def use_health_potion(self) -> bool:
        """Use a health potion from the belt."""
        for item in self.get_belt_items():
            if IC.is_health_potion(item):
                self._sender.send_raw(self._sender.builder.use_item(item.unit_id))
                log.debug("Used health potion %d", item.unit_id)
                return True
        log.warning("No health potions in belt")
        return False

    def use_mana_potion(self) -> bool:
        """Use a mana potion from the belt."""
        for item in self.get_belt_items():
            if IC.is_mana_potion(item):
                self._sender.send_raw(self._sender.builder.use_item(item.unit_id))
                log.debug("Used mana potion %d", item.unit_id)
                return True
        log.warning("No mana potions in belt")
        return False

    def use_rejuv_potion(self) -> bool:
        """Use a rejuvenation potion from the belt."""
        for item in self.get_belt_items():
            if IC.is_rejuv_potion(item):
                self._sender.send_raw(self._sender.builder.use_item(item.unit_id))
                log.debug("Used rejuv potion %d", item.unit_id)
                return True
        log.warning("No rejuv potions in belt")
        return False

    def use_potion_on_merc(self, merc_id: int) -> bool:
        """Use a health potion from belt on mercenary."""
        for item in self.get_belt_items():
            if IC.is_health_potion(item) or IC.is_rejuv_potion(item):
                # Shift-click potion on merc = use_item with merc unit
                pkt = self._sender.builder.use_item(item.unit_id)
                self._sender.send_raw(pkt)
                return True
        return False

    # ------------------------------------------------------------------
    # Auto-fill
    # ------------------------------------------------------------------

    def fill_belt(self) -> int:
        """
        Auto-fill the belt from inventory potions.

        Column assignment:
        - Col 0: health potions
        - Col 1: mana potions
        - Col 2-3: rejuv potions

        Returns number of potions added.
        """
        added = 0
        inv_items = [
            i for i in self._tracker.snapshot.inventory_items
            if i.location == ItemLocation.INVENTORY
        ]

        # Fill health potions (column 0)
        while not self.is_column_full(0):
            hp = next((i for i in inv_items if IC.is_health_potion(i)), None)
            if not hp:
                break
            self._sender.send_raw(self._sender.builder.use_item(hp.unit_id))
            inv_items.remove(hp)
            added += 1
            time.sleep(0.1)

        # Fill mana potions (column 1)
        while not self.is_column_full(1):
            mp = next((i for i in inv_items if IC.is_mana_potion(i)), None)
            if not mp:
                break
            self._sender.send_raw(self._sender.builder.use_item(mp.unit_id))
            inv_items.remove(mp)
            added += 1
            time.sleep(0.1)

        # Fill rejuv potions (columns 2-3)
        for col in (2, 3):
            while not self.is_column_full(col):
                rv = next((i for i in inv_items if IC.is_rejuv_potion(i)), None)
                if not rv:
                    break
                self._sender.send_raw(self._sender.builder.use_item(rv.unit_id))
                inv_items.remove(rv)
                added += 1
                time.sleep(0.1)

        if added:
            log.info("Filled %d potions into belt", added)
        return added

    def needs_refill(self, min_health: int = 2, min_mana: int = 2, min_rejuv: int = 2) -> bool:
        """Check if belt needs refilling based on minimum thresholds."""
        return (
            self.count_health_potions() < min_health
            or self.count_mana_potions() < min_mana
            or self.count_rejuv_potions() < min_rejuv
        )
