"""
Read raw results from k6 or JMeter and turn them into ONE common shape,
so every chart works the same no matter which tool ran the test.

Common shape
------------
requests  (one row per HTTP request)
    time            when the request finished (datetime)
    elapsed_ms      total response time
    waiting_ms      server processing / time to first byte (may be empty)
    connect_ms      connection + TLS setup (may be empty)
    label           test case / endpoint name
    status          HTTP status code as text ("200", "202", "500", ...)
    success         True / False
    bytes_sent      (may be empty)
    bytes_received  (may be empty)

users  (active virtual users / threads over time)
    time, users
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd


@dataclass
class TestData:
    tool: str
    requests: pd.DataFrame
    users: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["time", "users"]))
    thresholds: dict = field(default_factory=dict)  # e.g. {"http_req_duration": ["p(95)<5000"]}


# ---------------------------------------------------------------- k6

_K6_REQUEST_METRICS = {
    "http_req_duration": "elapsed_ms",
    "http_req_waiting": "waiting_ms",
    "http_req_connecting": "_tcp_ms",
    "http_req_tls_handshaking": "_tls_ms",
    "http_req_failed": "_failed",
}


def load_k6_json(path: str | Path) -> TestData:
    """k6 raw output created with:  k6 run --out json=results.json script.js"""
    points, vus, thresholds = [], [], {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("type") == "Metric":
                if obj["data"].get("thresholds"):
                    thresholds[obj["metric"]] = obj["data"]["thresholds"]
                continue
            if obj.get("type") != "Point":
                continue
            metric = obj["metric"]
            data = obj["data"]
            if metric == "vus":
                vus.append({"time": data["time"], "users": data["value"]})
            elif metric in _K6_REQUEST_METRICS:
                tags = data.get("tags") or {}
                points.append({
                    "time": data["time"],
                    "metric": _K6_REQUEST_METRICS[metric],
                    "value": data["value"],
                    "label": tags.get("caseType") or tags.get("name") or tags.get("url") or "request",
                    "status": tags.get("status", ""),
                    "url": tags.get("url", ""),
                })

    if not points:
        raise ValueError("No HTTP request data found. Was the test run with: k6 run --out json=results.json ?")

    raw = pd.DataFrame(points)
    # k6 writes every timing of one request with the same timestamp + tags -> pivot back into one row
    req = raw.pivot_table(index=["time", "label", "status", "url"], columns="metric",
                          values="value", aggfunc="first").reset_index()
    req.columns.name = None
    req["time"] = pd.to_datetime(req["time"], format="ISO8601")
    req["connect_ms"] = req.get("_tcp_ms", 0) + req.get("_tls_ms", 0)
    req["success"] = req["_failed"].fillna(0) == 0 if "_failed" in req else True
    req["bytes_sent"] = pd.NA
    req["bytes_received"] = pd.NA
    req = _finish(req)

    users = pd.DataFrame(vus)
    if not users.empty:
        users["time"] = pd.to_datetime(users["time"], format="ISO8601")
    return TestData(tool="k6", requests=req, users=users, thresholds=thresholds)


# ---------------------------------------------------------------- JMeter

def load_jmeter_jtl(path: str | Path) -> TestData:
    """JMeter results file (.jtl / .csv) with the default CSV columns."""
    df = pd.read_csv(path, low_memory=False)
    needed = {"timeStamp", "elapsed", "label", "responseCode", "success"}
    missing = needed - set(df.columns)
    if missing:
        raise ValueError(f"JMeter file is missing columns: {', '.join(sorted(missing))}")

    start = pd.to_datetime(df["timeStamp"], unit="ms", utc=True)
    req = pd.DataFrame({
        "time": start + pd.to_timedelta(df["elapsed"], unit="ms"),  # finish time, same as k6
        "elapsed_ms": df["elapsed"].astype(float),
        # JMeter "Latency" includes connect time; keep only the server wait so it matches k6
        "waiting_ms": (df.get("Latency", pd.Series(pd.NA, index=df.index)).astype("Float64")
                       - df.get("Connect", pd.Series(0, index=df.index)).astype("Float64")),
        "connect_ms": df.get("Connect", pd.Series(pd.NA, index=df.index)).astype("Float64"),
        "label": df["label"].astype(str),
        "status": df["responseCode"].astype(str),
        "success": df["success"].astype(str).str.lower() == "true",
        "bytes_sent": df.get("sentBytes", pd.Series(pd.NA, index=df.index)),
        "bytes_received": df.get("bytes", pd.Series(pd.NA, index=df.index)),
    })
    req = _finish(req)

    users = pd.DataFrame()
    if "allThreads" in df.columns:
        users = pd.DataFrame({"time": start, "users": df["allThreads"]}).sort_values("time")
    return TestData(tool="jmeter", requests=req, users=users)


# ---------------------------------------------------------------- auto-detect

def load_results(path: str | Path) -> TestData:
    """Pick the right loader by looking at the file."""
    path = Path(path)
    with open(path, encoding="utf-8", errors="ignore") as f:
        first = f.readline().strip()
    if first.startswith("{"):
        return load_k6_json(path)
    if "timeStamp" in first and "elapsed" in first:
        return load_jmeter_jtl(path)
    raise ValueError(f"Don't recognise {path.name}. Expected k6 --out json output or a JMeter .jtl/.csv file.")


def _finish(req: pd.DataFrame) -> pd.DataFrame:
    cols = ["time", "elapsed_ms", "waiting_ms", "connect_ms", "label", "status",
            "success", "bytes_sent", "bytes_received"]
    for c in cols:
        if c not in req:
            req[c] = pd.NA
    return req[cols].sort_values("time").reset_index(drop=True)