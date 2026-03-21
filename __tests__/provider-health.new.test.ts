import { describe, test, expect } from '@jest/globals';
import { buildProviderHeaders, normalizeVerificationModelId } from '../src/provider-health';

describe('provider-health new helpers', () => {
  test('buildProviderHeaders should include OpenRouter required headers', () => {
    const headers = buildProviderHeaders('openrouter', 'sk-test');
    expect(headers.Authorization).toBe('Bearer sk-test');
    expect(headers['Content-Type']).toBe('application/json');
    expect(headers['HTTP-Referer']).toBe('http://localhost:8765');
    expect(headers['X-Title']).toBe('OpenRouter Free Proxy');
  });

  test('buildProviderHeaders should not include OpenRouter extras for others', () => {
    const headers = buildProviderHeaders('groq', 'gsk-test');
    expect(headers.Authorization).toBe('Bearer gsk-test');
    expect(headers['Content-Type']).toBe('application/json');
    expect(headers['HTTP-Referer']).toBeUndefined();
    expect(headers['X-Title']).toBeUndefined();
  });

  test('normalizeVerificationModelId should add models/ for gemini', () => {
    expect(normalizeVerificationModelId('gemini', 'gemini-2.5-flash')).toBe('models/gemini-2.5-flash');
  });

  test('normalizeVerificationModelId should keep existing models/ prefix', () => {
    expect(normalizeVerificationModelId('gemini', 'models/gemini-2.5-flash')).toBe('models/gemini-2.5-flash');
  });

  test('normalizeVerificationModelId should keep other providers unchanged', () => {
    expect(normalizeVerificationModelId('openrouter', 'stepfun/step-3.5-flash:free')).toBe('stepfun/step-3.5-flash:free');
  });
});
