import { ProviderRouter } from '../../src/providers/router';

describe('ProviderRouter', () => {
  let router: ProviderRouter;

  beforeEach(() => {
    router = new ProviderRouter();
  });

  describe('parseModel', () => {
    test('should parse model with provider prefix', () => {
      const result = router.parseModel('groq/llama-3.1-8b');
      expect(result).toEqual({
        provider: 'groq',
        model: 'llama-3.1-8b'
      });
    });

    test('should parse model with nested path', () => {
      const result = router.parseModel('openrouter/meta-llama/llama-3.1-8b-instruct');
      expect(result).toEqual({
        provider: 'openrouter',
        model: 'meta-llama/llama-3.1-8b-instruct'
      });
    });

    test('should default to openrouter for unknown provider', () => {
      const result = router.parseModel('unknown-model');
      expect(result).toEqual({
        provider: 'openrouter',
        model: 'unknown-model'
      });
    });

    test('should handle model name that looks like provider', () => {
      const result = router.parseModel('meta-llama/llama-3.1-8b');
      expect(result).toEqual({
        provider: 'openrouter',
        model: 'meta-llama/llama-3.1-8b'
      });
    });
  });

  describe('getAvailableProviders', () => {
    test('should return empty array when no keys configured', () => {
      const providers = router.getAvailableProviders();
      expect(providers).toEqual([]);
    });

    test('should return openrouter when OPENROUTER_API_KEY is set', () => {
      process.env.OPENROUTER_API_KEY = 'test-key';
      const providers = router.getAvailableProviders();
      expect(providers).toContain('openrouter');
      delete process.env.OPENROUTER_API_KEY;
    });

    test('should return multiple providers when multiple keys configured', () => {
      process.env.OPENROUTER_API_KEY = 'test-key';
      process.env.GROQ_API_KEY = 'test-key';
      const providers = router.getAvailableProviders();
      expect(providers).toContain('openrouter');
      expect(providers).toContain('groq');
      delete process.env.OPENROUTER_API_KEY;
      delete process.env.GROQ_API_KEY;
    });
  });

  describe('executeWithFallback', () => {
    test('should throw error when no providers available', async () => {
      await expect(router.executeWithFallback('test-model', {}, async () => ({ success: true })))
        .rejects.toThrow('All providers failed');
    });
  });
});