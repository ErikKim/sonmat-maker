"""The game's own vibration, next to the sounds it played -> which sounds the original shakes the pad on,
and haptic waves drawn from those vibrations (maker tool).

    python3 tools/rumble_report.py <rumble_<exe>.log> <profile id> [--write] [--min-share 0.5] [--min-count 2]

Input: the log dll/rumble_tap.h writes while the game runs with ITS vibration switched on
("<unix ms> xr:<pad>:<left>:<right>" on every change, or "<unix ms> ds:<hex>" when the game drives a
DualSense itself; "<unix ms> ue:<sound>|<owner>" for each sound).
1. Vibrations: from the first non-zero motor value to the next "both zero" (bursts closer than GAP ms are one).
2. Whose vibration: sounds that started just before it (LEAD ms) or just after (LAG ms). Among those the
   one that most reliably comes with a vibration over the whole log wins ("share" = how many of that
   sound's plays had a vibration start with them).
3. Report: per sound - plays, plays with a vibration, share, length, motor peaks, and the profile rule
   that already answers it (or "-": the original vibrates here and we do not).
4. --write: for sounds with no rule, share >= --min-share and at least --min-count vibrations, add a wave
   "ffb_<name>" (the median-length vibration's curve: left motor -> LOW Hz, right motor -> HIGH Hz) and a
   rule to profiles/<id>/haptics.json (the old file is kept as haptics.json.bak_prerumble, once).
The curve is the game's own strength over time; the two carrier frequencies and gains are our choice
(a rumble motor has no pitch to copy) - tune LOW/HIGH/GAIN by feel.
"""
import argparse, collections, json, os, re, shutil, statistics, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAP, LEAD, LAG = 60, 250, 60                 # ms
LOW, HIGH = 65, 170                          # Hz: big (left) motor, small (right) motor
GAIN_LOW, GAIN_HIGH = 0.9, 0.45              # the small motor is the lighter one
MAX_POINTS = 14

TRIG, TRIGS = {}, []                         # trigger effects the game set: [(t, "L2"/"R2", hex of mode + 10 parameters)]

def parse(path):
    xr, snd = collections.defaultdict(list), []
    for l in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"(\d+) (\w+):(.*)", l.strip())
        if not m:
            continue
        t, kind, v = int(m.group(1)), m.group(2), m.group(3)
        if kind == "xr":
            p, a, b = (int(x) for x in v.split(":"))
            xr[p].append((t, a / 65535, b / 65535))
        elif kind == "ds":                   # the DualSense output report the game wrote itself (USB layout)
            b = bytes.fromhex(v)
            if len(b) >= 33:
                if not xr[0] or xr[0][-1][1:] != (b[4] / 255, b[3] / 255):       # big/left motor, small/right motor
                    xr[0].append((t, b[4] / 255, b[3] / 255))
                for name, eff in (("R2", b[11:22]), ("L2", b[22:33])):
                    if TRIG.get(name) != eff:
                        TRIG[name] = eff
                        TRIGS.append((t, name, eff.hex()))
        elif kind == "ue":
            name, _, owner = v.partition("|")
            if not (snd and snd[-1][1] == name and t - snd[-1][0] < 40):      # the hook reports each play twice
                snd.append((t, name, owner))
    return xr, snd

def segments(points):
    """[(start ms, [(dt, left, right), ...])]: one per vibration, ending on the 'motors off' line."""
    out, cur = [], None
    for t, a, b in points:
        on = a > 0 or b > 0
        if cur is None:
            if on:
                if out and t - (out[-1][0] + out[-1][1][-1][0]) < GAP:      # resumed at once: same vibration
                    cur = out.pop()
                    cur[1].append((t - cur[0], a, b))
                else:
                    cur = (t, [(0, a, b)])
        else:
            cur[1].append((t - cur[0], a, b))
            if not on:
                out.append(cur); cur = None
    if cur:
        out.append(cur)
    return out

def simplify(pts, n=MAX_POINTS):
    """Keep the corners of a (t, v) curve: drop the point whose removal changes the line least, until n are left."""
    pts = [list(p) for p in pts]
    while len(pts) > n:
        best, at = None, None
        for i in range(1, len(pts) - 1):
            (t0, v0), (t1, v1), (t2, v2) = pts[i - 1], pts[i], pts[i + 1]
            err = abs(v1 - (v0 + (v2 - v0) * (t1 - t0) / max(1, t2 - t0)))
            if best is None or err < best:
                best, at = err, i
        pts.pop(at)
    return [[int(t), round(v, 3)] for t, v in pts]

def wave_of(steps):
    """A vibration's steps -> a profile wave: the motor values are levels held until the next line."""
    layers = []
    for col, hz, gain in ((1, LOW, GAIN_LOW), (2, HIGH, GAIN_HIGH)):
        pts = []
        for i, s in enumerate(steps):
            if i and s[col] != steps[i - 1][col] and s[0] - steps[i - 1][0] > 25:
                pts.append((s[0] - 1, steps[i - 1][col] * gain))        # a held level, then a step
            pts.append((s[0], s[col] * gain))
        if max(v for _t, v in pts) > 0.01:
            layers.append([hz, simplify(pts)])
    return [{"curve": layers}]

