// «More options» of the topbar on a phone (BASE-F92) and the moment its rows act. Ionic keeps a popover presented
// while it plays its way out, and its focus trap pulls the keyboard back into it all that time: the assistant's box
// opened in that window lost the focus to a row of the menu, and the Enter written into it opened the bell (hub#1121).
// The double below plays that way out until the test lets it end (`finishLeaving`), as Ionic does after its animation.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, shallowRef, watch } from 'vue';

import { createAssistant, installAssistant, useAssistant } from '@erplora/ui/components';

import { flush, memoryStorage, mountBase } from '../__tests__/mount-base';
import TopbarChrome from './TopbarChrome.vue';

/** The popovers on their way out: each one ends when the test says so, then says `didDismiss`. */
const leaving: (() => void)[] = [];
/** The popovers on screen: a tap on the backdrop of each, which Ionic dismisses on its own (role `backdrop`). */
const backdrops = new Set<() => void>();

vi.mock('@ionic/vue', async (importOriginal) => {
  const LeavingPopover = defineComponent({
    name: 'IonPopover',
    inheritAttrs: false,
    props: { isOpen: Boolean, event: { type: null, default: undefined } },
    emits: ['didDismiss'],
    setup(props, { attrs, emit, slots }) {
      const shown = shallowRef(props.isOpen);
      let going = false;
      const leave = (role?: string): void => {
        if (!shown.value || going) return;
        going = true;
        leaving.push(() => {
          going = false;
          shown.value = false;
          backdrops.delete(backdrop);
          emit('didDismiss', new CustomEvent('didDismiss', { detail: { data: undefined, role } }));
        });
      };
      const backdrop = (): void => leave('backdrop');
      watch(
        () => props.isOpen,
        (open) => {
          if (!open) return leave();
          shown.value = true;
          backdrops.add(backdrop);
        },
      );
      return () => (shown.value ? h('div', { ...attrs, 'data-stub': 'ion-popover' }, slots.default?.()) : null);
    },
  });
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonPopover: LeavingPopover };
});

/** Ionic's animation ends: every popover on its way out is gone and says so. */
async function finishLeaving(): Promise<void> {
  await flush();
  for (const done of leaving.splice(0)) done();
  await flush();
}

/** A tap outside the menu: Ionic dismisses it on its own. */
async function tapBackdrop(): Promise<void> {
  for (const tap of [...backdrops]) tap();
  await finishLeaving();
}

const row = (id: string) => document.querySelector<HTMLElement>(`[data-testid="topbar-chrome-more-${id}"]`);

async function openMenu(m: Awaited<ReturnType<typeof mountBase>>): Promise<void> {
  await m.wrapper.get('[data-testid="topbar-chrome-more"]').trigger('click');
  await flush();
  expect(row('assistant')).not.toBeNull();
}

beforeEach(() => {
  installAssistant(createAssistant({ storage: memoryStorage(), openStorage: memoryStorage(), post: async () => undefined }));
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query === '(max-width: 767px)', addEventListener() {}, removeEventListener() {},
  }));
});

afterEach(() => {
  leaving.length = 0;
  backdrops.clear();
  vi.unstubAllGlobals();
  installAssistant(undefined);
  document.body.innerHTML = '';
});

describe('«More options» on a phone: a row acts once the menu has closed (hub#1121)', () => {
  it('«Assistant» opens the panel when the menu has finished closing, never while it still holds the keyboard', async () => {
    const m = await mountBase(TopbarChrome);
    await openMenu(m);
    row('assistant')!.click();
    await flush();
    // The menu is on its way out, and Ionic's focus trap is still in it: the panel waits.
    expect(row('assistant')).not.toBeNull();
    expect(useAssistant().state.open).toBe(false);

    await finishLeaving();
    expect(row('assistant')).toBeNull();
    expect(useAssistant().state.open).toBe(true);
  });

  it('closing the menu without choosing (a tap outside) opens nothing', async () => {
    const m = await mountBase(TopbarChrome);
    await openMenu(m);
    await tapBackdrop();
    expect(row('assistant')).toBeNull();
    expect(useAssistant().state.open).toBe(false);
  });

  it('the panel opened once from the menu is not opened again by a later close of the menu', async () => {
    const m = await mountBase(TopbarChrome);
    await openMenu(m);
    row('assistant')!.click();
    await finishLeaving();
    expect(useAssistant().state.open).toBe(true);
    useAssistant().setOpen(false);
    await flush();

    await openMenu(m);
    await tapBackdrop();
    expect(useAssistant().state.open).toBe(false);
  });
});
