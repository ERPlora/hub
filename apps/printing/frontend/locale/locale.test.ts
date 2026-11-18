// The printing app's UI texts: English source + Spanish. This test is their guardrail: same keys and
// placeholders in both languages, nothing empty, every key a page, a component or a helper of the app uses
// exists, and the screens' established texts are kept word for word.
import { describe, expect, it } from 'vitest';

import { appCatalogues, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('printing', en, es);
const { EN, ES } = CATALOGUES;

describe('printing catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'only' });

  it('name every function, connection, state, status and document the server knows', () => {
    for (const usage of ['receipt', 'kitchen', 'bar', 'label']) expect(EN.has(`printing.usage.${usage}`), usage).toBe(true);
    for (const kind of ['network', 'usb', 'bluetooth', 'system']) expect(EN.has(`printing.kind.${kind}`), kind).toBe(true);
    for (const state of ['ready', 'waiting', 'failing', 'inactive']) expect(EN.has(`printing.state.${state}`), state).toBe(true);
    for (const status of ['pending', 'sent', 'done', 'failed', 'cancelled']) expect(EN.has(`printing.status.${status}`), status).toBe(true);
    const documents = ['receipt', 'kitchen_order', 'invoice', 'delivery_note', 'barcode_label', 'cash_session_report', 'prebill', 'generic'];
    for (const document of [...documents, 'test_page', 'drawer']) expect(EN.has(`printing.documents.${document}`), document).toBe(true);
  });

  it('keep the old screen’s words (the WORKBOOK’s screens)', () => {
    expect(ES.get('printing.printers.heading')).toBe('Impresoras');
    expect(ES.get('printing.summary.heading')).toBe('Cola de impresión');
    expect(ES.get('printing.summary.loadError')).toBe('No se pudo leer la cola de impresión.');
    expect(ES.get('printing.summary.stalled')).toBe('En cola, sin impresora');
    expect(ES.get('printing.settings.heading')).toBe('Ajustes del tique');
    expect(ES.get('printing.settings.fields.print_receipt_on_sale')).toBe('Imprimir tique al cobrar');
    expect(ES.get('printing.settings.fields.open_drawer_on_sale')).toBe('Abrir cajón al cobrar');
    expect(ES.get('printing.settings.save')).toBe('Guardar ajustes');
    expect(ES.get('printing.settings.receiptText')).toBe(
      'El encabezado y el pie del tique forman parte de los ajustes de Ventas, que es de donde sale el tique.',
    );
    expect(ES.get('printing.settings.receiptLink')).toBe('Abrir los ajustes del tique');
    expect(ES.get('printing.printers.actions.test')).toBe('Probar');
    expect(ES.get('printing.printers.testFailed')).toBe('Falló la impresión de prueba');
    expect(ES.get('printing.modal.paper')).toBe('Ancho de papel');
    expect(ES.get('printing.jobs.actions.retry')).toBe('Reintentar');
    expect(ES.get('printing.jobs.cancel.reason')).toBe('Motivo (opcional)');
    expect(ES.get('printing.jobs.lastError')).toBe('Último error: {error}');
    expect(ES.get('printing.documents.kitchen_order')).toBe('Comanda de cocina');
    expect(ES.get('printing.documents.prebill')).toBe('Cuenta preliminar');
    expect(ES.get('printing.usage.receipt')).toBe('Recibo');
  });
});
