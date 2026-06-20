"use client";

import { useState } from "react";
import { api, ApiError, type AnalysisResult, type Interpretation } from "../lib/api";

export function ResultView({
  result,
  interpretation,
  resultId,
}: {
  result: AnalysisResult;
  interpretation: Interpretation;
  resultId?: number;
}) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");

  async function downloadPdf() {
    if (!resultId) return;
    setDownloading(true);
    setError("");
    try {
      const { report_id } = await api.post(`/results/${resultId}/report`, { format: "pdf" });
      // 認証付きで取得して blob としてダウンロード
      const res = await fetch(`${api.base}/reports/${report_id}`, { credentials: "include" });
      if (!res.ok) throw new ApiError(res.status, "レポートの取得に失敗しました。", null);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `report_${report_id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "PDF生成に失敗しました。");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div>
      <div className="card">
        <div className="row no-print" style={{ alignItems: "center" }}>
          <h2 style={{ margin: 0 }}>解析結果</h2>
          <span className="spacer" />
          {resultId && (
            <button onClick={downloadPdf} disabled={downloading}>
              {downloading ? "生成中..." : "PDFをダウンロード"}
            </button>
          )}
          <button className="secondary" onClick={() => window.print()}>
            印刷
          </button>
        </div>
        {error && <p className="error no-print">{error}</p>}
        <p className="muted">サンプル数: {result.sample_size}</p>

        {result.summary_metrics.length > 0 && (
          <>
            <h2>モデル全体の指標</h2>
            <table>
              <thead>
                <tr>
                  <th>指標</th>
                  <th className="num">値</th>
                  <th>有意</th>
                </tr>
              </thead>
              <tbody>
                {result.summary_metrics.map((m) => (
                  <tr key={m.key}>
                    <td>{m.label}</td>
                    <td className="num">{String(m.value)}</td>
                    <td>
                      {m.significant === true && <span className="badge sig">有意</span>}
                      {m.significant === false && <span className="muted">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        {result.coefficients.length > 0 && (
          <>
            <h2 style={{ marginTop: 20 }}>説明変数ごとの結果</h2>
            <table>
              <thead>
                <tr>
                  <th>変数</th>
                  <th className="num">係数</th>
                  <th className="num">標準誤差</th>
                  <th className="num">統計量</th>
                  <th className="num">P値</th>
                  <th className="num">95%CI</th>
                  <th className="num">補足</th>
                </tr>
              </thead>
              <tbody>
                {result.coefficients.map((c) => {
                  const sig = c.p_value !== null && c.p_value < 0.05;
                  return (
                    <tr key={c.variable} style={sig ? { background: "var(--highlight)" } : {}}>
                      <td>
                        {c.variable} {sig && <span className="badge sig">有意</span>}
                      </td>
                      <td className="num">{fmt(c.coef)}</td>
                      <td className="num">{fmt(c.std_err)}</td>
                      <td className="num">{fmt(c.stat)}</td>
                      <td className="num">{fmt(c.p_value)}</td>
                      <td className="num">
                        {c.ci_low !== null ? `${fmt(c.ci_low)}〜${fmt(c.ci_high)}` : "—"}
                      </td>
                      <td className="num">{extra(c.extra)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        )}

        {result.charts.length > 0 && (
          <>
            <h2 style={{ marginTop: 20 }}>グラフ</h2>
            {result.charts.map((ch, i) => (
              <div key={i}>
                <p className="muted">{ch.label}</p>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img className="chart" src={api.chartUrl(ch.path)} alt={ch.label} />
              </div>
            ))}
          </>
        )}

        {result.warnings.length > 0 && (
          <div style={{ marginTop: 16 }}>
            {result.warnings.map((w, i) => (
              <div key={i} className="sentence caution">
                ⚠ {w}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <h2>解釈サポート</h2>
        <p className="muted">結果を専門用語の少ない文章で自動解説します。</p>
        {interpretation.sentences.map((s, i) => (
          <div key={i} className={`sentence ${s.level}`}>
            {s.text}
          </div>
        ))}
      </div>
    </div>
  );
}

function fmt(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return Number.isInteger(v) ? String(v) : v.toFixed(4);
}

function extra(e: Record<string, number>): string {
  const parts: string[] = [];
  if (e.odds_ratio !== undefined) parts.push(`オッズ比 ${e.odds_ratio}`);
  if (e.vif !== undefined) parts.push(`VIF ${e.vif}`);
  return parts.length ? parts.join(" / ") : "—";
}
