# 用 REA 逆向 DeepSeek Harness（DSH）：可行性验证与完整分析报告

**分析对象**：本机安装的 DeepSeek Harness 桌面版
**分析工具**：REA（`morluto/rea`，"Reverse Engineer Anything"）+ 人工静态分析
**分析方式**：纯静态（未执行任何被还原的 DSH 代码，未运行其沙箱代码）
**工件版本**：`0.2.0-rc.2`（`hostProtocolVersion: 4`）
**平台**：Windows 11 x64，安装路径 `C:\Users\vincento\AppData\Local\Programs\DeepSeek Harness\`

---

## 0. 结论速览

**问题：REA 能不能反过来逆向当前正在使用的 DeepSeek Harness？**

**答：能，而且已经跑通了。** 但结论有一个重要的反转：**REA 真正的价值不在"读懂架构"，而在"工件清点 + 完整性取证 + 规模测绘"；架构语义的还原几乎完全来自 DSH 自己随包分发的文档与自动生成的 API 目录。**

| 维度 | 结果 |
|---|---|
| REA 能否处理该工件 | ✅ 能。`app.asar` 被识别为 `format:"asar"`，完整性校验 `integrity_contradictions: []` |
| REA 自动分析规模 | 10,102 个相关文件 / 9,110 个 JS 解析 / 9,966,129 个 AST 节点 / 30,314 条 findings |
| REA 输出图谱 | 376,204,805 B，**187,159 个节点 / 39,530 条边** |
| REA 覆盖状态 | ⚠️ `coverage: partial`，原因 `resource_constraint`（父结果预算 1,839,717,692 B） |
| 人工静态分析覆盖 | ✅ 12,411 / 12,411 个文件与出厂 manifest 逐字节校验一致 |
| 原生二进制逆向 | ❌ 未做（需要 Ghidra/Hopper/IDA/JEB；DSH 自身也不含任何二进制分析能力） |
| 自校验 | ✅ 38 处行号引用回验、22 处字节/行数断言、15 个包体量回验、manifest 哈希交叉校验——**共抓出本报告自身 5 处错误**（IPC 表计数、一处 sha256、一处包计数、两处行数/字节数、一处包归属） |
| 意外收获 | ✅ 出厂 README 泄露了 **161 条内部设计决策记录**的完整索引（日期 / 状态 / 分类 / slug），见 §6.3 |

**最重要的单项发现**：`app.asar` 内部其实是**两个互不相同的应用**，而 REA 的图谱把它们混在一起统计。这个发现纠正了本次分析早期一个错误结论（见 §3 与 §11.2）。

```
app.asar (121,348,951 B, 12,967 条目)
├── package.json            ← @deepseek-ai/dsh-desktop  Electron 外壳入口（757 B）
├── lib/                    ← Electron 主进程 + 5 个 preload（13 条目，939,233 B）
├── renderer/               ← 欢迎页 / 更新对话框（13 条目，44,677 B）
├── node_modules/           ← 外壳自己的依赖（528 条目，4,340,225 B）
└── dsh/                    ← 真正的 Harness 运行时（12,412 条目）
    ├── package.json        ← @deepseek-ai/dsh-desktop-runtime
    ├── desktop-runtime.json← 出厂文件 manifest（2,817,387 B）
    └── node_modules/@deepseek-ai/  ← 289 个包
```

---

## 1. REA 项目调研

### 1.1 它是什么

- 仓库 `morluto/rea`，MIT 许可，站点 rea.tools，npm 包 **`rea-agents` 6.4.0**。
- 交付形态是 **MCP server + CLI** 双入口，让 AI 代理驱动逆向流程。
- 它**自带** JavaScript 应用分析器（AST 级），对二进制则**依赖外部合法授权的反编译器**：Ghidra / Hopper / IDA / JEB。REA 本身不含反编译器。
- 许可边界明确：适用于研究者**合法获得**的工件（自有软件、教育、互操作）。本次分析对象是用户自己安装的软件，符合该范围。

### 1.2 本次实际用到的命令

```powershell
rea inspect-artifact <app.asar>              # 工件识别 + 完整性
rea analyze-javascript-application <app.asar> # JS 图谱
rea doctor / capabilities                     # 环境自检与能力清单
rea inspect-analysis-view / trace-application-feature / inspect-evidence-bundle
rea evidence-export                           # 证据落盘
```

全局输出控制：`--format <toon|json|yaml|md|jsonl>`、`--token-limit`、`--token-offset`、`--filter-output`、`--full-output`、`--llms`、`--llms-full`、`--schema`。

注意 `--format json` 与 `--token-limit` **不能同时使用**：
`UNSUPPORTED_OUTPUT_COMBINATION: Token windows cannot preserve structured output.`

### 1.3 证据信封（REA 的核心抽象）

每条结论都被包在一个统一结构里，字段为：

```
evidence_id, subject, provider, analysis_profile, predicate_type, operation,
parameters, raw_result, normalized_result, confidence, authority,
environment, limitations, locations, evidence_links
```

关键枚举（写错会被 CLI 直接拒绝）：

- `confidence` ∈ `observed | derived | inferred`
- `authority` ∈ `shipped-artifact | controlled-replay | historical-reference | external-service | analyst-inference`
- `subject.architecture` ∈ `x86 | x86_64 | arm | arm64 | mips`

这套"证据强度分级"是 REA 最有方法论价值的部分——它强迫分析者把"看到了什么"和"推断出什么"分开写。

---

## 2. 工件完整性：一次真实的取证过程（含一个我自己犯的错）

### 2.1 出厂 manifest

`dsh/desktop-runtime.json`（2,817,387 B）是 DSH 的出厂清单：

```json
{
  "schemaVersion": 1,
  "release": { "version": "0.2.0-rc.2", "hostProtocolVersion": 4,
               "nodeVersion": "24.18.1", "pnpmVersion": "11.7.0" },
  "platform": "win32", "arch": "x64",
  "sharedPackages": [ /* 287 个 @deepseek-ai/* */ ],
  "files": [ /* 12,411 条 {path, bytes, sha256, executable} */ ]
}
```

`executable` 字段全为 `false`——运行时层没有任何可执行位。

### 2.2 asar 头部解析踩坑（关键教训）

asar 的 pickle 头部是**四个 uint32**，不是两个：

```
偏移  0: 4            （pickle 头长度）
偏移  4: 3392056      （头部块总大小 hdrSize）
偏移  8: 3392052
偏移 12: 3392048      （JSON 字符串长度）
偏移 16: JSON 开始
payloadBase = 8 + hdrSize = 3392064
```

我最初的提取器把 payload 起点算成 `16 + hdrSize`，导致**所有解出来的文件内容整体后移 8 字节**。`desktop-runtime.json` 因此看起来"损坏"，一度被误判为工件问题。

用 `offset-probe.js` 做偏移扫描后定位到 `*** MATCH at delta -8`。修正后：

```
extracted = 12,412   match = 12,411   mismatch = 0   absent = 0
```

**每一个文件都与出厂 sha256 逐字节一致。** 期间还测试并排除了 LF 归一化与 BOM 两个假设（各解释 0 例）。

> 这条错误链本身值得记录：**"工件损坏"的假象来自工具，而不是软件。** 完整性校验必须双向（manifest ↔ 归档），单向校验只会掩盖 bug。

### 2.3 REA 侧的完整性取证

```
evidence_id   = ev_5cc34783d5f1812739553632f3a87d979cdccee623508bc08ae27422f410bda8
subject.digest.sha256 = 983ca71114e6dfd353fc79af5a1f9481a250ee64c2a3c757673029b811b23bc2
format = "asar"        architecture = null
provider = { id: "rea-javascript-application", version: "1" }
parameters = { format: "auto", integrity_policy: "fail" }
integrity_contradictions = []          ← 无任何完整性矛盾
inventory_manifest_id = agm_8ce47b28728fcf185679cd1b362a4c00ca68eb1021f80bb989410bdc8b247d59
inventory_graph_sha256 = cf6bd3688a2fee1c660159d149cf385a773f928f64690a87f7554d79c04b7b76
```

`architecture: null` 是正确判定：JS 工件没有 CPU 架构属性，也说明 REA 没有把它误当成 PE 文件。

---

## 3. 真正的架构：三层进程模型

这是本次逆向的核心成果，也是 REA 图谱没能自动分离出来的部分。

```
┌─────────────────────────────────────────────────────────────────┐
│ 第 1 层  Electron 外壳  @deepseek-ai/dsh-desktop                │
│   DeepSeek Harness.exe (244,481,512 B) · Electron 44.0.0        │
│   main: lib/main.js (490,173 B / 12,331 行)                     │
│   自定义特权协议 dsh-app://  ·  5 个 preload  ·  11 个桥 API     │
└───────────────────────────┬─────────────────────────────────────┘
                            │ spawn(--expose-internals, stdio:[ignore,pipe,pipe,ipc])
                            │ ELECTRON_RUN_AS_NODE=1
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 第 2 层  Node 宿主  @deepseek-ai/dsh-desktop-host               │
│   dsh/node_modules/@deepseek-ai/dsh-desktop-host/lib/index.js   │
│   Cordis 运行时 · 289 个 @deepseek-ai 包 · 43.5 MB JS           │
│   HTTP + WebSocket 监听 127.0.0.1:19387                         │
└───────────────────────────┬─────────────────────────────────────┘
                            │ koffi FFI / node-pty / spawn
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 第 3 层  原生 payload（app.asar.unpacked）                       │
│   koffi.node 1,058,280 · node-pty conpty.node · sharp 0.35.5   │
│   rg.exe 5,443,048 · libreoffice-kit.exe 178,581,480            │
│   onnxruntime.dll 17,812,456 · sherpa-onnx-c-api.dll            │
└─────────────────────────────────────────────────────────────────┘
```

### 3.1 外壳如何启动宿主（`lib/main.js:3671-3691`）

```js
const entry = join(this.runtimeDir, "node_modules", "@deepseek-ai",
                   "dsh-desktop-host", "lib", "index.js");
