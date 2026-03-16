import { ENV } from './config';

interface OpenRouterModel {
  id: string;
  name: string;
  description: string;
  context_length: number;
  pricing: {
    prompt: string;
    completion: string;
  };
}

let cachedModels: OpenRouterModel[] = [];
let lastFetchTime = 0;
const CACHE_TTL = 60 * 60 * 1000;

export async function fetchModels(forceRefresh = false): Promise<OpenRouterModel[]> {
  const now = Date.now();
  if (!forceRefresh && cachedModels.length && now - lastFetchTime < CACHE_TTL) {
    return cachedModels;
  }

  const response = await fetch(`${ENV.OPENROUTER_BASE_URL}/models`, {
    headers: {
      'Authorization': `Bearer ${ENV.OPENROUTER_API_KEY}`,
      'HTTP-Referer': 'http://localhost:8765',
      'X-Title': 'OpenRouter Free Proxy'
    }
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch models: ${response.statusText}`);
  }

  const data = (await response.json()) as { data: OpenRouterModel[] };
  cachedModels = data.data;
  lastFetchTime = now;
  return cachedModels;
}

export function filterFreeModels(models: OpenRouterModel[]): OpenRouterModel[] {
  return models
    .filter(model => model.id.endsWith(':free'))
    .sort((a, b) => a.name.localeCompare(b.name));
}
