// What the invoice's screen says of each of its emails (INVOICE-F26).
import type { InvoiceEmailOut } from '../operations/emails';

type Translate = (key: string, values?: Record<string, string>) => string;

/** «Sent to ana@example.com on …», «Sending to …» or «Not sent to …», without the address where there is none. */
export function emailLine(email: InvoiceEmailOut, t: Translate, when: (moment: string) => string): string {
  const to = email.to ? { to: email.to } : undefined;
  if (email.status === 'failed') return to ? t('invoice.email.notSentTo', to) : t('invoice.email.notSent');
  if (email.status !== 'sent' || !email.sent_at) return to ? t('invoice.email.sendingTo', to) : t('invoice.email.sending');
  const date = when(email.sent_at);
  return to ? t('invoice.email.sentTo', { ...to, date }) : t('invoice.email.sent', { date });
}

/** The newest email, when it did not leave. */
export function lastFailure(emails: readonly InvoiceEmailOut[]): InvoiceEmailOut | null {
  return emails[0]?.status === 'failed' ? emails[0] : null;
}
