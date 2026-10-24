// The way in's browser rules (APP-BASE-3): the entry by PIN or badge (BASE-G55, G56, G60), the badge reader's burst
// (G56; cases of the old hub's `badge-scanner.test.ts`), the idle lock (G59; its `idle-logout.test.ts`), the
// session's way in from the HTML (`hub-home.access`), a safe `next` and the «Now serving» note across a reload.
import { ApiError } from '@erplora/ui/sdk';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { memoryStorage } from '../__tests__/mount-base';
import {
  announceSwitch,
  BADGE_MAX_GAP_MS,
  createBadgeReader,
  createIdleLock,
  enterWith,
  readAccess,
  safeNext,
  startWayIn,
  takeSwitchAnnouncement,
} from './access';

function spaDocument(cookie = 'csrftoken=tok123'): Document {
  const doc = document.implementation.createHTMLDocument('hub');
  const config = doc.createElement('script');
  config.id = 'spa-config';
  config.type = 'application/json';
  config.textContent = JSON.stringify({ csrfCookieName: 'csrftoken', liveUrl: '/api/live', apiBase: '/api', lang: 'en' });
  doc.body.append(config);
  Object.defineProperty(doc, 'cookie', { value: cookie });
  return doc;
}

function reply(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });
}

describe('enterWith', () => {
  it('posts the entry as JSON with the CSRF token and answers where to go', async () => {
    const fetcher = vi.fn().mockResolvedValue(reply(200, { next: '/sale/pos' }));
    const next = await enterWith('/auth/pin', { person: 'p1', pin: '4826', next: '/sale/pos' }, spaDocument(), fetcher);
    expect(next).toBe('/sale/pos');
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/auth/pin');
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('same-origin');
    expect((init.headers as Record<string, string>)['X-CSRFToken']).toBe('tok123');
    expect(JSON.parse(String(init.body))).toEqual({ person: 'p1', pin: '4826', next: '/sale/pos' });
  });

  it('a refusal is the envelope’s code and sentence', async () => {
    const fetcher = vi.fn().mockResolvedValue(reply(401, { error: { code: 'base.pin_incorrect', message: 'Wrong PIN.' } }));
    const refused = await enterWith('/auth/pin', { person: 'p1', pin: '0000' }, spaDocument(), fetcher).catch((e) => e);
    expect(refused).toBeInstanceOf(ApiError);
    expect([refused.status, refused.code, refused.message]).toEqual([401, 'base.pin_incorrect', 'Wrong PIN.']);
  });

  it('too many attempts carries how long to wait, from Retry-After', async () => {
    const body = { error: { code: 'base.too_many_attempts', message: 'Too many wrong attempts. Wait 3 minutes.' } };
    const fetcher = vi.fn().mockResolvedValue(reply(429, body, { 'Retry-After': '170' }));
    const refused = await enterWith('/auth/badge', { badge: '0012345678' }, spaDocument(), fetcher).catch((e) => e);
    expect([refused.code, refused.details.retry_after]).toEqual(['base.too_many_attempts', 170]);
  });

  it('an answer that is not the envelope (a proxy’s page) is still an ApiError, never a silent entry', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('<html>502</html>', { status: 502 }));
    const refused = await enterWith('/auth/pin', { person: 'p1', pin: '4826' }, spaDocument(), fetcher).catch((e) => e);
    expect(refused).toBeInstanceOf(ApiError);
    expect(refused.status).toBe(502);
  });

  it('an answer without a next goes home', async () => {
    const fetcher = vi.fn().mockResolvedValue(reply(200, {}));
    expect(await enterWith('/auth/pin', { person: 'p1', pin: '4826' }, spaDocument(), fetcher)).toBe('/');
  });
});

describe('safeNext', () => {
  it.each([
    ['/sale/pos', '/sale/pos'],
    ['/sale/pos?table=3#x', '/sale/pos?table=3#x'],
    ['//evil.example/x', '/'],
    ['/\\evil.example', '/'],
    ['https://evil.example', '/'],
    ['', '/'],
    [undefined, '/'],
    [42, '/'],
  ])('%s → %s', (raw, expected) => {
    expect(safeNext(raw)).toBe(expected);
  });
});

