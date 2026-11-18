// Test helper of the pieces that read a query again by the clock while the page is in sight (the bell's counters,
// Printing's summary): the fake timers of one test only, and the reads of `path` the fake network answers and counts.
import { vi } from 'vitest';

import { type ApiCall, flush } from '../../../packages/ui/src/sdk/__tests__/live-harness';

interface FakeNet {
  onApi(handler: (call: ApiCall) => Response | Promise<Response>): void;
  readonly api: readonly ApiCall[];
}

/** Runs `test` with fake timers that still let real time pass, and gives the real ones back after it. */
export function withFakeTimers(test: () => Promise<void>): () => Promise<void> {
  return async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ['setTimeout', 'setInterval', 'clearTimeout', 'clearInterval'] });
    try {
      await test();
    } finally {
      vi.useRealTimers();
    }
  };
}

/** Answers every API call with `answer` (given the call's number, from 1); `reads` counts the ones to `path`, and `tick`
 *  moves the fake clock on and lets the page settle. */
export function clockReads(net: FakeNet, path: string, answer: (call: number) => Response | Promise<Response>) {
  let calls = 0;
  net.onApi(() => answer(++calls));
  const reads = () => net.api.filter((call) => call.url.startsWith(path)).length;
  const tick = async (ms: number) => {
    vi.advanceTimersByTime(ms);
    await flush();
  };
  return { reads, tick };
}
