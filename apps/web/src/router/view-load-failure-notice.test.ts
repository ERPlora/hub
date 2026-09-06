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

  // hub#1524 — the second cause: the screen's code threw. Same wall, different words, and the
  // difference is the point. Both sets are asserted here so neither can quietly become the other.
  it('speaks about the CODE failing when that is what failed, not about the connection', () => {
    showViewLoadFailure({ kind: 'code' });

    const notice = document.getElementById(VIEW_LOAD_FAILURE_ID);
    expect(notice?.textContent).toContain(i18n.global.t('viewLoad.brokenTitle'));
    expect(notice?.textContent).toContain(i18n.global.t('viewLoad.brokenBody'));
    // Not a raw key, and not hub#1518's copy: "the connection dropped" would be a lie here.
    expect(notice?.textContent).not.toContain('viewLoad.');
    expect(notice?.textContent).not.toContain(i18n.global.t('viewLoad.blockedTitle'));
    expect(notice?.textContent).not.toContain(i18n.global.t('viewLoad.blockedBody'));
  });

  it('still speaks about the connection for hub#1518, which is the default', () => {
    showViewLoadFailure({ kind: 'download' });

    const notice = document.getElementById(VIEW_LOAD_FAILURE_ID);
    expect(notice?.textContent).toContain(i18n.global.t('viewLoad.blockedBody'));
    expect(notice?.textContent).not.toContain(i18n.global.t('viewLoad.brokenBody'));
  });

  // The two sets exist to READ differently. Equal strings would pass every assertion above while
  // putting the person back in front of the wrong explanation.
  it('does not let the two sets of words collapse into one', () => {
    expect(i18n.global.t('viewLoad.brokenTitle')).not.toBe(i18n.global.t('viewLoad.blockedTitle'));
    expect(i18n.global.t('viewLoad.brokenBody')).not.toBe(i18n.global.t('viewLoad.blockedBody'));
  });
});
