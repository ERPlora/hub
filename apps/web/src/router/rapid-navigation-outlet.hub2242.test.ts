// @vitest-environment happy-dom
//
// hub#2242 — going back and forth quickly (Home → Staff → Home → Staff, tapping before the slide
// ends) left the address on Staff and Home on screen. Measured in Chromium against develop: 4/4
// with a gap of 150 or 300 ms, and the third navigation fired no ionViewWillEnter at all.
//
// The cause is @ionic/vue's IonRouterOutlet (8.8.9, unchanged in 9.0.5). Its `transition()` marks
// the entering page `ion-page-invisible` and only THEN waits for the outlet's transition lock, so
// while Staff → Home is still queued behind Home → Staff, Home is "invisible" and Staff is still
// visible. The third navigation (→ Staff) reads exactly that and returns early — "the entering
// view is already visible" — and when the queued transition finishes, Home is the page shown.
//
// Pinned here through the REAL IonRouterOutlet and Ionic's router. The only stand-in is the
// `<ion-router-outlet>` element's `commit` (the animation), which this test finishes by hand so
// the navigations can land in the middle of one, as a quick finger does.
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { createApp, defineComponent, h, type App } from 'vue';
import { IonicVue, IonPage, IonRouterOutlet } from '@ionic/vue';
import { createMemoryHistory, createRouter } from '@ionic/vue-router';
import type { Router } from 'vue-router';

type Commit = { entering: HTMLElement; leaving: HTMLElement | undefined; finish: () => void };
const commits: Commit[] = [];

beforeAll(() => {
  // Defined BEFORE the outlet mounts: `IonRouterOutlet` only defines Ionic's element when the tag is
  // still free. The fake keeps what matters of the real one — one transition at a time (its lock),
  // the classes @ionic/core's `transition()` moves (both pages un-hidden and the entering one made
  // visible when the slide starts, `ion-page-invisible` cleared on both when it ends) and a promise
  // that settles when the animation ends — and lets the test decide when that is.
  class FakeRouterOutlet extends HTMLElement {
    private queue: Promise<unknown> = Promise.resolve();
    commit(entering: HTMLElement, leaving: HTMLElement | undefined): Promise<boolean> {
      const run = () =>
        new Promise<boolean>((resolve) => {
          // Ionic starts the slide in a `writeTask` (the next frame), not in the unlock's microtask.
          setTimeout(() => {
            for (const el of [entering, leaving]) el?.classList.remove('ion-page-hidden');
            entering.classList.remove('ion-page-invisible');
            commits.push({
              entering,
              leaving,
              finish: () => {
                for (const el of [entering, leaving]) el?.classList.remove('ion-page-invisible');
                resolve(true);
              },
            });
          }, 0);
        });
      const done = this.queue.then(run);
      this.queue = done;
      return done;
    }
  }
  customElements.define('ion-router-outlet', FakeRouterOutlet);
});

const page = (name: string) => defineComponent({ name, render: () => h(IonPage, { 'data-page': name }, () => name) });

let app: App | undefined;
afterEach(() => {
  app?.unmount();
  app = undefined;
  commits.length = 0;
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
});

async function mountShell(): Promise<Router> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', redirect: '/home' },
      { path: '/home', component: page('home') },
      { path: '/staff', component: page('staff') },
      // A screen without `<ion-page>`: Ionic cannot slide it, and on a second visit its own
      // transition code throws (`isViewVisible(undefined)`).
      { path: '/bare', component: defineComponent({ name: 'bare', render: () => h('div', 'bare') }) },
    ],
  });
  app = createApp({ render: () => h(IonRouterOutlet) });
  app.use(IonicVue).use(router);
  await router.push('/home');
  await router.isReady();
  const root = document.createElement('div');
  document.body.appendChild(root);
  app.mount(root);
  await settle();
  return router;
}

const settle = async () => {
  for (let i = 0; i < 10; i++) await new Promise((r) => setTimeout(r, 0));
};

/** Ends every animation that has started, one by one, until nothing is running any more. */
async function finishAnimations() {
  for (let guard = 0; guard < 20; guard++) {
    await settle();
    const running = commits.shift();
    if (!running) return;
    running.finish();
  }
  throw new Error('the outlet kept starting transitions');
}

/** The page the person sees: the one the outlet neither hid nor left invisible. */
function shownPages(): string[] {
  return [...document.querySelectorAll<HTMLElement>('.ion-page[data-page]')]
    .filter((el) => !el.classList.contains('ion-page-hidden') && !el.classList.contains('ion-page-invisible'))
    .map((el) => el.dataset.page!);
}

describe('hub#2242 — a navigation that lands while the previous page still slides is not lost', () => {
  it('the bench works: one navigation at a time shows the page the address names', async () => {
    const router = await mountShell();
    expect(shownPages()).toEqual(['home']);

    await router.push('/staff');
    await finishAnimations();
    expect(router.currentRoute.value.path).toBe('/staff');
    expect(shownPages()).toEqual(['staff']);

    await router.push('/home');
    await finishAnimations();
    expect(shownPages()).toEqual(['home']);
  });

  it('Home → Staff → Home → Staff tapped mid-slide ends on Staff, the page in the address', async () => {
    const router = await mountShell();

    await router.push('/staff');
    await settle(); // Home → Staff is sliding…
    await router.push('/home');
    await settle(); // …and Staff → Home waits behind it,
    await router.push('/staff'); // when the finger asks for Staff again.
    await finishAnimations();

    expect(router.currentRoute.value.path).toBe('/staff');
    expect(shownPages()).toEqual(['staff']);
  });

  it('Home → Staff → Home tapped mid-slide ends on Home', async () => {
    const router = await mountShell();

    await router.push('/staff');
    await settle();
    await router.push('/home');
    await finishAnimations();

    expect(router.currentRoute.value.path).toBe('/home');
    expect(shownPages()).toEqual(['home']);
  });

  it('a transition that throws is reported and does not freeze the navigations after it', async () => {
    // What a browser gives the page: reportError fires the window `error` event, which is what the
    // shell's error reporter listens to (installErrorReporting). happy-dom does not have it.
    const reportError = vi.fn();
    vi.stubGlobal('reportError', reportError);
    vi.spyOn(console, 'warn').mockImplementation(() => undefined); // Ionic's «no <ion-page>» warning
    const router = await mountShell();

    await router.push('/bare');
    await finishAnimations();
    await router.push('/home');
    await finishAnimations();
    await router.push('/bare'); // Ionic's transition throws on this second visit…
    await finishAnimations();
    expect(reportError).toHaveBeenCalledWith(expect.any(TypeError));

    await router.push('/staff'); // …and the next screen still slides in.
    await finishAnimations();
    expect(shownPages()).toEqual(['staff']);
  });
});
