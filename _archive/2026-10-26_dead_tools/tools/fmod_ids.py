"""Table for the FMOD Ex hook (dll/dshaptics_fmodex.dll): the running game opens its banks without names, so the
hook reports a sound by its place, "#<sounds in the bank>.<index from 0>.<length in samples>". This reads the
user's own banks (the ones the profile's "source" lists) and writes which name sits at each place:

    python tools/fmod_ids.py sekiro        ->  <games>/sekiro/fmod_ids.json   {"<num>.<index>": [[length, name], ...]}

The engine reads it through the profile's "native.places". Made on the user's PC, never shipped.
"""
import json, os, re, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soundprep as sp

def bank_table(vgm, path):
    r = subprocess.run([vgm, "-m", "-s", "1", "-S", "0", path], capture_output=True, text=True, errors="replace")
    rows = []
    for blk in re.split(r"(?m)^metadata for ", r.stdout)[1:]:
        n = re.search(r"stream total samples: (\d+)", blk)
        name = re.search(r"stream name: (.*)", blk)
        rows.append((int(n.group(1)) if n else 0, name.group(1).split(";")[0].strip() if name else ""))
    return rows

def main(pid, log=print):
    j = sp.profiles()[pid]; cfg = sp.load_config()
    j["_id"] = pid
    game = sp.game_dir(j, cfg)
    vgm = sp.vgmstream_cmd(cfg)
    out = {}
    with tempfile.TemporaryDirectory(prefix="sonmat_") as tmp:
        for b in sp.fromsoft_files(j, game, tmp, log):
            rows = bank_table(vgm, b)
            log(f"{os.path.basename(b)}: {len(rows)} sounds, {sum(1 for _n, nm in rows if nm)} named")
            for i, (n, name) in enumerate(rows):
                if name:
                    out.setdefault(f"{len(rows)}.{i}", []).append([n, name])
    dst = os.path.join(j["_dir"], "fmod_ids.json")
    json.dump(out, open(dst, "w", encoding="utf-8"), separators=(",", ":"))
    log(f"{len(out)} places -> {dst}")

if __name__ == "__main__":
    main(sys.argv[1])
