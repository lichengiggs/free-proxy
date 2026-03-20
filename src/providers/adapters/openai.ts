import type { Provider, Model, ProviderAdapter, ChatRequest } from '../types';

export class OpenAIAdapter implements ProviderAdapter {
  constructor(private provider: Provider) {}

  get name(): string {
    return this.provider.name;
  }

  async validateKey(): Promise<boolean> {
    const key = process.env[this.provider.apiKeyEnv];
    if (!key) return false;

    try {
      const response = await fetch(`${this.provider.baseURL}/models`, {
        headers: { 'Authorization': `Bearer ${key}` }
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  async getModels(): Promise<Model[]> {
    const key = process.env[this.provider.apiKeyEnv];
    if (!key) return [];

    try {
      const response = await fetch(`${this.provider.baseURL}/models`, {
        headers: { 'Authorization': `Bearer ${key}` }
      });

      if (!response.ok) return [];

      const data = await response.json();
      return (data.data || []).map((m: any) => ({
        id: m.id,
        name: m.name || m.id,
        provider: this.provider.name,
        context_length: m.context_length,
        pricing: m.pricing
      }));
    } catch {
      return [];
    }
  }

  async chat(request: ChatRequest): Promise<Response> {
    const key = process.env[this.provider.apiKeyEnv];

    return fetch(`${this.provider.baseURL}/chat/completions`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${key}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(request)
    });
  }
}
