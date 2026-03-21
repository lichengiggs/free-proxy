import { describe, test, expect, beforeEach } from '@jest/globals';
import { markModelRateLimited, isModelRateLimited, clearModelRateLimited, resetRateLimitState } from '../src/rate-limit';

describe('rate-limit clear behavior', () => {
  beforeEach(() => {
    resetRateLimitState();
  });

  test('clearModelRateLimited should remove model from limit state', async () => {
    await markModelRateLimited('openrouter/some-model:free', 'rate_limit', 30);
    expect(isModelRateLimited('openrouter/some-model:free')).toBe(true);

    await clearModelRateLimited('openrouter/some-model:free');
    expect(isModelRateLimited('openrouter/some-model:free')).toBe(false);
  });
});
