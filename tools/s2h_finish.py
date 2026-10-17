"""Turn Sound2Hap model output (s2h_infer.py) into the daemon's haptic clips.

usage: python3 s2h_finish.py <s2h dir with levels.json> <out dir> [--target 0.45] [--max-sec 1.5]

The model peak-normalises every clip, which erases loudness. Restore it from the source clip's
RMS, compressed (square root) so quiet sounds stay feelable: gain = target * sqrt(rms / median rms).
Category trims, the hit "snap" and the overall level are applied at runtime by the daemon.
"""
import argparse, glob, json, os, wave
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("out")
ap.add_argument("--target", type=float, default=0.45)
ap.add_argument("--max-sec", type=float, default=1.5)
a = ap.parse_args()

levels = json.load(open(os.path.join(a.src, "levels.json")))
med = float(np.median([v["rms"] for v in levels.values() if v["rms"] > 0]))
os.makedirs(a.out, exist_ok=True)
peaks = []
for f in sorted(glob.glob(os.path.join(a.src, "*.wav"))):
    name = os.path.basename(f)
    w = wave.open(f)
    v = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    g = a.target * np.sqrt(levels[name]["rms"] / med)
    v = np.clip(v * min(g, 1.0), -1, 1)
    n = int(a.max_sec * 48000)
    if len(v) > n:
        v = v[:n].copy(); k = 4800; v[-k:] *= np.linspace(1, 0, k)
    o = wave.open(os.path.join(a.out, name), "w")
    o.setnchannels(1); o.setsampwidth(2); o.setframerate(48000)
    o.writeframes((v * 32767).astype(np.int16).tobytes()); o.close()
    peaks.append(float(np.abs(v).max()))
p = np.array(peaks)
print(f"clips {len(p)}  peak p10 {np.percentile(p, 10):.2f}  median {np.median(p):.2f}  p90 {np.percentile(p, 90):.2f}  clipped {(p >= 0.999).sum()}")
