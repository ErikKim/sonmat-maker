"""Haptic clips -> haptic recipes (json numbers), so the feel ships without any game audio.

usage: python3 clip_to_recipe.py <out recipes.json> <haptic clip dir> [<dir> ...] [--report report.tsv]
                                 [--tol 1.0] [--base-pts 10] [--pts-per-s 60]

Output: {"<dir relative to the repo>": {"<source id>": recipe}} - the keys hapticsd.py looks up when a
clip folder (clips.hap, steps, env, cutscene.dir) has no wav for an id. Haptic folders only: speaker
sounds can't be recipes.

Per band (recipe.BANDS, 30-450 Hz) a recipe keeps the band's centre frequency and its level curve
(3 ms RMS every 1 ms, in dB, reduced to its corner points: --tol dB, at most base + per-second points).
That is what a hand feels from a voice-coil actuator. No phase, nothing above 450 Hz: it can't be
turned back into the sound. hapticsd.py rebuilds the vibration with recipe.synth_recipe.

Fidelity, measured on every clip by rebuilding it: band-envelope correlation (10 ms RMS per band,
weighted by band energy), broadband-envelope correlation, and the time lag between the two envelopes
(cross-correlation). Report = worst first. 10-06 on 20 Wukong charge sounds: band median 0.96, min 0.82,
lag <= 5 ms, ~620 numbers per sound, level matched by RMS. The pad A/B against the original clips is the real judge.
"""
import argparse, glob, json, os, sys, wave
import numpy as np
from scipy.signal import butter, sosfiltfilt, correlate

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from recipe import BANDS, FLOOR, SR, synth_recipe   # the daemon's own synthesis: the report measures what plays

SOS = [butter(4, b, "band", fs=SR, output="sos") for b in BANDS]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load(path):
    w = wave.open(path)
    a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    if w.getframerate() != SR:          # cutscene tracks are stored at 4 kHz
        n = int(len(a) * SR / w.getframerate())
        a = np.interp(np.arange(n) * (w.getframerate() / SR), np.arange(len(a)), a).astype(np.float32)
    return a

def rms_env(x, ms):
    n = max(1, int(SR * ms / 1000))
    return np.sqrt(np.convolve(x * x, np.ones(n) / n, "same"))

