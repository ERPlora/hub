// What a follower beside the pane does with the live value it follows: the session is read again each time the value
// changes after its first answer (the first answer is the session's own state, already read).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { type EffectScope, effectScope, nextTick, ref } from 'vue';

import { sessionChanged } from './access';
import { readSessionAgainOnChange } from './session-follow';

vi.mock('./access', async (importOriginal) => (await import('../__tests__/apps-page-spies')).accessWithSessionSpy(importOriginal));

let scope: EffectScope;

beforeEach(() => {
  scope = effectScope();
  vi.mocked(sessionChanged).mockClear();
});
afterEach(() => {
  scope.stop();
});

describe('readSessionAgainOnChange', () => {
  it('the first answer reads nothing; each change after it reads the session once', async () => {
    const value = ref<string | undefined>(undefined);
    scope.run(() => readSessionAgainOnChange(() => value.value));

    value.value = 'en';
    await nextTick();
    expect(sessionChanged).not.toHaveBeenCalled();

    value.value = 'es';
    await nextTick();
    expect(sessionChanged).toHaveBeenCalledTimes(1);

    value.value = 'es';
    await nextTick();
    expect(sessionChanged).toHaveBeenCalledTimes(1);

    value.value = '';
    await nextTick();
    expect(sessionChanged).toHaveBeenCalledTimes(2);
  });

  it('a value that goes away (the live call closed) reads nothing', async () => {
    const value = ref<string | undefined>('en');
    scope.run(() => readSessionAgainOnChange(() => value.value));

    value.value = undefined;
    await nextTick();
    value.value = 'es';
    await nextTick();
    expect(sessionChanged).not.toHaveBeenCalled();
  });
});
