local mds = {}
local min_timestamp = math.maxinteger
local max_timestamp = 0

local null = setmetatable({}, {__index = function(t,k) return 0 end})
local mt = {__index = function(t, k) return null end}
for line in io.lines() do
    local timestamp, rank, data = line:match "(%d+)\t(%d+)%s*(.*)"
    rank = math.tointeger(rank)
    if not rank then io.stderr:write(line, "\n") os.exit(1) end
    timestamp = math.tointeger(timestamp)
    --mds[rank] = mds[rank] or {timestamps=setmetatable({}, mt),last=math.maxinteger-1,first=timestamp}
    if mds[rank] == nil then
        mds[rank] = {
            timestamps=setmetatable({}, mt),
            last=math.maxinteger-1,
            first=timestamp,
            n=nil,
        }
    end
    local rank = mds[rank]
    local last = rank.last
    local timestamps = rank.timestamps
    local datas = {}
    timestamps[timestamp] = datas
    --io.stderr:write(tostring(timestamp), " ", data, '\n')
    for d in data:gmatch("(%d+)%s*") do
        local d = tonumber(d)
        local n = #datas+1
        datas[n] = d
        --io.stderr:write('\t', tostring(n), "=", tostring(d), '\n')
        if last+1 <= timestamp-1 then
            local step = (d-timestamps[last][n])//(timestamp-last)
            for i = last+1, timestamp-1 do
                if rawget(timestamps, i) == nil then
                    timestamps[i] = {}
                end
                --io.stderr:write("last=", tostring(last), " i=", tostring(i), '\n')
                --io.stderr:write(tostring(timestamps[i]), " ", tostring(timestamps[i-1]), '\n')
                --io.stderr:write(tostring(timestamps[i][n]), " ", tostring(timestamps[i-1][n]), '\n')
                timestamps[i][n] = timestamps[i-1][n]+step
            end
        end
    end
    if rank.n == nil then
        rank.n = #datas
    else
        assert(#datas == rank.n)
    end
    rank.last = timestamp
    min_timestamp = math.min(min_timestamp, timestamp)
    max_timestamp = math.max(max_timestamp, timestamp)
end

--[[
local mt = {__index = function() return 0 end}
for rank, mds in pairs(mds) do
    for i = min_timestamp, mds.first do
        mds.timestamps[i] = setmetatable({}, mt)
    end
    for i = mds.last, max_timestamp do
        mds.timestamps[i] = setmetatable({}, mt)
    end
end
--]]

local ranks = {}
for rank, mds in pairs(mds) do
    ranks[#ranks+1] = rank
end
table.sort(ranks)

io.write 'timestamp'
for _, rank in ipairs(ranks) do
    io.write('\t', rank)
end
io.write '\n'
for i = min_timestamp, max_timestamp do
    io.write(i-min_timestamp)
    for id, rank in ipairs(ranks) do
        io.write('\t', id)
        local rank = mds[rank]
        local timestamps = rank.timestamps[i]
        for n = 1, rank.n do
            local d = timestamps[n]
            --io.stderr:write(i, '\t', _, '\t', d, '\n')
            io.write('\t', d)
        end
    end
    io.write '\n'
end
