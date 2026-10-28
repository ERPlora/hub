// `useSystemBack()`: Android's Back on the installed app closes the till's own layers (the ⋮ screen menu, «Open
// checks», the phone's check drawer) — sheets of the app, not Ionic overlays, which the shell cannot see nor close.
// Base's contract (`base/frontend/lib/system-back.ts`, `erplora:back`): on every press the shell dispatches a
// cancelable event on `window`; an app with something open closes its TOPMOST layer synchronously and calls
// `preventDefault()`, and the shell keeps the screen. With nothing open the event is left alone: the shell's Back.
//
// Topmost is the last opened («Open checks» from inside the drawer goes first, the drawer on the next press), so the
// layers open now are kept in one stack, and one listener on `window` lives while it is not empty. Only the layers of
// the screen on view count: a screen pushed over the till (another app from the ⠿) leaves it mounted under it, hidden
// by Ionic, with whatever was open, and that one must not take the Back of the screen on top.
import { getCurrentInstance, onScopeDispose, watch, type WatchSource } from 'vue';

import { SHELL_BACK_EVENT } from '../../../../../base/frontend/lib/system-back';

/** Ionic's class on a page of its stack that is not on view. */
const HIDDEN_PAGE = '.ion-page-hidden';

type Layer = { close: () => void; onView: () => boolean };

/** The own layers open now, bottom first. */
const layers: Layer[] = [];

function drop(layer: Layer): void {
  const at = layers.indexOf(layer);
  if (at < 0) return;
  layers.splice(at, 1);
  if (!layers.length) window.removeEventListener(SHELL_BACK_EVENT, onBack);
}

function onBack(event: Event): void {
  if (event.defaultPrevented) return;
  for (let at = layers.length - 1; at >= 0; at--) {
    const layer = layers[at];
    if (!layer.onView()) continue;
    event.preventDefault();
    layer.close();
    return;
  }
}

/** While `open` is true, the system Back calls `close` — one press, one layer, the topmost first. */
export function useSystemBack(open: WatchSource<boolean>, close: () => void): void {
  const instance = getCurrentInstance();
  const layer: Layer = {
    close: () => close(),
    onView: () => {
      // The component's root, or the parent of its anchor when it renders a fragment or nothing.
      const node = instance?.proxy?.$el as Node | null | undefined;
      const element = node instanceof Element ? node : node?.parentElement;
      return !element?.closest(HIDDEN_PAGE);
    },
  };
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
