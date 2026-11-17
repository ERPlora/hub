import { onBeforeUnmount, type Ref, shallowRef, watch } from 'vue';

import { fitPlan, type FloorFit } from '../lib/floor-fit';
import type { Size } from '../lib/floor';

export function useFloorFit(stage: Readonly<Ref<HTMLElement | null>>, content: Readonly<Ref<Size>>) {
  const fit = shallowRef<FloorFit>(fitPlan(content.value, { w: 0, h: 0 }));
  let observer: ResizeObserver | null = null;

  function measure(): void {
    const box = stage.value;
    fit.value = fitPlan(content.value, { w: box?.clientWidth ?? 0, h: box?.clientHeight ?? 0 });
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
