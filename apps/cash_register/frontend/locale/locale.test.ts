// The cash register app's UI texts: English source + Spanish. This test is their guardrail: same keys and
// placeholders in both languages, nothing empty, every key a page, a component or a helper of the app uses
// exists, and the screens' established texts are kept word for word.
import { describe, expect, it } from 'vitest';

import { appCatalogues, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('cash_register', en, es);
const { EN, ES } = CATALOGUES;

describe('cash register catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'only' });

  it('name every status, type, payment method and count type the server knows', () => {
    for (const status of ['open', 'closed']) expect(EN.has(`cash_register.status.${status}`), status).toBe(true);
    for (const type of ['in', 'out', 'sale', 'refund', 'void']) expect(EN.has(`cash_register.types.${type}`), type).toBe(true);
    for (const method of ['cash', 'card', 'transfer', 'other']) expect(EN.has(`cash_register.methods.${method}`), method).toBe(true);
    for (const kind of ['opening', 'closing']) expect(EN.has(`cash_register.countTypes.${kind}`), kind).toBe(true);
  });

  it('keep the old screens’ words (the WORKBOOK’s screens)', () => {
    expect(ES.get('cash_register.sessions.open')).toBe('Abrir sesión');
    expect(ES.get('cash_register.sessions.alreadyOpen')).toBe('Ya hay una sesión de caja abierta. Ciérrala antes de abrir otra.');
    expect(ES.get('cash_register.sessions.empty')).toBe('Sin sesiones de caja.');
    expect(ES.get('cash_register.sessions.search')).toBe('Buscar sesión…');
    expect(ES.get('cash_register.open.title')).toBe('Abrir sesión de caja');
    expect(ES.get('cash_register.open.balance')).toBe('Fondo de apertura');
    expect(ES.get('cash_register.count.submit')).toBe('Registrar arqueo');
    expect(ES.get('cash_register.close.countedRequired')).toBe('Escribe el efectivo contado para cerrar la sesión.');
    expect(ES.get('cash_register.close.anyway')).toBe('Cerrar de todos modos');
    expect(ES.get('cash_register.review.confirm')).toBe('El turno se cerrará igualmente. Pulsa otra vez para confirmar.');
    expect(ES.get('cash_register.detail.noMovements')).toBe('Sin movimientos en esta sesión.');
    expect(ES.get('cash_register.detail.noCounts')).toBe('Sin arqueos en esta sesión.');
    expect(ES.get('cash_register.settings.saved')).toBe('Ajustes guardados.');
  });
});
