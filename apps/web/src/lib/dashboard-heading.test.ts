// The panel header (hub#366, PLAN step 10): «the business name, not the email».
//
// What was on screen was `Good morning, ioanbeilic@gmail.com` — the header read the ACCOUNT, and
// an account address is plumbing, not a business. The `<h1>` answers «whose hub is this», the
// person's name lives in the account menu, and the two must not swap places.
//
// The rule is pure so it can be pinned without a browser: the view only paints what this returns.
import { describe, expect, it } from 'vitest';

import { GREETING_KEY, greetingSlot, panelHeading } from './dashboard-heading';

describe('the heading is the business', () => {
  it('is the business name, verbatim — no greeting wrapped around it', () => {
    expect(panelHeading('Bar Manolo', 9)).toEqual({ kind: 'business', name: 'Bar Manolo' });
  });

  it('trims what the owner typed, and nothing else', () => {
    expect(panelHeading('  Bar Manolo  ', 9)).toEqual({ kind: 'business', name: 'Bar Manolo' });
  });

  it('keeps the name exactly as typed — accents, case and punctuation included', () => {
    const heading = panelHeading('Peluquería LÍA & Co.', 21);

    expect(heading).toEqual({ kind: 'business', name: 'Peluquería LÍA & Co.' });
  });

  it('does not depend on the hour: a business is a business at any time of day', () => {
    for (const hour of [0, 9, 12, 19, 20, 23]) {
      expect(panelHeading('Bar Manolo', hour)).toEqual({ kind: 'business', name: 'Bar Manolo' });
    }
  });
});

describe('a hub that does not know its business yet greets the hour', () => {
  // Day one of EVERY hub lands here: `business_legal_name` starts empty (nothing in provisioning
  // seeds it) and a blueprint never carries it — `PORTABLE_SETTING_KEYS` leaves the fiscal identity
  // deliberately out, so even a hub bootstrapped from a template opens without a name. That makes
  // this the common path, not a corner: it has to read like a finished screen.
  it.each([
    ['empty', ''],
    ['blank', '   '],
    ['not answered yet (null)', null],
    ['not loaded yet (undefined)', undefined],
  ])('%s is not a name → the greeting takes the header', (_case, value) => {
    expect(panelHeading(value, 9)).toEqual({ kind: 'greeting', slot: 'morning' });
  });

  it('greets the hour of the day, so the fallback is never a blank header', () => {
    expect(panelHeading('', 13)).toEqual({ kind: 'greeting', slot: 'afternoon' });
    expect(panelHeading('', 22)).toEqual({ kind: 'greeting', slot: 'evening' });
  });
});

describe('nothing about the person can reach the header', () => {
  // Belt and braces. The person is already out by construction — this module is never told who is
  // logged in — but the header is exactly where an address showed up once, so a stored value that
  // IS an address is refused rather than printed. A demo hub whose user is literally called «Demo»
  // gets the same treatment for free: the header never repeats the account.
  it.each([
    'ioanbeilic@gmail.com',
    'ioanbeilic+a1@gmail.com',
    '  owner@erplora.com  ',
  ])('refuses «%s»: an address is not a business name', (address) => {
    expect(panelHeading(address, 9)).toEqual({ kind: 'greeting', slot: 'morning' });
  });

  it('an @ inside a real name is still a name — only an address is refused', () => {
    expect(panelHeading('Café @ Home', 9)).toEqual({ kind: 'business', name: 'Café @ Home' });
    expect(panelHeading('Bar@Manolo', 9)).toEqual({ kind: 'business', name: 'Bar@Manolo' });
  });
});

describe('the hour picks the greeting', () => {
  it.each([
    [0, 'morning'],
    [11, 'morning'],
    [12, 'afternoon'],
    [19, 'afternoon'],
    [20, 'evening'],
    [23, 'evening'],
  ])('%i → %s', (hour, slot) => {
    expect(greetingSlot(hour)).toBe(slot);
  });
});

describe('every greeting slot has its own string', () => {
  it('maps each slot to a dashboard key, and no two share one', () => {
    const keys = [GREETING_KEY.morning, GREETING_KEY.afternoon, GREETING_KEY.evening];

    expect(keys).toEqual([
      'dashboard.greetingMorning',
      'dashboard.greetingAfternoon',
      'dashboard.greetingEvening',
    ]);
    expect(new Set(keys).size).toBe(3);
  });
});
