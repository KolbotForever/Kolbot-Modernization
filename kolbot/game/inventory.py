"""
Inventory and stash management.

Handles item placement, free-space tracking, moving items between
inventory/stash/cube, and item identification via Cain or scrolls.
"""

from __future__ import annotations

import time
from typing import Optional

from kolbot.core.game_state import GameStateTracker
from kolbot.core.memory import GameMemoryReader
from kolbot.core.packets import PacketSender
from kolbot.core.structures import ItemLocation, ItemUnit, UnitType
from kolbot.game.items import ItemClassifier as IC
from kolbot.utils.logger import get_logger

log = get_logger("game.inventory")

# Inventory grid dimensions (4 rows x 10 columns)
INV_ROWS = 4
INV_COLS = 10

# Stash grid (classic stash = 6x8, expansion = 6x8 per tab concept; 1.14d = 6x8)
STASH_ROWS = 8
STASH_COLS = 6

# Cube grid (3x4)
CUBE_ROWS = 4
CUBE_COLS = 3


class InventoryGrid:
    """
    Tracks occupied cells in a 2D grid (inventory, stash, or cube).

    Each item occupies a rectangular region based on its base item size.
    """

    def __init__(self, rows: int, cols: int) -> None:
        self.rows = rows
        self.cols = cols
        self.grid: list[list[int]] = [[0] * cols for _ in range(rows)]

    def clear(self) -> None:
        for r in range(self.rows):
            for c in range(self.cols):
                self.grid[r][c] = 0

    def mark(self, x: int, y: int, w: int, h: int, item_id: int = 1) -> None:
        """Mark cells occupied by an item at (x, y) with size (w, h)."""
        for dy in range(h):
            for dx in range(w):
                gy = y + dy
                gx = x + dx
                if 0 <= gy < self.rows and 0 <= gx < self.cols:
                    self.grid[gy][gx] = item_id

    def is_free(self, x: int, y: int, w: int, h: int) -> bool:
        """Check if a rectangular region is completely free."""
        for dy in range(h):
            for dx in range(w):
                gy = y + dy
                gx = x + dx
                if gy >= self.rows or gx >= self.cols:
                    return False
                if self.grid[gy][gx] != 0:
                    return False
        return True

    def find_free_spot(self, w: int, h: int) -> Optional[tuple[int, int]]:
        """Find the first free spot that fits an item of size (w, h)."""
        for y in range(self.rows - h + 1):
            for x in range(self.cols - w + 1):
                if self.is_free(x, y, w, h):
                    return (x, y)
        return None

    @property
    def free_cells(self) -> int:
        count = 0
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] == 0:
                    count += 1
        return count

    @property
    def total_cells(self) -> int:
        return self.rows * self.cols

    @property
    def used_percent(self) -> float:
        return (1.0 - self.free_cells / self.total_cells) * 100.0


# ---------------------------------------------------------------------------
# Item size lookup (width x height for common base items)
# This is a simplified version; the full version loads from items.json
# ---------------------------------------------------------------------------

