// @vitest-environment happy-dom
// hub#2204 — three faults of the assistant panel, seen while recording the functional manual:
//   1. the answer showed «→ Ve a: [Ajustes de facturación](/m/invoice/settings)» literally;
//   2. the «Go to» buttons read «Cash_register › settings» — the module id and the raw tab id;
//   3. opened from the topbar icon, the panel offered no suggestion at all: the chips only showed
//      when the chat was opened from «Ask the assistant» on Home.
//
// The SFC is mounted for real (same criterion as assistant-unavailable-message.test.ts): an
// assertion on the source cannot tell «painted» from «written in the template and never rendered».
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const { push, query } = vi.hoisted(() => ({
  push: vi.fn(),
  query: vi.fn(async () => [] as unknown),
}));

vi.mock('../lib/shell', async () => {
  const { ref } = await import('vue');
  return { assistantOpen: ref(false), assistantIntent: ref(null), closeAssistant: vi.fn() };
});
vi.mock('../lib/session', async () => {
  const { ref } = await import('vue');
  return { isAdmin: ref(true) };
});
vi.mock('../lib/assistant-plan', () => ({
  assistantPlan: vi.fn(async () => null),
  startAssistantCheckout: vi.fn(),
}));
vi.mock('../lib/assistant', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  streamAssistant: vi.fn(() => () => {}),
}));
vi.mock('../lib/runtime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getClient: () => ({ query, command: vi.fn(async () => ({})) }),
}));
vi.mock('../lib/toast', () => ({ toastSuccess: vi.fn(), toastError: vi.fn() }));
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('../lib/nav', async () => {
  const { ref } = await import('vue');
  return {
    moduleNav: ref([
      { path: '/m/cash_register', label: 'Till', icon: '', tabs: [{ id: 'sessions', label: 'Sessions' }] },
      { path: '/m/invoice', label: 'Invoicing', icon: '', tabs: [] },
    ]),
  };
});
vi.mock('vue-router', () => ({
  useRouter: () => ({ getRoutes: () => [{ path: '/employees' }], push }),
}));

import AssistantDrawer from './AssistantDrawer.vue';
import { assistantOpen } from '../lib/shell';
import { assistantMessages } from '../lib/assistant-history';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en, es },
});

/** What the owner reads: the painted text, tags stripped (data-testids hold raw routes). */
function painted(html: string): string {
  return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ');
}

async function drawerWithAnswer(answer: string) {
  assistantMessages.value = [
    { role: 'user', content: 'How do I set up invoicing?' },
    { role: 'assistant', content: answer },
  ];
  const wrapper = mount(AssistantDrawer, { global: { plugins: [i18n] } });
  (assistantOpen as unknown as { value: boolean }).value = true;
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  vi.clearAllMocks();
  query.mockImplementation(async () => []);
  (assistantOpen as unknown as { value: boolean }).value = false;
  assistantMessages.value = [];
});

