// @vitest-environment happy-dom
// The answer still ARRIVING when the thread is taken away (hub#1544).
//
// `clearAssistantHistory()` is what the PIN hand-over (`switchUser`, user-switch.ts) and `logout()`
// call: it replaces the thread. The stream answering the previous person does not die with the
// array — `streamAssistant` keeps running its rounds, and every tool call and every next round
// goes out through `runtimeHeaders()`, i.e. through WHOEVER holds the session when that call is
// made. Left running across a hand-over, the previous person's turn would present ITS write-confirm
// card to the cashier who just arrived, execute the action under HER session, re-send the previous
// person's conversation under her headers, and keep the composer locked until an answer landed in a
// bubble nobody can see any more. So the drawer cuts the stream the moment its thread is replaced.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { IonTextarea } from '@ionic/vue';

import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

vi.mock('../lib/shell', async () => {
  const { ref } = await import('vue');
  return {
    assistantOpen: ref(false),
    assistantIntent: ref(null),
    closeAssistant: vi.fn(),
  };
});

vi.mock('../lib/session', async () => {
  const { ref } = await import('vue');
  return { isAdmin: ref(true) };
});

vi.mock('../lib/assistant-plan', () => ({
  assistantPlan: vi.fn(),
  startAssistantCheckout: vi.fn(),
}));

vi.mock('../lib/assistant', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  streamAssistant: vi.fn(() => () => {}),
}));

vi.mock('../lib/runtime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getClient: () => ({ query: vi.fn(async () => []), command: vi.fn(async () => ({})) }),
}));

vi.mock('../lib/toast', () => ({ toastSuccess: vi.fn(), toastError: vi.fn() }));
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('../lib/nav', async () => {
  const { ref } = await import('vue');
  return { moduleNav: ref([]) };
});
vi.mock('vue-router', () => ({ useRouter: () => ({ getRoutes: () => [], push: vi.fn() }) }));

// NOT mocked on purpose: `assistant-history` is the store whose replacement the drawer has to
// notice, and the hand-over route calls the real `clearAssistantHistory` — so does this test.
import AssistantDrawer from './AssistantDrawer.vue';
import { assistantOpen } from '../lib/shell';
import { streamAssistant, type StreamCallbacks } from '../lib/assistant';
import { assistantMessages, clearAssistantHistory } from '../lib/assistant-history';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en, es },
});

/** Where the thread is persisted (assistant-history.ts) — re-declared so a rename is deliberate. */
const ASSISTANT_SS_KEY = 'erplora.assistant.history';

function mountOpenDrawer() {
  const wrapper = mount(AssistantDrawer, { global: { plugins: [i18n] } });
  (assistantOpen as unknown as { value: boolean }).value = true;
  return wrapper;
}

/** The stop button is only rendered while an answer is arriving (`v-if="!streaming"` / `v-else`). */
function stopButton(wrapper: ReturnType<typeof mountOpenDrawer>) {
  return wrapper.find(`ion-button[aria-label="${en.assistant.stop}"]`);
}

beforeEach(() => {
  vi.clearAllMocks();
  (assistantOpen as unknown as { value: boolean }).value = false;
  // Set straight, never through `clearAssistantHistory()`: that call is what the test is about.
  assistantMessages.value = [];
  sessionStorage.clear();
});

describe('hub#1544 — the answer still arriving leaves with the thread', () => {
  it('cuts the stream and frees the composer the moment the thread is taken away', async () => {
    const abort = vi.fn();
    let callbacks: StreamCallbacks | null = null;
    vi.mocked(streamAssistant).mockImplementation(((_msgs: unknown, cb: StreamCallbacks) => {
      callbacks = cb;
      return abort;
    }) as never);

    const wrapper = mountOpenDrawer();
    await flushPromises();
    wrapper
      .findComponent(IonTextarea)
      .vm.$emit('update:modelValue', 'Create a 10% discount on every haircut');
    await flushPromises();
    await wrapper.find(`ion-button[aria-label="${en.assistant.send}"]`).trigger('click');
    await flushPromises();
    callbacks!.onToken?.('Sure — I will ');
    await flushPromises();

    // The positive first: an answer IS arriving. The question and the live bubble are on the
    // thread, the composer is locked behind the stop button, and nothing has been aborted.
    expect(assistantMessages.value).toHaveLength(2);
    expect(stopButton(wrapper).exists()).toBe(true);
    expect(wrapper.findComponent(IonTextarea).props('disabled')).toBe(true);
    expect(abort).not.toHaveBeenCalled();

    // The hand-over: exactly the call `switchUser` makes (and `logout()`, by another route).
    clearAssistantHistory();
    await flushPromises();

    // The stream is cut — no tool call, no confirm card and no next round under the new session —
    // and the person who just arrived gets a composer she can type into, on an empty thread.
    expect(abort).toHaveBeenCalledTimes(1);
    expect(stopButton(wrapper).exists()).toBe(false);
    expect(wrapper.find(`ion-button[aria-label="${en.assistant.send}"]`).exists()).toBe(true);
    expect(wrapper.findComponent(IonTextarea).props('disabled')).toBe(false);
    expect(assistantMessages.value).toEqual([]);
    // Cutting the stream is not a turn ending: nothing gets re-saved over the key the hand-over
    // just removed, so a reload on the next shift still finds no thread at all.
    expect(sessionStorage.getItem(ASSISTANT_SS_KEY)).toBeNull();
  });
});
