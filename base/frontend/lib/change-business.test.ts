// «Change business» inside the installed app (ERPlora/app, HUB_APP-F04): the session of this hub is closed first, then
// what the hub kept on the device is erased, and only then the app is asked to forget the hub (`forget_hub`), which
// opens the list of businesses. A sign-out that fails forgets nothing: the person stays, with the session they had.
// The same way out when the hub answers, while open, that it is gone (HUB_APP-F05), without forcing the list.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const shell = vi.hoisted(() => ({ stopNoticeListening: vi.fn(async () => {}) }));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  stopNoticeListening: shell.stopNoticeListening,
}));

import { PRIMER_ANSWERED_KEY } from '@erplora/ui/shell';

import { memoryStorage } from '../__tests__/mount-base';
import { askChangeBusiness, changeBusiness, changeBusinessOpen, FORGET_HUB_COMMAND, reloadOrForgetGone } from './change-business';

const DEVICE_KEY = 'erplora.device';
const CONFIG = { csrfCookieName: 'csrftoken', csrfHeader: 'X-CSRFToken', lang: 'es', deviceIdStorageKey: DEVICE_KEY };
const REDIRECTED = { type: 'opaqueredirect', status: 0, ok: false } as Response;
const GONE = { type: 'basic', status: 410, ok: false } as Response;
const REFUSED = { type: 'basic', status: 403, ok: false } as Response;

/** What happened, in order: the sign-out's POST, and each command the app was asked for with what the device kept. */
let steps: string[];
let invoke: ReturnType<typeof vi.fn<(command: string, args?: unknown) => Promise<unknown>>>;
let local: Storage;
let session: Storage;
let reload: ReturnType<typeof vi.fn>;

/** A window inside the installed app (its bridge), with its two storages and its reload to look at. */
function appWindow(): Window {
  return { __TAURI__: { core: { invoke } }, document, localStorage: local, sessionStorage: session, location: { reload } } as never;
}

function browserWindow(): Window {
  return { document, localStorage: local, sessionStorage: session, location: { reload } } as never;
}

function signOutAnswers(response: Response | Error): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string) => {
      steps.push(`POST ${path}`);
      if (response instanceof Error) throw response;
      return response;
    }),
  );
}

const kept = (storage: Storage) =>
  Object.fromEntries(Array.from({ length: storage.length }, (_, i) => storage.key(i)!).map((key) => [key, storage.getItem(key)]));

beforeEach(() => {
  document.body.innerHTML = `<script id="spa-config" type="application/json">${JSON.stringify(CONFIG)}</script>`;
  steps = [];
  local = memoryStorage();
  session = memoryStorage();
  local.setItem(DEVICE_KEY, '0190a5c8-0000-7000-8000-000000000001');
  local.setItem(PRIMER_ANSWERED_KEY, '1');
  local.setItem('erplora.sale.pos.currentCheck', 'check-1');
  local.setItem('hub-app-usage', '{"sale":3}');
  session.setItem('erplora.base.switched', 'Ana');
  reload = vi.fn();
  invoke = vi.fn(async (command: string, args?: unknown) => {
    steps.push(`${command} ${JSON.stringify(args)} local=${JSON.stringify(kept(local))} session=${JSON.stringify(kept(session))}`);
    return undefined;
  });
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  changeBusinessOpen.value = false;
  document.body.innerHTML = '';
});

const AFTER_ERASING = `local=${JSON.stringify({ [DEVICE_KEY]: '0190a5c8-0000-7000-8000-000000000001', [PRIMER_ANSWERED_KEY]: '1' })} session={}`;

describe('changeBusiness', () => {
  it('signs out first, then erases what the hub kept but the device’s own, and only then asks the app to forget the hub', async () => {
    signOutAnswers(REDIRECTED);
    const win = appWindow();

    await expect(changeBusiness(invokeOf(win), win)).resolves.toBe('left');

    expect(FORGET_HUB_COMMAND).toBe('forget_hub');
    expect(steps).toEqual(['POST /auth/logout', `forget_hub {"choose":true} ${AFTER_ERASING}`]);
    expect(shell.stopNoticeListening).toHaveBeenCalledOnce();
  });

  it.each([
    ['refuses it', REFUSED],
    ['does not answer', new TypeError('Failed to fetch')],
  ])('forgets nothing and erases nothing when the sign-out %s: the person stays signed in here', async (_case, answer) => {
    signOutAnswers(answer);
    const win = appWindow();
    const before = { local: kept(local), session: kept(session) };

    await expect(changeBusiness(invokeOf(win), win)).resolves.toBe('signOutFailed');

    expect(steps).toEqual(['POST /auth/logout']);
    expect(invoke).not.toHaveBeenCalled();
    expect({ local: kept(local), session: kept(session) }).toEqual(before);
    expect(shell.stopNoticeListening).not.toHaveBeenCalled();
  });

  it('goes on when the hub answers that it is gone: there was no session left to close', async () => {
    signOutAnswers(GONE);
    const win = appWindow();

    await expect(changeBusiness(invokeOf(win), win)).resolves.toBe('left');

    expect(steps).toEqual(['POST /auth/logout', `forget_hub {"choose":true} ${AFTER_ERASING}`]);
  });

  it('says so when the app refuses to forget the hub', async () => {
    signOutAnswers(REDIRECTED);
    invoke.mockRejectedValueOnce('io error');
    const win = appWindow();

    await expect(changeBusiness(invokeOf(win), win)).resolves.toBe('forgetRefused');
  });
});

describe('reloadOrForgetGone: the hub stopped serving the page', () => {
  it('inside the app, a hub that answers it is gone is signed out of and forgotten, without forcing the list', async () => {
    signOutAnswers(GONE);

    await reloadOrForgetGone(appWindow());

    expect(steps).toEqual(['POST /auth/logout', `forget_hub {"choose":false} ${AFTER_ERASING}`]);
    expect(reload).not.toHaveBeenCalled();
  });

  it('inside the app, any other answer reloads the page as before and forgets nothing', async () => {
    signOutAnswers({ type: 'basic', status: 402, ok: false } as Response);

    await reloadOrForgetGone(appWindow());

    expect(invoke).not.toHaveBeenCalled();
    expect(reload).toHaveBeenCalledOnce();
  });

  it('inside the app, reloads when the app refuses to forget the gone hub: its page has the way back', async () => {
    signOutAnswers(GONE);
    invoke.mockRejectedValueOnce('io error');

    await reloadOrForgetGone(appWindow());

    expect(reload).toHaveBeenCalledOnce();
  });

  it('in a browser, only reloads, as before: nothing is posted and nothing is erased', async () => {
    signOutAnswers(GONE);
    const before = kept(local);

    await reloadOrForgetGone(browserWindow());

    expect(steps).toEqual([]);
    expect(reload).toHaveBeenCalledOnce();
    expect(kept(local)).toEqual(before);
  });
});

describe('askChangeBusiness', () => {
  it('opens the question beside the pane', () => {
    askChangeBusiness();
    expect(changeBusinessOpen.value).toBe(true);
  });
});

function invokeOf(win: Window) {
  return { invoke: (win as unknown as { __TAURI__: { core: { invoke: typeof invoke } } }).__TAURI__.core.invoke };
}
