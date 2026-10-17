-- SoundProbe (UE native audio): log every sound start with asset name and owner.
local LOG = io.open("SoundProbe.log", "a")
local function log(s) LOG:write(os.date("%H:%M:%S "), s, "\n"); LOG:flush() end
log("=== SoundProbe loaded ===")

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

local function short(n) return (n:gsub("^%S+ ", ""):gsub("^.*:PersistentLevel%.", "")) end

local function owner_of(obj)
    local ok, r = pcall(function()
        local o = obj:GetOwner(); if o and o:IsValid() then return short(o:GetFullName()) end
        return "-"
    end)
    return ok and r or "-"
end

local warned = {}
local function hook(path)
    local fname = path:match("[^%.]+$")
    local ok = pcall(RegisterHook, path, function(ctx, ...)
        local self = ctx; pcall(function() self = ctx:get() end)
        local parts = {}
        if fname:find("^AudioComponent:") then
            local snd = "?"; pcall(function() snd = name_of(self.Sound) end)
            parts[1] = "sound=" .. snd
            parts[2] = "owner=" .. owner_of(self)
        else
            for _, a in ipairs({...}) do
                local v = a; pcall(function() v = a:get() end)
                local n = name_of(v)
                if n:find("Sound") or n:find("Actor") or n:find("Character") or n:find("Component") then parts[#parts+1] = short(n) end
            end
        end
        log(fname .. " | " .. table.concat(parts, " , "))
    end)
    if ok or not warned[path] then log((ok and "hooked  " or "pending ") .. path); warned[path] = true end
    return ok
end

local targets = {
    "/Script/Engine.GameplayStatics:PlaySoundAtLocation",
    "/Script/Engine.GameplayStatics:SpawnSoundAtLocation",
    "/Script/Engine.GameplayStatics:SpawnSoundAttached",
    "/Script/Engine.GameplayStatics:PlaySound2D",
    "/Script/Engine.GameplayStatics:SpawnSound2D",
    "/Script/Engine.AudioComponent:Play",
    "/Script/Engine.AudioComponent:FadeIn",
    "/Script/Engine.AudioComponent:SetSound",
    "/Script/Engine.Actor:ReceiveAnyDamage",
    "/Script/Engine.Actor:ReceivePointDamage",
    "/Script/Engine.GameplayStatics:ApplyDamage",
    "/Script/Engine.GameplayStatics:ApplyPointDamage",
}
local pending = {}
for _, t in ipairs(targets) do pending[t] = true end
LoopAsync(5000, function()
    ExecuteInGameThread(function()
        for t in pairs(pending) do if hook(t) then pending[t] = nil end end
    end)
    return next(pending) == nil
end)
