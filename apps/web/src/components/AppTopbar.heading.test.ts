// @vitest-environment happy-dom
// Every screen of the shell exposes ONE main heading, and there is exactly one of it (hub#794).
//
// The name of the screen was on the toolbar the whole time — visually. `ion-title` paints it as
// ordinary text, so the accessibility tree of `/employees`, `/files`, `/billing`, `/apps`,
// `/system`, `/settings` and every module host read:
//
//     banner
//       generic: Empleados        ← not a heading. Nothing to jump to, nothing to announce.
//     main
//       search, table, …
//
// Somebody navigating by headings — the first thing a screen-reader user does on an unfamiliar
// page — had no landmark at all, on eight of the ten screens. `/dashboard` and `/profile` did have
// one, which is worse than uniformly missing: the pattern looked deliberate.
//
// The fix has to answer TWO things, and the second is why this is not a one-line change: give the
// toolbar title heading semantics, AND not end up with two level-1 headings on the two screens that
// already paint their own. Who knows that is the VIEW, never the toolbar — the same reasoning
// `AppPage` already applies to `setupChecklistOnScreen`. If the toolbar guessed by route, there
// would be two truths about one screen and they would drift apart.
import { describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const { canOpenManagement, isCompactViewport, assistantAvailable } = await vi.hoisted(async () => {
  const { ref } = await import('vue');
  return {
    canOpenManagement: ref(false),
    isCompactViewport: ref(false),
    assistantAvailable: ref(false),
  };
});

vi.mock('../lib/management-link', () => ({ canOpenManagement, openManagement: vi.fn() }));
vi.mock('../lib/viewport', () => ({ isCompactViewport }));
vi.mock('../lib/shell', async () => {
  const { ref } = await import('vue');
  return {
    assistantAvailable,
    toggleAssistant: vi.fn(),
    notificationCount: ref(0),
    isLoading: ref(false),
    railCollapsed: ref(false),
  };
});
vi.mock('../lib/nav', async () => {
  const { ref } = await import('vue');
  return { moduleNav: ref([]), moduleNavState: ref('ready'), refreshModuleNav: vi.fn() };
});
vi.mock('../lib/icons', () => ({ resolveIcon: (name: string) => name }));
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn(), back: vi.fn() }) }));

import AppTopbar from './AppTopbar.vue';
import enCatalogue from '../i18n/locales/en';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: enCatalogue },
});

function mountTopbar(props: Record<string, unknown>) {
  return mount(AppTopbar, {
    props: { title: 'Employees', ...props },
    global: { plugins: [i18n] },
  });
}

const title = (w: ReturnType<typeof mountTopbar>) => w.find('ion-title');

describe('the toolbar title is the page heading', () => {
  it('announces itself as the level-1 heading of the screen', () => {
    const el = title(mountTopbar({}));

    expect(el.exists()).toBe(true);
    expect(el.attributes('role')).toBe('heading');
    expect(el.attributes('aria-level')).toBe('1');
    // Same words the eye reads. A heading that says something else is a second title.
    expect(el.text()).toBe('Employees');
  });

  it('steps aside when the screen already paints its own heading', () => {
    // `/dashboard` greets with the business name and `/profile` with the person's name — both real
    // `<h1>`s in the content. Two level-1 headings on one screen is the defect this issue forbids
    // in the same breath as it asks for the first one.
    const el = title(mountTopbar({ titleIsHeading: false }));

    expect(el.attributes('role')).toBeUndefined();
    expect(el.attributes('aria-level')).toBeUndefined();
    // And it is still the visible title: nothing about the LOOK changes.
    expect(el.text()).toBe('Employees');
  });

  it('is a heading by default — a screen has to opt OUT, never opt in', () => {
    // The direction of the default is the whole point. Opt-in would have left the eight screens
    // that were broken exactly as broken, waiting for somebody to remember each one.
    expect(title(mountTopbar({})).attributes('aria-level')).toBe('1');
  });
});
