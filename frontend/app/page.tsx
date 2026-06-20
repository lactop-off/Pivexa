"use client";

import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

/**
 * MVP のリファレンス画面（スケルトン）。
 * 「設定 → 実行 → 結果 → 解釈」の共通フローを最小構成で示す。
 * 本格的な画面（S-01〜S-10）は今後の実装で拡充する。
 */
export default function Home() {
  const [status, setStatus] = useState<string>("");

  async function ping() {
    try {
      const res = await fetch(`${API}/health`);
      const data = await res.json();
      setStatus(`API: ${data.status}`);
    } catch (e) {
      setStatus(`API へ接続できません: ${String(e)}`);
    }
  }

  return (
    <div>
      <h1>統計解析ツール（MVP スケルトン）</h1>
      <p>
        データをアップロードし、前処理 → 分析手法と変数を設定 → 実行 → 結果・解釈、の流れで利用します。
        本ページは疎通確認用のスケルトンです。
      </p>
      <ol>
        <li>データアップロード（CSV / Excel）</li>
        <li>自動プロファイリング・前処理（推奨値の提示）</li>
        <li>分析手法の選択（標準セット7手法）</li>
        <li>実行（重い処理は非同期）</li>
        <li>結果表示＋テンプレート解釈サポート</li>
        <li>PDF / 画像レポート出力</li>
      </ol>
      <button onClick={ping} style={{ padding: "8px 16px", cursor: "pointer" }}>
        API 疎通確認
      </button>
      {status && <p>{status}</p>}
    </div>
  );
}
