"""
.dbj (D2BS JavaScript) to Python transpiler.

Converts original Kolbot .dbj scripts into executable Python code
that runs against our ScriptAPI.  The transpiler handles:

- ``var`` → ``<removed>`` (Python doesn't need it)
- ``function name(args)`` → ``def name(args):``
- ``for/while/if/else`` block syntax ``{ }`` → ``:`` + indent
- ``===`` / ``!==`` → ``==`` / ``!=``
- ``true/false/null`` → ``True/False/None``
- ``this.`` → ``self.``
- Common D2BS API calls mapped to Python equivalents
- ``//`` comments → ``#`` comments
- Array/object literals (basic support)

This is a best-effort transpiler. Complex JS patterns (closures,
prototypes, dynamic ``this``) may need manual adjustment.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from kolbot.utils.logger import get_logger

log = get_logger("scripts.transpiler")


class DBJTranspiler:
    """
    Transpiles .dbj JavaScript files to Python.

    Usage::

        transpiler = DBJTranspiler()
        python_code = transpiler.transpile_file("libs/common/Pather.dbj")
        # or
        python_code = transpiler.transpile(js_source_code)
    """

    def __init__(self) -> None:
        self._indent_level = 0

    def transpile_file(self, path: str | Path) -> str:
        """Read a .dbj file and return transpiled Python source."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"DBJ file not found: {path}")
        source = path.read_text(encoding="utf-8", errors="replace")
        return self.transpile(source)

    def transpile(self, source: str) -> str:
        """Transpile JavaScript source to Python source."""
        lines = source.splitlines()
        output_lines: list[str] = []
        self._indent_level = 0

        # Header
        output_lines.append("# Auto-transpiled from .dbj by Kolbot-Python")
        output_lines.append("# Manual review recommended for complex logic")
        output_lines.append("")

        i = 0
        while i < len(lines):
            line = lines[i]
            converted = self._convert_line(line)
            if converted is not None:
                output_lines.append(converted)
            i += 1

        result = "\n".join(output_lines)

        # Post-processing passes
        result = self._fix_empty_blocks(result)
        result = self._fix_indent_consistency(result)

        return result

    def _convert_line(self, line: str) -> Optional[str]:
        """Convert a single line of JS to Python."""
        # Preserve blank lines
        stripped = line.strip()
        if not stripped:
            return ""

        # Get current indentation from the JS source
        indent = self._get_indent(line)

        # Handle closing brace
        if stripped == "}":
            self._indent_level = max(0, self._indent_level - 1)
            return None  # closing braces don't produce output in Python

        if stripped == "};":
            self._indent_level = max(0, self._indent_level - 1)
            return None

        if stripped.startswith("}") and ("else" in stripped or "catch" in stripped):
            self._indent_level = max(0, self._indent_level - 1)
            # Fall through to handle else/catch

        # Apply transformations
        result = stripped

        # Comments: // → #
        result = re.sub(r"//(.*)$", r"# \1", result)

        # Multi-line comment start/end (basic)
        result = result.replace("/*", '"""').replace("*/", '"""')

        # Variable declarations
        result = re.sub(r"\bvar\s+", "", result)
        result = re.sub(r"\blet\s+", "", result)
        result = re.sub(r"\bconst\s+", "", result)

        # Boolean/null literals
        result = result.replace("true", "True").replace("false", "False")
        result = result.replace("null", "None").replace("undefined", "None")

        # Strict equality
        result = result.replace("===", "==").replace("!==", "!=")

        # this. → self.
        result = result.replace("this.", "self.")

        # Logical operators
        result = result.replace("&&", " and ").replace("||", " or ")
        result = re.sub(r"(?<!\w)!(?!=)", "not ", result)

        # typeof x === "string" → isinstance(x, str)
        result = re.sub(
            r'typeof\s+(\w+)\s*==\s*"string"',
            r"isinstance(\1, str)",
            result,
        )
        result = re.sub(
            r'typeof\s+(\w+)\s*==\s*"number"',
            r"isinstance(\1, (int, float))",
            result,
        )

        # Function declaration: function name(args) { → def name(args):
        m = re.match(r"function\s+(\w+)\s*\((.*?)\)\s*\{?\s*$", result)
        if m:
            fname, args = m.group(1), m.group(2)
            result = f"def {fname}({args}):"
            self._indent_level += 1
            return self._make_indent() + result

        # Anonymous function assigned: var x = function(args) {
        m = re.match(r"(\w+)\s*=\s*function\s*\((.*?)\)\s*\{?\s*$", result)
        if m:
            vname, args = m.group(1), m.group(2)
            result = f"def {vname}({args}):"
            self._indent_level += 1
            return self._make_indent() + result

        # if/else if/else
        m = re.match(r"if\s*\((.*)\)\s*\{?\s*$", result)
        if m:
            cond = m.group(1)
            cond = self._fix_condition(cond)
            result = f"if {cond}:"
            self._indent_level += 1
            return self._make_indent() + result

        m = re.match(r"\}?\s*else\s+if\s*\((.*)\)\s*\{?\s*$", result)
        if m:
            cond = m.group(1)
            cond = self._fix_condition(cond)
            result = f"elif {cond}:"
            self._indent_level += 1
            return self._make_indent() + result

        if re.match(r"\}?\s*else\s*\{?\s*$", result):
            result = "else:"
            self._indent_level += 1
            return self._make_indent() + result

        # for loops
        m = re.match(r"for\s*\(\s*(\w+)\s*=\s*(\d+)\s*;\s*\1\s*<\s*(.+?)\s*;\s*\1\+\+\s*\)\s*\{?\s*$", result)
        if m:
            var, start, end = m.group(1), m.group(2), m.group(3)
            result = f"for {var} in range({start}, {end}):"
            self._indent_level += 1
            return self._make_indent() + result

        # while loop
        m = re.match(r"while\s*\((.*)\)\s*\{?\s*$", result)
        if m:
            cond = self._fix_condition(m.group(1))
            result = f"while {cond}:"
            self._indent_level += 1
            return self._make_indent() + result

        # do { → while True:  (with break at end of block)
        if result.strip() == "do {" or result.strip() == "do":
            result = "while True:"
            self._indent_level += 1
            return self._make_indent() + result

        # switch/case (basic → if/elif chain)
        m = re.match(r"switch\s*\((.*)\)\s*\{?\s*$", result)
        if m:
            # We'll convert to if/elif, storing the switch variable
            result = f"_switch_val = {m.group(1)}"
            return self._make_indent() + result

        m = re.match(r"case\s+(.+?)\s*:", result)
        if m:
            result = f"if _switch_val == {m.group(1)}:"
            self._indent_level += 1
            return self._make_indent() + result

        if result.strip() == "break;":
            result = "break"
            return self._make_indent() + result

        if result.strip().startswith("return"):
            result = result.rstrip(";")
            return self._make_indent() + result

        # try/catch
        m = re.match(r"try\s*\{?\s*$", result)
        if m:
            result = "try:"
            self._indent_level += 1
            return self._make_indent() + result

        m = re.match(r"\}?\s*catch\s*\((.*?)\)\s*\{?\s*$", result)
        if m:
            result = f"except Exception as {m.group(1)}:"
            self._indent_level += 1
            return self._make_indent() + result

        # .length → len()
        result = re.sub(r"(\w+)\.length", r"len(\1)", result)

        # .push(x) → .append(x)
        result = result.replace(".push(", ".append(")

        # .indexOf(x) → .index(x)  (approximate)
        result = result.replace(".indexOf(", ".index(")

        # new Array() → []
        result = re.sub(r"new\s+Array\(\)", "[]", result)

        # Math.floor/ceil/round
        result = result.replace("Math.floor(", "int(")
        result = result.replace("Math.ceil(", "math.ceil(")
        result = result.replace("Math.round(", "round(")
        result = result.replace("Math.random()", "random.random()")
        result = result.replace("Math.abs(", "abs(")
        result = result.replace("Math.min(", "min(")
        result = result.replace("Math.max(", "max(")

        # Remove trailing semicolons
        result = result.rstrip(";").rstrip()

        # Remove trailing { that opens a block
        if result.endswith("{"):
            result = result[:-1].rstrip()
            if not result.endswith(":"):
                result += ":"
            self._indent_level += 1

        return self._make_indent() + result

    def _make_indent(self) -> str:
        return "    " * max(0, self._indent_level - 1)

    def _get_indent(self, line: str) -> int:
        count = 0
        for ch in line:
            if ch == "\t":
                count += 4
            elif ch == " ":
                count += 1
            else:
                break
        return count

    def _fix_condition(self, cond: str) -> str:
        """Fix common JS condition patterns for Python."""
        cond = cond.replace("===", "==").replace("!==", "!=")
        cond = cond.replace("&&", " and ").replace("||", " or ")
        cond = cond.replace("true", "True").replace("false", "False")
        cond = cond.replace("null", "None")
        return cond

    def _fix_empty_blocks(self, source: str) -> str:
        """Add `pass` to empty blocks."""
        lines = source.splitlines()
        result: list[str] = []
        for i, line in enumerate(lines):
            result.append(line)
            if line.rstrip().endswith(":"):
                # Check if next non-empty line is at same or lower indent
                next_indent = None
                for j in range(i + 1, len(lines)):
                    if lines[j].strip():
                        next_indent = len(lines[j]) - len(lines[j].lstrip())
                        break
                current_indent = len(line) - len(line.lstrip())
                if next_indent is not None and next_indent <= current_indent:
                    result.append(" " * (current_indent + 4) + "pass")
                elif next_indent is None:
                    result.append(" " * (current_indent + 4) + "pass")
        return "\n".join(result)

    def _fix_indent_consistency(self, source: str) -> str:
        """Ensure consistent 4-space indentation."""
        lines = source.splitlines()
        result: list[str] = []
        for line in lines:
            # Replace tabs with 4 spaces
            line = line.replace("\t", "    ")
            result.append(line)
        return "\n".join(result)


def transpile_file(path: str | Path) -> str:
    """Convenience function: transpile a .dbj file to Python."""
    return DBJTranspiler().transpile_file(path)


def transpile_directory(src_dir: str | Path, out_dir: str | Path) -> int:
    """
    Transpile all .dbj files in a directory tree.

    Returns the number of files transpiled.
    """
    src_dir = Path(src_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    transpiler = DBJTranspiler()
    count = 0

    for dbj_file in src_dir.rglob("*.dbj"):
        rel = dbj_file.relative_to(src_dir)
        out_file = out_dir / rel.with_suffix(".py")
        out_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            python_code = transpiler.transpile_file(dbj_file)
            out_file.write_text(python_code, encoding="utf-8")
            count += 1
            log.info("Transpiled: %s → %s", dbj_file, out_file)
        except Exception:
            log.exception("Failed to transpile: %s", dbj_file)

    log.info("Transpiled %d .dbj files", count)
    return count
