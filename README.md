# free-proxy

[中文](README.md) | [English](README_EN.md)

聚合多家 provider 的免费层，变成一个可用的 token 池，方便个人开发与日常编码。

一句话概览：免费、易用、能足够日常OpenClaw使用。

### 免费额度一览

| 方案 | 稳定性 | 额度 | 成本 |
|---|---|---|---|
| `free-proxy` | 中 | 估算约 3.3k 次/日<br>约 100k 次/月<br>约 300USD/月等价 | 免费 |
| 美国付费 coding plan | 高 | 约 200–10,000 次/月 | 20-200USD/月 |
| 国内付费 coding plan | 高 | Lite 18,000 次/月<br>Pro 90,000 次/月 | 20-200RMB/月 |



## 核心功能

- 聚合 9 家 provider（OpenRouter / Groq / OpenCode / Longcat / Gemini / GitHub Models / Mistral / Cerebras / SambaNova）
- 自动回退：当前模型失败或限流时自动切换到可用模型
- 手动添加模型：支持 `provider+modelId` 直接添加
- 本地 Web 配置：卡片式保存 API Key，直接选模型并更新 OpenClaw
- OpenAI 兼容接口：`http://localhost:8765/v1`

## 快速开始

1) 克隆仓库

```bash
git clone https://github.com/lichengiggs/free-proxy.git
cd free-proxy
```

2) 安装 [uv](https://docs.astral.sh/uv/)（如果还没有）

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 或者用 Homebrew
brew install uv
```

3) 初始化环境并启动

```bash
uv sync                   # 首次运行，自动创建虚拟环境
uv run free-proxy serve   # 启动后端服务
```

小白提示：启动后请保持这个窗口打开，不要关闭。

4) 打开配置页面并保存至少一个 provider 的 API Key

- 访问：`http://localhost:8765`
- 保存 Key 后直接选择模型开始使用

## 常用接入方式

- OpenAI 兼容客户端 / Python SDK
  - Base URL：`http://127.0.0.1:8765/v1`
  - Model：`free-proxy/coding`（代码场景）或 `free-proxy/auto`（通用场景）

- OpenClaw
  - Provider：`free-proxy`
  - 推荐模型：`free-proxy/coding`
  - 保守入口：`free-proxy/auto`

- Opencode
  - Provider：`free-proxy`
  - 如果要写配置文件，路径通常是：`~/.config/opencode/opencode.json`
  - 推荐命令：`opencode run -m free-proxy/coding "Reply with exactly OK"`
  - 保守命令：`opencode run -m free-proxy/auto "Reply with exactly OK"`

## 当前对外行为（与实现一致）

- 标准 OpenAI 兼容接口：
  - `GET /v1/models`
  - `POST /v1/chat/completions`
- 对外稳定模型别名：
  - `free-proxy/auto`
  - `free-proxy/coding`
- OpenClaw 配置写入：
  - provider id：`free-proxy`
  - models：`auto`、`coding`
- Opencode 配置写入：
  - provider id：`free-proxy`
  - models：`auto`、`coding`

小白直接记住两条就够了：

1. OpenAI / Python SDK / 通用兼容客户端：`free-proxy/coding`
2. Opencode：`free-proxy/coding`

## 常见问题

- 网络错误：确认服务已启动（`uv run free-proxy serve`），使用 `http://localhost:8765`
- 无可用模型：免费模型可能被临时限流，点"刷新模型列表"或手动添加可用模型
- API Key 存放：本地 `.env`（不会上传）
- 旧版 Opencode 配置里如果出现 `free_proxy`
  - 这是旧命名
  - 当前统一名称是 `free-proxy`
  - 重新执行一次配置写入后应统一为 `free-proxy`

## 开发命令

```bash
# 启动服务
uv run free-proxy serve

# 查看所有子命令
uv run free-proxy --help

# 列出某 provider 的模型
uv run free-proxy models --provider sambanova

# 探测某模型可用性
uv run free-proxy probe --provider sambanova --model DeepSeek-V3-0324

# 运行测试
uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'

# 前端/历史静态测试
# （首次执行前先 npm install）
npm test
```

## 历史方案

- TypeScript 后端方案已归档为历史参考，不再作为主运行路径。
- 历史说明见：`docs/typescript-legacy.md`
- 迁移发布说明见：`docs/migration-python-mainline.md`

## 许可

MIT
