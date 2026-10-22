// `usePhone`: the Home folds on a phone as the topbar does (767 px), and follows a crossed breakpoint.
import { mount } from '@vue/test-utils';
import { defineComponent, h } from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PHONE_QUERY, usePhone } from './phone';

function fakeMedia(matches: boolean) {
  const listeners = new Set<(event: { matches: boolean }) => void>();
  const media = {
    matches,
    addEventListener: vi.fn((_: string, fn: (event: { matches: boolean }) => void) => listeners.add(fn)),
    removeEventListener: vi.fn((_: string, fn: (event: { matches: boolean }) => void) => listeners.delete(fn)),
  };
  vi.stubGlobal('matchMedia', vi.fn(() => media));
  return { media, change: (now: boolean) => listeners.forEach((fn) => fn({ matches: now })) };
}

const Probe = defineComponent({
  setup() {
    const phone = usePhone();
    return () => h('i', String(phone.value));
  },
});

afterEach(() => vi.unstubAllGlobals());

describe('usePhone', () => {
  it("asks the topbar's breakpoint and follows it while mounted", async () => {
    const { media, change } = fakeMedia(true);
    const wrapper = mount(Probe);
    expect(window.matchMedia).toHaveBeenCalledWith(PHONE_QUERY);
    expect(PHONE_QUERY).toBe('(max-width: 767px)');
    expect(wrapper.text()).toBe('true');
    change(false);
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toBe('false');
    wrapper.unmount();
    expect(media.removeEventListener).toHaveBeenCalled();
  });

  it('is a desk without matchMedia', () => {
    vi.stubGlobal('matchMedia', undefined);
    expect(mount(Probe).text()).toBe('false');
  });
});
