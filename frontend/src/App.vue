<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { apiClient } from "./api";
import type { ConvertResponse, HistoryRecord, ProductVersion } from "./types";

type ResultTab = "解析" | "IR" | "Lean" | "验证" | "日志";

const tabs: ResultTab[] = ["解析", "IR", "Lean", "验证", "日志"];
const examples = [
  {
    id: "real-positive",
    title: "实数正数加一",
    text: `# 定理名称
正数加一仍为正数

# 变量
x：实数

# 假设
hx：x > 0

# 结论
x + 1 > 0`,
  },
  {
    id: "nat-add",
    title: "自然数加法交换律",
    text: `# 定理名称
自然数加法交换律

# 变量
m：自然数
n：自然数

# 结论
m + n = n + m`,
  },
  {
    id: "integer-square",
    title: "整数平方非负",
    text: `# 定理名称
整数平方非负

# 变量
x：整数

# 结论
x ^ 2 ≥ 0`,
  },
] as const;

const source = ref<string>(examples[0].text);
const selectedExample = ref<string>(examples[0].id);
const result = ref<ConvertResponse | null>(null);
const version = ref<ProductVersion | null>(null);
const historyRecords = ref<HistoryRecord[]>([]);
const activeTab = ref<ResultTab>("解析");
const busy = ref(false);
const pageMessage = ref("");
const pageError = ref("");

const leanOutput = computed(() => result.value?.lean || result.value?.lean_code || "");
const resultVerified = computed(
  () => result.value?.status === "VERIFIED" && result.value?.verified === true,
);
const logOutput = computed(() => {
  if (!result.value) return "尚未产生转换日志。";
  const entries = [
    ...result.value.diagnostics.map((item) => ({ kind: "diagnostic", ...item })),
    ...result.value.warnings.map((item) => ({ kind: "warning", ...item })),
    ...result.value.repair_attempts.map((item) => ({ kind: "repair", ...item })),
  ];
  return entries.length === 0 ? "无诊断信息；未执行自动修复。" : JSON.stringify(entries, null, 2);
});

function formatJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

function formatTime(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("zh-CN", { hour12: false });
}

function historyLean(record: HistoryRecord): string {
  const output = record.output as Partial<ConvertResponse>;
  return output.lean || output.lean_code || "未生成 Lean 代码";
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    VERIFIED: "Lean Kernel 验证通过",
    GENERATED: "已生成，尚未验证",
    VERIFICATION_FAILED: "Lean 验证失败",
    PARSE_FAILED: "解析失败",
    NORMALIZATION_FAILED: "标准化失败",
    IR_INVALID: "IR 校验失败",
    AMBIGUOUS: "输入存在歧义",
  };
  return labels[status] ?? status;
}

async function loadVersion(): Promise<void> {
  try {
    version.value = await apiClient.version();
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : "无法读取版本信息。";
  }
}

async function loadHistory(): Promise<void> {
  try {
    historyRecords.value = await apiClient.history();
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : "无法读取历史记录。";
  }
}

async function runConversion(verify: boolean): Promise<void> {
  if (!source.value.trim()) {
    pageError.value = "请输入中文数学命题或证明。";
    return;
  }
  busy.value = true;
  pageError.value = "";
  pageMessage.value = verify ? "正在调用 Lean Kernel 验证……" : "正在解析并生成 Lean……";
  try {
    result.value = await apiClient.convert(source.value, verify);
    activeTab.value = result.value.status === "VERIFIED" ? "验证" : "解析";
    pageMessage.value = statusLabel(result.value.status);
    await loadHistory();
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : "转换请求失败。";
    pageMessage.value = "";
  } finally {
    busy.value = false;
  }
}

function chooseExample(): void {
  const example = examples.find((item) => item.id === selectedExample.value);
  if (example) {
    source.value = example.text;
    pageMessage.value = `已载入示例：${example.title}`;
    pageError.value = "";
  }
}

