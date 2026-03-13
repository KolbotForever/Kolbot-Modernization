"""
Centralized game state tracker.

Maintains a cached snapshot of the entire game state (player, monsters,
items, area, UI) that is refreshed on a configurable tick interval.
All other modules read from the snapshot rather than hitting memory directly,
which avoids redundant reads and race conditions.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from kolbot.core.memory import GameMemoryReader
from kolbot.core.structures import (
    AreaInfo,
    Difficulty,
    GameInfo,
    ItemUnit,
    MonsterUnit,
    PlayerUnit,
    Position,
    UnitAny,
)
from kolbot.utils.logger import get_logger

log = get_logger("core.game_state")


@dataclass(slots=True)
class GameSnapshot:
    """Immutable snapshot of the game world at a point in time."""
    timestamp: float = 0.0
    in_game: bool = False
    difficulty: Difficulty = Difficulty.NORMAL
    game_info: GameInfo = field(default_factory=GameInfo)
    player: Optional[PlayerUnit] = None
    area_id: int = 0
    area_info: Optional[AreaInfo] = None
    monsters: list[MonsterUnit] = field(default_factory=list)
    ground_items: list[ItemUnit] = field(default_factory=list)
    inventory_items: list[ItemUnit] = field(default_factory=list)
    objects: list[UnitAny] = field(default_factory=list)

    # Derived / cached helpers
    @property
    def player_pos(self) -> Position:
        if self.player:
            return self.player.position
        return Position()

    @property
    def alive_monsters(self) -> list[MonsterUnit]:
        return [m for m in self.monsters if not m.is_dead]

    @property
    def unique_monsters(self) -> list[MonsterUnit]:
        return [m for m in self.alive_monsters if m.is_unique or m.is_champion]


class GameStateTracker:
    """
    Continuously refreshes a ``GameSnapshot`` in a background thread.

    Usage::

        tracker = GameStateTracker(reader)
        tracker.start(tick_rate=20)  # 20 Hz
        snap = tracker.snapshot
        if snap.in_game:
            print(snap.player.name, snap.player.position)
        tracker.stop()
    """

    def __init__(self, reader: GameMemoryReader) -> None:
        self._reader = reader
        self._snapshot = GameSnapshot()
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._tick_rate: float = 20.0  # Hz
        self._error_count: int = 0
        self._max_errors: int = 50  # stop after consecutive errors

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def snapshot(self) -> GameSnapshot:
        with self._lock:
            return self._snapshot

    @property
    def running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, tick_rate: float = 20.0) -> None:
        if self._running:
            return
        self._tick_rate = tick_rate
        self._running = True
        self._error_count = 0
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="game-state"
        )
        self._thread.start()
        log.info("Game state tracker started @ %.0f Hz", tick_rate)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        log.info("Game state tracker stopped")

    def force_refresh(self) -> GameSnapshot:
        """Manually refresh the snapshot (blocking)."""
        snap = self._build_snapshot()
        with self._lock:
            self._snapshot = snap
        return snap

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        interval = 1.0 / self._tick_rate
        while self._running:
            start = time.perf_counter()
            try:
                snap = self._build_snapshot()
                with self._lock:
                    self._snapshot = snap
                self._error_count = 0
            except Exception as exc:
                self._error_count += 1
                if self._error_count % 10 == 1:
                    log.warning(
                        "Snapshot build error (%d): %s", self._error_count, exc
                    )
                if self._error_count >= self._max_errors:
                    log.error("Too many consecutive errors — stopping tracker")
                    self._running = False
                    break

            elapsed = time.perf_counter() - start
            sleep_time = max(0.0, interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _build_snapshot(self) -> GameSnapshot:
        snap = GameSnapshot(timestamp=time.time())
        snap.in_game = self._reader.is_in_game()

        if not snap.in_game:
            return snap

        snap.difficulty = self._reader.get_difficulty()
        snap.game_info = self._reader.get_game_info()
        snap.player = self._reader.get_player_unit()
        snap.area_id = self._reader.get_current_area_id()

        if snap.area_id:
            snap.area_info = self._reader.get_area_info(snap.area_id)

        snap.monsters = self._reader.get_monsters()
        snap.ground_items = self._reader.get_ground_items()
        snap.inventory_items = self._reader.get_inventory_items()
        snap.objects = self._reader.get_objects()

        return snap
