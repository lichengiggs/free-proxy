import type { BudgetResult, ChatMessage } from './request-budget';

export type OptimizeContextInput = {
  model: string;
  messages: ChatMessage[];
  tools?: unknown[];
  budget: BudgetResult;
};

export type OptimizeContextResult = {
  messages: ChatMessage[];
  summaryUsed: boolean;
  trimmed: boolean;
  droppedToolMessages: number;
  beforeTokens: number;
  afterTokens: number;
  summaryError?: string;
};

export async function optimizeRequestContext(_input: OptimizeContextInput): Promise<OptimizeContextResult> {
  throw new Error('RED_PHASE_NOT_IMPLEMENTED');
}
