# The table of vibration kinds (sonmat/data/haptic_templates.json), measured from a reference game's own haptic
# sounds. One kind = one group of its sounds (a hit on flesh, a guard, a landing ...). What is kept per kind:
# the level over time in eight bands, the pitch inside each band, how grainy it is, how strong it plays. Numbers
# only - none of the game's waveforms leave this machine.
#   python3 -I ref_templates.py <catalog.json> <raw_dir> <out.json> [kind ...]
# catalog = 11_sb_haptic_catalog.json (which sound belongs to which cue, and the cue's volume),
# raw_dir = the exported .uasset files (Ogg Vorbis or Bink Audio inside), decoded with vgmstream-cli.
import os, re, sys, json, wave, subprocess, tempfile
import numpy as np
from scipy.signal import butter, sosfiltfilt, hilbert

SR = 48000
BANDS = [(30, 42), (42, 60), (60, 85), (85, 120), (120, 170), (170, 240), (240, 340), (340, 500)]   # half octaves
GRID = [0, 3, 6, 10, 15, 22, 32, 45, 65, 90, 130, 180, 250, 350, 500, 700, 1000, 1400, 2000, 2800, 4000]   # ms

# kind -> (regex on the sound's name, what it is). Chosen by reading the game's list (11_sb_haptic_rules.md).
KINDS = {
    "hit":         (r"^Hit_flesh_Vib", "a weapon landing on flesh"),
    "hit_metal":   (r"^Hit_metal_Vib", "... on metal: brighter"),
    "hit_stone":   (r"^Hit_statue_Vib", "... on stone: longer"),
    "hit_wood":    (r"^PhyObj_WoodBreak_Vibration", "wood breaking"),
    "hit_s":       (r"^SE_Impact_S_\d", "small impact"),
    "hit_m":       (r"^SE_Impact_M_\d", "medium impact"),
    "hit_l":       (r"^SE_Impact_L_\d", "large impact"),
    "hit_xl":      (r"^SE_Impact_XL_\d", "largest impact"),
    "blunt":       (r"^PC_SE_Kick_Vibration|^PC_Foley_Punch_Vib", "kick, punch"),
    "stab":        (r"^PC_LinkAttack_Stab_[SL]_\d", "a stab going in"),
    "fatal":       (r"^PC_LinkAttack_Stab[1-4]_Vibration_N$|^PC_LinkAttack_Com_Stab\d", "finisher"),
    "guard":       (r"^Guard_Vibration", "guard"),
    "parry":       (r"^PC_Guard_Parry_Vibration", "parry"),
    "pguard":      (r"^PC_Guard_JustParry_Vibration", "perfect guard"),
    "stagger":     (r"^PC_Skill_Air_GuardBreak_Vibration|^UI_MainHUD_ShieldBreak_vib", "guard / shield broken"),
    "hurt":        (r"^PC_Damaged_Dot_\d", "damage over time"),
    "down":        (r"^PC_foley_Bodyfall_Vib", "the body hits the ground"),
    "roll":        (r"^PC_foley_Bodyroll_Vib_\d", "roll"),
    "evade":       (r"^PC_Skill_JustEvade_Vibration", "perfect dodge"),
    "dash":        (r"^PC_Skill_Dash_Vibration", "dash"),
    "jump":        (r"^PC_foley_Jump_Stiff", "jump"),
    "land":        (r"^PC_Foot_Land_\d", "landing"),
    "land_heavy":  (r"^PC_Foot_LandS_\d", "hard landing"),
    "step":        (r"^PC_Foot_Vibration_\d", "footstep on plain ground"),
    "step_sand":   (r"^Pc_Footstep_Desert", "footstep on sand"),
    "step_water":  (r"^Pc_Footstep_Water", "footstep in water"),
    "step_wire":   (r"^PC_Foley_Foot_MetalWire", "footstep on a metal grate"),
    "swim":        (r"^PC_foot_swimming", "swimming kick"),
    "water_in":    (r"^PC_swim_Dive", "going under water"),
    "move_light":  (r"^PC_Foley_Light_Vibration", "light body movement"),
    "move_mid":    (r"^PC_Foley_Mid_\d", "body movement"),
    "move_large":  (r"^PC_Foley_Large_\d", "large body movement"),
    "hand":        (r"^PC_Foley_HandTouch_Vibration", "a hand on a ledge"),
    "slide":       (r"^PC_WorldSliding_Slip_Loop", "sliding (loop)"),
    "shot_s":      (r"^PC_Skill_GunShoot_S_", "gun, small"),
    "shot_m":      (r"^PC_Skill_GunShoot_M_", "gun, medium"),
    "shot_l":      (r"^PC_Skill_GunShoot_L_", "gun, large"),
    "shot_xl":     (r"^PC_Skill_GunShoot_L_", "gun, largest: the large one played far above full scale"),
    "blast":       (r"^PhyObj_Explosion_Vibration", "explosion"),
    "thud":        (r"^SE_PhyObj_impact_metal_M|^SE_phyobj_impact_Metal_M", "a thing bumping into a thing"),
    "box":         (r"^SE_PhyObj_Cardboard_Box", "a light thing knocked over"),
    "charge":      (r"^PC_BetaSkill_Charge_Loop2", "holding a charge (loop)"),
    "heal":        (r"^PC_Basic_UsePotion", "potion"),
    "buff":        (r"^PC_Basic_Use_Buff", "buff"),
    "ui_ok":       (r"^UI_Interaction_Success", "it worked"),
    "ui_fail":     (r"^UI_Interaction_Fail_MainHUD", "it did not"),
    "uitick":      (r"^UI_Quest_RewardSlot_vib|^UI_SkillTree_Change", "menu tick"),
    "click":       (r"^UI_Escape_Click_vib", "button press"),
    "swing":       (r"^Atk_Norm_RtoL", "a weapon swung through the air"),
    "swing_l":     (r"^PC_BarSwing_L_\d", "a big swing of the whole body"),
    "charged":     (r"^Slot_ChargeSlash_\d|^Slot_ChargeSpin_\d", "a charge let go"),
    "massive":     (r"^PC_Skill_MassiveAttack_vib_\d", "a big skill coming down"),
    "shake":       (r"^PC_Skill_MassiveAttack_Shake_Vib", "a short hard shake"),
    "riser":       (r"^PC_Skill_MassiveAttack_Riser_vib", "something building up"),
    "knockdown":   (r"^KnockDown_Vibration|^PC_SE_KnockDown_Bodyfall_[Vv]ib", "knocked down, dying"),
    "pulse":       (r"^SE_Sine_Pulse_Short", "one short pulse (a heartbeat)"),
    "button":      (r"^Haptic_Button_[SM]_Vib_\d", "a small click"),
    "gain":        (r"^UI_Item_Buy_vib|^UI_VendingMachineReward_vib|^UI_NIKKE_LostArticle_Get_Reward_Vib", "something gained"),
    "item":        (r"^Object_Smallbox_01_open_vib_1|^PC_Interaction_Container_open_vib", "a box opened, an item taken"),
    "lever":       (r"^Lever_Pull_\d", "a lever pulled"),
    "fold":        (r"^PC_FoldSword_(Open|Close)_vibration", "a weapon unfolding, changing"),
    "spark":       (r"^SE_Spark_Vib_\d", "sparks"),
    "gun_heavy":   (r"^Drone_Gun_Heavy_[ES]_vibration", "a heavy gun"),
    "rope":        (r"^PC_Rope_MovingStart_Vibration|^PC_Rope_Move_Start_vib", "pulled along a rope"),
    "wallhit":     (r"^PC_Foley_WallHit_Vibration", "the body hits a wall"),
    "drop":        (r"^Obj_Drop_Can_Vib_\d", "a small thing dropped"),
    "warp":        (r"^SE_CampTeleport_(Down|grab)_vib", "teleport"),
    "door":        (r"^Obj_Door[EF]_Open_Vib|^Env_SE_ElderRoom_Door_Open_vib|^SE_ATL_Door01_Open_Vib", "a door opening"),
    "grind":       (r"^SE_Grinder_Loop_Vibration", "a grinder (loop)"),
    "tram":        (r"^SE_WLA40_Tram_Move_Vib", "riding a tram (loop)"),
    "hover":       (r"^SE_hovering_Loop_Vibration", "hovering, flying (loop)"),
    "cart":        (r"^SE_DiggerCart_Loop_vib", "a cart rolling (loop)"),
    "fire":        (r"^AMB_Fire_S_Vibration", "fire burning (loop)"),
    "spray":       (r"^SE_WashSystem_WaterSpray_Loop_vib", "a spray (loop)"),
    "rain":        (r"^AMB_Rain_loop_Vibration", "rain (loop)"),
    "quake":       (r"^SE_Earthquake_[SM]_Vibration_\d", "the ground shaking: thunder, a roar (loop)"),
}

