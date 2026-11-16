// `@erplora/ui/shell` with its success and error toasts as spies that resolve at once, for a test that reads what a
// screen says in a toast (Ionic presents a toast only in a real browser). `vi.mock` is hoisted above the file's imports,
// so its factory reaches this module through a dynamic import, and the test reads the spies from the mocked module:
//
//   vi.mock('@erplora/ui/shell', async (importOriginal) => (await import('<path>/toast-spies')).shellWithToastSpies(importOriginal));
//   import { toastSuccess } from '@erplora/ui/shell';  …  expect(toastSuccess).toHaveBeenCalledWith('Saved');
import { vi } from 'vitest';

export async function shellWithToastSpies(importOriginal: () => Promise<unknown>): Promise<Record<string, unknown>> {
  return {
    ...((await importOriginal()) as object),
    toastSuccess: vi.fn(() => Promise.resolve()),
    toastError: vi.fn(() => Promise.resolve()),
  };
}
