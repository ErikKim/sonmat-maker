"""Make staff-hit haptics read by material (Sound2Hap output is ~250 Hz for every material).

usage: python3 shape_materials.py <trees_bang.json> <hap dir in> <hap dir out>

Each source clip is shaped by the material(s) of the hit events that use it:
  flesh  (meat, bone, hardinsect)      low thud: low-pass 140 Hz, body kept, x1.15
  hard   (wood, shieldwood, stone)     dry knock: tail cut after 60 ms (tau 35 ms)
  metal  (metal, shieldmetal)          ring: high-pass 160 Hz, tail kept, x0.9
Clips shared by several groups (e.g. "_all" variants) are left as they are.
"""
import json, os, re, sys, wave
import numpy as np
from scipy.signal import butter, sosfilt

SR = 48000
GROUP = {"meat": "flesh", "bone": "flesh", "hardinsect": "flesh",
         "wood": "hard", "shieldwood": "hard", "stone": "hard",
         "metal": "metal", "shieldmetal": "metal"}
trees, src, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)

def walk(t, acc):
    if t["t"] == "s": acc.add(t["id"])
    for c in t.get("c", []): walk(c, acc)
    return acc

groups = {}
for name, t in json.load(open(trees)).items():
    g = GROUP.get(re.search(r"_([a-z]+)$", name).group(1))
    for i in walk(t, set()):
        groups.setdefault(i, set()).add(g)

lp, hp = butter(2, 140, "low", fs=SR, output="sos"), butter(2, 160, "high", fs=SR, output="sos")
n = {}
for i, gs in groups.items():
    f = os.path.join(src, f"{i}.wav")
    if not os.path.exists(f) or len(gs) != 1 or None in gs:
        continue
    g = next(iter(gs))
    a = np.frombuffer(wave.open(f).readframes(10**8), np.int16).astype(np.float32) / 32768
    if g == "flesh":
        y = sosfilt(lp, a); y *= 1.15 * np.abs(a).max() / max(np.abs(y).max(), 1e-6)
    elif g == "hard":
        t = np.arange(len(a)) / SR
        y = a * np.where(t < 0.06, 1.0, np.exp(-(t - 0.06) / 0.035))
    else:
        y = sosfilt(hp, a) * 0.9 * np.abs(a).max() / max(np.abs(sosfilt(hp, a)).max(), 1e-6)
    o = wave.open(os.path.join(out, f"{i}.wav"), "w")
    o.setnchannels(1); o.setsampwidth(2); o.setframerate(SR)
    o.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes()); o.close()
    n[g] = n.get(g, 0) + 1
print("shaped", n)
