"""Run hapticsd.py for real but with no pad and no game, to try the app window (sonmat.py) on a Mac.

usage: python3 tools/sim_daemon.py <profile id> [event log] [--pads 2]     then: python3 sonmat.py

Audio and HID are stubbed, the given profile counts as the running game, and event lines are appended to
its event file a few times a second: the lines of <event log> (a collect_*.log) in a loop, or without one,
names taken from the profile itself (clip trees, labels, the rules that are plain names). Everything else
is the real daemon: rules, settings.json, the messages to the window, quit.
"""
import os, re, sys, json, time, types, random, socket, threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sd = types.ModuleType("sounddevice"); hid = types.ModuleType("hid")
hid.enumerate = lambda *a: []
sd._terminate = sd._initialize = lambda: None
sys.modules["sounddevice"] = sd; sys.modules["hid"] = hid
sys.path.insert(0, ROOT)
import hapticsd as m

def pool(pr):
    """Event lines this profile reacts to, in its adapter's line format."""
    j = pr.json
    names = set(pr.a.trees) | set(j.get("_labels", {}))
    for r in j.get("rules", []):
        for alt in r["match"].split("|"):
            alt = alt.strip("^$")
            if re.fullmatch(r"[\w:]+", alt):
                names.add(alt + ("x" if alt.endswith("_") else ""))
    if pr.step_event:
        names.add(pr.step_event)
    line = {"wwise": lambda n: "SFX/Player/" + n, "ue4": lambda n: f"ue:{n}|PC_Pino", "mame": lambda n: n}[pr.engine]
    return [line(n) for n in sorted(names)]

def feeder(pr, lines):
    time.sleep(2)
    with open(pr.event_file, "a", encoding="utf-8") as f:
        k = 0
        while True:
            f.write((lines[k % len(lines)] if lines is not POOL else random.choice(lines)) + "\n"); f.flush()
            k += 1
            time.sleep(random.uniform(0.15, 0.9))

def main():
    pid = sys.argv[1]
    n = int(sys.argv[sys.argv.index("--pads") + 1]) if "--pads" in sys.argv else 1
    log = next((a for a in sys.argv[2:] if os.path.isfile(a)), None)
    pads = []
    for k in range(n):
        p = m.Pad.__new__(m.Pad)
        p.name, p.index, p.voices, p.underruns, p.lock = f"sim pad {k + 1}", k, [], 0, threading.Lock()
        def play(w, speaker=False, tag="", pan=0.0, _p=p):
            m.Pad.play(_p, w, speaker, tag, pan)
            _p.voices.clear()                # nothing consumes them here
        p.play = play
        pads.append(p)
    trig = m.Triggers.__new__(m.Triggers); trig.devs, trig.active = [], {}
    trig.send = lambda *a: None
    trig.battery = lambda: [[85 - 40 * k, k == 1] for k in range(n)]
    m.connect = lambda: (pads, trig)
    m.hid_count = lambda: n
    m.maybe_inject = lambda *a, **k: None
    # made-up events must not land in collect_<id>.log (that log is what rules are written from)
    m.open = lambda path, *a, **k: open(os.devnull if os.path.basename(str(path)).startswith("collect_") else path, *a, **k)
    profiles = m.load_profiles()
    key, pr = next((k, p) for k, p in profiles.items() if p.id == pid)
    m.running_exe = lambda names: (key, 1)
    global POOL
    POOL = pool(pr)
    lines = POOL
    if log:                                  # "HH:MM:SS <line>" as hapticsd collects them
        lines = [l.split(" ", 1)[1].strip() for l in open(log, encoding="utf-8", errors="replace") if " " in l]
    print(f"sim: {pid}, {len(lines)} event lines, {n} pad(s) -> {pr.event_file}", flush=True)
    threading.Thread(target=feeder, args=(pr, lines), daemon=True).start()
    lock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    lock.bind(m.CTL); lock.setblocking(False)
    m.main(lock)

POOL = []
if __name__ == "__main__":
    main()
