# Kolbot-Python

**Modern Diablo II Lord of Destruction 1.14d Bot Framework**

A complete, production-ready botting framework built from scratch in Python 3.12+ for Windows 10/11. Spiritual successor to the original Kolbot/D2BS with emphasis on stability, multi-instance support, packet interception, and .dbj script compatibility.

---

## High-Level Architecture Plan

Kolbot-Python is organized into layered subsystems, each building on the one below:

```
┌─────────────────────────────────────────────────────┐
│  CLI / GUI                                          │
│  (kolbot.cli, kolbot.gui)                           │
├─────────────────────────────────────────────────────┤
│  Multi-Instance Manager                             │
│  (kolbot.multi)                                     │
├─────────────────────────────────────────────────────┤
│  Scripts & Config                                   │
│  (kolbot.scripts — engine, transpiler, API)         │
│  (kolbot.config — profiles, settings, hot-reload)   │
├─────────────────────────────────────────────────────┤
│  Bot Logic                                          │
│  (kolbot.bot — autoplay, combat, pickit, pathing,   │
│   chicken, town_manager)                            │
├─────────────────────────────────────────────────────┤
│  Game Abstractions                                  │
│  (kolbot.game — player, items, skills, inventory,   │
│   belt, mercenary, monsters, map, NPCs, town)       │
├─────────────────────────────────────────────────────┤
│  Core                                               │
│  (kolbot.core — process, memory, packets,           │
│   game_state, structures, offsets)                   │
├─────────────────────────────────────────────────────┤
│  Utilities                                          │
│  (kolbot.utils — logger, helpers)                   │
└─────────────────────────────────────────────────────┘
```

### Memory Reading/Writing

- Uses `ctypes` with `ReadProcessMemory` / `WriteProcessMemory` from `kernel32.dll`
- Dynamically resolves `Game.exe` base address via module enumeration
- Pointer chains walk unit hash tables (128 entries per unit type)
- Stat lists use layer-based resolution (base stats vs full stats with bonuses)
- Game state is refreshed in a background thread at configurable tick rate

### Packet Interception

- Remote thread injection into the game process
- Shared-memory ring buffer for packet data exchange
- Supports both send and receive packet interception
- Packet builder constructs properly formatted game packets
- Used for skill casting, movement, NPC interaction, and game commands

### Script Engine

- Loads and executes native Python scripts or transpiled .dbj scripts
- ScriptAPI provides a D2BS-compatible namespace (`me`, `getUnit()`, `clickMap()`, etc.)
- .dbj transpiler handles `function→def`, `var→`, `===→==`, `true→True`, etc.
- Supports hot-reload via file system watchers (watchdog or polling fallback)

### Multi-Instance Support

- Each instance gets its own thread, profile, logger, and Game.exe attachment
- Instance Manager coordinates startup, shutdown, and status monitoring
- Automatic PID discovery and assignment to avoid conflicts
- Supports 4-8+ simultaneous bot instances

### GUI (Optional)

- Lightweight Dear PyGui dashboard showing instance status, controls, and logs
- Runs in a background thread, does not block the bot
- CLI-first design — GUI is entirely optional

---

## Full Project Structure

