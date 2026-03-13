"""
Monster tracking and classification.

Provides helpers to filter, sort, and classify monsters for the
combat and targeting systems.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from kolbot.core.game_state import GameStateTracker
from kolbot.core.structures import MonsterUnit, Position
from kolbot.utils.helpers import distance
from kolbot.utils.logger import get_logger

log = get_logger("game.monsters")

# ---------------------------------------------------------------------------
# Monster database (loaded from data/monsters.json or hardcoded)
# ---------------------------------------------------------------------------

# Monster type flags / immunities
IMMUNE_FIRE = 1
IMMUNE_COLD = 2
IMMUNE_LIGHTNING = 3
IMMUNE_POISON = 4
IMMUNE_MAGIC = 5
IMMUNE_PHYSICAL = 6

# Well-known boss IDs
ANDARIEL_ID = 156
DURIEL_ID = 211
MEPHISTO_ID = 242
DIABLO_ID = 243
BAAL_ID = 544
NIHLATHAK_ID = 526
SUMMONER_ID = 250
COUNTESS_ID = 740
PINDLESKIN_ID = 702
RAKANISHU_ID = 757
ELDRITCH_ID = 706
SHENK_ID = 707
THRESH_SOCKET_ID = 705

# Super unique monsters (commonly farmed)
SUPER_UNIQUES = {
    PINDLESKIN_ID, ELDRITCH_ID, SHENK_ID, THRESH_SOCKET_ID,
    RAKANISHU_ID, COUNTESS_ID,
}


class MonsterTracker:
    """
    High-level monster tracking utilities.

    Works from the game state snapshot to provide filtered and
    sorted monster lists for the combat system.
    """

    def __init__(self, tracker: GameStateTracker) -> None:
        self._tracker = tracker

    @property
    def all_monsters(self) -> list[MonsterUnit]:
        return self._tracker.snapshot.monsters

    @property
    def alive_monsters(self) -> list[MonsterUnit]:
        return self._tracker.snapshot.alive_monsters

    @property
    def unique_monsters(self) -> list[MonsterUnit]:
        return self._tracker.snapshot.unique_monsters

    def monsters_in_range(self, pos: Position, radius: float) -> list[MonsterUnit]:
        """Get alive monsters within *radius* tiles of *pos*."""
        return [
            m for m in self.alive_monsters
            if distance(pos.x, pos.y, m.position.x, m.position.y) <= radius
        ]

    def nearest_monster(self, pos: Position) -> Optional[MonsterUnit]:
        """Get the nearest alive monster to *pos*."""
        alive = self.alive_monsters
        if not alive:
            return None
        return min(
            alive,
            key=lambda m: distance(pos.x, pos.y, m.position.x, m.position.y),
        )

    def nearest_unique(self, pos: Position) -> Optional[MonsterUnit]:
        """Get the nearest unique/champion monster."""
        uniques = self.unique_monsters
        if not uniques:
            return None
        return min(
            uniques,
            key=lambda m: distance(pos.x, pos.y, m.position.x, m.position.y),
        )

    def count_in_range(self, pos: Position, radius: float) -> int:
        return len(self.monsters_in_range(pos, radius))

    def is_boss_present(self) -> bool:
        """Check if any act boss is in the monster list."""
        boss_ids = {ANDARIEL_ID, DURIEL_ID, MEPHISTO_ID, DIABLO_ID, BAAL_ID}
        return any(m.txt_file_no in boss_ids for m in self.alive_monsters)

    def get_boss(self) -> Optional[MonsterUnit]:
        """Get the act boss if present."""
        boss_ids = {ANDARIEL_ID, DURIEL_ID, MEPHISTO_ID, DIABLO_ID, BAAL_ID}
        for m in self.alive_monsters:
            if m.txt_file_no in boss_ids:
                return m
        return None

    def is_area_clear(self, pos: Position, radius: float = 30.0) -> bool:
        """Check if there are no alive monsters within radius."""
        return self.count_in_range(pos, radius) == 0

    def prioritized_targets(self, pos: Position, radius: float = 40.0) -> list[MonsterUnit]:
        """
        Get monsters sorted by priority:
        1. Bosses
        2. Uniques / Champions
        3. Regular monsters (nearest first)
        """
        in_range = self.monsters_in_range(pos, radius)
        if not in_range:
            return []

        bosses: list[MonsterUnit] = []
        uniques: list[MonsterUnit] = []
        normals: list[MonsterUnit] = []

        boss_ids = {ANDARIEL_ID, DURIEL_ID, MEPHISTO_ID, DIABLO_ID, BAAL_ID}
        for m in in_range:
            if m.txt_file_no in boss_ids:
                bosses.append(m)
            elif m.is_unique or m.is_champion:
                uniques.append(m)
            else:
                normals.append(m)

        # Sort each group by distance
        key = lambda m: distance(pos.x, pos.y, m.position.x, m.position.y)
        bosses.sort(key=key)
        uniques.sort(key=key)
        normals.sort(key=key)

        return bosses + uniques + normals

    def has_dangerous_enchants(self, monster: MonsterUnit) -> bool:
        """
        Check if a monster has dangerous enchantments.

        Commonly avoided: Conviction Aura (27), Lightning Enchanted (17)
        with Multi-Shot (9) on hardcore.
        """
        dangerous = {17, 27, 28}  # LE, Conviction, ??? 
        return bool(set(monster.enchantments) & dangerous)

    def get_monsters_by_id(self, txt_file_no: int) -> list[MonsterUnit]:
        """Get all alive monsters with a specific txtFileNo."""
        return [m for m in self.alive_monsters if m.txt_file_no == txt_file_no]