const child = spawn(this.node, [
  "--expose-internals",
  entry,
  this.runtimeDir,          // = app.asar/dsh
  this.projectDir,
  this.primaryRuntime ?? join(this.runtimeDir, "..", "runtime", "primary-runtime"),
  ...this.packageManager === void 0 ? [] : [this.packageManager.pnpm, this.packageManager.nodeBin]
], {
  cwd: this.projectDir,
  env: desktopNodeEnvironment(this.node, void 0, this.environment),
  stdio: ["ignore", "pipe", "pipe", "ipc"]     // ← 第 4 个描述符 = IPC 通道
});
```

`desktopNodeEnvironment`（:3529）注入 `ELECTRON_RUN_AS_NODE: "1"` 与 `DSH_DESKTOP_NODE_EXECUTABLE`——所以 `runtime\bin\node.cmd` 本质是"用 Electron 自己当 Node"。

### 3.2 父子之间的 IPC 词汇表（`main.js:3544-3581`）

宿主 → 外壳的消息被 `isDesktopHostEvent()` 严格白名单校验，非法即 `SIGTERM` 杀子进程：

| 消息 | 载荷 |
|---|---|
| `ready` | `{ url, injections }` |
| `shutdown-complete` | — |
| `quit-inspection` | `{ requestId, activeTasks, scheduledTasks, error? }` |
| `update-tasks` | `{ requestId, active, error? }` |
| `platform-session` | `{ origin, token, userId, embeddedPageDist?, requestHeaders? }` |
| `fatal` | `{ message, diagnostic }`（诊断上限 64 KB） |

`platform-session.requestHeaders` 有一段**显式禁用头名单**（:3556-3564）：
`authorization, x-dsh-auth-token, host, content-length, transfer-encoding, connection, content-type`
——并且要求头名已小写、不含 CR/LF。这是防请求头注入的硬编码围栏。

`origin` 只允许 `https:` 或 `http:` + `localhost | 127.0.0.1 | [::1]`（:3567-3571）。

### 3.3 自定义协议 `dsh-app://`（`main.js:11019-11029`, `11542-11551`）

```js
protocol.registerSchemesAsPrivileged([{ scheme: "dsh-app", privileges: {
  standard: true, secure: true, supportFetchAPI: true, corsEnabled: true,
  stream: true, codeCache: true }})]);

protocol.handle("dsh-app", (request) => {
  const url = new URL(request.url);
  if (url.hostname === "shell") return serveWebDocument(request, join(app.getAppPath(), "renderer"));
  if (url.hostname === "app") {
    if (url.pathname === "/" || url.pathname === "/index.html"
        || url.pathname.startsWith("/assets/")
        || ["/favicon.svg", "/manifest.webmanifest"].includes(url.pathname))
      return serveWebDocument(request, join(resources.dsh, "node_modules",
             "@deepseek-ai", "dsh-web-frontend", "dist"));   // ← 静态 UI 直接本地服务
    return forwardWebRequest(request, hostUrl, hostCookie);  // ← 其余全部反代到宿主
  }
  return Promise.resolve(new Response(null, { status: 404 }));
});
```

即：**UI 静态资源由外壳本地服务，API 流量由外壳反向代理到 `127.0.0.1:19387`。**

`serveWebDocument`（:7395-7416）还做了目录穿越围栏（`target.startsWith(directory + sep)`），并在 `index.html` 的 `<head>` 注入：

```html
<script>globalThis.__DSH_BOOT_READY__ = Promise.withResolvers()</script>
```

这解释了为什么 `dist/index.html`（825 B）里看不到任何注入——注入发生在**服务时**，不在构建产物里。

### 3.4 认证链（完整闭环）

```
宿主 ready{url}  ── url = http://127.0.0.1:19387/?token=<启动令牌>
      │              （dsh-client-connection: TOKEN_QUERY = "token", :226）
      ▼
authenticateWebHost(url)            main.js:7422
   fetch(url, {redirect:"manual"})
   期望 status === 303 且存在 set-cookie，否则抛 "Desktop Host authentication failed"
      │              （宿主侧 authorizeIndex :388 校验根令牌 → 铸 cookie → 303 跳 ./）
      ▼
hostCookie  ── 只保留在 Electron 主进程，绝不交给渲染进程
      │        WITHHELD_RESPONSE_HEADERS 显式吞掉 set-cookie（:7431-7436）
      ▼
forwardWebRequest()  main.js:7461
   删除 host/origin/cookie/sec-fetch-site，注入 cookie
   origin 必须 === "dsh-app://app"，否则 403
      ▼
WebSocket 升级  main.js:11583
   onBeforeSendHeaders({ urls: ["ws://127.0.0.1/*"] })
   origin !== "dsh-app://app" → cancel: true
   否则改写 origin 为宿主 origin、注入 cookie、sec-fetch-site: same-origin
```

**安全设计要点**：渲染进程永远拿不到令牌或 cookie；它只能以 `dsh-app://app` 身份发请求，由主进程代为鉴权。`isLoopbackHostname`（`dsh-client-connection:121`）在源码里被明确注明"**不是一层认证**"——真正的围栏是这个 origin 校验 + cookie 独占。

### 3.5 Electron IPC 面（外壳 ↔ 渲染进程）

5 个 preload 脚本，**11 个 `contextBridge.exposeInMainWorld` API**：

```
dshDesktop · dshDesktopBoot · dshPlatform · dshOnboarding
dshWelcome · dshUpdateDialog · dshMandatoryUpdate · dsh
__DSH_DIRECTORY_PICKER__ · __DSH_HOST_PATHS__ · __DSH_LOCALE__
```

5 张通道表、**45 个字符串字面量通道名**：

| 表 | 定义行 | 通道数 | 前缀 |
|---|---|---|---|
| `DESKTOP_IPC` | 6193 | 25 | `dsh-desktop:` |
| `WELCOME_IPC` | 7747 | 9 | `dsh-welcome:` |
| `PLATFORM_IPC` | 5919 | 5 | `dsh-platform:` |
| `MANDATORY_IPC` | 8856 | 3 | `dsh-desktop:mandatory-*` |
| `UPDATE_DIALOG_IPC` | 9465 | 3 | `dsh-update-dialog:` |
| **合计** | | **45** | 全部 45 个通道名都在这 5 张表内，表外无散落字面量 |

