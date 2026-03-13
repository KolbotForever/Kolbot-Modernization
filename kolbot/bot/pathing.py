"""
Pathfinding and navigation.

Provides area-to-area navigation using waypoints, portals, and
walking/teleporting.  Uses a simplified approach based on area
adjacency rather than full collision map pathfinding.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Optional

from kolbot.core.game_state import GameStateTracker
from kolbot.core.memory import GameMemoryReader
from kolbot.core.packets import PacketSender
from kolbot.core.structures import Position, UnitType
from kolbot.game.map import (
    Area,
    get_act,
    get_area_connections,
    get_nearest_waypoint_area,
    has_waypoint,
    is_town,
)
from kolbot.game.player import Player
from kolbot.utils.helpers import distance
from kolbot.utils.logger import get_logger

log = get_logger("bot.pathing")


class PathFinder:
    """
    Area-to-area pathfinding using BFS over the area adjacency graph.

    For intra-area movement, uses direct teleport/walk toward the target.
    """

    def __init__(
        self,
        player: Player,
        reader: GameMemoryReader,
        sender: PacketSender,
        tracker: GameStateTracker,
    ) -> None:
        self._player = player
        self._reader = reader
        self._sender = sender
        self._tracker = tracker

    # ------------------------------------------------------------------
    # Intra-area movement
    # ------------------------------------------------------------------

    def move_to(self, x: int, y: int, use_teleport: bool = False) -> bool:
        """
        Move to a position within the current area.

        If use_teleport is True and the player has Teleport, uses
        step-by-step teleportation for long distances.
        """
        if use_teleport and self._player.has_skill(54):  # Teleport
            return self._teleport_path(x, y)
        return self._player.move_to(x, y)

    def _teleport_path(self, target_x: int, target_y: int, step: int = 20) -> bool:
        """
        Teleport toward target in steps of *step* tiles.

        Breaking the path into smaller teleports avoids overshooting
        and handles obstacles better.
        """
        max_iterations = 50
        for _ in range(max_iterations):
            pos = self._player.position
            dist = distance(pos.x, pos.y, target_x, target_y)

            if dist <= 5:
                return True

            if dist <= step:
                self._player.teleport_to(target_x, target_y)
                time.sleep(0.1)
                return True

            # Calculate intermediate point
            ratio = step / dist
            ix = int(pos.x + (target_x - pos.x) * ratio)
            iy = int(pos.y + (target_y - pos.y) * ratio)
            self._player.teleport_to(ix, iy)
            time.sleep(0.1)

        log.warning("Teleport path to (%d, %d) exceeded max iterations", target_x, target_y)
        return False

    # ------------------------------------------------------------------
    # Area transitions
    # ------------------------------------------------------------------

    def find_exit(self, target_area: int) -> Optional[Position]:
        """
        Find an exit tile/warp to an adjacent area.

        Scans objects in the current snapshot for level warps
        (tiles/stairs) that lead to the target area.
        """
        snap = self._tracker.snapshot
        for obj in snap.objects:
            # Tile units (type 5) and warp objects lead to other areas
            # The txt_file_no often corresponds to the target area
            # This is simplified — real implementation would read the
            # warp's target area from the Room2/Level data
            if obj.txt_file_no == target_area or obj.mode == target_area:
                return obj.position
        return None

    def take_exit(self, target_area: int, use_teleport: bool = False) -> bool:
        """
        Navigate to and take an exit to an adjacent area.
        """
        exit_pos = self.find_exit(target_area)
        if not exit_pos:
            log.warning("Exit to area %d not found", target_area)
            return False

        # Move to exit
        self.move_to(exit_pos.x, exit_pos.y, use_teleport)
        time.sleep(0.5)

        # Interact with the exit object
        snap = self._tracker.snapshot
        for obj in snap.objects:
            if distance(obj.position.x, obj.position.y, exit_pos.x, exit_pos.y) < 10:
                self._sender.interact(UnitType.OBJECT, obj.unit_id)
                time.sleep(1.0)
                break

        # Verify we changed areas
        new_area = self._tracker.snapshot.area_id
        if new_area == target_area:
            log.info("Entered area %d", target_area)
            return True

        log.warning("Failed to enter area %d (currently in %d)", target_area, new_area)
        return False

    # ------------------------------------------------------------------
    # Multi-area navigation
    # ------------------------------------------------------------------

    def navigate_to_area(self, target_area: int, use_teleport: bool = False) -> bool:
        """
        Navigate from the current area to a target area.

        Uses waypoints for long distances, then walks/teleports through
        intermediate areas.
        """
        current = self._tracker.snapshot.area_id
        if current == target_area:
            return True

        log.info("Navigating from area %d to %d", current, target_area)

        # Check if we can use a waypoint to get close
        if has_waypoint(target_area):
            # Use waypoint directly if we're in town or near a waypoint
            if is_town(current):
                from kolbot.game.town import TownManager
                # Use the waypoint from town
                self._use_waypoint_to(target_area)
                return self._tracker.snapshot.area_id == target_area

        # BFS to find path through areas
        path = self._find_area_path(current, target_area)
        if not path:
            log.warning("No path found from area %d to %d", current, target_area)
            return False

        log.debug("Area path: %s", path)

        # Walk through each area transition
        for next_area in path[1:]:
            if not self.take_exit(next_area, use_teleport):
                log.warning("Failed at area transition to %d", next_area)
                return False

        return self._tracker.snapshot.area_id == target_area

    def _find_area_path(self, start: int, goal: int) -> list[int]:
        """BFS over area adjacency graph."""
        if start == goal:
            return [start]

        visited: set[int] = {start}
        queue: deque[list[int]] = deque([[start]])

        while queue:
            path = queue.popleft()
            current = path[-1]

            for neighbor in get_area_connections(current):
                if neighbor == goal:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])

        return []

    def _use_waypoint_to(self, target_area: int) -> bool:
        """Use a waypoint to travel to target_area."""
        snap = self._tracker.snapshot
        # Find waypoint object nearby
        for obj in snap.objects:
            if obj.txt_file_no in (
                119, 145, 156, 157, 237, 238, 288, 323, 324, 398, 402, 429, 494, 496, 511, 539
            ):
                self._sender.interact(UnitType.OBJECT, obj.unit_id)
                time.sleep(0.5)
                self._sender.open_waypoint(obj.unit_id, target_area)
                time.sleep(1.0)
                return True
        return False


class TeleportNavigator:
    """
    Specialized navigator for Teleport-capable characters.

    Handles teleporting through areas efficiently, avoiding
    dead ends and finding exits quickly.
    """

    def __init__(self, player: Player, path_finder: PathFinder) -> None:
        self._player = player
        self._pf = path_finder

    def teleport_to_exit(self, target_area: int, scan_radius: int = 40) -> bool:
        """
        Teleport around the current area looking for an exit to target_area.

        Uses a spiral search pattern if the exit isn't immediately visible.
        """
        # Try direct exit first
        exit_pos = self._pf.find_exit(target_area)
        if exit_pos:
            return self._pf.move_to(exit_pos.x, exit_pos.y, use_teleport=True)

        # Spiral search
        pos = self._player.position
        for ring in range(1, 6):
            for dx, dy in self._spiral_offsets(ring, scan_radius):
                tx = pos.x + dx
                ty = pos.y + dy
                self._player.teleport_to(tx, ty)
                time.sleep(0.15)

                exit_pos = self._pf.find_exit(target_area)
                if exit_pos:
                    return self._pf.move_to(exit_pos.x, exit_pos.y, use_teleport=True)

        return False

    @staticmethod
    def _spiral_offsets(ring: int, step: int) -> list[tuple[int, int]]:
        """Generate offsets for a spiral search ring."""
        offsets: list[tuple[int, int]] = []
        d = ring * step
        # Top edge
        for x in range(-d, d + 1, step):
            offsets.append((x, -d))
        # Right edge
        for y in range(-d + step, d + 1, step):
            offsets.append((d, y))
        # Bottom edge
        for x in range(d - step, -d - 1, -step):
            offsets.append((x, d))
        # Left edge
        for y in range(d - step, -d, -step):
            offsets.append((-d, y))
        return offsets
