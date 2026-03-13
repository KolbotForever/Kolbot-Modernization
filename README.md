The complete Kolbot-Python framework is done. Here's what was built:

53 files, ~11,000 lines of Python — a full botting framework for Diablo II LoD 1.14d built from scratch.

Architecture (8 layers):

Core — Process attachment, memory R/W via ctypes, packet interception with ring buffers, background game state snapshots

Game — Player, items, skills, inventory (4x10), belt (4-col), mercenary, monsters, map (136 areas), NPCs, town tasks

Bot — Pickit engine (rule-based filtering), chicken monitor (background thread), combat engine (skill rotation, boss tactics), BFS pathfinding, autoplay controller with run sequences

Scripts — Native Python scripting + .dbj transpiler with D2BS-compatible API (me, getUnit(), clickMap(), etc.)

Config — Pydantic-validated settings, per-bot profiles, hot-reload via watchdog

Multi — Thread-per-instance manager supporting 4-8+ simultaneous bots

CLI — Full CLI (run, multi, profile, transpile, script, processes, init)

GUI — Optional Dear PyGui dashboard

Example scripts included:

Advanced pickit config (uniques, sets, rares, runeword bases, charms with custom stat evaluation)

Full Blizzard Sorc autoplay (Mephisto → Pindleskin → Ancient Tunnels → Eldritch/Shenk rotation)

I don't have write access to a GitHub repo to create a PR. I've attached the complete project as a tarball. To use it:

Extract and cd kolbot-python/

python -m venv .venv && .venv\Scripts\activate

pip install -r requirements.txt

python -m kolbot.cli init

Edit profiles/default/config.json

python -m kolbot.cli run default