每个 handler 都有发送方围栏，例如 `assertDesktopSender(event, ["app"])`（:6227-6232）：无 sender frame 直接抛错，协议必须是 `dsh-app:`，hostname 必须在白名单内。`PLATFORM_IPC` 更严（`assertMainApplication`，:11605-11609）：必须是主窗口主框架且 URL 前缀为 `dsh-app://app/`。

`__DSH_HOST_PATHS__` 只暴露 `electron.webUtils.getPathForFile`——这是 Electron 32+ 移除 `File.path` 后的标准替代，说明作者有意避免把任意路径能力交给页面。

### 3.6 外壳自己的 HTTP RPC（欢迎页 / 引导流程）

`connectDesktopWelcome`（:8074-8099）在**主进程内**直接实现了一个 Typert HTTP 客户端：

```js
POST /api/<namespace>/<method>
{ "type": "client-request", "rpcId": "<uuid>", "method": "<ns>/<method>",
  "payload": { "args": {...} } }

→ { "type": "server-response", "rpcId": "<uuid>", "result": { "ok": true, "value": ... } }
```

该信封与宿主侧 `dsh-client-connection/lib/index.js:504-517` 的 zod schema 完全对应：

```js
const clientRequestSchema = z.object({ type: z.literal("client-request"), rpcId, method, payload });
const serverResponseSchema = z.object({ type: z.literal("server-response"), rpcId, result });
const rpcMessageSchema = z.discriminatedUnion("type", [clientRequestSchema, serverResponseSchema]);
```

引导流程实际调用了 `settings/describe`，从 `llm-deepseek` 命名空间读取 `apiKeyEnv`（官方凭据引用），从 `locale` 命名空间读取语言偏好。

---

## 4. 运行时层：包地图与代码体量

`dsh/node_modules/@deepseek-ai/` 下 **289 个包**：

| 统计 | 数值 |
|---|---|
| 许可证 | MIT 287 · MPL-2.0 1 · 无 1 |
| `README.md` | 296 |
| `README.zh.md` | **279**（几乎每个包都有中文文档） |
| `.js` 文件 | 1,195 个，共 **43,541,159 B** |
| 仓库 | `git+https://github.com/deepseek-ai/deepseek-harness.git`（**公开仓库**，标语 "Everything is a Plugin"） |

体积最大的包：

| 包 | JS 字节 | 说明 |
|---|---|---|
| `dsh-client-ui-sidebar-documentpreview` | 14,439,816 | `client.pdf.js` 7.1 MB + `client.excel.js` 7.1 MB（打包进浏览器的预览器） |
| `dsh-client-ui-settings-account` | 5,282,737 | 单文件 `client.js` 5.28 MB |
| `dsh-web-frontend` | 4,325,315 | 61 个 js，目录 `apps/web` |
| `dsh-api-session-controller` | 818,646 | 38 个 js |
| `dsh-client-ui-conversation` | 717,536 | |
| `dsh-tool-cordis` | 627,740 | 含 609 KB 的 API 目录 |

前端栈：**React 18 + Vite 6**，产物 `dsh-web-frontend/dist`（130 文件 / 5,702,341 B），哈希资源 `index-5SrrfWpU.js` 633,282 B、`vendor-CCJJTK99.js` 740,575 B、`cpp-DIPi6g--.js` 637,594 B。UI 由 **53 个 `dsh-client-ui-*` 包**组成。

第三方依赖 **229 个**（148 个普通包 + 81 个包分布在 27 个 scope 下）：`koffi`、`node-pty`、`@xterm`、`sharp`、`sherpa-onnx-*`、`@modelcontextprotocol/*`、`@agentclientprotocol`、`openai`、`undici`、`ws`、`jose`、`@opentelemetry/*`、`@vscode/ripgrep`。注意 `sharedPackages` 只列 `@deepseek-ai/*`——第三方包不在出厂共享清单里。

---

## 5. 组合机制：Cordis 插件框架

DSH 的骨架不是 DI 容器，而是 **Cordis**（`cordis` 4.0.4 + `cordis-plugin-group` 1.0.4 + `-include` 1.0.9 + `-loader` 1.0.5 + `-timer` 1.1.6），配合 `cosmokit` 1.8.5 与 `schemastery` 3.18.4。

### 5.1 组合脊柱

`dsh-base/cordis.patch.yml`（20,780 B / **529 行**）声明基础层：`llm`、`session`、`typert`、`typert-gateway`、`agent`、`jobs`、`authorization`、`deepseek-account`、`credentials`、`sandbox`、`compaction-basic`、`subagent`、`workflow-ptc`、`tools`、`fs-sandbox` …

`dsh-web-app/cordis.patch.yml`（21,637 B / **565 行**）叠加 Web 层，另有 `presets/{cordis,minimal,ptc,standard}.patch.yml` 四档预设。启动模板在 `dsh-app-boot/lib/index.js:529-535`：

```js
acp:           dsh-base + dsh-acp-app
web:           dsh-base + dsh-web-app      ← 本次会话所用
headless:      dsh-base + dsh-headless
sdk:           dsh-base + dsh-sdk-app
"sdk-minimal": dsh-sdk-minimal             ← 唯一不挂 dsh-base 的模板
```

profile 是 `$DSH_HOME/profiles/<name>/` 目录，其 `cordis.patch.yml` 是用户覆盖层。本机 `profiles/desktop/cordis.patch.yml` 实际内容就是模型覆盖：`provider: strata`、`model: iq3_xxs-novision`、`baseURL: https://api.deepseek.com`。

### 5.2 本次会话运行的真实组合

`dsh-web-app/presets/standard.patch.yml`（7,511 B / **146 行**）就是当前这套工具面的来源。它是一条 `insert`，在 web patch 之后插入一个 `@deepseek-ai/dsh-agent-preset`（`id: standard`, `order: 1`），其 `config.plugins` 逐条可读：

| id | 包 | 关键配置 |
|---|---|---|
| `persona` | `dsh-persona` | `prefix: You are a coding agent powered by the {{model}} model.`<br>`suffix: Your working directory is {{cwd}}.` |
| `agent-instructions` | `dsh-agent-instructions` | `maxBytes: 65536` → 读取 `$DSH_HOME/AGENTS.md` |
| `tool-bash` | `dsh-tool-bash` | `disabled: !!js process.platform === 'win32'` |
| `tool-pwsh` | `dsh-tool-pwsh` | `disabled: !!js process.platform !== 'win32'` ← **与 tool-bash 严格互斥** |
| `tool-fs` / `tool-fs-search` | | `sampleOverCapGlobResults: false` |
| `tool-jobs`、`skill-filesystem`、`tool-skill` | | |
| `command-goal`、`tool-goal` | `dsh-command-goal` / `dsh-tool-goal` | |
| `planning`（`cordis:group`，`isolate: {planMode: true}`） | `dsh-plan-mode` | 带一整段 `section:` 字面量（见下） |
| `compaction`（`isolate: {compaction: true, toolResultPruner: true}`） | `dsh-compaction-basic`、`dsh-command-compact`、`dsh-compaction-tool-result-pruner` | `thresholdChars: 8192, headChars: 4096, tailChars: 1024` |
| `delegation`（`isolate: {workflowEngine: true}`） | `dsh-tool-subagent-control`、`…/list-agents`、`dsh-tool-subagent`(spawn)、`dsh-tool-subagent`(fork)、`dsh-workflow-ptc`、`dsh-tool-workflow` | 见下 |
| `tool-ask-user`、`tool-todo` | | `allowParallelInProgress: true` |
| `tool-web` | | `fetch: true, searchTimeoutMs: 60000` |
| `present` | `dsh-tool-present` | |
| `tool-plugin-manager` | `dsh-plugin-manager/tools` | **`disabled: true`** ← 插件管理工具在本预设下不对代理开放 |

**被显式禁用的三个委派后端**（都在 `delegation` 组内，`disabled: true`）：

