import { beforeEach, describe, expect, test } from '@jest/globals';

import {
  __REQUEST_BUDGET_TEST_ONLY__,
  evaluateRequestBudget,
  recordObservedBudgetLimit,
} from '../src/request-budget';
import type { BudgetResult } from '../src/request-budget';

describe('request-budget: simple token estimation and trim decision', () => {
  beforeEach(() => {
    delete process.env.REQUEST_BUDGET_DEFAULT_INPUT_TOKENS;
    __REQUEST_BUDGET_TEST_ONLY__.reset();
  });

  test('small request returns shouldTrim=false', () => {
    const result = evaluateRequestBudget({
      model: 'openrouter/auto:free',
      messages: [{ role: 'user', content: 'hello' }],
    });

    expect(result.shouldTrim).toBe(false);
    expect(result.estimatedInputTokens).toBeGreaterThan(0);
    expect(result.budgetInputLimit).toBeGreaterThan(0);
  });

  test('BudgetResult has no risk, shouldSummarize, estimatedOutputTokens, or budgetOutputLimit fields', () => {
    const result = evaluateRequestBudget({
      model: 'openrouter/auto:free',
      messages: [{ role: 'user', content: 'hello' }],
    });

    expect(result).not.toHaveProperty('risk');
    expect(result).not.toHaveProperty('shouldSummarize');
    expect(result).not.toHaveProperty('estimatedOutputTokens');
    expect(result).not.toHaveProperty('budgetOutputLimit');
  });

  test('large request exceeding default limit returns shouldTrim=true', () => {
    process.env.REQUEST_BUDGET_DEFAULT_INPUT_TOKENS = '2000';

    const result = evaluateRequestBudget({
      model: 'github/gpt-4o-mini',
      messages: [
        { role: 'system', content: 'You are a coding agent.' },
        { role: 'user', content: 'A'.repeat(6000) },
        { role: 'assistant', content: 'B'.repeat(5000) },
        { role: 'tool', content: 'C'.repeat(7000) },
        { role: 'user', content: 'Please continue and keep the final answer short.' },
      ],
      tools: [{ name: 'run_command', description: 'D'.repeat(3000) }],
    });

    expect(result.shouldTrim).toBe(true);
    expect(result.estimatedInputTokens).toBeGreaterThan(2000);
    expect(result.budgetInputLimit).toBe(2000);
  });

  test('respects observed upstream limit with safety margin', () => {
    process.env.REQUEST_BUDGET_DEFAULT_INPUT_TOKENS = '24000';

    recordObservedBudgetLimit({
      model: 'opencode/minimax-m2.5-free',
      inputLimit: 12000,
      source: 'provider_error',
    });

    const result = evaluateRequestBudget({
      model: 'opencode/minimax-m2.5-free',
      messages: [{ role: 'user', content: 'E'.repeat(4000) }],
    });

    expect(result.budgetInputLimit).toBeLessThan(12000);
  });

  test('does not accept maxTokens in input (simplified interface)', () => {
    const result = evaluateRequestBudget({
      model: 'openrouter/auto:free',
      messages: [{ role: 'user', content: 'hello' }],
    });

    // Should succeed without maxTokens parameter
    expect(typeof result.shouldTrim).toBe('boolean');
  });

  test('empty messages array still returns a valid budget result', () => {
    const result = evaluateRequestBudget({
      model: 'openrouter/auto:free',
      messages: [],
    });

    expect(result.shouldTrim).toBe(false);
    expect(result.estimatedInputTokens).toBe(0);
  });
});
