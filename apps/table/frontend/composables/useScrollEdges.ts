// `useScrollEdges(el, content)`: which of the four edges of a scroller have something behind them, so each
// one fades out (a hard cut reads «nothing more»). Measured when the scroller appears (it may come after the
// page: the zone strip waits for the zones), on its scroll, and when it or what it holds (`content`) is
// resized; `mark()` measures again on demand.
import { onBeforeUnmount, type Ref, ref, watch } from 'vue';

export interface ScrollEdges {
  left: boolean;
  right: boolean;
  top: boolean;
  bottom: boolean;
}

export function useScrollEdges(el: Readonly<Ref<HTMLElement | null | undefined>>, content: () => (Element | null | undefined)[] = () => []) {
  const edges = ref<ScrollEdges>({ left: false, right: false, top: false, bottom: false });

  function mark(): void {
    const box = el.value;
    if (!box) return;
    const hiddenX = box.scrollWidth - box.clientWidth;
    const hiddenY = box.scrollHeight - box.clientHeight;
    edges.value = {
      left: box.scrollLeft > 1,
      right: box.scrollLeft < hiddenX - 1,
      top: box.scrollTop > 1,
      bottom: box.scrollTop < hiddenY - 1,
    };
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
