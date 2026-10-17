"""A first setup for a game nobody has made a profile for, without AI: which way its sounds are stored, every
sound name it has, each name put into a slot of the model by fixed rules, written as profiles/<id>/game.json for
tools/new_profile.py. The rules are the same for every game; nothing in here names a game.

    python3 tools/autosetup.py detect <game folder>                       which way the sounds are stored
    python3 tools/autosetup.py names <game folder> <names.json>           every sound name (+ length when known)
    python3 tools/autosetup.py slots <names.json> <ucs.csv> <out.json>    name -> slot, with the reason
    python3 tools/autosetup.py inputs <game folder> <inputs.json> [key id] which button does what, and co-op on one PC
    python3 tools/autosetup.py game <id> <names.json> <slots.json> <steam folder name> <exe> <title> [inputs.json]
                                                    -> profiles/<id>/game.json (+ event_ids.json), then new_profile.py

Ways (sonmat/WORKLOG.md 2026-10-15, "소리를 꺼내는 경로"): unity_audio (Unity's own audio, read with UnityPy),
unity_wwise (Wwise banks loose in StreamingAssets, names in SoundbanksInfo.xml), ue_pak (an Unreal pak).

How a name gets its slot, first match wins:
  1. a word that says what kind of track it is (music, ambience, UI, voice, cutscene) -> no vibration / scene
  2. a word for an action the player feels (step, land, jump, dash, throw, pick up, hit, break, explosion ...)
  3. the Universal Category System (public domain sound-effects taxonomy, ~10,000 synonyms) -> its category -> slot
  4. nothing -> no slot (no vibration: missing one is better than music shaking the pad)
Words a game uses in more than 5 % of its names (dlc, stage, obj ...) are not read. Loops and long sounds (over
4 s) that are not an action are left out - except the world moving under you (quake, roar, warp) and a held tool
or a fire that keeps going (hold).

Buttons (inputs): the game's own default layout, read from its files where the engine keeps one - Unreal's
DefaultInput.ini and Enhanced Input mapping contexts (paktool imc), Rewired's input manager (Unity). It decides:
  - triggers: only when the game puts an action of its own (not a menu's, not a chat message's) on L2 / R2
  - co-op on one PC (the Steam store's "Shared/Split Screen" categories): whose pad an action's sound goes to
Not readable (a game with input code of its own): the usual pad layout - A jumps / picks up, X uses, B dashes.
"""
import collections, csv, json, os, re, sys

# 1. what kind of track (checked on every word of the name)
TRACK = {
    "skip": "mus music bgm theme song jingle ditty stinger st ost amb ambience ambient atmo atmos roomtone ui hud menu "
            "frontend fe vo voice dialog dialogue ono talk speech chatter shout laugh scream grunt cheer crowd "
            "applause emote spawn respawn despawn appear disappear "
            "bat bats bird birds gull gulls raven crow crows rat rats insect insects frog frogs cricket crickets "
            "animal animals creature creatures drip drips",
    "scene": "cine cinematic cutscene",
}
# 2. actions -> model slot (profiles/_model/model.json). Order matters: the first slot with a word wins.
# The slots that need to know who "I" am (parry, finisher, stagger, my death) are never filled from names alone.
ACTION = [
    ("boom", "explo explosion explode boom bomb blast detonate firework fireworks"),
    ("blast", "break broken shatter crack crash collapse debris destroy destruct rockslide smash"),
    ("hurt", "hurt damage pain"),
    ("land", "land landing touchdown fall mantle climb vault"),
    ("jump", "jump hop"),
    ("dodge", "dash roll dodge slide skid"),
    ("step_texture", "snow sand grass gravel mud ice water splash metal iron steel grate wood wooden"),  # only with a step word
    # (metal and wood joined 10-15: fences and iron structures you walk in and out of - NieR, Chained Together)
    ("step", "step steps footstep footsteps fs walk run sprint"),
    ("charge", "charge"),
    ("shot", "shoot shot gunshot gun pistol rifle shotgun bullet laser"),
    ("heal", "heal"),
    ("hit", "hit impact bump thud thump knock punch kick slam bang"),
    ("swing", "swing whoosh swoosh swipe throw toss"),
    ("touch", "pick pickup grab catch place put chop cut slice knife wash plate ingredient item coin collect pull "
              "push drag"),
    ("click", "switch lever button toggle lock unlock latch"),
]
# 3. UCS category -> slot (None = no vibration)
UCS_SLOT = {
    "FOOTSTEPS": "step", "MOVEMENT": "touch", "CLOTH": None, "FOLEY": "touch",
    "FIGHT": "hit", "WEAPONS": "swing", "SWOOSHES": "swing", "GORE": "hurt", "BULLETS": "hit", "GUNS": "shot",
    "LASERS": "shot", "EXPLOSIONS": "boom", "FIREWORKS": "boom", "NATURAL DISASTER": "boom",
    "DESTRUCTION": "blast", "GLASS": "blast", "ROCKS": "hit",
    "OBJECTS": "touch", "TOOLS": "touch", "FOOD & DRINK": "touch", "PAPER": None, "PLASTIC": "touch",
    "CERAMICS": "touch", "METAL": "hit", "WOOD": "hit", "DRAWERS": "click", "DOORS": "click", "WINDOWS": "click",
    "EQUIPMENT": "click", "TOYS": "touch", "LEATHER": None, "RUBBER": "touch", "ROPE": "touch", "CHAINS": "touch",
    "SPORTS": "hit", "MECHANICAL": "click",
    # running things, places, voices, music: felt through the TV, not the hands
    "MACHINES": None, "MOTORS": None, "VEHICLES": None, "TRAINS": None, "BOATS": None, "AIRCRAFT": None,
    "ROBOTS": None, "ELECTRICITY": None, "COMPUTERS": None, "CLOCKS": None, "WATER": None, "LIQUID & MUD": None,
    "FIRE": None, "ICE": None, "SNOW": None, "DIRT & SAND": None, "AIR": None, "GEOTHERMAL": None,
    "CHEMICALS": None, "MAGIC": None, "SCIFI": None, "DESIGNED": None, "CARTOON": None, "AMBIENCE": None,
    "WEATHER": None, "RAIN": None, "WIND": None, "CROWDS": None, "BIRDS": None, "ANIMALS": None,
    "VEGETATION": None, "CREATURES": None, "WINGS": None, "MUSICAL": None, "USER INTERFACE": None, "VOICES": None,
    "HUMAN": None, "BEEPS": None, "ALARMS": None, "BELLS": None, "HORNS": None, "WHISTLES": None,
    "COMMUNICATIONS": None, "GAMES": None, "FARTS": None, "ARCHIVED": None,
}
LONG_S = 4.0
# the world moving under you: an event even when long or looped, or filed by the dictionary as an animal
# (Overcooked 2's rocking boat kitchens and earthquakes, a monster's roar, a warp)
WORLD = [("quake", "quake earthquake rumble tremor"), ("roar", "roar roars"), ("warp", "warp teleport")]   # not blink: an EyeBlink
# a wave is the sea only beside a word for water (not Wukong's magic / energy / sound waves)
WAVE, SEA = {"wave", "waves"}, set("ocean sea tide surf water".split())
# a loop that keeps going while something is on: a fire burning, a tool spraying (model slot "hold"). Not a
# firework, a fireplace or a wall torch (places, not something on); not the loop's own start / stop sound
HOLD = set("fire fires flame flames extinguisher jet waterjet hose spray sprayer".split())
HOLD_START = ("flame", "extinguish")                 # Flamethower (sic, Overcooked 2)
# the pad speaker: a few things you pick up or that click open, devices that call you, the "perfect" moments and
# the round's news (a fire breaking out, an order delivered, the time's-up bell). Not a timeout: user 10-16 - an
# order running out is not news. (model: one or two kinds of moment, low; any slot or none - never music, voices)
SPEAKER = ("pick pickup catch collect coin unlock phone ringtone radio mail message notify notification alarm flashlight warning deliver delivery "
           "ignition sting checkpoint perfect just")
