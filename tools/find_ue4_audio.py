"""Find what dshaptics_ue4.dll needs in a UE4 game exe and print the profile's "native" section.

    python3 find_ue4_audio.py <Game-Win64-Shipping.exe> <UE4SS.log from one run of that exe>

1. AddNewActiveSound + FActiveSound offsets, statically: UE4 keeps {"PlaySound2D", execPlaySound2D}
   name/function pairs for its native registration. The exec thunk (UGameplayStatics::PlaySound2D
   inlined) builds an FActiveSound on the stack - `lea rcx,[rbp+A]; call <ctor>` - stores the Sound
   into it, stores the owner's FName (`mov rax,[owner+0x18]; mov [rbp+A+off],rax`) and passes it as
   `lea rdx,[rbp+A]; call AddNewActiveSound`.
2. FName::ToString: UE4SS logs it ("Found FName::ToString: 0x7ff..."); the module base is recovered
   from all the absolute addresses in the log (the one base that lands every one on a function start).
Patterns are the shortest unique prefix (>= 16 bytes); +rva is the exact-build fallback.
Verified on Lies of P (2026-10-05) against the hand analysis.
"""
import re, sys, json, struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_REG

exe, ue4ss_log = sys.argv[1], sys.argv[2]
pe = pefile.PE(exe, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase
data = open(exe, "rb").read()
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
T0, T1 = BASE + text.VirtualAddress, BASE + text.VirtualAddress + text.Misc_VirtualSize

def off(va): return pe.get_offset_from_rva(va - BASE)

def disasm(va, limit=0x2000):
    out = []
    for i in md.disasm(data[off(va):off(va) + limit], va):
        out.append(i)
        if i.mnemonic == "int3":
            break
    return out

def exec_thunk(name):
    """The largest function paired with the native name string (exec thunk, not the tiny Z_Construct)."""
    best = None
    for m in re.finditer(re.escape(b"\x00" + name + b"\x00"), data):
        try: va = BASE + pe.get_rva_from_offset(m.start() + 1)
        except Exception: continue
        for p in re.finditer(re.escape(struct.pack("<Q", va)), data):
            for q in (p.start() + 8, p.start() - 8):
                fn = struct.unpack("<Q", data[q:q + 8])[0]
                if T0 <= fn < T1:
                    n = len(disasm(fn))
                    if not best or n > best[1]:
                        best = (fn, n)
    return best[0] if best else None

def rbp_disp(op):
    return op.mem.disp if op.type == X86_OP_MEM and md.reg_name(op.mem.base) == "rbp" else None

def analyse(thunk):
    ins = disasm(thunk)
    ctor = {}                                       # rbp displacement of an object passed in rcx to a call
    for a, b in zip(ins, ins[1:]):
        if a.mnemonic == "lea" and md.reg_name(a.operands[0].reg) == "rcx" and b.mnemonic == "call":
            ctor.setdefault(rbp_disp(a.operands[1]), b.address)
    for k, i in enumerate(ins):                     # lea rdx,[rbp+A] ... call T, with A constructed earlier
        if i.mnemonic != "call" or not i.op_str.startswith("0x"):
            continue
        for j in ins[max(0, k - 4):k]:
            if j.mnemonic == "lea" and md.reg_name(j.operands[0].reg) == "rdx":
                A = rbp_disp(j.operands[1])
                if A is not None and A in ctor and ctor[A] < i.address:
                    return int(i.op_str, 16), A, ins, ctor[A], i.address
    return None

def offsets(A, ins, start, end):
    """Sound = first qword register stored into the struct after the ctor; owner FName = a value loaded
    from [reg+0x18] (UObject::NamePrivate) and stored into the struct."""
    sound = owner = None
    loaded = {}
    for i in ins:
        if not (start < i.address < end) or len(i.operands) != 2:
            continue
        d, s = i.operands
        if i.mnemonic == "mov" and d.type == X86_OP_REG and s.type == X86_OP_MEM and s.mem.disp == 0x18 \
                and md.reg_name(s.mem.base) not in ("rbp", "rsp"):
            loaded[md.reg_name(d.reg)] = i.address
        if i.mnemonic == "mov" and rbp_disp(d) is not None and s.type == X86_OP_REG and d.size == 8:
            o = rbp_disp(d) - A
            if not 0 < o < 0x200:
                continue
            r = md.reg_name(s.reg)
            if r in loaded and owner is None:
                owner = o
            elif sound is None and r not in loaded:
                sound = o
    return sound, owner

def pattern(va):
    o = off(va)
    for n in range(16, 64, 4):
        if data.count(data[o:o + n]) == 1:
            return data[o:o + n].hex(" ").upper()
    return None

def tostring_rva():
    log = open(ue4ss_log, encoding="utf-8", errors="replace").read()
    m = re.search(r"Found FName::ToString: (0x[0-9a-fA-F]+)", log)
    if not m:
        return None
    ts = int(m.group(1), 16)
    # function addresses only ("Found GMalloc/GUObjectArray" are data, not function starts)
    addrs = sorted({int(a, 16) for a in re.findall(r"address:? (0x7ff[0-9a-fA-F]+)", log)} | {ts})
    for b in range((min(addrs) - (T1 - BASE)) & ~0xFFFF, min(addrs), 0x10000):
        try:
            if all(data[off(a - b + BASE) - 1] in (0xCC, 0xC3, 0x90) for a in addrs):
                return ts - b
        except Exception:
            continue
    return None

thunk = exec_thunk(b"PlaySound2D")
r = analyse(thunk) if thunk else None
if not r:
    sys.exit("AddNewActiveSound not found (no PlaySound2D thunk with an FActiveSound pattern)")
add, A, ins, cstart, cend = r
snd, own = offsets(A, ins, cstart, cend)
ts = tostring_rva()
add_rva = add - BASE
native = {
    "_note": f"tools/find_ue4_audio.py: {exe.split('/')[-1]} {len(data):,} bytes. Patterns first, +rva = this exact build",
    "AddNewActiveSound": [pattern(add), f"+{add_rva:x}"],
    "FNameToString": [pattern(BASE + ts), f"+{ts:x}"] if ts else ["FILL: run the game once with UE4SS and pass its UE4SS.log"],
    "SoundOffset": f"{snd:x}" if snd is not None else "FILL",
    "OwnerNameOffset": f"{own:x}" if own is not None else "FILL",
}
print(f"execPlaySound2D {thunk:#x}  AddNewActiveSound {add:#x}  FActiveSound at rbp{A:+#x}", file=sys.stderr)
print(json.dumps({"native": native}, indent=2))
