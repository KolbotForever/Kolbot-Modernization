"""
Map and area data.

Provides area ID constants, waypoint mappings, act boundaries, and
helpers for area-based navigation decisions.
"""

from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from kolbot.utils.logger import get_logger

log = get_logger("game.map")


# ===================================================================
# Area IDs (all 136 areas in LoD)
# ===================================================================

class Area:
    """Diablo II area ID constants."""
    # --- Act 1 ---
    ROGUE_ENCAMPMENT = 1
    BLOOD_MOOR = 2
    COLD_PLAINS = 3
    STONY_FIELD = 4
    DARK_WOOD = 5
    BLACK_MARSH = 6
    TAMOE_HIGHLAND = 7
    DEN_OF_EVIL = 8
    CAVE_LEVEL_1 = 9
    UNDERGROUND_PASSAGE_LEVEL_1 = 10
    HOLE_LEVEL_1 = 11
    PIT_LEVEL_1 = 12
    PIT_LEVEL_2 = 13
    BURIAL_GROUNDS = 17
    CRYPT = 18
    MAUSOLEUM = 19
    TOWER_CELLAR_LEVEL_1 = 20
    TOWER_CELLAR_LEVEL_2 = 21
    TOWER_CELLAR_LEVEL_3 = 22
    TOWER_CELLAR_LEVEL_4 = 23
    TOWER_CELLAR_LEVEL_5 = 24
    TRISTRAM = 28
    MOO_MOO_FARM = 39
    MONASTERY_GATE = 25
    OUTER_CLOISTER = 26
    BARRACKS = 27
    JAIL_LEVEL_1 = 29
    JAIL_LEVEL_2 = 30
    JAIL_LEVEL_3 = 31
    INNER_CLOISTER = 32
    CATHEDRAL = 33
    CATACOMBS_LEVEL_1 = 34
    CATACOMBS_LEVEL_2 = 35
    CATACOMBS_LEVEL_3 = 36
    CATACOMBS_LEVEL_4 = 37  # Andariel

    # --- Act 2 ---
    LUT_GHOLEIN = 40
    ROCKY_WASTE = 41
    DRY_HILLS = 42
    FAR_OASIS = 43
    LOST_CITY = 44
    VALLEY_OF_SNAKES = 45
    CANYON_OF_THE_MAGI = 46
    SEWERS_LEVEL_1_A2 = 47
    SEWERS_LEVEL_2_A2 = 48
    SEWERS_LEVEL_3_A2 = 49
    HAREM_LEVEL_1 = 50
    HAREM_LEVEL_2 = 51
    PALACE_CELLAR_LEVEL_1 = 52
    PALACE_CELLAR_LEVEL_2 = 53
    PALACE_CELLAR_LEVEL_3 = 54
    STONY_TOMB_LEVEL_1 = 55
    HALLS_OF_THE_DEAD_LEVEL_1 = 56
    HALLS_OF_THE_DEAD_LEVEL_2 = 57
    HALLS_OF_THE_DEAD_LEVEL_3 = 58
    CLAW_VIPER_TEMPLE_LEVEL_1 = 59
    CLAW_VIPER_TEMPLE_LEVEL_2 = 60
    MAGGOT_LAIR_LEVEL_1 = 62
    MAGGOT_LAIR_LEVEL_2 = 63
    MAGGOT_LAIR_LEVEL_3 = 64
    ANCIENT_TUNNELS = 65
    TAL_RASHAS_TOMB_1 = 66
    TAL_RASHAS_TOMB_2 = 67
    TAL_RASHAS_TOMB_3 = 68
    TAL_RASHAS_TOMB_4 = 69
    TAL_RASHAS_TOMB_5 = 70
    TAL_RASHAS_TOMB_6 = 71
    TAL_RASHAS_TOMB_7 = 72
    TAL_RASHAS_CHAMBER = 73  # Duriel
    ARCANE_SANCTUARY = 74

    # --- Act 3 ---
    KURAST_DOCKTOWN = 75
    SPIDER_FOREST = 76
    GREAT_MARSH = 77
    FLAYER_JUNGLE = 78
    LOWER_KURAST = 79
    KURAST_BAZAAR = 80
    UPPER_KURAST = 81
    KURAST_CAUSEWAY = 82
    TRAVINCAL = 83
    SPIDER_CAVE = 84
    SPIDER_CAVERN = 85
    SWAMPY_PIT_LEVEL_1 = 86
    SWAMPY_PIT_LEVEL_2 = 87
    FLAYER_DUNGEON_LEVEL_1 = 88
    FLAYER_DUNGEON_LEVEL_2 = 89
    SWAMPY_PIT_LEVEL_3 = 90
    FLAYER_DUNGEON_LEVEL_3 = 91
    SEWERS_LEVEL_1_A3 = 92
    SEWERS_LEVEL_2_A3 = 93
    RUINED_TEMPLE = 94
    DISUSED_FANE = 95
    FORGOTTEN_RELIQUARY = 96
    FORGOTTEN_TEMPLE = 97
    RUINED_FANE = 98
    DISUSED_RELIQUARY = 99
    DURANCE_OF_HATE_LEVEL_1 = 100
    DURANCE_OF_HATE_LEVEL_2 = 101
    DURANCE_OF_HATE_LEVEL_3 = 102  # Mephisto

    # --- Act 4 ---
    PANDEMONIUM_FORTRESS = 103
    OUTER_STEPPES = 104
    PLAINS_OF_DESPAIR = 105
    CITY_OF_THE_DAMNED = 106
    RIVER_OF_FLAME = 107
    CHAOS_SANCTUARY = 108  # Diablo

    # --- Act 5 ---
    HARROGATH = 109
    BLOODY_FOOTHILLS = 110
    FRIGID_HIGHLANDS = 111
    ARREAT_PLATEAU = 112
    CRYSTALLINE_PASSAGE = 113
    FROZEN_RIVER = 114
    GLACIAL_TRAIL = 115
    DRIFTER_CAVERN = 116
    FROZEN_TUNDRA = 117
    ANCIENTS_WAY = 118
    ICY_CELLAR = 119
    ARREAT_SUMMIT = 120
    NIHLATHAKS_TEMPLE = 121
    HALLS_OF_ANGUISH = 122
    HALLS_OF_PAIN = 123
    HALLS_OF_VAUGHT = 124  # Nihlathak
    ABADDON = 125
    PIT_OF_ACHERON = 126
    INFERNAL_PIT = 127
    WORLDSTONE_KEEP_LEVEL_1 = 128
    WORLDSTONE_KEEP_LEVEL_2 = 129
    WORLDSTONE_KEEP_LEVEL_3 = 130
    THRONE_OF_DESTRUCTION = 131  # Baal's throne
    WORLDSTONE_CHAMBER = 132  # Baal fight

    # --- Uber / Special ---
    MATRONS_DEN = 133
    FORGOTTEN_SANDS = 134
    FURNACE_OF_PAIN = 135
    UBER_TRISTRAM = 136


