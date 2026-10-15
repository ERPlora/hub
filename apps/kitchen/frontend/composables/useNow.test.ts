// `useNow`: the clock a screen paints with. The kitchen display's card clock moves every second (m:ss,
// as the old KDS); a list's «minutes ago» can tick slower. It stops with the screen.
import { mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import { NOW_TICK_MS, useNow } from './useNow';

describe('useNow', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-14T11:00:00Z'));
  });
  afterEach(() => vi.useRealTimers());

  function host(tick?: number) {
    return mount(
      defineComponent({
        setup() {
          const now = useNow(tick);
          return () => h('p', now.value.toISOString());
        },
      }),
    );
  }

  it('ticks every second by default and stops with the screen', async () => {
    const wrapper = host();
    expect(NOW_TICK_MS).toBe(1000);
    expect(wrapper.text()).toBe('2026-10-14T11:00:00.000Z');
    await vi.advanceTimersByTimeAsync(1000);
    expect(wrapper.text()).toBe('2026-10-14T11:00:01.000Z');
    const running = vi.getTimerCount();
    wrapper.unmount();
    // Its own interval is gone (happy-dom may keep a timer of its own).
    expect(vi.getTimerCount()).toBe(running - 1);
  });

  it('can tick slower', async () => {
    const wrapper = host(30_000);
    await vi.advanceTimersByTimeAsync(29_000);
    expect(wrapper.text()).toBe('2026-10-14T11:00:00.000Z');
    await vi.advanceTimersByTimeAsync(1000);
    expect(wrapper.text()).toBe('2026-10-14T11:00:30.000Z');
    wrapper.unmount();
  });
});
