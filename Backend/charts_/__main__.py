"""
Usage:
    python -m sonar_charts results.json charts_out
    python -m sonar_charts results.jtl  charts_out
"""
import sys

from .engine import build_charts

if len(sys.argv) != 3:
    sys.exit("Usage: python -m sonar_charts <results.json | results.jtl> <output_folder>")

manifest = build_charts(sys.argv[1], sys.argv[2])
print(f"{manifest['tool']}: {manifest['requests']} requests")
for c in manifest["charts"]:
    print(f"  created  {c['file']:32} {c['title']}")
for s in manifest["skipped"]:
    print(f"  skipped  {s['chart']:32} {s['reason']}")