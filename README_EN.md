# free-proxy

A local entrypoint that combines multiple free LLM providers. Add one API key and start using it.

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
```

Then restart the service:

```bash
uv run free-proxy serve
```

## Just remember 3 things

1. Start the service
2. Save one API key in the web page
3. Pick a model and start chatting

Then follow the page steps:

1. Save at least one provider API key
2. Pick a recommended model first
3. Click verify, or send a small test message

## Which model to choose

- Not sure: `free-proxy/auto`
- Mostly coding: `free-proxy/coding`

If you want troubleshooting logs, start with:

```bash
uv run free-proxy serve --debug
```

## FAQ

### The page does not open

Make sure the service is still running:

```bash
uv run free-proxy serve
```

### No model is available

Try another recommended model first.

### Where are API keys stored?

They are stored in the project root `.env` file and are not committed to GitHub.

## License

MIT
