"""
Item management: identification, classification, stat checking.

Provides helpers to look up item base types, check quality/stats, and
classify items for the pickit system.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from kolbot.core.structures import (
    ItemFlag,
    ItemLocation,
    ItemQuality,
    ItemUnit,
    StatEntry,
    StatID,
)
from kolbot.utils.logger import get_logger

log = get_logger("game.items")

# ---------------------------------------------------------------------------
# Item code → name database (loaded from data/items.json)
# ---------------------------------------------------------------------------

_ITEM_DB: dict[int, dict] = {}
_DB_LOADED = False


def _load_item_db() -> None:
    global _ITEM_DB, _DB_LOADED
    if _DB_LOADED:
        return
    db_path = Path(__file__).resolve().parents[2] / "data" / "items.json"
    if db_path.exists():
        with open(db_path, encoding="utf-8") as f:
            raw = json.load(f)
        for entry in raw:
            _ITEM_DB[entry["id"]] = entry
    _DB_LOADED = True
    log.debug("Loaded %d item definitions", len(_ITEM_DB))


def get_item_info(txt_file_no: int) -> dict:
    """Look up item base info by txt_file_no."""
    _load_item_db()
    return _ITEM_DB.get(txt_file_no, {})


def get_item_name(txt_file_no: int) -> str:
    info = get_item_info(txt_file_no)
    return info.get("name", f"Unknown({txt_file_no})")


def get_item_code(txt_file_no: int) -> str:
    info = get_item_info(txt_file_no)
    return info.get("code", "")


# ---------------------------------------------------------------------------
# Item classification helpers
# ---------------------------------------------------------------------------

# Rune txt_file_no ranges (El=610, Zod=642)
RUNE_MIN = 610
RUNE_MAX = 642

# Gem txt_file_no ranges
GEM_MIN = 557
GEM_MAX = 601

# Key IDs
KEY_OF_TERROR = 647
KEY_OF_HATE = 648
KEY_OF_DESTRUCTION = 649

# Essence IDs
TWISTED_ESSENCE = 650
CHARGED_ESSENCE = 651
BURNING_ESSENCE = 652
FESTERING_ESSENCE = 653

# Token of Absolution
TOKEN_OF_ABSOLUTION = 654

# Uber organs
DIABLOS_HORN = 655
BAALS_EYE = 656
MEPHIS_BRAIN = 657


class ItemClassifier:
    """Utility class for classifying items by type, quality, and value."""

    @staticmethod
    def is_rune(item: ItemUnit) -> bool:
        return RUNE_MIN <= item.txt_file_no <= RUNE_MAX

    @staticmethod
    def get_rune_number(item: ItemUnit) -> int:
        """Get rune number (1=El, 33=Zod). Returns 0 if not a rune."""
        if not ItemClassifier.is_rune(item):
            return 0
        return item.txt_file_no - RUNE_MIN + 1

    @staticmethod
    def is_gem(item: ItemUnit) -> bool:
        return GEM_MIN <= item.txt_file_no <= GEM_MAX

    @staticmethod
    def is_key(item: ItemUnit) -> bool:
        return item.txt_file_no in (KEY_OF_TERROR, KEY_OF_HATE, KEY_OF_DESTRUCTION)

    @staticmethod
    def is_essence(item: ItemUnit) -> bool:
        return item.txt_file_no in (
            TWISTED_ESSENCE, CHARGED_ESSENCE, BURNING_ESSENCE, FESTERING_ESSENCE
        )

    @staticmethod
    def is_uber_organ(item: ItemUnit) -> bool:
        return item.txt_file_no in (DIABLOS_HORN, BAALS_EYE, MEPHIS_BRAIN)

    @staticmethod
    def is_unique(item: ItemUnit) -> bool:
        return item.quality == ItemQuality.UNIQUE

    @staticmethod
    def is_set(item: ItemUnit) -> bool:
        return item.quality == ItemQuality.SET

    @staticmethod
    def is_rare(item: ItemUnit) -> bool:
        return item.quality == ItemQuality.RARE

    @staticmethod
    def is_magic(item: ItemUnit) -> bool:
        return item.quality == ItemQuality.MAGIC

    @staticmethod
    def is_runeword(item: ItemUnit) -> bool:
        return item.is_runeword

    @staticmethod
    def is_ethereal(item: ItemUnit) -> bool:
        return item.is_ethereal

    @staticmethod
    def is_identified(item: ItemUnit) -> bool:
        return item.is_identified

    @staticmethod
    def is_gold(item: ItemUnit) -> bool:
        """Check if item is a gold pile."""
        return item.txt_file_no == 523  # Gold small/medium/large

    @staticmethod
    def is_potion(item: ItemUnit) -> bool:
        """Check if item is any type of potion."""
        code = get_item_code(item.txt_file_no)
        return code.startswith(("hp", "mp", "rv", "ap"))  # health, mana, rejuv, antidote

    @staticmethod
    def is_health_potion(item: ItemUnit) -> bool:
        code = get_item_code(item.txt_file_no)
        return code.startswith("hp")

    @staticmethod
    def is_mana_potion(item: ItemUnit) -> bool:
        code = get_item_code(item.txt_file_no)
        return code.startswith("mp")

    @staticmethod
    def is_rejuv_potion(item: ItemUnit) -> bool:
        code = get_item_code(item.txt_file_no)
        return code in ("rvs", "rvl")

    @staticmethod
    def is_scroll(item: ItemUnit) -> bool:
        code = get_item_code(item.txt_file_no)
        return code in ("tsc", "isc")  # town portal scroll, identify scroll

    @staticmethod
    def is_tp_scroll(item: ItemUnit) -> bool:
        return get_item_code(item.txt_file_no) == "tsc"

    @staticmethod
    def is_id_scroll(item: ItemUnit) -> bool:
        return get_item_code(item.txt_file_no) == "isc"

    @staticmethod
    def is_charm(item: ItemUnit) -> bool:
        code = get_item_code(item.txt_file_no)
        return code in ("cm1", "cm2", "cm3")  # small, large, grand charm

    @staticmethod
    def is_small_charm(item: ItemUnit) -> bool:
        return get_item_code(item.txt_file_no) == "cm1"

    @staticmethod
    def is_grand_charm(item: ItemUnit) -> bool:
        return get_item_code(item.txt_file_no) == "cm3"

    @staticmethod
    def is_jewel(item: ItemUnit) -> bool:
        return get_item_code(item.txt_file_no) == "jew"

    @staticmethod
    def is_amulet(item: ItemUnit) -> bool:
        return get_item_code(item.txt_file_no) == "amu"

    @staticmethod
    def is_ring(item: ItemUnit) -> bool:
        return get_item_code(item.txt_file_no) == "rin"

    # ------------------------------------------------------------------
    # Stat helpers on items
    # ------------------------------------------------------------------

    @staticmethod
    def get_stat(item: ItemUnit, stat_id: int, layer: int = 0) -> int:
        """Get a stat value from an item's stat list."""
        for s in item.stats:
            if s.stat_id == stat_id and s.layer == layer:
                return s.value
        return 0

    @staticmethod
    def has_stat(item: ItemUnit, stat_id: int) -> bool:
        return any(s.stat_id == stat_id for s in item.stats)

    @staticmethod
    def get_sockets(item: ItemUnit) -> int:
        return ItemClassifier.get_stat(item, StatID.SOCKETS)

    @staticmethod
    def get_enhanced_damage(item: ItemUnit) -> int:
        return ItemClassifier.get_stat(item, StatID.ENHANCED_DAMAGE)

    @staticmethod
    def get_enhanced_defense(item: ItemUnit) -> int:
        return ItemClassifier.get_stat(item, StatID.ENHANCED_DEFENSE)

    @staticmethod
    def get_all_skills(item: ItemUnit) -> int:
        return ItemClassifier.get_stat(item, StatID.ITEM_ALL_SKILLS)

    @staticmethod
    def get_fcr(item: ItemUnit) -> int:
        return ItemClassifier.get_stat(item, StatID.FASTER_CAST_RATE)

    @staticmethod
    def get_fhr(item: ItemUnit) -> int:
        return ItemClassifier.get_stat(item, StatID.FASTER_HIT_RECOVERY)

    @staticmethod
    def get_frw(item: ItemUnit) -> int:
        return ItemClassifier.get_stat(item, StatID.FASTER_RUN_WALK)

    @staticmethod
    def get_ias(item: ItemUnit) -> int:
        return ItemClassifier.get_stat(item, StatID.INCREASED_ATTACK_SPEED)

    @staticmethod
    def get_mf(item: ItemUnit) -> int:
        return ItemClassifier.get_stat(item, StatID.MAGIC_FIND)

    @staticmethod
    def get_life(item: ItemUnit) -> int:
        return ItemClassifier.get_stat(item, StatID.HP) >> 8

    @staticmethod
    def get_all_res(item: ItemUnit) -> int:
        """Get minimum of all four resistances."""
        fr = ItemClassifier.get_stat(item, StatID.FIRE_RESIST)
        cr = ItemClassifier.get_stat(item, StatID.COLD_RESIST)
        lr = ItemClassifier.get_stat(item, StatID.LIGHTNING_RESIST)
        pr = ItemClassifier.get_stat(item, StatID.POISON_RESIST)
        return min(fr, cr, lr, pr)


# Convenience alias
IC = ItemClassifier
