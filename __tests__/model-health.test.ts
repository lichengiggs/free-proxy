import { beforeEach, describe, expect, jest, test } from '@jest/globals';

import {
  __MODEL_HEALTH_TEST_ONLY__,
  getDynamicPenalty,
  getModelCircuitState,
  getProviderCircuitState,
  recordModelFailure,
  recordModelSuccess,
} from '../src/model-health';

describe('model-health: circuit breaker state machine', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2026-03-24T00:00:00Z'));
    __MODEL_HEALTH_TEST_ONLY__.reset();
  });

  test('model starts in closed state', () => {
    expect(getModelCircuitState('opencode/minimax-m2.5-free')).toBe('closed');
  });

  test('provider starts in closed state', () => {
    expect(getProviderCircuitState('opencode')).toBe('closed');
  });

  test('opens model circuit after 3 consecutive failures (threshold)', async () => {
    await recordModelFailure('opencode/minimax-m2.5-free', 'opencode', 'timeout');
    await recordModelFailure('opencode/minimax-m2.5-free', 'opencode', 'timeout');
    expect(getModelCircuitState('opencode/minimax-m2.5-free')).toBe('closed');

    await recordModelFailure('opencode/minimax-m2.5-free', 'opencode', 'timeout');
    expect(getModelCircuitState('opencode/minimax-m2.5-free')).toBe('open');
  });

  test('opens provider circuit after multiple models from same provider fail', async () => {
    await recordModelFailure('opencode/minimax-m2.5-free', 'opencode', 'provider_unavailable');
    await recordModelFailure('opencode/mimo-v2-pro-free', 'opencode', 'provider_unavailable');
    await recordModelFailure('opencode/mimo-v2-omni-free', 'opencode', 'provider_unavailable');

    expect(getProviderCircuitState('opencode')).toBe('open');
  });

  test('transitions open -> half_open after cooldown -> closed after success', async () => {
    // 3 failures to open
    await recordModelFailure('openrouter/qwen/qwen3-coder:free', 'openrouter', 'rate_limit');
    await recordModelFailure('openrouter/qwen/qwen3-coder:free', 'openrouter', 'rate_limit');
    await recordModelFailure('openrouter/qwen/qwen3-coder:free', 'openrouter', 'rate_limit');

    expect(getModelCircuitState('openrouter/qwen/qwen3-coder:free')).toBe('open');

    // Advance past cooldown (30 minutes)
    jest.advanceTimersByTime(31 * 60 * 1000);
    expect(getModelCircuitState('openrouter/qwen/qwen3-coder:free')).toBe('half_open');

    // Success in half_open -> closed
    await recordModelSuccess('openrouter/qwen/qwen3-coder:free', 900);
    expect(getModelCircuitState('openrouter/qwen/qwen3-coder:free')).toBe('closed');
  });

  test('failure in half_open state re-opens the circuit', async () => {
    await recordModelFailure('github/gpt-4o-mini', 'github', 'timeout');
    await recordModelFailure('github/gpt-4o-mini', 'github', 'timeout');
    await recordModelFailure('github/gpt-4o-mini', 'github', 'timeout');

    expect(getModelCircuitState('github/gpt-4o-mini')).toBe('open');

    jest.advanceTimersByTime(31 * 60 * 1000);
    expect(getModelCircuitState('github/gpt-4o-mini')).toBe('half_open');

    // Failure in half_open -> back to open
    await recordModelFailure('github/gpt-4o-mini', 'github', 'timeout');
    expect(getModelCircuitState('github/gpt-4o-mini')).toBe('open');
  });

  test('auth_error triggers immediate open (strong circuit break)', async () => {
    await recordModelFailure('mistral/mistral-small', 'mistral', 'auth_error');

    expect(getModelCircuitState('mistral/mistral-small')).toBe('open');
  });

  test('reset clears all circuit states', async () => {
    await recordModelFailure('opencode/minimax-m2.5-free', 'opencode', 'timeout');
    await recordModelFailure('opencode/minimax-m2.5-free', 'opencode', 'timeout');
    await recordModelFailure('opencode/minimax-m2.5-free', 'opencode', 'timeout');

    expect(getModelCircuitState('opencode/minimax-m2.5-free')).toBe('open');

    __MODEL_HEALTH_TEST_ONLY__.reset();
    expect(getModelCircuitState('opencode/minimax-m2.5-free')).toBe('closed');
  });
});

describe('model-health: dynamic penalty calculation', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2026-03-24T00:00:00Z'));
    __MODEL_HEALTH_TEST_ONLY__.reset();
  });

  test('zero penalty for healthy model with no failures', () => {
    const penalty = getDynamicPenalty({
      modelId: 'openrouter/auto:free',
      provider: 'openrouter',
    });

    expect(penalty).toBe(0);
  });

  test('penalty increases with consecutive failures', async () => {
    const penaltyBefore = getDynamicPenalty({
      modelId: 'github/gpt-4o-mini',
      provider: 'github',
    });

    await recordModelFailure('github/gpt-4o-mini', 'github', 'timeout');
    await recordModelFailure('github/gpt-4o-mini', 'github', 'timeout');

    const penaltyAfter = getDynamicPenalty({
      modelId: 'github/gpt-4o-mini',
      provider: 'github',
    });

    expect(penaltyAfter).toBeGreaterThan(penaltyBefore);
  });

  test('rate_limit failures cause higher penalty than timeout', async () => {
    await recordModelFailure('model-a', 'prov', 'timeout');
    await recordModelFailure('model-a', 'prov', 'timeout');

    await recordModelFailure('model-b', 'prov', 'rate_limit');
    await recordModelFailure('model-b', 'prov', 'rate_limit');

    const penaltyA = getDynamicPenalty({ modelId: 'model-a', provider: 'prov' });
    const penaltyB = getDynamicPenalty({ modelId: 'model-b', provider: 'prov' });

    expect(penaltyB).toBeGreaterThan(penaltyA);
  });

  test('penalty decreases after success', async () => {
    await recordModelFailure('openrouter/qwen/qwen3-coder:free', 'openrouter', 'timeout');
    await recordModelFailure('openrouter/qwen/qwen3-coder:free', 'openrouter', 'timeout');

    const penaltyAfterFailures = getDynamicPenalty({
      modelId: 'openrouter/qwen/qwen3-coder:free',
      provider: 'openrouter',
    });

    await recordModelSuccess('openrouter/qwen/qwen3-coder:free', 500);

    const penaltyAfterSuccess = getDynamicPenalty({
      modelId: 'openrouter/qwen/qwen3-coder:free',
      provider: 'openrouter',
    });

    expect(penaltyAfterSuccess).toBeLessThan(penaltyAfterFailures);
  });

  test('penalty respects RequestRisk input (no import from request-budget)', () => {
    // getDynamicPenalty should accept an optional risk field
    const safePenalty = getDynamicPenalty({
      modelId: 'test-model',
      provider: 'test',
    });

    const criticalPenalty = getDynamicPenalty({
      modelId: 'test-model',
      provider: 'test',
      risk: 'critical',
    });

    // With no failures, both should be 0
    expect(safePenalty).toBe(0);
    expect(criticalPenalty).toBe(0);
  });
});
