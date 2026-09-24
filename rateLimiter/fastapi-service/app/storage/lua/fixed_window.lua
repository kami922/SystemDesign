-- KEYS[1] = window key
-- ARGV[1] = ttl_seconds
--
-- INCR then EXPIRE-if-first in one EVAL. Two separate calls would leave a
-- gap: a crash/preemption between them leaves a key with no TTL at all,
-- accumulating forever.
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], math.ceil(tonumber(ARGV[1])))
end
return count