# Default item sizes by item code prefix
_ITEM_SIZES: dict[str, tuple[int, int]] = {
    # Armor (2x3)
    "default_armor": (2, 3),
    # Weapons vary widely
    "default_weapon": (1, 3),
    # Small items
    "rin": (1, 1), "amu": (1, 1), "jew": (1, 1),
    "cm1": (1, 1),  # small charm
    "cm2": (1, 2),  # large charm
    "cm3": (1, 3),  # grand charm
    # Potions & scrolls
    "hp1": (1, 1), "hp2": (1, 1), "hp3": (1, 1), "hp4": (1, 1), "hp5": (1, 1),
    "mp1": (1, 1), "mp2": (1, 1), "mp3": (1, 1), "mp4": (1, 1), "mp5": (1, 1),
    "rvs": (1, 1), "rvl": (1, 1),
    "tsc": (1, 1), "isc": (1, 1),
    "tbk": (1, 1), "ibk": (1, 1),
    # Keys
    "pk1": (1, 1), "pk2": (1, 1), "pk3": (1, 1),
    # Runes (1x1)
    "r01": (1, 1), "r02": (1, 1), "r03": (1, 1), "r04": (1, 1),
    "r05": (1, 1), "r06": (1, 1), "r07": (1, 1), "r08": (1, 1),
    "r09": (1, 1), "r10": (1, 1), "r11": (1, 1), "r12": (1, 1),
    "r13": (1, 1), "r14": (1, 1), "r15": (1, 1), "r16": (1, 1),
    "r17": (1, 1), "r18": (1, 1), "r19": (1, 1), "r20": (1, 1),
    "r21": (1, 1), "r22": (1, 1), "r23": (1, 1), "r24": (1, 1),
    "r25": (1, 1), "r26": (1, 1), "r27": (1, 1), "r28": (1, 1),
    "r29": (1, 1), "r30": (1, 1), "r31": (1, 1), "r32": (1, 1),
    "r33": (1, 1),
    # Gems (1x1)
    "gcv": (1, 1), "gcy": (1, 1), "gcb": (1, 1), "gcg": (1, 1), "gcr": (1, 1), "gcw": (1, 1),
    "gfv": (1, 1), "gfy": (1, 1), "gfb": (1, 1), "gfg": (1, 1), "gfr": (1, 1), "gfw": (1, 1),
    "gsv": (1, 1), "gsy": (1, 1), "gsb": (1, 1), "gsg": (1, 1), "gsr": (1, 1), "gsw": (1, 1),
    "gzv": (1, 1), "gzb": (1, 1), "gzg": (1, 1), "gzr": (1, 1), "gzy": (1, 1), "gzw": (1, 1),
    "gpv": (1, 1), "gpb": (1, 1), "gpg": (1, 1), "gpr": (1, 1), "gpy": (1, 1), "gpw": (1, 1),
    # Gold
    "gld": (1, 1),
}


def get_item_size(item_code: str) -> tuple[int, int]:
    """Get (width, height) for an item code."""
    if item_code in _ITEM_SIZES:
        return _ITEM_SIZES[item_code]
    return (2, 2)  # safe default


