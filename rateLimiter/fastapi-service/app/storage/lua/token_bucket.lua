-- KEYS[1] = state key (hash: level, ts)
-- ARGV[1] = capacity, ARGV[2] = refill_rate (units/sec), ARGV[3] = now, ARGV[4] = cost
--
-- Refill + compare + decrement + write, all in one EVAL. This is the
-- whole point: two concurrent requests calling this script are never
-- interleaved by Redis (single-threaded command execution), so there is
-- no window where both can read the same pre-refill level and both
-- succeed past capacity - the exact race the in-memory store's
-- asyncio.Lock prevents at a different scale (see storage/memory.py).
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])

local state = redis.call('HMGET', KEYS[1], 'level', 'ts')
local level = tonumber(state[1])
local ts = tonumber(state[2])
if level == nil then
  level = capacity
  ts = now
end

level = math.min(capacity, level + math.max(0, now - ts) * rate)

local allowed = 0
local retry_after = 0
if level >= cost then
  level = level - cost
  allowed = 1
else
  retry_after = (cost - level) / rate
end

redis.call('HMSET', KEYS[1], 'level', level, 'ts', now)
-- Expire well after the bucket would refill to capacity anyway, so Redis
-- doesn't accumulate keys for clients who never come back.
redis.call('PEXPIRE', KEYS[1], math.ceil((capacity / rate) * 1000) + 1000)

return {allowed, tostring(level), tostring(retry_after)}
