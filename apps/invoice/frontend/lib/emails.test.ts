// What the invoice's screen says of each of its emails (INVOICE-F26).
import { describe, expect, it } from 'vitest';

import type { InvoiceEmailOut } from '../operations/emails';
import { emailLine, lastFailure } from './emails';

const SENT: InvoiceEmailOut = {
  id: 'e1',
  to: 'ana@example.com',
  status: 'sent',
  requested_at: '2026-11-24T11:00:00Z',
  sent_at: '2026-11-24T11:00:05Z',
  reason: '',
};
const t = (key: string, values: Record<string, string> = {}) => `${key}(${Object.values(values).join('|')})`;
const line = (email: Partial<InvoiceEmailOut>) => emailLine({ ...SENT, ...email }, t, () => 'WHEN');

describe('emailLine', () => {
  it('says to whom and when it was sent', () => {
    expect(line({})).toBe('invoice.email.sentTo(ana@example.com|WHEN)');
  });

  it.each(['queued', 'sending'] as const)('one %s is on its way', (status) => {
    expect(line({ status, sent_at: null })).toBe('invoice.email.sendingTo(ana@example.com)');
  });

  it('one that did not leave never says it was sent', () => {
    expect(line({ status: 'failed', sent_at: null, reason: 'Why' })).toBe('invoice.email.notSentTo(ana@example.com)');
  });

  it.each([null, ''])('without an address it says the rest (%s)', (to) => {
    expect(line({ to })).toBe('invoice.email.sent(WHEN)');
    expect(line({ to, status: 'queued', sent_at: null })).toBe('invoice.email.sending()');
    expect(line({ to, status: 'failed', sent_at: null })).toBe('invoice.email.notSent()');
  });
});

describe('lastFailure', () => {
  const failed: InvoiceEmailOut = { ...SENT, id: 'e2', status: 'failed', sent_at: null, reason: 'Why' };

  it('is the newest email when it did not leave', () => {
    expect(lastFailure([failed, SENT])).toBe(failed);
  });

  it.each([
    ['it was sent later', [SENT, failed]],
    ['another is on its way', [{ ...SENT, status: 'queued' as const, sent_at: null }, failed]],
    ['there is none', []],
  ])('is none when %s', (_why, emails) => {
    expect(lastFailure(emails)).toBeNull();
  });
});
