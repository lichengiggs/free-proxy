import { getBudgetEnvConfig } from './config';
import { loadModelDictionary } from './model-dictionary';

export type ChatMessage = {
  role: string;
  content: unknown;
};

export type RequestRisk = 'safe' | 'high' | 'critical';

export type BudgetResult = {
  estimatedInputTokens: number;
  estimatedOutputTokens: number;
  risk: RequestRisk;
  budgetInputLimit: number;
  budgetOutputLimit: number;
  shouldTrim: boolean;
  shouldSummarize: boolean;
};

export type ObservedBudgetLimitInput = {
  model: string;
  inputLimit: number;
  source: 'provider_error' | 'manual';
};

type DictionaryModelLimits = {
  input: number | null;
  output: number | null;
};

const OBSERVED_LIMIT_SAFETY_RATIO = 0.85;
const MODEL_LIMIT_SAFETY_RATIO = 0.8;
const PROVIDER_LIMIT_SAFETY_RATIO = 0.75;
const TOOL_SCHEMA_WEIGHT = 1.2;
const TOOL_MESSAGE_WEIGHT = 1.35;
const ASSISTANT_WEIGHT = 1.05;
const DEFAULT_MESSAGE_OVERHEAD = 10;

const observedInputLimits = new Map<string, number>();

function normalizeTokenEstimate(text: string, weight = 1): number {
  if (!text) return 0;
  return Math.max(1, Math.ceil((text.length / 4) * weight));
}

function stringifyContent(content: unknown): string {
  if (typeof content === 'string') return content;
  if (content == null) return '';
  try {
    return JSON.stringify(content);
  } catch {
    return String(content);
  }
}

function getProvider(model: string): string {
  const [provider] = model.split('/');
  return provider || 'unknown';
}

function estimateMessageTokens(message: ChatMessage): number {
  const text = stringifyContent(message.content);
  const role = message.role.toLowerCase();

  let weight = 1;
  if (role === 'tool') weight = TOOL_MESSAGE_WEIGHT;
  if (role === 'assistant') weight = ASSISTANT_WEIGHT;

  return DEFAULT_MESSAGE_OVERHEAD + normalizeTokenEstimate(text, weight);
}

function estimateToolsTokens(tools: unknown[] | undefined): number {
  if (!tools || tools.length === 0) return 0;
  const raw = stringifyContent(tools);
  return normalizeTokenEstimate(raw, TOOL_SCHEMA_WEIGHT);
}

function getDictionaryLimits(model: string): DictionaryModelLimits {
  const dictionary = (globalThis as typeof globalThis & {
    __FREE_PROXY_MODEL_DICTIONARY__?: Awaited<ReturnType<typeof loadModelDictionary>>;
  }).__FREE_PROXY_MODEL_DICTIONARY__;

  const entry = dictionary?.models?.find(item => item.id === model);
  return {
    input: entry?.input_context_limit ?? null,
    output: entry?.output_context_limit ?? null,
  };
}

function resolveInputLimit(model: string): number {
  const budgetConfig = getBudgetEnvConfig();
  const provider = getProvider(model);
  const dictionaryLimits = getDictionaryLimits(model);
  const observed = observedInputLimits.get(model);
  const modelOverride = budgetConfig.modelInputOverrides[model];
  const providerOverride = budgetConfig.providerInputOverrides[provider];

  if (typeof observed === 'number' && observed > 0) {
    return Math.max(256, Math.floor(observed * OBSERVED_LIMIT_SAFETY_RATIO));
  }

  if (typeof modelOverride === 'number' && modelOverride > 0) return modelOverride;
  if (typeof dictionaryLimits.input === 'number' && dictionaryLimits.input > 0) {
    return Math.max(512, Math.floor(dictionaryLimits.input * MODEL_LIMIT_SAFETY_RATIO));
  }
  if (typeof providerOverride === 'number' && providerOverride > 0) return providerOverride;

  if ((provider === 'openrouter' || provider === 'opencode') && budgetConfig.defaultInputTokens > 0) {
    return Math.floor(budgetConfig.defaultInputTokens * PROVIDER_LIMIT_SAFETY_RATIO);
  }

  return budgetConfig.defaultInputTokens;
}

function resolveOutputLimit(model: string, requestedMaxTokens?: number): number {
  const budgetConfig = getBudgetEnvConfig();
  const provider = getProvider(model);
  const dictionaryLimits = getDictionaryLimits(model);
  const modelOverride = budgetConfig.modelOutputOverrides[model];
  const providerOverride = budgetConfig.providerOutputOverrides[provider];

  const resolved = modelOverride
    || (typeof dictionaryLimits.output === 'number' && dictionaryLimits.output > 0
      ? Math.max(128, Math.floor(dictionaryLimits.output * MODEL_LIMIT_SAFETY_RATIO))
      : providerOverride || budgetConfig.defaultOutputTokens);

  if (Number.isFinite(requestedMaxTokens) && typeof requestedMaxTokens === 'number' && requestedMaxTokens > 0) {
    return Math.min(resolved, requestedMaxTokens);
  }

  return resolved;
}

function computeRisk(estimatedInputTokens: number, inputLimit: number): RequestRisk {
  if (inputLimit <= 0) return 'critical';
  const ratio = estimatedInputTokens / inputLimit;
  if (ratio >= 1) return 'critical';
  if (ratio >= 0.75) return 'high';
  return 'safe';
}

export function evaluateRequestBudget(input: {
  model: string;
  messages: ChatMessage[];
  tools?: unknown[];
  maxTokens?: number;
}): BudgetResult {
  const budgetConfig = getBudgetEnvConfig();
  const estimatedMessages = input.messages.reduce((sum, message) => sum + estimateMessageTokens(message), 0);
  const estimatedInputTokens = estimatedMessages + estimateToolsTokens(input.tools);
  const budgetInputLimit = resolveInputLimit(input.model);
  const budgetOutputLimit = resolveOutputLimit(input.model, input.maxTokens);
  const risk = computeRisk(estimatedInputTokens, budgetInputLimit);
  const shouldTrim = estimatedInputTokens > budgetInputLimit || risk !== 'safe';
  const shouldSummarize = estimatedInputTokens > budgetConfig.summaryTriggerTokens || estimatedInputTokens > budgetInputLimit;

  return {
    estimatedInputTokens,
    estimatedOutputTokens: budgetOutputLimit,
    risk,
    budgetInputLimit,
    budgetOutputLimit,
    shouldTrim,
    shouldSummarize,
  };
}

export function recordObservedBudgetLimit(input: ObservedBudgetLimitInput): void {
  if (!Number.isFinite(input.inputLimit) || input.inputLimit <= 0) return;
  observedInputLimits.set(input.model, input.inputLimit);
}

export const __REQUEST_BUDGET_TEST_ONLY__ = {
  reset(): void {
    observedInputLimits.clear();
  }
};
