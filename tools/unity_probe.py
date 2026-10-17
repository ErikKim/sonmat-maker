"""Proof: first setup of an unknown Unity game from its sound names alone.

    unity_probe.py game <game folder> <out.json>     read every AudioClip with UnityPy, classify, measure
    unity_probe.py names <list.txt> <out.json>       classify a list of sound file paths (names only)

The word list below was written before any of the test games was opened and is not changed per game.
"""
import json, os, random, re, sys

# class -> words. A name is cut into words (camelCase, digits, separators); a word matches by prefix.
HAPTIC = {
    "step":    "foot footstep step steps walk walking run running land landing jump dash roll slide skid sprint",
    "hit":     "hit impact punch kick slash sword stab slam smash crash thud bash whack blow bonk strike damage hurt "
               "attack melee swing whoosh swipe swoosh chop slap knock bump clang parry block",
    "gun":     "shot shoot gun gunshot fire rifle pistol laser bullet reload blast cannon bow arrow shotgun missile",
    "explode": "explo explosion boom bomb burst detonat grenade",
    "break":   "break shatter crack glass debris destroy crumble splinter smashed",
    "pickup":  "pick pickup collect coin item grab drop equip powerup heal potion loot throw catch",
    "mech":    "door lever switch gear machine engine motor open close lock unlock chest gate elevator",
}
IGNORE = {
    "music":   "bgm music mus theme song track ost jingle stinger soundtrack score",
    "amb":     "amb ambient ambience ambiance atmo atmosphere wind rain roomtone background crowd birds forest",
    "voice":   "vo voice dialog dialogue speech talk grunt scream shout laugh yell cry npc",
    "ui":      "ui menu button click hover select confirm cancel notify popup cursor tick beep alert",
}
ORDER = ["music", "amb", "ui", "voice", "explode", "break", "gun", "hit", "step", "pickup", "mech"]
WORDS = {k: v.split() for k, v in {**HAPTIC, **IGNORE}.items()}
SHORT = {"vo", "ui", "amb", "mus", "bgm", "ost", "hit", "run", "bow", "cry", "npc"}   # must match whole


def words(name):
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return [w for w in re.split(r"[^a-z]+", s.lower()) if w]


def by_name(name):
    ws = words(name)
    for cls in ORDER:
        for key in WORDS[cls]:
            if any(w == key if key in SHORT else w.startswith(key) for w in ws):
                return cls
    return None


def by_shape(samples, rate):
    """No usable name: decide from the sound itself. samples = mono float array."""
    import numpy as np
    n = len(samples)
    dur = n / float(rate)
    if dur >= 8.0:
        return "long(music/amb)"
    env = np.abs(samples)
    peak = float(env.max()) if n else 0.0
    if peak < 1e-4:
        return "silent"
    attack = float(np.argmax(env >= 0.5 * peak)) / rate        # time to half of the peak
    if dur <= 1.5 and attack <= 0.010:
        return "hit(shape)"
    if dur <= 0.6:
        return "short(shape)"
    return None


def summary(rows, title):
    tot = len(rows)
    named = [r for r in rows if r["by"] == "name"]
    shaped = [r for r in rows if r["by"] == "shape"]
    none = [r for r in rows if r["by"] is None]
    cnt = {}
    for r in rows:
        cnt[r["cls"] or "?"] = cnt.get(r["cls"] or "?", 0) + 1
    print("=== %s: %d sounds" % (title, tot))
    if tot:
        print("  by name %d (%.0f%%) | by shape %d (%.0f%%) | undecided %d (%.0f%%)" % (
            len(named), 100.0 * len(named) / tot, len(shaped), 100.0 * len(shaped) / tot, len(none), 100.0 * len(none) / tot))
    print("  " + ", ".join("%s %d" % kv for kv in sorted(cnt.items(), key=lambda kv: -kv[1])))
    random.seed(7)
    print("  -- sample of named:")
    for r in random.sample(named, min(30, len(named))):
        print("     %-9s %s" % (r["cls"], r["name"]))
    print("  -- sample of undecided:")
    for r in random.sample(none, min(20, len(none))):
        print("     %s" % r["name"])
    return {"total": tot, "by_name": len(named), "by_shape": len(shaped), "undecided": len(none), "classes": cnt}


def run_names(path, out):
    rows = []
    for line in open(path, encoding="utf-8"):
        name = os.path.splitext(os.path.basename(line.strip()))[0]
        if name:
            cls = by_name(name)
            rows.append({"name": name, "cls": cls, "by": "name" if cls else None})
    s = summary(rows, os.path.basename(path))
    json.dump({"summary": s, "rows": rows}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def run_game(folder, out):
    import io, time
    import numpy as np, soundfile as sf, UnityPy
    t0 = time.time()
    env = UnityPy.load(folder)
    rows, seen, fail = [], set(), 0
    for obj in env.objects:
        if obj.type.name != "AudioClip":
            continue
        clip = obj.read()
        name = clip.m_Name
        if name in seen:
            continue
        seen.add(name)
        cls = by_name(name)
        row = {"name": name, "cls": cls, "by": "name" if cls else None,
               "len": round(float(getattr(clip, "m_Length", 0) or 0), 3)}
        if cls is None:
            try:
                wav = next(iter(clip.samples.values()))
                data, rate = sf.read(io.BytesIO(wav), dtype="float32", always_2d=True)
                row["cls"] = by_shape(data.mean(axis=1), rate)
                row["by"] = "shape" if row["cls"] else None
            except Exception as e:
                fail += 1
                row["err"] = type(e).__name__
        rows.append(row)
    s = summary(rows, folder)
    s["seconds"] = round(time.time() - t0, 1)
    s["decode_failed"] = fail
    print("  read + classify: %.1f s, decode failed %d" % (s["seconds"], fail))
    json.dump({"summary": s, "rows": rows}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    (run_game if sys.argv[1] == "game" else run_names)(sys.argv[2], sys.argv[3])
