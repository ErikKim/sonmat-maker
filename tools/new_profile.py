"""Starting profile for a new game from the model (skill sonmat-new-game).

    python3 tools/new_profile.py <id>          # profiles/<id>/game.json + the model -> profiles/<id>/haptics.json

The code and the model live in the app since 2026-10-20 (it makes profiles itself, "자동 생성"):
sonmat/tools/gamesetup/autosetup.py profile(), sonmat/data/model.json. game.json and the result are as before: an existing
haptics.json is kept as .bak_model, and from then on it is edited by hand.
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.environ.get("SONMAT_TOOLS") or os.path.join(os.path.dirname(ROOT), "sonmat", "tools")
sys.path[:0] = [os.path.dirname(TOOLS), TOOLS]
from gamesetup import autosetup
d = os.path.join(ROOT, "profiles", sys.argv[1])
g = json.load(open(os.path.join(d, "game.json"), encoding="utf-8"))
try:
    rules, empty = autosetup.write_profile(d, g)
except ValueError as e:
    sys.exit(str(e))
print(f"{sys.argv[1]}: {len(rules)} rules from {len([s for s in g['slots'] if g['slots'][s]])} slots -> {os.path.join(d, 'haptics.json')}")
print("empty slots:", empty)
