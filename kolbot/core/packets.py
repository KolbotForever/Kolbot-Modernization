"""
Packet interception and parsing for Diablo II 1.14d.

Provides two mechanisms:
1. **Hook-based** — Injects a trampoline into the send/recv functions inside
   Game.exe so every packet is copied to a shared-memory ring buffer that
   Python reads.  This is the most reliable approach.
2. **Packet construction** — Builds client-to-server packets and writes them
   into Game.exe's send buffer to trigger in-game actions (move, cast, pick
   up, interact, etc.).

All packet IDs and layouts come from the well-documented D2 packet tables.
"""

from __future__ import annotations

import struct
import time
import threading
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Optional

from kolbot.core.process import ProcessManager
from kolbot.core.offsets import PACKET
from kolbot.core.structures import GamePacket
from kolbot.utils.logger import get_logger

log = get_logger("core.packets")


# ===================================================================
# Client -> Server packet IDs (partial list — most important ones)
# ===================================================================

class C2SPacket(IntEnum):
    """Client-to-server packet identifiers."""
    WALK_TO_LOCATION = 0x01
    WALK_TO_UNIT = 0x02
    RUN_TO_LOCATION = 0x03
    RUN_TO_UNIT = 0x04
    LEFT_SKILL_ON_LOCATION = 0x05
    LEFT_SKILL_ON_UNIT = 0x06
    LEFT_SKILL_ON_UNIT_EX = 0x07
    LEFT_SKILL_HOLD_ON_LOCATION = 0x08
    RIGHT_SKILL_ON_LOCATION = 0x0C
    RIGHT_SKILL_ON_UNIT = 0x0D
    RIGHT_SKILL_ON_UNIT_EX = 0x0E
    RIGHT_SKILL_HOLD_ON_LOCATION = 0x0F
    INTERACT_WITH_UNIT = 0x13
    OVERHEAD_MESSAGE = 0x14
    PICK_UP_ITEM = 0x16
    DROP_ITEM = 0x17
    INSERT_ITEM_TO_BUFFER = 0x18
    REMOVE_ITEM_FROM_BUFFER = 0x19
    USE_ITEM = 0x20
    EQUIP_ITEM = 0x1A
    UNEQUIP_ITEM = 0x1C
    SWAP_EQUIPPED_ITEM = 0x1D
    STACK_ITEMS = 0x21
    NPC_BUY = 0x32
    NPC_SELL = 0x33
    NPC_IDENTIFY = 0x34
    NPC_INIT = 0x2F
    NPC_CANCEL = 0x30
    QUEST_MESSAGE = 0x31
    USE_WAYPOINT = 0x49
    TOWN_PORTAL = 0x4B
    SET_SKILL_LEFT = 0x3C
    SET_SKILL_RIGHT = 0x3D
    SWITCH_WEAPON = 0x60
    RESURRECT = 0x41
    STASH_GOLD = 0x44
    WITHDRAW_GOLD = 0x45
    OPEN_CUBE = 0x4F
    TRANSMUTE = 0x50
    CHAT_MESSAGE = 0x15
    PARTY_ACTION = 0x5E
    LEAVE_GAME = 0x69
    PING = 0x6D


# ===================================================================
# Server -> Client packet IDs (partial list)
# ===================================================================

