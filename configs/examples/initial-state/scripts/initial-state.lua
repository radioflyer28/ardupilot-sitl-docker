-- Example SITL initial-state script.
--
-- Requires:
--   SCR_ENABLE 1
--   AHRS_EKF_TYPE 10
--
-- Copy this file into SITL_CONFIG_DIR/scripts/, or set LUA_SCRIPT to this
-- file. Edit the state table below for the scenario you want to start from.

local state = {
    enabled = true,

    -- "arm" applies once after the vehicle is armed.
    -- "start" applies once as soon as the AHRS origin is available.
    trigger = "arm",

    -- SITL instance passed to sim:set_pose. Use 0 for the first vehicle.
    instance = 0,

    -- Position is relative to the SITL home/origin in meters.
    -- Down is NED-style: negative values place the aircraft above home.
    position_ned_m = {
        north = 0,
        east = 0,
        down = -20,
    },

    -- Roll, pitch, and yaw are degrees.
    attitude_deg = {
        roll = 0,
        pitch = 0,
        yaw = 0,
    },

    -- Body-frame velocity in meters/second.
    -- x is forward, y is right, z is down.
    velocity_bf_mps = {
        x = 0,
        y = 0,
        z = 0,
    },

    -- Body rates in degrees/second.
    rates_dps = {
        x = 0,
        y = 0,
        z = 0,
    },

    -- Optional numeric vehicle mode. Mode IDs are vehicle-specific.
    -- This example defaults to Copter LOITER. Use nil to keep current mode.
    -- Examples: Copter GUIDED=4, Copter LOITER=5, Plane CRUISE=7.
    mode = 5,
}

local applied = false
local origin_wait_reported = false
local invalid_trigger_reported = false

local function value(tbl, key, default_value)
    if tbl ~= nil and tbl[key] ~= nil then
        return tbl[key]
    end
    return default_value
end

local function make_vector(tbl, scale)
    local vec = Vector3f()
    vec:x(value(tbl, "x", 0) * scale)
    vec:y(value(tbl, "y", 0) * scale)
    vec:z(value(tbl, "z", 0) * scale)
    return vec
end

local function make_quaternion(attitude)
    local quat = Quaternion()
    quat:from_euler(
        math.rad(value(attitude, "roll", 0)),
        math.rad(value(attitude, "pitch", 0)),
        math.rad(value(attitude, "yaw", 0))
    )
    return quat
end

local function make_location(position)
    local loc = ahrs:get_origin()
    if loc == nil then
        if not origin_wait_reported then
            gcs:send_text(6, "initial-state: waiting for AHRS origin")
            origin_wait_reported = true
        end
        return nil
    end

    loc:offset(value(position, "north", 0), value(position, "east", 0))
    loc:alt(loc:alt() - value(position, "down", 0) * 100)
    return loc
end

local function trigger_active()
    if state.trigger == "start" then
        return true
    end

    if state.trigger == "arm" then
        return arming:is_armed()
    end

    if not invalid_trigger_reported then
        gcs:send_text(3, "initial-state: trigger must be arm or start")
        invalid_trigger_reported = true
    end
    return false
end

local function apply_state()
    local loc = make_location(state.position_ned_m)
    if loc == nil then
        return false
    end

    local quat = make_quaternion(state.attitude_deg)
    local velocity = make_vector(state.velocity_bf_mps, 1)
    local gyro = make_vector(state.rates_dps, math.pi / 180)

    if not sim:set_pose(value(state, "instance", 0), loc, quat, velocity, gyro) then
        gcs:send_text(3, "initial-state: sim:set_pose failed")
        return false
    end

    if state.mode ~= nil and state.mode >= 0 then
        if not vehicle:set_mode(state.mode) then
            gcs:send_text(4, "initial-state: vehicle:set_mode failed")
        end
    end

    gcs:send_text(6, "initial-state: applied")
    return true
end

local function loop()
    if not state.enabled or applied then
        return loop, 1000
    end

    if trigger_active() then
        applied = apply_state()
    end

    return loop, 100
end

gcs:send_text(6, "initial-state: loaded")
return loop, 1000
