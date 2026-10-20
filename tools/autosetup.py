"""Moved into the app: sonmat/tools/autosetup.py (2026-10-20 - the app makes a profile itself, "자동 생성").
This runs it with the same commands. `game <id> ...` (an id, not a folder) writes into profiles/<id>/ here, as before.

    python3 tools/autosetup.py detect|judge|names|slots|inputs|game|make ...   (see sonmat/tools/autosetup.py)
"""
import os, runpy, sys
TOOLS = os.environ.get("SONMAT_TOOLS") or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "sonmat", "tools")
if len(sys.argv) > 2 and sys.argv[1] == "game" and not os.sep in sys.argv[2] and "/" not in sys.argv[2]:
    sys.argv[2] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles", sys.argv[2])
sys.path.insert(0, TOOLS)
runpy.run_path(os.path.join(TOOLS, "autosetup.py"), run_name="__main__")
