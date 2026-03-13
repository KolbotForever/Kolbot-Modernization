"""
Advanced pickit (item filter) system.

Evaluates ground items against a configurable rule set to decide
whether to pick, identify-then-decide, or ignore each item.

Supports:
- Quality-based rules (pick all uniques, rares with conditions, etc.)
- Stat-based conditions (e.g. "pick rare ring if FCR >= 10 and AllRes >= 15")
- Item type rules (always pick runes >= Lem, keys, essences, etc.)
- Gold threshold
- Tier system for inventory prioritization
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Callable, Optional

from kolbot.core.structures import ItemQuality, ItemUnit, StatID
from kolbot.game.items import ItemClassifier as IC, get_item_code, get_item_name
from kolbot.utils.logger import get_logger

log = get_logger("bot.pickit")


# ===================================================================
# Pickit decision
# ===================================================================

class PickitAction(IntEnum):
    """What to do with a ground item."""
    IGNORE = 0
    PICK = 1
    PICK_IF_ROOM = 2      # pick only if inventory has space
    IDENTIFY_THEN_DECIDE = 3  # pick, identify, then re-evaluate
    SELL = 4               # pick up to sell for gold


# ===================================================================
# Pickit rules
# ===================================================================

@dataclass(slots=True)
class StatCondition:
    """A single stat requirement for an item."""
    stat_id: int
    operator: str   # ">=", "<=", "==", ">", "<", "!="
    value: int

    def evaluate(self, item: ItemUnit) -> bool:
        actual = IC.get_stat(item, self.stat_id)
        match self.operator:
            case ">=":
                return actual >= self.value
            case "<=":
                return actual <= self.value
            case "==":
                return actual == self.value
            case ">":
                return actual > self.value
            case "<":
                return actual < self.value
            case "!=":
                return actual != self.value
        return False


@dataclass(slots=True)
class PickitRule:
    """
    A single pickit rule.

    Matches items by type/quality/code and optionally by stat conditions.
    """
    name: str = ""
    # Match criteria
    item_codes: list[str] = field(default_factory=list)  # empty = match any
    quality: Optional[ItemQuality] = None  # None = match any quality
    ethereal: Optional[bool] = None  # None = don't care
    identified: Optional[bool] = None
    min_sockets: int = 0
    max_sockets: int = 99
    is_runeword: Optional[bool] = None
    # Stat conditions (all must pass)
    conditions: list[StatCondition] = field(default_factory=list)
    # Action
    action: PickitAction = PickitAction.PICK
    # Priority tier (higher = stash first, keep over lower tier)
    tier: int = 0
    # Whether this rule needs the item to be identified first
    needs_id: bool = False

    def matches(self, item: ItemUnit) -> bool:
        """Check if this rule matches the given item."""
        # Item code filter
        if self.item_codes:
            code = get_item_code(item.txt_file_no)
            if code not in self.item_codes:
                return False

        # Quality filter
        if self.quality is not None and item.quality != self.quality:
            return False

        # Ethereal filter
        if self.ethereal is not None and item.is_ethereal != self.ethereal:
            return False

        # Identified filter
        if self.identified is not None and item.is_identified != self.identified:
            return False

        # Runeword filter
        if self.is_runeword is not None and item.is_runeword != self.is_runeword:
            return False

        # Socket filter
        sockets = IC.get_sockets(item)
        if sockets < self.min_sockets or sockets > self.max_sockets:
            return False

        # Stat conditions (only if item is identified)
        if self.conditions:
            if not item.is_identified:
                return self.needs_id  # match to trigger identify-then-decide
            for cond in self.conditions:
                if not cond.evaluate(item):
                    return False

        return True


# ===================================================================
# Pickit engine
# ===================================================================

class PickitEngine:
    """
    Evaluates items against the loaded rule set.

    Usage::

        engine = PickitEngine()
        engine.load_rules("profiles/default/pickit.json")
        for item in ground_items:
            action, rule = engine.evaluate(item)
            if action == PickitAction.PICK:
                pick_item(item)
    """

    def __init__(self) -> None:
        self._rules: list[PickitRule] = []
        self._min_gold: int = 0
        self._min_rune: int = 0  # min rune number to pick (e.g. 20 = Lem)
        self._custom_evaluators: list[Callable[[ItemUnit], Optional[PickitAction]]] = []

    @property
    def rules(self) -> list[PickitRule]:
        return self._rules

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_rules(self, path: str | Path) -> None:
        """Load pickit rules from a JSON file."""
        path = Path(path)
        if not path.exists():
            log.warning("Pickit file not found: %s", path)
            return

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        self._min_gold = data.get("min_gold", 0)
        self._min_rune = data.get("min_rune", 0)

        for entry in data.get("rules", []):
            rule = self._parse_rule(entry)
            self._rules.append(rule)

        log.info("Loaded %d pickit rules from %s", len(self._rules), path)

    def _parse_rule(self, entry: dict) -> PickitRule:
        """Parse a single rule from JSON."""
        rule = PickitRule()
        rule.name = entry.get("name", "")
        rule.item_codes = entry.get("codes", [])
        rule.tier = entry.get("tier", 0)
        rule.needs_id = entry.get("needs_id", False)

        if "quality" in entry:
            rule.quality = ItemQuality(entry["quality"])
        if "ethereal" in entry:
            rule.ethereal = entry["ethereal"]
        if "identified" in entry:
            rule.identified = entry["identified"]
        if "runeword" in entry:
            rule.is_runeword = entry["runeword"]
        if "min_sockets" in entry:
            rule.min_sockets = entry["min_sockets"]
        if "max_sockets" in entry:
            rule.max_sockets = entry["max_sockets"]

        action_str = entry.get("action", "pick")
        rule.action = {
            "pick": PickitAction.PICK,
            "pick_if_room": PickitAction.PICK_IF_ROOM,
            "identify": PickitAction.IDENTIFY_THEN_DECIDE,
            "sell": PickitAction.SELL,
            "ignore": PickitAction.IGNORE,
        }.get(action_str, PickitAction.PICK)

        for cond_entry in entry.get("conditions", []):
            stat_name = cond_entry.get("stat", "")
            stat_id = _STAT_NAME_MAP.get(stat_name.lower(), -1)
            if stat_id < 0:
                try:
                    stat_id = int(stat_name)
                except ValueError:
                    log.warning("Unknown stat name: %s", stat_name)
                    continue
            cond = StatCondition(
                stat_id=stat_id,
                operator=cond_entry.get("op", ">="),
                value=cond_entry.get("value", 0),
            )
            rule.conditions.append(cond)

        return rule

    def add_rule(self, rule: PickitRule) -> None:
        """Add a rule programmatically."""
        self._rules.append(rule)

    def add_custom_evaluator(self, evaluator: Callable[[ItemUnit], Optional[PickitAction]]) -> None:
        """Add a custom evaluation function that runs before rules."""
        self._custom_evaluators.append(evaluator)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(self, item: ItemUnit) -> tuple[PickitAction, Optional[PickitRule]]:
        """
        Evaluate an item against all rules.

        Returns (action, matching_rule).  The first matching rule wins.
        If no rule matches, returns (IGNORE, None).
        """
        # Built-in checks first
        builtin = self._builtin_check(item)
        if builtin is not None:
            return (builtin, None)

        # Custom evaluators
        for evaluator in self._custom_evaluators:
            result = evaluator(item)
            if result is not None:
                return (result, None)

        # Rule-based evaluation (first match wins)
        for rule in self._rules:
            if rule.matches(item):
                log.debug(
                    "Item %d matched rule '%s' -> %s",
                    item.unit_id, rule.name, rule.action.name,
                )
                return (rule.action, rule)

        return (PickitAction.IGNORE, None)

    def should_keep(self, item: ItemUnit) -> bool:
        """
        Re-evaluate an item after identification.

        Used for IDENTIFY_THEN_DECIDE: if no rule matches the identified
        item, it should be dropped or sold.
        """
        action, _ = self.evaluate(item)
        return action in (PickitAction.PICK, PickitAction.PICK_IF_ROOM)

    def get_tier(self, item: ItemUnit) -> int:
        """Get the priority tier for a matched item."""
        for rule in self._rules:
            if rule.matches(item):
                return rule.tier
        return -1

    # ------------------------------------------------------------------
    # Built-in checks
    # ------------------------------------------------------------------

    def _builtin_check(self, item: ItemUnit) -> Optional[PickitAction]:
        """Built-in checks that don't need rules."""
        # Gold
        if IC.is_gold(item):
            gold_amount = IC.get_stat(item, StatID.GOLD)
            if gold_amount >= self._min_gold:
                return PickitAction.PICK
            return PickitAction.IGNORE

        # Runes
        if IC.is_rune(item):
            rune_num = IC.get_rune_number(item)
            if rune_num >= self._min_rune:
                return PickitAction.PICK
            return PickitAction.IGNORE

        # Keys, essences, organs — always pick
        if IC.is_key(item) or IC.is_essence(item) or IC.is_uber_organ(item):
            return PickitAction.PICK

        return None  # defer to rules


