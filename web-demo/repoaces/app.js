const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const caseData = {
  title: "FastGPT PR #7008 - code-sandbox queueId 并发控制",
  repo: "https://github.com/labring/FastGPT",
  baseline: "4af1ef77674851e30478bef5a9e5cb6ded6db660",
  golden: "bd140f7144d9fe979b866740859a0e18b9659e87",
  requirement:
    "为 FastGPT code-sandbox 的 /sandbox/js 与 /sandbox/python 执行接口增加可选 queueId 字段，并通过 SANDBOX_QUEUE_ID_CONCURRENCY 控制同一 queueId 的并发进入执行流程数量。默认不启用，未传 queueId 时保持历史行为；同一 queueId 超限时 FIFO 排队，不同 queueId 之间互不阻塞；同时补充类型、调用端透传和测试验证。"
};

const analysisCards = [
  {
    title: "需求摘要",
    items: [
      "在 code-sandbox 的 JS/Python 执行接口中增加可选 queueId。",
      "通过 SANDBOX_QUEUE_ID_CONCURRENCY 控制同一 queueId 的并发。",
      "未配置环境变量或未传 queueId 时保持历史行为。"
    ]
  },
  {
    title: "验收标准",
    items: [
      "同一 queueId 超限后 FIFO 等待。",
      "不同 queueId 之间可以并发执行。",
      "queueId 非字符串或超长时返回 400。",
      "服务调用端能够透传 queueId。"
    ]
  },
  {
    title: "任务拆解",
    items: [
      "定位 code-sandbox 的 API 层和服务调用端。",
      "设计 QueueIdLimiter，不侵入工作进程池生命周期。",
      "补充环境变量、类型、schema、README 和测试。",
      "运行目标测试并对齐基准PR。"
    ]
  },
  {
    title: "风险与门禁",
    items: [
      "避免把业务队列逻辑塞入 BaseProcessPool。",
      "避免 README 全文件重写。",
      "测试需覆盖 FIFO、跨 queueId 并发、未传 queueId 兼容。",
      "Windows sh 缺失属于环境风险，不判定功能失败。"
    ]
  }
];

const graphNodes = [
  {
    id: "req",
    label: "需求节点",
    path: "queueId 并发需求",
    desc: "新增 queueId 维度的请求排队能力，同时保持历史接口兼容。",
    type: "api",
    x: 74,
    y: 72,
    tags: ["功能需求", "验收标准"]
  },
  {
    id: "index",
    label: "src/index.ts",
    path: "projects/code-sandbox/src/index.ts",
    desc: "Hono API 入口，负责请求体解析、schema 校验、认证、日志和调用 JS/Python 进程池。",
    type: "api",
    x: 330,
    y: 72,
    tags: ["API层", "Hono"]
  },
  {
    id: "schema",
    label: "executeSchema",
    path: "projects/code-sandbox/src/index.ts",
    desc: "新增 queueId schema：去除前后空白，空字符串转为未传，限制最大长度，非字符串走 400。",
    type: "api",
    x: 578,
    y: 72,
    tags: ["zod", "输入校验"]
  },
  {
    id: "limiter",
    label: "QueueIdLimiter",
    path: "projects/code-sandbox/src/utils/queue-id-limiter.ts",
    desc: "按 queueId 维护 FIFO 等待队列和运行计数，未启用或无 queueId 时直接旁路。",
    type: "core",
    x: 330,
    y: 230,
    tags: ["FIFO", "按 queueId", "API边界"]
  },
  {
    id: "env",
    label: "队列并发配置",
    path: "projects/code-sandbox/src/env.ts",
    desc: "可选环境变量，配置后启用同 queueId 并发限制，默认关闭。",
    type: "config",
    x: 74,
    y: 230,
    tags: ["配置", "默认关闭"]
  },
  {
    id: "pool",
    label: "进程池",
    path: "ProcessPool / PythonProcessPool",
    desc: "真实工作进程分配仍由现有进程池处理，queueId 限制器只控制进入执行流程。",
    type: "core",
    x: 586,
    y: 230,
    tags: ["工作进程生命周期", "不改动"]
  },
  {
    id: "types",
    label: "ExecuteOptions",
    path: "projects/code-sandbox/src/types.ts",
    desc: "新增 queueId?: string 类型字段，供 API 层和进程池 execute 选项共享。",
    type: "client",
    x: 840,
    y: 72,
    tags: ["类型定义"]
  },
  {
    id: "client",
    label: "服务调用入口",
    path: "packages/service/thirdProvider/codeSandbox/index.ts",
    desc: "FastGPT 服务侧 HTTP 调用端增加 queueId 可选参数，并透传到 sandbox 执行接口。",
    type: "client",
    x: 842,
    y: 230,
    tags: ["服务调用端", "参数透传"]
  },
  {
    id: "unit",
    label: "限制器单元测试",
    path: "projects/code-sandbox/test/unit/queue-id-limiter.test.ts",
    desc: "覆盖未启用、相同 queueId FIFO、不同 queueId 独立、空 queueId 旁路和非法配置。",
    type: "test",
    x: 196,
    y: 420,
    tags: ["单元测试", "FIFO"]
  },
  {
    id: "apiTest",
    label: "HTTP API 测试",
    path: "projects/code-sandbox/test/integration/api.test.ts",
    desc: "启动真实 Hono 服务并验证同 queueId 串行、不同 queueId 并行、未传 queueId 不受限。",
    type: "test",
    x: 486,
    y: 420,
    tags: ["集成测试", "HTTP"]
  },
  {
    id: "golden",
    label: "基准PR #7008",
    path: "bd140f7144d9fe979b866740859a0e18b9659e87",
    desc: "作为功能正确性和变更边界的基准目标。",
    type: "test",
    x: 780,
    y: 420,
    tags: ["基准PR", "评测"]
  }
];

