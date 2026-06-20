import type { ReactNode } from "react";

export const metadata = {
  title: "Pivexa 統計解析ツール",
  description: "データをアップロードして実行するだけで統計解析",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ja">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0, background: "#f7f8fa" }}>
        <header style={{ background: "#1f2937", color: "#fff", padding: "12px 24px" }}>
          <strong>Pivexa</strong> 統計解析ツール
        </header>
        <main style={{ maxWidth: 960, margin: "0 auto", padding: 24 }}>{children}</main>
      </body>
    </html>
  );
}
