"""Closed-loop load generator: N concurrent clients send readings for D seconds.

Prints throughput and latency percentiles as JSON, so runs can be compared
(e.g. 1 vs 4 uvicorn workers, or different concurrency levels).

Usage: python loadtest/load.py --url http://localhost:8000 --concurrency 32 --duration 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time

import httpx


def pct(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return float("nan")
    k = min(len(sorted_values) - 1, round(p / 100 * (len(sorted_values) - 1)))
    return sorted_values[k]


async def worker(client: httpx.AsyncClient, url: str, stop: float, wid: int, lat: list, errors: list):
    rng = random.Random(wid)
    machine = f"machine-{wid % 50}"
    while time.perf_counter() < stop:
        value = 60 + rng.gauss(0, 2) if rng.random() > 0.01 else 120.0
        t0 = time.perf_counter()
        try:
            r = await client.post(f"{url}/readings", json={"machine_id": machine, "value": value})
            if r.status_code != 201:
                errors.append(r.status_code)
        except httpx.HTTPError as exc:
            errors.append(type(exc).__name__)
        lat.append(time.perf_counter() - t0)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--concurrency", type=int, default=32)
    ap.add_argument("--duration", type=float, default=20)
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    lat: list[float] = []
    errors: list = []
    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)
    async with httpx.AsyncClient(limits=limits, timeout=10) as client:
        await client.get(f"{args.url}/healthz")
        start = time.perf_counter()
        stop = start + args.duration
        await asyncio.gather(*(worker(client, args.url, stop, i, lat, errors) for i in range(args.concurrency)))
        elapsed = time.perf_counter() - start

    lat.sort()
    print(json.dumps({
        "label": args.label,
        "concurrency": args.concurrency,
        "duration_s": round(elapsed, 1),
        "requests": len(lat),
        "errors": len(errors),
        "throughput_rps": round(len(lat) / elapsed, 1),
        "p50_ms": round(pct(lat, 50) * 1000, 2),
        "p95_ms": round(pct(lat, 95) * 1000, 2),
        "p99_ms": round(pct(lat, 99) * 1000, 2),
    }))


if __name__ == "__main__":
    asyncio.run(main())
