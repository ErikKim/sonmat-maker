"""find_ak.py on a memory image of the running game (code sections are encrypted on disk by the Steam wrapper).
usage: python3 find_ak_mem.py <image.bin read from the process, RVA-indexed> [--out candidates.json]"""
import json, struct, sys, math, collections
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
img = open(sys.argv[1], "rb").read()
pe = struct.unpack_from("<I", img, 0x3c)[0]; n = struct.unpack_from("<H", img, pe + 6)[0]; opt = struct.unpack_from("<H", img, pe + 20)[0]
secs = [(img[o:o + 8].rstrip(b"\0").decode("latin1"),) + struct.unpack_from("<II", img, o + 8) + (struct.unpack_from("<I", img, o + 36)[0],) for o in (pe + 24 + opt + 40 * i for i in range(n))]
name, vs, va, ch = next(s for s in secs if s[3] & 0x20000000)
code, base = img[va:va + vs], va          # addresses below are RVAs
c = collections.Counter(code[:2000000]); t = sum(c.values())
print("text", name, hex(va), vs, "entropy %.2f" % -sum(v / t * math.log2(v / t) for v in c.values()))
md = Cs(CS_ARCH_X86, CS_MODE_64)
def find_all(pat):
    i = code.find(pat)
    while i >= 0:
        yield i; i = code.find(pat, i + 1)
seeds = list(find_all(struct.pack("<I", 0x811C9DC5))); primes = sorted(find_all(struct.pack("<I", 0x01000193)))
print("FNV seeds", len(seeds), "primes", len(primes))
import bisect
hashers = set()
for s in seeds:
    k = bisect.bisect_left(primes, s - 96)
    if k < len(primes) and primes[k] < s + 96:
        st = s
        while st > 0 and not (code[st - 1] in (0xCC, 0xC3) and code[st - 2] in (0xCC, 0xC3)):
            st -= 1
            if s - st > 128: break
        hashers.add(st)
print("hash function candidates:", [hex(base + h) for h in sorted(hashers)][:20], len(hashers))
def func_start(off):
    i = off
    while i > 0 and off - i < 4096:
        if code[i - 1] == 0xCC and code[i - 2] == 0xCC: return i
        i -= 1
callers = {}
for i in find_all(b"\xE8"):
    if i + 5 <= len(code) and i + 5 + struct.unpack_from("<i", code, i + 1)[0] in hashers:
        f = func_start(i)
        if f is not None: callers.setdefault(f, []).append(i)
cands = []
for f, calls in callers.items():
    if max(calls) - f + 64 > 600: continue
    after = max(calls) + 5; nxt = None
    for ins in md.disasm(code[after:after + 120], base + after):
        if ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x"):
            nxt = int(ins.op_str, 16) - base; break
    if nxt is None or not (0 <= nxt < len(code)): continue
    cands.append({"by_name": hex(base + f), "hash_calls": len(calls), "by_id": hex(base + nxt), "pattern": " ".join(f"{b:02X}" for b in code[nxt:nxt + 24])})
cands.sort(key=lambda c: c["hash_calls"])
json.dump(cands, open("candidates.json", "w"), indent=1)
print(len(cands), "pairs; one hash:", sum(c["hash_calls"] == 1 for c in cands), "two:", sum(c["hash_calls"] == 2 for c in cands), "inline-hash callers (no call):", len(seeds) - len(hashers))
for c_ in cands[:40]: print(c_)
