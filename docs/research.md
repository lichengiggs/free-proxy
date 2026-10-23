# free-proxy 当前主线结构说明（2026-10-23）

## 1. 结论

- 当前唯一运行主线：`python_scripts/`
- 历史 TypeScript 方案已清理，不再单独保留档案
- 当前长期技术总览只有这一份文档
- 文档路径：`docs/research.md`
- 2026-10-23 的开源对照见第 10 节。这一轮只改三件事：失败候选在冷却期内直接跳过、聊天走上游真流式、全部失败时返回可操作的诊断。不整仓搬迁，不接入订阅套壳。

## 2. 对外稳定面

- OpenAI 兼容接口：
  - `GET /v1/models`
  - `POST /v1/chat/completions`
- 稳定别名：
  - `free-proxy/auto`
- Python 服务端兼容输入：
  - `auto`
  - `free-proxy/auto`
  - `free_proxy/auto`

## 3. 当前模块分层

### 3.1 Provider Catalog

- 文件：`python_scripts/provider_catalog.py`
- 职责：provider 名称、base URL、API key 环境变量、协议格式、模型 hints、required query
- 约束：这里只存事实，不存 fallback 策略

### 3.2 Provider Routing

- 文件：`python_scripts/provider_routing.py`
- 职责：
  - 解析 `auto` / `free-proxy/...`
  - 产出 `auto` 候选顺序
  - 基于健康状态重排候选模型

### 3.3 Provider Adapter / Transport

- 文件：
  - `python_scripts/provider_errors.py`
  - `python_scripts/provider_transport.py`
  - `python_scripts/provider_adapter.py`
- 职责：
  - 统一 HTTP 传输
  - 处理 OpenAI / Gemini 协议差异
  - 保留 OpenRouter 免费模型过滤、Ofox `:free` 过滤、Gemini 文本模型过滤
  - GitHub / Groq / NVIDIA / Ofox 在 `/models` 失败或返回空列表时回退 `model_hints`

### 3.4 Service

- 文件：`python_scripts/service.py`
- 职责：
  - provider key 状态
  - verify / probe
  - relay accessor
  - token budget 学习与重试
  - provider 侧推荐模型与本地状态维护

### 3.5 OpenAI Relay

- 文件：
  - `python_scripts/request_normalizer.py`
  - `python_scripts/fallback_policy.py`
  - `python_scripts/protocol_converter.py`
  - `python_scripts/response_normalizer.py`
  - `python_scripts/openai_relay.py`
- 职责：
  - 校验公开模型面，接受 `auto` / `free-proxy/auto` / `free_proxy/auto`，对外模型名归一为 `free-proxy/auto`
  - 统一提取 `requested_model`、`messages`、输出预算
  - 构建 health + hints + 静态 fallback 候选池
  - 按错误分类执行 fallback
  - 上游调用固定 `stream: false`；客户端要求流式时，把上游 JSON 包装成 OpenAI SSE

### 3.6 HTTP Server

- 文件：`python_scripts/server_fastapi.py`
- 职责：
  - 路由
  - 请求解析
  - 统一错误返回
  - relay 结果写回

## 4. 当前路由规则

- `free-proxy/auto` / `auto` / `free_proxy/auto`：按健康驱动候选池路由
- `coding` / `free-proxy/coding` / `free_proxy/coding`：拒绝并返回 `model_deprecated`
- `requested_model` 只作为内部路由偏好，不属于公开稳定接口

## 5. 当前验证链路

- provider key 保存后，通过 `verify_provider_key()` 先拉模型列表，再做真实 probe
- probe 使用小输出预算，真实 chat 使用常规输出预算
- token limit 错误会写入本地 `data/token-limits.json` 并自动重试一次
- 健康状态会写入本地 `data/model-health.json`
- 前端选中的模型偏好会写入本地 `data/preferred-model.json`
- 这三个文件都是运行时状态，不入库
- provider `/models` 不稳定时，路由仍需保留 `model_hints` 兜底
- provider 动态列出的候选模型会在当前 provider 静态默认模型失败后再懒加载，不等所有 provider 都失败

## 6. 验收命令

```bash
uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'
```

## 7. Debug 排障模式

