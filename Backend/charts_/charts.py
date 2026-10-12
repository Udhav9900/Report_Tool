"""
Every chart function:
  * takes the common TestData shape (see loaders.py)
  * saves one PNG
  * returns a Chart with the key numbers ("facts") that the explanation
    box next to the graph will be written from (by a person or by the AI step)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker

from .loaders import TestData
from .theme import (SLATE, ORANGE, RED, GREEN, INK,
                    MS_FORMATTER, fmt_ms)

WIDE = (7.2, 3.0)
HALF = (3.6, 2.7)


@dataclass
class Chart:
    id: str
    title: str
    file: str
    size: str               # "wide" or "half" -> how big the grid cell in the template is
    what_it_shows: str      # one fixed sentence, same every report
    facts: dict = field(default_factory=dict)  # numbers that change every report


# ---------------------------------------------------------------- helpers

def _bucket(duration_s: float) -> str:
    """Pick a time bucket that gives roughly 30-60 bars/points on any test length."""
    for seconds, rule in [(1, "1s"), (5, "5s"), (10, "10s"), (30, "30s"), (60, "1min"),
                          (300, "5min"), (600, "10min"), (900, "15min"), (1800, "30min")]:
        if duration_s / seconds <= 60:
            return rule
    return "1h"


def _local(series: pd.Series) -> pd.Series:
    """Drop the timezone for plotting but keep the wall-clock time from the file."""
    return series.dt.tz_localize(None) if series.dt.tz is not None else series


def _log_y_if_needed(ax, values) -> bool:
    values = np.asarray(values, dtype=float)
    values = values[values > 0]
    if len(values) and values.max() / max(values.min(), 1) > 20:
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(MS_FORMATTER)
        return True
    ax.yaxis.set_major_formatter(MS_FORMATTER)
    return False


def _time_axis(ax, times: pd.Series) -> None:
    """HH:MM on the x axis (adds the date if the test ran over more than a day)."""
    span = (times.max() - times.min()).total_seconds()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b %H:%M" if span > 86400 else "%H:%M"))


def _legend_top(ax) -> None:
    """Legend in one row above the plot, so it never covers data."""
    ax.legend(fontsize=7.5, loc="lower right", bbox_to_anchor=(1, 1.0), ncol=3, borderaxespad=0.2)


def _save(fig, out: Path, name: str) -> str:
    fig.tight_layout()
    path = out / f"{name}.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def _threshold_ms(data: TestData) -> float | None:
    """Pull the p(95)<X limit out of the k6 thresholds if one was set."""
    for rule in data.thresholds.get("http_req_duration", []):
        rule = rule.replace(" ", "")
        if rule.startswith("p(95)<"):
            try:
                return float(rule.split("<")[1])
            except ValueError:
                pass
    return None


# ---------------------------------------------------------------- charts

MAX_POINTS = 40_000  # plotting more dots than this only slows things down


def response_time_timeline(data: TestData, out: Path) -> Chart:
    full = data.requests
    r = full
    if len(r) > MAX_POINTS:
        # keep every failed / slow request, sample the rest
        keep = (~r.success) | (r.elapsed_ms >= np.median(r.elapsed_ms) * 5)
        r = pd.concat([r[keep], r[~keep].sample(MAX_POINTS - int(keep.sum()), random_state=1)]).sort_values("time")
    t = _local(r.time)
    slow_cut = np.median(full.elapsed_ms) * 5  # 5x slower than a typical request
    outlier = r.elapsed_ms >= slow_cut
    failed = ~r.success
    n_outlier = int((full.elapsed_ms >= slow_cut).sum())
    n_failed = int((~full.success).sum())

    fig, ax = plt.subplots(figsize=WIDE)
    ax.scatter(t[~outlier & ~failed], r.elapsed_ms[~outlier & ~failed], s=9, color=SLATE, lw=0, label="Request", rasterized=True)
    if outlier.any():
        ax.scatter(t[outlier & ~failed], r.elapsed_ms[outlier & ~failed], s=18, color=ORANGE, lw=0, label="Unusually slow")
    if failed.any():
        ax.scatter(t[failed], r.elapsed_ms[failed], s=22, color=RED, linewidths=1.4, marker="x", label="Failed", zorder=3)
    limit = _threshold_ms(data)
    if limit:
        ax.axhline(limit, color=ORANGE, lw=1.2, ls=(0, (4, 3)))
        ax.text(t.min(), limit * 1.08, f"limit {fmt_ms(limit)}", color=ORANGE, fontsize=7.5)
    _log_y_if_needed(ax, r.elapsed_ms)
    ax.set_xlabel("Time")
    _time_axis(ax, t)
    _legend_top(ax)
    ax.set_title("Response time of every request")
    return Chart("response_time_timeline", "Response time of every request", _save(fig, out, "01_response_time_timeline"),
                 "wide", "Each dot is one request, plotted at the time it finished.",
                 {"requests": int(len(full)), "median_ms": round(float(np.median(full.elapsed_ms)), 1),
                  "unusually_slow_requests": n_outlier, "slow_cutoff_ms": round(float(slow_cut), 1),
                  "failed_requests": n_failed,
                  "slowest_ms": round(float(full.elapsed_ms.max()), 1),
                  "slowest_at": str(full.loc[full.elapsed_ms.idxmax(), "time"])})


def percentiles(data: TestData, out: Path) -> Chart:
    e = data.requests.elapsed_ms
    names = ["Fastest", "Median", "p90", "p95", "p99", "Slowest"]
    vals = [e.min(), *np.percentile(e, [50, 90, 95, 99]), e.max()]
    limit = _threshold_ms(data)

    fig, ax = plt.subplots(figsize=HALF)
    colours = [RED if (limit and v > limit) else SLATE for v in vals]
    ax.bar(names, vals, color=colours, width=0.6)
    log = _log_y_if_needed(ax, vals)
    for i, v in enumerate(vals):
        ax.text(i, v * (1.12 if log else 1.02), fmt_ms(v), ha="center", fontsize=7, color=INK)
    if limit:
        ax.axhline(limit, color=ORANGE, lw=1.2, ls=(0, (4, 3)))
    ax.grid(axis="x", visible=False)
    ax.tick_params(axis="x", labelsize=7.5)
    ax.set_title("Response time percentiles")
    return Chart("percentiles", "Response time percentiles", _save(fig, out, "02_percentiles"), "half",
                 "How fast requests were at different points: half were faster than the median, 95% faster than p95.",
                 {k: round(float(v), 1) for k, v in zip(["min_ms", "median_ms", "p90_ms", "p95_ms", "p99_ms", "max_ms"], vals)}
                 | {"p95_limit_ms": limit})


def distribution(data: TestData, out: Path) -> Chart:
    e = data.requests.elapsed_ms
    lo, hi = max(e.min(), 1), e.max()
    fig, ax = plt.subplots(figsize=HALF)
    if hi / lo > 20:
        bins = np.logspace(np.log10(lo), np.log10(hi), 30)
        ax.set_xscale("log")
    else:
        bins = 30
    ax.hist(e, bins=bins, color=SLATE, edgecolor="white", linewidth=0.8)
    ax.set_yscale("symlog", linthresh=2)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}"))
    ax.xaxis.set_major_formatter(MS_FORMATTER)
    ax.set_ylabel("Requests")
    ax.grid(axis="x", visible=False)
    ax.set_title("How response times are spread")
    within_2x = float((e <= np.median(e) * 2).mean() * 100)
    return Chart("distribution", "How response times are spread", _save(fig, out, "03_distribution"), "half",
                 "How many requests fell into each response-time range. A tall narrow peak means consistent performance.",
                 {"pct_within_2x_median": round(within_2x, 1), "median_ms": round(float(np.median(e)), 1)})


def throughput(data: TestData, out: Path) -> Chart:
    r = data.requests
    dur = (r.time.max() - r.time.min()).total_seconds() or 1
    rule = _bucket(dur)
    counts = r.set_index("time").elapsed_ms.resample(rule).count()
    secs = pd.Timedelta(rule).total_seconds()
    rps = counts / secs

    fig, ax = plt.subplots(figsize=WIDE)
    ax.bar(_local(rps.index.to_series()), rps.values, width=secs / 86400 * 0.85, color=SLATE)
    ax.set_ylabel("Requests per second")
    ax.set_xlabel(f"Time (per {rule})")
    _time_axis(ax, r.time)
    ax.grid(axis="x", visible=False)
    ax.set_title("Throughput over time")
    return Chart("throughput", "Throughput over time", _save(fig, out, "04_throughput"), "wide",
                 "How many requests per second the API handled during the test.",
                 {"avg_rps": round(len(r) / dur, 2), "peak_rps": round(float(rps.max()), 2),
                  "bucket": rule, "duration_s": round(dur)})


def response_trend(data: TestData, out: Path) -> Chart:
    """Median and p95 per time bucket. The key chart for soak tests (does it get slower over time?)."""
    r = data.requests
    dur = (r.time.max() - r.time.min()).total_seconds() or 1
    rule = _bucket(dur)
    g = r.set_index("time").elapsed_ms.resample(rule)
    med, p95 = g.median(), g.quantile(0.95)
    x = _local(med.index.to_series())

    fig, ax = plt.subplots(figsize=WIDE)
    ax.plot(x, p95.values, color=ORANGE, lw=2, label="95th percentile")
    ax.plot(x, med.values, color=SLATE, lw=2, label="Median")
    _log_y_if_needed(ax, pd.concat([med, p95]).dropna())
    ax.set_xlabel(f"Time (per {rule})")
    _time_axis(ax, r.time)
    _legend_top(ax)
    ax.set_title("Response time trend")

    third = max(len(med.dropna()) // 3, 1)
    first, last = med.dropna().iloc[:third].mean(), med.dropna().iloc[-third:].mean()
    change = (last - first) / first * 100 if first else 0
    return Chart("response_trend", "Response time trend", _save(fig, out, "05_response_trend"), "wide",
                 "Typical (median) and slow-end (p95) response time over the test. A rising line means the API slows down the longer it runs.",
                 {"median_first_third_ms": round(float(first), 1), "median_last_third_ms": round(float(last), 1),
                  "change_pct": round(float(change), 1), "worst_bucket_p95_ms": round(float(p95.max()), 1),
                  "worst_bucket_at": str(p95.idxmax()), "bucket": rule})


def error_rate(data: TestData, out: Path) -> Chart:
    r = data.requests
    dur = (r.time.max() - r.time.min()).total_seconds() or 1
    rule = _bucket(dur)
    secs = pd.Timedelta(rule).total_seconds()
    rate = (~r.set_index("time").success).resample(rule).mean() * 100

    fig, ax = plt.subplots(figsize=WIDE)
    ax.bar(_local(rate.index.to_series()), rate.fillna(0).values, width=secs / 86400 * 0.85,
           color=[RED if v > 0 else SLATE for v in rate.fillna(0)])
    ax.set_ylim(0, max(5, float(rate.max() or 0) * 1.2))
    ax.set_ylabel("% failed")
    ax.set_xlabel(f"Time (per {rule})")
    _time_axis(ax, r.time)
    ax.grid(axis="x", visible=False)
    if not (rate > 0).any():
        ax.text(0.5, 0.5, "No failed requests", transform=ax.transAxes, ha="center", color=GREEN, fontsize=11, fontweight="bold")
    ax.set_title("Error rate over time")
    return Chart("error_rate", "Error rate over time", _save(fig, out, "06_error_rate"), "wide",
                 "Share of requests that failed in each time period.",
                 {"overall_error_pct": round(float((~r.success).mean() * 100), 2),
                  "failed_requests": int((~r.success).sum()),
                  "worst_bucket_error_pct": round(float(rate.max() or 0), 2)})


def active_users(data: TestData, out: Path) -> Chart | None:
    u = data.users
    if u.empty:
        return None
    fig, ax = plt.subplots(figsize=HALF)
    t = _local(u.time)
    ax.step(t, u.users, where="post", color=SLATE, lw=1.5)
    ax.fill_between(t, u.users, step="post", color=SLATE, alpha=0.08)
    ax.set_ylabel("Active users")
    ax.set_ylim(0, max(u.users.max() * 1.2, 1))
    ax.set_xlabel("Time")
    _time_axis(ax, u.time)
    ax.set_title("Virtual users")
    return Chart("active_users", "Virtual users", _save(fig, out, "07_active_users"), "half",
                 "How many simulated users were active during the test (the load profile).",
                 {"peak_users": int(u.users.max()), "avg_users": round(float(u.users.mean()), 1)})


def response_vs_users(data: TestData, out: Path) -> Chart | None:
    """p95 at each load level: shows the point where more users = slower API (load/stress tests)."""
    u, r = data.users, data.requests
    if u.empty or u.users.nunique() < 3:
        return None
    merged = pd.merge_asof(r.sort_values("time"), u.sort_values("time")[["time", "users"]], on="time")
    merged = merged.dropna(subset=["users"])
    merged = merged[merged.users > 0]
    if merged.users.nunique() < 3:
        return None
    bins = min(12, merged.users.nunique())
    merged["band"] = pd.cut(merged.users, bins=bins)
    g = merged.groupby("band", observed=True).elapsed_ms.quantile(0.95)
    labels = [f"{int(b.left) + 1}-{int(b.right)}" for b in g.index]

    fig, ax = plt.subplots(figsize=HALF)
    ax.bar(labels, g.values, color=SLATE, width=0.65)
    _log_y_if_needed(ax, g.values)
    ax.set_xlabel("Active users")
    ax.set_ylabel("95th percentile")
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    ax.grid(axis="x", visible=False)
    ax.set_title("Response time vs load")
    return Chart("response_vs_users", "Response time vs load", _save(fig, out, "08_response_vs_users"), "half",
                 "The slow-end response time at each level of load. A sharp rise shows where the API starts to struggle.",
                 {"p95_at_lowest_load_ms": round(float(g.iloc[0]), 1), "p95_at_highest_load_ms": round(float(g.iloc[-1]), 1)})


def per_label(data: TestData, out: Path, top: int = 25) -> Chart:
    r = data.requests
    g = r.groupby("label").elapsed_ms.agg(median="median", p95=lambda s: np.percentile(s, 95), n="count")
    g = g.sort_values("p95", ascending=False).head(top).iloc[::-1]
    h = max(2.6, 0.26 * len(g) + 0.8)

    fig, ax = plt.subplots(figsize=(7.2, h))
    y = np.arange(len(g))
    ax.barh(y + 0.2, g.p95, height=0.38, color=ORANGE, label="95th percentile")
    ax.barh(y - 0.2, g["median"], height=0.38, color=SLATE, label="Median")
    ax.set_yticks(y)
    ax.set_yticklabels([str(lbl)[:45] for lbl in g.index], fontsize=7, color=INK)
    if g.p95.max() / max(g["median"].min(), 1) > 20:
        ax.set_xscale("log")
    ax.xaxis.set_major_formatter(MS_FORMATTER)
    ax.grid(axis="y", visible=False)
    _legend_top(ax)
    ax.set_title("Response time by test case / endpoint")
    worst = g.p95.idxmax()
    return Chart("per_label", "Response time by test case / endpoint", _save(fig, out, "09_per_label"), "wide",
                 "Typical and slow-end response time for each test case or endpoint, slowest at the top.",
                 {"labels": int(r.label.nunique()), "slowest_label": str(worst),
                  "slowest_label_p95_ms": round(float(g.p95.max()), 1),
                  "fastest_label_median_ms": round(float(g["median"].min()), 1)})


def status_codes(data: TestData, out: Path) -> Chart:
    codes = data.requests.status.replace("", "none").value_counts().sort_index()
    fig, ax = plt.subplots(figsize=HALF)
    colours = [RED if c[:1] in ("4", "5") or not c[:1].isdigit() else GREEN for c in codes.index]
    ax.bar(codes.index, codes.values, color=colours, width=0.55)
    for i, v in enumerate(codes.values):
        ax.text(i, v, f"{v}", ha="center", va="bottom", fontsize=7.5, color=INK)
    ax.set_xlim(-0.5 - max(0, (4 - len(codes)) / 2), len(codes) - 0.5 + max(0, (4 - len(codes)) / 2))
    ax.set_ylim(0, codes.max() * 1.15)
    ax.set_ylabel("Requests")
    ax.grid(axis="x", visible=False)
    ax.set_title("HTTP status codes")
    return Chart("status_codes", "HTTP status codes", _save(fig, out, "10_status_codes"), "half",
                 "How many requests got each HTTP response code. 2xx = success, 4xx = request rejected, 5xx = server error.",
                 {"codes": {str(k): int(v) for k, v in codes.items()}})


def timing_breakdown(data: TestData, out: Path) -> Chart | None:
    r = data.requests
    if r.waiting_ms.isna().all():
        return None
    waiting = float(r.waiting_ms.astype(float).mean())
    connect = float(r.connect_ms.astype(float).fillna(0).mean())
    # k6: elapsed = sending + waiting + receiving (connection time is extra)
    # JMeter: elapsed already includes connection time
    other = float(r.elapsed_ms.mean()) - waiting - (connect if data.tool == "jmeter" else 0)
    other = max(other, 0)
    parts = {"Server processing": waiting, "Connection setup": connect, "Sending / receiving": other}

    fig, ax = plt.subplots(figsize=HALF)
    names = list(parts)[::-1]
    vals = [parts[n] for n in names]
    ax.barh(names, vals, color=[ORANGE, ORANGE, SLATE], height=0.55)
    for i, v in enumerate(vals):
        ax.text(v, i, f" {v:.1f} ms", va="center", fontsize=7.5, color=INK)
    ax.set_xlim(0, max(vals) * 1.35)
    ax.set_xlabel("Average per request")
    ax.grid(axis="y", visible=False)
    ax.set_title("Where the time goes")
    total = sum(parts.values()) or 1
    return Chart("timing_breakdown", "Where the time goes", _save(fig, out, "11_timing_breakdown"), "half",
                 "Average split of each request between server work and network/connection time.",
                 {"server_pct": round(waiting / total * 100, 1), "connect_pct": round(connect / total * 100, 1),
                  "server_ms": round(waiting, 1), "connect_ms": round(connect, 1)})


BANDS = [(0, 500, "Under 0.5 s"), (500, 1000, "0.5 - 1 s"), (1000, 2000, "1 - 2 s"),
         (2000, 5000, "2 - 5 s"), (5000, float("inf"), "Over 5 s")]
BAND_COLOURS = [GREEN, "#8fbf6a", ORANGE, "#d9622b", RED]


def latency_bands(data: TestData, out: Path) -> Chart:
    """Plain-English view: what share of requests felt fast / ok / slow."""
    e = data.requests.elapsed_ms
    shares = [float(((e >= lo) & (e < hi)).mean() * 100) for lo, hi, _ in BANDS]

    fig, ax = plt.subplots(figsize=(7.2, 1.9))
    left = 0.0
    for share, (_, _, name), colour in zip(shares, BANDS, BAND_COLOURS):
        if share <= 0:
            continue
        ax.barh(0, share, left=left, color=colour, height=0.55, edgecolor="white", linewidth=1.5)
        if share >= 6:
            ax.text(left + share / 2, 0, f"{share:.0f}%", ha="center", va="center", color="white",
                    fontsize=8.5, fontweight="bold")
        left += share
    ax.set_xlim(0, 100)
    ax.set_yticks([])
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.grid(False)
    ax.spines["left"].set_visible(False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in BAND_COLOURS]
    ax.legend(handles, [b[2] for b in BANDS], fontsize=7.5, loc="upper center",
              bbox_to_anchor=(0.5, -0.35), ncol=5)
    ax.set_title("Share of requests by response time")
    return Chart("latency_bands", "Share of requests by response time", _save(fig, out, "12_latency_bands"), "wide",
                 "Every request sorted into a speed band, from fast (green) to very slow (red).",
                 {f"pct_{i}": round(s, 1) for i, s in enumerate(shares)}
                 | {"pct_under_1s": round(shares[0] + shares[1], 1), "pct_over_5s": round(shares[4], 1)})


def errors_by_label(data: TestData, out: Path) -> Chart | None:
    r = data.requests
    failed = r[~r.success]
    if failed.empty:
        return None
    g = r.groupby("label").success.agg(total="count", ok="sum")
    g["failed"] = g.total - g.ok
    g = g[g.failed > 0].sort_values("failed").tail(15)
    g["pct"] = g.failed / g.total * 100

    fig, ax = plt.subplots(figsize=(7.2, max(2.2, 0.32 * len(g) + 0.9)))
    ax.barh([str(x)[:45] for x in g.index], g.failed, color=RED, height=0.55)
    for i, (n, pct) in enumerate(zip(g.failed, g.pct)):
        ax.text(n, i, f"  {int(n)} ({pct:.1f}%)", va="center", fontsize=7.5, color=INK)
    ax.set_xlim(0, g.failed.max() * 1.3)
    ax.set_xlabel("Failed requests")
    ax.tick_params(axis="y", labelsize=7.5)
    ax.grid(axis="y", visible=False)
    ax.set_title("Failures by test case / endpoint")
    worst = g.failed.idxmax()
    return Chart("errors_by_label", "Failures by test case / endpoint", _save(fig, out, "13_errors_by_label"), "wide",
                 "Which test cases or endpoints the failed requests came from.",
                 {"labels_with_errors": int(len(g)), "worst_label": str(worst),
                  "worst_label_failed": int(g.loc[worst, "failed"]), "worst_label_pct": round(float(g.loc[worst, "pct"]), 1)})


ALL_CHARTS = [response_time_timeline, latency_bands, percentiles, distribution, throughput, response_trend,
              error_rate, errors_by_label, active_users, response_vs_users, per_label, status_codes, timing_breakdown]