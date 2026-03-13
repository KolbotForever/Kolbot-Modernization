"""
Example Pickit Script — Advanced Item Filtering

This script demonstrates the pickit system by defining a comprehensive
set of item filtering rules for a typical Hell difficulty bot.

Usage:
    kolbot script scripts/example_pickit.py --pid <Game.exe PID>

Or load via the autoplay controller by placing in your profile's
scripts/ directory.
"""

from kolbot.bot.pickit import (
    PickitAction,
    PickitEngine,
    PickitRule,
    StatCondition,
)
from kolbot.core.structures import ItemQuality, StatID


def main():
    """Build and demonstrate an advanced pickit ruleset."""
    pickit = PickitEngine()

    # ===================================================================
    # RUNES — Always pick high runes, conditionally pick mid runes
    # ===================================================================
    pickit.min_rune = 15  # Pick Hel+ (rune index 15 = Hel)

    # ===================================================================
    # GOLD — Pick gold piles above threshold
    # ===================================================================
    pickit.min_gold = 5000

    # ===================================================================
    # UNIQUE ITEMS — Always pick, identify, then decide
    # ===================================================================

    # Top-tier unique items (always keep)
    pickit.add_rule(PickitRule(
        name="Unique Rings",
        quality=ItemQuality.UNIQUE,
        item_codes=["rin"],
        action=PickitAction.PICK,
        tier=100,
    ))

    pickit.add_rule(PickitRule(
        name="Unique Amulets",
        quality=ItemQuality.UNIQUE,
        item_codes=["amu"],
        action=PickitAction.PICK,
        tier=100,
    ))

    pickit.add_rule(PickitRule(
        name="Unique Small Charms",
        quality=ItemQuality.UNIQUE,
        item_codes=["cm1"],
        action=PickitAction.PICK,
        tier=90,  # Annihilus, Gheed's, Torch
    ))

    pickit.add_rule(PickitRule(
        name="Unique Grand Charms",
        quality=ItemQuality.UNIQUE,
        item_codes=["cm3"],
        action=PickitAction.PICK,
        tier=85,  # Skillers
    ))

    # Unique weapons/armor — identify first
    pickit.add_rule(PickitRule(
        name="Unique Weapons",
        quality=ItemQuality.UNIQUE,
        action=PickitAction.IDENTIFY_THEN_DECIDE,
        needs_id=True,
        tier=50,
    ))

    # ===================================================================
    # SET ITEMS — Always pick elite sets
    # ===================================================================

    pickit.add_rule(PickitRule(
        name="Set Rings",
        quality=ItemQuality.SET,
        item_codes=["rin"],
        action=PickitAction.PICK,
        tier=80,
    ))

    pickit.add_rule(PickitRule(
        name="Set Amulets",
        quality=ItemQuality.SET,
        item_codes=["amu"],
        action=PickitAction.PICK,
        tier=80,
    ))

    pickit.add_rule(PickitRule(
        name="Other Set Items",
        quality=ItemQuality.SET,
        action=PickitAction.IDENTIFY_THEN_DECIDE,
        needs_id=True,
        tier=40,
    ))

    # ===================================================================
    # RARE ITEMS — Pick jewelry and charms, identify armor/weapons
    # ===================================================================

    pickit.add_rule(PickitRule(
        name="Rare Rings",
        quality=ItemQuality.RARE,
        item_codes=["rin"],
        action=PickitAction.PICK,
        tier=70,
    ))

    pickit.add_rule(PickitRule(
        name="Rare Amulets",
        quality=ItemQuality.RARE,
        item_codes=["amu"],
        action=PickitAction.PICK,
        tier=70,
    ))

    pickit.add_rule(PickitRule(
        name="Rare Jewels",
        quality=ItemQuality.RARE,
        item_codes=["jew"],
        action=PickitAction.PICK,
        tier=60,
    ))

    # Rare boots with useful stats
    pickit.add_rule(PickitRule(
        name="Rare Boots (MF/FRW/Res)",
        quality=ItemQuality.RARE,
        item_codes=["lbt", "vbt", "mbt", "tbt", "hbt"],
        action=PickitAction.IDENTIFY_THEN_DECIDE,
        needs_id=True,
        conditions=[
            StatCondition(stat=StatID.FASTER_RUN_WALK, operator=">=", value=20),
        ],
        tier=55,
    ))

    # Rare circlets (potential GG items)
    pickit.add_rule(PickitRule(
        name="Rare Circlets",
        quality=ItemQuality.RARE,
        item_codes=["ci0", "ci1", "ci2", "ci3"],
        action=PickitAction.IDENTIFY_THEN_DECIDE,
        needs_id=True,
        tier=60,
    ))

    # ===================================================================
    # MAGIC ITEMS — Charms only
    # ===================================================================

    # Small charms with 20 life, 5 all res, 7 MF, or 3/20/20
    pickit.add_rule(PickitRule(
        name="Magic Small Charms",
        quality=ItemQuality.MAGIC,
        item_codes=["cm1"],
        action=PickitAction.IDENTIFY_THEN_DECIDE,
        needs_id=True,
        tier=45,
    ))

    # Grand charms (skillers)
    pickit.add_rule(PickitRule(
        name="Magic Grand Charms",
        quality=ItemQuality.MAGIC,
        item_codes=["cm3"],
        action=PickitAction.IDENTIFY_THEN_DECIDE,
        needs_id=True,
        tier=45,
    ))

    # ===================================================================
    # RUNEWORDS — Pick 4-socket items for runeword bases
    # ===================================================================

    pickit.add_rule(PickitRule(
        name="4os Monarch",
        item_codes=["mon"],
        min_sockets=4,
        max_sockets=4,
        quality=ItemQuality.NORMAL,
        action=PickitAction.PICK,
        tier=60,
    ))

    pickit.add_rule(PickitRule(
        name="4os Crystal Sword (Spirit base)",
        item_codes=["crs"],
        min_sockets=4,
        max_sockets=4,
        quality=ItemQuality.NORMAL,
        action=PickitAction.PICK,
        tier=55,
    ))

    pickit.add_rule(PickitRule(
        name="Eth 4os Thresher/CV (Insight base)",
        item_codes=["7s8", "7pa"],
        min_sockets=4,
        max_sockets=4,
        ethereal=True,
        quality=ItemQuality.NORMAL,
        action=PickitAction.PICK,
        tier=65,
    ))

    # ===================================================================
    # POTIONS — Always pick full rejuvs
    # ===================================================================

    pickit.add_rule(PickitRule(
        name="Full Rejuvenation Potions",
        item_codes=["rvl"],
        action=PickitAction.PICK,
        tier=10,
    ))

    # ===================================================================
    # CUSTOM EVALUATOR — Complex logic that rules can't express
    # ===================================================================

    def custom_charm_evaluator(item) -> tuple[PickitAction, int]:
        """
        Custom evaluator for identified charms.

        Keeps small charms with:
        - 20 life
        - 5 all res
        - 7% MF
        - 3% FRW + 20 AR + 20 life

        Keeps grand charms with:
        - +1 skill tree + life
        """
        stats = {s.stat_id: s.value for s in item.stats}

        # Small charm evaluation
        if item.item_code == "cm1":
            life = stats.get(StatID.HP, 0) >> 8
            all_res = min(
                stats.get(StatID.FIRE_RESIST, 0),
                stats.get(StatID.COLD_RESIST, 0),
                stats.get(StatID.LIGHTNING_RESIST, 0),
                stats.get(StatID.POISON_RESIST, 0),
            )
            mf = stats.get(StatID.MAGIC_FIND, 0)

            if life >= 20:
                return PickitAction.PICK, 80
            if all_res >= 5:
                return PickitAction.PICK, 75
            if mf >= 7:
                return PickitAction.PICK, 70

        # Grand charm evaluation
        if item.item_code == "cm3":
            # Check for skill tree bonus (stat 188 = add_skill_tab)
            if StatID.ADD_SKILL_TAB in stats:
                life = stats.get(StatID.HP, 0) >> 8
                if life >= 30:
                    return PickitAction.PICK, 90  # Skiller with life
                return PickitAction.PICK, 70  # Plain skiller

        return PickitAction.IGNORE, 0

    pickit.add_custom_evaluator(custom_charm_evaluator)

    # ===================================================================
    # Print rules summary
    # ===================================================================
    print(f"Loaded {len(pickit._rules)} pickit rules")
    print(f"Min rune index: {pickit.min_rune}")
    print(f"Min gold: {pickit.min_gold}")

    for rule in pickit._rules:
        codes = ", ".join(rule.item_codes) if rule.item_codes else "*"
        quality = rule.quality.name if rule.quality else "any"
        print(f"  [{rule.action.name}] {rule.name} "
              f"(quality={quality}, codes={codes}, tier={rule.tier})")

    return pickit


if __name__ == "__main__":
    main()
