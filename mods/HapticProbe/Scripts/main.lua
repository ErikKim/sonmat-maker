-- HapticProbe: log every sound/damage call with asset name and whether the player owns it.
local LOG = io.open("HapticProbe.log", "a")
local function log(s) LOG:write(os.date("%H:%M:%S "), s, "\n"); LOG:flush() end
log("=== HapticProbe loaded ===")

local function name_of(v)
    local ok, r = pcall(function()
        if v == nil then return "nil" end
        if type(v) ~= "userdata" then return tostring(v) end
        if v.IsValid and not v:IsValid() then return "invalid" end
        if v.GetFullName then return v:GetFullName() end
        if v.ToString then return "str:" .. v:ToString() end
        return tostring(v)
    end)
    return ok and r or "?"
end

local player_name = nil
local function player()
    if player_name then return player_name end
    pcall(function()
        local pc = FindFirstOf("PlayerController")
        if pc and pc:IsValid() and pc.Pawn and pc.Pawn:IsValid() then player_name = pc.Pawn:GetFullName() end
    end)
    return player_name
end

local function owner_of(obj)
    local ok, r = pcall(function()
        if obj.GetOwner then local o = obj:GetOwner(); if o and o:IsValid() then return o:GetFullName() end end
        return obj:GetFullName()
    end)
    return ok and r or "?"
end

local warned = {}
local function hook(path)
    local ok, err = pcall(RegisterHook, path, function(ctx, ...)
        local args = {...}
        local parts = {}
        for i, a in ipairs(args) do
            local v = a; pcall(function() v = a:get() end)
            parts[#parts+1] = name_of(v)
        end
        local self = ctx; pcall(function() self = ctx:get() end)
        local own = owner_of(self)
        local p = player()
        local mine = (p and (own == p or own:find(p, 1, true))) and "P1" or "--"
        log(string.format("%s | %s | self=%s | owner=%s | %s", mine, path:match("[^%.]+$"), name_of(self), own, table.concat(parts, " , ")))
    end)
    if ok or not warned[path] then log((ok and "hooked  " or "pending ") .. path); warned[path] = true end
    return ok
end

local targets = {
    "/Script/AkAudio.AkGameObject:PostAkEvent",
    "/Script/AkAudio.AkGameObject:PostAkEventAsync",
    "/Script/AkAudio.AkGameObject:PostAssociatedAkEvent",
    "/Script/AkAudio.AkGameObject:PostAssociatedAkEventAsync",
    "/Script/AkAudio.AkComponent:PostAkEventAndWaitForEnd",
    "/Script/AkAudio.AkGameplayStatics:PostEventOnDummyObj",
    "/Script/AkAudio.AkGameplayStatics:PostEventAtLocationByName",
    "/Script/AkAudio.AkGameplayStatics:PostEvent",
    "/Script/AkAudio.AkGameplayStatics:PostEventAtLocation",
    "/Script/AkAudio.AkGameplayStatics:PostEventByName",
    "/Script/AkAudio.AkAudioEvent:PostOnActor",
    "/Script/AkAudio.AkAudioEvent:PostOnComponent",
    "/Script/AkAudio.AkAudioEvent:PostAtLocation",
    "/Script/Engine.GameplayStatics:PlaySoundAtLocation",
    "/Script/Engine.GameplayStatics:SpawnSoundAtLocation",
    "/Script/Engine.GameplayStatics:SpawnSoundAttached",
    "/Script/Engine.GameplayStatics:PlaySound2D",
    "/Script/Engine.GameplayStatics:SpawnSound2D",
    "/Script/Engine.AudioComponent:Play",
    "/Script/Engine.Actor:ReceiveAnyDamage",
    "/Script/Engine.Actor:ReceivePointDamage",
    "/Script/Engine.GameplayStatics:ApplyDamage",
    "/Script/Engine.GameplayStatics:ApplyPointDamage",
}
-- engine classes may load late (AkComponent only after a level loads): retry every 5s
local pending = {}
for _, t in ipairs(targets) do pending[t] = true end
LoopAsync(5000, function()
    ExecuteInGameThread(function()
        for t in pairs(pending) do
            if hook(t) then pending[t] = nil end
        end
    end)
    return next(pending) == nil
end)

