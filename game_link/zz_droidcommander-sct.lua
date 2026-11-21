-- Droid Commander game link
--
-- Writes a few game events (your kills, hits on your ship, low hull, deaths, mission start/end)
-- as text lines to "droid_link.log", which Droid Commander reads so the droid can react, and
-- once a second a snapshot of your ship (hull, shields, energy, target, enemies left) to
-- "droid_state.txt", so the droid can answer questions like "are you ok?".
--
-- Voice commands: Droid Commander writes the game controls to press (e.g. MAX_THROTTLE) to
-- "droid_cmd.txt"; this script presses them through FSO's Lua button controls, exactly as if
-- you pressed their key, and confirms in "droid_ack.txt". It presses nothing else and changes
-- nothing else in the game.
--
-- Multiplayer: it runs in fair-play mode, so the droid only knows what your HUD shows:
-- "enemies left" counts only the hostile ships your radar can see (no stealth ships,
-- nothing out of sensor range).
--
-- Line format:  <seq>|<mission time>|<event>|<detail>
--
-- Installed and removed by Droid Commander (Events tab). Safe to delete by hand.

DroidLink = {
	file = "droid_link.log",
	state_file = "droid_state.txt",   -- snapshot of your ship, rewritten every second
	next_state = 0,
	path = "data/missions",       -- a writable folder (Fate of the Galaxy writes there too)
	seq = 0,
	hull_marks = {0.5, 0.25},     -- report when the hull drops below these fractions
	hull_level = 0,               -- how many marks have been passed
	next_check = 0,
	enabled = true,
	-- voice commands (game controls pressed for Droid Commander)
	cmd_file = "droid_cmd.txt",       -- written by Droid Commander: "<seq>|ACTION:count,ACTION:count"
	ack_file = "droid_ack.txt",       -- our answer: "<seq>|ok|..." or "<seq>|fail|reason"
	last_cmd = -1,                    -- last command seq handled (-1: not read yet)
	queue = {},                       -- {num, name, count} controls still to press
	pressed = false,                  -- a control is held this frame (released on the next)
	frame = 0,
}

-- ---------------------------------------------------------------- voice commands
function DroidLink:controlInfo()
	if self.ci == nil then pcall(function() self.ci = ba.getControlInfo() end) end
	return self.ci
end

function DroidLink:ack(seq, status, detail)
	pcall(function()
		local f = cf.openFile(self.ack_file, "w", self.path)
		if f ~= nil and f:isValid() then
			f:write(string.format("%s|%s|%s\n", tostring(seq), status, detail or ""))
			f:close()
		end
	end)
end

-- the game's number for a control name such as "MAX_THROTTLE", or nil
function DroidLink:controlNumber(name)
	local ci = self:controlInfo()
	if ci == nil then return nil end
	local ok, n = pcall(function() return ci:getButtonControlNumber(name) end)
	if ok and type(n) == "number" and n >= 0 then return n end
	return nil
end

