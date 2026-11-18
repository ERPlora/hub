// `@erplora/ui/shell` with its success and error toasts as spies, for a test that reads what a screen says in a toast
// (a real one would also leave its timer armed past the test). `vi.mock` is hoisted above the file's imports,
// so its factory reaches this module through a dynamic import, and the test reads the spies from the mocked module:
//
//   vi.mock('@erplora/ui/shell', async (importOriginal) => (await import('<path>/toast-spies')).shellWithToastSpies(importOriginal));
//   import { toastSuccess } from '@erplora/ui/shell';  …  expect(toastSuccess).toHaveBeenCalledWith('Saved');
import { vi } from 'vitest';

export async function shellWithToastSpies(importOriginal: () => Promise<unknown>): Promise<Record<string, unknown>> {
  return {
    ...((await importOriginal()) as object),
    toastSuccess: vi.fn(),
    toastError: vi.fn(),
  };
}
