"""Cutscene SFX beds -> faint haptic tracks (impacts only).

usage: python3 build_cutscene_haptics.py <wav dir (48 kHz mono)> <out dir> [--target 0.35] [--rate 4000]

A cutscene's SFX event is the whole scene's bed (median ~40 s, up to ~10 min). Turning all of it
into vibration would rumble the pad for the entire scene, so only transients pass: the 30-500 Hz
band is gated by how far its short-term energy (20 ms) rises above the scene's own slow level
(1.5 s). Footfalls, hits, doors and explosions come through; wind, rain and drones stay out.
One global gain maps the 99th-percentile peak of all scenes to --target (faint by design: the
pad is a layer under the TV, cutscenes even more so).

Output is stored at --rate Hz (the band ends at 500 Hz) to keep ~4.5 hours of tracks small; the
daemon upsamples to 48 kHz when it plays one.
"""
import argparse, glob, os, wave
import numpy as np
from scipy.signal import butter, sosfilt, resample_poly
from scipy.ndimage import uniform_filter1d

SR = 48000
BAND = butter(4, [30, 500], "band", fs=SR, output="sos")

def load(path):
    w = wave.open(path)
    return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768

def gate(x):
    e = np.sqrt(uniform_filter1d(x * x, int(0.02 * SR)) + 1e-12)         # 20 ms energy
    slow = uniform_filter1d(e, int(1.5 * SR))                              # the scene's own level
    g = np.clip((e - 1.6 * slow) / (e + 1e-9), 0, 1)                       # only what stands out
    # attack 2 ms / release 80 ms so a hit keeps its body instead of chattering
    a, r = np.exp(-1 / (0.002 * SR)), np.exp(-1 / (0.08 * SR))
    out = np.empty_like(g); s = 0.0
    for i in range(0, len(g), 48):                                         # 1 ms steps are plenty
        v = g[i:i + 48].max()
        s = v + (s - v) * (a ** 48 if v > s else r ** 48)
        out[i:i + 48] = s
    return x * out

ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("out")
ap.add_argument("--target", type=float, default=0.35)
ap.add_argument("--rate", type=int, default=4000)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)

tracks = {}
for f in sorted(glob.glob(os.path.join(a.src, "*.wav"))):
    tracks[os.path.basename(f)] = gate(sosfilt(BAND, load(f)).astype(np.float32)).astype(np.float32)
peaks = np.array([np.percentile(np.abs(t), 99.9) for t in tracks.values() if len(t)])
gain = a.target / max(np.percentile(peaks, 99), 1e-6)
for name, t in tracks.items():
    y = np.tanh(t * gain / 0.9) * 0.9                                      # soft ceiling
    y = resample_poly(y, a.rate, SR).astype(np.float32)
    o = wave.open(os.path.join(a.out, name), "w")
    o.setnchannels(1); o.setsampwidth(2); o.setframerate(a.rate)
    o.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes()); o.close()
active = [float(np.mean(np.abs(t * gain) > 0.02)) for t in tracks.values() if len(t)]
print(f"tracks {len(tracks)}  gain {gain:.2f}  time vibrating: median {np.median(active)*100:.1f}%  p90 {np.percentile(active, 90)*100:.1f}%")
