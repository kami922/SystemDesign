-- KEYS[1] = current window key, KEYS[2] = previous window key
-- ARGV[1] = weight, ARGV[2] = limit, ARGV[3] = ttl_seconds
--
-- Read both counters, compute the weighted estimate, and conditionally
-- increment - all in one EVAL. A separate get-both-then-increment from
-- the application side would reintroduce the exact race this project
-- exists to prevent: two concurrent requests both read estimate < limit,
-- both increment, both admit past the limit.
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local previous = tonumber(redis.call('GET', KEYS[2]) or '0')
local weight = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local estimate = previous * weight + current

local allowed = 0
if estimate < limit then
  current = redis.call('INCR', KEYS[1])
  if current == 1 then
    redis.call('EXPIRE', KEYS[1], math.ceil(tonumber(ARGV[3])))
  end
  allowed = 1
  estimate = previous * weight + current
end

return {allowed, tostring(estimate)}
