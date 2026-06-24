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

// 補完 method のラベル。
const METHOD_LABEL: Record<string, string> = {
  median: "中央値",
  mean: "平均値",
  mode: "最頻値",
  missing_category: "「欠損」カテゴリ",
};

// 列ごとの操作選択。kind は UI 上の種別、method/to は付随パラメータ。
type ColOp = {
  kind: "none" | "drop_column" | "impute" | "cast";
  method: string; // impute 用
  to: string; // cast 用 ("numeric" | "categorical")
};

// 列型に応じた補完 method の候補を返す。
function imputeMethods(type: string): string[] {
  if (type === "numeric") return ["median", "mean", "mode"];
  return ["mode", "missing_category"];
}

// 推奨アクションを ColOp の初期値に変換する。
function defaultOp(c: Column): ColOp {
  const r = c.recommendation;
  if (r?.action === "drop_column") {
    return { kind: "drop_column", method: "median", to: "numeric" };
  }
  if (r?.action === "impute") {
    const fallback = imputeMethods(c.type)[0];
    return { kind: "impute", method: r.method ?? fallback, to: "numeric" };
  }
  return { kind: "none", method: imputeMethods(c.type)[0], to: "numeric" };
}

export default function ProfilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const ready = useRequireAuth();
  const router = useRouter();
  const [columns, setColumns] = useState<Column[]>([]);
  // 列名 → 選択中の操作。
  const [ops, setOps] = useState<Record<string, ColOp>>({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!ready) return;
    api
      .get(`/datasets/${id}/profile`)
      .then((res) => {
        setColumns(res.columns);
        // 推奨があればその操作を既定選択にする（ユーザーが上書き可）。
        const init: Record<string, ColOp> = {};
        res.columns.forEach((c: Column) => {
          init[c.name] = defaultOp(c);
        });
        setOps(init);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "取得に失敗しました。"));
  }, [ready, id]);

  // 指定列の操作を部分更新する。
  function setOp(name: string, patch: Partial<ColOp>) {
    setOps((s) => ({ ...s, [name]: { ...s[name], ...patch } }));
  }

  // 列の操作種別を切り替える。impute/cast に切り替えた際は妥当な既定パラメータを補う。
  function changeKind(c: Column, kind: ColOp["kind"]) {
    if (kind === "impute") {
      const cur = ops[c.name];
      const candidates = imputeMethods(c.type);
      const method = candidates.includes(cur?.method) ? cur.method : candidates[0];
      setOp(c.name, { kind, method });
    } else {
      setOp(c.name, { kind });
    }
  }

  // 選択内容から operations 配列を組み立てる。
  function buildOperations() {
    const out: Record<string, unknown>[] = [];
    for (const c of columns) {
      const op = ops[c.name];
      if (!op || op.kind === "none") continue;
      if (op.kind === "drop_column") {
        out.push({ type: "drop_column", column: c.name });
      } else if (op.kind === "impute") {
        out.push({ type: "impute", column: c.name, method: op.method });
      } else if (op.kind === "cast") {
        out.push({ type: "cast", column: c.name, to: op.to });
      }
    }
    return out;
  }

  async function proceed() {
    setSaving(true);
    setError("");
    try {
      const operations = buildOperations();
      if (operations.length > 0) {
        await api.post(`/datasets/${id}/preprocess`, { operations });
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
          各列の型・欠損・統計を自動で確認しました。列ごとに前処理を選べます。推奨がある列は既定で選択済みです。
        </p>
        {error && <p className="error">{error}</p>}
        <table>
          <thead>
            <tr>
              <th>列名</th>
              <th>型</th>
              <th className="num">欠損</th>
              <th>サマリー</th>
              <th>推奨</th>
              <th>前処理</th>
            </tr>
          </thead>
          <tbody>
            {columns.map((c) => {
              const op = ops[c.name] ?? { kind: "none", method: "median", to: "numeric" };
              return (
                <tr key={c.name}>
                  <td>{c.name}</td>
                  <td>{TYPE_LABEL[c.type] ?? c.type}</td>
                  <td className="num">{c.missing}</td>
                  <td className="muted">{summarize(c)}</td>
                  <td>
                    {c.recommendation ? (
                      <span className="muted" title={c.recommendation.reason}>
                        {actionLabel(c.recommendation.action, c.recommendation.method)}
                      </span>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      <select
                        aria-label={`${c.name} の前処理`}
                        style={{ width: "auto" }}
                        value={op.kind}
                        onChange={(e) => changeKind(c, e.target.value as ColOp["kind"])}
                      >
                        <option value="none">操作なし</option>
                        <option value="drop_column">列を削除</option>
                        <option value="impute">欠損補完</option>
                        <option value="cast">型変換</option>
                      </select>
                      {op.kind === "impute" && (
                        <select
                          aria-label={`${c.name} の補完方法`}
                          style={{ width: "auto" }}
                          value={op.method}
                          onChange={(e) => setOp(c.name, { method: e.target.value })}
                        >
                          {imputeMethods(c.type).map((m) => (
                            <option key={m} value={m}>
                              {METHOD_LABEL[m] ?? m}
                            </option>
                          ))}
                        </select>
                      )}
                      {op.kind === "cast" && (
                        <select
                          aria-label={`${c.name} の変換先`}
                          style={{ width: "auto" }}
                          value={op.to}
                          onChange={(e) => setOp(c.name, { to: e.target.value })}
                        >
                          <option value="numeric">数値へ</option>
                          <option value="categorical">カテゴリへ</option>
                        </select>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
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
  if (action === "impute") {
    return `${METHOD_LABEL[method ?? ""] ?? "中央値"}で補完`;
  }
  return action;
}
