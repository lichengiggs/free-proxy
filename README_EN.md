# free-proxy

[中文](./README.md) | [English](./README_EN.md)

A local OpenAI-compatible entrypoint that combines multiple free LLM providers. Add one API key and start using it.

This project is best for:

1. People who want to try multiple free models at low cost
2. People who want one local entrypoint for OpenAI SDK / OpenClaw / Opencode
3. People who do not want to maintain separate provider configs by hand

## What you get

- A local OpenAI-compatible base URL: `http://127.0.0.1:8765/v1`
- One stable model alias: `free-proxy/auto`
- Automatic provider fallback when one model fails
- A local web page for API key setup, so you do not need to edit config files by hand
- Providers you can configure in the console: OpenRouter / Groq / Ofox / Gemini / GitHub Models / Mistral / SambaNova / NVIDIA NIM

## Stable public surface

- `GET /v1/models`
- `POST /v1/chat/completions`

## Install free-proxy

Clone the project to your machine:

```bash
git clone https://github.com/lichengiggs/free-proxy.git
cd free-proxy
```

Start the service:

```bash
uv run free-proxy serve
```

Open the page:

```text
http://127.0.0.1:8765
```

## Upgrade free-proxy

If you already installed it, run this inside the project folder:

```bash
git pull --ff-only
uv sync
uv run free-proxy serve
```

## Quick start in 3 steps

1. Save at least one provider API key
2. Pick a recommended model first
3. Click verify, or send a small test message

Beginner tip: keep the terminal window open while the service is running.

## Which model to choose

Save any provider key with free quota, then use `free-proxy/auto`.

| Provider | Recommended model | Best for | Notes |
|---|---|---|---|
| OpenRouter | `openrouter/auto:free` | free-model entry | the model list keeps free models only |
| Groq | `llama-3.1-8b-instant` | extra option | `llama-3.3-70b-versatile` is also built in |
| Ofox | `z-ai/glm-4.7-flash:free` | free-model extra | the model list keeps ids ending in `:free` |
| Gemini | `gemini-3.1-flash-lite-preview` | backup option | stable free tier fallback |
| Mistral | `mistral-large-latest` | stable backup | strong fallback quality |
| GitHub Models | `gpt-4o` / `gpt-4o-mini` | users with Copilot access | quality is high, quota depends on account |
| SambaNova | `DeepSeek-V3.1-Terminus` | extra option | useful as another fallback |
| NVIDIA NIM | `meta/llama-3.1-70b-instruct` | extra option | this is the current built-in recommendation |

If you only remember one rule:

- Not sure: `free-proxy/auto`

## Troubleshooting logs

If you want more detailed debugging output, start with:

```bash
uv run free-proxy serve --debug
```

## Streaming verification note

If your shell has `http_proxy` or `https_proxy` set, also set:

```bash
NO_PROXY=127.0.0.1,localhost
```

or temporarily clear proxy variables before testing the local server.

Otherwise tools like `curl` or `opencode` may go through a local proxy, receive injected `Connection: keep-alive` or `Proxy-Connection: keep-alive` headers, and incorrectly look like the SSE stream never closed.

## OpenAI-compatible examples

```bash
curl -s http://127.0.0.1:8765/v1/models

curl -s -X POST http://127.0.0.1:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"free-proxy/auto","messages":[{"role":"user","content":"Reply with exactly OK"}]}'
```

`/v1/chat/completions` currently behaves like this:

- The default response is plain JSON
- When the request sets `"stream": true`, the upstream call stays non-streaming and the server wraps that JSON as SSE

Plain JSON example:

```bash
curl -X POST http://127.0.0.1:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"free-proxy/auto","messages":[{"role":"user","content":"Reply with exactly OK"}]}'
```

For streaming checks, explicitly bypass proxies:

```bash
NO_PROXY=127.0.0.1,localhost HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy= \
curl -N -X POST http://127.0.0.1:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"free-proxy/auto","messages":[{"role":"user","content":"Reply with exactly OK"}],"stream":true}'
```

If you verify the local server with `opencode run`, clear the proxy variables the same way:

```bash
NO_PROXY=127.0.0.1,localhost HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy= \
opencode run --print-logs --format json -m free-proxy/auto "Reply with exactly OK"
```

## Connect OpenAI SDK / OpenClaw / Opencode

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

The OpenClaw action on the page writes `~/.openclaw/openclaw.json`:

- provider id: `free-proxy`
- baseUrl: `http://localhost:8765/v1`
- models: `auto`
- default model: `free-proxy/auto`

### Opencode

The Opencode action on the page writes `~/.config/opencode/opencode.json`:

- provider id: `free-proxy`
- baseURL: `http://127.0.0.1:8765/v1`
- models: `auto`

The verification command is in the previous section.

## Local agent pipeline

This is local scaffolding. It does not change how free-proxy runs. A person opens a GitHub issue and adds the existing `ready` label. A poll script on that machine then calls a coding-agent CLI and `gh`: an implementer opens a pull request, a reviewer in a separate process returns `ACCEPT` or `REJECT`, and `ACCEPT` with green checks squash-merges.

See [docs/agent-pipeline.md](docs/agent-pipeline.md). Cloud Agent and GitHub Actions are out of scope for this scaffold.

## FAQ

### The page does not open

Make sure the service is still running, then refresh the page.

### No model is available

Try another recommended model first.

### Where are API keys stored?

They are stored in the project root `.env` file and are not committed to GitHub.

## License

MIT
