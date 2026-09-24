"""Overhead comparison: how much latency does each algorithm/storage
combination add, and how does FastAPI vs Go compare. A different question
from tests/ (exact-count correctness) - here traffic should mostly NOT get
throttled, so an unexpected 429 signals the limit is misconfigured for
this load, not a finding.

Each virtual user gets its own X-Client-Id, generated once in on_start, so
most traffic stays under its own limit - and gives Redis realistic key
cardinality (many distinct keys, not one hot key), which matters since
every Lua script here operates per-key.
"""
import uuid

from locust import HttpUser, between, task

ENDPOINTS = [
    "/api/token-bucket/action",
    "/api/leaky-bucket/action",
    "/api/fixed-window/action",
    "/api/sliding-window-log/action",
    "/api/sliding-window-counter/action",
]


class RateLimiterUser(HttpUser):
    wait_time = between(0.05, 0.2)

    def on_start(self):
        self.headers = {"X-Client-Id": f"loadtest-{uuid.uuid4().hex[:12]}"}

    def _hit(self, path: str):
        with self.client.post(path, headers=self.headers, name=path, catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 429:
                resp.failure("unexpected 429 - limit too low for this load test's traffic rate")
            else:
                resp.failure(f"unexpected status {resp.status_code}")

    @task(1)
    def token_bucket(self):
        self._hit(ENDPOINTS[0])

    @task(1)
    def leaky_bucket(self):
        self._hit(ENDPOINTS[1])

    @task(1)
    def fixed_window(self):
        self._hit(ENDPOINTS[2])

    @task(1)
    def sliding_window_log(self):
        self._hit(ENDPOINTS[3])

    @task(1)
    def sliding_window_counter(self):
        self._hit(ENDPOINTS[4])