const graphEdges = [
  ["req", "index"],
  ["index", "schema"],
  ["schema", "types"],
  ["env", "limiter"],
  ["index", "limiter"],
  ["limiter", "pool"],
  ["types", "client"],
  ["client", "index"],
  ["limiter", "unit"],
  ["index", "apiTest"],
  ["unit", "golden"],
  ["apiTest", "golden"]
];

const agents = [
  {
    id: "planner",
    name: "规划智能体",
    role: "需求理解、验收标准、阶段状态机",
    output: "queueId 并发能力被拆解为 API、schema、调用端和测试四类任务。"
  },
  {
    id: "repo",
    name: "仓库分析智能体",
    role: "代码知识图谱、调用链、影响范围",
    output: "定位 code-sandbox 的 API 层和服务侧 HTTP 调用端。"
  },
  {
    id: "architect",
    name: "架构评审智能体",
    role: "实现边界、风险控制、方案评审",
    output: "限制器放在 API 层，不修改工作进程池生命周期。"
  },
  {
    id: "coder",
    name: "编码智能体",
    role: "调用 OpenHands/Codex 执行代码修改",
    output: "生成 QueueIdLimiter、schema、环境变量、类型、调用端和测试补丁。"
  },
  {
    id: "tester",
    name: "测试计划智能体",
    role: "结构化测试计划、测试命令、验收用例",
    output: "生成 IEEE 风格测试计划，覆盖正向、负向和回归。"
  },
  {
    id: "diagnoser",
    name: "诊断智能体",
    role: "失败日志摘要、SOP 诊断、自修复建议",
    output: "识别 Windows spawn sh 是环境失败，不是功能失败。"
  },
  {
    id: "reviewer",
    name: "审查智能体",
    role: "补丁差异审查、质量门禁、文档范围控制",
    output: "阻止 README 过度重写，标注 naive openhands 风险。"
  },
  {
    id: "evaluator",
    name: "评测智能体",
    role: "基准PR对比、评分、案例沉淀",
    output: "RepoACES 目标测试 37/37 通过，基准PR对齐度高。"
  }
];

const agentTimeline = [
  ["00:00", "规划智能体", "解析需求：queueId 是业务维度限流，不应污染工作进程池抽象。"],
  ["00:18", "仓库分析智能体", "定位 API 入口、环境变量、ExecuteOptions 和 CodeSandbox.runCode。"],
  ["00:41", "架构评审智能体", "确认实现边界：HTTP API -> QueueIdLimiter -> ProcessPool。"],
  ["01:12", "编码智能体", "生成 QueueIdLimiter 与 API、schema、调用端变更。"],
  ["01:44", "测试计划智能体", "根据 PR 描述、变更函数摘要生成结构化测试计划。"],
  ["02:16", "诊断智能体", "处理 pnpm/corepack 和 Windows sh 环境失败，切换 Linux 容器验证。"],
  ["02:58", "审查智能体", "对比 naive openhands 与 RepoACES，标记错层修改和测试缺口。"],
  ["03:30", "评测智能体", "输出补丁、测试报告、基准PR差异和可复现案例。"]
];

const runs = {
  openhands: {
    title: "naive openhands",
    heading: "naive openhands 智能体画布",
    logs: [
      ["15:16:59", "INFO", "智能体画布容器已启动，并完成 API schema 采集。"],
      ["15:29:21", "INFO", "已通过 OpenAI 兼容基础 URL 验证模型路由。"],
      ["15:30:32", "WARN", "直接调用子智能体任务工具失败：出现 unexpected conv_state 参数。"],
      ["15:34:20", "INFO", "已为 FastGPT PR #7008 创建主会话。"],
      ["15:36:02", "INFO", "开始检索仓库，随后在容器中安装 ripgrep。"],
      ["15:39:10", "WARN", "补丁触及 BaseProcessPool 和运行时 sandbox 调用端，存在实现边界风险。"],
      ["15:40:24", "FAIL", "单元测试文件受损：Semaphore import 被替换，但旧测试仍然保留。"],
      ["15:41:09", "WARN", "pnpm/corepack 交互提示中断，测试实际没有运行。"],
      ["15:52:39", "FAIL", "候选补丁已保存为 openhands-run1.patch，但实现不完整。"]
    ],
    findings: [
      ["具备编排验证价值", "OpenHands 能进入真实仓库、检查文件、编辑代码，并产出候选补丁。"],
      ["实现边界错误", "queueId 逻辑被放入 BaseProcessPool，而不是放在 API 层。"],
      ["质量门禁未通过", "TypeScript 字段被移除，测试文件受损，README 被过度重写，且测试没有真正运行。"],
      ["系统设计启发", "RepoACES 应保留 OpenHands 作为执行底座，同时补足仓库理解、测试计划、诊断和审查智能体。"]
    ]
  },
  codex: {
    title: "RepoACES",
    heading: "RepoACES 基线重做实现",
    logs: [
      ["16:00:11", "INFO", "从基线 4af1ef7 创建干净工作区 pr7008-run-002。"],
      ["16:06:34", "INFO", "检查基准PR以及基线中的 API、调用端和测试文件。"],
      ["16:12:10", "INFO", "新增 QueueIdLimiter，支持按 queueId FIFO 排队和默认旁路行为。"],
      ["16:14:18", "INFO", "将限制器接入 /sandbox/js 和 /sandbox/python 的 API 层。"],
      ["16:15:21", "INFO", "扩展环境变量、ExecuteOptions 和 CodeSandbox.runCode 的 queueId 透传。"],
      ["16:17:38", "WARN", "Windows 目标测试被基线 spawn('sh') 环境问题阻塞。"],
      ["16:24:12", "INFO", "Linux 容器目标测试通过：2 个文件，37 个测试。"],
      ["16:30:39", "INFO", "已保存 codex-run2.patch 和 codex-run2-evaluation.md。"]
    ],
    findings: [
      ["实现与基准PR对齐", "限制器位于 HTTP API 和 ProcessPool 之间，保留工作进程生命周期语义。"],
      ["补丁范围聚焦", "只修改代码、测试、环境变量、类型、调用端和 README 中的一行说明，避免无关大范围改动。"],
      ["目标测试通过", "queue-id-limiter 单元测试和 HTTP API 集成测试已在 Linux 容器中通过。"],
      ["剩余风险已记录", "完整 code-sandbox 测试集中存在 process-pool/resource-limit 环境失败，与 queueId 逻辑无关。"]
    ]
  }
};

