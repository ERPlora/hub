// The invoice app's UI texts: English source + Spanish, kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON (as the demo's). This test is their guardrail:
// same keys and placeholders in both languages, nothing empty, every key a page, a component or a
// helper of the app uses exists, and the texts the old screens showed are kept word for word.
import { describe, expect, it } from 'vitest';

import { appCatalogues, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('invoice', en, es);
const { EN, ES } = CATALOGUES;

describe('invoice catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms' });

  it('name every type, status, source and kind of document the server knows', () => {
    for (const type of ['F1', 'F2', 'F3', 'R1', 'R2', 'R3', 'R4', 'R5']) {
      expect(EN.has(`invoice.types.${type}`), type).toBe(true);
      expect(EN.has(`invoice.typeNames.${type}`), type).toBe(true);
    }
    for (const status of ['issued', 'paid', 'cancelled']) expect(EN.has(`invoice.status.${status}`), status).toBe(true);
    for (const source of ['sale', 'manual', 'substitution', 'rectification', 'refund', 'void']) {
      expect(EN.has(`invoice.sources.${source}`), source).toBe(true);
    }
    for (const idType of ['02', '03', '04', '05', '06', '07']) expect(EN.has(`invoice.recipient.idTypes.${idType}`), idType).toBe(true);
  });

  it('keep the old screens’ words (WORKBOOK «Pantallas»)', () => {
    expect(ES.get('invoice.title')).toBe('Facturación');
    expect(ES.get('invoice.tabs.invoices')).toBe('Facturas');
    expect(ES.get('invoice.tabs.series')).toBe('Series');
    expect(ES.get('invoice.list.search')).toBe('Buscar facturas…');
    expect(ES.get('invoice.list.empty')).toBe('Aún no hay facturas.');
    expect(ES.get('invoice.list.actions.markPaid')).toBe('Marcar pagada');
    expect(ES.get('invoice.detail.print')).toBe('Imprimir / PDF');
    expect(ES.get('invoice.detail.missingTaxId')).toBe(
      'Esta factura no tiene el NIF del cliente: la impresora de tiques no puede sacarla como factura completa.',
    );
    expect(ES.get('invoice.markPaid.title')).toBe('¿Marcar {number} como pagada?');
    expect(ES.get('invoice.markPaid.message')).toBe('El cobro se registra con la fecha y la hora de ahora.');
    expect(ES.get('invoice.rectify.title')).toBe('Rectificar {number}');
    expect(ES.get('invoice.rectify.submit')).toBe('Emitir rectificativa');
    expect(ES.get('invoice.rectify.isRectifying')).toBe('Una rectificativa no se puede rectificar.');
    expect(ES.get('invoice.rectify.cancelled')).toBe('La factura ya está cancelada.');
    expect(ES.get('invoice.create.title')).toBe('Nueva factura manual');
    expect(ES.get('invoice.create.submit')).toBe('Emitir factura');
    expect(ES.get('invoice.series.empty')).toBe('Aún no hay series. Crea la primera para numerar tus facturas.');
    expect(ES.get('invoice.series.loading')).toBe('Cargando series…');
    expect(ES.get('invoice.series.search')).toBe('Buscar código, nombre…');
    expect(ES.get('invoice.series.form.createTitle')).toBe('Nueva serie de numeración');
    expect(ES.get('invoice.series.form.editTitle')).toBe('Editar serie {code}');
    expect(ES.get('invoice.series.form.create')).toBe('Crear serie');
  });
});
