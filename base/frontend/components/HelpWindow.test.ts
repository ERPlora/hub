import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { createAssistant, installAssistant, useAssistant } from '@erplora/ui/components';

import type { AppHelp } from '../operations-help';
import { EMPLOYEE, flush, help, memoryStorage, mountBase } from '../__tests__/mount-base';
import { resetHelpCache } from '../lib/help';
import HelpContent from './HelpContent.vue';
import HelpWindow from './HelpWindow.vue';

interface SetupOptions {
  app?: string;
  answer?: AppHelp;
  onApi?: () => Response | Promise<Response>;
  session?: typeof EMPLOYEE;
  path?: string;
}

async function setup(options: SetupOptions = {}) {
  const app = options.app ?? 'table';
  const answer = options.answer ?? help;
  const m = await mountBase(HelpWindow, {
    path: options.path ?? '/table/floor-plan', routes: ['/table/floor-plan', '/table/floor-plan/:table', '/table/settings'],
    props: { open: true, app, appName: answer.name, icon: 'ion:grid-outline' },
    session: options.session,
    onApi: options.onApi ?? (() => Response.json(answer)),
  });
  await flush();
  const el = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  async function ask(): Promise<void> {
    el('help-ask-assistant')!.click();
    await flush();
  }
  async function reopen(): Promise<void> {
    await m.wrapper.setProps({ open: false });
    await m.wrapper.setProps({ open: true });
    await flush();
  }
  return { ...m, el, ask, reopen };
}

async function askFromSales(changeDraft?: (draft: string) => string): Promise<void> {
  const table = await setup();
  await table.ask();
  if (changeDraft) useAssistant().state.draft = changeDraft(useAssistant().state.draft);
  table.wrapper.unmount();

  const sale = await setup({ app: 'sale', answer: { ...help, app: 'sale', name: 'Sales' } });
  await sale.ask();
}

beforeEach(() => {
  resetHelpCache();
  installAssistant(createAssistant({ storage: memoryStorage(), openStorage: memoryStorage(), post: async () => undefined }));
});

afterEach(() => installAssistant(undefined));

