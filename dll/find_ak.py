"""Find AK::SoundEngine::PostEvent / SetSwitch in a game binary that links Wwise statically.

usage: python3 find_ak.py <game.exe> [--out candidates.json]

Anchor: AK::SoundEngine::GetIDFromString is FNV-1 32 (seed 0x811C9DC5, prime 0x01000193). The
by-name overloads hash their string arguments with it and then call the by-ID overloads, which are
the ones the DLL hooks:
  PostEvent(const char*, obj, ...)          -> 1 hash, then PostEvent(ID, obj, ...)
  SetSwitch(const char*, const char*, obj)  -> 2 hashes, then SetSwitch(groupID, stateID, obj)
Other by-name APIs (SetState, SetRTPCValue, PostTrigger ...) look alike, so this lists candidates
with byte patterns; the DLL's probe run then shows which callee receives real event IDs.
"""
import argparse, json, struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

ap = argparse.ArgumentParser()
ap.add_argument("exe"); ap.add_argument("--out", default="candidates.json")
a = ap.parse_args()

pe = pefile.PE(a.exe, fast_load=True)
text = next(s for s in pe.sections if s.Characteristics & 0x20000000)
code, base = text.get_data(), pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = False

def find_all(pat):
    i = code.find(pat)
    while i >= 0:
        yield i
        i = code.find(pat, i + 1)

# 1. hash functions: seed and prime within 96 bytes of each other
seeds = list(find_all(struct.pack("<I", 0x811C9DC5)))
primes = set(find_all(struct.pack("<I", 0x01000193)))
hashers = set()
for s in seeds:
    if any(abs(p - s) < 96 for p in primes):
        start = s                                   # walk back to the function start (int3/ret padding)
        while start > 0 and not (code[start - 1] in (0xCC, 0xC3) and code[start - 2] in (0xCC, 0xC3)):
            start -= 1
            if s - start > 128:
                break
        hashers.add(start)
print("hash function candidates:", [hex(base + h) for h in sorted(hashers)])

# 2. every E8 call to a hasher; group by enclosing caller (nearest padding before the call)
def func_start(off):
    i = off
    while i > 0 and off - i < 4096:
        if code[i - 1] == 0xCC and code[i - 2] == 0xCC:
            return i
        i -= 1
    return None

callers = {}
for i in find_all(b"\xE8"):
    if i + 5 > len(code):
        continue
    tgt = i + 5 + struct.unpack_from("<i", code, i + 1)[0]
    if tgt in hashers:
        f = func_start(i)
        if f is not None:
            callers.setdefault(f, []).append(i)

# 3. inside each small caller: after the last hash call, the next call is the by-ID overload
cands = []
for f, calls in callers.items():
    size = max(calls) - f + 64
    if size > 600:
        continue
    after = max(calls) + 5
    nxt = None
    for ins in md.disasm(code[after:after + 120], base + after):
        if ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x"):
            nxt = int(ins.op_str, 16) - base
            break
    if nxt is None or not (0 <= nxt < len(code)):
        continue
    pat = " ".join(f"{b:02X}" for b in code[nxt:nxt + 20])
    cands.append({"by_name": hex(base + f), "hash_calls": len(calls), "by_id": hex(base + nxt), "pattern": pat})

cands.sort(key=lambda c: c["hash_calls"])
json.dump(cands, open(a.out, "w"), indent=1)
print(len(cands), "by-name -> by-ID pairs;",
      sum(c["hash_calls"] == 1 for c in cands), "with one hash (PostEvent-like),",
      sum(c["hash_calls"] == 2 for c in cands), "with two (SetSwitch/SetState-like) ->", a.out)
