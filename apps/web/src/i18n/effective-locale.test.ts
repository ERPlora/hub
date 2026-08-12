// @vitest-environment happy-dom
// The shell and the modules have to be in the SAME language (hub#790).
//
// They were not, and not by a little: a user who picked English got an English shell — Home,
// Employees, Files, Settings, even the module's own tab title — and then opened the till and read
// «Vender», «Cuenta nueva», «Toca un producto para añadirlo». Every module, always, in Spanish.
//
// The reason is one line in each half, and they were pointing in opposite directions. A module Web
// Component cannot call into the shell's vue-i18n: it is a foreign custom element with its own
// bundle, so ADR-0055 gives it a SYNCHRONOUS bridge — `ErploraClient.locale` reads
// `localStorage['erplora.locale']` and falls back to `'es'`. And the shell, on applying the user's
// preference, did `localStorage.removeItem('erplora.locale')`. Nobody ever wrote it. The bridge was
// a key that only ever got deleted, so every module read the fallback for ever.
//
// The contract these tests fix, from the issue: the DATABASE stays the authority (`/api/profile`),
// and the key is a MIRROR of the effective locale the shell resolved —
//
//     effective = personal preference ?? hub default ?? 'es'
//
// — republished on every change, never removed. A mirror that is only ever deleted is not a mirror.
import { beforeEach, describe, expect, it } from 'vitest';

import {
  applyUserLocale,
  bootHubLanguage,
  getLocale,
  MODULE_LOCALE_KEY,
  resetUserLocale,
  setLocale,
} from './index';

/** What a module Web Component reads through `ErploraClient.locale` (ADR-0055). */
function whatTheModuleReads(): string {
  return localStorage.getItem(MODULE_LOCALE_KEY) || 'es';
}

beforeEach(() => {
  localStorage.clear();
  resetUserLocale('es');
});

describe('the bridge the modules read', () => {
  it('carries the personal preference — the case that was broken', () => {
    applyUserLocale('en', 'es');

    expect(getLocale()).toBe('en');
    expect(whatTheModuleReads()).toBe('en');
  });

  it('carries the hub default when the person has no preference of their own', () => {
    applyUserLocale(null, 'en');

    expect(getLocale()).toBe('en');
    expect(whatTheModuleReads()).toBe('en');
  });

  it('lets the personal preference win over the hub default', () => {
    applyUserLocale('es', 'en');

    expect(getLocale()).toBe('es');
    expect(whatTheModuleReads()).toBe('es');
  });

  it('follows a hot change of the shell language', () => {
    applyUserLocale('es', 'es');
    setLocale('en');

    expect(whatTheModuleReads()).toBe('en');
  });

  it('follows the hub language arriving late in the boot', () => {
    // `bootHubLanguage` runs when `/api/hub/context` answers, after the first paint. A module
    // mounted before that has to end up in the same language as everything else.
    bootHubLanguage('en');

    expect(getLocale()).toBe('en');
    expect(whatTheModuleReads()).toBe('en');
  });

  it('is never REMOVED — a mirror that only gets deleted is not a mirror', () => {
    applyUserLocale('en', 'es');
    // Signing out and back in as somebody with no preference must leave the key pointing at the new
    // effective language, not at nothing. `localStorage` outlives the session and is shared by every
    // user of that till: an absent key is read as `'es'` by every module, which is how a hub whose
    // own language is English ended up with Spanish modules.
    resetUserLocale('en');

    expect(localStorage.getItem(MODULE_LOCALE_KEY)).toBe('en');
  });

  it('is written at every door, so no path leaves the modules behind', () => {
    for (const [apply, expected] of [
      [() => applyUserLocale('en', null), 'en'],
      [() => setLocale('es'), 'es'],
      [() => resetUserLocale('en'), 'en'],
    ] as const) {
      localStorage.removeItem(MODULE_LOCALE_KEY);
      apply();
      expect(whatTheModuleReads()).toBe(expected);
    }
  });

  it('ignores a language with no catalogue instead of publishing a lie', () => {
    applyUserLocale('en', 'es');
    // `klingon` has no `locales/klingon.ts`, so the shell stays where it is — and so must the
    // bridge. Publishing it would put every module into a fallback the shell is not in.
    setLocale('klingon');

    expect(getLocale()).toBe('en');
    expect(whatTheModuleReads()).toBe('en');
  });
});
