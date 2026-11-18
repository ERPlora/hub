import { onBeforeUnmount, type Ref, shallowRef, watch } from 'vue';

import { fitPlan, type FloorFit } from '../lib/floor-fit';
import type { Size } from '../lib/floor';

/** The stage's box without its padding: the room the plan may fill. */
function inner(box: HTMLElement | null): Size {
  if (!box) return { w: 0, h: 0 };
  const style = getComputedStyle(box);
  const across = (parseFloat(style.paddingLeft) || 0) + (parseFloat(style.paddingRight) || 0);
  const down = (parseFloat(style.paddingTop) || 0) + (parseFloat(style.paddingBottom) || 0);
  return { w: Math.max(0, box.clientWidth - across), h: Math.max(0, box.clientHeight - down) };
}

export function useFloorFit(stage: Readonly<Ref<HTMLElement | null>>, content: Readonly<Ref<Size>>) {
  const fit = shallowRef<FloorFit>(fitPlan(content.value, { w: 0, h: 0 }));
  let observer: ResizeObserver | null = null;

  function measure(): void {
    fit.value = fitPlan(content.value, inner(stage.value));
  }

  watch(
    stage,
    (box) => {
      observer?.disconnect();
      observer = null;
      if (box && typeof ResizeObserver !== 'undefined') {
        observer = new ResizeObserver(measure);
        observer.observe(box);
      }
      measure();
    },
    { immediate: true, flush: 'post' },
  );
  watch(content, measure);
  onBeforeUnmount(() => observer?.disconnect());
  return { fit, measure };
}
