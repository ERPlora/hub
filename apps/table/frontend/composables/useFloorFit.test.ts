import { mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, nextTick, type Ref, ref } from 'vue';

import type { Size } from '../lib/floor';
import { useFloorFit } from './useFloorFit';

async function mountFit(content: Ref<Size>, style = '', refit?: () => unknown) {
  let api!: ReturnType<typeof useFloorFit>;
  const Host = defineComponent({
    setup() {
      const stage = ref<HTMLElement | null>(null);
      api = useFloorFit(stage, content, refit);
      return () => h('div', { ref: stage, 'data-testid': 'stage', style });
    },
  });
  const wrapper = mount(Host, { attachTo: document.body });
  await nextTick();
  const stage = wrapper.find('[data-testid="stage"]').element;
  const resize = (w: number, h: number) => {
    Object.defineProperty(stage, 'clientWidth', { configurable: true, value: w });
    Object.defineProperty(stage, 'clientHeight', { configurable: true, value: h });
  };
  return { wrapper, fit: () => api.fit.value, resize };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Stands in for the browser's ResizeObserver: `resized()` is the stage's resize, `disconnected()` its end. */
function stubObserver() {
  let callback = () => {};
  let disconnected = false;
  class FakeObserver {
    constructor(resized: () => void) {
      callback = resized;
    }
    observe() {}
    disconnect() {
      disconnected = true;
    }
  }
  vi.stubGlobal('ResizeObserver', FakeObserver);
  return { resized: () => callback(), disconnected: () => disconnected };
}

describe('useFloorFit', () => {
  it('starts at one with an unmeasured stage, follows resize and content, and disconnects', async () => {
    const { resized, disconnected } = stubObserver();
    const content = ref<Size>({ w: 450, h: 186 });
    const f = await mountFit(content);
    expect(f.fit()).toEqual({ spread: 1, box: 1, plane: { w: 450, h: 186 } });
    f.resize(1100, 600);
    resized();
    expect(f.fit().spread).toBe(2.2);
    expect(f.fit().plane).toEqual({ w: 990, h: 409.2 });
    content.value = { w: 900, h: 372 };
    await nextTick();
    expect(f.fit().plane).toEqual({ w: 1530, h: 632.4 });
    f.wrapper.unmount();
    expect(disconnected()).toBe(true);
  });

  it('works without ResizeObserver and measures again when content changes', async () => {
    vi.stubGlobal('ResizeObserver', undefined);
    const content = ref<Size>({ w: 450, h: 186 });
    const f = await mountFit(content);
    expect(f.fit().spread).toBe(1);
    content.value = { w: 900, h: 372 };
    await nextTick();
    expect(f.fit().plane).toEqual({ w: 900, h: 372 });
    f.wrapper.unmount();
  });

  it('fits the plan inside the stage padding, the room kept for the labels of the outer tables', async () => {
    const { resized } = stubObserver();
    const f = await mountFit(ref<Size>({ w: 450, h: 186 }), 'padding: 24px');
    f.resize(948, 700);
    resized();
    expect(f.fit().spread).toBe(2);
    f.wrapper.unmount();
  });

  it('with its own trigger keeps the scale while the content changes, and fits the content of the moment on that trigger or a resize', async () => {
    const { resized } = stubObserver();
    const content = ref<Size>({ w: 450, h: 186 });
    const key = ref('zone-a');
    const f = await mountFit(content, '', () => key.value);
    f.resize(900, 600);
    resized();
    expect(f.fit().spread).toBe(2);
    content.value = { w: 600, h: 186 };
    await nextTick();
    expect(f.fit().spread).toBe(2);
    key.value = 'zone-b';
    await nextTick();
    expect(f.fit().spread).toBe(1.7);
    content.value = { w: 400, h: 186 };
    await nextTick();
    f.resize(880, 600);
    resized();
    expect(f.fit().spread).toBe(2.2);
    f.wrapper.unmount();
  });
});
