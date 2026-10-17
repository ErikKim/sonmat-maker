-- Headless auto-play for Cadillacs and Dinosaurs on MAME (maker tool, not shipped to players): coin, start,
-- first character, then walk right / punch / jump on a fixed cycle with the public energy poke, starting at
-- a chosen episode, so the sonmat plugin can log a run without anyone playing.
--
--   SONMAT_OUT=/tmp/ev.log mame dino -rompath ~/mame/roms -pluginspath "<mame plugins>;<dshaptics>/mods/mame" \
--     -plugin sonmat -skip_gameinfo -video none -sound none -nothrottle -nocoin_lockout \
--     -snapshot_directory /tmp/snap -autoboot_script tools/mame_autoplay_dino.lua -autoboot_delay 0
--   DN_EP    starting episode 0-7 (public poke ff84d9)     DN_END   last frame
--   DN_SNAP  snapshot every N frames                       DN_FULL  file for raw ff8000-ffbfff every 60 frames
--   DN_OBJ / DN_WPN: see below                 DN_WANDER  1 = walk around without buttons (to get grabs)
--   DN_IDLE  from this frame on, hold right only (no buttons)     DN_STAY  "a,b": no input at all between these frames
local EP = tonumber(os.getenv("DN_EP") or "0")
local END = tonumber(os.getenv("DN_END") or "20000")
local SNAP = tonumber(os.getenv("DN_SNAP") or "300")
local FULL = os.getenv("DN_FULL")
local IDLE = tonumber(os.getenv("DN_IDLE") or "0")
local SA, SB = (os.getenv("DN_STAY") or "0,0"):match("(%d+),(%d+)")
SA, SB = tonumber(SA), tonumber(SB)
local OBJ = os.getenv("DN_OBJ")          -- file: P1 object (ffb274, 0x180 bytes) every frame from 1300 on
local WPN = os.getenv("DN_WPN")          -- "1": no fighting; every 120 frames put the next value 0200.. in the weapon cell, snapshot 40 frames later
local mach = manager.machine
local mem = mach.devices[":maincpu"].spaces["program"]
local fields = {}
for tag, port in pairs(mach.ioport.ports) do
  for name, f in pairs(port.fields) do fields[name] = f end
end
if os.getenv("DN_LIST") then for n in pairs(fields) do print("FIELD", n) end end
local function press(name, on) local f = fields[name]; if f then f:set_value(on and 1 or 0) end end
local fr = 0
local sub = emu.add_machine_frame_notifier(function()
  fr = fr + 1
  press("Coin 1", fr >= 600 and fr < 612)
  if fr >= 700 and fr < 1300 then mem:write_u8(0xff84d9, EP) end
  press("1 Player Start", fr >= 760 and fr < 768)
  if fr < 1300 then
    press("P1 Button 1", fr >= 900 and fr % 60 < 6)
  else
    mem:write_u8(0xffb2e1, 0x64)
    if os.getenv("DN_INV") then mem:write_u8(0xffb360, 0x00); mem:write_u8(0xffb361, 0x02) end   -- public invincibility poke: nobody interrupts a grab
    local ph = fr % 360
    if IDLE > 0 and fr >= IDLE then ph = 400 end
    if fr >= SA and fr < SB then ph = 500 end          -- no window below matches 500
    press("P1 Right", ph < 150 or (ph >= 240 and ph < 300) or ph == 400)
    press("P1 Down", ph >= 100 and ph < 125 and (fr // 360) % 2 == 0)
    press("P1 Up", ph >= 100 and ph < 125 and (fr // 360) % 2 == 1)
    local mash = fr % 8 < 4
    press("P1 Button 1", (ph >= 150 and ph < 240 and mash) or (ph >= 330 and ph < 360 and mash))
    press("P1 Button 2", ph >= 250 and ph < 254)
  end
  if OBJ and fr >= 1300 then
    local f = io.open(OBJ, "ab"); f:write(string.pack("<I4", fr)); f:write(mem:read_range(0xffb274, 0xffb3f3, 8)); f:close()
  end
  if WPN and fr >= 1500 then
    press("P1 Right", false); press("P1 Button 1", false); press("P1 Button 2", false); press("P1 Down", false); press("P1 Up", false)
    local i = (fr - 1500) // 120
    if (fr - 1500) % 120 < 40 then mem:write_u16(0xffb32a, 0x0200 + i) end
    if (fr - 1500) % 120 == 40 then mach.video:snapshot() end
  end
  if os.getenv("DN_WANDER") and fr >= 1300 then      -- no buttons, walk into whoever is around: left/right 50 frames each, up/down drifting
    local k = (fr // 50) % 4
    press("P1 Right", k == 0 or k == 1); press("P1 Left", k == 2 or k == 3)
    press("P1 Up", (fr // 35) % 4 == 1); press("P1 Down", (fr // 35) % 4 == 3)
    press("P1 Button 1", false); press("P1 Button 2", false)
  end
  if FULL and fr % 60 == 0 then
    local f = io.open(FULL, "ab"); f:write(string.pack("<I4", fr)); f:write(mem:read_range(0xff8000, 0xffbfff, 8)); f:close()
  end
  if fr % SNAP == 0 then mach.video:snapshot() end
  if fr >= END then mach:exit() end
end)
_G.__dn_sub = sub
