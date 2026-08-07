// Tests del lanzador del deep link `erplora://` y de su FALLBACK (ADR-0196 §7, hub#345).
//
// El fallback es la mitad que se olvida y la que más duele: si la app no está instalada, un
// navegador que intenta un esquema desconocido NO avisa —Chrome no hace absolutamente nada,
// Safari saca un diálogo del sistema— y el usuario se queda mirando una página que no reaccionó.
// Por eso cada caso tiene su test: app instalada, app ausente y navegador que bloquea el esquema.
//
// Entorno node puro (`vite.config.ts` → environment: 'node'): se stubbean `window` y `document`.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DEFAULT_WAIT_FOR_APP_MS, hubDeepLink, hubUrl, openHub } from './deep-link';

/** Doble de `window`/`document` que registra a dónde acabó el navegador. */
function stubBrowser() {
  const listeners: Record<string, Array<() => void>> = {};
  const location = {
    href: '',
    replace: vi.fn<(url: string) => void>(),
  };
  const doc = {
    hidden: false,
    addEventListener: vi.fn((type: string, fn: () => void) => {
      (listeners[type] ??= []).push(fn);
    }),
    removeEventListener: vi.fn((type: string, fn: () => void) => {
      listeners[type] = (listeners[type] ?? []).filter((l) => l !== fn);
    }),
  };
  const win = {
    location,
    addEventListener: doc.addEventListener,
    removeEventListener: doc.removeEventListener,
    setTimeout,
    clearTimeout,
  };
  vi.stubGlobal('window', win);
  vi.stubGlobal('document', doc);
  return {
    location,
    doc,
    /** Dispara un evento como haría el navegador. */
    fire(type: string) {
      for (const fn of [...(listeners[type] ?? [])]) fn();
    },
    listenerCount() {
      return Object.values(listeners).reduce((n, l) => n + l.length, 0);
    },
  };
}

describe('hubDeepLink', () => {
  it('builds the link the app registered', () => {
    expect(hubDeepLink('demo.a.erplora.com')).toBe('erplora://hub/demo.a.erplora.com');
  });

  it('normalises the host the way the app will read it', () => {
    expect(hubDeepLink('  DEMO.A.ERPLORA.COM ')).toBe('erplora://hub/demo.a.erplora.com');
  });

  it('refuses a malformed label even under our own domain', () => {
    // The suffix check alone is not enough: everything below it still has to look like a hostname,
    // or a homograph gets to wear our domain.
    for (const hostile of [
      'demo..erplora.com',
      'demo a.erplora.com',
      'demo_a.erplora.com',
      '-demo.erplora.com',
      'demo-.erplora.com',
      'demo@evil.erplora.com',
      'demo.а.erplora.com', // Cyrillic а — not the aura `a`
    ]) {
      expect(() => hubDeepLink(hostile), hostile).toThrow();
    }
  });

  it('refuses to build a link to something that is not a hub of ours', () => {
    // Same boundary as the app (`resolve_deep_link` in apps/tauri). Building the link here and
    // refusing it there would just move the failure to where nobody can see it.
    for (const hostile of [
      'evil.com',
      'demo.a.erplora.com.evil.com',
      'erplora.com',
      'evil-erplora.com',
      'demo.a.erplora.com/../evil.com',
      'demo.a.erplora.com@evil.com',
      '',
    ]) {
      expect(() => hubDeepLink(hostile), hostile).toThrow();
    }
  });
});

describe('hubUrl', () => {
  it('is the https address of the hub', () => {
    expect(hubUrl('demo.a.erplora.com')).toBe('https://demo.a.erplora.com/');
  });

  it('keeps development hubs on plain http loopback', () => {
    expect(hubUrl('127.0.0.1:8787')).toBe('http://127.0.0.1:8787/');
    expect(hubUrl('localhost:5173')).toBe('http://localhost:5173/');
    expect(hubUrl('127.0.0.1:87a7')).toBeNull();
  });

  it('is null for anything that is not a hub of ours', () => {
    expect(hubUrl('evil.com')).toBeNull();
    expect(hubUrl('erplora.com')).toBeNull();
  });
});

