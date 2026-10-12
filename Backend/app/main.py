"""
Sonar report service (FastAPI).

Flow
  1. POST /api/jobs                 upload results file  -> charts start building in the background
  2. PUT  /api/jobs/{id}/details    user's description of the test (sent while charts build)
  3. GET  /api/jobs/{id}            poll status; when "done" the report is ready
  4. GET  /api/jobs/{id}/report     download the .docx

Run:  uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import traceback
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from charts_ import build_charts, load_results
from reports_ import generate_report

JOBS_DIR = Path(__file__).parent.parent / "jobs"
STATIC_DIR = (Path(__file__).parent.parent / "static").resolve()  # built React app (only exists in the deployed container)
JOBS_DIR.mkdir(exist_ok=True)
MAX_UPLOAD_MB = 200
RESULT_EXTENSIONS = (".json", ".jtl", ".csv")
TEST_TYPES = {"load", "stress", "soak", "spike", "smoke"}

app = FastAPI(title="Sonar Report Service", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],  # lets the browser read the report's file name
)

executor = ThreadPoolExecutor(max_workers=2)
chart_lock = threading.Lock()   # matplotlib is not thread-safe: draw one job's charts at a time
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()

STAGES = {
    "uploaded": (10, "File received"),
    "building_charts": (35, "Reading results and drawing charts"),
    "waiting_for_details": (60, "Charts ready - waiting for your test details"),
    "writing_report": (85, "Analysing results and writing the report"),
    "done": (100, "Report ready"),
    "failed": (100, "Something went wrong"),
}


class TestDetails(BaseModel):
    project_name: str = ""
    client_name: str = ""
    environment: str = ""
    objective: str = ""
    expected_load: str = ""
    sla_p95_ms: Optional[float] = None
    sla_error_pct: Optional[float] = None
    tester_name: str = ""
    notes: str = ""


# ---------------------------------------------------------------- job helpers

def _update(job_id: str, **changes) -> dict:
    with jobs_lock:
        job = jobs[job_id]
        job.update(changes)
        (JOBS_DIR / job_id / "job.json").write_text(json.dumps(job, indent=2, default=str))
        return dict(job)


def _get(job_id: str) -> dict:
    with jobs_lock:
        if job_id not in jobs:
            raise HTTPException(404, "Job not found")
        return dict(jobs[job_id])


def _find_results_file(folder: Path) -> Path:
    """Pick the results file out of an upload (single file or extracted zip)."""
    candidates = sorted((p for p in folder.rglob("*") if p.suffix.lower() in RESULT_EXTENSIONS and p.is_file()),
                        key=lambda p: p.stat().st_size, reverse=True)
    for path in candidates:
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                first = f.readline().strip()
            if first.startswith("{") or ("timeStamp" in first and "elapsed" in first):
                return path
        except OSError:
            continue
    raise ValueError("No k6 JSON (k6 run --out json=...) or JMeter .jtl results file found in the upload.")


def _safe_extract(zip_path: Path, dest: Path) -> None:
    """Extract only result files, flattening paths (blocks ../ tricks in zip names)."""
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = Path(info.filename).name
            if info.is_dir() or not name.lower().endswith(RESULT_EXTENSIONS):
                continue
            with z.open(info) as src, open(dest / name, "wb") as out:
                shutil.copyfileobj(src, out)


# ---------------------------------------------------------------- background work

def _build_charts(job_id: str) -> None:
    job_dir = JOBS_DIR / job_id
    try:
        _update(job_id, status="building_charts")
        results = Path(_get(job_id)["results_file"])
        with chart_lock:
            manifest = build_charts(results, job_dir / "charts")
        data = load_results(results)  # quick facts for the waiting screen
        r = data.requests
        _update(job_id, charts=[{"title": c["title"], "file": c["file"]} for c in manifest["charts"]],
                tool=data.tool, preview={
                    "requests": int(len(r)),
                    "duration_min": round((r.time.max() - r.time.min()).total_seconds() / 60, 1),
                    "failed": int((~r.success).sum()),
                    "test_cases": int(r.label.nunique()),
                })
        with jobs_lock:  # check-and-set in one step so details arriving right now are never missed
            ready = jobs[job_id].get("details") is not None
            if not ready:
                jobs[job_id]["status"] = "waiting_for_details"
        if ready:
            _write_report(job_id)
        else:
            _update(job_id)
    except Exception as exc:
        traceback.print_exc()
        _update(job_id, status="failed", error=str(exc))


def _write_report(job_id: str) -> None:
    job_dir = JOBS_DIR / job_id
    try:
        _update(job_id, status="writing_report")
        job = _get(job_id)
        details = dict(job["details"]) | {"test_type": job["test_type"]}
        manifest = json.loads((job_dir / "charts" / "charts.json").read_text())
        path = generate_report(job["results_file"], job_dir, details, manifest)
        summary = json.loads((job_dir / "summary.json").read_text())
        _update(job_id, status="done", report_file=str(path), summary=summary,
                finished_at=datetime.now().isoformat())
    except Exception as exc:
        traceback.print_exc()
        _update(job_id, status="failed", error=str(exc))


# ---------------------------------------------------------------- API

@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/jobs")
async def create_job(file: UploadFile = File(...), test_type: str = Form("load"), tool: str = Form("")):
    if test_type not in TEST_TYPES:
        raise HTTPException(400, f"test_type must be one of {sorted(TEST_TYPES)}")
    name = Path(file.filename or "upload").name
    if not name.lower().endswith(RESULT_EXTENSIONS + (".zip",)):
        raise HTTPException(400, "Upload a k6 .json, JMeter .jtl/.csv, or a .zip containing one.")

    job_id = uuid.uuid4().hex[:12]
    job_dir = JOBS_DIR / job_id
    (job_dir / "input").mkdir(parents=True)
    saved = job_dir / "input" / name

    size = 0
    with open(saved, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_MB * 1024 * 1024:
                out.close()
                shutil.rmtree(job_dir, ignore_errors=True)
                raise HTTPException(413, f"File is larger than {MAX_UPLOAD_MB} MB.")
            out.write(chunk)

    try:
        if name.lower().endswith(".zip"):
            _safe_extract(saved, job_dir / "input")
        results = _find_results_file(job_dir / "input")
    except (ValueError, zipfile.BadZipFile) as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(400, str(exc))

    with jobs_lock:
        jobs[job_id] = {"id": job_id, "status": "uploaded", "test_type": test_type, "tool": tool,
                        "file_name": name, "results_file": str(results), "details": None,
                        "created_at": datetime.now().isoformat(), "charts": [], "error": None}
    executor.submit(_build_charts, job_id)
    return _public(job_id)


@app.put("/api/jobs/{job_id}/details")
def add_details(job_id: str, details: TestDetails):
    with jobs_lock:
        if job_id not in jobs:
            raise HTTPException(404, "Job not found")
        job = jobs[job_id]
        if job["status"] in ("writing_report", "done"):
            raise HTTPException(409, "Report is already being written for this job.")
        job["details"] = details.model_dump()
        start_now = job["status"] == "waiting_for_details"
        if start_now:
            job["status"] = "writing_report"
    _update(job_id)
    if start_now:
        executor.submit(_write_report, job_id)
    return _public(job_id)


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    return _public(job_id)


@app.get("/api/jobs/{job_id}/charts/{file_name}")
def chart_image(job_id: str, file_name: str):
    _get(job_id)
    if not re.fullmatch(r"[\w\-]+\.png", file_name):
        raise HTTPException(400, "Bad file name")
    path = JOBS_DIR / job_id / "charts" / file_name
    if not path.exists():
        raise HTTPException(404, "Chart not found")
    return FileResponse(path, media_type="image/png")


@app.get("/api/jobs/{job_id}/report")
def download_report(job_id: str):
    job = _get(job_id)
    if job["status"] != "done":
        raise HTTPException(409, "Report is not ready yet.")
    project = re.sub(r"[^\w]+", "_", (job["details"] or {}).get("project_name") or "API").strip("_")
    nice = f"Sonar_{project}_{job['test_type'].title()}_Test_Report_{datetime.now():%Y-%m-%d}.docx"
    return FileResponse(job["report_file"], filename=nice,
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def _public(job_id: str) -> dict:
    """What the frontend sees (no server file paths)."""
    job = _get(job_id)
    progress, label = STAGES[job["status"]]
    return {
        "id": job_id,
        "status": job["status"],
        "progress": progress,
        "stage": label,
        "error": job.get("error"),
        "test_type": job["test_type"],
        "file_name": job["file_name"],
        "details_received": job.get("details") is not None,
        "preview": job.get("preview"),
        "charts": [{"title": c["title"], "url": f"/api/jobs/{job_id}/charts/{c['file']}"} for c in job.get("charts", [])],
        "report_url": f"/api/jobs/{job_id}/report" if job["status"] == "done" else None,
        "summary": job.get("summary"),
    }
    

# ---------------------------------------------------------------- website (deployed version only)
# In the cloud the built React app sits in Backend/static and this same server hands it out,
# so the website and the API share one address. Locally (npm run dev) this folder doesn't exist.
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def website(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        file = (STATIC_DIR / full_path).resolve()
        if full_path and file.is_file() and STATIC_DIR in file.parents:
            return FileResponse(file)
        return FileResponse(STATIC_DIR / "index.html")  # React handles /login, / etc.