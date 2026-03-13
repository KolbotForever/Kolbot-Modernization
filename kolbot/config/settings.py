"""
Global and per-profile settings management.

Uses Pydantic models for validation and supports loading from
JSON/TOML files with sensible defaults.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from kolbot.utils.logger import get_logger

log = get_logger("config.settings")


# ===================================================================
# Settings models
# ===================================================================

class ChickenSettings(BaseModel):
    """Chicken / safety thresholds."""
    hp_chicken: float = 30.0
    hp_potion: float = 60.0
    hp_rejuv: float = 40.0
    mp_potion: float = 30.0
    merc_hp_chicken: float = 0.0
    merc_hp_potion: float = 50.0
    chicken_on_hostile: bool = True
    chicken_on_death: bool = True
    enabled: bool = True


class TownSettings(BaseModel):
    """Town visit configuration."""
    min_belt_potions: int = 4
    min_inventory_free: int = 4
    identify_items: bool = True
    stash_items: bool = True
    revive_merc: bool = True
    repair_threshold: float = 20.0


class CombatSettings(BaseModel):
    """Combat behavior."""
    clear_radius: float = 30.0
    max_attack_time: float = 30.0
    kite_distance: float = 0.0
    use_teleport: bool = False
    use_static: bool = False
    static_threshold: float = 50.0
    primary_skill: int = 0
    secondary_skill: int = 0
    prebuff_skills: list[int] = Field(default_factory=list)
    combat_aura: int = 0
    travel_aura: int = 0


class PickitSettings(BaseModel):
    """Pickit configuration."""
    pickit_file: str = "pickit.json"
    min_gold: int = 0
    min_rune: int = 0
    loot_radius: float = 30.0


class GameSettings(BaseModel):
    """Game creation / joining settings."""
    game_name_prefix: str = "kb-"
    game_password: str = ""
    game_counter_start: int = 1
    max_game_time: float = 300.0
    min_game_time: float = 120.0
    delay_between_games: float = 5.0
    difficulty: int = 2  # 0=Normal, 1=NM, 2=Hell
    game_count_limit: int = 0


class RunSettings(BaseModel):
    """Which runs to execute."""
    enabled_runs: list[str] = Field(default_factory=lambda: ["mephisto"])
    run_order: list[str] = Field(default_factory=list)


class LogSettings(BaseModel):
    """Logging configuration."""
    log_dir: str = "logs"
    log_level: str = "DEBUG"
    console_level: str = "INFO"
    log_packets: bool = False


class GlobalSettings(BaseModel):
    """Top-level settings that apply to the entire bot."""
    chicken: ChickenSettings = Field(default_factory=ChickenSettings)
    town: TownSettings = Field(default_factory=TownSettings)
    combat: CombatSettings = Field(default_factory=CombatSettings)
    pickit: PickitSettings = Field(default_factory=PickitSettings)
    game: GameSettings = Field(default_factory=GameSettings)
    runs: RunSettings = Field(default_factory=RunSettings)
    logging: LogSettings = Field(default_factory=LogSettings)

    # Advanced
    tick_rate: float = 20.0
    multi_instance: bool = False
    gui_enabled: bool = False


# ===================================================================
# Settings I/O
# ===================================================================

def load_settings(path: str | Path) -> GlobalSettings:
    """Load settings from a JSON file. Returns defaults if file missing."""
    path = Path(path)
    if not path.exists():
        log.info("Settings file not found, using defaults: %s", path)
        return GlobalSettings()

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    settings = GlobalSettings.model_validate(data)
    log.info("Loaded settings from %s", path)
    return settings


def save_settings(settings: GlobalSettings, path: str | Path) -> None:
    """Save settings to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings.model_dump(), f, indent=2)
    log.info("Saved settings to %s", path)


def create_default_settings(path: str | Path) -> GlobalSettings:
    """Create and save a default settings file."""
    settings = GlobalSettings()
    save_settings(settings, path)
    return settings
