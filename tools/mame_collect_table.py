"""Collect log from the sonmat MAME plugin -> "command -> what it plays" table.

  python3 tools/mame_collect_table.py collect_mame_ffight.log [romset.7z|.zip|folder] [--wav outdir]

Needs "log_oki": true in the profile's "mame" section while recording (off by default: the daemon
does not use those lines). For every sound command: how often it came, and which ADPCM samples the sound CPU started right
after it (those are the ones worth a pad-speaker clip). Samples that start with no command nearby
are the music's drums. With the user's romset, sample lengths are read from the OKI sample table;
--wav decodes them for listening (local use only, never shipped).
"""
import sys, os, json, re, subprocess, wave, collections
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOW = 4          # frames between a command and the sample it starts

def read_log(path):
    ev = []
    for line in open(path, encoding="utf-8"):
        if line.startswith("#"):
            continue
        f, _, rest = line.strip().partition(" ")
        kind, _, arg = rest.partition(":")
        ev.append((int(f), kind, arg))
    return ev

def rom_bytes(src, names):
    if os.path.isdir(src):
        return b"".join(open(os.path.join(src, n), "rb").read() for n in names)
    return b"".join(subprocess.run(["bsdtar", "-xOf", src, n], capture_output=True, check=True).stdout for n in names)

STEP = [16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157,
        173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963, 1060,
        1166, 1282, 1411, 1552]
IDX = [-1, -1, -1, -1, 2, 4, 6, 8]

def adpcm(data):
    out, sig, st = np.zeros(len(data) * 2, np.float32), 0, 0
    for i, b in enumerate(data):
        for k, n in enumerate((b >> 4, b & 15)):
            s = STEP[st]
            d = s >> 3
            if n & 4: d += s
            if n & 2: d += s >> 1
            if n & 1: d += s >> 2
            sig = max(-2048, min(2047, sig - d if n & 8 else sig + d))
            st = max(0, min(48, st + IDX[n & 7]))
            out[i * 2 + k] = sig / 2048
    return out

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    wav_dir = sys.argv[sys.argv.index("--wav") + 1] if "--wav" in sys.argv else None
    if wav_dir in args: args.remove(wav_dir)
    ev = read_log(args[0])
    pid = re.search(r"profile=(\S+)", open(args[0], encoding="utf-8").readline()).group(1)
    src = json.load(open(os.path.join(HERE, "profiles", pid, "haptics.json"), encoding="utf-8"))["source"]
    rom, rate = None, src.get("rate", 7575)
    if len(args) > 1:
        rom = rom_bytes(args[1], src["files"])
    def length(n):
        if not rom: return None
        a, b = (int.from_bytes(rom[n * 8 + o:n * 8 + o + 3], "big") & 0x3ffff for o in (0, 3))
        return (a, b) if a < b < len(rom) else None
    snd = [(f, a) for f, k, a in ev if k == "snd"]
    oki = [(f, int(a.split("|")[0])) for f, k, a in ev if k == "oki"]
    count, linked, claimed = collections.Counter(a for _, a in snd), collections.defaultdict(collections.Counter), set()
    for f, a in snd:
        for i, (g, n) in enumerate(oki):
            if f <= g <= f + WINDOW:
                linked[a][n] += 1; claimed.add(i)
    print(f"{len(snd)} commands ({len(count)} kinds), {len(oki)} sample starts, frames 0..{ev[-1][0]}")
    print("cmd  count  samples started within %d frames (n x count, ms)" % WINDOW)
    for a, c in sorted(count.items()):
        parts = []
        for n, k in linked[a].most_common(4):
            L = length(n)
            parts.append(f"{n}x{k}" + (f" {int((L[1] - L[0]) * 2000 / rate)}ms" if L else ""))
        print(f" {a}  {c:5d}  {', '.join(parts) or '- (music / control)'}")
    free = collections.Counter(n for i, (_, n) in enumerate(oki) if i not in claimed)
    print("samples with no command nearby (music drums):", dict(free.most_common(8)))
    if wav_dir and rom:
        os.makedirs(wav_dir, exist_ok=True)
        for n in sorted({n for _, n in oki}):
            L = length(n)
            if not L: continue
            pcm = (adpcm(rom[L[0]:L[1] + 1]) * 32767).astype("<i2")
            with wave.open(os.path.join(wav_dir, f"oki_{n:03d}.wav"), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm.tobytes())
        print("wav ->", wav_dir)

if __name__ == "__main__":
    main()
