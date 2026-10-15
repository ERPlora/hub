/* eslint-disable vue/one-component-per-file -- one throwaway host component per case */
// `useServerNow(asOf, ms)`: the page's clock on the SERVER's time (review of 2026-10-15, finding 8). The
// figures come «as of» the server's instant; a device whose clock is off would make the timer and the
// totals jump. The gap is measured when each result arrives (`as_of` against the device's clock) and the
// ticking clock runs with it.
import { mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, nextTick, ref } from 'vue';

import { useServerNow } from './useServerNow';

beforeEach(() => {
  vi.useFakeTimers();
  // The device is ten minutes behind the server.
  vi.setSystemTime(new Date('2026-10-06T08:20:00Z'));
});
afterEach(() => vi.useRealTimers());

describe('useServerNow', () => {
  it('is the server’s instant and ticks from it', async () => {
    const asOf = ref<string | undefined>('2026-10-06T08:30:00Z');
    const wrapper = mount(
      defineComponent({
        setup() {
          const now = useServerNow(() => asOf.value, 1000);
          return () => h('p', new Date(now.value).toISOString());
        },
      }),
    );
    expect(wrapper.text()).toBe('2026-10-06T08:30:00.000Z');
    await vi.advanceTimersByTimeAsync(60_000);
    expect(wrapper.text()).toBe('2026-10-06T08:31:00.000Z');
    // A new result measures the gap again.
    asOf.value = '2026-10-06T09:00:00Z';
    await nextTick();
    expect(wrapper.text()).toBe('2026-10-06T09:00:00.000Z');
  });

  it('without a server instant yet it is the device’s', () => {
    const wrapper = mount(
      defineComponent({
        setup() {
          const now = useServerNow(() => undefined, 1000);
          return () => h('p', new Date(now.value).toISOString());
        },
      }),
    );
    expect(wrapper.text()).toBe('2026-10-06T08:20:00.000Z');
  });
});
