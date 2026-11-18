import { type Ref, shallowRef } from 'vue';

interface Pan {
  pointerId: number;
  x: number;
  y: number;
  left: number;
  top: number;
}

const PAN_STEP = 48;
const ARROWS: Record<string, [number, number]> = {
  ArrowLeft: [-PAN_STEP, 0],
  ArrowRight: [PAN_STEP, 0],
  ArrowUp: [0, -PAN_STEP],
  ArrowDown: [0, PAN_STEP],
};

export function useStagePan(stage: Readonly<Ref<HTMLElement | null>>) {
  const panning = shallowRef(false);
  let pan: Pan | null = null;

  function onPointerDown(event: PointerEvent): void {
    const box = stage.value;
    if (!box || event.pointerType !== 'mouse' || event.button !== 0) return;
    if ((event.target as Element | null)?.closest('[data-testid^="table-floor-tile-"]')) return;
    pan = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, left: box.scrollLeft, top: box.scrollTop };
    box.setPointerCapture?.(event.pointerId);
    panning.value = true;
    event.preventDefault();
  }

  function onPointerMove(event: PointerEvent): void {
    const box = stage.value;
    if (!box || !pan || pan.pointerId !== event.pointerId) return;
    box.scrollLeft = pan.left - (event.clientX - pan.x);
    box.scrollTop = pan.top - (event.clientY - pan.y);
  }

  function onPointerUp(): void {
    pan = null;
    panning.value = false;
  }

  function onKeydown(event: KeyboardEvent): void {
    const box = stage.value;
    const delta = ARROWS[event.key];
    if (!box || event.target !== box || !delta) return;
    event.preventDefault();
    box.scrollLeft += delta[0];
    box.scrollTop += delta[1];
  }

  return { panning, onPointerDown, onPointerMove, onPointerUp, onKeydown };
}