```
kolbot-python/
├── kolbot/
│   ├── __init__.py              # Package root, version info
│   ├── cli.py                   # CLI entry point (run, multi, profile, transpile, etc.)
│   │
│   ├── core/                    # Low-level game interaction
│   │   ├── __init__.py
│   │   ├── process.py           # Process discovery, attachment, handle management
│   │   ├── memory.py            # ReadProcessMemory/WriteProcessMemory wrappers
│   │   ├── offsets.py           # All known D2 1.14d memory offsets
│   │   ├── structures.py        # Game data structures (units, stats, items, enums)
│   │   ├── packets.py           # Packet interception, ring buffer, builder, sender
│   │   └── game_state.py        # Background game state snapshot tracker
│   │
│   ├── game/                    # Game abstraction layer
│   │   ├── __init__.py
│   │   ├── player.py            # Player unit, stats, movement, skills
│   │   ├── items.py             # Item classification (runes, gems, keys, etc.)
│   │   ├── skills.py            # Skill ID database (100+ skills)
│   │   ├── inventory.py         # Inventory grid tracking, item placement, identification
│   │   ├── belt.py              # Potion belt management (4-column belt)
│   │   ├── mercenary.py         # Mercenary state and control
│   │   ├── monsters.py          # Monster tracking, classification, boss IDs
│   │   ├── map.py               # Area IDs, waypoints, town detection, connections
│   │   ├── npcs.py              # NPC lookup, roles, interaction
│   │   └── town.py              # Town task coordination (heal, repair, shop, etc.)
│   │
│   ├── bot/                     # High-level bot logic
│   │   ├── __init__.py
│   │   ├── pickit.py            # Rule-based item filtering engine
│   │   ├── chicken.py           # Emergency exit monitor (background thread)
│   │   ├── combat.py            # Combat engine with skill rotation
│   │   ├── pathing.py           # Area-to-area pathfinding (BFS + teleport)
│   │   ├── town_manager.py      # Automated town visit decisions
│   │   └── autoplay.py          # Main bot loop (run sequences, game cycling)
│   │
│   ├── scripts/                 # Script engine
│   │   ├── __init__.py
│   │   ├── engine.py            # Script loading, compilation, execution
│   │   ├── transpiler.py        # .dbj (JavaScript) to Python transpiler
│   │   └── api.py               # D2BS-compatible scripting API
│   │
│   ├── config/                  # Configuration
│   │   ├── __init__.py
│   │   ├── settings.py          # Global settings (Pydantic models)
│   │   ├── profile.py           # Per-bot profile management
│   │   └── hot_reload.py        # File watcher for live config/script reload
│   │
│   ├── multi/                   # Multi-instance
│   │   ├── __init__.py
│   │   └── instance_manager.py  # Manages multiple bot instances
│   │
│   ├── gui/                     # Optional GUI
│   │   ├── __init__.py
│   │   └── app.py               # Dear PyGui dashboard
│   │
│   └── utils/                   # Utilities
│       ├── __init__.py
│       ├── logger.py            # Per-instance logging with file + console output
│       └── helpers.py           # Geometry, timing, retry, bit manipulation
│
├── data/                        # Game data files
│   ├── items.json               # Item codes, names, sizes, types
│   ├── skills.json              # Skill IDs, names, classes, mana costs
│   ├── areas.json               # Area IDs, names, acts, connections
│   └── npcs.json                # NPC IDs, names, services
│
├── scripts/                     # Example bot scripts
│   ├── example_pickit.py        # Advanced pickit configuration
│   └── example_autoplay.py      # Full Blizzard Sorc autoplay setup
│
├── profiles/                    # Bot profiles (created at runtime)
│   └── default/
│       └── config.json
│
├── logs/                        # Log files (created at runtime)
│
├── pyproject.toml               # Project metadata and build config
├── requirements.txt             # Python dependencies
└── README.md                    # This file
```

---

## Setup Instructions

### Prerequisites

