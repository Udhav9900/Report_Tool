import axios from "axios";

// Backend address. Override with VITE_API_URL in .env.local when deployed.
export const API_URL = import.meta.env.VITE_API_URL ?? "";

const http = axios.create({ baseURL: API_URL, timeout: 120_000 });

export type JobStatus =
  | "uploaded"
  | "building_charts"
  | "waiting_for_details"
  | "writing_report"
  | "done"
  | "failed";

export type Severity = "HIGH" | "MEDIUM" | "LOW" | "INFO";

export type Job = {
  id: string;
  status: JobStatus;
  progress: number;
  stage: string;
  error: string | null;
  test_type: string;
  file_name: string;
  details_received: boolean;
  preview: { requests: number; duration_min: number; failed: number; test_cases: number } | null;
  charts: { title: string; url: string }[];
  report_url: string | null;
  summary: {
    verdict: string;
    verdict_colour: string;
    counts: Record<Severity, number>;
    findings: { id: string; title: string; severity: Severity }[];
  } | null;
};

export type TestDetails = {
  project_name: string;
  client_name: string;
  environment: string;
  objective: string;
  expected_load: string;
  sla_p95_ms: number | null;
  tester_name: string;
  notes: string;
};

/** 1. Upload the results file. Charts start building on the server straight away. */
export async function createJob(
  file: File,
  testType: string,
  tool: string,
  onUploadProgress?: (percent: number) => void
): Promise<Job> {
  const form = new FormData();
  form.append("file", file);
  form.append("test_type", testType);
  form.append("tool", tool);
  const { data } = await http.post<Job>("/api/jobs", form, {
    onUploadProgress: (e) => onUploadProgress?.(Math.round((e.loaded * 100) / (e.total ?? e.loaded))),
  });
  return data;
}

/** 2. Send the user's description of the test (can be sent while charts are still building). */
export async function sendDetails(jobId: string, details: TestDetails): Promise<Job> {
  const { data } = await http.put<Job>(`/api/jobs/${jobId}/details`, details);
  return data;
}

/** 3. Poll this until status is "done" or "failed". */
export async function getJob(jobId: string): Promise<Job> {
  const { data } = await http.get<Job>(`/api/jobs/${jobId}`);
  return data;
}

/** 4. Download the finished .docx and save it with the name the server suggests. */
export async function downloadReport(job: Job): Promise<void> {
  if (!job.report_url) return;
  const res = await http.get(job.report_url, { responseType: "blob" });
  const header = res.headers["content-disposition"] as string | undefined;
  const name = header?.match(/filename="?([^"]+)"?/)?.[1] ?? "Sonar_Report.docx";
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export const chartUrl = (path: string) => `${API_URL}${path}`;

/** Turn any axios / network error into a sentence for the user. */
export function errorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    if (!err.response) return "Can't reach the report server. Is the backend running on port 8000?";
    const detail = (err.response.data as { detail?: unknown })?.detail;
    if (typeof detail === "string") return detail;
    return `Server error (${err.response.status}).`;
  }
  return err instanceof Error ? err.message : "Something went wrong.";
}