const patchData = {
  codex: {
    title: "RepoACES 补丁",
    status: "与基准PR对齐",
    pill: "pass",
    files: [
      ["A", "projects/code-sandbox/src/utils/queue-id-limiter.ts", "FIFO 限制器"],
      ["M", "projects/code-sandbox/src/index.ts", "API 层接入"],
      ["M", "projects/code-sandbox/src/env.ts", "环境变量"],
      ["M", "projects/code-sandbox/src/types.ts", "queueId 选项"],
      ["M", "packages/service/thirdProvider/codeSandbox/index.ts", "调用端透传"],
      ["A", "projects/code-sandbox/test/unit/queue-id-limiter.test.ts", "单元测试"],
      ["M", "projects/code-sandbox/test/integration/api.test.ts", "HTTP 测试"],
      ["M", "projects/code-sandbox/vitest.config.ts", "测试环境"],
      ["M", "projects/code-sandbox/README.md", "新增一行环境变量说明"]
    ],
    diff: `diff --git a/projects/code-sandbox/src/index.ts b/projects/code-sandbox/src/index.ts
@@
+import { QueueIdLimiter } from './utils/queue-id-limiter';
@@
+const queueIdSchema = z.preprocess((value) => {
+  if (typeof value !== 'string') return value;
+  const queueId = value.trim();
+  return queueId || undefined;
+}, z.string().max(128).optional());
+
 const executeSchema = z.object({
   code: z.string().min(1).max(5 * 1024 * 1024),
-  variables: z.record(z.string(), z.any()).default({})
+  variables: z.record(z.string(), z.any()).default({}),
+  queueId: queueIdSchema
 });
@@
+const queueIdLimiter = new QueueIdLimiter(env.SANDBOX_QUEUE_ID_CONCURRENCY);
@@
-const result = await jsPool.execute(parsed.data as ExecuteOptions);
+const result = await queueIdLimiter.run(parsed.data.queueId, () =>
+  jsPool.execute(parsed.data as ExecuteOptions)
+);

diff --git a/projects/code-sandbox/src/utils/queue-id-limiter.ts b/projects/code-sandbox/src/utils/queue-id-limiter.ts
+export class QueueIdLimiter {
+  private readonly queues = new Map<string, QueueState>();
+  async run<T>(queueId: string | undefined, task: () => Promise<T>): Promise<T> {
+    if (!this.enabled || !queueId) return task();
+    await this.acquire(queueId);
+    try { return await task(); }
+    finally { this.release(queueId); }
+  }
+}`
  },
  openhands: {
    title: "naive openhands 补丁",
    status: "候选失败",
    pill: "fail",
    files: [
      ["M", "packages/service/core/ai/sandbox/service/runtime.ts", "服务路径错误"],
      ["M", "projects/code-sandbox/src/pool/base-process-pool.ts", "抽象层错误"],
      ["A", "projects/code-sandbox/src/utils/queue-limiter.ts", "限制器不完整"],
      ["M", "projects/code-sandbox/test/unit/semaphore.test.ts", "测试受损"],
      ["M", "projects/code-sandbox/README.md", "过度重写"],
      ["M", "projects/code-sandbox/test/integration/api.test.ts", "覆盖不足"]
    ],
    diff: `diff --git a/projects/code-sandbox/src/pool/base-process-pool.ts b/projects/code-sandbox/src/pool/base-process-pool.ts
@@
+// 队列限制器被加入 worker 进程池层
+// 风险：业务层 queueId 概念被耦合进 worker 生命周期。

diff --git a/projects/code-sandbox/test/unit/semaphore.test.ts b/projects/code-sandbox/test/unit/semaphore.test.ts
@@
-import { Semaphore } from '../../src/utils/semaphore';
+import { QueueConcurrencyLimiter } from '../../src/utils/queue-limiter';
@@
 const sem = new Semaphore(3);
 // 风险：旧 Semaphore 测试仍然保留，导致编译失败。

diff --git a/packages/service/core/ai/sandbox/service/runtime.ts b/packages/service/core/ai/sandbox/service/runtime.ts
@@
-private readonly sandboxId: string;
-private readonly providerName: string;
-private readonly provider: SandboxProvider;
 // 风险：字段被移除，但构造函数和方法仍在使用。`
  },
  golden: {
    title: "基准PR #7008",
    status: "参考实现",
    pill: "ready",
    files: [
      ["A", "projects/code-sandbox/src/utils/queue-id-limiter.ts", "参考限制器"],
      ["M", "projects/code-sandbox/src/index.ts", "API 层限制器"],
      ["M", "packages/service/thirdProvider/codeSandbox/index.ts", "queueId 透传"],
      ["A", "projects/code-sandbox/test/unit/queue-id-limiter.test.ts", "参考测试"],
      ["M", "projects/code-sandbox/test/integration/api.test.ts", "HTTP 队列测试"],
      ["M", "document/content/self-host/upgrading/4-15/41503.mdx", "文档"]
    ],
    diff: `基准PR实现模式：

HTTP 请求
  -> zod executeSchema 校验可选 queueId
  -> QueueIdLimiter.run(queueId, task)
  -> jsPool.execute / pythonPool.execute
  -> worker 进程池 waitQueue

关键对比：
+ RepoACES 符合 API 层实现边界。
+ RepoACES 保持 README 变更最小化。
+ RepoACES 包含 FIFO 和不同 queue 的 HTTP 测试。
- naive openhands 把排队逻辑放入 BaseProcessPool，并破坏了测试。`
  }
};

