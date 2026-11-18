// `base.bell.counters` is live: a write anywhere in the business re-runs it on the server, so the counters are never
// polled. A counter whose figure moves as time passes with no event (a job waiting a minute with no device alive) makes
// the result carry `refresh_every`: the counters are read again that often while the page is in sight, and a reading
// older than a live result that came meanwhile is dropped. A failed read keeps the last counters.
import { type LiveStatus, useLive, useLiveClient } from '@erplora/ui/sdk';
import { onScopeDispose, type Ref, shallowRef, watch } from 'vue';

import type { BellCounters } from '../operations';

export interface BellReading {
  /** The newest result: the live one, or the reading of the clock when it came after it; undefined before the first. */
  readonly counters: Readonly<Ref<BellCounters | undefined>>;
  readonly status: Readonly<Ref<LiveStatus>>;
  /** Reopens the stream so the server runs every query again. */
  refresh(): void;
}

export function useBellCounters(): BellReading {
  const client = useLiveClient();
  const { data, status, refresh } = useLive('base.bell.counters', {});
  const latest = shallowRef<BellCounters | undefined>();
  /** How many live results came: a reading that started before the last one is older than it. */
  let pushes = 0;
  watch(data, (value) => {
    pushes += 1;
    if (value !== undefined) latest.value = value;
  });

  async function readAgain(): Promise<void> {
    if (document.visibilityState === 'hidden') return;
    const before = pushes;
    try {
      const result = await client.api.call('base.bell.counters', {});
      if (pushes === before) latest.value = result;
    } catch (error) {
      console.warn('base: the bell could not read its counters again', error);
    }
  }

  let clock: ReturnType<typeof setInterval> | undefined;
  watch(
    () => latest.value?.refresh_every ?? null,
    (seconds) => {
      clearInterval(clock);
      clock = seconds ? setInterval(() => void readAgain(), seconds * 1000) : undefined;
    },
  );
  onScopeDispose(() => clearInterval(clock));

  return { counters: latest, status, refresh };
}
