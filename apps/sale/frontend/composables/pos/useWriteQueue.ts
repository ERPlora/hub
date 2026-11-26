// Writes to the check run ONE AT A TIME (five quick taps never open five checks) and each one reads the check as the
// previous answer left it.
import { computed, shallowRef } from 'vue';

export function useWriteQueue() {
  const inFlight = shallowRef(0);
  let tail: Promise<unknown> = Promise.resolve();

  /** Runs `task` after every write before it: one in flight at a time. */
  function serial<T>(task: () => Promise<T>): Promise<T> {
    inFlight.value += 1;
    const run = tail.then(task);
    tail = run.then(
      () => undefined,
      () => undefined,
    );
    return run.finally(() => {
      inFlight.value -= 1;
    });
  }

  /** Runs `next` once every write queued so far has answered. */
  function afterWrites(next: () => void): void {
    void tail.then(next);
  }

  return { inFlight, busy: computed(() => inFlight.value > 0), serial, afterWrites };
}