const patchFileDiffs = {
  codex: {
    "projects/code-sandbox/src/utils/queue-id-limiter.ts": `diff --git a/projects/code-sandbox/src/utils/queue-id-limiter.ts b/projects/code-sandbox/src/utils/queue-id-limiter.ts
new file mode 100644
@@
+type QueueState = { running: number; waiters: Array<() => void> };
+
+export class QueueIdLimiter {
+  private readonly queues = new Map<string, QueueState>();
+  constructor(private readonly concurrency?: number) {}
+
+  async run<T>(queueId: string | undefined, task: () => Promise<T>): Promise<T> {
+    if (!this.enabled || !queueId) return task();
+    await this.acquire(queueId);
+    try { return await task(); }
+    finally { this.release(queueId); }
+  }
+}`,
    "projects/code-sandbox/src/index.ts": `diff --git a/projects/code-sandbox/src/index.ts b/projects/code-sandbox/src/index.ts
@@
+import { QueueIdLimiter } from './utils/queue-id-limiter';
+
+const queueIdSchema = z.preprocess((value) => {
+  if (typeof value !== 'string') return value;
+  const queueId = value.trim();
+  return queueId || undefined;
+}, z.string().max(128).optional());
@@
   code: z.string().min(1).max(5 * 1024 * 1024),
-  variables: z.record(z.string(), z.any()).default({})
+  variables: z.record(z.string(), z.any()).default({}),
+  queueId: queueIdSchema
@@
+const queueIdLimiter = new QueueIdLimiter(env.SANDBOX_QUEUE_ID_CONCURRENCY);
+const result = await queueIdLimiter.run(parsed.data.queueId, () =>
+  jsPool.execute(parsed.data as ExecuteOptions)
+);`,
    "projects/code-sandbox/src/env.ts": `diff --git a/projects/code-sandbox/src/env.ts b/projects/code-sandbox/src/env.ts
@@
 export const envSchema = z.object({
   SANDBOX_WORKER_MAX_MEMORY: z.coerce.number().optional(),
+  SANDBOX_QUEUE_ID_CONCURRENCY: z.coerce.number().int().positive().optional()
 });
@@
+// 未配置时保持历史行为，不启用 queueId 并发控制。`,
    "projects/code-sandbox/src/types.ts": `diff --git a/projects/code-sandbox/src/types.ts b/projects/code-sandbox/src/types.ts
@@
 export interface ExecuteOptions {
   code: string;
   variables?: Record<string, unknown>;
+  queueId?: string;
 }
@@
+// queueId 只作为 API 层限流维度，不改变 worker 进程池协议。`,
    "packages/service/thirdProvider/codeSandbox/index.ts": `diff --git a/packages/service/thirdProvider/codeSandbox/index.ts b/packages/service/thirdProvider/codeSandbox/index.ts
@@
 export type RunCodeOptions = {
   code: string;
   variables?: Record<string, unknown>;
+  queueId?: string;
 };
@@
   return this.client.post(endpoint, {
     code: options.code,
-    variables: options.variables
+    variables: options.variables,
+    queueId: options.queueId
   });`,
    "projects/code-sandbox/test/unit/queue-id-limiter.test.ts": `diff --git a/projects/code-sandbox/test/unit/queue-id-limiter.test.ts b/projects/code-sandbox/test/unit/queue-id-limiter.test.ts
new file mode 100644
@@
+describe('QueueIdLimiter', () => {
+  it('serializes tasks with the same queueId by FIFO order', async () => {
+    const limiter = new QueueIdLimiter(1);
+    const order: string[] = [];
+    await Promise.all([
+      limiter.run('chat-a', async () => order.push('first')),
+      limiter.run('chat-a', async () => order.push('second'))
+    ]);
+    expect(order).toEqual(['first', 'second']);
+  });
+});`,
    "projects/code-sandbox/test/integration/api.test.ts": `diff --git a/projects/code-sandbox/test/integration/api.test.ts b/projects/code-sandbox/test/integration/api.test.ts
@@
+it('serializes same queueId requests and allows different queueId requests', async () => {
+  process.env.SANDBOX_QUEUE_ID_CONCURRENCY = '1';
+  const sameQueue = post('/sandbox/js', { code: delayedCode, queueId: 'same' });
+  const blocked = post('/sandbox/js', { code: delayedCode, queueId: 'same' });
+  const otherQueue = post('/sandbox/js', { code: delayedCode, queueId: 'other' });
+  await expect(otherQueue).resolves.toMatchObject({ status: 200 });
+  await Promise.all([sameQueue, blocked]);
+});`,
    "projects/code-sandbox/vitest.config.ts": `diff --git a/projects/code-sandbox/vitest.config.ts b/projects/code-sandbox/vitest.config.ts
@@
 export default defineConfig({
   test: {
     environment: 'node',
+    isolate: true,
+    restoreMocks: true
   }
 });`,
    "projects/code-sandbox/README.md": `diff --git a/projects/code-sandbox/README.md b/projects/code-sandbox/README.md
@@
 | SANDBOX_WORKER_MAX_MEMORY | Worker memory limit | optional |
+| SANDBOX_QUEUE_ID_CONCURRENCY | Max concurrent executions for the same queueId | optional |
@@
+未配置该变量时，所有请求保持历史执行路径。`
  },
  openhands: {
    "packages/service/core/ai/sandbox/service/runtime.ts": `diff --git a/packages/service/core/ai/sandbox/service/runtime.ts b/packages/service/core/ai/sandbox/service/runtime.ts
@@
-private readonly sandboxId: string;
-private readonly providerName: string;
-private readonly provider: SandboxProvider;
@@
+// 风险：字段被删除，但构造函数和后续方法仍引用这些字段。
+// 结果：候选补丁存在类型错误和运行时风险。`,
    "projects/code-sandbox/src/pool/base-process-pool.ts": `diff --git a/projects/code-sandbox/src/pool/base-process-pool.ts b/projects/code-sandbox/src/pool/base-process-pool.ts
@@
+// naive openhands 将 queueId 排队逻辑放入 BaseProcessPool。
+// 风险：业务维度泄漏到 worker 进程池抽象中。
+private readonly queueLimiter = new QueueConcurrencyLimiter();
@@
-return this.executeInProcess(options);
+return this.queueLimiter.run(options.queueId, () => this.executeInProcess(options));`,
    "projects/code-sandbox/src/utils/queue-limiter.ts": `diff --git a/projects/code-sandbox/src/utils/queue-limiter.ts b/projects/code-sandbox/src/utils/queue-limiter.ts
new file mode 100644
@@
+export class QueueConcurrencyLimiter {
+  private queues = new Map<string, Promise<void>>();
+  async run<T>(queueId: string | undefined, task: () => Promise<T>) {
+    // 风险：没有完整的 FIFO waiters 管理，也没有失败释放验证。
+    if (!queueId) return task();
+    return task();
+  }
+}`,
    "projects/code-sandbox/test/unit/semaphore.test.ts": `diff --git a/projects/code-sandbox/test/unit/semaphore.test.ts b/projects/code-sandbox/test/unit/semaphore.test.ts
@@
-import { Semaphore } from '../../src/utils/semaphore';
+import { QueueConcurrencyLimiter } from '../../src/utils/queue-limiter';
@@
 const sem = new Semaphore(3);
+// 风险：import 已替换，但旧 Semaphore 测试主体仍保留，测试无法编译。`,
    "projects/code-sandbox/README.md": `diff --git a/projects/code-sandbox/README.md b/projects/code-sandbox/README.md
@@
-# Code Sandbox
+# Code Sandbox QueueId Concurrency
@@
+// 风险：README 出现大范围重写，超出 PR #7008 所需文档边界。
+// RepoACES 审查策略要求只补充必要环境变量说明。`,
    "projects/code-sandbox/test/integration/api.test.ts": `diff --git a/projects/code-sandbox/test/integration/api.test.ts b/projects/code-sandbox/test/integration/api.test.ts
@@
+it('accepts queueId', async () => {
+  const res = await post('/sandbox/js', { code: 'return 1', queueId: 'a' });
+  expect(res.status).toBe(200);
+});
+// 风险：只验证字段接受，没有覆盖同 queue FIFO 和跨 queue 并发。`
  },
  golden: {
    "projects/code-sandbox/src/utils/queue-id-limiter.ts": `diff --git a/projects/code-sandbox/src/utils/queue-id-limiter.ts b/projects/code-sandbox/src/utils/queue-id-limiter.ts
new file mode 100644
@@
+export class QueueIdLimiter {
+  // 参考实现：按 queueId 维护 running 计数和 FIFO waiters。
+  // 无 queueId 或未配置并发限制时旁路，确保兼容历史行为。
+}`,
    "projects/code-sandbox/src/index.ts": `diff --git a/projects/code-sandbox/src/index.ts b/projects/code-sandbox/src/index.ts
@@
+const queueIdLimiter = new QueueIdLimiter(env.SANDBOX_QUEUE_ID_CONCURRENCY);
+const result = await queueIdLimiter.run(parsed.data.queueId, () =>
+  pool.execute(parsed.data)
+);
+// 参考实现边界：限制器位于 HTTP API 与 ProcessPool 之间。`,
    "packages/service/thirdProvider/codeSandbox/index.ts": `diff --git a/packages/service/thirdProvider/codeSandbox/index.ts b/packages/service/thirdProvider/codeSandbox/index.ts
@@
+queueId?: string;
@@
+body.queueId = options.queueId;
+// 参考实现：服务调用端只负责透传 queueId，不承担并发控制。`,
    "projects/code-sandbox/test/unit/queue-id-limiter.test.ts": `diff --git a/projects/code-sandbox/test/unit/queue-id-limiter.test.ts b/projects/code-sandbox/test/unit/queue-id-limiter.test.ts
@@
+it('runs tasks without queueId immediately', ...);
+it('queues tasks with the same queueId in FIFO order', ...);
+it('does not block tasks with different queueId values', ...);
+it('releases the slot when a task fails', ...);`,
    "projects/code-sandbox/test/integration/api.test.ts": `diff --git a/projects/code-sandbox/test/integration/api.test.ts b/projects/code-sandbox/test/integration/api.test.ts
@@
+it('limits same queueId requests through real HTTP API', ...);
+it('keeps omitted queueId behavior unchanged', ...);
+it('rejects non-string queueId with 400', ...);
+// 覆盖真实 API、校验和兼容性。`,
    "document/content/self-host/upgrading/4-15/41503.mdx": `diff --git a/document/content/self-host/upgrading/4-15/41503.mdx b/document/content/self-host/upgrading/4-15/41503.mdx
@@
+### code-sandbox queueId 并发控制
+如需限制同一 queueId 的并发执行数量，可配置 SANDBOX_QUEUE_ID_CONCURRENCY。
+未配置时保持默认行为。`
  }
};

