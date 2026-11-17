import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { useStagePan } from './useStagePan';

async function setup() {
  let api!: ReturnType<typeof useStagePan>;
  const Host = defineComponent({
    setup() {
      const stage = ref<HTMLElement | null>(null);
      api = useStagePan(stage);
      return () =>
        h(
          'div',
          {
            ref: stage,
            'data-testid': 'stage',
            // Vue binds `onPointerdown` to `pointerdown`; `onPointerDown` would listen to `pointer-down`.
            onPointerdown: api.onPointerDown,
            onPointermove: api.onPointerMove,
            onPointerup: api.onPointerUp,
          },
          [h('div', { 'data-testid': 'table-floor-tile-t1' }, [h('button', { 'data-testid': 'table' }, 'Table')])],
        );
    },
  });
  const wrapper = mount(Host);
  const stage = wrapper.find('[data-testid="stage"]').element as HTMLElement;
  stage.scrollLeft = 100;
  stage.scrollTop = 80;
  const pointer = async (type: string, x: number, y: number, target = stage) => {
    const event = new PointerEvent(type, { bubbles: true, pointerId: 1, pointerType: 'mouse', button: 0, clientX: x, clientY: y });
    target.dispatchEvent(event);
    await wrapper.vm.$nextTick();
  };
  const key = (name: string, target = stage) => {
    const event = new KeyboardEvent('keydown', { key: name, bubbles: true });
    Object.defineProperty(event, 'target', { value: target });
    api.onKeydown(event);
  };
  return { wrapper, stage, pointer, panning: () => api.panning.value, key };
}

describe('useStagePan', () => {
  it('drags the background with a mouse in both axes', async () => {
    const s = await setup();
    await s.pointer('pointerdown', 200, 200);
    expect(s.panning()).toBe(true);
    await s.pointer('pointermove', 160, 140);
    expect([s.stage.scrollLeft, s.stage.scrollTop]).toEqual([140, 140]);
    await s.pointer('pointerup', 160, 140);
    expect(s.panning()).toBe(false);
  });

  it('does not start a pan from a table or a non-mouse pointer', async () => {
    const s = await setup();
    const table = s.wrapper.find('[data-testid="table"]').element;
    await s.pointer('pointerdown', 200, 200, table);
    expect(s.panning()).toBe(false);
    const touch = new PointerEvent('pointerdown', { bubbles: true, pointerType: 'touch', button: 0 });
    Object.defineProperty(touch, 'currentTarget', { value: s.stage });
    s.stage.dispatchEvent(touch);
    expect(s.panning()).toBe(false);
  });

  it('scrolls a focused stage with arrows without taking a table key', async () => {
    const s = await setup();
    s.key('ArrowRight');
    s.key('ArrowDown');
    expect([s.stage.scrollLeft, s.stage.scrollTop]).toEqual([148, 128]);
    s.key('ArrowLeft', s.wrapper.find('[data-testid="table"]').element as HTMLElement);
    expect(s.stage.scrollLeft).toBe(148);
  });
});