# adaptive triggers (R2), by slot and word - the feel of each is the one a hand-made profile has used:
#   fire   = a shot: a short kick (Lies of P's Falcon Eyes)          charge = resist until the shot / the end
#   just   = a perfect dodge / guard: a short buzz (NieR's just evade)
TRIG_END = "release fire shoot shot launch end stop cancel"
# whose sound: a trigger is felt for what I do, not what an enemy does. Words in the name (NieR pl/em, Wukong
# Player/ENM, Lies of P PC/NPC); a game with no "me" word: anything that does not say enemy
ENEMY = "enm enemy enemies npc em boss mob monster"
PLAYER = "player pl pc hero"
TRIG_JUST = ("perfect just", "dodge avoid avoidance evade guard parry block")
#   tool   = a tool held on, whose sound has a start and an end (<X>Start ... <X>End): resist while it runs, like
#            Lies of P's Flamberge. Loops are kept out of the slots, so these are found among all the names
#   tug    = a chain / rope / hook that is pulled: a short pull on R2. Not a jump (user 10-16: Chained Together
#            has only jumping - its ChainJump is not a pull, no trigger there)
TRIG_TUG = ("chain rope cable tether leash grapple hook winch", "pull tug yank snap whip reel")
TRIG_TOOL = "extinguisher flamethrower thrower hose sprayer drill chainsaw vacuum blower welder torch mower"


def words(name):
    s = re.sub(r"([a-z])([A-Z])", r"\1_\2", name)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    return [w for w in re.split(r"[^a-z]+", s.lower()) if w]


def stems(w):
    """the word and the word without -s / -es / -ing / -ed (washing -> wash, dropped -> dropp, drop)."""
    out = [w]
    for suf in ("ing", "ed", "es", "s", "e"):          # -e: a name in another spelling (WingCollecte -> collect)
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            b = w[:-len(suf)]
            out += [b, b[:-1]] if len(b) > 3 and b[-1] == b[-2] else [b]
    return out


def table(spec):
    return {w: k for k, ws in spec for w in ws.split()}


TRACK_W, ACTION_W, WORLD_W = table(TRACK.items()), table(ACTION), table(WORLD)
SPEAKER_W = set(SPEAKER.split())
ACTION_ORDER = [k for k, _ in ACTION]


def ucs_words(path):
    """word -> Counter(UCS category) from the UCS list (Soundminer/_categorylist.csv of the UCS release)."""
    out = collections.defaultdict(collections.Counter)
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        for w in [r["Category"], r["SubCategory"]] + r["Synonyms - Comma Separated"].split(","):
            for t in re.split(r"[^a-z]+", w.lower()):
                if len(t) > 2:
                    out[t][r["Category"]] += 1
    return out


def known(w, ucs):
    return w in TRACK_W or w in ACTION_W or w in WORLD_W or w in ucs