- **Windows 10/11** (native — no Wine/Linux support)
- **Python 3.12+** — [Download from python.org](https://www.python.org/downloads/)
- **Diablo II Lord of Destruction 1.14d** — Classic client (not D2R)
- **Visual Studio Code** (recommended) — [Download](https://code.visualstudio.com/)

### Step-by-Step Installation

1. **Clone the repository:**

   ```powershell
   git clone https://github.com/YOUR_ORG/kolbot-python.git
   cd kolbot-python
   ```

2. **Create a virtual environment:**

   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install dependencies:**

   ```powershell
   pip install -r requirements.txt
   ```

4. **Initialize the project:**

   ```powershell
   python -m kolbot.cli init
   ```

   This creates `settings.json`, a default profile, and necessary directories.

5. **Configure your profile:**

   Edit `profiles/default/config.json` with your settings:
   - Account credentials
   - Character class and build
   - Chicken thresholds
   - Run preferences

6. **Start Diablo II** and create/join a game.

7. **Run the bot:**

   ```powershell
   # Auto-detect Game.exe process
   python -m kolbot.cli run default

   # Or specify a PID
   python -m kolbot.cli run default --pid 12345

   # With GUI dashboard
   python -m kolbot.cli run default --gui
   ```

### Multi-Instance Setup

1. Create multiple profiles:

   ```powershell
   python -m kolbot.cli profile create sorc1
   python -m kolbot.cli profile create sorc2
   python -m kolbot.cli profile create hammerdin1
   ```

2. Configure each profile with different characters and settings.

3. Start all instances:

   ```powershell
   python -m kolbot.cli multi --gui
   ```

### Visual Studio Code Setup

1. Open the project folder in VS Code
2. Select the Python interpreter from `.venv`
3. Install recommended extensions: Python, Pylance
4. Use the integrated terminal to run commands

### Useful Commands

```powershell
# List running Game.exe processes
python -m kolbot.cli processes

# List profiles
python -m kolbot.cli profile list

# Transpile a .dbj script
python -m kolbot.cli transpile my_script.dbj -o my_script.py

# Transpile a directory of .dbj scripts
python -m kolbot.cli transpile kolbot_scripts/ -o transpiled/

# Run a single script
python -m kolbot.cli script scripts/example_autoplay.py
```

---

## Example Scripts

### Pickit Configuration (`scripts/example_pickit.py`)

Defines comprehensive item filtering rules:
- **Runes:** Hel+ (index 15+)
- **Uniques:** Always pick rings, amulets, charms; identify weapons/armor
- **Sets:** Pick jewelry, identify everything else
- **Rares:** Pick jewelry and jewels, identify boots and circlets
- **Magic:** Identify charms (looking for 20 life, 5 all res, 7 MF, skillers)
- **Runeword bases:** 4os Monarch, 4os Crystal Sword, eth 4os polearms
- **Potions:** Always pick full rejuvenation potions
- **Custom evaluator:** Complex charm stat checking logic

### Autoplay Configuration (`scripts/example_autoplay.py`)

Full Blizzard Sorceress bot setup:
- **Run sequence:** Mephisto → Pindleskin → Ancient Tunnels → Eldritch/Shenk
- **Combat:** Blizzard primary, Glacial Spike secondary, Static Field on bosses
- **Chicken:** 30% HP exit, 60% HP potion, 40% HP rejuv, hostile detection
- **Town:** Auto heal, identify at Cain, stash valuables, repair, buy potions
- **Game cycling:** 5 min max, 2 min min, 5s delay between games

---

## Limitations and Future Improvements

### What Works

- **Memory reading architecture** — Full pointer chain resolution for units, items, stats, and game state with background refresh thread
- **Packet system** — Builder for all common game packets (movement, skills, NPC interaction, item operations)
- **Game abstraction layer** — Complete coverage of player, items, skills, inventory, belt, mercenary, monsters, map, NPCs, and town operations
- **Bot logic** — Pickit engine, chicken monitor, combat engine, pathfinding, town management, and autoplay controller
- **Script engine** — Native Python scripting + .dbj transpiler with D2BS-compatible API
- **Config system** — Pydantic-validated settings, per-bot profiles, hot-reload support
- **Multi-instance** — Thread-per-instance architecture with separate profiles and logging
- **CLI** — Full command-line interface for all operations
- **GUI** — Optional Dear PyGui dashboard

### Known Limitations

1. **Offset verification** — Memory offsets are based on documented 1.14d values but may need adjustment for specific client builds or patches. The offsets module is centralized for easy updating.

2. **Packet injection** — The remote thread injection approach requires the bot to run with administrator privileges. Some antivirus software may flag this behavior.

3. **Map data** — The framework uses area-to-area adjacency for pathfinding rather than reading the actual collision map from memory. This means within-area pathfinding relies on direct movement/teleport rather than true obstacle avoidance.

4. **.dbj transpiler** — Handles common patterns (functions, loops, conditions, D2BS API calls) but complex JavaScript features (closures, prototypes, async callbacks, `eval`) require manual adjustment after transpilation.

5. **Item identification** — Item stat evaluation works for common stats but complex item interactions (set bonuses, runeword detection by name) may need additional logic.

6. **GUI** — The Dear PyGui dashboard is functional but minimal. It shows instance status and controls but doesn't include item log visualization or map overlay.

7. **Testing** — This framework is designed for Diablo II LoD 1.14d on Windows. It cannot be tested on Linux/macOS or with newer game versions.

### Future Improvements

- **Collision map reading** — Parse the in-memory collision data for true within-area pathfinding
- **D2R support** — Extend to Diablo II Resurrected (different memory layout and anti-cheat considerations)
- **Web dashboard** — Replace Dear PyGui with a web-based UI (Flask/FastAPI + React) for remote monitoring
- **Plugin system** — Allow third-party plugins for custom run types, item evaluators, and combat strategies
- **Statistics database** — SQLite-backed run statistics, drop logging, and performance tracking
- **Network protocol** — Full packet parsing for all game events (currently focused on sending)
- **Advanced .dbj support** — More complete JavaScript transpilation including module system and require() resolution
- **Item price estimation** — Integrate with trade databases for automatic item valuation
- **Visual map overlay** — Render the game map with bot position, monster locations, and path visualization

---

## Technical Notes

### Key Memory Offsets (D2 LoD 1.14d)

| Offset | Description |
|--------|-------------|
| `0x3A6A70` | Player unit pointer |
| `0x3A5E70` | Unit hash table base (players) |
| `0x3A27E8` | In-game flag |
| `0x3A2868` | Area ID |
| `0x3A0608` | Difficulty |

### Item Classification

| Type | txtFileNo Range | Notes |
|------|----------------|-------|
| Runes | 610-642 | El (610) through Zod (642) |
| Gems | 557-601 | Chipped through Perfect, all types |
| Keys | 647-649 | Terror, Hate, Destruction |
| Essences | 650-653 | Twisted, Charged, Burning, Festering |
| Token | 654 | Token of Absolution |
| Organs | 655-657 | Horn, Eye, Brain |

### Grid Dimensions

| Container | Columns | Rows |
|-----------|---------|------|
| Inventory | 10 | 4 |
| Stash | 6 | 8 |
| Cube | 3 | 4 |

---

## License

This project is for educational purposes. Use at your own risk. The authors are not responsible for any consequences of using this software.
