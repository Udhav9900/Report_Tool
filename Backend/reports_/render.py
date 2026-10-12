"""
Fills templates/sonar_template.docx with the charts, numbers and text for one test run.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
from docx.shared import Cm
from docxtpl import DocxTemplate, InlineImage, RichText

from charts_ import build_charts, load_results
from charts_.theme import fmt_ms
from . import test_types, writer
from .analysis import analyse, fmt_duration

TEMPLATE = Path(__file__).parent.parent / "templates" / "sonar_template.docx"
TOOL_NAMES = {"k6": "Grafana k6", "jmeter": "Apache JMeter"}
AREA_BY_CHART = {
    "02_percentiles.png": "Response time", "01_response_time_timeline.png": "Availability",
    "06_error_rate.png": "Reliability", "05_response_trend.png": "Stability over time",
    "08_response_vs_users.png": "Capacity / scalability", "09_per_label.png": "Endpoint performance",
}
SLATE, LIGHT, WHITE = "4A4959", "F5F5F7", "FFFFFF"


def _period(start, end) -> str:
    tz = start.strftime("%z")
    tz = f" (UTC{tz[:3]}:{tz[3:]})" if tz else ""
    if start.date() == end.date():
        return f"{start:%d %b %Y}, {start:%H:%M} - {end:%H:%M}{tz}"
    return f"{start:%d %b %Y %H:%M} - {end:%d %b %Y %H:%M}{tz}"


def generate_report(results_file: str | Path, work_dir: str | Path, details: dict,
                    manifest: dict | None = None) -> Path:
    work = Path(work_dir)
    charts_dir = work / "charts"
    env = (details.get("environment") or "").strip()
    details = details | {"environment": env.upper() if len(env) <= 4 else env.title()}
    if manifest is None:
        manifest = (json.loads((charts_dir / "charts.json").read_text()) if (charts_dir / "charts.json").exists()
                    else build_charts(results_file, charts_dir))
    data = load_results(results_file)
    a = analyse(data, manifest, details)
    m = a["metrics"]
    tt = test_types.get(details.get("test_type"))
    doc = DocxTemplate(TEMPLATE)

    def image(name: str, width_cm: float):
        path = charts_dir / name
        return InlineImage(doc, str(path), width=Cm(width_cm)) if path.exists() else ""

    charts = [c | {"text": writer.chart_explanation(c, a)} for c in manifest["charts"]]
    wide = [{"title": c["title"], "image": image(c["file"], 16.4), "text": c["text"]}
            for c in charts if c["size"] == "wide"]
    halves = [{"title": c["title"], "image": image(c["file"], 7.9), "text": c["text"], "bar": SLATE, "box": LIGHT}
              for c in charts if c["size"] == "half"]
    empty = {"title": "", "image": "", "text": "", "bar": WHITE, "box": WHITE}
    half_rows = [{"left": halves[i], "right": halves[i + 1] if i + 1 < len(halves) else empty}
                 for i in range(0, len(halves), 2)]

    chart_titles = {c["file"]: c["title"] for c in charts}
    findings = []
    for f in a["findings"]:
        ev = f.get("chart") if f.get("chart") and (charts_dir / f["chart"]).exists() else None
        findings.append(f | {
            "area": AREA_BY_CHART.get(f.get("chart") or "", "Test design" if f["severity"] == "INFO" else "Performance"),
            "evidence": image(ev, 15.5) if ev else "",
            "evidence_caption": f"Figure: {chart_titles.get(ev, '')}" if ev else "",
        })

    key_rows = []
    for r in writer.key_results(a):
        key_rows.append(r | {"status_rt": RichText(r["status"] or "-", color=r["colour"] if r["status"] else "9A9AA5",
                                                   bold=bool(r["status"]), size=19)})

    labels = []
    for name, g in data.requests.groupby("label"):
        e = g.elapsed_ms
        labels.append({"name": str(name)[:60], "requests": f"{len(g):,}", "failed": f"{int((~g.success).sum()):,}",
                       "median": fmt_ms(float(np.median(e))), "p95": fmt_ms(float(np.percentile(e, 95))),
                       "max": fmt_ms(float(e.max()))})
    labels.sort(key=lambda l: l["name"])

    targets = []
    if a["sla_ms"]:
        targets.append(f"95th percentile under {fmt_ms(a['sla_ms'])}")
    targets.append(f"error rate under {a['error_target_pct']:g}%")
    load_bits = [f"{m['avg_rps']:.2f} requests/second on average"]
    if m["peak_users"]:
        load_bits.insert(0, f"up to {m['peak_users']} virtual users")

    context = {
        "project_name": details.get("project_name") or "API under test",
        "client_name": details.get("client_name") or "Client",
        "environment": details["environment"] or "Not specified",
        "tester_name": details.get("tester_name") or "Sonar Performance Team",
        "report_date": datetime.now().strftime("%d %B %Y"),
        "period": _period(m["start"], m["end"]),
        "tool_name": TOOL_NAMES.get(data.tool, data.tool),
        "test_type_name": tt["name"],
        "test_type_purpose": tt["purpose"],
        "objective": details.get("objective") or f"Measure how {details.get('project_name') or 'the API'} performs under the planned load.",
        "scope": f"{fmt_duration(m['duration_s'])} run, {m['requests']:,} requests across {m['labels']} test case(s)/endpoint(s).",
        "summary": writer.executive_summary(details, a),
        "counts": a["counts"],
        "verdict": a["verdict"],
        "verdict_colour": a["verdict_colour"],
        "key_results": key_rows,
        "top_findings": [f for f in findings if f["severity"] != "INFO"][:5],
        "positives": [{"title": t, "text": x} for t, x in a["positives"]],
        "load_profile": ", ".join(load_bits).capitalize(),
        "label_count": str(m["labels"]),
        "targets": "; ".join(targets).capitalize(),
        "source_file": Path(results_file).name,
        "method_text": tt["method"],
        "expected_load": details.get("expected_load") or "",
        "notes": details.get("notes") or "",
        "wide_charts": wide,
        "half_rows": half_rows,
        "findings": findings,
        "narrative": writer.narrative(details, a, manifest),
        "labels": labels,
    }
    doc.render(context, autoescape=True)
    out = work / "report.docx"
    doc.save(out)
    (work / "summary.json").write_text(json.dumps({
        "verdict": a["verdict"], "verdict_colour": a["verdict_colour"], "counts": a["counts"],
        "findings": [{"id": f["id"], "title": f["title"], "severity": f["severity"]} for f in a["findings"]],
    }))
    return out