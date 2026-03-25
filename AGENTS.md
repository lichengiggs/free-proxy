# AGENTS.md

## 目标与原则（最小够用）

- 只实现当前明确需求，拒绝过度设计（KISS / YAGNI）。
- 优先可运行、可验证的改动；完成后直接收尾，不扩展无关任务。
- 注释只解释 `Why`，不解释显而易见的 `What`。
- 强制覆盖边界条件：空值、空数组、网络失败、上游异常。

## Python 版关键约定

- `.env` 固定在项目根目录；不要读 home 目录配置。
- 运行与测试统一使用 `uv`：
  - 启动：`uv run free-proxy serve`
  - 测试：`uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'`
- Provider 接入主入口：
  - 元数据：`python_scripts/provider_catalog.py`
  - 客户端：`python_scripts/client.py`
  - 服务编排：`python_scripts/service.py`
  - 前端卡片：`python_scripts/web/index.html`

## 当前对外兼容面（长期有效）

- OpenAI 兼容接口必须保持：
  - `GET /v1/models`
  - `POST /v1/chat/completions`
- 当前公开稳定模型别名：
  - `free-proxy/auto`
  - `free-proxy/coding`
- Python 服务端需要兼容的别名输入：
  - `auto` / `coding`
  - `free-proxy/auto` / `free-proxy/coding`
  - `free_proxy/auto` / `free_proxy/coding`（仅旧配置迁移兼容，不再作为文档推荐写法）

## OpenClaw / Opencode 配置约定（长期有效）

- OpenClaw 配置写入：
  - 文件：`python_scripts/openclaw_config.py`
  - provider id：`free-proxy`
  - 写入模型：`auto`、`coding`
  - 默认主模型仍保持 `free-proxy/auto`，避免破坏旧用户习惯。

- Opencode 配置写入：
  - 文件：`python_scripts/opencode_config.py`
  - provider id：`free-proxy`
  - 写入模型：`auto`、`coding`
  - 文档、示例、验证命令统一使用 `free-proxy/...`。

## 本次 Longcat 接入沉淀（长期有效）

- Longcat 走 OpenAI 兼容入口：`https://api.longcat.chat/openai`。
- 新增 provider 时默认评估 `/models` 可用性；若不稳定，必须提供 `model_hints` 兜底，避免 UI 和验证流程卡死。
- 前端不会回填真实 API key；只展示 `configured + masked` 状态（通过 `/api/provider-keys`）。
- 若手工改 `.env` 后服务未重启，可能出现“状态与实际调用不一致”；优先重启后端再验证。

## 测试与发布

- 采用 TDD（red -> green），测试与实现同步提交。
- 提交前最少执行：
  - `uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'`
  - `npm test`
  - `npx tsc --noEmit`
- 清理中间文档（如 `plan.md`），保留并更新长期文档（`docs/research.md` / README）。

## 安全基线

- 禁止提交真实 API key；`.gitignore` 必须覆盖 `.env`。
- 推送前检查：
  - `git status`
  - `git diff --stat`
  - `rg --smart-case "sk-or-|gsk-|ak_|AIza|csk-|ghp_" src __tests__ python_scripts public`
- 发现泄露立刻停止推送，清理提交历史并轮换对应 key。

## 文档维护

- 复杂功能或重构先写执行计划，规范见 `.agent/PLANS.md`。
- 执行计划属于过程文档，任务完成后应清理；结论沉淀到长期文档。
- 用户文档必须优先覆盖三条真实使用路径：
  - OpenAI / Python SDK：`free-proxy/coding`
  - OpenClaw：`free-proxy/coding`
  - Opencode：`free-proxy/coding`

## 工具规范

- 代码搜索必须优先使用 `rg`，并默认带 `--smart-case`；按需加 `--context`。