describe('createBadgeReader', () => {
  let now = 0;
  const key = (target: EventTarget, k: string, init: KeyboardEventInit = {}) => {
    const event = new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true, ...init });
    target.dispatchEvent(event);
    return event;
  };
  const burst = (target: EventTarget, text: string, gap = 10) => {
    for (const ch of text) {
      key(target, ch);
      now += gap;
    }
    return key(target, 'Enter');
  };

  it('a fast burst of at least four characters ended by Enter is a badge, and its Enter goes nowhere else', () => {
    const onBadge = vi.fn();
    const stop = createBadgeReader(onBadge, { target: document, now: () => now });
    const enter = burst(document, '0012345678');
    expect(onBadge).toHaveBeenCalledExactlyOnceWith('0012345678');
    expect(enter.defaultPrevented).toBe(true);
    stop();
  });

  it('a person typing (slower than the reader) is never a badge', () => {
    const onBadge = vi.fn();
    const stop = createBadgeReader(onBadge, { target: document, now: () => now });
    const enter = burst(document, '1234', BADGE_MAX_GAP_MS + 60);
    expect(onBadge).not.toHaveBeenCalled();
    expect(enter.defaultPrevented).toBe(false);
    stop();
  });

  it('three characters and an Enter is a shortcut, not a badge', () => {
    const onBadge = vi.fn();
    const stop = createBadgeReader(onBadge, { target: document, now: () => now });
    burst(document, '123');
    expect(onBadge).not.toHaveBeenCalled();
    stop();
  });

  it('a modifier or a key outside the badge alphabet breaks the burst', () => {
    const onBadge = vi.fn();
    const stop = createBadgeReader(onBadge, { target: document, now: () => now });
    for (const ch of '0012') key(document, ch);
    key(document, 'c', { ctrlKey: true });
    for (const ch of '34') key(document, ch);
    key(document, 'Enter');
    for (const ch of '0012') key(document, ch);
    key(document, ' ');
    for (const ch of '34') key(document, ch);
    key(document, 'Enter');
    expect(onBadge).not.toHaveBeenCalled();
    stop();
  });

  it('once stopped it hears nothing', () => {
    const onBadge = vi.fn();
    createBadgeReader(onBadge, { target: document, now: () => now })();
    burst(document, '0012345678');
    expect(onBadge).not.toHaveBeenCalled();
  });
});

describe('createIdleLock', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('locks once after the minutes without a touch, a key or the wheel', () => {
    const onIdle = vi.fn();
    const stop = createIdleLock(5, onIdle, window);
    vi.advanceTimersByTime(5 * 60_000 - 1);
    expect(onIdle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onIdle).toHaveBeenCalledOnce();
    vi.advanceTimersByTime(30 * 60_000);
    expect(onIdle).toHaveBeenCalledOnce();
    stop();
  });

  it.each(['pointerdown', 'keydown', 'wheel', 'touchstart'])('a %s starts the minutes again', (type) => {
    const onIdle = vi.fn();
    const stop = createIdleLock(1, onIdle, window);
    vi.advanceTimersByTime(50_000);
    window.dispatchEvent(new Event(type));
    vi.advanceTimersByTime(50_000);
    expect(onIdle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(10_000);
    expect(onIdle).toHaveBeenCalledOnce();
    stop();
  });

  it('stopped, it never locks', () => {
    const onIdle = vi.fn();
    createIdleLock(1, onIdle, window)();
    vi.advanceTimersByTime(10 * 60_000);
    expect(onIdle).not.toHaveBeenCalled();
  });
});

