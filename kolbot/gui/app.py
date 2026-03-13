"""
Optional lightweight GUI using Dear PyGui.

Provides a dashboard to monitor and control multiple bot instances,
view logs, edit profiles, and see runtime stats.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Optional

from kolbot.utils.logger import get_logger

if TYPE_CHECKING:
    from kolbot.multi.instance_manager import InstanceManager

log = get_logger("gui.app")


def is_dearpygui_available() -> bool:
    """Check if Dear PyGui is installed."""
    try:
        import dearpygui.dearpygui
        return True
    except ImportError:
        return False


class BotGUI:
    """
    Dear PyGui dashboard for Kolbot-Python.

    Shows instance status, controls, logs, and stats in a
    lightweight native window.
    """

    def __init__(self, instance_manager: "InstanceManager") -> None:
        self._im = instance_manager
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the GUI in a background thread."""
        if not is_dearpygui_available():
            log.warning("Dear PyGui not installed — GUI disabled")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_gui, daemon=True, name="gui"
        )
        self._thread.start()
        log.info("GUI started")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)

    def _run_gui(self) -> None:
        """Build and run the Dear PyGui application."""
        try:
            import dearpygui.dearpygui as dpg

            dpg.create_context()
            dpg.create_viewport(
                title="Kolbot-Python",
                width=900,
                height=600,
                min_width=600,
                min_height=400,
            )

            # --- Main window ---
            with dpg.window(label="Kolbot-Python Dashboard", tag="main_window"):
                dpg.add_text("Kolbot-Python — Modern D2 Bot Framework", color=(255, 215, 0))
                dpg.add_separator()

                # Instance table
                dpg.add_text("Bot Instances", color=(100, 200, 255))
                with dpg.table(
                    tag="instance_table",
                    header_row=True,
                    resizable=True,
                    borders_innerH=True,
                    borders_innerV=True,
                    borders_outerH=True,
                    borders_outerV=True,
                ):
                    dpg.add_table_column(label="Profile")
                    dpg.add_table_column(label="State")
                    dpg.add_table_column(label="PID")
                    dpg.add_table_column(label="Uptime")
                    dpg.add_table_column(label="Error")

                dpg.add_separator()

                # Control buttons
                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Start All",
                        callback=self._on_start_all,
                        width=120,
                    )
                    dpg.add_button(
                        label="Stop All",
                        callback=self._on_stop_all,
                        width=120,
                    )
                    dpg.add_button(
                        label="Refresh",
                        callback=self._on_refresh,
                        width=120,
                    )

                dpg.add_separator()

                # Log area
                dpg.add_text("Recent Log", color=(100, 200, 255))
                dpg.add_input_text(
                    tag="log_output",
                    multiline=True,
                    readonly=True,
                    height=200,
                    width=-1,
                )

            dpg.set_primary_window("main_window", True)
            dpg.setup_dearpygui()
            dpg.show_viewport()

            # Refresh loop
            while dpg.is_dearpygui_running() and self._running:
                self._update_table()
                dpg.render_dearpygui_frame()
                time.sleep(0.1)

            dpg.destroy_context()

        except Exception:
            log.exception("GUI error")

    def _update_table(self) -> None:
        """Update the instance table with current status."""
        try:
            import dearpygui.dearpygui as dpg

            # Clear existing rows
            for child in dpg.get_item_children("instance_table", 1) or []:
                dpg.delete_item(child)

            status = self._im.get_status()
            for name, info in status.items():
                with dpg.table_row(parent="instance_table"):
                    dpg.add_text(name)
                    state = info["state"]
                    color = {
                        "RUNNING": (0, 255, 0),
                        "STOPPED": (150, 150, 150),
                        "ERROR": (255, 0, 0),
                        "STARTING": (255, 255, 0),
                    }.get(state, (255, 255, 255))
                    dpg.add_text(state, color=color)
                    dpg.add_text(str(info["pid"]))
                    dpg.add_text(f"{info['uptime_minutes']:.1f}m")
                    dpg.add_text(info["error"][:40] if info["error"] else "")

        except Exception:
            pass

    def _on_start_all(self) -> None:
        threading.Thread(
            target=self._im.start_all, daemon=True
        ).start()

    def _on_stop_all(self) -> None:
        threading.Thread(
            target=self._im.stop_all, daemon=True
        ).start()

    def _on_refresh(self) -> None:
        self._update_table()