const testPlan = [
  {
    title: "1. 测试目的",
    body:
      "验证 PR #7008 为 code-sandbox 引入的 queueId 并发排队能力是否正确、兼容且可维护。重点确认 API 行为、服务调用端透传、同队列 FIFO、跨队列并发、异常输入处理和回归影响。"
  },
  {
    title: "2. 测试范围",
    body:
      "范围内：/sandbox/js、/sandbox/python、QueueIdLimiter、SANDBOX_QUEUE_ID_CONCURRENCY、ExecuteOptions、CodeSandbox.runCode、单元测试和集成测试。范围外：工作进程池生命周期重构、真实部署发布、非 queueId 相关安全策略改动。"
  },
  {
    title: "3. 测试环境",
    items: [
      "Node >= 20.19, pnpm 10.x, Vitest",
      "建议使用 Linux 容器，因为基线工作进程池会调用 sh",
      "集成行为测试设置 SANDBOX_QUEUE_ID_CONCURRENCY=1",
      "命令：pnpm exec vitest run test/unit/queue-id-limiter.test.ts test/integration/api.test.ts --config vitest.config.ts"
    ]
  },
  {
    title: "4. 高优先级测试用例",
    items: [
      "TC-QID-001：相同 queueId 的真实 HTTP 请求应按 FIFO 顺序串行进入执行流程。",
      "TC-QID-002：不同 queueId 的请求应可以重叠执行，互不阻塞。",
      "TC-QID-003：未传或空白 queueId 应绕过队列限制器。",
      "TC-QID-004：非字符串 queueId 应返回 HTTP 400 校验错误。",
      "TC-QID-005：JS 和 Python 执行接口都应保持原有正常执行行为。"
    ]
  },
  {
    title: "5. 回归与负向用例",
    items: [
      "非法 JSON 和超大请求体仍返回原有错误响应。",
      "动态 import、eval、child_process 和 Python 白名单安全测试保持不变。",
      "任务失败后必须释放队列槽位，使后续相同 queueId 请求可以继续执行。",
      "服务调用端只在调用方提供 queueId 时才把该字段放入请求体。"
    ]
  },
  {
    title: "6. 预期结果",
    items: [
      "目标测试通过：2 个文件，37 个测试。",
      "git diff --check 通过。",
      "完整测试集若存在失败，应归类到 process-pool/resource-limit 环境风险，不与 queueId 逻辑混淆。",
      "候选补丁与基准PR的实现边界保持一致。"
    ]
  }
];

