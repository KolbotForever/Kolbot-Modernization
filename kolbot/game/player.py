"""
Player actions and state queries.

High-level interface for controlling the player character: movement,
skill casting, item usage, stat checking, etc.  Built on top of
GameMemoryReader and PacketSender.
"""

from __future__ import annotations

import time
from typing import Optional

from kolbot.core.game_state import GameStateTracker
from kolbot.core.memory import GameMemoryReader
from kolbot.core.packets import PacketSender
from kolbot.core.structures import (
    PlayerClass,
    PlayerMode,
    PlayerUnit,
    Position,
    SkillInfo,
    StatID,
)
from kolbot.utils.helpers import Cooldown, distance
from kolbot.utils.logger import get_logger

log = get_logger("game.player")


class Player:
    """
    High-level player controller.

    Provides blocking movement, skill casting with cooldown management,
    health/mana queries, and convenience methods for common actions.
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
        self._move_cooldown = Cooldown(50)  # min 50ms between moves
        self._cast_cooldown = Cooldown(250)

    # ------------------------------------------------------------------
    # Snapshot accessors
    # ------------------------------------------------------------------

    @property
    def unit(self) -> Optional[PlayerUnit]:
        return self._tracker.snapshot.player

    @property
    def position(self) -> Position:
        snap = self._tracker.snapshot
        return snap.player.position if snap.player else Position()

    @property
    def area_id(self) -> int:
        return self._tracker.snapshot.area_id

    @property
    def in_town(self) -> bool:
        pu = self.unit
        return pu.in_town if pu else False

    @property
    def hp(self) -> int:
        pu = self.unit
        return pu.hp if pu else 0

    @property
    def max_hp(self) -> int:
        pu = self.unit
        return pu.max_hp if pu else 1

    @property
    def hp_percent(self) -> float:
        mhp = self.max_hp
        return (self.hp / mhp * 100.0) if mhp else 0.0

    @property
    def mana(self) -> int:
        pu = self.unit
        return pu.mana if pu else 0

    @property
    def max_mana(self) -> int:
        pu = self.unit
        return pu.max_mana if pu else 1

    @property
    def mana_percent(self) -> float:
        mm = self.max_mana
        return (self.mana / mm * 100.0) if mm else 0.0

    @property
    def level(self) -> int:
        pu = self.unit
        return pu.level if pu else 0

    @property
    def player_class(self) -> PlayerClass:
        pu = self.unit
        return pu.player_class if pu else PlayerClass.AMAZON

    @property
    def gold(self) -> int:
        pu = self.unit
        return (pu.gold + pu.gold_stash) if pu else 0

    @property
    def is_dead(self) -> bool:
        pu = self.unit
        if not pu:
            return False
        return pu.mode in (PlayerMode.DEATH, PlayerMode.DEAD)

    @property
    def is_moving(self) -> bool:
        pu = self.unit
        if not pu:
            return False
        return pu.mode in (
            PlayerMode.WALKING,
            PlayerMode.RUNNING,
            PlayerMode.TOWN_WALKING,
        )

    @property
    def is_casting(self) -> bool:
        pu = self.unit
        if not pu:
            return False
        return pu.mode == PlayerMode.CASTING

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------

    def move_to(self, x: int, y: int, timeout: float = 5.0) -> bool:
        """
        Move to (x, y) and block until arrival or timeout.

        Uses run packets for speed.  Returns ``True`` if the player
        arrived within *tolerance* tiles of the target.
        """
        tolerance = 5
        deadline = time.time() + timeout

        while time.time() < deadline:
            pos = self.position
            if distance(pos.x, pos.y, x, y) <= tolerance:
                return True

            if self._move_cooldown.trigger_if_ready():
                self._sender.run_to(x, y)

            time.sleep(0.05)

        log.warning("move_to(%d, %d) timed out", x, y)
        return False

    def walk_to(self, x: int, y: int, timeout: float = 8.0) -> bool:
        """Same as move_to but uses walk (safer in town, doesn't drain stamina)."""
        tolerance = 5
        deadline = time.time() + timeout

        while time.time() < deadline:
            pos = self.position
            if distance(pos.x, pos.y, x, y) <= tolerance:
                return True
            if self._move_cooldown.trigger_if_ready():
                self._sender.walk_to(x, y)
            time.sleep(0.05)

        return False

    def teleport_to(self, x: int, y: int, skill_id: int = 54) -> bool:
        """
        Teleport to (x, y).  Sets right skill to Teleport, casts, then waits.
        Skill ID 54 = Teleport.
        """
        self._sender.set_right_skill(skill_id)
        time.sleep(0.05)
        self._sender.cast_right_at(x, y)
        time.sleep(0.15)
        return True

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------

    def get_skill(self, skill_id: int) -> Optional[SkillInfo]:
        """Find a skill by ID in the player's skill list."""
        pu = self.unit
        if not pu:
            return None
        for sk in pu.skills:
            if sk.skill_id == skill_id:
                return sk
        return None

    def has_skill(self, skill_id: int) -> bool:
        return self.get_skill(skill_id) is not None

    def get_skill_level(self, skill_id: int) -> int:
        sk = self.get_skill(skill_id)
        return sk.level if sk else 0

    def cast_right(self, skill_id: int, x: int, y: int) -> bool:
        """Set right skill and cast at location."""
        self._sender.set_right_skill(skill_id)
        time.sleep(0.04)
        self._sender.cast_right_at(x, y)
        return True

    def cast_right_on_unit(self, skill_id: int, unit_type: int, unit_id: int) -> bool:
        """Set right skill and cast on a unit."""
        self._sender.set_right_skill(skill_id)
        time.sleep(0.04)
        self._sender.cast_right_on(unit_type, unit_id)
        return True

    def cast_left(self, skill_id: int, x: int, y: int) -> bool:
        self._sender.set_left_skill(skill_id)
        time.sleep(0.04)
        self._sender.send_raw(self._sender.builder.cast_left_on_location(x, y))
        return True

    # ------------------------------------------------------------------
    # Misc actions
    # ------------------------------------------------------------------

    def use_town_portal(self) -> bool:
        """Cast a town portal (Book of Town Portal must be in inventory)."""
        self._sender.town_portal()
        time.sleep(0.5)
        return True

    def resurrect(self) -> bool:
        """Resurrect after death."""
        self._sender.send_raw(self._sender.builder.resurrect())
        time.sleep(1.0)
        return True

    def leave_game(self) -> bool:
        self._sender.leave_game()
        return True

    def switch_weapon(self) -> bool:
        self._sender.send_raw(self._sender.builder.switch_weapon())
        return True

    def interact(self, unit_type: int, unit_id: int) -> bool:
        """Interact with a unit (NPC, waypoint, portal, etc.)."""
        self._sender.interact(unit_type, unit_id)
        time.sleep(0.3)
        return True

    # ------------------------------------------------------------------
    # Wait helpers
    # ------------------------------------------------------------------

    def wait_for_mode(self, mode: int, timeout: float = 3.0) -> bool:
        """Wait until the player enters a specific animation mode."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            pu = self.unit
            if pu and pu.mode == mode:
                return True
            time.sleep(0.05)
        return False

    def wait_idle(self, timeout: float = 3.0) -> bool:
        """Wait until the player is standing still."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            pu = self.unit
            if pu and pu.mode in (
                PlayerMode.STANDING,
                PlayerMode.TOWN_STANDING,
            ):
                return True
            time.sleep(0.05)
        return False
