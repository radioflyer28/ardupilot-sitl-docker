-- Load a staged QGC WPL 110 mission file into ArduPilot.
--
-- The Docker wrapper copies the selected MISSION_FILE to this fixed runtime
-- path before SITL starts.

local mission_file = "missions/mission.waypoints"

local function split_fields(line)
    local fields = {}
    for field in string.gmatch(line, "%S+") do
        fields[#fields + 1] = field
    end
    return fields
end

local function number_field(fields, index, line_number)
    local value = tonumber(fields[index])
    assert(value ~= nil, string.format("%s:%u invalid numeric field %u", mission_file, line_number, index))
    return value
end

local function read_mission()
    local file = assert(io.open(mission_file), "Could not open: " .. mission_file)

    local header = file:read("l")
    assert(header ~= nil and string.find(header, "QGC WPL 110") == 1, mission_file .. ": incorrect format")
    assert(mission:clear(), "Could not clear current mission")

    local index = 0
    local line_number = 1

    while true do
        local line = file:read("l")
        if line == nil then
            break
        end

        line_number = line_number + 1
        local fields = split_fields(line)

        if #fields > 0 then
            assert(#fields >= 12, string.format("%s:%u expected 12 fields", mission_file, line_number))

            local seq = number_field(fields, 1, line_number)
            local current = number_field(fields, 2, line_number)
            local frame = number_field(fields, 3, line_number)
            local cmd = number_field(fields, 4, line_number)
            local p1 = number_field(fields, 5, line_number)
            local p2 = number_field(fields, 6, line_number)
            local p3 = number_field(fields, 7, line_number)
            local p4 = number_field(fields, 8, line_number)
            local x = number_field(fields, 9, line_number)
            local y = number_field(fields, 10, line_number)
            local z = number_field(fields, 11, line_number)

            assert(seq == index, string.format("%s:%u expected seq %u, got %u", mission_file, line_number, index, seq))

            local item = mavlink_mission_item_int_t()
            item:seq(seq)
            item:current(current)
            item:frame(frame)
            item:command(cmd)
            item:param1(p1)
            item:param2(p2)
            item:param3(p3)
            item:param4(p4)

            if mission:cmd_has_location(cmd) then
                item:x(math.floor(x * 1e7))
                item:y(math.floor(y * 1e7))
            else
                item:x(math.floor(x))
                item:y(math.floor(y))
            end
            item:z(z)

            if not mission:set_item(index, item) then
                mission:clear()
                error(string.format("%s:%u failed to set mission item %u", mission_file, line_number, index))
            end

            index = index + 1
        end
    end

    file:close()
    gcs:send_text(6, string.format("Loaded %u mission items from %s", index, mission_file))
end

local function update()
    read_mission()
    return
end

return update, 5000
