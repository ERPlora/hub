// `useScrollEdges(el)`: which edges of a sideways scroller have something behind them, so each one fades out
// (a hard cut reads «nothing more»: tables#97). Measured when the scroller appears, on its scroll, and when
// it or what it holds is resized; `mark()` measures again on demand (new content of the same size).
import { mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';
import { defineComponent, h, nextTick, ref } from 'vue';

import { useScrollEdges } from './useScrollEdges';

/** Gives `el` the box of a scroller `client` px wide holding `scroll` px, scrolled to `left`. */
function box(el: Element, client: number, scroll: number, left = 0): void {
  Object.defineProperty(el, 'clientWidth', { configurable: true, value: client });
  Object.defineProperty(el, 'scrollWidth', { configurable: true, value: scroll });
  Object.defineProperty(el, 'scrollLeft', { configurable: true, writable: true, value: left });
}

async function setup(shown = true) {
  const visible = ref(shown);
  let api!: ReturnType<typeof useScrollEdges>;
  const Host = defineComponent({
    setup() {
      const strip = ref<HTMLElement | null>(null);
      const inner = ref<HTMLElement | null>(null);
      api = useScrollEdges(strip, () => [inner.value]);
      return () => (visible.value ? h('div', { ref: strip, 'data-testid': 'strip' }, [h('div', { ref: inner, 'data-testid': 'inner' })]) : h('span'));
    },
  });
  const wrapper = mount(Host);
  await nextTick();
  const strip = () => wrapper.find('[data-testid="strip"]').element;
  const scroll = async (left: number) => {
    Object.defineProperty(strip(), 'scrollLeft', { configurable: true, writable: true, value: left });
    strip().dispatchEvent(new Event('scroll'));
    await nextTick();
  };
  return { wrapper, visible, strip, scroll, edges: () => ({ ...api.edges.value }), mark: () => api.mark() };
}

describe('useScrollEdges', () => {
  it('fades the edges with something behind them as the scroller moves', async () => {
    const s = await setup();
    box(s.strip(), 300, 700);
    s.mark();
    expect(s.edges()).toEqual({ left: false, right: true });
    await s.scroll(200);
    expect(s.edges()).toEqual({ left: true, right: true });
    await s.scroll(400);
    expect(s.edges()).toEqual({ left: true, right: false });
  });

  it('fades nothing when everything fits', async () => {
    const s = await setup();
    box(s.strip(), 300, 300);
    s.mark();
    expect(s.edges()).toEqual({ left: false, right: false });
  });

  it('follows a scroller that appears later (the zones arrive after the page)', async () => {
    const s = await setup(false);
    expect(s.edges()).toEqual({ left: false, right: false });
    s.visible.value = true;
    await nextTick();
    box(s.strip(), 300, 700);
    await s.scroll(400);
    expect(s.edges()).toEqual({ left: true, right: false });
  });

  it('measures again when the scroller or what it holds is resized, and lets both go with the screen', async () => {
    const seen: string[] = [];
    let resized = () => {};
    class FakeObserver {
      constructor(callback: () => void) {
        resized = callback;
      }
      observe(node: Element) {
        seen.push(`observe ${node.getAttribute('data-testid')}`);
      }
      unobserve() {}
      disconnect() {
        seen.push('disconnect');
      }
    }
    vi.stubGlobal('ResizeObserver', FakeObserver);
    try {
      const s = await setup();
      expect(seen).toEqual(['observe strip', 'observe inner']);
      box(s.strip(), 300, 700);
      resized();
      expect(s.edges()).toEqual({ left: false, right: true });
      s.wrapper.unmount();
      expect(seen.at(-1)).toBe('disconnect');
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('stops listening with the screen', async () => {
    const s = await setup();
    box(s.strip(), 300, 700);
    s.mark();
    const strip = s.strip();
    s.wrapper.unmount();
    Object.defineProperty(strip, 'scrollLeft', { configurable: true, writable: true, value: 400 });
    strip.dispatchEvent(new Event('scroll'));
    await nextTick();
    expect(s.edges()).toEqual({ left: false, right: true });
  });
});
