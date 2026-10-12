"""
Make a full report from the command line:
    python -m sonar_report results.json out_folder --type load --project "Orders API" --client "Acme"
"""
import argparse

from .render import generate_report

ap = argparse.ArgumentParser()
ap.add_argument("results")
ap.add_argument("out")
ap.add_argument("--type", default="load", help="load | stress | soak | spike | smoke")
ap.add_argument("--project", default="")
ap.add_argument("--client", default="")
ap.add_argument("--env", default="")
ap.add_argument("--sla", type=float, default=None, help="p95 target in ms")
args = ap.parse_args()

path = generate_report(args.results, args.out, {
    "test_type": args.type, "project_name": args.project, "client_name": args.client,
    "environment": args.env, "sla_p95_ms": args.sla,
})
print("Report written to", path)