# ===================================================================
# Stat name -> StatID mapping for rule parsing
# ===================================================================

_STAT_NAME_MAP: dict[str, int] = {
    "strength": StatID.STRENGTH,
    "str": StatID.STRENGTH,
    "energy": StatID.ENERGY,
    "dexterity": StatID.DEXTERITY,
    "dex": StatID.DEXTERITY,
    "vitality": StatID.VITALITY,
    "vit": StatID.VITALITY,
    "hp": StatID.HP,
    "life": StatID.HP,
    "max_hp": StatID.MAX_HP,
    "mana": StatID.MANA,
    "max_mana": StatID.MAX_MANA,
    "level": StatID.LEVEL,
    "defense": StatID.DEFENSE,
    "enhanced_damage": StatID.ENHANCED_DAMAGE,
    "ed": StatID.ENHANCED_DAMAGE,
    "enhanced_defense": StatID.ENHANCED_DEFENSE,
    "attack_rating": StatID.ATTACK_RATING,
    "ar": StatID.ATTACK_RATING,
    "magic_find": StatID.MAGIC_FIND,
    "mf": StatID.MAGIC_FIND,
    "gold_find": StatID.GOLD_FIND,
    "gf": StatID.GOLD_FIND,
    "fire_resist": StatID.FIRE_RESIST,
    "fire_res": StatID.FIRE_RESIST,
    "cold_resist": StatID.COLD_RESIST,
    "cold_res": StatID.COLD_RESIST,
    "lightning_resist": StatID.LIGHTNING_RESIST,
    "light_res": StatID.LIGHTNING_RESIST,
    "poison_resist": StatID.POISON_RESIST,
    "poison_res": StatID.POISON_RESIST,
    "fcr": StatID.FASTER_CAST_RATE,
    "faster_cast_rate": StatID.FASTER_CAST_RATE,
    "fhr": StatID.FASTER_HIT_RECOVERY,
    "faster_hit_recovery": StatID.FASTER_HIT_RECOVERY,
    "frw": StatID.FASTER_RUN_WALK,
    "faster_run_walk": StatID.FASTER_RUN_WALK,
    "ias": StatID.INCREASED_ATTACK_SPEED,
    "increased_attack_speed": StatID.INCREASED_ATTACK_SPEED,
    "sockets": StatID.SOCKETS,
    "all_skills": StatID.ITEM_ALL_SKILLS,
    "class_skills": StatID.ITEM_CLASS_SKILLS,
    "crushing_blow": StatID.CRUSHING_BLOW,
    "cb": StatID.CRUSHING_BLOW,
    "deadly_strike": StatID.DEADLY_STRIKE,
    "ds": StatID.DEADLY_STRIKE,
    "open_wounds": StatID.OPEN_WOUNDS,
    "ow": StatID.OPEN_WOUNDS,
    "life_leech": StatID.LIFE_LEECH,
    "ll": StatID.LIFE_LEECH,
    "mana_leech": StatID.MANA_LEECH,
    "ml": StatID.MANA_LEECH,
    "cannot_be_frozen": StatID.CANNOT_BE_FROZEN,
    "cbf": StatID.CANNOT_BE_FROZEN,
}


