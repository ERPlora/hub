// base's piece at the end of the topbar on a phone (BASE-F92). It is the assistant's sparkles alone: the shell's «⋮»
// lists it beside «My apps» when they do not fit next to the bell, and there it is the row «Assistant», which opens the
// panel once the menu has gone. Ionic keeps a popover presented while it plays its way out, and its focus trap pulls the
// keyboard back into it all that time: a box opened in that window lost the focus to a row (hub#1121). The double below
// plays that way out until the test lets it end (`finishLeaving`), as Ionic does after its animation.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, shallowRef, watch } from 'vue';

import { createAssistant, installAssistant, useAssistant } from '@erplora/ui/components';

import TopbarMore from '../../../packages/ui/src/shell/TopbarMore.vue';
import { outOfTheApp } from '../__tests__/app-download';
import { flush, memoryStorage, mountBase, OWNER } from '../__tests__/mount-base';
import { changeBusinessOpen } from '../lib/change-business';
import TopbarChrome from './TopbarChrome.vue';

/** The popovers on their way out: each one ends when the test says so, then says `didDismiss`. */
const leaving: (() => void)[] = [];

vi.mock('@ionic/vue', async (importOriginal) => {
  const LeavingPopover = defineComponent({
    name: 'IonPopover',
    inheritAttrs: false,
    props: { isOpen: Boolean, event: { type: null, default: undefined } },
    emits: ['didDismiss'],
    setup(props, { attrs, emit, slots }) {
      const shown = shallowRef(props.isOpen);
      watch(
        () => props.isOpen,
        (open) => {
          if (open) {
            shown.value = true;
            return;
          }
          leaving.push(() => {
            shown.value = false;
            emit('didDismiss', new CustomEvent('didDismiss', { detail: { data: undefined, role: undefined } }));
          });
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

/** The shell's «⋮» listing base's piece, as the bar does on a phone. */
const InTheShellMenu = defineComponent(() => () => h(TopbarMore, null, { default: () => h(TopbarChrome) }));

const inTheMenu = (id: string) => document.querySelector<HTMLElement>(`[data-stub="ion-popover"] [data-testid="${id}"]`);

beforeEach(() => {
  installAssistant(createAssistant({ storage: memoryStorage(), openStorage: memoryStorage(), post: async () => undefined }));
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query === '(max-width: 767px)', addEventListener() {}, removeEventListener() {},
  }));
});

afterEach(() => {
  leaving.length = 0;
  outOfTheApp();
  changeBusinessOpen.value = false;
  vi.unstubAllGlobals();
  installAssistant(undefined);
  document.body.innerHTML = '';
});

describe('base’s piece of the topbar on a phone (under 768 px)', () => {
  it('is the assistant’s sparkles alone, with no menu of its own: the shell’s «⋮» is the one that folds it', async () => {
    const m = await mountBase(TopbarChrome);
    expect(m.wrapper.findAll('ion-button').map((button) => button.attributes('data-testid'))).toEqual(['assistant-button']);
    expect(m.wrapper.findAllComponents({ name: 'IonPopover' })).toHaveLength(0);
  });

  it('listed in the shell’s «⋮», it is the row «Asistente», which opens the panel once the menu has gone (hub#1121)', async () => {
    const m = await mountBase(InTheShellMenu, { locale: 'es' });
    await m.wrapper.get('[data-testid="topbar-more"]').trigger('click');
    await flush();
    expect(inTheMenu('assistant-button')?.textContent?.trim()).toBe('Asistente');

    inTheMenu('assistant-button')!.click();
    await flush();
    // The menu is on its way out, and Ionic's focus trap is still in it: the panel waits.
    expect(useAssistant().state.open).toBe(false);
    await finishLeaving();
    expect(inTheMenu('assistant-button')).toBeNull();
    expect(useAssistant().state.open).toBe(true);
  });

  it('puts nothing on the bar for who may not use the assistant', async () => {
    const m = await mountBase(TopbarChrome, { session: { ...OWNER, permissions: [] } });
    expect(m.wrapper.findAll('ion-button')).toHaveLength(0);
  });
});

describe('base’s piece of the topbar inside the installed app', () => {
  const insideTheApp = () => {
    (window as { __TAURI__?: unknown }).__TAURI__ = { core: { invoke: vi.fn(async () => undefined) } };
  };

  it('is the assistant’s sparkles and then «Change business» (ERPlora/app HUB_APP-F04)', async () => {
    insideTheApp();
    const m = await mountBase(TopbarChrome);
    expect(m.wrapper.findAll('ion-button').map((button) => button.attributes('data-testid'))).toEqual([
      'assistant-button',
      'change-business-button',
    ]);
  });

  it('listed in the shell’s «⋮», «Cambiar de negocio» is a row that asks once the menu has gone', async () => {
    insideTheApp();
    const m = await mountBase(InTheShellMenu, { locale: 'es' });
    await m.wrapper.get('[data-testid="topbar-more"]').trigger('click');
    await flush();
    expect(inTheMenu('change-business-button')?.textContent?.trim()).toBe('Cambiar de negocio');

    inTheMenu('change-business-button')!.click();
    await flush();
    expect(changeBusinessOpen.value).toBe(false);
    await finishLeaving();
    expect(inTheMenu('change-business-button')).toBeNull();
    expect(changeBusinessOpen.value).toBe(true);
  });
});