# kinds that are a steady texture, not a blow: a wave of ours drawn from one keeps its own length and level
# over time and takes only what it is made of from the kind
LOOPS = {"slide", "charge", "grind", "tram", "hover", "cart", "fire", "spray", "rain", "quake"}

# the cue whose volume counts, where a sound is shared by several (the same gun sound plays as L and, louder, as XL)
CUES = {"fatal": "_Com_Stab", "step": "^PC_Foot_Vibration", "shot_l": "GunShoot_L_", "shot_xl": "GunShoot_XL_", "roll": "^PC_foley", "move_mid": "^PC_Foley"}

def decode(path, tmp):
    d = open(path, "rb").read()
    for magic, ext in ((b"OggS", ".ogg"), (b"ABEU", ".binka")):
        o = d.find(magic)
        if o >= 0:
            break
    else:
        return None
    src, dst = os.path.join(tmp, "a" + ext), os.path.join(tmp, "a.wav")
    open(src, "wb").write(d[o:])
    subprocess.run(["vgmstream-cli", "-i", "-o", dst, src], capture_output=True)
    w = wave.open(dst)
    assert w.getframerate() == SR, w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), "<i2").reshape(-1, w.getnchannels()).astype(np.float64) / 32768
    w.close()
    return x[:, np.argmax(np.abs(x).max(0))]             # the louder hand (one-sided sounds: that side)

