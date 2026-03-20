import { PROVIDERS, isKnownProvider } from './registry';
import { OpenAIAdapter } from './adapters/openai';
import type { ProviderAdapter } from './types';

export class ProviderRouter {
  private adapters: Map<string, ProviderAdapter> = new Map();
  private failureCount: Map<string, number> = new Map();

  constructor() {
    for (const provider of PROVIDERS) {
      if (provider.format === 'openai') {
        this.adapters.set(provider.name, new OpenAIAdapter(provider));
      }
    }
  }

  parseModel(modelId: string): { provider: string; model: string } {
    const parts = modelId.split('/');

    if (parts.length >= 2 && isKnownProvider(parts[0])) {
      return { provider: parts[0], model: parts.slice(1).join('/') };
    }

    return { provider: 'openrouter', model: modelId };
  }

  getAvailableProviders(): string[] {
    return PROVIDERS
      .filter(p => !!process.env[p.apiKeyEnv])
      .map(p => p.name);
  }

  async executeWithFallback<T>(
    modelId: string,
    request: any,
    execute: (provider: string, model: string, request: any) => Promise<{ success: boolean; response?: T; error?: any }>
  ): Promise<{ result: T; provider: string; model: string }> {
    const { provider: preferredProvider, model } = this.parseModel(modelId);
    const availableProviders = this.getAvailableProviders();

    const tryProviders = [preferredProvider, ...availableProviders.filter(p => p !== preferredProvider)];

    for (const providerName of tryProviders) {
      if ((this.failureCount.get(providerName) || 0) >= 3) {
        console.log(`[Router] Skipping ${providerName} (consecutive failures)`);
        continue;
      }

      const adapter = this.adapters.get(providerName);
      if (!adapter) continue;

      try {
        const { success, response, error } = await execute(providerName, model, request);

        if (success && response) {
          this.failureCount.delete(providerName);
          return { result: response, provider: providerName, model };
        }

        const current = this.failureCount.get(providerName) || 0;
        this.failureCount.set(providerName, current + 1);

      } catch (err) {
        console.error(`[Router] ${providerName} failed:`, err);
        const current = this.failureCount.get(providerName) || 0;
        this.failureCount.set(providerName, current + 1);
      }
    }

    throw new Error(`All providers failed for model ${modelId}`);
  }
}
