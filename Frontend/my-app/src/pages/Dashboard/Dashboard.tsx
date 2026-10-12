import { useEffect, useRef, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import sonarLogo from "../../assets/sonar-logo.png";
import {
  chartUrl, createJob, downloadReport, errorMessage, getJob, sendDetails,
  type Job, type Severity, type TestDetails,
} from "../../services/api";
import "./Dashboard.css";

type TestType = { id: string; name: string; short: string; explain: string };

const TEST_TYPES: TestType[] = [
  { id: "load", name: "Load Testing", short: "Expected traffic, normal conditions",
    explain: "Checks how the API behaves under the number of users you normally expect." },
  { id: "stress", name: "Stress Testing", short: "Push beyond limits to find the breaking point",
    explain: "Keeps adding users until the API slows down or fails, so you know its limit." },
  { id: "soak", name: "Soak Testing", short: "Steady load over many hours",
    explain: "Runs a steady load for a long time to catch memory leaks and slow degradation." },
  { id: "spike", name: "Spike Testing", short: "Sudden bursts of traffic",
    explain: "Throws a sudden burst of users at the API to see if it survives and recovers." },
  { id: "smoke", name: "Smoke Testing", short: "Quick sanity check with minimal load",
    explain: "A short, tiny test to confirm the API works at all before bigger tests." },
];

type Tool = "k6" | "jmeter";
const MAX_MB = 200;
const ACCEPTED = [".json", ".jtl", ".csv", ".zip"];
const SEVERITIES: Severity[] = ["HIGH", "MEDIUM", "LOW", "INFO"];
const STEPS = ["Choose test", "Upload results", "Test details", "Report"];

export default function Dashboard() {
  const { user, logout } = useAuth();

  // step 1-2: setup
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<TestType | null>(null);
  const [tool, setTool] = useState<Tool>("k6");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [uploadPct, setUploadPct] = useState<number | null>(null);

  // step 3-4: job on the server
  const [job, setJob] = useState<Job | null>(null);
  const [detailsSent, setDetailsSent] = useState(false);
  const [sending, setSending] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [details, setDetails] = useState<TestDetails>({
    project_name: "", client_name: "", environment: "staging", objective: "",
    expected_load: "", sla_p95_ms: null, tester_name: user?.name === "Guest" ? "" : user?.name ?? "", notes: "",
  });

  const [menuOpen, setMenuOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const step = !job ? (!selected ? 1 : 2) : job.status === "done" ? 4 : 3;
  const finished = job?.status === "done" || job?.status === "failed";

  // close dropdown / user menu on outside click or Escape
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) setOpen(false);
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); setMenuOpen(false); } };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onClick); document.removeEventListener("keydown", onKey); };
  }, []);

  // poll the job every 1.5 s until it's finished
  useEffect(() => {
    if (!job || finished) return;
    const timer = setTimeout(async () => {
      try { setJob(await getJob(job.id)); }
      catch (err) { setError(errorMessage(err)); }
    }, 1500);
    return () => clearTimeout(timer);
  }, [job, finished]);

  function pickFile(f?: File) {
    setError("");
    if (!f) return;
    if (!ACCEPTED.some((ext) => f.name.toLowerCase().endsWith(ext)))
      return setError("Upload a k6 .json, a JMeter .jtl / .csv, or a .zip containing one.");
    if (f.size > MAX_MB * 1024 * 1024) return setError(`File is bigger than ${MAX_MB} MB.`);
    setFile(f);
  }

  async function startUpload() {
    if (!selected || !file) return;
    setError("");
    setUploadPct(0);
    try {
      setJob(await createJob(file, selected.id, tool, setUploadPct));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setUploadPct(null);
    }
  }

  async function submitDetails(e: React.FormEvent) {
    e.preventDefault();
    if (!job) return;
    if (!details.project_name.trim()) return setError("Please give the API / system a name.");
    setError("");
    setSending(true);
    try {
      setJob(await sendDetails(job.id, details));
      setDetailsSent(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSending(false);
    }
  }

  async function handleDownload() {
    if (!job) return;
    setDownloading(true);
    try { await downloadReport(job); }
    catch (err) { setError(errorMessage(err)); }
    finally { setDownloading(false); }
  }

  function reset() {
    setSelected(null); setFile(null); setJob(null); setDetailsSent(false); setError("");
  }

  const set = <K extends keyof TestDetails>(key: K, value: TestDetails[K]) =>
    setDetails((d) => ({ ...d, [key]: value }));

  const initials = (user?.name ?? "?").split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();

  return (
    <div className="sn-page">
      <header className="sn-header">
        <div className="sn-header-inner">
          <img src={sonarLogo} alt="Sonar" className="sn-header-logo" />
          <div className="sn-user" ref={userMenuRef}>
            <button className="sn-user-btn" onClick={() => setMenuOpen((o) => !o)}>
              {user?.picture ? (
                <img src={user.picture} alt="" className="sn-avatar" referrerPolicy="no-referrer" />
              ) : (
                <span className="sn-avatar sn-avatar-initials">{initials}</span>
              )}
              <span className="sn-user-name">{user?.name}</span>
              <span className="sn-caret">▾</span>
            </button>
            {menuOpen && (
              <div className="sn-user-menu">
                <div className="sn-user-menu-head"><b>{user?.name}</b><small>{user?.email}</small></div>
                <button onClick={logout}>Sign out</button>
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="sn-center">
        <h1 className="sn-title">
          Turn test results into <span className="sn-accent">clear reports</span>
        </h1>
        <p className="sn-sub">Upload your k6 or JMeter or any other report here !</p>

        <ol className="sn-steps">
          {STEPS.map((label, i) => {
            const n = i + 1;
            const state = n < step ? "done" : n === step ? "active" : "";
            return (
              <li key={label} className={`sn-step ${state}`}>
                <span className="sn-step-dot">{n < step ? "✓" : n}</span>
                <span>{label}</span>
              </li>
            );
          })}
        </ol>

        {/* ---------------- STEP 1 + 2: choose test & upload ---------------- */}
        {!job && (
          <section className="sn-card">
            <label className="sn-label">What kind of test did you run?</label>
            <div className="dd" ref={dropdownRef}>
              <button type="button" className={`dd-trigger ${open ? "dd-open" : ""}`}
                onClick={() => setOpen((o) => !o)} aria-haspopup="listbox" aria-expanded={open}>
                {selected ? (
                  <span className="dd-value"><b>{selected.name}</b><small>{selected.short}</small></span>
                ) : (
                  <span className="dd-placeholder">Select a testing type…</span>
                )}
                <span className="dd-chevron">▾</span>
              </button>
              {open && (
                <ul className="dd-menu" role="listbox">
                  {TEST_TYPES.map((t) => (
                    <li key={t.id} role="option" aria-selected={selected?.id === t.id}
                      className={`dd-item ${selected?.id === t.id ? "active" : ""}`}
                      onClick={() => { setSelected(t); setOpen(false); }}>
                      <span className="dd-text"><b>{t.name}</b><small>{t.short}</small></span>
                      {selected?.id === t.id && <span className="dd-check">✓</span>}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {selected && <p className="sn-explain">💡 {selected.explain}</p>}

            {selected && (
              <div className="sn-section">
                <label className="sn-label">Which tool produced the report?</label>
                <div className="sn-toggle">
                  <button type="button" className={tool === "k6" ? "on" : ""} onClick={() => setTool("k6")}>k6</button>
                  <button type="button" className={tool === "jmeter" ? "on" : ""} onClick={() => setTool("jmeter")}>JMeter</button>
                </div>

                <label className="sn-label">Results file</label>
                {!file ? (
                  <div className={`sn-drop ${dragging ? "dragging" : ""}`}
                    onClick={() => fileInputRef.current?.click()}
                    onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={(e) => { e.preventDefault(); setDragging(false); pickFile(e.dataTransfer.files[0]); }}>
                    <input ref={fileInputRef} type="file" accept={ACCEPTED.join(",")} hidden
                      onChange={(e) => pickFile(e.target.files?.[0])} />
                    <svg className="sn-drop-icon" viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor"
                      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 16V4M7 9l5-5 5 5" />
                      <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
                    </svg>
                    <b>{dragging ? "Drop it!" : "Drag & drop your results file here"}</b>
                    <span>or <u>browse files</u></span>
                    <div className="sn-chips">
                      <span className="sn-chip">{tool === "k6" ? "k6 --out json" : "JMeter .jtl / .csv"}</span>
                      <span className="sn-chip">.zip also works</span>
                      <span className="sn-chip">max {MAX_MB} MB</span>
                    </div>
                  </div>
                ) : (
                  <div className="sn-file">
                    <div className="sn-file-badge">{file.name.split(".").pop()?.toUpperCase().slice(0, 4)}</div>
                    <div className="sn-file-info">
                      <b>{file.name}</b>
                      <small>{(file.size / 1024 / 1024).toFixed(2)} MB · {tool === "k6" ? "k6" : "JMeter"}</small>
                    </div>
                    {uploadPct === null && (
                      <button className="sn-icon-btn" onClick={() => setFile(null)} title="Remove file">✕</button>
                    )}
                  </div>
                )}
              </div>
            )}

            {error && <div className="sn-error">{error}</div>}

            {uploadPct === null ? (
              <button className="sn-btn" disabled={!selected || !file} onClick={startUpload}>Generate report</button>
            ) : (
              <div className="sn-progress-wrap">
                <div className="sn-progress-top"><span>Uploading…</span><span>{uploadPct}%</span></div>
                <div className="sn-progress"><div style={{ width: `${uploadPct}%` }} /></div>
              </div>
            )}
          </section>
        )}

        {/* ---------------- live status (steps 3 + 4) ---------------- */}
        {job && job.status !== "done" && (
          <section className="sn-card sn-status">
            <div className="sn-progress-top">
              <span>{job.status === "failed" ? "Report could not be created" : job.stage}</span>
              <span>{job.progress}%</span>
            </div>
            <div className={`sn-progress ${finished ? "" : "sn-progress-live"}`}>
              <div style={{ width: `${job.progress}%` }} />
            </div>
            {job.preview && (
              <div className="sn-facts">
                <div><b>{job.preview.requests.toLocaleString()}</b><small>requests</small></div>
                <div><b>{job.preview.duration_min} min</b><small>test length</small></div>
                <div><b>{job.preview.failed.toLocaleString()}</b><small>failed</small></div>
                <div><b>{job.preview.test_cases}</b><small>test cases</small></div>
              </div>
            )}
            {job.status === "failed" && (
              <>
                <div className="sn-error">{job.error}</div>
                <button className="sn-btn" onClick={reset}>Start again</button>
              </>
            )}
          </section>
        )}

        {/* ---------------- STEP 3: tell us about the test ---------------- */}
        {job && !detailsSent && job.status !== "failed" && (
          <form className="sn-card sn-form" onSubmit={submitDetails}>
            <h2 className="sn-card-title">While we build your charts, tell us about your test</h2>
            <p className="sn-hint">This goes into the executive summary and scope sections of the report.</p>

            <div className="sn-grid">
              <label className="sn-field">
                <span>API / system name *</span>
                <input value={details.project_name} onChange={(e) => set("project_name", e.target.value)}
                  placeholder="e.g. FreightS Ingestion API" />
              </label>
              <label className="sn-field">
                <span>Client</span>
                <input value={details.client_name} onChange={(e) => set("client_name", e.target.value)}
                  placeholder="e.g. Team Global Express" />
              </label>
              <label className="sn-field">
                <span>Environment</span>
                <select value={details.environment} onChange={(e) => set("environment", e.target.value)}>
                  <option value="dev">Dev</option>
                  <option value="qa">QA</option>
                  <option value="staging">Staging</option>
                  <option value="uat">UAT</option>
                  <option value="production">Production</option>
                </select>
              </label>
              <label className="sn-field">
                <span>Response time target (p95, ms)</span>
                <input type="number" min={1} value={details.sla_p95_ms ?? ""}
                  onChange={(e) => set("sla_p95_ms", e.target.value ? Number(e.target.value) : null)}
                  placeholder="e.g. 2000" />
              </label>
            </div>

            <label className="sn-field">
              <span>What were you testing, and why?</span>
              <textarea rows={3} value={details.objective} onChange={(e) => set("objective", e.target.value)}
                placeholder="e.g. Confirm the Syngin webhook stays fast and stable under steady booking traffic before go-live." />
            </label>
            <div className="sn-grid">
              <label className="sn-field">
                <span>Expected load</span>
                <input value={details.expected_load} onChange={(e) => set("expected_load", e.target.value)}
                  placeholder="e.g. 15 bookings per minute" />
              </label>
              <label className="sn-field">
                <span>Tested by</span>
                <input value={details.tester_name} onChange={(e) => set("tester_name", e.target.value)}
                  placeholder="Your name" />
              </label>
            </div>
            <label className="sn-field">
              <span>Anything else the readers should know?</span>
              <textarea rows={2} value={details.notes} onChange={(e) => set("notes", e.target.value)}
                placeholder="Optional notes, known issues, test data used…" />
            </label>

            {error && <div className="sn-error">{error}</div>}
            <button className="sn-btn" type="submit" disabled={sending}>
              {sending ? "Sending…" : "Create my report"}
            </button>
          </form>
        )}

        {/* ---------------- STEP 4: report ready ---------------- */}
        {job?.status === "done" && job.summary && (
          <section className="sn-card sn-result">
            <div className="sn-verdict" style={{ background: `#${job.summary.verdict_colour}` }}>
              <small>Overall result</small>
              <b>{job.summary.verdict}</b>
            </div>

            <div className="sn-tiles">
              {SEVERITIES.map((s) => (
                <div key={s} className={`sn-tile sn-tile-${s.toLowerCase()}`}>
                  <small>{s}</small>
                  <b>{job.summary!.counts[s]}</b>
                </div>
              ))}
            </div>

            {job.summary.findings.length > 0 && (
              <ul className="sn-findings">
                {job.summary.findings.map((f) => (
                  <li key={f.id}>
                    <span className={`sn-pill sn-pill-${f.severity.toLowerCase()}`}>{f.severity}</span>
                    <span><b>{f.id}</b> {f.title}</span>
                  </li>
                ))}
              </ul>
            )}

            {error && <div className="sn-error">{error}</div>}
            <div className="sn-done-row">
              <button className="sn-btn" onClick={handleDownload} disabled={downloading}>
                {downloading ? "Preparing…" : "Download Word report (.docx)"}
              </button>
              <button className="sn-btn-ghost" onClick={reset}>New report</button>
            </div>

            <label className="sn-label">Charts in this report</label>
            <div className="sn-thumbs">
              {job.charts.map((c) => (
                <a key={c.url} href={chartUrl(c.url)} target="_blank" rel="noreferrer" title={c.title}>
                  <img src={chartUrl(c.url)} alt={c.title} loading="lazy" />
                  <span>{c.title}</span>
                </a>
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}