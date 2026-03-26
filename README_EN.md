# free-proxy

[中文](README.md) | [English](README_EN.md)

It combines the free tiers of multiple providers into one usable token pool for daily development.

One-line overview: free, easy to use, and enough for everyday OpenClaw usage.

### Free-tier overview

| Option | Stability | Quota | Cost |
|---|---|---|---|
| `free-proxy` | Medium | Estimate ~3.3k requests/day<br>~100k requests/month<br>~300USD/month equivalent | Free |
| US paid coding plan | High | About 200–10,000 requests/month | 20-200USD/month |
| China paid coding plan | High | Lite 18,000 requests/month<br>Pro 90,000 requests/month | 20-200RMB/month |

Note: [Longcat](https://longcat.chat/platform/api-keys) currently offers about 50 million tokens/day on `LongCat-Flash-Lite`, so it is a strong first choice.

## Core features

- Aggregates 9 providers: OpenRouter / Groq / OpenCode / Longcat / Gemini / GitHub Models / Mistral / Cerebras / SambaNova
- Automatic fallback when a model fails or gets rate-limited
- Manual model add with `provider+modelId`
- Local web UI with card-style settings, model selection, and OpenClaw config updates
- OpenAI-compatible endpoint: `http://localhost:8765/v1`

## Quick start

1) First install: clone the repository

```bash
git clone https://github.com/lichengiggs/free-proxy.git
cd free-proxy
```

If you already cloned this repo before, updating is just:

```bash
cd free-proxy
git pull --ff-only
```

2) Install [uv](https://docs.astral.sh/uv/) (if you don't have it yet)

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# or Homebrew
brew install uv
```

3) Sync dependencies and start

```bash
uv sync
uv run free-proxy serve
```

If you are updating from an older version, run `uv sync` again after `git pull --ff-only`.

For beginners: keep this terminal open after startup.

4) Open the setup page and save at least one provider API key

- Visit: `http://localhost:8765`
- After saving a key, start with a recommended model, then click verify or send a quick test request.

## Common integrations

- OpenAI-compatible clients / Python SDK
  - Base URL: `http://127.0.0.1:8765/v1`
  - Model: `free-proxy/auto` for the easiest default
  - If your main use case is coding, switch to `free-proxy/coding`
  - Minimal example:

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

- OpenClaw
  - Provider ID: `free-proxy`
  - Base URL: `http://localhost:8765/v1`
  - Models: `auto`, `coding`
  - Default first choice: `free-proxy/auto`
  - Switch to `free-proxy/coding` if you mainly use it for coding

- Opencode
  - Provider ID: `free-proxy`
  - Config path is usually: `~/.config/opencode/opencode.json`
  - Base URL: `http://localhost:8765/v1`
  - Default command: `opencode run -m free-proxy/auto "Reply with exactly OK"`
  - Coding command: `opencode run -m free-proxy/coding "Reply with exactly OK"`

## Current external behavior

- Standard OpenAI-compatible routes:
  - `GET /v1/models`
  - `POST /v1/chat/completions`
- Stable public model aliases:
  - `free-proxy/auto`
  - `free-proxy/coding`
- OpenClaw config writer creates:
  - provider: `free-proxy`
  - models: `auto`, `coding`
- Opencode config writer creates:
  - provider: `free-proxy`
  - models: `auto`, `coding`

If you only want the shortest path:

1. When you are not sure which model to use, start with `free-proxy/auto`
2. If you mainly use it for coding, switch to `free-proxy/coding`

## FAQ

- Network error: make sure `uv run free-proxy serve` is still running, then open `http://localhost:8765`
- Update issues after pulling: run `git pull --ff-only`, then `uv sync`
- No available model: free models may be rate-limited temporarily; click **Refresh model list** first, then try another recommended model
- Where keys are stored: local `.env` file only (not uploaded)
- If an older Opencode config still contains `free_proxy`
  - That is the legacy name
  - The unified name is now `free-proxy`
  - Re-run config writing and use `free-proxy/...`

## Dev commands

```bash
# start backend
uv run free-proxy serve

# list subcommands
uv run free-proxy --help

# list models
uv run free-proxy models --provider sambanova

# probe one model
uv run free-proxy probe --provider sambanova --model DeepSeek-V3-0324

# python tests
uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'

# frontend/legacy static tests
# (run npm install first if dependencies are missing)
npm test
```

## Legacy implementation

- The TypeScript backend is now archived for reference only.
- See: `docs/typescript-legacy.md`
- Migration notes: `docs/migration-python-mainline.md`

## License

MIT
