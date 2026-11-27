// The Hub's sign-out without leaving the page: the POST of the logout's form, answered with the redirect that says the
// session closed, which the page does not follow. «Change business» needs to stay on the page after it, to erase what
// the hub kept on the device and to ask the installed app to forget the hub; a sign-out that did not happen must be
// told apart, so that nothing is forgotten while the session stays open.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const shell = vi.hoisted(() => ({ stopNoticeListening: vi.fn(async () => {}) }));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  stopNoticeListening: shell.stopNoticeListening,
}));

import { createAssistant, installAssistant } from '@erplora/ui/components';

import { memoryStorage } from '../__tests__/mount-base';
import { beforeSignOut, endSession, LOGOUT_PATH } from './sign-out';

const CONFIG = { csrfCookieName: 'csrftoken', csrfHeader: 'X-CSRFToken', lang: 'es', loginUrl: '/auth/login' };

function answering(response: Partial<Response> | Error) {
  return vi.fn<typeof fetch>(async () => {
    if (response instanceof Error) throw response;
    return response as Response;
  });
}

const REDIRECTED: Partial<Response> = { type: 'opaqueredirect', status: 0, ok: false };

beforeEach(() => {
  document.body.innerHTML = `<script id="spa-config" type="application/json">${JSON.stringify(CONFIG)}</script>`;
  document.cookie = 'csrftoken=tok-123';
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  document.body.innerHTML = '';
  vi.restoreAllMocks();
  shell.stopNoticeListening.mockClear();
});

describe('endSession', () => {
  it('posts the logout with the CSRF token and does not follow its redirect', async () => {
    const fetcher = answering(REDIRECTED);

    await endSession(document, fetcher);

    expect(fetcher).toHaveBeenCalledOnce();
    const [path, init] = fetcher.mock.calls[0];
    expect(path).toBe('/auth/logout');
    expect(LOGOUT_PATH).toBe('/auth/logout');
    expect(init?.method).toBe('POST');
    expect(init?.credentials).toBe('same-origin');
    expect(init?.redirect).toBe('manual');
    expect((init?.headers as Record<string, string>)['X-CSRFToken']).toBe('tok-123');
    expect(init?.signal).toBeInstanceOf(AbortSignal);
  });

  it('says the session closed when the logout answers its redirect', async () => {
    await expect(endSession(document, answering(REDIRECTED))).resolves.toBe('closed');
  });

  it('says the hub is gone when it answers 410: there is no session left to close', async () => {
    await expect(endSession(document, answering({ type: 'basic', status: 410, ok: false }))).resolves.toBe('gone');
  });

  it.each([
    ['a refused CSRF token', 403],
    ['a server error', 500],
    ['a business suspended for an unpaid invoice', 402],
    ['a hub under maintenance', 503],
  ])('says it failed on %s (%i): the session may still be open', async (_case, status) => {
    await expect(endSession(document, answering({ type: 'basic', status, ok: false }))).resolves.toBe('failed');
  });

  it('says it failed when the hub does not answer at all (no connection, or the wait ran out)', async () => {
    await expect(endSession(document, answering(new TypeError('Failed to fetch')))).resolves.toBe('failed');
    await expect(endSession(document, answering(new DOMException('timed out', 'TimeoutError')))).resolves.toBe('failed');
  });
});

describe('beforeSignOut', () => {
  afterEach(() => installAssistant(undefined));

  it('leaves the panel closed and empty for whoever enters next, on the device that kept it open', async () => {
    const storage = memoryStorage();
    const openStorage = memoryStorage();
    const leaving = createAssistant({ post: vi.fn(), storage, openStorage });
    installAssistant(leaving);
    leaving.forUser('u1');
    leaving.setOpen(true);

    await beforeSignOut();

    const next = createAssistant({ post: vi.fn(), storage, openStorage });
    next.forUser('u2');
    expect({ open: next.state.open, bubbles: next.state.thread.bubbles }).toEqual({ open: false, bubbles: [] });
  });

  it('forgets the conversation with the assistant and waits for the app to stop listening', async () => {
    sessionStorage.setItem('erplora.assistant.history', JSON.stringify({ user: 'u1', bubbles: [], conversation: [] }));
    let stopped!: () => void;
    shell.stopNoticeListening.mockReturnValueOnce(new Promise<void>((resolve) => (stopped = resolve)));
    let done = false;

    const leaving = beforeSignOut().then(() => (done = true));
    await Promise.resolve();
    expect(sessionStorage.getItem('erplora.assistant.history')).toBeNull();
    expect(shell.stopNoticeListening).toHaveBeenCalledOnce();
    expect(done).toBe(false);

    stopped();
    await leaving;
    expect(done).toBe(true);
  });
});
