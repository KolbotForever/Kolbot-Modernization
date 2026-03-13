"""
Script execution engine.

Loads, validates, and executes bot scripts (both native Python
and transpiled .dbj).  Supports hot-reload via file watchers
and provides sandboxed execution with the ScriptAPI namespace.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import threading
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

from kolbot.scripts.api import ScriptAPI
from kolbot.scripts.transpiler import DBJTranspiler
from kolbot.utils.logger import get_logger

log = get_logger("scripts.engine")


class ScriptError(Exception):
    """Raised when a script fails to load or execute."""
    pass


class Script:
    """
    Represents a loaded bot script.

    Can be a native .py file or a transpiled .dbj file.
    """

    def __init__(
        self,
        name: str,
        path: Path,
        source: str,
        entry_point: str = "main",
        is_transpiled: bool = False,
    ) -> None:
        self.name = name
        self.path = path
        self.source = source
        self.entry_point = entry_point
        self.is_transpiled = is_transpiled
        self._compiled: Optional[Any] = None
        self._module_dict: dict[str, Any] = {}

    def compile(self) -> None:
        """Compile the script source to bytecode."""
        try:
            self._compiled = compile(self.source, str(self.path), "exec")
        except SyntaxError as e:
            raise ScriptError(f"Syntax error in {self.name}: {e}") from e

    @property
    def is_compiled(self) -> bool:
        return self._compiled is not None


class ScriptEngine:
    """
    Manages script loading, compilation, and execution.

    Usage::

        engine = ScriptEngine(api)
        engine.load_script("scripts/my_bot.py")
        engine.run_script("my_bot")
    """

    def __init__(self, api: ScriptAPI) -> None:
        self._api = api
        self._scripts: dict[str, Script] = {}
        self._transpiler = DBJTranspiler()
        self._running_scripts: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    @property
    def loaded_scripts(self) -> list[str]:
        return list(self._scripts.keys())

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_script(self, path: str | Path) -> str:
        """
        Load a script from a file path.

        Supports .py (native) and .dbj (auto-transpiled).
        Returns the script name.
        """
        path = Path(path).resolve()
        if not path.exists():
            raise ScriptError(f"Script not found: {path}")

        name = path.stem

        if path.suffix == ".dbj":
            source = self._transpiler.transpile_file(path)
            script = Script(name, path, source, is_transpiled=True)
        elif path.suffix == ".py":
            source = path.read_text(encoding="utf-8")
            script = Script(name, path, source, is_transpiled=False)
        else:
            raise ScriptError(f"Unsupported script type: {path.suffix}")

        script.compile()

        with self._lock:
            self._scripts[name] = script

        log.info("Loaded script: %s (%s)", name, path)
        return name

    def load_directory(self, directory: str | Path) -> int:
        """Load all .py and .dbj scripts from a directory."""
        directory = Path(directory)
        count = 0
        for f in sorted(directory.iterdir()):
            if f.suffix in (".py", ".dbj") and not f.name.startswith("_"):
                try:
                    self.load_script(f)
                    count += 1
                except ScriptError as e:
                    log.error("Failed to load %s: %s", f, e)
        return count

    def reload_script(self, name: str) -> bool:
        """Reload a previously loaded script from disk."""
        with self._lock:
            if name not in self._scripts:
                return False
            path = self._scripts[name].path

        try:
            self.load_script(path)
            log.info("Reloaded script: %s", name)
            return True
        except ScriptError as e:
            log.error("Failed to reload %s: %s", name, e)
            return False

    def unload_script(self, name: str) -> bool:
        """Unload a script."""
        with self._lock:
            if name in self._scripts:
                del self._scripts[name]
                log.info("Unloaded script: %s", name)
                return True
        return False

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run_script(self, name: str, blocking: bool = True) -> bool:
        """
        Execute a loaded script.

        If blocking=True, runs synchronously and returns True on success.
        If blocking=False, runs in a background thread.
        """
        with self._lock:
            script = self._scripts.get(name)
            if not script:
                log.error("Script '%s' not loaded", name)
                return False

        if blocking:
            return self._execute(script)
        else:
            thread = threading.Thread(
                target=self._execute,
                args=(script,),
                daemon=True,
                name=f"script-{name}",
            )
            thread.start()
            with self._lock:
                self._running_scripts[name] = thread
            return True

    def stop_script(self, name: str) -> None:
        """Request a running script to stop (cooperative)."""
        # Scripts should check a stop flag periodically
        with self._lock:
            thread = self._running_scripts.pop(name, None)
        if thread and thread.is_alive():
            log.info("Requesting stop for script: %s", name)
            # We can't forcefully kill threads in Python, but scripts
            # should check the stop flag via api.should_stop

    def _execute(self, script: Script) -> bool:
        """Execute a compiled script in a sandboxed namespace."""
        if not script.is_compiled:
            script.compile()

        # Build execution namespace
        namespace = self._api.build_namespace()
        namespace["__name__"] = script.name
        namespace["__file__"] = str(script.path)

        log.info("Executing script: %s", script.name)

        try:
            exec(script._compiled, namespace)

            # Call the entry point function if it exists
            entry = namespace.get(script.entry_point)
            if callable(entry):
                entry()

            log.info("Script '%s' completed successfully", script.name)
            return True

        except Exception as e:
            log.error(
                "Script '%s' error: %s\n%s",
                script.name,
                e,
                traceback.format_exc(),
            )
            return False

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_script_source(self, name: str) -> Optional[str]:
        """Get the (possibly transpiled) source of a loaded script."""
        with self._lock:
            script = self._scripts.get(name)
            return script.source if script else None

    def transpile_dbj(self, source: str) -> str:
        """Transpile raw .dbj source to Python."""
        return self._transpiler.transpile(source)