const evalCards = [
  ["git diff --check", "通过", "未发现空白错误；仅出现 Windows 换行格式提示。", "pass"],
  ["目标测试", "37/37", "queue-id-limiter 单元测试和 HTTP API 集成测试已在 Linux 容器中通过。", "pass"],
  ["完整测试集", "499/506", "容器中已有 process-pool/resource-limit 测试失败；queueId 目标测试已通过。", "warn"],
  ["基准PR对齐", "高", "API 层限制器、调用端透传、环境变量、类型和测试均与 PR #7008 对齐。", "pass"]
];

const scores = [
  ["需求理解", 94],
  ["仓库上下文定位", 90],
  ["补丁正确性", 88],
  ["测试覆盖度", 86],
  ["基准PR对齐度", 92],
  ["流程可复现性", 84]
];

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function runWithDelay(button, loadingText, task, delay = 650) {
  if (!button || button.disabled) return;
  const originalText = button.textContent;
  button.disabled = true;
  button.classList.add("is-loading");
  button.textContent = loadingText;
  setTimeout(() => {
    task();
    button.textContent = originalText;
    button.classList.remove("is-loading");
    button.disabled = false;
  }, delay);
}

function splitGraphLabel(label) {
  const maxLength = 16;
  if (label.length <= maxLength) return [label];
  if (label.includes(" ")) {
    const lines = [];
    label.split(" ").forEach((part) => {
      const last = lines[lines.length - 1] || "";
      if (!last || `${last} ${part}`.length > maxLength) lines.push(part);
      else lines[lines.length - 1] = `${last} ${part}`;
    });
    return lines.slice(0, 2);
  }
  return [label.slice(0, maxLength), label.slice(maxLength, maxLength * 2)].filter(Boolean);
}

function setSection(target) {
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.target === target));
  $$(".panel").forEach((panel) => {
    const active = panel.id === target;
    panel.classList.toggle("active", active);
    if (active) $("#section-title").textContent = panel.dataset.title;
  });
}

function renderAnalysis() {
  const output = $("#analysis-output");
  output.innerHTML = analysisCards
    .map(
      (card) => `
      <article class="work-card">
        <span class="eyebrow">分析结果</span>
        <h3>${card.title}</h3>
        <ul class="check-list">${card.items.map((item) => `<li>${item}</li>`).join("")}</ul>
      </article>`
    )
    .join("");
  renderCaseSignals();
}

function renderCaseSignals() {
  $("#case-signal-output").innerHTML = `
    <div class="metric-grid">
      <div><strong>9</strong><span>核心变更文件</span></div>
      <div><strong>37</strong><span>目标测试通过</span></div>
      <div><strong>2</strong><span>候选运行对比</span></div>
      <div><strong>1</strong><span>基准PR</span></div>
    </div>
    <p class="muted">PR #7008 用作可复现案例，支撑从需求理解到基准PR对比的完整闭环。</p>`;
}

