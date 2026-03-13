"""
Auto-play controller.

Orchestrates the full bot loop: create/join games, execute run
sequences (boss runs, area clears, key farming, etc.), handle
town visits, and cycle games.

This is the top-level bot controller that ties all subsystems together.
"""

from __future__ import annotations

import time
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional

from kolbot.core.game_state import GameStateTracker
from kolbot.core.memory import GameMemoryReader
from kolbot.core.packets import PacketSender
from kolbot.bot.chicken import ChickenConfig, ChickenMonitor
from kolbot.bot.combat import CombatConfig, CombatEngine
from kolbot.bot.pathing import PathFinder
from kolbot.bot.pickit import PickitAction, PickitEngine
from kolbot.bot.town_manager import TownVisitManager
from kolbot.game.belt import BeltManager
from kolbot.game.inventory import InventoryManager
from kolbot.game.map import Area, get_act, is_town
from kolbot.game.mercenary import Mercenary
from kolbot.game.monsters import MonsterTracker
from kolbot.game.npcs import NPCManager
from kolbot.game.player import Player
from kolbot.game.town import TownManager
from kolbot.utils.logger import get_logger

log = get_logger("bot.autoplay")


# ===================================================================
# Run types
# ===================================================================

class RunType(Enum):
    """Predefined run types."""
    MEPHISTO = auto()
    BAAL = auto()
    DIABLO = auto()
    PINDLESKIN = auto()
    ANCIENT_TUNNELS = auto()
    COUNTESS = auto()
    NIHLATHAK = auto()
    PIT = auto()
    CHAOS_SANCTUARY = auto()
    WORLDSTONE_KEEP = auto()
    ELDRITCH_SHENK = auto()
    CUSTOM = auto()


# ===================================================================
# Run definitions
# ===================================================================

@dataclass(slots=True)
class RunDefinition:
    """Defines a single farming run."""
    name: str
    run_type: RunType
    target_area: int          # final area to reach
    waypoint_area: int = 0    # waypoint to use (0 = figure out automatically)
    boss_id: int = 0          # expected boss txtFileNo (0 = clear area)
    clear_area: bool = False  # clear all monsters in area?
    loot_after: bool = True   # loot ground after killing
    enabled: bool = True


# Prebuilt run definitions
MEPHISTO_RUN = RunDefinition(
    name="Mephisto",
    run_type=RunType.MEPHISTO,
    target_area=Area.DURANCE_OF_HATE_LEVEL_3,
    waypoint_area=Area.DURANCE_OF_HATE_LEVEL_2,
    boss_id=242,  # Mephisto
)

BAAL_RUN = RunDefinition(
    name="Baal",
    run_type=RunType.BAAL,
    target_area=Area.THRONE_OF_DESTRUCTION,
    waypoint_area=Area.WORLDSTONE_KEEP_LEVEL_2,
    boss_id=544,  # Baal
    clear_area=True,
)

PINDLESKIN_RUN = RunDefinition(
    name="Pindleskin",
    run_type=RunType.PINDLESKIN,
    target_area=Area.NIHLATHAKS_TEMPLE,
    waypoint_area=0,  # use Anya portal
    boss_id=702,
)

ANCIENT_TUNNELS_RUN = RunDefinition(
    name="Ancient Tunnels",
    run_type=RunType.ANCIENT_TUNNELS,
    target_area=Area.ANCIENT_TUNNELS,
    waypoint_area=Area.LOST_CITY,
    clear_area=True,
)

PIT_RUN = RunDefinition(
    name="The Pit",
    run_type=RunType.PIT,
    target_area=Area.PIT_LEVEL_1,
    waypoint_area=Area.BLACK_MARSH,
    clear_area=True,
)

COUNTESS_RUN = RunDefinition(
    name="Countess",
    run_type=RunType.COUNTESS,
    target_area=Area.TOWER_CELLAR_LEVEL_5,
    waypoint_area=Area.BLACK_MARSH,
    boss_id=740,
)

ELDRITCH_SHENK_RUN = RunDefinition(
    name="Eldritch & Shenk",
    run_type=RunType.ELDRITCH_SHENK,
    target_area=Area.FRIGID_HIGHLANDS,
    waypoint_area=Area.FRIGID_HIGHLANDS,
    clear_area=False,
)

CHAOS_SANCTUARY_RUN = RunDefinition(
    name="Chaos Sanctuary",
    run_type=RunType.CHAOS_SANCTUARY,
    target_area=Area.CHAOS_SANCTUARY,
    waypoint_area=Area.RIVER_OF_FLAME,
    boss_id=243,  # Diablo
    clear_area=True,
)


# ===================================================================
# Bot state
# ===================================================================

