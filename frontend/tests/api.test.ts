import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../src/api";

const jsonResponse = (body: unknown, init: ResponseInit = {}): Response =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiClient", () => {
  it("从共享版本接口读取产品版本", async () => {
    const version = {
      chinese2lean_version: "0.1.0",
      core_version: "0.1.0",
      desktop_version: "0.1.0",
      web_version: "0.1.0",
      lean_version: "4.19.0",
      mathlib_revision: "c44e0c8",
      dictionary_version: "0.1.0",
      ir_schema_version: "1",
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(version));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiClient.version()).resolves.toEqual(version);
    expect(fetchMock).toHaveBeenCalledWith("/api/version", {
      headers: { Accept: "application/json" },
    });
  });

  it("向共享转换接口提交输入和验证选择", async () => {
    const converted = {
      status: "VERIFIED",
      lean: "theorem demo : True := by trivial",
      ir: { theorem_name: "demo" },
      diagnostics: [],
      success: true,
      verified: true,
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(converted));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiClient.convert("# 定理\n真命题", true)).resolves.toEqual(converted);
    expect(fetchMock).toHaveBeenCalledWith("/api/convert", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ text: "# 定理\n真命题", verify: true }),
    });
  });

  it("从历史接口读取输入、时间、状态和输出", async () => {
    const records = [
      {
        id: 7,
        input_text: "任意实数 x，x = x。",
        created_at: "2026-07-16T10:00:00Z",
        status: "GENERATED",
        output: { lean: "theorem refl (x : Real) : x = x := by rfl" },
        versions: { core_version: "0.1.0" },
      },
    ];
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(records));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiClient.history()).resolves.toEqual(records);
    expect(fetchMock).toHaveBeenCalledWith("/api/history", {
      headers: { Accept: "application/json" },
    });
  });

  it("以原始请求体和 X-Filename 安全上传文件", async () => {
    const upload = { id: "upload-1", filename: "输入.md", text: "正文", size: 6 };
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      expect(() => new Headers(init?.headers)).not.toThrow();
      return Promise.resolve(jsonResponse(upload, { status: 201 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["正文"], "输入.md", { type: "text/markdown" });

    await expect(apiClient.upload(file)).resolves.toEqual(upload);
    expect(fetchMock).toHaveBeenCalledWith("/api/upload", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/octet-stream",
        "X-Filename": encodeURIComponent("输入.md"),
      },
      body: file,
    });
  });

  it("生成受控下载类型的同源 URL", () => {
    expect(apiClient.downloadUrl(12, "lean")).toBe("/api/history/12/download/lean");
    expect(apiClient.downloadUrl(12, "ir")).toBe("/api/history/12/download/ir");
    expect(apiClient.downloadUrl(12, "report")).toBe(
      "/api/history/12/download/report",
    );
  });

  it("向用户透传服务端 detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: "输入超过大小限制" }, { status: 422 }),
      ),
    );

    await expect(apiClient.convert("超长输入", false)).rejects.toThrow(
      "输入超过大小限制",
    );
  });

  it("服务端未提供 detail 时返回稳定中文错误", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("暂时不可用", { status: 503, statusText: "Service Unavailable" }),
      ),
    );

    await expect(apiClient.history()).rejects.toThrow("服务请求失败（HTTP 503）");
  });
});