describe('hub#2204 · 1 — a Markdown link is read as a link', () => {
  it('the owner reads the label, not the brackets, the parentheses or the path', async () => {
    const wrapper = await drawerWithAnswer('→ Go to: [Invoicing settings](/m/invoice/settings)');
    const bubble = painted(wrapper.find('[data-testid="assistant-message-1"] .chat-md').html());

    expect(bubble).toContain('Invoicing settings');
    expect(bubble).not.toContain('](');
    expect(bubble).not.toContain('[');
    expect(bubble).not.toContain('/m/invoice/settings');
  });

  it('clicking the link takes the owner to that screen', async () => {
    const wrapper = await drawerWithAnswer('→ Go to: [Invoicing settings](/m/invoice/settings)');
    const click = new MouseEvent('click', { bubbles: true, cancelable: true });
    wrapper.find('[data-testid="assistant-message-1"] .chat-md .md-link').element.dispatchEvent(click);

    expect(push).toHaveBeenCalledWith('/m/invoice/settings');
    // The router moves; the browser must not also follow the href and reload the whole hub.
    expect(click.defaultPrevented).toBe(true);
  });

  // The whole target has to be a screen: a web address that merely CARRIES a screen path in its
  // query is still an outside address, and a click on it would leave the hub.
  it('a web address carrying a screen path is still outside the hub, never a link', async () => {
    const wrapper = await drawerWithAnswer('Open [Settings](https://evil.example/?next=/settings) now.');

    expect(wrapper.find('[data-testid="assistant-message-1"] .chat-md .md-link').exists()).toBe(false);
    expect(wrapper.find('[data-testid="assistant-message-1"] .chat-md a').exists()).toBe(false);
  });

  it('a bare path in the prose is named like the screen, not printed', async () => {
    const wrapper = await drawerWithAnswer('Open /m/cash_register/sessions to count the drawer.');
    const bubble = painted(wrapper.find('[data-testid="assistant-message-1"] .chat-md').html());

    expect(bubble).toContain('Till › Sessions');
    expect(bubble).not.toContain('/m/cash_register');
  });

  // A screen the audit could not find in this hub (hub#1048) is never offered as a way in —
  // neither as a button nor as a link in the text.
  it('an external or unknown target is plain text, never a link', async () => {
    const wrapper = await drawerWithAnswer('See [the docs](https://evil.example/login) now.');

    expect(wrapper.find('[data-testid="assistant-message-1"] .chat-md .md-link').exists()).toBe(false);
    expect(painted(wrapper.find('[data-testid="assistant-message-1"] .chat-md').html())).toContain('the docs');
  });

  it('a screen the audit could not find in this hub is plain text, never a link', async () => {
    assistantMessages.value = [
      { role: 'user', content: 'Where do I set up the loyalty card?' },
      {
        role: 'assistant',
        content: 'Go to [Loyalty](/m/loyalty/settings).',
        grounding: { claimedWithoutEffect: false, unsourcedIds: [], unknownRoutes: ['/m/loyalty/settings'] },
      },
    ];
    const wrapper = mount(AssistantDrawer, { global: { plugins: [i18n] } });
    (assistantOpen as unknown as { value: boolean }).value = true;
    await flushPromises();

    expect(wrapper.find('[data-testid="assistant-message-1"] .chat-md .md-link').exists()).toBe(false);
    expect(painted(wrapper.find('[data-testid="assistant-message-1"] .chat-md').html())).toContain('Loyalty');
  });
});

describe('hub#2204 · 2 — the «Go to» buttons name the app and the screen', () => {
  it('«Go to Till › Settings», never «Cash_register › settings»', async () => {
    const wrapper = await drawerWithAnswer('You can do it in /m/cash_register/settings');
    const button = wrapper.find('[data-testid="assistant-goto-/m/cash_register/settings"]');

    expect(button.exists()).toBe(true);
    expect(painted(button.html()).trim()).toBe(`${en.assistant.goTo} Till › ${en.moduleSettings.tab}`);
  });
});

describe('hub#2204 · 3 — the same suggestions however the panel is opened', () => {
  it('opened from the topbar (no intent) the empty panel offers the starter suggestions', async () => {
    const wrapper = mount(AssistantDrawer, { global: { plugins: [i18n] } });
    (assistantOpen as unknown as { value: boolean }).value = true;
    await flushPromises();

    expect(wrapper.find('[data-testid="assistant-suggest-missing"]').exists()).toBe(true);
  });

  it('and it reads the checklist on opening, so the per-item chips are there too', async () => {
    query.mockImplementation(async () => [
      {
        items: [{ key: 'core.taxes', state: 'pending', title: 'Taxes', actionable: true }],
        total: 1,
        pending: 1,
        unavailable: 0,
      },
    ]);
    const wrapper = mount(AssistantDrawer, { global: { plugins: [i18n] } });
    (assistantOpen as unknown as { value: boolean }).value = true;
    await flushPromises();

    expect(query).toHaveBeenCalledWith('hub.setup.status');
    expect(wrapper.find('[data-testid="assistant-suggest-core.taxes"]').exists()).toBe(true);
  });
});
