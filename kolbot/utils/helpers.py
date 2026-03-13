"""
General-purpose helper utilities.
"""

from __future__ import annotations

import math
import time
import ctypes
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def distance(x1: int, y1: int, x2: int, y2: int) -> float:
    """Euclidean distance between two map coordinates."""
    return math.hypot(x2 - x1, y2 - y1)


def direction_to(x1: int, y1: int, x2: int, y2: int) -> float:
    """Angle in degrees from (x1,y1) to (x2,y2). 0=East, 90=North."""
    return math.degrees(math.atan2(y1 - y2, x2 - x1)) % 360


def point_in_rect(
    px: int, py: int, rx: int, ry: int, rw: int, rh: int
) -> bool:
    """Check if point (px,py) is inside rectangle (rx,ry,rw,rh)."""
    return rx <= px < rx + rw and ry <= py < ry + rh


# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------


class Stopwatch:
    """Simple high-resolution stopwatch."""

    __slots__ = ("_start",)

    def __init__(self) -> None:
        self._start = time.perf_counter()

    def reset(self) -> None:
        self._start = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000.0

    @property
    def elapsed_s(self) -> float:
        return time.perf_counter() - self._start


class Cooldown:
    """Reusable cooldown timer for skills / actions."""

    __slots__ = ("_interval_ms", "_last")

    def __init__(self, interval_ms: float) -> None:
        self._interval_ms = interval_ms
        self._last = 0.0

    @property
    def ready(self) -> bool:
        return (time.perf_counter() - self._last) * 1000.0 >= self._interval_ms

    def trigger(self) -> None:
        self._last = time.perf_counter()

    def trigger_if_ready(self) -> bool:
        if self.ready:
            self.trigger()
            return True
        return False


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------


def retry(attempts: int = 3, delay: float = 0.5):
    """Decorator: retry a function up to *attempts* times on exception."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for i in range(attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if i < attempts - 1:
                        time.sleep(delay)
            raise RuntimeError(
                f"{func.__name__} failed after {attempts} attempts"
            ) from last_exc

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# ctypes helpers
# ---------------------------------------------------------------------------


def read_null_terminated_string(buffer: bytes, encoding: str = "ascii") -> str:
    """Read a null-terminated string from a bytes buffer."""
    idx = buffer.find(b"\x00")
    if idx == -1:
        return buffer.decode(encoding, errors="replace")
    return buffer[:idx].decode(encoding, errors="replace")


def make_buffer(size: int) -> ctypes.Array[ctypes.c_char]:
    """Create a writable ctypes buffer of *size* bytes."""
    return ctypes.create_string_buffer(size)


# ---------------------------------------------------------------------------
# Bit helpers
# ---------------------------------------------------------------------------


def get_bit(value: int, bit: int) -> bool:
    return bool((value >> bit) & 1)


def set_bit(value: int, bit: int) -> int:
    return value | (1 << bit)


def clear_bit(value: int, bit: int) -> int:
    return value & ~(1 << bit)
