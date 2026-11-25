// Online orders' UI texts: English source + Spanish. This test is their guardrail: same keys and placeholders in both
// languages, nothing empty, every key a page or a component of the app uses exists, and the screen's words are the
// WORKBOOK's.
import { describe, expect, it } from 'vitest';

import { appCatalogues, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('online_order', en, es);
const { ES } = CATALOGUES;

describe('online_order catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'only' });

  it('say what the WORKBOOK’s screen says', () => {
    expect(ES.get('online_order.qrCodes.title')).toBe('Códigos QR');
    expect(ES.get('online_order.qrCodes.print')).toBe('Imprimir hoja');
    expect(ES.get('online_order.qrCodes.actions.regenerate')).toBe('Regenerar QR');
    expect(ES.get('online_order.qrCodes.actions.generate')).toBe('Generar QR');
    expect(ES.get('online_order.qrCodes.actions.print')).toBe('Imprimir QR');
    expect(ES.get('online_order.qrCodes.generateMissing')).toBe('Generar los QR que faltan');
    expect(ES.get('online_order.qrCodes.empty')).toBe('Aún no hay mesas');
    expect(ES.get('online_order.qrCodes.goToTables')).toBe('Ir a Mesas');
    expect(ES.get('online_order.qrCodes.printFailed')).toBe('No se ha podido imprimir la hoja.');
    expect(ES.get('online_order.sheet.scan')).toBe('Escanea para pedir');
  });
});
