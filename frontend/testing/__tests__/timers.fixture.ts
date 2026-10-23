// Not a test of the hub (no `.test.ts`: the suite never collects it): setup.test.ts runs it on its own, with
// the hub's config, and reads how each test ended. Each one ends in the state its name says, and the hub
// setup (frontend/testing/setup.ts) must fail exactly those that leave a real timer armed.
import { mount } from '@vue/test-utils';
import { afterAll, beforeAll, expect, it, vi } from 'vitest';
import { defineComponent, h, onBeforeUnmount, onMounted, ref } from 'vue';

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

it('leaves a real timeout armed', () => {
  setTimeout(() => fired.push('timeout'), 20);
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
