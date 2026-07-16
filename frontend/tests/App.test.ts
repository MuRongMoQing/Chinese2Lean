import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/App.vue";
import { apiClient } from "../src/api";
import type { ConvertResponse } from "../src/types";

vi.mock("../src/api", () => ({
  apiClient: {
    version: vi.fn(),
    convert: vi.fn(),
    history: vi.fn(),
    upload: vi.fn(),
    downloadUrl: vi.fn(
      (id: number, kind: string) => `/api/history/${id}/download/${kind}`,
    ),
  },
}));

const productVersion = {
  chinese2lean_version: "0.1.0",
  core_version: "0.1.0",
  desktop_version: "0.1.0",
  web_version: "0.1.0",
  lean_version: "4.19.0",
  mathlib_revision: "c44e0c8",
  dictionary_version: "0.1.0",
  ir_schema_version: "1",
};

const conversion = {
  status: "VERIFIED",
  success: true,
  verified: true,
  lean: "theorem positive_add_one (x : Real) (h : x > 0) : x + 1 > 0 := by\n  linarith",
  lean_code:
    "theorem positive_add_one (x : Real) (h : x > 0) : x + 1 > 0 := by\n  linarith",
  ir: {
    schema_version: 1,
    theorem: { name: "positive_add_one", variables: [{ name: "x", type: "Real" }] },
  },
  diagnostics: [],
  warnings: [],
  repair_attempts: [],
  terminology_mappings: [],
  name_mappings: {},
  lean_line_mappings: [],
  statement_hash: "known-statement-hash",
  selected_strategy: null,
  normalized_text: "对任意实数 x，如果 x > 0，那么 x + 1 > 0。",
  source_text: "对任意实数 x，如果 x > 0，那么 x + 1 > 0。",
  versions: productVersion,
} satisfies ConvertResponse;

const history = [
  {
    id: 7,
    input_text: "对任意实数 x，如果 x > 0，那么 x + 1 > 0。",
    created_at: "2026-07-16T09:30:00Z",
    status: "VERIFIED",
    output: conversion,
    versions: productVersion,
  },
];

describe("Chinese2Lean Web 产品页面", () => {
  beforeEach(() => {
    vi.mocked(apiClient.version).mockResolvedValue(productVersion);
    vi.mocked(apiClient.history).mockResolvedValue(history);
    vi.mocked(apiClient.convert).mockResolvedValue(conversion);
    vi.mocked(apiClient.upload).mockResolvedValue({
      id: "upload-1",
      filename: "proof.md",
      text: "# 定理\n\n对任意实数 x，如果 x > 0，那么 x + 1 > 0。",
      size: 72,
    });
  });

  it("启动后展示项目介绍、使用方式、当前版本和真实支持范围", async () => {
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.text()).toContain("Chinese2Lean");
    expect(wrapper.get("h1").text()).toContain("从受控中文到可信 Lean 证明");
    expect(wrapper.text()).toContain("从受控中文到可信 Lean 证明");
    expect(wrapper.text()).toContain("三步完成形式化");
    expect(wrapper.text()).toContain("当前版本");
    expect(wrapper.text()).toContain("Web");
    expect(wrapper.text()).toContain("0.1.0");
    expect(wrapper.text()).toContain("Lean");
    expect(wrapper.text()).toContain("4.19.0");
    expect(wrapper.text()).toContain("受控中文数学范围");
    expect(wrapper.text()).toContain("不支持任意自然语言证明");
    expect(apiClient.version).toHaveBeenCalledOnce();
  });

  it("调用转换 API，并在解析、IR、Lean、验证和日志五个标签展示结果", async () => {
    const wrapper = mount(App);
    await flushPromises();

    const source = "对任意实数 x，如果 x > 0，那么 x + 1 > 0。";
    await wrapper.get("[data-test='source-editor']").setValue(source);
    await wrapper.get("[data-test='verify-button']").trigger("click");
    await flushPromises();

    expect(apiClient.convert).toHaveBeenCalledWith(source, true);
    for (const label of ["解析", "IR", "Lean", "验证", "日志"]) {
      expect(wrapper.get(`[data-test='tab-${label}']`).text()).toBe(label);
    }

    expect(wrapper.get("[data-test='result-status']").text()).toContain("Lean Kernel 验证通过");
    await wrapper.get("[data-test='tab-Lean']").trigger("click");
    expect(wrapper.get("[data-test='lean-output']").text()).toContain("theorem positive_add_one");
    await wrapper.get("[data-test='tab-IR']").trigger("click");
    expect(wrapper.get("[data-test='ir-output']").text()).toContain('"schema_version": 1');
    await wrapper.get("[data-test='tab-日志']").trigger("click");
    expect(wrapper.get("[data-test='log-output']").text()).toContain("无诊断信息");
  });

  it("通过上传 API 载入 Markdown 文件并可选择内置示例", async () => {
    const wrapper = mount(App);
    await flushPromises();

    const file = new File(["# 定理"], "proof.md", { type: "text/markdown" });
    const input = wrapper.get<HTMLInputElement>("[data-test='file-input']");
    Object.defineProperty(input.element, "files", { value: [file] });
    await input.trigger("change");
    await flushPromises();

    expect(apiClient.upload).toHaveBeenCalledWith(file);
    expect(wrapper.get<HTMLTextAreaElement>("[data-test='source-editor']").element.value).toContain(
      "# 定理",
    );

    await wrapper.get<HTMLSelectElement>("[data-test='example-select']").setValue("real-positive");
    expect(wrapper.get<HTMLTextAreaElement>("[data-test='source-editor']").element.value).toContain(
      "x + 1 > 0",
    );
  });

  it("显示历史输入、时间、状态、输出并提供三种下载链接", async () => {
    const wrapper = mount(App);
    await flushPromises();

    const row = wrapper.get("[data-test='history-7']");
    expect(row.text()).toContain("对任意实数 x");
    expect(row.text()).toContain("2026");
    expect(row.text()).toContain("VERIFIED");
    expect(row.text()).toContain("theorem positive_add_one");

    const links = row.findAll("a[download]");
    expect(links.map((link) => link.attributes("download"))).toEqual([
      "history-7.lean",
      "history-7.ir.json",
      "history-7.report.json",
    ]);
    expect(links.map((link) => link.attributes("href"))).toEqual([
      "/api/history/7/download/lean",
      "/api/history/7/download/ir",
      "/api/history/7/download/report",
    ]);
  });
});
