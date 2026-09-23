// Mirrors locustfile.py's traffic mix (85% redirect / 10% create / 3% alias
// / 2% stats) so Locust and k6 can be compared on equal footing. Reads the
// same seeded_codes.json Locust uses, so both tools draw from the
// identical Zipf-weighted working set.
import http from 'k6/http';
import { check } from 'k6';
import { SharedArray } from 'k6/data';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';
const SEEDED_CODES_PATH = __ENV.SEEDED_CODES_PATH || './seeded_codes.json';

const seed = new SharedArray('seeded links', function () {
  return [JSON.parse(open(SEEDED_CODES_PATH))];
})[0];

const CODES = seed.codes;
const WEIGHTS = seed.weights;

// Cumulative weights precomputed once so each pick is an O(log n) binary
// search instead of resampling the distribution per request.
const CUMULATIVE = (() => {
  let acc = 0;
  return WEIGHTS.map((w) => (acc += w));
})();

function pickWeightedCode() {
  const r = Math.random() * CUMULATIVE[CUMULATIVE.length - 1];
  let lo = 0;
  let hi = CUMULATIVE.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (CUMULATIVE[mid] < r) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }
  return CODES[lo];
}

function randomAlias() {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let s = '';
  for (let i = 0; i < 10; i++) {
    s += chars[Math.floor(Math.random() * chars.length)];
  }
  return s;
}

export const options = {
  thresholds: {
    // "SLO as code" - k6 fails the run if the redirect hot path misses
    // this. Locust has no built-in equivalent.
    'http_req_duration{name:redirect}': ['p(95)<200'],
  },
};

export default function () {
  const roll = Math.random() * 100;

  if (roll < 85) {
    const code = pickWeightedCode();
    const res = http.get(`${BASE_URL}/${code}`, {
      redirects: 0,
      tags: { name: 'redirect' },
    });
    check(res, { 'redirect is 302': (r) => r.status === 302 });
  } else if (roll < 95) {
    const res = http.post(
      `${BASE_URL}/api/links`,
      JSON.stringify({ long_url: `https://example.com/created/${Math.floor(Math.random() * 1e7)}` }),
      { headers: { 'Content-Type': 'application/json' }, tags: { name: 'create_link' } }
    );
    check(res, { 'create is 201': (r) => r.status === 201 });
  } else if (roll < 98) {
    const res = http.post(
      `${BASE_URL}/api/links`,
      JSON.stringify({
        long_url: `https://example.com/aliased/${Math.floor(Math.random() * 1e7)}`,
        custom_alias: randomAlias(),
      }),
      { headers: { 'Content-Type': 'application/json' }, tags: { name: 'custom_alias' } }
    );
    check(res, { 'alias create is 201': (r) => r.status === 201 });
  } else {
    const code = CODES[Math.floor(Math.random() * CODES.length)];
    const res = http.get(`${BASE_URL}/api/links/${code}/stats`, { tags: { name: 'stats' } });
    check(res, { 'stats is 200': (r) => r.status === 200 });
  }
}