# ===================================================================
# Town area IDs
# ===================================================================

TOWN_AREAS = frozenset({
    Area.ROGUE_ENCAMPMENT,
    Area.LUT_GHOLEIN,
    Area.KURAST_DOCKTOWN,
    Area.PANDEMONIUM_FORTRESS,
    Area.HARROGATH,
})


def is_town(area_id: int) -> bool:
    """Check if an area ID corresponds to a town."""
    return area_id in TOWN_AREAS


def get_act(area_id: int) -> int:
    """Get the act number (1-5) for an area ID."""
    if area_id <= 39:
        return 1
    elif area_id <= 74:
        return 2
    elif area_id <= 102:
        return 3
    elif area_id <= 108:
        return 4
    else:
        return 5


def get_town_for_act(act: int) -> int:
    """Get the town area ID for a given act."""
    return {
        1: Area.ROGUE_ENCAMPMENT,
        2: Area.LUT_GHOLEIN,
        3: Area.KURAST_DOCKTOWN,
        4: Area.PANDEMONIUM_FORTRESS,
        5: Area.HARROGATH,
    }.get(act, Area.ROGUE_ENCAMPMENT)


# ===================================================================
# Waypoint mappings
# ===================================================================

@dataclass(frozen=True, slots=True)
class WaypointInfo:
    """Waypoint metadata."""
    area_id: int
    wp_index: int  # index in the waypoint menu
    name: str


