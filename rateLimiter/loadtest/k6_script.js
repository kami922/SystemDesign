// Mirrors locustfile.py's even mix across the five algorithm endpoints,
// for the same overhead-comparison question (not correctness - see
// tests/ for that). Each VU gets a stable client id from __VU so most
// traffic stays under its own limit.
import http from 'k6/http';
import { check } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8101';

const ENDPOINTS = [
  '/api/token-bucket/action',
  '/api/leaky-bucket/action',
  '/api/fixed-window/action',
  '/api/sliding-window-log/action',
  '/api/sliding-window-counter/action',
];

export default function () {
  const clientId = `loadtest-vu${__VU}`;
  const path = ENDPOINTS[Math.floor(Math.random() * ENDPOINTS.length)];

  const res = http.post(`${BASE_URL}${path}`, null, {
    headers: { 'X-Client-Id': clientId },
    tags: { name: path },
  });

  check(res, {
    'not rate limited (200)': (r) => r.status === 200,
  });
}
