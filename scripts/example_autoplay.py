"""
Example Auto-Play Script — Full Bot Configuration

This script demonstrates a complete autoplay setup for a Blizzard
Sorceress running Mephisto, Pindleskin, Ancient Tunnels, and
Eldritch/Shenk in rotation.

This mimics the classic Kolbot experience: town tasks, run sequence,
loot management, and game cycling — all in Python.

Usage:
    kolbot run default
    # (with this script configured in the profile)

Or run standalone:
    kolbot script scripts/example_autoplay.py --pid <PID>
"""

from kolbot.bot.autoplay import (
    ANCIENT_TUNNELS_RUN,
    ELDRITCH_SHENK_RUN,
    MEPHISTO_RUN,
    PINDLESKIN_RUN,
    AutoPlayConfig,
    AutoPlayController,
    RunDefinition,
    RunType,
)
from kolbot.bot.chicken import ChickenConfig
from kolbot.bot.combat import (
    AttackSkill,
    CombatConfig,
    blizzard_sorc_config,
)
from kolbot.bot.pickit import PickitEngine, create_default_rules
from kolbot.core.structures import StatID
from kolbot.game.map import Area
from kolbot.game.skills import SkillID


def build_blizzard_sorc_combat() -> CombatConfig:
    """
    Build combat configuration for a Blizzard Sorceress.

    Primary: Blizzard (skill 59)
    Secondary: Glacial Spike (skill 55) for freezing
    Prebuffs: Frozen Armor (skill 40), Energy Shield (skill 58)
    Uses Static Field on bosses above 50% HP.
    Uses Teleport for movement.
    """
    config = blizzard_sorc_config()

    # Customize for our build
    config.use_teleport = True
    config.teleport_skill_id = SkillID.TELEPORT
    config.kite_distance = 15.0
    config.clear_radius = 25.0
    config.max_attack_time = 30.0

    # Static Field for bosses
    config.use_static = True
    config.static_threshold = 50.0
    config.static_field_id = SkillID.STATIC_FIELD

    return config


def build_chicken_config() -> ChickenConfig:
    """
    Build chicken configuration — safety thresholds.

    HP below 30% → instant exit
    HP below 60% → use health potion
    HP below 40% → use rejuv potion
    MP below 30% → use mana potion
    Merc HP below 50% → feed merc a potion
    Chicken on hostile players.
    """
    return ChickenConfig(
        hp_chicken=30.0,
        hp_potion=60.0,
        hp_rejuv=40.0,
        mp_potion=30.0,
        merc_hp_chicken=0.0,  # don't chicken for merc
        merc_hp_potion=50.0,
        chicken_on_hostile=True,
        chicken_on_death=True,
        enabled=True,
        check_interval_ms=50,
    )


def build_pickit() -> PickitEngine:
    """Build the item filter using default rules + custom additions."""
    pickit = create_default_rules()

    # Bump minimum rune to Hel+
    pickit.min_rune = 15

    # Raise gold threshold
    pickit.min_gold = 8000

    return pickit


def build_run_sequence() -> list[RunDefinition]:
    """
    Define the run sequence.

    This Blizzard Sorc will run:
    1. Mephisto (Act 3 boss, most common MF target)
    2. Pindleskin (Act 5 super unique, fast kill)
    3. Ancient Tunnels (Act 2 alvl 85 area, no cold immunes)
    4. Eldritch & Shenk (Act 5 super uniques, fast kills)

    This mirrors a typical Kolbot rotation for a cold Sorc.
    """
    return [
        MEPHISTO_RUN,
        PINDLESKIN_RUN,
        ANCIENT_TUNNELS_RUN,
        ELDRITCH_SHENK_RUN,
    ]


def build_autoplay_config() -> AutoPlayConfig:
    """
    Build the complete autoplay configuration.

    Game settings:
    - Max 5 minutes per game
    - Min 2 minutes (avoid realm down)
    - 5 second delay between games
    - Infinite game count
    - Town tasks at game start
    """
    return AutoPlayConfig(
        runs=build_run_sequence(),
        max_game_time=300.0,
        min_game_time=120.0,
        game_count_limit=0,  # infinite
        delay_between_games=5.0,
        do_town_tasks_on_start=True,
        loot_radius=30.0,
        use_teleport=True,
        combat=build_blizzard_sorc_combat(),
        chicken=build_chicken_config(),
    )


def main():
    """
    Main entry point — demonstrates the full bot setup.

    In actual usage, the AutoPlayController is created by the
    CLI or instance manager, which provides the necessary game
    components (reader, sender, tracker, etc.).

    This script serves as both documentation and a template
    for creating custom bot configurations.
    """
    print("=" * 60)
    print("  Kolbot-Python — Blizzard Sorceress Autoplay Config")
    print("=" * 60)
    print()

    config = build_autoplay_config()

    # Display configuration
    print("Run Sequence:")
    for i, run in enumerate(config.runs, 1):
        boss = f"  (Boss ID: {run.boss_id})" if run.boss_id else ""
        clear = "  [CLEAR]" if run.clear_area else ""
        print(f"  {i}. {run.name}{boss}{clear}")

    print()
    print("Combat Configuration:")
    print(f"  Primary Attack: Blizzard (ID {config.combat.primary_attack.skill_id if config.combat.primary_attack else 'N/A'})")
    print(f"  Secondary Attack: Glacial Spike (ID {config.combat.secondary_attack.skill_id if config.combat.secondary_attack else 'N/A'})")
    print(f"  Teleport: {'Enabled' if config.use_teleport else 'Disabled'}")
    print(f"  Static Field: {'Enabled' if config.combat.use_static else 'Disabled'} (threshold: {config.combat.static_threshold}%)")
    print(f"  Kite Distance: {config.combat.kite_distance}")
    print(f"  Clear Radius: {config.combat.clear_radius}")

    print()
    print("Chicken Configuration:")
    chicken = config.chicken
    print(f"  HP Chicken: {chicken.hp_chicken}%")
    print(f"  HP Potion: {chicken.hp_potion}%")
    print(f"  HP Rejuv: {chicken.hp_rejuv}%")
    print(f"  MP Potion: {chicken.mp_potion}%")
    print(f"  Merc HP Potion: {chicken.merc_hp_potion}%")
    print(f"  Chicken on Hostile: {chicken.chicken_on_hostile}")

    print()
    print("Game Settings:")
    print(f"  Max Game Time: {config.max_game_time}s")
    print(f"  Min Game Time: {config.min_game_time}s")
    print(f"  Delay Between Games: {config.delay_between_games}s")
    print(f"  Game Count Limit: {'Infinite' if config.game_count_limit == 0 else config.game_count_limit}")
    print(f"  Town Tasks on Start: {config.do_town_tasks_on_start}")

    print()
    print("Pickit Configuration:")
    pickit = build_pickit()
    print(f"  Rules Loaded: {len(pickit._rules)}")
    print(f"  Min Rune Index: {pickit.min_rune}")
    print(f"  Min Gold: {pickit.min_gold}")

    print()
    print("=" * 60)
    print("  To run this bot:")
    print("  1. Start Diablo II LoD 1.14d")
    print("  2. Create and enter a game")
    print("  3. Run: kolbot run default")
    print("=" * 60)

    return config


if __name__ == "__main__":
    main()
