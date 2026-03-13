"""
Chicken (emergency exit) logic.

Monitors player and mercenary health and triggers an immediate game
exit when HP drops below configurable thresholds.  Also handles
hostility detection and other dangerous situations.
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Optional

from kolbot.core.game_state import GameStateTracker
from kolbot.core.packets import PacketSender
from kolbot.game.mercenary import Mercenary
from kolbot.utils.logger import get_logger

log = get_logger("bot.chicken")


@dataclass(slots=True)
class ChickenConfig:
    """Chicken threshold configuration."""
    # HP percent thresholds
    hp_chicken: float = 30.0       # exit game if HP below this %
    hp_potion: float = 60.0        # use health potion below this %
    hp_rejuv: float = 40.0         # use rejuv potion below this %

    # Mana thresholds
    mp_potion: float = 30.0        # use mana potion below this %

    # Merc thresholds
    merc_hp_chicken: float = 0.0   # exit if merc HP below this (0=disabled)
    merc_hp_potion: float = 50.0   # feed merc potion below this %

    # Behavior
    chicken_on_hostile: bool = True   # exit if someone goes hostile
    chicken_on_death: bool = True     # leave game after death
    enabled: bool = True

    # Timing
    check_interval_ms: float = 50.0  # how often to check (milliseconds)


class ChickenMonitor:
    """
    Background monitor that watches HP/threat levels and takes action.

    Runs in a separate thread with high-frequency polling. When a
    chicken condition is met, it sends a LEAVE_GAME packet immediately.
    """

    def __init__(
        self,
        tracker: GameStateTracker,
        sender: PacketSender,
        merc: Mercenary,
        config: Optional[ChickenConfig] = None,
    ) -> None:
        self._tracker = tracker
        self._sender = sender
        self._merc = merc
        self.config = config or ChickenConfig()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._chickened = False
        self._potion_callback: Optional[callable] = None
        self._on_chicken_callback: Optional[callable] = None

    @property
    def chickened(self) -> bool:
        """True if the bot exited the game due to chicken logic."""
        return self._chickened

    def set_potion_callback(self, callback: callable) -> None:
        """
        Set callback for potion usage: callback(potion_type: str)
        potion_type: "health", "mana", "rejuv", "merc_health"
        """
        self._potion_callback = callback

    def set_on_chicken(self, callback: callable) -> None:
        """Set callback that fires when chicken triggers."""
        self._on_chicken_callback = callback

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._chickened = False
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="chicken"
        )
        self._thread.start()
        log.info("Chicken monitor started (HP threshold: %.0f%%)", self.config.hp_chicken)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        log.info("Chicken monitor stopped")

    def _monitor_loop(self) -> None:
        interval = self.config.check_interval_ms / 1000.0
        while self._running:
            if self.config.enabled:
                try:
                    self._check()
                except Exception:
                    log.exception("Chicken monitor error")
            time.sleep(interval)

    def _check(self) -> None:
        snap = self._tracker.snapshot
        if not snap.in_game or not snap.player:
            return

        player = snap.player

        # --- Death check ---
        if self.config.chicken_on_death and player.mode in (0, 17):
            log.warning("Player is dead — leaving game")
            self._do_chicken("death")
            return

        hp_pct = (player.hp / max(player.max_hp, 1)) * 100.0
        mp_pct = (player.mana / max(player.max_mana, 1)) * 100.0

        # --- HP chicken ---
        if hp_pct <= self.config.hp_chicken and hp_pct > 0:
            log.warning("HP CHICKEN: %.0f%% <= %.0f%% threshold", hp_pct, self.config.hp_chicken)
            self._do_chicken("low_hp")
            return

        # --- HP potion ---
        if hp_pct <= self.config.hp_rejuv:
            self._use_potion("rejuv")
        elif hp_pct <= self.config.hp_potion:
            self._use_potion("health")

        # --- Mana potion ---
        if mp_pct <= self.config.mp_potion:
            self._use_potion("mana")

        # --- Merc checks ---
        if self._merc.is_alive:
            merc_hp = self._merc.hp_percent
            if self.config.merc_hp_chicken > 0 and merc_hp <= self.config.merc_hp_chicken:
                log.warning("MERC HP CHICKEN: %.0f%%", merc_hp)
                self._do_chicken("merc_low_hp")
                return
            if merc_hp <= self.config.merc_hp_potion:
                self._use_potion("merc_health")

    def _do_chicken(self, reason: str) -> None:
        """Execute chicken: leave game immediately."""
        log.warning("CHICKEN triggered: %s", reason)
        self._chickened = True
        self._sender.leave_game()
        self._running = False
        if self._on_chicken_callback:
            try:
                self._on_chicken_callback(reason)
            except Exception:
                log.exception("on_chicken callback error")

    def _use_potion(self, potion_type: str) -> None:
        """Request potion usage through callback."""
        if self._potion_callback:
            try:
                self._potion_callback(potion_type)
            except Exception:
                log.exception("Potion callback error for %s", potion_type)
