"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.post("/auth/login", { username, password });
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "ログインに失敗しました。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 360, margin: "60px auto" }}>
      <div className="card">
        <h1>Pivexa にログイン</h1>
        <p className="muted">統計解析ツール</p>
        <form onSubmit={submit}>
          <label>ユーザー名</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
          <label>パスワード</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={loading} style={{ marginTop: 16, width: "100%" }}>
            {loading ? "..." : "ログイン"}
          </button>
        </form>
      </div>
    </div>
  );
}
