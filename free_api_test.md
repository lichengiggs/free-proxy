# Free API Provider 测试报告

## 测试日期
2026-03-25

## 测试方法

使用标准测试消息测试各 Provider 的 chat/completions 端点：
```
如果你能正常接收到这段指令并准备就绪，请仅回复两个英文字母"ok"，不要输出任何多余的解释、标点符号或执行任何代码操作。
```

---

## 测试结果汇总（更新版）

| Provider | 状态 | 可用模型数 | 原因 |
|----------|------|------------|------|
| **github** | ✅ 可用 | 2 | gpt-4o-mini, gpt-4o 正常工作 |
| **sambanova** | ✅ 可用 | 2+ | DeepSeek-V3-0324, DeepSeek-V3.1 正常工作 |
| **openrouter** | ⚠️ 部分可用 | 7 | 部分免费模型可用，部分被限流/404 |
| **opencode** | ⚠️ 部分可用 | 5 | 5个免费模型可用，其他需要余额 |
| groq | ❌ 不可用 | 0 | 403 Forbidden (API Key 已被撤销) |
| mistral | ❌ 不可用 | 0 | fetch failed (网络连接问题) |
| cerebras | ❌ 不可用 | 0 | Cloudflare Error 1009 (地区限制) |
| gemini | ❌ 不可用 | 0 | fetch failed (网络连接问题) |

---

## 详细测试结果

### ✅ GitHub Models

**Base URL**: `https://models.github.ai/inference`

**测试结果**:
| 模型 | 状态 | 响应 |
|------|------|------|
| gpt-4o-mini | ✅ | ok |
| gpt-4o | ✅ | ok |
| o1-mini | ❌ | 400 - 需要 API 版本 2024-12-01-preview+ |
| o1-preview | ❌ | 400 - 需要 API 版本 2024-12-01-preview+ |
| text-embedding-3-small | ❌ | 400 - 不支持 embeddings |

**可用模型**: `gpt-4o-mini`, `gpt-4o`

**注意事项**:
- GitHub Models 没有 `/models` 端点 (404)
- 但 chat/completions 工作正常
- o1 系列需要特定 API 版本

**结论**: 完全可用，是最稳定的免费 Provider 之一。

**官方文档**: https://docs.github.com/en/github-models

---

### ✅ SambaNova

**Base URL**: `https://api.sambanova.ai/v1`

**测试结果**:
| 模型 | 状态 | 响应 |
|------|------|------|
| DeepSeek-V3-0324 | ✅ | ok |
| DeepSeek-V3.1 | ✅ | ok |
| Meta-Llama-3.1-8B-Instruct | ❌ | 500 - Unknown error |
| Llama-3.2-90B-Vision-Instruct | ❌ | 410 - Model not available |

**可用模型列表** (部分):
- DeepSeek-R1-0528, DeepSeek-R1-Distill-Llama-70B
- DeepSeek-V3-0324, DeepSeek-V3.1, DeepSeek-V3.1-Terminus
- DeepSeek-V3.1-cb, DeepSeek-V3.2
- E5-Mistral-7B-Instruct
- Llama-3.3-Swallow-70B-Instruct-v0.4
- Llama-4-Maverick-17B-128E-Instruct

**可用模型**: `DeepSeek-V3-0324`, `DeepSeek-V3.1`

**结论**: 完全可用，模型丰富，速度快。

**官方文档**: https://docs.sambanova.ai

---

### ⚠️ OpenRouter

**Base URL**: `https://openrouter.ai/api/v1`

**测试结果**:

#### ✅ 可用的免费模型 (7个):
| 模型 | 状态 | 说明 |
|------|------|------|
| nvidia/nemotron-3-super-120b-a12b:free | ✅ | 可用 |
| stepfun/step-3.5-flash:free | ✅ | 可用 |
| arcee-ai/trinity-large-preview:free | ✅ | 可用 |
| liquid/lfm-2.5-1.2b-thinking:free | ✅ | 可用 |
| liquid/lfm-2.5-1.2b-instruct:free | ✅ | 可用 |
| nvidia/nemotron-3-nano-30b-a3b:free | ✅ | 可用 |
| arcee-ai/trinity-mini:free | ✅ | 可用 |
| nvidia/nemotron-nano-12b-v2-vl:free | ✅ | 可用 |
| nvidia/nemotron-nano-9b-v2:free | ✅ | 可用 |
| qwen/qwen3-next-80b-a3b-instruct:free | ✅ | 可用 |
| z-ai/glm-4.5-air:free | ✅ | 可用 |
| mistralai/mistral-small-3.1-24b-instruct:free | ✅ | 可用 |
| meta-llama/llama-3.3-70b-instruct:free | ✅ | 可用 |

