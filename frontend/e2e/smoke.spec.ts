import { test, expect } from "@playwright/test";
import os from "node:os";
import path from "node:path";
import fs from "node:fs";

// 起動中の compose スタック(:8080)に対して、ブラウザ実機で主要動線を検証する。
// ログイン資格情報は CI で起動した .env と一致させる（既定は e2e_smoke.sh と同じ）。
const USER = process.env.E2E_ADMIN_USER ?? "admin";
const PASS = process.env.E2E_ADMIN_PASSWORD ?? "e2e-admin-pass";

test("ログイン → アップロード → プロファイル表示", async ({ page }) => {
  // 認証必須ページは /login へリダイレクトされる。
  await page.goto("/login");

  // ログインフォーム（label に for が無いため位置/種別で特定）。
  await page.locator("input").first().fill(USER);
  await page.locator('input[type="password"]').fill(PASS);
  await page.getByRole("button", { name: "ログイン" }).click();

  // ホーム（アップロード画面）に遷移する。
  await expect(page.getByRole("button", { name: /ファイルをアップロード/ })).toBeVisible();

  // CSV を生成して隠しファイル入力へ流し込む（onChange でアップロードが走る）。
  const csv = path.join(os.tmpdir(), `e2e-${Date.now()}.csv`);
  const lines = ["ad_cost,sales"];
  for (let i = 0; i < 20; i++) lines.push(`${100 + i},${2 * (100 + i)}`);
  fs.writeFileSync(csv, lines.join("\n") + "\n");
  await page.setInputFiles('input[type="file"]', csv);

  // アップロード成功でプロファイル画面へ遷移し、列名が表示される。
  await page.waitForURL(/\/datasets\/\d+\/profile/);
  await expect(page.getByText("ad_cost")).toBeVisible();
  await expect(page.getByText("sales")).toBeVisible();
});