def compound(w, ucs):
    """a word run together from two (rathit, ocean + wave, bwarp): [first part, last part] when the last is an action
    or world word and the first a word too (or one letter) - iceblock is not ice + b + lock"""
    if len(w) < 5 or known(w, ucs): return [], []
    return next(((w[:i], w[i:]) for i in range(1, len(w) - 2) if (w[i:] in ACTION_W or w[i:] in WORLD_W or w[i:] in WAVE)
                 and (i == 1 or known(w[:i], ucs))), ([], []))


def slot_of(name, length, stop, ucs):
    # -e is dropped only from a word nobody knows and only into a word of our own lists (WingCollecte -> collect):
    # not fire -> fir (a tree), bite -> bit, Arche (a Lies of P enemy) -> arch (electricity in the dictionary)
    ws = [x for w in words(name) if w not in stop for x in stems(w)
          if not (x == w[:-1] and w.endswith("e") and (known(w, ucs) or not (x in ACTION_W or x in TRACK_W or x in SPEAKER_W)))]
    raw = words(name)
    first, last = compound(raw[0], ucs) if len(raw) == 1 else ([], [])   # a name with no break at all (rathit01,
    if last:                                                               # bwarp, oceanwave3): its last part is read
        ws.append(last)
    for w in ws:
        if w in TRACK_W:
            return (None if TRACK_W[w] == "skip" else "scene"), "track:" + w
    looped = any(w in ("loop", "lp", "lps", "idle") for w in raw)
    world = next((w for w in ws if w in WORLD_W), None) or next((w for w in ws if w in WAVE and SEA & set(ws + [first or ""])), None)
    if world:
        return WORLD_W.get(world, "quake"), "world:" + world
    # (whose sound: the raw words - enm / npc are a game's frequent words, read past above)
    if looped and not {"start", "stop"} & set(raw) and not set(ENEMY.split()) & set(raw):
        hold = next((w for w in ws if w in HOLD or w.startswith(HOLD_START)), None)
        if hold:
            return "hold", "hold:" + hold
    hits = sorted({ACTION_W[w] for w in ws if w in ACTION_W}, key=ACTION_ORDER.index)
    if "step_texture" in hits:
        hits.remove("step_texture")
        if "step" in hits:
            return "step_texture", "action:step+ground"
    if hits and not looped:
        return hits[0], "action:" + next(w for w in ws if ACTION_W.get(w) == hits[0])
    if looped or (length and length > LONG_S):
        return None, "loop" if looped else "long"
    vote = collections.Counter()
    for w in ws:
        c = ucs.get(w) or (ucs.get(w[:-1]) if w.endswith("s") else None)
        if c:
            tot = sum(c.values())
            for cat, n in c.items():
                vote[cat] += n / tot
    if vote:
        cat = vote.most_common(1)[0][0]
        return UCS_SLOT.get(cat), "ucs:" + cat
    return None, "none"


def classify(names, ucs):
    # a game's own frequent words are read past - but only words the sound dictionary does not know
    # (dlc, stage, obj ...): "bat" may be in a tenth of a game's names and still say what the sound is
    """names = [{"name", "len"}] -> [{"name", "slot", "why"}] (Stop_/Pause_ events dropped)."""
    names = [n for n in names if not re.match(r"(stop|pause|resume|mute|break|set|reset)_", n["name"], re.I)]
    df = collections.Counter(w for n in names for w in set(words(n["name"])))
    stop = {w for w, k in df.items() if k > 0.05 * len(names) and w not in TRACK_W and w not in ACTION_W and w not in ucs}
    stop |= {"play", "sfx", "se", "snd", "sound", "fx", "oneshot"}       # oneshot: a sound file that does not loop
    return [dict(n, slot=s, why=y) for n in names for s, y in [slot_of(n["name"], n.get("len"), stop, ucs)]], stop


# ---------------------------------------------------------------- which way, which names
def detect(game):
    """The way, from the files in the game folder. An Unreal pak with Wwise inside (ue_pak_bnk) is told apart
    only once the pak is open: names_ue_pak. fmod_bank and cri are recognised but have no reader yet."""
    data = next((os.path.join(game, d) for d in os.listdir(game) if d.endswith("_Data")), None)
    if data:
        if os.path.exists(os.path.join(data, "StreamingAssets", "Audio", "GeneratedSoundBanks")):
            return "unity_wwise"
        return "unity_audio"
    files = [(r, f) for r, _, fs in os.walk(game) for f in fs]
    low = {f.lower() for _, f in files}
    if any(f.endswith(".pak") and "Content" in r and "Engine" not in r.split(os.sep) for r, f in files):
        return "ue_pak"
    if "init.bnk" in low:                             # Wwise banks loose or inside the game's own archives (NieR)
        return "wwise_bnk"
    if any(f.endswith(".bhd") for f in low) and any(f.startswith("fmod") for f in low):
        return "fromsoft_fsb"                         # FromSoftware archives + FMOD Ex sound banks (Sekiro)
    if any(f.endswith(".bank") for f in low):
        return "fmod_bank"
    if any(f.endswith((".acb", ".awb")) for f in low):
        return "cri"
    return None


def sonmat_tools():
    """the app's tools/ (wwise_bnk.py, soundprep.py): SONMAT_TOOLS, or the sonmat repo next to this one"""
    d = os.environ.get("SONMAT_TOOLS") or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "sonmat", "tools")
    if d not in sys.path: sys.path.insert(0, d)
    return d