describe('openHub', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('asks the operating system for the app first', () => {
    const browser = stubBrowser();

    openHub('demo.a.erplora.com');

    expect(browser.location.href).toBe('erplora://hub/demo.a.erplora.com');
    expect(browser.location.replace).not.toHaveBeenCalled();
  });

  it('leaves the browser alone when the installed app takes over', () => {
    // The app opening is what makes the page lose the foreground. If the fallback fired anyway,
    // the user would come back from the app to find the browser had also navigated.
    const browser = stubBrowser();

    openHub('demo.a.erplora.com');
    browser.fire('blur');
    vi.advanceTimersByTime(DEFAULT_WAIT_FOR_APP_MS * 10);

    expect(browser.location.replace).not.toHaveBeenCalled();
  });

  it('leaves the browser alone when the tab is hidden by the app', () => {
    // On mobile the signal is visibility, not focus.
    const browser = stubBrowser();

    openHub('demo.a.erplora.com');
    browser.doc.hidden = true;
    browser.fire('visibilitychange');
    vi.advanceTimersByTime(DEFAULT_WAIT_FOR_APP_MS * 10);

    expect(browser.location.replace).not.toHaveBeenCalled();
  });

  it('leaves the browser alone when a throttled timer fires late on a hidden page', () => {
    // A background tab has its timers throttled, so the fallback can fire long after the app
    // already took over — and with no `visibilitychange` left to hear, because it was dispatched
    // while the timer was still pending. The state of the page at fire time is the last word.
    const browser = stubBrowser();

    openHub('demo.a.erplora.com');
    browser.doc.hidden = true; // hidden, but nobody told us
    vi.advanceTimersByTime(DEFAULT_WAIT_FOR_APP_MS * 10);

    expect(browser.location.replace).not.toHaveBeenCalled();
  });

  it('lands the user on the hub when no app answers', () => {
    // THE case this exists for: without the app, nothing happens and nothing reports it. The user
    // must end up somewhere usable instead of on a page that did not react.
    const browser = stubBrowser();

    openHub('demo.a.erplora.com');
    expect(browser.location.replace).not.toHaveBeenCalled();

    vi.advanceTimersByTime(DEFAULT_WAIT_FOR_APP_MS);

    expect(browser.location.replace).toHaveBeenCalledWith('https://demo.a.erplora.com/');
  });

  it('does not fall back while the app might still be starting', () => {
    const browser = stubBrowser();

    openHub('demo.a.erplora.com');
    vi.advanceTimersByTime(DEFAULT_WAIT_FOR_APP_MS - 1);

    expect(browser.location.replace).not.toHaveBeenCalled();
  });

  it('replaces the launcher instead of stacking it', () => {
    // With a history entry, Back would return to the launcher and fire the link again — a loop the
    // user cannot get out of with the one button they trust.
    const browser = stubBrowser();

    openHub('demo.a.erplora.com');
    vi.advanceTimersByTime(DEFAULT_WAIT_FOR_APP_MS);

    expect(browser.location.replace).toHaveBeenCalledTimes(1);
  });

  it('falls back at once when the browser blocks the scheme', () => {
    // Some browsers refuse an unknown scheme outright and throw. Waiting 800 ms for something that
    // already failed only delays the only useful outcome.
    const browser = stubBrowser();
    Object.defineProperty(browser.location, 'href', {
      set() {
        throw new Error('unknown scheme');
      },
      get: () => '',
    });

    openHub('demo.a.erplora.com');

    expect(browser.location.replace).toHaveBeenCalledWith('https://demo.a.erplora.com/');
  });

  it('can send the user to the download page instead of the hub', () => {
    // When the app is REQUIRED (a thermal ticket cannot be printed from a browser, ADR-0196 §5),
    // the useful destination is "install the app", not the hub.
    const browser = stubBrowser();

    openHub('demo.a.erplora.com', { fallbackUrl: 'https://erplora.com/downloads/' });
    vi.advanceTimersByTime(DEFAULT_WAIT_FOR_APP_MS);

    expect(browser.location.replace).toHaveBeenCalledWith('https://erplora.com/downloads/');
  });

  it('never sends the user to a host that is not a hub of ours', () => {
    // The launcher is reached with the host in the URL, so a tampered one has to stop here too —
    // and stop BEFORE the browser is touched at all.
    const browser = stubBrowser();

    expect(() => openHub('evil.com')).toThrow();

    expect(browser.location.href).toBe('');
    expect(browser.location.replace).not.toHaveBeenCalled();
  });

  it('leaves no listeners behind once it is done', () => {
    const browser = stubBrowser();

    openHub('demo.a.erplora.com');
    vi.advanceTimersByTime(DEFAULT_WAIT_FOR_APP_MS);

    expect(browser.listenerCount()).toBe(0);
  });

  it('waits 800 ms by default, which the caller can change', () => {
    // Long enough for the OS to switch apps, short enough that nobody reads it as "broken".
    expect(DEFAULT_WAIT_FOR_APP_MS).toBe(800);

    const browser = stubBrowser();
    openHub('demo.a.erplora.com', { waitForAppMs: 2_000 });

    vi.advanceTimersByTime(1_999);
    expect(browser.location.replace).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(browser.location.replace).toHaveBeenCalledWith('https://demo.a.erplora.com/');
  });
});
