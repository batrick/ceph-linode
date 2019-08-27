local mds = {}
local min_timestamp = math.maxinteger
local max_timestamp = 0
for line in io.lines() do
    local timestamp, rank, data = line:match "(%d+)\t(%d+)\t(%d+)"
    rank = math.tointeger(rank)
    if not rank then io.stderr:write(line, "\n") os.exit(1) end
    timestamp = math.tointeger(timestamp)
    mds[rank] = mds[rank] or {timestamps={},last=math.maxinteger-1,first=timestamp}
    local last = mds[rank].last
    local timestamps = mds[rank].timestamps
    timestamps[timestamp] = data
    for i = last+1, timestamp-1 do
        local step = (data-timestamps[last])//(timestamp-last)
        timestamps[i] = timestamps[i-1]+step
    end
    mds[rank].last = timestamp
    min_timestamp = math.min(min_timestamp, timestamp)
    max_timestamp = math.max(max_timestamp, timestamp)
end

for rank, mds in pairs(mds) do
    for i = min_timestamp, mds.first do
        mds.timestamps[i] = 0
    end
    for i = mds.last, max_timestamp do
        mds.timestamps[i] = 0
    end
end

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
    for _, rank in ipairs(ranks) do
        io.write('\t', mds[rank].timestamps[i])
    end
    io.write '\n'
end
