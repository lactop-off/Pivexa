"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

export function AppHeader() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<{ username: string } | null>(null);

  useEffect(() => {
    api
      .get("/auth/me")
      .then((u) => setUser(u))
      .catch(() => setUser(null));
  }, [pathname]);

  async function logout() {
    await api.post("/auth/logout");
    setUser(null);
    router.push("/login");
  }

  if (pathname === "/login") return null;

  return (
    <header className="appbar">
      <span className="brand">Pivexa</span>
      <nav>
        <Link href="/">データセット</Link>
        <Link href="/users">ユーザー管理</Link>
      </nav>
      <span className="spacer" />
      {user && <span className="user">{user.username}</span>}
      {user && (
        <button className="secondary" onClick={logout} style={{ padding: "4px 12px" }}>
          ログアウト
        </button>
      )}
    </header>
  );
}