function renderCaseSignalPlaceholder() {
  $("#case-signal-output").innerHTML = `<p class="muted">点击“分析与拆解”后加载 PR #7008 的上下文信号。</p>`;
}

function renderGraph(filter = "all") {
  const svg = $("#knowledge-graph");
  const visible = new Set(
    graphNodes.filter((node) => filter === "all" || node.type === filter || (filter === "api" && node.type === "core")).map((node) => node.id)
  );
  const typeColor = {
    api: "#62a9ff",
    core: "#2dd4bf",
    client: "#b99cff",
    config: "#ff9f5a",
    test: "#6ee7a8"
  };
  const typeLabel = {
    api: "API",
    core: "核心",
    client: "调用端",
    config: "配置",
    test: "测试"
  };
  svg.innerHTML = `
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#4e6371"></path>
      </marker>
    </defs>
  `;
  graphEdges.forEach(([from, to]) => {
    if (!visible.has(from) || !visible.has(to)) return;
    const a = graphNodes.find((node) => node.id === from);
    const b = graphNodes.find((node) => node.id === to);
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", String(a.x + 92));
    line.setAttribute("y1", String(a.y + 28));
    line.setAttribute("x2", String(b.x));
    line.setAttribute("y2", String(b.y + 28));
    line.setAttribute("stroke", "#4e6371");
    line.setAttribute("stroke-width", "2");
    line.setAttribute("marker-end", "url(#arrow)");
    svg.appendChild(line);
  });
  graphNodes.forEach((node) => {
    if (!visible.has(node.id)) return;
    const labelLines = splitGraphLabel(node.label);
    const labelMarkup = labelLines
      .map((line, index) => `<tspan x="14" y="${labelLines.length > 1 ? 22 + index * 16 : 27}">${escapeHtml(line)}</tspan>`)
      .join("");
    const typeY = labelLines.length > 1 ? 58 : 49;
    const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
    group.setAttribute("class", "graph-node");
    group.setAttribute("transform", `translate(${node.x} ${node.y})`);
    group.style.cursor = "pointer";
    group.addEventListener("click", () => selectNode(node.id));
    group.innerHTML = `
      <rect width="184" height="68" rx="8" fill="#111820" stroke="${typeColor[node.type]}" stroke-width="2"></rect>
      <text fill="#edf4f8" font-size="15" font-weight="700">${labelMarkup}</text>
      <text x="14" y="${typeY}" fill="#9eb0bc" font-size="11">${typeLabel[node.type]}</text>
    `;
    svg.appendChild(group);
  });
}

function selectNode(id) {
  const node = graphNodes.find((item) => item.id === id) || graphNodes[0];
  $("#node-title").textContent = node.label;
  $("#node-path").textContent = node.path;
  $("#node-desc").textContent = node.desc;
  $("#node-tags").innerHTML = node.tags.map((tag) => `<span class="tag">${tag}</span>`).join("");
}

function renderAgents(activeIndex = -1) {
  const stateLabel = {
    done: "已完成",
    running: "运行中",
    pending: "等待中"
  };
  $("#agent-grid").innerHTML = agents
    .map((agent, index) => {
      const state = index < activeIndex ? "done" : index === activeIndex ? "running" : "";
      const label = stateLabel[state || "pending"];
      return `
        <article class="agent-card ${state}" data-agent="${agent.id}">
          <span class="agent-status"><i class="dot"></i>${label}</span>
          <h4>${agent.name}</h4>
          <p>${agent.role}</p>
        </article>`;
    })
    .join("");
  $("#agent-timeline").innerHTML = agentTimeline
    .slice(0, Math.max(activeIndex + 1, 0))
    .map(
      ([time, actor, text]) => `
      <div class="timeline-item">
        <time>${time}</time>
        <div><strong>${actor}</strong><p>${text}</p></div>
      </div>`
    )
    .join("");
}

function startAgents() {
  renderAgents(0);
  agents.forEach((_, index) => {
    setTimeout(() => renderAgents(index), index * 520);
  });
  setTimeout(() => renderAgents(agents.length), agents.length * 520);
}

function renderRun(runKey) {
  const run = runs[runKey];
  const levelLabel = {
    INFO: "信息",
    WARN: "警告",
    FAIL: "失败"
  };
  $("#terminal-heading").textContent = run.heading;
  $("#run-summary-title").textContent = run.title;
  $("#terminal-log").innerHTML = run.logs
    .map(([time, level, text]) => {
      const severity = level === "FAIL" ? "fail" : level === "WARN" ? "warn" : "";
      return `<div class="log-line ${severity}"><span class="time">${time}</span><span class="level">${levelLabel[level]}</span><span>${text}</span></div>`;
    })
    .join("");
  $("#run-summary").innerHTML = run.findings
    .map(([title, text]) => `<div class="finding"><strong>${title}</strong><p>${text}</p></div>`)
    .join("");
}

function replayRun() {
  const active = $(".run-toggle .seg.active").dataset.run;
  const run = runs[active];
  const levelLabel = {
    INFO: "信息",
    WARN: "警告",
    FAIL: "失败"
  };
  const terminal = $("#terminal-log");
  terminal.innerHTML = "";
  run.logs.forEach((line, index) => {
    setTimeout(() => {
      const [time, level, text] = line;
      const severity = level === "FAIL" ? "fail" : level === "WARN" ? "warn" : "";
      terminal.insertAdjacentHTML(
        "beforeend",
        `<div class="log-line ${severity}"><span class="time">${time}</span><span class="level">${levelLabel[level]}</span><span>${text}</span></div>`
      );
      terminal.scrollTop = terminal.scrollHeight;
    }, index * 260);
  });
}

