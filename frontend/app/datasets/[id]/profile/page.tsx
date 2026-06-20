"use client";

import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import { api, ApiError, type Column } from "../../../../lib/api";
import { useRequireAuth } from "../../../../lib/useRequireAuth";
import { Steps } from "../../../../components/Steps";

const TYPE_LABEL: Record<string, string> = {
  numeric: "数値",
  datetime: "日付",
  categorical: "カテゴリ",
};

export default function ProfilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const ready = useRequireAuth();
  const router = useRouter();
  const [columns, setColumns] = useState<Column[]>([]);
  const [applied, setApplied] = useState<Record<string, boolean>>({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!ready) return;
    api
      .get(`/datasets/${id}/profile`)
      .then((res) => {
        setColumns(res.columns);
        // 推奨があるものはデフォルトで適用ON
        const init: Record<string, boolean> = {};
        res.columns.forEach((c: Column) => {
          if (c.recommendation) init[c.name] = true;
        });
        setApplied(init);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "取得に失敗しました。"));
  }, [ready, id]);

  function buildOperations() {
    const ops: Record<string, unknown>[] = [];
    for (const c of columns) {
      if (!c.recommendation || !applied[c.name]) continue;
      const r = c.recommendation;
      if (r.action === "drop_column") {
        ops.push({ type: "drop_column", column: c.name });
      } else if (r.action === "impute") {
        ops.push({ type: "impute", column: c.name, method: r.method ?? "median" });
      }
    }
    return ops;
  }

  async function proceed() {
    setSaving(true);
    setError("");
    try {
      const ops = buildOperations();
      if (ops.length > 0) {
        await api.post(`/datasets/${id}/preprocess`, { operations: ops });
      }
      router.push(`/datasets/${id}/analyze`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "保存に失敗しました。");
    } finally {
      setSaving(false);
    }
  }

  if (!ready) return <p className="muted">読み込み中...</p>;

  return (
    <div>
      <Steps current={1} />
      <div className="card">
        <h1>データプロファイル・前処理</h1>
        <p className="muted">
          各列の型・欠損・統計を自動で確認しました。推奨される前処理は既定でオンになっています。
        </p>
        {error && <p className="error">{error}</p>}
        <table>
          <thead>
            <tr>
              <th>列名</th>
              <th>型</th>
              <th className="num">欠損</th>
              <th>サマリー</th>
              <th>推奨アクション</th>
              <th>適用</th>
            </tr>
          </thead>
          <tbody>
            {columns.map((c) => (
              <tr key={c.name}>
                <td>{c.name}</td>
                <td>{TYPE_LABEL[c.type] ?? c.type}</td>
                <td className="num">{c.missing}</td>
                <td className="muted">{summarize(c)}</td>
                <td>
                  {c.recommendation ? (
                    <span title={c.recommendation.reason}>
                      {actionLabel(c.recommendation.action, c.recommendation.method)}
                    </span>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>
                  {c.recommendation && (
                    <input
                      type="checkbox"
                      style={{ width: "auto" }}
                      checked={!!applied[c.name]}
                      onChange={(e) =>
                        setApplied((s) => ({ ...s, [c.name]: e.target.checked }))
                      }
                    />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button onClick={proceed} disabled={saving} style={{ marginTop: 16 }}>
          {saving ? "..." : "前処理を適用して分析へ進む →"}
        </button>
      </div>
    </div>
  );
}

function summarize(c: Column): string {
  const s = c.summary || {};
  if (c.type === "numeric" && s.mean !== undefined) {
    return `平均 ${s.mean} / 範囲 ${s.min}〜${s.max}`;
  }
  if (s.unique !== undefined) return `ユニーク ${s.unique} 種`;
  return "";
}

function actionLabel(action: string, method?: string): string {
  if (action === "drop_column") return "列を削除";
  if (action === "impute") return method === "mode" ? "最頻値で補完" : "中央値で補完";
  return action;
}
