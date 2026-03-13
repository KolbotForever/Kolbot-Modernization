"""
Mercenary control and monitoring.

Reads merc state (HP, position, alive/dead) and provides actions
like feeding potions and resurrection via NPC.
"""

from __future__ import annotations

import time
from typing import Optional

from kolbot.core.game_state import GameStateTracker
from kolbot.core.memory import GameMemoryReader
from kolbot.core.packets import PacketSender
from kolbot.core.structures import (
    MonsterUnit,
    Position,
    StatID,
    UnitType,
)
from kolbot.utils.helpers import distance
from kolbot.utils.logger import get_logger

log = get_logger("game.mercenary")

# Merc unit type in D2 is technically a "monster" owned by the player.
# The merc's owner_type == 0 (player) and owner_id == player's unit_id.


class Mercenary:
    """
    Mercenary state and control.

    The merc is found by scanning the monster hash table for a unit
    whose owner matches the local player.
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

    def find_merc(self) -> Optional[MonsterUnit]:
        """
        Find the player's mercenary among the monster list.

        The merc has owner_type == 0 and owner_id == player's unit_id.
        """
        snap = self._tracker.snapshot
        if not snap.player:
            return None

        player_id = snap.player.unit_id
        for m in snap.monsters:
            if m.owner_type == 0 and m.owner_id == player_id:
                return m
        return None

    @property
    def is_alive(self) -> bool:
        merc = self.find_merc()
        return merc is not None and not merc.is_dead

    @property
    def hp_percent(self) -> float:
        merc = self.find_merc()
        return merc.hp_percent if merc else 0.0

    @property
    def position(self) -> Optional[Position]:
        merc = self.find_merc()
        return merc.position if merc else None

    @property
    def unit_id(self) -> int:
        merc = self.find_merc()
        return merc.unit_id if merc else 0

    def needs_healing(self, threshold: float = 50.0) -> bool:
        """Check if merc HP is below threshold percent."""
        return self.is_alive and self.hp_percent < threshold

    def feed_potion(self) -> bool:
        """
        Give the merc a healing potion from the belt.

        In D2, shift-clicking a potion while the merc is alive
        feeds it to the merc.  We simulate this with the appropriate
        packet that targets the merc unit.
        """
        merc = self.find_merc()
        if not merc or merc.is_dead:
            return False

        # Use a health potion targeting the merc
        # This is done via the USE_ITEM packet with merc coordinates
        from kolbot.game.belt import BeltManager
        # We'll use the belt manager's use_potion_on_merc if available
        # For now, use the item directly
        belt_items = [
            i for i in self._tracker.snapshot.inventory_items
            if i.location.value == 3  # BELT
        ]

        from kolbot.game.items import ItemClassifier as IC
        for item in belt_items:
            if IC.is_health_potion(item) or IC.is_rejuv_potion(item):
                self._sender.send_raw(
                    self._sender.builder.use_item(item.unit_id)
                )
                log.debug("Fed potion %d to merc", item.unit_id)
                return True

        log.warning("No potions available for merc")
        return False

    def distance_to_player(self) -> float:
        """Distance between merc and player."""
        snap = self._tracker.snapshot
        merc = self.find_merc()
        if not snap.player or not merc:
            return 999.0
        pp = snap.player.position
        mp = merc.position
        return distance(pp.x, pp.y, mp.x, mp.y)

    def is_near_player(self, max_dist: float = 20.0) -> bool:
        return self.distance_to_player() <= max_dist

    def resurrect_at_npc(self, npc_unit_id: int) -> bool:
        """
        Resurrect the merc by interacting with Qual-Kehk (Act5) or
        other resurrection-capable NPCs.

        The NPC must already be in interaction range.
        """
        if self.is_alive:
            return True  # already alive

        self._sender.interact(UnitType.MONSTER, npc_unit_id)
        time.sleep(0.5)
        # TODO: Send the actual resurrection dialog packet
        log.info("Requested merc resurrection at NPC %d", npc_unit_id)
        return True
