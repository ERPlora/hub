// `useFirstAnswer(read, then)`: a section of «Automations» tells the page once its live read has its first answer —
// its data or its failure —, so the page stops saying «Loading…» (hub#950) and opens a linked card only when what
// is above the gallery is painted (FLOW-F05).
import { describe, expect, it, vi } from 'vitest';
import { effectScope, nextTick, shallowRef } from 'vue';

import { useFirstAnswer } from './useFirstAnswer';

function read(data: unknown = undefined, error: unknown = null) {
  return { data: shallowRef(data), error: shallowRef(error) };
}

function watched(source: ReturnType<typeof read>) {
  const then = vi.fn();
  const scope = effectScope();
  scope.run(() => useFirstAnswer(source, then));
  return { then, scope };
}

describe('useFirstAnswer', () => {
  it('tells once, on the first data, and never again', async () => {
    const source = read();
    const { then } = watched(source);
    await nextTick();
    expect(then).not.toHaveBeenCalled();
    source.data.value = { rows: [] };
    await nextTick();
    expect(then).toHaveBeenCalledTimes(1);
    source.data.value = { rows: [{ id: 'a' }] };
    source.error.value = { code: 'internal_error' };
    await nextTick();
    expect(then).toHaveBeenCalledTimes(1);
  });

  it('a failure is an answer too', async () => {
    const source = read();
    const { then } = watched(source);
    source.error.value = { code: 'internal_error' };
    await nextTick();
    expect(then).toHaveBeenCalledTimes(1);
  });

  it('an answer already there tells at once', () => {
    expect(watched(read({ rows: [] })).then).toHaveBeenCalledTimes(1);
    expect(watched(read(undefined, { code: 'internal_error' })).then).toHaveBeenCalledTimes(1);
  });

  it('stops watching with its scope', async () => {
    const source = read();
    const { then, scope } = watched(source);
    scope.stop();
    source.data.value = { rows: [] };
    await nextTick();
    expect(then).not.toHaveBeenCalled();
  });
});