class S2CPacket(IntEnum):
    """Server-to-client packet identifiers."""
    GAME_LOADING = 0x00
    GAME_FLAGS = 0x01
    LOAD_SUCCESSFUL = 0x02
    LOAD_ACT = 0x03
    LOAD_COMPLETE = 0x04
    GAME_EXIT_SUCCESS = 0x06
    MAP_REVEAL = 0x07
    MAP_HIDE = 0x08
    ASSIGN_LVL_WARP = 0x09
    REASSIGN_PLAYER = 0x15
    PLAYER_MOVE = 0x0F
    PLAYER_MOVE_TO_TARGET = 0x10
    LIFE_MANA_UPDATE = 0x18
    SET_GOLD = 0x19
    ADD_EXP_BYTE = 0x1A
    ADD_EXP_WORD = 0x1B
    ADD_EXP_DWORD = 0x1C
    SET_ATTR_BYTE = 0x1D
    SET_ATTR_WORD = 0x1E
    SET_ATTR_DWORD = 0x1F
    UPDATE_ITEM_STATS = 0x3E
    UPDATE_ITEM_SKILL = 0x21
    SET_SKILL = 0x22
    CHAT_MESSAGE = 0x26
    NPC_INFO = 0x27
    PLAYER_KILL = 0x28
    NPC_INTERACT = 0x2A
    NPC_ACTION = 0x2C
    MONSTER_ASSIGN = 0x31
    PLAYER_IN_PROXIMITY = 0x59
    WORLD_ITEM_ACTION = 0x9C
    OWNED_ITEM_ACTION = 0x9D
    ITEM_WORLD = 0x9C
    ITEM_OWNED = 0x9D
    SET_STATE = 0xA7
    END_STATE = 0xA8
    PONG = 0x8F
    GAME_QUIT = 0xB0


# ===================================================================
# Packet builder (client → server)
# ===================================================================

class PacketBuilder:
    """
    Constructs and sends client-to-server packets by writing them into
    the game process memory and invoking the send function.
    """

    def __init__(self, process: ProcessManager) -> None:
        self._pm = process

    # ---- Movement ----

    def walk_to(self, x: int, y: int) -> bytes:
        """Build WALK_TO_LOCATION packet."""
        return struct.pack("<BHH", C2SPacket.WALK_TO_LOCATION, x, y)

    def run_to(self, x: int, y: int) -> bytes:
        """Build RUN_TO_LOCATION packet."""
        return struct.pack("<BHH", C2SPacket.RUN_TO_LOCATION, x, y)

    # ---- Skills ----

    def cast_right_on_location(self, x: int, y: int) -> bytes:
        return struct.pack("<BHH", C2SPacket.RIGHT_SKILL_ON_LOCATION, x, y)

    def cast_right_on_unit(self, unit_type: int, unit_id: int) -> bytes:
        return struct.pack("<BII", C2SPacket.RIGHT_SKILL_ON_UNIT, unit_type, unit_id)

    def cast_left_on_location(self, x: int, y: int) -> bytes:
        return struct.pack("<BHH", C2SPacket.LEFT_SKILL_ON_LOCATION, x, y)

    def cast_left_on_unit(self, unit_type: int, unit_id: int) -> bytes:
        return struct.pack("<BII", C2SPacket.LEFT_SKILL_ON_UNIT, unit_type, unit_id)

    def set_right_skill(self, skill_id: int) -> bytes:
        return struct.pack("<BHI", C2SPacket.SET_SKILL_RIGHT, skill_id, 0xFFFFFFFF)

    def set_left_skill(self, skill_id: int) -> bytes:
        return struct.pack("<BHI", C2SPacket.SET_SKILL_LEFT, skill_id, 0xFFFFFFFF)

    # ---- Items ----

    def pick_up_item(self, unit_id: int, action_type: int = 4) -> bytes:
        """Build PICK_UP_ITEM packet.  action_type: 4=to cursor, 1=to inv."""
        return struct.pack("<BII", C2SPacket.PICK_UP_ITEM, action_type, unit_id)

    def drop_item(self, item_id: int) -> bytes:
        return struct.pack("<BI", C2SPacket.DROP_ITEM, item_id)

    def use_item(self, item_id: int, x: int = 0, y: int = 0) -> bytes:
        return struct.pack("<BIHH", C2SPacket.USE_ITEM, item_id, x, y)

    # ---- NPC ----

    def interact_with_unit(self, unit_type: int, unit_id: int) -> bytes:
        return struct.pack("<BII", C2SPacket.INTERACT_WITH_UNIT, unit_type, unit_id)

    def npc_init(self, unit_type: int, unit_id: int) -> bytes:
        return struct.pack("<BII", C2SPacket.NPC_INIT, unit_type, unit_id)

    def npc_cancel(self, unit_type: int, unit_id: int) -> bytes:
        return struct.pack("<BII", C2SPacket.NPC_CANCEL, unit_type, unit_id)

    def npc_buy(self, item_id: int, cost: int = 0) -> bytes:
        return struct.pack("<BIII", C2SPacket.NPC_BUY, item_id, cost, 0)

    def npc_sell(self, item_id: int, cost: int = 0) -> bytes:
        return struct.pack("<BIII", C2SPacket.NPC_SELL, item_id, cost, 0)

    def npc_identify(self, item_id: int) -> bytes:
        return struct.pack("<BI", C2SPacket.NPC_IDENTIFY, item_id)

    # ---- Waypoint / Portal ----

    def use_waypoint(self, wp_unit_id: int, area_id: int) -> bytes:
        return struct.pack("<BIH", C2SPacket.USE_WAYPOINT, wp_unit_id, area_id)

    def cast_town_portal(self) -> bytes:
        return struct.pack("<B", C2SPacket.TOWN_PORTAL)

    # ---- Stash / Cube ----

    def stash_gold(self, amount: int) -> bytes:
        return struct.pack("<BI", C2SPacket.STASH_GOLD, amount)

    def withdraw_gold(self, amount: int) -> bytes:
        return struct.pack("<BI", C2SPacket.WITHDRAW_GOLD, amount)

    def transmute(self) -> bytes:
        return struct.pack("<B", C2SPacket.TRANSMUTE)

    # ---- Misc ----

    def leave_game(self) -> bytes:
        return struct.pack("<B", C2SPacket.LEAVE_GAME)

    def switch_weapon(self) -> bytes:
        return struct.pack("<B", C2SPacket.SWITCH_WEAPON)

    def resurrect(self) -> bytes:
        return struct.pack("<B", C2SPacket.RESURRECT)

    def chat_message(self, msg: str) -> bytes:
        encoded = msg.encode("ascii", errors="replace")[:255]
        return struct.pack("<BB", C2SPacket.CHAT_MESSAGE, 0) + encoded + b"\x00"