- 启动命令：`uv run free-proxy serve --debug`
- 作用：把请求、路由、上游状态和错误分类打印到终端
- 约束：不打印 API key；字段名是 `messages` 或 `prompt` 的值会跳过。调试路由 `/chat/completions` 可能打印响应体前 300 个字符，失败时会记录上游错误正文
- 适用场景：远程用户无法稳定复现，只能贴终端日志

## 8. 对外文档约束

- 对外文档只保留 `GET /v1/models` 和 `POST /v1/chat/completions`
- 稳定模型别名只保留 `free-proxy/auto`
- `coding` 只作为历史兼容说明，不作为推荐写法
- `/chat/completions` 只用于网页调试，不写成对外主接口

## 9. 本地流式验收注意事项

- 验证 `127.0.0.1` 流式链路前，先检查 shell 里的 `http_proxy` / `https_proxy`
- 如存在代理，必须设置 `NO_PROXY=127.0.0.1,localhost` 或临时清空代理变量
- 否则代理可能注入 `Connection: keep-alive` / `Proxy-Connection: keep-alive`，把已正常结束的 SSE 误判成服务端未关闭连接

## 10. 体验改进与开源对照（2026-10-23）

这一轮从使用体验和等待时间做决定。开源仓库只提供做法，不作为底座。下面 10.2 以后是筛选证据，Star 和时间是 2026-10-23 的快照，已换算为 Asia/Shanghai。

### 10.1 这一轮要改的体验

用户成功拿到回复时，仍然只看到正文，不看到换了哪一家。要缩短的是失败候选造成的空等，以及整段生成完才出现第一个字。

现状：

- `provider_routing.py` 的健康分会把近期失败的模型排到后面，冷却期（默认 600 秒）内仍然放进候选，下一轮请求还是可能先打到它。
- `fallback_policy.py` 对限流算了 `sleep_seconds`，`openai_relay.py` 没有使用这个等待，失败后立刻串行请求下一家。每一家都要等自己的上游超时。
- `errors.py` 在正文看不出额度字样时，把 HTTP 429 一律记成 `rate_limit`。免费层常用 429 表示当日额度用尽。
- 全部候选失败时，公开接口只有 `all candidates failed`，没有 `provider`、`model`、`category`、`suggestion`。
- 上游固定 `stream: false`，服务端再把完整 JSON 包成 SSE。控制台文案写的是在等首个流式响应，实际要等整段生成结束。

按这个顺序改：

1. **冷却期内跳过，不在请求里睡觉。** 限流记下 `Retry-After`，没有这个头就冷却约 60 秒，期间从 `auto` 候选里拿掉该模型。额度用尽用更长的重置窗口，并且不要在几分钟后排回队首。鉴权失败则这次停止该 provider，后续消息也不要继续撞同一把 Key。做法来自 uni-api 的渠道冷却和 Bifrost `core/failureclass.go` 里对 5xx、限流短语、余额耗尽、地区不可用的分开。地区和鉴权不在 `auto` 里无限轮换。落点是 `health_store.py`、`provider_routing.py`、`errors.py`、`fallback_policy.py`。
2. **聊天改为上游真流式。** 客户端要求流式时，按上游流式读出并原样转给客户端，结束帧必须完整。探测继续用小输出预算，聊天用正常预算。结束帧的行为对照 new-api RelayKit 和 Bifrost，只学行为，不复制 AGPL 代码。aiproxy 的 `streamfake` 是为了避免非流式长请求被中间层掐断；当前假 SSE 已经是这一类，解决不了首字等待。
3. **全部失败时对齐控制台诊断。** 返回最后一次失败的 `provider`、`model`、`error`、`category`、`status`、`suggestion`。验证和探测已经是这组字段。成功的请求不附带内部跳转过程。

这一轮不改这些：

- 冷却生效之前不新增 Cloudflare、Cerebras、Cohere。候选变多会让失败路径更长。
- 不引入语义缓存、花费看板、虚拟 Key、多租户账单。
- 不复制 LiteLLM `router.py`，也不复制 new-api 的 `relaykit/`。
- 不把 `coding` 改回可用模型，不增加 `free-proxy/auto` 以外的稳定别名。

### 10.2 筛选标准

free-proxy 的边界是：用户用各厂商公开、合规的免费层或自己申请的 API Key，本地聚合成 `free-proxy/auto`，失败时自动换下一家，调用方只看到 OpenAI 兼容接口。不把消费者订阅、网页 Cookie、逆向协议或多人拼车包装成“免费 API”。

