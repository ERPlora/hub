// Types of the ticket's public page operations, from apps/invoice/schemas/public.py, written by hand as `../operations`.
import type { InvoiceOut, RecipientIn } from '../operations';

export interface PublicTicketSummaryOut {
  number: string;
  issue_date: string;
  total_amount: number;
  currency: string;
  issuer_name: string;
}

export interface PublicRecordOut {
  qr_svg: string;
  qr_url: string;
}

export interface PublicTicketOut {
  ticket: PublicTicketSummaryOut;
  invoice: InvoiceOut | null;
  record: PublicRecordOut | null;
}

export interface PublicSubstituteIn
  extends Pick<RecipientIn, 'customer_name' | 'customer_country' | 'customer_id_type' | 'customer_tax_id' | 'customer_address'> {
  code: string;
}

export interface PublicIssueOut {
  issued: boolean;
  already: boolean;
  invoice: InvoiceOut;
  record: PublicRecordOut | null;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'invoice.public.ticket': { input: { code: string }; output: PublicTicketOut };
    'invoice.public.substitute': { input: PublicSubstituteIn; output: PublicIssueOut };
  }
}
