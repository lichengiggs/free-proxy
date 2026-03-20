import { PROVIDERS } from '../../src/providers/registry';

describe('Provider Registry', () => {
  test('should export PROVIDERS array', () => {
    expect(PROVIDERS).toBeDefined();
    expect(Array.isArray(PROVIDERS)).toBe(true);
  });

  test('should have openrouter provider', () => {
    const openrouter = PROVIDERS.find(p => p.name === 'openrouter');
    expect(openrouter).toBeDefined();
    expect(openrouter?.baseURL).toBe('https://openrouter.ai/api/v1');
    expect(openrouter?.apiKeyEnv).toBe('OPENROUTER_API_KEY');
    expect(openrouter?.format).toBe('openai');
    expect(openrouter?.isFree).toBe(true);
  });

  test('should have groq provider', () => {
    const groq = PROVIDERS.find(p => p.name === 'groq');
    expect(groq).toBeDefined();
    expect(groq?.baseURL).toBe('https://api.groq.com/openai/v1');
    expect(groq?.apiKeyEnv).toBe('GROQ_API_KEY');
    expect(groq?.format).toBe('openai');
    expect(groq?.isFree).toBe(true);
  });

  test('should have opencode provider', () => {
    const opencode = PROVIDERS.find(p => p.name === 'opencode');
    expect(opencode).toBeDefined();
    expect(opencode?.baseURL).toBe('https://opencode.ai/zen/v1');
    expect(opencode?.apiKeyEnv).toBe('OPENCODE_API_KEY');
    expect(opencode?.format).toBe('openai');
    expect(opencode?.isFree).toBe(true);
  });

  test('all providers should have required fields', () => {
    PROVIDERS.forEach(provider => {
      expect(provider.name).toBeDefined();
      expect(provider.baseURL).toBeDefined();
      expect(provider.apiKeyEnv).toBeDefined();
      expect(provider.format).toBeDefined();
      expect(provider.isFree).toBeDefined();
    });
  });
});