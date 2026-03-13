"""
Multi-instance manager.

Manages multiple simultaneous bot instances, each attached to a
different Game.exe process with its own profile, thread pool,
and logging context.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from kolbot.config.profile import Profile, ProfileManager
from kolbot.config.settings import GlobalSettings
from kolbot.core.game_state import GameStateTracker
from kolbot.core.memory import GameMemoryReader
from kolbot.core.packets import PacketSender
from kolbot.core.process import ProcessManager
from kolbot.utils.logger import get_instance_logger, get_logger

log = get_logger("multi.instance_manager")


class InstanceState(Enum):
    """State of a bot instance."""
    IDLE = auto()
    STARTING = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    ERROR = auto()


@dataclass(slots=True)
class BotInstance:
    """A single bot instance with all its components."""
    profile: Profile
    pid: int = 0
    state: InstanceState = InstanceState.IDLE
    process: Optional[ProcessManager] = None
    reader: Optional[GameMemoryReader] = None
    sender: Optional[PacketSender] = None
    tracker: Optional[GameStateTracker] = None
    thread: Optional[threading.Thread] = None
    error: str = ""
    start_time: float = 0.0


class InstanceManager:
    """
    Manages multiple bot instances.

    Each instance is a fully independent bot attached to its own
    Game.exe process, running in its own thread with its own
    profile configuration.

    Usage::

        manager = InstanceManager(settings)
        manager.load_profiles("profiles/")
        manager.start_all()
        # ... later
        manager.stop_all()
    """

    def __init__(self, settings: GlobalSettings) -> None:
        self._settings = settings
        self._instances: dict[str, BotInstance] = {}
        self._profile_manager = ProfileManager()
        self._lock = threading.Lock()
        self._running = False

    @property
    def instances(self) -> dict[str, BotInstance]:
        return self._instances

    @property
    def running_count(self) -> int:
        return sum(
            1 for i in self._instances.values()
            if i.state == InstanceState.RUNNING
        )

    @property
    def all_stopped(self) -> bool:
        return all(
            i.state in (InstanceState.STOPPED, InstanceState.IDLE, InstanceState.ERROR)
            for i in self._instances.values()
        )

    # ------------------------------------------------------------------
    # Profile loading
    # ------------------------------------------------------------------

    def load_profiles(self, profiles_dir: str = "profiles") -> int:
        """Load all profiles and create instance placeholders."""
        self._profile_manager = ProfileManager(profiles_dir)
        count = self._profile_manager.load_all()

        for name, profile in self._profile_manager.profiles.items():
            if profile.enabled:
                self._instances[name] = BotInstance(profile=profile)

        log.info("Loaded %d enabled instance(s)", len(self._instances))
        return len(self._instances)

    def add_instance(self, profile: Profile) -> None:
        """Add an instance for a profile."""
        with self._lock:
            self._instances[profile.name] = BotInstance(profile=profile)

    def remove_instance(self, name: str) -> None:
        """Remove an instance (must be stopped first)."""
        with self._lock:
            inst = self._instances.get(name)
            if inst and inst.state in (InstanceState.IDLE, InstanceState.STOPPED, InstanceState.ERROR):
                del self._instances[name]

    # ------------------------------------------------------------------
    # Instance lifecycle
    # ------------------------------------------------------------------

    def start_instance(self, name: str) -> bool:
        """Start a single bot instance."""
        with self._lock:
            inst = self._instances.get(name)
            if not inst:
                log.error("Instance '%s' not found", name)
                return False
            if inst.state == InstanceState.RUNNING:
                log.warning("Instance '%s' already running", name)
                return True

        inst.state = InstanceState.STARTING
        inst_log = get_instance_logger(name)

        try:
            # Discover or use configured PID
            pid = inst.profile.pid
            if pid == 0:
                pids = ProcessManager.find_game_processes()
                # Find an unattached PID
                attached_pids = {
                    i.pid for i in self._instances.values()
                    if i.pid > 0 and i.state == InstanceState.RUNNING
                }
                available = [p for p, _ in pids if p not in attached_pids]
                if not available:
                    raise RuntimeError("No available Game.exe process for instance")
                pid = available[0]

            inst.pid = pid
            inst_log.info("Attaching to PID %d", pid)

            # Create components
            inst.process = ProcessManager()
            if not inst.process.attach(pid):
                raise RuntimeError(f"Failed to attach to PID {pid}")

            inst.reader = GameMemoryReader(inst.process)
            inst.sender = PacketSender(inst.process)
            inst.tracker = GameStateTracker(inst.reader)
            inst.tracker.start(tick_rate=self._settings.tick_rate)

            # Start the bot thread
            inst.thread = threading.Thread(
                target=self._run_instance,
                args=(inst,),
                daemon=True,
                name=f"bot-{name}",
            )
            inst.start_time = time.time()
            inst.state = InstanceState.RUNNING
            inst.thread.start()

            log.info("Instance '%s' started on PID %d", name, pid)
            return True

        except Exception as e:
            inst.state = InstanceState.ERROR
            inst.error = str(e)
            log.error("Failed to start instance '%s': %s", name, e)
            return False

    def stop_instance(self, name: str) -> None:
        """Stop a single bot instance."""
        with self._lock:
            inst = self._instances.get(name)
            if not inst:
                return

        if inst.state != InstanceState.RUNNING:
            return

        inst.state = InstanceState.STOPPING
        log.info("Stopping instance '%s'...", name)

        # Stop sub-components
        if inst.tracker:
            inst.tracker.stop()

        # Wait for thread
        if inst.thread and inst.thread.is_alive():
            inst.thread.join(timeout=5.0)

        if inst.process:
            inst.process.detach()

        inst.state = InstanceState.STOPPED
        log.info("Instance '%s' stopped", name)

    def start_all(self) -> int:
        """Start all enabled instances. Returns count started."""
        self._running = True
        started = 0
        for name in list(self._instances.keys()):
            if self.start_instance(name):
                started += 1
                time.sleep(0.5)  # stagger starts
        return started

    def stop_all(self) -> None:
        """Stop all running instances."""
        self._running = False
        for name in list(self._instances.keys()):
            self.stop_instance(name)
        log.info("All instances stopped")

    # ------------------------------------------------------------------
    # Instance thread
    # ------------------------------------------------------------------

    def _run_instance(self, inst: BotInstance) -> None:
        """
        Main loop for a bot instance thread.

        Imports and runs the autoplay controller with the instance's
        components and profile configuration.
        """
        inst_log = get_instance_logger(inst.profile.name)
        inst_log.info("Bot thread started for '%s'", inst.profile.name)

        try:
            from kolbot.bot.autoplay import AutoPlayConfig, AutoPlayController
            from kolbot.bot.combat import CombatConfig, CombatEngine
            from kolbot.bot.chicken import ChickenConfig
            from kolbot.bot.pickit import PickitEngine
            from kolbot.bot.pathing import PathFinder
            from kolbot.game.player import Player
            from kolbot.game.inventory import InventoryManager
            from kolbot.game.belt import BeltManager
            from kolbot.game.mercenary import Mercenary
            from kolbot.game.npcs import NPCManager
            from kolbot.game.monsters import MonsterTracker

            # Build all game modules
            player = Player(inst.reader, inst.sender, inst.tracker)
            inventory = InventoryManager(inst.reader, inst.sender, inst.tracker)
            belt = BeltManager(inst.reader, inst.sender, inst.tracker)
            merc = Mercenary(inst.reader, inst.sender, inst.tracker)
            npcs = NPCManager(inst.reader, inst.sender, inst.tracker)
            monster_tracker = MonsterTracker(inst.tracker)
            path_finder = PathFinder(player, inst.reader, inst.sender, inst.tracker)
            pickit = PickitEngine()

            # Build combat config from profile
            combat_config = CombatConfig(
                clear_radius=inst.profile.combat.clear_radius,
                max_attack_time=inst.profile.combat.max_attack_time,
                use_teleport=inst.profile.combat.use_teleport,
                use_static=inst.profile.combat.use_static,
            )
            combat = CombatEngine(player, inst.sender, inst.tracker, monster_tracker, combat_config)

            # Build chicken config
            chicken_config = ChickenConfig(
                hp_chicken=inst.profile.chicken.hp_chicken,
                hp_potion=inst.profile.chicken.hp_potion,
                hp_rejuv=inst.profile.chicken.hp_rejuv,
                mp_potion=inst.profile.chicken.mp_potion,
                merc_hp_chicken=inst.profile.chicken.merc_hp_chicken,
                merc_hp_potion=inst.profile.chicken.merc_hp_potion,
            )

            # Build autoplay config
            autoplay_config = AutoPlayConfig(
                max_game_time=inst.profile.game.max_game_time,
                min_game_time=inst.profile.game.min_game_time,
                delay_between_games=inst.profile.game.delay_between_games,
                game_count_limit=inst.profile.game.game_count_limit,
                use_teleport=inst.profile.combat.use_teleport,
                combat=combat_config,
                chicken=chicken_config,
            )

            # Build and run the controller
            controller = AutoPlayController(
                config=autoplay_config,
                reader=inst.reader,
                sender=inst.sender,
                tracker=inst.tracker,
                player=player,
                inventory=inventory,
                belt=belt,
                merc=merc,
                npcs=npcs,
                pickit=pickit,
                combat=combat,
                path_finder=path_finder,
                monster_tracker=monster_tracker,
            )

            # Run until stopped
            while inst.state == InstanceState.RUNNING:
                if inst.tracker.snapshot.in_game:
                    controller.run()
                else:
                    time.sleep(1.0)

        except Exception as e:
            inst_log.exception("Instance '%s' error", inst.profile.name)
            inst.error = str(e)
            inst.state = InstanceState.ERROR
        finally:
            inst_log.info("Bot thread ended for '%s'", inst.profile.name)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, dict]:
        """Get status of all instances."""
        result = {}
        for name, inst in self._instances.items():
            uptime = time.time() - inst.start_time if inst.start_time else 0
            result[name] = {
                "state": inst.state.name,
                "pid": inst.pid,
                "uptime_minutes": uptime / 60.0,
                "error": inst.error,
            }
        return result
