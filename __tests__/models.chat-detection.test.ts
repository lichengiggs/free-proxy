import { describe, test, expect } from '@jest/globals';
import { isChatModel } from '../src/models';

describe('isChatModel detection', () => {
  test('should detect chat model by task/object/type signals', () => {
    expect(isChatModel({ id: 'x', task: 'chat' } as any)).toBe(true);
    expect(isChatModel({ id: 'x', object: 'chat.completion' } as any)).toBe(true);
    expect(isChatModel({ id: 'x', type: 'completion' } as any)).toBe(true);
  });

  test('should detect chat model by architecture modality', () => {
    expect(isChatModel({ id: 'generic-model', architecture: { modality: 'text->text' } } as any)).toBe(true);
  });

  test('should detect chat model by known id keywords', () => {
    expect(isChatModel({ id: 'my-deepseek-model' } as any)).toBe(true);
    expect(isChatModel({ id: 'plain-llama' } as any)).toBe(true);
  });

  test('should reject non-chat model without known signals', () => {
    expect(isChatModel({ id: 'image-embedding-only' } as any)).toBe(false);
  });
});
