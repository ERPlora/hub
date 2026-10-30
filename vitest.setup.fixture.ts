// Not a test of the hub (no `.test.ts`: the suite never collects it): vitest.setup.test.ts runs it on its own,
// with the hub's config, and reads how each test ended. Each one ends in the state its name says, and the hub
// setup (vitest.setup.ts) must fail exactly those that leave a real timer armed, and paint the shell's icons as the
// app does and attach Ionic's elements as a browser would; base's setup file (assistant.setup.ts) configures the
// assistant as the Hub boots it.
import { IonButton, IonIcon, IonToggle } from '@ionic/vue';
import { mount } from '@vue/test-utils';
import { afterAll, beforeAll, expect, it, vi } from 'vitest';
import { defineComponent, h, onBeforeUnmount, onMounted, ref } from 'vue';

import { assistantConfig } from './packages/ui/src/components/Assistant/config';

const MINUTE = 60_000;

/** What a real timer a failed test left armed did when it fired (it must never fire). */
const fired: string[] = [];

/** A component that arms a timer when mounted and, with `clears`, clears it when unmounted, as AppPage does. */
const Ticking = defineComponent({
  props: { clears: { type: Boolean, default: false } },
  setup(props) {
    let timer: ReturnType<typeof setTimeout> | undefined;
    onMounted(() => {
      timer = setTimeout(() => fired.push('ticking'), MINUTE);
    });
    onBeforeUnmount(() => {
      if (props.clears) clearTimeout(timer);
    });
    return () => h('p', 'ticking');
  },
});

/** An element that holds a timer while it is on the page, as Ionic's do. */
class TimerHolder extends HTMLElement {
  private timer: ReturnType<typeof setTimeout> | undefined;
  connectedCallback(): void {
    this.timer = setTimeout(() => fired.push('holder'), MINUTE);
  }
  disconnectedCallback(): void {
    clearTimeout(this.timer);
  }
}
customElements.define('timer-holder', TimerHolder);

/** An element whose removal sets off a short timer of its own, which runs right after. */
class Farewell extends HTMLElement {
  disconnectedCallback(): void {
    setTimeout(() => fired.push('farewell'), 0);
  }
}
customElements.define('timer-farewell', Farewell);

/** A timer the file holds across its tests, cleared after them: no test's. */
let fileTimer: ReturnType<typeof setTimeout> | undefined;
beforeAll(() => {
  fileTimer = setTimeout(() => fired.push('file'), MINUTE);
});
afterAll(() => clearTimeout(fileTimer));

it('arms nothing while the file holds a timer of its own', () => {
  expect(fileTimer).toBeDefined();
});

// 0 ms, the worst case: it would run in the first tick after the test, while the setup leaves the page; caught then, a
// timer of any delay is (on a loaded machine the 20 ms this had ran before it was counted, and into the next test).
it('leaves a real timeout armed', () => {
  setTimeout(() => fired.push('timeout'), 0);
});

it('never runs the timeout the failed test before it left', async () => {
  await new Promise((resolve) => setTimeout(resolve, 60));
  expect(fired).toEqual([]);
});

it('clears its real timeout', () => {
  clearTimeout(setTimeout(() => fired.push('cleared'), MINUTE));
});

it('lets its real timeout run', async () => {
  await new Promise((resolve) => setTimeout(resolve, 1));
});

it('leaves a real interval armed', () => {
  setInterval(() => fired.push('interval'), MINUTE);
});

it('clears its real interval', () => {
  clearInterval(setInterval(() => fired.push('cleared interval'), MINUTE));
});

it('clears a real timeout it keeps in reactive state', () => {
  // Vue hands back a proxy of Node's timer object, which clears the timer all the same.
  const state = ref({ timer: setTimeout(() => fired.push('reactive'), MINUTE) });
  clearTimeout(state.value.timer);
});

it('leaves a timeout armed on fake timers', () => {
  vi.useFakeTimers();
  setTimeout(() => fired.push('fake'), MINUTE);
  vi.useRealTimers();
});

it('leaves mounted a component that clears its timer when unmounted', () => {
  mount(Ticking, { props: { clears: true } });
});

it('leaves mounted a component that never clears its timer', () => {
  mount(Ticking);
});

it('leaves on the page an element that clears its timer when removed', () => {
  document.body.append(document.createElement('timer-holder'));
});

it('leaves on the page an element whose removal sets off a short timer', () => {
  document.body.append(document.createElement('timer-farewell'));
});

/** The «Could not load icon» warnings `ion-icon` gives while `paint` runs and the element connects. */
async function iconWarnings(paint: () => void): Promise<string[]> {
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  try {
    paint();
    for (let i = 0; i < 3; i++) await new Promise((resolve) => setTimeout(resolve, 0));
    return warn.mock.calls.map(([message]) => String(message)).filter((message) => message.includes('Could not load icon'));
  } finally {
    warn.mockRestore();
  }
}

it('paints an icon the shell registers without a warning', async () => {
  expect(await iconWarnings(() => mount(IonIcon, { props: { name: 'backspace-outline' }, attachTo: document.body }))).toEqual([]);
});

it('warns about an icon the shell does not register', async () => {
  const warnings = await iconWarnings(() => mount(IonIcon, { props: { name: 'no-such-icon-outline' }, attachTo: document.body }));
  // ion-icon tries each time it loads (connecting, then rendering): one warning or more, all about that name.
  expect(warnings.length).toBeGreaterThan(0);
  expect(warnings.filter((warning) => !warning.includes('"no-such-icon-outline"'))).toEqual([]);
});

it('attaches Ionic elements without the errors happy-dom alone makes them log', async () => {
  const error = vi.spyOn(console, 'error').mockImplementation(() => {});
  try {
    // A button adopts its style sheet (`replaceSync`); a toggle reads the page's direction (`document.dir`).
    mount(() => [h(IonButton, () => 'Save'), h(IonToggle, () => 'Dark')], { attachTo: document.body });
    for (let i = 0; i < 3; i++) await new Promise((resolve) => setTimeout(resolve, 0));
    expect(error.mock.calls.map(([first]) => String(first))).toEqual([]);
  } finally {
    error.mockRestore();
  }
});

it('finds the assistant configured as the Hub boots it', () => {
  const config = assistantConfig();
  expect(config.turnUrl).toBe('/api/assistant/turn');
  expect(config.verbKey?.('sale.ticket.void')).toBe('base.assistant.card.actions.void');
});
