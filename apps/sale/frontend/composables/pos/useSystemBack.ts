// `useSystemBack()`: Android's Back on the installed app closes the till's own layers (the ⋮ screen menu, «Open
// checks», the phone's check drawer) — sheets of the app, not Ionic overlays, which the shell cannot see nor close.
// Base's contract (`base/frontend/lib/system-back.ts`, `erplora:back`): on every press the shell dispatches a
// cancelable event on `window`; an app with something open closes its TOPMOST layer synchronously and calls
// `preventDefault()`, and the shell keeps the screen. With nothing open the event is left alone: the shell's Back.
//
// Topmost is the last opened («Open checks» from inside the drawer goes first, the drawer on the next press), so the
// layers open now are kept in one stack, and one listener on `window` lives while it is not empty.
import { onScopeDispose, watch, type WatchSource } from 'vue';

import { SHELL_BACK_EVENT } from '../../../../../base/frontend/lib/system-back';

type Layer = () => void;

/** The own layers open now, bottom first. */
const layers: Layer[] = [];

function drop(layer: Layer): void {
  const at = layers.indexOf(layer);
  if (at < 0) return;
  layers.splice(at, 1);
  if (!layers.length) window.removeEventListener(SHELL_BACK_EVENT, onBack);
}

function onBack(event: Event): void {
  const top = layers.at(-1);
  if (!top || event.defaultPrevented) return;
  event.preventDefault();
  top();
}

/** While `open` is true, the system Back calls `close` — one press, one layer, the topmost first. */
export function useSystemBack(open: WatchSource<boolean>, close: () => void): void {
  const layer: Layer = () => close();
  watch(
    open,
    (isOpen) => {
      drop(layer);
      if (!isOpen) return;
      if (!layers.length) window.addEventListener(SHELL_BACK_EVENT, onBack);
      layers.push(layer);
    },
    // In step with `open`: the stack keeps the order the layers opened in, and a closed layer is off it before the
    // next press, repainted or not.
    { immediate: true, flush: 'sync' },
  );
  onScopeDispose(() => drop(layer));
}