class BotState(Enum):
    IDLE = auto()
    IN_TOWN = auto()
    TRAVELING = auto()
    FIGHTING = auto()
    LOOTING = auto()
    TOWN_VISIT = auto()
    GAME_ENDING = auto()
    ERROR = auto()


# ===================================================================
# Auto-play config
# ===================================================================

@dataclass(slots=True)
class AutoPlayConfig:
    """Top-level bot configuration."""
    # Run sequence (executed in order, then loops)
    runs: list[RunDefinition] = field(default_factory=list)

    # Game cycling
    max_game_time: float = 300.0    # max seconds per game
    min_game_time: float = 120.0    # min seconds (avoid realm down)
    game_count_limit: int = 0       # 0 = infinite
    delay_between_games: float = 5.0  # seconds between games

    # Behavior
    do_town_tasks_on_start: bool = True
    loot_radius: float = 30.0
    use_teleport: bool = True

    # Combat & chicken (referenced from their own configs)
    combat: CombatConfig = field(default_factory=CombatConfig)
    chicken: ChickenConfig = field(default_factory=ChickenConfig)


# ===================================================================
# Auto-play controller
# ===================================================================

class AutoPlayController:
    """
    Main bot controller that runs the full game loop.

    Usage::

        controller = AutoPlayController(config, ...)
        controller.run()  # blocking — runs until stopped or error
    """

    def __init__(
        self,
        config: AutoPlayConfig,
        reader: GameMemoryReader,
        sender: PacketSender,
        tracker: GameStateTracker,
        player: Player,
        inventory: InventoryManager,
        belt: BeltManager,
        merc: Mercenary,
        npcs: NPCManager,
        pickit: PickitEngine,
        combat: CombatEngine,
        path_finder: PathFinder,
        monster_tracker: MonsterTracker,
    ) -> None:
        self.config = config
        self._reader = reader
        self._sender = sender
        self._tracker = tracker
        self._player = player
        self._inventory = inventory
        self._belt = belt
        self._merc = merc
        self._npcs = npcs
        self._pickit = pickit
        self._combat = combat
        self._pf = path_finder
        self._monsters = monster_tracker

        # Build town manager
        self._town = TownManager(
            reader, sender, tracker, player, inventory, belt, merc, npcs
        )
        self._town_visit = TownVisitManager(
            player, tracker, self._town, inventory, belt, merc
        )

        # Chicken monitor
        self._chicken = ChickenMonitor(tracker, sender, merc, config.chicken)
        self._chicken.set_potion_callback(self._on_potion_needed)

        # State
        self._state = BotState.IDLE
        self._running = False
        self._game_count = 0
        self._run_index = 0
        self._game_start_time = 0.0

        # Stats
        self.stats = BotStats()

    @property
    def state(self) -> BotState:
        return self._state

    @property
    def running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the main bot loop (blocking)."""
        self._running = True
        log.info("AutoPlay starting with %d run(s) configured", len(self.config.runs))

        try:
            while self._running:
                if not self._tracker.snapshot.in_game:
                    log.info("Not in game — waiting...")
                    time.sleep(1.0)
                    continue

                self._game_start_time = time.time()
                self._game_count += 1
                log.info("=== Game #%d started ===", self._game_count)

                self._chicken.start()

                try:
                    self._run_game()
                except Exception:
                    log.exception("Error during game run")
                    self._state = BotState.ERROR

                self._chicken.stop()

                if self._chicken.chickened:
                    log.warning("Game ended by chicken logic")
                    self.stats.chicken_count += 1

                # Game cycling delay
                if self._running:
                    self._end_game()

                if 0 < self.config.game_count_limit <= self._game_count:
                    log.info("Game count limit reached (%d)", self._game_count)
                    break

        except KeyboardInterrupt:
            log.info("AutoPlay interrupted by user")
        finally:
            self._running = False
            self._state = BotState.IDLE
            log.info("AutoPlay stopped. Games: %d", self._game_count)

    def stop(self) -> None:
        """Signal the bot to stop after the current action."""
        self._running = False

    # ------------------------------------------------------------------
    # Game loop
    # ------------------------------------------------------------------

    def _run_game(self) -> None:
        """Execute all runs in a single game."""
        # Initial town tasks
        if self.config.do_town_tasks_on_start:
            self._state = BotState.IN_TOWN
            self._town.do_town_tasks()

        # Execute run sequence
        self._run_index = 0
        for run_def in self.config.runs:
            if not self._running or self._chicken.chickened:
                break
            if not run_def.enabled:
                continue

            log.info("--- Starting run: %s ---", run_def.name)
            self._execute_run(run_def)
            self._run_index += 1

            # Check game time
            elapsed = time.time() - self._game_start_time
            if elapsed >= self.config.max_game_time:
                log.info("Max game time reached (%.0fs)", elapsed)
                break

    def _execute_run(self, run: RunDefinition) -> None:
        """Execute a single farming run."""
        self.stats.runs_completed += 1

        # Town visit check before each run
        self._town_visit.check_and_visit()

        # Travel to target area
        self._state = BotState.TRAVELING
        if not self._travel_to_run(run):
            log.warning("Failed to reach %s", run.name)
            return

        # Combat phase
        self._state = BotState.FIGHTING
        if run.boss_id:
            self._fight_boss(run)
        if run.clear_area:
            self._clear_area(run)

        # Loot phase
        if run.loot_after:
            self._state = BotState.LOOTING
            self._loot_area()

    def _travel_to_run(self, run: RunDefinition) -> bool:
        """Navigate to the run's target area."""
        current_area = self._tracker.snapshot.area_id

        # Go to town first if not already there
        if not is_town(current_area):
            self._town.go_to_town()

        # Use waypoint if specified
        if run.waypoint_area:
            self._town.use_waypoint(run.waypoint_area)
            time.sleep(1.0)

        # Navigate from waypoint area to target
        current_area = self._tracker.snapshot.area_id
        if current_area != run.target_area:
            return self._pf.navigate_to_area(
                run.target_area,
                use_teleport=self.config.use_teleport,
            )

        return True

    def _fight_boss(self, run: RunDefinition) -> None:
        """Find and kill the boss for a run."""
        deadline = time.time() + 60.0
        while time.time() < deadline and self._running and not self._chicken.chickened:
            boss = self._monsters.get_boss()
            if not boss:
                # Look for the specific boss by ID
                matches = self._monsters.get_monsters_by_id(run.boss_id)
                if matches:
                    boss = matches[0]

            if boss:
                log.info("Boss found: txtFileNo=%d", boss.txt_file_no)
                self._combat.kill_boss(boss)
                self.stats.bosses_killed += 1
                return

            # Not found yet — explore/teleport around
            time.sleep(0.5)

        log.warning("Boss not found for run %s", run.name)

    def _clear_area(self, run: RunDefinition) -> None:
        """Clear all monsters in the target area."""
        self._combat.clear_area()

    def _loot_area(self) -> None:
        """Pick up valuable items from the ground."""
        snap = self._tracker.snapshot
        for item in snap.ground_items:
            if not self._running or self._chicken.chickened:
                break

            action, rule = self._pickit.evaluate(item)
            if action == PickitAction.IGNORE:
                continue

            if action in (PickitAction.PICK, PickitAction.PICK_IF_ROOM, PickitAction.IDENTIFY_THEN_DECIDE):
                # Move to item
                self._pf.move_to(item.position.x, item.position.y, use_teleport=self.config.use_teleport)
                time.sleep(0.1)

                # Pick it up
                if self._inventory.pick_item(item):
                    self.stats.items_picked += 1
                    time.sleep(0.2)

                    # Identify if needed
                    if action == PickitAction.IDENTIFY_THEN_DECIDE:
                        self._inventory.identify_item(item)
                        if not self._pickit.should_keep(item):
                            self._inventory.drop_item(item)
                            self.stats.items_picked -= 1

    # ------------------------------------------------------------------
    # Game ending
    # ------------------------------------------------------------------

    def _end_game(self) -> None:
        """End the current game and wait before the next one."""
        self._state = BotState.GAME_ENDING

        # Ensure minimum game time
        elapsed = time.time() - self._game_start_time
        if elapsed < self.config.min_game_time:
            wait = self.config.min_game_time - elapsed
            log.info("Waiting %.0fs to meet minimum game time", wait)
            time.sleep(wait)

        # Leave game
        self._sender.leave_game()
        time.sleep(self.config.delay_between_games)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_potion_needed(self, potion_type: str) -> None:
        """Called by chicken monitor when a potion should be used."""
        match potion_type:
            case "health":
                self._belt.use_health_potion()
            case "mana":
                self._belt.use_mana_potion()
            case "rejuv":
                self._belt.use_rejuv_potion()
            case "merc_health":
                self._belt.use_potion_on_merc(self._merc.unit_id)


# ===================================================================
# Bot statistics
# ===================================================================

@dataclass(slots=True)
class BotStats:
    """Runtime statistics."""
    runs_completed: int = 0
    bosses_killed: int = 0
    items_picked: int = 0
    chicken_count: int = 0
    deaths: int = 0
    start_time: float = field(default_factory=time.time)

    @property
    def uptime_minutes(self) -> float:
        return (time.time() - self.start_time) / 60.0

    @property
    def runs_per_hour(self) -> float:
        mins = self.uptime_minutes
        return (self.runs_completed / mins * 60.0) if mins > 0 else 0.0
