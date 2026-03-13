"""
Process management for Diablo II Game.exe instances.

Handles finding, attaching to, and managing Game.exe processes.
Uses ctypes to call Win32 API functions (OpenProcess, ReadProcessMemory, etc.).

NOTE: This module is designed for Windows. On non-Windows platforms it provides
stub implementations for development/testing purposes.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

from kolbot.utils.logger import get_logger

log = get_logger("core.process")

# ---------------------------------------------------------------------------
# Windows constants
# ---------------------------------------------------------------------------

PROCESS_ALL_ACCESS = 0x1F0FFF
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400

TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010

MAX_PATH = 260
INVALID_HANDLE_VALUE = -1

# ---------------------------------------------------------------------------
# Win32 structures
# ---------------------------------------------------------------------------


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * MAX_PATH),
    ]


class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", ctypes.c_char * (MAX_PATH + 1)),
        ("szExePath", ctypes.c_char * MAX_PATH),
    ]


# ---------------------------------------------------------------------------
# Win32 API bindings
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _psapi = ctypes.WinDLL("psapi", use_last_error=True)

    CreateToolhelp32Snapshot = _kernel32.CreateToolhelp32Snapshot
    CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    CreateToolhelp32Snapshot.restype = wintypes.HANDLE

    Process32First = _kernel32.Process32First
    Process32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    Process32First.restype = wintypes.BOOL

    Process32Next = _kernel32.Process32Next
    Process32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    Process32Next.restype = wintypes.BOOL

    Module32First = _kernel32.Module32First
    Module32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32)]
    Module32First.restype = wintypes.BOOL

    Module32Next = _kernel32.Module32Next
    Module32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32)]
    Module32Next.restype = wintypes.BOOL

    OpenProcess = _kernel32.OpenProcess
    OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    OpenProcess.restype = wintypes.HANDLE

    CloseHandle = _kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype = wintypes.BOOL

    ReadProcessMemory = _kernel32.ReadProcessMemory
    ReadProcessMemory.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCVOID,
        wintypes.LPVOID,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    ReadProcessMemory.restype = wintypes.BOOL

    WriteProcessMemory = _kernel32.WriteProcessMemory
    WriteProcessMemory.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.LPCVOID,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    WriteProcessMemory.restype = wintypes.BOOL

    VirtualAllocEx = _kernel32.VirtualAllocEx
    VirtualAllocEx.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        ctypes.c_size_t,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    VirtualAllocEx.restype = wintypes.LPVOID

    VirtualFreeEx = _kernel32.VirtualFreeEx
    VirtualFreeEx.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        ctypes.c_size_t,
        wintypes.DWORD,
    ]
    VirtualFreeEx.restype = wintypes.BOOL

    GetLastError = _kernel32.GetLastError
    GetLastError.argtypes = []
    GetLastError.restype = wintypes.DWORD


# ---------------------------------------------------------------------------
# Process info dataclass
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ProcessInfo:
    """Information about an attached Game.exe process."""
    pid: int = 0
    handle: int = 0  # HANDLE value
    base_address: int = 0
    module_size: int = 0
    exe_path: str = ""
    attached: bool = False
    _hwnd: int = 0  # window handle, discovered lazily


# ---------------------------------------------------------------------------
# Process manager
# ---------------------------------------------------------------------------

class ProcessManager:
    """
    Finds and attaches to Diablo II Game.exe processes.

    Usage::

        pm = ProcessManager()
        pm.attach(pid=12345)            # attach by PID
        pm.attach()                     # attach to first Game.exe found
        value = pm.read_uint(0x3A6A70)  # read DWORD at offset
        pm.detach()
    """

    TARGET_EXE = b"Game.exe"

    def __init__(self) -> None:
        self.info = ProcessInfo()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    @staticmethod
    def find_game_processes() -> list[tuple[int, str]]:
        """Return list of (pid, exe_path) for all running Game.exe instances."""
        if sys.platform != "win32":
            log.warning("Process discovery requires Windows")
            return []

        results: list[tuple[int, str]] = []
        snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == INVALID_HANDLE_VALUE:
            log.error("CreateToolhelp32Snapshot failed: %d", GetLastError())
            return results

        try:
            pe = PROCESSENTRY32()
            pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
            if not Process32First(snap, ctypes.byref(pe)):
                return results

            while True:
                if pe.szExeFile.lower() == b"game.exe":
                    results.append((pe.th32ProcessID, pe.szExeFile.decode("ascii", "replace")))
                if not Process32Next(snap, ctypes.byref(pe)):
                    break
        finally:
            CloseHandle(snap)

        log.debug("Found %d Game.exe process(es): %s", len(results), results)
        return results

    # ------------------------------------------------------------------
    # Attach / Detach
    # ------------------------------------------------------------------

    def attach(self, pid: int | None = None) -> bool:
        """
        Attach to a Game.exe process.

        If *pid* is ``None``, attaches to the first Game.exe found.
        Returns ``True`` on success.
        """
        if sys.platform != "win32":
            log.error("Cannot attach: not running on Windows")
            return False

        if self.info.attached:
            self.detach()

        # Discover PID if not given
        if pid is None:
            procs = self.find_game_processes()
            if not procs:
                log.error("No Game.exe process found")
                return False
            pid = procs[0][0]
            log.info("Auto-selected Game.exe PID %d", pid)

        # Open process
        access = PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION | PROCESS_QUERY_INFORMATION
        handle = OpenProcess(access, False, pid)
        if not handle:
            log.error("OpenProcess(%d) failed: %d", pid, GetLastError())
            return False

        self.info.pid = pid
        self.info.handle = handle

        # Get base address via module enumeration
        if not self._resolve_base_address():
            CloseHandle(handle)
            self.info = ProcessInfo()
            return False

        self.info.attached = True
        log.info(
            "Attached to Game.exe  PID=%d  Base=0x%08X  Size=0x%X",
            self.info.pid,
            self.info.base_address,
            self.info.module_size,
        )
        return True

    def detach(self) -> None:
        """Detach from the current process."""
        if self.info.handle:
            CloseHandle(self.info.handle)
            log.info("Detached from PID %d", self.info.pid)
        self.info = ProcessInfo()

    def is_alive(self) -> bool:
        """Check if the attached process is still running."""
        if not self.info.attached or sys.platform != "win32":
            return False
        # Try reading 1 byte from base address
        buf = ctypes.c_byte()
        read = ctypes.c_size_t()
        ok = ReadProcessMemory(
            self.info.handle,
            ctypes.c_void_p(self.info.base_address),
            ctypes.byref(buf),
            1,
            ctypes.byref(read),
        )
        return bool(ok)

    # ------------------------------------------------------------------
    # Memory read primitives
    # ------------------------------------------------------------------

    def read_bytes(self, address: int, size: int) -> bytes:
        """Read *size* bytes from *address* in the target process."""
        buf = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t()
        ok = ReadProcessMemory(
            self.info.handle,
            ctypes.c_void_p(address),
            buf,
            size,
            ctypes.byref(read),
        )
        if not ok:
            raise OSError(f"ReadProcessMemory @ 0x{address:08X} size={size} failed (err={GetLastError()})")
        return buf.raw[: read.value]

    def read_byte(self, address: int) -> int:
        data = self.read_bytes(address, 1)
        return data[0]

    def read_word(self, address: int) -> int:
        """Read unsigned 16-bit WORD."""
        data = self.read_bytes(address, 2)
        return int.from_bytes(data, "little", signed=False)

    def read_int(self, address: int) -> int:
        """Read signed 32-bit DWORD."""
        data = self.read_bytes(address, 4)
        return int.from_bytes(data, "little", signed=True)

    def read_uint(self, address: int) -> int:
        """Read unsigned 32-bit DWORD."""
        data = self.read_bytes(address, 4)
        return int.from_bytes(data, "little", signed=False)

    def read_uint64(self, address: int) -> int:
        """Read unsigned 64-bit QWORD."""
        data = self.read_bytes(address, 8)
        return int.from_bytes(data, "little", signed=False)

    def read_float(self, address: int) -> float:
        """Read 32-bit float."""
        data = self.read_bytes(address, 4)
        return ctypes.c_float.from_buffer_copy(data).value

    def read_string(self, address: int, max_len: int = 256) -> str:
        """Read a null-terminated ASCII string."""
        data = self.read_bytes(address, max_len)
        idx = data.find(b"\x00")
        if idx >= 0:
            data = data[:idx]
        return data.decode("ascii", errors="replace")

    def read_wstring(self, address: int, max_len: int = 256) -> str:
        """Read a null-terminated wide (UTF-16LE) string."""
        data = self.read_bytes(address, max_len * 2)
        idx = data.find(b"\x00\x00")
        if idx >= 0:
            data = data[: idx + (idx % 2)]
        return data.decode("utf-16-le", errors="replace")

    def read_pointer(self, address: int) -> int:
        """Read a 32-bit pointer and return as int."""
        return self.read_uint(address)

    def read_pointer_chain(self, base: int, offsets: list[int]) -> int:
        """Follow a chain of pointer dereferences."""
        addr = base
        for off in offsets:
            addr = self.read_uint(addr) + off
        return addr

    # ------------------------------------------------------------------
    # Memory write primitives
    # ------------------------------------------------------------------

    def write_bytes(self, address: int, data: bytes) -> bool:
        """Write raw bytes to *address* in the target process."""
        buf = ctypes.create_string_buffer(data)
        written = ctypes.c_size_t()
        ok = WriteProcessMemory(
            self.info.handle,
            ctypes.c_void_p(address),
            buf,
            len(data),
            ctypes.byref(written),
        )
        if not ok:
            log.error("WriteProcessMemory @ 0x%08X failed: %d", address, GetLastError())
        return bool(ok)

    def write_uint(self, address: int, value: int) -> bool:
        return self.write_bytes(address, value.to_bytes(4, "little", signed=False))

    def write_int(self, address: int, value: int) -> bool:
        return self.write_bytes(address, value.to_bytes(4, "little", signed=True))

    def write_word(self, address: int, value: int) -> bool:
        return self.write_bytes(address, value.to_bytes(2, "little", signed=False))

    def write_byte(self, address: int, value: int) -> bool:
        return self.write_bytes(address, value.to_bytes(1, "little", signed=False))

    # ------------------------------------------------------------------
    # Offset helpers (add module base automatically)
    # ------------------------------------------------------------------

    def addr(self, offset: int) -> int:
        """Convert a module-relative offset to an absolute address."""
        return self.info.base_address + offset

    def read_game_uint(self, offset: int) -> int:
        """Read DWORD at Game.exe + offset."""
        return self.read_uint(self.addr(offset))

    def read_game_int(self, offset: int) -> int:
        return self.read_int(self.addr(offset))

    def read_game_pointer(self, offset: int) -> int:
        return self.read_pointer(self.addr(offset))

    def read_game_word(self, offset: int) -> int:
        return self.read_word(self.addr(offset))

    def read_game_byte(self, offset: int) -> int:
        return self.read_byte(self.addr(offset))

    # ------------------------------------------------------------------
    # Pattern scanning
    # ------------------------------------------------------------------

    def pattern_scan(self, pattern: bytes, mask: str, start: int = 0, size: int = 0) -> int:
        """
        Scan the Game.exe module for a byte pattern.

        *pattern*: raw bytes to match.
        *mask*: string of 'x' (must match) and '?' (wildcard), same length as pattern.
        Returns the absolute address of the first match, or 0 if not found.
        """
        if not start:
            start = self.info.base_address
        if not size:
            size = self.info.module_size

        try:
            data = self.read_bytes(start, size)
        except OSError:
            return 0

        plen = len(pattern)
        for i in range(len(data) - plen):
            match = True
            for j in range(plen):
                if mask[j] == "x" and data[i + j] != pattern[j]:
                    match = False
                    break
            if match:
                return start + i
        return 0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_base_address(self) -> bool:
        """Find the base address of Game.exe in the target process."""
        snap = CreateToolhelp32Snapshot(
            TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, self.info.pid
        )
        if snap == INVALID_HANDLE_VALUE:
            log.error("Module snapshot failed: %d", GetLastError())
            return False

        try:
            me = MODULEENTRY32()
            me.dwSize = ctypes.sizeof(MODULEENTRY32)
            if not Module32First(snap, ctypes.byref(me)):
                log.error("Module32First failed: %d", GetLastError())
                return False

            while True:
                mod_name = me.szModule.lower()
                if mod_name == b"game.exe":
                    self.info.base_address = ctypes.cast(
                        me.modBaseAddr, ctypes.c_void_p
                    ).value or 0
                    self.info.module_size = me.modBaseSize
                    self.info.exe_path = me.szExePath.decode("ascii", "replace")
                    return True
                if not Module32Next(snap, ctypes.byref(me)):
                    break
        finally:
            CloseHandle(snap)

        log.error("Game.exe module not found in PID %d", self.info.pid)
        return False

    def __del__(self) -> None:
        self.detach()

    def __repr__(self) -> str:
        if self.info.attached:
            return f"<ProcessManager pid={self.info.pid} base=0x{self.info.base_address:08X}>"
        return "<ProcessManager detached>"