# ===================================================================
# Default rules factory (creates a sensible starter config)
# ===================================================================

def create_default_rules() -> list[PickitRule]:
    """Create a default set of pickit rules for general MF botting."""
    rules: list[PickitRule] = []

    # All unique items
    rules.append(PickitRule(
        name="All Uniques",
        quality=ItemQuality.UNIQUE,
        action=PickitAction.PICK,
        tier=10,
    ))

    # All set items
    rules.append(PickitRule(
        name="All Set Items",
        quality=ItemQuality.SET,
        action=PickitAction.PICK,
        tier=9,
    ))

    # Rare rings — identify then check stats
    rules.append(PickitRule(
        name="Rare Rings (ID Check)",
        item_codes=["rin"],
        quality=ItemQuality.RARE,
        action=PickitAction.IDENTIFY_THEN_DECIDE,
        needs_id=True,
        tier=7,
        conditions=[
            StatCondition(StatID.FASTER_CAST_RATE, ">=", 10),
        ],
    ))

    # Rare amulets — identify then check
    rules.append(PickitRule(
        name="Rare Amulets (ID Check)",
        item_codes=["amu"],
        quality=ItemQuality.RARE,
        action=PickitAction.IDENTIFY_THEN_DECIDE,
        needs_id=True,
        tier=7,
        conditions=[
            StatCondition(StatID.ITEM_ALL_SKILLS, ">=", 2),
        ],
    ))

    # Rare jewels — always ID
    rules.append(PickitRule(
        name="Rare Jewels",
        item_codes=["jew"],
        quality=ItemQuality.RARE,
        action=PickitAction.IDENTIFY_THEN_DECIDE,
        needs_id=True,
        tier=6,
    ))

    # Grand charms — identify
    rules.append(PickitRule(
        name="Grand Charms",
        item_codes=["cm3"],
        quality=ItemQuality.MAGIC,
        action=PickitAction.IDENTIFY_THEN_DECIDE,
        needs_id=True,
        tier=6,
    ))

    # Small charms — identify
    rules.append(PickitRule(
        name="Small Charms",
        item_codes=["cm1"],
        quality=ItemQuality.MAGIC,
        action=PickitAction.IDENTIFY_THEN_DECIDE,
        needs_id=True,
        tier=5,
    ))

    # Rejuv potions — always pick
    rules.append(PickitRule(
        name="Rejuv Potions",
        item_codes=["rvs", "rvl"],
        action=PickitAction.PICK_IF_ROOM,
        tier=1,
    ))

    return rules
