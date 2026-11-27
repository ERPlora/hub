// A step of a spec that waits on the browser (a `page.evaluate`, a navigation) gets a time limit of its own: Playwright
// sets none on them, and one that never answers held the whole run until its global limit.
import { describe, expect, it, vi } from 'vitest';

import { withinTime } from './within-time';

describe('withinTime: a step that has to answer in time', () => {
  it('gives back what the step answers in time', async () => {
    await expect(withinTime('the scan of /agenda', Promise.resolve(['a cut text']), 1000)).resolves.toEqual(['a cut text']);
  });

  it('passes on the step’s own error', async () => {
    await expect(withinTime('the scan of /agenda', Promise.reject(new Error('context destroyed')), 1000)).rejects.toThrow('context destroyed');
  });

  it('fails naming the step when it does not answer in time', async () => {
    vi.useFakeTimers();
    try {
      const late = withinTime('the scan of /agenda', new Promise<never>(() => undefined), 30_000);
      const failed = expect(late).rejects.toThrow('the scan of /agenda did not answer within 30 s');
      await vi.advanceTimersByTimeAsync(30_000);
      await failed;
    } finally {
      vi.useRealTimers();
    }
  });
});
