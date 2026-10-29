# free-proxy 当前主线结构说明（2026-10-23）

## 1. 结论

- 当前唯一运行主线：`python_scripts/`
- 历史 TypeScript 方案已清理，不再单独保留档案
- 当前长期技术总览只有这一份文档
- 文档路径：`docs/research.md`

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
- Cloudflare 的 base URL 由 `CLOUDFLARE_ACCOUNT_ID` 填进模板，已配置条件是 token 和合法 Account ID 同时存在。

### 3.2 Provider Routing

- 文件：`python_scripts/provider_routing.py`
- 职责：
  - 解析 `auto` / `free-proxy/...`
  - 产出 `auto` 候选顺序：成功记录、同一次请求刷新列表、hint 兜底

### 3.3 Provider Adapter / Transport

- 文件：
  - `python_scripts/provider_errors.py`
  - `python_scripts/provider_transport.py`
  - `python_scripts/provider_adapter.py`
- 职责：
  - 统一 HTTP 传输
  - 处理 OpenAI / Gemini 协议差异
  - 保留 OpenRouter 免费模型过滤、Gemini 文本模型过滤
  - Groq / NVIDIA / AMD / Cloudflare 在 `/models` 失败或返回空列表时回退那一个 `model_hints`

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
  - 构建候选池：有成功记录先试记录，同一次请求刷新列表，hint 只做没有记录或列表失败时的兜底
  - 按错误分类执行 fallback；已经把 2xx SSE 交给客户端之后不再换 provider
  - OpenAI 格式上游始终 `stream: true`。客户端要求流式时按到达顺序转发上游 SSE，包含 `data: [DONE]`；客户端不要求流式时，按顺序拼接 `choices[0].delta.content`，正文为空才改用拼接后的 `delta.reasoning_content`，`finish_reason` 取最后一个非空值，再合成 OpenAI JSON
  - 适配器只返回 JSON body 时保留现有 JSON 归一化；客户端要求流式且没有 SSE 迭代器时，仍把该 JSON 一次性包装成 SSE。Gemini 聊天使用 `streamGenerateContent?alt=sse`，再映射成 OpenAI SSE

### 3.6 HTTP Server

- 文件：`python_scripts/server_fastapi.py`
- 职责：
  - 路由
  - 请求解析
  - 统一错误返回
  - relay 结果写回

## 4. 当前路由规则

- `free-proxy/auto` / `auto` / `free_proxy/auto`：先试最近一次成功的模型，同一次请求刷新列表，hint 只做兜底
- `coding` / `free-proxy/coding` / `free_proxy/coding`：拒绝并返回 `model_deprecated`
- `requested_model` 只作为内部路由偏好，不属于公开稳定接口
- 冷却中的候选不会进入 `build_auto_candidates()`。转发循环在调用上游前再检查一次，同一次请求里刚写下的 provider 冷却会挡住已经生成的后续模型
- `rate_limit`、`quota`、`auth` 按 provider 冷却。`server`、`network`、`model_not_found`、`unknown` 按 model 冷却。`token_limit` 不写入冷却
- `rate_limit` 采用合法 `Retry-After`（秒数或 HTTP 日期，且不超过 15 分钟），否则 60 秒。`quota` 为 6 小时。`auth` 保持到该 provider 当前 key 的哈希变化
- 冷却写在健康记录的 `cooldown_until` 上。转发路径不 `sleep`
- 全部候选都在冷却中时，直接返回现有 502，不再补打冷却中的上游

## 5. 当前验证链路

- provider key 保存后，通过 `verify_provider_key()` 先拉模型列表，再做真实 probe
- probe 使用小输出预算，真实 chat 使用常规输出预算
- token limit 错误会写入本地 `data/token-limits.json` 并自动重试一次
- 健康状态会写入本地 `data/model-health.json`，失败记录可以带 `category`、`scope`、`cooldown_until`，鉴权失败再带 key 哈希。文件不保存 API key 原文
- 前端选中的模型偏好会写入本地 `data/preferred-model.json`
- 这三个文件都是运行时状态，不入库
- `free-proxy/auto` 对每个已配置 provider 的顺序是：成功记录、同一次请求刷新列表、hint 兜底
- 没有可用的成功记录，或 `/models` 失败、筛完没有合格模型时，才使用该 provider 剩下的那一个 `model_hints`
- 某个 provider 整家处于 `rate_limit`、`quota`、`auth` 冷却时，不为它拉列表，也不插入它的候选

## 6. 验收命令

```bash
uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'
```

同一条命令会跑 `python_scripts/tests/test_public_contract.py`。自动流水线还要求这份文件和默认分支的 blob 一致，并且测试方法数量不能比默认分支少。

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