-- read droid_cmd.txt; with skip, only remember where it is (old commands are never run)
function DroidLink:readCommands(skip)
	local lines = {}
	pcall(function()
		local f = cf.openFile(self.cmd_file, "r", self.path)
		if f == nil or not f:isValid() then return end
		for _ = 1, 50 do
			local line = f:read("*l")
			if line == nil then break end
			lines[#lines + 1] = line
		end
		f:close()
	end)
	for _, line in ipairs(lines) do
		local seq, body = line:match("^(%d+)|(.*)$")
		seq = tonumber(seq)
		if seq ~= nil and seq > self.last_cmd then
			self.last_cmd = seq
			if not skip then self:runCommand(seq, body) end
		end
	end
	if self.last_cmd < 0 then self.last_cmd = 0 end
end

function DroidLink:runCommand(seq, body)
	if self:controlInfo() == nil then
		self:ack(seq, "fail", "no Lua control info in this FSO build")
		return
	end
	local actions, missing, used = {}, {}, {}
	for name, count in body:gmatch("([%w_]+):(%d+)") do
		local n = self:controlNumber(name)
		if n == nil then
			missing[#missing + 1] = name
		else
			actions[#actions + 1] = {num = n, name = name, count = tonumber(count)}
			used[#used + 1] = name .. "=" .. n
		end
	end
	if #missing > 0 or #actions == 0 then
		self:ack(seq, "fail", "unknown control " .. table.concat(missing, ","))
		return
	end
	for _, a in ipairs(actions) do self.queue[#self.queue + 1] = a end
	self:ack(seq, "ok", table.concat(used, ","))
end

-- every frame: hold a queued control for one frame, release it for one frame, next one...
function DroidLink:pressControls()
	local ci = self:controlInfo()
	if ci == nil then return end
	if self.pressed then
		pcall(function() ci:clearLuaButtonInfo() end)
		self.pressed = false
		return
	end
	local a = self.queue[1]
	if a == nil then return end
	pcall(function() ci:useButtonControl(a.num, a.name) end)
	self.pressed = true
	a.count = a.count - 1
	if a.count <= 0 then table.remove(self.queue, 1) end
end

function DroidLink:commandsTick()
	self.frame = self.frame + 1
	self:pressControls()
	if self.frame % 5 == 0 then self:readCommands(self.last_cmd < 0) end
end

function DroidLink:resetCommands()
	self.queue, self.pressed, self.ci = {}, false, nil
	self.last_cmd = -1
	pcall(function() ba.setButtonControlMode(BUTTON_CONTROL_LUA_ADDITIVE) end)
	local ci = self:controlInfo()
	if ci ~= nil then pcall(function() ci:clearLuaButtonInfo() end) end
	self:readCommands(true)          -- commands written before this mission are not run
end

function DroidLink:write(event, detail)
	if not self.enabled then return end
	local ok = pcall(function()
		local f = cf.openFile(self.file, "a", self.path)
		if f ~= nil and f:isValid() then
			self.seq = self.seq + 1
			local t = 0
			pcall(function() t = mn.getMissionTime() or 0 end)
			f:write(string.format("%d|%.1f|%s|%s\n", self.seq, t, event, detail or ""))
			f:close()
		end
	end)
	if not ok then self.enabled = false end    -- never disturb the game if writing fails
end

-- the mission's "$Starting wing names" (FSO lists these wings first in the comm menu)
function DroidLink:readStartingWings()
	self.starting_wings = {"Alpha", "Beta", "Gamma"}           -- FSO's default
	pcall(function()
		local name = mn.getMissionFilename()
		if name == nil or name == "" then return end
		if not name:lower():find("%.fs2$") then name = name .. ".fs2" end
		local f = cf.openFile(name, "r", "")
		if f == nil or not f:isValid() then return end
		for _ = 1, 400 do
			local line = f:read("*l")
			if line == nil then break end
			if line:find("^%$Starting wing names:") then
				local names = {}
				for n in line:gmatch('"([^"]*)"') do names[#names + 1] = n end
				if #names > 0 then self.starting_wings = names end
				break
			end
		end
		f:close()
	end)
end

-- true if FSO would list this wing in the comm menu: a friendly ship of it is still flying
function DroidLink:wingUsable(wing, player)
	local ok, usable = pcall(function()
		for j = 1, #wing do
			local s = wing[j]
			if s ~= nil and s:isValid() and s ~= player and not s:isDying()
					and s.Team.Name == player.Team.Name then
				local departing = false
				pcall(function() departing = s:isDeparting() end)
				if not departing then return true end
			end
		end
		return false
	end)
	return ok and usable
end

-- your wings in the order of the comm menu "Wings" list: starting wings first, then the others
function DroidLink:wingMenu(player)
	local starting, listed, out = {}, {}, {}
	for i, n in ipairs(self.starting_wings or {}) do starting[n:lower()] = i end
	local wings = {}
	for i = 1, #mn.Wings do
		local w = mn.Wings[i]
		if w ~= nil and w:isValid() and self:wingUsable(w, player) then
			wings[#wings + 1] = {name = w.Name, start = starting[w.Name:lower()], index = i}
		end
	end
	table.sort(wings, function(a, b)
		if (a.start ~= nil) ~= (b.start ~= nil) then return a.start ~= nil end
		if a.start ~= nil then return a.start < b.start end
		return a.index < b.index
	end)
	for _, w in ipairs(wings) do out[#out + 1] = (w.name:gsub("|", "/")) end
	return table.concat(out, "|")
end

function DroidLink:reset()
	self.enabled = true
	self:readStartingWings()
	self:resetCommands()
	self.seq = 0
	self.hull_level = 0
	self.next_check = 0
	self.next_state = 0
	pcall(function()
		local f = cf.openFile(self.file, "w", self.path)
		if f ~= nil and f:isValid() then
			f:write("0|0|session|\n")
			f:close()
		end
	end)
end

-- the player's Ship handle, or nil
function DroidLink:playerShip()
	local ply = hv.Player
	if ply == nil or not ply:isValid() then return nil end
	local ship = mn.Ships[tostring(ply)]
	if ship ~= nil and ship:isValid() then return ship end
	return nil
end

-- the ship responsible for an object (a weapon's firing ship), or the object itself
function DroidLink:owner(obj)
	if obj == nil or not obj:isValid() then return nil end
	if obj:getBreedName() == "Weapon" then
		local parent = obj.Parent
		if parent ~= nil and parent:isValid() then return parent end
	end
	return obj
end

function DroidLink:shipType(ship)
	local name = "ship"
	pcall(function() name = ship.Class.Type.Name:lower() end)
	return name
end

function DroidLink:className(ship)
	local name = ""
	pcall(function() name = ship.Class.Name end)
	return (name:gsub("|", "/"))
end

function DroidLink:onShipDeath()
	local dead, player = hv.Ship, self:playerShip()
	if dead == nil or not dead:isValid() or player == nil then return end
	if dead == player then
		self:write("player_death", "")
		self:writeDead()
		return
	end
	local killer = self:owner(hv.Killer)
	local detail = self:shipType(dead) .. "|" .. self:className(dead)
	if killer ~= nil and killer == hv.Player then
		if dead.Team == player.Team then
			self:write("teamkill", detail)
		else
			self:write("kill", detail)
		end
	elseif dead.Team == player.Team then
		self:write("ally_down", detail)
	end
end

function DroidLink:onPainFlash()
	if hv.Pain_Type == 1 then
		self:write("hit_hull", "")
	else
		self:write("hit_shield", "")
	end
end

local function percent(left, max)
	if left == nil or max == nil or max <= 0 then return -1 end
	return math.floor(left / max * 100 + 0.5)
end

-- your ship's condition, answered by the droid when you ask "are you ok?", "are we clear?"...
function DroidLink:writeState(ship, now)
	local lines = {string.format("time=%.1f", now), "alive=1"}
	local function add(key, fn)
		local ok, value = pcall(fn)
		if ok and value ~= nil then lines[#lines + 1] = key .. "=" .. tostring(value) end
	end
	add("hull", function() return percent(ship.HitpointsLeft, ship.HitpointsMax) end)
	add("shields", function() return percent(ship.Shields.CombinedLeft, ship.Shields.CombinedMax) end)
	add("energy", function() return percent(ship.WeaponEnergyLeft, ship.WeaponEnergyMax) end)
	add("afterburner", function() return percent(ship.AfterburnerFuelLeft, ship.AfterburnerFuelMax) end)
	add("target", function()
		local t = ship.Target
		if t == nil or not t:isValid() or t:getBreedName() ~= "Ship" then return nil end
		local ts = mn.Ships[tostring(t)]
		if ts == nil or not ts:isValid() then return nil end
		return percent(ts.HitpointsLeft, ts.HitpointsMax) .. "|" .. self:className(ts)
	end)
	add("hostiles", function()
		-- multiplayer (fair play): only hostiles your radar shows; checkVisibility: 0 = not visible
		local radar_only = ba.MultiplayerMode
		local n = 0
		for i = 1, #mn.Ships do
			local s = mn.Ships[i]
			if s:isValid() and not s:isDying() and s.Team:attacks(ship.Team)
					and (not radar_only or s:checkVisibility(ship) > 0) then
				n = n + 1
			end
		end
		return n
	end)
	add("wings", function() return self:wingMenu(ship) end)   -- for "Alpha wing, cover me"
	pcall(function()
		local f = cf.openFile(self.state_file, "w", self.path)
		if f ~= nil and f:isValid() then
			f:write(table.concat(lines, "\n") .. "\n")
			f:close()
		end
	end)
end

function DroidLink:writeDead()
	pcall(function()
		local f = cf.openFile(self.state_file, "w", self.path)
		if f ~= nil and f:isValid() then
			f:write("alive=0\n")
			f:close()
		end
	end)
end

-- check the hull a few times per second, report each mark once (it rises again after repairs)
function DroidLink:onSimulation()
	pcall(function() self:commandsTick() end)
	local now = 0
	pcall(function() now = mn.getMissionTime() or 0 end)
	if self.enabled and now >= self.next_state then
		self.next_state = now + 1.0
		local ship = self:playerShip()
		if ship ~= nil then self:writeState(ship, now) end
	end
	if now < self.next_check then return end
	self.next_check = now + 0.25
	local ship = self:playerShip()
	if ship == nil or ship.HitpointsMax == nil or ship.HitpointsMax <= 0 then return end
	local frac = ship.HitpointsLeft / ship.HitpointsMax
	local level = 0
	for i, mark in ipairs(self.hull_marks) do
		if frac < mark then level = i end
	end
	if level > self.hull_level then
		self:write(level >= 2 and "hull_critical" or "hull_low", string.format("%d", math.floor(frac * 100)))
	end
	self.hull_level = level
end

function DroidLink:onCollision()
	local player = hv.Player
	if player == nil then return end
	if hv.Self == player or hv.Object == player then
		self:write("collision", "")
	end
end

function DroidLink:onSubsystemDestroyed()
	local player = self:playerShip()
	if player ~= nil and hv.Ship == player then
		local name = ""
		pcall(function() name = hv.Subsystem.Name end)
		self:write("subsystem_lost", name)
	end
end

-- every handler runs protected: an error here must never interrupt the game
local function safe(fn)
	return function()
		pcall(fn, DroidLink)
	end
end

if not IS_STANDALONE then
	engine.addHook("On Gameplay Start", safe(function(self) self:reset(); self:write("mission_start", "") end))
	engine.addHook("On Mission About To End", safe(function(self) self:write("mission_end", ""); self:writeDead() end))
	engine.addHook("On Ship Death", safe(DroidLink.onShipDeath), {State="GS_STATE_GAME_PLAY"})
	engine.addHook("On Pain Flash", safe(DroidLink.onPainFlash), {State="GS_STATE_GAME_PLAY"})
	engine.addHook("On Simulation", safe(DroidLink.onSimulation))
	engine.addHook("On Ship Collision", safe(DroidLink.onCollision), {State="GS_STATE_GAME_PLAY"})
	engine.addHook("On Subsystem Destroyed", safe(DroidLink.onSubsystemDestroyed), {State="GS_STATE_GAME_PLAY"})
end
