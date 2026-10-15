// The verifactu app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON (as the demo's). This test is their guardrail:
// same keys and placeholders in both languages, nothing empty, every key a page, a component or a
// helper of the app uses exists, and the texts the old screens showed are kept word for word.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import en from './en.json';
import es from './es.json';

type Catalogue = { [key: string]: string | Catalogue };

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), '..');

function flatten(catalogue: Catalogue, prefix = ''): Map<string, string> {
  const out = new Map<string, string>();
  for (const [key, value] of Object.entries(catalogue)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') out.set(path, value);
    else for (const [k, v] of flatten(value, path)) out.set(k, v);
  }
  return out;
}

function placeholders(message: string): string[] {
  return [...new Set([...message.matchAll(/\{(\w+)\}/g)].map((m) => m[1]))].sort();
}

/** The app's sources that may name a key: pages, components, composables and helpers (no tests). */
function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === '__tests__' ? [] : sources(path);
    return /\.(vue|ts)$/.test(entry.name) && !/\.(test|d)\.ts$/.test(entry.name) ? [path] : [];
  });
}

const EN = flatten(en as Catalogue);
const ES = flatten(es as Catalogue);

describe('verifactu catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['verifactu']);
    expect(Object.keys(es)).toEqual(['verifactu']);
  });

  it('have exactly the same keys', () => {
    expect([...ES.keys()].sort()).toEqual([...EN.keys()].sort());
  });

  it('have no empty message', () => {
    for (const [key, message] of [...EN, ...ES]) expect(message.trim(), key).not.toBe('');
  });

  it('keep the same placeholders and plural forms in both languages', () => {
    for (const [key, message] of EN) {
      const spanish = ES.get(key) ?? '';
      expect(placeholders(spanish), key).toEqual(placeholders(message));
      expect(spanish.split('|').length, key).toBe(message.split('|').length);
    }
  });

  it('cover every key the app’s sources use, literal or built from a known prefix', () => {
    const files = sources(FRONTEND);
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      const source = readFileSync(file, 'utf8');
      for (const [, key] of source.matchAll(/\bt\(\s*'(verifactu\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      // `t(`verifactu.status.${status}`)`: the prefix must hold keys.
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(verifactu\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

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
