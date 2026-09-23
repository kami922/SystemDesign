"""Seed a backend with N links and write a weighted code pool both Locust
and k6 read from - so the two tools hit the identical working set instead
of each computing their own popularity skew independently.
"""
import argparse
import json
import random
import sys

import requests

from traffic_profile import zipf_weights


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--zipf-s", type=float, default=1.2)
    parser.add_argument("--output", default="seeded_codes.json")
    args = parser.parse_args()

    codes = []
    session = requests.Session()
    for i in range(args.count):
        resp = session.post(
            f"{args.base_url}/api/links",
            json={"long_url": f"https://example.com/resource/{i}"},
            timeout=10,
        )
        resp.raise_for_status()
        codes.append(resp.json()["short_code"])
        if (i + 1) % 100 == 0:
            print(f"seeded {i + 1}/{args.count}", file=sys.stderr)

    # Shuffle so "most popular" isn't just "created first" - popularity
    # rank should be arbitrary with respect to creation order.
    random.shuffle(codes)

    weights = zipf_weights(len(codes), args.zipf_s)

    with open(args.output, "w") as f:
        json.dump({"base_url": args.base_url, "zipf_s": args.zipf_s, "codes": codes, "weights": weights}, f)

    print(f"wrote {len(codes)} codes to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
