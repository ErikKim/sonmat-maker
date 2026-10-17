"""Auto-classify a game's sound events and derive haptic rules (gain, snap) - no hand-written regex.

usage: python3 classify_events.py <events.txt> <out rules.json> [--log probe_events.txt] [--glossary g.txt]
                                 [--overrides o.json] [--model gemma4:12b-mlx]

events.txt: one event path per line (e.g. SFX/Player/WuKong/Attack/.../EVT_player_wk_atk_zadi_water_light).
--log: a play log with one event path per line; how often each event fires scales it (frequent
       events sit quieter, rare ones may hit harder - "peak strength only for key moments").

A local LLM (Ollama) only maps names to a fixed class + weight. Everything numeric comes from
RULES below, which is the same for every game.
--glossary: a few lines of game-specific vocabulary the model can't know (one "term = meaning" per line).
--overrides: {"regex": {"gain": x, "snap": bool}} taste decisions that win over the classifier.
"""
import argparse, collections, json, re, sys, urllib.request

CLASSES = {
    "my_hit":      "my weapon/attack connecting with an enemy or object",
    "my_swing":    "my attack swinging through air / whoosh, no contact",
    "parry":       "my perfect block / parry / perfect dodge / counter",
    "charge":      "my power charging up or a charge level reached",
    "release":     "releasing a charged / heavy special attack, ground slam, big smash",
    "get_hit":     "me being hit / hurt / knocked down",
    "move":        "my movement: roll, dodge, jump, landing, footstep, sliding",
    "skill":       "my spells, transformations, items, healing",
    "environment": "touching the world: foliage, breaking objects, doors, chests",
    "voice":       "voices, shouts, dialogue",
    "ui":          "menus, HUD, system sounds",
    "other":       "anything else",
}
# class -> (gain, snap). weight scales hits: light / mid / strong.
RULES = {
    "my_hit": (1.0, True), "my_swing": (0.6, False), "parry": (2.0, True), "charge": (1.0, False),
    "release": (1.6, True), "get_hit": (1.0, True), "move": (1.0, False), "skill": (1.0, False),
    "environment": (0.7, False), "voice": (0.0, False), "ui": (0.0, False), "other": (1.0, False),
}
WEIGHT = {"light": 0.6, "mid": 0.8, "strong": 1.0, "none": 1.0}

def ask(model, prompt):
    req = urllib.request.Request("http://localhost:11434/api/generate", data=json.dumps({
        "model": model, "prompt": prompt, "stream": False, "think": False,
        "options": {"temperature": 0, "num_predict": 4096}}).encode(), headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=600))
    if not r.get("response"):
        raise RuntimeError(f"empty response, done_reason={r.get('done_reason')}")
    return r["response"]

def classify(model, paths, glossary=""):
    classes = "\n".join(f"- {k}: {v}" for k, v in CLASSES.items())
    prompt = f"""You label sound events from a video game's audio middleware for controller haptics.
Names may be English, abbreviations, or Chinese pinyin (e.g. zadi=ground smash, xuli=charge up,
zhuangun=staff spin, wosh=whoosh, jingzhunshanbi=perfect dodge, heyao=drink potion, fabao=magic item).
"me/my" = the player character; enemy-side sounds that are not hitting me are "other".
"cast" of a charged move = release. Read names by meaning, not literally.
{glossary}

Classes:
{classes}

weight: "light", "mid" or "strong" from cues like light/mid/strong/heavy, level01..04, combo position; else "none".

Return ONLY a JSON array, one object per event, same order:
[{{"event": "<last path segment>", "class": "<class>", "weight": "<weight>"}}]

Events:
""" + "\n".join(paths)
    txt = ask(model, prompt)
    s, e = txt.find("["), txt.rfind("]")
    return json.loads(txt[s:e + 1])

ap = argparse.ArgumentParser()
ap.add_argument("events"); ap.add_argument("out")
ap.add_argument("--log"); ap.add_argument("--model", default="gemma4:12b-mlx")
ap.add_argument("--batch", type=int, default=25)
ap.add_argument("--glossary"); ap.add_argument("--overrides")
ap.add_argument("--votes", type=int, default=3, help="classify N times (shuffled batches), majority wins")
ap.add_argument("--auto-glossary", help="let the model write the glossary from the full event list first (saved to this path)")
a = ap.parse_args()
def make_glossary(model, paths):
    """Stage 1: the model reads every event name at once and explains the recurring terms."""
    names = "\n".join(p.rsplit("/", 1)[-1] for p in paths)
    prompt = f"""Below are all sound event names of one video game (audio middleware). Many terms recur
(English, abbreviations, Chinese pinyin). Write a short glossary for someone who must label each event
as one of: {", ".join(CLASSES)}.
"me/my" = the player character. For each recurring term give its meaning and, when it decides the
label, which class it implies. Mind word order: e.g. a prefix naming who is hit vs who hits.
Also say how intensity is encoded (light/mid/strong, levels, combo steps).
Output 8-20 lines, each "term = meaning (class hint)". No other text.

Event names:
{names}"""
    return ask(model, prompt).strip()