WWNAMES = "https://api.github.com/repos/bnnm/wwiser-utils/contents/wwnames"
def wwnames(game):
    """The public Wwise name list for this game (bnnm/wwiser-utils/wwnames, one name per line): the list whose
    file name starts with the game folder's name, PC first. None = no list - the events are numbers only."""
    import urllib.request
    key = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    g = key(os.path.basename(os.path.normpath(game)))
    ls = json.load(urllib.request.urlopen(urllib.request.Request(WWNAMES, headers={"User-Agent": "sonmat"})))
    hits = sorted((x for x in ls if key(x["name"]).startswith(g)), key=lambda x: "(pc)" not in x["name"].lower())
    if not hits: return None
    return urllib.request.urlopen(hits[0]["download_url"]).read().decode("utf-8", "replace").splitlines()


def fnv1(name):
    h = 2166136261
    for b in name.lower().encode():
        h = (h * 16777619) & 0xFFFFFFFF
        h ^= b
    return h


def names_wwise_bnk(game):
    """Wwise events in the game's banks (loose or in its archives), named from the public list."""
    sonmat_tools(); import wwise_bnk
    data = os.path.dirname(next(os.path.join(r, f) for r, _, fs in os.walk(game) for f in fs if f.lower() == "init.bnk"))
    while os.path.dirname(data) != os.path.normpath(game) and os.path.normpath(data) != os.path.normpath(game):
        data = os.path.dirname(data)                  # the top folder under the game that holds the banks
    index = wwise_bnk.scan(data, log=lambda m: None)
    events = {int(k) for k, v in index["objs"].items() if v[0] == wwise_bnk.EVENT}
    lst = wwnames(game)
    if lst is None:
        sys.exit("no public name list for this game: its events are numbers only (like an arcade ROM) - by hand")
    named = {fnv1(l.strip()): l.strip() for l in lst if l.strip() and not l.startswith("#")}
    out = [{"name": named[i], "id": i, "len": None} for i in events if i in named]
    print(f"events {len(events)}, named {len(out)}", file=sys.stderr)
    return sorted(out, key=lambda n: n["name"]), {"data": os.path.relpath(data, game).replace(os.sep, "/")}


FROMSOFT = {"archive": "Data1", "archive_files": ["/sound/main.fsb", "/sound/smain.fsb"]}   # Sekiro's layout


def names_fromsoft_fsb(game):
    """Sound names in the FMOD banks inside a FromSoftware archive (unpacked with BinderTool, as soundprep does)."""
    sonmat_tools(); import soundprep
    j = {"_id": "autosetup", "source": dict(FROMSOFT)}
    cfg = soundprep.load_config()
    out = {}
    with soundprep.temp_dir() as tmp:
        for b in soundprep.fromsoft_files(j, game, tmp, lambda m: print(m, file=sys.stderr)):
            for ns in soundprep.fsb_streams(soundprep.vgmstream_cmd(cfg), b):
                for n in ns.split(";"):
                    leaf = re.sub(r"\.wav$", "", n.strip().replace("\\", "/").rsplit("/", 1)[-1], flags=re.I)
                    if leaf: out.setdefault(leaf, {"name": leaf, "len": None})
    return sorted(out.values(), key=lambda n: n["name"]), dict(FROMSOFT)


def names_unity_wwise(game):
    import xml.etree.ElementTree as ET
    data = next(os.path.join(game, d) for d in os.listdir(game) if d.endswith("_Data"))
    root = os.path.join(data, "StreamingAssets", "Audio", "GeneratedSoundBanks")
    info = next(os.path.join(r, f) for r, _, fs in os.walk(root) for f in fs if f == "SoundbanksInfo.xml")
    out = {}
    for e in ET.parse(info).getroot().iter("Event"):
        mx = e.get("DurationMax")
        out[e.get("Name")] = {"name": e.get("Name"), "id": int(e.get("Id")),
                              "len": None if mx in (None, "Infinite") else float(mx),
                              "media": [int(m.get("Id")) for m in e.iter("MediaRef")]}
    return sorted(out.values(), key=lambda n: n["name"])


def ue_project(game):
    """(project folder, shipping exe path, CUE4Parse game version) of an Unreal game folder."""
    proj = next(d for d in os.listdir(game) if os.path.isdir(os.path.join(game, d, "Content", "Paks")))
    b = os.path.join(game, proj, "Binaries", "Win64")
    exe = next(os.path.join(b, f) for f in os.listdir(b) if f.endswith("-Shipping.exe"))
    m = re.search(rb"\+\+UE([45])\+Release-\1\.(\d+)", open(exe, "rb").read().replace(b"\0", b""))   # stored UTF-16
    return proj, exe, ("GAME_UE%s_%s" % (m.group(1).decode(), m.group(2).decode()) if m else "GAME_UE4_27")


# marketplace packs keep sounds under Wav/ or Cue/ (Chained Together's real footsteps: RealFootsteps/Cue, 10-15)
# and a folder named for sound in any form (SoundCue, AudioSFX) or "SD" (Lies of P: SD/SoundCue/...)
SOUND_DIR = re.compile(r"^(sfx|wavs?|cues?|sd)$|sound|audio", re.I)
NOT_A_SOUND = re.compile(r"attenuation|concurrency|class|submix|mix|reverb|settings|modulation|preset", re.I)


