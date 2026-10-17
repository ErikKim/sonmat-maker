"""Wwise event banks -> playback trees for the daemon (any Wwise game).

usage: python3 build_layers.py <wwiser.py> <out.json> <bank dir> [<bank dir> ...]

Each event becomes a tree the daemon renders per trigger, the way Wwise would:
  {"t": "s", "id": sourceID, "g": gain, "d": delay}   one sound
  {"t": "r", "c": [...], "g", "d"}                     random container: pick one child
  {"t": "l", "c": [...], "g", "d"}                     layer / actor-mixer / blend: play all children
Switch containers play their default switch. g = linear gain from the node's Volume (dB),
d = InitialDelay (+ Play action delay) in seconds. Parents outside the bank are ignored.
"""
import glob, json, os, re, subprocess, sys

wwiser, out_path, roots = sys.argv[1], sys.argv[2], sys.argv[3:]

def prop(blk, name):
    # first plain prop bundle of the node: "pID = 0x.. [Name]" ... later "pValue = x" in the same order
    m = re.search(r"cProps = (\d+)\s*\n\s*lst  pProps(.*?)(?=obj  AkPropBundle<RANGED)", blk, re.S)
    if not m:
        return 0.0
    ids = re.findall(r"pID = 0x\w+ \[(\w+)\]", m.group(2))
    vals = re.findall(r"pValue = (-?[\d.e+-]+)", m.group(2))
    return float(vals[ids.index(name)]) if name in ids and len(vals) == len(ids) else 0.0

def parse(txt):
    idx = [m.start() for m in re.finditer(r"eHircType = ", txt)]
    nodes, actions, events = {}, {}, {}
    for blk in (txt[a:b] for a, b in zip(idx, idx[1:] + [len(txt)])):
        kind = re.match(r"eHircType = 0x\w+ \[([^\]]+)\]", blk).group(1)
        m = re.search(r"ulID = (\d+)", blk)
        if not m:
            continue
        oid = int(m.group(1))
        g = 10 ** (prop(blk, "Volume") / 20)
        d = prop(blk, "InitialDelay")
        if kind == "Sound":
            s = re.search(r"sourceID = (\d+)", blk)
            if s:
                nodes[oid] = {"t": "s", "id": int(s.group(1)), "g": g, "d": d}
        elif kind == "Random/Sequence Container":
            nodes[oid] = {"t": "r", "kids": [int(x) for x in re.findall(r"ulChildID = (\d+)", blk)], "g": g, "d": d}
        elif kind == "Switch Container":
            default = re.search(r"ulDefaultSwitch = (\d+)", blk).group(1)
            kids = []
            for pk in re.split(r"obj  CAkSwitchPackage", blk)[1:]:
                if re.search(r"ulSwitchID = (\d+)", pk).group(1) == default:
                    kids = [int(x) for x in re.findall(r" NodeID = (\d+)", pk)]
            nodes[oid] = {"t": "l", "kids": kids, "g": g, "d": d}
        elif kind in ("Layer Container", "Actor-Mixer", "Blend Container"):
            kids = re.search(r"ulNumChilds = \d+(.*?)(?=obj  |\Z)", blk, re.S)
            nodes[oid] = {"t": "l", "kids": [int(x) for x in re.findall(r"ulChildID = (\d+)", kids.group(1) if kids else blk)], "g": g, "d": d}
        elif kind == "Action":
            t = re.search(r"ulActionType = 0x\w+ \[(\w+)\]", blk).group(1)
            ext = re.search(r"idExt = (\d+)", blk)
            if t == "Play" and ext:
                delay = prop(blk, "DelayTime")
                actions[oid] = (int(ext.group(1)), delay / 1000 if delay > 10 else delay)
        elif kind == "Event":
            name = re.search(r"ulID = \d+ \((\w+)\)", blk)
            events[name.group(1) if name else str(oid)] = [int(x) for x in re.findall(r"ulActionID = (\d+)", blk)]
    return nodes, actions, events

def build(nid, nodes, seen=()):
    n = nodes.get(nid)
    if n is None or nid in seen:
        return None
    if n["t"] == "s":
        return dict(n)
    kids = [k for k in (build(c, nodes, seen + (nid,)) for c in n["kids"]) if k]
    if not kids:
        return None
    return {"t": n["t"], "c": kids, "g": n["g"], "d": n["d"]}

out, sources = {}, set()
for root in roots:
    for b in sorted(glob.glob(os.path.join(root, "**", "*.bnk"), recursive=True)):
        name = os.path.basename(b)[:-4]
        if name in out:
            continue
        dump = "/tmp/bl_" + name
        subprocess.run(["python3", wwiser, "-d", "txt", "-dn", dump, b], capture_output=True)
        nodes, actions, events = parse(open(dump + ".txt").read())
        os.remove(dump + ".txt")
        trees = []
        for ev in events.values():
            for a in ev:
                if a in actions:
                    tgt, delay = actions[a]
                    t = build(tgt, nodes)
                    if t:
                        t["d"] = t.get("d", 0) + delay
                        trees.append(t)
        if trees:
            out[name] = trees[0] if len(trees) == 1 else {"t": "l", "c": trees, "g": 1.0, "d": 0.0}

def walk(t):
    if t["t"] == "s":
        sources.add(t["id"])
    for c in t.get("c", []):
        walk(c)
for t in out.values():
    walk(t)
json.dump(out, open(out_path, "w"))
print(f"events {len(out)}  sources {len(sources)}")