# All waypoints in order
WAYPOINTS: list[WaypointInfo] = [
    # Act 1
    WaypointInfo(Area.ROGUE_ENCAMPMENT, 0, "Rogue Encampment"),
    WaypointInfo(Area.COLD_PLAINS, 1, "Cold Plains"),
    WaypointInfo(Area.STONY_FIELD, 2, "Stony Field"),
    WaypointInfo(Area.DARK_WOOD, 3, "Dark Wood"),
    WaypointInfo(Area.BLACK_MARSH, 4, "Black Marsh"),
    WaypointInfo(Area.OUTER_CLOISTER, 5, "Outer Cloister"),
    WaypointInfo(Area.JAIL_LEVEL_1, 6, "Jail Level 1"),
    WaypointInfo(Area.INNER_CLOISTER, 7, "Inner Cloister"),
    WaypointInfo(Area.CATACOMBS_LEVEL_2, 8, "Catacombs Level 2"),
    # Act 2
    WaypointInfo(Area.LUT_GHOLEIN, 9, "Lut Gholein"),
    WaypointInfo(Area.SEWERS_LEVEL_2_A2, 10, "Sewers Level 2"),
    WaypointInfo(Area.DRY_HILLS, 11, "Dry Hills"),
    WaypointInfo(Area.HALLS_OF_THE_DEAD_LEVEL_2, 12, "Halls of the Dead Level 2"),
    WaypointInfo(Area.FAR_OASIS, 13, "Far Oasis"),
    WaypointInfo(Area.LOST_CITY, 14, "Lost City"),
    WaypointInfo(Area.PALACE_CELLAR_LEVEL_1, 15, "Palace Cellar Level 1"),
    WaypointInfo(Area.ARCANE_SANCTUARY, 16, "Arcane Sanctuary"),
    WaypointInfo(Area.CANYON_OF_THE_MAGI, 17, "Canyon of the Magi"),
    # Act 3
    WaypointInfo(Area.KURAST_DOCKTOWN, 18, "Kurast Docks"),
    WaypointInfo(Area.SPIDER_FOREST, 19, "Spider Forest"),
    WaypointInfo(Area.GREAT_MARSH, 20, "Great Marsh"),
    WaypointInfo(Area.FLAYER_JUNGLE, 21, "Flayer Jungle"),
    WaypointInfo(Area.LOWER_KURAST, 22, "Lower Kurast"),
    WaypointInfo(Area.KURAST_BAZAAR, 23, "Kurast Bazaar"),
    WaypointInfo(Area.UPPER_KURAST, 24, "Upper Kurast"),
    WaypointInfo(Area.TRAVINCAL, 25, "Travincal"),
    WaypointInfo(Area.DURANCE_OF_HATE_LEVEL_2, 26, "Durance of Hate Level 2"),
    # Act 4
    WaypointInfo(Area.PANDEMONIUM_FORTRESS, 27, "Pandemonium Fortress"),
    WaypointInfo(Area.CITY_OF_THE_DAMNED, 28, "City of the Damned"),
    WaypointInfo(Area.RIVER_OF_FLAME, 29, "River of Flame"),
    # Act 5
    WaypointInfo(Area.HARROGATH, 30, "Harrogath"),
    WaypointInfo(Area.FRIGID_HIGHLANDS, 31, "Frigid Highlands"),
    WaypointInfo(Area.ARREAT_PLATEAU, 32, "Arreat Plateau"),
    WaypointInfo(Area.CRYSTALLINE_PASSAGE, 33, "Crystalline Passage"),
    WaypointInfo(Area.GLACIAL_TRAIL, 34, "Glacial Trail"),
    WaypointInfo(Area.FROZEN_TUNDRA, 35, "Frozen Tundra"),
    WaypointInfo(Area.ANCIENTS_WAY, 36, "Ancients' Way"),
    WaypointInfo(Area.WORLDSTONE_KEEP_LEVEL_2, 37, "Worldstone Keep Level 2"),
]

# Quick lookup: area_id → WaypointInfo
_WP_BY_AREA: dict[int, WaypointInfo] = {wp.area_id: wp for wp in WAYPOINTS}


def has_waypoint(area_id: int) -> bool:
    """Check if an area has a waypoint."""
    return area_id in _WP_BY_AREA


def get_waypoint(area_id: int) -> Optional[WaypointInfo]:
    return _WP_BY_AREA.get(area_id)


def get_nearest_waypoint_area(area_id: int) -> int:
    """
    Get the nearest waypoint area for a given area.

    Simple heuristic: walk backwards through area IDs until we find
    one with a waypoint.
    """
    for aid in range(area_id, 0, -1):
        if aid in _WP_BY_AREA:
            return aid
    return Area.ROGUE_ENCAMPMENT


# ===================================================================
# Area connections (simplified adjacency for pathing)
# ===================================================================

# Load from data file if available; otherwise use hardcoded basics
_AREA_DB: dict[int, dict] = {}
_DB_LOADED = False


def _load_area_db() -> None:
    global _AREA_DB, _DB_LOADED
    if _DB_LOADED:
        return
    db_path = Path(__file__).resolve().parents[2] / "data" / "areas.json"
    if db_path.exists():
        with open(db_path, encoding="utf-8") as f:
            raw = json.load(f)
        for entry in raw:
            _AREA_DB[entry["id"]] = entry
    _DB_LOADED = True


def get_area_name(area_id: int) -> str:
    _load_area_db()
    info = _AREA_DB.get(area_id, {})
    return info.get("name", f"Area({area_id})")


def get_area_connections(area_id: int) -> list[int]:
    """Get adjacent area IDs."""
    _load_area_db()
    info = _AREA_DB.get(area_id, {})
    return info.get("connections", [])