def names_ue_pak(game, key_id):
    """Every asset under a sound folder of the paks (the key is the one keyfetch found, in tools/config.json)."""
    import subprocess
    proj, exe, ver = ue_project(game)
    tool = os.environ.get("PAKTOOL", "paktool.exe")
    env = dict(os.environ, PAK_DIR=os.path.join(game, proj, "Content", "Paks"), PAK_GAME=ver, PAK_KEY_ID=key_id)
    r = subprocess.run([tool, "list", r"\.(uasset|bnk)$"], env=env, capture_output=True, text=True)
    if not r.stdout.strip():                          # a game CUE4Parse knows by name (GAME_BlackMythWukong): its folder
        ver = "GAME_" + re.sub(r"[^A-Za-z0-9]", "", os.path.basename(os.path.normpath(game)))
        r = subprocess.run([tool, "list", r"\.(uasset|bnk)$"], env=dict(env, PAK_GAME=ver), capture_output=True, text=True)
    out = r.stdout
    names, dirs, pre = {}, set(), proj + "/Content/"
    # Wwise inside (ue_pak_bnk): a bank per event (<...>/Event/<n>/<event>.bnk) -> the events are the names
    ev = [l.split("\t")[-1] for l in out.splitlines() if re.search(r"/Event/[^/]*/?[^/]*\.bnk$", l, re.I)]
    if ev:
        ns = {p.rsplit("/", 1)[-1][:-4] for p in ev}
        return (sorted(({"name": n, "id": fnv1(n), "len": None} for n in ns), key=lambda n: n["name"]),
                {"proj": proj, "exe": exe, "game": ver, "wwise": True})
    for line in out.splitlines():
        if not line.endswith(".uasset"): continue
        path = line.split("\t")[-1]
        if not path.startswith(pre): continue
        parts = path[len(pre):].split("/")
        k = next((i for i, x in enumerate(parts[:-1]) if SOUND_DIR.match(x)), None)
        if k is None: continue
        dirs.add("/".join(parts[:k + 1]))
        n = parts[-1][:-7]
        if not NOT_A_SOUND.search(n): names.setdefault(n, {"name": n, "len": None})
    return sorted(names.values(), key=lambda n: n["name"]), {"proj": proj, "exe": exe, "game": ver, "dirs": sorted(dirs)}


def names_unity_audio(game):
    import UnityPy
    data = next(os.path.join(game, d) for d in os.listdir(game) if d.endswith("_Data"))
    env, out = UnityPy.load(data), {}
    for obj in env.objects:
        if obj.type.name == "AudioClip":
            c = obj.read()
            out.setdefault(c.m_Name, {"name": c.m_Name, "len": round(float(getattr(c, "m_Length", 0) or 0), 3)})
    return sorted(out.values(), key=lambda n: n["name"])


# ---------------------------------------------------------------- which button does what
# pad keys -> the names hapticsd.py reads in the pad's report (PlayStation names; Xbox A = cross, B = circle, X = square)
PAD_UE = {"Gamepad_FaceButton_Bottom": "cross", "Gamepad_FaceButton_Right": "circle", "Gamepad_FaceButton_Left": "square",
          "Gamepad_FaceButton_Top": "triangle", "Gamepad_LeftShoulder": "l1", "Gamepad_RightShoulder": "r1",
          "Gamepad_LeftTrigger": "l2", "Gamepad_LeftTriggerAxis": "l2", "Gamepad_RightTrigger": "r2",
          "Gamepad_RightTriggerAxis": "r2"}
# Rewired's Gamepad template (maps made against it carry its guid): element id -> button. Action Bottom Row 1 / 2 =
# A / B, Top Row 1 / 2 = X / Y, Shoulder 1 / 2 = bumper / trigger (Biped's d-pad, confirm, cancel and start fit, 10-16)
REWIRED_PAD = "83b427e4-086f-47f3-bb06-be266abd1ca5"
PAD_REWIRED = {4: "cross", 5: "circle", 7: "square", 8: "triangle", 10: "l1", 11: "l2", 12: "r1", 13: "r2"}
COOP_CATS = {"Shared/Split Screen Co-op", "Shared/Split Screen"}


def inputs_ue(game, key_id):
    """{action: [buttons]} from the paks: DefaultInput.ini's ActionMappings (UE4) and every Enhanced Input mapping
    context (UE5, paktool imc)."""
    import subprocess, tempfile
    proj, _, ver = ue_project(game)
    tool = os.environ.get("PAKTOOL", "paktool.exe")
    env = dict(os.environ, PAK_DIR=os.path.join(game, proj, "Content", "Paks"), PAK_GAME=ver, PAK_KEY_ID=key_id)
    out = collections.defaultdict(set)
    r = subprocess.run([tool, "imc", r"/IMC_[^/]*\.uasset$"], env=env, capture_output=True, text=True)
    for line in r.stdout.splitlines():
        _, act, key = line.split("\t")
        if key in PAD_UE: out[act].add(PAD_UE[key])
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([tool, "extract", proj + r"/Config/DefaultInput\.ini$", tmp], env=env, capture_output=True)
        ini = os.path.join(tmp, proj, "Config", "DefaultInput.ini")
        if os.path.exists(ini):
            for m in re.finditer(r'^\+ActionMappings=\(ActionName="([^"]+)".*?Key=(\w+)', open(ini, encoding="utf-8",
                                 errors="replace").read(), re.M):
                if m.group(2) in PAD_UE: out[m.group(1)].add(PAD_UE[m.group(2)])
    return {k: sorted(v) for k, v in out.items()}


