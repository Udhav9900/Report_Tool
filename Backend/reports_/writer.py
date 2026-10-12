"""
Writes the plain-English text of the report from the numbers.
Every sentence is a template filled with real values - nothing is invented.
"""
from __future__ import annotations

from charts_.theme import fmt_ms
from . import test_types
from .analysis import fmt_duration


def executive_summary(details: dict, a: dict) -> list[str]:
    m, tt = a["metrics"], test_types.get(details.get("test_type"))
    api = details.get("project_name") or "the API"
    paras = []

    paras.append(
        f"This {tt['name'].lower()} {tt['purpose']}. It was run against {api}"
        f"{' in the ' + details['environment'] + ' environment' if details.get('environment') else ''} "
        f"for {fmt_duration(m['duration_s'])}, sending {m['requests']:,} requests"
        f"{' with up to ' + str(m['peak_users']) + ' virtual users' if m['peak_users'] else ''}."
    )

    speed = (f"A typical request took {fmt_ms(m['median_ms'])} and 95% finished within {fmt_ms(m['p95_ms'])}")
    if a["sla_ms"]:
        speed += (f", {'inside' if m['p95_ms'] <= a['sla_ms'] else 'outside'} the {fmt_ms(a['sla_ms'])} target")
    errors = ("No requests failed." if m["failed"] == 0
              else f"{m['failed']:,} requests failed ({m['error_pct']:.2f}%).")
    paras.append(f"{speed}. {errors}")

    c = a["counts"]
    issues = sum(c[s] for s in ("HIGH", "MEDIUM", "LOW"))
    if issues == 0:
        paras.append("No performance issues were found. The API met expectations for this test.")
    else:
        parts = [f"{c[s]} {s.lower()}" for s in ("HIGH", "MEDIUM", "LOW") if c[s]]
        top = a["findings"][0]
        paras.append(f"The test found {issues} issue{'s' if issues > 1 else ''} ({', '.join(parts)} severity). "
                     f"The most important is \u201c{top['title']}\u201d. Details and recommendations are in the Findings section.")
    return paras


def chart_explanation(chart: dict, a: dict) -> str:
    """Fixed description + a sentence that reads this run's numbers."""
    f, cid, m = chart["facts"], chart["id"], a["metrics"]
    text = chart["what_it_shows"]

    if cid == "response_time_timeline":
        if f["unusually_slow_requests"] or f["failed_requests"]:
            text += (f" {f['unusually_slow_requests']} request(s) were unusually slow (over {fmt_ms(f['slow_cutoff_ms'])})"
                     f" and {f['failed_requests']} failed. The slowest took {fmt_ms(f['slowest_ms'])}.")
        else:
            text += " Response times stayed in a steady band with no unusual spikes."
    elif cid == "latency_bands":
        text += f" {f['pct_under_1s']:.0f}% of requests finished in under 1 second"
        text += f", and {f['pct_over_5s']:.1f}% took longer than 5 seconds." if f["pct_over_5s"] else "."
    elif cid == "percentiles":
        text += f" Median {fmt_ms(f['median_ms'])}, p95 {fmt_ms(f['p95_ms'])}, p99 {fmt_ms(f['p99_ms'])}."
        if f["p99_ms"] > f["p95_ms"] * 3:
            text += " The large jump from p95 to p99 shows a small group of much slower requests."
    elif cid == "distribution":
        text += f" {f['pct_within_2x_median']:.0f}% of requests finished within twice the typical time of {fmt_ms(f['median_ms'])}."
    elif cid == "throughput":
        text += f" The average was {f['avg_rps']:.2f} requests per second, peaking at {f['peak_rps']:.2f}."
    elif cid == "response_trend":
        ch = f["change_pct"]
        if abs(ch) < 10:
            text += " The typical response time stayed stable throughout the test."
        else:
            text += (f" The typical response time {'rose' if ch > 0 else 'fell'} by {abs(ch):.0f}% "
                     f"from the start to the end of the test.")
    elif cid == "error_rate":
        text += (" No requests failed at any point." if f["failed_requests"] == 0
                 else f" Overall {f['overall_error_pct']:.2f}% failed; the worst period reached {f['worst_bucket_error_pct']:.1f}%.")
    elif cid == "errors_by_label":
        text += f" '{f['worst_label']}' had the most failures ({f['worst_label_failed']}, {f['worst_label_pct']:.1f}% of its requests)."
    elif cid == "active_users":
        text += f" Peak: {f['peak_users']} users."
    elif cid == "response_vs_users":
        text += (f" The 95th percentile went from {fmt_ms(f['p95_at_lowest_load_ms'])} at the lowest load "
                 f"to {fmt_ms(f['p95_at_highest_load_ms'])} at the highest.")
    elif cid == "per_label":
        text += f" {f['labels']} test case(s) were measured; the slowest was '{f['slowest_label']}' (p95 {fmt_ms(f['slowest_label_p95_ms'])})."
    elif cid == "status_codes":
        codes = ", ".join(f"{k}: {v:,}" for k, v in f["codes"].items())
        text += f" Responses received - {codes}."
    elif cid == "timing_breakdown":
        text += f" About {f['server_pct']:.0f}% of the time was spent on server processing."
    return text