#### ❌ 不可用的免费模型:
| 模型 | 状态 | 原因 |
|------|------|------|
| openrouter/auto:free | ❌ | 402 - 账号从未购买过 credits |
| deepseek/deepseek-chat-v3:free | ❌ | 404 - 无可用端点 |
| microsoft/phi-4:free | ❌ | 404 - 无可用端点 |
| huggingfaceh4/zephyr-7b-beta:free | ❌ | 404 - 无可用端点 |
| openai/gpt-oss-120b:free | ❌ | Provider error |
| openai/gpt-oss-20b:free | ❌ | Provider error |
| qwen/qwen3-coder:free | ❌ | Provider error |
| meta-llama/llama-3.2-3b-instruct:free | ❌ | Provider error |
| google/gemma-3n-e2b-it:free | ❌ | Provider error |
| google/gemma-3n-e4b-it:free | ❌ | Provider error |
| qwen/qwen3-4b:free | ❌ | Provider error |
| cognitivecomputations/dolphin-mistral-24b-venice-edition:free | ❌ | Provider error |
| google/gemma-3-4b-it:free | ❌ | Provider error |
| google/gemma-3-12b-it:free | ❌ | Provider error |
| google/gemma-3-27b-it:free | ❌ | Provider error |
| nousresearch/hermes-3-llama-3.1-405b:free | ❌ | Provider error |

**问题分析**:
1. **402 Insufficient credits**: OpenRouter 免费模型需要账号曾经购买过 credits（即使余额为0也可使用免费模型）
2. **404 No endpoints**: 该免费模型当前没有可用的上游 Provider
3. **Provider error**: 上游 Provider 返回错误（通常是限流或服务不可用）

**结论**: OpenRouter 免费模型策略较复杂，**可用但有限制**。

**使用建议**:
- 需要充值任意金额（如 $5）来"激活"账号
- 免费模型无余额也可使用
- 部分免费模型可能因上游 Provider 不可用而 404

**官方文档**: https://openrouter.ai/docs

---

### ⚠️ OpenCode

**Base URL**: `https://opencode.ai/zen/v1`

**可用模型** (15个):
- claude-3-5-haiku
- gpt-5.4-mini
- gpt-5.4-nano
- gpt-5-nano
- glm-5
- minimax-m2.5
- minimax-m2.5-free ✅
- minimax-m2.1
- mimo-v2-pro-free ✅
- mimo-v2-omni-free ✅
- mimo-v2-flash-free ✅
- kimi-k2.5
- trinity-large-preview-free ✅
- big-pickle ✅
- nemotron-3-super-free ✅

**测试结果**:
| 模型 | 状态 | 原因 |
|------|------|------|
| minimax-m2.5-free | ✅ | ok |
| mimo-v2-pro-free | ✅ | ok |
| mimo-v2-omni-free | ✅ | ok |
| mimo-v2-flash-free | ✅ | ok |
| trinity-large-preview-free | ✅ | ok |
| big-pickle | ✅ | ok |
| nemotron-3-super-free | ✅ | ok |
| claude-3-5-haiku | ❌ | 401 - 余额不足 |
| gpt-5.4-mini | ❌ | 401 - 余额不足 |
| gpt-5.4-nano | ❌ | 401 - 余额不足 |
| gpt-5-nano | ❌ | 401 - 模型不支持 |
| glm-5 | ❌ | 401 - 余额不足 |
| minimax-m2.5 | ❌ | 401 - 余额不足 |
| minimax-m2.1 | ❌ | 401 - 余额不足 |
| kimi-k2.5 | ❌ | 401 - 余额不足 |

**可用模型** (5个): `minimax-m2.5-free`, `mimo-v2-pro-free`, `mimo-v2-omni-free`, `mimo-v2-flash-free`, `trinity-large-preview-free`, `big-pickle`, `nemotron-3-super-free`

**结论**: 部分免费模型可用，收费模型需要余额。

**官方文档**: https://opencode.ai

---

### ❌ Groq

**Base URL**: `https://api.groq.com/openai/v1`

