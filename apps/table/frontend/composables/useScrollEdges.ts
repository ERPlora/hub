// `useScrollEdges(el, content)`: which edges of a sideways scroller have something behind them, so each one
// fades out (a hard cut reads «nothing more»: tables#97). Measured when the scroller appears (it may come
// after the page: the zone strip waits for the zones), on its scroll, and when it or what it holds (`content`)
// is resized; `mark()` measures again on demand.
import { onBeforeUnmount, type Ref, ref, watch } from 'vue';

export interface ScrollEdges {
  left: boolean;
  right: boolean;
}

export function useScrollEdges(el: Readonly<Ref<HTMLElement | null | undefined>>, content: () => (Element | null | undefined)[] = () => []) {
  const edges = ref<ScrollEdges>({ left: false, right: false });

  function mark(): void {
    const box = el.value;
    if (!box) return;
    const hidden = box.scrollWidth - box.clientWidth;
    edges.value = { left: box.scrollLeft > 1, right: box.scrollLeft < hidden - 1 };
  }

  let observer: ResizeObserver | null = null;
  function detach(box: HTMLElement | null | undefined): void {
    box?.removeEventListener('scroll', mark);
    observer?.disconnect();
    observer = null;
  }
  function attach(box: HTMLElement | null | undefined): void {
    if (!box) return;
    box.addEventListener('scroll', mark, { passive: true });
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(mark);
      observer.observe(box);
      for (const node of content()) if (node) observer.observe(node);
    }
    mark();
  }

  watch(
    el,
    (now, before) => {
      detach(before);
      attach(now);
    },
    { immediate: true, flush: 'post' },
  );
  onBeforeUnmount(() => detach(el.value));

  return { edges, mark };
}
