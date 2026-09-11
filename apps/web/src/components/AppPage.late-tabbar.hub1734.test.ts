// @vitest-environment happy-dom
// Regression test for ERPlora/hub#1734 — the footer tabbar of a MODULE was never wired.
//
// What was on screen (QA on Android, hub v1.1.21): in VeriFactu the bottom bar read
// «Registros · Contingencia · Eventos · Recup…» with the last tab sliced by the right edge and
// nothing saying there was more. The shell owns that behaviour — `AppPage` calls `bindTabbar()`
// from OutfitKit, which is what marks the bar as overflowing (`data-overflow`), paints the fade
// and keeps the selected tab in view.
//
// It never ran on a module screen. `AppPage` looked for `ion-footer ion-segment` ONCE, inside its
// own `onMounted` + a single `nextTick`, and `ModuleView` renders that footer behind
// `v-if="segmentTabs.length > 1"` — tabs that arrive from the manifest, over the network, long
// after the layout mounted. The child mounts before the parent, so the query ran while the footer
// did not exist yet, found nothing, and the layout never looked again: every module screen was left
// with a raw `ion-segment`, no overflow hint, whatever OutfitKit version shipped underneath.
//
// So this is about WHEN the layout wires the bar, not about what the bar does once wired:
//
//   • a footer that arrives LATE is wired all the same — the defect;
//   • a footer already there at mount stays wired exactly once — no double binding;
//   • a footer that goes away is unwired — a module with a single tab, or a switch between
//     modules, must not leave a listener on a detached element;
//   • leaving the screen unwires — `bindTabbar` returns the undo and it has to be called.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { defineComponent, nextTick, ref } from 'vue';

const untie = vi.fn();
const bindTabbar = vi.fn((_segment: HTMLElement) => untie);
vi.mock('@erplora/outfitkit/tabbar', () => ({ bindTabbar: (el: HTMLElement) => bindTabbar(el) }));

// The layout is what is under test; its three fixed pieces are not.
vi.mock('@ionic/vue', () => ({
  IonPage: { name: 'IonPage', template: '<div class="ion-page"><slot /></div>' },
  IonContent: { name: 'IonContent', template: '<div class="ion-content"><slot /></div>' },
}));
vi.mock('./AppTopbar.vue', () => ({ default: { name: 'AppTopbar', template: '<div />' } }));
vi.mock('./SetupBlockingStrip.vue', () => ({
  default: { name: 'SetupBlockingStrip', template: '<div />' },
}));
vi.mock('./OfflineStrip.vue', () => ({ default: { name: 'OfflineStrip', template: '<div />' } }));
vi.mock('../lib/setup-status', async () => {
  const { ref: r } = await import('vue');
  return { setupStatus: r(null) };
});

import AppPage from './AppPage.vue';

/**
 * A screen whose footer tabbar appears only when `tabs` has more than one entry — the shape
 * `ModuleView` has: the tabs come from `navigation[]` of the manifest, fetched after mount.
 */
const ModuleLikeScreen = defineComponent({
  components: { AppPage },
  setup() {
    const tabs = ref<string[]>([]);
    return { tabs };
  },
  template: `
    <AppPage title="VeriFactu">
      <p>contenido</p>
      <template #footer>
        <ion-footer v-if="tabs.length > 1">
          <ion-toolbar>
            <ion-segment class="ok-tabbar module-tabbar">
              <ion-segment-button v-for="t in tabs" :key="t" :value="t">{{ t }}</ion-segment-button>
            </ion-segment>
          </ion-toolbar>
        </ion-footer>
      </template>
    </AppPage>
  `,
});

let screen: ReturnType<typeof mount> | null = null;

/** Mounted attached to the document: the layout finds its footer with a DOM query. */
function mountScreen() {
  screen = mount(ModuleLikeScreen, {
    global: {
      config: { compilerOptions: { isCustomElement: (tag: string) => tag.startsWith('ion-') } },
    },
    attachTo: document.body,
  });
  return screen as ReturnType<typeof mount> & { vm: { tabs: string[] } };
}

/** The footer as the LAYOUT looks for it, but scoped to this screen — never a leftover of another. */
const tabbarOf = (s: ReturnType<typeof mountScreen>) =>
  s.element.querySelector('ion-footer ion-segment');

beforeEach(() => {
  bindTabbar.mockClear();
  untie.mockClear();
});

// A screen left mounted would leave its footer in the document and the next test would find it.
afterEach(() => {
  screen?.unmount();
  screen = null;
  document.body.innerHTML = '';
});

describe('the shell wires the footer tabbar whenever it appears (hub#1734)', () => {
  it('wires a tabbar that arrives AFTER mount, like a module getting its tabs from the manifest', async () => {
    const screen = mountScreen();
    await nextTick();
    // Nothing to wire yet: the manifest has not answered.
    expect(bindTabbar).not.toHaveBeenCalled();

    screen.vm.tabs = ['records', 'contingency', 'events', 'recovery', 'settings'];
    await flushPromises();

    const segment = tabbarOf(screen);
    expect(segment, 'the footer is on screen').not.toBeNull();
    expect(bindTabbar).toHaveBeenCalledTimes(1);
    expect(bindTabbar.mock.calls[0][0]).toBe(segment);
  });

  it('wires a tabbar that is already there at mount exactly once, however the screen re-renders', async () => {
    const screen = mountScreen();
    screen.vm.tabs = ['a', 'b'];
    await nextTick();
    expect(bindTabbar).toHaveBeenCalledTimes(1);

    // Same bar, one more tab: the element survives the patch, so it must NOT be wired twice —
    // two bindings mean two scroll listeners and two fades fighting over one bar.
    screen.vm.tabs = ['a', 'b', 'c'];
    await flushPromises();
    expect(bindTabbar).toHaveBeenCalledTimes(1);
    expect(untie).not.toHaveBeenCalled();
  });

  it('unwires when the tabbar goes away — a module left with one tab keeps no listener behind', async () => {
    const screen = mountScreen();
    screen.vm.tabs = ['a', 'b'];
    await nextTick();
    expect(bindTabbar).toHaveBeenCalledTimes(1);

    screen.vm.tabs = ['a'];
    await flushPromises();
    expect(tabbarOf(screen)).toBeNull();
    expect(untie).toHaveBeenCalledTimes(1);
  });

  it('unwires when leaving the screen', async () => {
    const screen = mountScreen();
    screen.vm.tabs = ['a', 'b'];
    await nextTick();
    expect(bindTabbar).toHaveBeenCalledTimes(1);

    screen.unmount();
    expect(untie).toHaveBeenCalledTimes(1);
  });
});
