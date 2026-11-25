import { afterEach, describe, expect, it, vi } from 'vitest';

import type { SessionMe } from '@erplora/ui/shell';
import type { RouteMeta } from 'vue-router';

import { accessibleName, EMPLOYEE, flush, help, mountBase } from '../__tests__/mount-base';
import { embedHubHome, forgetHubHome } from '../__tests__/hub-home';
import HelpEntry from './HelpEntry.vue';
import HelpWindow from './HelpWindow.vue';

afterEach(() => {
  vi.restoreAllMocks();
  forgetHubHome();
  document.body.innerHTML = '';
});

function topbar(): void {
  document.body.insertAdjacentHTML('beforeend', '<div class="app-topbar"><div slot="end"></div></div>');
}

async function setup(app = 'table', locale: 'en' | 'es' = 'en', session: SessionMe = EMPLOYEE) {
  embedHubHome({ help_apps: ['table'] });
  topbar();
  return mountBase(HelpEntry, {
    path: `/${app}/floor-plan`, routes: [`/${app}/floor-plan`], app, locale, session,
    onApi: () => Response.json(help),
  });
}

interface PlatformOptions {
  helpApps?: string[];
  locale?: 'en' | 'es';
}

async function setupPlatform(path: string, meta: RouteMeta, options: PlatformOptions = {}) {
  topbar();
  return mountPlatform(path, meta, options);
}

/** On a screen of the Hub, in the pages the test put in the document. */
const setupOn = (path: string) => mountPlatform(path, { auth: true, help: true });

async function mountPlatform(path: string, meta: RouteMeta, options: PlatformOptions = {}) {
  embedHubHome({ help_apps: options.helpApps ?? ['base'] });
  return mountBase(HelpEntry, {
    path, routes: [path], meta, locale: options.locale,
    onApi: () => Response.json({ ...help, app: 'base', name: 'ERPlora' }),
  });
}

const buttonInDoc = () => document.querySelector<HTMLElement>('[data-testid="help-button"]')!;

describe('HelpEntry', () => {
  it('shows an icon-only named button only when the current app has help', async () => {
    const ready = await setup('table');
    const button = buttonInDoc();
    expect(accessibleName(button)).toBe('Help');
    expect(button.querySelector('ion-icon')?.getAttribute('name')).toBe('help-circle-outline');
    expect(button.textContent?.trim()).toBe('');
    expect(document.querySelector('[slot="end"]')?.contains(button)).toBe(true);
    ready.wrapper.unmount();

    const notReady = await setup('demo');
    expect(document.querySelector('[data-testid="help-button"]')).toBeNull();
    expect(notReady.wrapper.findComponent(HelpWindow).exists()).toBe(false);
  });

  it('uses the default Ionic topbar colour like the assistant button', async () => {
    await setup();
    expect(buttonInDoc().getAttribute('fill')).toBeNull();
  });

  it('uses the Spanish accessible name', async () => {
    await setup('table', 'es');
    expect(accessibleName(buttonInDoc())).toBe('Ayuda');
  });

  it('is not there for whoever cannot read the help', async () => {
    const m = await setup('table', 'en', { ...EMPLOYEE, permissions: ['table.view'] });
    expect(buttonInDoc()).toBeNull();
    expect(m.wrapper.findComponent(HelpWindow).exists()).toBe(false);
  });

  it('opens the window for the current app', async () => {
    const m = await setup();
    buttonInDoc().click();
    await flush();
    expect(m.wrapper.getComponent(HelpWindow).props('app')).toBe('table');
    expect(document.querySelector('[data-testid="help-window"]')).not.toBeNull();
    expect(m.net.api.some((call) => call.url.includes('/api/help?app=table'))).toBe(true);
  });
});

describe('HelpEntry on the screens of the Hub itself', () => {
  it('is on a screen of the platform that has help and opens the help of the platform', async () => {
    const m = await setupPlatform('/settings', { auth: true, help: true });
    buttonInDoc().click();
    await flush();
    expect(m.wrapper.getComponent(HelpWindow).props()).toMatchObject({ app: 'base', appName: 'ERPlora', open: true });
    expect(m.net.api.some((call) => call.url.includes('/api/help?app=base'))).toBe(true);
  });

  it('is not on a screen of the platform without help', async () => {
    const m = await setupPlatform('/api-docs', { auth: true });
    expect(buttonInDoc()).toBeNull();
    expect(m.wrapper.findComponent(HelpWindow).exists()).toBe(false);
  });

  it('is not there while the platform has no help ready', async () => {
    await setupPlatform('/settings', { auth: true, help: true }, { helpApps: ['table'] });
    expect(buttonInDoc()).toBeNull();
  });

  it('uses the Spanish accessible name', async () => {
    await setupPlatform('/settings', { auth: true, help: true }, { locale: 'es' });
    expect(accessibleName(buttonInDoc())).toBe('Ayuda');
  });
});

describe('HelpEntry in the bar of the page in view', () => {
  const page = (id: string) => {
    document.body.insertAdjacentHTML(
      'beforeend',
      `<div id="${id}" class="ion-page"><div class="app-topbar"><div slot="end"></div></div></div>`,
    );
    return document.getElementById(id)!;
  };
  const enters = async (entered: HTMLElement) => {
    entered.dispatchEvent(new CustomEvent('ionViewDidEnter'));
    await flush();
  };

  it('goes back to the page under the one that leaves, which is still the last in the document', async () => {
    const under = page('under');
    const leaving = page('leaving');
    await setupOn('/settings');
    expect(leaving.contains(buttonInDoc())).toBe(true);
    await enters(under);
    expect(under.contains(buttonInDoc())).toBe(true);
    leaving.remove();
    expect(buttonInDoc()).not.toBeNull();
  });

  it('stays where it is when what enters is a window, which has no bar', async () => {
    const inView = page('in-view');
    await setupOn('/settings');
    document.body.insertAdjacentHTML('beforeend', '<ion-modal><div id="window-content"><div slot="end"></div></div></ion-modal>');
    await enters(document.getElementById('window-content')!);
    expect(inView.contains(buttonInDoc())).toBe(true);
  });

  it('stops following the pages once it is gone', async () => {
    const listened = vi.spyOn(document, 'addEventListener');
    const removed = vi.spyOn(document, 'removeEventListener');
    const m = await setupOn('/settings');
    const follows = listened.mock.calls.find(([event]) => event === 'ionViewDidEnter');
    m.wrapper.unmount();
    expect(follows).toBeDefined();
    expect(removed).toHaveBeenCalledWith(...follows!);
  });
});
