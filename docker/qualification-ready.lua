-- Live-qualification witness: prove Lua executes in the effective run directory.
local file = assert(io.open("lua-qualification.txt", "w"))
file:write("executed\n")
file:close()
gcs:send_text(6, "qualification: Lua executed")
return
