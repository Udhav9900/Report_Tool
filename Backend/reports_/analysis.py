"""
Rule-based analysis: turns the raw numbers into findings with a severity,
the same way a performance engineer would read the results.
No AI service is used - every rule is written here and can be tuned.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from charts_.loaders import TestData
from charts_.theme import fmt_ms
from . import test_types

SEVERITY_ORDER = ["HIGH", "MEDIUM", "LOW", "INFO"]
SEVERITY_COLOUR = {"HIGH": "C8161D", "MEDIUM": "E07A1F", "LOW": "C98633", "INFO": "4A4959"}


def fmt_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} h {m} min"
    if m:
        return f"{m} min {s} s" if s and m < 10 else f"{m} min"
    return f"{s} s"


def _metrics(data: TestData) -> dict:
    r = data.requests
    e = r.elapsed_ms
    dur = max((r.time.max() - r.time.min()).total_seconds(), 1)
    codes = r.status.replace("", "none").value_counts()
    return {
        "requests": int(len(r)),
        "failed": int((~r.success).sum()),
        "error_pct": float((~r.success).mean() * 100),
        "server_errors": int(sum(v for k, v in codes.items() if str(k).startswith("5"))),
        "min_ms": float(e.min()), "median_ms": float(np.median(e)), "avg_ms": float(e.mean()),
        "p90_ms": float(np.percentile(e, 90)), "p95_ms": float(np.percentile(e, 95)),
        "p99_ms": float(np.percentile(e, 99)), "max_ms": float(e.max()),
        "duration_s": dur, "avg_rps": len(r) / dur,
        "peak_users": int(data.users.users.max()) if not data.users.empty else None,
        "labels": int(r.label.nunique()),
        "start": r.time.min(), "end": r.time.max(),
        "status_codes": {str(k): int(v) for k, v in codes.items()},
    }


def _sla_ms(data: TestData, details: dict) -> float | None:
    if details.get("sla_p95_ms"):
        return float(details["sla_p95_ms"])
    for rule in data.thresholds.get("http_req_duration", []):
        rule = rule.replace(" ", "")
        if rule.startswith("p(95)<"):
            try:
                return float(rule.split("<")[1])
            except ValueError:
                pass
    return None


def _stalls(data: TestData, median: float) -> list[dict]:
    """Groups of unusually slow requests close together in time (a pause / hang on the server)."""
    r = data.requests
    slow = r[r.elapsed_ms >= median * 5].sort_values("time")
    if slow.empty:
        return []
    gap = slow.time.diff().dt.total_seconds().fillna(0)
    groups = (gap > 60).cumsum()
    out = []
    for _, g in slow.groupby(groups):
        if len(g) < 2:
            continue
        sent_first = g.time.min() - pd.to_timedelta(g.loc[g.time.idxmin(), "elapsed_ms"], unit="ms")
        window = r[(r.time >= g.time.min()) & (r.time <= g.time.max())]
        # A real stall is short and almost every request inside it is slow.
        # A long stretch of mixed fast/slow requests is just "slow under load", handled by other rules.
        if (g.time.max() - g.time.min()).total_seconds() > 120 or len(g) / max(len(window), 1) < 0.5:
            continue
        out.append({"count": int(len(g)), "start": sent_first, "end": g.time.max(),
                    "max_ms": float(g.elapsed_ms.max()), "labels": sorted(g.label.unique().tolist()),
                    "index": g.index})
    return out


def analyse(data: TestData, manifest: dict, details: dict) -> dict:
    m = _metrics(data)
    sla = _sla_ms(data, details)
    err_target = float(details.get("sla_error_pct") or 1.0)
    ttype = (details.get("test_type") or "").lower()
    facts = {c["id"]: c["facts"] for c in manifest["charts"]}
    findings: list[dict] = []

    def add(severity, title, description, impact, recommendation, chart=None):
        findings.append({"severity": severity, "title": title, "description": description,
                         "impact": impact, "recommendation": recommendation, "chart": chart})

    # 1. Response time target
    if sla:
        if m["p95_ms"] > sla:
            add("HIGH", "Response time target missed",
                f"95% of requests should finish within {fmt_ms(sla)}, but the 95th percentile was {fmt_ms(m['p95_ms'])}. "
                f"About {(data.requests.elapsed_ms > sla).mean() * 100:.1f}% of all requests were slower than the target.",
                "Users and integrating systems will regularly experience slow responses, and client timeouts may cause failed or repeated requests.",
                "Profile the slowest endpoints, check database queries and downstream calls, and re-test after tuning.",
                "02_percentiles.png")
        elif m["max_ms"] > sla:
            over = int((data.requests.elapsed_ms > sla).sum())
            add("LOW", "Some requests exceeded the response time target",
                f"The 95th percentile ({fmt_ms(m['p95_ms'])}) met the {fmt_ms(sla)} target, but {over} request(s) were slower, "
                f"with the slowest taking {fmt_ms(m['max_ms'])}.",
                "A small number of users may see slow responses even though the overall target is met.",
                "Add a 99th percentile or maximum response time target so these outliers are tracked.",
                "01_response_time_timeline.png")

    # 2. Errors
    if m["failed"]:
        sev = "HIGH" if m["error_pct"] >= 5 else "MEDIUM" if m["error_pct"] >= err_target else "LOW"
        server = f" {m['server_errors']} of them were server errors (5xx)." if m["server_errors"] else ""
        worst = facts.get("errors_by_label", {})
        where = (f" Most failures came from '{worst['worst_label']}' ({worst['worst_label_failed']} failed)."
                 if worst.get("worst_label") else "")
        add(sev, "Requests failed during the test",
            f"{m['failed']} of {m['requests']} requests failed ({m['error_pct']:.2f}%).{server}{where}",
            "Failed requests mean lost or incomplete transactions unless the client retries them correctly.",
            "Check the server logs for the failing endpoints and time periods, and confirm clients retry safely.",
            "06_error_rate.png")
        if m["server_errors"] and sev == "LOW":
            findings[-1]["severity"] = "MEDIUM"

    # 3. Stalls / freezes
    stalls = _stalls(data, m["median_ms"])
    for s in stalls:
        too_slow = s["max_ms"] > (sla or 5000)
        add("MEDIUM" if too_slow else "LOW", "API stopped responding for a short period",
            f"{s['count']} requests sent between {s['start']:%H:%M:%S} and {s['end']:%H:%M:%S} were held by the server and answered "
            f"late, the slowest after {fmt_ms(s['max_ms'])}. Response times were normal before and after this window.",
            "If client timeouts are shorter than this delay, requests may fail or be sent twice, causing missed or duplicate transactions.",
            f"Check server, application-pool and database logs for {s['start']:%H:%M}-{s['end']:%H:%M} "
            "(restarts, locks, garbage collection or slow downstream calls).",
            "01_response_time_timeline.png")

    # 4. Slowing down over time (soak tests)
    trend = facts.get("response_trend", {})
    change = trend.get("change_pct", 0) or 0
    load_changed = bool(facts.get("response_vs_users"))  # rising load explains rising times -> rule 5 covers it
    if change >= 20 and not load_changed:
        sev = "HIGH" if change >= 50 else "MEDIUM"
        if ttype not in ("soak", "load") and sev == "HIGH":
            sev = "MEDIUM"
        add(sev, "Response times increased as the test went on",
            f"The typical response time rose from {fmt_ms(trend['median_first_third_ms'])} in the first third of the test "
            f"to {fmt_ms(trend['median_last_third_ms'])} in the last third (+{change:.0f}%).",
            "If this continues in production, the API will keep getting slower until it is restarted or fails.",
            "Monitor memory, connection pools and queue sizes over a longer run to find what is building up.",
            "05_response_trend.png")

    # 5. Breaking point under load
    vs = facts.get("response_vs_users", {})
    if vs.get("p95_at_lowest_load_ms"):
        ratio = vs["p95_at_highest_load_ms"] / max(vs["p95_at_lowest_load_ms"], 1)
        if ratio >= 1.5:
            add("MEDIUM" if ratio >= 3 else "LOW", "API slows down as more users are added",
                f"The 95th percentile grew from {fmt_ms(vs['p95_at_lowest_load_ms'])} at the lowest load to "
                f"{fmt_ms(vs['p95_at_highest_load_ms'])} at the highest load ({ratio:.1f}x slower).",
                "Capacity is limited: busy periods will bring noticeably slower responses for everyone.",
                "Identify the resource that saturates first (CPU, database, thread pool) and scale or optimise it.",
                "08_response_vs_users.png")

    # 6. Slow individual endpoints / cases
    stalled_idx = set().union(*[set(s["index"]) for s in stalls]) if stalls else set()
    normal = data.requests.drop(index=list(stalled_idx))
    g = normal.groupby("label").elapsed_ms.median()
    slow_labels = g[g > float(normal.elapsed_ms.median()) * 2]
    if len(slow_labels) and data.requests.label.nunique() > 1:
        names = ", ".join(f"'{n}'" for n in slow_labels.sort_values(ascending=False).index[:3])
        add("LOW", "Some test cases are noticeably slower than others",
            f"{len(slow_labels)} test case(s) had a typical response time more than twice the overall median, including {names}.",
            "These operations will feel slower to users and are the first to struggle under heavier load.",
            "Review these specific endpoints for heavy queries or extra downstream calls.",
            "09_per_label.png")

    # 7. Test design notes
    if ttype == "soak" and m["duration_s"] < 3600:
        add("INFO", "Soak test was shorter than recommended",
            f"The test ran for {fmt_duration(m['duration_s'])}. Soak tests usually run for 1-8 hours so slow build-ups have time to appear.",
            "Problems that only appear after hours of use (memory leaks, connection exhaustion) may not have been caught.",
            "Repeat the soak test for at least 1-2 hours at the same load.")
    if ttype in ("stress", "spike") and (m["peak_users"] or 0) <= 10:
        add("INFO", "Load level was low for this test type",
            f"The test peaked at {m['peak_users'] or 'a few'} virtual users, which is light for a {test_types.get(ttype)['name'].lower()}.",
            "The API's true limit was probably not reached.",
            "Increase the load in steps until response times or errors clearly rise.")
    if m["avg_rps"] < 1 and ttype in ("load", "stress"):
        add("INFO", "Low request rate",
            f"The average rate was {m['avg_rps']:.2f} requests per second, so the results describe behaviour at low traffic.",
            "The results may not reflect performance at real production volumes.",
            "Agree a target request rate with the business and test at that level.")

    findings.sort(key=lambda f: SEVERITY_ORDER.index(f["severity"]))
    for i, f in enumerate(findings, 1):
        f["id"] = f"FIND-{i:02d}"
        f["colour"] = SEVERITY_COLOUR[f["severity"]]

    counts = {s: sum(f["severity"] == s for f in findings) for s in SEVERITY_ORDER}
    if counts["HIGH"]:
        verdict, verdict_colour = "NEEDS ATTENTION", SEVERITY_COLOUR["HIGH"]
    elif counts["MEDIUM"] or counts["LOW"]:
        verdict, verdict_colour = "PASSED WITH ISSUES", SEVERITY_COLOUR["MEDIUM"]
    else:
        verdict, verdict_colour = "PASSED", "2F8A4C"

    # Things that went well (like LMNTRIX "notable controls")
    positives = []
    if m["failed"] == 0:
        positives.append(("No failed requests", f"All {m['requests']} requests completed successfully."))
    if sla and m["p95_ms"] <= sla:
        positives.append(("Response time target met", f"95% of requests finished within {fmt_ms(m['p95_ms'])}, inside the {fmt_ms(sla)} target."))
    if abs(change) < 10 and m["duration_s"] >= 300:
        positives.append(("Stable over time", "Typical response time stayed level from the start to the end of the test."))
    if facts.get("distribution", {}).get("pct_within_2x_median", 0) >= 90:
        positives.append(("Consistent response times",
                          f"{facts['distribution']['pct_within_2x_median']:.0f}% of requests finished within twice the typical response time."))
    if m["server_errors"] == 0 and m["requests"]:
        positives.append(("No server errors", "The API never returned a 5xx server error."))

    return {"metrics": m, "sla_ms": sla, "error_target_pct": err_target, "findings": findings,
            "counts": counts, "verdict": verdict, "verdict_colour": verdict_colour, "positives": positives,
            "change_pct": change}