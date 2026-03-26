from __future__ import annotations

import re
from dataclasses import dataclass

from .token_limit_store import TokenLimitState


DEFAULT_INPUT_TOKENS = 65_536
DEFAULT_OUTPUT_TOKENS = 4_096
MIN_INPUT_TOKENS = 2_048
MIN_OUTPUT_TOKENS = 256
CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class LearnedTokenLimit:
    input_tokens_limit: int
    output_tokens_limit: int
    source: str


@dataclass(frozen=True)
class TokenBudget:
    input_tokens_limit: int
    output_tokens_limit: int
    estimated_prompt_tokens: int
    trimmed_prompt: str
    source: str


def estimate_text_tokens(text: str) -> int:
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def trim_prompt_to_token_budget(text: str, max_input_tokens: int) -> str:
    max_chars = max_input_tokens * CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.7)
    tail = max_chars - head
    return text[:head] + '\n\n...[内容已截断]...\n\n' + text[-tail:]


def parse_token_limit_from_error(message: str, attempted_output_tokens: int) -> LearnedTokenLimit | None:
    lowered = message.lower()
    context_match = re.search(r'max(?:imum)? context length is\s+(\d+)\s+tokens', lowered)
    if context_match:
        return LearnedTokenLimit(
            input_tokens_limit=max(int(context_match.group(1)), MIN_INPUT_TOKENS),
            output_tokens_limit=max(min(attempted_output_tokens // 2, DEFAULT_OUTPUT_TOKENS), MIN_OUTPUT_TOKENS),
            source='learned_from_error',
        )
    output_match = re.search(r'max(?:imum)?(?:outputtokens|max tokens|max_tokens)\D+(\d+)', lowered)
    if output_match:
        return LearnedTokenLimit(
            input_tokens_limit=DEFAULT_INPUT_TOKENS,
            output_tokens_limit=max(min(int(output_match.group(1)), DEFAULT_OUTPUT_TOKENS), MIN_OUTPUT_TOKENS),
            source='learned_from_error',
        )
    return None


def pick_best_limit_source(
    provider: str,
    model: str,
    learned_limits: TokenLimitState,
) -> LearnedTokenLimit:
    exact = learned_limits.get(f'{provider}/{model}', {})
    input_limit = exact.get('input_tokens_limit')
    output_limit = exact.get('output_tokens_limit')
    source = exact.get('source')
    if isinstance(input_limit, int) and isinstance(output_limit, int) and isinstance(source, str):
        return LearnedTokenLimit(
            input_tokens_limit=max(input_limit, MIN_INPUT_TOKENS),
            output_tokens_limit=max(output_limit, MIN_OUTPUT_TOKENS),
            source=source,
        )
    provider_prefix = f'{provider}/'
    for key, value in learned_limits.items():
        if not key.startswith(provider_prefix):
            continue
        provider_input = value.get('input_tokens_limit')
        provider_output = value.get('output_tokens_limit')
        provider_source = value.get('source')
        if isinstance(provider_input, int) and isinstance(provider_output, int) and isinstance(provider_source, str):
            return LearnedTokenLimit(
                input_tokens_limit=max(provider_input, MIN_INPUT_TOKENS),
                output_tokens_limit=max(provider_output, MIN_OUTPUT_TOKENS),
                source='learned_from_provider',
            )
    return LearnedTokenLimit(
        input_tokens_limit=DEFAULT_INPUT_TOKENS,
        output_tokens_limit=DEFAULT_OUTPUT_TOKENS,
        source='default_fallback',
    )


def resolve_token_budget(
    *,
    provider: str,
    model: str,
    prompt: str,
    requested_output_tokens: int | None,
    learned_limits: TokenLimitState,
    model_metadata: object | None,
) -> TokenBudget:
    del model_metadata
    limits = pick_best_limit_source(provider, model, learned_limits)
    estimated_prompt_tokens = estimate_text_tokens(prompt)
    requested = requested_output_tokens if requested_output_tokens is not None else limits.output_tokens_limit
    if requested <= 0:
        safe_output_tokens = MIN_OUTPUT_TOKENS
    else:
        safe_output_tokens = min(requested, limits.output_tokens_limit)
        if safe_output_tokens >= MIN_OUTPUT_TOKENS:
            safe_output_tokens = max(safe_output_tokens, MIN_OUTPUT_TOKENS)
    safe_input_limit = max(limits.input_tokens_limit - safe_output_tokens, MIN_INPUT_TOKENS)
    trimmed_prompt = trim_prompt_to_token_budget(prompt, safe_input_limit)
    return TokenBudget(
        input_tokens_limit=safe_input_limit,
        output_tokens_limit=safe_output_tokens,
        estimated_prompt_tokens=estimated_prompt_tokens,
        trimmed_prompt=trimmed_prompt,
        source=limits.source,
    )


def shrink_budget_after_limit_error(
    *,
    provider: str,
    model: str,
    prompt: str,
    attempted_output_tokens: int,
    error_message: str,
) -> LearnedTokenLimit:
    del provider, model
    parsed = parse_token_limit_from_error(error_message, attempted_output_tokens)
    if parsed is not None:
        return parsed
    estimated_prompt = estimate_text_tokens(prompt)
    return LearnedTokenLimit(
        input_tokens_limit=max(int(estimated_prompt * 0.5), MIN_INPUT_TOKENS),
        output_tokens_limit=max(int(attempted_output_tokens * 0.5), MIN_OUTPUT_TOKENS),
        source='learned_by_backoff',
    )
