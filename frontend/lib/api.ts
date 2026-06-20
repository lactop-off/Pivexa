// API クライアント。Cookie(JWT) を使うため credentials: include 固定。
const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function handle(res: Response) {
  if (res.ok) {
    const ct = res.headers.get("content-type") ?? "";
    return ct.includes("application/json") ? res.json() : res;
  }
  let detail: unknown = null;
  try {
    const body = await res.json();
    detail = body.detail ?? body;
  } catch {
    detail = await res.text();
  }
  const msg = typeof detail === "string" ? detail : `エラー (${res.status})`;
  throw new ApiError(res.status, msg, detail);
}

export const api = {
  base: BASE,
  get: (path: string) =>
    fetch(`${BASE}${path}`, { credentials: "include" }).then(handle),
  post: (path: string, body?: unknown) =>
    fetch(`${BASE}${path}`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }).then(handle),
  del: (path: string) =>
    fetch(`${BASE}${path}`, { method: "DELETE", credentials: "include" }).then(handle),
  upload: (path: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(`${BASE}${path}`, {
      method: "POST",
      credentials: "include",
      body: fd,
    }).then(handle);
  },
  chartUrl: (path: string) => {
    const name = path.split("/").pop() ?? "";
    return `${BASE}/charts/${name}`;
  },
};

// --- 型 ---------------------------------------------------------------
export type Method = {
  name: string;
  display_name: string;
  needs_target: boolean;
  target_kind: string | null;
  min_rows: number;
};

export type ConfigField = {
  key: string;
  label: string;
  kind: "single_select" | "multi_select" | "option";
  required: boolean;
  candidates: string[];
};

export type ConfigSchema = {
  method: string;
  display_name: string;
  needs_target: boolean;
  target_kind: string | null;
  fields: ConfigField[];
};

export type Column = {
  name: string;
  type: string;
  missing: number;
  summary: Record<string, number>;
  recommendation: { action: string; method?: string; reason: string } | null;
};

export type Metric = {
  key: string;
  label: string;
  value: number | string;
  significant: boolean | null;
};

export type Coefficient = {
  variable: string;
  coef: number;
  std_err: number | null;
  stat: number | null;
  p_value: number | null;
  ci_low: number | null;
  ci_high: number | null;
  extra: Record<string, number>;
};

export type ChartRef = { kind: string; label: string; path: string };

export type AnalysisResult = {
  method: string;
  summary_metrics: Metric[];
  coefficients: Coefficient[];
  tables: Record<string, unknown>;
  charts: ChartRef[];
  sample_size: number;
  warnings: string[];
};

export type Interpretation = {
  sentences: { level: "info" | "highlight" | "caution"; text: string }[];
};
