// Types of the operations on the emails of an invoice, from apps/invoice/schemas/emails.py, written by hand as
// `../operations`.
import type { InvoiceRefIn } from '../operations';

export interface SendEmailIn extends InvoiceRefIn {
  /** The customer's card's, without it. */
  to?: string;
  /** Of one email: the same on a retry, which then never sends twice. */
  attempt_key?: string;
}

export interface InvoiceEmailOut {
  id: string;
  /** `null` for whoever does not see the customers' contact details; empty once they were erased. */
  to: string | null;
  status: 'queued' | 'sending' | 'sent' | 'failed';
  requested_at: string;
  sent_at: string | null;
  /** Why it was not sent; empty otherwise. */
  reason: string;
}

export interface EmailListOut {
  /** The email on the customer's card: `null` for whoever does not see it, empty without one. */
  customer_email: string | null;
  /** The newest first. */
  emails: InvoiceEmailOut[];
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'invoice.email.list': { input: InvoiceRefIn; output: EmailListOut };
    'invoice.email.send': { input: SendEmailIn; output: InvoiceEmailOut };
  }
}