```yaml
tool-subagent-codex:       provider: codex        backgroundMode: one-shot      maxDepth: provider-managed
tool-subagent-claude-code: provider: claude-code  backgroundMode: one-shot      maxDepth: provider-managed
tool-ralph:                subagentProvider: spawn                              maxRounds: 64
```

启用的两个：

```yaml
tool-subagent:       provider: spawn  toolName: subagent        backgroundMode: continuable  modelSelectionSettings: true
tool-subagent-fork:  provider: fork   toolName: subagent_fork   backgroundMode: continuable
```

即：**外部编码代理后端（codex / claude-code）与 ralph 循环在本构建里是关掉的**，只有进程内 spawn / fork 两种子代理后端 + PTC 工作流引擎对外可用。`continuable` 与 `one-shot` 的差别就是"能否用 send_message 继续同一个子会话"。

`planning` 组里的 `section:` 是一段完整的 plan-mode 提示词字面量，明确写着：工具目录跨模式保持不变以稳定请求缓存、plan-mode 规则**覆盖**后续工具描述、不得用 `todo_write` 跟踪规划阶段、`exit_plan_mode` 必须是该条回复里唯一且最后的工具调用。这段文本本身就是 DSH 行为语义的一手证据。

`!!js` 表达式是 patch 文件里的求值语法——配置即代码，这也是"Everything is a Plugin"标语的落地方式。

### 5.3 系统提示词的构造

`dsh-system-prompt/lib/index.js:10-43` 用固定序号排布 section：

```
HARNESS_IDENTITY: -1000  …  HARNESS_SOURCE: 10000
WEB_SURFACE: 10100 · DEPLOYMENT_PERSONA_SUFFIX: 10200
CONTEXT_ORDERS { SANDBOX_POLICY: 110, APPROVAL_POLICY: 115, SUBAGENT_DELEGATION: 120 }
```

身份句是硬编码字面量（:218）：`"You are an AI agent powered by DeepSeek Harness."`

---

## 6. 自描述性：DSH 把答案写在了包里

这是本次逆向效率最高的部分，也是"REA 价值有限"的直接原因。

### 6.1 生成的 API 目录

`dsh-tool-cordis/lib/types/api-catalog.js` — **609,169 B / 8,188 行**，由 `scripts/gen-cordis-api.ts` 生成，并由 `pnpm run verify-cordis-api` 做新鲜度门禁。它导出四张表：

| 表 | 内容 |
|---|---|
| `SERVICE_API` | **91 个服务键**、584 个方法签名、1,017 个 `name:` 条目 |
| `EVENT_API` | **81 个事件名** |
| `TYPE_API` | **936 个类型** |
| `INHERITED_CTX_API` | **9 组** ctx 继承 API（`ctx.on/once`、`ctx.emit/parallel/serial/bail/waterfall`、`ctx.plugin/inject`、`ctx.effect`、`ctx.get/set/provide/accessor/mixin`、`ctx.extend/isolate/intercept`、`ctx.root/fiber/registry/reflect/events/logger`、`ctx.timer`、`ctx.loader`） |

91 个服务键（完整）：

```
agentDefaultModel, agentLoop, agentPresets, agents, agentTeams, approval, attachments,
authorization, browserUse, clientModules, commands, compaction, computerUse, configEditor,
connection, credentials, credentialsController, deepseekAccount, deepseekLlmApiExtensions,
directoryPicker, directoryPickerController, fileReferences, fileUploads, fs, goals, hmr,
inspector, invariants, jobController, jobs, llm, lsp, mcpResources, messageFeedback,
officeToPdf, otel, permissionPresets, planMode, pluginManager, pluginRegistryProbe,
productAnalytics, productTelemetry, profileContext, ptcRuntime, sandbox, sandboxPolicy,
schedule, sessionController, sessionFeedback, sessionFileReferences, sessionPersistence,
sessionProjectionCache, sessionProjections, sessionQuery, sessionReferenceResolver,
sessions, sessionSkillCatalog, sessionTelemetry, sessionTitle, settings, settingsController,
shell, shellEnv, skills, speechController, speechToText, spillStore, ssh, storage,
storageDomain, subagentModelSelection, subagents, subprocess, systemPrompt,
terminalController, terminals, timer, tokenMeter, toolResultPruner, tools, typert,
typertGateway, userQuestions, web, webhookRuntime, webServer, workflowEngine,
workspaceChanges, workspaceController, workspaceFiles, workspaceRegistry
```

### 6.2 插件清单

`dsh-agent-preset/skills/cordis-composition-reference/references/packages.md`（38,782 B）同样是生成物（`scripts/gen-plugin-packages.ts` + `verify-plugin-packages`），按领域分组列出全部插件及其是否接受 Config。

DSH 还随包分发了**教代理如何给自己写插件的技能**：`cordis-plugin-development`（SKILL.md 8,144 B + 6 篇 references + 模板）、`editing-cordis-compositions`、`agent-experience`。

### 6.3 意外收获：出厂文档泄露了完整的内部设计决策索引

这是本次分析里性价比最高的一条线索。README 里有 **293 处**相对链接指向仓库内部的 `.agents/notes/…`，去重后得到 **161 条不同的设计决策记录**：

```
状态：implemented 126 · archived 31 · proposed 4
分类：architecture 79 · feature 68 · simplification 11 · process 2 · testing 1
日期跨度：2026-06-13 → 2026-09-20
```

这些 `.md` 文件本身**没有随包分发**（`dsh/.agents` 不存在），但**文件名、日期、状态、分类、slug 全部明文留在出厂文档里**。等于对方免费给了你一份架构决策日志的目录：

```
archived/feature/2026-07-10-sqlite-session-query-provider      ← 会话查询曾用 SQLite，后来撤了
archived/feature/2026-06-30-hook-bridges
archived/feature/2026-06-30-hook-protocol-lib                  ← hook 机制被整体废弃
archived/feature/2026-07-27-tmux-location-context
archived/architecture/2026-08-11-pwsh-persistent-pty           ← pwsh 持久 PTY 被撤
archived/architecture/2026-07-26-subprocess-seam
archived/architecture/2026-07-23-unified-session-query-service
implemented/simplification/2026-06-26-fsspec-style-fs-seam    ← fs 层是 fsspec 风格设计
implemented/simplification/2026-07-23-acp-automation-only-protocol
implemented/architecture/2026-07-15-agent-initiator-scope
implemented/feature/2026-09-20-default-workspace
proposed/feature/2026-06-30-pre-tool-input-rewrite             ← 工具入参改写：仍是提案，未实现
proposed/architecture/2026-09-14-composer-model-and-draft-editor
proposed/architecture/2026-07-27-session-projection-and-command-log
```

对逆向而言这份索引的价值是**方向性的**：它告诉你哪些子系统被重构过（`archived` 的 slug 就是曾经的实现方式）、哪些边界是刻意设计的（`implemented/architecture` 共 79 条）、哪些能力还没落地（4 条 `proposed`，别去代码里找——它确实不在）。例如 `proposed/feature/2026-06-30-pre-tool-input-rewrite` 与 `dsh-tools/README.md:230` 互相印证：README 明写 `tools/pre-execute` **故意不能**改写 `exec.arguments`，因为"记录与渲染的参数会和实际执行脱钩"，而改写方案"是一份提案 Agent Note"。

完整索引已导出：[re/agents-notes-index.md](S:\Develop\agent_harness\re\agents-notes-index.md)（20,079 B，161 条，含每条的被引次数与来源包）。

---

## 7. 工具层与策略管线

`dsh-tools/README.md:105` 原文给出了完整的固定管线：

> Every call runs a fixed pipeline: `tools/pre-execute` (extensible allow/deny/ask) → registered monotonic guards → `tools/execute` (around-dispatch wrappers) → `tools/post-execute` (inspect/replace, attach context) → definition-owned `finalizeContent` → the observe-only `tools/result` event. Only the `tools/execute` view may replace the required signal, and the registry re-fuses the caller signal before the body.

拆成可验证的语义：

