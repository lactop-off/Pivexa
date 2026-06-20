"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "../../lib/api";
import { useRequireAuth } from "../../lib/useRequireAuth";

type U = { id: number; username: string; role: string };

export default function UsersPage() {
  const ready = useRequireAuth();
  const [users, setUsers] = useState<U[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  function reload() {
    api.get("/users").then(setUsers).catch(() => {});
  }
  useEffect(() => {
    if (ready) reload();
  }, [ready]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/users", { username, password });
      setUsername("");
      setPassword("");
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "作成に失敗しました。");
    }
  }

  async function remove(uid: number) {
    if (!confirm("このユーザーを削除しますか？")) return;
    try {
      await api.del(`/users/${uid}`);
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "削除に失敗しました。");
    }
  }

  if (!ready) return <p className="muted">読み込み中...</p>;

  return (
    <div>
      <div className="card">
        <h1>ユーザー管理</h1>
        <p className="muted">ロールは管理者のみです（MVP）。</p>
        {error && <p className="error">{error}</p>}
        <table>
          <thead>
            <tr>
              <th>ユーザー名</th>
              <th>ロール</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.username}</td>
                <td>{u.role}</td>
                <td style={{ textAlign: "right" }}>
                  <button className="danger" style={{ padding: "4px 12px" }} onClick={() => remove(u.id)}>
                    削除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>ユーザーを追加</h2>
        <form onSubmit={create} className="row" style={{ alignItems: "flex-end" }}>
          <div>
            <label>ユーザー名</label>
            <input value={username} onChange={(e) => setUsername(e.target.value)} />
          </div>
          <div>
            <label>パスワード</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div style={{ flex: "0 0 auto" }}>
            <button type="submit" disabled={!username || !password}>
              追加
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