def inputs_rewired(game):
    """{action: [buttons]} from Rewired's input manager (the maps made for its Gamepad template). The manager is a
    script object without its layout in the build: the layout is made from the game's own DLLs (TypeTreeGeneratorAPI)."""
    import UnityPy
    from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
    data = next(os.path.join(game, d) for d in os.listdir(game) if d.endswith("_Data"))
    if not os.path.exists(os.path.join(data, "Managed", "Rewired_Core.dll")): return None
    env = UnityPy.load(os.path.join(data, "level0"))
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour": continue
        sc = obj.read(check_read=False).m_Script.read()
        if sc.m_ClassName != "InputManager" or sc.m_Namespace != "Rewired": continue
        g = TypeTreeGenerator(str(obj.assets_file.unity_version)); g.load_local_game(game)
        env.typetree_generator = g
        ud = obj.read_typetree()["_userData"]
        acts, out = {a["_id"]: a["_name"] for a in ud["actions"]}, collections.defaultdict(set)
        for m in ud["joystickMaps"]:
            if m.get("hardwareGuidString") != REWIRED_PAD: continue
            for e in m.get("actionElementMaps", []):
                b = PAD_REWIRED.get(e["_elementIdentifierId"]) if e["_elementType"] == 1 else None
                if b and e["_actionId"] in acts: out[acts[e["_actionId"]]].add(b)
        return {k: sorted(v) for k, v in out.items()}
    return None


def steam_coop(game):
    """True / False from the Steam store's categories (the app id from the library's appmanifest), None = unknown."""
    import urllib.request
    lib = os.path.dirname(os.path.dirname(os.path.normpath(game)))            # <library>/steamapps
    for f in os.listdir(lib):
        if not f.startswith("appmanifest_"): continue
        t = open(os.path.join(lib, f), encoding="utf-8", errors="replace").read()
        if re.search(r'"installdir"\s+"%s"' % re.escape(os.path.basename(os.path.normpath(game))), t, re.I):
            app = re.search(r'"appid"\s+"(\d+)"', t).group(1)
            u = f"https://store.steampowered.com/api/appdetails?appids={app}&l=english&filters=categories"
            d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "sonmat"})))[app]
            return bool(COOP_CATS & {c["description"] for c in d.get("data", {}).get("categories", [])})
    return None


def inputs(game, key_id):
    way = detect(game)
    acts = (inputs_ue(game, key_id) or None) if way == "ue_pak" else inputs_rewired(game) if way and way.startswith("unity") else None
    return {"actions": acts, "coop": steam_coop(game)}


WWISE_WAYS = ("unity_wwise", "ue_pak_bnk", "wwise_bnk")    # read by soundprep's Wwise reader: cutscene tracks too
# actions that are not the game's own: menus, chat messages, debug, the camera and moving (sticks)
NOT_PLAY = set("ui menu pause message chat tchat debug editor beta show submit cancel option options start continue "
               "select back quit reset look camera cam move horizontal vertical".split())
# an action's name -> the slots its sound is in (co-op: whose pad). Taking hold of a thing is touch; using it is a
# swing (chop, throw) - not touch: Chained Together's Use button would claim its walk-in pick-ups (WingCollecte)
PRESS = [("jump", "jump hop"), ("dodge", "dash roll dodge evade"), ("touch", "pick pickup grab drop put catch"),
         ("swing", "use interact attack throw chop")]
# the usual pad layout when a game's own cannot be read: A jumps / picks up, X uses, B dashes
HABIT = {"jump": ["cross"], "touch": ["cross", "square"], "swing": ["square"], "dodge": ["circle"]}


