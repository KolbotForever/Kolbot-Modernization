"""
Profile management.

Each profile represents a single bot instance configuration:
account credentials, character settings, run preferences, etc.
Profiles are stored as JSON files in the profiles/ directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from kolbot.config.settings import (
    ChickenSettings,
    CombatSettings,
    GameSettings,
    GlobalSettings,
    PickitSettings,
    RunSettings,
    TownSettings,
)
from kolbot.utils.logger import get_logger

log = get_logger("config.profile")


class AccountInfo(BaseModel):
    """Battle.net / game account info."""
    account: str = ""
    password: str = ""
    character: str = ""
    realm: str = ""  # e.g. "uswest", "useast", "europe", "asia"
    game_exe_path: str = r"C:\Games\Diablo II\Game.exe"


class CharacterInfo(BaseModel):
    """Character-specific configuration."""
    player_class: str = "sorceress"
    build: str = "blizzard"
    level: int = 0  # 0 = auto-detect
    use_teleport: bool = True


class Profile(BaseModel):
    """A complete bot profile."""
    name: str = "default"
    account: AccountInfo = Field(default_factory=AccountInfo)
    character: CharacterInfo = Field(default_factory=CharacterInfo)
    chicken: ChickenSettings = Field(default_factory=ChickenSettings)
    town: TownSettings = Field(default_factory=TownSettings)
    combat: CombatSettings = Field(default_factory=CombatSettings)
    pickit: PickitSettings = Field(default_factory=PickitSettings)
    game: GameSettings = Field(default_factory=GameSettings)
    runs: RunSettings = Field(default_factory=RunSettings)

    # Per-profile overrides
    scripts: list[str] = Field(default_factory=list)
    enabled: bool = True
    pid: int = 0  # attached Game.exe PID (0 = auto-detect)


class ProfileManager:
    """
    Loads, saves, and manages bot profiles.

    Profiles are stored in ``profiles/<name>/config.json``.
    """

    def __init__(self, profiles_dir: str | Path = "profiles") -> None:
        self._dir = Path(profiles_dir)
        self._profiles: dict[str, Profile] = {}

    @property
    def profiles(self) -> dict[str, Profile]:
        return self._profiles

    @property
    def profile_names(self) -> list[str]:
        return list(self._profiles.keys())

    def load_all(self) -> int:
        """Load all profiles from the profiles directory."""
        if not self._dir.exists():
            self._dir.mkdir(parents=True, exist_ok=True)
            return 0

        count = 0
        for subdir in sorted(self._dir.iterdir()):
            if subdir.is_dir():
                config_file = subdir / "config.json"
                if config_file.exists():
                    profile = self.load_profile(subdir.name)
                    if profile:
                        count += 1

        log.info("Loaded %d profile(s)", count)
        return count

    def load_profile(self, name: str) -> Optional[Profile]:
        """Load a single profile by name."""
        config_file = self._dir / name / "config.json"
        if not config_file.exists():
            log.warning("Profile config not found: %s", config_file)
            return None

        try:
            with open(config_file, encoding="utf-8") as f:
                data = json.load(f)
            profile = Profile.model_validate(data)
            profile.name = name
            self._profiles[name] = profile
            log.info("Loaded profile: %s", name)
            return profile
        except Exception as e:
            log.error("Failed to load profile '%s': %s", name, e)
            return None

    def save_profile(self, profile: Profile) -> None:
        """Save a profile to disk."""
        profile_dir = self._dir / profile.name
        profile_dir.mkdir(parents=True, exist_ok=True)
        config_file = profile_dir / "config.json"

        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(profile.model_dump(), f, indent=2)

        self._profiles[profile.name] = profile
        log.info("Saved profile: %s", profile.name)

    def create_profile(self, name: str) -> Profile:
        """Create a new profile with defaults."""
        profile = Profile(name=name)
        self.save_profile(profile)
        return profile

    def delete_profile(self, name: str) -> bool:
        """Delete a profile."""
        import shutil
        profile_dir = self._dir / name
        if profile_dir.exists():
            shutil.rmtree(profile_dir)
            self._profiles.pop(name, None)
            log.info("Deleted profile: %s", name)
            return True
        return False

    def get_profile(self, name: str) -> Optional[Profile]:
        return self._profiles.get(name)

    def get_enabled_profiles(self) -> list[Profile]:
        """Get all profiles that are enabled."""
        return [p for p in self._profiles.values() if p.enabled]

    def apply_global_settings(self, settings: GlobalSettings) -> None:
        """Apply global settings as defaults to all profiles."""
        for profile in self._profiles.values():
            # Only override fields that are still at default
            # This preserves per-profile customizations
            pass  # profiles override globals by design
