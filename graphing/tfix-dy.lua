local mds = {}
local min_timestamp = math.maxinteger
local max_timestamp = 0
for line in io.lines() do
    local timestamp, rank, data = line:match "^(%d+)\t(%d+)\t([%d.]+)$"
    rank = math.tointeger(rank)
    timestamp = math.tointeger(timestamp)
    data = tonumber(data)
    mds[rank] = mds[rank] or {timestamps={},data={},last=math.maxinteger-1,first=timestamp}
    local first = mds[rank].first
    local last = mds[rank].last
    local timestamps = mds[rank].timestamps
    if first == timestamp then
        timestamps[timestamp] = 0
    else
        timestamps[timestamp] = data-mds[rank].data[last]
    end
    for i = last+1, timestamp-1 do
        timestamps[i] = timestamps[i-1] -- just use last one!
    end
    mds[rank].data[timestamp] = data
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
