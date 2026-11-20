import { describe, expect, it, vi } from 'vitest';

import { clearToastSpies, shellWithToastSpies } from './toast-spies';

const TOASTS = ['toast', 'toastSuccess', 'toastError', 'toastWarning', 'toastInfo'];

describe('shellWithToastSpies', () => {
  it('turns every toast of the shell into a spy and keeps the rest of it', async () => {
    const real = Object.fromEntries([...TOASTS, 'dismissToast', 'createShell'].map((name) => [name, () => name]));

    const shell = await shellWithToastSpies(async () => real);

    expect(TOASTS.filter((name) => !vi.isMockFunction(shell[name]))).toEqual([]);
    expect(shell.dismissToast).toBe(real.dismissToast);
    expect(shell.createShell).toBe(real.createShell);
  });

  it('forgets what each toast was said by the time the next test clears them', async () => {
    const shell = await shellWithToastSpies(async () => ({}));
    for (const name of TOASTS) (shell[name] as (text: string) => void)('Saved');

    clearToastSpies();

    expect(TOASTS.filter((name) => vi.mocked(shell[name] as () => void).mock.calls.length)).toEqual([]);
  });
});
