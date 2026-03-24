import { afterEach, beforeEach, describe, expect, jest, test } from '@jest/globals';

describe('fallback: max-attempts limiting', () => {
  beforeEach(() => {
    process.env.FALLBACK_MAX_ATTEMPTS = '2';
    jest.resetModules();
  });

  afterEach(() => {
    delete process.env.FALLBACK_MAX_ATTEMPTS;
  });

  test('stops after configured max attempts instead of exhausting the whole chain', async () => {
    jest.unstable_mockModule('../src/rate-limit', () => ({
      isModelRateLimited: () => false,
      markModelRateLimited: async () => undefined,
      clearModelRateLimited: async () => undefined,
    }));

    jest.unstable_mockModule('../src/models', () => ({
      fetchAllModels: async () => [
        { id: 'opencode/minimax-m2.5-free', name: 'MiniMax', provider: 'opencode', pricing: { prompt: '0', completion: '0' }, context_length: 128000 },
        { id: 'github/gpt-4o-mini', name: 'GPT-4o Mini', provider: 'github', pricing: { prompt: '0', completion: '0' }, context_length: 128000 },
        { id: 'openrouter/qwen/qwen3-coder:free', name: 'Qwen3 Coder', provider: 'openrouter', pricing: { prompt: '0', completion: '0' }, context_length: 128000 },
      ],
      isEffectivelyFreeModel: () => true,
    }));

    jest.unstable_mockModule('../src/config', () => ({
      getCustomModels: async () => [],
    }));

    jest.unstable_mockModule('../src/provider-health', () => ({
      getLatestVerification: () => ({ verified: true }),
    }));

    jest.unstable_mockModule('../src/providers/registry', () => ({
      isKnownProvider: () => true,
    }));

    jest.unstable_mockModule('../src/model-dictionary', () => ({
      loadModelDictionary: async () => null,
      orderModelsByDictionary: (models: unknown[]) => models,
    }));

    jest.unstable_mockModule('../src/model-health', () => ({
      getModelCircuitState: () => 'closed',
      getProviderCircuitState: () => 'closed',
      getDynamicPenalty: () => 0,
      recordModelFailure: async () => undefined,
      recordModelSuccess: async () => undefined,
    }));

    const attempted: string[] = [];
    const { executeWithFallback } = await import('../src/fallback');

    await expect(executeWithFallback('openrouter/stepfun/step-3.5-flash:free', async (model) => {
      attempted.push(model);
      return {
        success: false,
        error: { status: 429, message: 'rate limit exceeded' },
      };
    })).rejects.toThrow('无可用模型');

    expect(attempted).toHaveLength(2);
    expect(attempted).toEqual([
      'openrouter/stepfun/step-3.5-flash:free',
      'opencode/minimax-m2.5-free',
    ]);
  });
});

describe('fallback: model-health circuit breaker integration', () => {
  beforeEach(() => {
    jest.resetModules();
  });

  test('skips models with open circuit state', async () => {
    jest.unstable_mockModule('../src/rate-limit', () => ({
      isModelRateLimited: () => false,
      markModelRateLimited: async () => undefined,
      clearModelRateLimited: async () => undefined,
    }));

    jest.unstable_mockModule('../src/models', () => ({
      fetchAllModels: async () => [
        { id: 'opencode/minimax-m2.5-free', name: 'MiniMax', provider: 'opencode', pricing: { prompt: '0', completion: '0' }, context_length: 128000 },
        { id: 'github/gpt-4o-mini', name: 'GPT-4o Mini', provider: 'github', pricing: { prompt: '0', completion: '0' }, context_length: 128000 },
      ],
      isEffectivelyFreeModel: () => true,
    }));

    jest.unstable_mockModule('../src/config', () => ({
      getCustomModels: async () => [],
    }));

    jest.unstable_mockModule('../src/provider-health', () => ({
      getLatestVerification: () => ({ verified: true }),
    }));

    jest.unstable_mockModule('../src/providers/registry', () => ({
      isKnownProvider: () => true,
    }));

    jest.unstable_mockModule('../src/model-dictionary', () => ({
      loadModelDictionary: async () => null,
      orderModelsByDictionary: (models: unknown[]) => models,
    }));

    jest.unstable_mockModule('../src/model-health', () => ({
      getModelCircuitState: (id: string) => id === 'opencode/minimax-m2.5-free' ? 'open' : 'closed',
      getProviderCircuitState: () => 'closed',
      getDynamicPenalty: () => 0,
      recordModelFailure: async () => undefined,
      recordModelSuccess: async () => undefined,
    }));

    const triedModels: string[] = [];
    const { executeWithFallback } = await import('../src/fallback');

    const result = await executeWithFallback('opencode/minimax-m2.5-free', async (model) => {
      triedModels.push(model);
      if (model === 'github/gpt-4o-mini') {
        return { success: true, response: { data: 'ok' } };
      }
      return { success: false, error: { status: 500 } };
    });

    // Should skip the circuit-open model and succeed with the next one
    expect(result.fallbackInfo.model).toBe('github/gpt-4o-mini');
    expect(triedModels).not.toContain('opencode/minimax-m2.5-free');
  });

  test('calls recordModelFailure on upstream failure', async () => {
    const failureCalls: Array<{ model: string; provider: string; kind: string }> = [];

    jest.unstable_mockModule('../src/rate-limit', () => ({
      isModelRateLimited: () => false,
      markModelRateLimited: async () => undefined,
      clearModelRateLimited: async () => undefined,
    }));

    jest.unstable_mockModule('../src/models', () => ({
      fetchAllModels: async () => [
        { id: 'github/gpt-4o-mini', name: 'GPT-4o Mini', provider: 'github', pricing: { prompt: '0', completion: '0' }, context_length: 128000 },
      ],
      isEffectivelyFreeModel: () => true,
    }));

    jest.unstable_mockModule('../src/config', () => ({
      getCustomModels: async () => [],
    }));

    jest.unstable_mockModule('../src/provider-health', () => ({
      getLatestVerification: () => ({ verified: true }),
    }));

    jest.unstable_mockModule('../src/providers/registry', () => ({
      isKnownProvider: () => true,
    }));

    jest.unstable_mockModule('../src/model-dictionary', () => ({
      loadModelDictionary: async () => null,
      orderModelsByDictionary: (models: unknown[]) => models,
    }));

    jest.unstable_mockModule('../src/model-health', () => ({
      getModelCircuitState: () => 'closed',
      getProviderCircuitState: () => 'closed',
      getDynamicPenalty: () => 0,
      recordModelFailure: async (model: string, provider: string, kind: string) => {
        failureCalls.push({ model, provider, kind });
      },
      recordModelSuccess: async () => undefined,
    }));

    const { executeWithFallback } = await import('../src/fallback');

    await expect(executeWithFallback('github/gpt-4o-mini', async () => ({
      success: false,
      error: { status: 429, message: 'rate limit exceeded' },
    }))).rejects.toThrow();

    expect(failureCalls.length).toBeGreaterThan(0);
    expect(failureCalls[0].model).toBe('github/gpt-4o-mini');
    expect(failureCalls[0].kind).toBe('rate_limit');
  });
});
