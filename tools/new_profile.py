"""Starting profile for a new game from the model (skill sonmat-new-game).

    python3 tools/new_profile.py <id>          # profiles/<id>/game.json + profiles/_model/model.json -> profiles/<id>/haptics.json

game.json holds only what is this game's own: the head (name, exe, engine, event_file, native, player, source ...)
and "slots": {slot: regex} - which of its sound names belong to which slot of the model. A slot may also be
[regex, {keys to override}], and "extra_rules" (put first) / "waves" add what the model has no slot for.
The result is an ordinary haptics.json: from then on it is edited by hand (an existing one is kept as .bak_model).
"""
import json, os, re, shutil, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pid = sys.argv[1]
model = json.load(open(os.path.join(ROOT, "profiles", "_model", "model.json"), encoding="utf-8"))
game = json.load(open(os.path.join(ROOT, "profiles", pid, "game.json"), encoding="utf-8"))
d, slots = model["defaults"], game.pop("slots")
unknown = set(slots) - {s["slot"] for s in model["slots"]}
if unknown: sys.exit(f"not in the model: {sorted(unknown)}")
for k, v in slots.items():                       # every regex must compile before anything is written
    re.compile(v[0] if isinstance(v, list) else v)
out = {k: v for k, v in game.items() if k not in ("extra_rules", "waves", "scenes")}
for k in ("master", "duck", "gap", "combat_hold"): out.setdefault(k, d[k])
out["waves"] = dict(model["waves"], **game.get("waves", {}))
rules, top, skip_w, skip_rx, trim, spk = list(game.get("extra_rules", [])), [], set(), [], [], []
# co-op on one PC ("controls" given): what one player's body does and no button says whose it is - walking, landing
# - would reach every pad, so it is not made (user 10-16: "걷는건 굳이 안줘도", a dash has its button)
PERSONAL = ("step", "step_texture", "land", "jump", "dodge", "swing")
coop = {k for k in game.get("controls", {}) if not k.startswith("_")}
wk = model.get("wave_kinds", {})      # how rough each wave is: the kind that thing is in the reference game
for s in model["slots"]:
    v = slots.get(s["slot"])
    if not v or s["area"] == "cutscene": continue
    if coop and s["slot"] in PERSONAL and s["slot"] not in coop: continue
    rx, over = (v[0], v[1]) if isinstance(v, list) else (v, {})
    s = dict(s, **{k: x for k, x in over.items() if not k.startswith("_")})
    r = {"match": rx, "wave": s["wave"], "who": "any", "_slot": s["slot"]}
    for f in ("combat", "combat_only", "player_control", "synth"):
        if s.get(f): r[f] = True
    if "gap" in s: r["gap"] = s["gap"]
    if s.get("drawn"): r["synth"] = True
    rules.append(r)
    if s.get("top"): top += [rx, "^%s$" % s["wave"]]
    if s.get("skip"): skip_w.add(s["wave"]); skip_rx.append(rx)
    if "trim" in s: trim.append([rx, s["trim"]])
    if s.get("speaker"): spk.append(rx)
    if s.get("texture"): out["steps"] = dict(out.get("steps", {}), texture=dict(d["texture"], match=rx))
    if s.get("bed"):                              # held while its sound plays: one bed per name, ended by Stop_<name>
        m = re.fullmatch(r"\^\(\?:(.*)\)\$", rx)
        for n in (m.group(1).split("|") if m else [rx.strip("^$")]):
            out.setdefault("beds", {})[s["slot"] + ":" + n] = dict(s["bed"], on="^%s$" % n, off="^Stop_%s$" % n, wave=s["wave"])
out["rules"] = rules
out["style"] = dict(d["style"], rough="hit", top="|".join(top) or "$^", skip="|".join(["^(%s)$" % "|".join(sorted(skip_w))] + skip_rx))
out["rough"] = {w: wk[w] for w in out["waves"] if w in wk}      # a wave the game adds: give it its kind by hand
out["haptic_trim"] = trim
out["speaker"] = dict(d["speaker"], **game.get("speaker", {}))
if spk and "allow" not in out["speaker"] and not out["speaker"].get("all"):
    out["speaker"]["allow"] = "|".join(spk)      # only the slots marked for the speaker: events share sound files,
                                                 # and "all" sends every one of them to the speaker (NieR, 2026-10-11)
ctl = {k: v for k, v in game.get("controls", {}).items() if not k.startswith("_")}
if ctl:                                           # co-op on one PC: "controls" {slot or trigger: [buttons]} = those sounds
    trg = {k: v["match"] for k, v in game.get("triggers", {}).items() if isinstance(v, dict)}   # go to the pad that
    match = {k: (v[0] if isinstance(v, list) else v) for k, v in slots.items() if v}            # pressed one of them
    match.update(trg)                                                                            # (hapticsd.py "press_owner")
    bad = set(ctl) - set(match) - {"world"}
    if bad: sys.exit(f"controls for slots / triggers this game does not have: {sorted(bad)}")
    out.pop("controls", None)
    ctl.pop("world", None)
    out["press_owner"] = {"window": 0.4, "rules": [[match[k], b] for k, b in ctl.items()]}
    if game.get("controls", {}).get("world") == "speaker" and game.get("speaker", {}).get("allow"):
        # the pad-speaker sounds are the world's news (time's up, an order delivered): every pad, whoever pressed what
        out["press_owner"]["rules"].insert(0, [game["speaker"]["allow"], []])
    if "tool" in trg and "tool" in ctl:           # the tool's end belongs to whoever holds it, too
        out["press_owner"]["rules"].append([game["triggers"]["tool"]["until"], ctl["tool"]])
out["cutscene"] = dict(d["cutscene"], **game.get("cutscene", {}))
if slots.get("scene") and "source" in out:        # scene cues -> long impacts-only tracks (tools/soundprep.py)
    sc = dict(d["scenes"], cues=slots["scene"], skip=slots.get("scene_skip", "$^"), **game.get("scenes", {}))
    out["source"]["scenes"] = sc
    out["cutscene"].update(tracks=sc["trees"], dir=sc["dir"])
if "source" in out:                               # the game's own sounds: which events get a clip, which also sound on the pad
    src = out["source"]
    if spk: src.setdefault("speaker", "|".join(spk))
    if src.get("trees") and src.get("hap"):
        out["clips"] = dict(trees=src["trees"], hap=src["hap"], **({"spk": src["spk"]} if src.get("spk") else {}))
        if src.get("auto_rules"): out["clips"]["auto_rules"] = src["auto_rules"]
    out["snap"] = "|".join(top) or "$^"
out["_made"] = "tools/new_profile.py from profiles/_model/model.json - first values, not felt yet"
p = os.path.join(ROOT, "profiles", pid, "haptics.json")
if os.path.exists(p): shutil.copy2(p, p + ".bak_model")
json.dump(out, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(f"{pid}: {len(rules)} rules from {len([s for s in slots if slots[s]])} slots -> {p}")
print("empty slots:", [s["slot"] for s in model["slots"] if not slots.get(s["slot"])])