- `ctx.tools.guard(guard)`（README:85）挂在 `tools/pre-execute` 瀑布之后，**单调**：返回理由即拒绝，后续任何监听者都无法把拒绝翻回许可。
- `tools/pre-execute` **故意不能**改写 `exec.arguments`（README:230），理由是"记录与渲染的参数会和实际执行脱钩"。
- 取消是协作式且静默的（README:123）：每个工具体拿到 caller-owned 的 `exec.signal` 且必须观察它；派发前取消 = `ABORTED_BEFORE_DISPATCH`，派发后取消 = 只把成功结果替换为 `ABORTED`。拒绝、wrapper 失败、工具失败、post-policy 失败、`TOOL_TIMEOUT` 都保持更具体的分类。未知/抛错工具变成结构化错误 `UNKNOWN_TOOL`，**单次调用失败不会终结这一轮**。
- 注册表按层持有类型化 `ToolDefinition`，在请求时才投影成面向模型的 `ToolSchema`；`output` / `execute` / `finalizeContent` / `timeoutMs` / 展示回调**不会泄漏到线上**。
- `mode` 配置 `native | ptc | both`（默认 `native`），`maxParallelSubCalls` 默认 10（`lib/index.js:2655`）。
- 统一 schema DSL：`string, number, integer, boolean, null, array, object`，作者专用 `json`，严格 `oneOf`；`InferValue` 保类型穿透 16 层容器。

Agent 循环（`dsh-agent-loop`）：`ReactLoopInbox`（:70）持有 `next-turn` / `next-step` 两个数组，事件 `agent/inbox/spliced|inserted|claimed|discarded`，`SOURCE = "runtime-context"`（:218）。

子代理两种后端：`dsh-subagent-spawn-in-process`（独立子会话）与 `dsh-subagent-fork-in-process`（把父会话**已完成**的轮次播种给子会话，不含在飞的那一轮，fork 时一次性快照）。

工作流引擎 `dsh-workflow-ptc` 生成 `WORKFLOW_GUEST_SOURCE`（ESM guest 注入挂载的 PTC 运行时，`node:vm` realm），用 `assertObjectJsonSchema` 校验 `opts.schema`，并对每次运行的子代理总数设上限——`dsh-workflow` 的接缝注释写着"a tripped cap must kill the script loudly"。

---

## 8. 沙箱：三平台三机制

| 平台 | 机制 | 证据 |
|---|---|---|
| Linux | **bwrap → Landlock** | `dsh-sandbox-local/lib/index.js:6` 直接 `import { LAUNCHER_BIN, LAUNCHER_FAILURE_EXIT, grantArgs, launcherPath, probe } from "@deepseek-ai/node-addon-system/landlock-run"`；`bwrapProfileArgs` :22、`landlockProfileArgs` :45 |
| macOS | **Seatbelt SBPL** | `seatbeltProfileArgs` :65（`sandbox-exec -p`），`defaultProbeSeatbelt` :123 |
| Windows | **受限令牌 + 原始 ACL（koffi FFI）** | `dsh-sandbox-windows-acl/lib/types-Cl_DXjhk.js` 64,309 B |

`node-addon-system` 甚至随包分发了 C 源码：`src/flock.c` 5,744 B、`src/main.c` 11,757 B。

### 8.1 Windows 侧没有静态导入

对 `@deepseek-ai` 全量 grep `CreateRestrictedToken|OpenProcessToken|SetEntriesInAcl|CreateProcessAsUserW|advapi32` → **41 处命中**，分布在 **4 个包**里，全部经由 **koffi FFI** 动态绑定：

| 包 | 角色 | 关键位置 |
|---|---|---|
| `dsh-sandbox-windows-acl` | 令牌构造 + ACL 授权 | `lib/types-Cl_DXjhk.js` :139-217 绑定表，:714-769 令牌前置，:893 `CreateRestrictedToken` |
| `dsh-win32-process` | 受限进程实际派发 | `lib/index.js` :150 `koffi.load("advapi32.dll")`，:189 `CreateProcessAsUserW`，:458/:693 调用点 |
| `dsh-fs-local` | 文件安全描述符读写 | `lib/index.js` :26-30 `GetFileSecurityW` / `SetFileSecurityW` |
| `dsh-sandbox-windows-acl/lib/runner.js` | 独立 runner 进程 | :42 注释直接点名 `CreateProcessAsUserW` |

绑定表内容（`types-Cl_DXjhk.js:139-217`，`extendWin32ProcessBindings(({ kernel32, advapi32, bind }) => …)`）。跨这三个包统计：**advapi32 17 个函数、kernel32 28 个函数**，全部运行时动态绑定。

advapi32（17）：

```
OpenProcessToken · GetTokenInformation · SetTokenInformation
CreateWellKnownSid · ConvertStringSidToSidW · IsValidSid · GetLengthSid · CopySid
CreateRestrictedToken · SetEntriesInAclW · InitializeAcl · AddMandatoryAce
SetNamedSecurityInfoW · GetNamedSecurityInfoW · CreateProcessAsUserW
GetFileSecurityW · SetFileSecurityW
```

kernel32（28，节选）：`OpenProcess · CreateProcessW · CreateJobObjectW · AssignProcessToJobObject · SetInformationJobObject · QueryInformationJobObject · TerminateJobObject · CreatePipe · PeekNamedPipe · ReadFile · SetConsoleCtrlHandler · SetEnvironmentVariableW · LockFileEx / UnlockFileEx · GetTempPathW · LocalAlloc / LocalFree · FormatMessageW …`

也就是说受限进程外面还套了 **Job Object**（作业对象）做进程树回收，并用 `LockFileEx`/`UnlockFileEx` 做文件锁——这两件事报告里之前没提。注意 `dsh-fs-local` 也走 advapi32——**连文件系统层都在用 ACL**，不只是进程层。

语义要点：`CreateRestrictedToken(currentToken, 13, 0, null, 0, null, nSids, restrictingSids, slot)`（:893）——`13` 是缩减标志组合，缩减项全部来自 restricting SID 列表；:769 明确"在 N 个令牌组里找不到 logon SID 就失败"。`WRITE_RESTRICTED` 只 intersect 写访问；Low-IL 标签阻止向上写；能力 SID `workspaceWriteSid` / `tempWriteSid` 区分**常驻授权**（工作区、跨会话缓存）与**可撤销授权**（临时目录）；授权需要目标具备有效的 `WRITE_DAC` + `WRITE_OWNER`。文档自己承认已知缺口：硬链接别名、被 AppContainer ACL 保护的文件不可读。

### 8.2 ACL runner 的 argv 契约

`dsh-sandbox-windows-acl/lib/runner.js`（188 行）。契约写在源码注释 :16-19 里：

```
[node, runner.js, '--workspace', <dir>, '--temp', <dir>,
 '--mode', <read-only|workspace-write>,
 ['--write-sid', <S-1-4-…>, '--temp-write-sid', <S-1-4-…>],
 '--', <argv...>]
```

参数校验（:94-120）：

- 缺 `--workspace` / `--temp` 即 `fail()`；`requireDirectory` 要求两者**确实存在且是目录**（:110-112）。
- `read-only` **不接受**任何 write-sid（:118）。
- `workspace-write` 要求 `--write-sid` 与 `--temp-write-sid` **成对出现**（:119）。
- `workspace-write` 下 `assertTempRootOutsideWorkspace(workspace, temp)`（:120）——临时根必须在工作区之外。

**最有价值的一点：runner 不信任调用方给的 SID。**（:130-141）

```js
writeSid = workspaceWriteSid(parsed.workspace);            // 由路径重新推导
if (parsed.writeSid !== writeSid) fail("--write-sid does not match --workspace");
privateTempSid = tempWriteSid(privateTempDir);
if (parsed.tempWriteSid !== privateTempSid) fail("--temp-write-sid does not match --temp");
```

SID 是由路径确定性推导的，runner 自己算一遍再与传入值比对——这防住了"seam 递给你一个授权给别的路径的 SID"这种越权。配套的是 `manageDacls: !seamManaged`（:149）：当 seam 已经预先授权时，runner **不去动 DACL**，避免两层同时改 ACL。

未由 seam 管理时，runner 自己 `mkdtempSync(join(temp, "dsh-"))` 造私有临时目录（:138），并在 `finally` 里 `rmSync(..., {recursive, force})` 清掉（:171-178）；`sandbox.dispose()` 也在 `finally` 里，清理失败只写 stderr、不改退出码。

