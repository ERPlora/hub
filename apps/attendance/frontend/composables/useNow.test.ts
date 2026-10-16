// `useNow(ms)`: the page's clock — «It is 09:00», the running timer and today's totals tick with it, from
// the server's figures, without asking the server every second. It stops with the component.
import { mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import { useNow } from './useNow';

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-10-06T10:30:00Z'));
});
afterEach(() => vi.useRealTimers());

describe('useNow', () => {
  it('ticks every interval and stops when the component goes', async () => {
    const seen: number[] = [];
    const wrapper = mount(
      defineComponent({
        setup() {
          const now = useNow(1000);
          return () => {
            seen.push(now.value);
            return h('p', String(now.value));
          };
        },
      }),
    );
    expect(Number(wrapper.text())).toBe(Date.parse('2026-10-06T10:30:00Z'));
    await vi.advanceTimersByTimeAsync(2000);
    expect(Number(wrapper.text())).toBe(Date.parse('2026-10-06T10:30:02Z'));
    wrapper.unmount();
    const renders = seen.length;
    await vi.advanceTimersByTimeAsync(5000);
    expect(seen.length).toBe(renders);
    expect(vi.getTimerCount()).toBe(0);
  });
});
