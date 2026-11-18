import { afterEach, describe, expect, it, vi } from 'vitest';

import type { AppHelp } from '../operations-help';
import { accessibleName, flush, mountBase } from '../__tests__/mount-base';
import { embedHubHome, forgetHubHome } from '../__tests__/hub-home';
import HelpEntry from './HelpEntry.vue';
import HelpWindow from './HelpWindow.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const help: AppHelp = {
  app: 'table', name: 'Tables', language: 'en', video: null, purpose: 'Purpose',
  screens: [{ id: 'floor', title: 'Floor plan', path: '/table/floor-plan', text: 'Floor' }], flows: [],
};

afterEach(forgetHubHome);

async function setup(app = 'table', locale: 'en' | 'es' = 'en') {
  embedHubHome({ help_apps: ['table'] });
  return mountBase(HelpEntry, {
    path: `/${app}/floor-plan`, routes: [`/${app}/floor-plan`], app, locale,
    onApi: () => Response.json(help),
  });
}

describe('HelpEntry', () => {
  it('shows an icon-only named button only when the current app has help', async () => {
    const ready = await setup('table');
    const button = ready.wrapper.get('[data-testid="help-button"]');
    expect(accessibleName(button.element)).toBe('Help');
    expect(button.find('ion-icon').attributes('name')).toBe('help-circle-outline');
    expect(button.text()).toBe('');
    ready.wrapper.unmount();

    const notReady = await setup('demo');
    expect(notReady.wrapper.find('[data-testid="help-button"]').exists()).toBe(false);
    expect(notReady.wrapper.findComponent(HelpWindow).exists()).toBe(false);
  });

  it('uses the Spanish accessible name', async () => {
    const m = await setup('table', 'es');
    expect(accessibleName(m.wrapper.get('[data-testid="help-button"]').element)).toBe('Ayuda');
  });

  it('opens the window for the current app', async () => {
    const m = await setup();
    await m.wrapper.get('[data-testid="help-button"]').trigger('click');
    await flush();
    expect(m.wrapper.getComponent(HelpWindow).props('app')).toBe('table');
    expect(document.querySelector('[data-testid="help-window"]')).not.toBeNull();
    expect(m.net.api.some((call) => call.url.includes('/api/help?app=table'))).toBe(true);
  });
});
