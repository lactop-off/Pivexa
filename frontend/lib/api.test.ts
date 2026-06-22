import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";

// fetch をモックして Response 風オブジェクトを返す。
function mockFetch(opts: {
  ok: boolean;
  status: number;
  ct?: string;
  json?: unknown; // undefined の場合 res.json() は失敗扱い（非JSONレスポンス）
  text?: string;
}) {
  const headers = {
    get: (k: string) =>
      k.toLowerCase() === "content-type" ? opts.ct ?? "" : null,
  };
  const res = {
    ok: opts.ok,
    status: opts.status,
    headers,
    json: async () => {
      if (opts.json === undefined) throw new SyntaxError("Unexpected token");
      return opts.json;
    },
    text: async () => opts.text ?? "",
  };
  const fn = vi.fn(async () => res as unknown as Response);
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("api client", () => {
  it("成功(JSON)時はパース済みオブジェクトを返す", async () => {
    const fn = mockFetch({ ok: true, status: 200, ct: "application/json", json: { hello: "world" } });
    const data = await api.get("/datasets");
    expect(data).toEqual({ hello: "world" });
    // 既定の API ベースは /api（同一オリジン）
    expect(fn).toHaveBeenCalledWith("/api/datasets", expect.objectContaining({ credentials: "include" }));
  });

  it("エラー応答(detail付きJSON)は detail をメッセージにした ApiError を投げる", async () => {
    mockFetch({ ok: false, status: 401, ct: "application/json", json: { detail: "認証が必要です。" } });
    const err = await api.get("/datasets").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(401);
    expect(err.message).toBe("認証が必要です。");
  });

  it("detailの無いJSONエラーは「エラー (status)」にフォールバックする", async () => {
    mockFetch({ ok: false, status: 422, ct: "application/json", json: { issues: [] } });
    const err = await api.post("/jobs", {}).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe("エラー (422)");
    // 元の構造化エラーは detail に保持される
    expect(err.detail).toEqual({ issues: [] });
  });

  it("非JSONエラー応答は本文テキストをメッセージにする", async () => {
    mockFetch({ ok: false, status: 502, ct: "text/html", text: "Bad Gateway" });
    const err = await api.get("/health").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(502);
    expect(err.message).toBe("Bad Gateway");
  });

  it("upload は FormData を POST し、成功時に JSON を返す", async () => {
    const fn = mockFetch({ ok: true, status: 201, ct: "application/json", json: { id: 7 } });
    const file = new File(["a,b\n1,2\n"], "d.csv", { type: "text/csv" });
    const res = await api.upload("/datasets", file);
    expect(res).toEqual({ id: 7 });
    const [, init] = fn.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(init.body).toBeInstanceOf(FormData);
  });
});
