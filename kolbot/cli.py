"""
CLI entry point for Kolbot-Python.

Provides commands to:
- Run a single bot instance with a profile
- Manage profiles (create, list, edit)
- Start multi-instance mode
- Transpile .dbj scripts
- Launch the optional GUI
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from kolbot.utils.logger import get_logger, init_logging

log = get_logger("cli")


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="kolbot",
        description="Kolbot-Python — Modern Diablo II LoD 1.14d Bot Framework",
    )
    parser.add_argument(
        "--version", action="version", version="kolbot-python 1.0.0"
    )

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # --- run ---
    p_run = sub.add_parser("run", help="Run a bot with a profile")
    p_run.add_argument("profile", help="Profile name (from profiles/ dir)")
    p_run.add_argument("--pid", type=int, default=0, help="Game.exe PID (0=auto)")
    p_run.add_argument("--settings", default="settings.json", help="Global settings file")
    p_run.add_argument("--gui", action="store_true", help="Enable GUI dashboard")

    # --- multi ---
    p_multi = sub.add_parser("multi", help="Run multiple bot instances")
    p_multi.add_argument("--profiles-dir", default="profiles", help="Profiles directory")
    p_multi.add_argument("--settings", default="settings.json", help="Global settings file")
    p_multi.add_argument("--gui", action="store_true", help="Enable GUI dashboard")

    # --- profile ---
    p_profile = sub.add_parser("profile", help="Manage profiles")
    profile_sub = p_profile.add_subparsers(dest="profile_cmd")
    profile_sub.add_parser("list", help="List all profiles")
    p_create = profile_sub.add_parser("create", help="Create a new profile")
    p_create.add_argument("name", help="Profile name")
    p_edit = profile_sub.add_parser("edit", help="Edit a profile (opens in editor)")
    p_edit.add_argument("name", help="Profile name")

    # --- transpile ---
    p_transpile = sub.add_parser("transpile", help="Transpile .dbj scripts to Python")
    p_transpile.add_argument("input", help="Input .dbj file or directory")
    p_transpile.add_argument("--output", "-o", help="Output file or directory")

    # --- script ---
    p_script = sub.add_parser("script", help="Run a single script")
    p_script.add_argument("script_path", help="Path to .py or .dbj script")
    p_script.add_argument("--pid", type=int, default=0, help="Game.exe PID")

    # --- processes ---
    sub.add_parser("processes", help="List running Game.exe processes")

    # --- init ---
    sub.add_parser("init", help="Initialize project structure with defaults")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    init_logging()

    try:
        match args.command:
            case "run":
                return cmd_run(args)
            case "multi":
                return cmd_multi(args)
            case "profile":
                return cmd_profile(args)
            case "transpile":
                return cmd_transpile(args)
            case "script":
                return cmd_script(args)
            case "processes":
                return cmd_processes(args)
            case "init":
                return cmd_init(args)
    except KeyboardInterrupt:
        log.info("Interrupted by user")
        return 130
    except Exception as e:
        log.error("Fatal error: %s", e, exc_info=True)
        return 1

    return 0


# ===================================================================
# Command implementations
# ===================================================================

def cmd_run(args: argparse.Namespace) -> int:
    """Run a single bot instance."""
    from kolbot.config.profile import ProfileManager
    from kolbot.config.settings import load_settings
    from kolbot.core.game_state import GameStateTracker
    from kolbot.core.memory import GameMemoryReader
    from kolbot.core.packets import PacketSender
    from kolbot.core.process import ProcessManager

    settings = load_settings(args.settings)
    pm = ProfileManager()
    pm.load_all()

    profile = pm.get_profile(args.profile)
    if not profile:
        log.error("Profile '%s' not found. Use 'kolbot profile list' to see available profiles.", args.profile)
        return 1

    if args.pid:
        profile.pid = args.pid

    log.info("Starting bot with profile: %s", profile.name)

    # Attach to game
    proc = ProcessManager()
    pid = profile.pid
    if pid == 0:
        processes = ProcessManager.find_game_processes()
        if not processes:
            log.error("No Game.exe processes found. Start Diablo II first.")
            return 1
        pid = processes[0][0]
        log.info("Auto-detected Game.exe PID: %d", pid)

    if not proc.attach(pid):
        log.error("Failed to attach to PID %d", pid)
        return 1

    reader = GameMemoryReader(proc)
    sender = PacketSender(proc)
    tracker = GameStateTracker(reader)
    tracker.start(tick_rate=settings.tick_rate)

    # Build bot components
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

    player = Player(reader, sender, tracker)
    inventory = InventoryManager(reader, sender, tracker)
    belt = BeltManager(reader, sender, tracker)
    merc = Mercenary(reader, sender, tracker)
    npcs = NPCManager(reader, sender, tracker)
    monster_tracker = MonsterTracker(tracker)
    path_finder = PathFinder(player, reader, sender, tracker)
    pickit = PickitEngine()

    # Load pickit rules
    pickit_file = Path("profiles") / args.profile / profile.pickit.pickit_file
    if pickit_file.exists():
        pickit.load_rules(pickit_file)

    combat = CombatEngine(player, sender, tracker, monster_tracker)
    chicken_config = ChickenConfig(
        hp_chicken=profile.chicken.hp_chicken,
        hp_potion=profile.chicken.hp_potion,
    )

    autoplay_config = AutoPlayConfig(
        max_game_time=profile.game.max_game_time,
        min_game_time=profile.game.min_game_time,
        use_teleport=profile.combat.use_teleport,
        chicken=chicken_config,
    )

    controller = AutoPlayController(
        config=autoplay_config,
        reader=reader,
        sender=sender,
        tracker=tracker,
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

    # Optional GUI
    if args.gui:
        from kolbot.multi.instance_manager import InstanceManager
        from kolbot.gui.app import BotGUI
        im = InstanceManager(settings)
        gui = BotGUI(im)
        gui.start()

    log.info("Bot running. Press Ctrl+C to stop.")

    try:
        controller.run()
    finally:
        tracker.stop()
        proc.detach()

    return 0


def cmd_multi(args: argparse.Namespace) -> int:
    """Run multiple bot instances."""
    from kolbot.config.settings import load_settings
    from kolbot.multi.instance_manager import InstanceManager

    settings = load_settings(args.settings)
    im = InstanceManager(settings)
    count = im.load_profiles(args.profiles_dir)

    if count == 0:
        log.error("No enabled profiles found in %s", args.profiles_dir)
        return 1

    # Optional GUI
    if args.gui:
        from kolbot.gui.app import BotGUI
        gui = BotGUI(im)
        gui.start()

    log.info("Starting %d bot instance(s)...", count)
    started = im.start_all()
    log.info("%d instance(s) started", started)

    try:
        while not im.all_stopped:
            time.sleep(1.0)
    except KeyboardInterrupt:
        log.info("Stopping all instances...")
        im.stop_all()

    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    """Profile management."""
    from kolbot.config.profile import ProfileManager

    pm = ProfileManager()
    pm.load_all()

    match args.profile_cmd:
        case "list":
            if not pm.profile_names:
                print("No profiles found. Create one with: kolbot profile create <name>")
            else:
                print("Profiles:")
                for name in pm.profile_names:
                    p = pm.get_profile(name)
                    status = "enabled" if p and p.enabled else "disabled"
                    print(f"  {name} ({status})")

        case "create":
            p = pm.create_profile(args.name)
            print(f"Created profile: {args.name}")
            print(f"  Config: profiles/{args.name}/config.json")
            print("  Edit the config file to set up your account and preferences.")

        case "edit":
            config_file = Path("profiles") / args.name / "config.json"
            if not config_file.exists():
                print(f"Profile '{args.name}' not found")
                return 1
            import subprocess
            editor = "notepad" if sys.platform == "win32" else "nano"
            subprocess.run([editor, str(config_file)])

        case _:
            print("Usage: kolbot profile {list|create|edit}")

    return 0


def cmd_transpile(args: argparse.Namespace) -> int:
    """Transpile .dbj scripts."""
    from kolbot.scripts.transpiler import DBJTranspiler, transpile_directory

    input_path = Path(args.input)

    if input_path.is_dir():
        out_dir = Path(args.output) if args.output else input_path / "transpiled"
        count = transpile_directory(input_path, out_dir)
        print(f"Transpiled {count} files to {out_dir}")
    elif input_path.is_file():
        transpiler = DBJTranspiler()
        result = transpiler.transpile_file(input_path)
        if args.output:
            Path(args.output).write_text(result, encoding="utf-8")
            print(f"Transpiled to {args.output}")
        else:
            print(result)
    else:
        print(f"Not found: {input_path}")
        return 1

    return 0


def cmd_script(args: argparse.Namespace) -> int:
    """Run a single script."""
    from kolbot.core.game_state import GameStateTracker
    from kolbot.core.memory import GameMemoryReader
    from kolbot.core.packets import PacketSender
    from kolbot.core.process import ProcessManager
    from kolbot.scripts.api import ScriptAPI
    from kolbot.scripts.engine import ScriptEngine
    from kolbot.game.player import Player
    from kolbot.game.inventory import InventoryManager
    from kolbot.game.belt import BeltManager
    from kolbot.game.mercenary import Mercenary
    from kolbot.game.npcs import NPCManager
    from kolbot.game.monsters import MonsterTracker
    from kolbot.bot.pickit import PickitEngine

    proc = ProcessManager()
    pid = args.pid
    if pid == 0:
        processes = ProcessManager.find_game_processes()
        if not processes:
            log.error("No Game.exe processes found")
            return 1
        pid = processes[0][0]

    if not proc.attach(pid):
        return 1

    reader = GameMemoryReader(proc)
    sender = PacketSender(proc)
    tracker = GameStateTracker(reader)
    tracker.start()

    player = Player(reader, sender, tracker)
    inventory = InventoryManager(reader, sender, tracker)
    belt = BeltManager(reader, sender, tracker)
    merc = Mercenary(reader, sender, tracker)
    npcs = NPCManager(reader, sender, tracker)
    monster_tracker = MonsterTracker(tracker)
    pickit = PickitEngine()

    api = ScriptAPI(
        tracker, reader, sender, player, inventory, belt,
        merc, npcs, monster_tracker, pickit,
    )
    engine = ScriptEngine(api)

    script_path = Path(args.script_path)
    name = engine.load_script(script_path)

    try:
        engine.run_script(name)
    finally:
        tracker.stop()
        proc.detach()

    return 0


def cmd_processes(args: argparse.Namespace) -> int:
    """List Game.exe processes."""
    from kolbot.core.process import ProcessManager

    processes = ProcessManager.find_game_processes()
    if not processes:
        print("No Game.exe processes found.")
        print("Start Diablo II Lord of Destruction first.")
        return 0

    print(f"Found {len(processes)} Game.exe process(es):")
    for pid, name in processes:
        print(f"  PID {pid}: {name}")

    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize project structure."""
    from kolbot.config.settings import create_default_settings
    from kolbot.config.profile import ProfileManager

    dirs = ["profiles", "scripts", "data", "logs"]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
        print(f"  Created {d}/")

    # Default settings
    create_default_settings("settings.json")
    print("  Created settings.json")

    # Default profile
    pm = ProfileManager()
    pm.create_profile("default")
    print("  Created profiles/default/config.json")

    print("\nProject initialized! Edit profiles/default/config.json to configure your bot.")
    print("Run with: kolbot run default")

    return 0


if __name__ == "__main__":
    sys.exit(main())