其它细节：

- `setConsoleCtrlHandler(null, 1)`（:122）——屏蔽 Ctrl+C / Ctrl+Break，防止信号穿透到被约束子进程。
- 用 `SetEnvironmentVariableW` 把 `TMP` / `TEMP` 改写到私有临时目录（:154-155），让被约束命令的临时文件天然落在可撤销授权区内。
- 子进程 `stdio: "inherit"`；经 `@deepseek-ai/dsh-subprocess/control` 的 `SUBPROCESS_CONTROL_ENV` / `SUBPROCESS_CONTROL_FD` 支持控制文件描述符，spawn 后 `closeSync` 掉自己这一端（:161-163）。
- `RUNNER_SIGNATURE = "windows-acl-run"`（:51）、`RUNNER_FAILURE_EXIT = 127`（:52）；注释明说"the seam's RUNNER_FAILURE_RULES matches that"——**127 是 seam 与 runner 之间的约定码**，不是巧合。`RunnerFailure` 类型的错误不再重复打印（:184）。

探测与失败语义：每个平台的 runner 都带**功能性探针**，不是"存在即认为可用"——`defaultProbeSeatbelt`（`dsh-sandbox-local/lib/index.js:123`）、`defaultProbeWindowsAcl`（:143，实际跑 `cmd /c exit 0`）。探针失败 ⇒ `SANDBOX_UNAVAILABLE`；runner 自身失败 ⇒ 退出码 127，stderr 前缀 `windows-acl-run: <detail>`。

诊断技能也打包在同一包内，并通过 `registerAclDiagnosisSkill(ctx)`（`types-Cl_DXjhk.js:1090`）注册，导出名 `ACL_DIAGNOSIS_SKILL`：

| 文件 | 字节 | 出厂 sha256 |
|---|---|---|
| `assets/diagnose-windows-sandbox-acl/SKILL.md` | 6,982 | `9c616c78892daeaea864a9b2d6baaea91ff133cf83cde0b725c6caee2d4933cb` |
| `…/scripts/diagnose-windows-sandbox-acl.ps1` | 45,460 | `adba89f3b10692302723d231d003cdf365311effaff996d32416f9531e3b63d9` |

两个哈希都与 `desktop-runtime.json` 里的记录逐字节一致——顺带说明：**本次分析过程中曾引用过一个错误的哈希值，是清单交叉校验把它抓出来的**。这类自校验在逆向里不是可选项。

### 8.3 进程内围栏与预设

- `dsh-fs-sandbox` → `FS_SANDBOX_DENIED`
- `dsh-fs-observation-policy` → 写前先读
- `dsh-user-approval` → `ask | never`，`unavailable` **失败关闭**
- `dsh-permission-presets` → `read-only+ask` / `workspace-write+ask` / `danger-full-access+never`，不匹配 ⇒ `custom`

`dsh-base/cordis.patch.yml:222-262` 是这段的装配点，注释直接写明意图（:223-225）："每个出厂 CLI 模式都从同一条文件效应边界开始；环境变量是显式的部署覆盖，否则新会话通过下面的 permission 服务钉在 workspace-write + ask"：

```yaml
- id: sandbox          name: '@deepseek-ai/dsh-sandbox-local'
- id: sandbox-policy   name: '@deepseek-ai/dsh-sandbox-policy'
  config:
    mode: !!js process.env.DSH_PERMISSION_MODE ?? 'workspace-write'
    workspaceRoot: !!js process.cwd()
- id: bash-sandbox     name: '@deepseek-ai/dsh-bash-sandbox'
  disabled: !!js process.platform === 'win32'      # timeoutMs: 60000
- id: pwsh-sandbox     name: '@deepseek-ai/dsh-pwsh-sandbox'
  disabled: !!js process.platform !== 'win32'
- id: approval         name: '@deepseek-ai/dsh-user-approval'
  config:
    policy: !!js "(process.env.DSH_PERMISSION_MODE ?? 'workspace-write') === 'danger-full-access' ? 'never' : 'ask'"
- id: permission       name: '@deepseek-ai/dsh-permission-presets'
  config:
    presets:
      read-only:          { sandbox: read-only,          approval: ask }
      workspace-write:    { sandbox: workspace-write,    approval: ask }
      danger-full-access: { sandbox: danger-full-access, approval: never }
```

注意沙箱是**两层**：`dsh-sandbox-local` 提供平台 runner，`dsh-bash-sandbox` / `dsh-pwsh-sandbox` 是**按工具分别挂载的包装层**，同样按平台互斥禁用。`danger-full-access` 预设把 approval 设为 `never`——这解释了为什么在该模式下"需要审批的动作被自动拒绝"且不应再请求提权。

---

## 9. Host ↔ Client 协议

### 9.1 传输

- 网关 `dsh-api-gateway/lib/index.js`：`REMOTE_STREAM_MUX_PATH = "/api/remote.mux"`（:12）、`REMOTE_EVENT_STREAM_ENDPOINT = "$events"`（:14）、`registerUpgrade(route)`（:642）、客户端 id 用 `randomUUID()`（:814/:860）。
- 全仓库 grep `registerRoute|registerUpgrade|registerIndexInjection|fallbackHandler` → 只有 **4 处命中，且只有 `registerUpgrade` 存在**。也就是说网关只暴露一个升级路由，其余全走 HTTP。
- `dsh-host-webserver` 配置：`host: union("127.0.0.1","0.0.0.0")`、`port: natural().max(65535)`（:142-143）。

### 9.2 Remote 命名空间（完整 10 个）

```
account · credentials · directoryPicker · fileReferences · job
session · settings · skills · terminal · workspace
```

线名格式在 `dsh-typert-registry/lib/index.js:34`：`` `${descriptor.namespace}/${descriptor.method}` ``，`validateWireName` :525。

被 `@Remote` 装饰的方法（跨控制器）：
`archiveSession, attachment, cancel, create, createDirectory, delete, fork, initializeDefault, insertBefore, insertSessionBefore, kill, list, modelCatalog, openWorkspacePath, page, pick, pinSession, projections, prompt, rename, search, selectModel, unarchiveSession, unpinSession, updateQueue, workspacePathApplications`；流式模式：`changes, control, follow, list, retain, watch, watchExpiry`。

### 9.3 事件转发

`dsh-api-remotes/lib/index.js` 的 `API_REMOTE_FORWARDED_EVENTS` 是 **27 条** Cordis 事件白名单：

```
agent-preset/selected · approval/request(waterfall)
api-session/{activity,added,error,removed,status} · commands/change
deepseek-account/{session-expired,model-sign-in-required}
credentials/{record-updated,reference-updated} · goal/activation-changed
cordis/{request-run,request-run-resolved,dynamic-package,dynamic-retract,inspect-query,inspect-query-resolved}
llm/adapters-updated · permission-presets/catalog-changed
plugin-manager/{changed,install-log,install-state} · settings/document-updated
schedule/changed · user-questions/request
```

注册方式：`ctx.typertGateway.registerRemoteEvents(..., { home: homedir() })`（:134），队列类 `RemoteEventQueue`（:165）。

### 9.4 SDK 模式

`dsh-sdk-protocol/lib/index.js`（7,336 B）是换行分隔的 JSON-RPC 2.0（`JsonRpcLineTransport`，`-32601` 未知方法、`-32603` 处理器失败）。`dsh-sdk-jsonrpc-server` 的 `handleRequest` 只接受三个方法：`initialize`、`session/prompt`、`shutdown`；通知为 `session.event`、`session.status`、`subagent.started`、`subagent.finished`。

---

## 10. 会话持久化、压缩、遥测、凭据

**持久化**：追加式 JSONL，`SESSION_FORMAT_VERSION = 4`（`dsh-session/lib/index.js:56`）。压缩由独立包 **`dsh-session-persistence-jsonl`** 承担，它 `import { createZstdCompress, createZstdDecompress, zstdCompress, zstdDecompress } from "node:zlib"`（`lib/index.js:15`），后缀函数明确返回 `.jsonl.zstd`（Zstandard）或 `.jsonl`（明文）（:745-748）。