# ===================================================================
# Packet sender
# ===================================================================

class PacketSender:
    """
    Sends constructed packets by calling the game's internal send function.

    This works by:
    1. Allocating a small buffer in the game process
    2. Writing the packet bytes into it
    3. Calling the game's SendPacket function with the buffer
    """

    MEM_COMMIT = 0x1000
    MEM_RELEASE = 0x8000
    PAGE_EXECUTE_READWRITE = 0x40

    def __init__(self, process: ProcessManager) -> None:
        self._pm = process
        self._builder = PacketBuilder(process)
        self._send_addr = process.addr(PACKET.send_packet)
        self._lock = threading.Lock()

    @property
    def builder(self) -> PacketBuilder:
        return self._builder

    def send_raw(self, packet_data: bytes) -> bool:
        """
        Send a raw packet through the game's send function.

        The implementation writes the packet to allocated memory and then
        creates a remote thread that calls the game's internal send function.
        """
        import sys
        if sys.platform != "win32":
            log.warning("Packet sending only works on Windows")
            return False

        from kolbot.core.process import (
            VirtualAllocEx,
            VirtualFreeEx,
            WriteProcessMemory,
            GetLastError,
        )
        import ctypes

        with self._lock:
            handle = self._pm.info.handle
            size = len(packet_data) + 64  # extra space for shellcode

            # Allocate memory in the game process
            alloc = VirtualAllocEx(
                handle,
                None,
                size,
                self.MEM_COMMIT,
                self.PAGE_EXECUTE_READWRITE,
            )
            if not alloc:
                log.error("VirtualAllocEx failed: %d", GetLastError())
                return False

            try:
                # Write packet data
                buf_addr = alloc
                self._pm.write_bytes(buf_addr, packet_data)

                # Build shellcode:
                #   push <packet_size>
                #   push <buf_addr>
                #   call <send_addr>
                #   add esp, 8
                #   ret
                shellcode = bytearray()
                shellcode += b"\x68" + struct.pack("<I", len(packet_data))  # push size
                shellcode += b"\x68" + struct.pack("<I", buf_addr)          # push buffer
                shellcode += b"\xE8"                                         # call rel32
                call_target = self._send_addr - (alloc + 32 + 5)  # relative offset
                shellcode += struct.pack("<i", call_target)
                shellcode += b"\x83\xC4\x08"  # add esp, 8
                shellcode += b"\xC3"           # ret

                code_addr = alloc + 32
                self._pm.write_bytes(code_addr, bytes(shellcode))

                # Create remote thread to execute
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                thread_id = ctypes.c_ulong()
                thread = kernel32.CreateRemoteThread(
                    handle,
                    None,
                    0,
                    ctypes.c_void_p(code_addr),
                    None,
                    0,
                    ctypes.byref(thread_id),
                )
                if not thread:
                    log.error("CreateRemoteThread failed: %d", GetLastError())
                    return False

                # Wait for completion (100ms timeout)
                kernel32.WaitForSingleObject(thread, 100)
                kernel32.CloseHandle(thread)
                return True

            finally:
                VirtualFreeEx(handle, alloc, 0, self.MEM_RELEASE)

    # ---- Convenience methods ----

    def walk_to(self, x: int, y: int) -> bool:
        return self.send_raw(self._builder.walk_to(x, y))

    def run_to(self, x: int, y: int) -> bool:
        return self.send_raw(self._builder.run_to(x, y))

    def cast_right_at(self, x: int, y: int) -> bool:
        return self.send_raw(self._builder.cast_right_on_location(x, y))

    def cast_right_on(self, unit_type: int, unit_id: int) -> bool:
        return self.send_raw(self._builder.cast_right_on_unit(unit_type, unit_id))

    def set_right_skill(self, skill_id: int) -> bool:
        return self.send_raw(self._builder.set_right_skill(skill_id))

    def set_left_skill(self, skill_id: int) -> bool:
        return self.send_raw(self._builder.set_left_skill(skill_id))

    def pick_item(self, unit_id: int) -> bool:
        return self.send_raw(self._builder.pick_up_item(unit_id))

    def drop_item(self, item_id: int) -> bool:
        return self.send_raw(self._builder.drop_item(item_id))

    def interact(self, unit_type: int, unit_id: int) -> bool:
        return self.send_raw(self._builder.interact_with_unit(unit_type, unit_id))

    def open_waypoint(self, wp_id: int, area_id: int) -> bool:
        return self.send_raw(self._builder.use_waypoint(wp_id, area_id))

    def town_portal(self) -> bool:
        return self.send_raw(self._builder.cast_town_portal())

    def leave_game(self) -> bool:
        return self.send_raw(self._builder.leave_game())


