// `usePhone`: the Home folds on a phone as the topbar does (767 px), and follows a crossed breakpoint. `useLowHeight`:
// a screen as low as a phone on its side (500 px, the till's own cut, hub#800), where the red strip goes in one line
// (hub#838).
import { mount } from '@vue/test-utils';
import { defineComponent, h, type Ref } from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { LOW_HEIGHT_QUERY, PHONE_QUERY, useLowHeight, usePhone } from './phone';

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

/** A component that paints what `use` says, live. */
const probeOf = (use: () => Ref<boolean>) =>
  defineComponent({
    setup() {
      const matches = use();
      return () => h('i', String(matches.value));
    },
  });

const Probe = probeOf(usePhone);
const LowProbe = probeOf(useLowHeight);

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

describe('useLowHeight', () => {
  it("asks the till's cut, 500 px high or less, and follows a phone turned while mounted", async () => {
    const { media, change } = fakeMedia(false);
    const wrapper = mount(LowProbe);
    expect(window.matchMedia).toHaveBeenCalledWith(LOW_HEIGHT_QUERY);
    expect(LOW_HEIGHT_QUERY).toBe('(max-height: 500px)');
    expect(wrapper.text()).toBe('false');
    change(true);
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toBe('true');
    wrapper.unmount();
    expect(media.removeEventListener).toHaveBeenCalled();
  });

  it('is a tall screen without matchMedia', () => {
    vi.stubGlobal('matchMedia', undefined);
    expect(mount(LowProbe).text()).toBe('false');
  });
});