async function uploadFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  busy.value = true;
  pageError.value = "";
  try {
    const uploaded = await apiClient.upload(file);
    source.value = uploaded.text;
    selectedExample.value = "";
    pageMessage.value = `已安全载入 ${uploaded.filename}（${uploaded.size} 字节）`;
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : "文件上传失败。";
  } finally {
    busy.value = false;
    input.value = "";
  }
}

onMounted(() => {
  void loadVersion();
  void loadHistory();
});
</script>

<template>
  <div class="app-shell">
    <header class="site-header">
      <a class="brand" href="#top" aria-label="Chinese2Lean 首页">
        <span class="brand-mark" aria-hidden="true">中 → λ</span>
        <span>Chinese2Lean</span>
      </a>
      <nav aria-label="主导航">
        <a href="#editor">数学编辑</a>
        <a href="#result">转换结果</a>
        <a href="#history">历史记录</a>
      </nav>
      <span class="trust-pill"><span class="pulse-dot"></span>Lean Kernel 可信验证</span>
    </header>

    <main id="top">
      <section class="hero" aria-labelledby="hero-title">
        <div class="hero-copy">
          <p class="eyebrow">可追溯 · 可验证 · 不猜测</p>
          <h1 id="hero-title">从受控中文到可信 Lean 证明</h1>
          <p class="hero-lead">
            Chinese2Lean 将结构化中文数学命题转换为 Lean 4 + Mathlib 源码，
            并以真实 Lean Kernel 编译作为唯一成功标准。
          </p>
          <div class="hero-actions">
            <a class="primary-link" href="#editor">开始形式化</a>
            <a class="secondary-link" href="#scope">查看支持范围</a>
          </div>
        </div>
        <div class="proof-card" aria-label="转换流程示意">
          <div class="proof-card-header"><span></span><span></span><span></span></div>
          <p class="code-comment">-- 受控中文输入</p>
          <p>对任意实数 x，如果 x &gt; 0，</p>
          <p>那么 x + 1 &gt; 0。</p>
          <div class="flow-line"><span>normalize</span><span>parse</span><span>IR</span></div>
          <p class="code-comment">-- Lean 4 + Mathlib</p>
          <p><b>theorem</b> positive_add_one</p>
          <p class="indent">(x : ℝ) (h : x &gt; 0) :</p>
          <p class="indent">x + 1 &gt; 0 := by linarith</p>
          <p class="kernel-ok">✓ Lean Kernel 验证通过</p>
        </div>
      </section>

      <section class="workflow" aria-labelledby="workflow-title">
        <div class="section-heading">
          <p class="eyebrow">使用方式</p>
          <h2 id="workflow-title">三步完成形式化</h2>
        </div>
        <ol class="workflow-grid">
          <li><span>01</span><div><h3>输入中文</h3><p>粘贴受控中文、Markdown 数学证明，或载入本地文件与示例。</p></div></li>
          <li><span>02</span><div><h3>转换与验证</h3><p>统一后端调用核心流水线，生成 IR 和 Lean，并按需执行真实编译。</p></div></li>
          <li><span>03</span><div><h3>审阅与下载</h3><p>检查完整追踪、诊断与验证结果，下载 Lean、IR 和转换报告。</p></div></li>
        </ol>
      </section>

      <section id="scope" class="scope-section" aria-labelledby="scope-title">
        <div>
          <p class="eyebrow">明确边界</p>
          <h2 id="scope-title">受控中文数学范围</h2>
          <p>系统在文档化模板内工作；遇到歧义会返回稳定诊断，不会静默猜测。</p>
        </div>
        <div class="scope-columns">
          <article>
            <h3><span class="scope-icon supported">✓</span>当前支持</h3>
            <ul>
              <li>显式类型的 Nat / Int / Rat / Real 变量</li>
              <li>全称、存在、蕴含、合取与否定</li>
              <li>等式、不等式与基础算术表达式</li>
              <li>结构化 Markdown 和字段冲突检测</li>
            </ul>
          </article>
          <article>
            <h3><span class="scope-icon partial">◐</span>部分支持</h3>
            <ul>
              <li>析取与双条件</li>
              <li>简单确定性存在见证</li>
              <li>初步集合关系表达式</li>
            </ul>
          </article>
          <article>
            <h3><span class="scope-icon unsupported">×</span>当前不支持</h3>
            <ul>
              <li>不支持任意自然语言证明</li>
              <li>隐式变量和代词消解</li>
              <li>复杂集合、依赖类型与高等数学自动化</li>
            </ul>
          </article>
        </div>
      </section>

      <section class="version-strip" aria-labelledby="version-title">
        <div><p class="eyebrow">锁定环境</p><h2 id="version-title">当前版本</h2></div>
        <dl v-if="version" class="version-grid">
          <div><dt>Web</dt><dd>{{ version.web_version }}</dd></div>
          <div><dt>Core</dt><dd>{{ version.core_version }}</dd></div>
          <div><dt>Lean</dt><dd>{{ version.lean_version }}</dd></div>
          <div><dt>Mathlib</dt><dd :title="version.mathlib_revision">{{ version.mathlib_revision.slice(0, 8) }}</dd></div>
          <div><dt>词典</dt><dd>{{ version.dictionary_version }}</dd></div>
          <div><dt>IR Schema</dt><dd>{{ version.ir_schema_version }}</dd></div>
        </dl>
        <p v-else class="muted">正在从本地 API 读取锁定版本……</p>
      </section>

      <section id="editor" class="workspace-section" aria-labelledby="editor-title">
        <div class="section-heading split-heading">
          <div><p class="eyebrow">工作区</p><h2 id="editor-title">数学编辑</h2></div>
          <p>支持 Markdown、中文数学文本和公式符号；所有转换均经过共享 Core。</p>
        </div>
        <div class="editor-toolbar">
          <label>
            <span>内置示例</span>
            <select v-model="selectedExample" data-test="example-select" @change="chooseExample">
              <option value="" disabled>选择一个示例</option>
              <option v-for="example in examples" :key="example.id" :value="example.id">
                {{ example.title }}
              </option>
            </select>
          </label>
          <label class="file-button">
            <span>上传 .md / .txt</span>
            <input
              data-test="file-input"
              type="file"
              accept=".md,.txt,text/markdown,text/plain"
              :disabled="busy"
              @change="uploadFile"
            />
          </label>
        </div>
        <label class="editor-label" for="source-editor">中文数学命题或证明</label>
        <textarea
          id="source-editor"
          v-model="source"
          data-test="source-editor"
          spellcheck="false"
          :disabled="busy"
          placeholder="请输入结构化 Markdown 或受控中文数学命题……"
        ></textarea>
        <div class="editor-footer">
          <span>{{ source.length }} 字符</span>
          <div class="editor-actions">
            <button type="button" class="secondary-button" :disabled="busy" @click="runConversion(false)">
              解析并生成 Lean
            </button>
            <button
              type="button"
              class="primary-button"
              data-test="verify-button"
              :disabled="busy"
              @click="runConversion(true)"
            >
              {{ busy ? "处理中…" : "转换并验证" }}
            </button>
          </div>
        </div>
        <p v-if="pageMessage" class="notice" role="status">{{ pageMessage }}</p>
        <p v-if="pageError" class="error-notice" role="alert">{{ pageError }}</p>
      </section>

      <section id="result" class="result-section" aria-labelledby="result-title">
        <div class="section-heading split-heading">
          <div><p class="eyebrow">完整追踪</p><h2 id="result-title">转换结果</h2></div>
          <div
            v-if="result"
            data-test="result-status"
            class="result-status"
            :class="{ verified: resultVerified }"
          >
            {{ resultVerified ? "✓ Lean Kernel 验证通过" : statusLabel(result.status) }}
          </div>
        </div>
        <div v-if="result" class="result-panel">
          <div class="tabs" role="tablist" aria-label="转换结果">
            <button
              v-for="tab in tabs"
              :key="tab"
              type="button"
              role="tab"
              :aria-selected="activeTab === tab"
              :class="{ active: activeTab === tab }"
              :data-test="`tab-${tab}`"
              @click="activeTab = tab"
            >
              {{ tab }}
            </button>
          </div>
          <div class="tab-content" role="tabpanel">
            <div v-if="activeTab === '解析'" class="semantic-view">
              <h3>标准化文本</h3>
              <p>{{ result.normalized_text || "无标准化文本" }}</p>
              <h3>源文本追踪</h3>
              <pre>{{ result.source_text || source }}</pre>
            </div>
            <pre v-else-if="activeTab === 'IR'" data-test="ir-output"><code>{{ formatJson(result.ir) }}</code></pre>
            <pre v-else-if="activeTab === 'Lean'" data-test="lean-output" class="lean-code"><code>{{ leanOutput }}</code></pre>
            <div v-else-if="activeTab === '验证'" class="verification-view">
              <div :class="['verification-banner', resultVerified ? 'success' : 'failure']">
                <b>{{ statusLabel(result.status) }}</b>
                <span>状态码：{{ result.status }}</span>
              </div>
              <div v-if="result.diagnostics.length" class="diagnostic-list">
                <article v-for="(diagnostic, index) in result.diagnostics" :key="index">
                  <b>{{ String(diagnostic.code ?? diagnostic.severity ?? "诊断") }}</b>
                  <pre>{{ formatJson(diagnostic) }}</pre>
                </article>
              </div>
              <p v-else>未返回编译诊断。</p>
            </div>
            <pre v-else data-test="log-output"><code>{{ logOutput }}</code></pre>
          </div>
        </div>
        <div v-else class="empty-state">
          <span aria-hidden="true">λ</span>
          <h3>等待转换结果</h3>
          <p>在上方编辑输入，然后选择“解析并生成 Lean”或“转换并验证”。</p>
        </div>
      </section>

      <section id="history" class="history-section" aria-labelledby="history-title">
        <div class="section-heading split-heading">
          <div><p class="eyebrow">本地记录</p><h2 id="history-title">历史记录</h2></div>
          <button class="text-button" type="button" @click="loadHistory">刷新历史</button>
        </div>
        <div v-if="historyRecords.length" class="history-list">
          <article
            v-for="record in historyRecords"
            :key="record.id"
            :data-test="`history-${record.id}`"
            class="history-card"
          >
            <div class="history-meta">
              <span class="history-id">#{{ record.id }}</span>
              <time :datetime="record.created_at">{{ formatTime(record.created_at) }}</time>
              <span class="status-badge" :class="{ verified: record.status === 'VERIFIED' }">
                {{ record.status }}
              </span>
            </div>
            <div class="history-content">
              <div><h3>输入</h3><pre>{{ record.input_text }}</pre></div>
              <div><h3>输出</h3><pre>{{ historyLean(record) }}</pre></div>
            </div>
            <div class="download-actions" aria-label="下载输出文件">
              <a :href="apiClient.downloadUrl(record.id, 'lean')" :download="`history-${record.id}.lean`">.lean</a>
              <a :href="apiClient.downloadUrl(record.id, 'ir')" :download="`history-${record.id}.ir.json`">.ir.json</a>
              <a :href="apiClient.downloadUrl(record.id, 'report')" :download="`history-${record.id}.report.json`">.report.json</a>
            </div>
          </article>
        </div>
        <div v-else class="empty-state compact"><p>尚无本地转换历史。</p></div>
      </section>
    </main>

    <footer>
      <p>Chinese2Lean · 数学正确性优先 · Lean Kernel 是唯一数学正确性来源</p>
      <p>本地单用户产品界面；CORS 不等同于身份认证。</p>
    </footer>
  </div>
</template>
