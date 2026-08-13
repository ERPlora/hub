// @vitest-environment happy-dom
// hub#447 — «switch business», the user's own door out of the ONE hub the installed app remembers.
//
// `forget_hub` existed and was only ever fired by a Cloud 410; `/shell/?choose=1` existed and
// nobody called it. What was missing is literally this button. The rules under test:
//
//   - **It exists only where it means something.** In a browser there is no capture to forget —
//     the control renders ONLY inside the installed app (`isTauri`), on both toolbar layouts
//     (wide row and the phone overflow menu, hub#758's sibling rule: nothing lost on the way in).
//   - **It confirms before it acts.** The local session is lost; the click hands the i18n words
//     to `requestChangeHub`, which owns the dialog and only then invokes the shell.
//   - **The words never say "hub".** The reader is the owner of a bar (PLAN step 8): both
//     catalogues speak of the business.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const { canChange, requestChangeHub, isCompactViewport } = await vi.hoisted(async () => {
  const { ref } = await import('vue');
  return {
    canChange: ref(true),
    requestChangeHub: vi.fn(async () => true),
    isCompactViewport: ref(false),
  };
});

vi.mock('../lib/change-hub', () => ({
  canChangeHub: () => canChange.value,
  requestChangeHub,
}));
vi.mock('../lib/viewport', () => ({ isCompactViewport }));
vi.mock('../lib/management-link', async () => {
  const { ref } = await import('vue');
  return { canOpenManagement: ref(false), openManagement: vi.fn() };
});
vi.mock('../lib/shell', async () => {
  const { ref } = await import('vue');
  return {
    assistantAvailable: ref(false),
    toggleAssistant: vi.fn(),
    notificationCount: ref(0),
    isLoading: ref(false),
    railCollapsed: ref(false),
  };
});
vi.mock('../lib/nav', async () => {
  const { ref } = await import('vue');
  return { moduleNav: ref([]) };
});
vi.mock('../lib/icons', () => ({ resolveIcon: (name: string) => name }));
vi.mock('./HubIcon.vue', () => ({
  default: { name: 'HubIcon', props: ['name'], template: '<span :data-icon="name" />' },
}));
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn(), back: vi.fn() }) }));

import AppTopbar from './AppTopbar.vue';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const mountTopbar = (locale = 'en') =>
  mount(AppTopbar, {
    props: { title: 'Till' },
    global: {
      plugins: [
        createI18n({
          legacy: false,
          locale,
          missingWarn: false,
          fallbackWarn: false,
          messages: { en, es },
        }),
      ],
    },
  });

const changeButton = (wrapper: ReturnType<typeof mountTopbar>) =>
  wrapper.findAll('ion-button').find((b) => b.attributes('data-testid') === 'topbar-change-hub');

beforeEach(() => {
  requestChangeHub.mockClear();
  canChange.value = true;
  isCompactViewport.value = false;
});

describe('the door to another business (wide toolbar)', () => {
  it('is offered inside the installed app', () => {
    expect(changeButton(mountTopbar())).toBeTruthy();
  });

  it('does not render in a browser — there is no capture to forget there', () => {
    canChange.value = false;

    expect(changeButton(mountTopbar())).toBeFalsy();
  });

  it('hands the confirmation (and only then the switch) to requestChangeHub, with i18n words', async () => {
    await changeButton(mountTopbar())!.trigger('click');

    expect(requestChangeHub).toHaveBeenCalledTimes(1);
    const labels = (requestChangeHub.mock.calls[0] as unknown[])[0] as Record<string, string>;
    expect(labels.header).toBe(en.shell.changeHubTitle);
    expect(labels.message).toBe(en.shell.changeHubBody);
    expect(labels.cancel).toBe(en.shell.changeHubCancel);
    expect(labels.confirm).toBe(en.shell.changeHubConfirm);
  });

  it('names itself for a screen reader — icon-only actions have nothing else', () => {
    const button = changeButton(mountTopbar())!;

    expect(button.attributes('aria-label')).toBe(en.shell.changeHub);
    expect(button.attributes('title')).toBe(en.shell.changeHub);
  });
});

describe('on a phone the action folds into the overflow menu, not away', () => {
  it('is a row of the menu inside the installed app', () => {
    isCompactViewport.value = true;
    const wrapper = mountTopbar();

    const row = wrapper
      .findAll('ion-item')
      .find((i) => i.attributes('data-testid') === 'topbar-more-change-hub');
    expect(row).toBeTruthy();
  });

  it('is absent from the menu in a browser', () => {
    isCompactViewport.value = true;
    canChange.value = false;

    const row = mountTopbar()
      .findAll('ion-item')
      .find((i) => i.attributes('data-testid') === 'topbar-more-change-hub');
    expect(row).toBeFalsy();
  });
});

describe('the catalogues', () => {
  it('speak of the business, never of a hub — the reader owns a bar, not an architecture', () => {
    for (const copy of [
      en.shell.changeHub,
      en.shell.changeHubTitle,
      en.shell.changeHubBody,
      es.shell.changeHub,
      es.shell.changeHubTitle,
      es.shell.changeHubBody,
    ]) {
      expect(copy.toLowerCase()).not.toContain('hub');
    }
  });

  it('warn that this device signs out — the consequence the confirmation exists for', () => {
    expect(en.shell.changeHubBody.toLowerCase()).toContain('sign');
    expect(es.shell.changeHubBody.toLowerCase()).toContain('sesión');
  });
});