class InventoryManager:
    """
    High-level inventory operations.

    Tracks inventory state, finds free space, moves items to stash,
    identifies items, and manages inventory cleanup.
    """

    def __init__(
        self,
        reader: GameMemoryReader,
        sender: PacketSender,
        tracker: GameStateTracker,
    ) -> None:
        self._reader = reader
        self._sender = sender
        self._tracker = tracker
        self.inv_grid = InventoryGrid(INV_ROWS, INV_COLS)
        self.stash_grid = InventoryGrid(STASH_ROWS, STASH_COLS)
        self.cube_grid = InventoryGrid(CUBE_ROWS, CUBE_COLS)

    def refresh_grids(self) -> None:
        """Rebuild inventory grids from current item positions."""
        self.inv_grid.clear()
        self.stash_grid.clear()
        self.cube_grid.clear()

        items = self._tracker.snapshot.inventory_items
        for item in items:
            code = item.item_code or ""
            w, h = get_item_size(code)

            if item.location == ItemLocation.INVENTORY:
                self.inv_grid.mark(item.inv_x, item.inv_y, w, h, item.unit_id)
            elif item.location == ItemLocation.STASH:
                self.stash_grid.mark(item.inv_x, item.inv_y, w, h, item.unit_id)
            elif item.location == ItemLocation.CUBE:
                self.cube_grid.mark(item.inv_x, item.inv_y, w, h, item.unit_id)

    def has_inventory_space(self, w: int = 2, h: int = 2) -> bool:
        """Check if there's room in inventory for an item of size (w, h)."""
        self.refresh_grids()
        return self.inv_grid.find_free_spot(w, h) is not None

    def has_stash_space(self, w: int = 2, h: int = 2) -> bool:
        self.refresh_grids()
        return self.stash_grid.find_free_spot(w, h) is not None

    @property
    def inventory_free_cells(self) -> int:
        self.refresh_grids()
        return self.inv_grid.free_cells

    @property
    def inventory_full_percent(self) -> float:
        self.refresh_grids()
        return self.inv_grid.used_percent

    def get_inventory_items(self) -> list[ItemUnit]:
        """Get items currently in the inventory."""
        return [
            i for i in self._tracker.snapshot.inventory_items
            if i.location == ItemLocation.INVENTORY
        ]

    def get_stash_items(self) -> list[ItemUnit]:
        return [
            i for i in self._tracker.snapshot.inventory_items
            if i.location == ItemLocation.STASH
        ]

    def get_cube_items(self) -> list[ItemUnit]:
        return [
            i for i in self._tracker.snapshot.inventory_items
            if i.location == ItemLocation.CUBE
        ]

    def get_equipped_items(self) -> list[ItemUnit]:
        return [
            i for i in self._tracker.snapshot.inventory_items
            if i.location == ItemLocation.EQUIPPED
        ]

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def pick_item(self, item: ItemUnit) -> bool:
        """Pick up an item from the ground."""
        log.info("Picking up item %d (type=%d)", item.unit_id, item.txt_file_no)
        return self._sender.pick_item(item.unit_id)

    def drop_item(self, item: ItemUnit) -> bool:
        """Drop an item from inventory to the ground."""
        log.info("Dropping item %d", item.unit_id)
        return self._sender.drop_item(item.unit_id)

    def stash_item(self, item: ItemUnit) -> bool:
        """Move an item from inventory to stash (stash UI must be open)."""
        # Send pick-to-cursor then place-in-stash packets
        buf = self._sender.builder.pick_up_item(item.unit_id, action_type=4)
        self._sender.send_raw(buf)
        time.sleep(0.2)

        spot = self.stash_grid.find_free_spot(2, 2)
        if spot:
            # Place item at stash position
            insert_pkt = self._sender.builder.use_item(item.unit_id, spot[0], spot[1])
            self._sender.send_raw(insert_pkt)
            time.sleep(0.2)
            return True

        log.warning("No stash space for item %d", item.unit_id)
        return False

    def identify_item(self, item: ItemUnit) -> bool:
        """Identify an item using Cain or an identify scroll."""
        if item.is_identified:
            return True

        # Find an identify scroll in inventory
        inv_items = self.get_inventory_items()
        scroll = None
        for i in inv_items:
            if IC.is_id_scroll(i):
                scroll = i
                break

        if scroll:
            # Use scroll on item
            self._sender.send_raw(
                self._sender.builder.use_item(scroll.unit_id)
            )
            time.sleep(0.1)
            self._sender.send_raw(
                self._sender.builder.npc_identify(item.unit_id)
            )
            time.sleep(0.3)
            return True

        log.warning("No identify scroll available")
        return False

    def identify_all(self) -> int:
        """Identify all unidentified items in inventory. Returns count."""
        count = 0
        for item in self.get_inventory_items():
            if not item.is_identified:
                if self.identify_item(item):
                    count += 1
                    time.sleep(0.1)
        return count

    def count_potions(self) -> dict[str, int]:
        """Count potions in inventory by type."""
        counts = {"health": 0, "mana": 0, "rejuv": 0}
        for item in self.get_inventory_items():
            if IC.is_health_potion(item):
                counts["health"] += 1
            elif IC.is_mana_potion(item):
                counts["mana"] += 1
            elif IC.is_rejuv_potion(item):
                counts["rejuv"] += 1
        return counts

    def count_tp_scrolls(self) -> int:
        return sum(1 for i in self.get_inventory_items() if IC.is_tp_scroll(i))

    def count_id_scrolls(self) -> int:
        return sum(1 for i in self.get_inventory_items() if IC.is_id_scroll(i))

    def find_item_by_code(self, code: str) -> Optional[ItemUnit]:
        """Find an inventory item by its item code."""
        for item in self.get_inventory_items():
            if item.item_code == code:
                return item
        return None
