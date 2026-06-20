"use client";

import { use, useEffect, useState } from "react";
import {
  api,
  ApiError,
  type ConfigSchema,
  type Method,
  type AnalysisResult,
  type Interpretation,
} from "../../../../lib/api";
import { useRequireAuth } from "../../../../lib/useRequireAuth";
import { Steps } from "../../../../components/Steps";
import { ResultView } from "../../../../components/ResultView";

type Phase = "config" | "running" | "result";

export default function AnalyzePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const ready = useRequireAuth();

  const [methods, setMethods] = useState<Method[]>([]);
  const [method, setMethod] = useState<string>("");
  const [schema, setSchema] = useState<ConfigSchema | null>(null);

  const [target, setTarget] = useState<string>("");
  const [explanatory, setExplanatory] = useState<string[]>([]);
  const [options, setOptions] = useState<Record<string, string>>({});

  const [phase, setPhase] = useState<Phase>("config");
  const [error, setError] = useState("");
  const [issues, setIssues] = useState<string[]>([]);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [interpretation, setInterpretation] = useState<Interpretation | null>(null);

  useEffect(() => {
    if (ready) api.get("/methods").then(setMethods).catch(() => {});
  }, [ready]);

  useEffect(() => {
    if (!method) return;
    setSchema(null);
    setTarget("");
    setExplanatory([]);
    setOptions({});
    api
      .get(`/datasets/${id}/methods/${method}/schema`)
      .then(setSchema)
      .catch((e) => setError(e instanceof ApiError ? e.message : "設定の取得に失敗しました。"));
  }, [method, id]);

  function buildConfig() {
    const opts: Record<string, string> = { ...options };
    const config: Record<string, unknown> = { options: opts };
    for (const f of schema?.fields ?? []) {
      if (f.key === "target") config.target = target;
      else if (f.key === "explanatory") config.explanatory = explanatory;
      // それ以外（group など）は options に入れる（既に opts へ格納済み）
    }
    return config;
  }

  async function run() {
    setError("");
    setIssues([]);
    setPhase("running");
    try {
      const res = await api.post("/jobs", {
        dataset_id: Number(id),
        method,
        config: buildConfig(),
      });
      await waitForResult(res);
    } catch (e) {
      setPhase("config");
      if (e instanceof ApiError && e.status === 422) {
        const detail = e.detail as { issues?: { level: string; message: string }[] };
        setIssues((detail.issues ?? []).map((i) => i.message));
      } else {
        setError(e instanceof ApiError ? e.message : "実行に失敗しました。");
      }
    }
  }

  async function waitForResult(res: { job_id: number; status: string; result_id: number | null }) {
    let resultId = res.result_id;
    let status = res.status;
    let tries = 0;
    while (status !== "done" && status !== "error" && tries < 120) {
      await sleep(1000);
      const job = await api.get(`/jobs/${res.job_id}`);
      status = job.status;
      resultId = job.result_id;
      tries++;
      if (status === "error") throw new ApiError(500, job.error_message ?? "解析に失敗しました。", null);
    }
    if (!resultId) throw new ApiError(500, "結果を取得できませんでした。", null);
    const data = await api.get(`/results/${resultId}`);
    setResult(data.result);
    setInterpretation(data.interpretation);
    setPhase("result");
  }

  function reset() {
    setPhase("config");
    setResult(null);
    setInterpretation(null);
  }

  if (!ready) return <p className="muted">読み込み中...</p>;

  return (
    <div>
      <Steps current={phase === "result" ? 4 : phase === "running" ? 3 : 2} />

      {phase === "result" && result && interpretation ? (
        <>
          <div className="no-print" style={{ marginBottom: 12 }}>
            <button className="secondary" onClick={reset}>
              ← 別の分析を行う
            </button>
          </div>
          <ResultView result={result} interpretation={interpretation} />
        </>
      ) : (
        <div className="card">
          <h1>分析設定</h1>
          <p className="muted">分析手法と変数を選び、実行してください。</p>

          <label>分析手法</label>
          <select value={method} onChange={(e) => setMethod(e.target.value)} disabled={phase === "running"}>
            <option value="">選択してください</option>
            {methods.map((m) => (
              <option key={m.name} value={m.name}>
                {m.display_name}
              </option>
            ))}
          </select>

          {schema?.fields.map((f) => (
            <div key={f.key}>
              <label>
                {f.label}
                {f.required && <span style={{ color: "var(--danger)" }}> *</span>}
              </label>
              {f.kind === "multi_select" ? (
                <MultiSelect
                  candidates={f.candidates}
                  value={f.key === "explanatory" ? explanatory : []}
                  onChange={(v) => {
                    if (f.key === "explanatory") setExplanatory(v);
                  }}
                />
              ) : (
                <select
                  value={f.key === "target" ? target : options[f.key] ?? ""}
                  onChange={(e) => {
                    if (f.key === "target") setTarget(e.target.value);
                    else setOptions((s) => ({ ...s, [f.key]: e.target.value }));
                  }}
                >
                  <option value="">選択してください</option>
                  {f.candidates.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              )}
            </div>
          ))}

          {issues.length > 0 && (
            <div style={{ marginTop: 12 }}>
              {issues.map((m, i) => (
                <div key={i} className="error">
                  ・{m}
                </div>
              ))}
            </div>
          )}
          {error && <p className="error">{error}</p>}

          <button onClick={run} disabled={!method || phase === "running"} style={{ marginTop: 16 }}>
            {phase === "running" ? "解析中..." : "実行"}
          </button>
          {phase === "running" && (
            <p className="muted">重い処理はバックグラウンドで実行され、完了すると結果が表示されます。</p>
          )}
        </div>
      )}
    </div>
  );
}

function MultiSelect({
  candidates,
  value,
  onChange,
}: {
  candidates: string[];
  value: string[];
  onChange: (v: string[]) => void;
}) {
  function toggle(c: string) {
    onChange(value.includes(c) ? value.filter((x) => x !== c) : [...value, c]);
  }
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {candidates.map((c) => (
        <label
          key={c}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            margin: 0,
            padding: "4px 10px",
            border: "1px solid var(--border)",
            borderRadius: 8,
            background: value.includes(c) ? "var(--highlight)" : "#fff",
            cursor: "pointer",
          }}
        >
          <input
            type="checkbox"
            style={{ width: "auto" }}
            checked={value.includes(c)}
            onChange={() => toggle(c)}
          />
          {c}
        </label>
      ))}
      {candidates.length === 0 && <span className="muted">候補となる列がありません。</span>}
    </div>
  );
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}
