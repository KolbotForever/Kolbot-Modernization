"""
Combat system.

Handles target selection, skill rotation, attack patterns, and
clearing logic.  Supports class-specific attack configurations
and dynamic skill switching based on monster immunities.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from kolbot.core.game_state import GameStateTracker
from kolbot.core.packets import PacketSender
from kolbot.core.structures import MonsterUnit, Position, UnitType
from kolbot.game.monsters import MonsterTracker
from kolbot.game.player import Player
from kolbot.game.skills import SkillID
from kolbot.utils.helpers import Cooldown, distance
from kolbot.utils.logger import get_logger

log = get_logger("bot.combat")


# ===================================================================
# Attack configuration
# ===================================================================

@dataclass(slots=True)
class AttackSkill:
    """Configuration for a single attack skill."""
    skill_id: int
    min_mana: int = 0         # minimum mana to use this skill
    range: float = 20.0       # max range in tiles
    aoe: bool = False         # area of effect?
    aoe_threshold: int = 3    # use AoE if >= this many monsters nearby
    cooldown_ms: float = 250  # minimum time between casts
    on_unit: bool = True      # cast on unit (vs on location)
    precast: bool = False     # is this a prebuff skill?
    _cooldown: Cooldown = field(default_factory=lambda: Cooldown(250))

    def __post_init__(self) -> None:
        self._cooldown = Cooldown(self.cooldown_ms)


@dataclass(slots=True)
class CombatConfig:
    """Combat configuration for a character build."""
    # Primary attack skills (tried in order)
    primary_attack: list[AttackSkill] = field(default_factory=list)
    # Secondary / AoE attack
    secondary_attack: list[AttackSkill] = field(default_factory=list)
    # Prebuff skills (cast before engaging)
    prebuffs: list[AttackSkill] = field(default_factory=list)
    # Cursor skill (left click — usually attack/telekinesis)
    cursor_skill: int = 0

    # Behavior
    clear_radius: float = 30.0     # tiles to scan for monsters
    max_attack_time: float = 30.0  # seconds before giving up on a pack
    kite_distance: float = 0.0     # run away if monster < this distance
    use_teleport: bool = False     # use teleport for repositioning
    teleport_skill_id: int = SkillID.TELEPORT
    static_field_id: int = SkillID.STATIC_FIELD
    use_static: bool = False       # use static field on bosses
    static_threshold: float = 50.0 # use static until boss HP below this %

    # Aura (for Paladins)
    combat_aura: int = 0     # skill ID of aura to keep active during combat
    travel_aura: int = 0     # skill ID of aura for traveling


# ===================================================================
# Prebuilt configs for common builds
# ===================================================================

def hammerdin_config() -> CombatConfig:
    """Blessed Hammer Paladin combat config."""
    return CombatConfig(
        primary_attack=[
            AttackSkill(SkillID.BLESSED_HAMMER, min_mana=10, range=10, aoe=True, cooldown_ms=200),
        ],
        prebuffs=[
            AttackSkill(SkillID.HOLY_SHIELD, precast=True),
        ],
        combat_aura=SkillID.CONCENTRATION if hasattr(SkillID, 'CONCENTRATION') else SkillID.BLESSED_AIM,
        travel_aura=SkillID.CLEANSING,
        use_teleport=True,
        clear_radius=25.0,
    )


def blizzard_sorc_config() -> CombatConfig:
    """Blizzard Sorceress combat config."""
    return CombatConfig(
        primary_attack=[
            AttackSkill(SkillID.BLIZZARD, min_mana=25, range=25, aoe=True, cooldown_ms=1800),
        ],
        secondary_attack=[
            AttackSkill(SkillID.GLACIAL_SPIKE, min_mana=8, range=20, aoe=True, cooldown_ms=300),
            AttackSkill(SkillID.ICE_BLAST, min_mana=5, range=20, cooldown_ms=200),
        ],
        prebuffs=[
            AttackSkill(SkillID.FROZEN_ARMOR, precast=True),
            AttackSkill(SkillID.ENERGY_SHIELD, precast=True),
        ],
        use_teleport=True,
        use_static=True,
        static_threshold=50.0,
        clear_radius=30.0,
    )


def lightning_sorc_config() -> CombatConfig:
    """Lightning Sorceress combat config."""
    return CombatConfig(
        primary_attack=[
            AttackSkill(SkillID.LIGHTNING, min_mana=10, range=25, cooldown_ms=250),
        ],
        secondary_attack=[
            AttackSkill(SkillID.CHAIN_LIGHTNING, min_mana=12, range=25, aoe=True, cooldown_ms=300),
        ],
        prebuffs=[
            AttackSkill(SkillID.ENERGY_SHIELD, precast=True),
        ],
        use_teleport=True,
        use_static=True,
        clear_radius=30.0,
    )


# ===================================================================
# Combat engine
# ===================================================================

class CombatEngine:
    """
    Executes combat logic based on a CombatConfig.

    Handles the full attack loop: prebuff, select target, approach,
    attack, and loot cycle.
    """

    def __init__(
        self,
        player: Player,
        sender: PacketSender,
        tracker: GameStateTracker,
        monster_tracker: MonsterTracker,
        config: Optional[CombatConfig] = None,
    ) -> None:
        self._player = player
        self._sender = sender
        self._tracker = tracker
        self._monsters = monster_tracker
        self.config = config or CombatConfig()
        self._prebuffed = False

    # ------------------------------------------------------------------
    # Prebuffing
    # ------------------------------------------------------------------

    def prebuff(self) -> None:
        """Cast all prebuff skills."""
        for skill in self.config.prebuffs:
            if self._player.has_skill(skill.skill_id):
                pos = self._player.position
                self._player.cast_right(skill.skill_id, pos.x, pos.y)
                time.sleep(0.5)
                log.debug("Prebuffed skill %d", skill.skill_id)
        self._prebuffed = True

    # ------------------------------------------------------------------
    # Main combat loop
    # ------------------------------------------------------------------

    def clear_area(self, center: Optional[Position] = None, radius: Optional[float] = None) -> bool:
        """
        Clear all monsters in the specified area.

        If no center is given, uses the player's current position.
        Returns True if the area is clear, False if timed out.
        """
        if not self._prebuffed:
            self.prebuff()

        if center is None:
            center = self._player.position
        if radius is None:
            radius = self.config.clear_radius

        deadline = time.time() + self.config.max_attack_time

        while time.time() < deadline:
            targets = self._monsters.prioritized_targets(self._player.position, radius)
            if not targets:
                log.info("Area clear (radius=%.0f)", radius)
                return True

            target = targets[0]
            self._attack_target(target)
            time.sleep(0.05)

        log.warning("Clear area timed out after %.0fs", self.config.max_attack_time)
        return False

    def kill_target(self, target: MonsterUnit, timeout: float = 30.0) -> bool:
        """Focus a single target until it's dead or timeout."""
        if not self._prebuffed:
            self.prebuff()

        deadline = time.time() + timeout

        while time.time() < deadline:
            # Refresh target from snapshot
            alive = [m for m in self._monsters.alive_monsters if m.unit_id == target.unit_id]
            if not alive:
                log.info("Target %d killed", target.unit_id)
                return True

            self._attack_target(alive[0])
            time.sleep(0.05)

        log.warning("Kill target %d timed out", target.unit_id)
        return False

    def kill_boss(self, boss: MonsterUnit, timeout: float = 60.0) -> bool:
        """Kill an act boss with optional static field usage."""
        if not self._prebuffed:
            self.prebuff()

        deadline = time.time() + timeout

        while time.time() < deadline:
            alive = [m for m in self._monsters.alive_monsters if m.unit_id == boss.unit_id]
            if not alive:
                log.info("Boss killed!")
                return True

            current_boss = alive[0]

            # Use static field if enabled and boss HP is high enough
            if (
                self.config.use_static
                and current_boss.hp_percent > self.config.static_threshold
                and self._player.has_skill(self.config.static_field_id)
            ):
                self._player.cast_right(
                    self.config.static_field_id,
                    current_boss.position.x,
                    current_boss.position.y,
                )
                time.sleep(0.3)
                continue

            self._attack_target(current_boss)
            time.sleep(0.05)

        return False

    # ------------------------------------------------------------------
    # Internal attack logic
    # ------------------------------------------------------------------

    def _attack_target(self, target: MonsterUnit) -> None:
        """Execute a single attack cycle on a target."""
        pos = self._player.position
        t_pos = target.position
        dist = distance(pos.x, pos.y, t_pos.x, t_pos.y)

        # Kiting
        if self.config.kite_distance > 0 and dist < self.config.kite_distance:
            self._kite_from(t_pos)
            return

        # Select best skill
        nearby_count = self._monsters.count_in_range(pos, 15)
        skill = self._select_skill(dist, nearby_count)
        if not skill:
            # Fallback: run toward target
            self._approach_target(target)
            return

        # Check mana
        if self._player.mana < skill.min_mana:
            time.sleep(0.1)  # wait for mana regen / potion
            return

        # Check cooldown
        if not skill._cooldown.trigger_if_ready():
            time.sleep(0.02)
            return

        # Approach if out of range
        if dist > skill.range:
            self._approach_target(target)
            return

        # Cast
        if skill.on_unit:
            self._player.cast_right_on_unit(
                skill.skill_id, UnitType.MONSTER, target.unit_id
            )
        else:
            self._player.cast_right(skill.skill_id, t_pos.x, t_pos.y)

    def _select_skill(self, dist: float, nearby_count: int) -> Optional[AttackSkill]:
        """Select the best attack skill for the current situation."""
        # Try secondary (AoE) if many monsters nearby
        if nearby_count >= 3:
            for skill in self.config.secondary_attack:
                if (
                    skill.aoe
                    and self._player.has_skill(skill.skill_id)
                    and self._player.mana >= skill.min_mana
                ):
                    return skill

        # Primary attack
        for skill in self.config.primary_attack:
            if (
                self._player.has_skill(skill.skill_id)
                and self._player.mana >= skill.min_mana
            ):
                return skill

        # Fallback to any secondary
        for skill in self.config.secondary_attack:
            if (
                self._player.has_skill(skill.skill_id)
                and self._player.mana >= skill.min_mana
            ):
                return skill

        return None

    def _approach_target(self, target: MonsterUnit) -> None:
        """Move toward a target (teleport or run)."""
        t_pos = target.position
        if self.config.use_teleport and self._player.has_skill(self.config.teleport_skill_id):
            self._player.teleport_to(t_pos.x, t_pos.y, self.config.teleport_skill_id)
        else:
            self._sender.run_to(t_pos.x, t_pos.y)
            time.sleep(0.15)

    def _kite_from(self, danger_pos: Position) -> None:
        """Move away from a dangerous position."""
        pos = self._player.position
        # Move in the opposite direction
        dx = pos.x - danger_pos.x
        dy = pos.y - danger_pos.y
        mag = max(1, (dx * dx + dy * dy) ** 0.5)
        kite_x = int(pos.x + dx / mag * self.config.kite_distance)
        kite_y = int(pos.y + dy / mag * self.config.kite_distance)

        if self.config.use_teleport and self._player.has_skill(self.config.teleport_skill_id):
            self._player.teleport_to(kite_x, kite_y)
        else:
            self._sender.run_to(kite_x, kite_y)
            time.sleep(0.2)