def smooth(e, ms):
    k = max(1, int(SR * ms / 1000))
    return np.convolve(e, np.ones(k) / k, mode="same")

def measure(x):
    """One sound -> per band: level on GRID (of the sound's own peak), pitch, width, grain; and its length."""
    x = x / np.abs(x).max()
    on = int(np.argmax(np.abs(x) > 0.5))                 # lined up where it first reaches half its peak, 8 ms
    pad = SR // 2                                        # before that kept. Silence around it: the filters and the
    lead = int(SR * 0.008)                               # Hilbert transform (circular) would carry one end over
    x = np.concatenate([np.zeros(pad), x[max(0, on - lead):], np.zeros(pad)])
    o = pad
    a = smooth(np.abs(x), 10)[o:]
    s = float(np.nonzero(a > 0.02 * a.max())[0][-1] / SR)     # ends where the last fiftieth of its level is gone
    mid = [0] + [(a_ + b_) / 2 for a_, b_ in zip(GRID, GRID[1:])] + [GRID[-1]]
    cut = [min(len(x) - 1, o + int(SR * t / 1000)) for t in mid]         # each grid point = the mean level from
    at = lambda e: [float(np.sqrt((e[i:max(j, i + 1)] ** 2).mean())) for i, j in zip(cut, cut[1:])]   # half-way to its neighbours
    out = {"env": [], "hz": [], "bw": [], "grain": [], "share": [], "s": s, "rise": float(np.argmax(a) / SR)}
    for lo, hi in BANDS:
        b = sosfiltfilt(butter(4, [lo, hi], "band", fs=SR, output="sos"), x)
        h = np.abs(hilbert(b))
        out["env"].append(at(h))
        S = np.abs(np.fft.rfft(b)) ** 2
        F = np.fft.rfftfreq(len(b), 1 / SR)
        m = (F >= lo) & (F < hi)
        c = float((F[m] * S[m]).sum() / max(S[m].sum(), 1e-12))
        out["hz"].append(c)
        out["bw"].append(float(np.sqrt(((F[m] - c) ** 2 * S[m]).sum() / max(S[m].sum(), 1e-12))))
        out["share"].append(float(S[m].sum()))
        slow = smooth(h, 60)                             # grain: how far the level jumps around its own 60 ms mean
        k = slow > 0.2 * slow.max()                      # (a steady tone 0, noise about 0.5)
        out["grain"].append(float(np.std(h[k] / slow[k])))
    return out

