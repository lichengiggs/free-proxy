## [Unreleased]

### Breaking Changes
- remove `free-proxy/coding`, use `free-proxy/auto` instead
- `/v1/models` now returns only `free-proxy/auto`
- console and catalog no longer offer GitHub Models
- console and catalog no longer offer Ofox
- console and catalog no longer offer SambaNova
- console no longer provides OpenClaw configuration

### Added
- `requested_model` support for internal routing preference
- health-driven candidate pool for `auto`
- unified JSON/SSE response normalization

### Changed
- skip cooled providers and models on `free-proxy/auto` instead of calling upstreams that already failed
- route `/v1/chat/completions` through a unified relay pipeline instead of scattered service/server logic
- `free-proxy/auto` 优先复用上次打通的模型，并在同一次请求里刷新 provider 列表。
- migrate OpenCode config output to `auto` only while cleaning legacy `coding` entries

### Fixed
- reject legacy `coding` runtime requests with explicit `model_deprecated` instead of silently falling back
- wrap `/v1/chat/completions` stream responses from non-streaming upstream JSON into OpenAI SSE
- document local proxy interference during localhost SSE verification