def insert(text, key, lines):
    """Add lines at the end of the top-level "key" block ({...} or [...]) of a hand-laid-out json text,
    leaving every other character as the maker wrote it."""
    at = text.index(f'\n  "{key}":')
    i = min(x for x in (text.find("{", at), text.find("[", at)) if x >= 0)
    depth, quoted, j = 0, False, i
    while True:
        c = text[j]
        if quoted:
            if c == "\\": j += 1
            elif c == '"': quoted = False
        elif c == '"': quoted = True
        elif c in "{[": depth += 1
        elif c in "}]":
            depth -= 1
            if depth == 0: break
        j += 1
    body = text[i + 1:j].rstrip()
    return text[:i + 1] + body + "".join(",\n    " + l for l in lines) + "\n  " + text[j:]

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("log"); ap.add_argument("profile")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--min-share", type=float, default=0.5)
    ap.add_argument("--min-count", type=int, default=2)
    a = ap.parse_args()
    ppath = os.path.join(HERE, "profiles", a.profile, "haptics.json")
    prof = json.load(open(ppath, encoding="utf-8"))
    rules = [(re.compile(r["match"], re.I), r) for r in prof.get("rules", []) if r.get("match")]
    xr, snd = parse(a.log)
    segs = sorted((s for p in xr for s in segments(xr[p])), key=lambda s: s[0])
    plays = collections.Counter(n for _t, n, _o in snd)
    # candidates per vibration, then each sound's share of plays that came with one
    cand = [[(t - s, n) for t, n, _o in snd if -LEAD <= t - s <= LAG] for s, _st in segs]
    with_vib = collections.Counter(n for c in cand for n in {n for _d, n in c})
    share = {n: with_vib[n] / plays[n] for n in with_vib}
    owner = [max(c, key=lambda x: (round(share[x[1]], 2), with_vib[x[1]], -abs(x[0])))[1] if c else None for c in cand]
    by = collections.defaultdict(list)
    for (s, steps), o in zip(segs, owner):
        by[o].append(steps)
    span = (max(snd[-1][0] if snd else 0, segs[-1][0] if segs else 0) - min(snd[0][0] if snd else 0, segs[0][0] if segs else 0)) / 1000
    print(f"{a.log}: {span / 60:.1f} min, {len(snd)} sound plays ({len(plays)} kinds), {len(segs)} vibrations")
    print(f"{'sound':58} {'plays':>5} {'vib':>4} {'share':>5} {'ms':>6} {'L':>4} {'R':>4}  our rule")
    rows, new = [], []
    for name, group in by.items():
        if name is None:
            continue
        dur = statistics.median(st[-1][0] for st in group)
        rule = next((r for rx, r in rules if rx.search(name)), None)
        rows.append((len(group), name, dur, max(max(s[1] for s in st) for st in group), max(max(s[2] for s in st) for st in group), rule))
    for n, name, dur, pl, pr, rule in sorted(rows, key=lambda r: (-r[0], r[1])):
        ok = not rule and share[name] >= a.min_share and n >= a.min_count
        print(f"{name[:58]:58} {plays[name]:5} {n:4} {share[name]:5.2f} {dur:6.0f} {pl:4.2f} {pr:4.2f}  {rule['wave'] if rule and 'wave' in rule else '(rule)' if rule else '-'}{'   <- add' if ok else ''}")
        if ok:
            new.append(name)
    if TRIGS:
        kinds = collections.Counter((n, e) for _t, n, e in TRIGS)
        print(f"\ntrigger effects the game set: {len(TRIGS)} changes, {len(kinds)} different (mode byte first; 00/05 = off)")
        for (n, e), k in kinds.most_common(30):
            first = next(t for t, n2, e2 in TRIGS if (n2, e2) == (n, e))
            near = [x for t, x, _o in snd if -LEAD <= t - first <= LAG]
            print(f"  {n} {e}  x{k}   first with: {', '.join(dict.fromkeys(near[-3:])) or '-'}")
    lone = by.get(None, [])
    if lone:
        print(f"\n{len(lone)} vibrations with no sound within {LEAD} ms before / {LAG} ms after "
              f"(lengths ms: {sorted(int(st[-1][0]) for st in lone)[:30]})")
    if not a.write:
        print(f"\n{len(new)} sounds the original vibrates on and the profile has no rule for. --write adds them.")
        return
    bak = ppath + ".bak_prerumble"
    if not os.path.exists(bak):
        shutil.copy2(ppath, bak)
    waves, added = [], []
    for name in new:
        group = sorted(by[name], key=lambda st: st[-1][0])
        wid = "ffb_" + re.sub(r"^(SE|AMB|SD)_|_Cue$", "", name)
        waves.append(json.dumps(wid) + ": " + json.dumps(wave_of(group[len(group) // 2])))
        added.append(json.dumps({"match": "^" + re.escape(name) + "$", "wave": wid, "who": "any", "_from": "game rumble"}))
    if new:
        text = insert(insert(open(ppath, encoding="utf-8").read(), "waves", waves), "rules", added)
        json.loads(text)                                  # still a profile, or nothing is written
        open(ppath, "w", encoding="utf-8").write(text)
    print(f"\nadded {len(new)} waves + rules to {ppath} (before: {os.path.basename(bak)})")

if __name__ == "__main__":
    main()