文件命名规则（:464-474）也是硬编码的：

```js
const CANONICAL_LOG_FILENAME = /^session(?:\.v([1-9][0-9]*))?\.jsonl$/u;
return generation === 0 ? "session.jsonl" : `session.v${generation}.jsonl`;
```

即第 0 代叫 `session.jsonl`，之后每代带 `.vN`；子代理各自落在 `subagents/<id>/session[.vN].jsonl`（:14-15）。:3438 还显式兼容读取旧的 `.jsonl` / `.jsonl.zstd` 命名。格式链 v0→v4；V3→V4 的变更：提升工具结果、重命名消息来源、闭合被中断的轮次、追加父目录事实。

**压缩**（`dsh-compaction-basic`）：`DEFAULT_THRESHOLD_RATIO = .8`、`DEFAULT_RETAIN_RATIO = .16`、`headroomTokens ?? 65536`；可调键 `thresholdRatio, headroomTokens, retainRatio, retainTokens, maxTokens`。

**目标轮次**（`dsh-goal-round-driver`）渲染成：

```
<goal_round>Objective: …
Round: n/maxGoalRounds
…</goal_round>
```

**遥测**：`dsh-host-product-telemetry-otel` 的 `serviceName` 是 **必填配置**（`lib/index.js:12` `serviceName: z.string().required()`，:50 映射成 OTel 的 `"service.name"`），值由组合层给定——`dsh-base/cordis.patch.yml:53` 写的是 `serviceName: deepseek-harness-desktop`。默认端点 `https://dsh-otel-collector.deepseeksvc.com/v1/logs`（`lib/index.js:10`）。

顺带挖到的产品标识（同一棵树里）：

```js
product: "deepseek-harness",
url:     "https://github.com/deepseek-ai/deepseek-harness"
"x-deepseek-harness-user-id":       this.dependencies.resolveUserId(),
"x-deepseek-harness-session-id":    String(options.sessionId)
// ACP 实现的 implementation name：
agent({ name: "deepseek-harness-acp" })
// 默认工作区落点：
<Documents>/deepseek-harness/<DEFAULT_WORKSPACE_DIRECTORY>
```

自定义请求头 `x-deepseek-harness-user-id` / `x-deepseek-harness-session-id` 是服务端关联会话用的——这是外部可观测的遥测面。

**凭据分层**（`dsh-credentials-local/lib/index.js:13-20`）：
`… > $DSH_HOME/.credentials.yaml（provider 管理，可写）> $DSH_HOME/.env（只读回退）`。
本机 `.credentials.yaml` 顶层键（仅名称）：`version, refs, DEEPSEEK_API_KEY, STRATA_API_KEY, records{kind, payload{version, secret}}`。

**Home 路径**（`dsh-home-paths`）：`DSH_HOME_DIR_NAME = ".dsh"`、`DSH_HOME_ENV = "DSH_HOME"`，优先级 配置路径 > `$DSH_HOME` > `~/.dsh`。

**更新**：`app-update.yml` 指向 `https://download.deepseek.com/dsh-desk/feeds/win-x64/`，channel `nightly`；外壳 `package.json` 里另有强制更新策略 `origin: https://harness.deepseek.com`、`authentication: "anonymous"`。构建溯源指纹：`dshBuildCommit: 04f392c9ddd144fa426da2045178797da6db6c11`、`dshBuildDirty: false`、`dshDesktopAppId: com.deepseek.dsh`。

---

## 11. REA 自动分析 vs 人工静态分析（方法学对比）

### 11.1 REA 的产出

`rea/app-graph.json`：**376,204,805 B**，schema `JavaScriptApplicationGraph`，根节点 `jag_node_197e4b…`。

流式统计：**187,159 个 `node_id` / 39,530 条 `edge_id`**。节点类型直方图：

```
expression 13826 · require 7366 · module 9109 · unknown 18206 · function 1219
binding 836 · package 700 · artifact 824 · network 1183 · route 143
parameter 847 · task 418 · promise 46 · timer 8 · worker 25 · endpoint 23
boundary 51 · literal 5
```

早期摘要：relevant_files 10,102 · parsed_javascript_files 9,110 · visited_ast_nodes 9,966,129 · findings 30,314 · parse_failures 5 · **IPC operations 83（全部 dynamic，0 literal channels）** · **context_bridge_apis 11** · native_addon_bindings 3 resolved / 7 native-addon 节点。

覆盖状态是诚实的：

```json
"analysis_failure": { "code": "resource_constraint",
  "reported_limits": { "parent_result_budget_bytes": 1839717692,
                       "application_projection_required_bytes": 162304 } },
"coverage": { "status": "partial",
  "limits": [{ "name": "javascript_analysis_parent_result_budget_bytes",
               "value": 1839717692 }] }
```

### 11.2 一次自我纠正（本报告最重要的方法论结论）

早期我得出过结论："DSH 里没有任何 `exposeInMainWorld`，REA 报的 11 个 context-bridge API 是第三方噪声。"

**这个结论是错的**，原因是我只 grep 了 `re/verified/dsh/`（即 asar 里的 `dsh/` 子树），完全漏掉了 asar 根部的 Electron 外壳。

补做外壳分析后，两边精确对上：

| 指标 | REA 自动报告 | 人工静态分析 | 一致性 |
|---|---|---|---|
| context-bridge API 数 | **11** | 5 个 preload 里 **11** 个 `exposeInMainWorld` | ✅ 完全一致 |
| IPC 操作数 | **83** | preload 中 `ipcRenderer.(invoke\|send\|on\|sendSync)` **48** + main.js 中 `ipcMain.(handle\|on)` **35** = **83** | ✅ 完全一致 |
| 字面量通道数 | **0** | main.js 里 **45** 个字符串字面量通道名 | ❌ REA 未能解析 |

第三行就是 REA 的能力边界所在：DSH 把通道名集中放在 5 张常量表里，调用点写成 `ipcMain.handle(DESKTOP_IPC.boot, …)`。REA 的 AST 走查把它记成"动态通道"，于是报出 0 个。人工读一遍就能拿到全部 45 个名字。

**修正后的判断**：REA 的 Electron 侧发现**是有效的、确实关于 DSH 本身**，只是**浅**——它数出了边界上的调用点，却没能解析出边界的名字。

### 11.3 真正的边界在哪里

REA 的 Electron 分析器找的是 `ipcMain`/`ipcRenderer`/`contextBridge`。但 DSH 的**实质**边界不在这三层：

| REA 视角 | DSH 实际情况 |
|---|---|
| Electron IPC（83 处） | 只承载外壳 UI 能力（快捷键、目录选择、更新对话框、引导页） |
| 未识别 | **HTTP + WebSocket `/api/remote.mux` @ 127.0.0.1:19387**，10 个 Remote 命名空间、27 条转发事件 |
| 未识别 | **`dsh-app://` 自定义特权协议 + 反代 + cookie 独占**（真正的鉴权围栏） |
| 3 个 native addon 绑定 | **koffi FFI 动态绑定 17 个 advapi32 + 28 个 kernel32 函数**，无静态导入，静态导入分析完全看不到 |
| — | **Cordis `cordis.patch.yml` 组合**（529 + 565 + 146 行 YAML），DSH 的全部行为语义都在这里 |

### 11.4 为什么"逆向 DSH"这件事 REA 帮助有限

