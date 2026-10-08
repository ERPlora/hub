// @vitest-environment happy-dom
// hub#2536 — the faces this browser remembers for the PIN grid carry a name and initials, never an
// e-mail; and the e-mails an older version left behind are forgotten when ERPlora starts, on every
// device (a personal laptop or a till that keeps its session never opens Acceso to rewrite them).
import { beforeEach, describe, expect, it } from 'vitest';
import { forgetTrustedUserEmails, readTrustedUsers, saveTrustedUsers } from './trusted-users';

const KEY = 'erplora.trusted_users';

beforeEach(() => localStorage.clear());

describe('the faces remembered for the PIN grid', () => {
  it('are saved with their id, name and initials only', () => {
    saveTrustedUsers([{ id: 'u-anna', name: 'Anna Cloud', initials: 'AC', email: 'anna@example.com' } as never]);

    expect(JSON.parse(localStorage.getItem(KEY) ?? '[]')).toEqual([
      { id: 'u-anna', name: 'Anna Cloud', initials: 'AC' },
    ]);
  });

  it('are read without the e-mail an older version stored', () => {
    localStorage.setItem(
      KEY,
      JSON.stringify([{ id: 'u-bob', name: 'Bob Till', email: 'bob@example.com', initials: 'BT' }]),
    );

    expect(readTrustedUsers()).toEqual([{ id: 'u-bob', name: 'Bob Till', initials: 'BT' }]);
  });

  it('read as none when what is stored is not a list of faces', () => {
    localStorage.setItem(KEY, '{not json');
    expect(readTrustedUsers()).toEqual([]);
    localStorage.setItem(KEY, JSON.stringify({ id: 'u-bob' }));
    expect(readTrustedUsers()).toEqual([]);
  });
});

describe('starting ERPlora', () => {
  it('forgets the e-mails an older version left in this browser and keeps the faces', () => {
    localStorage.setItem(
      KEY,
      JSON.stringify([
        { id: 'u-anna', name: 'Anna Cloud', email: 'anna@example.com', initials: 'AC' },
        { id: 'u-bob', name: 'Bob Till', initials: 'BT' },
      ]),
    );

    forgetTrustedUserEmails();

    expect(localStorage.getItem(KEY)).not.toContain('@');
    expect(JSON.parse(localStorage.getItem(KEY) ?? '[]')).toEqual([
      { id: 'u-anna', name: 'Anna Cloud', initials: 'AC' },
      { id: 'u-bob', name: 'Bob Till', initials: 'BT' },
    ]);
  });

  it('does not invent a list where there was none', () => {
    forgetTrustedUserEmails();
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it('drops a list it cannot read rather than keep whatever it holds', () => {
    localStorage.setItem(KEY, '{"email":"anna@example.com"');
    forgetTrustedUserEmails();
    expect(localStorage.getItem(KEY)).toBeNull();
  });
});