describe('readAccess', () => {
  function withHome(home: unknown): Document {
    const doc = document.implementation.createHTMLDocument('hub');
    const block = doc.createElement('script');
    block.id = 'hub-home';
    block.type = 'application/json';
    block.textContent = JSON.stringify(home);
    doc.body.append(block);
    return doc;
  }

  it('reads the session’s way in from hub-home', () => {
    const access = { credential: 'pin', switch_user: true, idle_minutes: 5 };
    expect(readAccess(withHome({ name: 'Bar', access }))).toEqual(access);
  });

  it('without it (the SaaS, a demo, an older HTML) there is no way in to tell: an account session, nothing to arm', () => {
    expect(readAccess(withHome({ name: 'Bar' }))).toEqual({ credential: 'account', switch_user: false, idle_minutes: null });
    expect(readAccess(document.implementation.createHTMLDocument('x'))).toEqual({
      credential: 'account',
      switch_user: false,
      idle_minutes: null,
    });
  });
});

describe('the «Now serving» note across the reload', () => {
  it('is told once, after the reload, and then forgotten', () => {
    const storage = memoryStorage();
    announceSwitch('Bea', storage);
    expect(takeSwitchAnnouncement(storage)).toBe('Bea');
    expect(takeSwitchAnnouncement(storage)).toBeNull();
  });

  it('a browser that keeps nothing (private window) just tells nothing', () => {
    const broken = { ...memoryStorage(), setItem: () => { throw new Error('QuotaExceededError'); } } as Storage;
    expect(() => announceSwitch('Bea', broken)).not.toThrow();
    expect(takeSwitchAnnouncement(broken)).toBeNull();
  });
});

describe('startWayIn — what the shell does with the session’s way in, once mounted', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  function page(home: unknown): Document {
    const doc = document.implementation.createHTMLDocument('hub');
    const block = doc.createElement('script');
    block.id = 'hub-home';
    block.type = 'application/json';
    block.textContent = JSON.stringify(home);
    doc.body.append(block);
    return doc;
  }

  function deps(storage = memoryStorage()) {
    return {
      translate: vi.fn((key: string, values?: Record<string, unknown>) => `${key} ${JSON.stringify(values ?? {})}`),
      logout: vi.fn(),
      toast: vi.fn(),
      paint: vi.fn(),
      reset: vi.fn(),
      label: () => 'Bea',
      storage,
      target: window,
    };
  }

  const ACCOUNT = { credential: 'account', switch_user: false, idle_minutes: null };
  const NONE = { theme_mode: '', palette: '' };

  it('a till that always asks signs out after its idle minutes (BASE-G59)', () => {
    const d = deps();
    const stop = startWayIn(page({ access: { ...ACCOUNT, credential: 'pin', idle_minutes: 5 }, preferences: NONE }), d);
    vi.advanceTimersByTime(5 * 60_000);
    expect(d.logout).toHaveBeenCalledOnce();
    stop();
  });

  it('anywhere else nothing is armed', () => {
    const d = deps();
    const stop = startWayIn(page({ access: ACCOUNT, preferences: NONE }), d);
    vi.advanceTimersByTime(60 * 60_000);
    expect(d.logout).not.toHaveBeenCalled();
    stop();
  });

  it('paints the person’s own appearance (BASE-G125)', () => {
    const d = deps();
    startWayIn(page({ access: ACCOUNT, preferences: { theme_mode: 'dark', palette: 'forest' } }), d)();
    expect(d.paint).toHaveBeenCalledWith('dark', 'forest');
    expect(d.reset).not.toHaveBeenCalled();
  });

  it('after «Switch user», tells who serves now and forgets the appearance of whoever left (gh:hub#2506)', () => {
    const storage = memoryStorage();
    announceSwitch('Bea', storage);
    const d = deps(storage);
    startWayIn(page({ access: { ...ACCOUNT, credential: 'pin' }, preferences: NONE }), d)();
    expect(d.reset).toHaveBeenCalledOnce();
    expect(d.toast).toHaveBeenCalledWith('base.switchUser.nowServing {"name":"Bea"}');
    expect(takeSwitchAnnouncement(storage)).toBeNull();
  });

  it('without a switch, no toast and the browser’s own appearance stays', () => {
    const d = deps();
    startWayIn(page({ access: ACCOUNT, preferences: NONE }), d)();
    expect([d.toast.mock.calls.length, d.paint.mock.calls.length, d.reset.mock.calls.length]).toEqual([0, 0, 0]);
  });
});
