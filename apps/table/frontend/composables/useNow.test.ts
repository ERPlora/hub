// `useNow`: the clock a screen paints «35 min» with; it moves on by itself every 30 seconds while the
// screen lives, so the minutes of an open check advance without anybody reloading.
import { mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import { NOW_TICK_MS, useNow } from './useNow';

describe('useNow', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-14T19:00:00Z'));
  });
  afterEach(() => vi.useRealTimers());

  it('ticks every 30 seconds and stops with the screen', async () => {
    const Host = defineComponent({
      setup() {
        const now = useNow();
        return () => h('p', now.value.toISOString());
      },
    });
    const wrapper = mount(Host);
    expect(NOW_TICK_MS).toBe(30_000);
    expect(wrapper.text()).toBe('2026-10-14T19:00:00.000Z');
    await vi.advanceTimersByTimeAsync(30_000);
    expect(wrapper.text()).toBe('2026-10-14T19:00:30.000Z');
    wrapper.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