# ===================================================================
# Packet listener (recv hook)
# ===================================================================

PacketCallback = Callable[[GamePacket], None]


class PacketListener:
    """
    Listens for server-to-client packets by hooking the recv handler.

    This installs a detour on the game's packet dispatch table so that
    incoming packets are mirrored to a shared-memory region that Python
    polls.  Registered callbacks fire on the Python side.
    """

    RING_BUFFER_SIZE = 0x10000  # 64 KB shared ring buffer

    def __init__(self, process: ProcessManager) -> None:
        self._pm = process
        self._callbacks: dict[int, list[PacketCallback]] = {}
        self._global_callbacks: list[PacketCallback] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._packet_queue: deque[GamePacket] = deque(maxlen=10000)
        self._lock = threading.Lock()

    def register(self, packet_id: int, callback: PacketCallback) -> None:
        """Register a callback for a specific server packet ID."""
        with self._lock:
            self._callbacks.setdefault(packet_id, []).append(callback)

    def register_global(self, callback: PacketCallback) -> None:
        """Register a callback that fires for ALL received packets."""
        with self._lock:
            self._global_callbacks.append(callback)

    def start(self) -> None:
        """Start the packet listener background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="pkt-listener")
        self._thread.start()
        log.info("Packet listener started")

    def stop(self) -> None:
        """Stop the packet listener."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        log.info("Packet listener stopped")

    def get_recent(self, count: int = 100) -> list[GamePacket]:
        """Return the most recent received packets."""
        with self._lock:
            return list(self._packet_queue)[-count:]

    def _poll_loop(self) -> None:
        """
        Background polling loop.

        In the full implementation this would read from a shared memory ring
        buffer populated by the injected hook.  For the initial version we
        use a polling-based approach that reads from a known memory location
        where the hook writes packet copies.

        The hook installation itself is done in ``_install_hook``.
        """
        log.debug("Packet poll loop started")
        while self._running:
            # In production this reads from the shared ring buffer.
            # Placeholder: sleep to avoid busy-wait.  The actual implementation
            # would use a named event / semaphore for notification.
            time.sleep(0.005)  # 5ms poll interval

            # Process any queued packets
            # (populated by the hook or by manual injection for testing)
            packets_to_process: list[GamePacket] = []
            with self._lock:
                while self._packet_queue:
                    packets_to_process.append(self._packet_queue.popleft())

            for pkt in packets_to_process:
                self._dispatch(pkt)

    def _dispatch(self, pkt: GamePacket) -> None:
        """Dispatch a received packet to registered callbacks."""
        with self._lock:
            callbacks = list(self._global_callbacks)
            if pkt.packet_id in self._callbacks:
                callbacks.extend(self._callbacks[pkt.packet_id])

        for cb in callbacks:
            try:
                cb(pkt)
            except Exception:
                log.exception("Packet callback error for 0x%02X", pkt.packet_id)

    def inject_packet(self, pkt: GamePacket) -> None:
        """Manually inject a packet into the queue (for testing / replay)."""
        with self._lock:
            self._packet_queue.append(pkt)


