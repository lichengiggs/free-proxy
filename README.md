# free-proxy

[中文](./README.md) | [English](./README_EN.md)

把多家免费 LLM provider 聚合成一个本地 OpenAI 兼容入口。你只需要配好 API Key，就能先跑起来，再按需要切模型。

这份项目最适合这三类人：

1. 想低成本体验多家免费模型的人
2. 想给 OpenAI SDK / OpenClaw / Opencode 提供统一本地入口的人
3. 不想手动维护多套 provider 配置的人

## 你会得到什么

- 一个本地 OpenAI 兼容地址：`http://127.0.0.1:8765/v1`
- 一个稳定模型别名：`free-proxy/auto`
- 多 provider 自动回退，某家失败时可切到其他可用模型
- 本地 Web 页面配置 API Key，不用手改复杂配置
- 控制台可配置的 provider：OpenRouter / Groq / Ofox / Gemini / GitHub Models / Mistral / SambaNova / NVIDIA NIM

## 当前稳定接口

- `GET /v1/models`
- `POST /v1/chat/completions`

## 安装 free-proxy

先把项目下载到本地：

```bash
git clone https://github.com/lichengiggs/free-proxy.git
cd free-proxy
```

然后启动服务：

```bash
uv run free-proxy serve
```

打开页面：

```text
http://127.0.0.1:8765
```

## 升级 free-proxy

如果你已经装过这个项目，在项目目录里执行：

```bash
git pull --ff-only
uv sync
uv run free-proxy serve
```

## 3 步快速开始

1. 保存至少一个 provider 的 API Key
2. 先选推荐模型
3. 点击验证，或者直接发一句测试消息

小白提示：服务启动后，这个终端窗口先不要关。

## 推荐怎么选

先保存任意一家有免费额度的 provider，再用 `free-proxy/auto`。

| Provider | 推荐模型 | 适合场景 | 说明 |
|---|---|---|---|
| OpenRouter | `openrouter/auto:free` | 免费模型入口 | 模型列表只保留免费模型 |
| Groq | `llama-3.1-8b-instant` | 补充选择 | 也可以选 `llama-3.3-70b-versatile` |
| Ofox | `z-ai/glm-4.7-flash:free` | 免费模型补充 | 模型列表只保留以 `:free` 结尾的模型 |
| Gemini | `gemini-3.1-flash-lite-preview` | 免费层回退 | 免费层稳定，适合回退 |
| Mistral | `mistral-large-latest` | 稳定后备 | 质量稳，适合补位 |
| GitHub Models | `gpt-4o` / `gpt-4o-mini` | 已有 Copilot 的用户 | 质量高，但额度取决于账号 |
| SambaNova | `DeepSeek-V3.1-Terminus` | 补充选择 | 适合作为额外后备 |
| NVIDIA NIM | `meta/llama-3.1-70b-instruct` | 补充选择 | 当前内置推荐是这一条 |

如果你只记一条：

- 不确定时先用 `free-proxy/auto`

## 排障日志

如果你想看更详细的排障日志，启动时加：

```bash
uv run free-proxy serve --debug
```

## 本地代理注意事项

如果你本机 shell 配了 `http_proxy` / `https_proxy`，验证本地服务时请同时设置：

```bash
NO_PROXY=127.0.0.1,localhost
```

或者临时清空代理变量再测。

否则 `curl`、`opencode` 之类的客户端可能经过本地代理，收到注入的 `Connection: keep-alive` 或 `Proxy-Connection: keep-alive`，把已经正常结束的 SSE 看成连接没有关闭。

## OpenAI 兼容调用示例

```bash
curl -s http://127.0.0.1:8765/v1/models

curl -s -X POST http://127.0.0.1:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"free-proxy/auto","messages":[{"role":"user","content":"Reply with exactly OK"}]}'
```

`/v1/chat/completions` 的当前行为是：

- 默认返回普通 JSON
- 请求里带 `"stream": true` 时，上游仍按非流式调用，服务端再把 JSON 包装成 SSE 返回，兼容 `opencode` 这类按流式消费的客户端

普通 JSON 示例：

```bash
curl -X POST http://127.0.0.1:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"free-proxy/auto","messages":[{"role":"user","content":"Reply with exactly OK"}]}'
```

SSE 示例：

```bash
NO_PROXY=127.0.0.1,localhost HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy= \
curl -N -X POST http://127.0.0.1:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"free-proxy/auto","messages":[{"role":"user","content":"Reply with exactly OK"}],"stream":true}'
```

如果你用 `opencode run` 验证本地服务，建议同样清空代理变量：

```bash
NO_PROXY=127.0.0.1,localhost HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy= \
opencode run --print-logs --format json -m free-proxy/auto "Reply with exactly OK"
```

## 接入 OpenAI SDK / OpenClaw / Opencode

### OpenAI / Python SDK

```python
from openai import OpenAI

client = OpenAI(
    api_key="not-needed",
    base_url="http://127.0.0.1:8765/v1",
)

resp = client.chat.completions.create(
    model="free-proxy/auto",
    messages=[{"role": "user", "content": "Reply with exactly OK"}],
)
print(resp.choices[0].message.content)
```

### OpenClaw

页面上的 OpenClaw 配置写入 `~/.openclaw/openclaw.json`：

- provider id：`free-proxy`
- baseUrl：`http://localhost:8765/v1`
- models：`auto`
- 默认模型：`free-proxy/auto`

### Opencode

页面上的 Opencode 配置写入 `~/.config/opencode/opencode.json`：

- provider id：`free-proxy`
- baseURL：`http://127.0.0.1:8765/v1`
- models：`auto`

验证命令见上一节。

## 常见问题

### 页面打不开

先确认服务还在运行，再刷新页面。

### 没有可用模型

先换一个推荐模型再试。

### API Key 存在哪里

保存在项目根目录的 `.env` 文件里，不会提交到 GitHub。

## License

MIT
