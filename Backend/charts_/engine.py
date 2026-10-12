from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path

from .charts import ALL_CHARTS
from .loaders import load_results
from .theme import apply_theme


def build_charts(results_file: str | Path, out_dir: str | Path) -> dict:
    """
    Read one k6 / JMeter results file, draw every chart that makes sense for it,
    and write charts.json next to the images.
    """
    apply_theme()
    data = load_results(results_file)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    charts, skipped = [], []
    for make in ALL_CHARTS:
        try:
            chart = make(data, out)
        except Exception as exc:  # one broken chart should never stop the report
            skipped.append({"chart": make.__name__, "reason": str(exc)})
            continue
        if chart is None:
            skipped.append({"chart": make.__name__, "reason": "not enough data for this chart"})
        else:
            charts.append(asdict(chart))

    r = data.requests
    manifest = {
        "tool": data.tool,
        "source_file": Path(results_file).name,
        "test_start": str(r.time.min()),
        "test_end": str(r.time.max()),
        "requests": int(len(r)),
        "thresholds": data.thresholds,
        "charts": charts,
        "skipped": skipped,
    }
    (out / "charts.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest