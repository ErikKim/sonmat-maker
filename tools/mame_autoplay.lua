-- Headless auto-play for Final Fight on MAME (maker tool, not shipped to players): coin, start, pick a
-- character, then walk / punch / jump-kick / special on a fixed cycle with the public energy and time pokes,
-- so the sonmat plugin can log a run without anyone playing. Same inputs every run -> runs are comparable
-- (2026-10-06: the same run with all three characters showed which sound commands are per character).
--
--   SONMAT_OUT=/tmp/ev.log mame ffight -rompath ~/mame/roms -pluginspath "<mame plugins>;<dshaptics>/mods/mame" \
--     -plugin sonmat -skip_gameinfo -video none -sound none -nothrottle -nocoin_lockout \
--     -snapshot_directory /tmp/snap -autoboot_script tools/mame_autoplay.lua -autoboot_delay 0
--   -nocoin_lockout is required: without it the scripted coin is ignored and the game stays in attract mode.
--   FF_CHAR  -1 Haggar, 0 Guy, 1 Cody          FF_END   last frame (30x speed: 12000 frames = ~7 s)
--   FF_SKIP  frames at which to clear the current scene, e.g. 1400,2200,3000 = straight to the subway
--   FF_P2    1 = two players (P2 walks with P1; attacks ph 195-285, P1 150-240: alone / together / alone)
--   FF_IDLE  from this frame on, only walk right, no buttons (to record a scene's own sound with -wavwrite)
--   FF_SNAP  snapshot every N frames           FF_DUMP  text dump of ff8100-ff813f + player state, every 30 frames
--   FF_OBJ   file for the P1 object every frame (to find per-player cells, e.g. the weapon in hand)
--   FF_FULL  file for raw ff8000-ff8fff every 100 frames (to find scene / object addresses by comparing scenes)
local CHAR = tonumber(os.getenv("FF_CHAR") or "0")      -- presses of "right" on the select screen (negative = left)
local END = tonumber(os.getenv("FF_END") or "12000")
local SKIP = os.getenv("FF_SKIP") or ""                 -- frames at which to poke "clear this scene", comma list
local P2 = os.getenv("FF_P2")
local IDLE = tonumber(os.getenv("FF_IDLE") or "0")
local START = tonumber(os.getenv("FF_START") or "760")
local FULL = os.getenv("FF_FULL")
local SNAP = tonumber(os.getenv("FF_SNAP") or "600")
local mach = manager.machine
local mem = mach.devices[":maincpu"].spaces["program"]
local fields = {}
for tag, port in pairs(mach.ioport.ports) do
  for name, f in pairs(port.fields) do fields[name] = f end
end
if os.getenv("FF_LIST") then for n in pairs(fields) do print("FIELD", n) end end
local function press(name, on) local f = fields[name]; if f then f:set_value(on and 1 or 0) end end
local skips = {}
for s in SKIP:gmatch("%d+") do skips[tonumber(s)] = true end
local dump = io.open(os.getenv("FF_DUMP") or "dump.txt", "w")
local fr = 0
local sub = emu.add_machine_frame_notifier(function()
  fr = fr + 1
  -- boot ~ 300 frames, then coin/start
  press("Coin 1", (fr >= 600 and fr < 612) or (P2 and fr >= 640 and fr < 652))
  press(P2 and "2 Players Start" or "1 Player Start", fr >= START and fr < START + 8)
  local sel = 860
  local n = math.abs(CHAR)
  local dir = CHAR < 0 and "P1 Left" or "P1 Right"
  local moving = false
  for i = 0, n - 1 do
    if fr >= sel + i * 20 and fr < sel + i * 20 + 4 then moving = true end
  end
  if fr < 1200 then
    press("P1 Left", moving and CHAR < 0); press("P1 Right", moving and CHAR > 0)
    press("P1 Button 1", fr >= sel + n * 20 + 30 and fr < sel + n * 20 + 36)
    if P2 then press("P2 Button 1", fr >= sel + 100 and fr < sel + 106) end
  else
    mem:write_u8(0xff8581, 0x90); mem:write_u8(0xff80af, 0x99)
    if os.getenv("FF_INV") and fr >= tonumber(os.getenv("FF_INV")) then mem:write_u8(0xff85c9, 0xfe) end      -- public invincibility poke: a weapon in hand is never knocked away
    if skips[fr] then mem:write_u8(0xff8129, 0x01) end
    local ph = fr % 360
    local cyc = (fr // 360) % 2
    if IDLE > 0 and fr >= IDLE then ph = 400 end      -- no window below matches 400
    press("P1 Right", ph < 150 or (ph >= 240 and ph < 300) or ph == 400)
    press("P1 Down", ph >= 100 and ph < 125 and cyc == 0); press("P1 Up", ph >= 100 and ph < 125 and cyc == 1)
    local mash = fr % 8 < 4
    local b1 = (ph >= 150 and ph < 240 and mash) or (ph >= 262 and ph < 266) or (ph >= 310 and ph < 314) or (ph >= 330 and ph < 360 and mash)
    local b2 = (ph >= 250 and ph < 254) or (ph >= 310 and ph < 314)
    press("P1 Button 1", b1); press("P1 Button 2", b2)
    if P2 then
      mem:write_u8(0xff8641, 0x90)
      press("P2 Right", ph < 150 or (ph >= 290 and ph < 330))
      press("P2 Down", ph >= 100 and ph < 125 and cyc == 1); press("P2 Up", ph >= 100 and ph < 125 and cyc == 0)
      press("P2 Button 1", ph >= 195 and ph < 285 and (fr + 4) % 8 < 4)
    end
  end
  if fr % 30 == 0 then
    local t = {}
    for a = 0xff8100, 0xff813f do t[#t + 1] = string.format("%02x", mem:read_u8(a)) end
    dump:write(fr, " ", table.concat(t), " | st=", string.format("%02x air=%02x en=%02x x=%04x y=%04x", mem:read_u8(0xff856b), mem:read_u8(0xff85f0), mem:read_u8(0xff8581), mem:read_u16(0xff856e), mem:read_u16(0xff8572)), "\n")
  end
  if os.getenv("FF_OBJ") and fr >= 1200 then      -- P1 object (ff8568, 0xc0 bytes) every frame
    local f = io.open(os.getenv("FF_OBJ"), "ab"); f:write(string.pack("<I4", fr)); f:write(mem:read_range(0xff8568, 0xff8627, 8)); f:close()
    if mem:read_u8(0xff85b2) ~= 0 then             -- something in hand: the object its pointer (+4c) names, 0x60 bytes
      local at = mem:read_u32(0xff85b4) & 0xffffff
      local g = io.open(os.getenv("FF_OBJ") .. ".held", "ab"); g:write(string.pack("<I4I4", fr, at)); g:write(mem:read_range(at, at + 0x5f, 8)); g:close()
    end
  end
  if FULL and fr % 100 == 0 then
    local f = io.open(FULL, "ab"); f:write(string.pack("<I4", fr)); f:write(mem:read_range(0xff8000, 0xff8fff, 8)); f:close()
  end
  if fr % SNAP == 0 or fr == 1250 then mach.video:snapshot() end
  if fr >= END then dump:close(); mach:exit() end
end)
_G.__ff_sub = sub
