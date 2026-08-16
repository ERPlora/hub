import { beforeEach, describe, expect, it, vi } from 'vitest';
import { applyUserLocale, bootHubLanguage, setLocale } from './index';

const values = new Map<string, string>();

beforeEach(() => {
  values.clear();
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  });
  vi.stubGlobal('window', { dispatchEvent: vi.fn() });
  vi.stubGlobal('CustomEvent', class {
    constructor(public type: string, public init?: unknown) {}
  });
});

describe('effective locale bridge for module Web Components', () => {
  it('publishes the personal locale where the module SDK reads it', () => {
    applyUserLocale('en', 'es');

    expect(localStorage.getItem('erplora.locale')).toBe('en');
  });

  it('publishes the Hub locale when the user has no override', () => {
    applyUserLocale(null, 'es');
    bootHubLanguage('en');

    expect(localStorage.getItem('erplora.locale')).toBe('en');
  });

  it('keeps direct locale changes in sync with modules', () => {
    setLocale('en');

    expect(localStorage.getItem('erplora.locale')).toBe('en');
  });
});
