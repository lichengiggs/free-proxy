# Python Backend 报告

## 结论
- 已在 `python_scripts/` 下补齐 Python 后端、provider 客户端、HTTP 服务和测试脚本。
- 支持读取根目录 `.env`，获取 provider 的模型列表，连通检测，并用最小请求返回 `ok` 证明可用。
- 参考 `cheahjs/free-llm-api-resources` 后，补强了 provider 探测策略：加入 GitHub preview 版本头、GitHub/Cerebras 备用模型候选、以及模型失败后的顺序重试。

## 覆盖范围
- Provider：`openrouter`、`groq`、`opencode`、`gemini`、`github`、`mistral`、`cerebras`、`sambanova`
- 功能：`.env` 读取、模型枚举、聊天探测、HTTP 服务、CLI、每个 provider 的 smoke 脚本
- 改进：`github` 使用 `api-version=2024-12-01-preview`；`service.probe()` 会按候选模型逐个尝试，提高命中率。

## 研究结论
- 这个仓库的核心优势不是“统一硬编码一个模型”，而是“按 provider 真实可用模型列表生成/维护候选集”。
- `GitHub Models` 需要 preview API version，且模型来自 `github.com/marketplace/models` 页面，不依赖 `/models` 端点。
- `Cerebras` 的公开文档和可用模型列表更接近“稳定白名单”，所以应该用已知可用模型做优先级兜底，而不是盲测任意模型。
- `OpenRouter` 的 free 模型列表和实际可用模型不完全一致，应该把“模型存在”与“模型可调用”分开处理。

## 代码入口
- `python_scripts/server.py`
- `python_scripts/cli.py`
- `python_scripts/service.py`
- `python_scripts/client.py`

## 改进点
- `python_scripts/config.py`：新增 provider 模型提示与探测候选集。
- `python_scripts/client.py`：GitHub 使用 preview 版本调用；模型列表失败时回退到已知候选。
- `python_scripts/service.py`：probe 支持多模型顺序尝试，返回 `actual_model`。

## 测试
- 已补充 `python_scripts/tests/` 下的单元测试与 provider 矩阵测试。
- 目标校验点：能获取模型 ID、能连通、能返回 `ok`。
