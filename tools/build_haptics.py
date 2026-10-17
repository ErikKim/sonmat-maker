"""Turn original game SFX into DualSense haptic clips (PS5-style audio-to-haptics).

usage: python3 build_haptics.py <raw wav dir> <out dir> [--max-sec 1.5] [--target 0.6] [--gain G]

- Band 30-500 Hz: the actuators are voice coils, so the low-mid "texture" (water, gravel,
  metal ring) carries over, not just the low thump. (A 300 Hz cut was tried on 10-05 for
  "tearing", but that tearing came from the pad speaker, not the actuators.)
- Linear gain, no per-clip normalisation: a light swing stays lighter than a heavy blow.
  One global gain maps the 90th-percentile clip peak to --target; only peaks above 0.8
  are soft-limited.
- Prints the gain it used; pass --gain to reuse it for another clip set (e.g. footsteps)
  so all sets share one scale.
"""
import argparse, glob, os, wave
import numpy as np
from scipy.signal import butter, sosfilt, resample_poly

SR = 48000
BAND = butter(4, [30, 500], "band", fs=SR, output="sos")

def load(path):
    w = wave.open(path)
    ch, sr = w.getnchannels(), w.getframerate()
    a = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, ch).astype(np.float32).mean(axis=1) / 32768
    return resample_poly(a, SR, sr).astype(np.float32) if sr != SR else a

def save(path, a):
    o = wave.open(path, "w")
    o.setnchannels(1); o.setsampwidth(2); o.setframerate(SR)
    o.writeframes((np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes()); o.close()

def soft_limit(x, knee=0.8):
    over = np.abs(x) > knee
    y = x.copy()
    y[over] = np.sign(x[over]) * (knee + (1 - knee) * np.tanh((np.abs(x[over]) - knee) / (1 - knee)))
    return y

def cap(a, sec):
    n = int(sec * SR)
    if len(a) > n:
        a = a[:n].copy(); f = SR // 10; a[-f:] *= np.linspace(1, 0, f)
    return a

ap = argparse.ArgumentParser()
ap.add_argument("raw"); ap.add_argument("out")
ap.add_argument("--max-sec", type=float, default=1.5)
ap.add_argument("--target", type=float, default=0.6)
ap.add_argument("--gain", type=float)
a = ap.parse_args()

os.makedirs(a.out, exist_ok=True)
clips = {os.path.basename(f): sosfilt(BAND, load(f)).astype(np.float32) for f in sorted(glob.glob(os.path.join(a.raw, "*.wav")))}
peaks = np.array([np.abs(c).max() for c in clips.values()])
gain = a.gain or a.target / np.percentile(peaks, 90)
for name, c in clips.items():
    save(os.path.join(a.out, name), cap(soft_limit(c * gain), a.max_sec))
out = np.minimum(peaks * gain, 1)
print(f"clips {len(clips)}  gain {gain:.2f}  peak p10 {np.percentile(out, 10):.2f}  median {np.median(out):.2f}  p90 {np.percentile(out, 90):.2f}")
