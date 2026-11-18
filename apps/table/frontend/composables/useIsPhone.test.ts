import { mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, nextTick } from 'vue';

import { useIsPhone } from './useIsPhone';

function mountPhone() {
  let api!: ReturnType<typeof useIsPhone>;
  const Host = defineComponent({
    setup() {
      api = useIsPhone();
      return () => h('div');
    },
  });
  const wrapper = mount(Host);
  return { wrapper, phone: () => api.value };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useIsPhone', () => {
  it('follows the 640 px phone breakpoint and lets it go with the screen', async () => {
    let listener: ((event: { matches: boolean }) => void) | null = null;
    const media = {
      matches: true,
      addEventListener: vi.fn((_: string, fn: (event: { matches: boolean }) => void) => {
        listener = fn;
      }),
      removeEventListener: vi.fn(),
    };
    const matchMedia = vi.fn(() => media);
    vi.stubGlobal('matchMedia', matchMedia);
    const p = mountPhone();
    expect(matchMedia).toHaveBeenCalledWith('(max-width: 640px)');
    expect(p.phone()).toBe(true);
    listener!({ matches: false });
    await nextTick();
    expect(p.phone()).toBe(false);
    p.wrapper.unmount();
    expect(media.removeEventListener).toHaveBeenCalledWith('change', listener);
  });

  it('is a desk without matchMedia', () => {
    vi.stubGlobal('matchMedia', undefined);
    expect(mountPhone().phone()).toBe(false);
  });
});