**测试结果**:
| 模型 | 状态 | 响应 |
|------|------|------|
| llama-3.1-8b-instant | ❌ | HTTP 403 - Forbidden |
| llama-3.3-70b-versatile | ❌ | HTTP 403 - Forbidden |
| mixtral-8x7b-32768 | ❌ | HTTP 403 - Forbidden |
| gemma2-9b-it | ❌ | HTTP 403 - Forbidden |

**问题分析**:
- `/models` 端点返回 403 Forbidden
- 所有 chat/completions 请求返回 403
- API Key 已被撤销或账号被封禁

**结论**: API Key 无效，需要重新注册获取新 Key。

**官方文档**: https://console.groq.com/docs

---

### ❌ Mistral

**Base URL**: `https://api.mistral.ai/v1`

**测试结果**:
| 模型 | 状态 | 响应 |
|------|------|------|
| mistral-small-latest | ❌ | fetch failed |
| mistral-medium-latest | ❌ | fetch failed |
| mistral-large-latest | ❌ | fetch failed |
| codestral-latest | ❌ | fetch failed |

**问题分析**:
- `fetch failed` 表示网络连接问题
- 可能是防火墙、VPN 或 DNS 问题
- Mistral API 在欧洲，可能需要特殊网络配置

**结论**: 网络不通，无法访问 Mistral API。

**官方文档**: https://docs.mistral.ai

---

### ❌ Cerebras

**Base URL**: `https://api.cerebras.ai/v1`

**测试结果**:
| 模型 | 状态 | 响应 |
|------|------|------|
| llama-3.3-70b | ❌ | HTTP 403 - Cloudflare Error 1009 |

**问题分析**:
- Cloudflare Error 1009: Access denied
- 原因: "The owner of this website (api.cerebras.ai) has banned the country or region your IP address is in (CN) from accessing this website."
- Cerebras 明确禁止中国 IP 访问

**结论**: **地区限制**，中国 IP 被禁止访问。

**官方文档**: https://cerebras.ai/docs

---

### ❌ Gemini

**Base URL**: `https://generativelanguage.googleapis.com/v1beta`

**测试结果**:
| 模型 | 状态 | 响应 |
|------|------|------|
| gemini-2.0-flash | ❌ | fetch failed |
| gemini-1.5-flash | ❌ | fetch failed |
| gemini-1.5-pro | ❌ | fetch failed |
| gemini-pro | ❌ | fetch failed |

**问题分析**:
- `fetch failed` 表示网络连接问题
- Google API 在中国被屏蔽

**结论**: 网络不通，无法访问 Google Gemini API。

**官方文档**: https://ai.google.dev/docs

---

## 推荐配置（更新版）

基于深度测试结果，推荐使用以下配置：

### Tier 1: 稳定可用 (优先使用)

```json
{
  "providers": [
    {
      "name": "github",
      "baseURL": "https://models.github.ai/inference",
      "apiKeyEnv": "GITHUB_MODELS_API_KEY",
      "recommendedModels": ["gpt-4o-mini", "gpt-4o"]
    },
    {
      "name": "sambanova",
      "baseURL": "https://api.sambanova.ai/v1",
      "apiKeyEnv": "SAMBANOVA_API_KEY",
      "recommendedModels": ["DeepSeek-V3-0324", "DeepSeek-V3.1"]
    }
  ]
}
```

### Tier 2: 部分可用 (备选)

```json
{
  "providers": [
    {
      "name": "openrouter",
      "baseURL": "https://openrouter.ai/api/v1",
      "apiKeyEnv": "OPENROUTER_API_KEY",
      "recommendedModels": [
        "nvidia/nemotron-3-super-120b-a12b:free",
        "stepfun/step-3.5-flash:free",
        "arcee-ai/trinity-large-preview:free",
        "liquid/lfm-2.5-1.2b-instruct:free",
        "nvidia/nemotron-3-nano-30b-a3b:free",
        "arcee-ai/trinity-mini:free",
        "nvidia/nemotron-nano-12b-v2-vl:free",
        "nvidia/nemotron-nano-9b-v2:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "z-ai/glm-4.5-air:free",
        "mistralai/mistral-small-3.1-24b-instruct:free",
        "meta-llama/llama-3.3-70b-instruct:free"
      ],
      "note": "需要先充值任意金额激活账号"
    },
    {
      "name": "opencode",
      "baseURL": "https://opencode.ai/zen/v1",
      "apiKeyEnv": "OPENCODE_API_KEY",
      "recommendedModels": [
        "minimax-m2.5-free",
        "mimo-v2-pro-free",
        "mimo-v2-omni-free",
        "mimo-v2-flash-free",
        "trinity-large-preview-free",
        "big-pickle",
        "nemotron-3-super-free"
      ]
    }
  ]
}
```