def thin(pts, tol=0.04):
    """Drop curve points a straight line between their neighbours already gives (within tol of the curve's top)."""
    top = max(p[1] for p in pts) or 1.0
    out = list(pts)
    i = 1
    while i < len(out) - 1:
        (t0, a0), (t1, a1), (t2, a2) = out[i - 1], out[i], out[i + 1]
        if abs(a0 + (a2 - a0) * (t1 - t0) / (t2 - t0) - a1) < tol * top:
            del out[i]
        else:
            i += 1
    return out

def main():
    cat_path, raw, out_path = sys.argv[1:4]
    only = set(sys.argv[4:]) - {"-v"}
    cat = json.load(open(cat_path))
    vol = {}
    for a in cat["assets"]:
        if a["kind"] == "cue":
            for w in a["cue"].get("waves") or []:
                vol.setdefault(w, []).append((a["name"], a["cue"]["volume"]))
    waves = [a for a in cat["assets"] if a["kind"] == "wave" and a["layer"] != "컷씬"]
    tmp = tempfile.mkdtemp(prefix="reftpl_")
    table = json.load(open(out_path)) if only and os.path.exists(out_path) else {}
    table["_note"] = ("Vibration kinds measured from a reference game's own haptic sounds (sonmat-maker/tools/"
                      "ref_templates.py). bands: hz = pitch, bw = how wide around it, grain = how far the level "
                      "jumps about (a steady tone 0, noise about 0.5), env = [[t ms, level], ...] with 1 = the "
                      "kind's peak. level = how strong the game plays it (above 1 = pushed flat against the "
                      "ceiling), s = length. Written by the tool: change the tool, not this file.")
    for kind, (pat, what) in KINDS.items():
        if only and kind not in only:
            continue
        rx = re.compile(pat)
        group = [a for a in waves if rx.search(a["name"])]
        ms, lv = [], []
        crx = re.compile(CUES.get(kind, ""))
        for a in group:
            x = decode(os.path.join(raw, a["path"]), tmp)
            if x is None or np.abs(x).max() < 1e-4:
                continue
            ms.append(measure(x))
            vs = [v for n, v in vol.get(a["path"], []) if crx.search(n)]
            if vs:
                lv.append(float(np.abs(x).max()) * max(vs))
        if not ms:
            print(f"{kind}: no sound matched {pat}", file=sys.stderr)
            continue
        env = np.sqrt((np.array([m["env"] for m in ms]) ** 2).mean(0))      # bands x grid: the group's mean power
        s = float(np.median([m["s"] for m in ms]))
        env = env / max(env.sum(0).max(), 1e-9)
        share = np.array([np.array(m["share"]) / sum(m["share"]) for m in ms]).mean(0)
        med = lambda key, b: float(np.median([m[key][b] for m in ms]))
        bands = []
        for b in range(len(BANDS)):
            pts = [[t, round(float(v), 3)] for t, v in zip(GRID, env[b]) if t / 1000 <= s]
            if share[b] < 0.03 * share.sum():                              # a band that carries nothing
                continue
            pts.append([int(round(max(pts[-1][0] + 10, s * 1000 + 20))), 0.0])
            bands.append({"band": list(BANDS[b]), "hz": round(med("hz", b)), "bw": round(med("bw", b), 1), "grain": round(med("grain", b), 2),
                          "env": thin(pts)})
        if not lv:
            print(f"{kind}: no cue matched {CUES.get(kind)}", file=sys.stderr)
        table[kind] = {
            "what": what, "from": f"{len(ms)} sounds /{pat}/",
            "s": round(s, 3), "rise_ms": round(float(np.median([m["rise"] for m in ms])) * 1000),
            "level": round(float(np.median(lv or [1.0])), 2),
            **({"loop": True} if kind in LOOPS else {}),
            "share": [round(float(v), 2) for v in share / share.sum()],
            "bands": bands,
        }
        t = table[kind]
        print(f"{kind:11} n={len(ms):2} {t['s']:5.2f}s rise {t['rise_ms']:4}ms level {t['level']:4} share {t['share']} "
              + " ".join(f"{b['hz']}±{b['bw']:.0f}g{b['grain']}" for b in bands))
        if "-v" in sys.argv:
            print("    cues", sorted({(n, v) for a in group for n, v in vol.get(a["path"], [])}))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("{\n" + ",\n".join(f' {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}' for k, v in table.items()) + "\n}\n")

if __name__ == "__main__":
    main()
