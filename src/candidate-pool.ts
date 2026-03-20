import { ENV, fetchWithTimeout, getProviderKey } from './config';
import { fetchAllModels, filterFreeModels, rankModels, OpenRouterModel } from './models';
import { PROVIDERS } from './providers/registry';

export interface CandidateModel {
  id: string;
  name: string;
  provider: string;
  context_length?: number;
  lastValidated?: number;
  successCount?: number;
  failCount?: number;
}

export class CandidatePool {
  private candidates: Map<string, CandidateModel> = new Map();
  private failedModels: Map<string, number> = new Map();
  private lastUpdateTime: number | null = null;
  private validating = false;

  async validateModel(modelId: string): Promise<boolean> {
    try {
      const response = await fetchWithTimeout(
        `${ENV.OPENROUTER_BASE_URL}/chat/completions`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${ENV.OPENROUTER_API_KEY}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            model: modelId,
            messages: [{ role: 'user', content: 'test' }],
            max_tokens: 1
          })
        },
        15000
      );

      if (response.status === 200) {
        return true;
      }
      return false;
    } catch {
      return false;
    }
  }

  async refresh(): Promise<void> {
    if (this.validating) {
      return;
    }

    this.validating = true;

    try {
      // 获取所有已配置 provider 的模型
      const allModels = await fetchAllModels();
      
      // 过滤免费模型
      const freeModels = allModels.filter(model => {
        const promptCost = parseFloat(String(model.pricing?.prompt || '0'));
        const completionCost = parseFloat(String(model.pricing?.completion || '0'));
        return promptCost === 0 && completionCost === 0;
      });

      this.candidates.clear();

      // 验证每个模型
      for (const model of freeModels) {
        const provider = PROVIDERS.find(p => p.name === model.provider);
        if (!provider) continue;

        const key = getProviderKey(model.provider);
        if (!key) continue;

        const isValid = await this.validateModelWithProvider(model.id, provider, key);
        
        if (isValid) {
          this.candidates.set(model.id, {
            id: model.id,
            name: model.name,
            provider: model.provider,
            context_length: model.context_length,
            lastValidated: Date.now(),
            successCount: 1,
            failCount: 0
          });
        }
      }

      this.lastUpdateTime = Date.now();
    } finally {
      this.validating = false;
    }
  }

  private async validateModelWithProvider(
    modelId: string, 
    provider: typeof PROVIDERS[0], 
    key: string
  ): Promise<boolean> {
    try {
      const response = await fetchWithTimeout(
        `${provider.baseURL}/chat/completions`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${key}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            model: modelId.replace(`${provider.name}/`, ''), // 去掉 provider 前缀
            messages: [{ role: 'user', content: 'test' }],
            max_tokens: 1
          })
        },
        15000
      );

      return response.status === 200;
    } catch {
      return false;
    }
  }

  getCandidates(): CandidateModel[] {
    return Array.from(this.candidates.values())
      .filter(c => !this.failedModels.has(c.id));
  }

  markModelFailed(modelId: string): void {
    const current = this.failedModels.get(modelId) || 0;
    this.failedModels.set(modelId, current + 1);
    
    this.candidates.delete(modelId);
  }

  addCandidate(model: CandidateModel): void {
    if (!this.candidates.has(model.id)) {
      this.candidates.set(model.id, {
        ...model,
        successCount: 1,
        failCount: 0
      });
    }
  }

  clear(): void {
    this.candidates.clear();
    this.failedModels.clear();
    this.lastUpdateTime = null;
  }

  getLastUpdateTime(): number | null {
    return this.lastUpdateTime;
  }
}