describe('HelpWindow', () => {
  it('uses the large read-only sheet contract and resolves the nested current route', async () => {
    const m = await setup();
    const modal = m.wrapper.getComponent({ name: 'FormModal' });
    expect(modal.props()).toMatchObject({ size: 'lg', readonly: true, phoneLayout: 'sheet', title: 'Help · Tables' });
    expect(m.el('help-current-screen')?.textContent).toContain('Floor plan');
    expect(m.el('help-content')?.getAttribute('lang')).toBe('en');
  });

  it("is on a module's screen also at an address below it", async () => {
    const m = await setup({ path: '/table/floor-plan/0190' });
    expect(m.el('help-current-screen')?.textContent).toContain('Floor plan');
  });

  it('puts the app icon before a left-aligned title in the newest dialog', async () => {
    const m = await setup();
    const modal = m.wrapper.getComponent({ name: 'FormModal' });
    expect(modal.vm.$attrs.onWillPresent).toBeTypeOf('function');
    await m.wrapper.setProps({ open: false });
    await flush();
    await m.wrapper.setProps({ open: true });
    await flush();
    const dialogs = [...document.querySelectorAll('[data-testid="help-window"]')];
    const newest = dialogs.at(-1);
    const title = newest?.querySelector('.help-window__title-content');
    expect(title?.getAttribute('aria-hidden')).toBe('true');
    expect(title?.firstElementChild?.classList.contains('help-window__app-icon')).toBe(true);
    expect(title?.querySelector('.help-window__title-text')?.textContent).toBe('Help · Tables');
  });

  it('shows a loading skeleton while the operation is pending', async () => {
    let release: (response: Response) => void = () => undefined;
    const m = await setup({ onApi: () => new Promise<Response>((resolve) => { release = resolve; }) });
    expect(m.el('help-loading')).not.toBeNull();
    expect(m.el('help-loading')?.getAttribute('aria-busy')).toBe('true');
    expect(m.el('help-loading')?.getAttribute('role')).toBe('status');
    expect(m.el('help-loading')?.querySelector('.visually-hidden')?.textContent).toBe('Loading help…');
    expect(document.querySelectorAll('ion-skeleton-text').length).toBeGreaterThan(3);
    release(Response.json(help));
    await flush();
    expect(m.el('help-loading')).toBeNull();
  });

  it('shows the load error and retries without closing', async () => {
    let attempts = 0;
    const m = await setup({ onApi: () => {
      attempts += 1;
      return attempts === 1 ? Response.json({ error: { code: 'offline', message: 'Offline' } }, { status: 503 }) : Response.json(help);
    } });
    expect(m.el('help-error')?.textContent).toContain('Could not load the help.');
    m.el('help-retry')!.click();
    await flush();
    expect(attempts).toBe(2);
    expect(m.el('help-error')).toBeNull();
    expect(m.el('help-content')).not.toBeNull();
  });

  it('writes the last expanded flow as a draft only after dismissal and never sends it', async () => {
    const m = await setup();
    m.el('help-flow-floor-seat')!.click();
    await flush();
    m.el('help-ask-assistant')!.click();
    expect(useAssistant().state.open).toBe(false);
    expect(useAssistant().state.draft).toBe('');
    await flush();
    expect(useAssistant().state.open).toBe(true);
    expect(useAssistant().state.draft).toBe('How do I do this: Seat a party?');
    expect(useAssistant().state.thread.bubbles).toEqual([]);
  });

  it('uses the app and screen for the draft when no flow was expanded', async () => {
    const m = await setup();
    m.el('help-ask-assistant')!.click();
    await flush();
    expect(useAssistant().state.draft).toBe('How do I use Tables on Floor plan?');
  });

  it('hides the assistant action without base.view_home', async () => {
    const m = await setup({ session: { ...EMPLOYEE, permissions: ['demo.view'] } });
    expect(m.el('help-ask-assistant')).toBeNull();
    expect(m.el('help-close')).not.toBeNull();
  });

  it('navigates and closes when markdown emits go', async () => {
    const m = await setup();
    m.wrapper.findComponent(HelpContent).vm.$emit('go', '/table/settings');
    await flush();
    expect(m.router.currentRoute.value.path).toBe('/table/settings');
    expect(m.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('appends the question after a blank line when an assistant draft already exists', async () => {
    const m = await setup();
    useAssistant().state.draft = 'My existing draft';
    m.el('help-ask-assistant')!.click();
    await flush();
    expect(useAssistant().state.draft).toBe('My existing draft\n\nHow do I use Tables on Floor plan?');
  });

  it('keeps one copy when the same help question is requested twice', async () => {
    const m = await setup();
    await m.ask();
    await m.reopen();
    await m.ask();
    expect(useAssistant().state.draft).toBe('How do I use Tables on Floor plan?');
  });

  it('replaces an unedited help question when another module asks', async () => {
    await askFromSales();
    expect(useAssistant().state.draft).toBe('How do I use Sales on Floor plan?');
  });

  it('keeps hand-written text above a replaced help question', async () => {
    await askFromSales((draft) => `My existing draft\n\n${draft}`);
    expect(useAssistant().state.draft).toBe('My existing draft\n\nHow do I use Sales on Floor plan?');
  });

  it('keeps an edited help question and appends the new question below it', async () => {
    await askFromSales((draft) => `${draft} Edited by me.`);
    expect(useAssistant().state.draft).toBe(
      'How do I use Tables on Floor plan? Edited by me.\n\nHow do I use Sales on Floor plan?',
    );
  });

  it('reads from the cache after the whole window has remounted', async () => {
    let requests = 0;
    const first = await setup({ onApi: () => {
      requests += 1;
      return Response.json(help);
    } });
    first.wrapper.unmount();

    const second = await setup({ onApi: () => {
      requests += 1;
      return Response.json({ error: { code: 'offline', message: 'Offline' } }, { status: 503 });
    } });
    expect(second.el('help-content')).not.toBeNull();
    expect(second.el('help-error')).toBeNull();
    expect(requests).toBe(1);
  });
});

describe('HelpWindow on the screens of the Hub itself', () => {
  const platform: AppHelp = {
    ...help,
    app: 'base',
    name: 'ERPlora',
    screens: [
      { id: 'settings_general', title: 'Settings · General', path: '/settings#general', text: 'The general settings.' },
      { id: 'settings_data', title: 'Settings · Data and backups', path: '/settings#data', text: 'The copies.' },
      { id: 'role', title: 'What it allows', path: '/employees/roles/:role', text: 'What a role allows.' },
    ],
    flows: [],
  };

  async function at(path: string, routes: string[], onApi = () => Response.json(platform)) {
    const m = await mountBase(HelpWindow, {
      path, routes, props: { open: true, app: 'base', appName: 'ERPlora', icon: 'ion:help-circle-outline' }, onApi,
    });
    await flush();
    const el = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
    return { ...m, el };
  }

  it('says the tab in view is where the person is, and the rest are the other screens', async () => {
    const m = await at('/settings#data', ['/settings']);
    expect(m.el('help-current-screen')?.textContent).toContain('Settings · Data and backups');
    expect(m.el('help-current-screen')?.textContent).toContain('The copies.');
    expect(m.el('help-other-screen-settings_general')).not.toBeNull();
    expect(m.el('help-other-screen-settings_data')).toBeNull();
  });

  it('follows the tab the person moves to', async () => {
    const m = await at('/settings', ['/settings']);
    expect(m.el('help-current-screen')?.textContent).toContain('Settings · General');
    await m.router.push('/settings#data');
    await flush();
    expect(m.el('help-current-screen')?.textContent).toContain('Settings · Data and backups');
  });

  it('is on a screen whose address carries an id', async () => {
    const m = await at('/employees/roles/0190', ['/employees/roles/:role']);
    expect(m.el('help-current-screen')?.textContent).toContain('What it allows');
  });

  it('titles the other screens without naming a module', async () => {
    const m = await at('/settings', ['/settings']);
    expect(document.querySelector('[data-help-section="screens"] .help-section__title')?.textContent?.trim()).toBe('Other screens');
    expect(document.querySelector('[data-help-section="flows"]')).toBeNull();
    expect(m.el('help-content')).not.toBeNull();
  });

  it('is titled ERPlora while it is read and when it cannot be read, and can be asked for again', async () => {
    const m = await at('/settings', ['/settings'], () =>
      Response.json({ error: { code: 'offline', message: 'Offline' } }, { status: 503 }));
    expect(m.wrapper.getComponent({ name: 'FormModal' }).props('title')).toBe('Help · ERPlora');
    expect(m.el('help-error')?.textContent).toContain('Could not load the help.');
    expect(m.el('help-retry')).not.toBeNull();
  });

  it('asks the assistant about the screen of ERPlora in view', async () => {
    const m = await at('/settings#data', ['/settings']);
    m.el('help-ask-assistant')!.click();
    await flush();
    expect(useAssistant().state.draft).toBe('How do I use ERPlora on Settings · Data and backups?');
  });
});