def simplify(t, v, tol):
    """Ramer-Douglas-Peucker on (t, v): keep the corners, drop points within tol of the line."""
    keep = np.zeros(len(t), bool); keep[0] = keep[-1] = True
    stack = [(0, len(t) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        line = v[a] + (v[b] - v[a]) * (t[a + 1:b] - t[a]) / (t[b] - t[a])
        d = np.abs(v[a + 1:b] - line)
        i = int(np.argmax(d))
        if d[i] > tol:
            keep[a + 1 + i] = True
            stack += [(a, a + 1 + i), (a + 1 + i, b)]
    return t[keep], v[keep]

def centroid(x, lo, hi):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    hz = np.fft.rfftfreq(len(x), 1 / SR)
    m = (hz >= lo) & (hz <= hi)
    return float((hz[m] * spec[m]).sum() / spec[m].sum()) if m.any() and spec[m].sum() > 0 else (lo * hi) ** 0.5

def to_recipe(x, tol=1.0, base_pts=10, pts_per_s=60):
    peak = float(np.abs(x).max()) or 1e-6
    max_pts = int(base_pts + pts_per_s * len(x) / SR)
    bands = []
    for (lo, hi), sos in zip(BANDS, SOS):
        b = sosfiltfilt(sos, x)                       # zero-phase: corners stay where they were
        env = rms_env(b, 3)[::SR // 1000] * np.sqrt(2) # amplitude of a sine with the same RMS, every 1 ms
        if env.max() < 0.03 * peak:
            continue                                   # nothing to feel in this band
        t = np.arange(len(env), dtype=float)
        db = np.maximum(20 * np.log10(np.maximum(env, 1e-9) / peak), FLOOR)
        tl = tol
        tt, vv = simplify(t, db, tl)
        while len(tt) > max_pts:
            tl *= 1.2; tt, vv = simplify(t, db, tl)
        bands.append([round(centroid(b, lo, hi), 1), [[int(a), round(float(c), 1)] for a, c in zip(tt, vv)]])
    r = {"peak": peak, "ms": round(len(x) / SR * 1000, 1), "bands": bands}
    y = synth_recipe(r)                                # sines at band centres land a little lower than the
    if bands and np.abs(y).max() > 0:                  # original: match its RMS once, here, not at playback
        r["peak"] *= float(np.sqrt((x ** 2).mean() / max((y ** 2).mean(), 1e-12)))
    r["peak"] = round(r["peak"], 4)
    return r

def corr(a, b):
    n = min(len(a), len(b)); a, b = a[:n], b[:n]
    if a.std() < 1e-9 or b.std() < 1e-9:
        return 1.0 if a.std() < 1e-9 and b.std() < 1e-9 else 0.0
    return float(np.corrcoef(a, b)[0, 1])

def fidelity(x, y):
    """(band-envelope corr, broadband-envelope corr, lag ms, level ratio)."""
    n = max(len(x), len(y)); x = np.pad(x, (0, n - len(x))); y = np.pad(y, (0, n - len(y)))
    hop = SR // 200
    ex, ey = rms_env(x, 10)[::hop], rms_env(y, 10)[::hop]
    broad = corr(ex, ey)
    a, b = ex - ex.mean(), ey - ey.mean()
    lag = (int(np.argmax(correlate(b, a, "full"))) - (len(a) - 1)) * 1000 / 200
    ws, cs = [], []
    for sos in SOS:
        bx, by = sosfiltfilt(sos, x), sosfiltfilt(sos, y)
        w = float((bx ** 2).sum())
        if w > 0:
            ws.append(w); cs.append(corr(rms_env(bx, 10)[::hop], rms_env(by, 10)[::hop]))
    band = float(np.average(cs, weights=ws)) if ws else 1.0
    level = float(np.sqrt((y ** 2).mean() / max((x ** 2).mean(), 1e-12)))
    return band, broad, lag, level

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("dirs", nargs="+")
    ap.add_argument("--report"); ap.add_argument("--root", default=ROOT, help="keys are folder paths relative to this")
    ap.add_argument("--tol", type=float, default=1.0, help="corner tolerance in dB")
    ap.add_argument("--base-pts", type=int, default=10)
    ap.add_argument("--pts-per-s", type=int, default=60)
    a = ap.parse_args()
    recipes, rows = {}, []
    for d in a.dirs:
        key = os.path.relpath(os.path.abspath(d), a.root).replace(os.sep, "/")
        recipes[key] = {}
        for f in sorted(glob.glob(os.path.join(d, "*.wav"))):
            i = os.path.basename(f)[:-4]
            x = load(f)
            if len(x) < 64 or np.abs(x).max() < 1e-4:
                continue
            r = to_recipe(x, a.tol, a.base_pts, a.pts_per_s)
            recipes[key][i] = r
            band, broad, lag, level = fidelity(x, synth_recipe(r))
            rows.append((band, broad, lag, level, f"{key}/{i}", sum(len(b[1]) * 2 + 1 for b in r["bands"]) + 2))
    json.dump(recipes, open(a.out, "w"), separators=(",", ":"))
    rows.sort()
    if rows:
        b = np.array([r[0] for r in rows]); br = np.array([r[1] for r in rows]); lg = np.array([abs(r[2]) for r in rows])
        print(f"{len(rows)} recipes -> {a.out} ({os.path.getsize(a.out) / 1024:.0f} KB)")
        print(f"band-envelope corr  median {np.median(b):.3f}  p10 {np.percentile(b, 10):.3f}  min {b.min():.3f}")
        print(f"broad-envelope corr median {np.median(br):.3f}  p10 {np.percentile(br, 10):.3f}")
        print(f"lag |ms|            median {np.median(lg):.1f}  max {lg.max():.1f}")
        print(f"numbers per sound   median {int(np.median([r[5] for r in rows]))}")
    if a.report:
        with open(a.report, "w") as fp:
            fp.write("id\tband_corr\tbroad_corr\tlag_ms\tlevel\tnumbers\n")
            for band, broad, lag, level, i, n in rows:
                fp.write(f"{i}\t{band:.3f}\t{broad:.3f}\t{lag:+.1f}\t{level:.2f}\t{n}\n")

if __name__ == "__main__":
    main()