### Tier 3: 当前不可用

| Provider | 原因 | 解决建议 |
|----------|------|----------|
| groq | API Key 被撤销 | 重新注册获取新 Key |
| mistral | 网络问题 | 检查网络配置，可能需要代理 |
| gemini | 网络问题 | 检查网络配置，可能需要代理 |
| cerebras | 地区限制 | 无法解决，需使用 VPN/代理 |

---

## 代码验证

项目代码中的 Provider 配置在 `src/providers/registry.ts`:

```typescript
export const PROVIDERS: Provider[] = [
  { name: 'openrouter', baseURL: 'https://openrouter.ai/api/v1', ... },
  { name: 'groq', baseURL: 'https://api.groq.com/openai/v1', ... },
  { name: 'opencode', baseURL: 'https://opencode.ai/zen/v1', ... },
  { name: 'gemini', baseURL: 'https://generativelanguage.googleapis.com/v1beta', ... },
  { name: 'github', baseURL: 'https://models.github.ai/inference', ... },
  { name: 'mistral', baseURL: 'https://api.mistral.ai/v1', ... },
  { name: 'cerebras', baseURL: 'https://api.cerebras.ai/v1', ... },
  { name: 'sambanova', baseURL: 'https://api.sambanova.ai/v1', ... },
];
```

Header 构建逻辑在 `src/provider-health.ts`:

```typescript
export function buildProviderHeaders(provider: string, apiKey: string): Record<string, string> {
  if (provider === 'gemini') {
    return { 'x-goog-api-key': apiKey, 'Content-Type': 'application/json' };
  }
  const headers = { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' };
  if (provider === 'openrouter') {
    headers['HTTP-Referer'] = 'http://localhost:8765';
    headers['X-Title'] = 'OpenRouter Free Proxy';
  }
  return headers;
}
```

代码逻辑正确，测试结果反映的是各 Provider API 本身的状态。

---

## 关键发现与改进建议

### 1. OpenRouter 免费模型使用策略

**问题**: OpenRouter 的免费模型需要账号曾经购买过 credits 才能使用。

**解决方案**:
- 在文档中明确说明需要充值激活
- 推荐用户充值 $5 即可解锁所有免费模型
- 实现自动检测账号状态，如果返回 402 则跳过该 provider

### 2. Provider 分类策略

建议实现三级 fallback 策略：

```
Tier 1 (稳定): github, sambanova
Tier 2 (部分可用): openrouter (需激活), opencode (部分免费)
Tier 3 (不可用): groq, mistral, cerebras, gemini
```

### 3. 模型可用性缓存

实现模型可用性检测和缓存机制：
- 启动时检测所有模型的可用性
- 缓存可用模型列表
- 定期刷新（如每 5 分钟）
- fallback 时优先使用已验证的可用模型

### 4. 错误处理改进

针对不同错误类型采取不同策略：
- `401/403`: 标记 provider 为不可用，记录原因
- `404`: 标记该模型不可用，尝试其他模型
- `429`: 标记该 provider 暂时不可用，加入冷却期
- `402`: 对于 OpenRouter，提示用户需要充值
- `fetch failed`: 网络问题，记录并重试

---

## 后续行动

1. **GitHub/SambaNova**: ✅ 完全可用，已添加到 fallback 链优先位置
2. **OpenRouter**: ⚠️ 部分可用，建议用户充值 $5 激活账号
3. **OpenCode**: ⚠️ 部分可用，使用 `-free` 后缀的模型
4. **Groq**: ❌ API Key 无效，建议重新注册
5. **Mistral/Gemini**: ❌ 网络问题，可能需要配置代理
6. **Cerebras**: ❌ 地区限制，中国 IP 被禁止

### 立即行动项

- [ ] 更新 provider registry，标记可用/不可用状态
- [ ] 实现模型可用性检测和缓存
- [ ] 添加 provider 健康检查 API
- [ ] 完善错误处理和日志记录
- [ ] 更新用户文档，说明各 provider 使用限制