// The verifactu app's UI texts: English source + Spanish, kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON (as the demo's). This test is their guardrail:
// same keys and placeholders in both languages, nothing empty, every key a page, a component or a
// helper of the app uses exists, and the texts the old screens showed are kept word for word.
import { describe, expect, it } from 'vitest';

import { appCatalogues, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('verifactu', en, es);
const { EN, ES } = CATALOGUES;

describe('verifactu catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms' });

  it('name every status, record type, environment, severity and event type the server knows', () => {
    for (const status of ['pending', 'sent', 'accepted', 'accepted_with_errors', 'rejected']) expect(EN.has(`verifactu.status.${status}`), status).toBe(true);
    for (const type of ['alta', 'anulacion']) expect(EN.has(`verifactu.recordType.${type}`), type).toBe(true);
    for (const env of ['testing', 'production']) expect(EN.has(`verifactu.env.${env}`), env).toBe(true);
    for (const severity of ['debug', 'info', 'warning', 'error', 'critical']) expect(EN.has(`verifactu.severity.${severity}`), severity).toBe(true);
    for (const state of ['none', 'submitted', 'approved', 'returned', 'revoked']) expect(EN.has(`verifactu.config.grant.${state}`), state).toBe(true);
  });

  it('keep the old screens’ words (WORKBOOK «Pantallas»)', () => {
    expect(ES.get('verifactu.records.title')).toBe('Registros VeriFactu');
    expect(ES.get('verifactu.records.search')).toBe('Buscar factura, emisor o NIF…');
    expect(ES.get('verifactu.contingency.title')).toBe('Cola de contingencia');
    expect(ES.get('verifactu.contingency.process')).toBe('Procesar cola');
    expect(ES.get('verifactu.contingency.processing')).toBe('Procesando…');
    expect(ES.get('verifactu.events.title')).toBe('Eventos de auditoría');
    expect(ES.get('verifactu.events.search')).toBe('Buscar tipo o mensaje…');
    expect(ES.get('verifactu.events.empty')).toBe('Sin eventos.');
    expect(ES.get('verifactu.recovery.title')).toBe('Recuperación de cadena');
    expect(ES.get('verifactu.recovery.valid')).toBe('Cadena de huellas íntegra ✓');
    expect(ES.get('verifactu.recovery.unknown')).toBe('Sin validar todavía');
    expect(ES.get('verifactu.recovery.aeatEmpty')).toBe('Sin datos de la AEAT. Pulsa «Consultar AEAT».');
    expect(ES.get('verifactu.recovery.confirm')).toBe('Confirmar recuperación');
    expect(ES.get('verifactu.recovery.done')).toBe('Operación completada.');
    expect(ES.get('verifactu.config.title')).toBe('Configuración de VeriFactu');
    expect(ES.get('verifactu.config.erplora')).toBe('Lo remite ERPlora');
    expect(ES.get('verifactu.settings.goLiveTitle')).toBe('¿Enviar tus facturas a la AEAT de verdad?');
    expect(ES.get('verifactu.settings.backTitle')).toBe('¿Volver al entorno de pruebas?');
    expect(ES.get('verifactu.detail.waitingTitle')).toBe('Aún no está en la AEAT');
    expect(ES.get('verifactu.detail.notStamped')).toBe('Aún sin estampar');
  });
});
