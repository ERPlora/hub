// The dates of an invoice as apps/invoice/schemas/invoices.py takes and sends them, written by hand as `operations.d.ts`.
import type { InvoiceStatus } from './operations';

/** The day a manual invoice is dated (today, when it says none) and the day it has to be paid by, if it says one. */
export interface InvoiceDatesIn {
  issue_date?: string;
  due_date?: string;
}

/** When an invoice has to be paid, and whether that day has passed without it. */
export interface InvoiceDueOut {
  due_date: string | null;
  overdue: boolean;
}

/** What the list's status filter takes: the statuses an invoice keeps, and the overdue ones. */
export type InvoiceStatusFilter = InvoiceStatus | 'overdue';
