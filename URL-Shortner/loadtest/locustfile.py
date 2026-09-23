"""Locust traffic mix for the URL shortener: read-heavy, Zipf-skewed
redirects dominate, with a smaller share of link/alias creation and
stats lookups. Targets whichever backend is passed via --host, so the
same suite can hit either the FastAPI or the Go stack.
"""
import json
import os
import random
import string

from locust import HttpUser, between, events, task

SEEDED_CODES_PATH = os.environ.get("SEEDED_CODES_PATH", "seeded_codes.json")

# Loaded lazily (on test start, not on import) so the web UI can boot even
# before seed_data.py has been run - it only errors once you actually try
# to start a test without seeded data.
_CODES: list[str] = []
_WEIGHTS: list[float] = []


@events.test_start.add_listener
def _load_seeded_codes(environment, **kwargs):
    global _CODES, _WEIGHTS
    with open(SEEDED_CODES_PATH) as f:
        seed = json.load(f)
    _CODES = seed["codes"]
    _WEIGHTS = seed["weights"]


def _random_alias() -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=10))


class UrlShortenerUser(HttpUser):
    wait_time = between(0.01, 0.1)

    @task(85)
    def redirect_hot_code(self):
        code = random.choices(_CODES, weights=_WEIGHTS, k=1)[0]
        with self.client.get(
            f"/{code}",
            name="/[code] (redirect)",
            allow_redirects=False,
            catch_response=True,
        ) as resp:
            if resp.status_code == 302:
                resp.success()
            else:
                resp.failure(f"unexpected status {resp.status_code}")

    @task(10)
    def create_link(self):
        self.client.post(
            "/api/links",
            json={"long_url": f"https://example.com/created/{random.randint(0, 10_000_000)}"},
            name="/api/links (create)",
        )

    @task(3)
    def create_custom_alias(self):
        self.client.post(
            "/api/links",
            json={
                "long_url": f"https://example.com/aliased/{random.randint(0, 10_000_000)}",
                "custom_alias": _random_alias(),
            },
            name="/api/links (custom alias)",
        )

    @task(2)
    def stats_lookup(self):
        code = random.choice(_CODES)
        self.client.get(f"/api/links/{code}/stats", name="/api/links/[code]/stats")