if a.auto_glossary:
    glossary_text = make_glossary(a.model, paths)
    open(a.auto_glossary, "w", encoding="utf-8").write(glossary_text + "\n")
    print("auto glossary:\n" + glossary_text, file=sys.stderr)
else:
    glossary_text = open(a.glossary, encoding="utf-8").read() if a.glossary else ""
glossary = ("Game vocabulary:\n" + glossary_text) if glossary_text else ""
overrides = [(re.compile(k, re.I), v) for k, v in json.load(open(a.overrides)).items()] if a.overrides else []

paths = [l.strip() for l in open(a.events) if l.strip()]
counts = collections.Counter(l.strip().rsplit("/", 1)[-1] for l in open(a.log)) if a.log else {}
def label_chunk(chunk):
    """{leaf: (class, weight)}; a failing chunk is split in half until it works."""
    leaves = [p.rsplit("/", 1)[-1] for p in chunk]
    for attempt in range(2):
        try:
            got = classify(a.model, chunk, glossary)
            out = {}
            for k, g in enumerate(got):
                ev = str(g.get("event", ""))
                leaf = next((l for l in leaves if ev.endswith(l) or l.endswith(ev) and ev), None)
                if leaf is None and len(got) == len(chunk):
                    leaf = leaves[k]                       # model rewrote the name: trust the order
                if leaf and g.get("class") in CLASSES:
                    out[leaf] = (g["class"], g.get("weight") if g.get("weight") in WEIGHT else "none")
            if len(out) >= len(chunk) * 0.8:
                return out
            print("partial", len(out), "/", len(chunk), file=sys.stderr)
        except Exception as ex:
            print("retry", ex, file=sys.stderr)
    if len(chunk) == 1:
        return {}
    h = len(chunk) // 2
    return {**label_chunk(chunk[:h]), **label_chunk(chunk[h:])}

import random
votes = collections.defaultdict(list)
for v in range(a.votes):
    order = paths[:] if v == 0 else random.Random(v).sample(paths, len(paths))   # different batch neighbours each pass
    for i in range(0, len(order), a.batch):
        chunk = order[i:i + a.batch]
        for leaf, lab in label_chunk(chunk).items():
            votes[leaf].append(lab)
    print(f"pass {v + 1}/{a.votes}", file=sys.stderr, flush=True)
labels, unsure = {}, []
for p in paths:
    leaf = p.rsplit("/", 1)[-1]
    vs = votes.get(leaf) or [("other", "none")]
    cls = collections.Counter(c for c, _ in vs).most_common(1)[0][0]
    weight = collections.Counter(w for c, w in vs if c == cls).most_common(1)[0][0]
    labels[leaf] = (cls, weight)
    if len(set(c for c, _ in vs)) > 1:
        unsure.append(f"{leaf}: {[c for c, _ in vs]}")
if unsure:
    print("split votes (worth a look):\n  " + "\n  ".join(unsure), file=sys.stderr)

seen = sorted(c for c in (counts.get(l, 0) for l in labels) if c)
median = seen[len(seen) // 2] if seen else 1
rules = {}
for leaf, (cls, weight) in labels.items():
    gain, snap = RULES[cls]
    if cls in ("my_hit", "release", "get_hit"):
        gain *= WEIGHT[weight]
    n = counts.get(leaf, 0)
    rarity = min(max((median / n) ** 0.15, 0.8), 1.0) if n else 1.0    # frequent -> softer (rare ones are already strong by class)
    if cls in ("my_hit", "release", "get_hit") and weight == "strong":
        rarity = 1.0                                                     # the big moments keep full strength
    rule = {"class": cls, "weight": weight, "gain": round(gain * rarity, 2), "snap": snap, "count": n}
    for rx, ov in overrides:
        if rx.search(leaf):
            rule.update(ov, override=rx.pattern)
            break
    rules[leaf] = rule
json.dump(rules, open(a.out, "w"), indent=1, ensure_ascii=False)
print(collections.Counter(r["class"] for r in rules.values()))
