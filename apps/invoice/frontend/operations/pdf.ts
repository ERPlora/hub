// Types of the invoice's PDF operation, from apps/invoice/schemas/pdf.py, written by hand as `../operations`.
import type { DocumentIn } from '../operations';

export interface InvoicePdfOut {
  filename: string;
  content_type: string;
  content_base64: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'invoice.invoice.pdf': { input: DocumentIn; output: InvoicePdfOut };
  }
}
