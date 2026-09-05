// @vitest-environment happy-dom
//
// hub#1518 — the last rung of the ladder: when a screen's file cannot be fetched even after the
// recovery reload, the app is not mounted and there is no toast, no Ionic, no Vue to lean on. The
// only thing left that can still speak to whoever is standing at the till is the document itself.
// A blank page is not an option, so this notice is written straight into the DOM.
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { i18n } from '../i18n';
import { VIEW_LOAD_FAILURE_ID, showViewLoadFailure } from './view-load-failure-notice';

beforeEach(() => {
  document.body.innerHTML = '';
});

describe('showViewLoadFailure', () => {
  it('paints a message the person can read, not a blank page', () => {
    showViewLoadFailure();

    const notice = document.getElementById(VIEW_LOAD_FAILURE_ID);
    expect(notice).not.toBeNull();
    expect(notice?.getAttribute('role')).toBe('alert');
    // Translated (ADR-0055): the text comes from the catalogue, so it is never a raw key and never
    // English hardcoded into the shell.
    expect(notice?.textContent).toContain(i18n.global.t('viewLoad.blockedTitle'));
    expect(notice?.textContent).toContain(i18n.global.t('viewLoad.blockedBody'));
    expect(notice?.textContent).not.toContain('viewLoad.');
  });

  it('offers a way out, and that way out reloads', () => {
    const reload = vi.fn();

    showViewLoadFailure({ reload });

    const button = document.querySelector<HTMLButtonElement>(`#${VIEW_LOAD_FAILURE_ID} button`);
    expect(button).not.toBeNull();
    expect(button?.textContent).toBe(i18n.global.t('viewLoad.blockedAction'));

    button?.click();
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('is idempotent — a second failure does not stack a second wall of text', () => {
    showViewLoadFailure();
    showViewLoadFailure();

    expect(document.querySelectorAll(`#${VIEW_LOAD_FAILURE_ID}`)).toHaveLength(1);
  });
});
