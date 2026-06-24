"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { useRequireAuth } from "../lib/useRequireAuth";
import { Steps } from "../components/Steps";

type Dataset = {
  id: number;
  name: string;
  format: string;
  row_count: number;
  col_count: number;
};

export default function HomePage() {
  const ready = useRequireAuth();
  const router = useRouter();
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  function reload() {
    api.get("/datasets").then(setDatasets).catch(() => {});
  }
  useEffect(() => {
    if (ready) reload();
  }, [ready]);

  async function upload(file: File) {
    setError("");
    setUploading(true);
    try {
      const ds = await api.upload("/datasets", file);
      router.push(`/datasets/${ds.id}/profile`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "アップロードに失敗しました。");
    } finally {
      setUploading(false);
    }
  }

  async function remove(d: Dataset) {
    if (!confirm(`「${d.name}」を削除します。よろしいですか？`)) return;
    setError("");
    try {
      await api.del(`/datasets/${d.id}`);
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "削除に失敗しました。");
    }
  }

  if (!ready) return <p className="muted">読み込み中...</p>;

  return (
    <div>
      <Steps current={0} />
      <div className="card">
        <h1>データセット</h1>
        <p className="muted">CSV または Excel ファイルをアップロードして解析を始めます。</p>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,.xlsx,.xls"
          style={{ display: "none" }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) upload(f);
          }}
        />
        <button onClick={() => fileRef.current?.click()} disabled={uploading}>
          {uploading ? "アップロード中..." : "＋ ファイルをアップロード"}
        </button>
        {error && <p className="error">{error}</p>}
      </div>

      <div className="card">
        <h2>アップロード済み</h2>
        {datasets.length === 0 && <p className="muted">まだデータがありません。</p>}
        {datasets.map((d) => (
          <div key={d.id} className="dataset-item">
            <span className="name">{d.name}</span>
            <span className="muted">
              {d.format.toUpperCase()} / {d.row_count}行 × {d.col_count}列
            </span>
            <span className="spacer" />
            <Link href={`/datasets/${d.id}/profile`}>
              <button className="secondary">開く</button>
            </Link>
            <button className="danger" onClick={() => remove(d)}>
              削除
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