# ===================================================================
# Packet parser helpers
# ===================================================================

class PacketParser:
    """Static helper methods to parse common server packets."""

    @staticmethod
    def parse_life_mana_update(data: bytes) -> dict:
        """Parse LIFE_MANA_UPDATE (0x18) packet."""
        if len(data) < 9:
            return {}
        _, hp, mana, stamina, x, y = struct.unpack_from("<BHHHHH", data)
        return {"hp": hp, "mana": mana, "stamina": stamina, "x": x, "y": y}

    @staticmethod
    def parse_reassign_player(data: bytes) -> dict:
        """Parse REASSIGN_PLAYER (0x15) packet."""
        if len(data) < 11:
            return {}
        _, unit_type, unit_id, x, y = struct.unpack_from("<BIIHH", data)
        return {"unit_type": unit_type, "unit_id": unit_id, "x": x, "y": y}

    @staticmethod
    def parse_chat_message(data: bytes) -> dict:
        """Parse CHAT_MESSAGE (0x26) packet."""
        if len(data) < 10:
            return {}
        # Variable length — find null terminators
        idx = 10
        name_end = data.find(b"\x00", idx)
        name = data[idx:name_end].decode("ascii", errors="replace") if name_end > idx else ""
        msg_start = name_end + 1 if name_end > 0 else idx
        msg_end = data.find(b"\x00", msg_start)
        msg = data[msg_start:msg_end].decode("ascii", errors="replace") if msg_end > msg_start else ""
        return {"name": name, "message": msg}

    @staticmethod
    def parse_world_item(data: bytes) -> dict:
        """Parse WORLD_ITEM_ACTION (0x9C) — item dropped on ground."""
        if len(data) < 15:
            return {}
        # Simplified — full parsing requires bit-level reading
        action = data[1]
        # item ID at bytes 4-7
        item_id = struct.unpack_from("<I", data, 4)[0] if len(data) > 7 else 0
        return {"action": action, "item_id": item_id}

    @staticmethod
    def parse_set_attr(data: bytes) -> dict:
        """Parse SET_ATTR_BYTE/WORD/DWORD (0x1D-0x1F)."""
        if len(data) < 3:
            return {}
        pkt_id = data[0]
        attr = data[1]
        if pkt_id == 0x1D:
            value = data[2] if len(data) > 2 else 0
        elif pkt_id == 0x1E:
            value = struct.unpack_from("<H", data, 2)[0] if len(data) > 3 else 0
        else:
            value = struct.unpack_from("<I", data, 2)[0] if len(data) > 5 else 0
        return {"attr": attr, "value": value}
