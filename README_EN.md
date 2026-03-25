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

## Core features

- Aggregates 9 providers: OpenRouter / Groq / OpenCode / Longcat / Gemini / GitHub Models / Mistral / Cerebras / SambaNova
- Automatic fallback when a model fails or gets rate-limited
- Manual model add with `provider+modelId`
- Local web UI with card-style settings, model selection, and OpenClaw config updates
- OpenAI-compatible endpoint: `http://localhost:8765/v1`

## Quick start

1) Clone the repository

```bash
git clone https://github.com/lichengiggs/free-proxy.git
cd free-proxy
```

2) Install [uv](https://docs.astral.sh/uv/) (if you don't have it yet)

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# or Homebrew
brew install uv
```

3) Initialize and start

```bash
uv sync
uv run free-proxy serve
```

For beginners: keep this terminal open after startup.

4) Open the setup page and save at least one provider API key

- Visit: `http://localhost:8765`
- After saving a key, you can pick a model and start using it

## Common integrations

- OpenAI-compatible clients / Python SDK
  - Base URL: `http://127.0.0.1:8765/v1`
  - Model: `free-proxy/coding` for coding tasks, or `free-proxy/auto` for general use

- OpenClaw
  - Provider ID: `free-proxy`
  - Recommended model: `free-proxy/coding`
  - Conservative fallback entry: `free-proxy/auto`

- Opencode
  - Provider ID uses underscore: `free_proxy`
  - Config path is usually: `~/.config/opencode/opencode.json`
  - Recommended command: `opencode run -m free_proxy/coding "Reply with exactly OK"`
  - Conservative command: `opencode run -m free_proxy/auto "Reply with exactly OK"`

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
  - provider: `free_proxy`
  - models: `auto`, `coding`

If you only want the shortest path:

1. OpenAI / Python SDK / generic compatible clients: use `free-proxy/coding`
2. Opencode: use `free_proxy/coding`

## FAQ

- Network error: make sure the service is running with `uv run free-proxy serve`, then open `http://localhost:8765`
- No available model: free models may be rate-limited temporarily; click **Refresh model list** or add a known-available model manually
- Where keys are stored: local `.env` file only (not uploaded)
- Opencode says `Model not found: free-proxy/coding`
  - Cause: Opencode uses `free_proxy` as the local provider ID, not `free-proxy`
  - Fix: run `opencode run -m free_proxy/coding ...`

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
