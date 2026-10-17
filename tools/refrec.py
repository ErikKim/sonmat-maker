"""Background reference recorder: while a reference game runs, save what the DualSense receiver
is sent (WASAPI loopback, 4ch: 1-2 speaker, 3-4 haptics) as 10 s WAV chunks.

Run as a scheduled task (survives SSH disconnects). Every chunk is written as soon as it is
recorded, so a crash or a device error loses at most 10 s. Silent chunks are dropped.

usage: python refrec.py [out dir] [process name fragment ...]   (case-insensitive substring of the .exe name)
"""
import os, subprocess, sys, time, wave
import numpy as np
import soundcard as sc

OUT = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Public\dshaptics\ref"
PROCS = sys.argv[2:] or ["DS2.exe", "StellarBlade", "SB-Win64"]
SR, CHUNK = 48000, 10
MAX_BYTES = 4 * 1024 ** 3

def running():
    out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True, errors="replace").stdout
    names = [l.split('","')[0].strip('"') for l in out.splitlines() if l.startswith('"')]
    return next((n for n in names for p in PROCS if p.lower() in n.lower()), None)

def pad():
    return next((m for m in sc.all_microphones(include_loopback=True)
                 if "DualSense" in m.name and m.channels == 4), None)

def used():
    return sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))

os.makedirs(OUT, exist_ok=True)
print(time.strftime("%H:%M:%S"), "watching", PROCS, flush=True)
while True:
    game = running()
    mic = pad() if game else None
    if not mic or used() > MAX_BYTES:
        time.sleep(5)
        continue
    try:
        with mic.recorder(samplerate=SR, channels=4, blocksize=4800) as r:
            while running():
                a = np.concatenate([r.record(numframes=4800) for _ in range(CHUNK * 10)])
                if np.abs(a).max() < 1e-4:
                    continue
                name = os.path.join(OUT, f"{game.split('.')[0]}_{time.strftime('%Y%m%d_%H%M%S')}.wav")
                w = wave.open(name, "w"); w.setnchannels(4); w.setsampwidth(2); w.setframerate(SR)
                w.writeframes((np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes()); w.close()
                print(time.strftime("%H:%M:%S"), "saved", os.path.basename(name), np.abs(a).max(axis=0).round(3), flush=True)
    except Exception as e:      # pad switched off / device reset: wait and reattach
        print(time.strftime("%H:%M:%S"), "recorder error", e, flush=True)
        time.sleep(5)
