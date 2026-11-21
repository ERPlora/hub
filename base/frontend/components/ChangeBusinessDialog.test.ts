// «Change business?» beside the pane (BackgroundChrome), asked from the bar inside the installed app (ERPlora/app,
// HUB_APP-F04): the Hub's own confirmation dialog. Cancelling does nothing. Confirming waits in the dialog while the
// session of this hub closes, and only then the app is asked to forget the hub; a sign-out that fails says so in the
// dialog and forgets nothing.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { outOfTheApp } from '../__tests__/app-download';
import { flush, mountBase } from '../__tests__/mount-base';
import { askChangeBusiness, changeBusinessOpen } from '../lib/change-business';
import ChangeBusinessDialog from './ChangeBusinessDialog.vue';

type TauriWindow = { __TAURI__?: { core: { invoke: (command: string, args?: unknown) => Promise<unknown> } } };

let steps: string[];
let invoke: ReturnType<typeof vi.fn<(command: string, args?: unknown) => Promise<unknown>>>;
let answerSignOut: (response: Response) => void;

const inDoc = (testid: string) => document.querySelector<HTMLElement>(`[data-testid="${testid}"]`);

const CONFIG = { csrfCookieName: 'csrftoken', csrfHeader: 'X-CSRFToken', lang: 'es', deviceIdStorageKey: 'erplora.device' };

beforeEach(() => {
  document.head.insertAdjacentHTML('beforeend', `<script id="spa-config" type="application/json">${JSON.stringify(CONFIG)}</script>`);
  steps = [];
  invoke = vi.fn(async (command: string, args?: unknown) => {
    steps.push(`${command} ${JSON.stringify(args)}`);
    return undefined;
  });
  (window as TauriWindow).__TAURI__ = { core: { invoke } };
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string) => {
      steps.push(`POST ${path}`);
      return new Promise<Response>((resolve) => (answerSignOut = resolve));
    }),
  );
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  outOfTheApp();
  changeBusinessOpen.value = false;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.getElementById('spa-config')?.remove();
  document.body.innerHTML = '';
});

async function opened(locale: 'en' | 'es' = 'es') {
  await mountBase(ChangeBusinessDialog, { locale });
  await flush();
  // Closed, the modal paints none of its content.
  expect(inDoc('change-business-dialog-submit')).toBeNull();
  askChangeBusiness();
  await flush();
}

describe('ChangeBusinessDialog', () => {
  it('asks «¿Cambiar de negocio?» with what happens, «Cambiar» and «Cancelar»', async () => {
    await opened('es');
    const dialog = inDoc('change-business-dialog')!;
    expect(dialog.textContent).toContain('¿Cambiar de negocio?');
    expect(dialog.textContent).toContain(
      'Se cerrará tu sesión en este negocio y verás la lista de tus negocios para elegir otro.',
    );
    expect(inDoc('change-business-dialog-submit')?.textContent?.trim()).toBe('Cambiar');
    expect(inDoc('change-business-dialog-cancel')?.textContent?.trim()).toBe('Cancelar');
  });

  it('asks in English too', async () => {
    await opened('en');
    const dialog = inDoc('change-business-dialog')!;
    expect(dialog.textContent).toContain('Change business?');
    expect(dialog.textContent).toContain(
      'You will be signed out of this business and see the list of your businesses to choose another.',
    );
    expect(inDoc('change-business-dialog-submit')?.textContent?.trim()).toBe('Change');
  });

  it('cancelled, closes and asks nothing of the hub or the app', async () => {
    await opened();
    inDoc('change-business-dialog-cancel')!.click();
    await flush();
    expect(changeBusinessOpen.value).toBe(false);
    expect(steps).toEqual([]);
  });

  it('confirmed, waits in the dialog while the session closes, and only then asks the app to forget the hub', async () => {
    await opened();
    inDoc('change-business-dialog-submit')!.click();
    await flush();
    expect(steps).toEqual(['POST /auth/logout']);
    expect(inDoc('change-business-dialog-submit')?.hasAttribute('disabled')).toBe(true);

    answerSignOut({ type: 'opaqueredirect', status: 0, ok: false } as Response);
    await flush();
    await flush();
    expect(steps).toEqual(['POST /auth/logout', 'forget_hub {"choose":true}']);
  });

  it('when the sign-out fails, says so in the dialog, forgets nothing and lets the person try again', async () => {
    await opened();
    inDoc('change-business-dialog-submit')!.click();
    await flush();
    answerSignOut({ type: 'basic', status: 500, ok: false } as Response);
    await flush();
    await flush();

    expect(inDoc('change-business-dialog-error')?.textContent).toContain(
      'No se ha podido cerrar la sesión en este negocio. Comprueba la conexión e inténtalo de nuevo.',
    );
    expect(invoke).not.toHaveBeenCalled();
    expect(changeBusinessOpen.value).toBe(true);
    expect(inDoc('change-business-dialog-submit')?.hasAttribute('disabled')).toBe(false);
  });

  it('asked again after a failure and a cancel, starts without the old failure', async () => {
    await opened();
    inDoc('change-business-dialog-submit')!.click();
    await flush();
    answerSignOut({ type: 'basic', status: 500, ok: false } as Response);
    await flush();
    await flush();
    expect(inDoc('change-business-dialog-error')).not.toBeNull();

    inDoc('change-business-dialog-cancel')!.click();
    await flush();
    askChangeBusiness();
    await flush();
    expect(inDoc('change-business-dialog-submit')).not.toBeNull();
    expect(inDoc('change-business-dialog-error')).toBeNull();
  });

  it('when the app refuses to forget the hub, says so in the dialog', async () => {
    invoke.mockRejectedValueOnce('io error');
    await opened('en');
    inDoc('change-business-dialog-submit')!.click();
    await flush();
    answerSignOut({ type: 'opaqueredirect', status: 0, ok: false } as Response);
    await flush();
    await flush();

    expect(inDoc('change-business-dialog-error')?.textContent).toContain(
      'You are signed out, but the app could not leave this business. Close the app and open it again.',
    );
  });
});
