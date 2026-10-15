// `useNow(ms)`: the time, as a ref that moves on by itself every `ms` (30 s by default), so what the
// queue shows from the clock — how long a job has waited, a device that did not answer in time — changes
// without waiting for another result. Stops with its component.
import { mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import { useNow } from './useNow';

const T0 = new Date('2026-10-15T08:00:00Z');

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] });
  vi.setSystemTime(T0);
});
afterEach(() => vi.useRealTimers());

function host(ms?: number) {
  let now: ReturnType<typeof useNow> | undefined;
  const wrapper = mount(
    defineComponent({
      setup() {
        now = useNow(ms);
        return () => h('time', now!.value.toISOString());
      },
    }),
  );
  return { wrapper, now: () => now!.value };
}

describe('useNow', () => {
  it('starts at the time it is called', () => {
    expect(host().now()).toEqual(T0);
  });

  it('moves on every 30 s by itself', () => {
    const s = host();
    vi.advanceTimersByTime(29_999);
    expect(s.now()).toEqual(T0);
    vi.advanceTimersByTime(1);
    expect(s.now()).toEqual(new Date(T0.getTime() + 30_000));
  });

  it('takes another rhythm and stops with its component', () => {
    const s = host(1_000);
    vi.advanceTimersByTime(1_000);
    expect(s.now()).toEqual(new Date(T0.getTime() + 1_000));
    s.wrapper.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
