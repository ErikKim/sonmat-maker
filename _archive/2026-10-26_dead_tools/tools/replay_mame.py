"""Feed a MAME plugin event log through hapticsd.py without a pad and report what would have played.

usage: python3 tools/replay_mame.py <scratch dir> <event log> [--id ffight]

Three passes over the same log, in a throwaway copy of the repo (audio/HID stubbed, runs on a Mac):
    clips     the user prepared sounds (tools/soundprep.py): sample-made vibration + pad speaker
    recipes   nothing prepared: shipped recipes for the vibration, no speaker
    synth     no recipes either: the profile's hand-made waves
Per event name: how many vibrations / speaker plays, and their peak. An event with no output in any
pass has no rule. Two fake pads are connected so p2_ events can be seen landing on the second pad only.
"""
import collections, importlib.util, os, shutil, sys, time, types
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sd = types.ModuleType("sounddevice"); hid = types.ModuleType("hid")
hid.enumerate = lambda *a: []
sys.modules["sounddevice"] = sd; sys.modules["hid"] = hid

class Clock:
    t = 1_000_000.0
clock = Clock()
time.time = lambda: clock.t

def build(scratch, pid, mode):
    d = os.path.join(scratch, mode)
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(os.path.join(d, "profiles"))
    for f in ("hapticsd.py", "recipe.py", "sonmat_paths.py"):
        shutil.copy2(os.path.join(ROOT, f), d)
    shutil.copytree(os.path.join(ROOT, "data"), os.path.join(d, "data"))
    shutil.copytree(os.path.join(ROOT, "profiles", pid), os.path.join(d, "profiles", pid))
    clips = next((c for c in (os.path.join(ROOT, "sounds", pid), os.path.join(ROOT, "pad_sfx_" + pid)) if os.path.isdir(c)), None)
    if mode == "clips" and clips:                    # this PC's sounds (sounds/<id>/, or the old pad_sfx_<id>/)
        shutil.copytree(clips, os.path.join(d, "sounds", pid))
    if mode == "synth" and os.path.exists(os.path.join(d, "profiles", pid, "recipes.json")):
        os.remove(os.path.join(d, "profiles", pid, "recipes.json"))
    return d

def run(d, pid, lines):
    sys.path.insert(0, d)
    sys.modules.pop("sonmat_paths", None)            # each copy finds its own sounds/ (sonmat_paths.APP = d)
    spec = importlib.util.spec_from_file_location("hapticsd_" + os.path.basename(d), os.path.join(d, "hapticsd.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    sys.path.pop(0)
    pr = m.Profile(os.path.join(d, "profiles", pid, "haptics.json"))
    m.Pad.profile = pr
    logs = [[], []]
    pads = []
    for k in range(2):
        p = m.Pad.__new__(m.Pad)
        p.name, p.voices, p.underruns, p.beds = f"pad{k + 1}", [], 0, {}
        import threading; p.lock = threading.Lock()
        def play(w, speaker=False, tag="", pan=0.0, _p=p, _log=logs[k]):
            n = len(_p.voices)
            m.Pad.play(_p, w, speaker, tag, pan)
            if len(_p.voices) > n:
                _log.append((cur[0], bool(speaker), float(np.abs(w).max()) if len(w) else 0.0))
                _p.voices.clear()
        p.play = play
        p.stop = lambda rx, fade_ms=30: None
        pads.append(p)
    trig = m.Triggers.__new__(m.Triggers); trig.devs, trig.active = [], {}
    trig.send = lambda *a: None
    eng, cur, seen = m.Engine(), [""], collections.Counter()
    for line in lines:
        frame = line.split(" ", 1)[0]
        if frame.isdigit():
            clock.t = 1_000_000.0 + int(frame) / 60.0
        e = m.ADAPTERS[pr.engine](line, pr, eng.st)
        if e:
            cur[0] = e.name if not e.name.startswith("ram:") else e.name.rsplit(":", 1)[0] + ":" + e.name.rsplit(":", 1)[1]
            seen[cur[0]] += 1
            eng.handle(pr, e, pads, trig)
    return seen, logs

def main():
    scratch, log = sys.argv[1], sys.argv[2]
    pid = sys.argv[sys.argv.index("--id") + 1] if "--id" in sys.argv else "ffight"
    lines = [l.strip() for l in open(log, encoding="utf-8") if l.strip() and not l.startswith("#")]
    lines += ["99999 ram:p2_state:0a>02", "99999 ram:p2_energy:90>80", "99999 snd:00"]     # a second player
    res = {}
    for mode in ("clips", "recipes", "synth"):
        res[mode] = run(build(scratch, pid, mode), pid, lines)
    seen = res["clips"][0]
    def cell(mode, name):
        l1 = res[mode][1][0]
        h = [p for n, s, p in l1 if n == name and not s]
        s = [p for n, sp, p in l1 if n == name and sp]
        return f"{len(h):4d} {max(h, default=0):.2f}" + (f" +spk{len(s)}" if s else "       ")
    print(f"{len(lines)} lines, {sum(seen.values())} events, {len(seen)} kinds.  columns: vibrations, peak [+speaker plays]")
    print(f"{'event':34s} {'n':>5s}   {'clips':17s} {'recipes':17s} {'synth':17s}")
    key = lambda kv: (kv[0].startswith("snd"), -kv[1])
    groups = collections.Counter()
    for name, n in seen.items():
        g = name if name.startswith("snd:") or name.endswith((":down", ":up")) else name.split(":")[1]
        groups[g] += n
    shown = set()
    for name, n in sorted(seen.items(), key=key):
        if name.startswith("ram:") and not name.endswith((":down", ":up")):
            continue                              # raw state changes: summarised below
        print(f"{name:34s} {n:5d}   {cell('clips', name)} {cell('recipes', name)} {cell('synth', name)}")
    raw = collections.Counter(); hits = collections.Counter()
    for name, n in seen.items():
        if name.startswith("ram:") and not name.endswith((":down", ":up")):
            w = name.split(":")[1]
            raw[w] += n
            hits[w] += sum(1 for k, s, p in res["clips"][1][0] + res["clips"][1][1] if k == name)
    for w, n in sorted(raw.items()):
        print(f"ram:{w:30s} {n:5d}   {hits[w]:4d} of them make a vibration (ram rules)")
    for mode in ("clips", "recipes", "synth"):
        l1, l2 = res[mode][1]
        print(f"{mode:8s} pad1: {sum(1 for x in l1 if not x[1])} vibrations, {sum(1 for x in l1 if x[1])} speaker   "
              f"pad2: {len(l2)} ({', '.join(sorted({x[0] for x in l2})) or '-'})")

if __name__ == "__main__":
    main()