同时看五件事：

| 维度 | 通过 | 降级或排除 |
|---|---|---|
| 更新时间 | 2026-10 仍有提交或发版 | 超过约 90 天无功能提交，或仓库已归档 |
| Star | 作为社区验证，1k 以上优先看 | Star 很高但产品是套壳时，Star 不构成采用理由 |
| 开发难度 | 能定位到一个模块，并映射回现有 Python 文件 | 单体仓库、企业计费、多租户控制台缠在一起 |
| 核心是否完成 | README 有端到端路径；近期 PR 在修转发链路；未关闭 issue 以边界和功能请求为主 | 主路径仍在反复坏掉，或项目已停更 |
| 合规 | 官方 API Key、官方免费层 | `refresh_token` 打消费者后端、Cookie、TLS 指纹伪装、订阅拼车 |

开发难度按能不能放进当前仓库判断：低表示 Python 且能对照单模块改写；中表示语言不同但模块边界清楚；高表示整仓搬进来会淹没现有主线。

许可证单独看。MIT 和 Apache-2.0 可以在保留声明的前提下改写进本仓库。AGPL-3.0 和 GPL-3.0 不复制进当前 MIT 服务。

### 10.3 总表

| 项目 | Star | 最近活动（Asia/Shanghai） | 语言 / 许可证 | 难度 | 处置 |
|---|---:|---|---|---|---|
| [mozilla-ai/any-llm](https://github.com/mozilla-ai/any-llm) | 2,228 | 2026-10-23 17:54 发布 1.40.1 | Python / Apache-2.0 | 低 | 证据：官方 SDK 适配。这一轮不改目录 |
| [BerriAI/litellm](https://github.com/BerriAI/litellm) | 61,886 | 2026-10-23 18:18 仍在推送；v1.106.2 于 2026-10-21 | Python / 非 `enterprise/` 为 MIT | 高 | 证据：限流后换候选。不搬 `router.py` |
| [maximhq/bifrost](https://github.com/maximhq/bifrost) | 9,040 | 2026-10-23 18:37 仍在合并 PR | Go / Apache-2.0 | 高 | 这一轮用 `failureclass.go` 的分类 |
| [yym68686/uni-api](https://github.com/yym68686/uni-api) | 1,269 | 2026-10-22 12:12 仍有提交 | Rust / Apache-2.0 | 中 | 这一轮用官方渠道冷却；排除 Codex engine |
| [labring/aiproxy](https://github.com/labring/aiproxy) | 564 | 2026-10-22 15:07 发布 v0.7.6 | Go / MIT | 中 | 证据。`streamfake` 不解决首字等待 |
| [QuantumNous/new-api](https://github.com/QuantumNous/new-api) | 50,558 | 2026-10-23 14:31 仍在推送；v1.0.0-rc.46 于 2026-10-22 | Go / AGPL-3.0 | 高 | 只读真流式结束行为，不复制代码 |
| [Portkey-AI/gateway](https://github.com/Portkey-AI/gateway) | 13,257 | 最近合并 PR 停在 2026-05-25；v1.15.2 于 2026-01-12 | TypeScript / MIT | 中 | 设计参考，不再作为二次开发底稿 |
| [tbphp/gpt-load](https://github.com/tbphp/gpt-load) | 7,166 | 2026-10-22 20:00 发布 v1.4.13 | Go / MIT | 高 | 调度思路可看；订阅渠道不碰 |
| [cheaper-inference/OmniRoute](https://github.com/cheaper-inference/OmniRoute) | 80,077 | 2026-10-23 12:09 仍在推送 | TypeScript / MIT | 高 | 只借鉴条款风险目录；不整仓重组 |
| [router-for-me/CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) | 56,049 | 2026-10-23 08:10 发布 v8.0.40 | Go / MIT | — | 不重组 |
| [Wei-Shaw/sub2api](https://github.com/Wei-Shaw/sub2api) | 44,677 | 2026-10-23 17:10 仍在推送 | Go / LGPL-3.0 | — | 不重组 |
| [decolua/9router](https://github.com/decolua/9router) | 31,269 | 2026-10-23 16:35 仍有推送；最新 Release v0.5.35 停在 2026-07-16 | JavaScript / MIT | — | 不重组 |

Star 不能单独排序。OmniRoute、CLIProxyAPI、sub2api、9router 的 Star 都高于 any-llm、uni-api 和 aiproxy，产品里却包含订阅套壳、Cookie 或拼车。

### 10.4 对照过的仓库

下面是证据，不是平行的待办。只有 10.1 的三步进入这一轮。

#### any-llm：provider 适配，不是网关

仓库定位是一个 Python 函数调用多家官方 SDK，自己不转发 HTTP。README 写明走官方 SDK，并明确对比 LiteLLM 是重写了厂商接口。Python 要求 3.11+，和本仓库一致。2026-10-23 的 1.40.1 仍在修 Gemini 模型 id、OpenAI metadata 和流式 tool call。未关闭 issue 集中在 Bedrock 多段 system、Gemini 工具结果里的图片、实时会话这些边界，聊天主路径在持续发版。

- 设计：`provider` 与 `model` 分开，错误信息直接可操作。这和本仓库 `provider_catalog.py` 只存事实、路由另做的分法一致。
- 产品：按需安装 provider，而不是一次塞进所有厂商。控制台可以继续“先配一家 Key，再选推荐模型”。
- 代码：`src/any_llm` 里的 Gemini、Groq、Mistral 转换适合当规格读。Apache-2.0 允许带声明改写。不把整个 SDK 依赖引进来，本仓库上游调用保持 `httpx`。它没有 fallback 服务器，不能拿来替换 `openai_relay.py`。

#### LiteLLM：重试策略，不搬 Router 文件

`litellm/router.py` 单文件约 794KB，和缓存、花费、虚拟 Key 绑在一起。2026-10-22 合并的 PR #47962 说明当前策略：一个分组里每个 deployment 都试过之后，再整体重试一轮。同日还有网关缓存点和用量字段的修复。未关闭 issue 有 5,635 个，抽样是翻译和边缘接口，不是“fallback 不存在”。`enterprise/` 目录使用另一份许可证，其余是 MIT。

- 设计：同一部署先区分“再试一次”和“换下一家”。限流换候选，鉴权失败停止。这和 `fallback_policy.py` 已有的 `retry_same_provider` / `next_candidate` / `auth` 停止是同一类决策。
- 产品：不引入虚拟 Key、花费看板和多租户。那些是网关公司的控制台，不是本仓库“配好 Key 就能用”的路径。
- 代码：不复制 `router.py`。限流之后换下一家的方向可以保留，额外的整组再试一轮不进入这一轮；等待用冷却跳过，不在单次请求里睡眠。

#### Bifrost：错误分类表

Bifrost 是 OpenAI 兼容网关，README 写了自动 failover、多 Key 负载均衡，上游是 OpenAI、Anthropic、Bedrock、Vertex、Groq、Cerebras、Mistral 等官方接口。2026-10-23 仍在合并流式分片和未加前缀模型的路由修复。未关闭 issue 约 1,335 个，抽样是 Bedrock 工具体、实时语音、Anthropic 流式 tool arguments，说明核心网关在跑，表面很宽。

`core/failureclass.go` 把错误分成可对同一把 Key 重试的 5xx、需要轮换 Key 的限流短语、余额耗尽、地区不可用。Apache-2.0，文件相对独立。

- 设计：429 不一定是限流。余额用尽、地区封锁、参数不兼容要分开。地区和鉴权不应在 `auto` 里无限轮换。
- 产品：失败时继续给调用方一个 OpenAI 兼容错误；内部分类只用于决定下一跳。诊断字段保持现在的 `action`、`provider`、`model`、`error`、`category`。
- 代码：把短语表翻译进 `provider_errors.py`，保留 Apache 声明。不引入 Go 核心、语义缓存、虚拟 Key 或企业插件。

#### uni-api：官方渠道的冷却和限速

README 把自己定义成个人向的 one-api 替代：一份配置聚合多家后端，统一成 OpenAI 格式，支持加权、轮询和多 Key 轮询，失败后冷却再恢复。官方后端包括 Gemini、Groq、Cloudflare、OpenRouter、Cohere。2026-10-22 的提交仍在修“不透明上游错误按 bad gateway 重试”。未关闭 issue 约 15 个，多数是模型元数据、JSON Schema、重排和图片编辑；#171（2026-04-03）仍指出 `keepalive_interval` 可能盖住超时、从而不触发 failover。聊天和负载均衡主路径可用，这条超时边角还没合上。

同一份 README 的 `engine: codex` 会把 `account_id,refresh_token` 换成 access token，请求 `https://chatgpt.com/backend-api/codex`。这是消费者账号后端，不在本项目边界内。

- 设计：渠道失败后冷却一段时间，而不是立刻再打；每把 Key 有自己的频率上限；429 单独冷却。动态模型列表失败时仍要有静态模型兜底，这一点本仓库已经有 `model_hints`。
- 产品：同一厂商多把自己的 Key 可以轮询。这是用户自己的 Key，不是把别人的订阅放进池子。可选的上游前审查能降低内容违规导致的封禁，但不是当前主路径。
- 代码：`src/routing.rs` 和官方 `src/providers/` 可以对照改写到 `provider_routing.py`。排除 Codex engine、`chatgpt.com` 和 refresh token 刷新。不把 Rust 服务嵌进来。

#### aiproxy：小而完整的渠道选择

Sealos 团队的网关。README 的主路径是 OpenAI、Claude、Gemini、Responses 之间的协议转换，按渠道优先级和错误率选路，失败再试。2026-10-22 发布 v0.7.6。GitHub 的 open issue 计数是 17，其中包含 PR；抽样到的未关闭 issue 是模型渠道、日志库和并发限制，没有“转发不可用”。有一条功能请求问 Antigravity CLI，仓库本身没有把该订阅渠道做成内置能力。

- 设计：渠道排序看近期错误率，而不只看静态优先级。相同请求缓存和 `<think>` 拆分是它自己的插件，不进入这一轮。
- 产品：`core/relay/plugin/streamfake/` 在内部用流式读取，避免非流式长回复被中间层超时掐断，再按客户端原来的形式返回。本仓库今天是上游固定 `stream: false`，再把 JSON 包成 SSE。若以后要减轻长回复超时，先看这个插件的行为，而不是先改前端滚动。
- 代码：MIT，模块在 `core/relay/plugin/streamfake/` 和 `core/relay/adaptor/`。语言是 Go，适合移植行为并补 Python 测试，不适合原文件拷进仓库。多租户账单、组织配额不进入本仓库。

### 10.5 只作设计证据

#### new-api

自托管网关，README 要求上游 Key 和账号必须合法取得，并遵守厂商条款。RelayKit 在 OpenAI Chat、Responses、Anthropic Messages、Gemini 之间做流式转换。2026-10-23 的合并 PR 仍在修 Responses 流结束、工具调用合并和日志里的查询凭据。未关闭 issue 约 1,400 个，抽样大多是计费和界面增强，也有“流正常结束却被当成成功、不再重试”这类转发边角。

核心转发是完成的，产品形态是团队额度、账单和渠道分发。许可证是 AGPL-3.0，不能把 `relaykit/` 复制进本仓库。可借鉴的只有行为：真实上游流要有明确结束；空的结束帧不能记成成功；工具调用片段要按 index 合并。

#### Portkey AI Gateway

MIT，README 的主路径是 2 分钟起一个本地网关，用配置声明重试、fallback、负载均衡和 guardrails。主分支最近一次合并停在 2026-05-25，发布标签停在 2026-01-12 的 v1.15.2。2026-10 仍有人开 issue，例如 Anthropic `/v1/messages` 打到 OpenAI provider 返回 500、Bedrock 流中途丢掉异常。问题还在进，修复没有跟上。

fallback 配置和“guardrail 是插件、失败策略与供应商调用分开”可以留作以后的形状。现在不把它当二次开发底稿。

#### gpt-load

MIT。官方 API Key 渠道和 Codex、Claude、Antigravity、Grok 订阅渠道共用一套调度：权重、重试、冷却、拉黑、会话粘性。2026-10-22 仍在发版。2026-10-23 的未关闭 issue #906 就是 Antigravity 额度窗口显示错误，说明订阅渠道已经是当前维护中心。

多凭据冷却和失败隔离可以对照 `health_store.py`。订阅 OAuth、回调端口和拼车不进入实现。因为两套凭据写在同一调度里，不整模块移植。

#### OmniRoute

MIT，Star 约 8 万，README 声称一个入口覆盖大量免费层，并写明额度来自用户自己向第三方申请的免费层，不是项目发放的代币。它同时提供 `tos: avoid` 目录，并说这些提供商默认不进 `auto`。同一份 README 还包含订阅阶梯、OAuth、网页 Cookie 提供商、共享订阅的 Key 池，以及 TLS 指纹伪装。

可取的是那份条款风险目录：进 `auto` 之前先标记厂商条款，风险项默认不进候选池。分层熔断（整个厂商、单把 Key、单个模型）也和现有健康状态同方向。Cookie、伪装指纹、订阅池和整仓都不重组。仓库体积和 478 个未关闭 issue 也说明它不适合拆进当前主线。

### 10.6 明确不重组

这些仓库更新活跃、Star 高，核心也在持续打补丁。排除原因是产品目标和使用方式会把封号风险带进 `free-proxy/auto`。

| 项目 | 读到的核心 | 排除原因 |
|---|---|---|
| CLIProxyAPI | 把 Antigravity、ChatGPT Codex、Claude Code、Grok Build 等包装成 OpenAI / Gemini / Claude API。2026-10-23 的 PR 仍在改 Codex、Claude 和 Antigravity 转发 | 用编码工具或消费者入口的额度对外提供 API |
| sub2api | README 写明 Claude、OpenAI、Gemini、Grok 订阅统一接入，并支持拼车分摊 | 订阅共享 |
| 9router | README 写明把 Claude Code、Codex、Cursor、Copilot、Antigravity 接到“免费” Claude / GPT / Gemini。2026-10 仍有推送，未关闭 issue 约 2,682；最新 Release 停在 2026-07-16 | 以绕开官方 API 额度为主 |
| uni-api 的 Codex engine | `chatgpt.com/backend-api/codex` 加 refresh token 自动换 access token | 只排除这个 engine，不否定它的官方渠道调度 |
| OmniRoute 的 Cookie / TLS stealth / 订阅阶梯 | 和官方 Key 路由写在同一产品里 | 只排除这些路径 |

另外三个看起来相近、但不作为底稿：

- `songquanpeng/one-api`：37,230 Star，MIT，最后推送停在 2026-01-09，未关闭 issue 约 1,040。维护已经转到 new-api 一系。
- `lm-sys/RouteLLM`：5,630 Star，Apache-2.0，最后推送停在 2024-08-10。它是质量和成本路由的研究框架，不是可运行的免费层网关。
- `tensorzero/tensorzero`：11,710 Star，2026-06 后归档。`Helicone/ai-gateway` 最后推送停在 2025-11-21，而且是 GPL-3.0。`theopenco/llmgateway` 核心是 AGPL-3.0，README 写明不接受新增 provider 的 PR，近期合并的是账单和退款邮件。

### 10.7 和当前代码的对应

| 顺序 | 现有模块 | 要改成 | 证据来源 |
|---|---|---|---|
| 1 | `health_store.py`、`provider_routing.py` | 冷却期内的模型不进入 `auto` 候选 | uni-api 渠道冷却 |
| 1 | `errors.py`、`fallback_policy.py` | 限流、额度用尽、鉴权、地区分开；请求路径里不睡眠 | Bifrost `core/failureclass.go` |
| 2 | `provider_adapter.py`、`response_normalizer.py` | 聊天按上游真流式转发，结束帧完整 | new-api RelayKit、Bifrost 的流式行为 |
| 3 | `openai_relay.py` | 全部失败时带上最后一次的 provider、model、category、suggestion | 控制台验证和探测已有的诊断字段 |

`provider_catalog.py` 里尚未收录、且合规网关已经按普通 API Key 接入的 Cloudflare Workers AI、Cerebras、Cohere，留到冷却生效之后再核对条款。目录站 [abbosaliboev/free-ai-bible](https://github.com/abbosaliboev/free-ai-bible)（约 190 Star，2026-10-22 更新）和 [CYBIRD-D/FREE-LLM-API-Provider](https://github.com/CYBIRD-D/FREE-LLM-API-Provider)（约 113 Star，2026-10-13 更新）只用来找名字。

二次开发如果搬入 Apache-2.0 或 MIT 片段，保留原版权声明。冷却和错误分类先补测试，再改路由。
