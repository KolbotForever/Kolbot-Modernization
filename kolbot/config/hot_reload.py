"""
Hot-reload support for scripts and configuration.

Watches script and config directories for changes and triggers
reloads without restarting the bot.  Uses the `watchdog` library.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional

from kolbot.utils.logger import get_logger

log = get_logger("config.hot_reload")


class FileWatcher:
    """
    Watches a directory for file changes and triggers callbacks.

    Uses polling as a cross-platform fallback.  If ``watchdog`` is
    available, it uses native OS file system events instead.
    """

    def __init__(
        self,
        watch_dir: str | Path,
        patterns: list[str] | None = None,
        callback: Callable[[str, str], None] | None = None,
        poll_interval: float = 1.0,
    ) -> None:
        """
        Parameters
        ----------
        watch_dir : path to watch
        patterns : file patterns to monitor (e.g. ["*.py", "*.json"])
        callback : called with (event_type, file_path) on changes
        poll_interval : seconds between polls (fallback mode)
        """
        self._dir = Path(watch_dir).resolve()
        self._patterns = patterns or ["*.py", "*.json", "*.dbj"]
        self._callback = callback
        self._poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._file_mtimes: dict[str, float] = {}
        self._use_watchdog = False
        self._observer = None

    def start(self) -> None:
        """Start watching for changes."""
        if self._running:
            return

        self._running = True

        # Try to use watchdog
        try:
            self._start_watchdog()
            self._use_watchdog = True
            log.info("File watcher started (watchdog) on %s", self._dir)
        except ImportError:
            # Fallback to polling
            self._snapshot_files()
            self._thread = threading.Thread(
                target=self._poll_loop, daemon=True, name="file-watcher"
            )
            self._thread.start()
            log.info("File watcher started (polling) on %s", self._dir)

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        if self._use_watchdog and self._observer:
            self._observer.stop()
            self._observer.join(timeout=2.0)
            self._observer = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        log.info("File watcher stopped")

    def _start_watchdog(self) -> None:
        """Start using watchdog library for native FS events."""
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent

        watcher = self

        class Handler(FileSystemEventHandler):
            def on_modified(self, event: FileModifiedEvent) -> None:
                if not event.is_directory:
                    watcher._on_change("modified", event.src_path)

            def on_created(self, event: FileCreatedEvent) -> None:
                if not event.is_directory:
                    watcher._on_change("created", event.src_path)

        self._observer = Observer()
        self._observer.schedule(Handler(), str(self._dir), recursive=True)
        self._observer.start()

    def _poll_loop(self) -> None:
        """Fallback polling loop."""
        while self._running:
            time.sleep(self._poll_interval)
            self._check_changes()

    def _snapshot_files(self) -> None:
        """Take a snapshot of all watched files and their mtimes."""
        self._file_mtimes.clear()
        for pattern in self._patterns:
            for f in self._dir.rglob(pattern):
                try:
                    self._file_mtimes[str(f)] = f.stat().st_mtime
                except OSError:
                    pass

    def _check_changes(self) -> None:
        """Check for file changes since last snapshot."""
        current: dict[str, float] = {}
        for pattern in self._patterns:
            for f in self._dir.rglob(pattern):
                try:
                    current[str(f)] = f.stat().st_mtime
                except OSError:
                    pass

        # Detect modifications and new files
        for fpath, mtime in current.items():
            old_mtime = self._file_mtimes.get(fpath)
            if old_mtime is None:
                self._on_change("created", fpath)
            elif mtime > old_mtime:
                self._on_change("modified", fpath)

        self._file_mtimes = current

    def _on_change(self, event_type: str, file_path: str) -> None:
        """Handle a file change event."""
        # Check if file matches our patterns
        p = Path(file_path)
        if not any(p.match(pat) for pat in self._patterns):
            return

        log.debug("File %s: %s", event_type, file_path)
        if self._callback:
            try:
                self._callback(event_type, file_path)
            except Exception:
                log.exception("File watcher callback error")


class HotReloadManager:
    """
    Coordinates hot-reloading of scripts and config files.

    Watches the scripts/ and profiles/ directories, and triggers
    reloads in the script engine and config system when files change.
    """

    def __init__(self) -> None:
        self._watchers: list[FileWatcher] = []
        self._script_reload_callback: Optional[Callable[[str], None]] = None
        self._config_reload_callback: Optional[Callable[[str], None]] = None

    def set_script_reload_callback(self, callback: Callable[[str], None]) -> None:
        self._script_reload_callback = callback

    def set_config_reload_callback(self, callback: Callable[[str], None]) -> None:
        self._config_reload_callback = callback

    def watch_scripts(self, directory: str | Path) -> None:
        """Watch a scripts directory for changes."""
        watcher = FileWatcher(
            directory,
            patterns=["*.py", "*.dbj"],
            callback=self._on_script_change,
        )
        self._watchers.append(watcher)
        watcher.start()

    def watch_config(self, directory: str | Path) -> None:
        """Watch a config/profiles directory for changes."""
        watcher = FileWatcher(
            directory,
            patterns=["*.json"],
            callback=self._on_config_change,
        )
        self._watchers.append(watcher)
        watcher.start()

    def stop_all(self) -> None:
        for w in self._watchers:
            w.stop()
        self._watchers.clear()

    def _on_script_change(self, event_type: str, file_path: str) -> None:
        log.info("Script file changed: %s (%s)", file_path, event_type)
        if self._script_reload_callback:
            self._script_reload_callback(file_path)

    def _on_config_change(self, event_type: str, file_path: str) -> None:
        log.info("Config file changed: %s (%s)", file_path, event_type)
        if self._config_reload_callback:
            self._config_reload_callback(file_path)
