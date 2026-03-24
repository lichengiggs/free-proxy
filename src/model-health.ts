import type { RequestRisk } from './request-budget';

export type FailureKind =
  | 'rate_limit'
  | 'auth_error'
  | 'provider_unavailable'
  | 'timeout'
  | 'network_error'
  | 'bad_request'
  | 'unknown_error';

export type CircuitState = 'closed' | 'open' | 'half_open';

export async function recordModelSuccess(_modelId: string, _latencyMs: number): Promise<void> {
  throw new Error('RED_PHASE_NOT_IMPLEMENTED');
}

export async function recordModelFailure(_modelId: string, _provider: string, _kind: FailureKind): Promise<void> {
  throw new Error('RED_PHASE_NOT_IMPLEMENTED');
}

export function getModelCircuitState(_modelId: string): CircuitState {
  throw new Error('RED_PHASE_NOT_IMPLEMENTED');
}

export function getProviderCircuitState(_provider: string): CircuitState {
  throw new Error('RED_PHASE_NOT_IMPLEMENTED');
}

export function getDynamicPenalty(_input: {
  modelId: string;
  provider: string;
  risk: RequestRisk;
}): number {
  throw new Error('RED_PHASE_NOT_IMPLEMENTED');
}

export const __MODEL_HEALTH_TEST_ONLY__ = {
  reset(): void {
    // RED phase placeholder
  }
};
