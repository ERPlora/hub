import { afterEach, describe, expect, it, vi } from 'vitest';

import { accessibleName, flush, help, mountBase } from '../__tests__/mount-base';
import { embedHubHome, forgetHubHome } from '../__tests__/hub-home';
import HelpEntry from './HelpEntry.vue';
import HelpWindow from './HelpWindow.vue';

vi.mock('@ionic/vue', async (importOriginal) => (await import('../__tests__/modal')).mockIonicModal(importOriginal));

afterEach(forgetHubHome);

async function setup(app = 'table', locale: 'en' | 'es' = 'en') {
  embedHubHome({ help_apps: ['table'] });
  document.body.insertAdjacentHTML('beforeend', '<div class="app-topbar"><div slot="end"></div></div>');
  return mountBase(HelpEntry, {
    path: `/${app}/floor-plan`, routes: [`/${app}/floor-plan`], app, locale,
    onApi: () => Response.json(help),
  });
}

describe('HelpEntry', () => {
  const buttonInDoc = () => document.querySelector<HTMLElement>('[data-testid="help-button"]')!;

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

  it('opens the window for the current app', async () => {
    const m = await setup();
    buttonInDoc().click();
    await flush();
    expect(m.wrapper.getComponent(HelpWindow).props('app')).toBe('table');
    expect(document.querySelector('[data-testid="help-window"]')).not.toBeNull();
    expect(m.net.api.some((call) => call.url.includes('/api/help?app=table'))).toBe(true);
  });
});