def game_json(pid, names, slots, steam_dir, exe, title, inp=None):
    """profiles/<id>/game.json from the names and their slots (and the buttons, `inputs`). One line per name in each
    slot's regex."""
    way, rows = names["way"], slots["rows"]
    inp = inp or {}
    acts = {a: b for a, b in (inp.get("actions") or {}).items() if not NOT_PLAY & set(words(a))}
    known = inp.get("actions") is not None
    on_trigger = any({"l2", "r2"} & set(b) for b in acts.values())
    data = exe[:-4] + "_Data"
    by = collections.defaultdict(list)
    for r in rows:
        if r["slot"]: by[r["slot"]].append(r["name"])
    rx = lambda ns: "^(?:%s)$" % "|".join(re.escape(n) for n in sorted(ns))
    spk_w = set(SPEAKER.split())
    has = lambda n, ws: any(x in ws for w in words(n) for x in stems(w))
    enemy, me = (lambda n: has(n, set(ENEMY.split()))), (lambda n: has(n, set(PLAYER.split())))
    any_me = any(me(r["name"]) for r in rows)
    mine = lambda n: not enemy(n) and (me(n) or not any_me)
    spk = [r["name"] for r in rows if not r["why"].startswith("track:") and has(r["name"], spk_w) and not enemy(r["name"])]
    trig = {}                     # only names put in their slot by an action word (the dictionary's "gun" is too wide)
    by_word = collections.defaultdict(list)
    for r in rows:
        if r["slot"] and r["why"].startswith("action:") and mine(r["name"]): by_word[r["slot"]].append(r["name"])
    by_all, by = by, by_word
    if by.get("shot"):
        trig["fire"] = {"match": rx(by["shot"]), "pad": "R2", "effect": "vibrate", "amp": 8, "hz": 8, "hold": 0.13}
    if by.get("charge"):
        end = [r["name"] for r in rows if r["slot"] in ("charge", "shot") and has(r["name"], set(TRIG_END.split()))]
        trig["charge"] = {"match": rx(set(by["charge"]) - set(end) or by["charge"]), "pad": "R2", "effect": "resist",
                          "force": 140, "hold": 4, **({"until": rx(end)} if end else {})}
    just = [r["name"] for r in rows if not r["why"].startswith("track:") and mine(r["name"])
            and has(r["name"], set(TRIG_JUST[0].split())) and has(r["name"], set(TRIG_JUST[1].split()))]
    if just:
        trig["just"] = {"match": rx(just), "pad": "R2", "effect": "vibrate", "amp": 8, "hz": 9, "hold": 0.13}
    all_names = {n if isinstance(n, str) else n.get("name") for n in names["names"]}
    starts, ends = [], []
    for n in sorted(all_names):
        m = re.match(r"(.+?)_?Start(_?\d*)$", n)
        if m and not enemy(n) and has(m.group(1), set(TRIG_TOOL.split())):   # a held tool: only "not an enemy's"
                                                                             # ("player" in one name of Overcooked 2 hid the rest)
            e = [x for x in all_names if re.match(re.escape(m.group(1)) + r"_?(End|Stop)(_?\d*)$", x)]
            if e: starts.append(n); ends += e
    tug = [n for n in sorted(all_names) if not enemy(n) and has(n, set(TRIG_TUG[0].split())) and has(n, set(TRIG_TUG[1].split()))]
    if tug:
        trig["tug"] = {"match": rx(tug), "pad": "R2", "effect": "resist", "force": 180, "hold": 0.25}
    if starts:
        trig["tool"] = {"match": rx(starts), "until": rx(ends), "pad": "R2", "effect": "resist", "force": 140, "hold": 12}
    by = by_all
    ue = way == "ue_pak"
    g = {"name": title, "exe": exe, "engine": "ue4" if ue else "wwise",
         "event_file": "C:\\Users\\Public\\dshaptics\\events_%s.log" % ("ue" if ue else "unity"),
         "_run_note": f"autosetup ({way}): BepInEx 5 + mods/unity/SonmatUnity.dll in the game folder sends every "
                      "sound name. Slots from tools/autosetup.py, nothing felt yet",
         "slots": {k: rx(v) for k, v in by.items() if k != "scene" or way in WWISE_WAYS}}
    # plain steps: the model sounds them in combat only, but whether a game fights cannot be told from names
    # (Overcooked 2's door slams fill "hit", a dash fills "dodge") - so here they always sound, as the faint tick
    if "step" in g["slots"]:
        g["slots"]["step"] = [g["slots"]["step"], {"combat_only": False}]
    # triggers only where the game puts an action of its own on L2 / R2 (model: "only on an action that really sits
    # on L2/R2"). Buttons not readable: by the names, but a held tool sits on the use button then, not on R2
    if known and not on_trigger:
        trig = {}
    if not on_trigger:
        trig.pop("tool", None)
    # co-op on one PC: whose pad an action's sound goes to = who pressed its button (new_profile.py -> press_owner)
    ctl = collections.defaultdict(set)
    if inp.get("coop"):
        for a, bs in (acts.items() if known else []):
            ws = {x for w in words(a) for x in stems(w)}
            for slot, kw in PRESS:
                if ws & set(kw.split()): ctl[slot].update(bs)
        if not known:
            for slot, bs in HABIT.items(): ctl[slot].update(bs)
    ctl = {k: sorted(v) for k, v in sorted(ctl.items()) if v and k in g["slots"]}
    if ctl:
        row = {r["name"]: r for r in rows}
        # what a player presses for is not news (Overcooked 2's pick-ups come every few seconds): off the speaker
        spk = [n for n in spk if not (row[n]["slot"] in ctl and row[n]["why"].startswith("action:"))]
        g["controls"] = ctl
        if any(row[n]["slot"] in ctl for n in spk):     # the rest of a pressed slot's speaker sounds: every pad's news
            g["controls"]["world"] = "speaker"
    if spk:
        g["speaker"] = {"allow": rx(spk)}
    if trig:
        g["triggers"] = dict(trig, _note="tools/autosetup.py: by slot and word, R2 (which trigger a game uses for "
                                         "what is not in its files) - nothing felt yet")
    src = {"steam_dir": steam_dir, "trees": "trees.json", "hap": "hap", "spk": "spk"}
    if spk: src["speaker"] = rx(spk)
    if way.startswith("unity"):
        g["install"] = {"bepinex": {}}
    if way == "unity_audio":
        g["source"] = dict(src, type="unity_audio", data=data)
    elif ue:
        u = names["ue"]
        g["_run_note"] = (f"autosetup (ue_pak, {u['game']}): UE4SS + the Lua mod DSHapticsUE4 send every sound a "
                          "blueprint plays, by its asset name (no native DLL: no signatures for this build). Slots "
                          "from tools/autosetup.py, nothing felt yet")
        g["install"] = {"ue4ss": {"mods": ["DSHapticsUE4"]}}
        g["source"] = dict(src, type="ue_pak_waves", paks=u["proj"] + "/Content/Paks", needs_key=True,
                           exe=u["proj"] + "/Binaries/Win64/" + re.split(r"[\\/]", u["exe"])[-1], game=u["game"],
                           content=u["proj"] + "/Content", dirs=u["dirs"])
    elif way == "ue_pak_bnk":
        u = names["ue"]
        g.update(engine="wwise", event_file="C:\\Users\\Public\\dshaptics\\events.log",
                 _run_note=f"autosetup (ue_pak_bnk, {u['game']}): UE4SS + the Lua mod DSHaptics send the Wwise events a "
                           "blueprint posts; the native DLL adds what C++ posts if sigs.txt fits this Wwise. Slots from "
                           "tools/autosetup.py, nothing felt yet")
        g["install"] = {"ue4ss": {"mods": ["DSHaptics"]}}
        g["native"] = {"dll": "dshaptics_wwise.dll", "sigs_file": "sigs.txt", "event_ids": "event_ids.json"}
        g["source"] = dict(src, type="ue_pak_bnk", paks=u["proj"] + "/Content/Paks", needs_key=True,
                           exe=u["proj"] + "/Binaries/Win64/" + re.split(r"[\\/]", u["exe"])[-1], game=u["game"],
                           event_ids="event_ids.json")
    elif way == "wwise_bnk":
        g.update(engine="wwise", event_file="C:\\Users\\Public\\dshaptics\\events.log",
                 _run_note="autosetup (wwise_bnk): names from the public list (bnnm/wwiser-utils). The hook is the "
                           "native DLL only, and its patterns are found by hand for each game (NieR: in a Steamless copy "
                           "of the exe) - until then nothing arrives. Slots from tools/autosetup.py, nothing felt yet")
        g["native"] = {"dll": f"{pid}/dshaptics_wwise_wide.dll", "event_ids": "event_ids.json", "main": True}
        g["source"] = dict(src, type="wwise_bnk", data=names["ue"]["data"], event_ids="event_ids.json")
    elif way == "fromsoft_fsb":
        g.update(engine="ue4", event_file="C:\\Users\\Public\\dshaptics\\events_fmod.log", player=".",
                 _run_note="autosetup (fromsoft_fsb): the FMOD Ex hook (dll/dshaptics_fmodex.dll) reports a sound by its "
                           "place in the bank - run tools/fmod_ids.py <id> once for the names. Slots from "
                           "tools/autosetup.py; unnamed blows are picked by their shape when the sounds are prepared")
        g["native"] = {"dll": "dshaptics_fmodex.dll", "places": "fmod_ids.json"}
        g["source"] = dict(src, type="fromsoft_fsb", auto_rules="rules_auto.json", auto_gain=0.6,
                           **{k: v for k, v in names["ue"].items() if k in ("archive", "archive_files")})
    elif way == "unity_wwise":
        g["native"] = {"event_ids": "event_ids.json"}
        g["source"] = dict(src, type="wwise_bnk", data=data + "/StreamingAssets/Audio/GeneratedSoundBanks/Windows",
                           event_ids="event_ids.json")
    if way in WWISE_WAYS and "scene" in g["slots"]:   # a cutscene's event carries the scene's sounds: a track
        g["scenes"] = {"trees": "trees_seq.json", "dir": "seq"}
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles", pid)
    os.makedirs(d, exist_ok=True)
    if way in ("unity_wwise", "ue_pak_bnk", "wwise_bnk"):
        json.dump({str(n["id"]): n["name"] for n in names["names"]}, open(os.path.join(d, "event_ids.json"), "w"),
                  ensure_ascii=False, indent=0)
    json.dump(g, open(os.path.join(d, "game.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return d


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "detect":
        print(detect(sys.argv[2]))
    elif cmd == "names":                                  # names <game> <out> [key id: Unreal paks with a key]
        way, extra = detect(sys.argv[2]), {}
        if way == "ue_pak":
            ns, extra = names_ue_pak(sys.argv[2], sys.argv[4] if len(sys.argv) > 4 else "none")
            if extra.get("wwise"): way = "ue_pak_bnk"
        elif way in ("wwise_bnk", "fromsoft_fsb"):
            ns, extra = {"wwise_bnk": names_wwise_bnk, "fromsoft_fsb": names_fromsoft_fsb}[way](sys.argv[2])
        elif way in ("unity_wwise", "unity_audio"):
            ns = {"unity_wwise": names_unity_wwise, "unity_audio": names_unity_audio}[way](sys.argv[2])
        else:
            sys.exit(f"{way}: no reader for this way yet - by hand")
        json.dump({"way": way, "names": ns, "ue": extra}, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False)
        print(way, len(ns))
    elif cmd == "inputs":                                 # inputs <game> <out> [key id: Unreal paks with a key]
        r = inputs(sys.argv[2], sys.argv[4] if len(sys.argv) > 4 else "none")
        json.dump(r, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("co-op" if r["coop"] else "one player" if r["coop"] is False else "co-op unknown",
              "| buttons:", "not readable (usual layout)" if r["actions"] is None else len(r["actions"]))
    elif cmd == "game":
        pid = sys.argv[2]
        d = game_json(pid, json.load(open(sys.argv[3], encoding="utf-8")), json.load(open(sys.argv[4], encoding="utf-8")),
                      *sys.argv[5:8], inp=json.load(open(sys.argv[8], encoding="utf-8")) if len(sys.argv) > 8 else None)
        import subprocess
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "new_profile.py"), pid], check=True)
    elif cmd == "slots":
        src = json.load(open(sys.argv[2], encoding="utf-8"))
        rows, stop = classify(src["names"], ucs_words(sys.argv[3]))
        json.dump({"way": src["way"], "stop": sorted(stop), "rows": rows},
                  open(sys.argv[4], "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        c = collections.Counter(r["slot"] or "-" for r in rows)
        print(f"{len(rows)} names, ignored words: {', '.join(sorted(stop))}")
        print("  " + ", ".join(f"{k} {v}" for k, v in c.most_common()))
