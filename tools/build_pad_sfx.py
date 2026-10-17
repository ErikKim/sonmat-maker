"""Build pad_sfx/ from extracted Wwise event banks + media.

usage: python3 build_pad_sfx.py <dir with b1/.../SoundBank/Event/**/*.bnk> <dir with converted *.wav> <out pad_sfx dir> <wwiser.py>
- Each RanSeqCntr in an event bank becomes a layer (one random clip per layer at play time);
  sounds outside any container become single-clip layers.
- Clips are downmixed to mono and resampled to 48 kHz (DS5Dongle audio endpoint rate).
"""
import glob, json, os, re, subprocess, sys, wave
import numpy as np

bnk_root, wav_dir, out_dir, wwiser = sys.argv[1:5]
os.makedirs(out_dir, exist_ok=True)
layers_by_event = {}
for b in glob.glob(os.path.join(bnk_root, "**", "*.bnk"), recursive=True):
    name = os.path.basename(b)[:-4]
    if name in layers_by_event:
        continue
    dump = os.path.join("/tmp", "bnk_" + name)
    subprocess.run(["python3", wwiser, "-d", "txt", "-dn", dump, b], capture_output=True)
    text = open(dump + ".txt").read()
    sounds, conts = {}, {}
    for blk in re.split(r"\n\s+obj  CAk", text)[1:]:
        kind = blk.split("[")[0]
        m = re.search(r"ulID = (\d+)", blk)
        if not m:
            continue
        oid = int(m.group(1))
        if kind == "Sound":
            sounds[oid] = int(re.search(r"sourceID = (\d+)", blk).group(1))
        elif kind == "RanSeqCntr":
            conts[oid] = [int(x) for x in re.findall(r"ulChildID = (\d+)", blk)]
    in_cont = {c for ch in conts.values() for c in ch}
    layers = [[sounds[c] for c in ch if c in sounds] for ch in conts.values()]
    layers += [[sid] for oid, sid in sounds.items() if oid not in in_cont]
    layers_by_event[name] = [l for l in layers if l]

for f in glob.glob(os.path.join(wav_dir, "*.wav")):
    w = wave.open(f)
    ch, sr = w.getnchannels(), w.getframerate()
    a = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, ch).astype(np.float32).mean(axis=1) / 32768
    if sr != 48000:
        a = np.interp(np.arange(0, len(a), sr / 48000), np.arange(len(a)), a)
    o = wave.open(os.path.join(out_dir, os.path.basename(f)), "w")
    o.setnchannels(1); o.setsampwidth(2); o.setframerate(48000)
    o.writeframes((np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes()); o.close()

json.dump(layers_by_event, open(os.path.join(out_dir, "layers.json"), "w"), indent=1)
print({k: v for k, v in layers_by_event.items()})
