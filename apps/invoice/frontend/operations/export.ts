// Types of the invoices' Excel operation, from apps/invoice/schemas/export.py, written by hand as `../operations`.
import type { InvoiceListIn } from '../operations';

/** The list's search and filters, without its sort or its page. */
export type InvoiceExportIn = Omit<InvoiceListIn, 'limit' | 'offset' | 'sort' | 'dir'>;

export interface InvoiceExportOut {
  filename: string;
  content_type: string;
  invoices: number;
  content_base64: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'invoice.invoice.export': { input: InvoiceExportIn; output: InvoiceExportOut };
  }
}