1. **DSH 高度自描述。** 296 份 `README.md` + 279 份 `README.zh.md`；`api-catalog.js`（609 KB，91 服务 / 584 方法 / 81 事件 / 936 类型）由 AST 走查生成并有 CI 新鲜度门禁；`packages.md`（38.8 KB）是现成的插件清单。**这些证据的 `authority` 是 `shipped-artifact`，比任何推断都强。**
2. **DSH 不混淆，但也不发源码映射。** 12,411 个文件全部是可读 ESM/CJS，带 `//#region lib/types/xxx.js` 源路径标记（抽样 400 个 `.js`：203 个含此类标记，共 1,563 处）——等价于保留了原始模块树，反查"这段代码来自哪个模块"几乎零成本。但整个 `dsh/` 子树里 `.js.map` / `.d.ts.map` / `.d.ts` 文件数均为 **0**，而 78 个 `.js` 文件末尾仍留着 `//# sourceMappingURL=client.js.map` 之类的引用。**打包环节剥掉了 map，却没清掉引用**——这是一个可操作的线索：真正的类型与源码映射存在于构建侧，不在工件里。
3. **DSH 不含二进制分析能力。** 289 个包里，**包名**匹配 `binary|ida|ghidra|disas|reverse|pe|elf|macho|capstone` 的是 **0 个**；296 份 `README.md` + 279 份 `README.zh.md` 里提到 Ghidra / Hopper / IDA Pro / JEB 的也是 **0 处**。对源码 grep `ghidra|ida-pro|capstone|angr|objdump|disassembl` 仅 1 处命中，落在 `dsh-web-frontend/dist/assets/langs/mdx-Cmh6b_Ma.js`（一份 MDX 语法高亮文法）里，是误报。
4. **REA 的强项被用上了**：工件识别（`format:"asar"`）、完整性取证（`integrity_contradictions: []` + 双 sha256）、规模测绘（187k 节点）。这些是人工做会非常枯燥的部分。

**分工结论**：REA 负责"这个工件是什么、是否被篡改、有多大、边界上有哪些调用点"；人工静态分析负责"这些调用点叫什么、连到哪里、语义是什么"。

---

## 12. 局限与未验证项

1. **未做二进制逆向。** `DeepSeek Harness.exe`（244,481,512 B，Electron 44.0.0 主二进制）、`koffi.node`（1,058,280 B）、`libreoffice-kit.exe`（178,581,480 B）、`onnxruntime.dll`、`node-pty` 的 `conpty.node` 均未反汇编。需要合法授权的 Ghidra/Hopper/IDA/JEB。
2. **未做动态验证。** 全程静态，未执行任何被还原的 DSH 代码，未启动其沙箱 runner。所有运行时行为描述均来自源码与文档，`authority` 应记为 `shipped-artifact` 而非 `controlled-replay`。
3. **REA 图谱覆盖 partial。** 359 MB 的 `app-graph.json` 无法一次性 `JSON.parse`（两次 OOM/挂起，job `pwsh-136`、`pwsh-467` 被杀），最终用 1 MB 分块 + 4 KB 尾重叠的流式探针统计。图谱中大量节点带 `analysis_failure: resource_constraint`，因此**节点计数是下界**。
4. **REA 的视图投影未跑通。** `inspect-analysis-view` / `trace-application-feature` 的输入契约要靠迭代报错才能摸清：正确形状是 `{"source":{"kind":"inline","evidence":{…完整 Evidence 记录…}},"view":{"kind":"summary|facet|item|page|native"}}`；`application` 是非法键，`source.evidence_json` 非法，且 Evidence 必须内联包含 `environment / limitations / locations / evidence_links`，枚举值必须合法。这一步未最终完成。
5. **REA 无本地会话留存。** `~\.rea`、`LOCALAPPDATA\rea`、`~\.cache\rea` 均不存在；唯一留存的证据是导出的 `rea/app-graph.json`。
6. **第三方依赖未展开分析**（229 个非 `@deepseek-ai` 包）。
7. **`sharedPackages` 只覆盖 `@deepseek-ai/*`**，第三方包不在出厂完整性清单内。

---

## 13. 附录：证据文件索引

| 路径 | 内容 |
|---|---|
| `re/verified/dsh/` | **权威提取结果**，12,412 条目，12,411/12,411 manifest 匹配 |
| `re/verified/dsh/desktop-runtime.json` | 出厂 manifest（2,817,387 B） |
| `re/shell/` | Electron 外壳层（618 文件）：`main.js`、5 个 `preload-*.cjs`、`renderer/*`、外壳自己的 `node_modules` |
| `re/shell/package.json` | `@deepseek-ai/dsh-desktop` 入口 + 构建指纹 |
| `rea/app-graph.json` | REA 图谱（376,204,805 B） |
| `rea/artifact-inspect.json` | REA 工件检查（17,610,570 B） |
| `rea/doctor.json` | REA 环境自检（63,438 B） |
| `rea/trace-sandbox.json` | 对 `@deepseek-ai/dsh-sandbox-windows-acl` 的反向 trace 请求 |
| `rea/_scratch.json`、`rea/llms-full.txt` | REA 能力清单快照（118,782 B） |
| `.work/asar-extract.js` | **修正后**的 asar 提取器（`base = 8 + hdrSize`） |
| `.work/asar-shell.js` | 外壳层枚举/提取脚本 |
| `.work/offset-probe.js` | 定位 `-8` 偏移 bug 的探针 |
| `.work/api-catalog.json` | 从 `api-catalog.js` 抽出的 EVENT/TYPE/INHERITED 三表 |
| `.work/pe-imports.js`、`.work/imports-*.json` | 原生 payload 的导入表 |
| [re/agents-notes-index.md](S:\Develop\agent_harness\re\agents-notes-index.md) | **161 条内部设计决策记录索引**（20,079 B），从出厂 README 提取 |
| `.work/extract-agents-notes.js` | 上述索引的提取脚本 |
| `.work/verify-citations.js` | 38 处行号引用回验（36 精确命中，2 处已修正） |
| `.work/verify-sizes.js`、`.work/verify-pkg-sizes.js` | 22 处字节数/行数断言 + 15 个包的 JS 体量回验 |
| `.work/verify-structure.js`、`.work/verify-events.js`、`.work/verify-behavior.js` | asar 结构、事件白名单、跨包行为断言回验 |
| `.work/check-diagnose-hash.js` | 出厂 manifest 哈希交叉校验（抓出本报告一处错误哈希） |
| `.work/ipc-tables.js` | 5 张 IPC 通道表的逐项计数（抓出本报告一处计数错误） |

> ⚠️ `re/full/dsh/` 是**首次（错误）提取**，payload 整体偏移 8 字节，**不可作为引用来源**。

### 关键 grep 模式（可复现）

```
CreateRestrictedToken|OpenProcessToken|SetEntriesInAcl|CreateProcessAsUserW|advapi32   → 41 命中（4 个包）
registerRoute|registerUpgrade|registerIndexInjection|fallbackHandler                   → 4 命中（仅 registerUpgrade）
DSH_HOME                                                                                → 45 命中
authenticatedUrl                                                                        → 9 命中
"(dsh-[a-z-]+:[a-z-]+)"  on re/shell/main.js                                            → 45 个通道名
exposeInMainWorld  on re/shell/preload-*.cjs                                            → 11 命中
ipcRenderer\.(invoke|send|on|sendSync)  on re/shell/preload-*.cjs                      → 48
ipcMain\.(handle|on)                    on re/shell/main.js                            → 35   （48+35 = REA 报的 83）
\.agents/notes/[a-z]+/[a-z]+/\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md  on */README*.md        → 293 处 / 161 条去重
^\s+key: '     on dsh-tool-cordis/lib/types/api-catalog.js                            → 91
^\s+signature: '  同上                                                                  → 584
createZstdCompress                                                                      → dsh-session-persistence-jsonl
serviceName:                            on */cordis.patch.yml                          → deepseek-harness-desktop
```

---

## 14. 一句话总结

**REA 能逆向 DSH，也确实抓到了 DSH 的 Electron 边界（11 个桥 API、83 处 IPC 调用，与人工计数完全吻合）；但 DSH 的真实架构——`dsh-app://` 反代 + cookie 独占鉴权、`/api/remote.mux` 上的 10 个 Remote 命名空间、koffi FFI 撑起的三平台沙箱、以及 529+565+146 行 `cordis.patch.yml` 拼出的插件组合——是靠人工静态分析、以及 DSH 自己随包分发的高质量文档与自动生成 API 目录还原的。** 对一个不混淆、自带中英双语文档和自描述 API 清单的软件，"逆向"的成本主要花在**覆盖完整**上，而不是**读懂**上；而覆盖完整性，恰恰是这次 asar 头部 8 字节偏移和"漏看外壳层"两个错误所暴露的最大风险点。