function renderPatch(kind, selectedFile) {
  const patch = patchData[kind];
  const activeFile = selectedFile || patch.files[0][1];
  $("#patch-title").textContent = patch.title;
  const status = $("#patch-status");
  status.textContent = patch.status;
  status.className = `status-pill ${patch.pill}`;
  $("#file-list").innerHTML = patch.files
    .map(
      ([flag, file, note]) => `
      <button type="button" class="file-item ${file === activeFile ? "active" : ""}" data-file="${escapeHtml(file)}">
        <strong>${flag} ${file}</strong>
        <span>${note}</span>
      </button>`
    )
    .join("");
  $$("#file-list .file-item").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.file === activeFile) return;
      $$("#file-list .file-item").forEach((item) => item.classList.remove("active", "is-loading"));
      button.classList.add("active", "is-loading");
      $("#diff-view").textContent = "正在加载该文件的补丁差异...";
      setTimeout(() => renderPatch(kind, button.dataset.file), 260);
    });
  });
  const diff = patchFileDiffs[kind]?.[activeFile] || patch.diff;
  $("#diff-view").innerHTML = diff
    .split("\n")
    .map((line) => {
      const cls = line.startsWith("+") ? "diff-add" : line.startsWith("-") ? "diff-del" : line.startsWith("@@") || line.startsWith("diff") ? "diff-hunk" : "";
      return `<span class="${cls}">${escapeHtml(line)}</span>`;
    })
    .join("\n");
}

function renderTestPlan() {
  $("#testplan-output").innerHTML = testPlan
    .map((section) => {
      const content = section.items
        ? `<ul>${section.items.map((item) => `<li>${item}</li>`).join("")}</ul>`
        : `<p>${section.body}</p>`;
      return `<article class="test-card"><h4>${section.title}</h4>${content}</article>`;
    })
    .join("");
}

function renderEvaluation(run = false) {
  const statusLabel = {
    pass: "通过",
    warn: "需说明",
    ready: "待运行"
  };
  $("#eval-grid").innerHTML = evalCards
    .map(
      ([title, value, desc, type], index) => `
      <article class="eval-card">
        <span class="status-pill ${run ? type : "ready"}">${run ? statusLabel[type] : statusLabel.ready}</span>
        <strong>${run ? value : "..."}</strong>
        <h4>${title}</h4>
        <p>${run ? desc : "点击运行评测后加载预生成的可复现结果。"}</p>
      </article>`
    )
    .join("");
  $("#score-status").textContent = run ? "带说明通过" : "就绪";
  $("#score-status").className = `status-pill ${run ? "pass" : "ready"}`;
  $("#scoreboard").innerHTML = scores
    .map(([label, score]) => {
      const shown = run ? score : 0;
      return `
      <div class="score-row">
        <span>${label}</span>
        <span class="bar"><i style="width:${shown}%"></i></span>
        <b>${run ? shown : "--"}</b>
      </div>`;
    })
    .join("");
}

function bindEvents() {
  $$(".nav-item").forEach((button) => button.addEventListener("click", () => setSection(button.dataset.target)));
  $("#analyze-btn").addEventListener("click", (event) => runWithDelay(event.currentTarget, "分析中...", renderAnalysis, 720));
  $("#requirement-file").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    $("#requirement-text").value = await file.text();
  });
  $$(".seg[data-graph-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      runWithDelay(
        button,
        "筛选中...",
        () => {
          $$(".seg[data-graph-filter]").forEach((item) => item.classList.remove("active"));
          button.classList.add("active");
          renderGraph(button.dataset.graphFilter);
        },
        260
      );
    });
  });
  $("#start-agents").addEventListener("click", (event) => runWithDelay(event.currentTarget, "编排准备中...", startAgents, 620));
  $$(".run-toggle .seg").forEach((button) => {
    button.addEventListener("click", () => {
      runWithDelay(
        button,
        "读取日志...",
        () => {
          $$(".run-toggle .seg").forEach((item) => item.classList.remove("active"));
          button.classList.add("active");
          renderRun(button.dataset.run);
        },
        360
      );
    });
  });
  $("#replay-run").addEventListener("click", (event) => runWithDelay(event.currentTarget, "准备回放...", replayRun, 420));
  $$(".patch-toggle .seg").forEach((button) => {
    button.addEventListener("click", () => {
      runWithDelay(
        button,
        "切换中...",
        () => {
          $$(".patch-toggle .seg").forEach((item) => item.classList.remove("active"));
          button.classList.add("active");
          renderPatch(button.dataset.patch);
        },
        340
      );
    });
  });
  $("#generate-testplan").addEventListener("click", (event) => runWithDelay(event.currentTarget, "生成中...", renderTestPlan, 780));
  $("#run-evaluation").addEventListener("click", (event) => runWithDelay(event.currentTarget, "评测中...", () => renderEvaluation(true), 920));
}

function renderAnalysisPlaceholder() {
  $("#analysis-output").innerHTML = `
    <article class="work-card">
      <span class="eyebrow">摘要</span>
      <h3>需求摘要</h3>
      <p class="muted">等待点击“分析与拆解”。</p>
    </article>`;
}

function renderTestPlanPlaceholder() {
  $("#testplan-output").innerHTML = `
    <article class="test-card">
      <h4>等待生成</h4>
      <p>点击“生成测试计划”后，展示基于远端 TestPlanAgent 提示词结构预生成的 PR #7008 测试计划。</p>
    </article>`;
}

function init() {
  bindEvents();
  renderAnalysisPlaceholder();
  renderCaseSignalPlaceholder();
  renderGraph("all");
  selectNode("req");
  renderAgents(-1);
  renderRun("openhands");
  renderPatch("codex");
  renderTestPlanPlaceholder();
  renderEvaluation(false);
}

init();
