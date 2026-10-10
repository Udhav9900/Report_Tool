import { useEffect, useRef, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import sonarLogo from "../../assets/sonar-logo.png";
import "./Dashboard.css";

type TestType = {
  id: string;
  name: string;
  short: string;
  explain: string;
};

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

export default function Dashboard() {
  const { user, logout } = useAuth();

  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<TestType | null>(null);
  const [tool, setTool] = useState<Tool>("k6");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  const dropdownRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Which step is active: 1 = choose test, 2 = upload, 3 = generate
  const step = !selected ? 1 : !file ? 2 : 3;

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) setOpen(false);
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setOpen(false); setMenuOpen(false); }
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  function pickFile(f?: File) {
    setError("");
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".zip")) return setError("Only .zip files are supported.");
    if (f.size > MAX_MB * 1024 * 1024) return setError(`File is bigger than ${MAX_MB} MB.`);
    setFile(f);
  }

  // Fake progress for now — replace with the real FastAPI call later
  function generate() {
    if (!selected || !file) return;
    setProgress(0);
    const timer = setInterval(() => {
      setProgress((p) => {
        if (p === null || p >= 100) {
          clearInterval(timer);
          return 100;
        }
        return p + 4;
      });
    }, 120);
  }

  function reset() {
    setSelected(null);
    setFile(null);
    setProgress(null);
    setError("");
  }

  const stageLabel =
    progress === null ? "" :
    progress < 30 ? "Unpacking ZIP…" :
    progress < 60 ? "Parsing test results…" :
    progress < 90 ? "AI is writing the summary…" :
    progress < 100 ? "Building PDF…" : "Report ready!";

  const initials = (user?.name ?? "?").split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();

  return (
    <div className="sn-page">
      {/* Top bar */}
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
                <div className="sn-user-menu-head">
                  <b>{user?.name}</b>
                  <small>{user?.email}</small>
                </div>
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

        {/* Stepper */}
        <ol className="sn-steps">
          {["Choose test", "Upload ZIP", "Generate"].map((label, i) => {
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

        <section className="sn-card">
          {/* STEP 1: dropdown */}
          <label className="sn-label">What kind of test did you run?</label>
          <div className="dd" ref={dropdownRef}>
            <button
              type="button"
              className={`dd-trigger ${open ? "dd-open" : ""}`}
              onClick={() => setOpen((o) => !o)}
              aria-haspopup="listbox"
              aria-expanded={open}
            >
              {selected ? (
                <span className="dd-value">
                  <b>{selected.name}</b>
                  <small>{selected.short}</small>
                </span>
              ) : (
                <span className="dd-placeholder">Select a testing type…</span>
              )}
              <span className="dd-chevron">▾</span>
            </button>

            {open && (
              <ul className="dd-menu" role="listbox">
                {TEST_TYPES.map((t) => (
                  <li
                    key={t.id}
                    role="option"
                    aria-selected={selected?.id === t.id}
                    className={`dd-item ${selected?.id === t.id ? "active" : ""}`}
                    onClick={() => {
                      setSelected(t);
                      setOpen(false);
                    }}
                  >
                    <span className="dd-text">
                      <b>{t.name}</b>
                      <small>{t.short}</small>
                    </span>
                    {selected?.id === t.id && <span className="dd-check">✓</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {selected && <p className="sn-explain">💡 {selected.explain}</p>}

          {/* STEP 2: tool + upload */}
          {selected && (
            <div className="sn-section">
              <label className="sn-label">Which tool produced the report?</label>
              <div className="sn-toggle">
                <button type="button" className={tool === "k6" ? "on" : ""} onClick={() => setTool("k6")}>k6</button>
                <button type="button" className={tool === "jmeter" ? "on" : ""} onClick={() => setTool("jmeter")}>JMeter</button>
              </div>

              <label className="sn-label">Report file</label>
              {!file ? (
                <div
                  className={`sn-drop ${dragging ? "dragging" : ""}`}
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={(e) => { e.preventDefault(); setDragging(false); pickFile(e.dataTransfer.files[0]); }}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".zip"
                    hidden
                    onChange={(e) => pickFile(e.target.files?.[0])}
                  />
                  <svg className="sn-drop-icon" viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 16V4M7 9l5-5 5 5" />
                    <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
                  </svg>
                  <b>{dragging ? "Drop it!" : "Drag & drop your ZIP here"}</b>
                  <span>or <u>browse files</u></span>
                  <div className="sn-chips">
                    <span className="sn-chip">.zip</span>
                    <span className="sn-chip">{tool === "k6" ? "k6 HTML / JSON" : "JMeter dashboard + .jtl"}</span>
                    <span className="sn-chip">max {MAX_MB} MB</span>
                  </div>
                </div>
              ) : (
                <div className="sn-file">
                  <div className="sn-file-badge">ZIP</div>
                  <div className="sn-file-info">
                    <b>{file.name}</b>
                    <small>{(file.size / 1024 / 1024).toFixed(2)} MB · {tool === "k6" ? "k6" : "JMeter"}</small>
                  </div>
                  {progress === null && (
                    <button className="sn-icon-btn" onClick={() => setFile(null)} title="Remove file">✕</button>
                  )}
                </div>
              )}

              {error && <div className="sn-error">{error}</div>}
            </div>
          )}

          {/* STEP 3: generate */}
          {progress === null ? (
            <button className="sn-btn" disabled={!selected || !file} onClick={generate}>
              Generate report
            </button>
          ) : (
            <div className="sn-progress-wrap">
              <div className="sn-progress-top">
                <span>{stageLabel}</span>
                <span>{progress}%</span>
              </div>
              <div className="sn-progress">
                <div style={{ width: `${progress}%` }} />
              </div>
              {progress >= 100 && (
                <div className="sn-done-row">
                  <button className="sn-btn" onClick={() => alert("PDF download will work once the backend is connected")}>
                    Download PDF
                  </button>
                  <button className="sn-btn-ghost" onClick={reset}>New report</button>
                </div>
              )}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}