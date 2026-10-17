"""Check (and fix) haptic clips whose onset runs ahead of the sound they belong to.

usage:
  python align_haptics.py check  <sounds dir, e.g. sounds/wukong> [--tol-ms 30]
  python align_haptics.py shift  <sounds dir> <id> [<id> ...]
  python align_haptics.py remake <sounds dir> <id> [--band 30 250] [--peak 0.6] [--decay-ms 60]

Each source id has spk/<id>.wav (the game's sound) and hap/<id>.wav (its haptic). The haptic should
swell when the sound does. A clip cut from the strong part of its source (the title "dudung" started
at the source's 0.28 s) fires at the button press while the sound only rings 0.28 s later.

check  - onset = first time the 10 ms envelope reaches 50 % of its peak; lists clips whose haptic
         onset is earlier than the sound's by more than --tol-ms.
shift  - pads the haptic with silence so its onset lands on the sound's. Keeps its shape.
remake - rebuilds the haptic from the sound itself on the sound's own timeline: band-pass, then an
         envelope follower with a fast decay so it hits when the waveform swells and lets go after.
Originals are kept as hap/<id>.wav.bak_align.
"""
import argparse, os, shutil, wave
import numpy as np
from scipy.signal import butter, sosfilt
from scipy.ndimage import uniform_filter1d, maximum_filter1d

SR = 48000

def load(path):
    w = wave.open(path)
    assert w.getframerate() == SR and w.getnchannels() == 1, path
    return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768

def save(path, a):
    if os.path.exists(path) and not os.path.exists(path + ".bak_align"):
        shutil.copy2(path, path + ".bak_align")
    w = wave.open(path, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes()); w.close()

def envelope(a):
    return np.sqrt(uniform_filter1d(a * a, int(0.01 * SR)) + 1e-12)

def onset(a):
    e = envelope(a)
    return int(np.argmax(e >= 0.5 * e.max())) / SR

def pairs(root, ids=None):
    for f in sorted(os.listdir(os.path.join(root, "hap"))):
        if not f.endswith(".wav"):
            continue
        i = f[:-4]
        if ids and i not in ids:
            continue
        spk = os.path.join(root, "spk", f)
        if os.path.exists(spk):
            yield i, spk, os.path.join(root, "hap", f)

def check(root, tol):
    late = []
    for i, spk, hap in pairs(root):
        d = onset(load(spk)) - onset(load(hap))
        if d * 1000 > tol:
            late.append((d, i))
    for d, i in sorted(late, reverse=True):
        print(f"{i}\thaptic {d * 1000:.0f} ms early")
    print(f"{len(late)} clip(s) over {tol} ms")

def shift(root, ids):
    for i, spk, hap in pairs(root, set(ids)):
        h = load(hap)
        d = onset(load(spk)) - onset(h)
        if d <= 0:
            print(i, "already in time"); continue
        save(hap, np.concatenate([np.zeros(int(d * SR), np.float32), h]))
        print(i, f"shifted {d * 1000:.0f} ms")

def remake(root, ids, band, peak, decay_ms):
    sos = butter(4, band, "band", fs=SR, output="sos")
    for i, spk, hap in pairs(root, set(ids)):
        s = load(spk)
        low = sosfilt(sos, s)
        e = envelope(s)
        # fast attack, decay_ms release: the pad hits on the swell, not on a long tail
        k = np.exp(-1 / (SR * decay_ms / 1000))
        g = np.empty_like(e); acc = 0.0
        for n, x in enumerate(e):
            acc = x if x > acc else acc * k
            g[n] = acc
        rise = np.clip(np.gradient(maximum_filter1d(e, int(0.005 * SR))) * SR * 0.02, 0, 1)
        h = low * (0.5 * g / g.max() + 0.5 * rise)
        h = h / max(np.abs(h).max(), 1e-6) * peak
        save(hap, h.astype(np.float32))
        print(i, f"remade from the sound: onset {onset(h) * 1000:.0f} ms (sound {onset(s) * 1000:.0f} ms)")

ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["check", "shift", "remake"])
ap.add_argument("root")
ap.add_argument("ids", nargs="*")
ap.add_argument("--tol-ms", type=float, default=30)
ap.add_argument("--band", type=float, nargs=2, default=[30, 250])
ap.add_argument("--peak", type=float, default=0.6)
ap.add_argument("--decay-ms", type=float, default=60)
a = ap.parse_args()
if a.cmd == "check":
    check(a.root, a.tol_ms)
elif a.cmd == "shift":
    shift(a.root, a.ids)
else:
    remake(a.root, a.ids, a.band, a.peak, a.decay_ms)
