import { defineConfig } from "vitest/config";

// 単体テストは lib 配下の *.test.ts のみ対象（e2e/ の Playwright spec は除外）。
export default defineConfig({
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts"],
  },
});
