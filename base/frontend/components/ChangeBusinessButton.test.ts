// «Change business» in the bar, only inside the installed app (ERPlora/app, HUB_APP-F04): a browser has no business
// to forget. The question lives beside the pane (ChangeBusinessDialog), so it outlives the «⋮» it is asked from on a
// phone (TopbarChrome.test.ts).
import { afterEach, describe, expect, it, vi } from 'vitest';

import { outOfTheApp } from '../__tests__/app-download';
import { accessibleName, mountBase } from '../__tests__/mount-base';
import { changeBusinessOpen } from '../lib/change-business';
import ChangeBusinessButton from './ChangeBusinessButton.vue';

type TauriWindow = { __TAURI__?: { core: { invoke: (command: string, args?: unknown) => Promise<unknown> } } };

function insideTheApp() {
  const invoke = vi.fn(async () => undefined);
  (window as TauriWindow).__TAURI__ = { core: { invoke } };
  return invoke;
}

afterEach(() => {
  outOfTheApp();
  changeBusinessOpen.value = false;
  vi.unstubAllGlobals();
  document.body.innerHTML = '';
});

describe('ChangeBusinessButton', () => {
  it('is not there in a browser', async () => {
    const m = await mountBase(ChangeBusinessButton);
    expect(m.wrapper.find('[data-testid="change-business-button"]').exists()).toBe(false);
  });

  it('inside the app is an icon named «Cambiar de negocio» that asks the question, asking nothing of the hub yet', async () => {
    const invoke = insideTheApp();
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    const m = await mountBase(ChangeBusinessButton, { locale: 'es' });

    const button = m.wrapper.get('[data-testid="change-business-button"]');
    expect(accessibleName(button.element)).toBe('Cambiar de negocio');
    expect(button.attributes('title')).toBe('Cambiar de negocio');
    expect(button.find('[slot="icon-only"]').exists()).toBe(true);

    await button.trigger('click');
    expect(changeBusinessOpen.value).toBe(true);
    expect(fetch).not.toHaveBeenCalled();
    expect(invoke).not.toHaveBeenCalled();
  });

  it('says «Change business» in English', async () => {
    insideTheApp();
    const m = await mountBase(ChangeBusinessButton, { locale: 'en' });
    expect(accessibleName(m.wrapper.get('[data-testid="change-business-button"]').element)).toBe('Change business');
  });
});
