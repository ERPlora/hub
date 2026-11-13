// The payment app's UI texts: English source + Spanish, kept by hand next to the pages. This test is their
// guardrail: same keys and placeholders in both languages, nothing empty, no Spanish that is the English
// pasted across, every key a page, a component or a helper uses exists, and the screen's established
// words are kept.
import { describe, expect, it } from 'vitest';

import { appCatalogues, expectWords, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

/** Keys whose Spanish IS the English, on purpose, and why. */
const SAME_IN_BOTH: Record<string, string> = {
  'payment.types.sepa': 'SEPA is the scheme’s own name in both languages',
  'payment.types.check': '«Cheque» is the Spanish word too',
};

const CATALOGUES = appCatalogues('payment', en, es);
const { EN } = CATALOGUES;

describe('payment catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'only', sameInBoth: SAME_IN_BOTH, coverage: { moreFilesThan: 5, moreKeysThan: 20 } });

  it('name every status and every method type the server knows', () => {
    for (const status of ['draft', 'approved', 'sent', 'completed', 'cancelled']) expect(EN.has(`payment.status.${status}`), status).toBe(true);
    for (const type of ['cash', 'transfer', 'card', 'sepa', 'check', 'other']) expect(EN.has(`payment.types.${type}`), type).toBe(true);
  });

  it('keep the old screen’s words', () => {
    expectWords(CATALOGUES, [
      ['payment.title', 'Outgoing payments', 'Pagos salientes'],
      ['payment.tabs.payments', 'Payments', 'Pagos'],
      ['payment.payments.columns.reference', 'Reference', 'Referencia'],
      ['payment.payments.columns.date', 'Date', 'Fecha'],
      ['payment.payments.columns.beneficiary', 'Beneficiary', 'Beneficiario'],
      ['payment.payments.columns.amount', 'Amount', 'Importe'],
      ['payment.payments.columns.status', 'Status', 'Estado'],
      ['payment.payments.columns.method', 'Method', 'Método'],
      ['payment.payments.form.concept', 'Concept', 'Concepto'],
      ['payment.status.draft', 'Draft', 'Borrador'],
      ['payment.status.approved', 'Approved', 'Aprobado'],
      ['payment.status.sent', 'Sent', 'Enviado'],
      ['payment.status.completed', 'Completed', 'Completado'],
      ['payment.status.cancelled', 'Cancelled', 'Cancelado'],
      ['payment.payments.new', 'New payment', 'Nuevo pago'],
      ['payment.payments.form.methodPlaceholder', 'Method…', 'Método…'],
      ['payment.payments.search', 'Search reference or beneficiary…', 'Buscar referencia o beneficiario…'],
      ['payment.loading', 'Loading…', 'Cargando…'],
      ['payment.payments.empty', 'No payments.', 'Sin pagos.'],
      ['payment.payments.cancelForm.reason', 'Cancellation reason', 'Motivo de cancelación'],
      ['payment.money.notPositive', 'The amount of a payment must be greater than 0.', 'El importe de un pago tiene que ser mayor que 0.'],
      ['payment.payments.form.methodsError', 'Payment methods could not be loaded.', 'No se han podido cargar los métodos de pago.'],
      ['payment.live.retry', 'Retry', 'Reintentar'],
    ]);
  });
});
