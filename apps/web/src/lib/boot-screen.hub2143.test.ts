// @vitest-environment happy-dom
// hub#2143 — the two faces of `#app` before the shell mounts: the spinner the served document paints
// (hub#2073) and the notice that replaces it when the hub does not answer. Retry must bring the
// spinner back — a notice that stays up while the new attempt runs reads as «the button did nothing».
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { createBootScreen } from './boot-screen';
import { MODULE_LOCALE_KEY, i18n } from '../i18n';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const SPINNER =
  '<div class="boot-progress" role="status" aria-busy="true"><div class="boot-progress-spinner"></div></div>';

let el: HTMLElement;

beforeEach(() => {
  localStorage.clear();
  i18n.global.locale.value = 'es';
  document.body.innerHTML = `<div id="app">${SPINNER}</div>`;
  el = document.getElementById('app')!;
});

describe('boot screen (hub#2143)', () => {
  it('replaces the spinner with the notice, whose button retries', async () => {
    const screen = createBootScreen(el);
    const retry = vi.fn();

    screen.showUnreachable(retry);
    await Promise.resolve();

    expect(el.querySelector('.boot-progress')).toBeNull();
    expect(el.querySelector('[data-testid="boot-unreachable"]')).not.toBeNull();

    (el.querySelector('[data-testid="boot-unreachable-retry"]') as HTMLElement).click();
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it('brings the served spinner back, and the notice is gone', async () => {
    const screen = createBootScreen(el);
    screen.showUnreachable(() => undefined);
    await Promise.resolve();

    screen.showProgress();

    expect(el.querySelector('[data-testid="boot-unreachable"]')).toBeNull();
    expect(el.querySelector('.boot-progress[role="status"]')).not.toBeNull();
    // The notice's app is unmounted, not just painted over: the shell mounts on this same `#app`
    // next, and Vue refuses to share a container with an app that is still alive there.
    expect((el as HTMLElement & { __vue_app__?: unknown }).__vue_app__).toBeUndefined();
  });

  it('can fail again after a retry: the notice comes back', async () => {
    const screen = createBootScreen(el);
    screen.showUnreachable(() => undefined);
    screen.showProgress();
    screen.showUnreachable(() => undefined);
    await Promise.resolve();

    expect(el.querySelectorAll('[data-testid="boot-unreachable"]')).toHaveLength(1);
    expect(el.querySelector('.boot-progress')).toBeNull();
  });

  // With no answer from the hub there is no hub language either, and the shell boots in its default
  // (Spanish) until the context says otherwise. The best fact left is the language this device
  // showed last time — published on every change under `erplora.locale`.
  it('speaks the language this device used last', async () => {
    localStorage.setItem(MODULE_LOCALE_KEY, 'en');
    const screen = createBootScreen(el);

    screen.showUnreachable(() => undefined);
    await Promise.resolve();

    const retry = el.querySelector('[data-testid="boot-unreachable-retry"]')!;
    expect(retry.textContent?.trim()).toBe(en.boot.unreachable.retry);
  });

  it('with no language on record, uses the default one', async () => {
    const screen = createBootScreen(el);

    screen.showUnreachable(() => undefined);
    await Promise.resolve();

    const retry = el.querySelector('[data-testid="boot-unreachable-retry"]')!;
    expect(retry.textContent?.trim()).toBe(es.boot.unreachable.retry);
  });

  it('leaves the shell language as it found it once the notice goes', () => {
    localStorage.setItem(MODULE_LOCALE_KEY, 'en');
    const screen = createBootScreen(el);

    screen.showUnreachable(() => undefined);
    screen.showProgress();

    // The hub's own language is reconciled by `bootHubLanguage` once the context answers; the
    // notice must not have decided it on the way.
    expect(i18n.global.locale.value).toBe('es');
  });

  it('ignores a language on record that has no translation', async () => {
    localStorage.setItem(MODULE_LOCALE_KEY, 'xx');
    const screen = createBootScreen(el);

    screen.showUnreachable(() => undefined);
    await Promise.resolve();

    expect(el.querySelector('[data-testid="boot-unreachable-retry"]')!.textContent?.trim()).toBe(
      es.boot.unreachable.retry,
    );
    // Not even borrowed: like `setLocale`, a language with no file is never put in place (vue-i18n
    // would only mask it with its fallback, and warn about it).
    expect(i18n.global.locale.value).toBe('es');
  });
});
