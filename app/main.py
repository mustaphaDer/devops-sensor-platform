"""Sensor ingest API: machines send readings, the API flags anomalies.

Exposes Prometheus metrics on /metrics so the service can be watched in
Grafana, and /healthz + /readyz for Kubernetes probes.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from statistics import fmean, pstdev

from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from pydantic import BaseModel, Field

WINDOW = int(os.getenv("WINDOW_SIZE", "200"))
Z_THRESHOLD = float(os.getenv("Z_THRESHOLD", "3.0"))
VERSION = os.getenv("APP_VERSION", "dev")

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram(
    "http_request_duration_seconds",
    "Request latency",
    ["route"],
    buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1),
)
READINGS = Counter("sensor_readings_total", "Accepted readings", ["machine"])
ANOMALIES = Counter("sensor_anomalies_total", "Readings flagged as anomalous", ["machine"])
MACHINES = Gauge("sensor_machines_tracked", "Machines with at least one reading")

app = FastAPI(title="sensor-api", version=VERSION)
_windows: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=WINDOW))


class Reading(BaseModel):
    machine_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(default="C", max_length=8)


@app.middleware("http")
async def observe(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    path = route.path if route is not None else "unmatched"
    if path != "/metrics":
        LATENCY.labels(path).observe(time.perf_counter() - start)
        REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    return response


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    return {"status": "ready", "version": VERSION}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/readings", status_code=201)
async def ingest(reading: Reading):
    window = _windows[reading.machine_id]
    z = None
    anomaly = False
    if len(window) >= 20:
        mean, std = fmean(window), pstdev(window)
        if std > 0:
            z = (reading.value - mean) / std
            anomaly = abs(z) > Z_THRESHOLD
    window.append(reading.value)
    MACHINES.set(len(_windows))
    READINGS.labels(reading.machine_id).inc()
    if anomaly:
        ANOMALIES.labels(reading.machine_id).inc()
    return {"machine_id": reading.machine_id, "anomaly": anomaly, "z_score": None if z is None else round(z, 3)}


@app.get("/machines/{machine_id}/stats")
async def stats(machine_id: str):
    window = _windows.get(machine_id)
    if not window:
        raise HTTPException(status_code=404, detail="unknown machine")
    return {
        "machine_id": machine_id,
        "count": len(window),
        "mean": round(fmean(window), 3),
        "std": round(pstdev(window), 3),
        "min": min(window),
        "max": max(window),
    }
