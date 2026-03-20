import { fetchAllModels } from '../src/models';

describe('Multi-Provider Model Fetching', () => {
  describe('fetchAllModels', () => {
    test('should return empty array when no providers configured', async () => {
      delete process.env.OPENROUTER_API_KEY;
      delete process.env.GROQ_API_KEY;
      delete process.env.OPENCODE_API_KEY;
      
      const models = await fetchAllModels();
      expect(models).toEqual([]);
    });

    test('should fetch models from configured provider', async () => {
      process.env.OPENROUTER_API_KEY = 'test-key';
      
      const models = await fetchAllModels();
      expect(Array.isArray(models)).toBe(true);
      
      delete process.env.OPENROUTER_API_KEY;
    });

    test('should prefix model IDs with provider name', async () => {
      process.env.OPENROUTER_API_KEY = 'test-key';
      
      const models = await fetchAllModels();
      if (models.length > 0) {
        expect(models[0].id).toMatch(/^(openrouter|groq|opencode)\//);
        expect(models[0].provider).toBeDefined();
      }
      
      delete process.env.OPENROUTER_API_KEY;
    });

    test('should handle network errors gracefully', async () => {
      process.env.GROQ_API_KEY = 'invalid-key';
      
      const models = await fetchAllModels();
      expect(Array.isArray(models)).toBe(true);
      
      delete process.env.GROQ_API_KEY;
    });
  });
});