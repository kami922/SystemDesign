-- KEYS[1] = zset key (member = unique per-request string, score = timestamp ms)
-- ARGV[1] = now_ms, ARGV[2] = window_ms, ARGV[3] = limit, ARGV[4] = unique member
--
-- Evict expired entries, count what's left, and conditionally add - all in
-- one EVAL. A separate evict-then-count-then-add would let two concurrent
-- requests both see room under the limit and both add, exceeding it.
-- Members must be unique per request (not just the timestamp): two
-- requests landing in the same millisecond would otherwise collide in the
-- ZSET and only count once.
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, ARGV[1] - ARGV[2])
local count = redis.call('ZCARD', KEYS[1])
local allowed = 0
if count < tonumber(ARGV[3]) then
  redis.call('ZADD', KEYS[1], ARGV[1], ARGV[4])
  redis.call('PEXPIRE', KEYS[1], ARGV[2])
  allowed = 1
  count = count + 1
end
return {allowed, count}