def key_results(a: dict) -> list[dict]:
    """Rows for the key results table, with a status colour."""
    m, sla = a["metrics"], a["sla_ms"]
    ok, warn, bad, neutral = "2F8A4C", "E07A1F", "C8161D", "4A4959"
    rows = [
        {"name": "Requests sent", "value": f"{m['requests']:,}", "status": "", "colour": neutral},
        {"name": "Failed requests", "value": f"{m['failed']:,} ({m['error_pct']:.2f}%)",
         "status": "PASS" if m["error_pct"] < a["error_target_pct"] else "FAIL",
         "colour": ok if m["error_pct"] < a["error_target_pct"] else bad},
        {"name": "Typical response (median)", "value": fmt_ms(m["median_ms"]), "status": "", "colour": neutral},
        {"name": "95th percentile", "value": fmt_ms(m["p95_ms"]),
         "status": ("PASS" if m["p95_ms"] <= sla else "FAIL") if sla else "",
         "colour": (ok if m["p95_ms"] <= sla else bad) if sla else neutral},
        {"name": "99th percentile", "value": fmt_ms(m["p99_ms"]),
         "status": ("WATCH" if sla and m["p99_ms"] > sla else ""), "colour": warn if sla and m["p99_ms"] > sla else neutral},
        {"name": "Slowest request", "value": fmt_ms(m["max_ms"]), "status": "", "colour": neutral},
        {"name": "Average throughput", "value": f"{m['avg_rps']:.2f} req/s", "status": "", "colour": neutral},
        {"name": "Test duration", "value": fmt_duration(m["duration_s"]), "status": "", "colour": neutral},
    ]
    if m["peak_users"]:
        rows.insert(1, {"name": "Peak virtual users", "value": str(m["peak_users"]), "status": "", "colour": neutral})
    return rows


def narrative(details: dict, a: dict, manifest: dict) -> list[str]:
    """A short story of the test run, like the LMNTRIX 'attack narrative'."""
    m = a["metrics"]
    tt = test_types.get(details.get("test_type"))
    paras = [
        f"The test started at {m['start']:%H:%M} on {m['start']:%d %B %Y} and ran until {m['end']:%H:%M}. "
        f"{tt['method']}"
    ]
    trend = next((c["facts"] for c in manifest["charts"] if c["id"] == "response_trend"), {})
    if trend:
        ch = trend.get("change_pct", 0)
        steady = "remained steady" if abs(ch) < 10 else ("rose" if ch > 0 else "fell")
        paras.append(f"Over the course of the run the typical response time {steady}"
                     f"{'' if abs(ch) < 10 else f' by {abs(ch):.0f}%'}, and the worst period had a 95th percentile of "
                     f"{fmt_ms(trend['worst_bucket_p95_ms'])}.")
    if a["findings"]:
        notable = [f for f in a["findings"] if f["severity"] != "INFO"]
        if notable:
            paras.append("Notable events: " + " ".join(f["description"] for f in notable[:2]))
    else:
        paras.append("No unusual events were observed during the run.")
    return paras