import type { ReactNode } from "react";
import "./globals.css";
import { AppHeader } from "../components/AppHeader";

export const metadata = {
  title: "Pivexa 統計解析ツール",
  description: "データをアップロードして実行するだけで統計解析",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ja">
      <body>
        <AppHeader />
        <div className="container">{children}</div>
      </body>
    </html>
  );
}
